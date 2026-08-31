"""
LLM 모델 비교 테스트 — "6랩 블라인드 테스트"를 여러 Bedrock 모델로 동시에 재현한다
(2026-08-28 추가, MlTestPage.jsx의 "6랩 블라인드 테스트" 버튼 전용 개발/테스트 기능).

hyperextension_llm_check.py(실제 서비스 판정 경로)와 마찬가지로 boto3 bedrock-runtime의
Converse API(converse())를 직접 쓴다 — 이 API는 Anthropic/Amazon Nova/Meta Llama/
Mistral Large 등 여러 벤더 모델에서 동일한 방식으로 도구 사용(toolConfig)을 지원하는
통합 인터페이스라, 벤더별로 다른 클라이언트/프롬프트 포맷을 만들지 않고도 같은 판정
함수로 여러 모델을 공정하게 비교할 수 있다.

이 모듈은 실제 서비스 판정 경로(hyperextension_llm_check.py)와 별개다 — 그쪽은 환경변수
(HYPEREXTENSION_BEDROCK_MODEL_ID)로 지정된 모델 하나만 실시간 코칭에 쓰지만, 여기는 여러
모델 후보를 병렬로 동시에 호출해 정확도·지연시간을 나란히 비교하는 순수 비교/실험
도구다 — 여기서 비교해보고 마음에 드는 모델 ID를 그 환경변수에 넣으면 실제 서비스
경로에도 그대로 반영된다.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Optional

try:
    import boto3
    from botocore.exceptions import BotoCoreError, ClientError

    _BOTO3_AVAILABLE = True
except ImportError:
    _BOTO3_AVAILABLE = False

    # boto3 미설치 환경에서도 아래 except (BotoCoreError, ClientError) 구문 자체는 평가돼야
    # 하므로(파이썬은 except 튜플의 이름을 항상 조회한다), 아무것도 잡지 않는 더미 예외
    # 클래스로 대체해둔다 — hyperextension_llm_check.py의 _ANTHROPIC_AVAILABLE 가드와
    # 달리, 여기는 클라이언트 생성 이전에 함수 정의 시점에서부터 이름이 필요하기 때문.
    class BotoCoreError(Exception):  # type: ignore[no-redef]
        pass

    class ClientError(Exception):  # type: ignore[no-redef]
        pass

# 프롬프트에 넣는 프레임 수 상한 — hyperextension_llm_check.py와 동일한 이유(비용 상한).
MAX_PROMPT_FRAMES = 60

# 여러 벤더 모델이 공통으로 가진 측면(시상면) 지표만 쓴다 — hyperextension_llm_check.py의
# _SIDE_FIELDS와 동일한 목록(같은 판정을 여러 모델로 재현해야 비교가 공정하다).
_SIDE_FIELDS: tuple[str, ...] = (
    "knee_angle",
    "hip_angle",
    "torso_length_ratio",
    "torso_shin_lean_gap_deg",
    "shoulder_forward_lean_deg",
)

_TOOL_NAME = "report_hip_hyperextension_verdict"
_TOOL_SPEC = {
    "toolSpec": {
        "name": _TOOL_NAME,
        "description": "스쿼트 렙 1개의 측면 관절각도 시계열을 보고 고관절 과신전 여부를 판정해 보고한다.",
        "inputSchema": {
            "json": {
                "type": "object",
                "properties": {
                    # 필드 순서 = 모델이 강제 tool call로 값을 채우는 순서(Converse API의
                    # toolChoice가 이 도구를 강제하므로). verdict를 맨 앞에 두면 근거(reasoning)를
                    # 쓰기도 전에 결론부터 확정해야 해서 CoT(생각 먼저, 결론 나중)의 이점을 못
                    # 살린다 — reasoning을 먼저 채우게 해서 판정 전에 근거를 먼저 풀어놓도록
                    # 순서를 바꿨다(2026-08-31, 프롬프트 문구는 변경하지 않음).
                    "reasoning": {
                        "type": "string",
                        "description": "판정 근거를 한두 문장으로 설명.",
                    },
                    "confidence": {
                        "type": "string",
                        "enum": ["상", "중", "하"],
                        "description": "판정 확신도.",
                    },
                    "verdict": {
                        "type": "string",
                        "enum": ["과신전_의심", "정상"],
                        "description": "이 렙에 고관절 과신전(허리를 과도하게 젖히는 보상동작)이 있었는지.",
                    },
                },
                "required": ["reasoning", "confidence", "verdict"],
            }
        },
    }
}

_SYSTEM_PROMPT = (
    "당신은 스쿼트 자세를 분석하는 운동처방 전문가입니다. 측면에서 촬영한 관절각도 "
    "시계열만 보고, 고관절 과신전(허리를 과도하게 젖히는 보상동작) 여부를 판정해야 "
    "합니다. 단일 프레임의 절대 수치보다, 렙 전체에 걸친 패턴의 형태로 판단하세요. "
    "판정을 정하기 전에 reasoning 필드에 관찰한 패턴과 근거를 먼저 충분히 정리하고, "
    "그 근거를 바탕으로 confidence와 verdict를 결정하세요 — 결론부터 정한 뒤 근거를 "
    "나중에 붙이지 마세요. "
    "report_hip_hyperextension_verdict 도구를 반드시 한 번 호출해 결과를 보고하세요."
)


def _downsample(frames: list[dict], max_frames: int = MAX_PROMPT_FRAMES) -> list[dict]:
    n = len(frames)
    if n <= max_frames:
        return frames
    step = n / max_frames
    return [frames[int(i * step)] for i in range(max_frames)]


def _build_prompt(frames: list[dict]) -> str:
    sampled = _downsample(frames)
    lines = []
    for f in sampled:
        parts = [f"t={f.get('timestamp', 0.0):.2f}"]
        for name in _SIDE_FIELDS:
            value = f.get(name)
            if value is not None:
                parts.append(f"{name}={value:.1f}")
        lines.append(", ".join(parts))
    return (
        "아래는 스쿼트 렙 1개 동안 측면에서 촬영한 관절각도 시계열입니다(프레임 순서대로, "
        "t=경과시간(초)). 각도 단위는 도, torso_length_ratio는 무단위 비율입니다.\n\n"
        + "\n".join(lines)
        + "\n\n이 렙에서 고관절 과신전이 있었는지 판정해주세요."
    )


def _get_bedrock_client(region: str):
    if not _BOTO3_AVAILABLE:
        return None
    return boto3.client("bedrock-runtime", region_name=region)


def _call_one(client, model_id: str, frames: list[dict]) -> dict[str, Any]:
    """Bedrock Converse API로 모델 1개·렙 1개를 판정한다. 성공하면
    {verdict, confidence, reasoning, latency_ms}, 실패하면 {error, latency_ms}를 반환한다
    — 예외를 여기서 삼키는 이유는 여러 모델을 병렬로 돌릴 때 하나가 실패해도(모델 접근권한
    미승인 등) 나머지 결과는 정상적으로 돌려주기 위함."""
    prompt = _build_prompt(frames)
    t0 = time.monotonic()
    try:
        response = client.converse(
            modelId=model_id,
            system=[{"text": _SYSTEM_PROMPT}],
            messages=[{"role": "user", "content": [{"text": prompt}]}],
            toolConfig={"tools": [_TOOL_SPEC], "toolChoice": {"tool": {"name": _TOOL_NAME}}},
            inferenceConfig={"temperature": 0},
        )
        latency_ms = int((time.monotonic() - t0) * 1000)
        content = response["output"]["message"]["content"]
        for block in content:
            tool_use = block.get("toolUse")
            if tool_use and tool_use.get("name") == _TOOL_NAME:
                data = tool_use.get("input", {})
                return {
                    "verdict": data.get("verdict"),
                    "confidence": data.get("confidence"),
                    "reasoning": data.get("reasoning", ""),
                    "latency_ms": latency_ms,
                    "usage": response.get("usage"),
                }
        return {"error": "응답에 tool_use 블록이 없습니다.", "latency_ms": latency_ms}
    except (BotoCoreError, ClientError) as e:  # noqa: BLE001
        return {"error": str(e), "latency_ms": int((time.monotonic() - t0) * 1000)}
    except Exception as e:  # noqa: BLE001 - 예상 못 한 모델별 응답 형식 차이 등도 결과로 감싸 돌려준다
        return {"error": f"{type(e).__name__}: {e}", "latency_ms": int((time.monotonic() - t0) * 1000)}


def compare_models(
    reps: list[dict],
    model_ids: list[str],
    region: str,
    client_factory=_get_bedrock_client,
    max_workers: int = 10,
) -> dict[str, Any]:
    """reps(각 {"id", "true_label"(선택), "frames"}) x model_ids 전체 조합을 병렬로
    호출해 결과를 모은다. client_factory는 테스트에서 가짜 클라이언트를 주입하기 위한
    DI 지점(hyperextension_llm_check.py의 client 파라미터와 동일한 패턴).

    반환: {
      "results": {model_id: {rep_id: {verdict, confidence, reasoning, latency_ms} | {error, latency_ms}}},
      "accuracy": {model_id: 0.0~1.0 | None},  # true_label이 있는 렙 기준, 없으면 None
    }
    """
    client = client_factory(region)
    if client is None:
        return {
            "results": {},
            "accuracy": {},
            "error": "Bedrock 클라이언트를 만들 수 없습니다(boto3 미설치 또는 자격증명 없음).",
        }

    results: dict[str, dict[str, Any]] = {m: {} for m in model_ids}

    jobs = [(model_id, rep) for model_id in model_ids for rep in reps]
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_job = {
            executor.submit(_call_one, client, model_id, rep["frames"]): (model_id, rep)
            for model_id, rep in jobs
        }
        for future in as_completed(future_to_job):
            model_id, rep = future_to_job[future]
            results[model_id][rep["id"]] = future.result()

    accuracy: dict[str, Optional[float]] = {}
    for model_id in model_ids:
        labeled_reps = [r for r in reps if r.get("true_label")]
        if not labeled_reps:
            accuracy[model_id] = None
            continue
        correct = 0
        for rep in labeled_reps:
            verdict = results[model_id].get(rep["id"], {}).get("verdict")
            predicted_label = "과신전" if verdict == "과신전_의심" else "정상" if verdict == "정상" else None
            if predicted_label == rep["true_label"]:
                correct += 1
        accuracy[model_id] = correct / len(labeled_reps)

    return {"results": results, "accuracy": accuracy}
