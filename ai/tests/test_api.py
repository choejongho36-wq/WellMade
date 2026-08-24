"""
빠른 수동 검증용 스크립트 (정식 테스트 스위트 아님, 임시 확인용).
- 실시간 코칭 판정(/ai/coaching/frame) 등 AI 엔드포인트가 기대한 방향으로 동작하는지
  TestClient로 확인한다.

(2026-08-24) 원래는 정지 자세 판정(/ai/pose/analyze, AI-03)도 함께 검증했다. 사용자가
업로드한 서비스 흐름도를 기준으로 "정지자세 촬영 관련 부분은 다른 팀원이 맡기로 했다"며
AI-03 삭제를 요청해(동년배 비교 인사이트 AI-15는 예외로 유지), 그 엔드포인트와 전용 각도
계산 함수들(app/pose/angles.py)이 제거되며 관련 테스트도 함께 삭제했다 — 원래 테스트는
git 히스토리 참고. 삭제된 판정 로직 중 실시간 코칭(AI-06)이 여전히 쓰는 부분(어깨 말림/
발뒤꿈치 뜸/무릎 모임/좌우 비대칭/무릎-발끝/등 굽음 임계값 비교)은 test_coaching_frame_*
테스트들이 계속 검증한다.
"""

import os

from fastapi.testclient import TestClient

from app.main import app
from app.pose.rules import personalized_hip_range, HEEL_LIFT_RATIO_THRESHOLD
from app.schemas import HipFlexibilityCalibration
from app.orchestration.harness import decide_next_action, API_KEY_ENV_VAR, DEFAULT_MODEL_ENV_VAR
from app.rag.retrieval import search as rag_search
from app.rag.generation import generate_guide, generate_qna
from app.session.report import generate_session_report, aggregate_session_stats

client = TestClient(app)


def landmark(x=0.5, y=0.5, z=0.0, visibility=0.9):
    return {"x": x, "y": y, "z": z, "visibility": visibility}


# (2026-08-24) make_landmarks()(측면 촬영 33개 landmark를 스쿼트 정지 자세로 채우는 헬퍼)가
# 이 자리에 있었다 — /ai/pose/analyze(AI-03) 테스트 전용이었는데, 그 엔드포인트 자체가
# 삭제되며(위 주석 참고) 더 이상 쓰는 곳이 없어져 함께 삭제했다. 아래 posture-insight(AI-15)
# 테스트가 쓰는 landmark()/make_front_view_landmarks()는 이것과 무관하게 그대로 남아있다.


def test_health():
    res = client.get("/health")
    assert res.status_code == 200
    print("health:", res.json())


# (2026-08-24) 정지 자세 판정(/ai/pose/analyze, AI-03) 관련 테스트들이 이 자리에 있었다.
# 사용자가 업로드한 서비스 흐름도를 기준으로 "정지자세 촬영 관련 부분은 다른 팀원이
# 맡기로 했다"며 AI-03 삭제를 요청해(동년배 비교 인사이트 AI-15는 예외로 유지), 그
# 엔드포인트를 검증하던 테스트도 함께 제거했다 — 어깨 말림 판정(shoulder_forward_lean_deg)
# 등 판정 로직 자체는 실시간 코칭(AI-06)에 그대로 남아있고, 아래 test_coaching_frame_*
# 테스트들이 이어서 검증한다. 원래 테스트는 git 히스토리 참고.


def test_coaching_frame_descending():
    # 무릎 각도가 175 -> 95로 꾸준히 줄어드는(굽혀지는) 시계열 -> "descending" 기대
    angle_history = [
        {"timestamp": i * 0.1, "knee_angle": 175 - i * 8, "hip_angle": 170 - i * 7}
        for i in range(10)
    ]
    body = {"angle_history": angle_history}
    res = client.post("/ai/coaching/frame", json=body)
    print("coaching_frame(descending):", res.status_code, res.json())
    assert res.status_code == 200
    data = res.json()
    assert data["phase"] == "descending", data


def test_coaching_frame_holding_at_bottom_normal():
    # 하단(약 85도)에서 거의 변화 없이 멈춰 있는 시계열 -> "holding" + is_normal True 기대
    angle_history = [
        {"timestamp": i * 0.1, "knee_angle": 85 + (i % 2), "hip_angle": 80 + (i % 2)}
        for i in range(10)
    ]
    body = {"angle_history": angle_history}
    res = client.post("/ai/coaching/frame", json=body)
    print("coaching_frame(holding@bottom):", res.status_code, res.json())
    assert res.status_code == 200
    data = res.json()
    assert data["phase"] == "holding", data
    assert data["is_normal"] is True, data
    assert data["confidence"] > 0.7, data  # 떨림이 적은 안정적인 holding이므로 신뢰도가 높아야 함


def test_coaching_frame_holding_shoulder_rounded_flagged():
    # 무릎/엉덩이는 정상 범위인데 shoulder_forward_lean_deg만 임계값(20.0)을 넘게(어깨
    # 말림) 들어온 경우 -> 이상 감지돼야 함. (2026-08-24: shoulder_angle 절대각도 대신
    # shoulder_forward_lean_deg로 판정 방식이 바뀜 — rules.py 주석 참고.)
    angle_history = [
        {
            "timestamp": i * 0.1,
            "knee_angle": 85 + (i % 2),
            "hip_angle": 80 + (i % 2),
            "shoulder_forward_lean_deg": 30,
        }
        for i in range(10)
    ]
    body = {"angle_history": angle_history}
    res = client.post("/ai/coaching/frame", json=body)
    print("coaching_frame(holding, rounded shoulder):", res.status_code, res.json())
    assert res.status_code == 200
    data = res.json()
    assert data["is_normal"] is False, data
    assert any(issue["part"] == "shoulder" for issue in data["issues"]), data


