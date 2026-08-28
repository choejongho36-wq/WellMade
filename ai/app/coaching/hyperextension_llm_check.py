"""
고관절 과신전 LLM 2차 확인 — 측면 DTW+LLM 하이브리드의 LLM 단계 (2026-08-28).

배경: claude/wellmade-ai-progress.md(2026-08-25/26)에서 측면 시계열(knee_angle,
hip_angle, torso 관련 지표)을 LLM에 통째로 보내 판단시켰더니 블라인드 테스트
6/6(100%) 정확도가 나왔다 — hip_angle·torso 기울기처럼 시상면(옆에서 본) 신호가
있어야만 성립하는 판정이라, dtw_matching.py의 DEFAULT_METRIC_FIELDS(측면 지표)와
같은 계열의 데이터를 쓴다. (2026-08-28) 정면 카메라로 만든 hip_hyperextension_frontal
DTW 검사는 애초에 정면 영상엔 이 시상면 신호가 안 잡혀서 과신전을 원리적으로 못
잡는다는 게 실측(실제 프레임 직접 확인)으로 드러났다 — 그 한계를 보완하는 게 이
모듈이다.

왜 DTW 하나로 안 끝내고 LLM까지 2차로 부르는가: 측면 DTW 템플릿(dtw_templates/)은
"정상" 단일 클래스라 최근접거리가 크면 "뭔가 이상하다"까지만 말할 수 있고, 그게
과신전인지 다른 문제인지는 구분 못 한다(rules.py DTW_NEAREST_DISTANCE_THRESHOLD
주석 참고). LLM은 실제로 "과신전이다/아니다"를 판단할 수 있다는 게 위 블라인드
테스트로 확인됐으므로, DTW 거리가 애매한 구간(rules.py DTW_AMBIGUOUS_LOWER_DISTANCE~
DTW_AMBIGUOUS_UPPER_DISTANCE)에 들어온 렙만 LLM에 2차로 넘긴다.

왜 매 렙마다 무조건 LLM을 부르지 않는가: 위 실측 기준 LLM 응답 지연시간이 20~40초
(평균 약 27초), 토큰 비용도 렙 1개당 4.4만~4.6만 토큰으로 상당하다 — 실시간 200ms
폴링(frontend LIVE_SAMPLE_INTERVAL_MS) 응답 하나를 그만큼 묶어두면 코칭 화면이
멈춘 것처럼 보인다. 그래서 DTW로 먼저 걸러낸 애매한 구간만, 그것도 요청-응답을
막지 않는 백그라운드 스레드로 돌린다.

동시성/상태 모델: 이 서버는 원래 완전 무상태(schemas.py의 JudgmentRecord 주석 —
"AI 서버는 세션 상태를 직접 들고 있지 않는 무상태 설계를 유지한다")지만, 백그라운드로
돌아가는 LLM 호출 결과를 어딘가에는 잠깐 담아둬야 한다. "세션"을 통째로 기억하는
대신, job_id 하나에 결과 하나만 담아두는 훨씬 좁은 예외를 뒀다 — 프론트가 이전
응답에서 받은 job_id(CoachingFrameResponse.pending_llm_job_id)를 다음 호출들의
요청(CoachingFrameRequest.pending_llm_job_id)에 그대로 실어 보내면(angle_history를
매번 다시 보내주는 것과 같은 패턴), 서버는 그 job_id로 "이 작업 끝났어?"만 조회해준다.
결과를 한 번 돌려주고 나면 그 job_id는 저장소에서 지운다(1회성 소비) — 세션 전체를
서버가 계속 들고 있는 게 아니다. 결과를 못 받아간 채로 LLM_HYPEREXTENSION_JOB_TTL_SECONDS
(rules.py)가 지나면 그냥 버린다(세션 종료 등으로 다시 물어볼 사람이 없는 경우).

전달 시점: 사용자 제안대로("첫 렙은 DTW 결과만, 애매한 건 얘기도 하지 말고 —
그러다 이후 호출에서 준비돼 있으면 그때 알려줘") 특정 렙에 딱 맞춰 전달하는 게 아니라,
프론트가 pending_llm_job_id를 실어 보내는 매 호출마다 "혹시 준비됐나"만 가볍게
확인한다(dict 조회 1회, 비용 없음) — 대개는 다음 렙이 끝날 때쯤 준비돼 있겠지만,
그보다 빨리 끝나면 더 일찍 전달돼도 무방하다.
"""

