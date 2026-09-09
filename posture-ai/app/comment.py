"""
MVP2: 계산된 각도/판정 결과 -> Claude API -> 자연어 코멘트 생성.

로드맵 4장 MVP2 정의:
    목표      : 각도 결과(JSON)를 Claude API에 단순 전달해 자연어 코멘트 생성
    LLM/에이전트: LLM 있음. 단, Tool-use 에이전트는 아님(그건 MVP4).

핵심 설계 원칙 — "판단은 LLM, 계산은 코드"를 MVP2에서도 깨지 않는다.
    각도 계산(angles.py)과 3단계 판정(thresholds.py)은 이미 코드가 끝낸
    상태다. LLM은 그 확정된 결과를 "읽기 전용"으로 받아 설명 문구만
    만든다. LLM이 각도를 다시 계산하거나 판정을 뒤집을 여지를 구조적으로
    차단하기 위해, 아래 두 겹의 장치를 둔다.

    1) 프롬프트 차원: 숫자를 쓰지 말 것, 판정 라벨을 바꾸지 말 것을 지시
    2) 출력 검증 차원: 위 지시를 어긴 출력은 코드가 기계적으로 거부하고
       결정론적 템플릿 문구(fallback)로 대체 (validate_comment 참고)

    2번이 있기 때문에, LLM이 지시를 무시하더라도 사용자에게 잘못된 숫자나
    뒤집힌 판정이 노출되지 않는다. MVP0~1에서 "신뢰도 점수를 어디까지
    믿을 수 있는가"를 검증했던 것과 같은 방식으로, MVP2는 "LLM 출력을
    어디까지 믿을 수 있는가"를 코드가 검사한다.

NFR-06(재현성)에 대하여:
    LLM 출력은 본질적으로 완전한 결정론을 보장할 수 없다. 그래서 재현성이
    요구되는 값(각도, 판정)은 전부 코드 레이어에 남기고, LLM은 그 값에
    영향을 주지 못하는 설명 문구만 담당하도록 경계를 그었다. 문구 자체의
    변동 폭은 temperature=0(지원 모델 한정)으로 최소화한다.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Any, Literal

from .landmarks import to_korean

# --- 모델 설정 -------------------------------------------------------------
# 이 작업은 "작은 JSON을 받아 2~3문장 한국어 코멘트를 쓰는" 가벼운 생성이라
# 최상위 모델이 필요하지 않다. 기본값으로 Haiku를 쓰는 이유는 비용/지연
# 때문만이 아니라, 아래 SAMPLING_LOCKED_MODEL_PREFIXES 주석 참고 —
# temperature=0을 지정할 수 있는 모델이어야 문구 변동 폭을 줄일 수 있다.
DEFAULT_MODEL = os.environ.get("POSTURE_LLM_MODEL", "claude-haiku-4-5-20251001")
DEFAULT_MAX_TOKENS = 300
DEFAULT_TIMEOUT_SEC = 15.0

# Sonnet 5 세대부터는 적응형 사고가 기본 활성화되면서 기본값이 아닌 샘플링
# 파라미터(temperature/top_p/top_k)를 지정하면 API가 요청을 거부한다.
# 모델을 환경변수로 갈아끼울 수 있게 열어둔 이상, temperature를 무조건
# 보내면 모델 교체 순간 500이 터진다. 그래서 모델 계열을 보고 보낼지
# 말지를 코드가 판단한다.
SAMPLING_LOCKED_MODEL_PREFIXES = (
    "claude-sonnet-5",
    "claude-opus-5",
    "claude-fable-5",
    "claude-mythos-5",
)

# --- 출력 검증 기준 --------------------------------------------------------
MAX_COMMENT_CHARS = 250
MIN_COMMENT_CHARS = 15

# 판정 라벨. LLM이 payload에 없는 라벨을 쓰면 판정을 뒤집은 것으로 간주한다.
# (예: 어깨/골반 모두 "정상"인데 코멘트에 "주의"가 등장 -> 거부)
VERDICT_WORDS = ("정상", "경미", "주의")

# 의료 진단/치료를 암시하는 표현. NFR-04(의료 진단 아님) 위반 방지.
# 질환명을 직접 나열하는 이유: LLM이 "척추측만증이 의심됩니다" 같은 문장을
# 쓰는 순간 이 서비스는 참고용 도구가 아니라 진단 도구가 되어버린다.
FORBIDDEN_PHRASES = (
    "진단",
    "질환",
    "질병",
    "치료",
    "처방",
    "수술",
    "약물",
    "환자",
    "병명",
    "측만증",
    "디스크",
    "협착",
    "증후군",
    "탈구",
    "골절",
    "염증",
)

# 표현용 데드존: 부호가 있어도 이 이하면 "좌우 차이 없음"으로 안내한다.
# 판정 임계값(5도)과는 다른 목적 — 0.2도 차이를 "오른쪽이 낮습니다"라고
# 말하면 측정 오차를 실제 비대칭인 것처럼 전달하게 되기 때문이다.
DIRECTION_DEADZONE_DEG = 1.0


@dataclass
class CommentResult:
    """
    자연어 코멘트 생성 결과.

    source 값의 의미:
        "llm"      - Claude가 생성했고 검증도 통과함
        "fallback" - LLM 호출 실패 또는 출력 검증 실패 -> 템플릿 문구로 대체
        "skipped"  - 신뢰할 수 없는 결과라 LLM을 아예 호출하지 않음

    reason은 fallback/skipped인 경우의 구체적 사유(운영 디버깅용)를 담는다.
    사용자 화면에는 text만 노출하면 되지만, "왜 이 문구가 나왔는가"를
    추적할 수 없으면 LLM 레이어는 사실상 블랙박스가 되므로 항상 함께 반환한다.
    """

    text: str
    source: Literal["llm", "fallback", "skipped"]
    reason: str = ""
    model: str = ""


@dataclass
class PromptPayload:
    """LLM에 넘길 최소 정보. 이미지나 원본 좌표는 넘기지 않는다."""

    shoulder_angle_deg: float
    shoulder_verdict: str
    shoulder_lower_side: str  # "left" | "right" | "level"
    pelvis_angle_deg: float
    pelvis_verdict: str
    pelvis_lower_side: str
    low_confidence_points: list[str] = field(default_factory=list)

    def verdicts(self) -> set[str]:
        return {self.shoulder_verdict, self.pelvis_verdict}

    def to_json(self) -> str:
        return json.dumps(
            {
                "shoulder": {
                    "angle_deg": self.shoulder_angle_deg,
                    "verdict": self.shoulder_verdict,
                    "lower_side": self.shoulder_lower_side,
                },
                "pelvis": {
                    "angle_deg": self.pelvis_angle_deg,
                    "verdict": self.pelvis_verdict,
                    "lower_side": self.pelvis_lower_side,
                },
                "low_confidence_points": self.low_confidence_points,
            },
            ensure_ascii=False,
            indent=2,
        )


@dataclass
class SidePromptPayload:
    """
    측면 분석용 LLM 페이로드 (MVP3). PromptPayload와 별도 클래스로 둔다 —
    지표 구성이 다르고(lower_side 대신 근사값 여부를 알려야 함), 필드를
    억지로 공유하면 "정면/측면 공통 스키마"라는 잘못된 인상을 준다.
    generate_comment()는 to_json()/verdicts()만 요구하므로 검증
    로직(validate_comment)은 그대로 재사용된다.
    """

    forward_head_angle_deg: float
    forward_head_verdict: str
    round_shoulder_angle_deg: float
    round_shoulder_verdict: str
    near_side_determined: bool  # False면 근접 측 판정이 불확실했다는 뜻
    low_confidence_points: list[str] = field(default_factory=list)

    def verdicts(self) -> set[str]:
        return {self.forward_head_verdict, self.round_shoulder_verdict}

    def to_json(self) -> str:
        return json.dumps(
            {
                "forward_head": {
                    "angle_deg": self.forward_head_angle_deg,
                    "verdict": self.forward_head_verdict,
                },
                "round_shoulder": {
                    "angle_deg": self.round_shoulder_angle_deg,
                    "verdict": self.round_shoulder_verdict,
                    "note": "C7은 어깨-골반 좌표로 근사한 값입니다.",
                },
                "near_side_determined": self.near_side_determined,
                "low_confidence_points": self.low_confidence_points,
            },
            ensure_ascii=False,
            indent=2,
        )


def build_side_payload(analysis: dict[str, Any]) -> SidePromptPayload:
    """
    analyze_side_image() 응답 dict에서 LLM에 넘길 최소 페이로드를 만든다.

    Args:
        analysis: {"forward_head": {...}, "round_shoulder": {...},
                   "near_side_determined": bool, "keypoint_confidence": [...]}

    Returns:
        SidePromptPayload
    """
    forward_head = analysis.get("forward_head", {})
    round_shoulder = analysis.get("round_shoulder", {})

    low_points = [
        item.get("name", "")
        for item in analysis.get("keypoint_confidence", [])
        if item.get("band") in ("낮음", "보통")
    ]

    return SidePromptPayload(
        forward_head_angle_deg=float(forward_head.get("angle_deg", 0.0)),
        forward_head_verdict=str(forward_head.get("verdict", "")),
        round_shoulder_angle_deg=float(round_shoulder.get("angle_deg", 0.0)),
        round_shoulder_verdict=str(round_shoulder.get("verdict", "")),
        near_side_determined=bool(analysis.get("near_side_determined", True)),
        # 영문 랜드마크 이름을 그대로 넘기면 LLM이 번역하다가 부정확한
        # 표현을 만든다(실측: left_hip -> "왼쪽 엉덩이"). 코드가 확정한다.
        low_confidence_points=[to_korean(name) for name in low_points if name],
    )


SYSTEM_PROMPT = """당신은 자세 사진 분석 결과를 사용자에게 설명해 주는 도우미입니다.

