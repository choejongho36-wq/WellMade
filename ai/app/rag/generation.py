"""
RAG 생성 (AI-09/AI-14, 요구사항 정의서 "3.RAG파이프라인" 시트 ⑥⑦ 단계: 생성·출처 표기).

시트는 생성을 두 가지로 나눈다:
- 지시형(AI-09): 하네스가 trigger_rag_search를 선택했을 때 자동으로 나가는 "조치 가이드".
  이미 감지된 이슈 종류가 명확하므로, 검색 결과 중 가장 관련 있는 문서 하나를 바탕으로
  짧고 실행 가능한 코칭 문구를 만든다.
- 설명형(AI-14): 사용자가 직접 자유 질문을 입력하는 Q&A. 여러 문서를 종합해 설명하는
  답변이 필요할 수 있다.

두 경우 모두 "반드시 근거 문서 내용만 활용" 원칙(할루시네이션 억제)을 지키기 위해,
LLM에게 검색된 청크 텍스트만 근거로 주고 "문서에 없는 내용은 지어내지 말라"고 지시한다.

LLM 호출 가능 여부에 따른 폴백 구조는 harness.py와 동일한 이유로 여기도 그대로 적용한다
(하나의 LLM 호출 실패가 사용자 경험 전체를 끊으면 안 됨). 다만 harness.py처럼 완전히
별도의 규칙기반 로직을 새로 만드는 대신, 지식베이스 문서 자체에 미리 준비해둔
short_message(knowledge_base.py 참고, 기존 ML 분류기 문구와 동일 출처)를 그대로 폴백으로
쓴다 — "LLM 없이도 안전한 기본값이 있어야 한다"는 원칙은 같지만, 이 경우엔 규칙을 다시
짜는 대신 이미 검수된 문구를 재사용하는 편이 할루시네이션 위험도 없고 더 안전하다.

# (2026-08-31) 원래는 harness.py와 같은 환경변수(HARNESS_BEDROCK_MODEL_ID)를 공유했다.
# 하네스가 완전히 규칙기반으로 바뀌면서(더 이상 LLM을 호출하지 않음) 그 이름을 그대로
# 물려받는 게 오히려 혼란스러워, RAG 생성 전용 환경변수(RAG_GENERATION_BEDROCK_MODEL_ID)로
# 분리했다. 실제 모델 선택은 이 모듈을 담당하는 사람이 정한다 — 지금은 .env에 비워둔
# 상태(=LLM 미사용, 규칙기반 폴백 문구만 사용).
"""

import os
from typing import Optional

try:
    import boto3

    _BOTO3_AVAILABLE = True
except ImportError:
    _BOTO3_AVAILABLE = False

from app.rag.retrieval import search

AWS_REGION_ENV_VAR = "AWS_BEDROCK_REGION"
MODEL_ENV_VAR = "RAG_GENERATION_BEDROCK_MODEL_ID"  # (2026-08-31) harness.py와의 공유를 그만두고 분리(위 설명 참고)
MAX_TOKENS = 400

GUIDE_TOP_K = 1
QNA_TOP_K = 3

# 검색 결과가 아예 없을 때(관련 지식베이스 문서를 못 찾았을 때) 쓰는 안내 문구.
# 하네스의 use_generic_guidance 액션과 같은 취지 — 특정 부위를 지목할 수 없을 땐 일반적인
# 안내로 대체한다.
GENERIC_GUIDANCE_MESSAGE = "자세를 천천히, 일정한 속도로 유지해 주세요. 무리하지 않는 범위에서 동작해 주세요."
NO_MATCH_QNA_MESSAGE = "죄송해요, 관련된 안내 자료를 찾지 못했어요. 질문을 조금 더 구체적으로 표현해 주시면 다시 찾아볼게요."


def _get_client():
    """boto3 bedrock-runtime 클라이언트를 지연 생성한다. harness.py의 _get_client()와
    동일한 패턴 — 각 모듈이 자기 완결적으로 폴백을 판단할 수 있도록 일부러 공용 함수로
    뽑지 않고 모듈마다 자체 구현을 유지한다(rules.py/coaching/realtime.py 등 기존 관례와
    동일)."""
    if not _BOTO3_AVAILABLE:
        return None
    region = os.environ.get(AWS_REGION_ENV_VAR)
    if not region:
        return None
    return boto3.client("bedrock-runtime", region_name=region)


def _sources_from_chunks(chunks: list[dict]) -> list[dict]:
    """응답에 실을 출처 목록을 만든다. 같은 문서(doc_id)의 청크가 여러 개 뽑혀도 출처는
    중복 없이 한 번만 나오게 한다."""
    seen = set()
    sources = []
    for chunk in chunks:
        if chunk["doc_id"] in seen:
            continue
        seen.add(chunk["doc_id"])
        sources.append(
            {
                "title": chunk["title"],
                "source": chunk["source"],
                "source_url": chunk.get("source_url"),
                "source_date": chunk.get("source_date"),
            }
        )
    return sources


