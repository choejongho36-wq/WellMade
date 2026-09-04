"""운동 추천 v2 테스트 (app/exercise/recommend.py + /ai/exercise/recommend)."""

from datetime import date

from fastapi.testclient import TestClient

from app.exercise.recommend import (
    MIN_PICKS,
    find_detail,
    normalize_body_part,
    parse_recent_body_parts,
    recommend,
)
from app.main import app

client = TestClient(app)


def test_한국어_부위를_영문_body_part로_바꾼다():
    assert normalize_body_part("하체") == "upper legs"
    assert normalize_body_part("가슴") == "chest"
    assert normalize_body_part("복근") == "waist"
    assert normalize_body_part("chest") == "chest"
    assert normalize_body_part("알수없는부위") is None


def test_부위로_필터링하고_후보를_돌려준다():
    result = recommend(body_part="가슴")

    assert result["body_part"] == "chest"
    assert result["body_part_ko"] == "가슴"
    assert len(result["candidates"]) >= MIN_PICKS
    assert all(c["body_part"] == "chest" for c in result["candidates"])
    assert all(c["name"] and c["instructions_ko"] for c in result["candidates"])


def test_같은_요청은_항상_같은_답을_준다():
    """random.sample을 쓰던 v1은 매번 달라서 재현도 평가도 안 됐다."""
    first = recommend(body_part="등", equipment="맨몸")
    second = recommend(body_part="등", equipment="맨몸")

    assert [c["name"] for c in first["candidates"]] == [c["name"] for c in second["candidates"]]


def test_비슷한_운동이_뭉치지_않게_고른다():
    """정렬만으로 앞에서 자르면 이름순 때문에 '스쿼트 둘 + 런지 둘'이 나왔다."""
    result = recommend(body_part="하체", equipment="집")
    targets = [c["target"] for c in result["candidates"]]

    assert len(set(targets)) >= 3, targets


def test_복합운동과_쉬운_동작이_먼저_나온다():
    result = recommend(body_part="가슴")
    names = [c["name"] for c in result["candidates"]]
    difficulties = [c["difficulty"] for c in result["candidates"]]

    # 고립운동만 나오면 3~4개짜리 루틴에서 정작 큰 근육을 안 쓰게 된다
    assert result["candidates"][0]["is_compound"] is True
    assert "초급" in difficulties, names


def test_최근_추천한_운동은_빼고_고른다():
    first = recommend(body_part="어깨")
    already = [c["name"] for c in first["candidates"]]

    second = recommend(body_part="어깨", exclude=already)

    assert not (set(already) & {c["name"] for c in second["candidates"]})


def test_뺄_게_너무_많으면_제외를_포기한다():
    """제외 때문에 후보가 없어지면 추천 자체가 안 되므로, 반복을 감수하고 채운다."""
    result = recommend(body_part="목", exclude=["목 옆 스트레칭", "옆으로 밀기 목 스트레칭"])

    assert result["candidates"]


def test_목표에_따라_세트와_횟수가_달라진다():
    gain = recommend(body_part="가슴", goal="GAIN")
    loss = recommend(body_part="가슴", goal="LOSE")
    keep = recommend(body_part="가슴", goal="MAINTAIN")

    assert "3세트 x 8~12회" in gain["plan"]
    assert "서킷 3라운드" in loss["plan"]
    assert "2세트 x 12~15회" in keep["plan"]
    assert all(c["sets_reps"] == "3세트 x 8~12회" for c in gain["candidates"])


def test_목표가_없으면_유지_기준으로_처방한다():
    result = recommend(body_part="가슴")

    assert result["goal"] is None
    assert "2세트 x 12~15회" in result["plan"]


def test_유산소는_세트가_아니라_시간으로_처방한다():
    result = recommend(body_part="유산소", goal="LOSE")

    assert "분" in result["plan"]
    # 유산소에 "세트 사이 휴식"이 붙으면 말이 안 된다
    assert "세트 사이" not in result["plan"]


def test_유산소_처방에는_세트_휴식을_붙이지_않는다():
    for goal in ("GAIN", "MAINTAIN"):
        plan = recommend(body_part="유산소", goal=goal)["plan"]
        assert "휴식" not in plan, plan


