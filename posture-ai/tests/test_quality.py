import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.keypoints import keypoints_from_raw
from app.quality import (
    check_geometric_plausibility,
    check_image_quality,
    determine_near_side,
)


def _good_side_raw(near="left"):
    """
    잘 찍힌 측면 사진 합성 좌표. near는 카메라에 가까운 쪽.
    근접 측: visibility 높음 + z 작음(가까움). 먼 측: visibility 낮음(가려짐) + z 큼.
    """
    far = "right" if near == "left" else "left"
    return {
        f"{near}_ear": (0.5, 0.20, -0.10, 0.9),
        f"{far}_ear": (0.51, 0.205, 0.05, 0.3),  # 가려짐 -> visibility 낮음(정상)
        f"{near}_shoulder": (0.5, 0.35, -0.08, 0.92),
        f"{far}_shoulder": (0.505, 0.352, 0.04, 0.6),
        f"{near}_hip": (0.49, 0.60, -0.07, 0.9),
        f"{far}_hip": (0.495, 0.602, 0.03, 0.55),
    }


def _good_front_raw():
    return {
        "left_shoulder": (0.3, 0.5, 0.0, 0.95),
        "right_shoulder": (0.7, 0.5, 0.0, 0.93),
        "left_hip": (0.32, 0.8, 0.0, 0.9),
        "right_hip": (0.68, 0.8, 0.0, 0.91),
    }


def test_valid_front_image_passes():
    result = keypoints_from_raw(_good_front_raw(), view="front")
    q = check_image_quality(result)
    assert q.is_valid is True
    assert q.issue == ""


def test_missing_keypoint_fails():
    raw = _good_front_raw()
    del raw["right_hip"]
    result = keypoints_from_raw(raw, view="front")
    q = check_image_quality(result)
    assert q.is_valid is False
    assert "missing_keypoints" in q.issue


def test_low_visibility_fails():
    raw = _good_front_raw()
    raw["left_shoulder"] = (0.3, 0.5, 0.0, 0.2)  # NFR-01: 0.5 미만
    result = keypoints_from_raw(raw, view="front")
    q = check_image_quality(result)
    assert q.is_valid is False
    assert "low_visibility" in q.issue


def test_no_person_detected():
    result = keypoints_from_raw({}, view="front")
    q = check_image_quality(result)
    assert q.is_valid is False
    assert q.issue == "no_person_detected"


def test_geometric_check_catches_overlapping_points_despite_high_confidence():
    # 회귀 테스트 (sample6 마네킹): visibility는 높아도(>=0.5) 좌우 점이
    # 사실상 겹쳐 찍히면(예: 마네킹, 오검출) 기하학적 검사로 걸러져야 한다.
    raw = {
        "left_shoulder": (0.495, 0.19, 0.0, 0.9),
        "right_shoulder": (0.49, 0.192, 0.0, 0.88),  # 사실상 같은 위치
        "left_hip": (0.5, 0.45, 0.0, 0.85),
        "right_hip": (0.502, 0.451, 0.0, 0.83),  # 사실상 같은 위치
    }
    result = keypoints_from_raw(raw, view="front")
    assert result.confidence >= 0.5  # 신뢰도 자체는 높음(문제의 핵심)
    q = check_image_quality(result)
    assert q.is_valid is False
    assert "overlapping" in q.issue


def test_geometric_check_catches_unusual_shoulder_hip_ratio():
    # 회귀 테스트 (sample11 롱패딩): 옷 때문에 어깨는 과도하게 넓고
    # 골반은 좁게 잡히는 비인체적 비율을 감지해야 한다.
    raw = {
        "left_shoulder": (0.75, 0.2, 0.0, 0.9),
        "right_shoulder": (0.15, 0.2, 0.0, 0.9),  # 너비 0.6
        "left_hip": (0.55, 0.5, 0.0, 0.9),
        "right_hip": (0.45, 0.5, 0.0, 0.9),  # 너비 0.1
    }
    result = keypoints_from_raw(raw, view="front")
    q = check_image_quality(result)
    assert q.is_valid is False
    assert "ratio_unusual" in q.issue


