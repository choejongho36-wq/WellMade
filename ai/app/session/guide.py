"""
스쿼트 세션 진행 상태 및 안내 메시지 결정.

책임:
- 현재 세션 단계와 이벤트를 기반으로 다음 단계를 결정
- 다음 단계에서 프론트엔드에 전달할 안내 문구 결정
- 카메라 방향 결정

비책임:
- TTS 실행
- 카메라 제어
- 실제 스쿼트 자세 판정
- 반복 횟수 측정

실시간 자세 판정은 app/coaching/realtime.py에서 담당한다.
"""

from typing import Literal

from app.session.messages import (
    FRONT_INSTRUCTION_MESSAGE,
    FRONT_READY_MESSAGE,
    FRONT_SETUP_MESSAGE,
    SESSION_FINISH_MESSAGE,
    SESSION_START_MESSAGE,
    SIDE_INSTRUCTION_MESSAGE,
    SIDE_READY_MESSAGE,
    SIDE_SETUP_MESSAGE,
)


SessionStage = Literal[
    "session_start",
    "side_setup",
    "side_instruction",
    "side_ready",
    "side_squat",
    "front_setup",
    "front_instruction",
    "front_ready",
    "front_squat",
    "session_finish",
]

SessionEvent = Literal[
    "session_started",
    "camera_ready",
    "guide_completed",
    "set_started",
    "set_completed",
]

CameraView = Literal[
    "side",
    "front",
]


STAGE_MESSAGES: dict[SessionStage, str] = {
    "session_start": SESSION_START_MESSAGE,
    "side_setup": SIDE_SETUP_MESSAGE,
    "side_instruction": SIDE_INSTRUCTION_MESSAGE,
    "side_ready": SIDE_READY_MESSAGE,
    "front_setup": FRONT_SETUP_MESSAGE,
    "front_instruction": FRONT_INSTRUCTION_MESSAGE,
    "front_ready": FRONT_READY_MESSAGE,
    "session_finish": SESSION_FINISH_MESSAGE,
}


STAGE_CAMERA_VIEW: dict[SessionStage, CameraView | None] = {
    "session_start": None,
    "side_setup": "side",
    "side_instruction": "side",
    "side_ready": "side",
    "side_squat": "side",
    "front_setup": "front",
    "front_instruction": "front",
    "front_ready": "front",
    "front_squat": "front",
    "session_finish": None,
}


TRANSITIONS: dict[
    tuple[SessionStage, SessionEvent],
    SessionStage,
] = {
    (
        "session_start",
        "session_started",
    ): "side_setup",

    (
        "side_setup",
        "camera_ready",
    ): "side_instruction",

    (
        "side_instruction",
        "guide_completed",
    ): "side_ready",

    (
        "side_ready",
        "set_started",
    ): "side_squat",

    (
        "side_squat",
        "set_completed",
    ): "front_setup",

    (
        "front_setup",
        "camera_ready",
    ): "front_instruction",

    (
        "front_instruction",
        "guide_completed",
    ): "front_ready",

    (
        "front_ready",
        "set_started",
    ): "front_squat",

    (
        "front_squat",
        "set_completed",
    ): "session_finish",
}


def get_next_stage(
    current_stage: SessionStage,
    event: SessionEvent,
) -> SessionStage:
    """
    현재 단계와 이벤트를 기반으로 다음 세션 단계를 반환한다.

    허용되지 않은 상태 전이는 ValueError를 발생시킨다.
    """

    transition = TRANSITIONS.get((current_stage, event))

    if transition is None:
        raise ValueError(
            f"허용되지 않은 세션 상태 전이입니다: "
            f"{current_stage} + {event}"
        )

    return transition


def build_guide_response(
    stage: SessionStage,
) -> dict:
    """
    특정 세션 단계에 해당하는 안내 정보를 반환한다.
    """

    return {
        "stage": stage,
        "camera_view": STAGE_CAMERA_VIEW[stage],
        "message": STAGE_MESSAGES.get(stage),
    }


def get_next_guide(
    current_stage: SessionStage,
    event: SessionEvent,
) -> dict:
    """
    현재 세션 상태와 이벤트를 받아
    다음 단계 및 안내 메시지를 반환한다.
    """

    next_stage = get_next_stage(
        current_stage=current_stage,
        event=event,
    )

    return build_guide_response(next_stage)