def test_coaching_frame_negative_shoulder_lean_not_flagged():
    # shoulder_forward_lean_deg가 0 이하(목이 상체보다 세워진, 좋은 자세)면 절대 플래그되면
    # 안 된다 — 2026-08-24에 고친 실제 오탐 사례의 회귀 테스트.
    angle_history = [
        {
            "timestamp": i * 0.1,
            "knee_angle": 85 + (i % 2),
            "hip_angle": 80 + (i % 2),
            "shoulder_forward_lean_deg": -29.6,
        }
        for i in range(10)
    ]
    body = {"angle_history": angle_history}
    res = client.post("/ai/coaching/frame", json=body)
    print("coaching_frame(negative shoulder lean):", res.status_code, res.json())
    assert res.status_code == 200
    data = res.json()
    assert not any(issue["part"] == "shoulder" for issue in data["issues"]), data


def test_coaching_frame_without_shoulder_fields_still_works():
    # shoulder_angle/shoulder_forward_lean_deg 필드를 아예 안 보내는 기존 프론트 호출도
    # 에러 없이 동작해야 한다(하위 호환).
    angle_history = [
        {"timestamp": i * 0.1, "knee_angle": 85 + (i % 2), "hip_angle": 80 + (i % 2)} for i in range(10)
    ]
    body = {"angle_history": angle_history}
    res = client.post("/ai/coaching/frame", json=body)
    print("coaching_frame(no shoulder fields):", res.status_code, res.json())
    assert res.status_code == 200
    data = res.json()
    assert not any(issue["part"] == "shoulder" for issue in data["issues"]), data


def test_coaching_frame_holding_halfway_abnormal():
    # 하단까지 못 내려가고 중간(약 130도)에서 멈춘 시계열 -> "holding" + is_normal False 기대
    angle_history = [
        {"timestamp": i * 0.1, "knee_angle": 130 + (i % 2), "hip_angle": 150}
        for i in range(10)
    ]
    body = {"angle_history": angle_history}
    res = client.post("/ai/coaching/frame", json=body)
    print("coaching_frame(holding halfway):", res.status_code, res.json())
    assert res.status_code == 200
    data = res.json()
    assert data["phase"] == "holding", data
    assert data["is_normal"] is False, data


def test_coaching_frame_jittery_movement_flagged():
    # 값이 크게 요동치는(떨리는) 시계열 -> is_normal False (movement 이슈) 기대
    values = [170, 90, 165, 95, 172, 88, 168, 92, 171, 89]
    angle_history = [
        {"timestamp": i * 0.1, "knee_angle": v, "hip_angle": 150} for i, v in enumerate(values)
    ]
    body = {"angle_history": angle_history}
    res = client.post("/ai/coaching/frame", json=body)
    print("coaching_frame(jittery):", res.status_code, res.json())
    assert res.status_code == 200
    data = res.json()
    assert any(issue["part"] == "movement" for issue in data["issues"]), data


def test_coaching_frame_insufficient_frames():
    angle_history = [{"timestamp": 0.0, "knee_angle": 170, "hip_angle": 160}]
    body = {"angle_history": angle_history}
    res = client.post("/ai/coaching/frame", json=body)
    print("coaching_frame(insufficient):", res.status_code, res.json())
    assert res.status_code == 200
    data = res.json()
    assert data["confidence"] < 0.5, data


def test_session_end_user_requested():
    # 데이터가 어떻든 사용자가 직접 종료를 요청하면 즉시 종료돼야 함
    body = {
        "judgment_history": [{"timestamp": 0.0, "is_normal": False}],
        "user_requested_end": True,
    }
    res = client.post("/ai/session/end-check", json=body)
    print("session_end(user_requested):", res.status_code, res.json())
    assert res.status_code == 200
    data = res.json()
    assert data["should_end"] is True
    assert data["reason"] == "user_requested"


def test_session_end_not_enough_duration_yet():
    # 목표 시간(180초)만큼 데이터가 안 쌓였으면 정상 비율이 100%여도 아직 종료 안 됨
    judgment_history = [{"timestamp": float(i), "is_normal": True} for i in range(30)]
    body = {"judgment_history": judgment_history, "user_requested_end": False}
    res = client.post("/ai/session/end-check", json=body)
    print("session_end(not enough duration):", res.status_code, res.json())
    assert res.status_code == 200
    data = res.json()
    assert data["should_end"] is False
    assert data["reason"] == "in_progress"


def test_session_end_sustained_good_form():
    # 최근 180초 동안 정상 비율이 70% 이상 유지되면 종료돼야 함
    judgment_history = [
        {"timestamp": float(i), "is_normal": (i % 10 != 0)}  # 10프레임마다 1번만 이상 -> 90% 정상
        for i in range(200)
    ]
    body = {"judgment_history": judgment_history, "user_requested_end": False}
    res = client.post("/ai/session/end-check", json=body)
    print("session_end(sustained good form):", res.status_code, res.json())
    assert res.status_code == 200
    data = res.json()
    assert data["should_end"] is True
    assert data["reason"] == "target_sustained"
    assert data["normal_ratio"] >= 0.7


def test_session_end_sustained_poor_form():
    # 시간은 충분히 지났지만 최근 정상 비율이 낮으면 아직 종료되면 안 됨
    judgment_history = [
        {"timestamp": float(i), "is_normal": (i % 2 == 0)}  # 50%만 정상
        for i in range(200)
    ]
    body = {"judgment_history": judgment_history, "user_requested_end": False}
    res = client.post("/ai/session/end-check", json=body)
    print("session_end(sustained poor form):", res.status_code, res.json())
    assert res.status_code == 200
    data = res.json()
    assert data["should_end"] is False
    assert data["reason"] == "in_progress"
    assert data["normal_ratio"] < 0.7


def test_personalized_hip_range_formula():
    # 서 있을 때 160도, 무리 없이 최대한 숙였을 때 100도 -> 가동범위 60도
    # low = 160 - 0.9*60 = 106, high = 160 - 0.7*60 = 118
    calibration = HipFlexibilityCalibration(standing_hip_angle=160, max_flex_hip_angle=100)
    low, high = personalized_hip_range(calibration)
    print("personalized_hip_range:", low, high)
    assert round(low, 1) == 106.0
    assert round(high, 1) == 118.0


