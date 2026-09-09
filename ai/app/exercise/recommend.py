"""
운동 추천 v2 — 규칙 기반 선정 + 목표별 세트/횟수 + 최근 운동 기록 반영.

v1과 달라진 것:

1) 후보를 1,324건 전체가 아니라 사람이 고른 기본 동작(exercises_core.json, 152건)에서 뽑는다.
   전체를 후보로 두면 "덤벨 하이트 플라이" 같은 변형이 "덤벨 플라이"보다 먼저 나온다.
   나머지 1,000여 건은 find_detail(이름으로 설명 찾기)에서 계속 쓰이므로 커버리지는 그대로다.

2) random.sample을 없앴다. 같은 질문에 매번 다른 답이 나오면 재현도 평가도 안 된다.
   정렬은 결정적으로(태그 점수 -> 이름 순) 하고, 다양성은 "최근 추천한 것 제외"(exclude)로 만든다.

3) 무엇을 몇 세트 할지까지 여기서 정한다. LLM은 이 결과를 문장으로 옮기기만 한다 -
   메뉴 경로(ChatService.menuReply)에서 이미 검증한 패턴이다. 세트/횟수를 모델이 지어내게 두면
   같은 목표에도 답이 흔들리고, 근거를 댈 수 없다.

4) 최근 운동 메모를 읽어 "어제 하체 하셨으니 오늘은 등 어때요?"를 만든다. 메모는 자유 텍스트지만
   부위 키워드(BODY_PART_KO)만 맞춰봐도 충분히 동작한다.

임베딩/벡터 검색은 아직 넣지 않는다 - "허리 안 아프게 하는 등 운동" 같은 자유 표현이 실제로
들어오는지 로그(log_freeform_request)를 먼저 보고, 필요해지면 큐레이션 152건 + 영상 설명문에만
좁게 거는 게 순서다. 30,090건 영상에 그대로 벡터 검색을 걸면 중복이 많아 품질이 오히려 나빠진다.
"""

import json
import logging
import re
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from app.exercise.movements import movements_of_exercise

log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent / "data"
CORE_PATH = DATA_DIR / "exercises_core.json"
VIDEO_PATH = DATA_DIR / "exercise_videos.json"
FULL_PATH = Path(__file__).parent.parent / "rag" / "data" / "exercises_ko.json"

# 한 번에 추천할 운동 수. 3개면 루틴이라 하기엔 얇고, 5개가 넘으면 초보자가 다 못 한다.
MIN_PICKS = 3
MAX_PICKS = 4

VALID_BODY_PARTS = {
    "chest", "back", "shoulders", "upper arms", "lower arms",
    "waist", "upper legs", "lower legs", "neck", "cardio",
}

# 사용자가 자유롭게 말한 한국어 부위 -> body_part(영문).
# 추천 인자를 정규화할 때도, 운동 메모에서 "무슨 부위를 했는지" 읽을 때도 이 사전을 쓴다.
BODY_PART_KO = {
    "가슴": "chest", "흉근": "chest",
    "등": "back", "광배": "back", "승모": "back", "견갑": "back",
    "어깨": "shoulders", "삼각근": "shoulders",
    "팔": "upper arms", "이두": "upper arms", "삼두": "upper arms", "팔뚝": "upper arms",
    "전완": "lower arms", "손목": "lower arms",
    "복근": "waist", "코어": "waist", "허리": "waist", "배": "waist", "복부": "waist",
    "식스팩": "waist", "옆구리": "waist",
    "하체": "upper legs", "허벅지": "upper legs", "다리": "upper legs",
    "엉덩이": "upper legs", "둔근": "upper legs", "대퇴": "upper legs", "스쿼트": "upper legs",
    "힙": "upper legs", "햄스트링": "upper legs",
    "종아리": "lower legs", "정강이": "lower legs", "장딴지": "lower legs",
    "목": "neck",
    "유산소": "cardio", "전신": "cardio", "심폐": "cardio", "러닝": "cardio", "달리기": "cardio",
    "런닝": "cardio", "걷기": "cardio", "자전거": "cardio",
}

# "상체"처럼 한 번에 여러 부위를 가리키는 말. 단일 body_part로 접을 수 없다 - 가슴 하나로
# 접으면 등·어깨·팔을 뺀 게 되고, 그렇다고 못 맞췄다고 돌려주면 후보가 0건이라 모델이
# 운동을 지어낸다(실측: "상체운동" -> 데이터에 없는 "바벨 로우 릴리즈"를 창작).
# 그래서 속한 부위의 후보를 합친 풀에서 뽑고, _pick이 부위가 겹치지 않게 고르게 한다.
#
# "하체"는 예전부터 upper legs 하나로 처리해 왔고 그 결과가 검증돼 있어 그대로 둔다
# (허벅지·둔근만 32건이라 루틴을 채우기에 충분하다).
BODY_PART_GROUPS = {
    "upper body": ["chest", "back", "shoulders", "upper arms"],
}

