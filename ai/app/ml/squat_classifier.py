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

# 알려진 신뢰도 문제 (2026-08-21, 실제 사진 테스트로 발견) — 팀 확정 필요
사용자가 실제 사진으로 테스트한 결과 정상 자세도 label=3(무릎 모임)/label=4(발뒤꿈치 뜸)로
자주 오탐되는 문제가 확인됐다. 조사 결과 두 가지 서로 다른 원인이 겹쳐 있었다:

1. **발뒤꿈치 뜸(label=4) — train/serve skew**: 학습에 쓴 Kaggle 데이터셋
   (squat_features_augmented.csv)의 ankle_angle 컬럼이 실제로 어떤 공식으로 계산됐는지
   공개돼 있지 않은데, 우리는 이 컬럼이 우리 calculate_angle(knee, ankle, foot_index)와
   같은 방식일 거라 가정하고 그대로 재사용했다. 값 범위를 직접 비교해보니 전혀 다른
   스케일이었다(예: 실측 랜드마크로 계산한 "정상적인 깊은 스쿼트"의 ankle_angle이 90~170대인
   반면, 학습 데이터의 label=0 ankle_angle은 대부분 16~75 사이였음) — 그래서 실측 입력을
   넣으면 모델이 거의 항상 label=4 쪽으로 예측한다. 이 문제는 이 데이터셋만으로는 고칠 수
   없다(원본 landmark 좌표가 없어 우리 방식으로 재계산이 불가능 — features.py 주석 참고).
   → 실시간 판정에서는 이 예측 대신 app/pose/rules.py의 규칙기반 검사
   (get_heel_lift_ratio 기반)로 대체했다.
2. **무릎 모임(label=3) — 관측 자체가 불가능**: 무릎 모임(knee valgus)은 좌우(관상면) 판단이라
   정면에 가까운 촬영이 있어야 관측할 수 있는데, 이 앱의 스쿼트/런지 판정은 측면 촬영을
   전제로 한다(schemas.py의 Side 설명 참고, 2026-08-21 사용자에게 재확인함). 즉 이 모델이
   무릎 모임을 맞추려면 애초에 측면 랜드마크에 없는 정보가 필요하다 — 학습 데이터에 있는
   knee_lateral 컬럼(좌우 편차)은 우리가 재현 불가능해 특징에서 아예 제외했으므로(features.py
   참고), label=3 예측은 knee_angle(깊이) 같은 무관한 특징에 의존한 우연한 상관관계일
   가능성이 높다. **좌우비대칭(label=5)도 같은 이유로 신뢰할 수 없다** — 측면 촬영으로는
   한쪽 다리만 보이므로 좌우를 비교할 근거 자체가 없다.

결론: 이 엔드포인트가 신뢰할 수 있게 예측하는 건 사실상 label=0(정상)/label=1(얕음) 정도이고,
그마저도 rules.py의 knee_angle 깊이 검사와 대부분 겹친다. 그래도 이 모듈 자체는 지우지
않았다 — 애초 목적이 "포트폴리오/비교실험"(전통 ML 실제 구현 경험)이었고, 이 발견 자체가
그 비교실험에서 나온 유의미한 결과이기 때문이다(왜 정면 촬영이 필요한지, 왜 train/serve
skew가 위험한지를 실측으로 보여줌). 다만 이 예측 결과를 실제 코칭 문구로 사용자에게 그대로
노출하면 안 된다 — TODO: 팀 확정 필요, 프론트가 이 엔드포인트 결과를 어떻게(숨김 / "실험적"
라벨 표시 / 미노출) 다룰지 결정 필요.
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
