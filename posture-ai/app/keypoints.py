"""
관절 좌표 데이터 구조 (좌표 입력 전용 — MediaPipe 미포함).

posture-mvp의 app/keypoints.py에서 **자세추정 실행 부분만 제거**한 것이다.
데이터 구조(Keypoint, KeypointResult)와 pixel_xy() 종횡비 보정은 그대로
가져왔다 — 이 둘이 바뀌면 quality.py의 모든 검증이 어긋난다.

왜 서버가 자세추정을 하지 않는가:
    브라우저(@mediapipe/tasks-vision)가 이미 좌표를 뽑아 보내주므로 서버가
    다시 할 이유가 없다. 그리고 사진을 서버로 보내지 않으면:
      - 신체 사진이 사용자 기기를 벗어나지 않는다(전송·로그·크래시덤프
        어디에도 남지 않음)
      - mediapipe(~100MB) 의존성이 빠져 배포 이미지가 가벼워진다

    실측 검증(scripts/verify_landmark_input.py)에서 좌표 입력만으로도
    각도·판정·quality·reliability가 이미지 입력과 **완전히 동일**하게
    나오는 것을 확인했다. 유일한 차이는 person_detection 등급이
    "강함"에서 "보통"으로 내려가는 것인데, 이 등급은 원래 is_reliable을
    떨어뜨리지 않는다(quality.assess_combined_reliability는 "약함"만
    문제로 본다). 마네킹 방어도 세그멘테이션이 아니라
    check_geometric_plausibility가 담당하므로 그대로 유지된다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from .landmarks import KEY_POINTS_OF_INTEREST, POSE_LANDMARK_NAMES

View = Literal["front", "side"]


@dataclass
class Keypoint:
    name: str
    x: float
    y: float
    z: float
    visibility: float

    def xy(self) -> tuple[float, float]:
        return (self.x, self.y)


@dataclass
class KeypointResult:
    view: View
    keypoints: list[Keypoint] = field(default_factory=list)
    confidence: float = 0.0
    # 원본 이미지 픽셀 크기. 각도 계산 시 종횡비 보정에 쓴다(pixel_xy 참고).
    # 좌표만으로는 알 수 없는 값이라 클라이언트가 함께 보내야 한다.
    image_width: int = 1
    image_height: int = 1

    def get(self, name: str) -> Keypoint:
        for kp in self.keypoints:
            if kp.name == name:
                return kp
        raise KeyError(f"keypoint '{name}' not found in detection result")

    def pixel_xy(self, name: str) -> tuple[float, float]:
        """
        종횡비가 보정된 좌표를 반환한다. 각도 계산(angles.py)에는 반드시
        이 메서드를 써야 한다.

        MediaPipe는 x를 이미지 너비 대비, y를 이미지 높이 대비로 각각
        따로 정규화한다(둘 다 0~1). 이미지가 정사각형이 아니면(예:
        720x900 세로 사진) 두 축의 실제 물리적 스케일이 다른데, xy()가
        주는 (x, y)를 그대로 atan2 각도 공식에 넣으면 축마다 다른 배율이
        섞여 각도가 왜곡된다. 실측에서 720x900 사진의 forward_head가
        약 6도 어긋나는 것을 확인했다.

        각도 공식은 비율만 보므로(atan2), 픽셀 값의 절대 크기는 상관없다
        — 종횡비(width/height)만 맞으면 된다.
        """
        kp = self.get(name)
        return (kp.x * self.image_width, kp.y * self.image_height)

    def interest_point_coords(self) -> list[tuple[float, float]]:
        """검증에 쓰는 주요 관절의 (x, y) 목록."""
        out = []
        for name in KEY_POINTS_OF_INTEREST:
            try:
                out.append(self.get(name).xy())
            except KeyError:
                continue
        return out


def from_landmark_list(
    landmarks: list[dict],
    view: View,
    image_width: int,
    image_height: int,
) -> KeypointResult:
    """
    클라이언트가 보낸 33개 랜드마크 배열을 KeypointResult로 변환한다.

    Args:
        landmarks: [{x, y, z, visibility}, ...] 33개. MediaPipe Pose의
            인덱스 순서 그대로여야 한다(landmarks.POSE_LANDMARK_NAMES 참고).
        view: "front" | "side"
        image_width/height: 원본 이미지 픽셀 크기 (pixel_xy 종횡비 보정용)

    Returns:
        KeypointResult

    Raises:
        ValueError: 랜드마크 개수가 33개가 아닐 때. 인덱스와 관절 이름을
            대응시키는 구조라 개수가 다르면 전혀 다른 관절을 참조하게 된다.
    """
    expected = len(POSE_LANDMARK_NAMES)
    if len(landmarks) != expected:
        raise ValueError(
            f"랜드마크는 {expected}개여야 합니다 (받은 개수: {len(landmarks)}). "
            "MediaPipe Pose의 33개 전체를 인덱스 순서 그대로 보내주세요."
        )

    keypoints = [
        Keypoint(
            name=POSE_LANDMARK_NAMES[i],
            x=float(lm["x"]),
            y=float(lm["y"]),
            z=float(lm.get("z", 0.0)),
            visibility=float(lm.get("visibility", 1.0)),
        )
        for i, lm in enumerate(landmarks)
    ]
    confidence = sum(kp.visibility for kp in keypoints) / len(keypoints)
    return KeypointResult(
        view=view,
        keypoints=keypoints,
        confidence=confidence,
        image_width=image_width,
        image_height=image_height,
    )


def keypoints_from_raw(
    raw: dict[str, tuple[float, float, float, float]],
    view: View,
    image_width: int = 1,
    image_height: int = 1,
) -> KeypointResult:
    """
    테스트용: 관절 이름으로 좌표를 직접 주입한다.
    raw = {"left_shoulder": (x, y, z, visibility), ...}
    """
    keypoints = [
        Keypoint(name=name, x=v[0], y=v[1], z=v[2], visibility=v[3])
        for name, v in raw.items()
    ]
    confidence = (
        sum(kp.visibility for kp in keypoints) / len(keypoints) if keypoints else 0.0
    )
    return KeypointResult(
        view=view,
        keypoints=keypoints,
        confidence=confidence,
        image_width=image_width,
        image_height=image_height,
    )