이미 코드가 각도를 계산하고 3단계(정상/경미/주의) 판정을 끝냈습니다.
당신의 역할은 그 확정된 결과를 사용자가 이해할 수 있는 문장으로 옮기는 것뿐입니다.
결과를 다시 판단하거나 바꾸지 마세요.

반드시 지킬 규칙:
1. 숫자를 절대 쓰지 마세요. 아라비아 숫자도, 한글 숫자(예: 이 점 삼 도)도 쓰지 마세요.
   각도 수치는 화면에 이미 따로 표시되므로, 당신은 말로만 설명하면 됩니다.
2. 입력에 주어진 판정(verdict) 그대로만 말하세요. 주어지지 않은 판정 단어
   (정상/경미/주의 중 입력에 없는 것)를 쓰면 안 됩니다.
3. 의료 진단, 질환명, 치료·처방 권유를 하지 마세요. 이 서비스는 참고용입니다.
4. lower_side는 사진에 찍힌 사람 본인 기준의 좌우입니다. 보는 사람 기준이 아닙니다.
   "left"면 본인 기준 왼쪽, "right"면 본인 기준 오른쪽이 더 낮다는 뜻이고,
   "level"이면 좌우 차이가 거의 없다는 뜻입니다.
5. low_confidence_points에 관절 이름이 있으면, 그 부위는 사진에서 뚜렷하게
   보이지 않아 참고만 하라는 취지를 한 문장으로 덧붙이세요. 비어 있으면 언급하지 마세요.