def test_geometric_check_passes_normal_human_proportions():
    # 정상적인 사람 비율에서는 오탐(false positive)이 없어야 한다.
    raw = {
        "left_shoulder": (0.65, 0.22, 0.0, 0.9),
        "right_shoulder": (0.35, 0.22, 0.0, 0.9),  # 너비 0.3
        "left_hip": (0.58, 0.47, 0.0, 0.9),
        "right_hip": (0.4, 0.47, 0.0, 0.9),  # 너비 0.18
    }
    result = keypoints_from_raw(raw, view="front")
    q = check_image_quality(result)
    assert q.is_valid is True
    assert q.issue == ""


def test_geometric_check_overlapping_does_not_also_report_ratio():
    # 회귀 테스트: 좌우 점이 겹쳐서(overlapping) 나온 경우, 그로 인해
    # 분모가 0에 가까워져 파생되는 shoulder_hip_ratio_unusual까지 같이
    # 뜨면 같은 근본 원인이 두 개의 별개 사유처럼 보여 혼란을 준다.
    # 겹침이 이미 잡혔으면 비율 검사는 건너뛰어야 한다.
    raw = {
        "left_shoulder": (0.48, 0.19, 0.0, 1.0),
        "right_shoulder": (0.44, 0.192, 0.0, 1.0),
        "left_hip": (0.5, 0.45, 0.0, 1.0),
        "right_hip": (0.5036, 0.451, 0.0, 0.999),  # 거의 겹침
    }
    result = keypoints_from_raw(raw, view="front")
    q = check_image_quality(result)
    assert q.is_valid is False
    assert "hip_points_overlapping" in q.issue
    assert "ratio_unusual" not in q.issue  # 파생 사유는 표시하지 않음


def test_confidence_report_distinguishes_medium_from_high():
    # 핵심 요구사항: 0.5 이진 통과 여부만 보여주면 0.51과 0.95가 똑같이
    # "정상"으로 보인다. keypoint_confidence_report는 등급을 나눠서
    # 둘을 구분해서 보여줘야 한다.
    from app.quality import (
        CONFIDENCE_BAND_HIGH,
        CONFIDENCE_BAND_MEDIUM,
        keypoint_confidence_report,
    )

    raw = _good_front_raw()
    raw["left_ear"] = (0.5, 0.1, 0.0, 0.51)  # 발라클라바 모자 위 -> 턱걸이 통과
    raw["right_ear"] = (0.5, 0.1, 0.0, 0.92)  # 실제 사람 -> 확실
    result = keypoints_from_raw(raw, view="front")

    report = {item.name: item for item in keypoint_confidence_report(result, names=["left_ear", "right_ear"])}
    assert report["left_ear"].band == CONFIDENCE_BAND_MEDIUM
    assert report["right_ear"].band == CONFIDENCE_BAND_HIGH
    # 둘 다 0.5 기준은 넘었지만(=기존 이진 검사로는 똑같이 "통과") 등급은 달라야 함
    assert report["left_ear"].visibility >= 0.5
    assert report["right_ear"].visibility >= 0.5
    assert report["left_ear"].band != report["right_ear"].band


def test_confidence_report_low_band_below_threshold():
    from app.quality import CONFIDENCE_BAND_LOW, keypoint_confidence_report

    raw = _good_front_raw()
    raw["left_ear"] = (0.5, 0.1, 0.0, 0.3)
    result = keypoints_from_raw(raw, view="front")
    report = {item.name: item for item in keypoint_confidence_report(result, names=["left_ear"])}
    assert report["left_ear"].band == CONFIDENCE_BAND_LOW


def test_confidence_report_missing_point_is_low_band_zero():
    from app.quality import CONFIDENCE_BAND_LOW, keypoint_confidence_report

    raw = _good_front_raw()  # 귀 데이터 자체가 없음
    result = keypoints_from_raw(raw, view="front")
    report = {item.name: item for item in keypoint_confidence_report(result, names=["left_ear"])}
    assert report["left_ear"].visibility == 0.0
    assert report["left_ear"].band == CONFIDENCE_BAND_LOW


