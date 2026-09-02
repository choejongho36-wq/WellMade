"""
하네스 오케스트레이션 (AI-07).

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
선택해도 이 함수가 실제로 RAG를 호출하지는 않는다(AI-08/09가 아직 구현 전이기도 하고, API
명세상 `/ai/orchestrate`는 { nextAction, reasoning }만 돌려주는 결정 엔드포인트다). 실제
액션 실행은 이 응답을 받은 백엔드/프론트가 담당한다.

"""

from typing import Optional

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


def _tool(name: str, description: str, extra_properties: Optional[dict] = None) -> dict:
    """
    도구(tool) 스키마를 만드는 헬퍼 — 지금은 실제로 호출하는 곳이 없다(아래 HARNESS_TOOLS는
    참고용 문서로만 남아있음, 이유는 모듈 docstring 참고). 예전 LLM Tool Use 시절 스키마
    형태를 그대로 남겨둔 이유는, 각 액션의 부가 인자(action_args) 구조를 이 형태로 보는 게
    가장 명확하기 때문이다.
    """
    properties = {"reasoning": {"type": "string", "description": "이 액션을 선택한 이유(한국어, 1~2문장)"}}
    if extra_properties:
        properties.update(extra_properties)
    return {
        "toolSpec": {
            "name": name,
            "description": description,
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": properties,
                    "required": ["reasoning"],
                }
            },
        }
    }


# (2026-08-31) 이 모듈은 이제 LLM을 전혀 호출하지 않는다. 아래 HARNESS_TOOLS·
# HARNESS_SYSTEM_PROMPT는 어떤 코드도 참조하지 않는 순수 참고 문서다 — 액션별 부가 인자
# (action_args) 구조와 H-01~H-06 판단 규칙을 한눈에 보여주는 자료로서 가치가 있어 남겨둔다.
# schemas.py의 NextAction Literal과 이름을 맞춰야 하는 것도 여전히 유효하다.
#
# 요구사항 정의서 "2.하네스판단로직" 시트의 "선택 가능 액션" 컬럼을 그대로 도구화한 것.
# H-01과 H-03에 둘 다 등장하는 "재분석"은 같은 도구(request_reanalysis)로 합쳤다 — 둘 다
# "지금 확정하지 말고 몇 프레임 더 본다"는 같은 의미의 액션이기 때문.
HARNESS_TOOLS = [
    _tool(
        "request_retake",
        "관절 인식 신뢰도(visibility)가 너무 낮아 판정 자체가 불가능한 상태(H-01). "
        "사용자에게 카메라 각도/조명/거리를 조정해 다시 촬영하도록 안내한다.",
    ),
    _tool(
        "request_reanalysis",
        "판정 신뢰도(confidence)가 낮지만 재촬영까지는 필요 없는 상태(H-01, H-03). "
        "다음 N프레임을 추가로 관찰해 신뢰도가 안정되는지 다시 판단한다.",
    ),
    _tool(
        "proceed",
        "신뢰도가 충분하고 특별한 이상 신호가 없어 정상적으로 판정을 계속 진행해도 되는 상태.",
    ),
    _tool(
        "recommend_expert_consultation",
        "골반 비대칭 등 의학적으로 민감할 수 있는 소견이 반복 감지된 상태(H-02). "
        "AI는 의학적으로 확정 진단을 내리지 않고(Human-in-the-loop 원칙), "
        "전문가(의사/물리치료사 등) 상담을 권장하는 안내만 제공한다.",
    ),
    _tool(
        "hold_judgment",
        "민감 소견이 감지됐지만 아직 확정 판단도 전문가 상담 권장도 이르다고 판단되는 상태(H-02). "
        "추가 확인 없이는 어느 쪽으로도 단정하지 않고 판단을 보류한다.",
    ),
    _tool(
        "wait_next_frame",
        "실시간 코칭 중 판정 신뢰도가 낮아(H-03) 확정 피드백을 주기엔 이르지만, "
        "곧 다음 프레임에서 안정될 가능성이 높아 별도 안내 없이 조용히 다음 프레임을 기다리는 상태.",
    ),
    _tool(
        "use_generic_guidance",
        "실시간 코칭 중 판정 신뢰도가 계속 낮은 상태(H-03)라, 특정 부위를 지목하는 확정 피드백 "
        "대신 '자세를 천천히 유지해주세요' 같은 일반적인 안내로 대체한다.",
    ),
    _tool(
        "trigger_rag_search",
        "동일한 이상 소견이 3회 이상 반복 감지된 상태(H-04). 매번 호출하면 불필요한 API 비용이 "
        "발생하므로, 반복성이 확인된 시점에만 RAG 검색(AI-08/AI-09, 자동 조치가이드)을 호출한다.",
        extra_properties={
            "search_query": {
                "type": "string",
                "description": "RAG 검색에 사용할 쿼리(예: '무릎 모임 교정 스트레칭')",
            }
        },
    ),
    _tool(
        "prefer_latest_document",
        "RAG 검색 결과가 2건 이상이고 내용이 서로 상충하는 상태(H-05). "
        "문서 메타데이터(작성일) 비교 후 가장 최신 지침을 우선 채택한다.",
    ),
    _tool(
        "refine_query_and_research",
        "RAG 검색 결과가 상충하는데(H-05) 어느 문서가 최신인지도 불분명하거나 신뢰하기 어려운 "
        "상태. 쿼리를 더 구체화해서 재검색한다.",
        extra_properties={
            "refined_query": {"type": "string", "description": "구체화된 재검색 쿼리"}
        },
    ),
    _tool(
        "end_session",
        "정상판정 비율/지속시간이 세션 종료 조건(AI-13)에 도달했거나, 사용자가 직접 종료를 "
        "요청한 상태(H-06). 세션을 종료하고 세션 리포트 생성(AI-12)을 트리거한다.",
        extra_properties={
            "end_reason": {
                "type": "string",
                "enum": ["target_sustained", "user_requested"],
                "description": "종료 사유 — 리포트 문구의 톤을 사유에 따라 다르게 생성할 때 쓰인다(AI-12, 확정 필요)",
            }
        },
    ),
]

