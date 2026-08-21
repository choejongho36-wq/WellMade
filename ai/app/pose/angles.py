"""
관절 3점 좌표로 각도를 계산하는 모듈.

WellMade는 무거운 자세추정(MediaPipe Pose)을 클라이언트(브라우저)에서 실행하고,
AI 서버는 결과 좌표(33개 관절)만 받아 "각도 계산 → 규칙 판정"이라는 가벼운 연산만 수행한다.
이 파일은 그중 "각도 계산" 담당이며, rules.py/coaching/realtime.py가 이 함수들을 가져다 쓴다.
"""

import math

from app.schemas import Landmark

# MediaPipe Pose가 반환하는 33개 관절 좌표 중, 스쿼트/런지 판정에 필요한 인덱스만 정의.
# (공식 인덱스 정의: https://ai.google.dev/edge/mediapipe/solutions/vision/pose_landmarker)
LEFT_SHOULDER = 11
RIGHT_SHOULDER = 12
LEFT_HIP = 23
RIGHT_HIP = 24
LEFT_KNEE = 25
RIGHT_KNEE = 26
LEFT_ANKLE = 27
RIGHT_ANKLE = 28
# 발뒤꿈치/발끝 좌표. get_heel_lift_ratio()(발뒤꿈치 뜸 규칙기반 검사)와
# get_knee_valgus_ratio()(무릎 모임 규칙기반 검사)에서 쓴다.
LEFT_HEEL = 29
RIGHT_HEEL = 30
LEFT_FOOT_INDEX = 31
RIGHT_FOOT_INDEX = 32
# 어깨 정렬(상체) 판정에 쓰는 귀 좌표. 하체 중심 MVP 이후 "하체 랜드마크만 쓴다"는 제약은
# 없었다는 걸 사용자가 확인해줘서(2026-08-18) 추가함 — get_shoulder_alignment_angle() 참고.
LEFT_EAR = 7
RIGHT_EAR = 8


def calculate_angle(a: Landmark, b: Landmark, c: Landmark) -> float:
    """
    세 점(a, b, c)이 주어졌을 때 b를 꼭짓점으로 하는 각도(0~180도)를 계산한다.

    왜 x, y만 쓰고 z(깊이)는 버리는가?
    - 촬영은 "측면 각도 고정"이 전제이므로, 카메라를 정면으로 보는 2D 평면(x, y)만으로도
      무릎/엉덩이의 굽힘 각도를 충분히 정확하게 잴 수 있다.
    - MediaPipe의 z값은 카메라 기준 상대 깊이라 스케일이 불안정해서, 2D 각도 계산에
      오히려 노이즈를 더할 수 있다 (z를 배제하는 것이 더 안정적인 판단으로 이어진다).
    """
    ba = (a.x - b.x, a.y - b.y)
    bc = (c.x - b.x, c.y - b.y)

    mag_ba = math.hypot(*ba)
    mag_bc = math.hypot(*bc)

    if mag_ba == 0 or mag_bc == 0:
        # 좌표가 겹치는 경우(트래킹 실패 등) 각도 계산이 불가능하므로 0을 반환.
        # 예외를 던지지 않는 이유: 실시간 판정 경로에서 프레임 하나가 흔들렸다고
        # 전체 요청이 실패하면 안 되기 때문 (호출부에서 이후 프레임으로 자연스럽게 보정됨).
        return 0.0

    dot = ba[0] * bc[0] + ba[1] * bc[1]
    cos_angle = dot / (mag_ba * mag_bc)
    cos_angle = max(-1.0, min(1.0, cos_angle))  # 부동소수점 오차로 [-1, 1]을 벗어나는 것 방지
    return math.degrees(math.acos(cos_angle))


