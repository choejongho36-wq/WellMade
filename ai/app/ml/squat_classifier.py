"""
스쿼트 자세 ML 기반 다중분류 보조 판정 (전통 ML, 포트폴리오/비교실험 목적).

런지(lunge_classifier.py)는 이진분류(정상/이상)였지만, 스쿼트는 "어떤 오류인지"까지
다중분류로 구분한다 — 사용자가 "라벨별로 맞는 교정 문구를 보내달라"고 명시적으로 요청했기
때문 (정상/이상만 구분해서는 "무릎을 모으지 마세요" 같은 구체적 코칭을 줄 수 없다).

이 모듈이 반환하는 coaching_message는 "TTS로 바로 읽을 수 있는 한국어 텍스트"까지다.
실제 음성 변환(TTS 엔진 호출)은 프론트엔드가 담당한다는 원칙을 이번에 사용자와 다시
확인했다 (session 2026-08-18, claude/wellmade-ai-progress.md 참고) — AI 서버가 오디오
파일까지 만들지는 않는다.

label=2(상체 숙임)는 이 모델의 판정 대상이 아니다 (이미 rules.py의 hip_angle 검사가
담당 — 자세한 이유는 app/ml/features.py, ml_training/train_squat_classifier.py 참고).
"""

from pathlib import Path

import joblib

from app.ml.features import extract_squat_features
from app.ml.squat_labels import SQUAT_COACHING_MESSAGES, SQUAT_LABEL_NAMES
from app.schemas import Landmark

MODEL_PATH = Path(__file__).resolve().parent / "models" / "squat_form_classifier.joblib"

_model_bundle = None


def _load_model() -> dict:
    global _model_bundle
    if _model_bundle is None:
        if not MODEL_PATH.exists():
            raise RuntimeError(
                f"ML 모델 파일을 찾을 수 없습니다: {MODEL_PATH}\n"
                "ai/ml_training/train_squat_classifier.py를 먼저 실행해서 모델을 생성하세요."
            )
        _model_bundle = joblib.load(MODEL_PATH)
    return _model_bundle


def classify_squat_form(landmarks: list[Landmark]) -> dict:
    """
    랜드마크에서 특징을 뽑아 학습된 다중분류 파이프라인으로 스쿼트 오류 유형을 예측하고,
    라벨에 맞는 한국어 교정 문구를 함께 반환한다.

    correct_probability는 "정상(label=0)일 확률"만 뽑아서 반환한다 — 규칙기반 confidence,
    런지 ML 응답과 필드 이름을 통일해 프론트가 값을 다룰 때 일관된 방식으로 처리할 수
    있게 하기 위함.
    """
    bundle = _load_model()
    pipeline = bundle["pipeline"]

    features = [extract_squat_features(landmarks)]
    predicted_label = int(pipeline.predict(features)[0])
    proba = dict(zip(pipeline.classes_, pipeline.predict_proba(features)[0]))
    correct_probability = float(proba.get(0, 0.0))

    return {
        "predicted_label": predicted_label,
        "label_name": SQUAT_LABEL_NAMES.get(predicted_label, "알 수 없음"),
        "is_normal": predicted_label == 0,
        "correct_probability": round(correct_probability, 4),
        "coaching_message": SQUAT_COACHING_MESSAGES.get(predicted_label),
        "model_name": bundle.get("model_name", "unknown"),
    }
