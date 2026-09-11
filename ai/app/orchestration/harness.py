"""
하네스 오케스트레이션 (AI-07).

ID 표기 확정(2026-09-02): 요구사항정의서 "1.AI모듈상세"·"2.하네스판단로직"·"5.AI_API명세"
(POST /ai/orchestrate) 시트 기준 AI-07로 쓴다. "8.요구사항정의서" 시트가 같은 번호를 세션
종료 판단(AI-13)에 재사용하는 건 그 시트 쪽 오기로 보고 따르지 않는다 — 이 모듈은 앞으로도
계속 AI-07로 표기한다.

요구사항 정의서(`실시간운동코칭_AI요구사항정의서_v2.xlsx`, 시트 "2.하네스판단로직")의
판단 포인트 H-01~H-06을 규칙기반(if/elif)으로 구현한다.

(2026-08-31) 원래는 이 판단을 LLM Tool Use(Function Calling)로 구현했었다 — "여러 신호를
종합해서 판단해야 하는 문제라 조건문을 계속 늘리는 방식으로는 관리가 어렵다"는 이유였다.
그런데 실제로 이 하네스가 받는 입력(confidence, landmark_visibility, issue_repeat_count,
pelvis_height_diff_deg 등)은 전부 이미 정제된 숫자/불리언 값이라, 아래 [판단 규칙]을 그대로
옮긴 임계값 비교(_fallback_decision)만으로도 결정이 완결된다는 게 확인됐다. 게다가 이
엔드포인트(/ai/orchestrate)는 실시간 코칭 흐름 중 반복 호출될 것으로 예상돼, 결정마다 LLM
호출의 비용·지연·실패 위험을 감수할 이득이 크지 않다고 판단해 완전히 규칙기반으로
되돌렸다(판단 근거는 Claude 프로젝트의 2026-08-31 addendum-5/6/7 문서 참고). reasoning
문구도 이제 아래 _fallback_decision()에 하드코딩된 한국어 템플릿이 전부다 — 문구를 바꾸고
싶으면 그 함수의 문자열을 직접 수정하면 된다.

이 모듈이 "실행"이 아니라 "결정"만 한다는 점은 여전히 유효하다: trigger_rag_search를
선택해도 이 함수가 실제로 RAG를 호출하지는 않는다(RAG 검색/생성 코드(AI-08/09)는 2026-09-02에 이 스코프에서 삭제되기도 했고, API
명세상 `/ai/orchestrate`는 { nextAction, reasoning }만 돌려주는 결정 엔드포인트다). 실제
액션 실행은 이 응답을 받은 백엔드/프론트가 담당한다.

"""

# H-02(골반 비대칭)는 요구사항 정의서에 "임계치 초과"라고만 적혀있고 구체적인 도(度) 값이
# 없다. 자세 비교 인사이트(AI-15/AI-04, app/insight/posture_percentile.py)에서 실측정한
# 세종시 데이터의 골반 기울기 중앙값이 절대값 기준 1도 안팎이었던 걸 참고해, "그보다 뚜렷하게
# 큰 차이"라는 의미로 3.0도를 잠정값으로 둔다.
# NOTE: MVP 잠정치 — 데이터가 쌓이는 대로 사용자 신고 기반 액티브러닝으로 조정할 예정.
PELVIS_ASYMMETRY_THRESHOLD_DEG = 3.0
ISSUE_REPEAT_THRESHOLD = 3  # H-02, H-04 공통: "3회 이상 반복"

# H-01/H-03 신뢰도 임계값 — 요구사항 정의서에 명시된 값 그대로.
VISIBILITY_THRESHOLD = 0.6  # H-01
STATIC_CONFIDENCE_THRESHOLD = 0.70  # H-01 (정지 자세 판정)
REALTIME_CONFIDENCE_THRESHOLD = 0.65  # H-03 (실시간 코칭 판정)


