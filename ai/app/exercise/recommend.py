"""
운동 추천 v1 — exercises_ko.json(1,324건)에서 부위/장비로 필터링해 후보를 돌려준다.

RAG(임베딩/벡터 검색)가 아니라 정형 필터다. body_part는 값이 10종, equipment는 28종뿐이고
사용자 조건도 대개 "부위 + 장비" 수준이라 필터로 충분하다. 난이도는 이 데이터셋에 필드가
없어서 여기서 거르지 않고, 생성 단계(백엔드 Ollama)가 후보 중에서 고를 때 참고만 하게 둔다.

자연어 추천문은 만들지 않는다 — 후보 목록만 백엔드에 넘기면, 백엔드가 기존 챗봇 스트리밍
경로로 문장을 생성한다(도구 결과를 문장으로 옮기는 기존 패턴과 동일).
"""

import json
import random
from pathlib import Path
from typing import Optional

DATA_PATH = Path(__file__).parent.parent / "rag" / "data" / "exercises_ko.json"

# 후보마다 한국어 설명(instructions_ko, 평균 170자)을 같이 싣기 때문에 8건에서 3건으로 줄였다.
# 모델은 어차피 2~3개를 골라 추천하므로 사용자가 보는 다양성은 그대로고(매번 random.sample),
# 컨텍스트는 3x170 = 500자 수준으로 작다.
MAX_CANDIDATES = 3

VALID_BODY_PARTS = {
    "chest", "back", "shoulders", "upper arms", "lower arms",
    "waist", "upper legs", "lower legs", "neck", "cardio",
}

# 사용자가 자유롭게 말한 한국어 부위 -> exercises_ko.json의 body_part(영문).
# LLM이 body_part 인자를 한국어로 넘겨도, 영문 키로 넘겨도 받도록 한다.
BODY_PART_KO = {
    "가슴": "chest",
    "등": "back", "광배": "back",
    "어깨": "shoulders", "삼각근": "shoulders",
    "팔": "upper arms", "이두": "upper arms", "삼두": "upper arms", "팔뚝": "upper arms",
    "전완": "lower arms", "손목": "lower arms",
    "복근": "waist", "코어": "waist", "허리": "waist", "배": "waist", "복부": "waist",
    "하체": "upper legs", "허벅지": "upper legs", "다리": "upper legs",
    "엉덩이": "upper legs", "둔근": "upper legs", "대퇴": "upper legs",
    "종아리": "lower legs", "정강이": "lower legs",
    "목": "neck",
    "유산소": "cardio", "전신": "cardio", "심폐": "cardio",
}

# 맨몸/집 운동으로 볼 표현. equipment == "body weight"로 좁힌다.
BODYWEIGHT_HINTS = {"맨몸", "집", "무기구", "홈트", "bodyweight", "body weight", "none", "없음"}

_cache: Optional[list] = None


def _load() -> list:
    """참조 데이터는 프로세스당 한 번만 읽어 캐싱한다(nutrition_peer._load_reference와 같은 취지)."""
    global _cache
    if _cache is None:
        _cache = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    return _cache


def normalize_body_part(raw: str) -> Optional[str]:
    """한국어/영문 부위 표현을 exercises_ko.json의 body_part 키로. 못 맞추면 None."""
    if not raw:
        return None
    text = raw.strip().lower()
    if text in VALID_BODY_PARTS:
        return text
    for ko, en in BODY_PART_KO.items():
        if ko in text:
            return en
    return None


