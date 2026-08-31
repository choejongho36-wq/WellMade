"""
스쿼트 세션 리포트 통계 집계.

책임:
- 세션 전체 반복 횟수 계산
- 정상/이상 반복 횟수 계산
- 이상 유형별 발생 횟수 계산
- 정상 자세 비율 계산
- 이전 세션 대비 변화량 계산
- 반복별 판정 타임라인 데이터 생성

이 모듈에서는 LLM을 호출하지 않는다.
숫자와 구조화된 데이터만 계산한다.
"""

from collections import Counter
from typing import Any


def aggregate_session_statistics(
    frame_history: list[dict[str, Any]],
    previous_sessions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    세션 프레임/반복 판정 데이터를 리포트용 통계로 집계한다.

    frame_history 예시:

    [
        {
            "rep": 1,
            "is_normal": True,
            "issues": [],
        },
        {
            "rep": 2,
            "is_normal": False,
            "issues": [
                {
                    "type": "knee_valgus",
                    "message": "무릎이 안쪽으로 모이고 있어요."
                }
            ],
        },
    ]
    """

    previous_sessions = previous_sessions or []

    total_reps = len(frame_history)

    normal_reps = sum(
        1
        for frame in frame_history
        if frame.get("is_normal") is True
    )

    abnormal_reps = total_reps - normal_reps

    normal_ratio = (
        round(normal_reps / total_reps * 100)
        if total_reps > 0
        else 0
    )

    issue_counter: Counter[str] = Counter()

    rep_timeline: list[dict[str, Any]] = []

    for index, frame in enumerate(frame_history, start=1):
        issues = frame.get("issues") or []

        issue_types: list[str] = []

        for issue in issues:
            issue_type = (
                issue.get("type")
                or issue.get("code")
                or issue.get("name")
            )

            if issue_type:
                issue_counter[issue_type] += 1
                issue_types.append(issue_type)

        rep_number = frame.get("rep", index)

        rep_timeline.append(
            {
                "rep": rep_number,
                "is_normal": frame.get("is_normal", True),
                "issues": issue_types,
            }
        )

    issue_counts = dict(issue_counter)

    previous_normal_ratio = None

    if previous_sessions:
        previous = previous_sessions[-1]

        previous_normal_ratio = previous.get(
            "normal_ratio"
        )

    normal_ratio_delta = None

    if previous_normal_ratio is not None:
        normal_ratio_delta = (
            normal_ratio - previous_normal_ratio
        )

    most_frequent_issue = None

    if issue_counter:
        most_frequent_issue = issue_counter.most_common(1)[0][0]

    return {
        "total_reps": total_reps,
        "normal_reps": normal_reps,
        "abnormal_reps": abnormal_reps,
        "normal_ratio": normal_ratio,
        "previous_normal_ratio": previous_normal_ratio,
        "normal_ratio_delta": normal_ratio_delta,
        "issue_counts": issue_counts,
        "most_frequent_issue": most_frequent_issue,
        "rep_timeline": rep_timeline,
    }