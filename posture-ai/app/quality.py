"""
check_image_quality Tool 구현체.

요구사항정의서:
    FR-03  이미지 품질 검증 — 키포인트 신뢰도가 낮거나 주요 관절이
           가려진 경우 이를 감지한다.
    NFR-01 MediaPipe 키포인트 검출 신뢰도(confidence) 0.5 미만 시
           결과를 신뢰 불가로 표시한다.

MVP1 범위에서는 LLM 에이전트가 아니라 if문 기반으로 판정한다
(로드맵 4장: "MVP1 ... if문 기반 3단계 판정").

중요한 한계: MediaPipe의 visibility 점수는 "이 관절이 가려지지 않고
보이는가"에 대한 모델의 확신도이지, "찍힌 좌표가 실제로 정확한가"를
보장하지 않는다. 마네킹이나 두꺼운 옷 위에도 모델은 그럴듯한 위치에
점을 찍고 0.5 이상의 visibility를 줄 수 있다(실사용 검증에서 확인됨).
그래서 신뢰도 검사만으로는 부족하며, check_geometric_plausibility()로
좌표 자체가 인체적으로 말이 되는지를 별도로 확인한다.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .keypoints import KeypointResult, View

CONFIDENCE_THRESHOLD = 0.5  # NFR-01

# 신뢰도를 "통과/실패" 이진 판정만으로 보여주면, 0.51과 0.95가 사용자 눈에
# 똑같이 "정상"으로 보여서 오히려 혼동을 준다(실사용 검증에서 확인됨:
# 발라클라바 모자 위 귀 0.5대와 실제 사람 사진 귀 0.85+가 똑같이 표시됨).
# 그래서 등급을 하나 더 나눠, 기준선 근처(보통)와 확실히 높은 경우(높음)를
# 구분해서 항상 숫자와 함께 보여준다.
CONFIDENCE_HIGH_THRESHOLD = 0.8

# 신뢰도 밴드 이름들. 사용자에게 항상 이 3단계 + 실제 수치를 함께 노출한다.
CONFIDENCE_BAND_LOW = "낮음"      # < 0.5, NFR-01 기준 미달 -> 위치를 믿기 어려움
CONFIDENCE_BAND_MEDIUM = "보통"   # 0.5 ~ 0.8, 기준은 넘었지만 확실치 않음(턱걸이)
CONFIDENCE_BAND_HIGH = "높음"     # >= 0.8, 확실함

# FR-04(재촬영 요청) 대응 안내 문구. 여러 진입점(main_mvp0, visualize, api_mvp1)에서
# 공유해서 쓰도록 여기 한 곳에 둔다 — 문구가 흩어져서 일부만 갱신되는 것을 방지.
# '잘못 찍으셨어요' 식이 아닌 팁 형태로 프레이밍 (요구사항정의서 8.3 이탈 최소화 전략).
NO_PERSON_TIPS: list[str] = [
    "롱패딩·오버사이즈 외투처럼 몸 실루엣을 가리는 옷은 벗고 촬영해보세요.",
    "상반신(어깨~골반)이 화면에 온전히 나오는지 확인해주세요.",
    "조명이 충분하고 배경과 옷 색이 겹치지 않는지 확인해주세요.",
]

# view별로 최소한 검출되어야 하는 관절.
# "front"는 좌우 모두 필요하다. "side"는 여기 나열된 이름 자체가 아니라
# _required_side_triad()가 근접 측(카메라에 가까운 쪽)을 판정해 동적으로
# 정한다 — 진짜 측면 사진에서는 먼 쪽 귀가 가려져 visibility가 낮게
# 나오는 게 정상이므로, "양쪽 다" 요구하면 정상 사진까지 걸러진다
# (MVP3_설계결정.md Q2). 이 리스트는 하위호환/문서화 목적으로만 남긴다.
REQUIRED_KEYPOINTS: dict[View, list[str]] = {
    "front": ["left_shoulder", "right_shoulder", "left_hip", "right_hip"],
    "side": ["left_ear", "right_ear", "left_shoulder", "right_shoulder"],
}

# --- 기하학적 타당성 검사 기준값 (경험적 기준, 절대 임상 기준 아님) ---
# 좌우 두 점 사이 거리가 이미지 너비 대비 이 값보다 좁으면 "사실상 겹침"으로 간주.
# (sample6 마네킹: 어깨 두 점 거리가 약 0.005였음 — 명백한 오검출)
MIN_PAIR_DISTANCE = 0.03
# 어깨 너비 / 골반 너비 비율이 인체로서 자연스러운 범위. 이 밖이면 의심.
SHOULDER_HIP_RATIO_RANGE = (0.4, 3.0)

# --- 측면 전용 기준값 (MVP3_설계결정.md Q1/Q2, 전부 잠정값) ---
# 정면 검사(겹치면 이상)를 측면에서는 뒤집어 적용한다: 진짜 측면이면
# 좌우 어깨가 x축으로 거의 겹쳐야 정상이고, 오히려 너무 벌어지면
# 정면/사선 사진을 측면으로 잘못 올렸을 가능성으로 본다.
MAX_SIDE_SHOULDER_X = 0.15  # TODO(MVP3-실측)
# 측면이면 근접 관절과 먼 관절의 깊이(z) 차이가 뚜렷해야 한다. 거의
# 없으면 실제로는 옆을 보고 있지 않다는 신호.
MIN_Z_SEPARATION = 0.05  # TODO(MVP3-실측)
# 귀-어깨 수직 거리가 사실상 0이면 목이 프레임 밖이거나 극단적으로
# 눌려 찍힌 경우로, 각도 계산 자체가 무의미해진다.
MIN_NECK_VERTICAL = 0.03  # TODO(MVP3-실측)
# 좌우 귀 z(깊이) 차이가 이 값 이상이어야 근접 측을 판정할 수 있다
# (determine_near_side에서 사용). _check_geometric_plausibility_side의
# "측면 사진이 맞는가" 검사(MIN_Z_SEPARATION)와 같은 값을 그대로
# 재사용한다 — 애초에 z 차이가 뚜렷하지 않으면 "측면 사진 여부" 판정과
# "근접 측이 어디인가" 판정 둘 다 못 하는 게 자연스럽기 때문에, 값을
# 따로 둬서 어긋나게 하지 않는다.


@dataclass
class QualityCheckResult:
    is_valid: bool
    issue: str  # 문제 없으면 빈 문자열


def check_image_quality(result: KeypointResult) -> QualityCheckResult:
    """
    Args:
        result: detect_keypoints()의 반환값

    Returns:
        QualityCheckResult(is_valid, issue)
    """
    if not result.keypoints:
        return QualityCheckResult(is_valid=False, issue="no_person_detected")

    if result.view == "side":
        return _check_image_quality_side(result)
    return _check_image_quality_front(result)


def _check_image_quality_front(result: KeypointResult) -> QualityCheckResult:
    required = REQUIRED_KEYPOINTS.get(result.view, [])
    present_names = {kp.name for kp in result.keypoints}
    missing = [name for name in required if name not in present_names]
    if missing:
        return QualityCheckResult(
            is_valid=False, issue=f"missing_keypoints:{','.join(missing)}"
        )

    low_visibility = [
        kp.name
        for kp in result.keypoints
        if kp.name in required and kp.visibility < CONFIDENCE_THRESHOLD
    ]
    if low_visibility:
        return QualityCheckResult(
            is_valid=False,
            issue=f"low_visibility:{','.join(low_visibility)}",
        )

    if result.confidence < CONFIDENCE_THRESHOLD:
        return QualityCheckResult(is_valid=False, issue="low_overall_confidence")

    geometry = check_geometric_plausibility(result)
    if not geometry.is_valid:
        return geometry

    return QualityCheckResult(is_valid=True, issue="")


def _check_image_quality_side(result: KeypointResult) -> QualityCheckResult:
    """
    측면 이미지 품질 검사 (MVP3_설계결정.md Q2).

    정면과 달리 "양쪽 다" 잘 보일 것을 요구하지 않는다 — 진짜 측면
    사진에서는 카메라에서 먼 쪽 귀가 머리에 가려지는 게 정상이다.
    대신 먼저 근접 측(카메라에 가까운 쪽)을 판정하고, 그 측의 귀/어깨/
    골반만 visibility 기준을 만족하면 통과시킨다.
    """
    present_names = {kp.name for kp in result.keypoints}
    base_required = [
        "left_ear", "right_ear", "left_shoulder", "right_shoulder",
        "left_hip", "right_hip",
    ]
    missing = [name for name in base_required if name not in present_names]
    if missing:
        return QualityCheckResult(
            is_valid=False, issue=f"missing_keypoints:{','.join(missing)}"
        )

    near = determine_near_side(result)
    if near.side is None:
        return QualityCheckResult(
            is_valid=False, issue=f"near_side_undetermined:{near.detail}"
        )

    required_triad = [f"{near.side}_ear", f"{near.side}_shoulder", f"{near.side}_hip"]
    low_visibility = [
        name for name in required_triad
        if result.get(name).visibility < CONFIDENCE_THRESHOLD
    ]
    if low_visibility:
        return QualityCheckResult(
            is_valid=False, issue=f"low_visibility:{','.join(low_visibility)}"
        )

    if result.confidence < CONFIDENCE_THRESHOLD:
        return QualityCheckResult(is_valid=False, issue="low_overall_confidence")

    geometry = check_geometric_plausibility(result)
    if not geometry.is_valid:
        return geometry

    return QualityCheckResult(is_valid=True, issue="")


@dataclass
class NearSideResult:
    """determine_near_side()의 결과. side가 None이면 판정 불가."""
    side: str | None  # "left" | "right" | None
    detail: str


def determine_near_side(result: KeypointResult) -> NearSideResult:
    """
    카메라에 가까운 쪽(근접 측)을 좌/우 귀의 z(깊이) 좌표로 판정한다
    (MVP3_설계결정.md Q2 — 실측 재검증 후 수정).

    원래 설계는 visibility를 주 신호로 삼고 z는 교차검증용으로만 썼다.
    그런데 실제 사진 2장(sample41.jpg, sample42.jpg — 둘 다 완전한
    측면 사진)에서 좌우 귀 visibility 차이가 각각 0.000, 0.002로 사실상
    구분력이 없었다. MediaPipe가 가려진 먼 쪽 귀도 인체 사전지식으로
    강하게 확신해 비슷한 visibility를 매기는 것으로 보인다. 반면 z
    (깊이) 차이는 두 사진 다 0.37~0.39로 뚜렷했다. 그래서 z를 주(유일한)
    판정 신호로 바꾼다 — visibility 기반 판정은 실전에서 거의 항상
    "차이 없음"으로 막혀 near_side_undetermined를 과도하게 유발했다.

    z가 작을수록(더 음수) 카메라에 더 가깝다.

    Args:
        result: detect_keypoints()의 반환값 (view 무관하게 동작하지만
            side 이미지에서 의미가 있다)

    Returns:
        NearSideResult
    """
    try:
        left_ear = result.get("left_ear")
        right_ear = result.get("right_ear")
    except KeyError:
        return NearSideResult(side=None, detail="ear_keypoints_missing")

    z_gap = left_ear.z - right_ear.z
    if abs(z_gap) < MIN_Z_SEPARATION:
        # visibility는 더 이상 판정에 쓰지 않지만, 이상 사례 진단용으로
        # detail에 참고 삼아 같이 남겨둔다.
        vis_gap = left_ear.visibility - right_ear.visibility
        return NearSideResult(
            side=None,
            detail=f"z_gap_too_small({abs(z_gap):.3f}, visibility_gap={vis_gap:+.3f})",
        )

    return NearSideResult(side="left" if z_gap < 0 else "right", detail="")


def confidence_band(visibility: float) -> str:
    """visibility 수치를 3단계 등급(낮음/보통/높음)으로 분류한다."""
    if visibility >= CONFIDENCE_HIGH_THRESHOLD:
        return CONFIDENCE_BAND_HIGH
    if visibility >= CONFIDENCE_THRESHOLD:
        return CONFIDENCE_BAND_MEDIUM
    return CONFIDENCE_BAND_LOW


@dataclass
class KeypointConfidence:
    name: str
    visibility: float
    band: str  # "낮음" | "보통" | "높음"


def keypoint_confidence_report(
    result: KeypointResult, names: list[str] | None = None
) -> list[KeypointConfidence]:
    """
    지정한 키포인트 전체의 신뢰도를 통과 여부와 무관하게 항상 보여준다.

    통과/실패 이진값으로만 필터링해서 보여주면, 0.51(보통)과 0.95(높음)가
    사용자 화면에서 똑같이 "통과"로만 보여서 실제로는 신뢰도 차이가 큰데도
    똑같은 정보로 오인하게 된다 — 이를 막기 위해 항상 실제 수치 + 등급을 노출한다.

    Args:
        result: detect_keypoints()의 반환값
        names: 조회할 키포인트 이름 목록. None이면 검출된 전체.

    Returns:
        [KeypointConfidence(name, visibility, band), ...] — 신뢰도 낮은 순 정렬.
        검출 자체가 안 된 이름은 visibility=0.0, band="낮음"으로 포함된다.
    """
    present = {kp.name: kp.visibility for kp in result.keypoints}
    target_names = names if names is not None else list(present.keys())

    report = [
        KeypointConfidence(name=name, visibility=present.get(name, 0.0), band=confidence_band(present.get(name, 0.0)))
        for name in target_names
    ]
    return sorted(report, key=lambda item: item.visibility)


def _pair_distance(result: KeypointResult, name_a: str, name_b: str) -> float | None:
    try:
        a, b = result.get(name_a), result.get(name_b)
    except KeyError:
        return None
    return math.hypot(a.x - b.x, a.y - b.y)


def check_geometric_plausibility(result: KeypointResult) -> QualityCheckResult:
    """
    좌표 자체가 인체적으로 말이 되는지 검사한다. view에 따라 "말이 되는
    좌표"의 조건이 정반대이므로(MVP3_설계결정.md Q1) 여기서 분기한다 —
    정면은 좌우가 벌어져야 정상이고, 측면은 좌우가 거의 겹쳐야 정상이다.

    Args:
        result: detect_keypoints()의 반환값

    Returns:
        QualityCheckResult(is_valid, issue) — issue는 세미콜론으로 구분된
        복수 사유를 담을 수 있음.
    """
    if result.view == "side":
        return _check_geometric_plausibility_side(result)
    return _check_geometric_plausibility_front(result)


def _check_geometric_plausibility_front(result: KeypointResult) -> QualityCheckResult:
    """
    visibility 점수가 높아도(>= 0.5) 좌표 자체가 인체적으로 말이 안 되는
    경우를 잡아낸다. visibility는 "이 지점이 가려지지 않았는가"에 대한
    모델의 확신도일 뿐, "찍힌 픽셀이 실제 그 관절 위치인가"는 보증하지
    않기 때문에 이 검사가 별도로 필요하다.

    검사 항목:
      1. 어깨 좌우 점 사이 거리가 사실상 0에 가까운가 (겹쳐 찍힘)
      2. 골반 좌우 점 사이 거리가 사실상 0에 가까운가 (겹쳐 찍힘)
      3. 어깨 너비 / 골반 너비 비율이 인체로서 자연스러운 범위인가
         (예: 오버사이즈 외투로 어깨만 과도하게 부풀려진 경우 감지)
    """
    issues: list[str] = []

    shoulder_width = _pair_distance(result, "left_shoulder", "right_shoulder")
    hip_width = _pair_distance(result, "left_hip", "right_hip")

    if shoulder_width is not None and shoulder_width < MIN_PAIR_DISTANCE:
        issues.append(f"shoulder_points_overlapping({shoulder_width:.4f})")
    if hip_width is not None and hip_width < MIN_PAIR_DISTANCE:
        issues.append(f"hip_points_overlapping({hip_width:.4f})")

    # 좌우 점이 이미 겹쳐서(overlapping) 잡혔다면, 그로 인해 비율 계산 자체가
    # 왜곡되어 shoulder_hip_ratio_unusual이 자동으로 같이 뜬다 (겹침 -> 분모가
    # 0에 가까워짐 -> 비율 폭주). 같은 근본 원인을 두 개의 별개 사유처럼
    # 나열하면 사용자가 혼란스러우므로, 겹침이 이미 잡혔으면 비율 검사는 건너뛴다.
    already_overlapping = len(issues) > 0
    if not already_overlapping and shoulder_width and hip_width:
        ratio = shoulder_width / hip_width
        lo, hi = SHOULDER_HIP_RATIO_RANGE
        if not (lo <= ratio <= hi):
            issues.append(f"shoulder_hip_ratio_unusual({ratio:.2f})")

    if issues:
        return QualityCheckResult(is_valid=False, issue=";".join(issues))
    return QualityCheckResult(is_valid=True, issue="")


def _check_geometric_plausibility_side(result: KeypointResult) -> QualityCheckResult:
    """
    측면 전용 기하학적 타당성 검사 (MVP3_설계결정.md Q1).

    정면 검사를 그냥 끄면 마네킹류를 못 거르게 되므로 끄는 게 아니라
    다른 조건으로 교체한다:
      1. 좌우 어깨 x축 거리가 오히려 너무 크면 의심 — 진짜 측면은 좌우
         어깨가 거의 겹쳐야 하므로, 벌어져 있으면 정면/사선 사진을
         측면으로 잘못 올렸을 가능성.
      2. 좌우 귀의 z(깊이) 차이가 너무 작으면 의심 — 실제로 옆을 보고
         있지 않다는 신호.
      3. 근접 측을 판정할 수 없으면 의심 (determine_near_side 참고).
      4. 근접 측 귀-어깨 수직 거리가 사실상 0이면 의심 — 목이 프레임
         밖이거나 극단적으로 눌려 찍힌 경우.
    """
    issues: list[str] = []

    try:
        left_ear, right_ear = result.get("left_ear"), result.get("right_ear")
        left_shoulder, right_shoulder = result.get("left_shoulder"), result.get("right_shoulder")
    except KeyError:
        # 필수 관절 자체가 없으면 check_image_quality의 missing_keypoints
        # 단계에서 이미 걸렀을 것이므로 여기서는 중복 보고하지 않는다.
        return QualityCheckResult(is_valid=True, issue="")

    shoulder_x_gap = abs(left_shoulder.x - right_shoulder.x)
    if shoulder_x_gap > MAX_SIDE_SHOULDER_X:
        issues.append(f"not_a_side_profile:shoulder_x_gap({shoulder_x_gap:.4f})")

    z_gap = abs(left_ear.z - right_ear.z)
    if z_gap < MIN_Z_SEPARATION:
        issues.append(f"not_a_side_profile:z_separation({z_gap:.4f})")

    near = determine_near_side(result)
    if near.side is None:
        issues.append(f"near_side_undetermined:{near.detail}")
    else:
        near_ear = left_ear if near.side == "left" else right_ear
        near_shoulder = left_shoulder if near.side == "left" else right_shoulder
        neck_vertical = abs(near_ear.y - near_shoulder.y)
        if neck_vertical < MIN_NECK_VERTICAL:
            issues.append(f"neck_too_short({neck_vertical:.4f})")

    if issues:
        return QualityCheckResult(is_valid=False, issue=";".join(issues))
    return QualityCheckResult(is_valid=True, issue="")


@dataclass
class PersonDetectionStrength:
    """
    '사람이다' 1단계 판별의 종합 강도.

    기존에는 PoseLandmarker 하나의 자체 확신도만 있었다. 여기서는
    person_detection.py의 독립 세그멘테이션 모델 결과까지 합쳐서,
    '두 개의 서로 다른 모델이 동시에 사람이라고 동의하는가'를
    하나의 등급으로 정리한다. 1단계가 강할수록 2단계(좌표 추정) 결과를
    더 신뢰할 근거가 생긴다.
    """
    level: str  # "강함" | "보통" | "약함"
    pose_detected: bool
    silhouette_plausible: bool | None  # 세그멘테이션 모델을 안 썼으면 None
    landmarks_agree: bool | None  # 관절 좌표들이 세그멘테이션 마스크와 일치하는지
    detail: str


def evaluate_person_detection_strength(
    pose_detected: bool,
    silhouette_check=None,  # PersonSilhouetteCheck | None
    pose_points_xy: list[tuple[float, float]] | None = None,
) -> PersonDetectionStrength:
    """
    PoseLandmarker(1개 모델)와 ImageSegmenter(독립된 별개 모델)의 결과를
    합쳐 '사람이다' 판별의 종합 강도를 매긴다.

    등급:
      강함 - 두 독립 모델이 모두 사람으로 인식했고, PoseLandmarker가
             찍은 관절 좌표들이 세그멘테이션 마스크(사람 영역) 위에
             실제로 놓여 있음 (가장 신뢰할 수 있는 상태)
      보통 - PoseLandmarker만 사람으로 인식함 (세그멘테이션 모델을 안
             썼거나, 비교할 수 없는 경우) — 지금까지의 기존 동작과 동일
      약함 - PoseLandmarker는 사람으로 인식했지만 세그멘테이션 결과와
             모순됨(실루엣이 비인체적이거나, 관절 좌표들이 세그멘테이션이
             찾은 사람 영역 밖에 찍힘) -> 2단계 좌표를 신뢰하기 어려움

    Args:
        pose_detected: PoseLandmarker가 사람을 감지했는지 (result.keypoints 존재 여부)
        silhouette_check: person_detection.check_person_silhouette()의 결과. 안 썼으면 None.
        pose_points_xy: KeypointResult.interest_point_coords() — 검증에 쓸 관절 좌표들

    Returns:
        PersonDetectionStrength
    """
    if not pose_detected:
        return PersonDetectionStrength(
            level="약함", pose_detected=False, silhouette_plausible=None,
            landmarks_agree=None, detail="pose_landmarker가 사람을 감지하지 못함",
        )

    if silhouette_check is None:
        return PersonDetectionStrength(
            level="보통", pose_detected=True, silhouette_plausible=None,
            landmarks_agree=None,
            detail="세그멘테이션 교차검증 없이 PoseLandmarker 단독 판정 (기존 동작)",
        )

    # 이 import는 silhouette_check가 있을 때만 실행되는 지연 import다.
    # posture-ai(좌표 입력)에서는 항상 None이 들어오므로 위에서 반환되어
    # 여기까지 도달하지 않는다 — person_detection 모듈이 없어도 동작한다.
    # (이미지 입력 버전인 posture-mvp에서는 이 경로가 실제로 쓰인다)
    from .person_detection import cross_validate_with_pose

    landmarks_agree, mismatch_reason = cross_validate_with_pose(silhouette_check, pose_points_xy)

    if silhouette_check.is_plausible_person and landmarks_agree:
        return PersonDetectionStrength(
            level="강함", pose_detected=True, silhouette_plausible=True,
            landmarks_agree=True,
            detail="PoseLandmarker와 세그멘테이션 모델이 서로 독립적으로 동의함",
        )

    reasons = []
    if not silhouette_check.is_plausible_person:
        reasons.append(f"실루엣 비정상({silhouette_check.issue})")
    if not landmarks_agree:
        reasons.append(f"관절 좌표가 세그멘테이션 사람 영역과 불일치({mismatch_reason})")

    # 진단용: 마스크 크기와 원본 이미지 크기를 detail에 덧붙인다. 이 값이
    # 다르면(리사이즈 보정 이전이라면) 좌표계 불일치가 원인일 가능성이 높다는
    # 신호이므로, '약함'이 재현될 경우 원인을 바로 특정할 수 있게 해둔다.
    if silhouette_check.debug_mask_shape and silhouette_check.debug_original_shape:
        reasons.append(
            f"mask_shape={silhouette_check.debug_mask_shape}, "
            f"original_shape={silhouette_check.debug_original_shape}"
        )

    return PersonDetectionStrength(
        level="약함", pose_detected=True, silhouette_plausible=silhouette_check.is_plausible_person,
        landmarks_agree=landmarks_agree,
        detail="; ".join(reasons),
    )


@dataclass
class ReliabilityAssessment:
    """
    person_detection(세그멘테이션 교차검증)과 check_geometric_plausibility
    (좌표 자체의 기하학적 타당성)를 하나로 합친 최종 판정.

    두 검사는 서로 다른 문제를 잡는다 — 하나가 통과했다고 다른 하나도
    통과했다는 보장이 없다. 실사용 검증에서 확인된 예:
        마네킹: person_detection은 '강함'(세그멘테이션이 사람 모양으로
                인식하고 관절도 그 안에 있음)이지만, 어깨/골반 좌표가
                서로 거의 겹쳐 찍혀 check_geometric_plausibility는 실패함.
    이런 경우를 놓치지 않으려면 두 검사를 AND로 묶어야 한다.

    "강함/보통/약함" 같은 등급 라벨은 사용자에게 노출하지 않는다 —
    "강함"이라는 말이 "진짜 사람이라고 확인됨"으로 오인되기 쉽지만,
    실제로는 "PoseLandmarker가 엉뚱한 곳에 점을 찍은 건 아니다" 정도의
    좁은 의미이기 때문이다(마네킹도 이 기준은 통과함). 대신 문제가
    있을 때 두 모델이 실제로 찾아낸 구체적 사유만 그대로 보여준다.
    """
    is_reliable: bool
    issues: list[str]  # 문제 없으면 빈 리스트


def assess_combined_reliability(
    person_strength: PersonDetectionStrength, geometry: QualityCheckResult
) -> ReliabilityAssessment:
    """
    Args:
        person_strength: evaluate_person_detection_strength()의 결과
        geometry: check_geometric_plausibility()의 결과

    Returns:
        ReliabilityAssessment
    """
    issues: list[str] = []

    if person_strength.level == "약함":
        issues.append(person_strength.detail)

    if not geometry.is_valid:
        issues.append(geometry.issue)

    return ReliabilityAssessment(is_reliable=not issues, issues=issues)
