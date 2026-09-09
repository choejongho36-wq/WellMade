"""
MVP4: 에이전트가 호출할 수 있는 도구 정의 + 인자 검증 + 실행 디스패치.

핵심 원칙 — "판단은 LLM, 계산은 코드"를 에이전트에서도 깨지 않는다.
    도구는 이미 확정된 분석 결과를 *조회*하거나, 참고 자료를 *찾아볼* 뿐이다.
    LLM이 임의 좌표를 넣어 각도를 새로 계산할 수 있는 도구는 의도적으로
    노출하지 않는다(calculate_* 계열). 계산은 에이전트 루프가 시작되기
    전에 analysis.py가 이미 끝내둔다.

    이 경계가 없으면 MVP1~3에서 쌓아 올린 검증(품질 게이트, 기하학적
    타당성, 신뢰도 판정)을 LLM이 우회해서 자기 숫자를 만들어낼 수 있다.

노출하지 않는 것 (MVP4_설계.md §3):
    - calculate_shoulder_tilt / calculate_forward_head / approximate_c7 등
      계산 함수 전부
    - 이미지 경로, 33개 원본 좌표 접근
    - 파일 쓰기, 네트워크 등 부수효과가 있는 모든 것
"""

from __future__ import annotations

import re
from typing import Any, Callable

from .landmarks import to_korean
from .thresholds import NORMAL_RANGES, lookup_normal_range

# 지표 이름 체계가 두 곳에서 달라 LLM이 혼란을 겪었다(실측: 정면 경로에서
# lookup_normal_range("pelvis_tilt")는 성공하는데 get_metric_note("pelvis_tilt")는
# 실패해서, 도구를 8번 부르며 이름을 찾아 헤맸다).
#   thresholds.NORMAL_RANGES 키 : shoulder_tilt, pelvis_tilt, forward_head, ...
#   분석 결과 dict 키           : shoulder, pelvis, forward_head, round_shoulder
# 대외적으로는 NORMAL_RANGES 쪽 이름 하나로 통일하고, 내부에서 변환한다.
# 도구마다 다른 이름을 쓰게 두면 LLM이 추측할 수밖에 없다.
_PUBLIC_TO_ANALYSIS_KEY = {
    "shoulder_tilt": "shoulder",
    "pelvis_tilt": "pelvis",
    "forward_head": "forward_head",
    "round_shoulder": "round_shoulder",
    "pelvis_sagittal": "pelvis_sagittal",  # 아직 분석 결과에 없음
}


def _public_metric_names(analysis: dict[str, Any]) -> list[str]:
    """이번 분석에 실제로 값이 있는 지표의 대외 이름 목록."""
    return [
        public
        for public, key in _PUBLIC_TO_ANALYSIS_KEY.items()
        if isinstance(analysis.get(key), dict)
    ]


