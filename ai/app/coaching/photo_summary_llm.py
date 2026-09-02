"""
사진 코칭 "분석 결과" 자연어 요약 (2026-09-02).

배경: 사진 코칭 페이지의 "분석 결과" 패널이 원래는 무릎/엉덩이 각도 등을 막대그래프
숫자로 그대로 보여줬는데, 사용자 요청으로 이 숫자 표시를 없애고 대신 LLM(Bedrock, 기본
Nova Micro)이 문장으로 정리해서 보여주는 방식으로 바꿨다.

중요: 판정 자체(정상/이상 여부, 어떤 부위가 이상인지)는 여전히 규칙 기반
(pose/rules.py 임곗값 비교, coaching/realtime.py의 judge_realtime_coaching)이 그대로
담당한다. 이 모듈은 그 판정 결과(정상/이상 여부 + 부위별 메시지 + 원본 각도·비율 수치)를
받아 문장으로 "정리"만 한다 — session/report.py의 세션 리포트 요약(AI-12)과 정확히 같은
패턴이다(규칙 기반 집계 → LLM 요약 시도 → 실패 시 규칙 기반 폴백 문구). 다른 세 LLM 모듈
(session/report.py, coaching/hyperextension_llm_check.py)과 마찬가지로 모델 ID를
독립된 환경변수로 분리해서, 이 기능만 따로 모델을 바꿔 실험할 수 있게 했다.

LLM이 이미 준 판정 결과를 새로 "재판단"하지 않도록(=규칙 기반 판정과 LLM 설명이 서로
어긋나는 사고를 막기 위해) 프롬프트에서 "판정 자체를 바꾸지 말라"고 명시한다.

2026-09-02 정정: 사진 코칭이 처음엔 "정면 필수 + 측면 선택"이었다가, 실제 AI-06 판정의
핵심 값(무릎/엉덩이 각도 등)이 전부 측면 사진에서 나온다는 걸 반영해 "측면 필수 + 정면
선택"으로 바뀌었다. 그래서 이 모듈이 받는 플래그도 has_side_photo(측면 포함 여부)에서
has_front_photo(정면 포함 여부)로 바뀌었다 — 이제 측면은 항상 있어서 "포함 여부"를 LLM에
알려줄 의미가 없고, 대신 정면 포함 여부(무릎모임 판정이 같이 있었는지)가 문장에 영향을 준다.
"""

from __future__ import annotations

import os
from typing import Any, Optional

try:
    import boto3

    _BOTO3_AVAILABLE = True
except ImportError:
    _BOTO3_AVAILABLE = False

# session/report.py, coaching/hyperextension_llm_check.py와 같은 AWS_BEDROCK_REGION을
# 공유한다(리전은 서버 전체에서 하나면 충분) — 모델 ID만 이 모듈 전용 환경변수로 분리.
AWS_REGION_ENV_VAR = "AWS_BEDROCK_REGION"
MODEL_ENV_VAR = "PHOTO_SUMMARY_BEDROCK_MODEL_ID"

# 문장 요약이라 세션 리포트(AI-12, MAX_TOKENS=400)와 비슷한 수준이면 충분하다.
MAX_TOKENS = 500

# issue.part / metrics 키를 사람이 읽을 한국어로 바꾼다 — frontend/src/lib/squatPose.js의
# PART_LABELS와 같은 매핑을 서버 쪽에도 둔다(용도가 달라 공유 모듈로 묶지 않았다: 프론트는
# 화면 배지 라벨, 여기는 LLM 프롬프트에 넣을 텍스트).
PART_LABELS_KO = {
    "knee": "무릎 각도",
    "hip": "엉덩이(고관절) 각도",
    "gaze": "시선·목 기울기",
    "heel": "발뒤꿈치 들림",
    "knee_over_toe": "무릎-발끝 거리",
    "center_of_mass": "무게중심 정렬",
    "knee_valgus": "무릎 모임",
}

METRIC_LABELS_KO = {
    "knee_angle": "무릎 각도(도)",
    "hip_angle": "엉덩이(고관절) 각도(도)",
    "shoulder_forward_lean_deg": "시선·목 기울기(도)",
    "heel_lift_ratio": "발뒤꿈치 들림 비율",
    "knee_over_toe_ratio": "무릎-발끝 비율",
    "torso_shin_lean_gap_deg": "무게중심 정렬 차이(도)",
    "knee_valgus_ratio": "무릎모임 비율(무릎너비/발목너비)",
}


def _get_client():
    """Bedrock Runtime client를 필요할 때 생성한다. 리전 미설정/boto3 미설치 시 None."""

    if not _BOTO3_AVAILABLE:
        return None

    region = os.environ.get(AWS_REGION_ENV_VAR)
    if not region:
        return None

    return boto3.client("bedrock-runtime", region_name=region)