from __future__ import annotations

import os
import threading
import time
import uuid
from typing import Any, Optional

try:
    import anthropic

    _ANTHROPIC_AVAILABLE = True
except ImportError:
    _ANTHROPIC_AVAILABLE = False

from app.pose.rules import LLM_HYPEREXTENSION_JOB_TTL_SECONDS
from app.schemas import AngleFrame

# AWS Bedrock 인증(AnthropicBedrock, AWS SigV4 — boto3 필요, requirements.txt 참고).
# harness.py/rag/generation.py/session/report.py도 같은 AWS_REGION_ENV_VAR을 공유한다 —
# 리전은 서버 전체에서 하나면 되므로 모듈마다 따로 안 둔다. 모델 ID만 모듈별로 분리했다
# (이 모듈은 HYPEREXTENSION_BEDROCK_MODEL_ID, 나머지 셋은 HARNESS_BEDROCK_MODEL_ID 공유) —
# 과신전 2차 확인은 다른 세 기능과 별도로 모델을 바꿔 실험할 여지를 남겨둔다.
AWS_REGION_ENV_VAR = "AWS_BEDROCK_REGION"
BEDROCK_MODEL_ID_ENV_VAR = "HYPEREXTENSION_BEDROCK_MODEL_ID"

MAX_TOKENS = 1024

# 프롬프트에 넣는 프레임 수 상한 — 렙이 아주 길어도(카메라가 오래 멈칫하는 등) 토큰
# 비용이 무한정 늘지 않게 균등 다운샘플링한다. 지난 세션 블라인드 테스트가 쓴 샘플
# 간격(0.15초, 약 6.7fps)과 실시간 프론트 샘플 간격(LIVE_SAMPLE_INTERVAL_MS=200ms,
# 5fps)이 이미 비슷한 밀도라 대부분의 렙은 이 상한에 걸리지 않는다.
MAX_PROMPT_FRAMES = 60

# 프롬프트에 실을 측면(시상면) 지표 — dtw_matching.py의 DEFAULT_METRIC_FIELDS와 겹치되,
# 지난 세션 블라인드 테스트에서 유의미했던 torso_shin_lean_gap_deg(무게중심/상체-정강이
# 기울기 차이)까지 추가로 포함한다. AngleFrame의 선택 필드라 프레임마다 없을 수 있음.
_SIDE_FIELDS: tuple[str, ...] = (
    "knee_angle",
    "hip_angle",
    "torso_length_ratio",
    "torso_shin_lean_gap_deg",
    "shoulder_forward_lean_deg",
)

_VERDICT_TOOL_NAME = "report_hip_hyperextension_verdict"
_VERDICT_TOOL = {
    "name": _VERDICT_TOOL_NAME,
    "description": "스쿼트 렙 1개의 측면 관절각도 시계열을 보고 고관절 과신전 여부를 판정해 보고한다.",
    "input_schema": {
        "type": "object",
        "properties": {
            "verdict": {
                "type": "string",
                "enum": ["과신전_의심", "정상"],
                "description": "이 렙에 고관절 과신전(허리를 과도하게 젖히는 보상동작)이 있었는지.",
            },
            "confidence": {
                "type": "string",
                "enum": ["상", "중", "하"],
                "description": "판정 확신도.",
            },
            "reasoning": {
                "type": "string",
                "description": "판정 근거를 한두 문장으로 설명.",
            },
        },
        "required": ["verdict", "confidence", "reasoning"],
    },
}