def test_combined_reliability_catches_mannequin_without_segmentation():
    # 핵심 회귀 테스트 (좌표 입력 버전):
    # posture-ai는 이미지를 받지 않으므로 세그멘테이션 교차검증을 쓸 수
    # 없다. 그래도 마네킹은 여전히 걸러져야 한다 — 마네킹을 실제로 잡는
    # 건 세그멘테이션이 아니라 좌표 자체의 기하학적 타당성(어깨/골반이
    # 서로 거의 겹쳐 찍힘)이기 때문이다.
    #
    # 이미지 입력 버전(posture-mvp)의 ReliabilityAssessment docstring에도
    # 같은 내용이 있다: "마네킹: person_detection은 '강함'이지만
    # check_geometric_plausibility는 실패함" — 세그멘테이션은 원래부터
    # 마네킹을 못 잡았다.
    from app.quality import assess_combined_reliability, evaluate_person_detection_strength

    raw = {
        "left_shoulder": (0.495, 0.20, 0.0, 1.0),
        "right_shoulder": (0.49, 0.202, 0.0, 1.0),  # 어깨 좌우가 거의 겹침
        "left_hip": (0.5, 0.45, 0.0, 1.0),
        "right_hip": (0.502, 0.451, 0.0, 1.0),      # 골반도 겹침
    }
    result = keypoints_from_raw(raw, view="front")

    # 좌표 입력이므로 silhouette_check=None -> "보통" 등급
    person_strength = evaluate_person_detection_strength(
        pose_detected=True, silhouette_check=None,
        pose_points_xy=result.interest_point_coords(),
    )
    assert person_strength.level == "보통"

    geometry = check_geometric_plausibility(result)
    assert geometry.is_valid is False  # 기하학적 검사가 잡는다

    combined = assess_combined_reliability(person_strength, geometry)
    assert combined.is_reliable is False, "세그멘테이션 없이도 마네킹은 걸러져야 한다"
    assert any("overlapping" in issue for issue in combined.issues)


def test_determine_near_side_picks_higher_visibility():
    raw = _good_side_raw(near="left")
    result = keypoints_from_raw(raw, view="side")
    near = determine_near_side(result)
    assert near.side == "left"
    assert near.detail == ""


def test_determine_near_side_right():
    raw = _good_side_raw(near="right")
    result = keypoints_from_raw(raw, view="side")
    near = determine_near_side(result)
    assert near.side == "right"


def test_determine_near_side_undetermined_when_z_gap_too_small():
    # 실제 MediaPipe 출력에서는 visibility 차이가 사실상 0에 가까운 게
    # 정상이라(sample41/42.jpg 실측), 지금은 z 차이만으로 판정한다.
    # z 차이가 작으면(카메라를 향해 몸을 충분히 안 튼 경우) 판정 보류.
    raw = _good_side_raw(near="left")
    raw["right_ear"] = (0.51, 0.205, -0.09, 0.3)  # z를 근접 측과 거의 같게
    result = keypoints_from_raw(raw, view="side")
    near = determine_near_side(result)
    assert near.side is None
    assert "z_gap_too_small" in near.detail


def test_determine_near_side_ignores_visibility_when_z_is_clear():
    # visibility가 거의 같아도(실측에서 흔한 패턴) z 차이가 뚜렷하면
    # 판정해야 한다 — visibility는 더 이상 게이트가 아니다.
    raw = _good_side_raw(near="left")
    raw["right_ear"] = (0.51, 0.205, 0.05, 0.89)  # 왼쪽(0.9)과 visibility 거의 동일
    result = keypoints_from_raw(raw, view="side")
    near = determine_near_side(result)
    assert near.side == "left"


def test_determine_near_side_z_decides_even_if_visibility_disagrees():
    # z가 유일한 판정 신호이므로, visibility가 반대를 가리켜도 z를 따른다.
    raw = _good_side_raw(near="left")
    raw["left_ear"] = (0.5, 0.20, 0.05, 0.9)   # z는 먼 쪽인데 visibility는 높음
    raw["right_ear"] = (0.51, 0.205, -0.10, 0.3)  # z는 가까운 쪽인데 visibility는 낮음
    result = keypoints_from_raw(raw, view="side")
    near = determine_near_side(result)
    assert near.side == "right"  # z 기준으로 오른쪽이 근접 측


