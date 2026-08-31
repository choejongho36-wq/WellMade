"""
세션 리포트 생성 (AI-12).

# TODO: 팀 확정 필요 — 요구사항 정의서 ID 불일치를 또 하나 발견했다. AI-07 때와
# 같은 문제: "1.AI모듈상세"·"2.하네스판단로직"·"5.AI_API명세" 기준으로는 AI-12가 "세션 리포트
# 생성"이지만, "8.요구사항정의서" 시트에서는 같은 기능이 AI-08로, AI-12는 완전히 다른 기능
# ("세션 다시보기" — 영상을 클라이언트 IndexedDB에 저장하는 기능, AI 서버 책임 범위 밖)으로
# 쓰여 있다. 이 모듈은 지금까지와 동일하게 "1.AI모듈상세" 기준(AI-12=세션 리포트)으로
# 구현했다 — 팀이 ID 체계를 통일해야 한다.

요구사항 정의서가 명시한 2단계 구조를 그대로 따른다:
① 통계 집계(평균 편차, 개선률 계산) — 규칙기반.
② 집계 결과를 LLM에 전달해 자연어 코칭 문구 생성 — "제안안, 팀 확정 필요"라고 명시돼 있어
   그대로 반영했다.

①을 규칙기반으로 하는 이유는 rules.py/termination.py와 동일하다: 평균·비율 계산은 학습이
필요 없는 명확한 산술이고, 이 결과가 그대로 ②단계 LLM 프롬프트의 "근거 수치"가 되어야
하네스(harness.py)·RAG 생성(generation.py)에서 지켜온 "수치/문서에 없는 내용은 지어내지
않는다"는 원칙을 여기서도 지킬 수 있다. ②가 LLM 호출 불가/실패 시 규칙기반 폴백 문구로
대체되는 것도 harness.py/generation.py와 같은 이유(하나의 LLM 호출 실패가 세션 종료
경험을 끊으면 안 됨)다.

이 모듈도 AI 서버 전체의 무상태(stateless) 원칙을 따른다 — "최근 N회 세션 이력"을 서버가
직접 들고 있지 않고, 호출부(백엔드)가 이전 세션 요약을 함께 넘겨주면 그걸로 비교만 한다.
"""

import os
from typing import Optional

try:
    import boto3

    _BOTO3_AVAILABLE = True
except ImportError:
    _BOTO3_AVAILABLE = False

AWS_REGION_ENV_VAR = "AWS_BEDROCK_REGION"
# (2026-08-31) 원래는 harness.py/generation.py와 HARNESS_BEDROCK_MODEL_ID를 공유했다. 하네스가
# 완전히 규칙기반으로 바뀌고(LLM 미사용) RAG 생성도 별도 변수(RAG_GENERATION_BEDROCK_MODEL_ID)로
# 분리되면서, 사실상 이 모듈(AI-12 세션 리포트) 전용 변수가 됐다 — 이름도 그에 맞게 바꿨다.
MODEL_ENV_VAR = "SESSION_REPORT_BEDROCK_MODEL_ID"
MAX_TOKENS = 400

# 이상 부위(part) 코드를 사람이 읽는 한국어로 바꾸는 매핑. rules.py/coaching/realtime.py가
# 반환하는 PoseIssue.part 값과 반드시 일치해야 한다.
PART_LABELS = {
    "knee": "무릎",
    "hip": "엉덩이(고관절)",
    "gaze": "시선/고개",
    "back_rounded": "등(자세)",
    "movement": "움직임 안정성",
    "data": "판정 데이터",
    # (2026-08-28 추가, 2026-08-28 같은 날 폐기) "hip_hyperextension_frontal": "고관절
    # 과신전(정면)" 라벨이 이 자리에 있었다 — 정면 카메라 기반 판정 자체가 폐기됐다
    # (checklist 2026-08-28 addendum 참고). "hip_hyperextension"(측면 DTW+LLM
    # 하이브리드)만 남는다.
    # (2026-08-28 추가) 측면 DTW+LLM 하이브리드(coaching/realtime.py (1.45) 블록,
    # app/coaching/hyperextension_llm_check.py, HIP_HYPEREXTENSION_LLM_MESSAGE)가
    # 반환하는 part 값 — 위 정면 버전과 달리 실제 시상면 신호를 LLM이 직접 본 판정이다.
    "hip_hyperextension": "고관절 과신전",
}

