
"""
AI 서버의 시작점.
'uvicorn app.main:app --reload' 명령어로 이 서버를 실행한다.
"""

from datetime import date

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.schemas import PoseAnalyzeRequest, PoseAnalyzeResponse, PoseIssue
from app.schemas import CoachingFrameRequest, CoachingFrameResponse
from app.schemas import SessionEndCheckRequest, SessionEndCheckResponse
from app.schemas import PostureInsightRequest, PostureInsightResponse
from app.schemas import OrchestrateRequest, OrchestrateResponse
from app.schemas import RagGuideRequest, RagGuideResponse, RagQnaRequest, RagQnaResponse
from app.schemas import SessionReportRequest, SessionReportResponse
from app.pose.rules import judge_static_pose
from app.pose.angles import get_shoulder_tilt_angle, get_pelvis_tilt_angle
from app.coaching.realtime import judge_realtime_coaching
from app.session.termination import judge_session_end
from app.insight.posture_percentile import compute_posture_insight
from app.orchestration.harness import decide_next_action
from app.rag.generation import generate_guide, generate_qna
from app.session.report import generate_session_report

app = FastAPI(title="WellMade AI Server")

# 프론트(Vite 개발 서버, localhost:5173)가 브라우저에서 이 서버를 직접 호출하려면 CORS
# 설정이 필요하다 — 이게 없으면 브라우저가 실제 요청 전에 보내는 사전요청(OPTIONS)이
# 405 Method Not Allowed로 거부되어, POST 요청 자체가 서버에 도달하지 못한다(2026-08-21,
# /ml-test 페이지에서 프론트→AI 서버 직접 호출을 테스트하며 실제로 겪은 문제).
# 로컬 개발용 오리진만 허용해뒀다.
# TODO: 팀 확정 필요 — 실제 배포 도메인이 정해지면 allow_origins를 그 도메인으로 좁혀야
# 한다(지금처럼 로컬 포트만 있는 상태를 운영에도 그대로 쓰면 안 됨).
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",  # Vite 기본 개발 서버 포트
        "http://127.0.0.1:5173",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health_check():
    """서버가 살아있는지 확인하는 용도 (배포/모니터링 시 사용)"""
    return {"status": "ok"}


@app.post("/ai/pose/analyze", response_model=PoseAnalyzeResponse)
def analyze_pose(request: PoseAnalyzeRequest):
    """
    정지 자세 1차 판정 API (AI-03)
    프론트가 MediaPipe로 뽑은 33개 관절 좌표를 보내면,
    이 서버가 각도 계산 + 정상범위 비교를 해서 결과를 돌려준다.

    front_landmarks(정면 촬영, 2026-08-21 추가)를 함께 보내면 무릎 모임/좌우 비대칭 검사도
    같이 수행한다 — 이 두 항목은 측면 촬영만으로는 관측할 수 없는 관상면(좌우) 판단이라
    정면 촬영이 있어야만 검사할 수 있다(app/pose/rules.py 주석 참고). 안 보내면(기존
    클라이언트) 이 두 검사만 건너뛰고 나머지는 그대로 동작한다.
    """
    result = judge_static_pose(
        request.landmarks,
        request.exercise_type,
        hip_calibration=request.hip_calibration,
        front_landmarks=request.front_landmarks,
    )

    return PoseAnalyzeResponse(
        is_normal=result["is_normal"],
        confidence=result["confidence"],
        issues=[PoseIssue(**issue) for issue in result["issues"]],
    )


@app.post("/ai/coaching/frame", response_model=CoachingFrameResponse)
def coaching_frame(request: CoachingFrameRequest):
    """
    실시간 코칭 판정 API (AI-06)
    프론트가 일정 간격으로 "최근 N프레임 각도 시계열"을 보내면, 현재 동작 단계
    (내려감/올라옴/정지)와 정상/이상 여부, 신뢰도를 계산해 돌려준다.
    프레임마다 새 딥러닝 추론을 돌리는 대신 이미 계산된 각도 값을 규칙기반으로
    비교하는 가벼운 연산이라, 실시간 호출에도 서버 부하 없이 응답할 수 있다.

    각 프레임(AngleFrame)의 knee_valgus_ratio/knee_asymmetry_deg(2026-08-21 추가, 선택
    필드)는 정면 카메라 랜드마크로 프론트가 직접 계산해서 보낸다 — 정지 자세 판정과 달리
    이 엔드포인트는 원본 좌표를 받지 않으므로, 정면 촬영을 지원하려면 이 두 값을 프레임마다
    함께 보내야 한다(app/schemas.py의 AngleFrame 참고).
    """
    result = judge_realtime_coaching(
        request.angle_history, request.exercise_type, hip_calibration=request.hip_calibration
    )

    return CoachingFrameResponse(
        phase=result["phase"],
        is_normal=result["is_normal"],
        confidence=result["confidence"],
        issues=[PoseIssue(**issue) for issue in result["issues"]],
    )


