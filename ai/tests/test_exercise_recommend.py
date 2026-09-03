"""운동 추천 v1 테스트 (app/exercise/recommend.py + /ai/exercise/recommend)."""

from fastapi.testclient import TestClient

from app.exercise.recommend import MAX_CANDIDATES, find_detail, normalize_body_part, recommend
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
    assert result["matched"] > MAX_CANDIDATES  # 가슴 운동은 데이터에 163건 있음
    assert len(result["candidates"]) == MAX_CANDIDATES
    assert all(c["body_part"] == "chest" for c in result["candidates"])
    assert all(c["name"] for c in result["candidates"])


def test_모르는_부위면_후보를_비우고_안내만_돌려준다():
    # "플랭크"처럼 부위가 아닌 값이 오면, 엉뚱한 운동 8건 대신 빈 후보 + 안내를 준다
    result = recommend(body_part="플랭크")

    assert result["candidates"] == []
    assert result["matched"] == 0
    assert result["note"]


def test_맨몸_조건이면_body_weight로_좁힌다():
    result = recommend(body_part="복근", equipment="맨몸")

    assert result["matched"] > 0
    assert all(c["equipment"] == "body weight" for c in result["candidates"])


def test_장비가_안맞으면_부위_필터까지만_적용한다():
    # '종아리 + 스미스머신' 조합은 데이터에 없을 수 있다 - 그래도 종아리 후보는 나와야 한다
    result = recommend(body_part="종아리", equipment="존재하지않는장비")

    assert result["matched"] > 0
    assert all(c["body_part"] == "lower legs" for c in result["candidates"])


def test_엔드포인트가_후보를_반환한다():
    res = client.post("/ai/exercise/recommend", json={"body_part": "등"})

    assert res.status_code == 200
    body = res.json()
    assert body["body_part"] == "back"
    assert len(body["candidates"]) == MAX_CANDIDATES


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
