"""
AI 서버의 시작점.
'uvicorn app.main:app --reload' 명령어로 이 서버를 실행한다.
"""

import os
from datetime import date

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
    ModelCompareRequest,
    ModelCompareResponse,
    OrchestrateRequest,
    OrchestrateResponse,
    PoseIssue,
    PostureInsightRequest,
    PostureInsightResponse,
    RagGuideRequest,
    RagGuideResponse,
    RagQnaRequest,
    RagQnaResponse,
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
from app.coaching.realtime import judge_realtime_coaching
from app.insight.posture_percentile import compute_posture_insight
from app.orchestration.harness import decide_next_action
from app.pose.angles import (
    get_pelvis_tilt_angle,
    get_shoulder_tilt_angle,
)
from app.rag.generation import generate_guide, generate_qna
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

    age = date.today().year - request.birth_year

    result = compute_posture_insight(
        shoulder_tilt_deg=shoulder_tilt_deg,
        pelvis_tilt_deg=pelvis_tilt_deg,
        gender=request.gender,
        age=age,
    )

    return PostureInsightResponse(**result)


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
# AI-09. RAG Guide
# ===========================================================================


@app.post(
    "/ai/rag/guide",
    response_model=RagGuideResponse,
)
def rag_guide(
    request: RagGuideRequest,
):
    """
    지시형 RAG 가이드 API (AI-09).

    하네스가 trigger_rag_search를 선택했을 때 전달한
    검색 질의를 기반으로 지식베이스를 검색하고,
    근거 기반 코칭 문구를 생성한다.
    """

    result = generate_guide(request.query)

    return RagGuideResponse(**result)


# ===========================================================================
# AI-14. RAG Q&A
# ===========================================================================


@app.post(
    "/ai/rag/qna",
    response_model=RagQnaResponse,
)
def rag_qna(
    request: RagQnaRequest,
):
    """
    설명형 RAG Q&A API (AI-14).

    사용자의 자유 질문을 받아 관련 문서를 검색하고
    근거 기반 답변을 생성한다.
    """

    result = generate_qna(request.question)

    return RagQnaResponse(**result)


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