_SYSTEM_PROMPT = (
    "당신은 스쿼트 자세를 분석하는 운동처방 전문가입니다. 측면에서 촬영한 관절각도 "
    "시계열만 보고, 고관절 과신전(허리를 과도하게 젖히는 보상동작) 여부를 판정해야 "
    "합니다. 단일 프레임의 절대 수치보다, 렙 전체에 걸친 패턴의 형태(예: 저점 이후 "
    "고관절/상체가 완전히 편 상태로 복귀하는지, 상체 기울기가 깊이에 비례해 점진적으로 "
    "느는지 급격히 튀는지)로 판단하세요. report_hip_hyperextension_verdict 도구를 "
    "반드시 한 번 호출해 결과를 보고하세요."
)


def _get_client():
    """AnthropicBedrock 클라이언트를 지연 생성한다. 패키지 미설치·리전 미설정이면
    None을 반환해 호출부가 폴백 경로를 타게 한다 — harness.py의 _get_client()와
    동일한 원칙.

    AnthropicBedrock은 생성 시점엔 자격증명을 검증하지 않고(내부적으로 boto3 체인에
    위임) 실제 요청 시점에야 실패하는데, 여기서는 "리전 환경변수가 있을 때만
    활성화"로 단순하게 판단해 설정 안 된 환경(로컬 개발 등)에서 매번 느린 실패를
    겪지 않고 바로 폴백하게 한다.
    """
    if not _ANTHROPIC_AVAILABLE:
        return None
    region = os.environ.get(AWS_REGION_ENV_VAR)
    if not region:
        return None
    return anthropic.AnthropicBedrock(aws_region=region)


def _downsample(rep_frames: list[AngleFrame], max_frames: int = MAX_PROMPT_FRAMES) -> list[AngleFrame]:
    n = len(rep_frames)
    if n <= max_frames:
        return rep_frames
    step = n / max_frames
    return [rep_frames[int(i * step)] for i in range(max_frames)]


def _build_prompt(rep_frames: list[AngleFrame]) -> str:
    frames = _downsample(rep_frames)
    lines = []
    for f in frames:
        parts = [f"t={f.timestamp:.2f}"]
        for name in _SIDE_FIELDS:
            value = getattr(f, name, None)
            if value is not None:
                parts.append(f"{name}={value:.1f}")
        lines.append(", ".join(parts))
    return (
        "아래는 스쿼트 렙 1개 동안 측면에서 촬영한 관절각도 시계열입니다(프레임 순서대로, "
        "t=경과시간(초)). 각도 단위는 도, torso_length_ratio는 무단위 비율입니다.\n\n"
        + "\n".join(lines)
        + "\n\n이 렙에서 고관절 과신전이 있었는지 판정해주세요."
    )


def _call_llm(rep_frames: list[AngleFrame], client, model: str) -> dict[str, Any]:
    prompt = _build_prompt(rep_frames)
    response = client.messages.create(
        model=model,
        max_tokens=MAX_TOKENS,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
        tools=[_VERDICT_TOOL],
        tool_choice={"type": "tool", "name": _VERDICT_TOOL_NAME},
    )
    for block in response.content:
        if getattr(block, "type", None) == "tool_use" and block.name == _VERDICT_TOOL_NAME:
            data = block.input
            return {
                "verdict": data.get("verdict"),
                "confidence": data.get("confidence"),
                "reasoning": data.get("reasoning", ""),
            }
    raise ValueError("LLM 응답에 report_hip_hyperextension_verdict tool_use 블록이 없습니다.")


# ---- job 저장소 (job_id -> 상태/결과), 프로세스 메모리, 스레드 안전 ----
_jobs: dict[str, dict[str, Any]] = {}
_jobs_lock = threading.Lock()


def _cleanup_expired_locked() -> None:
    """_jobs_lock을 쥔 상태에서만 호출해야 한다. TTL 지난 job을 지운다 — 별도 정리
    스레드를 두지 않고, start/get 호출 시점에 얹혀서(opportunistic) 정리한다."""
    now = time.time()
    expired = [
        job_id
        for job_id, entry in _jobs.items()
        if now - entry["created_at"] > LLM_HYPEREXTENSION_JOB_TTL_SECONDS
    ]
    for job_id in expired:
        del _jobs[job_id]


