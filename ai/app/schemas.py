"""
AI 서버가 주고받는 요청/응답 데이터 형태(Pydantic 모델)를 정의하는 모듈.

왜 모든 요청/응답을 Pydantic 모델로 강제하는가?
- 프론트(MediaPipe 추정 결과)와 AI 서버 사이의 "계약"을 코드로 명시해두면,
  형식이 어긋난 요청은 FastAPI가 422 에러로 즉시 알려준다.
  런타임 중간에 잘못된 값(예: 좌표 누락)으로 조용히 엉뚱한 각도가 계산되는 것보다,
  입구에서 바로 막는 편이 디버깅이 훨씬 쉽다.
"""

from typing import List, Literal, Optional
from pydantic import BaseModel, Field

# 지원 종목. 새 종목을 추가할 땐 이 타입과 rules.py의 NORMAL_RANGES를 함께 확장해야 한다.
ExerciseType = Literal["squat", "lunge"]

# 측면 촬영이 전제이므로 좌/우 중 어느 쪽 옆모습인지가 필요하다.
# "auto"는 서버가 visibility(카메라에 보이는 정도)를 보고 알아서 더 신뢰도 높은 쪽을 선택하게 한다.
Side = Literal["left", "right", "auto"]


class Landmark(BaseModel):
    """MediaPipe Pose가 반환하는 관절 좌표 1개.
    x, y는 이미지 기준 0~1 정규화 좌표, z는 카메라 기준 상대 깊이(현재 각도 계산에는 미사용)."""

    x: float
    y: float
    z: float = 0.0
    visibility: float = Field(
        1.0, ge=0.0, le=1.0, description="해당 관절이 카메라에 보이는 정도(0~1). 가려짐/저신뢰 판단에 사용."
    )


class HipFlexibilityCalibration(BaseModel):
    """사용자 개인별 고관절 유연성 캘리브레이션 결과 (선택 입력).

    왜 필요한가?: rules.py에 있는 hip_angle 고정 정상범위(60~100도)는 스포츠의학 문헌 기준
    "개인 고관절 가동범위 차이가 커서 고정값으로는 정확한 판정이 어렵다"고 확인된 값이다.
    그래서 프론트가 세션 시작 전에 "편하게 서 있기"와 "무리하지 않는 선에서 최대한 숙이기"
    두 동작을 한 번 측정해서 보내주면, AI 서버는 그 사람의 실제 가동범위를 기준으로
    정상/이상을 판정한다. 이 필드가 없으면 기존처럼 NORMAL_RANGES 고정값으로 판정한다
    (하위 호환 — 캘리브레이션을 아직 안 한 사용자도 서비스는 계속 쓸 수 있어야 하므로).

    캘리브레이션 동작 자체(측정 UI, 언제 다시 측정할지 등)는 프론트/백엔드 영역이고,
    AI 파트가 책임지는 범위는 "이 두 각도 값을 받아서 판정 기준으로 바꾸는 로직"까지다."""

    standing_hip_angle: float = Field(..., description="편하게 서 있을 때 측정한 hip_angle (보통 180도 근처)")
    max_flex_hip_angle: float = Field(
        ..., description="무리하지 않는 선에서 최대한 숙였을 때 측정한 hip_angle (많이 숙일수록 작은 값)"
    )


class PoseAnalyzeRequest(BaseModel):
    """정지 자세 1차 판정(/ai/pose/analyze) 요청."""

    landmarks: List[Landmark] = Field(
        ..., min_length=33, max_length=33, description="MediaPipe Pose 33개 관절 좌표 (인덱스 순서 고정)"
    )
    exercise_type: ExerciseType
    side: Side = "auto"
    hip_calibration: Optional[HipFlexibilityCalibration] = Field(
        None, description="개인별 고관절 유연성 캘리브레이션 결과. 없으면 고정 NORMAL_RANGES로 판정."
    )


class PoseIssue(BaseModel):
    """판정에서 발견된 이상 소견 1건. RAG 검색 쿼리, 코칭 문구 생성에 그대로 재사용할 수 있도록
    "부위(part)"를 구조화된 값으로 분리해두었다 (자연어 message만 있으면 이후 단계에서 다시 파싱해야 함)."""

    part: str = Field(..., description="이상이 감지된 부위 (예: knee, hip, movement)")
    message: str


class PoseAnalyzeResponse(BaseModel):
    is_normal: bool
    confidence: float
    issues: List[PoseIssue]


# ---- 실시간 코칭 판정 (AI-06) ----
# 동작 단계: 무릎을 굽히는 중(descending) / 펴는 중(ascending) / 거의 멈춰있음(holding)
MotionPhase = Literal["descending", "ascending", "holding"]


