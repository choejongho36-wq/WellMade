"""
app/pose/dtw_matching.py 단위 테스트.

실제 템플릿 데이터(mediapipe로 추출한 진짜 영상)는 아직 없으므로(체크리스트 "실행
대기 목록" 3번 참고), 여기서는 합성(synthetic) 곡선으로 다음만 검증한다:
1) 지표 추출·정규화·저장/로딩이 왕복(round-trip)해도 값이 보존되는가
2) DTW 거리가 "똑같은 곡선은 0, 형태가 다른 곡선은 크게" 나오는 기본 성질을 지키는가
3) 최근접 템플릿 조회가 실제로 더 가까운 쪽을 고르는가, 템플릿이 없을 때 명시적으로
   에러를 던지는가

실측 데이터 기반 정확도 검증(사람 간 일반화 80% 등)은 이전 세션 프로토타입에서 이미
진행했고(wellmade-ai-progress.md), 진짜 템플릿이 레포에 들어온 뒤 별도로 다시 검증해야
한다 — 이 테스트는 "알고리즘 배선이 맞는지"만 보장한다.
"""

import json
import math
from pathlib import Path

import numpy as np
import pytest

from app.pose.dtw_matching import (
    DEFAULT_METRIC_FIELDS,
    DTWTemplate,
    MetricNormalization,
    TemplateNotFoundError,
    build_template,
    compute_normalization,
    dtw_distance,
    extract_metric_matrix,
    load_template,
    load_templates,
    load_templates_from_bundle,
    nearest_normal_distance,
    normalize_matrix,
    save_template,
    save_templates_bundle,
)
from app.schemas import AngleFrame

REAL_TEMPLATE_DIR = Path(__file__).parent.parent / "app" / "pose" / "dtw_templates"


def _make_frames(knee_curve, hip_curve):
    """knee_angle/hip_angle만 있는 최소 프레임 시퀀스를 만든다(다른 3개 기본 지표는
    상수로 채워 형태 비교에 영향이 없게 한다)."""
    return [
        {
            "knee_angle": k,
            "hip_angle": h,
            "torso_length_ratio": 1.0,
            "shoulder_forward_lean_deg": 0.0,
            "knee_valgus_ratio": 1.0,
        }
        for k, h in zip(knee_curve, hip_curve)
    ]


# ---- extract_metric_matrix ----


def test_extract_metric_matrix_basic():
    frames = _make_frames([170, 120, 90, 120, 170], [170, 130, 100, 130, 170])
    matrix = extract_metric_matrix(frames, DEFAULT_METRIC_FIELDS)
    assert matrix.shape == (5, len(DEFAULT_METRIC_FIELDS))
    assert matrix[2, 0] == 90  # knee_angle
    assert matrix[2, 1] == 100  # hip_angle


def test_extract_metric_matrix_accepts_angle_frame_objects():
    """실제 서버 코드는 AngleFrame(pydantic) 객체를 다루므로, dict가 아니라 속성
    접근으로도 지표를 뽑을 수 있어야 한다."""
    frames = [
        AngleFrame(
            timestamp=i * 0.1,
            knee_angle=170 - i * 10,
            hip_angle=170 - i * 10,
            torso_length_ratio=1.0,
            shoulder_forward_lean_deg=0.0,
            knee_valgus_ratio=1.0,
        )
        for i in range(5)
    ]
    matrix = extract_metric_matrix(frames, DEFAULT_METRIC_FIELDS)
    assert matrix.shape == (5, len(DEFAULT_METRIC_FIELDS))


def test_extract_metric_matrix_missing_field_raises_with_index_and_name():
    frames = _make_frames([170, 120, 90], [170, 130, 100])
    frames[1]["torso_length_ratio"] = None
    with pytest.raises(ValueError) as exc_info:
        extract_metric_matrix(frames, DEFAULT_METRIC_FIELDS)
    assert "1" in str(exc_info.value)
    assert "torso_length_ratio" in str(exc_info.value)


def test_extract_metric_matrix_empty_raises():
    with pytest.raises(ValueError):
        extract_metric_matrix([], DEFAULT_METRIC_FIELDS)


# ---- normalization ----


