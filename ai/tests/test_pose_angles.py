"""정면 좌우 기울기 각도 계산 (app/pose/angles.py).

MediaPipe가 좌/우를 피사체 본인 기준으로 명명하기 때문에, 정면 촬영에서는
dx = right.x - left.x 가 항상 음수가 된다. 이 성질 때문에 생겼던 부호 버그를
막는 회귀 테스트다 (재현: tests/repro_tilt_sign_bug.py).
"""

import pytest

from app.pose.angles import get_pelvis_tilt_angle, get_shoulder_tilt_angle
from app.schemas import Landmark

LEFT_SHOULDER = 11
RIGHT_SHOULDER = 12
LEFT_HIP = 23
RIGHT_HIP = 24


def _landmarks(**overrides) -> list[Landmark]:
    """33개 랜드마크를 만들고, 지정한 인덱스만 덮어쓴다."""
    lms = [Landmark(x=0.5, y=0.5) for _ in range(33)]
    for index, (x, y) in overrides.items():
        lms[int(index)] = Landmark(x=x, y=y)
    return lms


def test_정면_촬영에서_오른쪽_어깨가_낮으면_양수가_나온다():
    """MediaPipe 실측 좌표. right.y(0.2586) > left.y(0.2382) 이므로 오른쪽이 더
    아래 = 왼쪽이 올라감 = docstring 규약상 양수여야 한다.

    수정 전에는 +175.69도가 나왔다 — 부호는 양수지만 범위를 완전히 벗어나
    posture_percentile의 참조 분포(0~13도) 비교가 무의미해졌다."""
    lms = _landmarks(**{
        str(LEFT_SHOULDER): (0.6425, 0.2382),
        str(RIGHT_SHOULDER): (0.3716, 0.2586),
    })

    angle = get_shoulder_tilt_angle(lms)

    assert angle > 0
    assert angle == pytest.approx(4.31, abs=0.1)


def test_정면_촬영에서_왼쪽_어깨가_낮으면_음수가_나온다():
    """반대 케이스. 한쪽 방향만 우연히 맞는 것을 방지한다."""
    lms = _landmarks(**{
        str(LEFT_SHOULDER): (0.6500, 0.3000),
        str(RIGHT_SHOULDER): (0.4000, 0.2200),
    })

    angle = get_shoulder_tilt_angle(lms)

    assert angle < 0
    assert angle == pytest.approx(-17.74, abs=0.1)


def test_기울기_각도는_항상_마이너스90도에서_90도_사이다():
    """수평선 대비 기울기이므로 이 범위를 벗어날 수 없다. 벗어나면 참조 분포
    (0~13도)와 비교하는 posture_percentile이 항상 최상단에 걸린다."""
    cases = [
        ((0.6425, 0.2382), (0.3716, 0.2586)),
        ((0.6500, 0.3000), (0.4000, 0.2200)),
        ((0.7500, 0.2300), (0.4200, 0.2200)),
        ((0.5100, 0.2000), (0.4900, 0.4000)),  # 좌우 거리가 아주 좁은 경우
    ]
    for left, right in cases:
        lms = _landmarks(**{str(LEFT_SHOULDER): left, str(RIGHT_SHOULDER): right})
        angle = get_shoulder_tilt_angle(lms)
        assert -90 <= angle <= 90, f"{left} {right} -> {angle}"


def test_좌우가_완전히_수평이면_0도다():
    lms = _landmarks(**{
        str(LEFT_SHOULDER): (0.6500, 0.2400),
        str(RIGHT_SHOULDER): (0.3500, 0.2400),
    })

    assert get_shoulder_tilt_angle(lms) == pytest.approx(0.0, abs=1e-9)


def test_골반도_어깨와_같은_부호_규약을_따른다():
    lms = _landmarks(**{
        str(LEFT_HIP): (0.5689, 0.4797),
        str(RIGHT_HIP): (0.4253, 0.4779),
    })

    angle = get_pelvis_tilt_angle(lms)

    # right.y(0.4779) < left.y(0.4797) -> 오른쪽이 더 위 = 음수
    assert angle < 0
    assert -90 <= angle <= 90


def test_거울상_좌표는_부호만_뒤집히고_크기는_같다():
    """촬영 방향이 바뀌어도(x축 반전) 기울기의 크기는 같아야 한다."""
    normal = _landmarks(**{
        str(LEFT_SHOULDER): (0.6425, 0.2382),
        str(RIGHT_SHOULDER): (0.3716, 0.2586),
    })
    mirrored = _landmarks(**{
        str(LEFT_SHOULDER): (1 - 0.6425, 0.2382),
        str(RIGHT_SHOULDER): (1 - 0.3716, 0.2586),
    })

    assert abs(get_shoulder_tilt_angle(normal)) == pytest.approx(
        abs(get_shoulder_tilt_angle(mirrored)), abs=1e-9
    )


def test_두_점이_완전히_겹치면_0도를_반환한다():
    """오검출 방어. ZeroDivision이나 예외 없이 0이 나와야 한다."""
    lms = _landmarks(**{
        str(LEFT_SHOULDER): (0.5, 0.5),
        str(RIGHT_SHOULDER): (0.5, 0.5),
    })

    assert get_shoulder_tilt_angle(lms) == 0.0
