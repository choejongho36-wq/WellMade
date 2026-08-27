"""
AI 서버가 주고받는 요청/응답 데이터 형태(Pydantic 모델)를 정의하는 모듈.

왜 모든 요청/응답을 Pydantic 모델로 강제하는가?
- 프론트(MediaPipe 추정 결과)와 AI 서버 사이의 "계약"을 코드로 명시해두면,
  형식이 어긋난 요청은 FastAPI가 422 에러로 즉시 알려준다.
  런타임 중간에 잘못된 값(예: 좌표 누락)으로 조용히 엉뚱한 각도가 계산되는 것보다,
  입구에서 바로 막는 편이 디버깅이 훨씬 쉽다.

스쿼트만 지원한다(런지 등 다른 종목 없음) — 그래서 요청/응답 어디에도 종목을 구분하는
필드가 없다.
"""

from typing import List, Literal, Optional
from pydantic import BaseModel, Field


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

    왜 필요한가?: rules.py에 있는 hip_angle 고정 정상범위는 스포츠의학 문헌 기준
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
    standing_shoulder_hip_ratio: Optional[float] = Field(
        None,
        description="편하게 서 있을 때(standing_hip_angle과 같은 순간) 측정한 어깨-엉덩이 "
        "직선거리/발 길이 비율(app/pose/angles.py의 get_torso_length_ratio 참고). "
        "등이 곧게 펴진 상태의 기준값으로 써서, 실제 자세에서 이 비율이 얼마나 "
        "줄었는지로 '등이 둥글게 말렸는지'(척추 굴곡)를 판정한다. hip_angle 캘리브레이션과 "
        "같은 '편하게 서 있기' 측정 한 번으로 같이 얻을 수 있는 값이라 이 모델에 함께 둔다. "
        "선택 필드 — 없으면(하위 호환) 등 굽음 검사만 건너뛰고 나머지 캘리브레이션은 그대로 "
        "동작한다.",
    )


class PoseIssue(BaseModel):
    """판정에서 발견된 이상 소견 1건. RAG 검색 쿼리, 코칭 문구 생성에 그대로 재사용할 수 있도록
    "부위(part)"를 구조화된 값으로 분리해두었다 (자연어 message만 있으면 이후 단계에서 다시 파싱해야 함)."""

    part: str = Field(..., description="이상이 감지된 부위 (예: knee, hip, movement)")
    message: str


# ---- 실시간 코칭 판정 (AI-06) ----
# 동작 단계: 무릎을 굽히는 중(descending) / 펴는 중(ascending) / 거의 멈춰있음(holding)
MotionPhase = Literal["descending", "ascending", "holding"]