def _fallback_decision(context: dict) -> dict:
    """
    하네스의 실제 판단 로직(2026-08-31부터 유일한 경로 — 더 이상 "폴백"이 아니라 이게
    본체다. 함수 이름은 과거 LLM 시절의 흔적으로 그대로 남겨뒀다).

    요구사항 정의서 "2.하네스판단로직" 시트의 판단 규칙(H-01~H-06)을 그대로 if/elif로
    옮긴 것. 이 엔드포인트는 실시간 코칭 흐름 중간에 반복 호출될 수 있는데, 입력이 이미
    정제된 숫자/불리언 값이라 임계값 비교만으로 결정이 완결되므로 LLM 호출 없이도 안전하고
    빠르게 판단할 수 있다.
    """
    visibility = context.get("landmark_visibility")
    confidence = context.get("confidence")
    issue_type = context.get("issue_type")
    issue_repeat_count = context.get("issue_repeat_count") or 0
    pelvis_diff = context.get("pelvis_height_diff_deg")
    session_end_met = context.get("session_end_condition_met")
    user_requested_end = context.get("user_requested_end")
    rag_result_count = context.get("rag_result_count") or 0
    rag_conflicting = context.get("rag_results_conflicting")

    # 우선순위: 세션 종료 > 민감 소견 > 신뢰도 낮음 > RAG 상충 > 반복 이상 소견 > 진행
    # (시스템 프롬프트의 "가장 시급한 것 하나를 우선"이라는 지침과 동일한 순서를 코드로도 유지)
    if user_requested_end:
        return {"next_action": "end_session", "reasoning": "사용자가 직접 종료를 요청했습니다.", "action_args": {"end_reason": "user_requested"}}
    if session_end_met:
        return {"next_action": "end_session", "reasoning": "세션 종료 조건(AI-13)을 충족했습니다.", "action_args": {"end_reason": "target_sustained"}}

    if pelvis_diff is not None and pelvis_diff > PELVIS_ASYMMETRY_THRESHOLD_DEG and issue_repeat_count >= ISSUE_REPEAT_THRESHOLD:
        return {"next_action": "recommend_expert_consultation", "reasoning": f"골반 높이차 {pelvis_diff}도가 {ISSUE_REPEAT_THRESHOLD}회 이상 반복 감지됐습니다.", "action_args": {}}

    if visibility is not None and visibility < VISIBILITY_THRESHOLD:
        return {"next_action": "request_retake", "reasoning": f"관절 인식 신뢰도(visibility={visibility})가 너무 낮습니다.", "action_args": {}}
    if confidence is not None and confidence < STATIC_CONFIDENCE_THRESHOLD:
        return {"next_action": "request_reanalysis", "reasoning": f"판정 신뢰도({confidence})가 낮아 재분석이 필요합니다.", "action_args": {}}

    if rag_result_count >= 2 and rag_conflicting:
        return {"next_action": "refine_query_and_research", "reasoning": "RAG 검색 결과가 상충해 쿼리 재검색이 필요합니다.", "action_args": {}}

    if issue_type and issue_repeat_count >= ISSUE_REPEAT_THRESHOLD:
        return {"next_action": "trigger_rag_search", "reasoning": f"'{issue_type}' 소견이 {issue_repeat_count}회 반복 감지됐습니다.", "action_args": {"search_query": issue_type}}

    return {"next_action": "proceed", "reasoning": "특이 신호가 없어 정상적으로 진행합니다.", "action_args": {}}


def decide_next_action(session_id: str, context: dict) -> dict:
    """
    하네스의 메인 진입점. 상황 정보(context)를 보고 다음 액션을 결정한다.

    (2026-08-31) 완전히 규칙기반으로 동작한다 — LLM 호출은 하지 않는다. next_action과
    reasoning 문구 모두 _fallback_decision()이 결정한 값 그대로 나간다. source/
    fallback_reason 필드는 과거 LLM 판단·reasoning 다듬기 시절의 API 계약을 그대로 유지하기
    위해 남겨뒀고(OrchestrateResponse를 쓰는 다른 곳을 건드리지 않기 위함), 이제는 항상
    같은 값이 나간다.

    session_id는 지금은 쓰이지 않지만, 이 함수가 세션 단위 API(/ai/orchestrate)의 결정
    로직이라는 걸 시그니처에서도 알 수 있게, 그리고 나중에 세션별 로깅 등에 쓸 수 있게
    남겨둔다.
    """
    result = _fallback_decision(context)
    result["source"] = "fallback"
    result["fallback_reason"] = "이 하네스는 항상 규칙기반으로 판단합니다(2026-08-31, LLM 호출 제거)."
    return result
