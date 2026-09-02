"""
RAG 청킹 (AI-08, 요구사항 정의서 "3.RAG파이프라인" 시트 ② 단계).

시트가 제시한 기준은 "200~400 토큰, 의미단위(chunking)"다. 여기서 "토큰"을 형태소 분석기
(KoNLPy 등)로 정확히 세지 않고 공백 기준 어절 수로 근사하는 이유:
- 이 서버는 딥러닝 프레임워크는 물론, 별도의 형태소 분석기 의존성도 아직 추가하지 않았다
  (requirements.txt 상단 주석 참고 — "무거운 연산은 클라이언트"라는 원칙과 맥을 같이 함).
- 어절 수는 실제 서브워드/형태소 토큰 수와 정확히 일치하지 않지만, "청크 하나가 너무 길지도
  짧지도 않게 자른다"는 목적 자체에는 충분한 근사치다. 나중에 실제 임베딩/토크나이저를
  도입하게 되면 estimate_tokens()만 교체하면 되도록 함수로 분리해뒀다.

"의미단위"는 문서를 무작정 글자수로 자르지 않고, 문단(빈 줄 기준) → 그래도 너무 길면 문장
단위로 나눠 쌓는 방식으로 구현했다. 문장 중간에서 잘리면 검색된 청크만 보고는 맥락을 알기
어려워, 생성 단계(generation.py)에서 "근거 문서 내용만 활용"하라는 지시를 지키기 어려워지기
때문이다.
"""

import re

# NOTE: MVP 잠정치 — 데이터가 쌓이는 대로 사용자 신고 기반 액티브러닝으로 조정할 예정.
TARGET_MIN_TOKENS = 200
TARGET_MAX_TOKENS = 400

# 한국어 문장 종결(다./요./다!/요?/다: 등) 뒤에 오는 공백을 기준으로 문장을 나눈다.
# 완벽한 문장 분리기는 아니지만(예: "3.5도"의 마침표를 문장 끝으로 오인할 수 있음),
# 이 지식베이스 문서들은 소수점 표현이 거의 없어 실용적으로는 충분하다.
_SENTENCE_SPLIT_PATTERN = re.compile(r"(?<=[다요][.!?])\s+")


def estimate_tokens(text: str) -> int:
    """공백 기준 어절 수로 토큰 수를 근사한다. 모듈 docstring 참고."""
    return len(text.split())


def _split_sentences(paragraph: str) -> list[str]:
    sentences = [s.strip() for s in _SENTENCE_SPLIT_PATTERN.split(paragraph) if s.strip()]
    return sentences or [paragraph.strip()]


def _pack(units: list[str]) -> str:
    return " ".join(units).strip()


def chunk_text(text: str) -> list[str]:
    """
    본문 텍스트 하나를 200~400 토큰(근사치) 청크 여러 개로 나눈다.

    문단 단위로 그리디하게 채우다가 TARGET_MAX_TOKENS를 넘기기 직전에 새 청크로 넘어간다.
    문단 하나가 이미 TARGET_MAX_TOKENS를 넘으면 문장 단위로 한 번 더 쪼갠다.
    """
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]

    chunks: list[str] = []
    current_units: list[str] = []
    current_tokens = 0

    def flush():
        nonlocal current_units, current_tokens
        if current_units:
            chunks.append(_pack(current_units))
            current_units = []
            current_tokens = 0

    for paragraph in paragraphs:
        paragraph_tokens = estimate_tokens(paragraph)
        if paragraph_tokens > TARGET_MAX_TOKENS:
            # 문단 자체가 너무 길면 문장 단위로 쪼개서 같은 방식으로 채운다.
            for sentence in _split_sentences(paragraph):
                sentence_tokens = estimate_tokens(sentence)
                if current_tokens + sentence_tokens > TARGET_MAX_TOKENS and current_units:
                    flush()
                current_units.append(sentence)
                current_tokens += sentence_tokens
            continue

        if current_tokens + paragraph_tokens > TARGET_MAX_TOKENS and current_units:
            flush()
        current_units.append(paragraph)
        current_tokens += paragraph_tokens

    flush()

    # 마지막 청크가 TARGET_MIN_TOKENS에 크게 못 미치고(너무 짧아 단독으로는 의미 파악이
    # 어려울 정도) 청크가 2개 이상이면, 바로 앞 청크와 합친다 — "문서 끝에 한두 문장만
    # 남는" 상황을 피하기 위함.
    if len(chunks) >= 2 and estimate_tokens(chunks[-1]) < TARGET_MIN_TOKENS // 2:
        last = chunks.pop()
        chunks[-1] = f"{chunks[-1]} {last}".strip()

    return chunks


def build_chunks() -> list[dict]:
    """
    지식베이스 전체 문서를 청크로 쪼갠 뒤, 검색·출처 표기에 필요한 메타데이터를 붙여
    반환한다. retrieval.py가 이 함수의 결과를 그대로 검색 인덱스 구축에 사용한다.
    """
    # 순환 import를 피하려고 함수 안에서 지연 import한다 (knowledge_base.py는 이 모듈을
    # 가져올 필요가 없고, 이 모듈만 knowledge_base.py를 가져오면 되는 단방향 의존이므로
    # 실제로는 문제되지 않지만, retrieval.py까지 포함해 이후 순서가 바뀌어도 안전하도록
    # 관례적으로 지연 import를 유지한다).
    from app.rag.knowledge_base import get_all_documents

    chunks = []
    for doc in get_all_documents():
        body_chunks = chunk_text(doc["body"])
        for i, chunk_body in enumerate(body_chunks):
            chunks.append(
                {
                    "chunk_id": f"{doc['id']}#{i}",
                    "doc_id": doc["id"],
                    "title": doc["title"],
                    "tags": doc["tags"],
                    "short_message": doc["short_message"],
                    "text": chunk_body,
                    "source": doc["source"],
                    "source_url": doc.get("source_url"),
                    "source_date": doc.get("source_date"),
                }
            )
    return chunks