BODY_PART_GROUP_KO = {
    "상체": "upper body",
    "상반신": "upper body",
}

BODY_PART_LABEL = {
    "chest": "가슴", "back": "등", "shoulders": "어깨", "upper arms": "팔",
    "lower arms": "전완", "waist": "복근", "upper legs": "하체",
    "lower legs": "종아리", "neck": "목", "cardio": "유산소",
    "upper body": "상체",
}

# "맨몸"과 "집"은 다른 조건이다. 사용자에게 맨몸은 "기구 없음"인데, 덤벨·밴드 운동도
# home_friendly=True로 태그돼 있어서 둘을 같이 묶으면 "맨몸 하체"에 덤벨 스쿼트가 나온다.
EQUIPMENT_FREE_HINTS = {"맨몸", "무기구", "없음", "bodyweight", "body weight", "none"}
HOME_HINTS = {"집", "홈트", "홈", "home"}

# 사용자가 말하는 장비 이름 -> 데이터의 equipment 값에 들어 있는 영문 표현.
# 데이터는 ExerciseDB 영문("dumbbell", "leverage machine")인데 사용자는 한국어로 말한다.
# 이 사전이 없던 동안 "덤벨"은 어느 값에도 안 걸려서, 장비 조건이 조용히 무시된 채 부위
# 전체에서 뽑혔다(실측: "덤벨 상체운동" -> 바벨·케이블 운동이 섞여 나옴).
#
# 값은 부분 일치로 쓴다. "barbell"은 "ez barbell"까지, "machine"은 "leverage machine"과
# "smith machine"을 같이 잡는다. 그래서 "스미스"를 "머신"보다 먼저 둔다(먼저 걸린 게 이긴다).
EQUIPMENT_KO = {
    "덤벨": "dumbbell", "아령": "dumbbell",
    "바벨": "barbell", "역기": "barbell",
    "밴드": "band", "고무줄": "band",
    "케이블": "cable",
    "케틀벨": "kettlebell", "케틀": "kettlebell",
    "스미스": "smith machine",
    "머신": "machine", "기구": "machine",
    "줄넘기": "rope", "로프": "rope",
}

# 목표별 처방. 백엔드 프로필의 Goal enum 이름(LOSE/GAIN/MAINTAIN)을 그대로 키로 쓴다 -
# 중간에 이름을 바꾸면 양쪽이 어긋났을 때 조용히 기본값으로 떨어진다.
GOAL_PLANS = {
    "GAIN": {
        "label": "근육량 증가",
        "sets_reps": "3세트 x 8~12회",
        "rest": "세트 사이 60~90초 휴식",
        # 유산소는 세트로 하는 운동이 아니라 시간으로 처방하고, 세트 휴식도 붙이지 않는다
        "cardio_sets_reps": "5~10분 가볍게 (본 운동 전 준비운동)",
        "cardio_rest": None,
    },
    "LOSE": {
        "label": "체중 감량",
        "sets_reps": "서킷 3라운드 (동작당 40초 수행 / 20초 휴식)",
        "rest": "라운드 사이 60초 휴식",
        "cardio_sets_reps": "20~30분 연속 (숨이 조금 찰 정도)",
        "cardio_rest": "숨이 너무 차면 걷기로 속도를 낮춰 이어가세요",
    },
    "MAINTAIN": {
        "label": "체중 유지",
        "sets_reps": "2세트 x 12~15회",
        "rest": "세트 사이 60초 휴식",
        "cardio_sets_reps": "15~20분 연속",
        "cardio_rest": None,
    },
}
# 목표를 아직 설정하지 않은 사용자. 유지 기준이 가장 무난하다.
DEFAULT_GOAL = "MAINTAIN"

# 부위별 기본 주의사항. 지어내지 않고 여기 적힌 것만 내보낸다.
BODY_PART_CAUTIONS = {
    "chest": "어깨가 말리지 않게 가슴을 펴고, 팔꿈치를 몸통과 45도 정도로 유지하세요.",
    "back": "허리를 젖히지 말고 등을 곧게 편 상태로 당기세요.",
    "shoulders": "무게를 올리기 전에 어깨가 아프지 않은 범위인지 먼저 확인하세요.",
    "upper arms": "반동으로 들어올리지 말고 팔꿈치를 몸통에 붙여 고정하세요.",
    "lower arms": "손목 통증이 있으면 즉시 멈추고 무게를 줄이세요.",
    "waist": "목을 손으로 당기지 말고, 허리가 바닥에서 뜨지 않게 하세요.",
    "upper legs": "무릎이 발끝보다 과하게 나가지 않게 하고, 허리를 굽히지 마세요.",
    "lower legs": "발목을 갑자기 튕기지 말고 천천히 올렸다 내리세요.",
    "neck": "통증이 아니라 당기는 느낌까지만, 반동 없이 천천히 하세요.",
    "cardio": "무릎·발목에 통증이 있으면 뛰는 동작 대신 걷기로 바꾸세요.",
}

