"""
MVP4: Tool-use 에이전트 루프.

MVP2(comment.py)와의 차이 — 자율성의 위치:
    MVP2에서 LLM은 "무엇을 말할지"만 정했다. 확정된 페이로드를 받아
    문구 하나를 돌려주는 단방향 1회 호출이었다.
    MVP4에서는 "무엇을 알아볼지"도 LLM이 정한다. 어떤 도구를 어떤 순서로
    부를지 스스로 판단하고, 그 결과를 보고 다음 행동을 정한다.

    그만큼 코드가 막아야 할 지점이 늘어난다. MVP2 문서 §9의 표현을 빌리면:
    "자율적으로 도구를 호출하는 만큼 경계를 코드로 강제할 지점이 늘어난다."

이 파일이 강제하는 경계 (MVP4_설계.md §4):
    1. MAX_TURNS 상한 — 루프는 LLM이 판단하는 만큼 늘어나므로 상한이
       없으면 비용과 지연이 예측 불가능해진다. MVP2는 1회 호출이라
       비용이 상수였다.
    2. 도구 화이트리스트 — agent_tools.run_tool이 미등록 도구를 거부한다.
    3. 신뢰도 게이트 — is_reliable=False면 루프를 아예 시작하지 않는다.
       믿을 수 없는 숫자로 에이전트가 추론을 이어가면 그럴듯한 오답이 나온다.
    4. 최종 출력 검증 — MVP2의 validate_comment를 그대로 재사용한다.
       복사하지 않고 import해서 쓰는 것이 이 프로젝트의 원칙(파이프라인
       복사 금지)과 일치한다.
    5. 실패 시 폴백 — 어떤 경우에도 예외를 올리지 않고 결정론적 문구가 나간다.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from .agent_tools import TOOL_SCHEMAS, ToolError, run_tool
from .comment import (
    DEFAULT_MODEL,
    DEFAULT_TIMEOUT_SEC,
    UNRELIABLE_COMMENT,
    PromptPayload,
    SidePromptPayload,
    _default_client,
    _sampling_kwargs,
    build_payload,
    build_side_payload,
    fallback_comment,
    fallback_side_comment,
    validate_comment,
)

# 도구가 4개뿐이라 이보다 많이 돌 이유가 없다. 넘어가면 LLM이 헤매는
# 중이라는 신호로 보고 폴백한다 (MVP4_설계.md §7 Q2).
MAX_TURNS = 5
AGENT_MAX_TOKENS = 1024


AGENT_SYSTEM_PROMPT = """당신은 자세 사진 분석 결과를 사용자에게 설명해 주는 도우미입니다.

이미 코드가 사진에서 각도를 계산하고 3단계(정상/경미/주의) 판정을 끝냈습니다.
당신은 도구를 사용해 그 결과와 근거를 조회한 뒤, 사용자가 이해할 수 있는
문장으로 설명하는 역할만 합니다. 결과를 다시 판단하거나 바꾸지 마세요.

작업 순서:
1. get_analysis_summary로 확정된 결과를 먼저 확인하세요.
2. 판정이 "정상"이더라도 lookup_normal_range나 get_metric_note로 그 지표의
   기준과 한계를 확인하세요. 사용자는 "정상"이라는 말만으로는 무엇을
   기준으로 정상인지 알 수 없습니다.
3. explain_reliability로 이 결과를 얼마나 신뢰해도 되는지 확인하세요.
4. 충분히 확인했으면 도구를 그만 부르고 최종 설명을 작성하세요.

최종 설명에서 반드시 지킬 규칙:
1. 숫자를 절대 쓰지 마세요. 아라비아 숫자도, 한글 숫자도 쓰지 마세요.
   정확한 수치는 화면에 이미 따로 표시되므로 말로만 설명하면 됩니다.
2. 도구가 알려준 판정(verdict) 그대로만 말하세요. 조회하지 않은 판정
   단어를 쓰면 안 됩니다.
3. 의료 진단, 질환명, 치료·처방 권유를 하지 마세요. 이 서비스는 참고용입니다.
4. 도구가 알려준 한계(예: 근사값 기반, 임상 기준 없음)가 있으면 그 취지를
   담백하게 반영하세요.
