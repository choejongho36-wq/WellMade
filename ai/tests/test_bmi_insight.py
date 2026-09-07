"""BMI 또래 비교 + 비만도 분류 테스트 (app/insight/bmi_percentile.py + /ai/inbody/bmi-insight)."""

from fastapi.testclient import TestClient

from app.insight.bmi_percentile import classify_bmi, compute_bmi_insight, estimate_percentile
from app.main import app

client = TestClient(app)


def test_대한비만학회_기준으로_분류한다():
    assert classify_bmi(17.0) == "저체중"
    assert classify_bmi(18.5) == "정상"
    assert classify_bmi(22.9) == "정상"
    assert classify_bmi(23.0) == "비만 전단계(과체중)"
    assert classify_bmi(25.0) == "1단계 비만"
    assert classify_bmi(30.0) == "2단계 비만"
    assert classify_bmi(35.0) == "3단계 비만(고도비만)"


def test_공개된_백분위수_지점은_그대로_돌려준다():
    percentiles = {"5": 20.0, "50": 24.0, "95": 32.0}

    assert estimate_percentile(24.0, percentiles) == 50.0
    assert estimate_percentile(20.0, percentiles) == 5.0


def test_지점_사이는_선형보간한다():
    percentiles = {"25": 20.0, "75": 30.0}

    # 25%(20.0)와 75%(30.0)의 정중앙이므로 50%
    assert estimate_percentile(25.0, percentiles) == 50.0


def test_공개_구간_밖이면_백분위를_만들지_않는다():
    percentiles = {"5": 20.0, "95": 32.0}

    assert estimate_percentile(15.0, percentiles) is None
    assert estimate_percentile(40.0, percentiles) is None


def test_또래_비교와_분류를_함께_돌려준다():
    result = compute_bmi_insight(bmi=24.9, gender="M", age=35)

    assert result["category"] == "비만 전단계(과체중)"
    assert result["age_bracket"] == "30-39"
    assert result["peer_mean"] is not None
    assert 0 <= result["percentile"] <= 100


def test_참조_그룹이_없으면_분류만_한다():
    # 19세 미만은 성인 참조 데이터가 없다 - 비교는 생략하되 분류는 그대로 제공
    result = compute_bmi_insight(bmi=21.0, gender="F", age=15)

    assert result["category"] == "정상"
    assert result["percentile"] is None
    assert result["peer_mean"] is None


def test_엔드포인트가_인사이트를_돌려준다():
    response = client.post(
        "/ai/inbody/bmi-insight",
        json={"bmi": 26.4, "gender": "M", "birth_year": 1990},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["category"] == "1단계 비만"
    assert body["age_bracket"] == "30-39"
    assert "국민건강통계" in body["source"]


def test_음수_BMI는_거부한다():
    response = client.post(
        "/ai/inbody/bmi-insight",
        json={"bmi": -1, "gender": "M", "birth_year": 1990},
    )

    assert response.status_code == 422


def test_상식_범위를_벗어난_BMI는_엔드포인트가_거부한다():
    # 인바디 OCR이 소수점을 놓치거나(2.5) 자릿수를 잘못 읽으면(250) 그대로 분류돼버린다
    for bmi in (2.5, 250):
        response = client.post(
            "/ai/inbody/bmi-insight",
            json={"bmi": bmi, "gender": "M", "birth_year": 1990},
        )
        assert response.status_code == 422


def test_범위_밖_BMI는_분류도_비교도_하지_않는다():
    # 스키마를 거치지 않고 함수를 직접 부르는 경로(다른 서비스에서의 재사용)도 막는다
    result = compute_bmi_insight(bmi=2.5, gender="M", age=35)

    assert result["category"] == ""
    assert result["percentile"] is None
    assert "벗어나요" in result["warning"]


def test_키_체중으로_다시_계산한_BMI와_다르면_경고한다():
    # 175cm 70kg => 22.9. 기록된 26.4와 3.5 차이면 둘 중 하나가 틀린 것이다
    result = compute_bmi_insight(
        bmi=26.4, gender="M", age=35, height_cm=175, weight_kg=70
    )

    assert result["warning"] is not None
    assert "22.9" in result["warning"]
    # 어느 쪽이 맞는지 모르므로 값 자체는 고치지 않는다
    assert result["bmi"] == 26.4
    assert result["category"] == "1단계 비만"


def test_키_체중이_기록과_맞으면_경고하지_않는다():
    result = compute_bmi_insight(
        bmi=22.9, gender="M", age=35, height_cm=175, weight_kg=70
    )

    assert result["warning"] is None


def test_최신_기록_한_건에_대해서만_말한다():
    """추이를 덧붙이면 "지금 내가 어디쯤인가"라는 이 API의 답이 흐려진다."""
    result = compute_bmi_insight(bmi=24.0, gender="M", age=35)

    assert "trend" not in result
    assert result["message"].startswith("체질량지수 24.0")
    assert "지금은" not in result["message"]
