
"""
AI 서버의 시작점.
'uvicorn app.main:app --reload' 명령어로 이 서버를 실행한다.
"""
 
from fastapi import FastAPI
from app.schemas import PoseAnalyzeRequest, PoseAnalyzeResponse, PoseIssue
from app.pose.rules import judge_static_pose
 
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
    result = judge_static_pose(request.landmarks, request.exercise_type)
 
    return PoseAnalyzeResponse(
        is_normal=result["is_normal"],
        confidence=result["confidence"],
        issues=[PoseIssue(**issue) for issue in result["issues"]],
    )
 