def test_personalized_hip_range_invalid_calibration_is_safe():
    # 최대 숙임 각도가 서 있는 각도보다 크거나 같은(측정이 잘못된) 경우 -> 가동범위 <= 0
    # "항상 범위 밖"으로 처리되는 안전한 값(standing, standing)을 반환해야 함
    calibration = HipFlexibilityCalibration(standing_hip_angle=160, max_flex_hip_angle=170)
    low, high = personalized_hip_range(calibration)
    print("personalized_hip_range(invalid):", low, high)
    assert low == high == 160


def test_coaching_frame_hip_calibration_changes_normal_judgement():
    # 무릎은 정상범위(30~120) 안에서 정지, 엉덩이는 130도로 정지한 상황(2026-08-21 상하한
    # 확대 이후 고정 범위는 25~120이라 130은 여전히 범위 밖 — 아래 수치도 그에 맞게 갱신).
    # 고정 NORMAL_RANGES(25~120)로는 130이 범위 밖이라 이상으로 판정되지만,
    # 유연성이 낮은 사용자의 캘리브레이션(standing 178, max_flex 118 -> 개인 범위 124~136)을
    # 적용하면 130은 그 사람 기준으로는 정상 범위 안이라 정상으로 바뀌어야 한다.
    angle_history = [
        {"timestamp": i * 0.1, "knee_angle": 85 + (i % 2), "hip_angle": 130} for i in range(10)
    ]

    body_without_calibration = {"angle_history": angle_history}
    res_without = client.post("/ai/coaching/frame", json=body_without_calibration)
    print("coaching_frame(no calibration, hip=130):", res_without.status_code, res_without.json())
    assert res_without.status_code == 200
    assert res_without.json()["is_normal"] is False

    body_with_calibration = {
        "angle_history": angle_history,
        "hip_calibration": {"standing_hip_angle": 178, "max_flex_hip_angle": 118},
    }
    res_with = client.post("/ai/coaching/frame", json=body_with_calibration)
    print("coaching_frame(with calibration, hip=130):", res_with.status_code, res_with.json())
    assert res_with.status_code == 200
    assert res_with.json()["is_normal"] is True


def make_front_view_landmarks(shoulder_tilt="level", pelvis_tilt="level"):
    """자세 비교 인사이트(/ai/onboarding/posture-insight) 테스트용 정면 촬영 랜드마크.
    좌우 어깨(11/12)와 좌우 골반(23/24)의 y좌표 차이로 기울기를 만든다
    (y가 작을수록 위 -> 더 "올라간" 쪽)."""
    lms = [landmark() for _ in range(33)]
    if shoulder_tilt == "left_up":
        lms[11] = landmark(0.3, 0.20)  # LEFT_SHOULDER (더 위로 -> 왼쪽이 올라감)
        lms[12] = landmark(0.7, 0.23)  # RIGHT_SHOULDER
    else:  # "level"
        lms[11] = landmark(0.3, 0.20)
        lms[12] = landmark(0.7, 0.20)

    if pelvis_tilt == "right_up":
        lms[23] = landmark(0.35, 0.53)  # LEFT_HIP
        lms[24] = landmark(0.65, 0.49)  # RIGHT_HIP (더 위로 -> 오른쪽이 올라감)
    else:  # "level"
        lms[23] = landmark(0.35, 0.50)
        lms[24] = landmark(0.65, 0.50)
    return lms


def test_posture_insight_level_posture_returns_no_tilt_message():
    body = {
        "front_landmarks": make_front_view_landmarks("level", "level"),
        "gender": "F",
        "birth_year": 1990,
    }
    res = client.post("/ai/onboarding/posture-insight", json=body)
    print("posture_insight(level):", res.status_code, res.json())
    assert res.status_code == 200
    data = res.json()
    assert data["shoulder_side"] == "level"
    assert data["pelvis_side"] == "level"
    assert data["age_bracket"] == 30  # 2026 - 1990 = 36세 -> 30대


def test_posture_insight_tilted_posture_returns_percentile():
    body = {
        "front_landmarks": make_front_view_landmarks("left_up", "right_up"),
        "gender": "M",
        "birth_year": 1990,
    }
    res = client.post("/ai/onboarding/posture-insight", json=body)
    print("posture_insight(tilted):", res.status_code, res.json())
    assert res.status_code == 200
    data = res.json()
    assert data["shoulder_side"] == "left"
    assert data["pelvis_side"] == "right"
    assert data["shoulder_percentile"] is not None
    assert 0.0 <= data["shoulder_percentile"] <= 100.0
    assert data["pelvis_percentile"] is not None
    assert 0.0 <= data["pelvis_percentile"] <= 100.0
    assert "왼쪽" in data["shoulder_message"]
    assert "오른쪽" in data["pelvis_message"]
    assert data["sample_size"] > 0


def test_posture_insight_old_age_maps_to_60_plus_bracket():
    # 1950년생 -> 76세, 참조 데이터가 60대 이상을 하나로 묶어뒀으므로 age_bracket=60이어야 함
    body = {
        "front_landmarks": make_front_view_landmarks("level", "level"),
        "gender": "F",
        "birth_year": 1950,
    }
    res = client.post("/ai/onboarding/posture-insight", json=body)
    print("posture_insight(old age):", res.status_code, res.json())
    assert res.status_code == 200
    data = res.json()
    assert data["age_bracket"] == 60


def _without_llm_env(fn):
    """테스트 중 ANTHROPIC_API_KEY/HARNESS_LLM_MODEL이 우연히 설정돼있어도(로컬 .env 등)
    fallback 경로 테스트가 실제 LLM을 호출하지 않도록, 두 환경변수를 잠시 지웠다가
    복원한다."""
    saved = {}
    for key in (API_KEY_ENV_VAR, DEFAULT_MODEL_ENV_VAR):
        saved[key] = os.environ.pop(key, None)
    try:
        return fn()
    finally:
        for key, value in saved.items():
            if value is not None:
                os.environ[key] = value


