"""
세션 종료 조건 판단 (AI-13).

기획 문서 기준: "정상판정 비율이 임계치 이상인 상태가 목표 시간 이상 지속되거나,
사용자가 직접 종료 → 세션 자동 종료".

이 로직을 규칙기반으로 구현한 이유는 rules.py와 동일하다 — "정상 비율 X% 이상이
Y분 지속되면 종료"는 별도 학습 없이도 명확하게 정의할 수 있는 조건이고, 판정 근거를
사용자에게 그대로 설명할 수 있어야 하기 때문이다(예: "70% 이상 3분 유지해서 종료됐어요").

설계에서 중요한 선택 하나: "세션 시작부터 지금까지 전체 평균 정상 비율"이 아니라,
"최근 목표 시간(TARGET_DURATION_SEC) 동안의 정상 비율"만 본다. 세션 초반에 자세를
못 잡아서 비율이 낮았더라도 최근에 계속 잘하고 있다면 종료 조건을 만족해야 하고,
반대로 초반에 우연히 잘해서 전체 평균이 높아도 최근에 흐트러졌다면 아직 끝내면 안
되기 때문이다. 즉 "지속(sustained)"이라는 단어를 전체 누적이 아니라 트레일링 윈도우로
해석했다.
"""

from app.schemas import JudgmentRecord

# NOTE: MVP 잠정치 — 데이터가 쌓이는 대로 사용자 신고 기반 액티브러닝으로 조정할 예정.
TARGET_NORMAL_RATIO = 0.7
TARGET_DURATION_SEC = 180


def judge_session_end(
    judgment_history: list[JudgmentRecord],
    user_requested_end: bool = False,
) -> dict:
    """
    누적된 프레임별 정상/이상 판정 이력을 보고, 지금 세션을 종료해도 되는지 판단한다.

    반환값을 dict로 두는 이유는 다른 규칙기반 모듈(rules.py, coaching/realtime.py)과
    동일 — main.py의 응답 스키마와 분리해서, 나중에 하네스(AI-07)나 세션 리포트(AI-12)
    에서도 이 함수를 그대로 재사용할 수 있게 하기 위함이다.
    """
    # 사용자가 직접 종료 버튼을 눌렀으면 다른 조건은 볼 필요가 없다 — 항상 최우선.
    if user_requested_end:
        return {
            "should_end": True,
            "reason": "user_requested",
            "normal_ratio": 0.0,
            "window_duration_sec": 0.0,
        }

    if not judgment_history:
        # 판정 이력이 아예 없는 상태(세션이 막 시작됨)에서 호출된 경우.
        # 예외를 던지지 않고 "아직 진행 중"으로 처리하는 이유는 coaching/realtime.py의
        # "프레임 부족" 처리와 같다 — 호출부가 매번 별도 에러 처리를 하지 않아도 되게 함.
        return {
            "should_end": False,
            "reason": "no_data",
            "normal_ratio": 0.0,
            "window_duration_sec": 0.0,
        }

    # 가장 최근 시각 기준으로 "최근 TARGET_DURATION_SEC초" 구간만 잘라낸다.
    # (오래된 판정은 지금 상태를 대표하지 못하므로 트레일링 윈도우 방식을 씀 — 위 docstring 참고)
    latest_ts = judgment_history[-1].timestamp
    window_start = latest_ts - TARGET_DURATION_SEC
    window = [record for record in judgment_history if record.timestamp >= window_start]

    window_duration = latest_ts - window[0].timestamp if window else 0.0
    normal_ratio = sum(1 for record in window if record.is_normal) / len(window)

    if window_duration < TARGET_DURATION_SEC:
        # 아직 목표 시간만큼 데이터가 쌓이지 않았다 — 지금까지의 비율은 참고용으로만 반환하고,
        # 종료 조건 자체는 만족할 수 없다고 판단한다 (짧은 구간의 우연한 고비율로 조기 종료되는
        # 것을 방지).
        return {
            "should_end": False,
            "reason": "in_progress",
            "normal_ratio": round(normal_ratio, 2),
            "window_duration_sec": round(window_duration, 1),
        }

    should_end = normal_ratio >= TARGET_NORMAL_RATIO
    return {
        "should_end": should_end,
        "reason": "target_sustained" if should_end else "in_progress",
        "normal_ratio": round(normal_ratio, 2),
        "window_duration_sec": round(window_duration, 1),
    }
