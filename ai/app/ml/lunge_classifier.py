"""
런지 자세 ML 기반 보조 판정 (전통 ML, 포트폴리오/비교실험 목적).

왜 이 모듈이 필요한가?
- 프로젝트 기본 원칙은 "규칙기반 우선"이고(rules.py 주석 참고), 그 원칙은 지금도 유효하다.
- 다만 실제 사용자 요청으로 "전통 ML을 직접 구현해서 규칙기반과 비교해보는" 포트폴리오용
  작업을 별도로 진행하기로 했다 (정확도 문제를 해결하려는 목적이 아님 — 프로젝트 문서
  claude/wellmade-ai-progress.md 참고).
- 그래서 이 모듈은 기존 규칙기반 판정(judge_static_pose, judge_realtime_coaching)을
  대체하지 않고, 완전히 별도인 엔드포인트(/ai/ml/lunge/analyze)로만 노출된다. 프론트가
  이 결과를 실제로 사용할지, "참고용 2차 의견"으로만 보여줄지는 팀이 정할 문제다.
- 학습 데이터는 NgoQuocBao1010/Exercise-Correction 레포의 err.train.csv/err.test.csv
  (실제 참가자 영상 기반 정상/이상 라벨). 학습 스크립트는 ai/ml_training/에 있고,
  원본 CSV는 용량 문제로 git에 커밋하지 않는다(.gitignore) — 재현하려면 ml_training/README.md
  참고. 실제로 서버가 로딩하는 건 학습 결과물인 이 아래 .joblib 파일뿐이다.
"""

from pathlib import Path

import joblib

from app.ml.features import extract_lunge_features
from app.schemas import Landmark

MODEL_PATH = Path(__file__).resolve().parent / "models" / "lunge_form_classifier.joblib"

# 모듈을 import할 때마다 디스크에서 모델을 다시 읽으면 요청마다 지연이 생기므로,
# 최초 1회만 로딩해서 프로세스 메모리에 캐싱해둔다 (전형적인 lazy singleton 패턴).
_model_bundle = None


def _load_model() -> dict:
    global _model_bundle
    if _model_bundle is None:
        if not MODEL_PATH.exists():
            raise RuntimeError(
                f"ML 모델 파일을 찾을 수 없습니다: {MODEL_PATH}\n"
                "ai/ml_training/train_lunge_classifier.py를 먼저 실행해서 모델을 생성하세요."
            )
        _model_bundle = joblib.load(MODEL_PATH)
    return _model_bundle


def classify_lunge_form(landmarks: list[Landmark]) -> dict:
    """
    랜드마크에서 특징을 뽑아 학습된 파이프라인(StandardScaler + 분류기)으로
    정상/이상을 예측한다.

    확률(correct_probability)까지 반환하는 이유: 이진 판정만 주면 "애매하게 정상"과
    "명백하게 정상"을 구분할 수 없어, 규칙기반 confidence와 마찬가지로 하네스(AI-07)가
    이 값을 보고 다음 행동(예: 규칙기반과 의견이 갈리면 더 신뢰도 높은 쪽 채택)을
    스스로 판단하기 어렵기 때문이다.
    """
    bundle = _load_model()
    pipeline = bundle["pipeline"]

    features = [extract_lunge_features(landmarks)]
    prediction = pipeline.predict(features)[0]  # 1=정상(C), 0=이상(L)
    # predict_proba가 반환하는 열 순서는 pipeline.classes_ 순서를 따르므로, 인덱스로
    # 가정하지 않고 클래스 값(1)을 직접 찾아 매칭한다 — 학습 데이터 클래스 순서가 바뀌어도
    # 안전하게 동작하도록 하기 위함.
    proba = dict(zip(pipeline.classes_, pipeline.predict_proba(features)[0]))
    correct_probability = float(proba.get(1, 0.0))

    return {
        "is_normal": bool(prediction == 1),
        "correct_probability": round(correct_probability, 4),
        "model_name": bundle.get("model_name", "unknown"),
    }