def test_orchestrate_fallback_no_signals_proceeds():
    def run():
        body = {"session_id": "s1", "context": {}}
        res = client.post("/ai/orchestrate", json=body)
        print("orchestrate(no signals):", res.status_code, res.json())
        assert res.status_code == 200
        data = res.json()
        assert data["source"] == "fallback"
        assert data["next_action"] == "proceed"
        assert data["fallback_reason"] is not None

    _without_llm_env(run)


def test_orchestrate_fallback_low_visibility_requests_retake():
    def run():
        body = {"session_id": "s1", "context": {"landmark_visibility": 0.3}}
        res = client.post("/ai/orchestrate", json=body)
        print("orchestrate(low visibility):", res.status_code, res.json())
        assert res.status_code == 200
        assert res.json()["next_action"] == "request_retake"

    _without_llm_env(run)


def test_orchestrate_fallback_user_requested_end_wins_over_low_confidence():
    # 사용자 직접 종료 요청(H-06)이 낮은 신뢰도(H-01)보다 우선순위가 높아야 한다.
    def run():
        body = {
            "session_id": "s1",
            "context": {"user_requested_end": True, "confidence": 0.2},
        }
        res = client.post("/ai/orchestrate", json=body)
        print("orchestrate(user requested end + low confidence):", res.status_code, res.json())
        assert res.status_code == 200
        data = res.json()
        assert data["next_action"] == "end_session"
        assert data["action_args"]["end_reason"] == "user_requested"

    _without_llm_env(run)


def test_orchestrate_fallback_repeated_issue_triggers_rag():
    def run():
        body = {
            "session_id": "s1",
            "context": {"issue_type": "knee_valgus", "issue_repeat_count": 3},
        }
        res = client.post("/ai/orchestrate", json=body)
        print("orchestrate(repeated issue):", res.status_code, res.json())
        assert res.status_code == 200
        data = res.json()
        assert data["next_action"] == "trigger_rag_search"
        assert data["action_args"]["search_query"] == "knee_valgus"

    _without_llm_env(run)


class _FakeToolUseBlock:
    def __init__(self, name, input_):
        self.type = "tool_use"
        self.name = name
        self.input = input_


class _FakeMessage:
    def __init__(self, content):
        self.content = content


class _FakeMessagesAPI:
    def __init__(self, block=None, exc=None):
        self._block = block
        self._exc = exc

    def create(self, **kwargs):
        if self._exc is not None:
            raise self._exc
        return _FakeMessage([self._block])


class _FakeAnthropicClient:
    """실제 anthropic.Anthropic() 대신 주입하는 가짜 클라이언트 — 네트워크 호출 없이
    harness.decide_next_action()의 파싱/폴백 로직만 검증한다."""

    def __init__(self, block=None, exc=None):
        self.messages = _FakeMessagesAPI(block=block, exc=exc)


def test_harness_llm_path_parses_tool_use_response():
    os.environ[DEFAULT_MODEL_ENV_VAR] = "fake-model-for-test"
    try:
        block = _FakeToolUseBlock(
            "recommend_expert_consultation", {"reasoning": "골반 비대칭이 반복됐습니다."}
        )
        fake_client = _FakeAnthropicClient(block=block)
        result = decide_next_action("s1", {"issue_type": "pelvis_asymmetry"}, client=fake_client)
        print("harness(llm path):", result)
        assert result["source"] == "llm"
        assert result["next_action"] == "recommend_expert_consultation"
        assert result["reasoning"] == "골반 비대칭이 반복됐습니다."
        assert result["action_args"] == {}  # reasoning은 action_args에서 빠져야 함
    finally:
        os.environ.pop(DEFAULT_MODEL_ENV_VAR, None)


def test_harness_llm_failure_falls_back():
    os.environ[DEFAULT_MODEL_ENV_VAR] = "fake-model-for-test"
    try:
        fake_client = _FakeAnthropicClient(exc=RuntimeError("network down"))
        result = decide_next_action("s1", {}, client=fake_client)
        print("harness(llm failure -> fallback):", result)
        assert result["source"] == "fallback"
        assert "network down" in result["fallback_reason"]
        assert result["next_action"] == "proceed"  # 상황 정보가 없으니 안전한 기본값
    finally:
        os.environ.pop(DEFAULT_MODEL_ENV_VAR, None)


def test_rag_search_finds_relevant_document():
    # "무릎 모임"으로 검색하면 knee_valgus 문서가 최상위로 나와야 한다.
    results = rag_search("무릎 모임", top_k=3)
    print("rag_search(무릎 모임):", [(r["doc_id"], round(r["score"], 3)) for r in results])
    assert results
    assert results[0]["doc_id"] == "knee_valgus"


def test_rag_search_unrelated_query_returns_empty():
    # 전혀 무관한 문장은 검색 결과가 없어야 한다(MIN_SIMILARITY_SCORE 미만).
    results = rag_search("오늘 저녁 뭐 먹지", top_k=3)
    print("rag_search(무관한 문장):", results)
    assert results == []


def test_rag_guide_fallback_matched():
    def run():
        result = generate_guide("무릎 모임")
        print("generate_guide(무릎 모임, fallback):", result)
        assert result["matched"] is True
        assert result["generation_source"] == "fallback"
        assert result["guidance_message"] == SQUAT_COACHING_MESSAGES_KNEE_VALGUS
        assert result["sources"][0]["source"] == "NASM (National Academy of Sports Medicine)"

    _without_llm_env(run)


def test_rag_guide_fallback_no_match_uses_generic_message():
    def run():
        result = generate_guide("완전히 무관한 검색어 아무말")
        print("generate_guide(무관, fallback):", result)
        assert result["matched"] is False
        assert result["sources"] == []

    _without_llm_env(run)