SENIOR_AGE = 60
NO_ADVANCED_AGE = 50

DIFFICULTY_ORDER = {"beginner": 0, "intermediate": 1, "advanced": 2}
DIFFICULTY_LABEL = {"beginner": "초급", "intermediate": "중급", "advanced": "고급"}
# 영상의 난이도 태그(초급/중급/고급)와 운동 태그를 맞춰 붙이기 위한 대응
VIDEO_LEVEL_BY_DIFFICULTY = {"beginner": "초급", "intermediate": "중급", "advanced": "고급"}

# 최근 운동 기록을 "요즘 한 것"으로 볼 기간
RECENT_DAYS = 7
# 이 안에 같은 부위를 했으면 연속 자극이라 알려준다
CONSECUTIVE_DAYS = 2
# "이번 주에 한 번도 안 한 부위"로 짚어줄 대상(팔·전완·목처럼 작은 부위는 빼고 큰 덩어리만)
MAJOR_PARTS = ["chest", "back", "shoulders", "upper legs", "waist"]

_core_cache: Optional[dict] = None
_video_cache: Optional[dict] = None
_full_cache: Optional[list] = None


def _load_core() -> dict:
    global _core_cache
    if _core_cache is None:
        _core_cache = json.loads(CORE_PATH.read_text(encoding="utf-8"))["groups"]
    return _core_cache


def _load_videos() -> dict:
    """동작 이름 -> 국민체력100 영상 목록 (app/exercise/movements.py 기준)"""
    global _video_cache
    if _video_cache is None:
        _video_cache = json.loads(VIDEO_PATH.read_text(encoding="utf-8"))["by_movement"]
    return _video_cache


def _load_full() -> list:
    """설명 조회용 원본 전체(1,324건). 추천 후보로는 쓰지 않는다."""
    global _full_cache
    if _full_cache is None:
        _full_cache = json.loads(FULL_PATH.read_text(encoding="utf-8"))
    return _full_cache


def normalize_body_part(raw: str) -> Optional[str]:
    """
    한국어/영문 부위 표현을 body_part 키로. 못 맞추면 None.

    "상체"처럼 여러 부위를 아우르는 말은 그룹 키("upper body")로 돌려준다. 단일 부위보다
    먼저 보는 이유는 부분 일치라 순서가 결과를 바꾸기 때문이다.
    """
    if not raw:
        return None
    text = raw.strip().lower()
    if text in VALID_BODY_PARTS or text in BODY_PART_GROUPS:
        return text
    for ko, group in BODY_PART_GROUP_KO.items():
        if ko in text:
            return group
    for ko, en in BODY_PART_KO.items():
        if ko in text:
            return en
    return None


def parts_of(target: str) -> list[str]:
    """그룹이면 속한 부위들, 단일 부위면 그 부위 하나. 데이터 조회는 항상 이걸 거친다."""
    return BODY_PART_GROUPS.get(target) or [target]


def log_freeform_request(body_part: str, equipment: str, matched: Optional[str]) -> None:
    """
    부위 사전으로 못 맞춘 요청을 남긴다. "허리 안 아프게 하는 등 운동"처럼 필터로 못 잡는
    자유 표현이 실제로 얼마나 들어오는지 봐야 임베딩 검색이 필요한지 판단할 수 있다.
    (지금 단계에서 벡터 DB를 세우는 건 비용 대비 효과가 낮다는 판단이라, 근거부터 모은다.)
    """
    if matched is None:
        log.info("운동 추천 부위 매칭 실패 body_part=%r equipment=%r", body_part, equipment)


# ---------------------------------------------------------------------------
# 최근 운동 기록 읽기
# ---------------------------------------------------------------------------


