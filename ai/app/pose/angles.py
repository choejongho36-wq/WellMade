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

# get_heel_lift_ratio()/get_knee_over_toe_ratio()가 정규화 기준(발목-발끝 거리, foot_length)
# 으로 나눌 때 쓰는 최소 허용값(2026-08-21 추가). 발이 카메라를 거의 정면으로 향하거나
# (foot_length가 0에 가까워짐) 랜드마크 인식이 불안정한 프레임에서는, 분모가 아주 작은
# 값으로 나뉘면서 분자의 작은 노이즈(몇 픽셀 수준의 오차)가 비율을 몇 배로 증폭시킨다 —
# 실제로 러닝/스프린트 크라우치처럼 발이 거의 겹쳐 보이는 사진에서 "무릎이 발끝을 크게
# 넘었다"는 오탐이 이 방식으로 재현됨을 확인했다. foot_length가 이 값보다 작으면
# calculate_angle()의 "판정 불가 -> 안전한 기본값" 패턴과 동일하게 0.0(정상 쪽)을 반환한다.
# TODO: 팀 확정 필요 — 0.03(정규화 좌표 기준 화면 너비의 3%)은 실측 근거가 아니라
# 상식적으로 잡은 잠정치.
MIN_RELIABLE_FOOT_LENGTH = 0.03


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
    if foot_length < MIN_RELIABLE_FOOT_LENGTH:
        # 발목/발끝 좌표가 거의 겹치는 경우(트래킹 실패, 또는 발이 카메라 쪽을 거의 정면으로
        # 향해 2D 투영상 거리가 매우 작아진 경우) 계산이 불안정해지므로(MIN_RELIABLE_FOOT_LENGTH
        # 주석 참고), calculate_angle()과 동일한 방식으로 "판정 불가 -> 안전한 기본값(0, 정상
        # 쪽)"을 반환한다.
        return 0.0
    return (toe.y - heel.y) / foot_length