def _run_job(job_id: str, rep_frames: list[AngleFrame], client, model: str) -> None:
    """백그라운드 스레드(또는 테스트에서 동기적으로)에서 실제 LLM 호출을 수행한다.
    예외를 여기서 다 삼키는 이유: 백그라운드 스레드에서 예외가 그대로 새 나가면
    스레드가 조용히 죽을 뿐 아무도 알 수 없다 — 대신 job 상태를 "error"로 남겨
    get_job_result()가 "결과 없음"으로 조용히 처리하게 한다(이 기능 자체가 실험적
    보조 기능이라, 실패했다고 사용자에게 이상한 메시지를 보여줄 필요는 없다)."""
    try:
        result = _call_llm(rep_frames, client, model)
        with _jobs_lock:
            if job_id in _jobs:
                _jobs[job_id]["status"] = "done"
                _jobs[job_id]["result"] = result
    except Exception as e:  # noqa: BLE001 - 백그라운드 작업 실패를 조용히 기록만 함(위 설명 참고)
        with _jobs_lock:
            if job_id in _jobs:
                _jobs[job_id]["status"] = "error"
                _jobs[job_id]["error"] = str(e)


def start_hyperextension_analysis(
    rep_frames: list[AngleFrame],
    client=None,
    model: Optional[str] = None,
    run_in_background: bool = True,
) -> Optional[str]:
    """애매한 구간에 걸린 렙 하나에 대해 LLM 2차 확인을 시작한다. 즉시 job_id를
    반환하고(요청-응답을 막지 않음), 실제 LLM 호출은 백그라운드 스레드에서 진행된다.

    client/model 파라미터는 테스트에서 실제 AWS Bedrock을 호출하지 않고 가짜 클라이언트를
    주입할 수 있게 하기 위함(harness.py의 decide_next_action(client=...)과 동일한
    의존성 주입 패턴). run_in_background=False는 테스트 전용 — 스레드 타이밍에 기대지
    않고 동기적으로 즉시 완료시켜 결정적으로 검증할 수 있게 한다.

    LLM 하이브리드가 설정 안 된 환경(AWS_BEDROCK_REGION/HYPEREXTENSION_BEDROCK_MODEL_ID
    미설정)이면 None을 반환한다 — 호출하는 쪽(realtime.py)이 기존 DTW 임곗값 방식으로
    폴백해야 한다는 신호다.
    """
    active_client = client if client is not None else _get_client()
    active_model = model if model is not None else os.environ.get(BEDROCK_MODEL_ID_ENV_VAR)
    if active_client is None or not active_model:
        return None

    job_id = uuid.uuid4().hex
    with _jobs_lock:
        _cleanup_expired_locked()
        _jobs[job_id] = {"status": "pending", "created_at": time.time(), "result": None, "error": None}

    if run_in_background:
        thread = threading.Thread(
            target=_run_job, args=(job_id, rep_frames, active_client, active_model), daemon=True
        )
        thread.start()
    else:
        _run_job(job_id, rep_frames, active_client, active_model)

    return job_id


def get_job_result(job_id: Optional[str]) -> Optional[dict[str, Any]]:
    """job_id로 결과를 조회한다. 아직 안 끝났거나(pending), 없거나(만료/잘못된 id),
    실패했으면(error) None을 반환한다 — 셋 다 호출하는 쪽 입장에서는 "지금은 알려줄 게
    없다"로 동일하게 처리하면 된다. 결과가 있으면(done) 한 번 돌려주고 저장소에서
    지운다(1회성 소비) — 같은 job_id를 또 보내도 두 번째부터는 아무것도 안 나온다."""
    if not job_id:
        return None
    with _jobs_lock:
        _cleanup_expired_locked()
        entry = _jobs.get(job_id)
        if entry is None or entry["status"] == "pending":
            return None
        del _jobs[job_id]
        if entry["status"] == "error":
            return None
        return entry["result"]
