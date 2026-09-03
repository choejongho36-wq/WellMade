"""
BMI 또래 비교용 참조 데이터 전처리 스크립트.

질병관리청 "2024 국민건강통계"의 체질량지수 분포표(표15-4)에서 성별×연령대별
평균과 백분위수(5/10/25/50/75/90/95)를 뽑아 JSON으로 만든다.

영양 섭취(prepare_nutrition_reference.py)와 달리 백분위수가 공개돼 있어서,
"같은 또래 중 상위 몇 %"를 실제로 계산할 수 있다(그 사이 값은 선형보간).

체지방률·골격근량은 이 통계에 없다 — 2024 국민건강통계의 신체계측은 신장/체중/
허리둘레/BMI까지다. 그래서 인바디 항목 중 BMI만 또래 비교가 가능하다.

실행:
    python ml_training/prepare_bmi_reference.py "<2024국민건강통계 엑셀 폴더 경로>"
"""

import json
import re
import sys
from pathlib import Path

import openpyxl

OUTPUT_PATH = Path(__file__).parent.parent / "app" / "insight" / "data" / "bmi_reference.json"

SOURCE_FILE = "15. 비만.xlsx"
SHEET = "4.체질량지수분포"

# 표 레이아웃(2024년 현황표): B=성별 블록, C=구분, D=n, E=평균, F=표준오차, G~M=백분위수
COL_SEX = 1
COL_LABEL = 2
COL_N = 3
COL_MEAN = 4
PERCENTILE_COLUMNS = {5: 6, 10: 7, 25: 8, 50: 9, 75: 10, 90: 11, 95: 12}

AGE_BRACKETS = ["19-29", "30-39", "40-49", "50-59", "60-69", "70+"]
AGE_LABEL_PATTERN = re.compile(r"\d+-\d+|\d+\+")
SEX_LABELS = {"남자": "M", "여자": "F"}


def to_float(value):
    """'2,548', '25.2' 처럼 문자열로 들어있는 칸이 섞여 있어 함께 처리한다."""
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = value.replace(",", "").strip()
        if re.fullmatch(r"-?\d+(\.\d+)?", cleaned):
            return float(cleaned)
    return None


def read_sheet(sheet) -> dict:
    groups: dict = {"M": {}, "F": {}}
    current_sex = None
    in_age_block = False

    for row in sheet.iter_rows(min_row=8, values_only=True):
        sex_label = str(row[COL_SEX]).strip() if row[COL_SEX] else ""
        label = str(row[COL_LABEL]).strip() if len(row) > COL_LABEL and row[COL_LABEL] else ""

        if sex_label in SEX_LABELS:
            current_sex = SEX_LABELS[sex_label]
            in_age_block = False

        if label == "연령(세)":
            in_age_block = True
            continue
        # 거주지역/소득수준 같은 다른 구분 제목을 만나면 연령 블록이 끝난 것
        if label and in_age_block and not AGE_LABEL_PATTERN.fullmatch(label):
            in_age_block = False

        if not (in_age_block and current_sex and label in AGE_BRACKETS):
            continue

        percentiles = {
            str(p): to_float(row[col])
            for p, col in PERCENTILE_COLUMNS.items()
            if len(row) > col and to_float(row[col]) is not None
        }
        mean = to_float(row[COL_MEAN])
        if mean is None or not percentiles:
            continue

        groups[current_sex][label] = {
            "sample_size": int(to_float(row[COL_N]) or 0),
            "mean": mean,
            "percentiles": percentiles,
        }

    return groups


def main() -> None:
    if len(sys.argv) < 2:
        print(f'사용법: python {Path(__file__).name} "<2024국민건강통계 엑셀 폴더 경로>"')
        raise SystemExit(1)

    workbook = openpyxl.load_workbook(Path(sys.argv[1]) / SOURCE_FILE, read_only=True, data_only=True)
    groups = read_sheet(workbook[SHEET])
    workbook.close()

    payload = {
        "source": "질병관리청 2024 국민건강통계 (국민건강영양조사) 표15-4 체질량지수 분포",
        "survey_year": 2024,
        "note": "임신부 제외",
        "groups": groups,
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    total = sum(len(v) for v in groups.values())
    print(f"저장 완료: {OUTPUT_PATH} (성별×연령대 {total}개 그룹)")


if __name__ == "__main__":
    main()
