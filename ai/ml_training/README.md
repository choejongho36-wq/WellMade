# ML 학습 스크립트 (오프라인 전용)

`app/`는 FastAPI 서버 실행 코드이고, 이 폴더(`ml_training/`)는 그 서버가 쓰는 ML 모델
파일(`app/ml/models/*.joblib`)을 만들어내는 **오프라인 학습 스크립트** 모음이다. 서버가
직접 이 폴더의 코드를 import하지 않는다 — 학습은 사람이 필요할 때 한 번 실행하는 작업이고,
그 결과물(.joblib)만 서버가 로딩해서 쓴다.

## 왜 이 폴더가 필요한가 (배경)

프로젝트 기본 원칙은 "규칙기반 우선, 파인튜닝 금지"다(`app/pose/rules.py` 주석 참고).
이 폴더는 그 원칙을 깨는 게 아니라, **별도 실험**으로 전통 ML을 실제로 구현해보고
규칙기반과 비교하기 위해 추가했다 (정확도 문제 해결이 아니라 포트폴리오/구현 경험 목적 —
자세한 배경은 프로젝트 문서 `claude/wellmade-ai-progress.md` 참고). 그래서 학습된 모델은
기존 규칙기반 판정을 대체하지 않고, 완전히 별도인 `/ai/ml/lunge/analyze` 엔드포인트로만
노출된다.

## 모델 두 개

| 운동 | 학습 스크립트 | 분류 방식 | 데이터 출처 |
|---|---|---|---|
| 런지 | `train_lunge_classifier.py` | 이진(정상/이상) | Exercise-Correction 레포 (실촬영) |
| 스쿼트 | `train_squat_classifier.py` | 다중분류(5클래스, 오류 유형별) | Kaggle Squat Exercise Pose Dataset (일부 합성) |

## 데이터 준비

원본 학습 데이터(CSV)는 용량 문제로 git에 커밋하지 않았다 (`.gitignore`에
`ml_training/data/` 추가됨). 다시 받으려면:

**런지**
```bash
git clone --depth 1 https://github.com/NgoQuocBao1010/Exercise-Correction.git /tmp/exercise-correction
mkdir -p ml_training/data/lunge
cp /tmp/exercise-correction/core/lunge_model/err.train.csv ml_training/data/lunge/
cp /tmp/exercise-correction/core/lunge_model/err.test.csv ml_training/data/lunge/
```
실제 참가자들이 런지를 수행한 영상에서 MediaPipe로 추출한 랜드마크 좌표에 정상(`C`)/
이상(`L`) 라벨이 붙어있다 (합성 데이터 아님).

**스쿼트**
```
https://www.kaggle.com/datasets/thashmiladewmini/squat-exercise-pose-dataset
```
위 페이지에서 로그인 후 `squat_features_augmented.csv`를 받아 `ml_training/data/squat/`에
둔다. 정상(label=0) 자세는 실제 유튜브 영상 기반이지만, 이상 라벨(1~5)은 정상 데이터의
특정 값을 수치적으로 왜곡(perturb)해서 합성한 데이터라는 점이 원본 README에 명시돼 있다 —
런지 데이터보다 신뢰도가 낮다고 봐야 한다 (자세한 배경은 프로젝트 문서 참고).

## 실행

```bash
cd ai
source .venv/bin/activate
pip install -r requirements.txt   # scikit-learn, joblib, pandas 포함
python3 -m ml_training.train_lunge_classifier
python3 -m ml_training.train_squat_classifier
```

둘 다 LogisticRegression / RandomForest / SVC를 비교해 테스트셋 정확도가 가장 높은 모델을
`app/ml/models/*.joblib`로 저장한다. 이 파일들은 (용량이 작으므로) git에 커밋되어 있어서,
학습을 다시 돌리지 않아도 서버는 바로 동작한다. 스쿼트 학습은 SVC 비교 단계에서 수 분 정도
걸릴 수 있다 (데이터가 약 4만 건이라 커널 기반 모델이 느림).

## 특징(feature) 설계

`app/ml/features.py`의 `extract_lunge_features()` / `extract_squat_features()`를
학습·추론 양쪽에서 공유해서 쓴다 (train/serve skew 방지). 특히 스쿼트 쪽은 원본 데이터셋의
12개 컬럼 중 우리가 직접 재현 가능한 6개(좌우 무릎/엉덩이/발목 각도)만 골라 쓴 이유와,
그로 인해 "상체 숙임(forward lean)" 오류를 이 모델의 판정 범위에서 제외한 이유가 그 파일과
`train_squat_classifier.py` 주석에 자세히 설명되어 있다 — 재현 전에 꼭 읽어볼 것.