def parse_recent_body_parts(recent_workouts: Optional[list], today: Optional[date] = None) -> dict:
    """
    운동 메모(자유 텍스트)에서 부위 키워드만 뽑아 {body_part: 며칠 전} 으로 바꾼다.

    메모는 "하체 - 스쿼트 60kg 5x5" 처럼 쓰이므로 키워드 매칭만으로도 충분히 동작한다.
    형태소 분석이나 임베딩을 붙일 이유가 없다 - 못 맞추면 조언 한 줄이 빠질 뿐이다.

    :param recent_workouts: [{"date": "2026-09-03", "text": "하체 스쿼트"}, ...]
    """
    today = today or date.today()
    days_ago: dict[str, int] = {}
    for entry in recent_workouts or []:
        text = (entry or {}).get("text") or ""
        raw_date = (entry or {}).get("date") or ""
        try:
            memo_date = datetime.strptime(raw_date, "%Y-%m-%d").date()
        except ValueError:
            continue
        gap = (today - memo_date).days
        if gap < 0 or gap > RECENT_DAYS:
            continue
        for keyword, part in BODY_PART_KO.items():
            if keyword in text:
                days_ago[part] = min(days_ago.get(part, gap), gap)
        # "어제 상체" 같은 메모는 속한 부위를 전부 한 것으로 본다 - 안 그러면 어제 상체를
        # 한 사람에게 "이번 주에 가슴을 한 번도 안 했다"고 말한다.
        for keyword, group in BODY_PART_GROUP_KO.items():
            if keyword in text:
                for part in BODY_PART_GROUPS[group]:
                    days_ago[part] = min(days_ago.get(part, gap), gap)
    return days_ago


def _workout_note(target: str, days_ago: dict) -> Optional[str]:
    """
    최근 기록을 근거로 한 줄. 없으면 None.

    추천 자체를 바꾸지는 않는다(사용자가 부위를 골라서 물었는데 다른 부위를 들이밀면 안 된다).
    "이런 상황이니 참고하라"는 정보만 준다.
    """
    if not days_ago:
        return None

    # 그룹("상체")이면 속한 부위 중 가장 최근에 한 것을 기준으로 본다.
    parts = parts_of(target)
    gap = min((days_ago[p] for p in parts if p in days_ago), default=None)
    if gap is not None and gap <= CONSECUTIVE_DAYS:
        when = "오늘" if gap == 0 else ("어제" if gap == 1 else f"{gap}일 전")
        rested = [p for p in MAJOR_PARTS if p not in parts and p not in days_ago]
        if rested:
            others = "이나 ".join(BODY_PART_LABEL[p] for p in rested[:2])
            return (
                f"{when} {BODY_PART_LABEL[target]} 운동을 하셨네요. 같은 부위를 이어서 하면 회복이 부족할 수 있으니,"
                f" {others} 쪽도 생각해보세요."
            )
        return f"{when} {BODY_PART_LABEL[target]} 운동을 하셨어요. 근육통이 남아 있으면 강도를 낮춰서 하세요."

    untouched = [p for p in MAJOR_PARTS if p not in days_ago]
    if untouched:
        names = ", ".join(BODY_PART_LABEL[p] for p in untouched[:2])
        return f"최근 {RECENT_DAYS}일 기록을 보면 {names} 운동이 한 번도 없었어요. 이번 주에 한 번 넣어보세요."
    return None


# ---------------------------------------------------------------------------
# 후보 선정
# ---------------------------------------------------------------------------


def _drop_advanced(pool: list, age: Optional[int]) -> list:
    """
    고급 동작을 후보에서 뺀다. 초·중급만으로 채울 수 있으면 나이와 무관하게 뺀다 -
    "하체 맨몸"에 맨몸 글루트햄 레이즈가 나오면 초보자는 그대로 다치거나 포기한다.
    고급은 사용자가 명시적으로 원할 때 주는 게 맞는데, 지금은 그렇게 말할 통로가 없다.

    초·중급이 MIN_PICKS도 안 되는 부위(데이터가 얇은 경우)에는 어쩔 수 없이 채우되,
    50세 이상이면 개수가 모자라더라도 고급은 넣지 않는다.
    """
    safer = [e for e in pool if e["difficulty"] != "advanced"]
    if len(safer) >= MIN_PICKS:
        return safer
    if age is not None and age >= NO_ADVANCED_AGE and safer:
        return safer
    return pool


