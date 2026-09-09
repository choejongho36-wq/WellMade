"""
MVP4 도구 레이어 단위 테스트.

핵심 검증 대상은 "LLM이 이상한 도구 호출을 했을 때 코드가 막는가"다.
실제 API는 호출하지 않는다.
"""

import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.agent_tools import TOOL_NAMES, TOOL_SCHEMAS, ToolError, run_tool


def make_side_analysis(is_reliable=True, issues=None):
    return {
        "success": True,
        "view": "side",
        "near_side": "left",
        "near_side_determined": True,
        "quality": {"is_valid": True, "issue": ""},
        "reliability": {"is_reliable": is_reliable, "issues": issues or []},
        "confidence": 0.9,
        "keypoint_confidence": [
            {"name": "left_ear", "visibility": 0.9, "band": "높음"},
            {"name": "left_hip", "visibility": 0.55, "band": "보통"},
        ],
        "forward_head": {"angle_deg": -13.2, "verdict": "정상", "note": "임상 단일 기준 없음"},
        "round_shoulder": {"angle_deg": 80.2, "verdict": "정상", "note": "C7은 근사값"},
        "disclaimer": "참고용",
    }


def make_front_analysis():
    return {
        "success": True,
        "quality": {"is_valid": True, "issue": ""},
        "reliability": {"is_reliable": True, "issues": []},
        "confidence": 0.94,
        "keypoint_confidence": [],
        "shoulder": {"angle_deg": 2.3, "verdict": "정상"},
        "pelvis": {"angle_deg": -0.8, "verdict": "정상", "note": "잠정 구간"},
        "disclaimer": "참고용",
    }


# --- 스키마 자체 ---------------------------------------------------------


def test_all_schemas_have_required_fields():
    for schema in TOOL_SCHEMAS:
        assert "name" in schema
        assert "description" in schema
        assert "input_schema" in schema


def test_calculation_tools_are_not_exposed():
    # 회귀 방지(MVP4_설계.md §3): 계산 함수를 도구로 노출하면 LLM이 임의
    # 좌표로 다른 각도를 만들어낼 수 있게 되어, MVP1~3의 검증 계층을
    # 통째로 우회하게 된다.
    forbidden = {"calculate_shoulder_tilt", "calculate_forward_head",
                 "calculate_shoulder_angle", "approximate_c7", "detect_keypoints"}
    assert not (TOOL_NAMES & forbidden)


# --- 화이트리스트 / 인자 검증 ----------------------------------------------


def test_unregistered_tool_raises_tool_error():
    with pytest.raises(ToolError) as exc:
        run_tool("delete_everything", {}, make_side_analysis())
    assert "등록되지 않은" in str(exc.value)


def test_non_dict_args_rejected():
    with pytest.raises(ToolError):
        run_tool("lookup_normal_range", "not-a-dict", make_side_analysis())


def test_lookup_normal_range_rejects_unknown_metric():
    with pytest.raises(ToolError) as exc:
        run_tool("lookup_normal_range", {"metric": "nonexistent"}, make_side_analysis())
    # 에러 메시지가 사용 가능한 지표를 알려줘야 LLM이 스스로 고칠 수 있다
    assert "사용 가능한 지표" in str(exc.value)


def test_get_metric_note_rejects_metric_not_in_this_analysis():
    # 측면 분석에 shoulder(정면 지표)를 물어보면 거부해야 한다
    with pytest.raises(ToolError) as exc:
        run_tool("get_metric_note", {"metric": "shoulder"}, make_side_analysis())
    assert "사용 가능" in str(exc.value)


# --- 정상 동작 -----------------------------------------------------------


def test_get_analysis_summary_side():
    out = run_tool("get_analysis_summary", {}, make_side_analysis())
    assert out["view"] == "side"
    assert out["forward_head"]["verdict"] == "정상"
    assert out["round_shoulder"]["verdict"] == "정상"
    # angle_deg는 넘기지 않는다 — 숫자를 재료로 주면 LLM이 문구에 옮겨
    # 쓴다(test_analysis_summary_contains_no_numbers 참고).
    assert "angle_deg" not in out["forward_head"]
    # 영문 랜드마크 이름이 아니라 한국어 부위명이 나가야 한다 — LLM에게
    # 번역을 맡기면 부정확해진다(실측: left_hip -> "왼쪽 엉덩이").
    assert out["low_confidence_points"] == ["왼쪽 골반"]
    assert "left_hip" not in str(out)


def test_get_analysis_summary_front():
    out = run_tool("get_analysis_summary", {}, make_front_analysis())
    # 대외 이름(NORMAL_RANGES 키)으로 통일 — 다른 도구가 쓰는 이름과
    # 같아야 LLM이 이름을 찾아 헤매지 않는다(실측: 정면에서 도구를 8번
    # 부르며 이름을 추측하는 사례).
    assert out["shoulder_tilt"]["verdict"] == "정상"
    assert "pelvis_tilt" in out


def test_summary_keys_match_metric_note_names():
    # 회귀 방지: get_analysis_summary가 반환한 키를 그대로 get_metric_note에
    # 넣으면 반드시 성공해야 한다. 이 두 도구가 다른 이름 체계를 쓰던 것이
    # 실측에서 발견된 혼란의 원인이었다.
    for analysis in (make_side_analysis(), make_front_analysis()):
        summary = run_tool("get_analysis_summary", {}, analysis)
        metric_names = [k for k in summary if k not in ("view", "low_confidence_points")]
        assert metric_names, "지표가 하나도 없음"
        for name in metric_names:
            out = run_tool("get_metric_note", {"metric": name}, analysis)
            assert out["metric"] == name


