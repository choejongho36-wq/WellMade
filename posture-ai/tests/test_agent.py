"""
MVP4 에이전트 루프 테스트.

MVP2의 test_comment.py와 같은 원칙 — 실제 Claude API를 호출하지 않는다.
가짜 클라이언트로 "LLM이 이런 도구 호출/출력을 했을 때 코드가 어떻게
반응하는가"를 검증한다. 네트워크 의존 테스트는 CI에서 불안정할 뿐 아니라,
정작 확인하고 싶은 것(무한 루프를 막는가, 잘못된 도구를 거부하는가)을
재현할 수 없다.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.agent import MAX_TURNS, run_agent
from app.comment import UNRELIABLE_COMMENT


# --- 가짜 응답 객체 -------------------------------------------------------


class FakeBlock:
    def __init__(self, type, text=None, id=None, name=None, input=None):
        self.type = type
        self.text = text
        self.id = id
        self.name = name
        self.input = input


class FakeResponse:
    def __init__(self, blocks):
        self.content = blocks


class ScriptedClient:
    """
    미리 정해둔 응답 시퀀스를 순서대로 돌려주는 가짜 클라이언트.
    호출 인자를 calls에 기록해 tools 전달 여부 등을 검증할 수 있게 한다.
    """

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []
        self.messages = self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if not self._responses:
            raise AssertionError("가짜 클라이언트의 응답이 소진되었습니다")
        return self._responses.pop(0)


class ExplodingClient:
    def __init__(self, exc):
        self._exc = exc
        self.calls = []
        self.messages = self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        raise self._exc


def text_response(text):
    return FakeResponse([FakeBlock("text", text=text)])


def tool_response(name, input=None, tool_id="tu_1"):
    return FakeResponse([FakeBlock("tool_use", id=tool_id, name=name, input=input or {})])


# --- 테스트용 분석 결과 ---------------------------------------------------


def make_side_analysis(is_reliable=True, success=True):
    return {
        "success": success,
        "view": "side",
        "near_side": "left",
        "near_side_determined": True,
        "quality": {"is_valid": True, "issue": ""},
        "reliability": {"is_reliable": is_reliable, "issues": [] if is_reliable else ["not_a_side_profile"]},
        "confidence": 0.9,
        "keypoint_confidence": [],
        "forward_head": {"angle_deg": -13.2, "verdict": "정상", "note": "임상 단일 기준 없음"},
        "round_shoulder": {"angle_deg": 80.2, "verdict": "정상", "note": "C7은 근사값"},
        "disclaimer": "참고용",
    }


GOOD_TEXT = "전방머리자세 경향은 두드러지지 않는 편입니다. 어깨 말림도 크지 않습니다."


@pytest.fixture(autouse=True)
def no_real_api_calls(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


# --- 게이트: 신뢰도 --------------------------------------------------------


def test_no_llm_call_when_unreliable():
    # MVP2 §5의 가장 중요한 규칙을 에이전트에서도 유지 — 믿을 수 없는
    # 숫자로는 루프를 아예 시작하지 않는다.
    client = ScriptedClient([text_response("쓰이면 안 되는 문구")])
    result = run_agent(make_side_analysis(is_reliable=False), client=client)
    assert result.source == "skipped"
    assert result.reason == "not_reliable"
    assert result.text == UNRELIABLE_COMMENT
    assert client.calls == []


def test_no_llm_call_when_analysis_failed():
    client = ScriptedClient([text_response("쓰이면 안 되는 문구")])
    result = run_agent({"success": False, "reason": "no_person_detected"}, client=client)
    assert result.source == "skipped"
    assert client.calls == []


# --- 정상 루프 -------------------------------------------------------------


def test_direct_answer_without_tool_use():
    result = run_agent(make_side_analysis(), client=ScriptedClient([text_response(GOOD_TEXT)]))
    assert result.source == "agent"
    assert result.text == GOOD_TEXT
    assert result.turns == 1
    assert result.tool_calls == []


def test_tool_use_then_answer():
    client = ScriptedClient([
        tool_response("get_analysis_summary"),
        text_response(GOOD_TEXT),
    ])
    result = run_agent(make_side_analysis(), client=client)
    assert result.source == "agent"
    assert result.turns == 2
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].name == "get_analysis_summary"
    assert result.tool_calls[0].ok is True


def test_multiple_tools_recorded_in_order():
    client = ScriptedClient([
        tool_response("get_analysis_summary", tool_id="a"),
        tool_response("lookup_normal_range", {"metric": "round_shoulder"}, tool_id="b"),
        text_response(GOOD_TEXT),
    ])
    result = run_agent(make_side_analysis(), client=client)
    names = [tc.name for tc in result.tool_calls]
    assert names == ["get_analysis_summary", "lookup_normal_range"]


def test_tools_are_passed_to_api():
    client = ScriptedClient([text_response(GOOD_TEXT)])
    run_agent(make_side_analysis(), client=client)
    assert "tools" in client.calls[0]
    assert len(client.calls[0]["tools"]) >= 4


# --- 경계: 도구 실패 처리 --------------------------------------------------


def test_bad_tool_name_does_not_kill_loop():
    # 도구 하나가 실패해도 LLM이 고칠 기회를 줘야 한다
    client = ScriptedClient([
        tool_response("nonexistent_tool"),
        text_response(GOOD_TEXT),
    ])
    result = run_agent(make_side_analysis(), client=client)
    assert result.source == "agent"
    assert result.tool_calls[0].ok is False
    assert "등록되지 않은" in result.tool_calls[0].error


def test_bad_tool_args_recorded_as_error():
    client = ScriptedClient([
        tool_response("lookup_normal_range", {"metric": "nope"}),
        text_response(GOOD_TEXT),
    ])
    result = run_agent(make_side_analysis(), client=client)
    assert result.tool_calls[0].ok is False
    assert result.source == "agent"


def test_error_result_sent_back_to_llm():
    client = ScriptedClient([
        tool_response("nonexistent_tool"),
        text_response(GOOD_TEXT),
    ])
    run_agent(make_side_analysis(), client=client)
    # 두 번째 호출의 messages에 tool_result(is_error=True)가 들어있어야 한다
    second_messages = client.calls[1]["messages"]
    tool_results = [
        block
        for msg in second_messages
        if isinstance(msg.get("content"), list)
        for block in msg["content"]
        if isinstance(block, dict) and block.get("type") == "tool_result"
    ]
    assert tool_results and tool_results[0]["is_error"] is True


# --- 경계: 루프 상한 -------------------------------------------------------


def test_max_turns_stops_infinite_tool_loop():
    # LLM이 도구만 계속 부르는 상황. 상한이 없으면 비용/지연이 무한대가 된다.
    client = ScriptedClient([tool_response("get_analysis_summary")] * 20)
    result = run_agent(make_side_analysis(), client=client)
    assert result.source == "fallback"
    assert result.reason == "max_turns_exceeded"
    assert result.turns == MAX_TURNS
    assert len(client.calls) == MAX_TURNS


def test_custom_max_turns_respected():
    client = ScriptedClient([tool_response("get_analysis_summary")] * 20)
    result = run_agent(make_side_analysis(), client=client, max_turns=2)
    assert result.turns == 2
    assert len(client.calls) == 2


# --- 경계: 출력 검증 (MVP2 재사용) -----------------------------------------


def test_output_with_number_falls_back():
    # validate_comment를 그대로 재사용하므로 숫자가 있으면 거부된다
    client = ScriptedClient([text_response("고개가 20도 앞으로 나와 있습니다.")])
    result = run_agent(make_side_analysis(), client=client)
    assert result.source == "fallback"
    assert result.reason.startswith("validation_failed")


def test_output_with_forbidden_phrase_falls_back():
    client = ScriptedClient([text_response("일자목 진단이 의심되니 병원을 방문하세요.")])
    result = run_agent(make_side_analysis(), client=client)
    assert result.source == "fallback"
    assert result.reason.startswith("validation_failed")


def test_output_with_wrong_verdict_falls_back():
    client = ScriptedClient([
        text_response("전방머리자세는 정상이지만 어깨는 주의가 필요합니다.")
    ])
    result = run_agent(make_side_analysis(), client=client)
    assert result.source == "fallback"
    assert result.reason.startswith("validation_failed")


def test_fallback_text_itself_passes_validation():
    # 폴백이 규칙을 어기면 안전장치 전체가 무의미해진다
    client = ScriptedClient([text_response("고개가 20도 나왔습니다.")])
    result = run_agent(make_side_analysis(), client=client)
    from app.comment import build_side_payload, validate_comment

    payload = build_side_payload(make_side_analysis())
    assert validate_comment(result.text, payload) == ""


# --- 경계: API 오류 --------------------------------------------------------


def test_api_error_falls_back():
    result = run_agent(make_side_analysis(), client=ExplodingClient(RuntimeError("boom")))
    assert result.source == "fallback"
    assert "api_error" in result.reason


def test_no_api_key_falls_back_without_calling():
    result = run_agent(make_side_analysis())  # client=None, 키 없음
    assert result.source == "fallback"
    assert result.reason == "no_api_key"


# --- 응답 스키마 -----------------------------------------------------------


def test_result_dict_has_agent_fields():
    client = ScriptedClient([
        tool_response("get_analysis_summary"),
        text_response(GOOD_TEXT),
    ])
    out = run_agent(make_side_analysis(), client=client).to_dict()
    assert set(out) >= {"text", "source", "reason", "model", "turns", "tool_calls"}
    assert out["tool_calls"][0]["name"] == "get_analysis_summary"


# --- 서론 제거 -------------------------------------------------------------


def test_preamble_line_is_stripped():
    # 실측(MVP4 실제 API 검증)에서 LLM이 프롬프트 지시를 어기고 서론을
    # 붙였다. 프롬프트만으로는 보장되지 않으므로 코드가 떼어낸다.
    client = ScriptedClient([text_response(f"분석 결과를 설명드리겠습니다.\n{GOOD_TEXT}")])
    result = run_agent(make_side_analysis(), client=client)
    assert result.source == "agent"
    assert result.text == GOOD_TEXT
    assert "설명드리겠습니다" not in result.text


def test_preamble_in_same_line_is_stripped():
    client = ScriptedClient([text_response(f"결과를 말씀드리면. {GOOD_TEXT}")])
    result = run_agent(make_side_analysis(), client=client)
    assert result.text == GOOD_TEXT


def test_normal_text_without_preamble_unchanged():
    client = ScriptedClient([text_response(GOOD_TEXT)])
    result = run_agent(make_side_analysis(), client=client)
    assert result.text == GOOD_TEXT


def test_preamble_only_output_is_not_emptied():
    # 서론만 있고 뒤에 본문이 없으면 통째로 지우지 않고 원문을 유지한다.
    # 지워버리면 빈 문자열이 되어 길이 검증에 걸리는데, 그러면 폴백 사유가
    # "너무 짧음"으로 찍혀서 진짜 원인(서론만 왔다)이 가려진다.
    only_preamble = "분석 결과를 설명드리겠습니다"
    client = ScriptedClient([text_response(only_preamble)])
    result = run_agent(make_side_analysis(), client=client)
    assert result.text == only_preamble


def test_good_news_preamble_is_stripped():
    # 실측(정면 경로 검증)에서 나온 케이스. "좋은 소식입니다"로 시작하는
    # 감탄형 서두는 담백한 톤 지시에 어긋난다.
    client = ScriptedClient([text_response(f"좋은 소식입니다. {GOOD_TEXT}")])
    result = run_agent(make_side_analysis(), client=client)
    assert result.text == GOOD_TEXT


def test_reassuring_closing_is_stripped():
    # 실측에서 나온 케이스: "특별히 걱정하실 필요는 없습니다."
    # 안심시키는 단정은 참고용 서비스의 취지(NFR-04)와 어긋난다.
    client = ScriptedClient([
        text_response(f"{GOOD_TEXT} 특별히 걱정하실 필요는 없습니다.")
    ])
    result = run_agent(make_side_analysis(), client=client)
    assert "걱정하실 필요는 없습니다" not in result.text
    assert "두드러지지 않는" in result.text


def test_preamble_and_closing_both_stripped():
    client = ScriptedClient([
        text_response(f"좋은 소식입니다. {GOOD_TEXT} 안심하셔도 됩니다.")
    ])
    result = run_agent(make_side_analysis(), client=client)
    assert "좋은 소식" not in result.text
    assert "안심하셔도" not in result.text
    assert "두드러지지 않는" in result.text


def test_closing_pattern_in_middle_is_not_stripped():
    # 마지막 문장만 검사하므로, 본문 중간의 비슷한 표현은 건드리지 않는다.
    text = "걱정하실 필요는 없습니다 라는 말은 드리기 어렵습니다. 어깨 말림 경향이 있습니다."
    client = ScriptedClient([text_response(text)])
    result = run_agent(make_side_analysis(), client=client)
    assert result.text == text