def _select_side(landmarks: list[Landmark], side: str) -> str:
    """
    side="auto"로 요청이 오면, 왼쪽/오른쪽 중 카메라에 더 잘 보이는(visibility 평균이 높은)
    쪽을 자동으로 골라 사용한다.

    왜 필요한가?
    - 측면 촬영에서는 카메라 반대쪽 관절이 몸에 가려져 visibility가 낮게 나오는 경우가 많다.
    - 사용자가 왼쪽/오른쪽 중 어느 옆모습을 찍을지 앱이 강제하지 않으므로,
      서버가 더 신뢰도 높은 쪽 랜드마크로 알아서 계산하는 편이 사용성이 좋다.
    """
    if side in ("left", "right"):
        return side

    left_score = (
        landmarks[LEFT_HIP].visibility
        + landmarks[LEFT_KNEE].visibility
        + landmarks[LEFT_ANKLE].visibility
    ) / 3
    right_score = (
        landmarks[RIGHT_HIP].visibility
        + landmarks[RIGHT_KNEE].visibility
        + landmarks[RIGHT_ANKLE].visibility
    ) / 3
    return "left" if left_score >= right_score else "right"


def get_knee_angle(landmarks: list[Landmark], side: str = "auto") -> float:
    """엉덩이-무릎-발목 3점으로 무릎 굽힘 각도를 계산한다.
    (180도에 가까울수록 다리를 편 상태, 각도가 작을수록 더 굽힌 상태)"""
    chosen = _select_side(landmarks, side)
    hip, knee, ankle = (
        (landmarks[LEFT_HIP], landmarks[LEFT_KNEE], landmarks[LEFT_ANKLE])
        if chosen == "left"
        else (landmarks[RIGHT_HIP], landmarks[RIGHT_KNEE], landmarks[RIGHT_ANKLE])
    )
    return calculate_angle(hip, knee, ankle)


def get_hip_angle(landmarks: list[Landmark], side: str = "auto") -> float:
    """어깨-엉덩이-무릎 3점으로 엉덩이(고관절) 굽힘 각도를 계산한다.
    상체가 얼마나 앞으로 숙여졌는지(스쿼트/런지 시 상체 기울기)를 나타낸다."""
    chosen = _select_side(landmarks, side)
    shoulder, hip, knee = (
        (landmarks[LEFT_SHOULDER], landmarks[LEFT_HIP], landmarks[LEFT_KNEE])
        if chosen == "left"
        else (landmarks[RIGHT_SHOULDER], landmarks[RIGHT_HIP], landmarks[RIGHT_KNEE])
    )
    return calculate_angle(shoulder, hip, knee)


def get_heel_lift_ratio(landmarks: list[Landmark], side: str = "auto") -> float:
    """
    측면 촬영 기준, 발뒤꿈치가 발끝 대비 얼마나 떠 있는지를 나타내는 비율.

    왜 각도(calculate_angle) 대신 이런 비율을 쓰는가? (2026-08-21, ML 분류기 대체 배경)
    - 원래 "발뒤꿈치 뜸"은 Kaggle 데이터셋 기반 ML 분류기(app/ml/squat_classifier.py의
      label=4)가 담당했는데, 실제 사진으로 테스트해보니 정상 자세도 대부분 "발뒤꿈치 뜸"으로
      오탐되는 문제가 확인됐다. 원인은 그 데이터셋의 사전 계산된 ankle_angle 컬럼이 우리
      calculate_angle(knee, ankle, foot_index)와 같은 방식으로 계산됐다는 보장이 없었고,
      실제 값 범위를 비교해보니 완전히 다른 스케일이었다(train/serve skew — 자세한 근거는
      squat_classifier.py 주석 참고). 그래서 이 프로젝트의 기본 원칙("규칙기반 우선")대로,
      검증되지 않은 ML 대신 우리가 직접 재현 가능한 기하학적 지표로 대체했다.
    - "무릎 모임(knee valgus)"도 같은 이유로 대체를 시도했지만, 그건 좌우(관상면) 판단이라
      측면 촬영 랜드마크만으로는 애초에 관측이 불가능하다고 판단해 대체하지 않았다(정면
      촬영이 필요 — rules.py 주석 참고). 발뒤꿈치 뜸은 순수 상하(시상면) 움직임이라 측면
      촬영으로도 원리적으로 관측 가능하다는 점이 다르다.

    값이 0에 가까우면 발뒤꿈치가 발끝과 비슷한 높이(바닥에 붙어있는 상태), 값이 클수록
    발뒤꿈치가 발끝보다 위로 들려 있는(뜬) 상태를 뜻한다. MediaPipe 좌표는 y가 아래로
    갈수록 커지는 이미지 좌표계이므로, "발뒤꿈치가 발끝보다 위로 들림"은
    heel.y < toe.y, 즉 (toe.y - heel.y) > 0으로 나타난다.

    발목-발끝 사이 x축 거리(대략적인 발 길이)로 나눠 정규화한다 — 카메라 거리/줌 배율이
    달라져도(발이 화면에 크게/작게 찍혀도) 비슷한 비율이 나오게 하기 위함. 발뒤꿈치-발끝
    거리 대신 발목-발끝 거리를 정규화 기준으로 쓴 이유: 발뒤꿈치는 이 지표가 감지하려는
    "들림" 현상 자체로 위치가 크게 바뀌는 점이라 정규화 기준으로 쓰면 값이 함께 흔들린다.
    발목은 발뒤꿈치가 뜨는 동안에도 상대적으로 안정적인 기준점이다.

    # TODO: 팀 확정 필요 — knee_angle/hip_angle과 달리 이 지표는 문헌에서 가져온 값이
    # 아니라 이번에 새로 설계한 기하학적 근사치다. 실사용자 테스트 데이터가 쌓이기 전까지는
    # 임계값(rules.py의 HEEL_LIFT_RATIO_THRESHOLD)도 잠정값으로 봐야 한다.
    """
    chosen = _select_side(landmarks, side)
    heel, toe, ankle = (
        (landmarks[LEFT_HEEL], landmarks[LEFT_FOOT_INDEX], landmarks[LEFT_ANKLE])
        if chosen == "left"
        else (landmarks[RIGHT_HEEL], landmarks[RIGHT_FOOT_INDEX], landmarks[RIGHT_ANKLE])
    )
    foot_length = abs(ankle.x - toe.x)
    if foot_length == 0:
        # 발목/발끝 좌표가 겹치는 경우(트래킹 실패 등) 계산이 불가능하므로, calculate_angle()과
        # 동일한 방식으로 "판정 불가 -> 안전한 기본값(0, 정상 쪽)"을 반환한다.
        return 0.0
    return (toe.y - heel.y) / foot_length


