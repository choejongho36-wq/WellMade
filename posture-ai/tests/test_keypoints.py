"""
KeypointResult.pixel_xy() 단위 테스트 — 종횡비 보정 검증.

720x900(세로가 긴) 사진에서 x/y 정규화 좌표를 그대로 각도 공식에 넣으면
각도가 왜곡된다는 걸 sample42.jpg 실측으로 확인했다(대화 로그 참고).
pixel_xy()가 이 왜곡을 없애는지 여기서 고정 회귀 테스트로 잠근다.
"""

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.angles import calculate_forward_head
from app.keypoints import keypoints_from_raw


def test_pixel_xy_defaults_to_normalized_when_size_not_given():
    # image_width/height를 안 주면(기본 1x1) pixel_xy()는 xy()와 동일해야
    # 한다 — 기존 테스트/코드가 이 메서드 도입 전과 동일하게 동작해야 함.
    raw = {"left_ear": (0.3, 0.4, 0.0, 0.9)}
    result = keypoints_from_raw(raw, view="side")
    kp = result.get("left_ear")
    assert result.pixel_xy("left_ear") == kp.xy()


def test_pixel_xy_scales_by_image_dimensions():
    raw = {"left_ear": (0.5, 0.25, 0.0, 0.9)}
    result = keypoints_from_raw(raw, view="side", image_width=720, image_height=900)
    x, y = result.pixel_xy("left_ear")
    assert math.isclose(x, 0.5 * 720)
    assert math.isclose(y, 0.25 * 900)


def test_aspect_ratio_distortion_changes_angle_without_pixel_xy():
    # 회귀 방지용: 정사각형이 아닌 이미지에서 정규화 좌표를 그대로 쓰면
    # (보정 없이 xy()로) 각도가 픽셀 보정 각도와 달라져야 한다 — 즉 이
    # 왜곡이 실제로 존재함을 보여주는 대조군 테스트.
    raw = {
        "left_ear": (0.5547, 0.0924, 0.0, 0.9),
        "left_shoulder": (0.6397, 0.1766, 0.0, 0.9),
    }
    result = keypoints_from_raw(raw, view="side", image_width=720, image_height=900)

    ear_norm = result.get("left_ear").xy()
    shoulder_norm = result.get("left_shoulder").xy()
    angle_distorted = calculate_forward_head(ear_norm, shoulder_norm)

    ear_px = result.pixel_xy("left_ear")
    shoulder_px = result.pixel_xy("left_shoulder")
    angle_corrected = calculate_forward_head(ear_px, shoulder_px)

    # sample42.jpg 실측에서 약 6도 차이가 났었다 — 부호/방향은 케이스마다
    # 다를 수 있으니 "달라진다"만 확인하고 정확한 크기는 강제하지 않는다.
    assert not math.isclose(angle_distorted, angle_corrected, abs_tol=1.0)


def test_pixel_xy_missing_keypoint_raises():
    result = keypoints_from_raw({}, view="side", image_width=720, image_height=900)
    try:
        result.pixel_xy("left_ear")
        assert False, "KeyError가 발생해야 함"
    except KeyError:
        pass
