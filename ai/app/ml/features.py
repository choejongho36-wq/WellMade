"""
런지 자세 ML 분류 모델의 특징(feature) 추출 로직.

왜 이 파일을 따로 두는가?
- 학습 스크립트(ai/ml_training/train_lunge_classifier.py)와 실시간 추론
  (app/ml/lunge_classifier.py)이 "정확히 같은 방식"으로 특징을 뽑아야 한다.
  학습 때와 추론 때 각도 계산 공식이나 특징 순서가 미세하게라도 다르면, 모델이 조용히
  엉뚱한 예측을 내는 train/serve skew 버그로 이어진다. 그래서 이 함수 하나를 두 곳이
  그대로 가져다 쓰게 만들어 그 문제 자체를 구조적으로 차단한다.

왜 랜드마크 원본 좌표(x, y) 대신 계산된 각도를 특징으로 쓰는가?
- rules.py가 이미 "관절 각도"를 판정 기준으로 채택한 것과 같은 이유(각도는 촬영 거리·
  프레임 내 위치가 달라져도 비교적 안정적인 반면, 원본 좌표는 카메라 위치에 따라 값 자체가
  크게 달라짐)로, ML 모델도 원본 좌표보다 각도 기반 특징이 더 일반화가 잘 될 것으로 판단함.
"""

from app.pose.angles import (
    LEFT_ANKLE,
    LEFT_FOOT_INDEX,
    LEFT_HIP,
    LEFT_KNEE,
    LEFT_SHOULDER,
    RIGHT_ANKLE,
    RIGHT_FOOT_INDEX,
    RIGHT_HIP,
    RIGHT_KNEE,
    RIGHT_SHOULDER,
    calculate_angle,
)
from app.schemas import Landmark

# 학습(train_lunge_classifier.py)과 추론(lunge_classifier.py) 양쪽에서 순서를 맞추는 데
# 쓰는 이름 목록. 실제로 모델에 들어가는 값은 이 순서와 반드시 일치해야 한다.
FEATURE_NAMES = [
    "front_knee_angle",  # 앞다리(더 굽혀진 쪽) 무릎 각도 — README 기준 정상범위는 내각 60~135도
    "front_knee_over_toe",  # 앞다리 무릎 x좌표 - 발끝 x좌표. 규칙(각도)만으로 잡기 어려운
    # "무릎이 발끝을 넘었는지" 문제를 ML에 맡기기 위한 특징 (원 데이터 저자도 이 오류는
    # 규칙 대신 ML로 판정했다고 명시함 — README 참고)
    "back_knee_angle",  # 뒷다리 무릎 각도
    "torso_lean_angle",  # 상체(어깨-엉덩이-무릎) 기울기 — 상체가 과도하게 숙여졌는지 참고용
]


def extract_lunge_features(landmarks: list[Landmark]) -> list[float]:
    """
    33개 랜드마크에서 런지 정상/이상 판정에 쓸 4개 특징을 뽑는다.

    "앞다리"를 어떻게 정하는가?
    - 런지 하단 자세에서는 앞으로 내민 다리의 무릎이 더 많이 굽혀진다(각도가 더 작다).
      원본 데이터에 "이 영상에서 어느 쪽이 앞다리인지" 표시가 따로 없어서, 좌/우 무릎 각도
      중 더 작은(더 굽혀진) 쪽을 앞다리로 추정하는 간단한 휴리스틱을 썼다.
    # TODO: 팀 확정 필요 — 프론트가 "왼쪽 다리로 런지 중" 같은 명시적 정보를 함께 보내줄 수
    # 있다면 이 휴리스틱 대신 그 값을 쓰는 게 더 정확하다.
    """
    left_knee_angle = calculate_angle(
        landmarks[LEFT_HIP], landmarks[LEFT_KNEE], landmarks[LEFT_ANKLE]
    )
    right_knee_angle = calculate_angle(
        landmarks[RIGHT_HIP], landmarks[RIGHT_KNEE], landmarks[RIGHT_ANKLE]
    )

    if left_knee_angle <= right_knee_angle:
        front_knee_angle = left_knee_angle
        back_knee_angle = right_knee_angle
        front_knee_x = landmarks[LEFT_KNEE].x
        front_toe_x = landmarks[LEFT_FOOT_INDEX].x
        shoulder, hip, knee = landmarks[LEFT_SHOULDER], landmarks[LEFT_HIP], landmarks[LEFT_KNEE]
    else:
        front_knee_angle = right_knee_angle
        back_knee_angle = left_knee_angle
        front_knee_x = landmarks[RIGHT_KNEE].x
        front_toe_x = landmarks[RIGHT_FOOT_INDEX].x
        shoulder, hip, knee = landmarks[RIGHT_SHOULDER], landmarks[RIGHT_HIP], landmarks[RIGHT_KNEE]

    front_knee_over_toe = front_knee_x - front_toe_x
    torso_lean_angle = calculate_angle(shoulder, hip, knee)

    return [front_knee_angle, front_knee_over_toe, back_knee_angle, torso_lean_angle]
