"""
각도 계산 Tool 단위 테스트.

MediaPipe 모델 파일 없이도 실행 가능해야 한다 (angles.py는 순수 함수).
"""

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.angles import (
    approximate_c7,
    calculate_forward_head,
    calculate_pelvis_tilt,
    calculate_shoulder_angle,
    calculate_shoulder_tilt,
)
from app.thresholds import (
    classify_forward_head,
    classify_pelvis_tilt,
    classify_round_shoulder,
    classify_shoulder_tilt,
)


def test_shoulder_tilt_level_is_zero():
    # 완전히 수평인 어깨: 왼쪽(0.3, 0.5), 오른쪽(0.7, 0.5)
    angle = calculate_shoulder_tilt((0.3, 0.5), (0.7, 0.5))
    assert angle == 0.0


def test_shoulder_tilt_left_lower_is_negative():
    # 왼쪽 어깨가 더 아래(y가 더 큼) -> 부호 규약상 음수
    angle = calculate_shoulder_tilt((0.3, 0.55), (0.7, 0.50))
    assert angle < 0


def test_shoulder_tilt_right_lower_is_positive():
    # 오른쪽 어깨가 더 아래(y가 더 큼) -> 부호 규약상 양수
    angle = calculate_shoulder_tilt((0.3, 0.50), (0.7, 0.55))
    assert angle > 0


def test_shoulder_tilt_45_degrees():
    # dx == dy 인 경우 45도가 나와야 함
    left = (0.0, 0.0)
    right = (1.0, 1.0)
    angle = calculate_shoulder_tilt(left, right)
    assert math.isclose(abs(angle), 45.0, abs_tol=1e-6)


def test_pelvis_tilt_same_formula_as_shoulder():
    assert calculate_pelvis_tilt((0.3, 0.5), (0.7, 0.5)) == 0.0
    assert calculate_pelvis_tilt((0.3, 0.6), (0.7, 0.5)) < 0  # 왼쪽이 더 아래 -> 음수


def test_forward_head_neutral_is_zero():
    # 귀가 어깨 바로 위(같은 x) -> 0도
    shoulder = (0.5, 0.6)
    ear = (0.5, 0.3)
    angle = calculate_forward_head(ear, shoulder)
    assert math.isclose(angle, 0.0, abs_tol=1e-6)


def test_forward_head_forward_is_nonzero():
    # 귀가 어깨보다 앞으로(x 오른쪽으로) 나가 있으면 0이 아니어야 함
    shoulder = (0.5, 0.6)
    ear = (0.6, 0.3)
    angle = calculate_forward_head(ear, shoulder)
    assert angle != 0.0


def test_calculate_shoulder_angle_returns_float():
    c7 = (0.5, 0.3)
    shoulder = (0.55, 0.31)
    angle = calculate_shoulder_angle(shoulder, c7)
    assert isinstance(angle, float)


def test_calculate_shoulder_angle_is_direction_invariant():
    # 회귀 방지(sample42.jpg 실측 검증 중 발견): 촬영 방향(좌/우 프로필)이
    # 바뀌어도 "얼마나 말렸는지"는 같아야 하므로, x축을 뒤집은 거울상
    # 좌표에서도 같은 각도가 나와야 한다. 예전 atan2 기반 공식은 이때
    # 부호가 뒤집혀 정상 자세를 "주의"로 오판하는 사고가 있었다.
    c7 = (0.5, 0.3)
    shoulder = (0.55, 0.31)
    mirrored_c7 = (-0.5, 0.3)
    mirrored_shoulder = (-0.55, 0.31)

    angle = calculate_shoulder_angle(shoulder, c7)
    mirrored_angle = calculate_shoulder_angle(mirrored_shoulder, mirrored_c7)
    assert angle == mirrored_angle


