"""
posture-ai 서버가 주고받는 요청/응답 형태(Pydantic 모델).

Pydantic으로 강제하는 이유는 팀 ai 서버(ai/app/schemas.py)와 같다 —
형식이 어긋난 요청은 FastAPI가 422로 즉시 막아주므로, 잘못된 값이
파이프라인 중간까지 흘러들어가 조용히 엉뚱한 각도가 계산되는 것보다
입구에서 걸러내는 편이 디버깅이 쉽다.

팀 스키마(ai/app/schemas.py의 Landmark)와 좌표 형식은 동일하되,
image_width/image_height를 추가로 받는다 — 종횡비 보정에 필요한데
정규화 좌표만으로는 알 수 없는 값이기 때문이다
(app/keypoints.py의 pixel_xy 참고).
"""

from __future__ import annotations

from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field

Verdict = Literal["정상", "경미", "주의"]


class Landmark(BaseModel):
    """MediaPipe Pose가 반환하는 관절 좌표 1개.

    x, y는 이미지 기준 0~1 정규화 좌표, z는 카메라 기준 상대 깊이다.
    z는 측면 촬영에서 "어느 쪽이 카메라에 가까운가"를 판정하는 데 실제로
    쓴다(quality.determine_near_side) — 실측에서 좌우 귀의 visibility
    차이는 0에 가까운 반면 z 차이는 뚜렷했기 때문이다.
    """

    x: float
    y: float
    z: float = 0.0
    visibility: float = Field(
        1.0, ge=0.0, le=1.0, description="관절이 카메라에 보이는 정도(0~1). 가려짐/저신뢰 판단에 사용."
    )


class PostureAnalyzeRequest(BaseModel):
    """정지 자세 분석 요청 (정면/측면 공통).

    사진 자체는 받지 않는다 — 브라우저가 MediaPipe로 좌표를 뽑아 보내므로
    신체 사진이 서버에 도달하지 않는다. 전송량도 수 MB에서 수 KB로 줄어든다.
    """

    landmarks: List[Landmark] = Field(
        ...,
        min_length=33,
        max_length=33,
        description="MediaPipe Pose 33개 관절 좌표. 인덱스 순서 그대로 보낼 것.",
    )
    image_width: int = Field(
        ..., gt=0, description="원본 이미지 가로 픽셀. 종횡비 보정에 사용(정사각형이 아닌 사진에서 각도 왜곡 방지)."
    )
    image_height: int = Field(..., gt=0, description="원본 이미지 세로 픽셀.")


class MetricResult(BaseModel):
    angle_deg: float
    verdict: Verdict
    note: Optional[str] = Field(None, description="이 지표의 한계나 주의사항(예: 임상 확립 기준 없음).")


class QualityInfo(BaseModel):
    is_valid: bool
    issue: str = Field("", description="문제가 있을 때 그 사유. 없으면 빈 문자열.")


class ReliabilityInfo(BaseModel):
    is_reliable: bool
    issues: List[str] = Field(default_factory=list)


class KeypointConfidence(BaseModel):
    name: str
    visibility: float
    band: str = Field(..., description="신뢰도 등급: 높음 | 보통 | 낮음")


class CommentInfo(BaseModel):
    """자연어 코멘트. 생성 실패나 신뢰도 미달 시에도 항상 문구가 들어간다."""

    text: str
    source: Literal["llm", "agent", "fallback", "skipped"]
    reason: str = Field("", description="fallback/skipped인 경우 그 사유.")
    model: str = ""
    turns: Optional[int] = Field(None, description="에이전트 모드에서 루프를 돈 횟수.")
    tool_calls: Optional[List[Dict]] = Field(
        None, description="에이전트 모드에서 실제로 호출한 도구 기록."
    )


class FrontAnalyzeResponse(BaseModel):
    success: bool
    view: Literal["front"]
    quality: QualityInfo
    reliability: ReliabilityInfo
    confidence: float
    keypoint_confidence: List[KeypointConfidence]
    shoulder: MetricResult
    pelvis: MetricResult
    disclaimer: str
    comment: Optional[CommentInfo] = None


class SideAnalyzeResponse(BaseModel):
    success: bool
    view: Literal["side"]
    near_side: Literal["left", "right"] = Field(
        ..., description="각도 계산에 실제로 사용한 쪽(카메라에 가까운 쪽)."
    )
    near_side_determined: bool = Field(
        ...,
        description="근접 측 판정이 엄격 기준(z 깊이 차이)을 통과했는지. "
        "False면 near_side는 최선의 추정치일 뿐이며 reliability도 함께 False다.",
    )
    quality: QualityInfo
    reliability: ReliabilityInfo
    confidence: float
    keypoint_confidence: List[KeypointConfidence]
    forward_head: MetricResult
    round_shoulder: MetricResult
    disclaimer: str
    comment: Optional[CommentInfo] = None
