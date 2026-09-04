"""
AI 서버의 시작점.
'uvicorn app.main:app --reload' 명령어로 이 서버를 실행한다.
"""

import os

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

# .env 파일의 값을 os.environ에 주입한다.
# 다른 app.* 모듈 임포트보다 먼저 실행한다.
load_dotenv()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

from app.schemas import (
    CoachingFrameRequest,
    CoachingFrameResponse,
    ExerciseDetailRequest,
    ExerciseDetailResponse,
    ExerciseRecommendRequest,
    ExerciseRecommendResponse,
    ModelCompareRequest,
    ModelCompareResponse,
    OrchestrateRequest,
    OrchestrateResponse,
    PoseIssue,
    PhotoSummaryRequest,
    PhotoSummaryResponse,
    BmiInsightRequest,
    BmiInsightResponse,
    NutritionPeerCompareRequest,
    NutritionPeerCompareResponse,
    PostureInsightRequest,
    PostureInsightResponse,
    SessionEndCheckRequest,
    SessionEndCheckResponse,
    SessionGuideRequest,
    SessionGuideResponse,
    SessionReportRequest,
    SessionReportResponse,
)


# ---------------------------------------------------------------------------
# Services / Business Logic
# ---------------------------------------------------------------------------

from app.coaching.llm_model_compare import compare_models
from app.coaching.photo_summary_llm import summarize_photo_analysis
from app.coaching.realtime import judge_realtime_coaching
from app.exercise.recommend import find_detail as find_exercise_detail
from app.exercise.recommend import recommend as recommend_exercises
from app.insight.age import resolve_age
from app.insight.bmi_percentile import compute_bmi_insight
from app.insight.nutrition_peer import compare_with_peers
from app.insight.posture_percentile import compute_posture_insight
from app.orchestration.harness import decide_next_action
from app.pose.angles import (
    get_pelvis_tilt_angle,
    get_shoulder_tilt_angle,
)
from app.session.guide import get_next_guide
from app.session.report import generate_session_report
from app.session.termination import judge_session_end


# ---------------------------------------------------------------------------
# FastAPI
# ---------------------------------------------------------------------------

app = FastAPI(title="WellMade AI Server")


# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------