def test_rag_qna_fallback_matched():
    def run():
        result = generate_qna("스쿼트 할 때 무릎이 안쪽으로 모여요 어떻게 하죠")
        print("generate_qna(fallback):", result)
        assert result["matched"] is True
        assert result["generation_source"] == "fallback"
        assert len(result["sources"]) > 0

    _without_llm_env(run)


def test_rag_qna_fallback_no_match():
    def run():
        result = generate_qna("오늘 저녁 뭐 먹지")
        print("generate_qna(무관, fallback):", result)
        assert result["matched"] is False
        assert result["answer"] == NO_MATCH_QNA_MESSAGE

    _without_llm_env(run)


def test_rag_guide_llm_path_uses_generated_text():
    os.environ[DEFAULT_MODEL_ENV_VAR] = "fake-model-for-test"
    try:
        block = _FakeTextBlock("무릎이 안쪽으로 모이지 않도록 밀어내며 앉아주세요.")
        fake_client = _FakeAnthropicClient(block=block)
        result = generate_guide("무릎 모임", client=fake_client)
        print("generate_guide(llm path):", result)
        assert result["generation_source"] == "llm"
        assert result["guidance_message"] == "무릎이 안쪽으로 모이지 않도록 밀어내며 앉아주세요."
        assert result["matched"] is True
    finally:
        os.environ.pop(DEFAULT_MODEL_ENV_VAR, None)


def test_rag_guide_llm_failure_falls_back_to_short_message():
    os.environ[DEFAULT_MODEL_ENV_VAR] = "fake-model-for-test"
    try:
        fake_client = _FakeAnthropicClient(exc=RuntimeError("network down"))
        result = generate_guide("무릎 모임", client=fake_client)
        print("generate_guide(llm failure -> fallback):", result)
        assert result["generation_source"] == "fallback"
        assert result["matched"] is True
    finally:
        os.environ.pop(DEFAULT_MODEL_ENV_VAR, None)


def test_rag_guide_endpoint_returns_valid_response():
    def run():
        res = client.post("/ai/rag/guide", json={"query": "무릎 모임"})
        print("POST /ai/rag/guide:", res.status_code, res.json())
        assert res.status_code == 200
        data = res.json()
        assert data["matched"] is True
        assert data["generation_source"] == "fallback"
        assert len(data["sources"]) > 0

    _without_llm_env(run)


def make_frame_history(normal_count, abnormal_count, part="knee", deviation_deg=15.0):
    """정상 프레임과 이상 프레임(지정한 부위/편차로)을 섞은 세션 리포트용 프레임 이력."""
    history = [{"timestamp": float(i), "is_normal": True, "issues": []} for i in range(normal_count)]
    history += [
        {
            "timestamp": float(normal_count + i),
            "is_normal": False,
            "issues": [{"part": part, "deviation_deg": deviation_deg}],
        }
        for i in range(abnormal_count)
    ]
    return history


def test_aggregate_session_stats_basic():
    history = make_frame_history(normal_count=7, abnormal_count=3, part="knee", deviation_deg=10.0)
    stats = aggregate_session_stats(history, previous_sessions=[])
    print("aggregate_session_stats(7 normal, 3 abnormal knee):", stats)
    assert stats["normal_ratio"] == 0.7
    assert stats["avg_deviation_deg"] == 10.0
    assert stats["most_frequent_issue_part"] == "knee"
    assert stats["improvement_vs_previous_pct"] is None


def test_aggregate_session_stats_improvement_vs_previous():
    history = make_frame_history(normal_count=9, abnormal_count=1)
    stats = aggregate_session_stats(history, previous_sessions=[{"session_date": "2026-08-01", "normal_ratio": 0.6}])
    print("aggregate_session_stats(improvement):", stats)
    # 이번 세션 정상비율 0.9 - 직전 0.6 = +30.0%p
    assert stats["improvement_vs_previous_pct"] == 30.0


def test_generate_session_report_fallback():
    def run():
        history = make_frame_history(normal_count=6, abnormal_count=4, part="shoulder", deviation_deg=20.0)
        result = generate_session_report(history, session_duration_sec=300.0, previous_sessions=[])
        print("generate_session_report(fallback):", result)
        assert result["generation_source"] == "fallback"
        assert result["normal_ratio"] == 0.6
        assert result["most_frequent_issue_part"] == "shoulder"
        assert "어깨" in result["summary_message"]  # PART_LABELS 매핑이 폴백 문구에 반영됐는지
        assert isinstance(result["summary_message"], str) and len(result["summary_message"]) > 0

    _without_llm_env(run)


def test_generate_session_report_llm_path():
    os.environ[DEFAULT_MODEL_ENV_VAR] = "fake-model-for-test"
    try:
        block = _FakeTextBlock("오늘도 수고하셨어요! 무릎 자세에 조금 더 신경 써보면 좋을 것 같아요.")
        fake_client = _FakeAnthropicClient(block=block)
        history = make_frame_history(normal_count=8, abnormal_count=2, part="knee", deviation_deg=8.0)
        result = generate_session_report(history, session_duration_sec=180.0, client=fake_client)
        print("generate_session_report(llm path):", result)
        assert result["generation_source"] == "llm"
        assert result["summary_message"] == "오늘도 수고하셨어요! 무릎 자세에 조금 더 신경 써보면 좋을 것 같아요."
    finally:
        os.environ.pop(DEFAULT_MODEL_ENV_VAR, None)


def test_session_report_endpoint_returns_valid_response():
    def run():
        body = {
            "session_id": "s1",
            "frame_history": make_frame_history(normal_count=7, abnormal_count=3, part="knee", deviation_deg=12.0),
            "session_duration_sec": 240.0,
            "previous_sessions": [{"session_date": "2026-08-10", "normal_ratio": 0.5}],
        }
        res = client.post("/ai/session/report", json=body)
        print("POST /ai/session/report:", res.status_code, res.json())
        assert res.status_code == 200
        data = res.json()
        assert data["normal_ratio"] == 0.7
        assert data["improvement_vs_previous_pct"] == 20.0
        assert data["generation_source"] == "fallback"

    _without_llm_env(run)