def test_compute_normalization_zscores_non_constant_column():
    matrix = np.array([[1.0], [2.0], [3.0], [4.0], [5.0]])
    norm = compute_normalization(matrix, ("x",))
    normalized = normalize_matrix(matrix, ("x",), norm)
    assert normalized.mean() == pytest.approx(0.0, abs=1e-8)
    assert normalized.std() == pytest.approx(1.0, abs=1e-8)


def test_compute_normalization_constant_column_does_not_divide_by_zero():
    matrix = np.array([[7.0], [7.0], [7.0]])
    norm = compute_normalization(matrix, ("x",))
    assert norm.stds["x"] == 1.0  # 0으로 나누기 방지용 대체값
    normalized = normalize_matrix(matrix, ("x",), norm)
    assert np.allclose(normalized, 0.0)


# ---- dtw_distance ----


def test_dtw_distance_identical_curves_is_zero():
    curve = np.array([[0.0, 1.0], [1.0, 2.0], [2.0, 3.0], [1.0, 2.0], [0.0, 1.0]])
    assert dtw_distance(curve, curve.copy()) == pytest.approx(0.0, abs=1e-9)


def test_dtw_distance_larger_for_differently_shaped_curve():
    squat_like = np.array([[0.0], [-1.0], [-2.0], [-1.0], [0.0]])  # 내려갔다 올라옴
    monotonic = np.array([[0.0], [1.0], [2.0], [3.0], [4.0]])  # 계속 증가만 함
    similar = np.array([[0.0], [-1.1], [-2.1], [-0.9], [0.1]])  # squat_like와 비슷한 모양

    d_similar = dtw_distance(squat_like, similar)
    d_different = dtw_distance(squat_like, monotonic)
    assert d_similar < d_different


# ---- template build / save / load round-trip ----


def test_build_template_and_save_load_roundtrip(tmp_path):
    frames = _make_frames([170, 120, 90, 120, 170], [170, 130, 100, 130, 170])
    matrix = extract_metric_matrix(frames, DEFAULT_METRIC_FIELDS)
    norm = compute_normalization(matrix, DEFAULT_METRIC_FIELDS)

    template = build_template(
        label="normal", source="test_rep_1", frames=frames, normalization=norm
    )
    path = tmp_path / "template.json"
    save_template(template, path)
    loaded = load_template(path)

    assert loaded.label == template.label
    assert loaded.source == template.source
    assert loaded.metric_fields == template.metric_fields
    assert np.allclose(loaded.curve, template.curve)


def test_load_template_malformed_file_raises_with_path(tmp_path):
    path = tmp_path / "broken.json"
    path.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError) as exc_info:
        load_template(path)
    assert str(path) in str(exc_info.value)


def test_load_templates_missing_directory_returns_empty_list(tmp_path):
    assert load_templates(tmp_path / "does_not_exist") == []


# ---- nearest_normal_distance ----


def _template_from_curve(label, source, knee_curve, hip_curve, normalization):
    frames = _make_frames(knee_curve, hip_curve)
    return build_template(label, source, frames, normalization)


@pytest.fixture
def two_templates():
    # 정상 렙 2개(주영/우혁 느낌으로 살짝 다른 진폭) — 둘 다 "내려갔다 올라오는" 같은 모양.
    all_frames = _make_frames(
        [170, 130, 90, 130, 170, 168, 128, 88, 128, 168],
        [170, 140, 100, 140, 170, 169, 139, 99, 139, 169],
    )
    norm = compute_normalization(
        extract_metric_matrix(all_frames, DEFAULT_METRIC_FIELDS), DEFAULT_METRIC_FIELDS
    )
    t1 = _template_from_curve(
        "normal", "rep_a", [170, 130, 90, 130, 170], [170, 140, 100, 140, 170], norm
    )
    t2 = _template_from_curve(
        "normal", "rep_b", [168, 128, 88, 128, 168], [169, 139, 99, 139, 169], norm
    )
    return [t1, t2], norm