# 브라우저가 이 서버를 직접(cross-origin) 호출할 때 CORS가 필요하다.
#
# ALLOWED_ORIGINS:
# 콤마로 구분해서 여러 origin을 지정할 수 있다.
#
# 예:
# ALLOWED_ORIGINS="https://wellmade.example,https://www.wellmade.example"
#
# 운영에서 프론트를 nginx를 통해 같은 origin으로 제공하면
# CORS의 필요성이 줄어들지만, 직접 호출 경로를 대비해 환경변수로 관리한다.
_allowed_origins = os.environ.get(
    "ALLOWED_ORIGINS",
    "http://localhost:5173,http://127.0.0.1:5173",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        origin.strip()
        for origin in _allowed_origins.split(",")
        if origin.strip()
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ===========================================================================
# Health Check
# ===========================================================================


@app.get("/health")
def health_check():
    """
    서버가 살아있는지 확인하는 용도.
    배포 및 모니터링 시 사용한다.
    """
    return {"status": "ok"}


# ===========================================================================
# AI-06. Real-time Squat Coaching
# ===========================================================================


@app.post(
    "/ai/coaching/frame",
    response_model=CoachingFrameResponse,
)
def coaching_frame(request: CoachingFrameRequest):
    """
    실시간 코칭 판정 API (AI-06).

    프론트가 일정 간격으로 최근 N프레임의 각도 시계열을 보내면,
    현재 동작 단계(내려감/올라옴/정지)와 정상/이상 여부,
    신뢰도를 계산해 반환한다.

    프레임마다 새로운 딥러닝 추론을 수행하는 대신,
    이미 계산된 각도 값을 규칙 기반으로 비교하므로
    실시간 호출에도 서버 부하가 낮다.

    knee_valgus_ratio는 정면 카메라 랜드마크를 기반으로
    프론트가 계산하여 전달한다.
    """

    result = judge_realtime_coaching(
        request.angle_history,
        hip_calibration=request.hip_calibration,
        pending_llm_job_id=request.pending_llm_job_id,
    )

    return CoachingFrameResponse(
        phase=result["phase"],
        is_normal=result["is_normal"],
        confidence=result["confidence"],
        issues=[
            PoseIssue(**issue)
            for issue in result["issues"]
        ],
        pending_llm_job_id=result["pending_llm_job_id"],
    )


# ===========================================================================
# 사진 코칭 분석 결과 요약 (app/coaching/photo_summary_llm.py, 2026-09-02)
# ===========================================================================


@app.post(
    "/ai/coaching/photo-summary",
    response_model=PhotoSummaryResponse,
)
def coaching_photo_summary(request: PhotoSummaryRequest) -> PhotoSummaryResponse:
    """
    사진 코칭 "분석 결과" 자연어 요약 API.

    /ai/coaching/frame(AI-06)이 이미 내린 규칙 기반 판정 결과를 받아, 그 결과를 사람이
    읽기 편한 한국어 문장으로 정리해 돌려준다. 판정 자체(정상/이상 여부)는 이 API가
    새로 계산하지 않는다 — 이미 결정된 판정을 설명만 한다.
    """

    result = summarize_photo_analysis(
        is_normal=request.is_normal,
        confidence=request.confidence,
        issues=[issue.model_dump() for issue in request.issues],
        metrics=request.metrics,
        has_front_photo=request.has_front_photo,
    )

    return PhotoSummaryResponse(**result)


# ===========================================================================
# Session Guide
# ===========================================================================


@app.post(
    "/ai/session/guide",
    response_model=SessionGuideResponse,
)
def session_guide(
    request: SessionGuideRequest,
) -> SessionGuideResponse:
    """
    스쿼트 세션 진행 안내 API.

    현재 세션 단계와 프론트엔드에서 발생한 이벤트를 기반으로
    다음 세션 단계와 안내 문구를 결정한다.

    AI 서버의 책임:
    - 세션 진행 단계 결정
    - 다음 카메라 방향 결정
    - 안내 문구 반환

    프론트엔드의 책임:
    - 카메라 전환
    - TTS 실행
    - 사용자 인터랙션
    - 실제 세트 시작/종료 이벤트 전달

    실시간 스쿼트 자세 판정은 /ai/coaching/frame에서 별도로 담당한다.
    """

    try:
        result = get_next_guide(
            current_stage=request.current_stage,
            event=request.event,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    return SessionGuideResponse(**result)


# ===========================================================================
# AI-13. Session End Check
# ===========================================================================


@app.post(
    "/ai/session/end-check",
    response_model=SessionEndCheckResponse,
)
def session_end_check(
    request: SessionEndCheckRequest,
):
    """
    세션 종료 조건 판단 API (AI-13).

    /ai/coaching/frame이 프레임마다 반환한 is_normal 값을
    프론트 또는 백엔드가 누적해두었다가,
    세션을 종료해도 되는지 확인할 때 누적 이력을 전달한다.

    AI 서버는 세션 상태를 직접 저장하지 않는 무상태 설계를 유지한다.
    상태 저장은 호출부가 담당하고 AI 서버는 판단 로직만 제공한다.
    """

    result = judge_session_end(
        request.judgment_history,
        request.user_requested_end,
    )

    return SessionEndCheckResponse(
        should_end=result["should_end"],
        reason=result["reason"],
        normal_ratio=result["normal_ratio"],
        window_duration_sec=result["window_duration_sec"],
    )


# ===========================================================================
# AI-12. Session Report
# ===========================================================================


@app.post(
    "/ai/session/report",
    response_model=SessionReportResponse,
)
def session_report(
    request: SessionReportRequest,
):
    """
    세션 리포트 생성 API (AI-12).

    세션 종료 시 호출된다.

    1. 각도 편차와 정상 비율 등을 규칙 기반으로 집계한다.
    2. 집계된 수치를 기반으로 자연어 코칭 요약을 생성한다.
    """

    result = generate_session_report(
        frame_history=[
            frame.model_dump()
            for frame in request.frame_history
        ],
        session_duration_sec=request.session_duration_sec,
        previous_sessions=[
            previous.model_dump()
            for previous in request.previous_sessions
        ],
    )

    return SessionReportResponse(**result)


# ===========================================================================
# AI-15. Posture Insight
# ===========================================================================


@app.post(
    "/ai/onboarding/posture-insight",
    response_model=PostureInsightResponse,
)
def posture_insight(
    request: PostureInsightRequest,
):
    """
    자세 비교 인사이트 API (AI-15).

    세션 시작 시 정지 자세에서 촬영한 정면 사진의
    랜드마크를 기반으로 어깨/골반 좌우 기울기를 계산하고,
    참조 분포와 비교하여 백분위 인사이트를 반환한다.

    이 API는 다른 팀원의 정면 사진 촬영 기능과 연계되는 영역이다.

    본 작업의 세션 진행 안내에서는 이 단계를 사용하지 않는다.
    """

    shoulder_tilt_deg = get_shoulder_tilt_angle(
        request.front_landmarks
    )

    pelvis_tilt_deg = get_pelvis_tilt_angle(
        request.front_landmarks
    )

    # 연 나이(만 나이보다 최대 1살 많음) - 계산 근거는 app/insight/age.py 한곳에 모아둔다
    age, _ = resolve_age(request.birth_year)

    result = compute_posture_insight(
        shoulder_tilt_deg=shoulder_tilt_deg,
        pelvis_tilt_deg=pelvis_tilt_deg,
        gender=request.gender,
        age=age,
    )

    return PostureInsightResponse(**result)


# ===========================================================================
# 영양 섭취 또래 비교 (posture-insight의 자매 기능)
# ===========================================================================


@app.post(
    "/ai/nutrition/peer-compare",
    response_model=NutritionPeerCompareResponse,
)
def nutrition_peer_compare(
    request: NutritionPeerCompareRequest,
):
    """
    영양 섭취 또래 비교 API.

    백엔드가 집계해둔 하루 섭취량을 받아, 질병관리청 2024 국민건강통계의
    성별×연령대별 평균과 비교한 결과를 돌려준다.

    posture-insight와 달리 백분위가 아니라 "평균 대비 몇 %"를 낸다 —
    원 통계가 집계값(평균+표준오차)만 공개해 분포가 없기 때문이다.
    정상/이상 판정은 하지 않는다(목표 대비 판정은 백엔드의 목표 섭취량 계산이 담당).

    넘어오는 섭취량은 "하루 전체"여야 한다 - 진행 중인 오늘의 부분 합계를 비교하면
    무의미한 비율이 나온다. 그 판단은 날짜·시각을 아는 백엔드가 한다.
    """

    # 생년만 있으면 연 나이라 만 나이보다 최대 1살 많다(구간 경계에서 그룹이 바뀔 수 있음)
    age, _ = resolve_age(request.birth_year, request.birth_date)

    result = compare_with_peers(
        intake={
            "energy_kcal": request.energy_kcal,
            "protein_g": request.protein_g,
            "carbs_g": request.carbs_g,
            "fat_g": request.fat_g,
        },
        gender=request.gender,
        age=age,
    )

    return NutritionPeerCompareResponse(**result)


# ===========================================================================
# BMI 또래 비교 + 비만도 분류 (인바디 수치 해석)
# ===========================================================================


@app.post(
    "/ai/inbody/bmi-insight",
    response_model=BmiInsightResponse,
)
def bmi_insight(
    request: BmiInsightRequest,
):
    """
    BMI 인사이트 API.

    대한비만학회 기준 분류와, 질병관리청 2024 국민건강통계의 성별×연령대별
    백분위수 대비 위치를 함께 돌려준다.

    체지방률·골격근량은 이 통계에 없어 또래 비교를 할 수 없다 — BMI만 지원한다.

    비교는 넘겨받은 BMI 한 건(백엔드가 고른 가장 최근 인바디 기록)에 대해서만 한다.
    키·체중을 같이 주면 그 값으로 BMI를 다시 계산해 교차검증한다.
    """

    age, _ = resolve_age(request.birth_year, request.birth_date)

    result = compute_bmi_insight(
        bmi=request.bmi,
        gender=request.gender,
        age=age,
        height_cm=request.height_cm,
        weight_kg=request.weight_kg,
    )

    return BmiInsightResponse(**result)


# ===========================================================================
# 운동 추천 v1 (챗봇 "운동 추천" 메뉴)
# ===========================================================================


@app.post(
    "/ai/exercise/recommend",
    response_model=ExerciseRecommendResponse,
)
def exercise_recommend(request: ExerciseRecommendRequest):
    """
    운동 추천 후보 조회 API (v1).

    exercises_ko.json에서 부위(+장비)로 필터링한 후보 목록만 돌려준다. 자연어 추천문은
    백엔드 챗봇이 기존 스트리밍 경로로 생성한다(도구 결과를 문장으로 옮기는 패턴).
    RAG/임베딩 없이 정형 필터 — body_part 값이 10종뿐이고 조건도 단순해서 충분하다.
    난이도는 데이터에 없어 여기서 거르지 않는다(생성 단계에서 참고).
    """

    result = recommend_exercises(
        body_part=request.body_part,
        equipment=request.equipment or "",
    )

    return ExerciseRecommendResponse(**result)


@app.post(
    "/ai/exercise/detail",
    response_model=ExerciseDetailResponse,
)
def exercise_detail(request: ExerciseDetailRequest):
    """
    운동 하나의 한국어 수행 방법 조회.

    추천 목록을 보여준 뒤 사용자가 "플랭크는 어떻게 해?"처럼 하나를 지목했을 때 쓴다.
    예전에는 이 단계에서 챗봇이 도구 없이 설명을 직접 지어냈는데, 근거 없는 자유 생성이라
    Qwen이 중국어로 새는 턴이 나왔다(실측). 데이터셋 1,324건 전부에 instructions_ko 가
    있으므로 그걸 그대로 넘겨 "창작"을 "옮겨쓰기"로 바꾼다.
    """

    return ExerciseDetailResponse(**find_exercise_detail(request.name))


# ===========================================================================
# AI-07. Orchestration
# ===========================================================================


@app.post(
    "/ai/orchestrate",
    response_model=OrchestrateResponse,
)
def orchestrate(
    request: OrchestrateRequest,
):
    """
    하네스 판단 실행 API (AI-07).

    현재까지 쌓인 상황 정보(신뢰도, 소견, 지속시간,
    RAG 검색 상태 등)를 기반으로 다음 액션을 결정한다.

    이 엔드포인트는 액션을 직접 실행하지 않고
    다음 액션만 결정한다.
    """

    result = decide_next_action(
        request.session_id,
        request.context.model_dump(),
    )

    return OrchestrateResponse(
        next_action=result["next_action"],
        reasoning=result["reasoning"],
        action_args=result.get("action_args", {}),
        source=result["source"],
        fallback_reason=result.get("fallback_reason"),
    )


# ===========================================================================
# Development - LLM Model Comparison
# ===========================================================================


@app.post(
    "/ai/dev/llm-model-compare",
    response_model=ModelCompareResponse,
)
def llm_model_compare(
    request: ModelCompareRequest,
):
    """
    LLM 모델 비교 테스트 API (개발/테스트 전용).

    실제 서비스 판정 경로가 아니라 모델별 정확도와 지연시간을
    비교하기 위한 개발용 엔드포인트다.
    """

    region = (
        request.region
        or os.environ.get("AWS_BEDROCK_REGION")
    )

    if not region:
        return ModelCompareResponse(
            results={},
            accuracy={},
            error=(
                "리전이 지정되지 않았습니다. "
                "요청의 region 필드나 서버의 "
                "AWS_BEDROCK_REGION 환경변수 중 하나가 필요합니다."
            ),
        )

    result = compare_models(
        reps=[
            representation.model_dump()
            for representation in request.reps
        ],
        model_ids=request.model_ids,
        region=region,
    )

    return ModelCompareResponse(**result)