class AngleFrame(BaseModel):
    """실시간 코칭용 각도 1프레임.
    좌표(landmarks) 전체를 보내지 않고, 프론트가 이미 계산한 무릎/엉덩이 각도 값만
    받는다 — "무거운 연산은 클라이언트, 서버는 경량 수치만"이라는 기술 원칙을 실시간
    경로에서도 그대로 지키기 위함. (프레임마다 좌표를 보내면 페이로드가 커지고, 서버가
    매번 각도 계산까지 반복할 이유도 없다.)

    아래 필드 설명 중 "app/pose/angles.py의 get_X 참고"는 그 각도가 어떻게 계산되는지에
    대한 정의를 가리킨다 — 실제 계산은 프론트가 동일한 로직을 JS로 미러링해 매 프레임
    수행해서 이 값들을 보내주고, 서버는 받은 값을 비교만 한다.
    """

    timestamp: float = Field(..., description="세션(또는 반복 동작) 시작 기준 경과 시간(초)")
    knee_angle: float
    hip_angle: float
    shoulder_angle: Optional[float] = Field(
        None,
        description="귀-어깨-엉덩이 절대각도(어깨 정렬). 어깨 판정에는 쓰이지 않는다"
        "(shoulder_forward_lean_deg로 대체됨, 아래 참고) — 이 필드는 참고용으로만 "
        "남아있고, 안 보내도 아무 영향 없다.",
    )
    shoulder_forward_lean_deg: Optional[float] = Field(
        None,
        description="목이 상체 기울기보다 얼마나 더 앞으로 기울었는지(app/pose/angles.py의 "
        "get_shoulder_forward_lean_deg 참고) — 상체가 앞으로 기울어도 목이 정상적으로 "
        "세워져 있으면 오탐하지 않도록, 절대각도가 아니라 상체 대비 상대각도로 계산한다. "
        "heel_lift_ratio/knee_over_toe_ratio와 동일하게 측면 랜드마크만으로 계산 가능한 값이라, "
        "프론트가 매 프레임 직접 계산해서 보낸다. 선택 필드 — 없으면(하위 호환) 어깨 검사를 "
        "건너뛴다.",
    )
    heel_lift_ratio: Optional[float] = Field(
        None,
        description="발뒤꿈치 들림 비율(app/pose/angles.py의 get_heel_lift_ratio 참고). "
        "선택 필드 — 없으면 발뒤꿈치 검사를 건너뛴다(하위 호환, shoulder_angle과 동일한 이유).",
    )
    knee_valgus_ratio: Optional[float] = Field(
        None,
        description="정면 촬영 기준 무릎 모임 비율(app/pose/angles.py의 get_knee_valgus_ratio 참고). "
        "프론트가 정면 카메라 랜드마크로 매 프레임 직접 계산해서 보낸다 — "
        "무거운 연산(좌표 계산)은 클라이언트가 담당한다는 원칙을 이 필드에도 그대로 적용. "
        "선택 필드 — 없으면(정면 카메라 미지원 클라이언트) 무릎 모임 검사를 건너뛴다(하위 호환).",
    )
    knee_asymmetry_deg: Optional[float] = Field(
        None,
        description="정면 촬영 기준 좌우 무릎 굽힘 각도 차이(app/pose/angles.py의 "
        "get_knee_lr_asymmetry_deg 참고). knee_valgus_ratio와 동일한 이유로 "
        "프론트가 직접 계산해서 보낸다. 선택 필드 — 없으면 좌우 비대칭 검사를 건너뛴다(하위 호환).",
    )
    knee_over_toe_ratio: Optional[float] = Field(
        None,
        description="무릎이 발끝보다 앞으로 나간 정도(app/pose/angles.py의 "
        "get_knee_over_toe_ratio 참고) — 무릎-발끝 거리를 허벅지(엉덩이-무릎) 길이로 나눈 "
        "비율이다. (2026-08-27 변경) 예전에는 정규화 없는 원시 좌표 거리였는데, 발이 "
        "스탠스 때문에 바깥으로 돌아가면(외회전) 발 길이 자체가 줄어들어 자로 쓰기 "
        "불안정하다는 게 확인돼(자세한 배경은 checklist 2026-08-27 addendum 참고) 허벅지 "
        "길이 기준으로 바꿨다. heel_lift_ratio와 동일하게 측면 랜드마크 기준이라 프론트가 "
        "매 프레임 직접 계산해서 보낸다. 선택 필드 — 없으면 이 검사를 건너뛴다(하위 호환).",
    )
    torso_length_ratio: Optional[float] = Field(
        None,
        description="어깨-엉덩이 직선거리/발 길이 비율(app/pose/angles.py의 "
        "get_torso_length_ratio 참고). hip_calibration에 standing_shoulder_hip_ratio가 함께 "
        "있을 때만 '등이 둥글게 말렸는지' 판정에 쓰인다(기준값 없이는 이 숫자 하나만으로는 "
        "판단 불가). 선택 필드 — 없으면 등 굽음 검사를 건너뛴다(하위 호환).",
    )
    torso_shin_lean_gap_deg: Optional[float] = Field(
        None,
        description="상체(어깨-엉덩이)와 정강이(무릎-발목)가 각각 수직선 대비 얼마나 기울었는지의 "
        "차이(app/pose/angles.py의 get_torso_shin_lean_gap_deg 참고) — 무게중심이 지지기반(발) "
        "뒤쪽에 남는 자세('앞에 반대 방향 무게가 없으면 뒤로 넘어갈 것 같은' 자세)를 잡기 위한 "
        "신호다. (2026-08-27 추가) '무게중심이 무너진 것 같다'고 지적된 실제 사진 2장에서 "
        "27.2도·28.9도가 나왔고, 확인된 정상 사진 10장은 -2.0~23.3도 사이였다 — 상체·정강이 "
        "절대 기울기는 체형에 따라 개별적으로는 편차가 컸지만 그 차이값은 정상군과 갈렸다 "
        "(자세한 배경은 checklist 2026-08-27 addendum 8번 참고). 측면 랜드마크만으로 계산 "
        "가능한 값이라 heel_lift_ratio/knee_over_toe_ratio와 동일하게 프론트가 매 프레임 직접 "
        "계산해서 보낸다. 선택 필드 — 없으면 이 검사를 건너뛴다(하위 호환). "
        "TODO: 팀 확정 필요(중요) — 나쁜 사례 표본이 아직 2건뿐이라 임계값 검증이 매우 약하다.",
    )


