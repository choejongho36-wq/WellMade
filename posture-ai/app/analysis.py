"""
정면/측면 정지 자세 분석 파이프라인 (좌표 입력).

posture-mvp의 app/analysis.py를 좌표 입력용으로 옮긴 것이다. 각도 계산과
3단계 판정은 **완전히 동일한 코드**(angles.py, thresholds.py)가 담당한다 —
입력 경로만 바뀌었을 뿐 판정 로직은 그대로다.

이미지 입력 버전과의 유일한 차이는 person_detection(세그멘테이션 교차검증)
이 빠진 것이다. evaluate_person_detection_strength가 원래부터
silhouette_check=None을 지원하도록 설계되어 있어 우회 없이 정식 경로로
"보통" 등급을 받는다. "보통"은 is_reliable을 떨어뜨리지 않으므로
(quality.assess_combined_reliability는 "약함"만 문제로 본다) 최종 판정
결과는 이미지 입력과 동일하다.

마네킹 방어는 유지된다 — 그건 세그멘테이션이 아니라
check_geometric_plausibility(어깨/골반 좌표가 겹쳐 찍히는 것)가 잡는다.
"""

from __future__ import annotations

from typing import Any

from .angles import (
    approximate_c7,
    calculate_forward_head,
    calculate_pelvis_tilt,
    calculate_shoulder_angle,
    calculate_shoulder_tilt,
)
from .keypoints import KeypointResult
from .quality import (
    assess_combined_reliability,
    check_geometric_plausibility,
    check_image_quality,
    determine_near_side,
    evaluate_person_detection_strength,
    keypoint_confidence_report,
)
from .thresholds import (
    classify_forward_head,
    classify_pelvis_tilt,
    classify_round_shoulder,
    classify_shoulder_tilt,
)

DISCLAIMER = "이 결과는 의료 진단이 아닌 참고용 정보이며, 진단·치료를 대체하지 않습니다."

RECAPTURE_TIPS = [
    "전신이 모두 나오도록 촬영해주세요.",
    "밝은 곳에서 배경이 단순한 벽 앞에 서주세요.",
    "카메라를 몸 높이에 맞추고 정면(또는 옆)을 향해 서주세요.",
    "몸에 딱 붙지 않는 헐렁한 옷은 관절 위치 인식을 어렵게 합니다.",
]


def _base_result(result: KeypointResult) -> tuple[dict[str, Any], bool]:
    """
    front/side 공통 검증을 수행하고 응답 뼈대를 만든다.

    Returns:
        (응답 dict, reliability.is_reliable)
    """
    quality = check_image_quality(result)
    geometry = check_geometric_plausibility(result)

    # silhouette_check=None — 좌표 입력이라 이미지 기반 교차검증이 불가능하다.
    # 이 경로는 원래부터 지원되는 정식 분기다(모듈 docstring 참고).
    person_strength = evaluate_person_detection_strength(
        pose_detected=bool(result.keypoints),
        silhouette_check=None,
        pose_points_xy=result.interest_point_coords(),
    )
    reliability = assess_combined_reliability(person_strength, geometry)

    return (
        {
            "success": True,
            "quality": {"is_valid": quality.is_valid, "issue": quality.issue},
            "reliability": {
                "is_reliable": reliability.is_reliable,
                "issues": reliability.issues,
            },
            "confidence": round(result.confidence, 4),
            "disclaimer": DISCLAIMER,
        },
        reliability.is_reliable,
    )


def _confidence_report(result: KeypointResult, is_reliable: bool, names=None) -> list[dict]:
    """
    신뢰할 수 없는 결과에는 관절별 신뢰도를 내지 않는다 — 믿을 수 없는
    좌표의 신뢰도 수치는 오히려 오해를 부른다(posture-mvp와 동일 동작).
    """
    if not is_reliable:
        return []
    report = keypoint_confidence_report(result, names=names) if names else keypoint_confidence_report(result)
    return [
        {"name": item.name, "visibility": round(item.visibility, 4), "band": item.band}
        for item in report
    ]