def test_rag_qna_endpoint_returns_valid_response():
    def run():
        res = client.post("/ai/rag/qna", json={"question": "스쿼트할 때 무릎이 발끝을 넘어가요"})
        print("POST /ai/rag/qna:", res.status_code, res.json())
        assert res.status_code == 200
        data = res.json()
        assert data["matched"] is True
        assert isinstance(data["answer"], str) and len(data["answer"]) > 0

    _without_llm_env(run)


class _FakeTextBlock:
    """generation.py가 파싱하는 텍스트 응답 블록(anthropic SDK의 TextBlock 흉내)."""

    def __init__(self, text):
        self.type = "text"
        self.text = text


# knowledge_base.py가 coaching_messages.py의 문구를 그대로 재사용하므로, 테스트에서도 같은
# 상수를 참조해 "문구가 우연히 같다"가 아니라 "의도적으로 같은 출처를 쓴다"를 검증한다.
from app.pose.coaching_messages import KNEE_VALGUS_MESSAGE
from app.rag.generation import NO_MATCH_QNA_MESSAGE

SQUAT_COACHING_MESSAGES_KNEE_VALGUS = KNEE_VALGUS_MESSAGE


# (2026-08-24) 발뒤꿈치 뜸 규칙기반 검사의 단위 테스트(get_heel_lift_ratio 직접 호출)와
# 그 /ai/pose/analyze 통합 테스트가 이 자리에 있었다 — AI-03 삭제(위 주석 참고)와 함께
# get_heel_lift_ratio() 자체가 angles.py에서 제거되며 같이 삭제했다. 아래
# test_coaching_frame_heel_lift_* 테스트들이 실시간 코칭(AI-06) 경로로 같은 임계값
# (HEEL_LIFT_RATIO_THRESHOLD) 판정을 계속 검증한다.


def test_coaching_frame_heel_lift_flagged_when_deep_hold():
    # 무릎/엉덩이는 정상 범위(holding, deep)인데 heel_lift_ratio만 임계값을 넘는 경우.
    angle_history = [
        {
            "timestamp": i * 0.1,
            "knee_angle": 85 + (i % 2),
            "hip_angle": 80 + (i % 2),
            "heel_lift_ratio": HEEL_LIFT_RATIO_THRESHOLD + 0.3,
        }
        for i in range(10)
    ]
    body = {"angle_history": angle_history}
    res = client.post("/ai/coaching/frame", json=body)
    print("coaching_frame(heel lift, deep hold):", res.status_code, res.json())
    assert res.status_code == 200
    data = res.json()
    assert data["is_normal"] is False, data
    assert any(issue["part"] == "heel" for issue in data["issues"]), data


def test_coaching_frame_without_heel_lift_field_still_works():
    # heel_lift_ratio 필드를 아예 안 보내는 기존 프론트 호출도 에러 없이 동작해야 한다(하위 호환).
    angle_history = [
        {"timestamp": i * 0.1, "knee_angle": 85 + (i % 2), "hip_angle": 80 + (i % 2)} for i in range(10)
    ]
    body = {"angle_history": angle_history}
    res = client.post("/ai/coaching/frame", json=body)
    print("coaching_frame(no heel_lift_ratio field):", res.status_code, res.json())
    assert res.status_code == 200
    data = res.json()
    assert not any(issue["part"] == "heel" for issue in data["issues"]), data


def test_coaching_frame_heel_lift_ignored_while_standing():
    # 서 있는 상태(is_deep_hold=False)에서는 heel_lift_ratio가 커도 검사 대상이 아니다
    # (realtime.py 주석 참고 — 서 있을 땐 애초에 발뒤꿈치가 뜰 이유가 없는 상황을 가정).
    angle_history = [
        {
            "timestamp": i * 0.1,
            "knee_angle": 175 + (i % 2),
            "hip_angle": 170 + (i % 2),
            "heel_lift_ratio": HEEL_LIFT_RATIO_THRESHOLD + 0.3,
        }
        for i in range(10)
    ]
    body = {"angle_history": angle_history}
    res = client.post("/ai/coaching/frame", json=body)
    print("coaching_frame(heel lift while standing):", res.status_code, res.json())
    assert res.status_code == 200
    data = res.json()
    assert not any(issue["part"] == "heel" for issue in data["issues"]), data


# (2026-08-24) 무릎 모임/좌우 비대칭 규칙기반 검사의 단위 테스트(get_knee_valgus_ratio/
# get_knee_lr_asymmetry_deg 직접 호출)와 그 /ai/pose/analyze 통합 테스트가 이 자리에
# 있었다 — AI-03 삭제(위 주석 참고)와 함께 이 두 함수 자체가 angles.py에서 제거되며 같이
# 삭제했다. 아래 test_coaching_frame_knee_valgus_*/knee_asymmetry_* 테스트들이 실시간
# 코칭(AI-06) 경로로 같은 임계값(KNEE_VALGUS_RATIO_THRESHOLD/KNEE_ASYMMETRY_THRESHOLD_DEG)
# 판정을 계속 검증한다.
from app.pose.rules import KNEE_ASYMMETRY_THRESHOLD_DEG, KNEE_VALGUS_RATIO_THRESHOLD  # noqa: E402


def test_coaching_frame_knee_valgus_flagged_when_deep_hold():
    angle_history = [
        {
            "timestamp": i * 0.1,
            "knee_angle": 85 + (i % 2),
            "hip_angle": 80 + (i % 2),
            "knee_valgus_ratio": KNEE_VALGUS_RATIO_THRESHOLD - 0.3,
        }
        for i in range(10)
    ]
    body = {"angle_history": angle_history}
    res = client.post("/ai/coaching/frame", json=body)
    print("coaching_frame(knee valgus, deep hold):", res.status_code, res.json())
    assert res.status_code == 200
    data = res.json()
    assert data["is_normal"] is False, data
    assert any(issue["part"] == "knee_valgus" for issue in data["issues"]), data