class AngleFrame(BaseModel):
    """실시간 코칭용 각도 1프레임.
    정지 자세 판정과 달리 좌표(landmarks) 전체를 다시 보내지 않고, 프론트가 이미 계산한
    무릎/엉덩이 각도 값만 받는다 — "무거운 연산은 클라이언트, 서버는 경량 수치만"이라는
    기술 원칙을 실시간 경로에서도 그대로 지키기 위함. (프레임마다 좌표를 보내면 페이로드가
    커지고, 서버가 매번 각도 계산까지 반복할 이유도 없다.)"""

    timestamp: float = Field(..., description="세션(또는 반복 동작) 시작 기준 경과 시간(초)")
    knee_angle: float
    hip_angle: float


class CoachingFrameRequest(BaseModel):
    """실시간 코칭 판정(/ai/coaching/frame) 요청.
    프론트는 매 호출마다 "최근 N프레임 윈도우"를 통째로 보낸다 (단일 프레임이 아님).
    단일 프레임만으로는 "지금 굽히는 중인지 펴는 중인지" 방향을 알 수 없기 때문."""

    exercise_type: ExerciseType
    angle_history: List[AngleFrame] = Field(
        ...,
        min_length=1,
        description="최근 N프레임 각도 시계열. 오래된 프레임 → 최신 프레임 순으로 정렬되어 있어야 한다.",
    )
    hip_calibration: Optional[HipFlexibilityCalibration] = Field(
        None, description="개인별 고관절 유연성 캘리브레이션 결과. 없으면 고정 NORMAL_RANGES로 판정."
    )


class CoachingFrameResponse(BaseModel):
    phase: MotionPhase
    is_normal: bool
    confidence: float
    issues: List[PoseIssue]


# ---- 세션 종료 조건 판단 (AI-13) ----


class JudgmentRecord(BaseModel):
    """세션이 시작된 이후 프레임(또는 반복 동작)마다 나온 정상/이상 판정 1건.
    /ai/coaching/frame이 프레임마다 돌려준 is_normal 값을, 프론트(또는 백엔드)가
    타임스탬프와 함께 계속 누적해서 보관하고 있다가 세션 종료 판단 시 그대로 넘겨준다는
    전제다 — AI 서버는 세션 상태를 직접 들고 있지 않는 무상태(stateless) 설계를 유지한다."""

    timestamp: float = Field(..., description="세션 시작 기준 경과 시간(초)")
    is_normal: bool


class SessionEndCheckRequest(BaseModel):
    """세션 종료 조건 판단(/ai/session/end-check) 요청."""

    judgment_history: List[JudgmentRecord] = Field(
        ..., min_length=1, description="세션 시작부터 지금까지 누적된 프레임별 정상/이상 판정 이력"
    )
    user_requested_end: bool = Field(
        False, description="사용자가 '운동 종료' 버튼을 직접 눌렀는지 여부. True면 다른 조건과 무관하게 즉시 종료."
    )


class SessionEndCheckResponse(BaseModel):
    should_end: bool
    reason: Literal["user_requested", "target_sustained", "in_progress", "no_data"]
    normal_ratio: float = Field(..., description="판단에 사용한 구간의 정상판정 비율(0~1)")
    window_duration_sec: float = Field(..., description="판단에 사용한 구간의 실제 길이(초)")


# ---- 런지 ML 기반 보조 판정 (전통 ML, 포트폴리오/비교실험 목적 — API 명세 표에 없는 신규 엔드포인트) ----
# 기존 규칙기반 판정(judge_static_pose)을 대체하지 않는 "참고용 2차 의견"이라는 점을 명확히
# 하기 위해 별도 요청/응답 모델로 분리했다. 자세한 배경은 app/ml/lunge_classifier.py 주석 참고.


class MLLungeAnalyzeRequest(BaseModel):
    """런지 ML 보조 판정(/ai/ml/lunge/analyze) 요청.
    특징 추출에 실제로 쓰이는 관절은 일부(어깨/엉덩이/무릎/발목/발끝)지만, 다른 정지 자세
    판정 엔드포인트와 입력 형식을 통일해 프론트 구현 부담을 줄이기 위해 33개 전체를 받는다."""

    landmarks: List[Landmark] = Field(
        ..., min_length=33, max_length=33, description="MediaPipe Pose 33개 관절 좌표 (인덱스 순서 고정)"
    )


class MLLungeAnalyzeResponse(BaseModel):
    is_normal: bool
    correct_probability: float = Field(..., description="학습된 모델이 '정상 자세(C)'로 판단한 확률(0~1)")
    model_name: str = Field(..., description="교차검증으로 선택된 전통 ML 알고리즘 이름 (예: RandomForest)")