@app.post("/ai/session/end-check", response_model=SessionEndCheckResponse)
def session_end_check(request: SessionEndCheckRequest):
    """
    세션 종료 조건 판단 API (AI-13)
    /ai/coaching/frame이 프레임마다 돌려준 is_normal 값을 프론트(또는 백엔드)가 계속
    누적해뒀다가, "지금 세션을 끝내도 되는지" 물어볼 때 그 누적 이력을 통째로 보낸다.
    (AI 서버는 세션 상태를 직접 들고 있지 않는 무상태 설계를 유지하기 위해, 상태 저장은
    호출부가 책임지고 AI 서버는 판단 로직만 제공한다.)
    """
    result = judge_session_end(request.judgment_history, request.user_requested_end)

    return SessionEndCheckResponse(
        should_end=result["should_end"],
        reason=result["reason"],
        normal_ratio=result["normal_ratio"],
        window_duration_sec=result["window_duration_sec"],
    )


@app.post("/ai/onboarding/posture-insight", response_model=PostureInsightResponse)
def posture_insight(request: PostureInsightRequest):
    """
    자세 비교 인사이트 API (AI-15, 신규 — API 명세 표에 없는 온보딩 캘리브레이션 확장).

    세션 시작 시 "정지 자세에서 정면 촬영"한 랜드마크로 어깨/골반의 좌우 기울기를 재고,
    세종특별자치시 공공데이터(data.go.kr id 15128996) 기반 참조 분포와 비교해
    "비슷한 연령대에서는 몇 %에 해당하는지" 백분위 인사이트를 돌려준다.
    자세한 배경·부호 규칙·백분위 정의는 app/insight/posture_percentile.py 주석 참고.

    다른 정지 자세 판정(/ai/pose/analyze)과 달리 "정상/이상"을 가르지 않는다 — 이 기능은
    참고용 비교 정보만 제공하고, 판정은 기존 규칙기반 로직이 그대로 담당한다.
    """
    shoulder_tilt_deg = get_shoulder_tilt_angle(request.front_landmarks)
    pelvis_tilt_deg = get_pelvis_tilt_angle(request.front_landmarks)
    age = date.today().year - request.birth_year

    result = compute_posture_insight(
        shoulder_tilt_deg=shoulder_tilt_deg,
        pelvis_tilt_deg=pelvis_tilt_deg,
        gender=request.gender,
        age=age,
    )

    return PostureInsightResponse(**result)


@app.post("/ai/orchestrate", response_model=OrchestrateResponse)
def orchestrate(request: OrchestrateRequest):
    """
    하네스 판단 실행 API (AI-07).

    단순 순차 파이프라인이 아니라, 지금까지 쌓인 상황 정보(신뢰도/소견/지속시간/RAG
    검색 상태 등)를 보고 "다음에 뭘 해야 하는지"를 LLM Tool Use로 동적으로 결정한다.
    자세한 판단 규칙(H-01~H-06)과 LLM 호출 실패 시 규칙기반 폴백은
    app/orchestration/harness.py 주석 참고.

    이 엔드포인트는 액션을 "실행"하지 않고 "결정"만 한다 — 예를 들어 trigger_rag_search를
    반환해도 이 함수가 직접 RAG를 호출하지는 않는다. 실제 실행은 이 응답을 받은 백엔드/
    프론트가 담당한다(명세상 응답이 { nextAction, reasoning }인 이유).
    """
    result = decide_next_action(request.session_id, request.context.model_dump())

    return OrchestrateResponse(
        next_action=result["next_action"],
        reasoning=result["reasoning"],
        action_args=result.get("action_args", {}),
        source=result["source"],
        fallback_reason=result.get("fallback_reason"),
    )


@app.post("/ai/rag/guide", response_model=RagGuideResponse)
def rag_guide(request: RagGuideRequest):
    """
    지시형 RAG 가이드 API (AI-09).

    하네스(AI-07)가 trigger_rag_search를 선택하며 돌려준 search_query를 받아, 지식베이스에서
    가장 관련 있는 문서를 찾아 근거 기반 코칭 문구를 만든다. 자세한 검색·생성 방식(TF-IDF
    검색 채택 이유, LLM 실패 시 폴백)은 app/rag/retrieval.py, app/rag/generation.py 주석 참고.
    """
    result = generate_guide(request.query)
    return RagGuideResponse(**result)


@app.post("/ai/rag/qna", response_model=RagQnaResponse)
def rag_qna(request: RagQnaRequest):
    """
    설명형 RAG Q&A API (AI-14).

    사용자가 직접 입력한 자유 질문을 받아, 지식베이스에서 관련 문서를 검색해 근거 기반으로
    답변한다. "문서에 없는 내용은 지어내지 않는다"는 원칙은 app/rag/generation.py의
    시스템 프롬프트에 명시돼 있다.
    """
    result = generate_qna(request.question)
    return RagQnaResponse(**result)


@app.post("/ai/session/report", response_model=SessionReportResponse)
def session_report(request: SessionReportRequest):
    """
    세션 리포트 생성 API (AI-12).

    세션 종료 시(하네스의 end_session 이후) 호출된다고 전제한다. ①각도 편차·정상비율 등을
    규칙기반으로 집계하고, ②그 수치를 근거로 자연어 코칭 요약 문구를 생성한다. 두 단계
    모두의 자세한 설계 이유는 app/session/report.py 주석 참고.
    """
    result = generate_session_report(
        frame_history=[f.model_dump() for f in request.frame_history],
        session_duration_sec=request.session_duration_sec,
        previous_sessions=[p.model_dump() for p in request.previous_sessions],
    )
    return SessionReportResponse(**result)