# LLM에게 넘길 도구 스키마 (Anthropic tool-use 형식).
# 설명문은 LLM이 읽는 유일한 사용 설명서이므로, "무엇을 하는가"보다
# "언제 쓰는가"를 명확히 쓴다.
TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "name": "get_analysis_summary",
        "description": (
            "이미 계산이 끝난 자세 분석 결과(3단계 판정, 신뢰도 낮은 관절)를 조회한다. "
            "**항상 이 도구를 가장 먼저 호출하라** — 반환된 키가 이번 분석에 있는 "
            "지표 이름이며, 다른 도구에도 같은 이름을 쓰면 된다. "
            "이 판정들은 코드가 확정한 것이며 변경할 수 없다."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "lookup_normal_range",
        "description": (
            "특정 지표의 판정 기준과 그 근거(출처)를 조회한다. "
            "판정이 왜 그렇게 나왔는지 설명할 근거가 필요할 때 사용하라. "
            "이번 분석에 없는 지표도 조회할 수 있지만, 그 경우 응답의 "
            "in_this_analysis가 false로 오므로 이 사람의 결과인 것처럼 "
            "설명하면 안 된다."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "metric": {
                    "type": "string",
                    "enum": sorted(NORMAL_RANGES.keys()),
                    "description": "조회할 지표 이름",
                }
            },
            "required": ["metric"],
        },
    },
    {
        "name": "get_metric_note",
        "description": (
            "특정 지표에 붙은 한계/주의사항을 조회한다(예: C7 근사값 기반, "
            "임상 확립 기준 없음 등). 사용자에게 결과를 얼마나 신뢰해도 되는지 "
            "설명할 때 사용하라. "
            "**이번 분석에 있는 지표만 조회할 수 있다** — 어떤 지표가 있는지는 "
            "get_analysis_summary의 응답 키를 보라."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "metric": {
                    "type": "string",
                    "enum": sorted(_PUBLIC_TO_ANALYSIS_KEY.keys()),
                    "description": "조회할 지표 이름 (get_analysis_summary 응답에 있는 이름)",
                }
            },
            "required": ["metric"],
        },
    },
    {
        "name": "explain_reliability",
        "description": (
            "이번 분석 결과의 신뢰도 상태와, 신뢰할 수 없다면 그 사유를 조회한다. "
            "사진 품질이나 촬영 각도 문제로 결과가 불확실한지 확인할 때 사용하라."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
]

TOOL_NAMES = {schema["name"] for schema in TOOL_SCHEMAS}

# 신뢰도 issue 코드를 사람이 읽을 수 있는 설명으로 바꾼다. LLM이 코드
# 문자열(not_a_side_profile:shoulder_x_gap(0.2496))을 직접 해석하게 두면
# 부호나 숫자를 오독할 여지가 있으므로, 해석은 코드가 미리 해준다.
_RELIABILITY_EXPLANATIONS = {
    "not_a_side_profile": "몸이 완전히 옆을 향하지 않은 것으로 보입니다(정면이나 비스듬한 각도일 수 있음).",
    "near_side_undetermined": "카메라에 가까운 쪽을 판정하지 못했습니다. 옆모습이 뚜렷하지 않을 수 있습니다.",
    "neck_too_short": "목 부분이 프레임에서 잘렸거나 지나치게 눌려 보입니다.",
    "shoulder_points_overlapping": "좌우 어깨가 겹쳐 보입니다. 정면 사진에서는 비정상입니다.",
    "hip_points_overlapping": "좌우 골반이 겹쳐 보입니다. 정면 사진에서는 비정상입니다.",
    "shoulder_hip_ratio": "어깨와 골반의 너비 비율이 인체로서 부자연스럽습니다.",
    "person_detection": "사진에서 사람을 충분히 뚜렷하게 인식하지 못했습니다.",
}


class ToolError(Exception):
    """도구 실행 실패. 루프를 중단시키지 않고 LLM에게 에러 내용을 돌려준다."""


def _tool_get_analysis_summary(analysis: dict[str, Any], _: dict[str, Any]) -> dict[str, Any]:
    """
    확정된 분석 결과 요약. MVP2의 build_payload와 같은 철학으로 최소한만
    노출한다 — 이미지, 33개 원본 좌표, 파일명은 넘기지 않는다.
    """
    out: dict[str, Any] = {"view": analysis.get("view", "front")}
    for public, key in _PUBLIC_TO_ANALYSIS_KEY.items():
        metric = analysis.get(key)
        if isinstance(metric, dict):
            # angle_deg를 넘기지 않는다 — LLM이 그 숫자를 문구에 옮겨 쓰면
            # validate_comment에 걸려 폴백된다(_describe_range docstring 참고).
            # 정확한 수치는 이미 응답의 다른 필드로 화면에 표시되므로,
            # 설명을 쓰는 데는 판정만 있으면 충분하다.
            #
            # 키는 대외 이름(shoulder_tilt 등)으로 통일한다 — 다른 도구가
            # 쓰는 이름과 같아야 LLM이 이름을 찾아 헤매지 않는다.
            out[public] = {"verdict": metric.get("verdict")}
    low_confidence = [
        item.get("name")
        for item in analysis.get("keypoint_confidence", [])
        if item.get("band") in ("낮음", "보통")
    ]
    # 영문 랜드마크 이름을 그대로 넘기면 LLM이 번역하다가 부정확한 표현을
    # 만든다(실측: left_hip -> "왼쪽 엉덩이"). 번역은 코드가 확정한다.
    out["low_confidence_points"] = [to_korean(n) for n in low_confidence if n]
    return out


def _describe_range(metric: str, rng: tuple | None) -> str:
    """
    정상범위를 숫자 없이 서술한다.

    LLM에게 숫자를 넘기면 그걸 문구에 그대로 옮겨 쓸 확률이 올라간다 —
    실측에서 도구 호출이 6건으로 늘자 validate_comment의 숫자 금지 검사에
    걸려 폴백되는 사례가 나왔다. 폴백은 안전하지만, 에이전트가 도구를
    여러 번 불러 만든 맥락이 통째로 버려진다는 뜻이기도 하다.

    그래서 애초에 숫자를 재료로 주지 않는다. explain_reliability가 issue
    코드를 미리 해석해서 넘기는 것과 같은 원칙이다 — 정확한 수치는 이미
    화면에 따로 표시되므로, LLM에게는 판정의 방향만 알려주면 충분하다.
    """
    if rng is None:
        return "임상적으로 확립된 단일 기준이 없어 잠정 구간을 사용합니다."

    low, high = rng
    if high is None:
        # 단방향 기준 (예: round_shoulder — 기준각 이하면 이상)
        return "기준값 이하이면 해당 경향이 있는 것으로, 초과하면 정상 경향으로 봅니다."
    if low == 0.0:
        # 0부터 시작 = 절대값이 작을수록 정상
        return "값이 작을수록 정상에 가깝고, 커질수록 해당 경향이 뚜렷해집니다."
    return "정해진 구간 안에 들면 정상 범위이고, 벗어나면 해당 경향이 있는 것으로 봅니다."


# source/note 문자열에는 숫자가 섞여 있다(예: "52도 이하 시 라운드숄더
# 경향", "판정 구간: 5도 이내 정상 / 5~15도 경미"). 위와 같은 이유로
# 제거해서 넘긴다. 완전히 지우면 문장이 어색해지므로 일반적인 표현으로
# 바꾼다.
#
# (?<![A-Za-z]) : 앞에 알파벳이 있으면 제외 — "C7"(경추 7번) 같은 해부학
#   용어의 숫자는 측정값이 아니므로 보존해야 한다. 지우면 "C은 어깨-골반
#   좌표로 근사한 값"처럼 의미가 깨진다.
# (?:\s*~\s*...) : "5~15도" 같은 범위 표기도 한 덩어리로 잡는다.
_NUMBER_PATTERN = re.compile(
    r"(?<![A-Za-z])[-+]?\d+(?:\.\d+)?(?:\s*~\s*[-+]?\d+(?:\.\d+)?)?\s*도?"
)

# "판정 구간: 5도 이내 정상 / 5~15도 경미 / 15도 이상 주의." 처럼 숫자를
# 지우면 의미가 뭉개지는 문장은 통째로 제거한다. 구간 방향은 criterion
# 필드가 이미 설명하므로 정보 손실은 없다.
_SEGMENT_SENTENCE_PATTERN = re.compile(r"판정 구간:[^.]*\.")


def _strip_numbers_from_source(source: str) -> str:
    """
    출처/한계 설명에서 측정 수치를 제거한다.

    "C7"(경추 7번)처럼 해부학 용어에 포함된 숫자는 측정값이 아니므로
    보존한다 — 제거하면 "C은 어깨-골반 좌표로 근사한 값"처럼 의미가
    깨진다. _NUMBER_PATTERN의 lookbehind가 이를 처리한다.

    숫자를 지우면 의미가 뭉개지는 문장(예: "5도 이내 정상 / 5~15도 경미
    / 15도 이상 주의" -> "기준값 이내 정상 / 기준값 경미 / 기준값 이상
    주의")은 아예 제거한다. 구간 방향은 criterion 필드가 이미 설명하므로
    정보가 손실되지 않는다.
    """
    cleaned = _SEGMENT_SENTENCE_PATTERN.sub("", source)
    return _NUMBER_PATTERN.sub("기준값", cleaned).strip()


def _strip_all_numbers(text: str) -> str:
    """
    모든 숫자를 제거한다. 매핑에 없는 신뢰도 issue 코드처럼 형식을
    예측할 수 없는 문자열에 쓴다.
    """
    return re.sub(r"[-+]?\d+(?:\.\d+)?", "값", text)


def _tool_lookup_normal_range(analysis: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    metric = args.get("metric")
    if not isinstance(metric, str):
        raise ToolError("metric 인자는 문자열이어야 합니다.")
    try:
        info = lookup_normal_range(metric)
    except ValueError as exc:
        raise ToolError(
            f"{exc} 사용 가능한 지표: {', '.join(sorted(NORMAL_RANGES.keys()))}"
        ) from exc

    # 이번 분석에 없는 지표도 조회 자체는 허용한다 — 차단하면 "정면
    # 결과를 설명하면서 측면 촬영을 권하는" 식의 맥락이 막힌다. 대신
    # 그 사실을 명시해서, LLM이 없는 지표를 결과인 것처럼 말하지 않도록
    # 한다. 제약이 아니라 정보 제공이며, 도구 실패 처리와 같은 원칙이다
    # (막지 말고 알려주기).
    in_analysis = metric in _public_metric_names(analysis)

    # range 숫자를 그대로 넘기지 않는다 — _describe_range의 docstring 참고.
    out = {
        "metric": metric,
        "criterion": _describe_range(metric, info["range"]),
        "source": _strip_numbers_from_source(info["source"]),
        "in_this_analysis": in_analysis,
    }
    if not in_analysis:
        out["note"] = (
            "이번 분석에는 이 지표가 없습니다. 참고 정보로만 쓰고, "
            "이 사람의 결과인 것처럼 설명하지 마세요."
        )
    return out


def _tool_get_metric_note(analysis: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    metric = args.get("metric")
    if not isinstance(metric, str):
        raise ToolError("metric 인자는 문자열이어야 합니다.")

    available = _public_metric_names(analysis)
    if metric not in available:
        raise ToolError(
            f"이번 분석에 없는 지표입니다: {metric}. 사용 가능: {', '.join(available)}"
        )

    key = _PUBLIC_TO_ANALYSIS_KEY[metric]
    note = analysis[key].get("note", "")
    # note에도 숫자가 섞여 있다(예: "기준각 52도 자체는 Thigpen et al. 문헌
    # 근거"). 같은 이유로 제거해서 넘긴다.
    return {"metric": metric, "note": _strip_numbers_from_source(note) or "별도 주의사항 없음"}


def _tool_explain_reliability(analysis: dict[str, Any], _: dict[str, Any]) -> dict[str, Any]:
    reliability = analysis.get("reliability", {})
    is_reliable = bool(reliability.get("is_reliable", False))
    issues = reliability.get("issues", [])

    explanations = []
    for issue in issues:
        code = str(issue).split(":")[0].split("(")[0]
        # 매핑에 없는 코드는 원문이 그대로 넘어가는데, 거기 숫자가 섞여
        # 있을 수 있다(예: shoulder_x_gap(0.2496)). 숫자를 빼고 넘긴다.
        explanations.append(
            _RELIABILITY_EXPLANATIONS.get(code, _strip_all_numbers(str(issue)))
        )

    return {
        "is_reliable": is_reliable,
        "issues": explanations,
        "quality_valid": bool(analysis.get("quality", {}).get("is_valid", True)),
    }


_DISPATCH: dict[str, Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]] = {
    "get_analysis_summary": _tool_get_analysis_summary,
    "lookup_normal_range": _tool_lookup_normal_range,
    "get_metric_note": _tool_get_metric_note,
    "explain_reliability": _tool_explain_reliability,
}


def run_tool(name: str, args: dict[str, Any], analysis: dict[str, Any]) -> dict[str, Any]:
    """
    도구 하나를 실행한다.

    화이트리스트에 없는 이름이면 예외를 올리지 않고 ToolError를 발생시켜
    호출자가 LLM에게 에러 내용을 돌려줄 수 있게 한다 — 에이전트 루프에서
    도구 하나가 실패했다고 전체가 죽으면, LLM이 스스로 고칠 기회 자체가
    없어진다.

    Args:
        name: 도구 이름
        args: LLM이 넘긴 인자
        analysis: 이미 확정된 분석 결과 (analyze_front_image/analyze_side_image)

    Returns:
        도구 실행 결과 dict

    Raises:
        ToolError: 미등록 도구이거나 인자가 잘못된 경우
    """
    if name not in _DISPATCH:
        raise ToolError(
            f"등록되지 않은 도구입니다: {name}. 사용 가능: {', '.join(sorted(TOOL_NAMES))}"
        )
    if not isinstance(args, dict):
        raise ToolError("도구 인자는 객체(JSON object)여야 합니다.")
    return _DISPATCH[name](analysis, args)