def test_calculate_shoulder_angle_always_between_0_and_90():
    # 다양한 부호 조합에서도 항상 0~90도 범위여야 한다 (더 이상
    # -180~180 범위로 튀지 않는다는 걸 잠그는 회귀 테스트).
    cases = [
        ((0.5, 0.3), (0.6, 0.35)),
        ((0.5, 0.3), (0.4, 0.35)),
        ((0.5, 0.3), (0.5, 0.35)),
        ((0.5, 0.35), (0.5, 0.30)),
    ]
    for shoulder, c7 in cases:
        angle = calculate_shoulder_angle(shoulder, c7)
        assert 0.0 <= angle <= 90.0, f"{shoulder=} {c7=} angle={angle}"


def test_calculate_shoulder_angle_matches_sample42_regression():
    # 실제로 겪은 회귀 케이스 고정: 종횡비 미보정 상태에서도 방향-무관
    # 공식은 -99.83도(버그)가 아니라 약 77.77도(정상 쪽)를 내야 한다.
    shoulder = (0.6397, 0.1766)
    c7 = (0.649015, 0.133623)  # approximate_c7(shoulder, hip)의 실측 결과값
    angle = calculate_shoulder_angle(shoulder, c7)
    assert math.isclose(angle, 77.77, abs_tol=0.5)


def test_approximate_c7_straight_trunk_extends_upward():
    # 몸통이 수직으로 곧게 펴져 있으면(골반 바로 위에 어깨), C7은 어깨보다
    # 더 위(y가 더 작음)에 와야 하고 x는 그대로여야 한다.
    hip = (0.5, 0.6)
    shoulder = (0.5, 0.3)
    c7 = approximate_c7(shoulder, hip)
    assert math.isclose(c7[0], 0.5, abs_tol=1e-9)
    assert c7[1] < shoulder[1]


def test_approximate_c7_ratio_scales_neck_length():
    hip = (0.5, 0.6)
    shoulder = (0.5, 0.3)  # 트렁크 길이 0.3
    c7 = approximate_c7(shoulder, hip, neck_ratio=0.2)
    # 0.2 * 0.3 = 0.06 만큼 어깨 위로 이동
    assert math.isclose(c7[1], 0.3 - 0.06, abs_tol=1e-9)


def test_approximate_c7_degenerate_trunk_returns_shoulder():
    # 골반-어깨 좌표가 사실상 겹치면(오검출) 어깨 좌표를 그대로 반환해
    # 0으로 나누기 등 예외가 나지 않아야 한다.
    hip = (0.5, 0.3)
    shoulder = (0.5, 0.3)
    c7 = approximate_c7(shoulder, hip)
    assert c7 == shoulder


def test_classify_shoulder_tilt_boundaries():
    assert classify_shoulder_tilt(0.0).verdict == "정상"
    assert classify_shoulder_tilt(5.0).verdict == "정상"
    assert classify_shoulder_tilt(5.01).verdict == "경미"
    assert classify_shoulder_tilt(15.0).verdict == "경미"
    assert classify_shoulder_tilt(15.01).verdict == "주의"
    # 음수(반대 방향 비대칭)도 절대값 기준으로 동일하게 판정
    assert classify_shoulder_tilt(-20.0).verdict == "주의"


def test_classify_pelvis_tilt_returns_note():
    result = classify_pelvis_tilt(3.0)
    assert result.verdict == "정상"
    assert "참고용" in result.note


def test_classify_forward_head_boundaries():
    assert classify_forward_head(0.0).verdict == "정상"
    assert classify_forward_head(15.0).verdict == "정상"
    assert classify_forward_head(15.01).verdict == "경미"
    assert classify_forward_head(25.0).verdict == "경미"
    assert classify_forward_head(25.01).verdict == "주의"
    assert classify_forward_head(-30.0).verdict == "주의"  # 절대값 기준


def test_classify_forward_head_returns_note():
    result = classify_forward_head(5.0)
    assert "임상 단일 기준" in result.note


def test_classify_round_shoulder_boundaries():
    assert classify_round_shoulder(52.0).verdict == "정상"
    assert classify_round_shoulder(60.0).verdict == "정상"
    assert classify_round_shoulder(51.99).verdict == "경미"
    assert classify_round_shoulder(45.0).verdict == "경미"  # 52 - 7 margin
    assert classify_round_shoulder(44.99).verdict == "주의"
    assert classify_round_shoulder(20.0).verdict == "주의"