HARNESS_SYSTEM_PROMPT = """당신은 운동 자세 코칭 앱 "WellMade"의 AI 하네스(오케스트레이터)입니다.
정해진 순서대로 움직이는 파이프라인이 아니라, 매 순간 주어지는 상황 정보(신뢰도, 감지된
소견, 지속시간, 검색 결과 상태 등)를 보고 다음에 어떤 행동을 취할지 스스로 결정해야 합니다.

반드시 아래 판단 규칙을 근거로, 제공된 도구(tool) 중 정확히 하나를 선택해서 호출하세요.
자유 텍스트로만 답하지 말고 항상 도구를 호출해야 합니다.

[판단 규칙]
- H-01 (정지 자세 판정 신뢰도 낮음): 관절 visibility < 0.6 또는 판정 confidence < 70% 이면,
  visibility가 특히 낮다면 재촬영(request_retake)을, 그 정도는 아니면 재분석
  (request_reanalysis)을 선택하세요. 둘 다 문제 없으면 proceed.
- H-02 (골반 비대칭 등 민감 소견 반복 감지): 좌우 골반 높이차가 임계치를 초과하고 3회 이상
  반복 감지됐다면, 절대 스스로 확정 진단을 내리지 마세요(Human-in-the-loop 원칙). 확신이
  들 만큼 근거가 충분하면 recommend_expert_consultation, 아직 이르다고 판단되면
  hold_judgment를 선택하세요.
- H-03 (실시간 코칭 판정 신뢰도 낮음): 동작 분류 confidence < 65% 이면, 낮은 신뢰도로 확정
  피드백을 주지 마세요. 곧 안정될 것 같으면 wait_next_frame, 계속 불안정하면
  use_generic_guidance, 재관찰이 필요하면 request_reanalysis를 선택하세요.
- H-04 (이상 자세 반복 감지): 동일 이상 소견이 3회 이상 반복되면 trigger_rag_search를
  선택하세요. 반복이 확인되지 않았는데 미리 호출하면 불필요한 비용이 발생하니 피하세요.
- H-05 (RAG 검색결과 다수/상충): 검색된 문서가 2건 이상이고 내용이 상충하면, 최신 문서를
  신뢰할 수 있으면 prefer_latest_document, 그렇지 않으면 refine_query_and_research를
  선택하세요.
- H-06 (세션 종료 조건 충족): 정상판정 비율/지속시간이 목표에 도달했거나 사용자가 직접
  종료를 요청했으면 end_session을 선택하고, end_reason을 상황에 맞게 지정하세요.

여러 규칙 조건이 동시에 해당될 수 있습니다 — 그중 사용자에게 가장 중요하고 시급한 것
하나를 우선순위로 판단하세요(예: 세션 종료 조건과 낮은 신뢰도가 동시에 감지되면, 세션
종료가 사용자 경험상 더 우선입니다). 어느 규칙에도 해당하지 않으면 proceed를 선택하세요.
"""


def _fallback_decision(context: dict) -> dict:
    """
    하네스의 실제 판단 로직(2026-08-31부터 유일한 경로 — 더 이상 "폴백"이 아니라 이게
    본체다. 함수 이름은 과거 LLM 시절의 흔적으로 그대로 남겨뒀다).

    위 HARNESS_SYSTEM_PROMPT의 [판단 규칙]을 그대로 if/elif로 옮긴 것. 이 엔드포인트는
    실시간 코칭 흐름 중간에 반복 호출될 수 있는데, 입력이 이미 정제된 숫자/불리언 값이라
    임계값 비교만으로 결정이 완결되므로 LLM 호출 없이도 안전하고 빠르게 판단할 수 있다.
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