def get_knee_over_toe_ratio(landmarks: list[Landmark], side: str = "auto") -> float:
    """
    측면 촬영 기준, 무릎이 발끝보다 얼마나 앞으로 나갔는지를 나타내는 비율.

    왜 뒤늦게(2026-08-21) 추가됐는가?
    - 원래 "무릎이 발끝을 넘는지"는 ML 런지 분류기(app/ml/lunge_classifier.py, 삭제됨)가
      담당하던 항목이었다. 스쿼트/런지 ML을 전부 규칙기반으로 대체할 때(같은 날짜) 발뒤꿈치
      뜸/무릎 모임/좌우 비대칭은 대체 지표를 같이 설계했지만, 이 항목은 누락된 채로
      남아있었다 — RAG 지식베이스(knowledge_base.py)의 lunge_knee_over_toe 문서와 코칭
      문구에는 언급이 남아있는데 실제로 자동 판정하는 로직이 없는 상태였다. 사용자가 이
      공백을 지적해서 뒤늦게 추가한다.
    - get_heel_lift_ratio()와 마찬가지로 "무거운 ML 없이 재현 가능한 기하학적 지표로
      규칙기반 우선 원칙을 지킨다"는 같은 설계를 따른다.

    왜 스쿼트에도 적용하는가?
    - 원래 ML 시절엔 런지 전용 판정이었지만, "무릎이 발끝을 넘지 않는 선에서 앉는다"는
      코칭 지침 자체는 스쿼트에도 똑같이 적용되는 일반적인 원칙이라(NASM 오버헤드 스쿼트
      평가에도 포함되는 항목), 사용자 요청에 따라 스쿼트/런지 둘 다에 적용한다.

    부호/방향 처리:
    - 측면 촬영에서는 사람이 카메라 기준 왼쪽을 보고 있을 수도, 오른쪽을 보고 있을 수도
      있어서, "무릎 x좌표가 발끝 x좌표보다 크다/작다"만으로는 "앞으로 나갔다"를 판단할 수
      없다 — 마이너스 부호가 반대로 나올 수 있다. 그래서 발목→발끝 벡터의 x축 부호로
      "몸이 카메라 기준 어느 방향을 보고 있는지"(facing_direction)를 먼저 추정하고, 그
      방향 기준으로 무릎이 발끝보다 앞에 있으면 항상 양수가 되도록 부호를 맞춘다.

    발목-발끝 사이 x축 거리(발 길이)로 정규화하는 이유는 get_heel_lift_ratio()와 동일
    (카메라 거리/줌 배율에 따라 비슷한 비율이 나오게 하기 위함).

    값이 0 이하면 무릎이 발끝을 넘지 않은 상태(정상), 값이 클수록 무릎이 발끝보다 앞으로
    많이 나간 상태를 뜻한다.

    # TODO: 팀 확정 필요 — 이 지표도 heel_lift_ratio와 마찬가지로 문헌에서 가져온 값이
    # 아니라 새로 설계한 기하학적 근사치이며, 임계값(rules.py의
    # KNEE_OVER_TOE_RATIO_THRESHOLD)도 잠정값이다. 특히 스쿼트/런지 모두 무릎이 발끝을
    # "약간" 넘는 것 자체는 정상적인 가동범위(특히 발목 가동성이 좋은 사람이나 깊은
    # 스쿼트)라는 의견도 있어, 실사용자 테스트로 재조정이 필요하다.
    """
    chosen = _select_side(landmarks, side)
    knee, ankle, toe = (
        (landmarks[LEFT_KNEE], landmarks[LEFT_ANKLE], landmarks[LEFT_FOOT_INDEX])
        if chosen == "left"
        else (landmarks[RIGHT_KNEE], landmarks[RIGHT_ANKLE], landmarks[RIGHT_FOOT_INDEX])
    )
    foot_length = abs(ankle.x - toe.x)
    if foot_length == 0:
        return 0.0
    facing_direction = 1.0 if (toe.x - ankle.x) >= 0 else -1.0
    return ((knee.x - toe.x) * facing_direction) / foot_length


