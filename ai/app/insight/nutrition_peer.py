"""
영양 섭취 또래 비교 (신규 — 온보딩 캘리브레이션 확장인 posture_percentile.py의 자매 기능).

사용자가 기록한 하루 섭취량을 질병관리청 "2024 국민건강통계"의 성별×연령대별 평균과
비교해서 "같은 또래는 얼마나 먹는가"를 알려준다.
(예: "오늘 단백질 62g을 드셨어요. 같은 30대 남성 평균은 97g이에요.")

posture_percentile.py와 다른 점 — 백분위가 아니라 평균 대비 비율을 쓴다:
- 세종시 자세 데이터는 개인 단위 원시 기록이라 정렬해서 백분위를 낼 수 있었지만,
  국민건강통계는 이미 집계된 평균값(+표준오차)만 공개한다. 분포가 없으므로 "상위 몇 %"는
  계산할 수 없고, 계산한 척하면 근거 없는 숫자가 된다. 그래서 "평균 대비 몇 %"만 말한다.

"정상/이상"을 가르지 않는 것은 posture_percentile.py와 같다 — 평균보다 적게 먹는 게
곧 문제라는 뜻이 아니므로(활동량·체격에 따라 다름), 판정 없이 비교 정보만 제공한다.
목표 대비 판정은 기존 NutrientTargetCalculator(백엔드)가 계속 담당한다.
"""

import json
from pathlib import Path
from typing import Optional

REFERENCE_PATH = Path(__file__).parent / "data" / "nutrition_reference.json"

# 국민건강통계의 연령 구간을 그대로 따른다(임의로 다시 묶으면 원 통계와 어긋난다).
AGE_BRACKETS = [
    (10, 18, "10-18"),
    (19, 29, "19-29"),
    (30, 39, "30-39"),
    (40, 49, "40-49"),
    (50, 59, "50-59"),
    (60, 69, "60-69"),
]
OLDEST_BRACKET = "70+"

# 이 미만이면 그룹 평균이 흔들릴 수 있어 참고용이라고 알린다(posture_percentile과 같은 취지).
MIN_RELIABLE_SAMPLE = 100

NUTRIENT_LABELS = {
    "energy_kcal": ("칼로리", "kcal"),
    "protein_g": ("단백질", "g"),
    "carbs_g": ("탄수화물", "g"),
    "fat_g": ("지방", "g"),
}

_reference_cache: Optional[dict] = None


def _load_reference() -> dict:
    """참조 데이터는 크지 않아(그룹 14개) 프로세스당 한 번만 읽어 캐싱한다."""
    global _reference_cache
    if _reference_cache is None:
        _reference_cache = json.loads(REFERENCE_PATH.read_text(encoding="utf-8"))
    return _reference_cache


def to_age_bracket(age: int) -> Optional[str]:
    """
    나이를 국민건강통계의 연령 구간 라벨로 바꾼다. 비교할 구간이 없으면 None.

    위로는 열려 있고(70+는 "70세 이상"이라 몇 살이든 이 구간이 맞다) 아래로는 닫혀 있다 —
    10세 미만을 10-18 구간과 비교하면 근거 없는 비교가 되므로 아예 비교하지 않는다.
    """
    for low, high, label in AGE_BRACKETS:
        if low <= age <= high:
            return label
    return OLDEST_BRACKET if age >= 70 else None


def compare_with_peers(intake: dict, gender: str, age: int) -> dict:
    """
    :param intake: {"energy_kcal": 1850.0, "protein_g": 62.0, ...} — 없는 항목은 비교에서 빠진다
    :param gender: "M" | "F"
    :param age: 만 나이
    """
    reference = _load_reference()
    bracket = to_age_bracket(age)
    group = reference["groups"].get(gender, {}).get(bracket) if bracket else None

    if not group:
        # 참조 그룹이 없으면 비교 자체를 생략한다 - 다른 그룹 값을 빌려 쓰면 틀린 비교가 된다
        return {
            "age_bracket": bracket or "",
            "sample_size": 0,
            "low_sample_warning": True,
            "comparisons": [],
            "message": "비교할 또래 통계가 없어 이번에는 비교를 건너뛰었어요.",
            "source": reference["source"],
        }

    comparisons = []
    for field, (label, unit) in NUTRIENT_LABELS.items():
        my_value = intake.get(field)
        peer_mean = group.get(field)
        if my_value is None or not peer_mean:
            continue

        percent_of_peer = round(my_value / peer_mean * 100, 1)
        comparisons.append({
            "nutrient": label,
            "unit": unit,
            "my_value": round(float(my_value), 1),
            "peer_mean": peer_mean,
            "percent_of_peer": percent_of_peer,
            "message": (
                f"{label} {round(float(my_value), 1)}{unit}을(를) 드셨어요. "
                f"같은 또래 평균은 {peer_mean}{unit}으로, 평균의 {percent_of_peer}% 수준이에요."
            ),
        })

    sample_size = int(group.get("sample_size") or 0)
    sex_label = "남성" if gender == "M" else "여성"
    headline = f"{bracket}세 {sex_label} 평균과 비교했어요."
    if comparisons:
        headline += " " + " ".join(c["message"] for c in comparisons)

    return {
        "age_bracket": bracket,
        "sample_size": sample_size,
        "low_sample_warning": sample_size < MIN_RELIABLE_SAMPLE,
        "comparisons": comparisons,
        # 권장섭취량 대비 비율은 에너지·단백질만 원 통계에 있어 따로 내려준다
        "peer_energy_ratio_pct": group.get("energy_ratio_pct"),
        "peer_protein_ratio_pct": group.get("protein_ratio_pct"),
        "message": headline,
        "source": reference["source"],
    }
