"""posture-ai 엔드포인트 통합 테스트.

실제 LLM API는 호출하지 않는다(fixture가 환경변수를 지운다).
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

fastapi_testclient = pytest.importorskip("fastapi.testclient")
TestClient = fastapi_testclient.TestClient

from app.landmarks import POSE_LANDMARK_NAMES  # noqa: E402
from app.main import app  # noqa: E402

_INDEX = {name: i for i, name in enumerate(POSE_LANDMARK_NAMES)}


@pytest.fixture(autouse=True)
def no_real_api_calls(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


def make_landmarks(**overrides):
    """33개 랜드마크를 만들고 지정한 관절만 덮어쓴다."""
    lms = [{"x": 0.5, "y": 0.5, "z": 0.0, "visibility": 0.9} for _ in range(33)]
    for name, (x, y, z, v) in overrides.items():
        lms[_INDEX[name]] = {"x": x, "y": y, "z": z, "visibility": v}
    return lms


# sample41.jpg 실측 좌표 (정상적인 측면 사진)
SIDE_LANDMARKS = make_landmarks(
    left_ear=(0.4673, 0.1172, -0.4396, 1.0),
    right_ear=(0.4613, 0.1142, -0.0652, 0.9999),
    left_shoulder=(0.5073, 0.2306, -0.6419, 1.0),
    right_shoulder=(0.4824, 0.2383, 0.2256, 0.9996),
    left_hip=(0.4745, 0.5021, -0.2444, 0.9986),
    right_hip=(0.4654, 0.4973, 0.2441, 0.9969),
)

# sample27.jpg 실측 좌표 (정상적인 정면 사진)
FRONT_LANDMARKS = make_landmarks(
    left_shoulder=(0.6425, 0.2382, -0.49, 1.0),
    right_shoulder=(0.3716, 0.2586, -0.44, 1.0),
    left_hip=(0.5689, 0.4797, -0.015, 0.9998),
    right_hip=(0.4253, 0.4779, 0.015, 0.9998),
)


def post(path, landmarks, width=720, height=900):
    with TestClient(app) as client:
        return client.post(
            path,
            json={"landmarks": landmarks, "image_width": width, "image_height": height},
        )


# --- 정상 동작 -------------------------------------------------------------


def test_side_returns_metrics_and_comment():
    res = post("/posture-api/analyze/side", SIDE_LANDMARKS)
    assert res.status_code == 200
    body = res.json()

    assert body["view"] == "side"
    assert body["near_side"] in ("left", "right")
    assert body["forward_head"]["verdict"] in ("정상", "경미", "주의")
    assert body["round_shoulder"]["verdict"] in ("정상", "경미", "주의")
    assert body["comment"]["text"]


def test_front_returns_metrics_and_comment():
    res = post("/posture-api/analyze/front", FRONT_LANDMARKS)
    assert res.status_code == 200
    body = res.json()

    assert body["view"] == "front"
    assert body["shoulder"]["verdict"] in ("정상", "경미", "주의")
    assert body["pelvis"]["verdict"] in ("정상", "경미", "주의")


def test_agent_endpoint_adds_turns_and_tool_calls():
    res = post("/posture-api/analyze/side/agent", SIDE_LANDMARKS)
    assert res.status_code == 200
    comment = res.json()["comment"]
    # API 키가 없으므로 fallback이지만, 에이전트 전용 필드는 있어야 한다
    assert "turns" in comment
    assert "tool_calls" in comment


# --- 입력 검증 -------------------------------------------------------------


def test_rejects_wrong_landmark_count():
    res = post("/posture-api/analyze/side", SIDE_LANDMARKS[:20])
    assert res.status_code == 422  # Pydantic min_length=33


def test_rejects_zero_image_size():
    res = post("/posture-api/analyze/side", SIDE_LANDMARKS, width=0)
    assert res.status_code == 422  # gt=0


def test_rejects_visibility_out_of_range():
    bad = make_landmarks(left_ear=(0.5, 0.1, 0.0, 1.5))
    res = post("/posture-api/analyze/side", bad)
    assert res.status_code == 422  # le=1.0


# --- 종횡비 보정이 실제로 반영되는지 ---------------------------------------


def test_image_size_changes_angle():
    # 종횡비가 다르면 각도가 달라져야 한다. 같은 좌표라도 이미지 비율이
    # 다르면 실제 기울기가 다르기 때문 — pixel_xy()가 동작한다는 증거다.
    square = post("/posture-api/analyze/side", SIDE_LANDMARKS, 800, 800).json()
    tall = post("/posture-api/analyze/side", SIDE_LANDMARKS, 800, 1600).json()

    assert square["forward_head"]["angle_deg"] != tall["forward_head"]["angle_deg"]


# --- 신뢰도 게이트 ---------------------------------------------------------


def test_mannequin_like_coords_are_flagged_unreliable():
    # 어깨/골반이 겹쳐 찍힌 좌표(마네킹 패턴)는 세그멘테이션 없이도
    # 걸러져야 한다.
    mannequin = make_landmarks(
        left_shoulder=(0.495, 0.20, 0.0, 1.0),
        right_shoulder=(0.49, 0.202, 0.0, 1.0),
        left_hip=(0.5, 0.45, 0.0, 1.0),
        right_hip=(0.502, 0.451, 0.0, 1.0),
    )
    body = post("/posture-api/analyze/front", mannequin).json()

    assert body["reliability"]["is_reliable"] is False
    assert body["comment"]["source"] == "skipped"


def test_front_photo_sent_to_side_endpoint_is_flagged():
    # 정면 사진을 측면으로 보내면 측면 전용 검증이 잡아야 한다.
    body = post("/posture-api/analyze/side", FRONT_LANDMARKS).json()
    assert body["reliability"]["is_reliable"] is False


def test_unreliable_result_has_no_keypoint_confidence():
    # 믿을 수 없는 결과에는 관절별 신뢰도를 내지 않는다.
    mannequin = make_landmarks(
        left_shoulder=(0.495, 0.20, 0.0, 1.0),
        right_shoulder=(0.49, 0.202, 0.0, 1.0),
        left_hip=(0.5, 0.45, 0.0, 1.0),
        right_hip=(0.502, 0.451, 0.0, 1.0),
    )
    body = post("/posture-api/analyze/front", mannequin).json()
    assert body["keypoint_confidence"] == []


# --- health ----------------------------------------------------------------


def test_health():
    with TestClient(app) as client:
        body = client.get("/health").json()
    assert body["status"] == "ok"
    assert "max_turns" in body
