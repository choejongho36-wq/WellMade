"""
app/pose/dtw_template_store.py 단위 테스트 — S3 → 로컬 캐시 → 디렉토리 3단계 폴백 순서
(2026-08-28 추가).

실제 S3에 접속하지 않는다 — _fetch_bundle_from_s3()를 monkeypatch로 갈아끼워 "성공"/
"실패" 두 경우만 흉내낸다. harness.py/hyperextension_llm_check.py 테스트는 client
객체를 인자로 주입하는 DI 패턴을 쓰지만, 이 모듈은 client를 인자로 받지 않고 환경변수로
설정을 읽는 구조라(load_templates_for_store는 harness.py의 decide_next_action(client=...)
같은 주입 파라미터가 없음) monkeypatch로 내부 함수 자체를 갈아끼우는 쪽이 더 간단하다 —
test_api.py의 monkeypatch 기반 통합 테스트와 동일한 이유의 선택.
"""

import json
from pathlib import Path

import pytest

import app.pose.dtw_template_store as store
from app.pose.dtw_matching import (
    DEFAULT_METRIC_FIELDS,
    build_template,
    compute_normalization,
    extract_metric_matrix,
    save_templates_bundle,
)

REAL_TEMPLATE_DIR = Path(__file__).parent.parent / "app" / "pose" / "dtw_templates"
REAL_TEMPLATE_COUNT = 20  # test_dtw_matching.py의 실제 배포 템플릿 회귀 테스트와 동일한 전제


@pytest.fixture
def one_simple_template():
    frames = [
        {
            "knee_angle": k,
            "hip_angle": h,
            "torso_length_ratio": 1.0,
            "shoulder_forward_lean_deg": 0.0,
        }
        for k, h in zip([170, 130, 90, 130, 170], [170, 140, 100, 140, 170])
    ]
    norm = compute_normalization(
        extract_metric_matrix(frames, DEFAULT_METRIC_FIELDS), DEFAULT_METRIC_FIELDS
    )
    return [build_template("normal", "rep_a", frames, norm)]


def _clear_s3_env(monkeypatch):
    monkeypatch.delenv(store.S3_BUCKET_ENV_VAR, raising=False)
    monkeypatch.delenv(store.S3_KEY_ENV_VAR, raising=False)
    monkeypatch.delenv(store.S3_REGION_ENV_VAR, raising=False)


def _bundle_bytes(templates):
    return json.dumps(
        [
            {
                "label": t.label,
                "source": t.source,
                "metric_fields": list(t.metric_fields),
                "normalization": t.normalization.to_dict(),
                "curve": t.curve.tolist(),
            }
            for t in templates
        ]
    ).encode("utf-8")


def test_falls_back_to_directory_when_s3_env_not_set(tmp_path, monkeypatch):
    _clear_s3_env(monkeypatch)
    result = store.load_templates_for_store(REAL_TEMPLATE_DIR, cache_path=tmp_path / "no_cache.json")
    assert len(result) == REAL_TEMPLATE_COUNT


def test_uses_local_cache_when_s3_not_configured_but_cache_exists(tmp_path, monkeypatch, one_simple_template):
    _clear_s3_env(monkeypatch)
    cache_path = tmp_path / "cache.json"
    save_templates_bundle(one_simple_template, cache_path)

    # 디렉토리 쪽엔 존재하지 않는 경로를 줘서, 결과가 정말 캐시에서 왔다는 걸 확인한다
    # (디렉토리 폴백이었다면 load_templates()가 빈 리스트를 반환했을 것).
    result = store.load_templates_for_store(tmp_path / "no_such_dir", cache_path=cache_path)
    assert len(result) == 1
    assert result[0].source == "rep_a"


