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

## 데이터 준비

원본 학습 데이터(CSV)는 용량 문제로 git에 커밋하지 않았다 (`.gitignore`에
`ml_training/data/` 추가됨). 다시 받으려면:

```bash
git clone --depth 1 https://github.com/NgoQuocBao1010/Exercise-Correction.git /tmp/exercise-correction
mkdir -p ml_training/data/lunge
cp /tmp/exercise-correction/core/lunge_model/err.train.csv ml_training/data/lunge/
cp /tmp/exercise-correction/core/lunge_model/err.test.csv ml_training/data/lunge/
```

이 데이터는 실제 참가자들이 런지를 수행한 영상에서 MediaPipe로 추출한 랜드마크 좌표에
정상(`C`)/이상(`L`) 라벨이 붙어있다 (합성 데이터 아님).

## 실행

```bash
cd ai
source .venv/bin/activate
pip install -r requirements.txt   # scikit-learn, joblib 포함
python3 -m ml_training.train_lunge_classifier
```

LogisticRegression / RandomForest / SVC 세 알고리즘을 5-fold 교차검증으로 비교하고,
테스트셋 정확도가 가장 높은 모델을 `app/ml/models/lunge_form_classifier.joblib`로 저장한다.
이 파일은 (용량이 작으므로) git에 커밋되어 있어서, 학습을 다시 돌리지 않아도 서버는 바로
동작한다.

## 특징(feature) 설계

`app/ml/features.py`의 `extract_lunge_features()`를 학습·추론 양쪽에서 공유해서
쓴다 (train/serve skew 방지). 자세한 설계 이유는 그 파일의 주석을 참고.