def get_shoulder_alignment_angle(landmarks: list[Landmark], side: str = "auto") -> float:
    """
    귀-어깨-엉덩이 3점으로 "어깨가 말리지 않고 펴져 있는지"(가슴을 편 자세)를 계산한다.

    왜 이 3점인가?
    - hip_angle(어깨-엉덩이-무릎)은 "상체 전체가 다리 기준으로 얼마나 숙여졌는지"를 재는
      값이라, 어깨가 둥글게 말리는(scapula protraction) 것과는 다른 문제다. 몸통이 곧게
      펴진 채로 숙여진 것과, 몸통은 안 숙여졌는데 어깨만 앞으로 말린 것을 hip_angle
      하나로는 구분할 수 없다.
    - NASM의 오버헤드 스쿼트 평가(Overhead Squat Assessment)는 "가슴을 펴고 흉추를 살짝
      편 상태로 유지"하는지, "어깨의 과도한 둥글림"이 있는지를 육안으로 확인하는 항목을
      포함한다(https://blog.nasm.org/newletter/squat-form). 이 육안 평가를 각도로 옮기면,
      좋은 자세에서는 귀-어깨-엉덩이가 대략 일직선(180도에 가까움)이고, 어깨가 말리면서
      머리가 앞으로 빠지면(forward head posture) 이 각도가 줄어든다.

    한계 (# TODO: 팀 확정 필요):
    - NASM 자료도 "몇 도 이상이면 이상"이라는 수치 기준을 제시하지 않는, 육안 평가 항목이라
      아래 rules.py의 정상범위는 knee_angle/hip_angle과 달리 문헌에서 직접 가져온 수치가
      아니다 — 방향성만 근거가 있고 정확한 임계값은 사용자 테스트로 조정이 필요하다.
    - 스쿼트/런지 하단처럼 상체 전체가 앞으로 기울어진 자세에서는, 목/머리가 정상적으로
      몸통과 같은 방향을 유지해도 이 각도가 자연스럽게 줄어들 수 있어(하체 하나만 굽혀도
      상체 전체가 같이 기울기 때문), 서 있는 자세만큼 정확하지 않을 수 있다.
    """
    chosen = _select_side(landmarks, side)
    ear, shoulder, hip = (
        (landmarks[LEFT_EAR], landmarks[LEFT_SHOULDER], landmarks[LEFT_HIP])
        if chosen == "left"
        else (landmarks[RIGHT_EAR], landmarks[RIGHT_SHOULDER], landmarks[RIGHT_HIP])
    )
    return calculate_angle(ear, shoulder, hip)


