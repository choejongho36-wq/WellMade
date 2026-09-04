"""
또래 비교에 쓰는 나이 계산.

국민건강통계의 연령 구간은 **만 나이** 기준인데, 우리 프로필은 생년(birth_year)만 받는다.
`오늘.year - 생년`은 만 나이가 아니라 **연 나이**라, 생일이 아직 안 지난 사람은 실제보다
한 살 많게 계산된다. 구간 경계(18/19, 29/30, 69/70)에서는 이 1살 차이로 비교 그룹 자체가
바뀌므로, 어림값이라는 사실을 숨기지 않고 한곳에 모아둔다.

생년월일(birth_date)을 받을 수 있으면 정확한 만 나이를 쓴다 - 지금은 프로필에 없지만,
넣기만 하면 이 함수에 넘기는 것만으로 오차가 사라지도록 통로를 열어둔다.
"""

from datetime import date
from typing import Optional


def resolve_age(
    birth_year: int,
    birth_date: Optional[date] = None,
    today: Optional[date] = None,
) -> tuple[int, bool]:
    """
    :return: (나이, 만 나이가 정확한가)
             birth_date가 있으면 (만 나이, True), 없으면 (연 나이, False).
             연 나이는 만 나이보다 0~1살 많다.
    """
    today = today or date.today()
    if birth_date is not None:
        had_birthday = (today.month, today.day) >= (birth_date.month, birth_date.day)
        return today.year - birth_date.year - (0 if had_birthday else 1), True
    return today.year - birth_year, False
