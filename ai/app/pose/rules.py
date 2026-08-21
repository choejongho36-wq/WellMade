"""
정지 자세 1차 판정 로직 (AI-03).

"파인튜닝 금지, 규칙기반 우선"이라는 기술 원칙에 따라, 각도 계산 결과를
사전에 정의한 정상 범위(NORMAL_RANGES)와 비교하는 방식으로 구현했다.
딥러닝 분류기 대신 규칙기반을 택한 이유:
1) 스쿼트/런지의 "바른 자세" 각도 기준은 운동/재활 자료에 이미 잘 정리되어 있어,
   별도 라벨링 데이터 없이도 신뢰할 수 있는 규칙을 세울 수 있다.
2) 규칙기반은 판정 근거를 사람이 바로 설명할 수 있어(설명가능성), "왜 이상 자세로
   판정했는지"를 코칭 문구·RAG 검색 쿼리에 그대로 재사용하기 좋다.
"""

from app.pose.angles import (
    get_heel_lift_ratio,
    get_hip_angle,
    get_knee_angle,
    get_knee_lr_asymmetry_deg,
    get_knee_over_toe_ratio,
    get_knee_valgus_ratio,
    get_shoulder_alignment_angle,
)
from app.pose.coaching_messages import (
    ASYMMETRY_MESSAGE,
    HEEL_LIFT_MESSAGE,
    KNEE_OVER_TOE_MESSAGE,
    KNEE_VALGUS_MESSAGE,
)
from app.schemas import HipFlexibilityCalibration, Landmark

