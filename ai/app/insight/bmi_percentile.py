"""
BMI 또래 비교 + 비만도 분류 (인바디 수치 해석의 첫 항목).

두 가지를 같이 돌려준다:
1) 분류 — 대한비만학회 기준으로 저체중/정상/비만 전단계/1~3단계 비만
2) 또래 비교 — 질병관리청 2024 국민건강통계의 성별×연령대별 BMI 백분위수와 비교

왜 분류와 비교를 함께 주는가:
- 백분위만 주면 "또래의 절반이 비만인 집단에서 평균이라 괜찮다"는 잘못된 안심을 준다.
- 분류만 주면 "나만 그런가?"라는 맥락이 빠진다.
두 값은 서로를 대체하지 않으므로 각각 계산해 함께 내려준다.

체지방률·골격근량은 이 통계에 없어서(2024 국민건강통계의 신체계측은 신장/체중/허리둘레/
BMI까지) 또래 비교를 할 수 없다. 그 항목들은 별도 기준이 확보되기 전까지 다루지 않는다.

백분위 계산 방식:
- 원 통계가 7개 지점(5/10/25/50/75/90/95)만 공개하므로 그 사이는 선형보간한다.
- 양 끝(5 미만, 95 초과)은 보간할 구간이 없어 "5% 미만"/"95% 초과"로만 말한다 —
  없는 구간을 외삽하면 근거 없는 숫자가 된다.
"""

import json
from pathlib import Path
from typing import Optional

REFERENCE_PATH = Path(__file__).parent / "data" / "bmi_reference.json"

AGE_BRACKETS = [
    (19, 29, "19-29"),
    (30, 39, "30-39"),
    (40, 49, "40-49"),
    (50, 59, "50-59"),
    (60, 69, "60-69"),
]
OLDEST_BRACKET = "70+"

# 대한비만학회 비만 진료지침 기준(아시아인 기준 — WHO 국제 기준보다 낮다).
# (하한 이상, 분류명) 순서. 같은 BMI라도 아시아인은 체지방률이 높아 더 낮은 값에서
# 동반질환 위험이 올라간다는 근거로 25 kg/m²를 비만 기준으로 쓴다.
BMI_CATEGORIES = [
    (35.0, "3단계 비만(고도비만)"),
    (30.0, "2단계 비만"),
    (25.0, "1단계 비만"),
    (23.0, "비만 전단계(과체중)"),
    (18.5, "정상"),
    (0.0, "저체중"),
]

_reference_cache: Optional[dict] = None


def _load_reference() -> dict:
    global _reference_cache
    if _reference_cache is None:
        _reference_cache = json.loads(REFERENCE_PATH.read_text(encoding="utf-8"))
    return _reference_cache


def to_age_bracket(age: int) -> Optional[str]:
    """국민건강통계의 성인 연령 구간. 19세 미만은 참조 데이터가 없어 None."""
    for low, high, label in AGE_BRACKETS:
        if low <= age <= high:
            return label
    return OLDEST_BRACKET if age >= 70 else None


def classify_bmi(bmi: float) -> str:
    for lower_bound, label in BMI_CATEGORIES:
        if bmi >= lower_bound:
            return label
    return "저체중"


def estimate_percentile(bmi: float, percentiles: dict) -> Optional[float]:
    """
    공개된 백분위수 지점들 사이를 선형보간해 "또래 중 상위 몇 %"를 추정한다.
    보간할 구간 밖(최저 지점 미만 / 최고 지점 초과)이면 None을 돌려준다.
    """
    points = sorted((float(p), value) for p, value in percentiles.items())
    if not points or bmi < points[0][1] or bmi > points[-1][1]:
        return None

    for (low_p, low_v), (high_p, high_v) in zip(points, points[1:]):
        if low_v <= bmi <= high_v:
            if high_v == low_v:
                return low_p
            ratio = (bmi - low_v) / (high_v - low_v)
            return round(low_p + ratio * (high_p - low_p), 1)
    return None


def compute_bmi_insight(bmi: float, gender: str, age: int) -> dict:
    reference = _load_reference()
    bracket = to_age_bracket(age)
    group = reference["groups"].get(gender, {}).get(bracket) if bracket else None

    category = classify_bmi(bmi)
    bmi = round(float(bmi), 1)

    if not group:
        return {
            "bmi": bmi,
            "category": category,
            "age_bracket": bracket or "",
            "sample_size": 0,
            "peer_mean": None,
            "percentile": None,
            "message": f"체질량지수 {bmi}로 '{category}'에 해당해요. 비교할 또래 통계가 없어 또래 비교는 생략했어요.",
            "source": reference["source"],
        }

    percentile = estimate_percentile(bmi, group["percentiles"])
    sex_label = "남성" if gender == "M" else "여성"

    if percentile is None:
        # 5~95 구간 밖 - 방향만 말하고 숫자는 만들지 않는다
        low_end = bmi < group["percentiles"]["5"]
        position = "하위 5% 안쪽" if low_end else "상위 5% 안쪽"
        comparison = f"같은 {bracket}세 {sex_label} 중에서는 {position}이에요."
    else:
        comparison = f"같은 {bracket}세 {sex_label} 중 {percentile}%가 회원님보다 낮거나 같아요(평균 {group['mean']})."

    return {
        "bmi": bmi,
        "category": category,
        "age_bracket": bracket,
        "sample_size": int(group.get("sample_size") or 0),
        "peer_mean": group["mean"],
        "percentile": percentile,
        "message": f"체질량지수 {bmi}로 '{category}'에 해당해요. {comparison}",
        "source": reference["source"],
    }