class CoachingFrameRequest(BaseModel):
    """실시간 코칭 판정(/ai/coaching/frame) 요청.
    프론트는 매 호출마다 "최근 N프레임 윈도우"를 통째로 보낸다 (단일 프레임이 아님).
    단일 프레임만으로는 "지금 굽히는 중인지 펴는 중인지" 방향을 알 수 없기 때문."""

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


# ---- 자세 비교 인사이트 (AI-15, 신규 — API 명세 표에 없는 온보딩 캘리브레이션 확장) ----
# 세션 시작 시 정면 촬영으로 어깨/골반의 좌우 기울기를 재고, 공공데이터 기반 참조 분포와
# 비교해 백분위 인사이트를 준다. 자세한 배경은 app/insight/posture_percentile.py 참고.

# 참조 분포(세종시 공공데이터)의 성별 표기를 그대로 따른다. 새 값을 늘리려면
# ml_training/prepare_posture_reference.py의 참조 데이터도 함께 확장해야 한다.
Gender = Literal["M", "F"]


class PostureInsightRequest(BaseModel):
    """자세 비교 인사이트(/ai/onboarding/posture-insight) 요청.

    다른 엔드포인트와 달리 "정면 촬영" 랜드마크만 받는다 — 어깨/골반의 좌우 높이차
    (관상면)는 정면 카메라가 있어야 계산할 수 있고, 기존 측면 촬영 랜드마크로는 잴 수 없는
    값이기 때문이다(app/pose/angles.py의 get_shoulder_tilt_angle 참고). 온보딩 단계에서
    측면 촬영도 함께 이루어지지만(고관절 유연성 캘리브레이션용), 그건 이 계산과 무관해
    여기서는 받지 않는다 — 엔드포인트 입력은 실제로 쓰는 데이터로만 최소화한다는 원칙.
    """

    front_landmarks: List[Landmark] = Field(
        ..., min_length=33, max_length=33, description="정면 촬영 기준 MediaPipe Pose 33개 관절 좌표"
    )
    gender: Gender = Field(..., description="참조 분포 그룹을 나누는 기준. 세종시 공공데이터의 성별 표기를 따름")
    birth_year: int = Field(..., ge=1900, le=2026, description="출생년도. 서버가 현재 연도 기준으로 나이/연령대를 계산한다")


