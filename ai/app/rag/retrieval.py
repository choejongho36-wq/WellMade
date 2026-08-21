"""
RAG 검색 (AI-08, 요구사항 정의서 "3.RAG파이프라인" 시트 ③④⑤ 단계: 임베딩·검색·재순위화).

# 왜 스펙이 제안한 Chroma(벡터DB)+임베딩 대신 TF-IDF를 쓰는가? (2026-08-19, 팀 확정 필요)
스펙 원문(requirements.txt에 주석 처리해 남겨둔 chromadb/sentence-transformers)은 벡터DB +
임베딩 모델 조합을 전제로 하지만, 이 프로젝트 상황에서는 다음 이유로 적합하지 않다고
판단해 scikit-learn TF-IDF(문자 n-gram) + 코사인 유사도로 대체했다:

1) 비용 — 사용자가 "LLM 쓰이면 비용문제가 걱정됐다"고 직접 밝힌 만큼, 매 검색마다 유료
   임베딩 API를 호출하는 구조는 피하는 게 맞다고 판단했다. TF-IDF는 로컬 연산이라
   검색 자체에는 추가 API 비용이 전혀 들지 않는다.
2) 딥러닝 프레임워크 배제 원칙 — sentence-transformers는 내부적으로 torch를 요구한다.
   requirements.txt 상단 주석이 "이 서버는 딥러닝 프레임워크를 의도적으로 포함하지 않는다"고
   명시하고 있어, 이 원칙과 정면으로 부딪힌다.
3) 재사용 — scikit-learn은 ml/ 아래 분류기들 때문에 이미 의존성에 포함돼 있다("전통 ML
   우선" 원칙과도 맞음). 새 무거운 의존성을 추가하지 않고 검색을 구현할 수 있다.
4) 한국어 처리 — analyzer="char_wb"(문자 n-gram, 단어 경계 인식)는 형태소 분석기
   (KoNLPy 등) 없이도 "무릎이"/"무릎을"/"무릎에" 같은 조사 변화에 어느 정도 강건하게
   매칭된다. 정확한 임베딩만큼 의미적으로 정교하진 않지만, 이 지식베이스처럼 문서 수가
   적고(십여 건) 검색어가 짧은(이슈 종류, 질문 한두 문장) 상황에서는 충분히 실용적이다.

트레이드오프: 완전히 다른 단어로 표현된 같은 의미(동의어)는 임베딩만큼 잘 못 잡는다.
지식베이스 문서마다 tags에 자주 쓰일 법한 동의어를 미리 채워 넣어(knowledge_base.py 참고)
이 약점을 부분적으로 보완했다. 검색 품질이 실제로 부족하다고 판단되면, 이 모듈의
_build_index()/search() 내부 구현만 교체하면 되도록 검색 인터페이스(search 함수 시그니처)는
그대로 유지할 수 있게 설계했다.
"""

from typing import Optional

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from app.rag.chunking import build_chunks

# 검색어가 문서와 전혀 관련 없을 때 억지로 결과를 끼워 맞추지 않기 위한 최소 유사도 기준.
# 수동 테스트로 대략의 분포를 확인했다: 관련 있는 자연어 질문은 대체로 0.17~0.5, 완전히
# 무관한 문장(예: "오늘 저녁 뭐 먹지")은 대부분 0(결과 없음)이지만 일부는 우연한 문자
# n-gram 중복으로 0.08~0.14까지도 나온다 — char n-gram 방식이라 완벽히 분리되진 않는다
# (검색 방식 자체의 트레이드오프는 이 파일 상단 docstring 참고). 0.12로 잡으면 눈에 띄는
# 오탐(false positive) 상당수를 걸러내지만, "얕게 앉는다는 게 무슨 뜻이에요"처럼 짧고
# 간접적인 진짜 질문(0.067) 몇 개는 함께 걸러진다 — 관련 문서 없음으로 처리되는 게
# 엉뚱한 문서를 근거랍시고 들이대는 것보다 안전하다고 판단해 보수적인 쪽을 택했다.
# TODO: 팀 확정 필요 — 실제 질의 로그가 쌓인 뒤 조정.
MIN_SIMILARITY_SCORE = 0.12