def _narrow_by_equipment(pool: list, equipment: str) -> tuple:
    """
    장비 조건으로 후보를 좁힌다. (좁힌 후보, 안내 문구) - 조건을 그대로 지키지 못했을 때만 문구가 붙는다.

    "맨몸"은 기구 없이(equipment == "body weight") 할 수 있는 것만이다. 다만 어깨처럼 맨몸
    동작이 데이터에 거의 없는 부위가 있어서, 그때는 조건을 한 단계씩 넓히고 넓혔다는 사실을
    사용자에게 알린다 - 조용히 덤벨 운동을 내주면 "맨몸이라고 했는데?"가 된다.
    """
    if not equipment:
        return pool, None

    if any(hint in equipment for hint in EQUIPMENT_FREE_HINTS):
        bodyweight = [e for e in pool if e["equipment"] == "body weight"]
        if len(bodyweight) >= MIN_PICKS:
            return bodyweight, None
        home = [e for e in pool if e["home_friendly"]]
        if len(home) >= MIN_PICKS:
            return home, "이 부위는 기구 없이 하는 동작이 많지 않아, 집에서 할 수 있는 가벼운 도구 운동도 같이 골랐어요."
        return pool, "이 부위는 기구 없이 하는 동작이 많지 않아 장비 조건을 넓혀서 골랐어요."

    if any(hint in equipment for hint in HOME_HINTS):
        home = [e for e in pool if e["home_friendly"]]
        if len(home) >= MIN_PICKS:
            return home, None
        return pool, "집에서 할 수 있는 동작이 많지 않아 장비 조건을 넓혀서 골랐어요."

    keyword = _equipment_keyword(equipment)
    narrowed = [e for e in pool if (keyword or equipment) in e["equipment"].lower()]
    if narrowed:
        return narrowed, None
    if keyword:
        # 무슨 장비인지 알아들었는데 이 부위엔 그 동작이 없는 경우다. 조용히 넓히면
        # "덤벨이라고 했는데?"가 된다 - 맨몸일 때와 같은 이유로 알린다.
        return pool, f"이 부위에는 {equipment} 동작이 없어서 장비 조건 없이 골랐어요."
    # 장비인지 아닌지 모르는 문자열이면 예전처럼 부위 필터까지만 적용하고 조용히 넘어간다
    return pool, None


def _equipment_keyword(equipment: str) -> Optional[str]:
    """사용자가 말한 장비를 데이터의 equipment 값에 들어 있는 영문 표현으로. 못 맞추면 None."""
    for ko, en in EQUIPMENT_KO.items():
        if ko in equipment:
            return en
    return None


def _sort_key(exercise: dict, prefer_home: bool) -> tuple:
    """
    결정적 정렬. 앞의 항목일수록 좋은 후보다.

    난이도를 맨 앞에 두는 이유: 이 앱 사용자는 대부분 초보다. 복합운동을 먼저 두면
    "복근 맨몸"에서 인치웜(중급)이 3/4 싯업(초급)보다 앞에 나온다 - 자극의 효율보다
    "지금 따라 할 수 있는가"가 먼저다. 복합운동 우선은 같은 난이도 안에서만 적용한다
    (3~4개짜리 루틴이 고립운동으로만 차면 정작 큰 근육을 안 쓰게 되므로).
    """
    return (
        DIFFICULTY_ORDER[exercise["difficulty"]],
        0 if exercise["is_compound"] else 1,
        0 if (prefer_home and exercise["home_friendly"]) else 1,
        exercise["name_ko"],
    )


def names_in_text(pool: list, texts: Optional[list]) -> set:
    """
    최근 챗봇 답변 원문에서 이미 추천했던 운동 이름을 찾아낸다.

    운동 이름 목록은 이 서버(큐레이션 파일)에만 있으므로, 백엔드는 답변 원문만 넘기고
    "무엇이 운동 이름인지"는 여기서 판단한다. 이름을 양쪽에 복제하지 않기 위한 분담이다.
    """
    joined = " ".join(texts or [])
    if not joined:
        return set()

    # 짧은 이름이 긴 이름 안에 그대로 들어 있다("푸시업" ⊂ "닐링 푸시업", "풀업" ⊂ "보조 풀업").
    # 단순 부분 문자열로 세면 "닐링 푸시업"만 추천했는데 "푸시업"까지 제외돼 후보가 깎인다.
    # 한국어는 조사가 이름에 바로 붙어서("워킹 런지를") 단어 경계 정규식도 못 쓴다.
    # 그래서 긴 이름부터 맞춰보고, 이미 다른 이름이 차지한 자리는 건너뛴다.
    claimed = [False] * len(joined)
    found = set()
    for exercise in sorted(pool, key=lambda e: -len(e["name_ko"] or "")):
        name = exercise["name_ko"]
        if not name:
            continue
        for match in re.finditer(re.escape(name), joined):
            if any(claimed[match.start():match.end()]):
                continue
            for index in range(match.start(), match.end()):
                claimed[index] = True
            found.add(name)
            break
    return found