def _llm_generate(system_prompt: str, user_message: str, client) -> Optional[str]:
    """LLM 호출 공통 부분. 실패하면 None을 반환해 호출부가 폴백을 쓰게 한다."""
    try:
        response = client.converse(
            modelId=os.environ[MODEL_ENV_VAR],
            system=[{"text": system_prompt}],
            messages=[{"role": "user", "content": [{"text": user_message}]}],
            inferenceConfig={"maxTokens": MAX_TOKENS},
        )
        content = response["output"]["message"]["content"]
        text_blocks = [block["text"] for block in content if "text" in block]
        combined = "".join(text_blocks).strip()
        return combined or None
    except Exception:  # noqa: BLE001 — 네트워크/파싱 등 다양한 이유로 실패할 수 있어 폭넓게 처리
        return None


def generate_guide(query: str, client=None) -> dict:
    """
    지시형 생성(AI-09). 하네스의 trigger_rag_search가 넘겨준 search_query(이슈 종류)를 받아
    RAG 검색 → 근거 기반 코칭 문구를 생성한다.
    """
    results = search(query, top_k=GUIDE_TOP_K, rerank_by_recency=True)

    if not results:
        return {
            "guidance_message": GENERIC_GUIDANCE_MESSAGE,
            "sources": [],
            "matched": False,
            "generation_source": "fallback",
        }

    top = results[0]
    fallback_message = top["short_message"]
    active_client = client if client is not None else _get_client()
    model_set = bool(os.environ.get(MODEL_ENV_VAR))

    if active_client is not None and model_set:
        system_prompt = (
            "당신은 운동 자세 코칭 앱 WellMade의 코칭 문구 생성기입니다. "
            "아래 [근거 문서] 내용만 근거로 삼아, 2~3문장의 한국어 코칭 문구를 만드세요. "
            "문서에 없는 내용은 절대 지어내지 마세요. TTS로 바로 읽을 수 있는 자연스러운 "
            "구어체로, 사용자에게 직접 말하듯이 작성하세요."
        )
        user_message = f"[근거 문서]\n{top['text']}\n\n[요청]\n'{query}'에 대한 코칭 문구를 만들어주세요."
        generated = _llm_generate(system_prompt, user_message, active_client)
        if generated:
            return {
                "guidance_message": generated,
                "sources": _sources_from_chunks(results),
                "matched": True,
                "generation_source": "llm",
            }

    # LLM 미설정/실패 → 문서에 미리 준비된 short_message로 폴백(할루시네이션 위험 없음).
    return {
        "guidance_message": fallback_message,
        "sources": _sources_from_chunks(results),
        "matched": True,
        "generation_source": "fallback",
    }


def generate_qna(question: str, client=None) -> dict:
    """
    설명형 생성(AI-14). 사용자의 자유 질문을 받아 RAG 검색 → 근거 기반 설명 답변을 생성한다.
    """
    results = search(question, top_k=QNA_TOP_K, rerank_by_recency=False)

    if not results:
        return {
            "answer": NO_MATCH_QNA_MESSAGE,
            "sources": [],
            "matched": False,
            "generation_source": "fallback",
        }

    active_client = client if client is not None else _get_client()
    model_set = bool(os.environ.get(MODEL_ENV_VAR))

    if active_client is not None and model_set:
        context = "\n\n".join(f"[{r['title']}]\n{r['text']}" for r in results)
        system_prompt = (
            "당신은 운동 자세 코칭 앱 WellMade의 Q&A 도우미입니다. "
            "아래 [근거 문서]들의 내용만 근거로 삼아 사용자 질문에 답하세요. "
            "문서에 없는 내용은 절대 지어내지 말고, 문서로 답할 수 없으면 모른다고 "
            "솔직하게 말하세요. 한국어로 자연스럽게 답하세요."
        )
        user_message = f"[근거 문서]\n{context}\n\n[질문]\n{question}"
        generated = _llm_generate(system_prompt, user_message, active_client)
        if generated:
            return {
                "answer": generated,
                "sources": _sources_from_chunks(results),
                "matched": True,
                "generation_source": "llm",
            }

    # LLM 미설정/실패 → 검색된 문서 본문을 그대로 발췌해 답한다(추출적 요약).
    # "생성"이 아니라 "발췌"라 자연스러운 문장은 아니지만, 지어낸 내용이 섞일 위험이 없는
    # 가장 안전한 폴백이다.
    excerpt = results[0]["text"]
    fallback_answer = f"관련 자료를 찾았어요. {excerpt}"
    return {
        "answer": fallback_answer,
        "sources": _sources_from_chunks(results),
        "matched": True,
        "generation_source": "fallback",
    }