def _horizontal_tilt_angle(left_point: Landmark, right_point: Landmark) -> float:
    """
    좌우 두 점을 잇는 선이 수평선과 이루는 각도(도)를 부호 있게 계산한다.
    양수 = 왼쪽 점이 더 높음(=왼쪽이 올라감), 음수 = 오른쪽 점이 더 높음.

    MediaPipe 정규화 좌표는 y가 아래로 갈수록 커지므로(이미지 좌표계),
    "왼쪽이 올라감"은 곧 left_point.y < right_point.y를 의미한다.
    """
    dx = right_point.x - left_point.x
    dy = right_point.y - left_point.y
    if dx == 0 and dy == 0:
        return 0.0
    # atan2(dy, dx): dy가 양수(오른쪽이 더 아래)일 때 양수 각도가 나오도록,
    # 그대로가 "왼쪽이 올라간 정도"와 부호가 일치한다.
    return math.degrees(math.atan2(dy, dx))


def get_shoulder_tilt_angle(landmarks: list[Landmark]) -> float:
    """
    정면 촬영 기준, 좌우 어깨의 높이 차이로 "어깨가 좌우로 얼마나 기울었는지"를 계산한다.

    측면 촬영 전제로 만든 get_shoulder_alignment_angle()(귀-어깨-엉덩이, 어깨가 앞으로
    말렸는지 = 시상면 문제)과는 완전히 다른 축의 측정값이다 — 이건 좌우 높이 차이(관상면
    문제)라 정면 카메라가 있어야만 계산할 수 있다. 자세 비교 인사이트(AI-15) 기능을 위해
    2026-08-18 추가했다. 이름도 다르게 지은 이유는 두 값을 절대 헷갈리지 않게 하기 위함.

    반환값 부호: 양수 = 왼쪽 어깨가 올라감, 음수 = 오른쪽 어깨가 올라감(세종시 공공데이터의
    "왼쪽 어깨가 N도 올라간 상태입니다" 표현과 부호를 맞춰, 참조 분포와 직접 비교 가능하게 함).
    """
    return _horizontal_tilt_angle(landmarks[LEFT_SHOULDER], landmarks[RIGHT_SHOULDER])


def get_pelvis_tilt_angle(landmarks: list[Landmark]) -> float:
    """
    정면 촬영 기준, 좌우 골반(엉덩이) 높이 차이로 "골반이 좌우로 얼마나 기울었는지"를 계산한다.
    부호 규칙과 배경은 get_shoulder_tilt_angle()과 동일 — 자세 비교 인사이트(AI-15)용.
    """
    return _horizontal_tilt_angle(landmarks[LEFT_HIP], landmarks[RIGHT_HIP])