class PostureInsightResponse(BaseModel):
    age_bracket: int = Field(..., description="비교에 사용한 연령대 (10=10대, ..., 60=60대 이상)")
    sample_size: int = Field(..., description="비교 대상 참조 그룹의 표본 수")
    low_sample_warning: bool = Field(..., description="표본이 적어(MIN_RELIABLE_SAMPLE 미만) 참고용으로만 봐야 하는 경우 True")

    shoulder_tilt_deg: float = Field(..., description="어깨 좌우 기울기(도). 양수=왼쪽이 올라감, 음수=오른쪽이 올라감")
    shoulder_side: Literal["left", "right", "level"]
    shoulder_percentile: Optional[float] = Field(None, description="같은 성별·연령대 중 이 기울기 크기 이하인 비율(%)")
    shoulder_message: str

    pelvis_tilt_deg: float = Field(..., description="골반 좌우 기울기(도). 양수=왼쪽이 올라감, 음수=오른쪽이 올라감")
    pelvis_side: Literal["left", "right", "level"]
    pelvis_percentile: Optional[float] = Field(None, description="같은 성별·연령대 중 이 기울기 크기 이하인 비율(%)")
    pelvis_message: str

    message: str = Field(..., description="어깨+골반 인사이트를 하나로 합친 한국어 문구 (TTS로 바로 읽을 수 있는 텍스트)")


# ---- 하네스 오케스트레이션 (AI-07) ----
# LLM Tool Use 기반으로 "다음에 어떤 행동을 할지"를 동적으로 결정한다. 자세한 배경·판단
# 규칙(H-01~H-06)은 app/orchestration/harness.py 주석 참고.

# 요구사항 정의서 "2.하네스판단로직" 시트의 "선택 가능 액션"을 도구화한 값과 1:1 대응.
# harness.py의 HARNESS_TOOLS와 반드시 이름이 일치해야 한다 — 여기서 하나 늘리거나 이름을
# 바꾸면 harness.py도 같이 수정해야 함.
NextAction = Literal[
    "request_retake",
    "request_reanalysis",
    "proceed",
    "recommend_expert_consultation",
    "hold_judgment",
    "wait_next_frame",
    "use_generic_guidance",
    "trigger_rag_search",
    "prefer_latest_document",
    "refine_query_and_research",
    "end_session",
]


class OrchestrateContext(BaseModel):
    """하네스가 판단에 쓰는 상황 정보. 전부 선택 필드다 — 호출 시점(정지 자세 판정 중/실시간
    코칭 중/RAG 검색 후/세션 종료 체크 시 등)마다 그때 알 수 있는 값만 채워 보내면 된다."""

    confidence: Optional[float] = Field(None, ge=0.0, le=1.0, description="판정 신뢰도 (H-01, H-03)")
    landmark_visibility: Optional[float] = Field(None, ge=0.0, le=1.0, description="관절 평균 visibility (H-01)")
    issue_type: Optional[str] = Field(None, description="감지된 이상 소견 종류 (H-02, H-04)")
    issue_repeat_count: Optional[int] = Field(None, ge=0, description="동일 소견 반복 감지 횟수 (H-02, H-04)")
    pelvis_height_diff_deg: Optional[float] = Field(None, description="좌우 골반 높이차(도) (H-02)")
    elapsed_normal_time_sec: Optional[float] = Field(None, ge=0.0, description="정상판정 상태 누적 지속시간(초) (H-06)")
    session_end_condition_met: Optional[bool] = Field(None, description="세션 종료 조건(AI-13) 충족 여부 (H-06)")
    user_requested_end: Optional[bool] = Field(None, description="사용자 직접 종료 요청 여부 (H-06)")
    rag_result_count: Optional[int] = Field(None, ge=0, description="RAG 검색 결과 문서 수 (H-05)")
    rag_results_conflicting: Optional[bool] = Field(None, description="RAG 검색 결과 내용 상충 여부 (H-05)")


class OrchestrateRequest(BaseModel):
    """하네스 판단 실행(/ai/orchestrate) 요청. API 명세(5.AI_API명세 시트)의
    { sessionId, context } 형태를 그대로 따르되, 이 코드베이스의 기존 관례대로
    필드명은 snake_case로 옮겼다(예: hip_calibration, angle_history와 동일한 관례)."""

    session_id: str
    context: OrchestrateContext = Field(default_factory=OrchestrateContext)