def test_classify_round_shoulder_returns_c7_approximation_note():
    result = classify_round_shoulder(52.0)
    assert "C7" in result.note
    assert "근사" in result.note


def test_deterministic_same_input_same_output():
    # NFR-06 재현성: 같은 입력 -> 같은 출력
    a = calculate_shoulder_tilt((0.31, 0.512), (0.69, 0.498))
    b = calculate_shoulder_tilt((0.31, 0.512), (0.69, 0.498))
    assert a == b


def test_shoulder_tilt_mirrored_mediapipe_naming_stays_near_zero():
    # 회귀 테스트 (sample7 실사진에서 발견된 버그):
    # MediaPipe는 좌/우를 피사체 본인 기준으로 명명하므로, 카메라를 정면으로
    # 마주본 사람의 경우 화면상으로는 right_shoulder가 왼쪽(작은 x),
    # left_shoulder가 오른쪽(큰 x)에 찍힌다. 이 "정상적으로 잘 검출된" 상황에서
    # 어깨가 거의 수평이면 각도는 0에 가까워야 한다 (수정 전에는 ±180 근처로
    # 잘못 나왔었음).
    left_shoulder = (0.75, 0.23)   # 화면 오른쪽 (피사체 기준 왼쪽 어깨)
    right_shoulder = (0.42, 0.22)  # 화면 왼쪽 (피사체 기준 오른쪽 어깨)
    angle = calculate_shoulder_tilt(left_shoulder, right_shoulder)
    assert abs(angle) < 10  # 거의 수평이므로 큰 값이 나오면 안 됨


def test_shoulder_tilt_sign_correct_with_realistic_mirrored_coords():
    # 회귀 테스트 (sample27.jpg 실측 검증 중 발견된 버그, MVP1부터 있었음):
    # dx(=right.x - left.x)가 음수인 "일반적인 정면 사진" 상황에서, 예전
    # 코드(atan2 + ±180 wrap)는 dy의 부호와 반대로 lower_side를 판정했다.
    # sample27.jpg 실측: right_shoulder.y(0.2586) > left_shoulder.y(0.2382)
    # -> 오른쪽이 실제로 더 낮은데, 예전 코드는 "왼쪽이 낮다"(-6.95도)고
    # 오판했다. dx가 음수인 채로 dy 부호와 최종 각도 부호가 일치하는지
    # 명시적으로 고정한다.
    left_shoulder = (0.6425, 0.2382)
    right_shoulder = (0.3716, 0.2586)  # y가 더 큼 -> 오른쪽이 실제로 더 낮음
    angle = calculate_shoulder_tilt(left_shoulder, right_shoulder)
    assert angle > 0, "오른쪽이 더 낮으면 양수여야 한다 (실제로는 음수 버그가 있었음)"


def test_shoulder_tilt_sign_correct_when_left_lower_with_negative_dx():
    # 위 테스트의 대칭 케이스: dx가 음수인 채로 왼쪽이 더 낮은 경우도
    # 확인한다 (한쪽 방향만 우연히 맞는 것을 방지).
    left_shoulder = (0.65, 0.30)   # y가 더 큼 -> 왼쪽이 실제로 더 낮음
    right_shoulder = (0.40, 0.22)
    angle = calculate_shoulder_tilt(left_shoulder, right_shoulder)
    assert angle < 0, "왼쪽이 더 낮으면 음수여야 한다"


def test_shoulder_tilt_normalized_range():
    # 정규화 후에는 항상 -90 ~ 90도 범위 안에 있어야 한다 (선은 방향이 없으므로)
    import random

    random.seed(0)
    for _ in range(200):
        left = (random.uniform(0, 1), random.uniform(0, 1))
        right = (random.uniform(0, 1), random.uniform(0, 1))
        angle = calculate_shoulder_tilt(left, right)
        assert -90 <= angle <= 90
