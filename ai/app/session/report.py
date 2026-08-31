"""
AI-12 세션 리포트 생성.

세션 종료 후 실시간 스쿼트 판정 결과를 집계하고,
집계된 수치를 기반으로 사용자에게 보여줄 세션 요약 문구를 생성한다.

처리 순서:

1. 실시간 판정 결과 집계
   - 정상 자세 비율
   - 평균 편차
   - 이상 부위별 발생 횟수
   - 가장 자주 발생한 이상 부위
   - 직전 세션 대비 변화량
   - 권장 운동 빈도

2. 집계 결과를 기반으로 자연어 요약 생성
   - Bedrock LLM 사용
   - LLM 사용 불가/실패 시 규칙 기반 fallback

AI 서버는 세션 상태를 저장하지 않는다.
현재 세션 데이터와 이전 세션 데이터는 호출부에서 전달받는다.
"""

import os
from typing import Optional

try:
    import boto3

    _BOTO3_AVAILABLE = True
except ImportError:
    _BOTO3_AVAILABLE = False


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

AWS_REGION_ENV_VAR = "AWS_BEDROCK_REGION"
MODEL_ENV_VAR = "SESSION_REPORT_BEDROCK_MODEL_ID"

MAX_TOKENS = 400


# ---------------------------------------------------------------------------
# Labels
# ---------------------------------------------------------------------------

# realtime.py / rules.py에서 반환하는 PoseIssue.part 값과 일치해야 한다.
PART_LABELS = {
    "knee": "무릎",
    "hip": "엉덩이(고관절)",
    "gaze": "시선/고개",
    "back_rounded": "등(자세)",
    "movement": "움직임 안정성",
    "data": "판정 데이터",
    "hip_hyperextension": "고관절 과신전",
}


# ---------------------------------------------------------------------------
# Exercise Frequency
# ---------------------------------------------------------------------------

# 정상 자세 비율에 따른 권장 운동 빈도.
#
# TODO:
# 실제 사용자 테스트 이후 임계값과 문구를 팀에서 확정한다.
FREQUENCY_THRESHOLDS = [
    (
        0.8,
        "지금처럼 주 3회 정도만 꾸준히 유지해도 좋아요.",
    ),
    (
        0.5,
        "주 3~4회 연습하면서 자세를 조금 더 다듬어보는 걸 권장해요.",
    ),
    (
        0.0,
        "주 4~5회, 천천히 기본 자세부터 다시 잡아보는 걸 권장해요.",
    ),
]


# ---------------------------------------------------------------------------
# Bedrock
# ---------------------------------------------------------------------------


def _get_client():
    """
    Bedrock Runtime client를 필요할 때 생성한다.

    AWS 리전이 설정되지 않았거나 boto3가 설치되지 않은 경우
    None을 반환하여 fallback으로 처리한다.
    """

    if not _BOTO3_AVAILABLE:
        return None

    region = os.environ.get(AWS_REGION_ENV_VAR)

    if not region:
        return None

    return boto3.client(
        "bedrock-runtime",
        region_name=region,
    )


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------


def _recommended_frequency_message(
    normal_ratio: float,
) -> str:
    """
    정상 자세 비율에 따른 권장 운동 빈도를 반환한다.
    """

    for threshold, message in FREQUENCY_THRESHOLDS:
        if normal_ratio >= threshold:
            return message

    # 안전망
    return FREQUENCY_THRESHOLDS[-1][1]


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------