# 정상 비율에 따른 권장 운동 빈도 — 요구사항 정의서 예시("부족 시 권장 빈도 문구")를
# 구체적인 규칙으로 구현한 초안.
# TODO: 팀 확정 필요 — 실제 사용자 테스트 후 임계값/문구 조정.
FREQUENCY_THRESHOLDS = [
    (0.8, "지금처럼 주 3회 정도만 꾸준히 유지해도 좋아요."),
    (0.5, "주 3~4회 연습하면서 자세를 조금 더 다듬어보는 걸 권장해요."),
    (0.0, "주 4~5회, 천천히 기본 자세부터 다시 잡아보는 걸 권장해요."),
]


def _get_client():
    """harness.py/generation.py와 동일한 지연 생성 패턴(boto3 bedrock-runtime)."""
    if not _BOTO3_AVAILABLE:
        return None
    region = os.environ.get(AWS_REGION_ENV_VAR)
    if not region:
        return None
    return boto3.client("bedrock-runtime", region_name=region)


def _recommended_frequency_message(normal_ratio: float) -> str:
    for threshold, message in FREQUENCY_THRESHOLDS:
        if normal_ratio >= threshold:
            return message
    return FREQUENCY_THRESHOLDS[-1][1]  # 안전망 — 이론상 도달 불가(마지막 threshold가 0.0이므로)


def aggregate_session_stats(frame_history: list[dict], previous_sessions: list[dict]) -> dict:
    """
    ① 통계 집계 단계. 프레임별 판정 이력을 요약 수치로 압축한다.

    dict를 입/출력으로 쓰는 이유는 다른 규칙기반 모듈(rules.py, termination.py)과 동일 —
    main.py의 Pydantic 응답 스키마와 분리해, 이 함수 자체를 가볍게 재사용/테스트할 수 있게
    하기 위함.
    """
    total = len(frame_history)
    normal_count = sum(1 for f in frame_history if f["is_normal"])
    normal_ratio = normal_count / total if total else 0.0

    all_issues = [issue for f in frame_history for issue in f.get("issues", [])]

    deviations = [i["deviation_deg"] for i in all_issues if i.get("deviation_deg") is not None]
    avg_deviation_deg = round(sum(deviations) / len(deviations), 1) if deviations else None

    # part_counts는 "가장 빈번한 부위" 계산에도 쓰이고, issue_counts_by_part로 그대로
    # 응답에 실어 보내 프론트가 부위별 이상 발생 빈도 막대그래프를 그릴 수 있게 한다
    # (2026-08-31 추가 — 통계 리포트 그래프 예시 논의에서 나온 요청).
    part_counts: dict[str, int] = {}
    for issue in all_issues:
        part_counts[issue["part"]] = part_counts.get(issue["part"], 0) + 1
    most_frequent_issue_part = max(part_counts, key=part_counts.get) if part_counts else None

    improvement_vs_previous_pct = None
    if previous_sessions:
        # "최근 N회 세션 이력" 중 가장 최근 것(리스트의 마지막 원소를 최신으로 간주)과 비교한다.
        # 무엇이 "가장 최근"인지는 호출부가 이미 시간순으로 정렬해 보낸다고 전제한다
        # (judgment_history/angle_history 등 다른 엔드포인트도 동일한 "정렬은 호출부 책임" 관례를 따름).
        previous_ratio = previous_sessions[-1]["normal_ratio"]
        improvement_vs_previous_pct = round((normal_ratio - previous_ratio) * 100, 1)

    return {
        "normal_ratio": round(normal_ratio, 2),
        "avg_deviation_deg": avg_deviation_deg,
        "most_frequent_issue_part": most_frequent_issue_part,
        "issue_counts_by_part": part_counts,
        "improvement_vs_previous_pct": improvement_vs_previous_pct,
        "recommended_frequency_message": _recommended_frequency_message(normal_ratio),
    }


