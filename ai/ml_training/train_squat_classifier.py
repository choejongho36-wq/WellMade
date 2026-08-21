"""
스쿼트 자세 다중분류(정상/얕음/무릎모임/발뒤꿈치뜸/좌우비대칭) ML 모델 학습 스크립트.

런지 학습 스크립트(train_lunge_classifier.py)와 달리, 이 데이터셋(Kaggle
"Squat Exercise Pose Dataset", thashmiladewmini)은 원본 landmark 좌표가 아니라 이미
계산된 관절 각도/자세 지표 12개 컬럼을 CSV로 제공한다. 그래서 여기서는 랜드마크 →
Landmark 객체 변환 과정이 없고, 그중 우리가 재현 가능한 6개 컬럼만 그대로 읽어 쓴다.

데이터 출처: https://www.kaggle.com/datasets/thashmiladewmini/squat-exercise-pose-dataset
정상(label=0) 자세는 실제 유튜브 영상에서 추출한 값이고, 이상 라벨(1~5)은 정상 데이터의
특정 값을 인위적으로 왜곡(perturb)해서 합성한 데이터라는 점이 README에 명시되어 있다
(런지 데이터와 달리 실제 "틀린 동작" 촬영이 아님 — 프로젝트 문서 참고).

왜 label=2(상체 숙임/forward lean)를 학습에서 아예 제외하는가?
- 이 데이터셋은 label=2에서 spine_angle/torso_lean만 왜곡하고 hip_angle은 그대로 둔다.
  우리는 spine_angle/torso_lean의 원본 계산식을 몰라 재현할 수 없으므로(feature.py 주석
  참고), 이 6개 특징만으로는 label=0과 label=2가 통계적으로 거의 구별되지 않는다(실험 결과
  macro F1 ~0.08). 상체 숙임은 이미 rules.py의 hip_angle 정상범위 검사가 규칙기반으로
  담당하므로, ML 모델의 책임 범위에서 제외하는 게 "각 방식이 잘하는 일을 맡는다"는 원칙에
  맞다고 판단했다.

실행 방법:
    cd ai
    python3 -m ml_training.train_squat_classifier

전제조건: ml_training/data/squat/squat_features_augmented.csv (용량 문제로 git 미포함,
ml_training/README.md의 데이터 준비 방법 참고).
"""

import sys
from pathlib import Path

import joblib
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

AI_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(AI_ROOT))

from app.ml.features import SQUAT_FEATURE_NAMES  # noqa: E402
from app.ml.squat_labels import SQUAT_LABEL_NAMES  # noqa: E402

DATA_PATH = Path(__file__).resolve().parent / "data" / "squat" / "squat_features_augmented.csv"
MODEL_OUT = AI_ROOT / "app" / "ml" / "models" / "squat_form_classifier.joblib"

EXCLUDED_LABEL = 2  # 상체 숙임(forward lean) — 규칙기반이 담당, 사유는 위 docstring 참고


def load_dataset():
    df = pd.read_csv(DATA_PATH)
    df = df[df["label"] != EXCLUDED_LABEL]
    X = df[SQUAT_FEATURE_NAMES].to_numpy()
    y = df["label"].to_numpy()
    return X, y


def main():
    if not DATA_PATH.exists():
        raise FileNotFoundError(
            f"{DATA_PATH} 가 없습니다. ml_training/README.md의 데이터 준비 방법을 참고하세요."
        )

    print("데이터 로딩 중...")
    X, y = load_dataset()
    print(f"총 {len(X)}건 (label=2 제외), 특징: {SQUAT_FEATURE_NAMES}")
    print(f"클래스 분포: {[(int(lbl), int((y == lbl).sum())) for lbl in sorted(set(y))]}")

    # Kaggle 데이터라 별도 test.csv가 없으므로, 여기서 80/20 stratified split을 직접 만든다.
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    # 런지 쪽(train_lunge_classifier.py)과 다르게 SVC를 후보에서 뺐다 — 데이터가 약 4만 건
    # (런지의 2배 이상)이라 커널 기반 SVC는 학습에 수 분이 걸리는데도 테스트 정확도는 오히려
    # 더 낮았다(직접 비교 실험: 61%). RandomForest도 max_depth 제한 없이 쓰면 모델 파일이
    # 300MB를 넘어가 git/기기 전송에 부담이 되므로 depth를 제한했다. 대신 HistGradientBoosting을
    # 추가했는데, 트리 개수가 많아도 내부적으로 히스토그램 기반이라 모델 용량이 훨씬 작으면서도
    # (수 MB) 정확도는 depth 무제한 RandomForest와 비슷하게 나온다(직접 비교 실험 기준).
    candidates = {
        # scikit-learn 1.5+에서는 다중분류 시 자동으로 multinomial 방식을 쓰므로 별도 옵션 불필요.
        "LogisticRegression": LogisticRegression(max_iter=2000),
        "RandomForest": RandomForestClassifier(n_estimators=150, max_depth=12, random_state=42),
        "HistGradientBoosting": HistGradientBoostingClassifier(max_iter=300, random_state=42),
    }

    best_name, best_pipeline, best_test_acc = None, None, -1.0
    for name, clf in candidates.items():
        pipeline = Pipeline([("scaler", StandardScaler()), ("clf", clf)])
        pipeline.fit(X_train, y_train)
        test_acc = accuracy_score(y_test, pipeline.predict(X_test))
        print(f"[{name}] 테스트 정확도={test_acc:.4f}")
        if test_acc > best_test_acc:
            best_name, best_pipeline, best_test_acc = name, pipeline, test_acc

    print(f"\n최종 선택 모델: {best_name} (테스트 정확도 {best_test_acc:.4f})")
    label_order = sorted(SQUAT_LABEL_NAMES.keys() - {EXCLUDED_LABEL})
    print(
        classification_report(
            y_test,
            best_pipeline.predict(X_test),
            labels=label_order,
            target_names=[f"{lbl}:{SQUAT_LABEL_NAMES[lbl]}" for lbl in label_order],
        )
    )

    MODEL_OUT.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(
        {
            "pipeline": best_pipeline,
            "feature_names": SQUAT_FEATURE_NAMES,
            "model_name": best_name,
            "excluded_label": EXCLUDED_LABEL,
        },
        MODEL_OUT,
    )
    print(f"모델 저장 완료: {MODEL_OUT}")


if __name__ == "__main__":
    main()