# 스포츠의학/트레이너 자격 기준 자료를 근거로 한 값 (2026-08-18 업데이트).
#
# 주의: 아래 문헌들이 말하는 "무릎 굴곡각(knee flexion angle)"은 다리를 편 상태를 0도로
# 두고 "얼마나 굽혔는지"를 재는 값이라, get_knee_angle()이 계산하는 "관절 내각"(편 상태가
# 180도)과는 서로 보각(180 - 굴곡각) 관계다. 아래 범위는 전부 내각 기준으로 이미 변환해뒀다.
#
# [스쿼트]
# IJSPT(International Journal of Sports Physical Therapy)의 스쿼트 임상 리뷰 논문은
# 깊이를 얕음(굴곡 0~90도) / 평행(90~110도) / 깊음(110~135도)으로 나눈다.
# 이걸 내각으로 바꾸면 평행 스쿼트는 70~90도, 깊은(ATG 포함) 스쿼트는 그 아래로도 내려간다.
# 참고: https://ijspt.scholasticahq.com/article/94600-a-biomechanical-review-of-the-squat-exercise-implications-for-clinical-practice
#
# (2026-08-21 변경) 원래는 "대퇴가 바닥과 평행한 지점까지"만 정상으로 잡아(하한 70도),
# 그보다 깊게 앉으면 "이상"으로 판정했다. 그런데 실제 깊은 스쿼트(ATG) 사진(무릎 53도/
# 엉덩이 56도)을 테스트해보니 육안으로는 명백히 정상적인(오히려 좋은 가동범위의) 자세인데
# "이상"으로 잘못 판정되는 문제가 확인됐다. 사용자 확인 후, 깊은 스쿼트도 정상으로 인정하도록
# 하한을 낮췄다(70→50) — "평행보다 얕은" 자세만 이상으로 잡고, 얼마나 깊이 앉는지는 더 이상
# 제한하지 않는다는 뜻. 상한(100도)은 그대로 — 판정이 너무 빡빡해서 정상 동작도 이상으로
# 잡아내는 것을 막기 위한 여유값이라는 원래 취지와 별개로 여전히 유효함.
# TODO: 팀 확정 필요 — 50도라는 새 하한도 문헌 기준 정확한 수치가 아니라, 이번 실측 사례
# (53도)가 걸리지 않도록 여유를 둔 잠정치다. 무릎에 무리가 갈 정도로 극단적인 깊이(예: 완전히
# 쪼그려 앉은 자세)까지 계속 "정상"으로 볼지는 실사용자 테스트 후 재조정이 필요하다.
#
# 같은 논문은 엉덩이(고관절) 각도에 대해서는 "개인의 고관절 가동범위가 다 달라서 고정된
# 정상범위를 제시하기 어렵고, 각자의 가동범위 안에서 척추 중립만 지키면 된다"고 명시한다.
# 즉 hip_angle에 고정 숫자를 넣는 것 자체가 의학적으로 엄밀한 기준은 아니다.
# 그래서 아래 값은 "이 범위를 벗어나면 상체를 과도하게 숙이거나 너무 꼿꼿이 세운
# 상태"라는 느슨한 안전장치(sanity check)로만 쓰고, "이 범위 안 = 완벽한 자세"라고
# 해석하지 않는다. hip_angle 하한도 knee_angle과 같은 이유(2026-08-21)로 낮췄다(60→45) —
# 깊게 앉을수록 상체가 자연히 더 숙여지는(고관절이 더 접히는) 경향이 있어, 무릎 하한만
# 낮추고 hip_angle을 그대로 두면 깊은 스쿼트가 이번엔 "hip" 이슈로 걸리는 문제가 남기 때문.
#
# [런지]
# NASM(National Academy of Sports Medicine, 트레이너 자격 기준)은 상체를 세운 런지를
# "90/90 런지"라 부르며, 하단에서 앞다리·뒷다리 무릎이 둘 다 약 90도라고 명시한다.
# (참고로 Cleveland Clinic 자료는 뒷다리를 45도라고 설명하는데, 어느 각도 정의를 쓴
# 건지 불명확하고 트레이너 자격 기준인 NASM 쪽이 더 표준적이라 판단해 NASM 값을 채택함.)
# 참고: https://blog.nasm.org/training-benefits/lunge-effective-lower-body-training-exercise
# knee_angle 범위는 이 90도를 중심으로 실제 반복 동작에서 나올 수 있는 오차를 감안해
# 위아래로 여유를 뒀다. hip_angle은 "상체를 세운(upright) 런지" 전제와 일치해 기존 값을
# 유지한다.
#
# [어깨 정렬] (2026-08-18 추가)
# "하체 중심 MVP"는 범위를 하체 랜드마크로 제한하겠다는 뜻이 아니었다는 걸 사용자가
# 확인해줘서(2026-08-18), 필요한 상체 피드백(어깨 정렬)을 추가함.
# NASM 오버헤드 스쿼트 평가는 "가슴을 펴고 흉추를 살짝 편 상태 유지"를 확인하지만,
# 육안 평가 항목이라 명확한 각도 수치를 제시하지 않는다(참고:
# https://blog.nasm.org/newletter/squat-form). 그래서 아래 범위는 knee_angle/hip_angle과
# 달리 문헌에서 직접 가져온 수치가 아니라, "귀-어깨-엉덩이가 거의 일직선(180도)이어야
# 어깨가 안 말린 것"이라는 방향성만 근거로 잡은 값이다. 스쿼트/런지 모두 같은 기준을 쓴다
# (어깨 정렬 기준 자체는 하체 동작 종류와 무관하다고 판단).
#
# [발뒤꿈치 뜸/무릎 모임/좌우 비대칭] (2026-08-21 — ML 분류기 완전 대체)
# 실제 사진으로 테스트한 결과, ML 스쿼트 분류기(app/ml/squat_classifier.py)가 정상 자세도
# "발뒤꿈치 뜸"/"무릎 모임"으로 자주 오탐하는 문제가 확인됐다. 조사 결과 두 가지 원인이 있었다:
# 1) 발뒤꿈치 뜸은 학습에 쓴 Kaggle 데이터셋의 ankle_angle 컬럼과 우리 calculate_angle() 계산
#    방식이 서로 다른 값 범위를 갖고 있던 train/serve skew 문제였고,
# 2) 무릎 모임/좌우 비대칭은 애초에 좌우(관상면) 판단이라 "측면 촬영만" 전제로는 관측 자체가
#    불가능한 구조적 한계였다(측면에서는 카메라 반대쪽 다리가 가려지거나 원근 때문에 좌우
#    비교 기준이 없음).
# 그래서 카메라 전제를 "측면 단독"에서 "측면 + 정면 듀얼"로 확장하고, ML 모델은 완전히
# 삭제한 뒤 세 가지 모두 규칙기반 기하학적 지표로 대체했다:
# - 발뒤꿈치 뜸: get_heel_lift_ratio() (측면 랜드마크, HEEL_LIFT_RATIO_THRESHOLD)
# - 무릎 모임: get_knee_valgus_ratio() (정면 랜드마크, KNEE_VALGUS_RATIO_THRESHOLD)
# - 좌우 비대칭: get_knee_lr_asymmetry_deg() (정면 랜드마크, KNEE_ASYMMETRY_THRESHOLD_DEG)
#
# (2026-08-21 추가) 이때 함께 옮겼어야 했는데 누락된 항목이 하나 더 있었다 — "무릎이
# 발끝을 넘는지"는 원래 ML 런지 분류기가 담당했는데, RAG 지식베이스(knowledge_base.py의
# lunge_knee_over_toe)와 코칭 문구에는 언급이 남아있으면서도 정작 자동 판정 로직이 없는
# 채로 방치돼 있었다. 뒤늦게 get_knee_over_toe_ratio()(측면 랜드마크,
# KNEE_OVER_TOE_RATIO_THRESHOLD)로 추가했다 — 원래 런지 전용이었지만 "무릎이 발끝을
# 넘지 않는다"는 코칭 지침 자체는 스쿼트에도 똑같이 적용되는 원칙이라 두 종목 모두에 쓴다.
# 정면 랜드마크(front_landmarks)는 선택 입력이다 — 프론트가 아직 정면 카메라를 붙이지 않은
# 기존 클라이언트도 계속 동작해야 하므로(하위 호환, shoulder_angle/heel_lift_ratio와 동일한
# 패턴), 정면 랜드마크가 없으면 무릎 모임/좌우 비대칭 검사를 건너뛴다.
#
# ~~TODO: 스쿼트를 "평행" 대신 "깊은 스쿼트"까지 목표로 할지~~ → 2026-08-21 사용자 확인 후
# 확정: 깊은 스쿼트도 정상으로 허용(위 [스쿼트] 절 참고). 런지 뒷다리 각도 별도 판정은
# 여전히 미정 — 제품 방향에 따라 달라지므로 재검토 필요.
# TODO: 팀 확정 필요 — shoulder_angle 범위는 수치 근거가 약해 사용자 테스트 후 조정 필요.
NORMAL_RANGES = {
    "squat": {
        "knee_angle": (50, 100),  # (2026-08-21) 깊은 스쿼트도 정상 허용 — 하한 70→50, 위 주석 참고
        "hip_angle": (45, 100),  # (2026-08-21) 위와 같은 이유로 하한 60→45, 위 주석 참고
        "shoulder_angle": (155, 180),  # 귀-어깨-엉덩이 일직선 여부 — 수치 근거 약함(위 설명 참고)
    },
    "lunge": {
        "knee_angle": (75, 105),  # NASM "90/90 런지" 기준, 90도 중심으로 여유를 둠
        "hip_angle": (140, 180),  # 런지는 상체를 세운 상태(upright) 유지가 기준
        "shoulder_angle": (155, 180),  # 스쿼트와 동일 기준 (하체 동작 종류와 무관하다고 판단)
    },
}

