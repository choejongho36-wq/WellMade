"""
lookup_normal_range Tool + 3단계(정상/경미/주의) 판정 로직.

요구사항정의서 6장 "판정 기준값(참고용)" 표를 그대로 코드화한다.
전부 참고용 정성 구간이며 의료 진단 기준이 아니다(NFR-04).
MVP1은 Tool-use 에이전트가 아니라 if문 기반 판정이다(로드맵 4장).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Verdict = Literal["정상", "경미", "주의"]

# metric -> (min, max, source) : 요구사항정의서 6장
NORMAL_RANGES: dict[str, dict] = {
    "shoulder_tilt": {
        "range": (0.0, 5.0),
        "source": "어깨 좌우 비대칭(정면): 15도 초과 시 척추측만증 참고 지표로 활용 가능. "
        "판정 구간: 5도 이내 정상 / 5~15도 경미 / 15도 이상 주의.",
    },
    "pelvis_tilt": {
        "range": None,  # 명확한 단일 임상 기준 없음 -> 상대비교/정성 평가
        "source": "골반 좌우 비대칭(정면): 명확한 단일 임상 기준 없음. "
        "상대 비교 위주의 정성적 표현(정상/경미/주의)으로 순화.",
    },
    "forward_head": {
        # 잠정 구간 (MVP3_설계결정.md Q5). 임상 CVA 문헌(귀-C7-수평 기준)은
        # 대략 48~53도를 정상/이상 전환 구간으로 보는 경향이 있으나, 본
        # 지표는 기준점(어깨 vs C7)과 기준축(수직 vs 수평)이 달라 그
        # 수치를 그대로 옮길 수 없다. 방향성만 참고한 잠정 구간이며
        # 실측 사진으로 재보정이 필요하다.
        "range": (0.0, 15.0),  # TODO(MVP3-실측): 0~15 정상 / 15~25 경미 / 25~ 주의
        "source": "전방머리자세(측면, CVA 대체 지표): 귀-어깨 정렬 기반 상대 평가. "
        "임상 CVA(귀-C7-수평 기준)는 기준점·기준축이 달라 직접 대응되지 않으므로 "
        "방향성만 참고한 잠정 구간. 참고용 정성 평가로만 사용.",
    },
    "round_shoulder": {
        # 52도 기준은 Thigpen 등 임상 문헌 근거 확정치 (MVP3_설계결정.md Q4):
        # "C7-견봉(어깨) 선이 수평선과 이루는 각도, 52도 이하 = 라운드숄더 경향".
        # 단, 여기 들어가는 C7 좌표는 실측이 아니라 approximate_c7()의 근사값이므로
        # 기준선 자체는 맞아도 입력 오차가 있을 수 있다 -> classify_round_shoulder의
        # note와 코멘트 문구에서 근사값 기반임을 항상 명시한다.
        "range": (52.0, None),
        "source": "라운드숄더(측면, 견봉-C7 각도): 52도 이하 시 라운드숄더 경향, 52도 초과 시 정상 경향 "
        "(Thigpen et al. 기준, 수평선 대비 각도). C7은 어깨-골반 좌표로 근사한 값이다.",
    },
    "pelvis_sagittal": {
        "range": (7.0, 19.0),
        "source": "골반 전후 경사(측면): 정상 전방경사 평균 약 8~13도, 넓게는 7~19도. "
        "절대각도보다 전방/중립/후방 경향으로 안내.",
    },
}


def lookup_normal_range(metric: str) -> dict:
    """
    지표별 참고 정상범위 조회 (Tool: lookup_normal_range).

    Args:
        metric: "shoulder_tilt" | "pelvis_tilt" | "forward_head" |
                "round_shoulder" | "pelvis_sagittal"

    Returns:
        {"range": (min, max) | None, "source": str}
    """
    if metric not in NORMAL_RANGES:
        raise ValueError(f"알 수 없는 지표: {metric}")
    return NORMAL_RANGES[metric]


@dataclass
class ClassificationResult:
    verdict: Verdict
    angle_deg: float
    note: str = ""


def classify_shoulder_tilt(angle_deg: float) -> ClassificationResult:
    """
    정면 어깨 비대칭 3단계 판정 (FR-07). if문 기반, MVP1 요구사항 그대로.
    요구사항정의서 6장: 5도 이내 정상 / 5~15도 경미 / 15도 이상 주의.
    """
    abs_angle = abs(angle_deg)
    if abs_angle <= 5.0:
        return ClassificationResult("정상", angle_deg)
    if abs_angle <= 15.0:
        return ClassificationResult("경미", angle_deg)
    return ClassificationResult("주의", angle_deg)


def classify_pelvis_tilt(angle_deg: float) -> ClassificationResult:
    """
    정면 골반 비대칭 3단계 판정.

    임상 기준이 없어(요구사항정의서 6장) 어깨와 동일한 구간을 잠정
    기준으로 사용하되, 결과 문구는 정량("N도")이 아닌 정성 표현으로
    노출할 것을 권장한다(순도 낮은 근거이므로 note에 명시).
    """
    abs_angle = abs(angle_deg)
    if abs_angle <= 5.0:
        verdict: Verdict = "정상"
    elif abs_angle <= 15.0:
        verdict = "경미"
    else:
        verdict = "주의"
    return ClassificationResult(
        verdict,
        angle_deg,
        note="골반은 임상적으로 확립된 단일 기준이 없어 잠정 구간을 사용함 (참고용).",
    )


def classify_forward_head(angle_deg: float) -> ClassificationResult:
    """
    측면 전방머리자세 3단계 판정 (MVP3_설계결정.md Q5).

    임상 CVA 문헌(귀-C7-수평 기준, 대략 48~53도를 전환 구간으로 보는
    경향)은 본 지표(귀-어깨-수직 기준)와 기준점·기준축이 달라 그대로
    옮길 수 없다. NORMAL_RANGES["forward_head"]의 잠정 구간을 그대로
    따르며, 실측 사진으로 재보정하기 전까지는 방향성 참고용이다.
    """
    abs_angle = abs(angle_deg)
    if abs_angle <= 15.0:
        verdict: Verdict = "정상"
    elif abs_angle <= 25.0:
        verdict = "경미"
    else:
        verdict = "주의"
    return ClassificationResult(
        verdict,
        angle_deg,
        note="전방머리자세는 임상 단일 기준이 없어 잠정 구간을 사용함 "
        "(참고용, 실측 후 보정 예정).",
    )


# Thigpen et al. 기준, C7-견봉 선이 수평선과 이루는 각도. 문헌 근거로 확정됨
# (MVP3_설계결정.md Q4). 52도 이하이면 라운드숄더 경향.
ROUND_SHOULDER_NORMAL_THRESHOLD = 52.0

# C7 근사 오차를 흡수하기 위한 완충 구간 폭(도). approximate_c7()이 실측이
# 아닌 트렁크 연장선 근사이므로, 52도 경계 바로 옆을 곧바로 정상/주의로
# 가르지 않고 "경미"로 완충한다. 임의값이며 실측 후 보정 대상이다.
ROUND_SHOULDER_MARGIN = 7.0  # TODO(MVP3-실측)


def classify_round_shoulder(angle_deg: float) -> ClassificationResult:
    """
    측면 라운드숄더 3단계 판정 (MVP3_설계결정.md Q4).

    52도 기준 자체는 문헌 근거가 있는 확정치이지만, 여기 들어가는 각도는
    approximate_c7()로 근사한 C7 좌표를 사용하므로 경계선 부근 판정에는
    오차가 섞일 수 있다. 그래서 52도를 정상/이상 이분법으로 바로 쓰지
    않고, ROUND_SHOULDER_MARGIN만큼 완충 구간을 둬 "경미"로 흡수한다.

    이 함수는 angle_deg가 calculate_shoulder_angle()의 결과(방향-무관,
    항상 0~90도)라고 전제한다. calculate_shoulder_angle이 원래 atan2
    기반이라 촬영 방향(좌/우 프로필)에 따라 부호가 뒤집히는 버그가
    있었는데(sample42.jpg 실측 검증 중 발견 — 정상 자세가 "주의"로
    오판됨), 그 공식 자체를 고쳐서 여기서는 추가 처리가 필요 없다.

    참고로 ROUND_SHOULDER_MARGIN(7.0도)은 원래 임의값이었는데,
    round_shoulder_ml 실험에서 합성 데이터로 학습한 MLP의 검증 오차가
    공교롭게도 7.7도로 나와 — 우연이지만 이 폭이 비현실적인 값은
    아니라는 방증 정도는 된다.
    """
    threshold = ROUND_SHOULDER_NORMAL_THRESHOLD
    if angle_deg >= threshold:
        verdict: Verdict = "정상"
    elif angle_deg >= threshold - ROUND_SHOULDER_MARGIN:
        verdict = "경미"
    else:
        verdict = "주의"
    return ClassificationResult(
        verdict,
        angle_deg,
        note="C7은 어깨-골반 좌표로 근사한 값이며, 해부학적 C7 실측과 다를 수 있습니다 "
        "(기준각 52도 자체는 Thigpen et al. 문헌 근거).",
    )
