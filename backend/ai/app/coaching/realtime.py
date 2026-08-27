"""
실시간 코칭 판정 (AI-06).

프레임마다 딥러닝을 새로 돌리는 대신, "최근 N프레임 동안 각도가 어떻게 변했는가"를
기준 프로파일(rules.py의 NORMAL_RANGES)과 비교하는 패턴매칭 방식으로 구현했다.
이렇게 설계한 이유:
1) 실시간(수십 ms 이내) 응답이 필요한데, 규칙기반 비교는 연산량이 거의 없어
   매 프레임 호출해도 서버 부하가 생기지 않는다.
2) 스쿼트처럼 "내려갔다 올라오는" 단순 반복 동작은 각도의 증가/감소 "방향"만으로도
   동작 단계를 충분히 구분할 수 있어, 별도 학습 데이터(Kaggle 관절각도 시계열 등은
   기준 프로파일을 잡을 때 참고자료로만 활용) 없이도 합리적인 판정이 가능하다.
"""

from app.pose.coaching_messages import (
    ASYMMETRY_MESSAGE,
    BACK_ROUNDED_MESSAGE,
    HEEL_LIFT_MESSAGE,
    HIP_HYPEREXTENSION_MESSAGE,
    KNEE_OVER_TOE_MESSAGE,
    KNEE_VALGUS_MESSAGE,
    SHOULDER_FORWARD_LEAN_MESSAGE,
)
from app.pose.rules import (
    BACK_ROUNDING_RATIO_THRESHOLD,
    HEEL_LIFT_RATIO_THRESHOLD,
    HIP_HYPEREXTENSION_VALGUS_THRESHOLD,
    KNEE_ASYMMETRY_THRESHOLD_DEG,
    KNEE_OVER_TOE_RATIO_THRESHOLD,
    KNEE_VALGUS_RATIO_THRESHOLD,
    NORMAL_RANGES,
    SHOULDER_FORWARD_LEAN_THRESHOLD_DEG,
    personalized_hip_range,
)
from app.schemas import AngleFrame, HipFlexibilityCalibration

# TODO: 팀 확정 필요 — 아래 임계값들은 실제 사용자 테스트 전까지의 초안값이다.
MIN_FRAMES = 3  # 판정에 필요한 최소 프레임 수. 너무 적으면 노이즈에, 너무 많으면 반응 지연에 취약.
STATIC_SLOPE_THRESHOLD_DEG_PER_SEC = 15.0  # 이보다 느린 변화율은 "정지(holding)"로 간주.
JITTER_STD_THRESHOLD_DEG = 10.0  # 프레임 간 각도 변화량의 표준편차가 이 값을 넘으면 "불안정한 움직임".
DEEP_MARGIN_DEG = 15.0  # 동작 중 정상범위 하한보다 이 값 이상 더 굽혀지면 "과도한 굽힘(위험)"으로 판단.
STANDING_KNEE_ANGLE_MIN = 150.0  # 이 이상이면 "선 자세(하단이 아님)"로 보고, 정지 상태의 하단 자세 검사를 건너뜀.


def _linear_fit(xs: list[float], ys: list[float]) -> tuple[float, float]:
    """
    최소제곱법으로 1차 직선(y = slope*x + intercept)을 구하고 (slope, r_squared)를 반환한다.

    왜 (마지막값-첫값)/시간차 같은 단순 계산 대신 회귀를 쓰는가?
    - 프레임 하나하나는 카메라·자세추정 노이즈로 흔들릴 수 있는데, 첫/끝 프레임만 보면
      그 노이즈에 그대로 휘둘린다. 전체 구간의 추세를 보는 편이 안정적이다.
    - r_squared(적합도)는 "이 구간이 얼마나 일관되게 한 방향으로 움직였는가"를 나타내므로,
      그대로 신뢰도(confidence) 계산에 활용할 수 있다 (추세가 들쭉날쭉하면 신뢰도를 낮춤).
    """
    n = len(xs)
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n

    ss_xx = sum((x - mean_x) ** 2 for x in xs)
    if ss_xx == 0:
        # 모든 timestamp가 동일한 비정상 입력 → 변화를 계산할 수 없으므로 기울기 0으로 처리.
        return 0.0, 0.0

    ss_xy = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    slope = ss_xy / ss_xx
    intercept = mean_y - slope * mean_x

    ss_tot = sum((y - mean_y) ** 2 for y in ys)
    if ss_tot == 0:
        # 각도가 프레임 내내 완전히 동일 → 완벽한 "정지" 상태이므로 적합도를 1로 처리.
        return slope, 1.0

    ss_res = sum((y - (slope * x + intercept)) ** 2 for x, y in zip(xs, ys))
    r_squared = max(0.0, 1.0 - ss_res / ss_tot)
    return slope, r_squared