class OrchestrateResponse(BaseModel):
    next_action: NextAction = Field(..., description="하네스가 결정한 다음 행동")
    reasoning: str = Field(..., description="이 행동을 선택한 이유(한국어)")
    action_args: dict = Field(default_factory=dict, description="액션별 부가 인자 (예: end_session의 end_reason)")
    source: Literal["llm", "fallback"] = Field(
        ..., description="LLM이 직접 판단했는지, LLM 호출이 불가능/실패해 규칙기반 폴백을 썼는지"
    )
    fallback_reason: Optional[str] = Field(None, description="source가 fallback일 때만: 폴백을 쓴 이유")


# ---- RAG 지식베이스 검색·생성 (AI-08/09/14) ----
# 요구사항 정의서 "3.RAG파이프라인" 시트에는 이 두 엔드포인트의 정확한 요청/응답 필드명이
# 표로 정리돼 있지 않다(다른 엔드포인트는 "5.AI_API명세" 시트에 명시돼 있었지만 RAG는
# 파이프라인 단계 설명만 있음) — 그래서 AI-15/ML 엔드포인트와 마찬가지로 기존 코드베이스
# 관례(session_id, snake_case)를 따라 자체적으로 설계했다.
# TODO: 팀 확정 필요 — 실제 프론트/백엔드 연동 시 필드명 재검토.


class RagSource(BaseModel):
    """RAG 응답에 실리는 출처 정보 1건. 요구사항 정의서 ⑦ 출처 표기 단계에 대응."""

    title: str
    source: str = Field(..., description="출처 기관명 (예: NASM, Mayo Clinic)")
    source_url: Optional[str] = None
    source_date: Optional[str] = Field(None, description="지식베이스 문서 작성/확인 시점 (YYYY-MM). knowledge_base.py 주석 참고")


class RagGuideRequest(BaseModel):
    """지시형 RAG 가이드(/ai/rag/guide, AI-09) 요청.
    하네스(AI-07)가 trigger_rag_search를 선택하며 돌려준 search_query를 그대로 받는
    흐름을 전제로 한다 — 즉 이 엔드포인트는 하네스 응답을 받은 백엔드/프론트가 이어서
    호출하는 것을 기대한다(harness.py 모듈 docstring의 "결정과 실행은 분리" 설명 참고)."""

    query: str = Field(..., min_length=1, description="검색 쿼리 (예: 이슈 종류 '무릎 모임', 'knee_valgus')")
    session_id: Optional[str] = None


class RagGuideResponse(BaseModel):
    guidance_message: str = Field(..., description="근거 문서 기반 코칭 문구 (TTS로 바로 읽을 수 있는 한국어 텍스트)")
    sources: List[RagSource]
    matched: bool = Field(..., description="관련 지식베이스 문서를 찾았는지 여부. False면 일반 안내로 대체됨")
    generation_source: Literal["llm", "fallback"] = Field(
        ..., description="LLM이 직접 문구를 생성했는지, 문서에 준비된 고정 문구(short_message)로 대체했는지"
    )


class RagQnaRequest(BaseModel):
    """설명형 RAG Q&A(/ai/rag/qna, AI-14) 요청. 사용자가 자유 형식으로 입력하는 질문을 받는다."""

    question: str = Field(..., min_length=1)
    session_id: Optional[str] = None


class RagQnaResponse(BaseModel):
    answer: str = Field(..., description="근거 문서 기반 답변")
    sources: List[RagSource]
    matched: bool = Field(..., description="관련 지식베이스 문서를 찾았는지 여부")
    generation_source: Literal["llm", "fallback"] = Field(
        ..., description="LLM이 직접 답변을 생성했는지, 검색된 문서를 그대로 발췌해 답했는지"
    )


# ---- 세션 리포트 생성 (AI-12) ----
# TODO: 팀 확정 필요 — 이 기능의 ID가 시트마다 다르게 쓰여 있다(1.AI모듈상세=AI-12,
# 8.요구사항정의서=AI-08). 여기서는 "1.AI모듈상세" 기준(AI-12)으로 구현했다.


