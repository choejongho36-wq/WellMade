"""또래 비교에 쓰는 나이 계산 (app/insight/age.py)."""

from datetime import date

from app.insight.age import resolve_age


def test_생년만_있으면_연_나이를_쓰고_정확하지_않다고_알린다():
    # 1990년생, 아직 생일 전(3월 1일 기준) - 만 나이는 35세지만 연 나이는 36세다
    age, exact = resolve_age(1990, today=date(2026, 3, 1))

    assert age == 36
    assert exact is False


def test_생년월일이_있으면_정확한_만_나이를_쓴다():
    before_birthday = resolve_age(1990, birth_date=date(1990, 7, 20), today=date(2026, 3, 1))
    after_birthday = resolve_age(1990, birth_date=date(1990, 7, 20), today=date(2026, 8, 1))

    assert before_birthday == (35, True)
    assert after_birthday == (36, True)


def test_생일_당일은_한_살_올라간다():
    assert resolve_age(1990, birth_date=date(1990, 7, 20), today=date(2026, 7, 20)) == (36, True)


def test_연_나이와_만_나이가_구간_경계에서_그룹을_바꿀_수_있다():
    """29/30 경계 - 이 1살 차이로 비교 대상 통계 그룹 자체가 달라진다."""
    from app.insight.nutrition_peer import to_age_bracket

    year_age, _ = resolve_age(1996, today=date(2026, 3, 1))
    korean_age, _ = resolve_age(1996, birth_date=date(1996, 7, 20), today=date(2026, 3, 1))

    assert to_age_bracket(year_age) == "30-39"
    assert to_age_bracket(korean_age) == "19-29"
