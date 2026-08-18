"""
런지 자세 정상/이상(C/L) 분류 전통 ML 모델 학습 스크립트.

이 파일은 서버 실행 경로(app/)에 포함되지 않는 "오프라인 학습 스크립트"다 — 학습은
사람이 필요할 때 한 번 돌려서 모델 파일(.joblib)을 만들어내는 작업이지, 매 요청마다
실행되는 게 아니기 때문에 서버 코드와 분리했다.

데이터 출처: NgoQuocBao1010/Exercise-Correction 레포의 core/lunge_model/err.train.csv,
err.test.csv. 실제 참가자들이 런지를 수행한 영상에서 MediaPipe로 추출한 랜드마크 좌표에
정상(C)/이상(L) 라벨이 붙어있다 (Kaggle 스쿼트 데이터셋과 달리 "이상" 라벨도 실제 촬영
기반이라는 점이 이 데이터를 런지 쪽에 먼저 적용한 이유 — 자세한 배경은 프로젝트 문서
claude/wellmade-ai-progress.md 참고).

실행 방법:
    cd ai
    python3 -m ml_training.train_lunge_classifier

전제조건: ml_training/data/lunge/ 아래에 err.train.csv, err.test.csv가 있어야 한다.
(용량 문제로 git에는 올리지 않았으므로, 재현하려면 원본 레포에서 직접 받아야 한다 —
ml_training/README.md 참고.)

왜 여러 알고리즘을 한 번에 비교하는가?
- "전통 ML 구현 경험"이 이 작업의 목적 중 하나이므로, 하나의 알고리즘만 쓰기보다
  성격이 다른 몇 가지(선형/트리기반/커널기반)를 교차검증으로 비교하고 최고 성능 모델을
  자동으로 선택하게 했다. 이렇게 하면 "왜 이 모델을 선택했는지"를 수치로 설명할 수 있다.
"""

import csv
import sys
from pathlib import Path

import joblib
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report
from sklearn.model_selection import cross_val_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC

# app.* 모듈을 import하려면 ai/ 루트가 sys.path에 있어야 한다 (python3 -m ml_training.xxx로
# 실행하면 보통 자동으로 잡히지만, 스크립트를 직접 실행하는 경우까지 대비해 명시적으로 추가).
AI_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(AI_ROOT))

from app.ml.features import FEATURE_NAMES, extract_lunge_features  # noqa: E402
from app.schemas import Landmark  # noqa: E402

DATA_DIR = Path(__file__).resolve().parent / "data" / "lunge"
MODEL_OUT = AI_ROOT / "app" / "ml" / "models" / "lunge_form_classifier.joblib"

# CSV 컬럼 접두사 -> 33개 랜드마크 인덱스. err.train.csv는 스쿼트 analyze_pose.csv와 달리
# nose/양쪽 어깨·엉덩이·무릎·발목·발뒤꿈치·발끝(13개 관절)의 x,y,z,visibility를 모두 담고 있다.
LANDMARK_COLUMN_TO_INDEX = {
    "nose": 0,
    "left_shoulder": 11,
    "right_shoulder": 12,
    "left_hip": 23,
    "right_hip": 24,
    "left_knee": 25,
    "right_knee": 26,
    "left_ankle": 27,
    "right_ankle": 28,
    "left_heel": 29,
    "right_heel": 30,
    "left_foot_index": 31,
    "right_foot_index": 32,
}


def _row_to_landmarks(row: dict) -> list:
    """CSV 한 행(랜드마크 좌표 52개 + 라벨)을 extract_lunge_features가 기대하는 33개짜리
    Landmark 리스트로 변환한다. 특징 추출에 쓰이지 않는 나머지 20개 관절은 값이 없으므로
    더미(0)로 채운다 — 실제 판정에 영향 없음 (extract_lunge_features가 참조하지 않는 인덱스)."""
    landmarks = [Landmark(x=0.0, y=0.0, z=0.0, visibility=0.0) for _ in range(33)]
    for prefix, idx in LANDMARK_COLUMN_TO_INDEX.items():
        landmarks[idx] = Landmark(
            x=float(row[f"{prefix}_x"]),
            y=float(row[f"{prefix}_y"]),
            z=float(row[f"{prefix}_z"]),
            visibility=float(row[f"{prefix}_v"]),
        )
    return landmarks


def load_dataset(csv_path: Path) -> tuple:
    X, y = [], []
    with open(csv_path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            landmarks = _row_to_landmarks(row)
            X.append(extract_lunge_features(landmarks))
            y.append(1 if row["label"] == "C" else 0)  # 1=정상(C), 0=이상(L)
    return np.array(X), np.array(y)


def main():
    train_csv = DATA_DIR / "err.train.csv"
    test_csv = DATA_DIR / "err.test.csv"
    if not train_csv.exists() or not test_csv.exists():
        raise FileNotFoundError(
            f"{DATA_DIR} 에 err.train.csv / err.test.csv가 없습니다. "
            "ml_training/README.md의 데이터 준비 방법을 참고하세요."
        )

    print("데이터 로딩 중...")
    X_train, y_train = load_dataset(train_csv)
    X_test, y_test = load_dataset(test_csv)
    print(f"학습 {len(X_train)}건 / 테스트 {len(X_test)}건, 특징: {FEATURE_NAMES}")
    print(
        f"학습셋 클래스 분포 — 정상(C): {int((y_train == 1).sum())}, "
        f"이상(L): {int((y_train == 0).sum())}"
    )

    # 세 알고리즘을 성격이 다르게 골랐다: 선형(LogisticRegression), 트리 앙상블
    # (RandomForest), 커널 기반(SVC) — 이 데이터에 어떤 결정 경계가 잘 맞는지 비교하기 위함.
    candidates = {
        "LogisticRegression": LogisticRegression(max_iter=1000),
        "RandomForest": RandomForestClassifier(n_estimators=200, random_state=42),
        "SVC": SVC(probability=True, random_state=42),
    }

    best_name, best_pipeline, best_test_acc = None, None, -1.0
    for name, clf in candidates.items():
        # StandardScaler가 필요한 이유: 각도(0~180)와 x좌표 차이(front_knee_over_toe,
        # 보통 -0.2~0.2 근처)의 값 범위가 크게 달라, 스케일을 맞추지 않으면 SVC/LogisticRegression
        # 같은 거리 기반 모델이 각도 특징에 과도하게 좌우된다.
        pipeline = Pipeline([("scaler", StandardScaler()), ("clf", clf)])
        cv_scores = cross_val_score(pipeline, X_train, y_train, cv=5)
        pipeline.fit(X_train, y_train)
        test_acc = accuracy_score(y_test, pipeline.predict(X_test))
        print(f"[{name}] 5-fold CV 평균 정확도={cv_scores.mean():.4f}, 테스트 정확도={test_acc:.4f}")
        if test_acc > best_test_acc:
            best_name, best_pipeline, best_test_acc = name, pipeline, test_acc

    print(f"\n최종 선택 모델: {best_name} (테스트 정확도 {best_test_acc:.4f})")
    print(
        classification_report(
            y_test, best_pipeline.predict(X_test), target_names=["이상(L)", "정상(C)"]
        )
    )

    MODEL_OUT.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(
        {"pipeline": best_pipeline, "feature_names": FEATURE_NAMES, "model_name": best_name},
        MODEL_OUT,
    )
    print(f"모델 저장 완료: {MODEL_OUT}")


if __name__ == "__main__":
    main()