# 정상범위를 살짝 벗어나도 confidence가 완만하게 낮아지도록, "이만큼 벗어나면 신뢰도 0"으로
# 보는 여유 각도(도). 값이 클수록 관대하게(천천히) 신뢰도가 떨어진다.
# TODO: 팀 확정 필요 — 사용자 테스트 후 조정.
CONFIDENCE_TOLERANCE_DEG = 20

# 개인별 고관절 유연성 캘리브레이션(HipFlexibilityCalibration)이 있을 때, "그 사람이 낼 수
# 있는 최대 가동범위" 중 몇 %~몇 % 구간을 정상으로 볼지 정하는 값.
# 100%(자기 한계까지)로 잡지 않고 70~90%로 여유를 두는 이유는, 캘리브레이션 때 잰
# "무리하지 않는 선의 최대치" 자체가 이미 안전 마진이 있는 값이라, 실제 운동 중 매 반복을
# 그 한계까지 밀어붙이게 하면 부상 위험이 커지기 때문이다.
# TODO: 팀 확정 필요 — 사용자 테스트 후 조정.
CALIBRATION_LOW_PCT = 0.7
CALIBRATION_HIGH_PCT = 0.9

# 발뒤꿈치가 얼마나 뜨면 이상으로 볼지의 잠정 임계값. get_heel_lift_ratio()가 반환하는
# 값(대략적인 발 길이 대비 발뒤꿈치-발끝 높이차 비율)과 비교한다. 0.5는 "발뒤꿈치가
# 발끝보다 발 길이의 절반만큼 들렸다"는 뜻으로, 실측 문헌값이 아니라 이번에 새로 설계한
# 지표라 상식적으로 "눈에 띄게 뜬 정도"를 가늠한 잠정치다.
# TODO: 팀 확정 필요 — 실사용자 테스트로 조정.
HEEL_LIFT_RATIO_THRESHOLD = 0.5