def analyze_front(result: KeypointResult) -> dict[str, Any]:
    """
    정면 좌표에서 어깨/골반 좌우 기울기를 계산하고 3단계 판정한다.

    pixel_xy() 사용 이유: 정규화 좌표를 그대로 쓰면 이미지가 정사각형이
    아닐 때 각도가 왜곡된다(keypoints.pixel_xy 참고).
    """
    out, is_reliable = _base_result(result)

    shoulder_angle = calculate_shoulder_tilt(
        result.pixel_xy("left_shoulder"), result.pixel_xy("right_shoulder")
    )
    pelvis_angle = calculate_pelvis_tilt(
        result.pixel_xy("left_hip"), result.pixel_xy("right_hip")
    )
    shoulder_verdict = classify_shoulder_tilt(shoulder_angle)
    pelvis_verdict = classify_pelvis_tilt(pelvis_angle)

    out.update({
        "view": "front",
        "keypoint_confidence": _confidence_report(result, is_reliable),
        "shoulder": {
            "angle_deg": shoulder_angle,
            "verdict": shoulder_verdict.verdict,
        },
        "pelvis": {
            "angle_deg": pelvis_angle,
            "verdict": pelvis_verdict.verdict,
            "note": pelvis_verdict.note,
        },
    })
    return out


def _best_effort_near_side(result: KeypointResult) -> str:
    """
    각도 계산용 근접 측을 결정한다(품질 게이트용 determine_near_side와는
    목적이 다르다).

    신뢰도와 무관하게 항상 결정론적인 숫자를 내야 하므로, 엄격 기준
    (MIN_Z_SEPARATION)을 통과하지 못해도 최선의 추정으로 한쪽을 고른다.
    값을 신뢰할지 여부는 이 함수가 아니라 reliability 필드가 책임진다.
    """
    try:
        left_ear = result.get("left_ear")
        right_ear = result.get("right_ear")
    except KeyError:
        return "left"
    # z가 작을수록 카메라에 가깝다
    return "left" if left_ear.z <= right_ear.z else "right"


def analyze_side(result: KeypointResult) -> dict[str, Any]:
    """
    측면 좌표에서 전방머리자세/라운드숄더 각도를 계산하고 3단계 판정한다.

    round_shoulder의 C7은 approximate_c7()로 근사한 값이라 구조적 한계가
    있다 — 자세한 내용은 classify_round_shoulder의 note와 프로젝트 문서
    참고. 그 한계는 판정 note와 코멘트 문구에 반영된다.
    """
    out, is_reliable = _base_result(result)

    near = determine_near_side(result)
    near_side = _best_effort_near_side(result)

    ear_xy = result.pixel_xy(f"{near_side}_ear")
    shoulder_xy = result.pixel_xy(f"{near_side}_shoulder")
    hip_xy = result.pixel_xy(f"{near_side}_hip")
    c7_xy = approximate_c7(shoulder_xy, hip_xy)

    forward_head_angle = calculate_forward_head(ear_xy, shoulder_xy)
    round_shoulder_angle = calculate_shoulder_angle(shoulder_xy, c7_xy)
    forward_head_verdict = classify_forward_head(forward_head_angle)
    round_shoulder_verdict = classify_round_shoulder(round_shoulder_angle)

    names = [f"{near_side}_ear", f"{near_side}_shoulder", f"{near_side}_hip"]
    out.update({
        "view": "side",
        "near_side": near_side,
        "near_side_determined": near.side is not None,
        "keypoint_confidence": _confidence_report(result, is_reliable, names=names),
        "forward_head": {
            "angle_deg": forward_head_angle,
            "verdict": forward_head_verdict.verdict,
            "note": forward_head_verdict.note,
        },
        "round_shoulder": {
            "angle_deg": round_shoulder_angle,
            "verdict": round_shoulder_verdict.verdict,
            "note": round_shoulder_verdict.note,
        },
    })
    return out
