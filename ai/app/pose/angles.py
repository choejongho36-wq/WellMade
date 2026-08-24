"""
관절 3점 좌표로 각도를 계산하는 모듈.

WellMade는 무거운 자세추정(MediaPipe Pose)을 클라이언트(브라우저)에서 실행하고,
AI 서버는 결과 좌표(33개 관절)만 받아 "각도 계산 → 규칙 판정"이라는 가벼운 연산만 수행한다.
이 파일은 그중 "각도 계산" 담당이며, insight/posture_percentile.py(AI-15)가 이 함수들을
가져다 쓴다.

(2026-08-24) 원래 이 파일은 정지 자세 판정(AI-03, pose/rules.py의 judge_static_pose())
전용 각도 함수(get_knee_angle/get_hip_angle/get_shoulder_alignment_angle/
get_shoulder_forward_lean_deg/get_heel_lift_ratio/get_knee_over_toe_ratio/
get_torso_length_ratio/get_knee_valgus_ratio/get_knee_lr_asymmetry_deg)가 대부분을
차지했다. 사용자가 "정지자세 촬영 관련 부분은 다른 팀원이 맡기로 했다"며 AI-03 삭제를
요청해(동년배 비교 인사이트 AI-15는 예외), 이 함수들을 호출부(judge_static_pose())와
함께 제거했다. 실시간 코칭(AI-06)은 프론트가 이미 계산한 각도 값을 받으므로(각도
계산을 서버가 하지 않음) 애초에 이 함수들을 쓰지 않았고, 남은 get_shoulder_tilt_angle/
get_pelvis_tilt_angle(정면 좌우 기울기, AI-15 전용)만 이 파일에 남았다 — 이 두 함수는
위 목록의 함수들과는 계산 방식(관절 3점 각도가 아니라 좌우 두 점의 수평 기울기)도
쓰임(관상면 좌우 비교 vs 시상면 굽힘 판정)도 완전히 달라 서로 의존 관계가 없었다.
"""

import math

from app.schemas import Landmark

# MediaPipe Pose가 반환하는 33개 관절 좌표 중, 어깨/골반 좌우 기울기(AI-15) 계산에
# 필요한 인덱스만 정의. (공식 인덱스 정의:
# https://ai.google.dev/edge/mediapipe/solutions/vision/pose_landmarker)
LEFT_SHOULDER = 11
RIGHT_SHOULDER = 12
LEFT_HIP = 23
RIGHT_HIP = 24


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