def test_side_geometric_check_passes_realistic_side_photo():
    raw = _good_side_raw(near="left")
    result = keypoints_from_raw(raw, view="side")
    geometry = check_geometric_plausibility(result)
    assert geometry.is_valid is True


def test_side_geometric_check_flags_front_photo_mislabeled_as_side():
    # 회귀 대상 시나리오(MVP3_착수정리 §3-A): 실제로는 정면 사진인데
    # view="side"로 잘못 올라온 경우, 좌우 어깨가 뚜렷이 벌어져 있으므로
    # "측면치고 이상하다"로 잡아내야 한다.
    raw = {
        "left_ear": (0.7, 0.10, 0.0, 0.9),
        "right_ear": (0.3, 0.10, 0.0, 0.88),
        "left_shoulder": (0.65, 0.22, 0.0, 0.9),
        "right_shoulder": (0.35, 0.22, 0.0, 0.9),
        "left_hip": (0.58, 0.47, 0.0, 0.9),
        "right_hip": (0.4, 0.47, 0.0, 0.9),
    }
    result = keypoints_from_raw(raw, view="side")
    geometry = check_geometric_plausibility(result)
    assert geometry.is_valid is False
    assert "not_a_side_profile:shoulder_x_gap" in geometry.issue


def test_side_geometric_check_flags_no_depth_separation():
    # z 차이가 거의 없으면(카메라를 향해 몸을 안 튼 경우) 의심해야 한다.
    raw = _good_side_raw(near="left")
    raw["right_ear"] = (0.51, 0.205, -0.09, 0.3)  # z를 근접 측과 거의 같게
    result = keypoints_from_raw(raw, view="side")
    geometry = check_geometric_plausibility(result)
    assert geometry.is_valid is False
    assert "z_separation" in geometry.issue


def test_side_geometric_check_flags_neck_too_short():
    raw = _good_side_raw(near="left")
    raw["left_ear"] = (0.5, 0.351, -0.10, 0.9)  # 귀가 어깨 바로 옆(수직거리 0에 가까움)
    result = keypoints_from_raw(raw, view="side")
    geometry = check_geometric_plausibility(result)
    assert geometry.is_valid is False
    assert "neck_too_short" in geometry.issue


def test_side_image_quality_passes_with_only_near_side_visible():
    # 핵심 회귀 테스트(MVP3_착수정리 §3-B): 먼 쪽 귀 visibility가 낮아도
    # (실제 측면 사진에서 정상적인 현상) 전체 품질 검사는 통과해야 한다.
    raw = _good_side_raw(near="left")
    result = keypoints_from_raw(raw, view="side")
    q = check_image_quality(result)
    assert q.is_valid is True
    assert q.issue == ""


def test_side_image_quality_fails_when_near_side_itself_low_visibility():
    raw = _good_side_raw(near="left")
    raw["left_shoulder"] = (0.5, 0.35, -0.08, 0.3)  # 근접 측인데도 낮음
    result = keypoints_from_raw(raw, view="side")
    q = check_image_quality(result)
    assert q.is_valid is False
    assert "low_visibility" in q.issue


def test_combined_reliability_passes_normal_photo_without_segmentation():
    # 좌표 입력에서 정상 사진은 그대로 통과해야 한다. person_detection이
    # "보통"이어도 is_reliable에는 영향이 없다 — assess_combined_reliability는
    # "약함"만 문제로 보기 때문이다.
    from app.quality import assess_combined_reliability, evaluate_person_detection_strength

    raw = {
        "left_shoulder": (0.35, 0.22, 0.0, 1.0),
        "right_shoulder": (0.65, 0.22, 0.0, 1.0),
        "left_hip": (0.35, 0.42, 0.0, 1.0),
        "right_hip": (0.65, 0.42, 0.0, 1.0),
    }
    result = keypoints_from_raw(raw, view="front")
    person_strength = evaluate_person_detection_strength(
        pose_detected=True, silhouette_check=None,
        pose_points_xy=result.interest_point_coords(),
    )
    geometry = check_geometric_plausibility(result)

    combined = assess_combined_reliability(person_strength, geometry)
    assert combined.is_reliable is True
    assert combined.issues == []