def test_summary_keys_are_valid_lookup_metrics():
    # get_analysis_summary의 키는 lookup_normal_range에도 그대로 통해야 한다.
    for analysis in (make_side_analysis(), make_front_analysis()):
        summary = run_tool("get_analysis_summary", {}, analysis)
        metric_names = [k for k in summary if k not in ("view", "low_confidence_points")]
        for name in metric_names:
            out = run_tool("lookup_normal_range", {"metric": name}, analysis)
            assert out["in_this_analysis"] is True


def test_lookup_flags_metric_not_in_this_analysis():
    # 정면 분석인데 측면 지표를 조회하는 경우. 차단하지 않고 표시만 한다 —
    # "정면 결과를 설명하며 측면 촬영을 권하는" 맥락을 막지 않기 위함이다.
    out = run_tool("lookup_normal_range", {"metric": "round_shoulder"}, make_front_analysis())
    assert out["in_this_analysis"] is False
    assert "결과인 것처럼" in out["note"]


def test_get_analysis_summary_excludes_raw_data():
    # MVP2 build_payload와 같은 철학 — 이미지/원본 좌표/파일명은 안 넘긴다
    out = run_tool("get_analysis_summary", {}, make_side_analysis())
    assert "keypoints" not in out
    assert "near_side" not in out
    assert "disclaimer" not in out


def test_lookup_normal_range_returns_source():
    out = run_tool("lookup_normal_range", {"metric": "round_shoulder"}, make_side_analysis())
    assert out["metric"] == "round_shoulder"
    assert "Thigpen" in out["source"]


def test_get_metric_note_returns_limitation():
    out = run_tool("get_metric_note", {"metric": "round_shoulder"}, make_side_analysis())
    assert "C7" in out["note"]


def test_explain_reliability_translates_issue_codes():
    analysis = make_side_analysis(
        is_reliable=False, issues=["not_a_side_profile:shoulder_x_gap(0.2496)"]
    )
    out = run_tool("explain_reliability", {}, analysis)
    assert out["is_reliable"] is False
    # 코드 문자열이 아니라 사람이 읽을 수 있는 설명이어야 한다 — LLM이
    # 숫자를 오독할 여지를 없애기 위해 해석은 코드가 미리 해준다
    assert "옆을 향하지 않은" in out["issues"][0]
    assert "0.2496" not in out["issues"][0]


def test_explain_reliability_passes_through_unknown_code():
    analysis = make_side_analysis(is_reliable=False, issues=["some_new_code"])
    out = run_tool("explain_reliability", {}, analysis)
    assert out["issues"] == ["some_new_code"]


# --- 숫자 미노출 (핵심 회귀 방지) ------------------------------------------


def _contains_digit(value) -> bool:
    """
    측정 수치가 노출됐는지 검사한다.

    "C7"(경추 7번)은 해부학 용어라 제거 대상이 아니다 — 지우면 의미가
    깨진다. 검사에서도 제외한다.
    """
    text = json.dumps(value, ensure_ascii=False).replace("C7", "")
    return bool(re.search(r"\d", text))


def test_analysis_summary_contains_no_numbers():
    # 도구가 숫자를 넘기면 LLM이 그걸 문구에 옮겨 써서 validate_comment의
    # 숫자 금지 검사에 걸린다(실측: 도구 호출이 6건으로 늘자 폴백 발생).
    # 애초에 재료를 주지 않는다.
    for analysis in (make_side_analysis(), make_front_analysis()):
        out = run_tool("get_analysis_summary", {}, analysis)
        assert not _contains_digit(out), f"숫자가 노출됨: {out}"


def test_lookup_normal_range_contains_no_numbers():
    from app.thresholds import NORMAL_RANGES

    for metric in NORMAL_RANGES:
        out = run_tool("lookup_normal_range", {"metric": metric}, make_side_analysis())
        assert not _contains_digit(out), f"{metric}에서 숫자가 노출됨: {out}"


def test_lookup_normal_range_still_conveys_direction():
    # 숫자를 빼도 판정 방향은 전달되어야 한다 — 안 그러면 LLM이 근거를
    # 설명할 수 없다.
    out = run_tool("lookup_normal_range", {"metric": "round_shoulder"}, make_side_analysis())
    assert "criterion" in out and out["criterion"]
    assert "이하" in out["criterion"] or "초과" in out["criterion"]


def test_get_metric_note_contains_no_numbers():
    # round_shoulder의 note에는 원래 "기준각 52도"가 들어 있다
    out = run_tool("get_metric_note", {"metric": "round_shoulder"}, make_side_analysis())
    assert not _contains_digit(out), f"숫자가 노출됨: {out}"
    assert "C7" in out["note"]  # 한계 정보 자체는 남아야 한다


def test_explain_reliability_strips_numbers_from_unknown_codes():
    analysis = make_side_analysis(
        is_reliable=False, issues=["brand_new_check(0.2496)"]
    )
    out = run_tool("explain_reliability", {}, analysis)
    assert not _contains_digit(out), f"숫자가 노출됨: {out}"
