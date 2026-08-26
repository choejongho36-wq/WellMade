"""
스쿼트 자세 판정에 쓰는 공통 규칙(정상범위 · 임계값 · 개인화 계산).

NORMAL_RANGES/각종 임계값(threshold)/personalized_hip_range()는 실시간 코칭(AI-06,
coaching/realtime.py의 judge_realtime_coaching())이 가져다 쓴다.

"파인튜닝 금지, 규칙기반 우선" 원칙에 따라, 각도 계산 결과를 사전에 정의한 정상 범위
(NORMAL_RANGES)와 비교하는 방식으로 구현했다. 규칙기반을 택한 이유:
1) 스쿼트의 "바른 자세" 각도 기준은 운동/재활 자료에 이미 잘 정리되어 있어, 별도 라벨링
   데이터 없이도 신뢰할 수 있는 규칙을 세울 수 있다.
2) 규칙기반은 판정 근거를 사람이 바로 설명할 수 있어(설명가능성), "왜 이상 자세로
   판정했는지"를 코칭 문구·RAG 검색 쿼리에 그대로 재사용하기 좋다.
"""

from app.schemas import HipFlexibilityCalibration

# 스포츠의학/트레이너 자격 기준 자료를 근거로 한 값.
#
# 주의: 아래 문헌들이 말하는 "무릎 굴곡각(knee flexion angle)"은 다리를 편 상태를 0도로
# 두고 "얼마나 굽혔는지"를 재는 값이라, get_knee_angle()이 계산하는 "관절 내각"(편 상태가
# 180도)과는 서로 보각(180 - 굴곡각) 관계다. 아래 범위는 전부 내각 기준으로 이미 변환해뒀다.
#
# IJSPT(International Journal of Sports Physical Therapy)의 스쿼트 임상 리뷰 논문은 깊이를
# 얕음(굴곡 0~90도) / 평행(90~110도) / 깊음(110~135도)으로 나눈다. 내각 기준 하한/상한(아래
# 30~120도)은 실측 오탐 사례들을 반영해 넓게 잡혀 있다 — 극단적인 이상(전혀 안 앉음 / 무릎에
# 무리가 갈 정도로 과도하게 접음)만 잡고, 정상 범위 안의 깊이 편차는 폭넓게 허용한다.
# 참고: https://ijspt.scholasticahq.com/article/94600-a-biomechanical-review-of-the-squat-exercise-implications-for-clinical-practice
# TODO: 팀 확정 필요 — 30/120은 문헌 기준이 아니라 실측 오탐 방지용 잠정치. 범위가 너무 넓어
# 실제 이상 자세를 놓치는 건 아닌지 실사용자 테스트 후 재검토 필요.
#
# 같은 논문은 엉덩이(고관절) 각도에 대해서는 "개인의 고관절 가동범위가 달라 고정된 정상범위를
# 제시하기 어렵다"고 명시한다. 그래서 hip_angle 범위는 "이 범위를 벗어나면 상체를 과도하게
# 숙이거나 너무 꼿꼿이 세운 상태"라는 느슨한 안전장치로만 쓰고, "이 범위 안 = 완벽한 자세"로
# 해석하지 않는다.
NORMAL_RANGES = {
    "knee_angle": (30, 120),
    "hip_angle": (25, 120),
}

# 개인별 고관절 유연성 캘리브레이션(HipFlexibilityCalibration)이 있을 때, "그 사람이 낼 수
# 있는 최대 가동범위" 중 몇 %~몇 % 구간을 정상으로 볼지 정하는 값. 100%(자기 한계까지)로
# 잡지 않고 70~90%로 여유를 두는 이유는, 캘리브레이션 때 잰 "무리하지 않는 선의 최대치"
# 자체가 이미 안전 마진이 있는 값이라, 실제 운동 중 매 반복을 그 한계까지 밀어붙이면 부상
# 위험이 커지기 때문이다.
# TODO: 팀 확정 필요 — 사용자 테스트 후 조정.
CALIBRATION_LOW_PCT = 0.7
CALIBRATION_HIGH_PCT = 0.9

# 발뒤꿈치가 얼마나 뜨면 이상으로 볼지의 잠정 임계값. get_heel_lift_ratio()가 반환하는 값
# (발 길이 대비 발뒤꿈치-발끝 높이차 비율)과 비교한다. 0.5는 "발뒤꿈치가 발끝보다 발 길이의
# 절반만큼 들렸다"는 뜻으로, 실측 문헌값이 아니라 상식적으로 잡은 잠정치다.
# TODO: 팀 확정 필요 — 실사용자 테스트로 조정.
HEEL_LIFT_RATIO_THRESHOLD = 0.5

# 무릎 사이 너비가 발목 사이 너비의 몇 %보다 좁아지면 무릎 모임(valgus)으로 볼지의 잠정
# 임계값. get_knee_valgus_ratio()가 반환하는 값(무릎너비/발목너비)과 비교한다. 0.8은 "무릎이
# 발목 너비의 80% 미만으로 좁아지면 눈에 띄게 모인 것"이라는 상식적인 잠정치다.
# TODO: 팀 확정 필요 — 실사용자 테스트로 조정.
KNEE_VALGUS_RATIO_THRESHOLD = 0.8

