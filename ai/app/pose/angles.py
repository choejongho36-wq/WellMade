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