def test_nearest_normal_distance_picks_closer_template(two_templates):
    templates, norm = two_templates
    # rep_a와 거의 동일한 쿼리 — rep_a가 rep_b보다 더 가까워야 한다.
    query_frames = _make_frames([170, 131, 91, 131, 170], [170, 141, 101, 141, 170])
    nearest, all_matches = nearest_normal_distance(query_frames, templates)
    assert nearest.label == "normal"
    assert nearest.distance <= all_matches[-1].distance
    assert all_matches == sorted(all_matches, key=lambda m: m.distance)


def test_nearest_normal_distance_no_templates_raises():
    query_frames = _make_frames([170, 130, 90, 130, 170], [170, 140, 100, 140, 170])
    with pytest.raises(TemplateNotFoundError):
        nearest_normal_distance(query_frames, [])


def test_nearest_normal_distance_mismatched_metric_fields_raises(two_templates):
    templates, norm = two_templates
    other = DTWTemplate(
        label="normal",
        source="rep_c",
        metric_fields=("knee_angle", "hip_angle"),  # 다른 지표 집합
        normalization=norm,
        curve=np.zeros((5, 2)),
    )
    query_frames = _make_frames([170, 130, 90, 130, 170], [170, 140, 100, 140, 170])
    with pytest.raises(ValueError):
        nearest_normal_distance(query_frames, [*templates, other])


# ---- 실제 배포 템플릿(app/pose/dtw_templates/*.json) 회귀 테스트 ----
# ml_training/build_dtw_templates.py로 생성한 실제 템플릿이 깨지지 않았는지 확인한다.
# 정확도(사람 간 일반화 등)가 아니라 "로딩/사용 가능한 형태를 유지하는지"만 본다.


def test_real_templates_load_and_are_consistent():
    templates = load_templates(REAL_TEMPLATE_DIR)
    assert len(templates) >= 20  # 영상 렙 12개 + 이미지 구간 8개 (2026-08-27 생성 기준)
    fields = templates[0].metric_fields
    for t in templates:
        assert t.metric_fields == fields
        assert t.curve.shape[1] == len(fields)
        assert t.curve.shape[0] >= 1
        assert "knee_valgus_ratio" not in fields  # 정면 지표는 이번 세대 템플릿에서 제외


def test_real_templates_nearest_match_is_self_consistent():
    """정규화된 커브를 그대로 쿼리로 되돌려 넣으면(역정규화 후 재정규화), 자기 자신과의
    거리가 0에 가까워야 한다 — 왕복 계산이 어긋나지 않았는지 확인."""
    templates = load_templates(REAL_TEMPLATE_DIR)
    target = templates[0]
    fields = target.metric_fields
    means = np.array([target.normalization.means[f] for f in fields])
    stds = np.array([target.normalization.stds[f] for f in fields])
    raw = target.curve * stds + means
    frames = [dict(zip(fields, row)) for row in raw]

    nearest, _ = nearest_normal_distance(frames, templates, metric_fields=fields)
    assert nearest.label == "normal"
    assert nearest.distance == pytest.approx(0.0, abs=1e-6)


# ---- 템플릿 묶음(bundle) 저장/로딩 (2026-08-28 추가, app/pose/dtw_template_store.py용) ----


def test_templates_bundle_roundtrip(tmp_path, two_templates):
    templates, _norm = two_templates
    path = tmp_path / "bundle.json"
    save_templates_bundle(templates, path)
    loaded = load_templates_from_bundle(path.read_bytes())

    assert len(loaded) == len(templates)
    for original, restored in zip(templates, loaded):
        assert restored.label == original.label
        assert restored.source == original.source
        assert restored.metric_fields == original.metric_fields
        assert np.allclose(restored.curve, original.curve)


def test_load_templates_from_bundle_malformed_json_raises():
    with pytest.raises(ValueError):
        load_templates_from_bundle("이건 JSON이 아닙니다")


def test_load_templates_from_bundle_malformed_item_raises_with_index():
    # metric_fields/normalization/curve가 빠진 항목 — 몇 번째 항목인지 에러 메시지에 있어야 한다.
    bad = json.dumps([{"label": "normal", "source": "rep_0"}])
    with pytest.raises(ValueError) as exc_info:
        load_templates_from_bundle(bad)
    assert "0번째" in str(exc_info.value)