def get_knee_over_toe_ratio(landmarks: list[Landmark], side: str = "auto") -> float:
    """
    측면 촬영 기준, 무릎이 발끝보다 얼마나 앞으로 나갔는지를 나타내는 값.

    왜 뒤늦게(2026-08-21) 추가됐는가?
    - 원래 "무릎이 발끝을 넘는지"는 ML 런지 분류기(app/ml/lunge_classifier.py, 삭제됨)가
      담당하던 항목이었다. 스쿼트/런지 ML을 전부 규칙기반으로 대체할 때(같은 날짜) 발뒤꿈치
      뜸/무릎 모임/좌우 비대칭은 대체 지표를 같이 설계했지만, 이 항목은 누락된 채로
      남아있었다 — RAG 지식베이스(knowledge_base.py, 당시엔 lunge_knee_over_toe라는 런지
      전용 문서였고 2026-08-24 런지 제거 후 knee_over_toe로 다시 씀)와 코칭 문구에는
      언급이 남아있는데 실제로 자동 판정하는 로직이 없는 상태였다. 사용자가 이 공백을
      지적해서 뒤늦게 추가한다.
    - get_heel_lift_ratio()와 마찬가지로 "무거운 ML 없이 재현 가능한 기하학적 지표로
      규칙기반 우선 원칙을 지킨다"는 같은 설계를 따른다.

    왜 스쿼트에도 적용하는가?
    - 원래 ML 시절엔 런지 전용 판정이었지만, "무릎이 발끝을 넘지 않는 선에서 앉는다"는
      코칭 지침 자체는 스쿼트에도 똑같이 적용되는 일반적인 원칙이라(NASM 오버헤드 스쿼트
      평가에도 포함되는 항목), 사용자 요청에 따라 스쿼트/런지 둘 다에 적용했었다.
      (2026-08-24: 런지 지원 자체가 사용자 요청으로 제거돼(스쿼트만 지원) 이제는 사실상
      스쿼트 전용으로 쓰인다 — 함수/임계값을 고칠 필요는 없어서 그대로 남겨뒀다.)

    부호/방향 처리:
    - 측면 촬영에서는 사람이 카메라 기준 왼쪽을 보고 있을 수도, 오른쪽을 보고 있을 수도
      있어서, "무릎 x좌표가 발끝 x좌표보다 크다/작다"만으로는 "앞으로 나갔다"를 판단할 수
      없다 — 마이너스 부호가 반대로 나올 수 있다. 그래서 발목→발끝 벡터의 x축 부호로
      "몸이 카메라 기준 어느 방향을 보고 있는지"(facing_direction)를 먼저 추정하고, 그
      방향 기준으로 무릎이 발끝보다 앞에 있으면 항상 양수가 되도록 부호를 맞춘다.

    왜 발 길이로 정규화하지 않는가 (2026-08-21 변경, get_heel_lift_ratio()와의 차이):
    - 처음엔 get_heel_lift_ratio()와 동일하게 발목-발끝 거리(발 길이)로 나눠 "발 길이
      대비 몇 %"라는 비율로 반환했었다. 그런데 실사용자 테스트 사진(손을 바닥에 짚은
      크라우칭/스프린트 스타트 자세)을 다시 진단하는 과정에서, 사용자가 "그냥 좌표로
      발끝/발목 위치를 보고 무릎이 그 방향으로 넘어갔는지만 보면 되는 거 아니냐"고 직접
      문제를 제기했고, 순수 좌표 비교 + 약간의 여유(margin)를 둔 방식으로 이 사진을
      다시 판정해보고 싶다고 명시적으로 요청함 → 발 길이 정규화를 제거하고, 무릎-발끝의
      원시 좌표 거리(facing_direction 방향 보정만 반영)를 그대로 반환하도록 바꿨다.
    - 트레이드오프: 카메라 거리/줌 배율이 달라지면 같은 정도로 무릎이 넘어가도 원시 좌표
      거리 값 자체는 달라질 수 있어(비율 방식보다 카메라 거리 변화에 덜 강건함),
      rules.py의 KNEE_OVER_TOE_RATIO_THRESHOLD도 "발 길이의 몇 %"가 아니라 "원시 좌표
      거리로 이 정도"라는 작은 여유값으로 함께 바꿨다 — 자세한 근거는 그쪽 주석 참고.
      # TODO: 팀 확정 필요 — 실사용자 테스트로 이 방식이 충분한지, 다시 발 길이 비율
      방식으로 되돌릴지 판단 필요.

    값이 0 이하면 무릎이 발끝을 넘지 않은 상태(정상), 값이 클수록 무릎이 발끝보다 앞으로
    많이 나간 상태를 뜻한다.

    # TODO: 팀 확정 필요 — 이 지표도 heel_lift_ratio와 마찬가지로 문헌에서 가져온 값이
    # 아니라 새로 설계한 기하학적 근사치이며, 임계값(rules.py의
    # KNEE_OVER_TOE_RATIO_THRESHOLD)도 잠정값이다. 특히 스쿼트에서 무릎이 발끝을 "약간"
    # 넘는 것 자체는 정상적인 가동범위(특히 발목 가동성이 좋은 사람이나 깊은 스쿼트)라는
    # 의견도 있어, 실사용자 테스트로 재조정이 필요하다.
    """
    chosen = _select_side(landmarks, side)
    knee, ankle, toe = (
        (landmarks[LEFT_KNEE], landmarks[LEFT_ANKLE], landmarks[LEFT_FOOT_INDEX])
        if chosen == "left"
        else (landmarks[RIGHT_KNEE], landmarks[RIGHT_ANKLE], landmarks[RIGHT_FOOT_INDEX])
    )
    foot_length = abs(ankle.x - toe.x)
    if foot_length < MIN_RELIABLE_FOOT_LENGTH:
        # get_heel_lift_ratio()와 동일한 이유(MIN_RELIABLE_FOOT_LENGTH 주석 참고) — foot_length가
        # 아주 작으면 facing_direction 부호 자체도 노이즈에 따라 뒤집힐 수 있어 판정 자체가
        # 무의미해진다. 실제로 이 문제로 오탐이 발생한 걸 확인해 뒤늦게 추가한 안전장치다.
        # (2026-08-21 갱신: 아래에서 더 이상 foot_length로 나누지는 않지만, facing_direction
        # 부호를 신뢰할 수 있는지 판단하는 용도로는 계속 필요해서 이 가드는 그대로 유지한다.)
        return 0.0
    facing_direction = 1.0 if (toe.x - ankle.x) >= 0 else -1.0
    # (2026-08-21 변경) 더 이상 foot_length로 나누지 않는다 — 위 docstring의 "왜 발 길이로
    # 정규화하지 않는가" 참고. 순수 좌표 거리(facing_direction 방향 보정만 반영)를 반환한다.
    return (knee.x - toe.x) * facing_direction


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