def test_coaching_frame_knee_asymmetry_flagged_when_deep_hold():
    angle_history = [
        {
            "timestamp": i * 0.1,
            "knee_angle": 85 + (i % 2),
            "hip_angle": 80 + (i % 2),
            "knee_asymmetry_deg": KNEE_ASYMMETRY_THRESHOLD_DEG + 10.0,
        }
        for i in range(10)
    ]
    body = {"angle_history": angle_history}
    res = client.post("/ai/coaching/frame", json=body)
    print("coaching_frame(knee asymmetry, deep hold):", res.status_code, res.json())
    assert res.status_code == 200
    data = res.json()
    assert data["is_normal"] is False, data
    assert any(issue["part"] == "asymmetry" for issue in data["issues"]), data


def test_coaching_frame_without_frontal_fields_still_works():
    # knee_valgus_ratio/knee_asymmetry_deg 필드를 아예 안 보내도 에러 없이 동작해야 한다(하위 호환).
    angle_history = [
        {"timestamp": i * 0.1, "knee_angle": 85 + (i % 2), "hip_angle": 80 + (i % 2)} for i in range(10)
    ]
    body = {"angle_history": angle_history}
    res = client.post("/ai/coaching/frame", json=body)
    print("coaching_frame(no frontal fields):", res.status_code, res.json())
    assert res.status_code == 200
    data = res.json()
    assert not any(issue["part"] in ("knee_valgus", "asymmetry") for issue in data["issues"]), data


# (2026-08-24) 무릎-발끝 규칙기반 검사의 단위 테스트(get_knee_over_toe_ratio 직접 호출),
# 그 /ai/pose/analyze 통합 테스트, 그리고 그 자리에 있던 레거시 exercise_type 필드 무시
# 회귀 테스트가 이 자리에 있었다 — AI-03 삭제(위 주석 참고)와 함께 get_knee_over_toe_ratio()
# 자체가 angles.py에서 제거되고 /ai/pose/analyze 엔드포인트도 없어지며 같이 삭제했다.
# (exercise_type 필드 무시 동작은 그 자체가 AI-03 전용 검증이라 함께 제거 — 다른 엔드포인트는
# 애초에 그 필드를 받은 적이 없다.) 아래 test_coaching_frame_knee_over_toe_* 테스트들이
# 실시간 코칭(AI-06) 경로로 같은 임계값(KNEE_OVER_TOE_RATIO_THRESHOLD) 판정을 계속 검증한다.
from app.pose.rules import KNEE_OVER_TOE_RATIO_THRESHOLD  # noqa: E402


def test_coaching_frame_knee_over_toe_flagged_when_deep_hold():
    angle_history = [
        {
            "timestamp": i * 0.1,
            "knee_angle": 85 + (i % 2),
            "hip_angle": 80 + (i % 2),
            "knee_over_toe_ratio": KNEE_OVER_TOE_RATIO_THRESHOLD + 0.3,
        }
        for i in range(10)
    ]
    body = {"angle_history": angle_history}
    res = client.post("/ai/coaching/frame", json=body)
    print("coaching_frame(knee over toe, deep hold):", res.status_code, res.json())
    assert res.status_code == 200
    data = res.json()
    assert data["is_normal"] is False, data
    assert any(issue["part"] == "knee_over_toe" for issue in data["issues"]), data


def test_coaching_frame_without_knee_over_toe_field_still_works():
    # knee_over_toe_ratio 필드를 아예 안 보내는 기존 프론트 호출도 에러 없이 동작해야 한다(하위 호환).
    angle_history = [
        {"timestamp": i * 0.1, "knee_angle": 85 + (i % 2), "hip_angle": 80 + (i % 2)} for i in range(10)
    ]
    body = {"angle_history": angle_history}
    res = client.post("/ai/coaching/frame", json=body)
    print("coaching_frame(no knee_over_toe_ratio field):", res.status_code, res.json())
    assert res.status_code == 200
    data = res.json()
    assert not any(issue["part"] == "knee_over_toe" for issue in data["issues"]), data


# (2026-08-24) 등 굽음(척추 굴곡) 규칙기반 검사의 단위 테스트(get_torso_length_ratio
# 직접 호출)와 그 /ai/pose/analyze 통합 테스트가 이 자리에 있었다 — AI-03 삭제(위 주석
# 참고)와 함께 get_torso_length_ratio() 자체가 angles.py에서 제거되며 같이 삭제했다.
# 아래 test_coaching_frame_back_rounded_* 테스트들이 실시간 코칭(AI-06) 경로로 같은
# 판정(hip_calibration.standing_shoulder_hip_ratio 기준 비교)을 계속 검증한다.


def _calibration_with_baseline(standing_shoulder_hip_ratio=1.5):
    return {
        "standing_hip_angle": 178,
        "max_flex_hip_angle": 118,
        "standing_shoulder_hip_ratio": standing_shoulder_hip_ratio,
    }


def test_coaching_frame_back_rounded_flagged_when_deep_hold():
    angle_history = [
        {
            "timestamp": i * 0.1,
            "knee_angle": 85 + (i % 2),
            "hip_angle": 80 + (i % 2),
            "torso_length_ratio": 1.0,  # 1.5 * 0.85 = 1.275보다 작음 -> 등 굽음으로 판정돼야 함
        }
        for i in range(10)
    ]
    body = {
        "angle_history": angle_history,
        "hip_calibration": _calibration_with_baseline(),
    }
    res = client.post("/ai/coaching/frame", json=body)
    print("coaching_frame(back rounded, deep hold):", res.status_code, res.json())
    assert res.status_code == 200
    data = res.json()
    assert any(issue["part"] == "back_rounded" for issue in data["issues"]), data


