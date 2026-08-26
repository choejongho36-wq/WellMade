"""
관절 3점 좌표로 각도를 계산하는 모듈.

WellMade는 무거운 자세추정(MediaPipe Pose)을 클라이언트(브라우저)에서 실행하고,
AI 서버는 결과 좌표(33개 관절)만 받아 "각도 계산 → 규칙 판정"이라는 가벼운 연산만 수행한다.
이 파일은 그중 "각도 계산" 담당이며, insight/posture_percentile.py(AI-15)가 이 함수들을
가져다 쓴다.

이 파일에는 get_shoulder_tilt_angle/get_pelvis_tilt_angle(정면 좌우 기울기, AI-15 전용)만
있다 — 관절 3점 각도가 아니라 좌우 두 점의 수평 기울기를 계산하는 함수들이다. 실시간
코칭(AI-06)은 프론트가 이미 계산한 각도 값을 받으므로(각도 계산을 서버가 하지 않음) 이
파일의 함수를 쓰지 않는다.
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
    자세 비교 인사이트(AI-15)용 — 어깨가 앞으로 말렸는지(시상면) 판정과는 완전히 다른
    축(관상면, 좌우 높이 차이)의 측정값이라 정면 카메라가 있어야만 계산할 수 있다.

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