def _pick(pool: list, prefer_home: bool, exclude: set, spread_body_parts: bool = False) -> list:
    """
    최근 추천한 것을 뺀 뒤, 정렬 1등부터 시작해 "겹치지 않는 것"을 이어 붙인다.

    정렬만으로 앞에서 4개를 자르면 이름순 때문에 비슷한 게 뭉친다 - 실제로 "덤벨 고블릿
    스쿼트 / 덤벨 런지 / 덤벨 리어 런지 / 덤벨 스쿼트"처럼 스쿼트 둘 + 런지 둘이 나왔다.
    그래서 다음 후보를 고를 때 아직 안 쓴 타겟 근육 -> 아직 안 쓴 장비 순으로 우선한다.
    무작위가 아니라 순위 기반이라 결과는 매번 같다.

    :param spread_body_parts: 복합 부위("상체")일 때 True. 부위가 겹치지 않는 것을 먼저 고른다 -
                              합친 풀은 정렬이 부위를 구분하지 않아서, 이게 없으면 "상체"인데
                              가슴 운동만 4개 나온다.
    """
    remaining = [e for e in pool if e["name_ko"] not in exclude and e["name"] not in exclude]
    if len(remaining) < MIN_PICKS:
        remaining = pool

    ordered = sorted(remaining, key=lambda e: _sort_key(e, prefer_home))
    if len(ordered) <= MIN_PICKS:
        return ordered

    picks = [ordered[0]]
    rest = list(enumerate(ordered))[1:]
    while rest and len(picks) < MAX_PICKS:
        used_parts = {e["body_part"] for e in picks}
        used_targets = {e["target"] for e in picks}
        used_equipment = {e["equipment"] for e in picks}
        rank, best = min(
            rest,
            key=lambda pair: (
                0 if not spread_body_parts or pair[1]["body_part"] not in used_parts else 1,
                0 if pair[1]["target"] not in used_targets else 1,
                # 다양성보다 난이도가 먼저다. 이게 빠져 있어서 "하체 맨몸"에 햄스트링 타겟이
                # 비었다는 이유로 글루트햄 레이즈(고급)가 초급 런지들을 밀어냈다.
                DIFFICULTY_ORDER[pair[1]["difficulty"]],
                0 if pair[1]["equipment"] not in used_equipment else 1,
                pair[0],  # 같은 조건이면 원래 순위대로
            ),
        )
        picks.append(best)
        rest = [pair for pair in rest if pair[0] != rank]
    return picks


def _video_for(exercise: dict, index: int) -> Optional[dict]:
    """
    추천한 운동에 붙일 국민체력100 영상 1건. 같은 '동작'인 영상만 붙이고, 없으면 안 붙인다.

    예전엔 타겟 근육으로 이었는데 "덤벨 런지" 아래에 "Clamshell"이 붙었다 - 근육은 같아도
    사용자 눈에는 남의 운동이다. 붙는 운동이 줄더라도 맞는 것만 붙이는 편이 낫다.

    난이도 태그가 맞는 것을 우선하고, 같은 동작이 여러 개면 순번으로 어긋나게 집는다
    (무작위가 아니라 위치 기반이라 결과는 매번 같다).
    """
    videos = _load_videos()
    bucket: list = []
    seen_urls = set()
    for movement in movements_of_exercise(exercise["name"]):
        for video in videos.get(movement) or []:
            if video["video_url"] not in seen_urls:
                seen_urls.add(video["video_url"])
                bucket.append(video)
    if not bucket:
        return None

    wanted_level = VIDEO_LEVEL_BY_DIFFICULTY[exercise["difficulty"]]
    leveled = [v for v in bucket if v["level"] == wanted_level]
    pool = leveled or bucket
    return pool[index % len(pool)]


def _cautions(target: str, picks: list, age: Optional[int]) -> list:
    if target in BODY_PART_GROUPS:
        # 복합 부위는 실제로 뽑힌 운동의 부위만 짚는다 - 등 운동이 안 나왔는데 등 주의사항을
        # 붙이면 사용자는 없는 운동을 찾는다. 말풍선이 주의 목록이 되지 않게 2개까지만.
        picked = list(dict.fromkeys(e["body_part"] for e in picks))
        cautions = [BODY_PART_CAUTIONS[p] for p in picked if p in BODY_PART_CAUTIONS][:2]
    else:
        cautions = [BODY_PART_CAUTIONS[target]]
    if age is not None and age >= SENIOR_AGE:
        cautions.append("관절에 무리가 가지 않는 범위에서, 반동 없이 천천히 하세요.")
    if any(e["difficulty"] == "advanced" for e in picks):
        cautions.append("고급 동작이 포함돼 있어요. 자세가 익숙하지 않으면 쉬운 동작부터 하세요.")
    return cautions