형식:
- 한국어 존댓말, 2~3문장, 전체 200자 이내.
- 목록이나 제목 없이 줄글로만 작성하세요.
- 불안을 키우지 말고, 담백하고 차분한 톤을 유지하세요.
- 설명 외의 말(인사, 서론, 마무리 멘트)은 붙이지 마세요."""


SIDE_SYSTEM_PROMPT = """당신은 자세 사진 분석 결과를 사용자에게 설명해 주는 도우미입니다.

이미 코드가 측면 사진에서 전방머리자세와 라운드숄더 각도를 계산하고
3단계(정상/경미/주의) 판정을 끝냈습니다. 당신의 역할은 그 확정된 결과를
사용자가 이해할 수 있는 문장으로 옮기는 것뿐입니다. 결과를 다시
판단하거나 바꾸지 마세요.

반드시 지킬 규칙:
1. 숫자를 절대 쓰지 마세요. 아라비아 숫자도, 한글 숫자도 쓰지 마세요.
   각도 수치는 화면에 이미 따로 표시되므로, 당신은 말로만 설명하면 됩니다.
2. 입력에 주어진 판정(verdict) 그대로만 말하세요. 주어지지 않은 판정 단어
   (정상/경미/주의 중 입력에 없는 것)를 쓰면 안 됩니다.
