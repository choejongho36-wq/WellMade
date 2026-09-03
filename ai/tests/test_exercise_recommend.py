"""운동 추천 v1 테스트 (app/exercise/recommend.py + /ai/exercise/recommend)."""

from fastapi.testclient import TestClient

from app.exercise.recommend import MAX_CANDIDATES, normalize_body_part, recommend
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
    assert all(c["name"] and c["steps"] for c in result["candidates"])


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