# 무릎 사이 너비가 발목 사이 너비의 몇 %보다 좁아지면 무릎 모임(valgus)으로 볼지의 잠정
# 임계값. get_knee_valgus_ratio()가 반환하는 값(무릎너비/발목너비)과 비교한다. 0.8은
# "무릎이 발목 너비의 80% 미만으로 좁아지면 눈에 띄게 모인 것"이라는 상식적인 잠정치다.
# TODO: 팀 확정 필요 — 실사용자 테스트로 조정.
KNEE_VALGUS_RATIO_THRESHOLD = 0.8

# 좌우 무릎 굽힘 각도 차이가 몇 도 이상이면 좌우 비대칭(체중 쏠림)으로 볼지의 잠정 임계값.
# get_knee_lr_asymmetry_deg()가 반환하는 값과 비교한다. 15도는 다른 각도 기반 판정의 여유값
# (예: coaching/realtime.py의 DEEP_MARGIN_DEG)과 같은 자릿수로 맞춘 잠정치다.
# TODO: 팀 확정 필요 — 실사용자 테스트로 조정.
KNEE_ASYMMETRY_THRESHOLD_DEG = 15.0

# 무릎이 발끝보다 발 길이의 몇 %만큼 더 나가면 "발끝을 넘었다"고 볼지의 잠정 임계값
# (2026-08-21 추가 — ML 런지 분류기가 담당하던 항목을 규칙기반으로 뒤늦게 대체).
# get_knee_over_toe_ratio()가 반환하는 값과 비교한다. 0.3은 "무릎이 발 길이의 30%만큼
# 발끝을 넘으면 눈에 띄게 나간 것"이라는 상식적인 잠정치이고, 약간 넘는 정도는 정상적인
# 가동범위로 보고 여유를 뒀다. 스쿼트/런지 둘 다 같은 임계값을 쓴다(app/pose/angles.py의
# get_knee_over_toe_ratio() 주석 참고 — 원래 런지 전용이었지만 스쿼트에도 적용).
# TODO: 팀 확정 필요 — 실사용자 테스트로 조정.
KNEE_OVER_TOE_RATIO_THRESHOLD = 0.3