def recommend(
    body_part: str,
    equipment: str = "",
    goal: Optional[str] = None,
    age: Optional[int] = None,
    recent_workouts: Optional[list] = None,
    exclude: Optional[list] = None,
    exclude_from_text: Optional[list] = None,
    today: Optional[date] = None,
) -> dict:
    """
    :param body_part: 운동할 부위 (한국어 표현 또는 영문 키). 못 맞추면 후보를 비워 돌려준다 -
                      엉뚱한 부위를 던지면 챗봇이 그걸로 헛소리를 만든다.
    :param equipment: 장비/환경 힌트. "맨몸"/"집" 계열이면 집에서 되는 것만, 그 외 문자열이면
                      equipment 부분일치로 좁힌다. 좁힌 결과가 비면 부위 필터까지만 적용한다.
    :param goal: 프로필의 목표. 백엔드 Goal enum 이름 그대로 LOSE / GAIN / MAINTAIN 셋 중 하나다
                 (다른 문자열이 오면 조용히 MAINTAIN 기준으로 처방된다). 세트·횟수가 여기서 갈린다.
    :param age: 나이. 50대 이상이면 고급 동작을 후보에서 뺀다.
    :param recent_workouts: 최근 운동 메모 [{"date","text"}]. 조언 한 줄을 만드는 데만 쓴다.
    :param exclude: 최근에 이미 추천한 운동 이름. 같은 답이 반복되지 않게 뺀다.
    :param exclude_from_text: 최근 챗봇 답변 원문. 여기 등장한 운동 이름도 같이 뺀다.
    """
    target = normalize_body_part(body_part)
    log_freeform_request(body_part, equipment, target)
    if target is None:
        return {
            "body_part": "",
            "matched": 0,
            "candidates": [],
            "note": "어느 부위 운동인지 알려주시면 추천해드릴게요. (예: 상체, 하체, 가슴, 등, 어깨, 팔, 복근, 종아리)",
        }

    core = _load_core()
    pool = [e for part in parts_of(target) for e in core.get(part) or []]

    eq = (equipment or "").strip().lower()
    prefer_home = any(hint in eq for hint in EQUIPMENT_FREE_HINTS | HOME_HINTS) if eq else False
    pool, equipment_note = _narrow_by_equipment(pool, eq)

    pool = _drop_advanced(pool, age)

    if not pool:
        return {
            "body_part": target,
            "matched": 0,
            "candidates": [],
            "note": "조건에 맞는 운동을 찾지 못했어요. 부위나 장비 조건을 바꿔서 다시 시도해 주세요.",
        }

    excluded = set(exclude or []) | names_in_text(pool, exclude_from_text)
    picks = _pick(pool, prefer_home, excluded, spread_body_parts=target in BODY_PART_GROUPS)
    plan = GOAL_PLANS.get(goal or DEFAULT_GOAL, GOAL_PLANS[DEFAULT_GOAL])
    is_cardio = target == "cardio"
    sets_reps = plan["cardio_sets_reps"] if is_cardio else plan["sets_reps"]
    rest = plan["cardio_rest"] if is_cardio else plan["rest"]

    candidates = []
    for index, exercise in enumerate(picks):
        related_video = _video_for(exercise, index)
        candidates.append({
            "name": exercise["name_ko"],
            "body_part": exercise["body_part"],
            "equipment": exercise["equipment"],
            "target": exercise["target"],
            "difficulty": DIFFICULTY_LABEL[exercise["difficulty"]],
            "is_compound": exercise["is_compound"],
            "home_friendly": exercise["home_friendly"],
            # 후보에 한국어 설명을 같이 싣는다. 예전엔 이름만 넘기고 설명은 챗봇이 직접 쓰게 뒀는데,
            # 근거 없는 자유 생성이라 Qwen이 중국어로 새는 턴이 나왔다(실측).
            "instructions_ko": exercise["instructions_ko"],
            "sets_reps": sets_reps,
            # 같은 동작인 영상만 붙는다(movements.py). 없으면 None - 근육만 같은 남의 운동은 안 붙인다
            "related_video": related_video,
        })

    return {
        "body_part": target,
        "body_part_ko": BODY_PART_LABEL[target],
        "matched": len(pool),
        "goal": plan["label"] if goal else None,
        "plan": f"{sets_reps} · {rest}" if rest else sets_reps,
        "candidates": candidates,
        "cautions": _cautions(target, picks, age),
        # 장비 조건을 그대로 지키지 못했으면 그 사실을 알린다(조용히 넓히면 거짓말이 된다)
        "note": equipment_note,
        "workout_note": _workout_note(target, parse_recent_body_parts(recent_workouts, today)),
    }


_override_cache: Optional[dict] = None


def _core_name_overrides() -> dict:
    """큐레이션에서 덧씌운 한국어 이름 -> 원본 영문 이름"""
    global _override_cache
    if _override_cache is None:
        _override_cache = {}
        for rows in _load_core().values():
            for e in rows:
                if e["name_ko"] != e.get("name_ko_source"):
                    _override_cache[_normalize_name(e["name_ko"])] = e
    return _override_cache


def _normalize_name(raw: str) -> str:
    """이름 비교용 정규화 - 공백 차이("벤치 프레스" vs "벤치프레스")로 못 찾는 걸 막는다."""
    return "".join((raw or "").split()).lower()