DEFAULT_TOP_K = 3

_index_cache: Optional[dict] = None


def _chunk_search_text(chunk: dict) -> str:
    """벡터화에 쓸 텍스트를 구성한다. 태그를 반복해 넣는 이유: char n-gram 유사도에서
    태그(짧은 핵심어)가 본문(긴 설명문) 대비 상대적으로 묻히지 않도록 가중치를 주기
    위함 — TF-IDF는 문서 길이에 자연히 영향을 받으므로, 짧고 중요한 태그를 여러 번
    반복해 그 n-gram의 등장 빈도를 인위적으로 높였다."""
    tags_repeated = " ".join(chunk["tags"] * 3)
    return f"{chunk['title']} {tags_repeated} {chunk['text']}"


def _build_index() -> dict:
    """청크 전체로 TF-IDF 인덱스를 1회 구축하고 캐싱한다 (posture_percentile.py의
    참조 데이터 캐싱과 동일한 이유 — 요청마다 재계산하지 않기 위함)."""
    chunks = build_chunks()
    vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4))
    matrix = vectorizer.fit_transform([_chunk_search_text(c) for c in chunks])
    return {"chunks": chunks, "vectorizer": vectorizer, "matrix": matrix}


def _get_index() -> dict:
    global _index_cache
    if _index_cache is None:
        _index_cache = _build_index()
    return _index_cache


def search(query: str, top_k: int = DEFAULT_TOP_K, rerank_by_recency: bool = False) -> list[dict]:
    """
    쿼리 문자열로 지식베이스를 검색해 상위 top_k개 청크를 반환한다.
    각 결과에 "score"(코사인 유사도)를 함께 담아, 호출부(generation.py)가
    MIN_SIMILARITY_SCORE 미만인 결과를 "관련 문서 없음"으로 처리할 수 있게 한다.

    rerank_by_recency=True면 요구사항 정의서 ⑤ 재순위화 단계(하네스의
    prefer_latest_document 액션과 연결)를 적용한다 — 다만 "최신 문서로 무조건 덮어쓰기"가
    아니라, 유사도가 비슷한 후보들 안에서만 최신순으로 순서를 조정한다(유사도가 크게
    다른데 날짜만 보고 관련 없는 문서를 앞세우면 안 되기 때문).
    """
    index = _get_index()
    query_vector = index["vectorizer"].transform([query])
    scores = cosine_similarity(query_vector, index["matrix"])[0]

    scored = [
        {**chunk, "score": float(score)}
        for chunk, score in zip(index["chunks"], scores)
        if score >= MIN_SIMILARITY_SCORE
    ]
    scored.sort(key=lambda c: c["score"], reverse=True)
    results = scored[:top_k]

    if rerank_by_recency and len(results) > 1:
        # 최상위 결과와 유사도 차이가 0.05 이내인 후보들만 "동등하게 관련 있다"고 보고,
        # 그 안에서 source_date가 최신인 순으로 재정렬한다.
        top_score = results[0]["score"]
        close_enough = [r for r in results if top_score - r["score"] <= 0.05]
        rest = [r for r in results if r not in close_enough]
        close_enough.sort(key=lambda c: c.get("source_date") or "", reverse=True)
        results = close_enough + rest

    return results


def reset_index_cache() -> None:
    """테스트에서 지식베이스 변경 없이도 매번 새 인덱스를 강제로 재구축하고 싶을 때 사용.
    (일반 서비스 흐름에서는 호출할 필요 없음 — 지식베이스는 배포 시점에 고정되므로.)"""
    global _index_cache
    _index_cache = None