def get_knee_valgus_ratio(front_landmarks: list[Landmark]) -> float:
    """
    정면 촬영 기준, 무릎 사이 가로 거리를 발목 사이 가로 거리로 나눈 비율.

    왜 이 지표가 필요한가? (2026-08-21, ML 분류기 완전 대체 배경)
    - 무릎 모임(knee valgus)은 원래 Kaggle 데이터셋 기반 ML 분류기(app/ml/squat_classifier.py,
      이제 삭제됨)의 label=3이 담당했는데, 실제 사진 테스트에서 신뢰할 수 없는 것으로 확인됐다.
      근본 원인은 학습 데이터의 knee_lateral(좌우 편차) 컬럼을 우리가 재현할 수 없어 애초에
      특징에서 제외했었고(features.py, 이제 삭제됨), 그래서 그 예측이 사실상 무관한 특징에
      의존한 우연한 상관관계였다는 점이다.
    - 더 근본적인 문제는 "좌우(관상면) 판단은 측면 촬영만으로는 관측 자체가 불가능하다"는
      것이었다(get_heel_lift_ratio() 주석 참고). 이번에 카메라 전제를 "측면 단독"에서
      "측면 + 정면 듀얼"로 바꾸면서, 정면 랜드마크로 직접 계산 가능한 지표로 교체했다.

    왜 각도 대신 이 비율(너비 비교)을 쓰는가?
    - NgoQuocBao1010/Exercise-Correction 레포(이 프로젝트가 런지 학습 데이터 출처로도 참고한
      곳)의 자체 스쿼트 폼 오류 검출도 3점 각도가 아니라 "무릎 너비 vs 발목 너비" 비율로
      무릎 모임을 판정한다 — 무릎이 안쪽으로 모이면 무릎 사이 거리가 발목 사이 거리보다
      좁아진다는 게 이 현상을 정의하는 방식 자체이기 때문에, 각도보다 이 비율이 더 직접적인
      지표다.
    - 발목 너비로 정규화하는 이유는 get_heel_lift_ratio()와 동일 — 카메라 거리/줌 배율이
      달라져도 비슷한 비율이 나오게 하기 위함.

    값이 1.0에 가깝거나 클수록 무릎이 발목만큼(또는 그 이상) 벌어진 정상 자세, 값이 작을수록
    무릎이 발목보다 안쪽으로 모인(valgus) 상태를 뜻한다.

    # TODO: 팀 확정 필요 — get_heel_lift_ratio()와 마찬가지로 문헌값이 아니라 이번에 새로
    # 설계한 기하학적 근사치다. 임계값(rules.py의 KNEE_VALGUS_RATIO_THRESHOLD)도 잠정값이다.
    """
    knee_width = abs(front_landmarks[RIGHT_KNEE].x - front_landmarks[LEFT_KNEE].x)
    ankle_width = abs(front_landmarks[RIGHT_ANKLE].x - front_landmarks[LEFT_ANKLE].x)
    if ankle_width == 0:
        # 발목 좌표가 겹치는 경우(트래킹 실패 등) 계산이 불가능하므로, 다른 지표와 동일하게
        # "판정 불가 -> 안전한 기본값"을 반환한다. 이 지표는 1.0 이상이 정상이므로 넉넉한 값(1.0)을
        # 기본값으로 둔다.
        return 1.0
    return knee_width / ankle_width


def get_knee_lr_asymmetry_deg(front_landmarks: list[Landmark]) -> float:
    """
    정면 촬영 기준, 좌우 무릎 굽힘 각도 차이(도, 절대값)로 "양쪽 다리에 체중이 고르게
    실렸는지"를 근사한다.

    왜 이 지표가 필요한가? (2026-08-21, ML 분류기 완전 대체 배경)
    - 좌우 비대칭(label=5)도 knee valgus와 같은 이유로 신뢰할 수 없었다: 측면 촬영으로는
      한쪽 다리만 보여서 애초에 좌우를 비교할 근거 자체가 없었다(squat_classifier.py 주석
      참고, 이제 삭제됨). 정면 촬영을 추가하면서 양쪽 다리가 동시에 보이므로, 처음으로
      "진짜 좌우 비교"가 가능해졌다.

    왜 get_knee_angle()처럼 한쪽만 고르지 않고 양쪽을 모두 계산하는가?
    - get_knee_angle()의 _select_side()는 "측면 촬영에서 어느 쪽이 더 잘 보이는지" 고르기
      위한 것으로, 애초에 한쪽만 볼 수 있다는 전제에서 나온 설계다. 정면 촬영은 양쪽 다리가
      동시에 보이므로 그 전제 자체가 다르다 — 이 함수는 side 선택 없이 좌우 무릎 각도를
      각각 직접 계산해서 비교한다.

    값이 0에 가까울수록 양쪽 다리가 비슷하게 굽혀진(대칭) 상태, 값이 클수록 한쪽만 더 깊이
    굽혀진(비대칭 — 체중이 한쪽으로 쏠렸을 가능성) 상태를 뜻한다.

    # TODO: 팀 확정 필요 — 이 지표는 "굽힘 정도 차이"로 체중 분배 차이를 근사한 값이지,
    # 실제 압력(체중) 분포를 직접 측정한 값이 아니다. 임계값(rules.py의
    # KNEE_ASYMMETRY_THRESHOLD_DEG)도 잠정값이다.
    """
    left_angle = calculate_angle(
        front_landmarks[LEFT_HIP], front_landmarks[LEFT_KNEE], front_landmarks[LEFT_ANKLE]
    )
    right_angle = calculate_angle(
        front_landmarks[RIGHT_HIP], front_landmarks[RIGHT_KNEE], front_landmarks[RIGHT_ANKLE]
    )
    return abs(left_angle - right_angle)
