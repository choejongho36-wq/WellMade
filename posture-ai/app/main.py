"""
정지 자세 분석 AI 서버.

    uvicorn app.main:app --reload --port 8001

팀 ai 서버(:8000, 운동 동작 코칭)와는 별개 서비스다. 같은 프로젝트 안에
있지만 의존성·배포·포트를 분리한 이유:
  - 서로의 requirements가 섞이지 않는다(한쪽 변경이 다른 쪽 배포에 영향 없음)
  - 한쪽이 죽어도 다른 쪽은 계속 동작한다
  - 팀 저장소의 ai/ backend/ frontend/ 구조와 같은 패턴이다

이 서버는 "정지 자세"(서 있는 자세의 좌우 기울기, 전방머리자세,
라운드숄더)를 다루고, 팀 ai 서버는 "운동 동작"(스쿼트 등)을 다룬다.

엔드포인트:
    POST /posture-api/analyze/front        정면: 어깨·골반 좌우 기울기
    POST /posture-api/analyze/side         측면: 전방머리자세·라운드숄더
    POST /posture-api/analyze/front/agent  정면 + 에이전트 코멘트
    POST /posture-api/analyze/side/agent   측면 + 에이전트 코멘트
    GET  /health

경로가 /posture 가 아니라 /posture-api 인 이유:
    프론트엔드의 React 라우트가 /posture 를 쓴다(정지 자세 분석 페이지).
    nginx 가 location /posture/ 로 이 서버에 프록시하면 **페이지 요청까지
    API 서버로 가로채** 404 가 난다(실제로 배포 후 겪은 문제 —
    "GET /posture/ HTTP/1.1" 404 가 posture-ai 로그에 찍혔다).

    nginx 에서 rewrite 로 우회할 수도 있지만, 그러면 로컬 개발(:8001 직접
    호출)과 프로덕션(nginx 경유)의 경로가 달라져 디버깅이 어려워진다.
    서버 경로 자체를 분리하면 두 환경이 같아진다.

/agent 경로를 따로 둔 이유는 기존 경로의 응답이 바뀌지 않도록 잠그기
위해서다 — 옵션 플래그로 섞으면 회귀를 테스트로 확인하기 어렵다.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .agent import MAX_TURNS, run_agent
from .analysis import DISCLAIMER, analyze_front, analyze_side
from .comment import DEFAULT_MODEL, comment_for_analysis, comment_for_side_analysis
from .env import load_env
from .keypoints import from_landmark_list
from .schemas import (
    FrontAnalyzeResponse,
    PostureAnalyzeRequest,
    SideAnalyzeResponse,
)

load_env()

app = FastAPI(title="Posture AI (정지 자세 분석)", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "llm_model": DEFAULT_MODEL, "max_turns": MAX_TURNS}


def _to_result(req: PostureAnalyzeRequest, view: str):
    return from_landmark_list(
        [lm.model_dump() for lm in req.landmarks],
        view=view,
        image_width=req.image_width,
        image_height=req.image_height,
    )


def _attach(result: dict[str, Any], comment_obj) -> dict[str, Any]:
    """분석 결과에 코멘트를 덧붙인다. 기존 필드는 절대 수정하지 않는다."""
    result["comment"] = (
        comment_obj.to_dict()
        if hasattr(comment_obj, "to_dict")
        else {
            "text": comment_obj.text,
            "source": comment_obj.source,
            "reason": comment_obj.reason,
            "model": comment_obj.model,
        }
    )
    return result


@app.post("/posture-api/analyze/front", response_model=FrontAnalyzeResponse)
def analyze_front_endpoint(req: PostureAnalyzeRequest) -> dict:
    """정면 좌표에서 어깨·골반 좌우 기울기를 판정하고 코멘트를 생성한다."""
    result = analyze_front(_to_result(req, "front"))
    return _attach(result, comment_for_analysis(result))


@app.post("/posture-api/analyze/side", response_model=SideAnalyzeResponse)
def analyze_side_endpoint(req: PostureAnalyzeRequest) -> dict:
    """측면 좌표에서 전방머리자세·라운드숄더를 판정하고 코멘트를 생성한다."""
    result = analyze_side(_to_result(req, "side"))
    return _attach(result, comment_for_side_analysis(result))


@app.post("/posture-api/analyze/front/agent", response_model=FrontAnalyzeResponse)
def analyze_front_agent_endpoint(req: PostureAnalyzeRequest) -> dict:
    """정면 분석 + 에이전트가 도구를 호출해가며 생성한 코멘트."""
    result = analyze_front(_to_result(req, "front"))
    return _attach(result, run_agent(result))


@app.post("/posture-api/analyze/side/agent", response_model=SideAnalyzeResponse)
def analyze_side_agent_endpoint(req: PostureAnalyzeRequest) -> dict:
    """측면 분석 + 에이전트가 도구를 호출해가며 생성한 코멘트."""
    result = analyze_side(_to_result(req, "side"))
    return _attach(result, run_agent(result))


__all__ = ["app", "DISCLAIMER"]
