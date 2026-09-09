"""
app/pose/angles.py 좌우 기울기 부호 버그 재현 (AI-15 자세 비교 인사이트 영향).

실행:
    cd ai
    python tests/repro_tilt_sign_bug.py

표준 라이브러리만 사용한다(math, json, bisect). 서버를 띄우지 않아도 된다.

=============================================================================
한 줄 요약
=============================================================================
`_horizontal_tilt_angle()`이 `atan2(dy, dx)`를 쓰는데, 정면 촬영에서는 dx가
항상 음수라 결과가 ±90~180도 범위로 나간다. 그 결과 AI-15 백분위가 모든
사용자에게 100%로 나오고, "왼쪽 어깨가 175.7도 올라간 상태입니다" 같은
문장이 사용자에게 나간다.

수정: `atan2(dy, dx)` -> `atan2(dy, abs(dx))` (한 줄)

=============================================================================
왜 dx가 항상 음수인가
=============================================================================
MediaPipe Pose는 좌/우를 **피사체 본인 기준**으로 명명한다. 카메라를 마주본
사람의 왼쪽 어깨(LEFT_SHOULDER=11)는 화면에서 오른쪽에 찍히고, 오른쪽
어깨(RIGHT_SHOULDER=12)는 화면 왼쪽에 찍힌다.

    dx = right.x - left.x
       = (화면 왼쪽 x) - (화면 오른쪽 x)
       < 0   ← 정면 촬영이면 항상

atan2(dy, dx)에서 dx가 음수면 결과가 2사분면(dy>0) 또는 3사분면(dy<0)으로
가서 절댓값이 90~180도가 된다. docstring이 명시한 부호 규약
("양수 = 왼쪽 어깨가 올라감")도 이때 뒤집힌다.

abs(dx)를 쓰면 결과가 항상 1/4사분면(-90~90도)에 들어오고 부호가 dy와
정확히 일치한다. dx의 **크기**는 그대로 쓰이므로(기울기 = dy/dx) 각도
정보에 손실이 없다 — 부호만 제거하는 것이다.
"""

import bisect
import json
import math
from pathlib import Path

REFERENCE_PATH = Path(__file__).resolve().parent.parent / "app" / "insight" / "data" / "posture_reference.json"


# --- 현재 app/pose/angles.py 구현 (그대로 복사) ---------------------------


def current_tilt(left, right) -> float:
    dx = right[0] - left[0]
    dy = right[1] - left[1]
    if dx == 0 and dy == 0:
        return 0.0
    return math.degrees(math.atan2(dy, dx))


# --- 제안하는 수정 ---------------------------------------------------------


def fixed_tilt(left, right) -> float:
    dx = right[0] - left[0]
    dy = right[1] - left[1]
    if dx == 0 and dy == 0:
        return 0.0
    return math.degrees(math.atan2(dy, abs(dx)))


# --- 실측 좌표 (MediaPipe Pose 정면 사진 출력) -----------------------------

CASES = [
    {
        "label": "실측 A — 오른쪽 어깨가 더 낮음",
        "left": (0.6425, 0.2382),
        "right": (0.3716, 0.2586),
    },
    {
        "label": "실측 B — 왼쪽 어깨가 더 낮음",
        "left": (0.6500, 0.3000),
        "right": (0.4000, 0.2200),
    },
    {
        "label": "실측 C — 거의 수평",
        "left": (0.7500, 0.2300),
        "right": (0.4200, 0.2200),
    },
]


def percentile_rank(value_abs_deg, sorted_abs_list):
    """posture_percentile._percentile_rank와 동일한 계산."""
    if not sorted_abs_list:
        return None
    rank = bisect.bisect_right(sorted_abs_list, value_abs_deg)
    return round(rank / len(sorted_abs_list) * 100, 1)


def describe(signed_deg, percentile):
    """posture_percentile._describe와 동일한 문구 형식(어깨 기준)."""
    if abs(signed_deg) < 0.5:
        return "어깨가 수평에 가깝게 잘 정렬되어 있습니다."
    side_kr = "왼쪽" if signed_deg >= 0.5 else "오른쪽"
    base = f"{side_kr} 어깨가 {abs(signed_deg):.1f}도 올라간 상태입니다."
    if percentile is None:
        return base
    return f"{base} 비슷한 연령대에서는 {percentile:.0f}%에 해당합니다."