def test_coaching_frame_back_rounded_ignored_while_standing():
    # 서 있는 상태(is_deep_hold=False)에서는 다른 깊게-앉은-상태 전용 검사들과 마찬가지로
    # torso_length_ratio가 낮아도 검사 대상이 아니다.
    angle_history = [
        {
            "timestamp": i * 0.1,
            "knee_angle": 175 + (i % 2),
            "hip_angle": 170 + (i % 2),
            "torso_length_ratio": 1.0,
        }
        for i in range(10)
    ]
    body = {
        "angle_history": angle_history,
        "hip_calibration": _calibration_with_baseline(),
    }
    res = client.post("/ai/coaching/frame", json=body)
    print("coaching_frame(back rounded while standing):", res.status_code, res.json())
    assert res.status_code == 200
    data = res.json()
    assert not any(issue["part"] == "back_rounded" for issue in data["issues"]), data


def test_coaching_frame_back_rounded_ignored_without_baseline():
    # torso_length_ratio 필드는 보내더라도, hip_calibration.standing_shoulder_hip_ratio가
    # 없으면(하위 호환) 기준값이 없어 판정 자체를 건너뛴다.
    angle_history = [
        {
            "timestamp": i * 0.1,
            "knee_angle": 85 + (i % 2),
            "hip_angle": 80 + (i % 2),
            "torso_length_ratio": 1.0,
        }
        for i in range(10)
    ]
    body = {"angle_history": angle_history}
    res = client.post("/ai/coaching/frame", json=body)
    print("coaching_frame(back rounded, no baseline):", res.status_code, res.json())
    assert res.status_code == 200
    data = res.json()
    assert not any(issue["part"] == "back_rounded" for issue in data["issues"]), data


def test_coaching_frame_without_torso_length_ratio_field_still_works():
    # torso_length_ratio 필드를 아예 안 보내는 기존 프론트 호출도 에러 없이 동작해야 한다(하위 호환).
    angle_history = [
        {"timestamp": i * 0.1, "knee_angle": 85 + (i % 2), "hip_angle": 80 + (i % 2)} for i in range(10)
    ]
    body = {
        "angle_history": angle_history,
        "hip_calibration": _calibration_with_baseline(),
    }
    res = client.post("/ai/coaching/frame", json=body)
    print("coaching_frame(no torso_length_ratio field):", res.status_code, res.json())
    assert res.status_code == 200
    data = res.json()
    assert not any(issue["part"] == "back_rounded" for issue in data["issues"]), data


# (2026-08-24) 어깨 말림 판정 지표(get_shoulder_forward_lean_deg) 단위 테스트가 이 자리에
# 있었다 — AI-03 삭제(위 주석 참고)와 함께 이 함수 자체가 angles.py에서 제거되며 같이
# 삭제했다. 같은 판정(SHOULDER_FORWARD_LEAN_THRESHOLD_DEG 임계값 비교)은 실시간 코칭
# (AI-06) 경로로 이미 test_coaching_frame_holding_shoulder_rounded_flagged()와
# test_coaching_frame_negative_shoulder_lean_not_flagged()가 검증하고 있다.


if __name__ == "__main__":
    test_health()
    test_coaching_frame_descending()
    test_coaching_frame_holding_at_bottom_normal()
    test_coaching_frame_holding_shoulder_rounded_flagged()
    test_coaching_frame_negative_shoulder_lean_not_flagged()
    test_coaching_frame_without_shoulder_fields_still_works()
    test_coaching_frame_holding_halfway_abnormal()
    test_coaching_frame_jittery_movement_flagged()
    test_coaching_frame_insufficient_frames()
    test_session_end_user_requested()
    test_session_end_not_enough_duration_yet()
    test_session_end_sustained_good_form()
    test_session_end_sustained_poor_form()
    test_personalized_hip_range_formula()
    test_personalized_hip_range_invalid_calibration_is_safe()
    test_coaching_frame_hip_calibration_changes_normal_judgement()
    test_posture_insight_level_posture_returns_no_tilt_message()
    test_posture_insight_tilted_posture_returns_percentile()
    test_posture_insight_old_age_maps_to_60_plus_bracket()
    test_orchestrate_fallback_no_signals_proceeds()
    test_orchestrate_fallback_low_visibility_requests_retake()
    test_orchestrate_fallback_user_requested_end_wins_over_low_confidence()
    test_orchestrate_fallback_repeated_issue_triggers_rag()
    test_harness_llm_path_parses_tool_use_response()
    test_harness_llm_failure_falls_back()
    test_rag_search_finds_relevant_document()
    test_rag_search_unrelated_query_returns_empty()
    test_rag_guide_fallback_matched()
    test_rag_guide_fallback_no_match_uses_generic_message()
    test_rag_qna_fallback_matched()
    test_rag_qna_fallback_no_match()
    test_rag_guide_llm_path_uses_generated_text()
    test_rag_guide_llm_failure_falls_back_to_short_message()
    test_rag_guide_endpoint_returns_valid_response()
    test_rag_qna_endpoint_returns_valid_response()
    test_aggregate_session_stats_basic()
    test_aggregate_session_stats_improvement_vs_previous()
    test_generate_session_report_fallback()
    test_generate_session_report_llm_path()
    test_session_report_endpoint_returns_valid_response()
    test_coaching_frame_heel_lift_flagged_when_deep_hold()
    test_coaching_frame_without_heel_lift_field_still_works()
    test_coaching_frame_heel_lift_ignored_while_standing()
    test_coaching_frame_knee_valgus_flagged_when_deep_hold()
    test_coaching_frame_knee_asymmetry_flagged_when_deep_hold()
    test_coaching_frame_without_frontal_fields_still_works()
    test_coaching_frame_knee_over_toe_flagged_when_deep_hold()
    test_coaching_frame_without_knee_over_toe_field_still_works()
    test_coaching_frame_back_rounded_flagged_when_deep_hold()
    test_coaching_frame_back_rounded_ignored_while_standing()
    test_coaching_frame_back_rounded_ignored_without_baseline()
    test_coaching_frame_without_torso_length_ratio_field_still_works()
    print("\nALL MANUAL CHECKS PASSED")
