"""영양 섭취 또래 비교 테스트 (app/insight/nutrition_peer.py + /ai/nutrition/peer-compare)."""

from fastapi.testclient import TestClient

from app.insight.nutrition_peer import compare_with_peers, to_age_bracket
from app.main import app

client = TestClient(app)


def test_연령을_국민건강통계_구간으로_바꾼다():
    assert to_age_bracket(25) == "19-29"
    assert to_age_bracket(30) == "30-39"
    assert to_age_bracket(69) == "60-69"
    # 통계의 마지막 구간은 70+ 하나로 묶여 있다
    assert to_age_bracket(70) == "70+"
    assert to_age_bracket(95) == "70+"


def test_또래_평균_대비_비율을_계산한다():
    result = compare_with_peers(
        intake={"energy_kcal": 1000.0, "protein_g": 50.0},
        gender="M",
        age=35,
    )

    assert result["age_bracket"] == "30-39"
    assert result["sample_size"] > 0
    nutrients = {c["nutrient"]: c for c in result["comparisons"]}

    # 참조값이 바뀌어도 깨지지 않도록 "내 값/또래 평균"이라는 관계만 검증한다
    energy = nutrients["칼로리"]
    assert energy["percent_of_peer"] == round(1000.0 / energy["peer_mean"] * 100, 1)
    assert energy["percent_of_peer"] < 100  # 또래 평균보다 적게 먹은 경우


def test_넘기지_않은_영양소는_비교에서_빠진다():
    result = compare_with_peers(intake={"protein_g": 60.0}, gender="F", age=42)

    assert [c["nutrient"] for c in result["comparisons"]] == ["단백질"]


def test_참조_그룹이_없으면_비교를_건너뛴다():
    # 10세 미만은 이 서비스 대상이 아니라 참조 데이터에도 없다 - 죽지 않고 빈 비교를 돌려준다
    result = compare_with_peers(intake={"protein_g": 30.0}, gender="M", age=5)

    assert result["comparisons"] == []
    assert result["low_sample_warning"] is True


def test_엔드포인트가_또래_비교를_돌려준다():
    response = client.post(
        "/ai/nutrition/peer-compare",
        json={
            "gender": "M",
            "birth_year": 1995,
            "energy_kcal": 1850,
            "protein_g": 62,
            "carbs_g": 210,
            "fat_g": 55,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["age_bracket"] == "30-39"
    assert len(body["comparisons"]) == 4
    assert "국민건강통계" in body["source"]
    # 권장섭취량 대비 비율은 원 통계에 에너지·단백질만 있다
    assert body["peer_energy_ratio_pct"] is not None
    assert body["peer_protein_ratio_pct"] is not None


def test_성별은_M_또는_F만_받는다():
    response = client.post(
        "/ai/nutrition/peer-compare",
        json={"gender": "X", "birth_year": 1995, "protein_g": 60},
    )

    assert response.status_code == 422