# 고관절 과신전(hip hyperextension) 의심 신호 임계값. get_knee_valgus_ratio()가 반환하는
# 같은 지표를 재해석해 쓴다 — latest_knee_valgus < 0.8이면 이미 "무릎 모임"(knee_valgus)으로
# 판정되므로, 그보다는 크지만 이 값(1.1) 미만인 구간만 "고관절 과신전 의심"으로 별도
# 태깅한다(coaching/realtime.py 판정 로직 참고) — 두 이슈가 중복 태깅되지 않도록 하기 위함.
# TODO: 팀 확정 필요 — N=1 실측 기반 잠정치라 근거가 약함. 무릎 모임과 물리적으로 같은
# 지표를 재해석한 것이므로, 실제로 두 문제를 하나의 지표로 구분할 수 있는지 다른 사람
# 데이터로 추가 검증 필요.
HIP_HYPEREXTENSION_VALGUS_THRESHOLD = 1.1

# 좌우 무릎 굽힘 각도 차이가 몇 도 이상이면 좌우 비대칭(체중 쏠림)으로 볼지의 잠정 임계값.
# get_knee_lr_asymmetry_deg()가 반환하는 값과 비교한다.
# TODO: 팀 확정 필요 — 실사용자 테스트로 조정.
KNEE_ASYMMETRY_THRESHOLD_DEG = 15.0

# 무릎이 발끝보다 얼마나(원시 좌표 거리 기준) 더 나가면 "발끝을 넘었다"고 볼지의 잠정
# 임계값. get_knee_over_toe_ratio()가 반환하는 원시 좌표 거리(MediaPipe 정규화 좌표, 0~1
# 범위)와 비교한다. 0.03은 이미지 너비의 약 3%로, 그 정도까지는 노이즈/정상 가동범위로
# 보고 넘긴다는 취지다(app/pose/angles.py의 get_knee_over_toe_ratio() 참고).
# TODO: 팀 확정 필요 — 실사용자 테스트로 이 값과 "비율 vs 원시 좌표" 방식 자체를 재검토.
KNEE_OVER_TOE_RATIO_THRESHOLD = 0.03

# 어깨 말림(forward head/shoulder rounding) 판정 임계값. get_shoulder_forward_lean_deg()가
# 반환하는 값(목 기울기 - 상체 기울기, 도 단위)과 비교한다. 0 이하는 목이 상체와 비슷하거나
# 더 세워진 정상 자세이므로, 그보다 얼마나 더 커야 진짜 어깨 말림으로 볼지를 정하는 값이다.
# 20.0은 문헌값이 아니라 실측 정상 사례(-29.6도)와 확실히 구분되도록 잡은 잠정치.
# TODO: 팀 확정 필요 — 실제 어깨 말림(양성) 사례로 검증된 적이 없는 잠정치.
SHOULDER_FORWARD_LEAN_THRESHOLD_DEG = 20.0

# 등 굽음(척추 굴곡) 판정 임계값. get_torso_length_ratio()가 반환하는, 어깨-엉덩이 직선거리를
# 발 길이로 정규화한 값과 비교한다. 사람마다 체형(어깨-엉덩이 길이 대 발 길이 비율)이 달라
# 고정된 절대 기준값을 둘 수 없으므로, 온보딩 캘리브레이션
# (HipFlexibilityCalibration.standing_shoulder_hip_ratio, "편하게 서 있을 때" 잰 이 사람의
# 기준 비율) 대비 "몇 % 이상 줄었는지"로 판정한다. 캘리브레이션이 없으면(하위 호환) 이 검사
# 자체를 건너뛴다. 0.85는 "기준값보다 15% 이상 줄어들면 등이 굽었다고 본다"는 뜻.
# TODO: 팀 확정 필요 — 실사용자 테스트로 15%라는 폭 자체를 재검토해야 한다.
BACK_ROUNDING_RATIO_THRESHOLD = 0.85


def personalized_hip_range(calibration: HipFlexibilityCalibration) -> tuple[float, float]:
    """
    캘리브레이션 결과(서 있을 때 각도, 무리 없이 최대한 숙였을 때 각도)로부터
    "이 사람 기준 정상 hip_angle 범위"를 계산한다.

    계산 방식은 "숙인 정도(가동범위)의 70~90% 지점을 정상 구간으로 본다": 자기 최대치의
    90%보다 더 깊이 숙이면 한계에 너무 가까워 위험 신호로, 70%보다 덜 숙이면 아직 목표한
    만큼 자세를 안 잡은 것으로 판정하겠다는 뜻이다.
    """
    available_range = calibration.standing_hip_angle - calibration.max_flex_hip_angle
    # 가동범위가 0 이하(측정값이 잘못 들어온 경우)면 계산이 무의미하므로, 계산을 포기하고
    # 서 있는 각도 자체를 상하한으로 반환해 "항상 범위 밖"으로 처리되게 한다 — 잘못된
    # 캘리브레이션 데이터로 엉뚱하게 "정상"이라고 판정하는 것보다는 안전한 실패 방식이다.
    if available_range <= 0:
        return calibration.standing_hip_angle, calibration.standing_hip_angle

    low = calibration.standing_hip_angle - CALIBRATION_HIGH_PCT * available_range
    high = calibration.standing_hip_angle - CALIBRATION_LOW_PCT * available_range
    return low, high