def _fallback_summary_message(stats: dict, session_duration_sec: float) -> str:
    """LLM 없이도 항상 만들 수 있는 템플릿 기반 요약 문구. harness.py의 _fallback_decision과
    같은 역할 — 집계된 수치를 그대로 문장으로 옮기기만 해서, 지어낸 내용이 섞일 위험이
    전혀 없는 가장 안전한 폴백이다."""
    minutes = round(session_duration_sec / 60, 1)
    parts = [f"오늘 약 {minutes}분 동안 운동하셨고, 전체 동작 중 {stats['normal_ratio'] * 100:.0f}%가 정상 자세였어요."]

    if stats["most_frequent_issue_part"]:
        label = PART_LABELS.get(stats["most_frequent_issue_part"], stats["most_frequent_issue_part"])
        parts.append(f"가장 자주 감지된 부분은 {label}이었어요.")

    if stats["improvement_vs_previous_pct"] is not None:
        diff = stats["improvement_vs_previous_pct"]
        if diff > 0:
            parts.append(f"직전 세션보다 정상 자세 비율이 {diff:.1f}%p 올랐어요.")
        elif diff < 0:
            parts.append(f"직전 세션보다 정상 자세 비율이 {abs(diff):.1f}%p 낮아졌어요.")
        else:
            parts.append("직전 세션과 비슷한 수준을 유지했어요.")

    parts.append(stats["recommended_frequency_message"])
    return " ".join(parts)


def generate_session_report(
    frame_history: list[dict],
    session_duration_sec: float,
    previous_sessions: Optional[list[dict]] = None,
    client=None,
) -> dict:
    """
    세션 리포트 생성의 메인 진입점. ①집계 → ②자연어 요약 생성을 순서대로 수행한다.
    """
    previous_sessions = previous_sessions or []
    stats = aggregate_session_stats(frame_history, previous_sessions)
    fallback_message = _fallback_summary_message(stats, session_duration_sec)

    active_client = client if client is not None else _get_client()
    model_set = bool(os.environ.get(MODEL_ENV_VAR))

    if active_client is not None and model_set:
        system_prompt = (
            "당신은 운동 자세 코칭 앱 WellMade의 세션 리포트 작성기입니다. "
            "아래 [집계 수치]만 근거로 삼아, 사용자에게 오늘 세션을 요약해주는 3~4문장의 "
            "따뜻하고 격려하는 톤의 한국어 문구를 작성하세요. 수치에 없는 내용(예: 구체적인 "
            "부상 위험, 확정 진단)은 절대 지어내지 마세요."
        )
        user_message = (
            f"[집계 수치]\n"
            f"- 정상 자세 비율: {stats['normal_ratio'] * 100:.0f}%\n"
            f"- 세션 시간: {round(session_duration_sec / 60, 1)}분\n"
            f"- 가장 자주 감지된 부위: {PART_LABELS.get(stats['most_frequent_issue_part'], '없음') if stats['most_frequent_issue_part'] else '없음'}\n"
            f"- 평균 편차: {stats['avg_deviation_deg']}도\n"
            f"- 직전 세션 대비 변화: {stats['improvement_vs_previous_pct']}%p\n"
            f"- 권장 빈도: {stats['recommended_frequency_message']}"
        )
        try:
            response = active_client.converse(
                modelId=os.environ[MODEL_ENV_VAR],
                system=[{"text": system_prompt}],
                messages=[{"role": "user", "content": [{"text": user_message}]}],
                inferenceConfig={"maxTokens": MAX_TOKENS},
            )
            content = response["output"]["message"]["content"]
            text_blocks = [block["text"] for block in content if "text" in block]
            generated = "".join(text_blocks).strip()
            if generated:
                return {**stats, "summary_message": generated, "generation_source": "llm"}
        except Exception:  # noqa: BLE001 — harness.py/generation.py와 동일하게 폭넓게 처리 후 폴백
            pass

    return {**stats, "summary_message": fallback_message, "generation_source": "fallback"}