def test_나이가_많으면_고급_동작을_뺀다():
    senior = recommend(body_part="하체", age=65)

    assert all(c["difficulty"] != "고급" for c in senior["candidates"])
    assert any("관절" in caution for caution in senior["cautions"])


def test_부위별_주의사항을_같이_준다():
    result = recommend(body_part="복근")

    assert result["cautions"]
    assert "허리" in result["cautions"][0]


def test_맨몸이면_기구가_아예_없는_것만_고른다():
    """사용자에게 '맨몸'은 '기구 없음'이다. 덤벨도 home_friendly라 그걸로 거르면 덤벨이 나왔다."""
    for body_part in ("복근", "하체", "가슴"):
        result = recommend(body_part=body_part, equipment="맨몸")

        assert result["candidates"], body_part
        assert all(c["equipment"] == "body weight" for c in result["candidates"]), \
            [c["name"] + "/" + c["equipment"] for c in result["candidates"]]


def test_집_조건이면_가벼운_도구까지_허용한다():
    result = recommend(body_part="하체", equipment="집")

    assert all(c["home_friendly"] for c in result["candidates"])
    # 집이면 덤벨·밴드도 되므로 맨몸만 나오지는 않는다
    assert any(c["equipment"] != "body weight" for c in result["candidates"])


def test_맨몸_동작이_부족한_부위는_조건을_넓히고_그_사실을_알린다():
    """어깨는 데이터에 맨몸 동작이 사실상 없다. 조용히 덤벨을 내주면 거짓말이 된다."""
    result = recommend(body_part="어깨", equipment="맨몸")

    assert result["candidates"]
    assert result["note"]
    assert "기구 없이" in result["note"]


def test_장비가_안맞으면_부위_필터까지만_적용한다():
    # '종아리 + 존재하지 않는 장비' 조합이 비면 그래도 종아리 후보는 나와야 한다
    result = recommend(body_part="종아리", equipment="존재하지않는장비")

    assert result["matched"] > 0
    assert all(c["body_part"] == "lower legs" for c in result["candidates"])


def test_모르는_부위면_후보를_비우고_안내만_돌려준다():
    # "플랭크"처럼 부위가 아닌 값이 오면, 엉뚱한 운동 대신 빈 후보 + 안내를 준다
    result = recommend(body_part="플랭크")

    assert result["candidates"] == []
    assert result["matched"] == 0
    assert result["note"]


# ---- 최근 운동 메모 반영 ----


def test_메모에서_부위_키워드를_읽는다():
    parsed = parse_recent_body_parts(
        [
            {"date": "2026-09-03", "text": "하체 - 스쿼트 60kg 5x5"},
            {"date": "2026-08-20", "text": "가슴 벤치프레스"},  # 7일 밖이라 무시
        ],
        today=date(2026, 9, 4),
    )

    assert parsed["upper legs"] == 1
    assert "chest" not in parsed


def test_어제_같은_부위를_했으면_알려준다():
    result = recommend(
        body_part="하체",
        recent_workouts=[{"date": "2026-09-03", "text": "하체 스쿼트"}],
        today=date(2026, 9, 4),
    )

    assert "어제" in result["workout_note"]
    assert "하체" in result["workout_note"]


def test_이번_주에_안_한_부위를_짚어준다():
    result = recommend(
        body_part="가슴",
        recent_workouts=[{"date": "2026-09-03", "text": "가슴 푸시업"}],
        today=date(2026, 9, 4),
    )

    # 가슴은 어제 했으니 쉬어야 할 다른 부위를 권한다
    assert result["workout_note"]
    assert "등" in result["workout_note"]


def test_메모가_없으면_조언도_없다():
    assert recommend(body_part="가슴")["workout_note"] is None


# ---- 국민체력100 영상 ----


def test_같은_동작인_영상만_붙인다():
    """근육으로 이었을 땐 '덤벨 런지' 아래에 'Clamshell'이 붙었다 - 남의 운동이다."""
    result = recommend(body_part="가슴", equipment="맨몸")
    videos = [c["related_video"] for c in result["candidates"] if c["related_video"]]

    assert videos
    assert all(v["video_url"].startswith("http") for v in videos)
    # 난이도 태그가 없는 영상은 애초에 데이터에 넣지 않는다(화면에 보여줄 정보가 없다)
    assert all(v["level"] in ("초급", "중급", "고급") for v in videos)