def get_shoulder_forward_lean_deg(landmarks: list[Landmark], side: str = "auto") -> float:
    """
    "목이 상체 기울기보다 얼마나 더 앞으로 기울었는지"를 재는, 상체 기울기 상대적 어깨
    말림 지표 (2026-08-24 추가 — get_shoulder_alignment_angle()의 실측 오탐을 고쳐서 대체).

    왜 get_shoulder_alignment_angle()(귀-어깨-엉덩이 절대각도)을 대체하는가?
    - 그 함수의 docstring에 이미 "상체 전체가 앞으로 기울어진 자세에서는 목/머리가
      정상적으로 몸통과 같은 방향을 유지해도 이 각도가 자연스럽게 줄어들 수 있다"고
      한계가 적혀 있었는데, 실사용자가 좋은 자세의 스쿼트 사진을 보내 실제로 이 한계가
      재현됨을 확인했다(2026-08-24). mediapipe로 그 사진을 직접 분석해보니: 무릎/엉덩이
      각도는 정상 범위 안인데 어깨만 걸림 — 실측값은 hip_angle 79.3도, shoulder_angle
      150.3도(정상범위 하한 155도에서 4.7도 모자람). 좌표를 더 뜯어보니 엉덩이→어깨(상체)
      선은 수직에서 약 42도 앞으로 기울어 있는데, 어깨→귀(목) 선은 수직에서 약 12도만
      기울어 있었다 — 즉 이 사람은 상체를 숙이면서도 시선/머리는 자연스럽게 세운, 바로
      "좋은" 자세였다. 그런데 절대각도 방식은 "목이 상체가 기운 선을 그대로 연장해야
      180도"로 계산하기 때문에, 상체를 숙인 채 고개만 정상적으로 들어도 각도가 줄어들어
      정상 자세를 오탐한다 — 이건 사진의 밝기/실루엣 문제가 아니라(랜드마크는 전부
      visibility 1.0으로 정상 인식됐다) 지표 자체의 구조적 결함이었다.
    - "진짜 어깨 말림"이 의미하는 것은 목이 상체보다 훨씬 더 앞으로(아래로) 숙여진
      경우이지, 목이 상체보다 덜 기울어(고개를 든) 경우가 아니다. 그래서 절대각도 대신
      "목 기울기 - 상체 기울기"라는 상대적 편차를 쓴다: 상체가 얼마나 기울었든, 목이
      그보다 더 앞으로 기울어야만(양수, 그것도 크게) 진짜 문제로 본다. 목이 상체와
      비슷하거나 더 세워져 있으면(0 이하) 스쿼트 중 시선을 세우는 정상적인 자세다.

    부호/방향 처리:
    - get_knee_over_toe_ratio()와 동일하게 발목→발끝 벡터의 x축 부호로 촬영 방향
      (facing_direction)을 판별해, "몸이 향한 방향 쪽으로 기울면 항상 양수"가 되도록
      상체/목 기울기 부호를 통일한다(측면 촬영에서 사람이 카메라 기준 왼쪽을 보는지
      오른쪽을 보는지에 따라 원시 x좌표 부호가 뒤바뀌므로 이 보정이 필요하다).
    - torso_tilt_deg = atan2(상체 벡터의 보정된 가로성분, 상체 벡터의 세로성분(위쪽이 +))
      neck_tilt_deg = atan2(목 벡터의 보정된 가로성분, 목 벡터의 세로성분(위쪽이 +))
      반환값 = neck_tilt_deg - torso_tilt_deg. 0에 가깝거나 음수면 목이 상체만큼(또는
      더) 세워진 정상 자세, 크게 양수면 목이 상체보다 훨씬 더 앞으로 숙여진(진짜 말린)
      자세다.

    한계 (# TODO: 팀 확정 필요):
    - 이 지표도 문헌값이 아니라 위 실측 사례를 근거로 새로 설계한 기하학적 근사치이며,
      임계값(rules.py의 SHOULDER_FORWARD_LEAN_THRESHOLD_DEG)도 잠정값이다.
    - get_shoulder_alignment_angle()과 마찬가지로 "귀"가 유일한 머리 랜드마크라, 머리를
      좌우로 살짝 돌리는 등 순수 시상면이 아닌 움직임에는 다소 취약할 수 있다.
    """
    chosen = _select_side(landmarks, side)
    ear, shoulder, hip, ankle, toe = (
        (landmarks[LEFT_EAR], landmarks[LEFT_SHOULDER], landmarks[LEFT_HIP], landmarks[LEFT_ANKLE], landmarks[LEFT_FOOT_INDEX])
        if chosen == "left"
        else (landmarks[RIGHT_EAR], landmarks[RIGHT_SHOULDER], landmarks[RIGHT_HIP], landmarks[RIGHT_ANKLE], landmarks[RIGHT_FOOT_INDEX])
    )
    foot_length = abs(ankle.x - toe.x)
    if foot_length < MIN_RELIABLE_FOOT_LENGTH:
        # get_knee_over_toe_ratio()와 동일한 이유 — facing_direction 부호를 신뢰할 수 없는
        # 구간이라 판정을 포기하고, "값이 클수록 이상"인 지표이므로 0.0(안전한 정상 쪽)을
        # 반환한다.
        return 0.0
    facing_direction = 1.0 if (toe.x - ankle.x) >= 0 else -1.0

    torso_dx = (shoulder.x - hip.x) * facing_direction
    torso_dy = shoulder.y - hip.y  # 이미지 좌표는 아래로 갈수록 y가 커지므로, 위쪽이 음수
    torso_tilt_deg = math.degrees(math.atan2(torso_dx, -torso_dy))

    neck_dx = (ear.x - shoulder.x) * facing_direction
    neck_dy = ear.y - shoulder.y
    neck_tilt_deg = math.degrees(math.atan2(neck_dx, -neck_dy))

    return neck_tilt_deg - torso_tilt_deg


