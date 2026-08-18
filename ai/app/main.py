
"""
AI 서버의 시작점.
'uvicorn app.main:app --reload' 명령어로 이 서버를 실행한다.
"""

from fastapi import FastAPI
from app.schemas import PoseAnalyzeRequest, PoseAnalyzeResponse, PoseIssue
from app.schemas import CoachingFrameRequest, CoachingFrameResponse
from app.schemas import SessionEndCheckRequest, SessionEndCheckResponse
from app.schemas import MLLungeAnalyzeRequest, MLLungeAnalyzeResponse
from app.schemas import MLSquatAnalyzeRequest, MLSquatAnalyzeResponse
from app.pose.rules import judge_static_pose
from app.coaching.realtime import judge_realtime_coaching
from app.session.termination import judge_session_end
from app.ml.lunge_classifier import classify_lunge_form
from app.ml.squat_classifier import classify_squat_form

app = FastAPI(title="WellMade AI Server")


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
    """
    result = judge_static_pose(
        request.landmarks, request.exercise_type, hip_calibration=request.hip_calibration
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


@app.post("/ai/ml/lunge/analyze", response_model=MLLungeAnalyzeResponse)
def ml_lunge_analyze(request: MLLungeAnalyzeRequest):
    """
    런지 자세 ML 기반 보조 판정 (전통 ML, 포트폴리오/비교실험 목적).
    API 명세 표에 없는 신규 엔드포인트 — 팀 확정 필요.

    기존 /ai/pose/analyze(규칙기반)를 대체하지 않는다. 실제 참가자 영상 기반 라벨
    데이터(NgoQuocBao1010/Exercise-Correction)로 학습한 전통 ML 모델의 "참고용 2차 의견"만
    제공하며, 이 결과를 프론트가 어떻게(그대로 노출 / 규칙기반과 다를 때만 표시 / 미사용)
    쓸지는 팀이 정할 문제다.
    """
    result = classify_lunge_form(request.landmarks)

    return MLLungeAnalyzeResponse(
        is_normal=result["is_normal"],
        correct_probability=result["correct_probability"],
        coaching_message=result["coaching_message"],
        model_name=result["model_name"],
    )


@app.post("/ai/ml/squat/analyze", response_model=MLSquatAnalyzeResponse)
def ml_squat_analyze(request: MLSquatAnalyzeRequest):
    """
    스쿼트 자세 ML 기반 다중분류 보조 판정 (전통 ML, 포트폴리오/비교실험 목적).
    API 명세 표에 없는 신규 엔드포인트 — 팀 확정 필요.

    런지와 달리 정상/이상 이진판정이 아니라 "어떤 오류인지"까지 예측해서, 오류 유형에 맞는
    한국어 교정 문구(coaching_message)를 함께 반환한다. 이 문구를 프론트가 TTS로 읽어주는
    식으로 활용할 것을 염두에 두고 설계했다 — 다만 실제 음성 변환은 프론트엔드가 담당하고
    AI 서버는 텍스트까지만 책임진다 (session 2026-08-18에 사용자와 확인).

    기존 /ai/pose/analyze(규칙기반)를 대체하지 않는다. 상체 숙임(forward lean) 오류는 이
    모델이 아니라 규칙기반 hip_angle 검사가 담당한다 (이유는 app/ml/features.py 참고).
    """
    result = classify_squat_form(request.landmarks)

    return MLSquatAnalyzeResponse(
        predicted_label=result["predicted_label"],
        label_name=result["label_name"],
        is_normal=result["is_normal"],
        correct_probability=result["correct_probability"],
        coaching_message=result["coaching_message"],
        model_name=result["model_name"],
    )