3. 의료 진단, 질환명, 치료·처방 권유를 하지 마세요. 이 서비스는 참고용입니다.
4. round_shoulder의 각도는 C7(경추 7번) 좌표를 실측이 아닌 어깨-골반
   좌표로 근사해서 계산한 값입니다. 그러니 "라운드숄더 경향"처럼 방향성
   위주로 담백하게 표현하고, 정밀한 수치인 것처럼 단정적으로 말하지 마세요.
5. near_side_determined가 false이면, 카메라와 몸의 각도가 완전한 옆모습이
   아니었을 수 있어 참고용으로만 보라는 취지를 한 문장으로 덧붙이세요.
6. low_confidence_points에 관절 이름이 있으면, 그 부위는 사진에서 뚜렷하게
   보이지 않아 참고만 하라는 취지를 한 문장으로 덧붙이세요. 비어 있으면 언급하지 마세요.

형식:
- 한국어 존댓말, 2~3문장, 전체 200자 이내.
- 목록이나 제목 없이 줄글로만 작성하세요.
- 불안을 키우지 말고, 담백하고 차분한 톤을 유지하세요.
- 설명 외의 말(인사, 서론, 마무리 멘트)은 붙이지 마세요."""


def _lower_side(angle_deg: float) -> str:
    """
    부호 규약(angles.py)을 사람이 읽을 수 있는 방향 라벨로 바꾼다.

    angles.py 규약: 양수 -> 오른쪽이 더 아래로 처짐 / 음수 -> 왼쪽이 더 아래.
    좌/우는 MediaPipe 명명 기준, 즉 피사체 본인 기준이다.
    """
    if abs(angle_deg) < DIRECTION_DEADZONE_DEG:
        return "level"
    return "right" if angle_deg > 0 else "left"


def build_payload(analysis: dict[str, Any]) -> PromptPayload:
    """
    api_mvp1 응답 형태의 dict에서 LLM에 넘길 최소 페이로드를 만든다.

    이미지, 원본 33개 좌표, 파일명은 넘기지 않는다 — 코멘트를 쓰는 데
    필요 없는 정보이고, 외부로 나가는 데이터는 적을수록 좋다.

    Args:
        analysis: {"shoulder": {...}, "pelvis": {...}, "keypoint_confidence": [...]}

    Returns:
        PromptPayload
    """
    shoulder = analysis.get("shoulder", {})
    pelvis = analysis.get("pelvis", {})

    shoulder_angle = float(shoulder.get("angle_deg", 0.0))
    pelvis_angle = float(pelvis.get("angle_deg", 0.0))

    # 신뢰도가 "높음"이 아닌 관절만 추린다. 사용자는 이미 수치+등급을 다
    # 보고 있지만(MVP1에서 추가), 코멘트에서도 "이 부위는 확실하지 않다"고
    # 말해줘야 숫자만 보고 과신하는 것을 막을 수 있다.
    low_points = [
        item.get("name", "")
        for item in analysis.get("keypoint_confidence", [])
        if item.get("band") in ("낮음", "보통")
    ]

    return PromptPayload(
        shoulder_angle_deg=shoulder_angle,
        shoulder_verdict=str(shoulder.get("verdict", "")),
        shoulder_lower_side=_lower_side(shoulder_angle),
        pelvis_angle_deg=pelvis_angle,
        pelvis_verdict=str(pelvis.get("verdict", "")),
        pelvis_lower_side=_lower_side(pelvis_angle),
        # 영문 랜드마크 이름을 그대로 넘기면 LLM이 번역하다가 부정확한
        # 표현을 만든다(실측: left_hip -> "왼쪽 엉덩이"). 코드가 확정한다.
        low_confidence_points=[to_korean(name) for name in low_points if name],
    )


def validate_comment(text: str, payload: PromptPayload) -> str:
    """
    LLM이 만든 문구가 안전 규칙을 지켰는지 기계적으로 검사한다.

    프롬프트로 "하지 마세요"라고 적어두는 것만으로는 보장이 되지 않는다.
    실제로 어겼을 때 사용자에게 그대로 노출되면 안 되는 항목들(숫자 왜곡,
    판정 뒤집기, 진단 표현)만 골라 코드로 다시 막는다.

    Args:
        text: LLM 출력 원문
        payload: 생성에 사용한 페이로드 (판정 라벨 대조용)

    Returns:
        위반 사유 문자열. 문제가 없으면 빈 문자열.
    """
    stripped = text.strip()

    if not stripped:
        return "empty_response"
    if len(stripped) < MIN_COMMENT_CHARS:
        return f"too_short({len(stripped)}자)"
    if len(stripped) > MAX_COMMENT_CHARS:
        return f"too_long({len(stripped)}자)"

    # 숫자 금지. 코드가 확정한 각도와 다른 수치를 LLM이 만들어낼 여지를
    # 아예 없애기 위해, 애초에 숫자를 한 글자도 허용하지 않는다.
    # (정확한 수치는 응답의 angle_deg 필드로 이미 전달되고 있다.)
    if re.search(r"\d", stripped):
        return "contains_number"

    for phrase in FORBIDDEN_PHRASES:
        if phrase in stripped:
            return f"forbidden_phrase({phrase})"

    # 판정 뒤집기 검사: payload에 없는 판정 라벨이 등장하면 거부.
    allowed = payload.verdicts()
    for word in VERDICT_WORDS:
        if word not in allowed and word in stripped:
            return f"verdict_mismatch({word})"

    return ""


# --- 결정론적 폴백 문구 -----------------------------------------------------
# LLM 없이도 서비스가 성립해야 한다. API 키가 없는 개발 환경, 네트워크 장애,
# 검증 실패 — 어느 경우든 사용자는 빈 화면 대신 정상적인 안내를 받아야 한다.
# MVP1까지의 동작이 그대로 유지되는 것이 이 폴백의 기준선이다.

_SIDE_LABEL = {"left": "왼쪽", "right": "오른쪽", "level": ""}

_VERDICT_TAIL = {
    "정상": "좌우가 고른 편입니다",
    "경미": "좌우 차이가 조금 있습니다",
    "주의": "좌우 차이가 눈에 띄는 편입니다",
}


def _topic_particle(word: str) -> str:
    """
    한국어 주제 조사(은/는)를 받침 유무에 따라 고른다.

    "어깨은", "골반는" 같은 문장이 나오면 사용자는 즉시 자동 생성 문구임을
    알아채고 결과 전체의 신뢰도를 낮게 본다. 템플릿이 폴백으로서 제 역할을
    하려면 LLM 문구와 나란히 놓여도 어색하지 않아야 한다.
    """
    if not word:
        return "는"
    code = ord(word[-1])
    if not 0xAC00 <= code <= 0xD7A3:  # 한글 음절이 아니면 기본값
        return "는"
    has_final_consonant = (code - 0xAC00) % 28 != 0
    return "은" if has_final_consonant else "는"


def _part_sentence(part_name: str, verdict: str, lower_side: str) -> str:
    tail = _VERDICT_TAIL.get(verdict, "결과를 확인해 주세요")
    side = _SIDE_LABEL.get(lower_side, "")
    particle = _topic_particle(part_name)
    if verdict == "정상" or not side:
        return f"{part_name}{particle} {tail}."
    return f"{part_name}{particle} 본인 기준 {side}이 조금 더 낮아 {tail}."


def fallback_comment(payload: PromptPayload) -> str:
    """
    LLM을 쓸 수 없을 때 사용하는 템플릿 문구. 순수 함수이며 같은 입력에는
    항상 같은 문장을 낸다. 검증 규칙(숫자 없음, 판정 라벨 일치, 진단 표현
    없음)을 템플릿 자체가 이미 만족하도록 작성했다.
    """
    both_level_and_same = (
        payload.shoulder_verdict == payload.pelvis_verdict
        and payload.shoulder_lower_side == "level"
        and payload.pelvis_lower_side == "level"
    )
    if both_level_and_same:
        # 같은 문장을 두 번 반복하지 않는다.
        tail = _VERDICT_TAIL.get(payload.shoulder_verdict, "결과를 확인해 주세요")
        body = f"어깨와 골반 모두 {tail}."
    else:
        body = " ".join(
            [
                _part_sentence("어깨", payload.shoulder_verdict, payload.shoulder_lower_side),
                _part_sentence("골반", payload.pelvis_verdict, payload.pelvis_lower_side),
            ]
        )

    if payload.low_confidence_points:
        body += " 일부 관절은 사진에서 뚜렷하게 보이지 않아 참고용으로만 봐주세요."

    if payload.verdicts() == {"정상"}:
        body += " 지금 자세를 유지해 보세요."
    else:
        body += " 자세한 평가는 전문가와 상담해 보시는 것을 권합니다."

    return body


_FORWARD_HEAD_TAIL = {
    "정상": "전방머리자세 경향은 두드러지지 않는 편입니다",
    "경미": "고개가 앞으로 살짝 나온 경향이 조금 있습니다",
    "주의": "고개가 앞으로 나온 경향이 눈에 띄는 편입니다",
}

_ROUND_SHOULDER_TAIL = {
    "정상": "어깨가 앞으로 말린 경향은 크지 않은 편입니다",
    "경미": "어깨가 앞으로 살짝 말린 경향이 조금 있습니다",
    "주의": "어깨가 앞으로 말린 경향이 눈에 띄는 편입니다",
}


def fallback_side_comment(payload: SidePromptPayload) -> str:
    """
    측면 분석용 결정론적 폴백 문구. fallback_comment(정면)와 같은
    설계 원칙 — 순수 함수이며 자기 자신이 validate_comment를 항상
    통과하도록 작성했다(숫자 없음, 판정 라벨 일치, 진단 표현 없음).
    """
    forward_head_tail = _FORWARD_HEAD_TAIL.get(
        payload.forward_head_verdict, "결과를 확인해 주세요"
    )
    round_shoulder_tail = _ROUND_SHOULDER_TAIL.get(
        payload.round_shoulder_verdict, "결과를 확인해 주세요"
    )

    body = f"{forward_head_tail}. {round_shoulder_tail}."

    if not payload.near_side_determined:
        body += " 완전한 옆모습으로 찍히지 않았을 수 있어 참고용으로만 봐주세요."

    if payload.low_confidence_points:
        body += " 일부 관절은 사진에서 뚜렷하게 보이지 않아 참고용으로만 봐주세요."

    if payload.verdicts() == {"정상"}:
        body += " 지금 자세를 유지해 보세요."
    else:
        body += " 자세한 평가는 전문가와 상담해 보시는 것을 권합니다."

    return body


UNRELIABLE_COMMENT = (
    "사진에서 관절 위치를 신뢰할 수 있을 만큼 정확하게 잡지 못했습니다. "
    "이 상태의 결과는 해석하지 않는 편이 안전하니, 안내에 따라 다시 촬영해 주세요."
)


# --- Claude API 호출 --------------------------------------------------------


def _sdk_accepts_temperature() -> bool:
    """
    설치된 anthropic SDK의 messages.create가 temperature를 받는지 확인한다.

    모델 계열만 보고 판단하면 부족하다는 걸 실측에서 확인했다(MVP4 실제
    API 검증 중 발견): Haiku는 temperature를 지원하는 모델이라 코드가
    값을 보냈는데, 설치된 SDK 쪽이 그 인자를 아예 몰라서
    `TypeError: Messages.create() got an unexpected keyword argument
    'temperature'`가 났다. 모델 지원 여부와 SDK 지원 여부는 별개이므로
    둘 다 확인해야 한다.

    시그니처를 못 읽는 경우(래핑된 함수 등)에는 보내지 않는 쪽으로
    안전하게 판단한다 — temperature가 빠지면 문구 변동 폭이 조금
    커질 뿐이지만, TypeError가 나면 LLM 호출 자체가 실패한다.
    """
    import inspect  # noqa: PLC0415

    try:
        from anthropic.resources.messages import Messages  # noqa: PLC0415

        params = inspect.signature(Messages.create).parameters
    except Exception:
        return False

    if "temperature" in params:
        return True
    # **kwargs로 받는 형태면 통과시킨다
    return any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values())


def _sampling_kwargs(model: str) -> dict:
    """
    모델 계열과 SDK 지원 여부를 함께 보고 temperature 전달 여부를 결정한다.

    Sonnet 5 세대부터는 기본값이 아닌 샘플링 파라미터를 지정하면 요청이
    거부된다. 반대로 Haiku 계열에서는 temperature=0이 문구 변동을 줄이는
    데 실제로 도움이 된다. 모델을 환경변수로 바꿀 수 있게 열어둔 이상,
    이 분기를 코드가 들고 있어야 모델 교체가 장애로 이어지지 않는다.

    여기에 더해 _sdk_accepts_temperature()로 SDK 쪽도 확인한다 —
    자세한 이유는 그 함수의 docstring 참고.
    """
    if model.startswith(SAMPLING_LOCKED_MODEL_PREFIXES):
        return {}
    if not _sdk_accepts_temperature():
        return {}
    return {"temperature": 0.0}


def _extract_text(response: Any) -> str:
    """
    Messages API 응답에서 텍스트 블록만 이어붙인다.

    content는 여러 블록의 리스트이고 텍스트가 아닌 블록이 섞일 수 있으므로,
    content[0].text를 바로 꺼내지 않고 type으로 걸러낸다.
    """
    parts: list[str] = []
    for block in getattr(response, "content", []) or []:
        if getattr(block, "type", None) == "text":
            parts.append(getattr(block, "text", ""))
    return "\n".join(parts).strip()


def _default_client(timeout: float):
    """anthropic SDK 클라이언트를 지연 생성한다 (미설치 환경도 동작하도록)."""
    from anthropic import Anthropic  # noqa: PLC0415 - 선택적 의존성

    return Anthropic(timeout=timeout)


def generate_comment(
    payload: PromptPayload,
    *,
    client: Any | None = None,
    model: str = DEFAULT_MODEL,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    timeout: float = DEFAULT_TIMEOUT_SEC,
    system_prompt: str = SYSTEM_PROMPT,
    fallback_fn: Any | None = None,
) -> CommentResult:
    """
    확정된 분석 결과를 Claude API에 넘겨 자연어 코멘트를 받는다.

    호출이 실패하거나 출력이 검증을 통과하지 못하면 예외를 올리지 않고
    결정론적 템플릿 문구로 대체한다 — 코멘트는 부가 정보이지 서비스의
    핵심 결과물이 아니므로, 이것 때문에 각도 분석 응답 전체가 실패해서는
    안 된다.

    이 함수 자체는 payload 종류(정면/측면)를 모른다 — payload가
    to_json()/verdicts()만 제공하면 되므로, MVP3의 측면 코멘트도
    별도 함수를 새로 만들지 않고 system_prompt/fallback_fn만 바꿔
    그대로 재사용한다(MVP3_착수정리 §3-E: 가드레일은 지표가 늘어도
    그대로 동작한다는 설계 그대로).

    Args:
        payload: build_payload() 또는 build_side_payload()의 결과
        client: anthropic 클라이언트. None이면 환경변수로 생성 (테스트 주입용)
        model: 모델 ID
        max_tokens: 응답 최대 토큰
        timeout: 호출 타임아웃(초)
        system_prompt: LLM에 넘길 시스템 프롬프트. 기본값은 정면(SYSTEM_PROMPT).
        fallback_fn: 폴백 문구 생성 함수(payload -> str). None이면
            fallback_comment(정면용)를 쓴다.

    Returns:
        CommentResult
    """
    fallback = fallback_fn or fallback_comment

    if client is None and not os.environ.get("ANTHROPIC_API_KEY"):
        return CommentResult(
            text=fallback(payload),
            source="fallback",
            reason="no_api_key",
        )

    try:
        if client is None:
            client = _default_client(timeout)

        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": payload.to_json()}],
            **_sampling_kwargs(model),
        )
        text = _extract_text(response)
    except ImportError:
        return CommentResult(
            text=fallback(payload),
            source="fallback",
            reason="anthropic_sdk_not_installed",
        )
    except Exception as exc:  # 네트워크/인증/레이트리밋 등 전부 폴백 처리
        return CommentResult(
            text=fallback(payload),
            source="fallback",
            reason=f"api_error({type(exc).__name__})",
            model=model,
        )

    violation = validate_comment(text, payload)
    if violation:
        return CommentResult(
            text=fallback(payload),
            source="fallback",
            reason=f"validation_failed:{violation}",
            model=model,
        )

    return CommentResult(text=text.strip(), source="llm", model=model)


def comment_for_analysis(
    analysis: dict[str, Any],
    *,
    client: Any | None = None,
    model: str = DEFAULT_MODEL,
) -> CommentResult:
    """
    분석 결과 dict 하나로 코멘트까지 만들어 주는 진입점.

    신뢰할 수 없는 결과(reliability.is_reliable == False)에는 LLM을 아예
    호출하지 않는다. 믿을 수 없는 숫자를 근거로 자연어 설명을 붙이면,
    MVP1에서 여러 겹으로 쌓아 올린 검증이 마지막 단계에서 무의미해진다 —
    사용자는 결국 그럴듯한 문장 쪽을 믿게 되기 때문이다.
    """
    if not analysis.get("success", False):
        return CommentResult(
            text=UNRELIABLE_COMMENT, source="skipped", reason="analysis_failed"
        )

    reliability = analysis.get("reliability", {})
    if not reliability.get("is_reliable", False):
        return CommentResult(
            text=UNRELIABLE_COMMENT, source="skipped", reason="not_reliable"
        )

    return generate_comment(build_payload(analysis), client=client, model=model)


def comment_for_side_analysis(
    analysis: dict[str, Any],
    *,
    client: Any | None = None,
    model: str = DEFAULT_MODEL,
) -> CommentResult:
    """
    analyze_side_image() 결과 dict 하나로 코멘트까지 만들어 주는 진입점.
    comment_for_analysis(정면)와 같은 게이트를 그대로 적용한다 —
    신뢰할 수 없는 결과에는 LLM을 아예 호출하지 않는다.
    """
    if not analysis.get("success", False):
        return CommentResult(
            text=UNRELIABLE_COMMENT, source="skipped", reason="analysis_failed"
        )

    reliability = analysis.get("reliability", {})
    if not reliability.get("is_reliable", False):
        return CommentResult(
            text=UNRELIABLE_COMMENT, source="skipped", reason="not_reliable"
        )

    return generate_comment(
        build_side_payload(analysis),
        client=client,
        model=model,
        system_prompt=SIDE_SYSTEM_PROMPT,
        fallback_fn=fallback_side_comment,
    )
