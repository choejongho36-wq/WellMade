"""
MediaPipe Pose(BlazePose) 33개 키포인트 인덱스 <-> 이름 매핑.

요구사항정의서 5장 Tool 명세의 detect_keypoints 출력(keypoints[])이
이 이름 체계를 따른다. mediapipe Tasks API(PoseLandmarker)는 idx만
반환하므로, 여기서 이름을 붙여준다.
"""

from __future__ import annotations

# BlazePose 33 keypoints 공식 순서 (index == 리스트 위치)
POSE_LANDMARK_NAMES: list[str] = [
    "nose",
    "left_eye_inner",
    "left_eye",
    "left_eye_outer",
    "right_eye_inner",
    "right_eye",
    "right_eye_outer",
    "left_ear",
    "right_ear",
    "mouth_left",
    "mouth_right",
    "left_shoulder",
    "right_shoulder",
    "left_elbow",
    "right_elbow",
    "left_wrist",
    "right_wrist",
    "left_pinky",
    "right_pinky",
    "left_index",
    "right_index",
    "left_thumb",
    "right_thumb",
    "left_hip",
    "right_hip",
    "left_knee",
    "right_knee",
    "left_ankle",
    "right_ankle",
    "left_heel",
    "right_heel",
    "left_foot_index",
    "right_foot_index",
]

NAME_TO_INDEX: dict[str, int] = {name: i for i, name in enumerate(POSE_LANDMARK_NAMES)}

# 이번 프로젝트(정면/측면 자세 측정)에서 실제로 쓰는 부위만 별칭으로 노출
KEY_POINTS_OF_INTEREST = {
    "left_shoulder": NAME_TO_INDEX["left_shoulder"],
    "right_shoulder": NAME_TO_INDEX["right_shoulder"],
    "left_hip": NAME_TO_INDEX["left_hip"],
    "right_hip": NAME_TO_INDEX["right_hip"],
    "left_ear": NAME_TO_INDEX["left_ear"],
    "right_ear": NAME_TO_INDEX["right_ear"],
}

# 사용자에게 노출할 한국어 부위명.
# LLM에게 영문 랜드마크 이름을 그대로 넘기면 알아서 번역하다가 부정확한
# 표현이 나온다 — 실제로 MVP4 검증 중 LLM이 left_hip을 "왼쪽 엉덩이"로
# 옮기는 사례가 있었다(hip은 엉덩이가 아니라 골반/고관절이다). 번역을
# LLM에게 맡기지 않고 코드가 확정한다. agent_tools의 신뢰도 issue 코드
# 해석을 코드가 미리 해주는 것과 같은 이유다.
LANDMARK_KOREAN_NAMES: dict[str, str] = {
    "left_shoulder": "왼쪽 어깨",
    "right_shoulder": "오른쪽 어깨",
    "left_hip": "왼쪽 골반",
    "right_hip": "오른쪽 골반",
    "left_ear": "왼쪽 귀",
    "right_ear": "오른쪽 귀",
}


def to_korean(name: str) -> str:
    """랜드마크 이름을 한국어 부위명으로 바꾼다. 매핑에 없으면 원문 유지."""
    return LANDMARK_KOREAN_NAMES.get(name, name)
