"""
자세 비교 인사이트(AI-15, 신규)용 참조 분포 데이터 전처리 스크립트.

세종특별자치시 공공데이터(data.go.kr id 15128996, "세종 똑똑건강 앱" 자세 측정 내역,
21,609건)를 내려받아, "같은 성별·비슷한 연령대에서 내 어깨/골반 기울기가 몇 %에
해당하는가"를 계산할 때 쓸 참조 분포(성별×연령대별 기울기 각도 분포)로 가공한다.

왜 원본 CSV를 그대로 서버에 두지 않고 미리 가공해서 작은 JSON으로 만드는가?
1) 원본은 5.6MB에 pandas 의존성까지 필요해, 매 요청마다 읽고 파싱하면 실시간
   응답에 불필요한 지연이 생긴다. 참조 분포(정렬된 각도 리스트)만 뽑아두면
   런타임에는 표준 라이브러리(bisect)만으로 백분위를 계산할 수 있다.
2) 원본 CSV는 "측정일자/측정시간"별 개별 측정 기록이라, 같은 사용자가 앱을 자주 쓸수록
   그 사람의 상태가 참조 분포에 여러 번 중복 반영된다(최대 321회 중복 확인됨).
   이러면 "여러 번 측정한 소수의 극단값"이 백분위를 왜곡할 수 있으므로,
   사용자당 최신 측정 1건만 남기고 나머지는 버린다(중복 제거).

왜 percentile을 "부호 있는 기울기"가 아니라 "기울기 크기(절대값)"로 계산하는가?
- 사용자가 요청한 인사이트는 "왼쪽 어깨가 2도 올라간 상태입니다. 비슷한 연령대에서는
  39%에 해당합니다"처럼 "이 정도 기울어진 정도가 얼마나 흔한가/심한가"를 말해주는
  것이지, "왼쪽으로 기운 사람 중 몇 등인가"가 아니다. 방향(왼쪽/오른쪽)은 그대로
  텍스트에 표기하고, 백분위는 방향과 무관하게 "기울어진 정도"만으로 계산한다.

# TODO: 팀 확정 필요 — 이 백분위의 정확한 의미(값이 클수록 "더 심하다"는 뜻인지,
# 단순히 "이 정도인 사람이 이만큼 있다"는 뜻인지)는 사용자 테스트로 문구를 다듬을 필요가
# 있다. 현재는 "abs(기울기) <= 내 abs(기울기)인 참조 인구 비율"로 정의했다(표준적인
# 백분위 순위 정의).
"""

import json
import re
from collections import defaultdict
from pathlib import Path

import pandas as pd

CSV_PATH = Path(__file__).parent / "data" / "posture" / "sejong_posture.csv"
OUTPUT_PATH = Path(__file__).parent.parent / "app" / "insight" / "data" / "posture_reference.json"

# 세종시 데이터는 21,609건이 3,732명의 반복 측정으로 이루어져 있다(위 docstring 참고).
# 연령대(10년 단위) x 성별로 나누면 60대 이상 구간의 표본이 급격히 줄어드므로(70대 26~55명,
# 80대 1~4명), 60대 이상은 하나로 묶어 표본을 확보한다.
# TODO: 팀 확정 필요 — 연령대 구간을 10년 단위로 자를지, 다른 기준(생애주기 등)을 쓸지는
# 제품 방향에 따라 재검토 필요.
MAX_BRACKET = 60  # 60 이상은 전부 "60대 이상"으로 합침
BRACKET_SIZE = 10


def parse_tilt_degrees(text: str) -> float | None:
    """
    '왼쪽 어깨가 2도 올라간 상태입니다.' / '좌우 골반의 정렬이 좋습니다.' 같은
    자연어 소견 문장에서 부호 있는 기울기 각도를 뽑아낸다.
    양수 = 왼쪽이 올라감, 음수 = 오른쪽이 올라감, 0 = 정렬이 좋음(기울기 없음).
    패턴이 매칭되지 않으면(예상 밖의 문장 형식) None을 반환해 해당 행을 건너뛰게 한다.
    """
    if not isinstance(text, str):
        return None
    text = text.strip()
    if "정렬이 좋습니다" in text:
        return 0.0
    match = re.search(r"(왼쪽|오른쪽)\s*(?:어깨|골반)?[가이]\s*(\d+(?:\.\d+)?)도", text)
    if not match:
        return None
    degrees = float(match.group(2))
    return degrees if match.group(1) == "왼쪽" else -degrees


def age_bracket(age: int) -> int:
    """나이를 10년 단위 연령대로 변환하되, MAX_BRACKET 이상은 모두 묶는다."""
    bracket = (age // BRACKET_SIZE) * BRACKET_SIZE
    return min(max(bracket, 10), MAX_BRACKET)


def main():
    df = pd.read_csv(CSV_PATH, encoding="cp949")

    df["shoulder_tilt_deg"] = df["어깨 기울기 소견"].apply(parse_tilt_degrees)
    df["pelvis_tilt_deg"] = df["골반 기울기 소견"].apply(parse_tilt_degrees)
    df["measured_at"] = pd.to_datetime(df["측정일자"] + " " + df["측정시간"], errors="coerce")

    # 파싱 실패 행 제거 (예상 밖 문장 형식 — 드물지만 있을 수 있으므로 방어적으로 처리)
    before = len(df)
    df = df.dropna(subset=["shoulder_tilt_deg", "pelvis_tilt_deg", "measured_at"])
    print(f"파싱 성공: {len(df)}/{before}행")

    # 사용자당 최신 측정 1건만 남긴다 (중복 반영 방지 — docstring 참고)
    df = df.sort_values("measured_at").groupby("사용자 고유번호").tail(1).copy()
    print(f"중복 제거 후: {len(df)}행 (고유 사용자 수와 동일해야 함)")

    df["age"] = 2026 - df["사용자 출생년도"]
    df["age_bracket"] = df["age"].apply(age_bracket)

    # (성별, 연령대) -> {"shoulder": [절대값 정렬 리스트], "pelvis": [...], "sample_size": n}
    reference: dict = defaultdict(lambda: {"shoulder": [], "pelvis": []})
    for _, row in df.iterrows():
        key = f"{row['성별']}_{row['age_bracket']}"
        reference[key]["shoulder"].append(abs(row["shoulder_tilt_deg"]))
        reference[key]["pelvis"].append(abs(row["pelvis_tilt_deg"]))

    output = {}
    for key, vals in reference.items():
        shoulder_sorted = sorted(vals["shoulder"])
        pelvis_sorted = sorted(vals["pelvis"])
        output[key] = {
            "sample_size": len(shoulder_sorted),
            "shoulder_abs_deg_sorted": shoulder_sorted,
            "pelvis_abs_deg_sorted": pelvis_sorted,
        }
        print(f"{key}: n={len(shoulder_sorted)}")

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\n저장 완료: {OUTPUT_PATH} ({OUTPUT_PATH.stat().st_size / 1024:.1f} KB)")


if __name__ == "__main__":
    main()