def get_torso_length_ratio(landmarks: list[Landmark], side: str = "auto") -> float:
    """
    측면 촬영 기준, 어깨-엉덩이 사이 직선 거리를 발 길이로 정규화한 비율. 등이 둥글게
    말렸는지(척추 굴곡)를 규칙기반으로 잡아내기 위해 2026-08-21 추가.

    왜 이 방식인가? (get_shoulder_alignment_angle()로는 못 잡는 것)
    - MediaPipe의 33개 랜드마크에는 어깨(11/12)와 엉덩이(23/24)만 있고, 그 사이를 지나는
      등/척추 중간 지점이 아예 없다. 그래서 "등이 굽었는지"를 좌표 기하학으로 직접 재려면
      사실상 2점(어깨-엉덩이)만 갖고 판단해야 하는데, 2점은 항상 직선이라 그 자체로는
      "굽었다/안 굽었다"를 구분할 정보가 없다 — 이건 계산 방식을 바꿔서 해결되는 문제가
      아니라 입력 데이터에 아예 없는 정보를 요구하는 것이다(실사용자가 이 한계를 직접
      확인하고 다른 방법을 요청해서 이 함수가 추가됨).
    - 대신 "척추 끝점 사이의 직선 거리(현, chord)"를 이용한다: 척추 자체의 길이(뼈 길이)는
      자세가 바뀌어도 변하지 않지만, 등이 곧게 펴져 있으면 어깨-엉덩이 직선 거리가 척추
      길이에 가깝게 나오고, 등이 둥글게 말리면 두 끝점이 서로 가까워지면서(활이 굽으면
      양 끝이 가까워지는 것과 같은 원리) 직선 거리가 짧아진다. 반대로 등이 곧게 편 채로
      카메라 평면 안에서 앞으로 기울기(회전)만 한다면, 이론적으로는 이 직선 거리가 거의
      그대로 유지된다 — 그래서 "직선 거리가 기준치보다 줄었는지"가 "등이 굽었는지 vs
      그냥 앞으로 기울었는지"를 구분하는 신호가 될 수 있다.
    - "기준치"가 필요한 이유: 사람마다 몸통 길이가 달라서, 지금 잰 거리가 짧은 게 이
      사람이 원래 몸통이 짧아서인지 등이 굽어서인지 이 값 하나만으로는 알 수 없다. 그래서
      hip_calibration과 같은 타이밍("편하게 서 있기")에 이 비율도 함께 재서
      HipFlexibilityCalibration.standing_shoulder_hip_ratio로 기준값을 받는다(rules.py의
      judge_static_pose/coaching/realtime.py의 judge_realtime_coaching 참고). 기준값이
      없으면 이 함수가 계산한 값 자체는 응답에 그대로 노출되지만(디버깅용), 정상/이상
      판정에는 쓰이지 않는다.

    발목-발끝 거리(foot_length)로 정규화하는 이유는 get_heel_lift_ratio()/
    get_knee_over_toe_ratio()와 동일 — 발은 동작 내내 바닥에 고정돼 있어(자세 자체로는
    안 변함) 카메라 거리/줌 배율 변화만 반영하는 안정적인 "자" 역할을 한다. 벽/바닥 같은
    외부 배경으로 카메라 거리를 추정하는 방안도 검토했지만, 사진마다 배경이 다르고 실제
    물리적 크기를 알 방법이 없어(예: 벽 폭을 모름) 안정적인 기준이 될 수 없다고 판단해
    채택하지 않았다 — 이미 있는 몸 안의 다른 거리(발 길이)로 정규화하는 쪽이 훨씬
    간단하고 안정적이다.

    한계 (# TODO: 팀 확정 필요):
    - 카메라가 완전한 측면이 아니라 몸이 카메라 평면 밖으로 살짝 회전(사선 촬영)해 있으면,
      등이 안 굽었어도 어깨-엉덩이 직선 거리가 원근 때문에 짧아 보일 수 있다(오탐 위험).
    - 캘리브레이션 시점과 실제 측정 시점 사이에 카메라와의 거리가 크게 달라지면(예: 세션
      중간에 자리를 옮김) foot_length로 정규화해도 완전히 상쇄되지 않을 수 있다.
    """
    chosen = _select_side(landmarks, side)
    shoulder, hip, ankle, toe = (
        (landmarks[LEFT_SHOULDER], landmarks[LEFT_HIP], landmarks[LEFT_ANKLE], landmarks[LEFT_FOOT_INDEX])
        if chosen == "left"
        else (landmarks[RIGHT_SHOULDER], landmarks[RIGHT_HIP], landmarks[RIGHT_ANKLE], landmarks[RIGHT_FOOT_INDEX])
    )
    foot_length = abs(ankle.x - toe.x)
    if foot_length < MIN_RELIABLE_FOOT_LENGTH:
        # 다른 foot_length 정규화 함수들과 동일한 이유(MIN_RELIABLE_FOOT_LENGTH 주석 참고) —
        # 분모가 아주 작으면 노이즈가 증폭돼 판정 자체가 무의미해진다. 다만 "안전한 기본값"의
        # 방향이 다른 함수들과 반대라는 점에 주의: heel_lift_ratio/knee_over_toe_ratio는
        # "값이 클수록 이상"이라 0.0이 안전(정상) 쪽이지만, 이 함수는 "값이 기준치보다 작을수록
        # 이상"이라 0.0을 반환하면 오히려 "극단적으로 굽었다"로 오판된다. 그래서 비교 방향이
        # 반대인 999.0(비정상적으로 큰 값 — 항상 기준치 이상이라 "굽지 않음"으로 처리됨)을
        # 안전한 기본값으로 쓴다. (float('inf')는 표준 JSON으로 직렬화되지 않아 프론트 파싱이
        # 깨질 수 있어 피했다.)
        return 999.0
    torso_length = math.hypot(shoulder.x - hip.x, shoulder.y - hip.y)
    return torso_length / foot_length


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
