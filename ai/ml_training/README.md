# 오프라인 전처리 스크립트

`app/`는 FastAPI 서버 실행 코드이고, 이 폴더(`ml_training/`)는 그 서버가 쓰는 참조 분포
데이터(`app/insight/data/*.json`)를 만들어내는 **오프라인 스크립트** 모음이다. 서버가 직접 이 폴더의 코드를 import하지 않는다 — 전처리는 사람이 필요할 때 한 번
실행하는 작업이고, 그 결과물만 서버가 로딩해서 쓴다.

## 스쿼트/런지 ML 학습 스크립트는 삭제됨 (2026-08-21)

이 폴더에는 원래 `train_lunge_classifier.py`/`train_squat_classifier.py`(전통 ML 분류기
학습, 포트폴리오/비교실험 목적)도 있었다. 실제 사진으로 테스트한 결과 스쿼트 쪽에서 정상
자세도 오탐되는 신뢰도 문제가 확인됐고(train/serve skew + 측면 촬영만으로는 애초에 관측
불가능한 항목 — 자세한 배경은 프로젝트 문서 `claude/wellmade-ai-progress.md` 참고), 카메라
전제를 "측면 단독"에서 "측면 + 정면 듀얼"로 바꾸면서 ML 모델 두 개를 전부 삭제하고
규칙기반 판정(`app/pose/rules.py`, `app/pose/angles.py`)으로 완전히 대체했다. 학습
스크립트, 특징 추출(`app/ml/features.py`), 저장된 모델 파일(`app/ml/models/*.joblib`),
`/ai/ml/lunge/analyze`·`/ai/ml/squat/analyze` 엔드포인트 모두 함께 제거했다.

## 참조 분포 데이터 (또래 비교 인사이트)

| 스크립트 | 만드는 것 | 용도 | 데이터 출처 | 통계 연도 |
|---|---|---|---|---|
| `prepare_posture_reference.py` | `app/insight/data/posture_reference.json` | 성별×연령대별 어깨/골반 기울기 백분위 비교 | 세종특별자치시_자세 측정 내역 (공공데이터포털) | 2024 측정분 |
| `prepare_bmi_reference.py` | `app/insight/data/bmi_reference.json` | 성별×연령대별 BMI 백분위 비교 (`/ai/inbody/bmi-insight`) | 질병관리청 국민건강통계 표15-4 체질량지수 분포 | **2024 (스크립트에 하드코딩)** |
| `prepare_nutrition_reference.py` | `app/insight/data/nutrition_reference.json` | 성별×연령대별 영양 섭취 평균 비교 (`/ai/nutrition/peer-compare`) | 질병관리청 국민건강통계 (국민건강영양조사) | **2024 (스크립트에 하드코딩)** |

이건 분류 모델을 학습하는 게 아니라, "같은 성별·연령대에서 내 값이 어디쯤인지"를 계산할 때 쓸
참조 데이터를 미리 만들어두는 전처리 스크립트다. 자세한 배경(왜 원본을 그대로 안 쓰는지,
백분위/평균 대비 비율을 어떻게 정의했는지)은 각 스크립트와 `app/insight/*.py` 주석 참고.

> **통계 연도는 자동으로 갱신되지 않는다.** BMI/영양 두 스크립트는 엑셀에서 `'24` 열을 찾도록
> 연도가 박혀 있고(`SURVEY_YEAR_HEADER`, 표 레이아웃 상수), 결과 JSON의 `source`/`survey_year`도
> 그 값을 그대로 쓴다. 2025 국민건강통계가 나오면 **스크립트의 연도 상수를 고치고 다시 실행**해야
> 하며, 표 레이아웃이 바뀌었을 수 있으니 열 위치 상수도 함께 확인해야 한다.
> (자세 데이터는 세종시가 파일을 새로 올릴 때만 갱신 대상이다.)

**데이터 준비**

```
https://www.data.go.kr/data/15128996/fileData.do
```
위 페이지에서 "다운로드" 버튼으로 `세종특별자치시_자세 측정 내역_20241231.csv`를 받아
`ml_training/data/posture/sejong_posture.csv`에 둔다 (로그인 불필요, cp949 인코딩 CSV,
21,609행). 세종시가 운영하는 "세종 똑똑건강 앱"의 실측정 데이터로, 사용자 고유번호/측정
일시/성별/출생년도/행정동/어깨·골반·척추·경추 소견 문장으로 구성되어 있다.

**실행**

```bash
cd ai
source .venv/bin/activate
python3 -m ml_training.prepare_posture_reference
```

사용자당 최신 측정 1건만 남기고(반복 방문자가 참조 분포를 왜곡하지 않도록), 연령대를
10년 단위(60대 이상은 통합)로 나눠 성별×연령대별 절대 기울기 각도를 정렬된 리스트로 저장한다.
결과 JSON은 82KB 정도로 작아서 git에 커밋되어 있다 — 원본 CSV(5.6MB)는 다른 학습 데이터와
마찬가지로 `ml_training/data/`에 있어 git에 커밋되지 않는다.
