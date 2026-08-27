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

(2026-08-27 추가) 위 규칙기반 비교와 별개로, 렙 1개가 끝날 때마다 그 렙 전체를
DTW(동적 시간 워핑)로 정상 렙 템플릿 20개(app/pose/dtw_templates/*.json)와 비교하는
검사를 추가했다 — 자세한 배경·임곗값 근거는 rules.py의 DTW_NEAREST_DISTANCE_THRESHOLD
주석 참고. 위의 "최근 N프레임" 규칙기반 검사들과 달리 이 검사는 angle_history 전체를
훑어 "가장 최근에 완료된 렙"을 찾아내 그 구간에만 적용된다 — 렙이 아직 안 끝났으면
건너뛴다.
"""

from pathlib import Path

from app.pose.coaching_messages import (
    ASYMMETRY_MESSAGE,
    BACK_ROUNDED_CALIBRATION_MISSING_MESSAGE,
    BACK_ROUNDED_MESSAGE,
    CENTER_OF_MASS_SHIFT_MESSAGE,
    DTW_FORM_MISMATCH_MESSAGE,
    HEEL_LIFT_MESSAGE,
    KNEE_OVER_TOE_MESSAGE,
    KNEE_VALGUS_MESSAGE,
    GAZE_FORWARD_MESSAGE,
)
from app.pose.dtw_matching import (
    DEFAULT_METRIC_FIELDS,
    DTWTemplate,
    TemplateNotFoundError,
    load_templates,
    nearest_normal_distance,
)
from app.pose.rules import (
    BACK_ROUNDING_RATIO_THRESHOLD,
    DTW_NEAREST_DISTANCE_THRESHOLD,
    HEEL_LIFT_RATIO_THRESHOLD,
    KNEE_ASYMMETRY_THRESHOLD_DEG,
    KNEE_OVER_TOE_RATIO_THRESHOLD,
    KNEE_VALGUS_RATIO_THRESHOLD,
    MIN_DTW_REP_FRAMES,
    NORMAL_RANGES,
    SHOULDER_FORWARD_LEAN_THRESHOLD_DEG,
    TORSO_SHIN_LEAN_GAP_THRESHOLD_DEG,
    personalized_hip_range,
)
from app.schemas import AngleFrame, HipFlexibilityCalibration

# TODO: 팀 확정 필요 — 아래 임계값들은 실제 사용자 테스트 전까지의 초안값이다.
MIN_FRAMES = 3  # 판정에 필요한 최소 프레임 수. 너무 적으면 노이즈에, 너무 많으면 반응 지연에 취약.
STATIC_SLOPE_THRESHOLD_DEG_PER_SEC = 15.0  # 이보다 느린 변화율은 "정지(holding)"로 간주.
JITTER_STD_THRESHOLD_DEG = 10.0  # 프레임 간 각도 변화량의 표준편차가 이 값을 넘으면 "불안정한 움직임".
DEEP_MARGIN_DEG = 15.0  # 동작 중 정상범위 하한보다 이 값 이상 더 굽혀지면 "과도한 굽힘(위험)"으로 판단.
STANDING_KNEE_ANGLE_MIN = 150.0  # 이 이상이면 "선 자세(하단이 아님)"로 보고, 정지 상태의 하단 자세 검사를 건너뜀.

# app/pose/dtw_templates/*.json이 있는 디렉토리. 이 파일(app/coaching/realtime.py) 기준
# 상대경로로 잡아, 배포 환경에서 작업 디렉토리가 달라져도 항상 같은 위치를 가리키게 한다.
DTW_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "pose" / "dtw_templates"

# 템플릿 20개는 요청마다 새로 읽지 않고 프로세스당 한 번만 읽어 캐싱한다 — 파일 읽기
# 자체는 가볍지만(JSON 20개), 실시간 엔드포인트는 프레임마다 호출되므로 굳이 매번
# 디스크 I/O를 반복할 이유가 없다. None은 "아직 안 읽음"과 "읽어봤는데 비어있음"을
# 구분할 수 있는 값이 필요해서가 아니라(load_templates는 없으면 빈 리스트를 반환),
# 단순히 "최초 1회만 로드"를 표시하는 용도다.
_dtw_templates_cache: list[DTWTemplate] | None = None


def _get_dtw_templates() -> list[DTWTemplate]:
    global _dtw_templates_cache
    if _dtw_templates_cache is None:
        _dtw_templates_cache = load_templates(DTW_TEMPLATES_DIR)
    return _dtw_templates_cache


def _extract_last_completed_rep(angle_history: list[AngleFrame]) -> list[AngleFrame] | None:
    """angle_history 안에서 가장 최근에 "완료된" 렙(무릎각도가 STANDING_KNEE_ANGLE_MIN
    아래로 내려갔다가 다시 그 이상으로 올라온 구간)을 찾아 그 프레임들만 잘라 반환한다.

    ml_training/build_dtw_templates.py의 cut_reps()와 동일한 저점 기준
    (STANDING_KNEE_ANGLE_MIN=150.0, cut_reps의 STANDING_KNEE_ANGLE_DEG와 같은 값)을
    그대로 재사용한다 — 쿼리와 템플릿이 서로 다른 기준으로 잘리면 DTW 비교 자체가
    일관성을 잃는다.

    아직 렙이 안 끝났거나(히스토리가 깊게 앉은 채로 끝남), 애초에 깊게 앉은 적이 없으면
    None을 반환해 호출하는 쪽이 DTW 비교를 건너뛰게 한다.
    """
    knee = [f.knee_angle for f in angle_history]
    n = len(knee)

    # 뒤에서부터 훑어 "선 자세로 다시 올라온" 경계(그 프레임 자체가 STANDING_KNEE_ANGLE_MIN
    # 이상, 바로 앞 프레임은 미만)를 렙의 끝으로 본다.
    end = None
    for i in range(n - 1, 0, -1):
        if knee[i] >= STANDING_KNEE_ANGLE_MIN and knee[i - 1] < STANDING_KNEE_ANGLE_MIN:
            end = i
            break
    if end is None:
        return None

    # end 이전 구간에서 "150도 아래로 처음 내려간" 프레임(그 프레임 자체는 미만, 바로
    # 앞 프레임은 이상)을 렙의 시작으로 본다 — ml_training/build_dtw_templates.py의
    # cut_reps()가 렙을 [처음 미만이 된 프레임, ..., 다시 이상이 된 프레임]으로 자르는
    # 것과 정확히 같은 경계를 잡아야 한다(예를 들어 그 직전의 "서 있는" 프레임까지
    # 포함시키면 템플릿에는 없는 여분의 프레임이 쿼리에만 더해져 비교 기준이 어긋난다).
    start = None
    for i in range(end - 1, 0, -1):
        if knee[i] < STANDING_KNEE_ANGLE_MIN and knee[i - 1] >= STANDING_KNEE_ANGLE_MIN:
            start = i
            break
    if start is None:
        # 히스토리 맨 앞부터 이미 깊게 앉아있던 경우 — 렙 시작점이 히스토리 범위 밖이라
        # 정확한 시작점을 알 수 없다. 완전히 버리지 않고 히스토리 시작을 시작점으로 써서
        # 잘린 렙이라도 비교는 시도한다(다소 부정확할 수 있음을 인지한 트레이드오프).
        start = 0

    rep = angle_history[start : end + 1]
    if len(rep) < MIN_DTW_REP_FRAMES:
        return None
    return rep


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
    # 에러 처리를 하지 않고 계속 호출할 수 있게 하기 위함. 이건 사용자에게 코칭할 "문제"가
    # 아니라 세션이 막 시작해 데이터가 덜 쌓인 것뿐이라, 별도 문구 없이 낮은 confidence만
    # 반환한다(하네스 AI-07이 신뢰도 낮음을 이미 판단 근거로 쓴다).
    if len(angle_history) < MIN_FRAMES:
        return {
            "phase": "holding",
            "is_normal": True,
            "confidence": round(len(angle_history) / MIN_FRAMES * 0.3, 2),
            "issues": [],
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
    # 무게중심(상체가 정강이보다 얼마나 더 기울었는지) — 측면 랜드마크 기준, knee_over_toe와
    # 동일하게 정면 카메라 여부와 무관한 선택 필드다(rules.py의
    # TORSO_SHIN_LEAN_GAP_THRESHOLD_DEG 주석 참고 — 나쁜 사례 표본이 2건뿐인 잠정 신호).
    latest_torso_shin_lean_gap = angle_history[-1].torso_shin_lean_gap_deg  # 선택 필드라 None일 수 있음

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
        # 목/시선(고개가 앞으로 떨어졌는지)은 무릎/엉덩이와 달리 "깊게 앉았을 때"만이 아니라
        # 정지한 어느 시점에서든 확인할 문제라, is_deep_hold 조건 없이 검사한다(상시검사).
        # shoulder_forward_lean_deg가 없으면(하위 호환 — 프론트가 아직 안 보내는 경우) 검사를
        # 건너뛴다. 원래 이 신호는 "어깨 말림"도 같이 판정했으나, 어깨 말림/등 굽음은 원인을
        # "등이 굽었다"로 단정해 아래 back_rounded(등 굽음) 판정으로 통합했다 — 그쪽은
        # is_deep_hold 조건이 있어 여기와 달리 상시검사가 아니다(트레이드오프로 수용).
        if latest_shoulder_forward_lean is not None and latest_shoulder_forward_lean > SHOULDER_FORWARD_LEAN_THRESHOLD_DEG:
            issues.append(
                {
                    "part": "gaze",
                    "message": GAZE_FORWARD_MESSAGE,
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
        # (2026-08-27 폐기) 여기 있던 "고관절 과신전 의심"(latest_knee_valgus가
        # KNEE_VALGUS_RATIO_THRESHOLD 이상 ~ 1.1 미만이면 별도 태깅) 로직은 근거 부족으로
        # 폐기했다 — 자세한 배경은 rules.py의 HIP_HYPEREXTENSION_VALGUS_THRESHOLD 자리에
        # 남은 주석 참고. knee_valgus_ratio가 KNEE_VALGUS_RATIO_THRESHOLD 이상(무릎이 발목
        # 너비 이상으로 벌어진 상태, varus 방향)이면 이제 아무 이슈도 태깅하지 않는다.
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
        # 무게중심도 무릎-발끝과 같은 이유로 "깊게 앉아 멈춘 상태"에서만 검사한다 — 동작
        # 중(내려가는/올라오는 도중)에는 상체-정강이 기울기 차이가 과도기적으로 커질 수 있다.
        if (
            is_deep_hold
            and latest_torso_shin_lean_gap is not None
            and latest_torso_shin_lean_gap > TORSO_SHIN_LEAN_GAP_THRESHOLD_DEG
        ):
            issues.append({"part": "center_of_mass", "message": CENTER_OF_MASS_SHIFT_MESSAGE})
        # 등 굽음도 같은 이유로 "깊게 앉아 멈춘 상태"에서만 검사한다 — 기준값
        # (hip_calibration.standing_shoulder_hip_ratio)이 없으면(캘리브레이션을 안 한 기존
        # 클라이언트) 검사 자체를 건너뛴다.
        back_rounding_baseline = (
            hip_calibration.standing_shoulder_hip_ratio if hip_calibration is not None else None
        )
        # 등 굽음 판정은 "등 굽음"과 "어깨 말림"을 하나의 원인("등이 굽었다")으로 묶어서
        # 알려준다 — 원래 어깨 말림 전용이었던 shoulder_forward_lean_deg 상시검사를 대체한다.
        if (
            is_deep_hold
            and latest_torso_length_ratio is not None
            and back_rounding_baseline is not None
            and latest_torso_length_ratio < back_rounding_baseline * BACK_ROUNDING_RATIO_THRESHOLD
        ):
            issues.append({"part": "back_rounded", "message": BACK_ROUNDED_MESSAGE})
        elif is_deep_hold and latest_torso_length_ratio is not None and back_rounding_baseline is None:
            # 캘리브레이션이 없어 기준값 자체가 없는 경우 — 조용히 건너뛰지 않고, 왜 이
            # 검사가 빠졌는지 알려준다(어깨 말림까지 여기로 흡수된 뒤로는 이 검사가 하는
            # 역할이 커져서, 조용한 스킵보다 명시적 안내가 낫다고 판단).
            issues.append({"part": "data", "message": BACK_ROUNDED_CALIBRATION_MISSING_MESSAGE})
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

    # --- (1.5) DTW 렙 패턴 유사도 판정 ---
    # 위 (1)/(2)는 "현재 순간"만 보는 규칙기반 판정이라 phase에 따라 갈라지지만, 이 검사는
    # 그와 독립적으로 angle_history 전체를 훑어 "가장 최근에 완료된 렙"을 찾아 그 렙
    # 하나를 정상 렙 템플릿 20개와 통째로 비교한다 — 그래서 phase 분기 밖, 이 함수
    # 어디서 호출해도 상관없는 위치에 둔다. 자세한 배경은 이 파일 상단 docstring과
    # rules.py의 DTW_NEAREST_DISTANCE_THRESHOLD 주석 참고.
    rep_frames = _extract_last_completed_rep(angle_history)
    if rep_frames is not None:
        try:
            templates = _get_dtw_templates()
            nearest, _all_distances = nearest_normal_distance(
                rep_frames, templates, metric_fields=DEFAULT_METRIC_FIELDS
            )
            if nearest.distance > DTW_NEAREST_DISTANCE_THRESHOLD:
                issues.append({"part": "form_pattern", "message": DTW_FORM_MISMATCH_MESSAGE})
        except (ValueError, TemplateNotFoundError):
            # ValueError: 이 렙 프레임 중 하나라도 DEFAULT_METRIC_FIELDS(선택 필드인
            # torso_length_ratio/shoulder_forward_lean_deg 포함)가 없는 경우 —
            # 다른 선택 필드 검사들과 동일하게 조용히 건너뛴다(하위 호환).
            # TemplateNotFoundError: 템플릿 디렉토리가 비어있는 개발/테스트 환경 —
            # 이 경우도 검사를 건너뛴다(운영 배포본에는 템플릿 20개가 항상 커밋돼 있다).
            pass

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