def _std_dev(values: list[float]) -> float:
    """프레임 간 각도 변화량의 표준편차. 값이 크면 "떨림/불안정한 움직임"으로 본다."""
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    variance = sum((v - mean) ** 2 for v in values) / len(values)
    return variance**0.5


def judge_realtime_coaching(
    angle_history: list[AngleFrame],
    hip_calibration: HipFlexibilityCalibration | None = None,
) -> dict:
    """
    최근 N프레임의 무릎/엉덩이 각도 시계열을 보고
    (1) 현재 동작 단계, (2) 정상/이상 여부, (3) 신뢰도를 판정한다(스쿼트 전용).

    반환값을 dict로 두는 이유는 main.py가 API 응답으로 감싸기 전, 하네스(AI-07)에서도
    그대로 재사용할 수 있는 순수 값 형태를 유지하기 위함이다.
    """
    issues: list[dict] = []

    # 프레임이 너무 적으면 추세를 신뢰할 수 없다. 예외를 던지는 대신 "정지"로 잠정 판단하고
    # 신뢰도만 낮게 준다 — 세션 시작 직후 프레임이 아직 안 쌓였을 때도 프론트가 매번
    # 에러 처리를 하지 않고 계속 호출할 수 있게 하기 위함.
    if len(angle_history) < MIN_FRAMES:
        return {
            "phase": "holding",
            "is_normal": True,
            "confidence": round(len(angle_history) / MIN_FRAMES * 0.3, 2),
            "issues": [
                {
                    "part": "data",
                    "message": f"판정에 필요한 프레임이 부족합니다 ({len(angle_history)}/{MIN_FRAMES}).",
                }
            ],
        }

    timestamps = [f.timestamp for f in angle_history]
    knee_series = [f.knee_angle for f in angle_history]
    hip_series = [f.hip_angle for f in angle_history]
    # shoulder_angle(절대각도)은 판정에 안 쓰인다 — 아래 shoulder_forward_lean_deg가
    # 대신 담당한다(schemas.py/rules.py 주석 참고).
    latest_shoulder_forward_lean = angle_history[-1].shoulder_forward_lean_deg  # 선택 필드라 None일 수 있음
    latest_heel_lift = angle_history[-1].heel_lift_ratio  # 선택 필드라 None일 수 있음
    # 정면 랜드마크 기반 지표 — 프론트가 정면 카메라도 붙였을 때만 채워진다.
    latest_knee_valgus = angle_history[-1].knee_valgus_ratio  # 선택 필드라 None일 수 있음
    latest_knee_asymmetry = angle_history[-1].knee_asymmetry_deg  # 선택 필드라 None일 수 있음
    # 무릎-발끝 — 측면 랜드마크 기준이라 정면 카메라 여부와 무관하게 선택 필드다.
    latest_knee_over_toe = angle_history[-1].knee_over_toe_ratio  # 선택 필드라 None일 수 있음
    # 등 굽음 — 측면 랜드마크 기준. hip_calibration.standing_shoulder_hip_ratio라는
    # 기준값이 함께 있어야만 실제 판정에 쓰인다(rules.py의 BACK_ROUNDING_RATIO_THRESHOLD 주석 참고).
    latest_torso_length_ratio = angle_history[-1].torso_length_ratio  # 선택 필드라 None일 수 있음

    knee_slope, knee_r2 = _linear_fit(timestamps, knee_series)
    knee_deltas = [b - a for a, b in zip(knee_series, knee_series[1:])]
    jitter = _std_dev(knee_deltas)

    # --- (1) 동작 단계 판정 ---
    # 무릎 각도가 시간에 따라 "감소"하면 굽히는 중(내려감), "증가"하면 펴는 중(올라옴)으로 정의했다.
    # 스쿼트는 하강 시 무릎 각도가 작아지는 방향이라 이 기준을 그대로 쓸 수 있다.
    if knee_slope < -STATIC_SLOPE_THRESHOLD_DEG_PER_SEC:
        phase = "descending"
    elif knee_slope > STATIC_SLOPE_THRESHOLD_DEG_PER_SEC:
        phase = "ascending"
    else:
        phase = "holding"

    latest_knee = knee_series[-1]
    latest_hip = hip_series[-1]
    knee_low, knee_high = NORMAL_RANGES["knee_angle"]
    # hip_angle만 개인별 캘리브레이션으로 바꿔치기한다(knee_angle은 문헌 기준 보편성이 있지만
    # hip_angle은 개인차가 커서 고정값이 부적절함).
    if hip_calibration is not None:
        hip_low, hip_high = personalized_hip_range(hip_calibration)
    else:
        hip_low, hip_high = NORMAL_RANGES["hip_angle"]

    # --- (2) 정상/이상 판정 ---
    # 움직임 자체가 떨리듯 불규칙하면(단순 카메라 노이즈가 아니라 자세가 흔들리는 경우 포함)
    # 동작 단계와 무관하게 이상으로 본다.
    if jitter > JITTER_STD_THRESHOLD_DEG:
        issues.append(
            {
                "part": "movement",
                "message": "움직임이 불안정합니다. 천천히, 일정한 속도로 동작해 주세요.",
            }
        )

    if phase == "holding":
        # "정지" 상태일 때만 정적 자세 기준(NORMAL_RANGES)을 그대로 적용한다.
        # 동작 중(내려감/올라옴)에는 각도가 정상범위 밖을 지나가는 것이 당연하므로 이 기준을 적용하면
        # 오탐(false positive)이 계속 발생한다.
        # 다만 "선 자세로 멈춰 있는 것"까지 하단 자세 기준으로 검사하면 안 되므로,
        # 무릎이 충분히 굽혀진(STANDING_KNEE_ANGLE_MIN 미만) 경우에만 검사한다.
        is_deep_hold = latest_knee < STANDING_KNEE_ANGLE_MIN
        if is_deep_hold and not (knee_low <= latest_knee <= knee_high):
            issues.append(
                {
                    "part": "knee",
                    "message": f"무릎 각도가 {latest_knee:.1f}도로 목표 구간({knee_low}~{knee_high}도)을 벗어난 채 멈춰 있습니다.",
                }
            )
        if is_deep_hold and not (hip_low <= latest_hip <= hip_high):
            issues.append(
                {
                    "part": "hip",
                    "message": f"엉덩이(고관절) 각도가 {latest_hip:.1f}도로 목표 구간({hip_low}~{hip_high}도)을 벗어났습니다.",
                }
            )
        # 어깨 정렬은 무릎/엉덩이와 달리 "깊게 앉았을 때"만이 아니라 정지한 어느 시점에서든
        # 확인할 문제라(어깨가 말리는 건 자세 전반의 문제), is_deep_hold 조건 없이 검사한다.
        # shoulder_forward_lean_deg가 없으면(하위 호환 — 프론트가 아직 안 보내는 경우) 검사를
        # 건너뛴다. (절대각도 기준 shoulder_angle 판정은 실측 오탐이 확인돼
        # shoulder_forward_lean_deg로 교체했다 — rules.py 주석 참고.)
        if latest_shoulder_forward_lean is not None and latest_shoulder_forward_lean > SHOULDER_FORWARD_LEAN_THRESHOLD_DEG:
            issues.append(
                {
                    "part": "shoulder",
                    "message": SHOULDER_FORWARD_LEAN_MESSAGE,
                }
            )
        # 발뒤꿈치 뜸도 knee/hip과 같은 이유로 "깊게 앉아 멈춘 상태"에서만 검사한다 — 서 있는
        # 상태에서는 애초에 발뒤꿈치가 뜰 이유가 없어 검사 대상이 아니고, 동작 중(내려감/올라옴)에
        # 순간적으로 값이 흔들리는 걸 이상으로 잡으면 오탐이 늘어난다(rules.py 주석 참고).
        if is_deep_hold and latest_heel_lift is not None and latest_heel_lift > HEEL_LIFT_RATIO_THRESHOLD:
            issues.append({"part": "heel", "message": HEEL_LIFT_MESSAGE})
        # 무릎 모임/좌우 비대칭도 발뒤꿈치와 같은 이유로 "깊게 앉아 멈춘 상태"에서만 검사한다
        # (rules.py 주석 참고). 정면 카메라를 아직 안 붙인 프론트는 이 필드를
        # 안 보내므로(None) 자동으로 검사가 건너뛰어진다 — 하위 호환.
        if is_deep_hold and latest_knee_valgus is not None and latest_knee_valgus < KNEE_VALGUS_RATIO_THRESHOLD:
            issues.append({"part": "knee_valgus", "message": KNEE_VALGUS_MESSAGE})
        # 고관절 과신전 의심 — knee_valgus와 같은 latest_knee_valgus 값을
        # 재사용하되 더 완만한 구간에서만 별도로 태깅한다. latest_knee_valgus가
        # KNEE_VALGUS_RATIO_THRESHOLD보다 작으면 위에서 이미 "knee_valgus"로 판정되므로,
        # 여기서는 그 값 이상이면서 HIP_HYPEREXTENSION_VALGUS_THRESHOLD 미만인 구간만 잡아
        # 두 이슈가 중복 태깅되지 않게 한다(자세한 배경·근거는 rules.py의
        # HIP_HYPEREXTENSION_VALGUS_THRESHOLD 주석 참고).
        if (
            is_deep_hold
            and latest_knee_valgus is not None
            and KNEE_VALGUS_RATIO_THRESHOLD <= latest_knee_valgus < HIP_HYPEREXTENSION_VALGUS_THRESHOLD
        ):
            issues.append({"part": "hip_hyperextension", "message": HIP_HYPEREXTENSION_MESSAGE})
        if (
            is_deep_hold
            and latest_knee_asymmetry is not None
            and latest_knee_asymmetry > KNEE_ASYMMETRY_THRESHOLD_DEG
        ):
            issues.append({"part": "asymmetry", "message": ASYMMETRY_MESSAGE})
        # 무릎-발끝도 발뒤꿈치와 같은 이유로 "깊게 앉아 멈춘 상태"에서만 검사한다 — 동작
        # 중(내려가는/올라오는 도중)에는 무릎이 발끝을 순간적으로 넘는 게 자연스러울 수 있다.
        if (
            is_deep_hold
            and latest_knee_over_toe is not None
            and latest_knee_over_toe > KNEE_OVER_TOE_RATIO_THRESHOLD
        ):
            issues.append({"part": "knee_over_toe", "message": KNEE_OVER_TOE_MESSAGE})
        # 등 굽음도 같은 이유로 "깊게 앉아 멈춘 상태"에서만 검사한다 — 기준값
        # (hip_calibration.standing_shoulder_hip_ratio)이 없으면(캘리브레이션을 안 한 기존
        # 클라이언트) 검사 자체를 건너뛴다.
        back_rounding_baseline = (
            hip_calibration.standing_shoulder_hip_ratio if hip_calibration is not None else None
        )
        if (
            is_deep_hold
            and latest_torso_length_ratio is not None
            and back_rounding_baseline is not None
            and latest_torso_length_ratio < back_rounding_baseline * BACK_ROUNDING_RATIO_THRESHOLD
        ):
            issues.append({"part": "back_rounded", "message": BACK_ROUNDED_MESSAGE})
    else:
        # 동작 중에는 "정상범위 하한보다 훨씬 더 굽혀지는" 과도한 굽힘만 위험 신호로 본다.
        # (무릎에 부담이 되는 과도한 가동범위는 동작 단계와 무관하게 바로 감지해야 하기 때문)
        if latest_knee < knee_low - DEEP_MARGIN_DEG:
            issues.append(
                {
                    "part": "knee",
                    "message": f"무릎을 너무 깊게 굽혔습니다 ({latest_knee:.1f}도). 무릎 부담이 커질 수 있습니다.",
                }
            )

    # --- (3) 신뢰도 계산 ---
    # 하네스(AI-07)가 "confidence < 0.7이면 재분석"을 판단하는 근거가 되므로,
    # 단순 True/False가 아니라 연속값으로 반환한다.
    #
    # descending/ascending일 때는 "한 방향으로 얼마나 일관되게 움직였는가"(r_squared)가
    # 곧 판정 신뢰도이지만, holding일 때는 정의상 기울기가 거의 0이라 r_squared가
    # (추세가 없다는 이유만으로) 낮게 나온다 — "정지"라는 판정 자체와는 무관한 수치이므로
    # 그대로 곱하면 오히려 신뢰도를 왜곡한다. 그래서 holding은 "떨림이 적을수록 신뢰도가
    # 높다"는 별도 기준을 쓴다.
    jitter_penalty = min(1.0, jitter / JITTER_STD_THRESHOLD_DEG)
    if phase == "holding":
        confidence = 1.0 - jitter_penalty
    else:
        confidence = knee_r2 * (1.0 - 0.5 * jitter_penalty)
    confidence = max(0.0, min(1.0, confidence))

    return {
        "phase": phase,
        "is_normal": len(issues) == 0,
        "confidence": round(confidence, 2),
        "issues": issues,
    }