def personalized_hip_range(calibration: HipFlexibilityCalibration) -> tuple[float, float]:
    """
    캘리브레이션 결과(서 있을 때 각도, 무리 없이 최대한 숙였을 때 각도)로부터
    "이 사람 기준 정상 hip_angle 범위"를 계산한다.

    NORMAL_RANGES의 hip_angle이 왜 모두에게 똑같은 고정값이면 안 되는지는 위쪽 주석에
    적힌 IJSPT 논문 근거와 같다 — 이 함수가 그 문제의 실제 해결책이다. 계산 방식은
    "숙인 정도(가동범위)의 70~90% 지점을 정상 구간으로 본다": 자기 최대치의 90%보다
    더 깊이 숙이면 한계에 너무 가까워 위험 신호로, 70%보다 덜 숙이면 아직 목표한 만큼
    자세를 안 잡은 것으로 판정하겠다는 뜻이다.
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


def _range_confidence(value: float, low: float, high: float) -> float:
    """
    값이 [low, high] 범위 안이면 1.0에 가깝게, 범위를 벗어날수록 0.0에 가깝게
    선형으로 신뢰도를 계산한다.

    왜 이진(정상/이상) 판정 말고 신뢰도까지 계산하는가?
    - 하네스(AI-07)가 "confidence < 0.7이면 재분석 도구 호출"처럼 신뢰도를 기준으로
      다음 행동을 스스로 결정해야 하므로, True/False만으로는 정보가 부족하다.
    """
    if low <= value <= high:
        # 범위 중앙에 가까울수록 1.0, 경계에 가까울수록 0.8까지 완만하게 낮춘다
        # (경계값도 "정상"이므로 confidence가 너무 낮아지지 않도록 하한을 둠).
        mid = (low + high) / 2
        half_width = (high - low) / 2 or 1
        distance_ratio = abs(value - mid) / half_width
        return max(0.8, 1.0 - 0.2 * distance_ratio)

    # 범위를 벗어난 정도에 비례해 신뢰도를 낮추고, CONFIDENCE_TOLERANCE_DEG 이상 벗어나면 0으로 수렴.
    over = (low - value) if value < low else (value - high)
    return max(0.0, 1.0 - over / CONFIDENCE_TOLERANCE_DEG)


def judge_static_pose(
    landmarks: list[Landmark],
    exercise_type: str,
    side: str = "auto",
    hip_calibration: HipFlexibilityCalibration | None = None,
    front_landmarks: list[Landmark] | None = None,
) -> dict:
    """
    정지 자세 1장을 규칙기반으로 판정한다.

    front_landmarks(정면 촬영, 2026-08-21 추가)는 선택 입력이다 — 없으면 무릎 모임/좌우
    비대칭 검사를 건너뛰고 기존(측면 전용)과 동일하게 동작한다(하위 호환). 있으면 두 검사를
    추가로 수행한다. 자세한 배경은 위쪽 "[발뒤꿈치 뜸/무릎 모임/좌우 비대칭]" 주석 참고.

    반환값을 Pydantic 모델이 아닌 dict로 두는 이유: main.py가 API 응답으로 감싸기 전에,
    하네스(AI-07)나 세션 리포트(AI-12) 같은 다른 모듈에서도 가볍게 재사용할 수 있도록
    순수 값 형태를 유지하기 위함 (불필요하게 스키마 모듈에 의존하지 않게 함).
    """
    ranges = NORMAL_RANGES.get(exercise_type)
    if ranges is None:
        raise ValueError(f"지원하지 않는 운동 종목: {exercise_type}")

    knee_angle = get_knee_angle(landmarks, side)
    hip_angle = get_hip_angle(landmarks, side)
    shoulder_angle = get_shoulder_alignment_angle(landmarks, side)
    heel_lift_ratio = get_heel_lift_ratio(landmarks, side)
    knee_over_toe_ratio = get_knee_over_toe_ratio(landmarks, side)

    knee_low, knee_high = ranges["knee_angle"]
    # hip_angle만 개인별로 바꿔치기하는 이유: knee_angle은 문헌상 인구 전체에 어느 정도
    # 보편적인 기준(IJSPT 논문)이 있지만, hip_angle은 그 문헌이 스스로 "개인차가 커서 고정값
    # 부적절"이라고 밝힌 값이기 때문 — 캘리브레이션이 있으면 그걸로, 없으면 기존 고정값으로.
    if hip_calibration is not None:
        hip_low, hip_high = personalized_hip_range(hip_calibration)
    else:
        hip_low, hip_high = ranges["hip_angle"]
    shoulder_low, shoulder_high = ranges["shoulder_angle"]

    issues = []
    if not (knee_low <= knee_angle <= knee_high):
        issues.append(
            {
                "part": "knee",
                "message": f"무릎 각도가 {knee_angle:.1f}도로 정상 범위({knee_low}~{knee_high}도)를 벗어났습니다.",
            }
        )
    if not (hip_low <= hip_angle <= hip_high):
        issues.append(
            {
                "part": "hip",
                "message": f"엉덩이(고관절) 각도가 {hip_angle:.1f}도로 정상 범위({hip_low}~{hip_high}도)를 벗어났습니다.",
            }
        )
    if not (shoulder_low <= shoulder_angle <= shoulder_high):
        issues.append(
            {
                "part": "shoulder",
                "message": f"어깨가 말려 있습니다({shoulder_angle:.1f}도). 가슴을 펴고 어깨를 뒤로 젖혀주세요.",
            }
        )
    if heel_lift_ratio > HEEL_LIFT_RATIO_THRESHOLD:
        issues.append({"part": "heel", "message": HEEL_LIFT_MESSAGE})
    if knee_over_toe_ratio > KNEE_OVER_TOE_RATIO_THRESHOLD:
        issues.append({"part": "knee_over_toe", "message": KNEE_OVER_TOE_MESSAGE})

    knee_conf = _range_confidence(knee_angle, knee_low, knee_high)
    hip_conf = _range_confidence(hip_angle, hip_low, hip_high)
    shoulder_conf = _range_confidence(shoulder_angle, shoulder_low, shoulder_high)
    # 발뒤꿈치는 범위가 아니라 단일 임계값 비교라 _range_confidence를 그대로 쓸 수 없다 —
    # 임계값을 얼마나 넘었는지에 비례해 완만하게 신뢰도를 낮추고, 임계값의 2배 이상
    # 벗어나면 0으로 수렴시킨다(다른 부위의 "여유값 벗어나면 0" 패턴과 동일한 취지).
    heel_conf = max(0.0, 1.0 - max(0.0, heel_lift_ratio - HEEL_LIFT_RATIO_THRESHOLD) / HEEL_LIFT_RATIO_THRESHOLD)
    # 무릎-발끝도 heel_conf와 같은 방식(단일 임계값, 클수록 이상)의 신뢰도 계산을 재사용한다.
    knee_over_toe_conf = max(
        0.0,
        1.0 - max(0.0, knee_over_toe_ratio - KNEE_OVER_TOE_RATIO_THRESHOLD) / KNEE_OVER_TOE_RATIO_THRESHOLD,
    )
    confidences = [knee_conf, hip_conf, shoulder_conf, heel_conf, knee_over_toe_conf]

    # 정면 랜드마크가 있을 때만 무릎 모임/좌우 비대칭을 검사한다 — 없으면(하위 호환) 이 두
    # 항목은 판정에서 완전히 빠진다(신뢰도 계산에도 관여하지 않음).
    if front_landmarks is not None:
        knee_valgus_ratio = get_knee_valgus_ratio(front_landmarks)
        knee_asymmetry_deg = get_knee_lr_asymmetry_deg(front_landmarks)

        if knee_valgus_ratio < KNEE_VALGUS_RATIO_THRESHOLD:
            issues.append({"part": "knee_valgus", "message": KNEE_VALGUS_MESSAGE})
        if knee_asymmetry_deg > KNEE_ASYMMETRY_THRESHOLD_DEG:
            issues.append({"part": "asymmetry", "message": ASYMMETRY_MESSAGE})

        # 무릎 모임은 "1.0 이상이 정상, 낮을수록 이상"이라 heel과 방향이 반대다 — 임계값
        # 미만으로 떨어진 정도에 비례해 완만하게 낮추고, 임계값의 절반(즉 0에 근접)까지
        # 벌어지면 0으로 수렴시킨다.
        valgus_conf = (
            1.0
            if knee_valgus_ratio >= KNEE_VALGUS_RATIO_THRESHOLD
            else max(0.0, knee_valgus_ratio / KNEE_VALGUS_RATIO_THRESHOLD)
        )
        # 좌우 비대칭은 heel_conf와 같은 방향(클수록 이상)이라 같은 공식을 재사용한다.
        asymmetry_conf = max(
            0.0, 1.0 - max(0.0, knee_asymmetry_deg - KNEE_ASYMMETRY_THRESHOLD_DEG) / KNEE_ASYMMETRY_THRESHOLD_DEG
        )
        confidences.extend([valgus_conf, asymmetry_conf])

    # 검사한 부위 중 가장 낮은 신뢰도를 최종 신뢰도로 사용한다 (가장 취약한 부위가 전체 판정을 좌우하게 함).
    confidence = min(confidences)

    return {
        "is_normal": len(issues) == 0,
        "confidence": round(confidence, 2),
        "issues": issues,
    }