class SessionIssueRecord(BaseModel):
    """세션 리포트 집계에 쓰이는 이상 소견 1건. 기존 PoseIssue(part, message)와 달리
    "사람이 읽을 문장(message)" 대신 "집계 가능한 편차 수치(deviation_deg)"를 받는다 —
    리포트는 "무릎 각도가 180도였습니다" 같은 개별 메시지가 아니라 "평균 편차 12도"처럼
    여러 프레임을 합산한 통계가 필요하기 때문이다. deviation_deg는 선택 필드다 — 호출부가
    편차 수치까지는 계산해서 넘기지 않는 경우(예: movement 이슈처럼 각도 하나로 정의되지
    않는 소견)도 있어, 그런 경우는 발생 횟수 집계에만 반영되고 평균 편차 계산에서는 제외된다
    (app/session/report.py의 aggregate_session_stats 참고)."""

    part: str = Field(..., description="이상이 감지된 부위. rules.py/coaching/realtime.py의 PoseIssue.part와 동일 값")
    deviation_deg: Optional[float] = Field(None, description="정상범위 기준 벗어난 정도(도). 계산하지 않았다면 None")


class SessionFrameRecord(BaseModel):
    """세션 리포트 집계에 쓰이는 프레임(또는 반복 동작) 1건의 판정 결과.
    JudgmentRecord(AI-13)와 비슷하지만, 리포트는 "몇 도나 벗어났는지"까지 집계해야 해서
    issues 필드가 추가로 필요하다 — 그래서 별도 모델로 분리했다(JudgmentRecord를
    확장하지 않은 이유: AI-13은 오직 정상/이상 비율만 필요해 issues가 있으면 오히려
    불필요한 페이로드가 커짐)."""

    timestamp: float
    is_normal: bool
    issues: List[SessionIssueRecord] = Field(default_factory=list)


class PreviousSessionSummary(BaseModel):
    """"최근 N회 세션 이력" 중 1건. AI 서버는 세션 이력을 직접 저장하지 않는 무상태
    설계이므로(harness.py/termination.py와 동일 원칙), 비교에 필요한 최소 요약값만 받는다."""

    session_date: Optional[str] = None
    normal_ratio: float = Field(..., ge=0.0, le=1.0)


class SessionReportRequest(BaseModel):
    """세션 리포트 생성(/ai/session/report) 요청."""

    session_id: str
    frame_history: List[SessionFrameRecord] = Field(..., min_length=1, description="세션 시작부터 종료까지의 프레임별 판정 이력")
    session_duration_sec: float = Field(..., ge=0.0)
    previous_sessions: List[PreviousSessionSummary] = Field(
        default_factory=list,
        description="최근 N회 세션 이력(시간순 정렬, 마지막 원소가 가장 최근). 없으면 첫 세션으로 처리해 개선폭을 계산하지 않는다.",
    )
    end_reason: Optional[Literal["target_sustained", "user_requested"]] = Field(
        None, description="세션 종료 사유. 하네스(AI-07)의 end_session 액션이 돌려준 action_args.end_reason을 그대로 넘기는 흐름을 전제로 한다."
    )


class SessionReportResponse(BaseModel):
    normal_ratio: float = Field(..., description="세션 전체 정상 자세 비율(0~1)")
    avg_deviation_deg: Optional[float] = Field(None, description="이상 소견의 평균 편차(도). deviation_deg가 제공된 소견이 하나도 없으면 None")
    most_frequent_issue_part: Optional[str] = Field(None, description="가장 자주 감지된 이상 부위. 이상 소견이 없으면 None")
    improvement_vs_previous_pct: Optional[float] = Field(None, description="직전 세션 대비 정상 비율 개선폭(%p). previous_sessions가 없으면 None")
    recommended_frequency_message: str = Field(..., description="정상 비율 기준 규칙기반 권장 운동 빈도 문구")
    summary_message: str = Field(..., description="세션 전체를 요약하는 한국어 코칭 문구 (TTS로 바로 읽을 수 있는 텍스트)")
    generation_source: Literal["llm", "fallback"] = Field(
        ..., description="LLM이 summary_message를 직접 생성했는지, 규칙기반 템플릿 문구로 대체했는지"
    )
