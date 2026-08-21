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
# 아래 두 개는 규칙기반 각도 계산에는 안 쓰지만, ML 특징 추출(app/ml/features.py)에서
# "무릎이 발끝보다 앞으로 나갔는지" 판단에 발끝(foot_index) 좌표가 필요해 추가했다.
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