def aggregate_session_stats(
    frame_history: list[dict],
    previous_sessions: list[dict],
) -> dict:
    """
    세션 판정 결과를 리포트용 통계로 집계한다.

    이 함수에서는 LLM을 호출하지 않는다.
    모든 값은 전달받은 판정 데이터만으로 계산한다.

    frame_history 예시:

    [
        {
            "is_normal": True,
            "issues": [],
        },
        {
            "is_normal": False,
            "issues": [
                {
                    "part": "knee",
                    "deviation_deg": 8.2,
                }
            ],
        },
    ]
    """

    # -----------------------------------------------------------------------
    # 기본 세션 통계
    # -----------------------------------------------------------------------

    total = len(frame_history)

    normal_count = sum(
        1
        for frame in frame_history
        if frame.get("is_normal") is True
    )

    normal_ratio = (
        normal_count / total
        if total > 0
        else 0.0
    )

    # -----------------------------------------------------------------------
    # 이상 판정 수집
    # -----------------------------------------------------------------------

    all_issues = [
        issue
        for frame in frame_history
        for issue in frame.get("issues", [])
    ]

    # -----------------------------------------------------------------------
    # 평균 편차
    # -----------------------------------------------------------------------

    deviations = [
        issue["deviation_deg"]
        for issue in all_issues
        if issue.get("deviation_deg") is not None
    ]

    avg_deviation_deg = (
        round(
            sum(deviations) / len(deviations),
            1,
        )
        if deviations
        else None
    )

    # -----------------------------------------------------------------------
    # 부위별 이상 발생 횟수
    # -----------------------------------------------------------------------

    part_counts: dict[str, int] = {}

    for issue in all_issues:
        part = issue.get("part")

        if not part:
            continue

        part_counts[part] = (
            part_counts.get(part, 0) + 1
        )

    # 가장 자주 발생한 이상 부위
    most_frequent_issue_part = (
        max(
            part_counts,
            key=part_counts.get,
        )
        if part_counts
        else None
    )

    # -----------------------------------------------------------------------
    # 직전 세션과 비교
    # -----------------------------------------------------------------------

    improvement_vs_previous_pct = None

    if previous_sessions:
        # previous_sessions는 호출부가 시간순으로 전달한다고 전제한다.
        previous = previous_sessions[-1]

        previous_ratio = previous.get(
            "normal_ratio"
        )

        if previous_ratio is not None:
            improvement_vs_previous_pct = round(
                (normal_ratio - previous_ratio) * 100,
                1,
            )

    # -----------------------------------------------------------------------
    # 최종 통계
    # -----------------------------------------------------------------------

    return {
        "total_reps": total,
        "normal_reps": normal_count,
        "abnormal_reps": total - normal_count,
        "normal_ratio": round(
            normal_ratio,
            2,
        ),
        "avg_deviation_deg": avg_deviation_deg,
        "most_frequent_issue_part": (
            most_frequent_issue_part
        ),
        "issue_counts_by_part": part_counts,
        "improvement_vs_previous_pct": (
            improvement_vs_previous_pct
        ),
        "recommended_frequency_message": (
            _recommended_frequency_message(
                normal_ratio
            )
        ),
    }


# ---------------------------------------------------------------------------
# Fallback Summary
# ---------------------------------------------------------------------------


def _fallback_summary_message(
    stats: dict,
    session_duration_sec: float,
) -> str:
    """
    LLM 호출이 불가능하거나 실패했을 때 사용하는
    규칙 기반 요약 문구.

    전달받은 통계만 사용하므로
    근거 없는 내용을 생성하지 않는다.
    """

    minutes = round(
        session_duration_sec / 60,
        1,
    )

    parts = [
        (
            f"오늘 약 {minutes}분 동안 운동하셨고, "
            f"전체 동작 중 "
            f"{stats['normal_ratio'] * 100:.0f}%가 "
            "정상 자세였어요."
        )
    ]

    # 가장 자주 발생한 이상 부위
    if stats["most_frequent_issue_part"]:
        label = PART_LABELS.get(
            stats["most_frequent_issue_part"],
            stats["most_frequent_issue_part"],
        )

        parts.append(
            f"가장 자주 감지된 부분은 {label}이었어요."
        )

    # 직전 세션 비교
    improvement = stats[
        "improvement_vs_previous_pct"
    ]

    if improvement is not None:
        if improvement > 0:
            parts.append(
                f"직전 세션보다 정상 자세 비율이 "
                f"{improvement:.1f}%p 올랐어요."
            )

        elif improvement < 0:
            parts.append(
                f"직전 세션보다 정상 자세 비율이 "
                f"{abs(improvement):.1f}%p 낮아졌어요."
            )

        else:
            parts.append(
                "직전 세션과 비슷한 수준을 유지했어요."
            )

    # 권장 운동 빈도
    parts.append(
        stats["recommended_frequency_message"]
    )

    return " ".join(parts)