def test_동작이_안_맞으면_영상을_안_붙인다():
    """맞는 영상이 없는데 근육만 같은 걸 붙이느니 안 붙이는 게 낫다."""
    result = recommend(body_part="전완")

    assert all(c["related_video"] is None for c in result["candidates"])


def test_엔드포인트가_추천을_반환한다():
    res = client.post(
        "/ai/exercise/recommend",
        json={"body_part": "등", "goal": "GAIN", "age": 30},
    )

    assert res.status_code == 200
    body = res.json()
    assert body["body_part"] == "back"
    assert len(body["candidates"]) >= MIN_PICKS
    assert "3세트" in body["plan"]


# ---- 운동 상세 (find_detail + /ai/exercise/detail) ----
# 이 단계는 예전에 도구 없이 모델이 설명을 직접 지어내게 뒀다가, 근거 없는 자유 생성이라
# Qwen이 중국어로 새는 턴이 나왔다(실측). 데이터의 한국어 설명을 반드시 실어 보내야 한다.


def test_정확한_이름으로_한국어_설명을_찾는다():
    result = find_detail("덤벨 벤치 프레스")

    assert result["found"] is True
    assert result["name"] == "덤벨 벤치 프레스"
    assert result["instructions_ko"]  # 설명이 비어 있으면 모델이 또 지어낸다


def test_공백_차이를_무시하고_찾는다():
    assert find_detail("덤벨벤치프레스")["name"] == "덤벨 벤치 프레스"


def test_부분_이름이면_가장_짧은_후보로_고른다():
    # 데이터에 플레인 "플랭크"는 없고 변형만 9건 있다. 못 찾았다고 끝내지 않고
    # 실제 존재하는 운동 하나를 골라 그 진짜 이름과 설명을 준다.
    result = find_detail("플랭크")

    assert result["found"] is True
    assert "플랭크" in result["name"]
    assert result["instructions_ko"]


def test_없는_운동이면_지어내지_말라고_안내한다():
    result = find_detail("존재하지않는운동zzz")

    assert result["found"] is False
    assert result["note"]
    assert "instructions_ko" not in result or not result.get("instructions_ko")


def test_상세_엔드포인트가_설명을_돌려준다():
    res = client.post("/ai/exercise/detail", json={"name": "덤벨 벤치 프레스"})

    assert res.status_code == 200
    body = res.json()
    assert body["found"] is True
    assert body["instructions_ko"]


def test_짧은_이름이_긴_이름_안에_걸리지_않는다():
    """"푸시업"은 "닐링 푸시업" 안에 그대로 들어 있다 - 둘 다 셌다간 후보가 괜히 깎인다."""
    from app.exercise.recommend import _load_core, names_in_text

    chest = _load_core()["chest"]
    assert names_in_text(chest, ["닐링 푸시업을 추천드렸어요."]) == {"닐링 푸시업"}
    # 조사가 붙어도(“푸시업을”) 이름은 잡아야 한다
    assert names_in_text(chest, ["푸시업을 해보세요."]) == {"푸시업"}
    assert names_in_text(chest, ["닐링 푸시업과 푸시업을 했어요."]) == {"닐링 푸시업", "푸시업"}


def test_덧씌운_이름으로_되물어도_설명을_찾는다():
    """추천에는 '앞으로 런지'로 보여줬는데 원본 이름은 '앞으로 런지 (남성)'이다."""
    result = find_detail("앞으로 런지")

    assert result["found"] is True
    assert result["name"] == "앞으로 런지"
    assert result["instructions_ko"]


def test_최근_답변에_나온_운동도_제외한다():
    first = recommend(body_part="어깨")
    reply = "지난번엔 " + ", ".join(c["name"] for c in first["candidates"]) + " 을(를) 추천드렸어요."

    second = recommend(body_part="어깨", exclude_from_text=[reply])

    assert not ({c["name"] for c in first["candidates"]} & {c["name"] for c in second["candidates"]})
