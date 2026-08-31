"""
app/coaching/llm_model_compare.py("6랩 블라인드 테스트" 다중 벤더 Bedrock Converse API
비교 도구)와 /ai/dev/llm-model-compare 엔드포인트 테스트.

hyperextension_llm_check.py 테스트(tests/test_api.py)와 동일한 DI 패턴 — 실제 AWS를
호출하지 않고 가짜 클라이언트(_FakeBedrockRuntimeClient)를 주입해 결정적으로 검증한다.
"""

from fastapi.testclient import TestClient

from app.coaching.llm_model_compare import compare_models
from app.main import app

client = TestClient(app)


def _rep(id_, true_label=None, n_frames=5):
    frames = [
        {
            "timestamp": i * 0.15,
            "knee_angle": 90.0 + i,
            "hip_angle": 80.0 + i,
            "torso_length_ratio": 2.0,
            "shoulder_forward_lean_deg": 5.0,
        }
        for i in range(n_frames)
    ]
    entry = {"id": id_, "frames": frames}
    if true_label is not None:
        entry["true_label"] = true_label
    return entry


class _FakeBedrockRuntimeClient:
    """converse()가 model_id별로 미리 정해둔 verdict를 돌려주는 가짜 클라이언트.
    model_id가 _error_models에 있으면 예외를 던져 "일부 모델 실패해도 나머지는 정상
    처리"를 검증할 수 있게 한다."""

    def __init__(self, verdict_by_model, error_models=frozenset()):
        self._verdict_by_model = verdict_by_model
        self._error_models = error_models

    def converse(self, modelId, system, messages, toolConfig, inferenceConfig=None):
        if modelId in self._error_models:
            raise RuntimeError("모델 접근권한이 없습니다(시뮬레이션).")
        verdict, confidence = self._verdict_by_model[modelId]
        return {
            "output": {
                "message": {
                    "content": [
                        {
                            "toolUse": {
                                "name": "report_hip_hyperextension_verdict",
                                "input": {
                                    "verdict": verdict,
                                    "confidence": confidence,
                                    "reasoning": "테스트용 근거",
                                },
                            }
                        }
                    ]
                }
            },
            "usage": {"inputTokens": 100, "outputTokens": 20},
        }


def test_compare_models_computes_accuracy_per_model():
    reps = [
        _rep("우혁_과신전", true_label="과신전"),
        _rep("우혁_정상", true_label="정상"),
    ]
    fake_client = _FakeBedrockRuntimeClient(
        verdict_by_model={
            "model-a": ("과신전_의심", "상"),  # 둘 다 실제로는 과신전_의심 -> 2번째 렙은 오답
            "model-b": ("정상", "중"),  # 둘 다 실제로는 정상 -> 1번째 렙은 오답
        }
    )
    result = compare_models(
        reps=reps,
        model_ids=["model-a", "model-b"],
        region="ap-northeast-2",
        client_factory=lambda region: fake_client,
    )

    assert result["accuracy"]["model-a"] == 0.5  # 과신전 렙만 맞춤
    assert result["accuracy"]["model-b"] == 0.5  # 정상 렙만 맞춤
    assert result["results"]["model-a"]["우혁_과신전"]["verdict"] == "과신전_의심"
    assert result["results"]["model-b"]["우혁_정상"]["verdict"] == "정상"
    assert result["results"]["model-a"]["우혁_과신전"]["latency_ms"] >= 0


def test_compare_models_without_true_label_gives_none_accuracy():
    reps = [_rep("렙1")]  # true_label 없음
    fake_client = _FakeBedrockRuntimeClient(verdict_by_model={"model-a": ("정상", "상")})
    result = compare_models(
        reps=reps, model_ids=["model-a"], region="ap-northeast-2",
        client_factory=lambda region: fake_client,
    )
    assert result["accuracy"]["model-a"] is None


def test_compare_models_one_model_fails_others_still_succeed():
    reps = [_rep("렙1", true_label="정상")]
    fake_client = _FakeBedrockRuntimeClient(
        verdict_by_model={"model-ok": ("정상", "상"), "model-bad": ("정상", "상")},
        error_models={"model-bad"},
    )
    result = compare_models(
        reps=reps, model_ids=["model-ok", "model-bad"], region="ap-northeast-2",
        client_factory=lambda region: fake_client,
    )
    assert result["results"]["model-ok"]["렙1"]["verdict"] == "정상"
    assert "error" in result["results"]["model-bad"]["렙1"]
    assert result["accuracy"]["model-ok"] == 1.0
    assert result["accuracy"]["model-bad"] == 0.0  # 실패는 오답으로 집계(verdict 없음)


def test_compare_models_no_client_returns_error():
    result = compare_models(
        reps=[_rep("렙1")], model_ids=["model-a"], region="ap-northeast-2",
        client_factory=lambda region: None,
    )
    assert result["results"] == {}
    assert result["accuracy"] == {}
    assert result["error"]


def test_llm_model_compare_endpoint_missing_region_returns_error_not_500(monkeypatch):
    monkeypatch.delenv("AWS_BEDROCK_REGION", raising=False)
    res = client.post(
        "/ai/dev/llm-model-compare",
        json={
            "reps": [
                {
                    "id": "렙1",
                    "frames": [
                        {"timestamp": 0.0, "knee_angle": 90.0, "hip_angle": 80.0}
                    ],
                }
            ],
            "model_ids": ["model-a"],
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["results"] == {}
    assert body["error"]


def test_llm_model_compare_endpoint_uses_injected_compare_models(monkeypatch):
    import app.main as main_module

    def fake_compare_models(reps, model_ids, region):
        assert region == "ap-northeast-2"
        return {
            "results": {"model-a": {"렙1": {"verdict": "정상", "confidence": "상", "reasoning": "ok", "latency_ms": 10}}},
            "accuracy": {"model-a": 1.0},
        }

    monkeypatch.setattr(main_module, "compare_models", fake_compare_models)
    res = client.post(
        "/ai/dev/llm-model-compare",
        json={
            "reps": [
                {"id": "렙1", "true_label": "정상", "frames": [{"timestamp": 0.0, "knee_angle": 90.0, "hip_angle": 80.0}]}
            ],
            "model_ids": ["model-a"],
            "region": "ap-northeast-2",
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["results"]["model-a"]["렙1"]["verdict"] == "정상"
    assert body["accuracy"]["model-a"] == 1.0


if __name__ == "__main__":
    test_compare_models_computes_accuracy_per_model()
    test_compare_models_without_true_label_gives_none_accuracy()
    test_compare_models_one_model_fails_others_still_succeed()
    test_compare_models_no_client_returns_error()
    print("모든 llm_model_compare 테스트 통과 (pytest 없이 직접 실행)")