def test_fetches_from_s3_and_writes_local_cache(tmp_path, monkeypatch, one_simple_template):
    monkeypatch.setenv(store.S3_BUCKET_ENV_VAR, "fake-bucket")
    monkeypatch.setenv(store.S3_KEY_ENV_VAR, "fake-key.json")
    monkeypatch.setenv(store.S3_REGION_ENV_VAR, "us-east-1")

    bundle_bytes = _bundle_bytes(one_simple_template)
    monkeypatch.setattr(store, "_fetch_bundle_from_s3", lambda bucket, key, region: bundle_bytes)

    cache_path = tmp_path / "cache.json"
    assert not cache_path.exists()
    result = store.load_templates_for_store(tmp_path / "no_such_dir", cache_path=cache_path)

    assert len(result) == 1
    assert result[0].source == "rep_a"
    assert cache_path.exists()  # S3에서 받아온 뒤 다음 실패에 대비해 로컬 캐시에도 저장돼야 한다
    assert cache_path.read_bytes() == bundle_bytes


def test_falls_back_to_cache_when_s3_fetch_fails(tmp_path, monkeypatch, one_simple_template):
    monkeypatch.setenv(store.S3_BUCKET_ENV_VAR, "fake-bucket")
    monkeypatch.setenv(store.S3_KEY_ENV_VAR, "fake-key.json")
    monkeypatch.setenv(store.S3_REGION_ENV_VAR, "us-east-1")
    # 권한 문제·네트워크 장애 등을 흉내 — 실제 _fetch_bundle_from_s3()도 이런 경우 None을 반환한다.
    monkeypatch.setattr(store, "_fetch_bundle_from_s3", lambda bucket, key, region: None)

    cache_path = tmp_path / "cache.json"
    save_templates_bundle(one_simple_template, cache_path)

    result = store.load_templates_for_store(tmp_path / "no_such_dir", cache_path=cache_path)
    assert len(result) == 1
    assert result[0].source == "rep_a"


def test_falls_back_to_directory_when_s3_fails_and_no_cache(tmp_path, monkeypatch):
    monkeypatch.setenv(store.S3_BUCKET_ENV_VAR, "fake-bucket")
    monkeypatch.setenv(store.S3_KEY_ENV_VAR, "fake-key.json")
    monkeypatch.setenv(store.S3_REGION_ENV_VAR, "us-east-1")
    monkeypatch.setattr(store, "_fetch_bundle_from_s3", lambda bucket, key, region: None)

    result = store.load_templates_for_store(REAL_TEMPLATE_DIR, cache_path=tmp_path / "no_cache.json")
    assert len(result) == REAL_TEMPLATE_COUNT


def test_partial_s3_env_skips_s3_and_falls_back_to_directory(tmp_path, monkeypatch):
    # 버킷/키/리전 셋 중 하나라도 비어있으면 S3 자체를 시도하지 않아야 한다 —
    # hyperextension_llm_check.py의 "설정 안 됨 → 폴백" 판단과 동일한 원칙(부분 설정은
    # 미설정과 동일하게 취급).
    monkeypatch.setenv(store.S3_BUCKET_ENV_VAR, "fake-bucket")
    monkeypatch.delenv(store.S3_KEY_ENV_VAR, raising=False)
    monkeypatch.delenv(store.S3_REGION_ENV_VAR, raising=False)

    def _fail_if_called(*args, **kwargs):
        raise AssertionError("S3 설정이 불완전한데도 _fetch_bundle_from_s3가 호출됐습니다.")

    monkeypatch.setattr(store, "_fetch_bundle_from_s3", _fail_if_called)

    result = store.load_templates_for_store(REAL_TEMPLATE_DIR, cache_path=tmp_path / "no_cache.json")
    assert len(result) == REAL_TEMPLATE_COUNT


def test_fetch_bundle_from_s3_returns_none_without_boto3(monkeypatch):
    # boto3가 설치돼 있지 않은 환경(이 저장소의 로컬 개발 환경 포함 — requirements.txt에는
    # 있지만 아직 pip install 안 됐을 수 있음) 시뮬레이션.
    monkeypatch.setattr(store, "_BOTO3_AVAILABLE", False)
    result = store._fetch_bundle_from_s3("fake-bucket", "fake-key.json", "us-east-1")
    assert result is None