def _fallback_summary_message(
    is_normal: bool,
    issues: list[dict],
) -> str:
    """LLM을 못 부를 때 쓰는 규칙 기반 대체 문구."""

    if is_normal:
        return "전체적으로 정상 범위의 스쿼트 자세예요. 지금처럼 유지해주세요."

    parts = ", ".join(
        PART_LABELS_KO.get(issue["part"], issue["part"]) for issue in issues
    )
    return f"{parts} 부분에서 점검이 필요한 자세예요. 아래 안내를 참고해서 교정해보세요."


def _generate_llm_summary(
    *,
    is_normal: bool,
    confidence: float,
    issues: list[dict],
    metrics: dict[str, Optional[float]],
    has_front_photo: bool,
    client,
) -> Optional[str]:
    """규칙 기반 판정 결과를 Bedrock LLM에 전달해 자연어 분석 결과 문장을 생성한다.

    사진 원본이나 좌표는 전달하지 않는다 — 이미 계산된 판정 결과만 넘긴다
    (session/report.py의 "원본 프레임 데이터는 LLM에 전달하지 않는다"와 같은 원칙).
    """

    model_id = os.environ.get(MODEL_ENV_VAR)
    if not model_id:
        return None

    system_prompt = (
        "당신은 운동 자세 코칭 앱 WellMade의 사진 코칭 '분석 결과' 작성기입니다. "
        "아래에 제공되는 규칙 기반 판정 결과(정상/이상 여부, 이상 부위별 메시지, 원본 각도·비율 "
        "수치)만 근거로 삼아, 사용자가 올린 스쿼트 사진에 대한 분석 결과를 정리하세요. "
        "한국어 해요체를 사용하고, 4~6문장 정도로 작성하세요. "
        "제공된 수치나 메시지에 없는 사실, 의학적 진단, 부상 위험을 절대 지어내지 마세요. "
        "이미 내려진 판정(정상/이상 여부, 이상 부위)을 임의로 바꾸거나 새로운 이상 소견을 "
        "추가하지 말고, 주어진 판정을 사용자가 이해하기 쉬운 문장으로 풀어 설명하는 역할만 "
        "하세요."
    )

    issue_lines = (
        "\n".join(
            f"- [{PART_LABELS_KO.get(issue['part'], issue['part'])}] {issue['message']}"
            for issue in issues
        )
        or "없음"
    )
    metric_lines = (
        "\n".join(
            f"- {METRIC_LABELS_KO.get(key, key)}: {value:.1f}"
            for key, value in metrics.items()
            if value is not None
        )
        or "없음"
    )

    user_message = (
        "[규칙 기반 판정 결과]\n"
        f"- 전체 판정: {'정상' if is_normal else '이상 있음'}\n"
        f"- 신뢰도: {confidence * 100:.0f}%\n"
        f"- 정면 사진 포함 여부: {'포함(무릎 모임 여부도 같이 판정)' if has_front_photo else '미포함(측면 사진만 분석)'}\n"
        f"[이상 소견]\n{issue_lines}\n"
        f"[원본 수치]\n{metric_lines}"
    )

    try:
        response = client.converse(
            modelId=model_id,
            system=[{"text": system_prompt}],
            messages=[
                {
                    "role": "user",
                    "content": [{"text": user_message}],
                }
            ],
            inferenceConfig={"maxTokens": MAX_TOKENS},
        )

        content = response["output"]["message"]["content"]
        text_blocks = [block["text"] for block in content if "text" in block]
        generated = "".join(text_blocks).strip()
        return generated or None

    except Exception:
        # LLM 오류가 분석 결과 표시 자체를 막지 않도록 상위에서 fallback으로 전환한다.
        return None


def summarize_photo_analysis(
    *,
    is_normal: bool,
    confidence: float,
    issues: list[dict],
    metrics: dict[str, Optional[float]],
    has_front_photo: bool,
    client: Any = None,
) -> dict:
    """사진 코칭 판정 결과 → 자연어 분석 결과 요약. 메인 진입점.

    처리 순서:
    1. fallback 문구를 항상 먼저 준비한다.
    2. Bedrock client가 있으면 LLM 요약을 시도한다.
    3. 실패하면(모델 ID 미설정, 자격증명 없음, 호출 실패 등) fallback을 돌려준다.
    """

    fallback_message = _fallback_summary_message(is_normal=is_normal, issues=issues)

    active_client = client if client is not None else _get_client()

    if active_client is not None:
        generated = _generate_llm_summary(
            is_normal=is_normal,
            confidence=confidence,
            issues=issues,
            metrics=metrics,
            has_front_photo=has_front_photo,
            client=active_client,
        )
        if generated:
            return {
                "summary_message": generated,
                "generation_source": "llm",
            }

    return {
        "summary_message": fallback_message,
        "generation_source": "fallback",
    }
