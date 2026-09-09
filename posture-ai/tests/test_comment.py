"""
MVP2 자연어 코멘트 레이어 단위 테스트.

실제 Claude API를 호출하지 않는다 — 가짜 클라이언트를 주입해서 "LLM이
이런 출력을 냈을 때 코드가 어떻게 반응하는가"를 검증한다. 네트워크나
API 키에 의존하는 테스트는 CI에서 불안정해질 뿐 아니라, 정작 확인하고
싶은 것(잘못된 출력을 걸러내는가)을 재현할 수 없다.

MediaPipe/anthropic SDK 없이도 실행 가능해야 한다 (comment.py는 표준
라이브러리만 쓰고, SDK는 호출 시점에 지연 import한다).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.comment import (
    DIRECTION_DEADZONE_DEG,
    MAX_COMMENT_CHARS,
    SAMPLING_LOCKED_MODEL_PREFIXES,
    UNRELIABLE_COMMENT,
    PromptPayload,
    _lower_side,
    _sampling_kwargs,
    build_payload,
    comment_for_analysis,
    fallback_comment,
    generate_comment,
    validate_comment,
)


# --- 테스트용 더블 ---------------------------------------------------------


class _Block:
    def __init__(self, text, type="text"):
        self.text = text
        self.type = type


class _Response:
    def __init__(self, blocks):
        self.content = blocks


class FakeMessages:
    def __init__(self, blocks=None, exc=None):
        self._blocks = blocks or []
        self._exc = exc
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self._exc is not None:
            raise self._exc
        return _Response(self._blocks)


class FakeClient:
    """anthropic.Anthropic의 최소 인터페이스(messages.create)만 흉내낸다."""

    def __init__(self, text=None, blocks=None, exc=None):
        if blocks is None:
            blocks = [_Block(text)] if text is not None else []
        self.messages = FakeMessages(blocks=blocks, exc=exc)


def make_analysis(
    shoulder_angle=2.31,
    shoulder_verdict="정상",
    pelvis_angle=-0.78,
    pelvis_verdict="정상",
    is_reliable=True,
    bands=None,
):
    """api_mvp1/analysis 응답 형태의 dict를 만든다."""
    keypoint_confidence = bands if bands is not None else [
        {"name": "left_shoulder", "visibility": 0.95, "band": "높음"},
        {"name": "right_shoulder", "visibility": 0.93, "band": "높음"},
    ]
    return {
        "success": True,
        "quality": {"is_valid": True, "issue": ""},
        "reliability": {"is_reliable": is_reliable, "issues": [] if is_reliable else ["실루엣 비정상"]},
        "confidence": 0.94,
        "keypoint_confidence": keypoint_confidence,
        "shoulder": {"angle_deg": shoulder_angle, "verdict": shoulder_verdict},
        "pelvis": {"angle_deg": pelvis_angle, "verdict": pelvis_verdict, "note": "..."},
        "disclaimer": "참고용",
    }


def make_payload(**kwargs):
    return build_payload(make_analysis(**kwargs))


# --- 페이로드 구성 ---------------------------------------------------------


def test_payload_keeps_code_computed_values():
    # LLM에 넘기는 값은 코드가 계산한 각도/판정 그대로여야 한다.
    payload = make_payload(shoulder_angle=7.5, shoulder_verdict="경미")
    assert payload.shoulder_angle_deg == 7.5
    assert payload.shoulder_verdict == "경미"


def test_payload_direction_follows_angles_sign_convention():
    # angles.py 규약: 양수 -> 오른쪽이 더 아래, 음수 -> 왼쪽이 더 아래.
    assert _lower_side(8.0) == "right"
    assert _lower_side(-8.0) == "left"


def test_payload_direction_deadzone_reports_level():
    # 판정은 5도 기준이지만, 방향 표현은 별도의 좁은 데드존을 쓴다.
    # 0.2도 차이를 "오른쪽이 낮습니다"라고 말하면 측정 오차를 실제
    # 비대칭처럼 전달하게 되기 때문이다.
    assert _lower_side(DIRECTION_DEADZONE_DEG / 2) == "level"
    assert _lower_side(-DIRECTION_DEADZONE_DEG / 2) == "level"


def test_payload_collects_low_and_medium_confidence_points():
    payload = make_payload(
        bands=[
            {"name": "left_ear", "visibility": 0.51, "band": "보통"},
            {"name": "right_ear", "visibility": 0.32, "band": "낮음"},
            {"name": "left_shoulder", "visibility": 0.95, "band": "높음"},
        ]
    )
    assert payload.low_confidence_points == ["왼쪽 귀", "오른쪽 귀"]
    assert "left_shoulder" not in payload.low_confidence_points


def test_payload_json_has_no_image_or_raw_coordinates():
    # 코멘트를 쓰는 데 필요 없는 정보는 외부로 내보내지 않는다.
    body = make_payload().to_json()
    assert "keypoints" not in body
    assert "image" not in body
    assert "visibility" not in body


# --- 출력 검증 (가드레일) ---------------------------------------------------


def test_valid_comment_passes():
    payload = make_payload()
    text = "어깨와 골반 모두 좌우가 고른 편입니다. 지금 자세를 유지해 보세요."
    assert validate_comment(text, payload) == ""


def test_rejects_any_number_in_comment():
    # LLM이 각도를 다시 언급하면 코드가 확정한 값과 어긋날 수 있다.
    # 숫자를 아예 금지해서 수치 왜곡 가능성을 원천 차단한다.
    payload = make_payload()
    text = "어깨가 2.31도 기울어져 있으며 좌우가 고른 편입니다."
    assert validate_comment(text, payload) == "contains_number"


def test_rejects_hallucinated_number_even_if_plausible():
    payload = make_payload(shoulder_angle=2.31)
    text = "어깨가 약 8도 정도 기울어 보입니다. 좌우가 고른 편입니다."
    assert validate_comment(text, payload) == "contains_number"


def test_rejects_verdict_not_in_payload():
    # 어깨/골반 모두 "정상"인데 코멘트에 "주의"가 등장 -> 판정 뒤집기.
    payload = make_payload(shoulder_verdict="정상", pelvis_verdict="정상")
    violation = validate_comment("어깨는 정상이지만 주의가 필요합니다.", payload)
    assert violation.startswith("verdict_mismatch")


def test_allows_verdict_present_in_payload():
    payload = make_payload(shoulder_verdict="경미", pelvis_verdict="정상")
    text = "어깨는 좌우 차이가 경미하게 있고, 골반은 정상 범위입니다."
    assert validate_comment(text, payload) == ""


def test_rejects_medical_diagnosis_phrases():
    # NFR-04: 의료 진단이 아니어야 한다.
    payload = make_payload()
    for text in (
        "척추측만증이 의심되니 확인해 보세요. 좌우 균형을 살펴보세요.",
        "가까운 곳에서 치료를 받아 보시기를 권합니다. 어깨가 고른 편입니다.",
        "허리 디스크 가능성이 있어 보입니다. 자세를 확인해 주세요.",
    ):
        assert validate_comment(text, payload).startswith("forbidden_phrase")


def test_rejects_empty_and_overlong_comment():
    payload = make_payload()
    assert validate_comment("   ", payload) == "empty_response"
    assert validate_comment("짧음", payload).startswith("too_short")
    assert validate_comment("가" * (MAX_COMMENT_CHARS + 1), payload).startswith("too_long")


# --- 폴백 문구 -------------------------------------------------------------


def test_fallback_is_deterministic():
    payload = make_payload()
    assert fallback_comment(payload) == fallback_comment(payload)


def test_fallback_itself_passes_validation():
    # 폴백은 검증 실패 시의 대체재이므로, 폴백 자체가 규칙을 어기면
    # 안전장치가 무의미해진다. 모든 판정 조합에서 검증을 통과해야 한다.
    for shoulder in ("정상", "경미", "주의"):
        for pelvis in ("정상", "경미", "주의"):
            payload = make_payload(
                shoulder_angle=9.0,
                shoulder_verdict=shoulder,
                pelvis_angle=-9.0,
                pelvis_verdict=pelvis,
                bands=[{"name": "left_ear", "visibility": 0.5, "band": "보통"}],
            )
            assert validate_comment(fallback_comment(payload), payload) == "", (
                f"{shoulder}/{pelvis} 조합의 폴백 문구가 검증을 통과하지 못함"
            )


def test_fallback_mentions_subject_perspective_side():
    # MediaPipe의 좌/우는 피사체 본인 기준이다(§7-1 미러링 버그의 원인).
    # 코멘트에서도 이 점을 흐리면 같은 오해가 사용자 화면에서 재현된다.
    payload = make_payload(shoulder_angle=9.0, shoulder_verdict="경미")
    text = fallback_comment(payload)
    assert "본인 기준" in text
    assert "오른쪽" in text  # 양수 -> 오른쪽이 더 낮음


# --- 호출 오케스트레이션 ----------------------------------------------------


def test_generate_uses_llm_text_when_valid():
    good = "어깨와 골반 모두 좌우가 고른 편입니다. 지금 자세를 유지해 보세요."
    result = generate_comment(make_payload(), client=FakeClient(text=good))
    assert result.source == "llm"
    assert result.text == good


def test_generate_falls_back_when_llm_violates_rules():
    bad = "어깨가 12.5도 기울어 척추측만증이 의심됩니다."
    payload = make_payload()
    result = generate_comment(payload, client=FakeClient(text=bad))
    assert result.source == "fallback"
    assert result.reason.startswith("validation_failed")
    assert result.text == fallback_comment(payload)
    # 사용자에게는 위반한 문구가 절대 노출되지 않아야 한다.
    assert "척추측만증" not in result.text


def test_generate_falls_back_on_api_error():
    # 네트워크/레이트리밋 장애로 각도 분석 응답 전체가 실패하면 안 된다.
    payload = make_payload()
    result = generate_comment(payload, client=FakeClient(exc=RuntimeError("boom")))
    assert result.source == "fallback"
    assert result.reason == "api_error(RuntimeError)"
    assert result.text == fallback_comment(payload)


def test_generate_ignores_non_text_blocks():
    # content는 텍스트가 아닌 블록이 섞일 수 있으므로 content[0]을
    # 그대로 꺼내지 않는다.
    blocks = [
        _Block(None, type="thinking"),
        _Block("어깨와 골반 모두 좌우가 고른 편입니다. 유지해 보세요.", type="text"),
    ]
    result = generate_comment(make_payload(), client=FakeClient(blocks=blocks))
    assert result.source == "llm"
    assert result.text.startswith("어깨와 골반")


def test_sampling_params_omitted_for_models_that_reject_them():
    # Sonnet 5 세대는 기본값이 아닌 샘플링 파라미터를 거부한다.
    # 모델을 환경변수로 바꿀 수 있으므로 코드가 이 분기를 들고 있어야 한다.
    for prefix in SAMPLING_LOCKED_MODEL_PREFIXES:
        assert _sampling_kwargs(prefix) == {}


def test_sampling_params_omitted_when_sdk_rejects_temperature(monkeypatch):
    # 회귀 방지(MVP4 실제 API 검증 중 발견): 모델이 temperature를
    # 지원해도 설치된 SDK가 그 인자를 모르면 TypeError로 호출 자체가
    # 실패한다. 모델 지원 여부와 SDK 지원 여부는 별개다.
    import app.comment as comment_module

    monkeypatch.setattr(comment_module, "_sdk_accepts_temperature", lambda: False)
    assert _sampling_kwargs("claude-haiku-4-5-20251001") == {}

    monkeypatch.setattr(comment_module, "_sdk_accepts_temperature", lambda: True)
    assert _sampling_kwargs("claude-haiku-4-5-20251001") == {"temperature": 0.0}


def test_generate_sends_temperature_zero_when_sdk_supports_it(monkeypatch):
    import app.comment as comment_module

    monkeypatch.setattr(comment_module, "_sdk_accepts_temperature", lambda: True)
    client = FakeClient(text="어깨와 골반 모두 좌우가 고른 편입니다. 유지해 보세요.")
    generate_comment(make_payload(), client=client, model="claude-haiku-4-5-20251001")
    assert client.messages.calls[0]["temperature"] == 0.0


def test_generate_omits_temperature_when_sdk_lacks_it(monkeypatch):
    import app.comment as comment_module

    monkeypatch.setattr(comment_module, "_sdk_accepts_temperature", lambda: False)
    client = FakeClient(text="어깨와 골반 모두 좌우가 고른 편입니다. 유지해 보세요.")
    generate_comment(make_payload(), client=client, model="claude-haiku-4-5-20251001")
    assert "temperature" not in client.messages.calls[0]


# --- 신뢰도 게이트 ---------------------------------------------------------


def test_no_llm_call_when_result_is_unreliable():
    # 믿을 수 없는 숫자에 자연어 설명을 붙이면, MVP1에서 여러 겹으로
    # 쌓아 올린 검증이 마지막 단계에서 무의미해진다.
    client = FakeClient(text="이 문구는 쓰이면 안 됩니다. 좌우가 고른 편입니다.")
    result = comment_for_analysis(make_analysis(is_reliable=False), client=client)
    assert result.source == "skipped"
    assert result.reason == "not_reliable"
    assert result.text == UNRELIABLE_COMMENT
    assert client.messages.calls == []  # 실제로 호출되지 않았는지 확인


def test_no_llm_call_when_person_not_detected():
    client = FakeClient(text="쓰이면 안 되는 문구입니다. 좌우가 고른 편입니다.")
    analysis = {"success": False, "reason": "no_person_detected"}
    result = comment_for_analysis(analysis, client=client)
    assert result.source == "skipped"
    assert client.messages.calls == []


def test_comment_does_not_mutate_analysis_result():
    # MVP2는 MVP1 결과에 필드를 덧붙이기만 한다. 각도나 판정을 건드리면
    # "판단은 LLM, 계산은 코드" 원칙이 깨진다.
    analysis = make_analysis(shoulder_angle=7.5, shoulder_verdict="경미")
    before = {
        "shoulder": dict(analysis["shoulder"]),
        "pelvis": dict(analysis["pelvis"]),
        "reliability": dict(analysis["reliability"]),
    }
    comment_for_analysis(
        analysis, client=FakeClient(text="어깨는 좌우 차이가 경미합니다. 확인해 보세요.")
    )
    assert analysis["shoulder"] == before["shoulder"]
    assert analysis["pelvis"] == before["pelvis"]
    assert analysis["reliability"] == before["reliability"]


def test_payload_verdicts_set_used_for_validation():
    payload = PromptPayload(
        shoulder_angle_deg=1.0,
        shoulder_verdict="정상",
        shoulder_lower_side="level",
        pelvis_angle_deg=20.0,
        pelvis_verdict="주의",
        pelvis_lower_side="right",
    )
    assert payload.verdicts() == {"정상", "주의"}
    # "경미"는 payload에 없으므로 거부되어야 한다.
    assert validate_comment("골반이 경미하게 기울어 보입니다. 확인해 주세요.", payload).startswith(
        "verdict_mismatch"
    )


def test_korean_topic_particle_is_correct():
    # "어깨은", "골반는" 같은 문장이 나오면 폴백이 폴백 역할을 못 한다.
    from app.comment import _topic_particle

    assert _topic_particle("어깨") == "는"   # 받침 없음
    assert _topic_particle("골반") == "은"   # 받침 ㄴ
    assert _topic_particle("머리") == "는"


def test_fallback_avoids_repeating_identical_sentence():
    # 어깨/골반 판정이 같고 둘 다 좌우 차이가 없으면 한 문장으로 합친다.
    payload = make_payload(shoulder_angle=0.1, pelvis_angle=-0.2)
    text = fallback_comment(payload)
    assert text.startswith("어깨와 골반 모두")
    assert text.count("좌우가 고른 편입니다") == 1


def test_fallback_has_no_broken_particles():
    for shoulder in ("정상", "경미", "주의"):
        for pelvis in ("정상", "경미", "주의"):
            text = fallback_comment(
                make_payload(
                    shoulder_angle=9.0,
                    shoulder_verdict=shoulder,
                    pelvis_angle=-9.0,
                    pelvis_verdict=pelvis,
                )
            )
            assert "어깨은" not in text
            assert "골반는" not in text