def recommend(body_part: str, equipment: str = "") -> dict:
    """
    :param body_part: 운동할 부위 (한국어 표현 또는 영문 body_part 키). 못 맞추면 후보를 비워
                      돌려준다 - 엉뚱한 부위 8건을 던지면 챗봇이 그걸로 헛소리를 만든다.
    :param equipment: 장비/환경 힌트. "맨몸"/"집" 계열이면 body weight로, 그 외 문자열이면
                      equipment 부분일치로 좁힌다. 좁힌 결과가 비면 부위 필터까지만 적용한다.
    """
    exercises = _load()
    target = normalize_body_part(body_part)
    if target is None:
        return {
            "body_part": "",
            "matched": 0,
            "candidates": [],
            "note": "어느 부위 운동인지 알려주시면 추천해드릴게요. (예: 가슴, 등, 어깨, 팔, 복근, 하체, 종아리)",
        }

    pool = [e for e in exercises if e["body_part"] == target]

    eq = (equipment or "").strip().lower()
    if eq:
        if eq in BODYWEIGHT_HINTS:
            narrowed = [e for e in pool if e["equipment"] == "body weight"]
        else:
            narrowed = [e for e in pool if eq in e["equipment"].lower()]
        if narrowed:
            pool = narrowed

    if not pool:
        return {
            "body_part": target or "",
            "matched": 0,
            "candidates": [],
            "note": "조건에 맞는 운동을 찾지 못했어요. 부위나 장비 조건을 바꿔서 다시 시도해 주세요.",
        }

    picked = random.sample(pool, min(MAX_CANDIDATES, len(pool)))
    # 후보에 한국어 설명을 같이 싣는다. 예전엔 이름/부위/장비/타겟만 넘기고 "운동 방법 설명은
    # 챗봇이 직접" 하게 뒀는데, 근거 없는 자유 생성이라 Qwen이 중국어로 새는 턴이 나왔다.
    # 프롬프트로 "설명이 필요하면 도구를 부르라"고 시켜봤지만 모델이 도구를 부르지 않았다(6회 중 0회).
    # 반대로 설명이 컨텍스트에 있으면 드리프트가 사라졌다(5회 중 0회) - 그래서 모델이 확실히
    # 부르는 이 도구에 설명을 실어, 추천과 설명이 같은 턴에서 근거를 갖고 이뤄지게 한다.
    candidates = [
        {
            "name": e.get("name_ko") or e["name"],
            "body_part": e["body_part"],
            "equipment": e["equipment"],
            "target": e["target"],
            "instructions_ko": e.get("instructions_ko") or "",
        }
        for e in picked
    ]
    return {"body_part": target, "matched": len(pool), "candidates": candidates, "note": None}


def _normalize_name(raw: str) -> str:
    """이름 비교용 정규화 - 공백 차이("벤치 프레스" vs "벤치프레스")로 못 찾는 걸 막는다."""
    return "".join((raw or "").split()).lower()


def find_detail(name: str) -> dict:
    """
    운동 이름 하나로 그 운동의 한국어 설명(instructions_ko)을 찾아 돌려준다.

    챗봇이 추천 목록을 보여준 뒤 사용자가 "플랭크는 어떻게 해?"처럼 하나를 지목할 때 쓴다.
    예전에는 이 단계에서 도구를 안 부르고 모델이 설명을 직접 지어내게 뒀는데, 근거 없는
    자유 생성이라 Qwen이 중국어로 새는 턴이 나왔다(실측). 데이터에 1,324건 전부 한국어
    설명이 있으므로 그걸 그대로 넘겨서 "창작"을 "옮겨쓰기"로 바꾼다.

    :param name: 사용자가 지목한 운동 이름 (추천 목록에 보여준 name_ko 이거나 그 일부)
    """
    exercises = _load()
    key = _normalize_name(name)
    if not key:
        return {"found": False, "note": "어떤 운동인지 알려주시면 설명해드릴게요."}

    # 1) 정확히 같은 이름 (추천 목록에서 그대로 지목한 흔한 경우)
    for e in exercises:
        if key in (_normalize_name(e.get("name_ko")), _normalize_name(e.get("name"))):
            return _detail_of(e)

    # 2) 부분 일치 - "플랭크"처럼 짧게 말하면 9건이 걸린다(데이터에 플레인 "플랭크"는 없다).
    #    수식어가 적은 쪽이 기본 동작에 가까우므로 이름이 가장 짧은 것을 고른다. 정확한 선택은
    #    아니지만 실제 존재하는 운동의 실제 설명이고, 응답에 그 운동의 진짜 이름을 같이 실어서
    #    챗봇이 "OO는 ~입니다"로 무엇을 설명하는지 밝히게 한다.
    partial = [e for e in exercises if key in _normalize_name(e.get("name_ko"))]
    if partial:
        return _detail_of(min(partial, key=lambda e: len(e.get("name_ko") or "")))

    return {"found": False, "note": f"'{name}' 운동을 찾지 못했어요. 추천해드린 목록 중에서 골라주세요."}


def _detail_of(e: dict) -> dict:
    return {
        "found": True,
        "name": e.get("name_ko") or e["name"],
        "body_part": e["body_part"],
        "equipment": e["equipment"],
        "target": e["target"],
        "instructions_ko": e.get("instructions_ko") or "",
        "note": None,
    }