def main() -> None:
    print("=" * 78)
    print("app/pose/angles.py — 좌우 기울기 부호 버그 재현")
    print("=" * 78)
    print()
    print("docstring 규약: 양수 = 왼쪽 어깨가 올라감 / 음수 = 오른쪽 어깨가 올라감")
    print("(MediaPipe y축은 아래로 증가 -> y가 작은 쪽이 '올라간' 쪽)")
    print()

    failures = 0
    for case in CASES:
        left, right = case["left"], case["right"]
        dx = right[0] - left[0]
        dy = right[1] - left[1]

        cur = current_tilt(left, right)
        fix = fixed_tilt(left, right)

        expected_sign = "양수" if dy > 0 else ("음수" if dy < 0 else "0")
        actual_sign = "양수" if cur > 0 else ("음수" if cur < 0 else "0")
        in_range = -90 <= cur <= 90
        ok = (expected_sign == actual_sign) and in_range

        print(f"[{case['label']}]")
        print(f"  dx = {dx:+.4f}  <- 정면 촬영이면 항상 음수")
        print(f"  dy = {dy:+.4f}  -> 기대 부호 {expected_sign}, 기대 범위 -90~90도")
        print(f"  현재 : {cur:+8.2f}도   {'OK' if ok else '<-- 규약 위반'}")
        print(f"  수정 : {fix:+8.2f}도")
        print()
        if not ok:
            failures += 1

    # --- 실제 참조 데이터로 AI-15 영향 확인 ---
    print("-" * 78)
    print("AI-15(자세 비교 인사이트) 실제 영향")
    print("-" * 78)

    if not REFERENCE_PATH.exists():
        print(f"  참조 데이터를 찾지 못했습니다: {REFERENCE_PATH}")
        print("  (ai/ 디렉토리에서 실행했는지 확인하세요)")
    else:
        reference = json.load(open(REFERENCE_PATH, encoding="utf-8"))
        key = next(iter(reference))
        group = reference[key]
        sorted_list = group["shoulder_abs_deg_sorted"]

        print(f"  참조 그룹 [{key}] 표본 {group['sample_size']}명")
        print(f"  세종시 데이터의 어깨 기울기 분포: {min(sorted_list)}도 ~ {max(sorted_list)}도"
              f" (중앙 {sorted_list[len(sorted_list)//2]}도)")
        print()

        left, right = CASES[0]["left"], CASES[0]["right"]
        cur = current_tilt(left, right)
        fix = fixed_tilt(left, right)
        cur_p = percentile_rank(abs(cur), sorted_list)
        fix_p = percentile_rank(abs(fix), sorted_list)

        print("  실측 A 좌표로 /ai/onboarding/posture-insight 응답을 만들면:")
        print()
        print(f"    현재  shoulder_tilt_deg = {cur:.2f}, shoulder_percentile = {cur_p}%")
        print(f"          message: \"{describe(cur, cur_p)}\"")
        print()
        print(f"    수정  shoulder_tilt_deg = {fix:.2f}, shoulder_percentile = {fix_p}%")
        print(f"          message: \"{describe(fix, fix_p)}\"")
        print()
        print(f"  참조 분포 최댓값이 {max(sorted_list)}도인데 계산값이 {abs(cur):.0f}도로 나오므로,")
        print("  bisect 비교가 항상 분포 최상단에 걸려 **모든 사용자의 백분위가 100%**가 된다.")

    print()
    print("=" * 78)
    if failures:
        print(f"부호 규약 위반: {len(CASES)}건 중 {failures}건")
        print()
        print("수정 방법 — app/pose/angles.py 의 _horizontal_tilt_angle 마지막 줄:")
        print()
        print("    -    return math.degrees(math.atan2(dy, dx))")
        print("    +    return math.degrees(math.atan2(dy, abs(dx)))")
        print()
        print("영향 범위: get_shoulder_tilt_angle, get_pelvis_tilt_angle,")
        print("           insight/posture_percentile.py, PostureInsightResponse 전체")
    else:
        print("모든 케이스가 규약과 일치합니다 (이미 수정된 상태로 보입니다).")
    print("=" * 78)


if __name__ == "__main__":
    main()