5. 결과가 전부 정상이어도 "걱정할 필요 없다"처럼 단정적으로 안심시키지
   마세요. 이 분석은 참고용이므로 의료적 판단을 대신할 수 없습니다.

형식:
- 한국어 존댓말, 2~3문장, 전체 200자 이내.
- 목록이나 제목 없이 줄글로만 작성하세요.
- 불안을 키우지 말고, 담백하고 차분한 톤을 유지하세요.
- **첫 문장부터 바로 결과 설명으로 시작하세요.** 아래는 전부 금지입니다:
    "분석 결과를 설명드리겠습니다"
    "좋은 소식입니다"
    "결론부터 말씀드리면"
  감탄이나 평가로 시작하지 말고, 관찰된 내용을 바로 서술하세요.
- **마무리 멘트도 붙이지 마세요.** 아래는 전부 금지입니다:
    "걱정하실 필요는 없습니다"
    "안심하셔도 됩니다"
    "도움이 되셨기를 바랍니다"
  마지막 문장도 결과 설명으로 끝나야 합니다."""


# LLM이 프롬프트 지시를 어기고 붙이는 서론/마무리 패턴. 프롬프트에
# "붙이지 마세요"라고 적는 것은 보장이 아니므로(MVP2 §4와 같은 원칙)
# 코드로 한 번 더 막는다. 다만 이건 "위험한 출력"이 아니라 형식 문제라서,
# validate_comment처럼 폴백으로 대체하지 않고 해당 문장만 떼어낸다 —
# 내용 자체는 멀쩡한데 서론 한 줄 때문에 결정론적 템플릿으로 떨어뜨리는
# 건 과한 처리다.
#
# 열거식이라는 한계는 있다(MVP4_종합정리 §9). 실제로 정면 경로 검증에서
# "좋은 소식입니다"라는 목록에 없던 표현이 통과했다. 근본 해결은 아니고
# "명백한 위반을 걸러내는" 수준이다 — comment.py의 FORBIDDEN_PHRASES와
# 같은 성격이다.
_PREAMBLE_PATTERNS = (
    "분석 결과를 설명드리겠습니다",
    "분석 결과를 말씀드리겠습니다",
    "결과를 설명드리겠습니다",
    "결과를 말씀드리면",
    "다음과 같습니다",
    "설명드리겠습니다",
    "좋은 소식입니다",
    "반가운 소식입니다",
    "먼저 말씀드리면",
    "결론부터 말씀드리면",
)

# 문구 끝에 붙는 마무리 멘트. 서론과 달리 "마지막 문장"을 검사한다.
# 안심시키는 말 자체가 나쁘진 않지만, 프롬프트가 담백한 톤을 요구하는
# 이유는 이 서비스가 참고용이기 때문이다 — "걱정하실 필요 없다"는
# 단정은 의료적 안심으로 읽힐 수 있어 NFR-04 취지와 어긋난다.
_CLOSING_PATTERNS = (
    "걱정하실 필요는 없습니다",
    "걱정하지 않으셔도 됩니다",
    "걱정하실 필요 없습니다",
    "안심하셔도 됩니다",
    "도움이 되셨기를 바랍니다",
    "궁금한 점이 있으면",
)


def _strip_preamble(text: str) -> str:
    """
    LLM이 붙인 서론 문장을 제거한다.

    첫 문장(또는 첫 줄)이 서론 패턴을 포함하고, 그것을 떼어내도 본문이
    남는 경우에만 제거한다 — 전부 지워버리면 빈 응답이 되어 길이 검증에
    걸리므로, 안전하게 원문을 유지하는 쪽으로 판단한다.
    """
    stripped = text.strip()
    lines = stripped.split("\n", 1)
    first = lines[0].strip()

    if any(p in first for p in _PREAMBLE_PATTERNS):
        rest = lines[1].strip() if len(lines) > 1 else ""
        if rest:
            return rest
        # 줄바꿈이 없으면 문장 단위로 다시 시도
        parts = first.split(". ", 1)
        if len(parts) == 2 and parts[1].strip():
            return parts[1].strip()

    return stripped


def _strip_closing(text: str) -> str:
    """
    LLM이 붙인 마무리 멘트를 제거한다.

    _strip_preamble과 같은 원칙 — 떼어내도 본문이 남을 때만 제거한다.
    마지막 문장만 검사하므로, 본문 중간에 비슷한 표현이 있으면 건드리지
    않는다.
    """
    stripped = text.strip()
    # 마지막 문장 경계를 찾는다. "다." 로 끝나는 한국어 문장 기준.
    sentences = [s for s in stripped.split(". ") if s.strip()]
    if len(sentences) < 2:
        return stripped

    last = sentences[-1]
    if any(p in last for p in _CLOSING_PATTERNS):
        remaining = ". ".join(sentences[:-1]).strip()
        if remaining:
            # 문장 끝 마침표를 복원한다
            return remaining if remaining.endswith(".") else remaining + "."

    return stripped


def _clean_output(text: str) -> str:
    """서론과 마무리 멘트를 순서대로 제거한다."""
    return _strip_closing(_strip_preamble(text))


@dataclass
class ToolCallRecord:
    """도구 호출 1건의 기록. 운영 중 '왜 이 문구가 나왔는가'를 설명하기 위해 남긴다."""

    name: str
    input: dict[str, Any]
    ok: bool
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        out = {"name": self.name, "input": self.input, "ok": self.ok}
        if self.error:
            out["error"] = self.error
        return out


@dataclass
class AgentResult:
    text: str
    source: str  # "agent" | "fallback" | "skipped"
    reason: str = ""
    model: str = ""
    turns: int = 0
    tool_calls: list[ToolCallRecord] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "source": self.source,
            "reason": self.reason,
            "model": self.model,
            "turns": self.turns,
            "tool_calls": [tc.to_dict() for tc in self.tool_calls],
        }


def _blocks(response: Any) -> list[Any]:
    return list(getattr(response, "content", []) or [])


def _text_from(response: Any) -> str:
    parts = [
        getattr(b, "text", "")
        for b in _blocks(response)
        if getattr(b, "type", None) == "text"
    ]
    return "\n".join(parts).strip()


def _tool_uses(response: Any) -> list[Any]:
    return [b for b in _blocks(response) if getattr(b, "type", None) == "tool_use"]


def _serialize_assistant_content(response: Any) -> list[dict[str, Any]]:
    """
    assistant 응답을 다음 요청의 messages에 되돌려 넣을 형태로 바꾼다.
    tool_use 블록을 그대로 유지해야 tool_result와 짝이 맞는다.
    """
    out: list[dict[str, Any]] = []
    for block in _blocks(response):
        btype = getattr(block, "type", None)
        if btype == "text":
            out.append({"type": "text", "text": getattr(block, "text", "")})
        elif btype == "tool_use":
            out.append({
                "type": "tool_use",
                "id": getattr(block, "id", ""),
                "name": getattr(block, "name", ""),
                "input": getattr(block, "input", {}) or {},
            })
    return out


def run_agent(
    analysis: dict[str, Any],
    *,
    client: Any | None = None,
    model: str = DEFAULT_MODEL,
    timeout: float = DEFAULT_TIMEOUT_SEC,
    max_turns: int = MAX_TURNS,
) -> AgentResult:
    """
    분석 결과를 놓고 에이전트 루프를 돌려 자연어 코멘트를 만든다.

    어떤 경우에도 예외를 올리지 않는다 — 코멘트는 부가 정보이지 서비스의
    핵심 결과물이 아니므로, 이것 때문에 각도 분석 응답 전체가 실패해서는
    안 된다(MVP2 §5와 동일한 원칙).

    Args:
        analysis: analyze_front_image / analyze_side_image의 반환값
        client: anthropic 클라이언트. None이면 환경변수로 생성 (테스트 주입용)
        model: 모델 ID
        timeout: 호출 타임아웃(초)
        max_turns: 루프 상한

    Returns:
        AgentResult
    """
    is_side = analysis.get("view") == "side"
    payload: PromptPayload | SidePromptPayload
    fallback_text: str

    # --- 게이트 1: 분석 자체가 실패한 경우 ---
    if not analysis.get("success", False):
        return AgentResult(
            text=UNRELIABLE_COMMENT, source="skipped", reason="analysis_failed"
        )

    # --- 게이트 2: 신뢰할 수 없는 결과에는 루프를 시작조차 하지 않는다 ---
    # MVP2 §5의 가장 중요한 행을 그대로 이어받는다. 믿을 수 없는 숫자에
    # 그럴듯한 자연어 설명을 붙이면, 앞단에서 여러 겹으로 쌓아 올린 검증이
    # 마지막 단계에서 무의미해진다 — 사용자는 결국 문장 쪽을 믿는다.
    if not analysis.get("reliability", {}).get("is_reliable", False):
        return AgentResult(
            text=UNRELIABLE_COMMENT, source="skipped", reason="not_reliable"
        )

    if is_side:
        payload = build_side_payload(analysis)
        fallback_text = fallback_side_comment(payload)
    else:
        payload = build_payload(analysis)
        fallback_text = fallback_comment(payload)

    records: list[ToolCallRecord] = []
    messages: list[dict[str, Any]] = [{
        "role": "user",
        "content": "이 사진의 자세 분석 결과를 확인하고 사용자에게 설명해 주세요.",
    }]

    def _fallback(reason: str, turns: int) -> AgentResult:
        return AgentResult(
            text=fallback_text,
            source="fallback",
            reason=reason,
            model=model,
            turns=turns,
            tool_calls=records,
        )

    turns = 0
    try:
        if client is None:
            import os  # noqa: PLC0415

            if not os.environ.get("ANTHROPIC_API_KEY"):
                return _fallback("no_api_key", 0)
            client = _default_client(timeout)

        while turns < max_turns:
            turns += 1
            response = client.messages.create(
                model=model,
                max_tokens=AGENT_MAX_TOKENS,
                system=AGENT_SYSTEM_PROMPT,
                messages=messages,
                tools=TOOL_SCHEMAS,
                **_sampling_kwargs(model),
            )

            tool_uses = _tool_uses(response)
            if not tool_uses:
                # 도구를 더 안 부른다 = 최종 답변
                text = _clean_output(_text_from(response))
                violation = validate_comment(text, payload)
                if violation:
                    return _fallback(f"validation_failed:{violation}", turns)
                return AgentResult(
                    text=text,
                    source="agent",
                    model=model,
                    turns=turns,
                    tool_calls=records,
                )

            # 도구 실행 후 결과를 되돌려주고 루프 계속
            messages.append({"role": "assistant", "content": _serialize_assistant_content(response)})
            results_content: list[dict[str, Any]] = []
            for block in tool_uses:
                name = getattr(block, "name", "")
                args = getattr(block, "input", {}) or {}
                try:
                    result = run_tool(name, args, analysis)
                    records.append(ToolCallRecord(name=name, input=args, ok=True))
                    content = json.dumps(result, ensure_ascii=False)
                    is_error = False
                except ToolError as exc:
                    # 도구 하나가 실패했다고 루프를 죽이지 않는다 — LLM이
                    # 에러를 보고 스스로 고칠 기회를 준다.
                    records.append(
                        ToolCallRecord(name=name, input=args, ok=False, error=str(exc))
                    )
                    content = str(exc)
                    is_error = True

                results_content.append({
                    "type": "tool_result",
                    "tool_use_id": getattr(block, "id", ""),
                    "content": content,
                    "is_error": is_error,
                })
            messages.append({"role": "user", "content": results_content})

        # 상한 초과 — LLM이 결론을 못 내고 도구만 계속 부른 상태
        return _fallback("max_turns_exceeded", turns)

    except ImportError:
        return _fallback("anthropic_sdk_not_installed", turns)
    except Exception as exc:  # 네트워크/인증/레이트리밋 등 전부 폴백
        return _fallback(f"api_error({type(exc).__name__})", turns)