def find_detail(name: str) -> dict:
    """
    운동 이름 하나로 그 운동의 한국어 설명(instructions_ko)을 찾아 돌려준다.

    추천 후보는 큐레이션 152건으로 좁혔지만 이 조회는 원본 1,324건 전체를 뒤진다 -
    사용자가 큐레이션에 없는 운동을 물어도 답할 수 있어야 커버리지가 유지된다.

    예전에는 이 단계에서 도구를 안 부르고 모델이 설명을 직접 지어내게 뒀는데, 근거 없는
    자유 생성이라 Qwen이 중국어로 새는 턴이 나왔다(실측). 데이터에 전부 한국어 설명이
    있으므로 그걸 그대로 넘겨서 "창작"을 "옮겨쓰기"로 바꾼다.

    :param name: 사용자가 지목한 운동 이름 (추천 목록에 보여준 이름이거나 그 일부)
    """
    exercises = _load_full()
    key = _normalize_name(name)
    if not key:
        return {"found": False, "note": "어떤 운동인지 알려주시면 설명해드릴게요."}

    # 추천 목록에서는 시드가 덧씌운 이름("앞으로 런지")을 보여줬을 수 있다. 사용자가 그 이름으로
    # 되물으면 원본에는 없는 이름이라 못 찾으므로, 덧씌운 이름 -> 원본 이름을 먼저 되돌린다.
    override = _core_name_overrides().get(key)
    if override:
        for e in exercises:
            if e["name"] == override["name"]:
                # 설명은 원본 것이지만 이름은 추천에 보여준 이름으로 돌려준다
                return {**_detail_of(e), "name": override["name_ko"]}

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

    # 3) 문장 안에 이름이 들어 있는 경우 - "덤벨 런지 자세 알려줘"처럼 백엔드가 사용자 문장을
    #    그대로 넘긴다(어떤 말이 운동 이름인지는 이 서버만 안다). 긴 이름부터 맞춰 "닐링 푸시업"이
    #    "푸시업"으로 접히지 않게 한다. 큐레이션이 덧씌운 이름은 원본 목록에 없으므로 같이 본다.
    found = _longest_name_in(exercises, key)
    if found:
        return found

    # 4) 조사를 뗀 낱말로 다시 - "플랭크는 어떻게 해?"의 "플랭크"는 어느 이름과도 같지 않지만
    #    "프론트 플랭크"처럼 그 말을 품은 이름은 있다. 낱말 단위로 2)를 다시 돌린다.
    for word in sorted(_words_without_particles(name), key=len, reverse=True):
        wkey = _normalize_name(word)
        if len(wkey) < 2 or wkey in _DETAIL_STOPWORDS:
            continue
        partial = [e for e in exercises if wkey in _normalize_name(e.get("name_ko"))]
        if partial:
            return _detail_of(min(partial, key=lambda e: len(e.get("name_ko") or "")))

    return {"found": False, "note": "어떤 운동인지 찾지 못했어요. 추천해드린 목록에 있는 이름으로 물어봐 주세요."}


# 운동 이름의 일부이긴 하지만 그 자체로는 운동을 가리키지 않는 말. "두 번째 운동 어떻게 해?"의
# "운동"이 "운동 볼 딥스"에 걸리는 걸 막는다.
_DETAIL_STOPWORDS = {"운동", "자세", "방법", "설명", "동작", "세트", "횟수", "번째", "추천", "알려", "어떻게", "하는"}

# 낱말 끝에 붙는 조사. 긴 것부터 떼야 "으로"가 "로"로만 잘리지 않는다.
_PARTICLES = ("으로", "에서", "이랑", "하고", "는", "은", "이", "가", "을", "를", "의", "도", "로", "랑", "에")


def _words_without_particles(text: str) -> list[str]:
    words = []
    for raw in re.split(r"[\s,.?!~/()]+", text or ""):
        if not raw:
            continue
        for particle in _PARTICLES:
            if raw.endswith(particle) and len(raw) > len(particle):
                raw = raw[: -len(particle)]
                break
        words.append(raw)
    return words


def _longest_name_in(exercises: list, key: str) -> Optional[dict]:
    """key(정규화된 문장) 안에 들어 있는 운동 이름 중 가장 긴 것의 설명. 없으면 None."""
    best_len = 0
    best: Optional[dict] = None
    # 큐레이션에서 덧씌운 이름(추천 목록에 보여준 이름)이 원본 이름보다 우선이다
    for norm, override in _core_name_overrides().items():
        if len(norm) >= 2 and norm in key and len(norm) > best_len:
            for e in exercises:
                if e["name"] == override["name"]:
                    best, best_len = {**_detail_of(e), "name": override["name_ko"]}, len(norm)
                    break
    for e in exercises:
        norm = _normalize_name(e.get("name_ko"))
        if len(norm) >= 2 and norm in key and len(norm) > best_len:
            best, best_len = _detail_of(e), len(norm)
    return best


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