# ---------------------------------------------------------------------------
# LLM Summary
# ---------------------------------------------------------------------------


def _generate_llm_summary(
    stats: dict,
    session_duration_sec: float,
    client,
) -> Optional[str]:
    """
    집계된 세션 통계를 Bedrock LLM에 전달하여
    자연어 코칭 요약을 생성한다.

    원본 프레임 데이터는 LLM에 전달하지 않는다.
    """

    model_id = os.environ.get(
        MODEL_ENV_VAR
    )

    if not model_id:
        return None

    issue_part = (
        PART_LABELS.get(
            stats["most_frequent_issue_part"],
            stats["most_frequent_issue_part"],
        )
        if stats["most_frequent_issue_part"]
        else "없음"
    )

    system_prompt = (
        "당신은 운동 자세 코칭 앱 WellMade의 "
        "세션 리포트 작성기입니다. "
        "아래에 제공되는 집계 수치만 근거로 삼아 "
        "사용자의 오늘 스쿼트 세션을 요약하세요. "
        "한국어 해요체를 사용하고, "
        "3~4문장 정도로 작성하세요. "
        "사용자를 격려하되 과장하지 마세요. "
        "제공된 수치에 없는 사실이나 의학적 진단, "
        "부상 위험 등을 절대 지어내지 마세요."
    )

    user_message = (
        "[세션 집계 수치]\n"
        f"- 총 동작 수: {stats['total_reps']}회\n"
        f"- 정상 자세: {stats['normal_reps']}회\n"
        f"- 이상 자세: {stats['abnormal_reps']}회\n"
        f"- 정상 자세 비율: "
        f"{stats['normal_ratio'] * 100:.0f}%\n"
        f"- 세션 시간: "
        f"{round(session_duration_sec / 60, 1)}분\n"
        f"- 평균 편차: "
        f"{stats['avg_deviation_deg']}도\n"
        f"- 가장 자주 감지된 부위: {issue_part}\n"
        f"- 부위별 이상 횟수: "
        f"{stats['issue_counts_by_part']}\n"
        f"- 직전 세션 대비 변화: "
        f"{stats['improvement_vs_previous_pct']}%p\n"
        f"- 권장 운동 빈도: "
        f"{stats['recommended_frequency_message']}"
    )

    try:
        response = client.converse(
            modelId=model_id,
            system=[
                {
                    "text": system_prompt,
                }
            ],
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "text": user_message,
                        }
                    ],
                }
            ],
            inferenceConfig={
                "maxTokens": MAX_TOKENS,
            },
        )

        content = (
            response["output"]
            ["message"]
            ["content"]
        )

        text_blocks = [
            block["text"]
            for block in content
            if "text" in block
        ]

        generated = "".join(
            text_blocks
        ).strip()

        return generated or None

    except Exception:
        # LLM 오류가 세션 종료 자체를 막지 않도록
        # 상위에서 fallback으로 전환한다.
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_session_report(
    frame_history: list[dict],
    session_duration_sec: float,
    previous_sessions: Optional[list[dict]] = None,
    client=None,
) -> dict:
    """
    AI-12 세션 리포트 생성의 메인 진입점.

    처리 순서:

    1. 세션 통계 집계
    2. LLM 자연어 요약 시도
    3. 실패하면 규칙 기반 fallback
    """

    previous_sessions = (
        previous_sessions or []
    )

    # 1. 통계 집계
    stats = aggregate_session_stats(
        frame_history=frame_history,
        previous_sessions=previous_sessions,
    )

    # 2. fallback 문구를 항상 준비
    fallback_message = _fallback_summary_message(
        stats=stats,
        session_duration_sec=session_duration_sec,
    )

    # 3. Bedrock client 준비
    active_client = (
        client
        if client is not None
        else _get_client()
    )

    # 4. LLM 요약 시도
    if active_client is not None:
        generated = _generate_llm_summary(
            stats=stats,
            session_duration_sec=session_duration_sec,
            client=active_client,
        )

        if generated:
            return {
                **stats,
                "summary_message": generated,
                "generation_source": "llm",
            }

    # 5. LLM 실패 → fallback
    return {
        **stats,
        "summary_message": fallback_message,
        "generation_source": "fallback",
    }