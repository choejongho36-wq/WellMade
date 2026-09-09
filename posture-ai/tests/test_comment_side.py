"""
MVP3 측면 코멘트 레이어 단위 테스트.

test_comment.py와 같은 원칙 — 실제 Claude API를 호출하지 않고, 가짜
클라이언트로 "LLM 출력에 코드가 어떻게 반응하는가"만 검증한다.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.comment import (
    UNRELIABLE_COMMENT,
    SidePromptPayload,
    build_side_payload,
    comment_for_side_analysis,
    fallback_side_comment,
    validate_comment,
)
from tests.test_comment import FakeClient  # 기존 더블 재사용


def make_side_analysis(
    forward_head_angle=5.0,
    forward_head_verdict="정상",
    round_shoulder_angle=60.0,
    round_shoulder_verdict="정상",
    is_reliable=True,
    near_side_determined=True,
    bands=None,
):
    keypoint_confidence = bands if bands is not None else [
        {"name": "left_ear", "visibility": 0.9, "band": "높음"},
    ]
    return {
        "success": True,
        "view": "side",
        "near_side": "left",
        "near_side_determined": near_side_determined,
        "quality": {"is_valid": True, "issue": ""},
        "reliability": {"is_reliable": is_reliable, "issues": [] if is_reliable else ["측면 불확실"]},
        "confidence": 0.9,
        "keypoint_confidence": keypoint_confidence,
        "forward_head": {"angle_deg": forward_head_angle, "verdict": forward_head_verdict, "note": "..."},
        "round_shoulder": {"angle_deg": round_shoulder_angle, "verdict": round_shoulder_verdict, "note": "..."},
        "disclaimer": "참고용",
    }


def make_side_payload(**kwargs):
    return build_side_payload(make_side_analysis(**kwargs))


# --- 페이로드 구성 -----------------------------------------------------------


def test_side_payload_keeps_code_computed_values():
    payload = make_side_payload(forward_head_angle=18.0, forward_head_verdict="경미")
    assert payload.forward_head_angle_deg == 18.0
    assert payload.forward_head_verdict == "경미"


def test_side_payload_json_has_no_raw_coordinates():
    body = make_side_payload().to_json()
    assert "keypoints" not in body
    assert "image" not in body


def test_side_payload_carries_near_side_determined_flag():
    payload = make_side_payload(near_side_determined=False)
    assert payload.near_side_determined is False
    assert "false" in payload.to_json().lower()


# --- 기존 가드레일 재사용 확인 (validate_comment는 payload 종류를 모름) -------


def test_existing_guardrails_reject_numbers_in_side_comment():
    payload = make_side_payload()
    text = "고개가 5도 정도 나와 있고 어깨도 살짝 말려 있습니다."
    assert validate_comment(text, payload) == "contains_number"


def test_existing_guardrails_reject_verdict_not_in_side_payload():
    payload = make_side_payload(forward_head_verdict="정상", round_shoulder_verdict="정상")
    text = "전방머리자세는 정상이지만 라운드숄더는 주의가 필요합니다."
    assert validate_comment(text, payload).startswith("verdict_mismatch")


def test_existing_guardrails_reject_medical_phrases_in_side_comment():
    payload = make_side_payload()
    text = "일자목 진단이 의심되니 병원을 방문하세요."
    assert validate_comment(text, payload).startswith("forbidden_phrase")


# --- 폴백 문구 ---------------------------------------------------------------


def test_side_fallback_is_deterministic():
    payload = make_side_payload()
    assert fallback_side_comment(payload) == fallback_side_comment(payload)


def test_side_fallback_itself_passes_validation():
    # MVP3_착수정리 §3-E: 새 지표 조합에서도 폴백이 자기검증을 통과해야 한다.
    for fh in ("정상", "경미", "주의"):
        for rs in ("정상", "경미", "주의"):
            for determined in (True, False):
                payload = make_side_payload(
                    forward_head_angle=20.0,
                    forward_head_verdict=fh,
                    round_shoulder_angle=40.0,
                    round_shoulder_verdict=rs,
                    near_side_determined=determined,
                    bands=[{"name": "left_hip", "visibility": 0.55, "band": "보통"}],
                )
                assert validate_comment(fallback_side_comment(payload), payload) == "", (
                    f"{fh}/{rs}/determined={determined} 조합의 폴백이 검증 실패"
                )


def test_side_fallback_mentions_uncertain_profile_when_not_determined():
    payload = make_side_payload(near_side_determined=False)
    text = fallback_side_comment(payload)
    assert "완전한 옆모습" in text


# --- 호출 오케스트레이션 / 신뢰도 게이트 ---------------------------------------


def test_generate_side_uses_llm_text_when_valid():
    good = "전방머리자세는 두드러지지 않는 편입니다. 어깨 말림도 크지 않습니다."
    result = comment_for_side_analysis(make_side_analysis(), client=FakeClient(text=good))
    assert result.source == "llm"
    assert result.text == good


def test_generate_side_falls_back_when_llm_violates_rules():
    bad = "고개가 20도 앞으로 나와 있습니다."
    result = comment_for_side_analysis(make_side_analysis(), client=FakeClient(text=bad))
    assert result.source == "fallback"
    assert result.reason.startswith("validation_failed")


def test_no_llm_call_when_side_result_is_unreliable():
    client = FakeClient(text="쓰이면 안 되는 문구입니다.")
    result = comment_for_side_analysis(make_side_analysis(is_reliable=False), client=client)
    assert result.source == "skipped"
    assert result.reason == "not_reliable"
    assert result.text == UNRELIABLE_COMMENT
    assert client.messages.calls == []


def test_no_llm_call_when_side_person_not_detected():
    client = FakeClient(text="쓰이면 안 되는 문구입니다.")
    analysis = {"success": False, "reason": "no_person_detected"}
    result = comment_for_side_analysis(analysis, client=client)
    assert result.source == "skipped"
    assert client.messages.calls == []


def test_side_payload_verdicts_used_for_validation():
    payload = SidePromptPayload(
        forward_head_angle_deg=5.0,
        forward_head_verdict="정상",
        round_shoulder_angle_deg=60.0,
        round_shoulder_verdict="정상",
        near_side_determined=True,
    )
    assert payload.verdicts() == {"정상"}
    assert validate_comment("전체적으로 경미한 경향이 있어 보입니다.", payload).startswith(
        "verdict_mismatch"
    )
