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
from app.schemas import AngleFrame, HipFlexibilityCalibration
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


def test_coaching_frame_holding_gaze_forward_flagged():
    # 무릎/엉덩이는 정상 범위인데 shoulder_forward_lean_deg만 임계값(40.0)을 넘게(고개가
    # 앞으로 떨어짐) 들어온 경우 -> 이상 감지돼야 함. (2026-08-26: 이 신호는 원래 "어깨
    # 말림"도 같이 판정했으나, 어깨 말림/등 굽음은 back_rounded로 통합하고 여기는 목/시선
    # 전용 신호(part="gaze")로 분리했다 — rules.py/realtime.py 주석 참고. 2026-08-27:
    # 임곗값이 20.0 -> 40.0으로 올라가(실측 정상 사례 확장 + 귀 랜드마크 노이즈 감안,
    # rules.py 주석 참고) 테스트 입력값도 그에 맞춰 올림.)
    angle_history = [
        {
            "timestamp": i * 0.1,
            "knee_angle": 85 + (i % 2),
            "hip_angle": 80 + (i % 2),
            "shoulder_forward_lean_deg": 50,
        }
        for i in range(10)
    ]
    body = {"angle_history": angle_history}
    res = client.post("/ai/coaching/frame", json=body)
    print("coaching_frame(holding, gaze forward):", res.status_code, res.json())
    assert res.status_code == 200
    data = res.json()
    assert data["is_normal"] is False, data
    assert any(issue["part"] == "gaze" for issue in data["issues"]), data


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
    assert not any(issue["part"] == "gaze" for issue in data["issues"]), data


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
    assert not any(issue["part"] == "gaze" for issue in data["issues"]), data


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
        # (2026-08-27) knee_valgus 문서의 source가 NASM 인용에 Lorenzetti et al.
        # (2018) 인용이 추가되며 길어졌다 — 정확 일치 대신 두 출처가 모두 포함됐는지만 확인.
        assert "NASM" in result["sources"][0]["source"]
        assert "Lorenzetti" in result["sources"][0]["source"]

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
        history = make_frame_history(normal_count=6, abnormal_count=4, part="gaze", deviation_deg=20.0)
        result = generate_session_report(history, session_duration_sec=300.0, previous_sessions=[])
        print("generate_session_report(fallback):", result)
        assert result["generation_source"] == "fallback"
        assert result["normal_ratio"] == 0.6
        assert result["most_frequent_issue_part"] == "gaze"
        assert "시선" in result["summary_message"]  # PART_LABELS 매핑이 폴백 문구에 반영됐는지
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


# (2026-08-27 추가, 같은 날 재정정) 웨지·역도화처럼 원래 발뒤꿈치를 들고 서는 사용자를
# 위한 차이값 기준 판정 테스트 — 처음에는 온보딩 캘리브레이션(hip_calibration)에 기준값을
# 두려 했으나, 온보딩은 "힐업 안 한" 평상시 자세로 재는 게 보통이라 그날그날 웨지 사용
# 여부를 반영하지 못한다는 문제가 있어, angle_history 안에서 "이번 렙 직전 서 있던
# 프레임"을 실시간으로 찾아 기준값으로 쓰는 방식(_find_standing_baseline_before_dip)으로
# 바꿨다 — 아래 테스트는 hip_calibration이 아니라 angle_history 자체에 "서 있는 구간 +
# 깊게 앉은 구간"을 함께 넣어 이 동적 기준값 동작을 검증한다.
def _build_rep_history_with_standing_baseline(standing_heel_lift, hold_heel_lift, n_hold=120):
    """서 있는 구간(5프레임) -> 점진적 하강(20프레임) -> 깊게 앉아 멈춘 구간(n_hold프레임)을
    이어붙인 angle_history를 만든다. _find_standing_baseline_before_dip()이 찾을 "직전 서
    있던 프레임"을 실제로 포함시키면서도, phase 판정(knee_slope 전체 회귀)이 "holding"으로
    읽히도록 홀딩 구간을 충분히 길게 잡는다 — 하강을 3~4프레임 만에 뚝 끊어버리면(비현실적인
    순간이동) 전체 구간 회귀 기울기가 지나치게 가팔라져 phase가 "descending"으로 읽히고
    is_deep_hold 검사 블록 전체가 스킵돼버린다(judge_realtime_coaching은 "최근 N프레임"이
    아니라 angle_history 전체로 기울기를 계산한다 — DTW 렙 추출과 마찬가지로 실제 서비스는
    렙 시작부터의 전체 히스토리를 그대로 보내는 걸 전제하므로, 테스트도 실제 30fps 근처
    간격 + 충분한 홀딩 프레임 수로 맞춰야 phase 판정이 실제 상황과 같아진다).
    """
    frames = []
    for i in range(5):
        frames.append(
            {
                "timestamp": i * 0.033,
                "knee_angle": 175 + (i % 2),
                "hip_angle": 170 + (i % 2),
                "heel_lift_ratio": standing_heel_lift,
            }
        )
    descent_frames = 20
    for i in range(descent_frames):
        progress = (i + 1) / descent_frames
        frames.append(
            {
                "timestamp": (5 + i) * 0.033,
                "knee_angle": 175 - (175 - 85) * progress,
                "hip_angle": 170 - (170 - 80) * progress,
                # heel_lift_ratio는 하강 중에는 그대로 서 있을 때 값을 유지한다(발뒤꿈치는
                # 보통 하강 내내 바닥에 붙어있다가 깊게 앉은 뒤에야 변화가 생기는 게 자연스러운
                # 시나리오라서) — _find_standing_baseline_before_dip()이 찾는 "150도 문턱을
                # 넘기 직전 프레임"이 하강 중간의 임의 보간값이 아니라 정확히 standing_heel_lift
                # 값이 되도록 하기 위함이기도 하다.
                "heel_lift_ratio": standing_heel_lift,
            }
        )
    base_index = 5 + descent_frames
    for i in range(n_hold):
        frames.append(
            {
                "timestamp": (base_index + i) * 0.033,
                "knee_angle": 85 + (i % 2),
                "hip_angle": 80 + (i % 2),
                "heel_lift_ratio": hold_heel_lift,
            }
        )
    return frames


def test_coaching_frame_heel_lift_dynamic_baseline_prevents_false_positive_for_elevated_standing():
    # 서 있을 때부터 heel_lift_ratio가 이미 임곗값을 넘는 사용자(웨지 사용) — 스쿼트 중에도
    # 서 있을 때와 거의 같은 값이면(추가로 더 들리지 않았으면) 이상으로 잡으면 안 된다.
    baseline = HEEL_LIFT_RATIO_THRESHOLD + 0.2  # 서 있을 때부터 이미 임곗값 초과
    angle_history = _build_rep_history_with_standing_baseline(baseline, baseline + 0.05)
    body = {"angle_history": angle_history}
    res = client.post("/ai/coaching/frame", json=body)
    print("coaching_frame(heel lift, dynamic elevated standing baseline):", res.status_code, res.json())
    assert res.status_code == 200
    data = res.json()
    assert data["phase"] == "holding", data  # phase 판정 자체가 잘못돼 검사가 스킵된 게 아닌지 확인
    assert not any(issue["part"] == "heel" for issue in data["issues"]), data


def test_coaching_frame_heel_lift_dynamic_baseline_still_flags_real_lift():
    # 서 있을 때 기준값이 낮은 사용자가 스쿼트 중 실제로 기준보다 크게 더 들리면(차이값이
    # 임곗값을 넘으면) 절대값이 임곗값 미만이어도 이상으로 잡아야 한다.
    baseline = -0.3
    latest = 0.5  # 절대값만 보면 HEEL_LIFT_RATIO_THRESHOLD(0.7) 미만이라 기존 방식이면 안 잡힘
    assert latest < HEEL_LIFT_RATIO_THRESHOLD
    assert latest - baseline > HEEL_LIFT_RATIO_THRESHOLD
    angle_history = _build_rep_history_with_standing_baseline(baseline, latest)
    body = {"angle_history": angle_history}
    res = client.post("/ai/coaching/frame", json=body)
    print("coaching_frame(heel lift, dynamic baseline catches real lift):", res.status_code, res.json())
    assert res.status_code == 200
    data = res.json()
    assert data["phase"] == "holding", data
    assert any(issue["part"] == "heel" for issue in data["issues"]), data


def test_coaching_frame_heel_lift_falls_back_to_absolute_without_standing_prefix():
    # angle_history 안에 "서 있던 프레임"이 아예 없으면(예: 이미 깊게 앉은 채로 시작하는
    # 히스토리) 동적 기준값을 못 찾아 기존처럼 절대값(HEEL_LIFT_RATIO_THRESHOLD)으로
    # 판정해야 한다 — test_coaching_frame_heel_lift_flagged_when_deep_hold와 같은 상황이지만,
    # 여기서는 "왜 절대값 경로를 타는지"를 명시적으로 검증한다.
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
    print("coaching_frame(heel lift, no standing prefix -> absolute fallback):", res.status_code, res.json())
    assert res.status_code == 200
    data = res.json()
    assert any(issue["part"] == "heel" for issue in data["issues"]), data


# (2026-08-24) 무릎 모임/좌우 비대칭 규칙기반 검사의 단위 테스트(get_knee_valgus_ratio/
# get_knee_lr_asymmetry_deg 직접 호출)와 그 /ai/pose/analyze 통합 테스트가 이 자리에
# 있었다 — AI-03 삭제(위 주석 참고)와 함께 이 두 함수 자체가 angles.py에서 제거되며 같이
# 삭제했다. 아래 test_coaching_frame_knee_valgus_*/knee_asymmetry_* 테스트들이 실시간
# 코칭(AI-06) 경로로 같은 임계값(KNEE_VALGUS_RATIO_THRESHOLD/KNEE_ASYMMETRY_THRESHOLD_DEG)
# 판정을 계속 검증한다.
from app.pose.rules import (  # noqa: E402
    KNEE_ASYMMETRY_THRESHOLD_DEG,
    KNEE_VALGUS_RATIO_THRESHOLD,
)


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


# (2026-08-25 도입 → 2026-08-27 폐기) 이 자리에 고관절 과신전 의심 판정
# (rules.py의 HIP_HYPEREXTENSION_VALGUS_THRESHOLD, knee_valgus_ratio가 0.8~1.1이면
# 별도 태깅) 테스트 4건이 있었다. 그 판정 로직 자체가 근거 부족(N=1 잠정치)으로 폐기되며
# 함께 삭제했다 — 자세한 배경은 rules.py의 HIP_HYPEREXTENSION_VALGUS_THRESHOLD 자리에
# 남은 주석과 checklist 2026-08-27 addendum 참고.


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


# (2026-08-27 추가) 오버헤드 스쿼트 보상작용 참고 사진(무릎각도 154~158도)을 실제
# mediapipe로 검증하다가, 무릎 모임(valgus)이 교과서적으로 뚜렷한 사진조차
# is_deep_hold(무릎각도<150도) 게이트에 막혀 통째로 안 잡히는 걸 확인했다. 무릎 모임/
# 좌우비대칭을 목/시선과 동일하게 상시검사로 바꾼 변경(realtime.py)이 실제로 "깊게 안
# 앉은(무릎각도>=150도) 상태"에서도 잡아내는지 회귀로 고정한다.
def test_coaching_frame_knee_valgus_flagged_even_when_not_deep_hold():
    angle_history = [
        {
            "timestamp": i * 0.1,
            "knee_angle": 155,  # STANDING_KNEE_ANGLE_MIN(150) 이상 — is_deep_hold=False
            "hip_angle": 165,
            "knee_valgus_ratio": KNEE_VALGUS_RATIO_THRESHOLD - 0.3,
        }
        for i in range(10)
    ]
    body = {"angle_history": angle_history}
    res = client.post("/ai/coaching/frame", json=body)
    print("coaching_frame(knee valgus, NOT deep hold):", res.status_code, res.json())
    assert res.status_code == 200
    data = res.json()
    assert data["is_normal"] is False, data
    assert any(issue["part"] == "knee_valgus" for issue in data["issues"]), data


def test_coaching_frame_knee_asymmetry_flagged_even_when_not_deep_hold():
    angle_history = [
        {
            "timestamp": i * 0.1,
            "knee_angle": 155,  # STANDING_KNEE_ANGLE_MIN(150) 이상 — is_deep_hold=False
            "hip_angle": 165,
            "knee_asymmetry_deg": KNEE_ASYMMETRY_THRESHOLD_DEG + 10.0,
        }
        for i in range(10)
    ]
    body = {"angle_history": angle_history}
    res = client.post("/ai/coaching/frame", json=body)
    print("coaching_frame(knee asymmetry, NOT deep hold):", res.status_code, res.json())
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


# (2026-08-27) 무게중심(get_torso_shin_lean_gap_deg 기반) 판정 테스트. knee_over_toe와
# 동일하게 is_deep_hold(무릎이 충분히 굽혀진 상태)에서만 검사한다 — rules.py의
# TORSO_SHIN_LEAN_GAP_THRESHOLD_DEG 주석 참고. 나쁜 사례 표본이 2건뿐인 잠정 임계값이라,
# 팀 확정 전까지 이 값(25.0)은 언제든 바뀔 수 있다.
from app.pose.rules import TORSO_SHIN_LEAN_GAP_THRESHOLD_DEG  # noqa: E402


def test_coaching_frame_center_of_mass_flagged_when_deep_hold():
    angle_history = [
        {
            "timestamp": i * 0.1,
            "knee_angle": 85 + (i % 2),
            "hip_angle": 80 + (i % 2),
            "torso_shin_lean_gap_deg": TORSO_SHIN_LEAN_GAP_THRESHOLD_DEG + 2.0,
        }
        for i in range(10)
    ]
    body = {"angle_history": angle_history}
    res = client.post("/ai/coaching/frame", json=body)
    print("coaching_frame(center of mass, deep hold):", res.status_code, res.json())
    assert res.status_code == 200
    data = res.json()
    assert data["is_normal"] is False, data
    assert any(issue["part"] == "center_of_mass" for issue in data["issues"]), data


def test_coaching_frame_without_center_of_mass_field_still_works():
    # torso_shin_lean_gap_deg 필드를 아예 안 보내는 기존 프론트 호출도 에러 없이 동작해야 한다(하위 호환).
    angle_history = [
        {"timestamp": i * 0.1, "knee_angle": 85 + (i % 2), "hip_angle": 80 + (i % 2)} for i in range(10)
    ]
    body = {"angle_history": angle_history}
    res = client.post("/ai/coaching/frame", json=body)
    print("coaching_frame(no torso_shin_lean_gap_deg field):", res.status_code, res.json())
    assert res.status_code == 200
    data = res.json()
    assert not any(issue["part"] == "center_of_mass" for issue in data["issues"]), data


# (2026-08-27) DTW(동적 시간 워핑) 렙 패턴 유사도 판정 테스트. 다른 검사들과 달리 이
# 검사는 정적인 마지막 프레임 값이 아니라 "렙 1개 전체의 움직임 곡선"을 실제 정상 렙
# 템플릿 20개(app/pose/dtw_templates/*.json)와 비교하므로, 손으로 대충 지어낸 몇 개
# 숫자로는 의미 있는 테스트가 안 된다 — 실제 템플릿 하나(우혁_정상.mp4_rep0)를 정규화
# 기준값(mean/std)으로 역정규화해 "진짜였던 원본 raw 값"을 복원한 뒤, 그걸 그대로 보내면
# 정상 판정이, 지표를 크게 왜곡해서 보내면 이상 판정이 나오는지를 확인한다(임곗값
# DTW_NEAREST_DISTANCE_THRESHOLD=20.0의 근거는 rules.py 주석 참고, 아래 왜곡 폭은
# 2026-08-27 실측으로 실제 거리값이 20.0을 넘는 걸 미리 확인한 값이다 — 거리=41.9).
from pathlib import Path as _Path  # noqa: E402

from app.pose.dtw_matching import load_templates as _load_dtw_templates_for_test  # noqa: E402

_DTW_TEST_TEMPLATE = next(
    t
    for t in _load_dtw_templates_for_test(_Path(__file__).parent.parent / "app" / "pose" / "dtw_templates")
    if "우혁_정상.mp4_rep0" in t.source
)


def _real_dtw_rep_angle_history(hip_offset=0.0, shoulder_offset=0.0, torso_scale=1.0):
    """실제 템플릿 하나를 역정규화해 angle_history(dict 리스트)를 만든다. 맨 앞에 "서 있는"
    프레임 1개를 붙여 _extract_last_completed_rep이 렙 시작/끝 경계를 찾을 수 있게 한다."""
    t = _DTW_TEMPLATE = _DTW_TEST_TEMPLATE
    means, stds = t.normalization.means, t.normalization.stds
    n = t.curve.shape[0]
    raw = {
        field: (t.curve[:, j] * stds[field] + means[field]).tolist()
        for j, field in enumerate(t.metric_fields)
    }
    frames = [
        {
            "timestamp": -0.033,
            "knee_angle": 172.0,
            "hip_angle": 175.0 + hip_offset,
            "torso_length_ratio": sum(raw["torso_length_ratio"]) / n * torso_scale,
            "shoulder_forward_lean_deg": sum(raw["shoulder_forward_lean_deg"]) / n + shoulder_offset,
        }
    ]
    for i in range(n):
        frames.append(
            {
                "timestamp": i * 0.033,
                "knee_angle": raw["knee_angle"][i],
                "hip_angle": raw["hip_angle"][i] + hip_offset,
                "torso_length_ratio": raw["torso_length_ratio"][i] * torso_scale,
                "shoulder_forward_lean_deg": raw["shoulder_forward_lean_deg"][i] + shoulder_offset,
            }
        )
    return frames


def test_coaching_frame_dtw_form_pattern_not_flagged_for_real_normal_rep():
    angle_history = _real_dtw_rep_angle_history()  # 왜곡 없음 — 템플릿 원본 그대로
    body = {"angle_history": angle_history}
    res = client.post("/ai/coaching/frame", json=body)
    print("coaching_frame(dtw, 왜곡 없는 실제 렙):", res.status_code, res.json())
    assert res.status_code == 200
    data = res.json()
    assert not any(issue["part"] == "form_pattern" for issue in data["issues"]), data


def test_coaching_frame_dtw_form_pattern_flagged_when_severely_distorted():
    # hip_angle +60도, shoulder_forward_lean_deg +80도, torso_length_ratio 0.3배 —
    # 2026-08-27 실측으로 nearest_normal_distance가 41.9(임곗값 20.0의 2배 이상)가
    # 나오는 걸 미리 확인한 왜곡 폭이다.
    angle_history = _real_dtw_rep_angle_history(hip_offset=60.0, shoulder_offset=80.0, torso_scale=0.3)
    body = {"angle_history": angle_history}
    res = client.post("/ai/coaching/frame", json=body)
    print("coaching_frame(dtw, 심하게 왜곡된 렙):", res.status_code, res.json())
    assert res.status_code == 200
    data = res.json()
    assert data["is_normal"] is False, data
    assert any(issue["part"] == "form_pattern" for issue in data["issues"]), data


def test_coaching_frame_dtw_skipped_when_optional_fields_missing():
    # 렙 모양(150도 아래로 내려갔다 올라옴)은 갖췄지만 torso_length_ratio/
    # shoulder_forward_lean_deg를 안 보내는 기존 프론트 호출 — DTW 비교에 필요한
    # 지표가 없으므로(extract_metric_matrix가 ValueError) 에러 없이 조용히
    # 건너뛰어야 한다(하위 호환, 다른 선택 필드 검사들과 동일한 패턴).
    knee_seq = [172, 160, 140, 110, 90, 85, 88, 95, 120, 150, 165, 172]
    hip_seq = [175, 165, 150, 120, 100, 95, 98, 105, 130, 155, 168, 175]
    angle_history = [
        {"timestamp": i * 0.1, "knee_angle": k, "hip_angle": h}
        for i, (k, h) in enumerate(zip(knee_seq, hip_seq))
    ]
    body = {"angle_history": angle_history}
    res = client.post("/ai/coaching/frame", json=body)
    print("coaching_frame(dtw, 선택 필드 없음):", res.status_code, res.json())
    assert res.status_code == 200
    data = res.json()
    assert not any(issue["part"] == "form_pattern" for issue in data["issues"]), data


# (2026-08-28 추가, 2026-08-28 같은 날 폐기) 정면 전용 DTW 고관절 과신전 판정
# (coaching/realtime.py (1.6) 블록) 테스트 3건이 이 자리에 있었다 — 정면 카메라는
# 고관절 과신전(시상면 신호)을 원리적으로 촬영할 수 없다는 게 실측으로 확인돼 판정
# 로직 전체와 함께 삭제했다. 자세한 배경은 checklist 2026-08-28 addendum 참고.


# (2026-08-28) 측면 DTW+LLM 하이브리드(app/coaching/hyperextension_llm_check.py) 테스트.
# 위 정면 DTW 테스트들과 마찬가지로 실제 템플릿(우혁_정상.mp4_rep0)을 왜곡해 DTW
# 최근접거리를 원하는 범위로 만든다 — 아래 두 함수가 쓰는 offset 조합은 rules.py의
# DTW_AMBIGUOUS_LOWER_DISTANCE(10.0)~DTW_AMBIGUOUS_UPPER_DISTANCE(30.0) 경계를 실측으로
# 캘리브레이션한 결과다:
#   - hip_offset=15.0, shoulder_offset=20.0, torso_scale=0.75 -> distance ≈ 10.82
#     (하한 10.0보다 살짝 위, 옛 임곗값 20.0보다는 한참 아래 — 애매한 구간의 "낮은 쪽")
#   - hip_offset=35.0, shoulder_offset=45.0, torso_scale=0.4 -> distance ≈ 23.19
#     (옛 임곗값 20.0은 넘지만 새 상한 30.0보다는 아래 — 애매한 구간의 "높은 쪽")
# 이 테스트 환경엔 AWS_BEDROCK_REGION/HYPEREXTENSION_BEDROCK_MODEL_ID가 설정돼있지
# 않으므로(로컬 .env에 우연히 있어도 아래 헬퍼로 잠시 지운다 — _without_llm_env와 동일한
# 이유), start_hyperextension_analysis()가 항상 None을 반환해 realtime.py가 기존 DTW
# 임곗값(DTW_NEAREST_DISTANCE_THRESHOLD=20.0) 방식으로 폴백한다 — 즉 아래 두 테스트는
# "LLM 미설정 환경에서도 하위 호환이 깨지지 않는다"를 검증한다. 실제 LLM 경로 자체는 더
# 아래 test_coaching_frame_hyperextension_llm_hybrid_end_to_end()가 monkeypatch로
# 검증한다.
def _without_aws_bedrock_env(fn):
    from app.coaching.hyperextension_llm_check import AWS_REGION_ENV_VAR, BEDROCK_MODEL_ID_ENV_VAR

    saved = {}
    for key in (AWS_REGION_ENV_VAR, BEDROCK_MODEL_ID_ENV_VAR):
        saved[key] = os.environ.pop(key, None)
    try:
        return fn()
    finally:
        for key, value in saved.items():
            if value is not None:
                os.environ[key] = value


def test_coaching_frame_dtw_ambiguous_below_old_threshold_no_llm_not_flagged():
    def run():
        angle_history = _real_dtw_rep_angle_history(hip_offset=15.0, shoulder_offset=20.0, torso_scale=0.75)
        body = {"angle_history": angle_history}
        res = client.post("/ai/coaching/frame", json=body)
        print("coaching_frame(측면 dtw, 애매한 구간 낮은 쪽, LLM 미설정):", res.status_code, res.json())
        assert res.status_code == 200
        data = res.json()
        assert not any(issue["part"] in ("form_pattern", "hip_hyperextension") for issue in data["issues"]), data
        assert data["pending_llm_job_id"] is None, data

    _without_aws_bedrock_env(run)


def test_coaching_frame_dtw_ambiguous_above_old_threshold_no_llm_falls_back_and_flags():
    def run():
        angle_history = _real_dtw_rep_angle_history(hip_offset=35.0, shoulder_offset=45.0, torso_scale=0.4)
        body = {"angle_history": angle_history}
        res = client.post("/ai/coaching/frame", json=body)
        print("coaching_frame(측면 dtw, 애매한 구간 높은 쪽, LLM 미설정):", res.status_code, res.json())
        assert res.status_code == 200
        data = res.json()
        assert any(issue["part"] == "form_pattern" for issue in data["issues"]), data
        assert not any(issue["part"] == "hip_hyperextension" for issue in data["issues"]), data
        assert data["pending_llm_job_id"] is None, data

    _without_aws_bedrock_env(run)


# --- 아래는 hyperextension_llm_check.py 모듈 자체의 단위 테스트 — harness.py 테스트가
# 쓰는 _FakeToolUseBlock/_FakeMessage/_FakeMessagesAPI/_FakeAnthropicClient(위 429번째 줄
# 근처)와 generation.py 테스트가 쓰는 _FakeTextBlock(위 681번째 줄 근처)을 그대로 재사용한다
# — AnthropicBedrock 클라이언트도 client.messages.create(...) -> response.content 구조가
# 동일해(둘 다 anthropic SDK) 같은 가짜로 검증할 수 있다.
def test_hyperextension_check_no_client_when_unconfigured():
    def run():
        from app.coaching.hyperextension_llm_check import start_hyperextension_analysis

        angle_history = _real_dtw_rep_angle_history()
        job_id = start_hyperextension_analysis(angle_history)
        assert job_id is None

    _without_aws_bedrock_env(run)


def test_hyperextension_check_job_completes_and_is_consumed_once():
    from app.coaching.hyperextension_llm_check import get_job_result, start_hyperextension_analysis

    block = _FakeToolUseBlock(
        "report_hip_hyperextension_verdict",
        {"verdict": "과신전_의심", "confidence": "중", "reasoning": "테스트용 판정"},
    )
    fake_client = _FakeAnthropicClient(block=block)
    # _call_llm 내부(_build_prompt)가 AngleFrame 속성 접근(f.timestamp 등)을 하므로 —
    # realtime.py가 실제로 넘기는 것과 같은 타입으로 맞춘다(원시 dict가 아님).
    angle_history = [AngleFrame(**f) for f in _real_dtw_rep_angle_history()]
    job_id = start_hyperextension_analysis(
        angle_history, client=fake_client, model="test-model", run_in_background=False
    )
    assert job_id is not None

    result = get_job_result(job_id)
    assert result == {"verdict": "과신전_의심", "confidence": "중", "reasoning": "테스트용 판정"}
    # 1회성 소비 — 같은 job_id로 다시 조회하면 아무것도 안 나온다.
    assert get_job_result(job_id) is None


def test_hyperextension_check_job_error_returns_none():
    from app.coaching.hyperextension_llm_check import get_job_result, start_hyperextension_analysis

    fake_client = _FakeAnthropicClient(exc=RuntimeError("network down"))
    angle_history = [AngleFrame(**f) for f in _real_dtw_rep_angle_history()]
    job_id = start_hyperextension_analysis(
        angle_history, client=fake_client, model="test-model", run_in_background=False
    )
    assert job_id is not None
    assert get_job_result(job_id) is None


def test_hyperextension_check_missing_tool_use_block_treated_as_error():
    from app.coaching.hyperextension_llm_check import get_job_result, start_hyperextension_analysis

    fake_client = _FakeAnthropicClient(block=_FakeTextBlock("tool_use 아닌 응답"))
    angle_history = [AngleFrame(**f) for f in _real_dtw_rep_angle_history()]
    job_id = start_hyperextension_analysis(
        angle_history, client=fake_client, model="test-model", run_in_background=False
    )
    assert job_id is not None
    assert get_job_result(job_id) is None


def test_hyperextension_check_get_job_result_unknown_id_returns_none():
    from app.coaching.hyperextension_llm_check import get_job_result

    assert get_job_result(None) is None
    assert get_job_result("no-such-job-id") is None


def test_hyperextension_check_job_expires_after_ttl():
    import time as _time

    import app.coaching.hyperextension_llm_check as hll

    block = _FakeToolUseBlock(
        "report_hip_hyperextension_verdict",
        {"verdict": "정상", "confidence": "상", "reasoning": "테스트용"},
    )
    fake_client = _FakeAnthropicClient(block=block)
    angle_history = [AngleFrame(**f) for f in _real_dtw_rep_angle_history()]
    job_id = hll.start_hyperextension_analysis(
        angle_history, client=fake_client, model="test-model", run_in_background=False
    )
    assert job_id is not None

    # TTL을 직접 만료시켜(created_at을 과거로 되돌려) 정리 로직(_cleanup_expired_locked)이
    # get_job_result() 호출 시점에 얹혀 동작하는지 확인한다 — 실제로 300초를 기다리지 않는다.
    with hll._jobs_lock:
        hll._jobs[job_id]["created_at"] = _time.time() - hll.LLM_HYPEREXTENSION_JOB_TTL_SECONDS - 1

    assert hll.get_job_result(job_id) is None


def test_hyperextension_check_downsample_caps_frame_count():
    import app.coaching.hyperextension_llm_check as hll

    base_history = _real_dtw_rep_angle_history()
    frames = [AngleFrame(**f) for f in base_history] * 3  # MAX_PROMPT_FRAMES(60) 넘기기
    assert len(frames) > hll.MAX_PROMPT_FRAMES
    sampled = hll._downsample(frames)
    assert len(sampled) == hll.MAX_PROMPT_FRAMES


def test_hyperextension_check_build_prompt_includes_side_fields():
    import app.coaching.hyperextension_llm_check as hll

    angle_history = _real_dtw_rep_angle_history()
    frames = [AngleFrame(**f) for f in angle_history]
    prompt = hll._build_prompt(frames)
    assert "hip_angle=" in prompt
    assert "knee_angle=" in prompt
    assert "과신전" in prompt


def test_coaching_frame_hyperextension_llm_hybrid_end_to_end(monkeypatch):
    # 전체 job_id 왕복 흐름을 실제 엔드포인트(/ai/coaching/frame)로 검증한다 — 사용자가
    # 제안한 "첫 렙은 DTW 결과만(애매하면 얘기도 안 함), 다음 호출에서 준비돼 있으면 그때
    # 알려줌" 시나리오 그대로다. 이 저장소 테스트 스위트에 monkeypatch가 쓰인 유일한
    # 자리인데, judge_realtime_coaching()이 이 기능을 위해 별도 client 주입 파라미터를
    # 노출하지 않게 설계했기 때문이다(모듈 내부 함수 자체를 갈아끼워야 함) — 위
    # _Fake*client 패턴(의존성 주입)과는 다른 이유의 의도적 선택이다.
    import app.coaching.realtime as realtime_module

    fake_job_id = "fake-job-123"
    monkeypatch.setattr(realtime_module, "_start_hyperextension_analysis", lambda rep_frames: fake_job_id)

    # 1차 호출 시점엔 pending_llm_job_id가 없어 이 mock이 아예 호출되지 않고(아래 참고),
    # 2차 호출에서 프론트가 job_id를 실어 보낼 때 처음 호출된다 — 그때 이미 "완료"로
    # 응답하게 해 2번의 왕복으로 전체 흐름(시작 -> 결과 수신)을 검증한다. 실제로는 폴링
    # 여러 번 만에 준비될 수 있다는 것은 get_job_result() 자체의 pending 동작을 검증하는
    # 위 단위 테스트들이 이미 확인했다.
    def fake_get_job_result(job_id):
        assert job_id == fake_job_id
        return {"verdict": "과신전_의심", "confidence": "중", "reasoning": "테스트"}

    monkeypatch.setattr(realtime_module, "_get_llm_job_result", fake_get_job_result)

    angle_history = _real_dtw_rep_angle_history(hip_offset=15.0, shoulder_offset=20.0, torso_scale=0.75)

    # 1차 호출 — 애매한 구간이라 job이 새로 시작되지만, 아직 결과가 없으므로 이슈로
    # 나타나면 안 된다(사용자 제안: "애매한 건 얘기도 하지 말고").
    body = {"angle_history": angle_history}
    res1 = client.post("/ai/coaching/frame", json=body)
    print("coaching_frame(LLM 하이브리드 1차):", res1.status_code, res1.json())
    assert res1.status_code == 200
    data1 = res1.json()
    assert not any(issue["part"] in ("form_pattern", "hip_hyperextension") for issue in data1["issues"]), data1
    assert data1["pending_llm_job_id"] == fake_job_id, data1

    # 2차 호출 — 프론트가 job_id를 그대로 실어 보내면, 이번엔 결과가 준비돼있어(_run_job이
    # "완료" 상태를 흉내) 이슈로 전달되고 pending_llm_job_id는 지워진다(1회성 소비 +
    # 새로 시작할 job도 없음).
    body2 = {"angle_history": angle_history, "pending_llm_job_id": fake_job_id}
    res2 = client.post("/ai/coaching/frame", json=body2)
    print("coaching_frame(LLM 하이브리드 2차, job 완료):", res2.status_code, res2.json())
    assert res2.status_code == 200
    data2 = res2.json()
    assert any(issue["part"] == "hip_hyperextension" for issue in data2["issues"]), data2
    assert data2["pending_llm_job_id"] is None, data2


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
    # 없으면(하위 호환) 기준값이 없어 등 굽음(이상 유무) 자체는 판정하지 않는다 — 다만
    # 조용히 건너뛰지 않고, 캘리브레이션이 필요하다는 안내(data 항목)는 대신 나가야 한다
    # (2026-08-26: 어깨 말림까지 이 검사로 흡수된 뒤로 추가된 동작).
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
    assert any(issue["part"] == "data" and "캘리브레이션" in issue["message"] for issue in data["issues"]), data


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
    test_coaching_frame_holding_gaze_forward_flagged()
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
    test_coaching_frame_heel_lift_dynamic_baseline_prevents_false_positive_for_elevated_standing()
    test_coaching_frame_heel_lift_dynamic_baseline_still_flags_real_lift()
    test_coaching_frame_heel_lift_falls_back_to_absolute_without_standing_prefix()
    test_coaching_frame_knee_valgus_flagged_when_deep_hold()
    test_coaching_frame_knee_asymmetry_flagged_when_deep_hold()
    test_coaching_frame_without_frontal_fields_still_works()
    test_coaching_frame_knee_over_toe_flagged_when_deep_hold()
    test_coaching_frame_without_knee_over_toe_field_still_works()
    test_coaching_frame_back_rounded_flagged_when_deep_hold()
    test_coaching_frame_back_rounded_ignored_while_standing()
    test_coaching_frame_back_rounded_ignored_without_baseline()
    test_coaching_frame_without_torso_length_ratio_field_still_works()
    test_coaching_frame_center_of_mass_flagged_when_deep_hold()
    test_coaching_frame_without_center_of_mass_field_still_works()
    test_coaching_frame_dtw_form_pattern_not_flagged_for_real_normal_rep()
    test_coaching_frame_dtw_form_pattern_flagged_when_severely_distorted()
    test_coaching_frame_dtw_skipped_when_optional_fields_missing()
    test_coaching_frame_dtw_ambiguous_below_old_threshold_no_llm_not_flagged()
    test_coaching_frame_dtw_ambiguous_above_old_threshold_no_llm_falls_back_and_flags()
    test_hyperextension_check_no_client_when_unconfigured()
    test_hyperextension_check_job_completes_and_is_consumed_once()
    test_hyperextension_check_job_error_returns_none()
    test_hyperextension_check_missing_tool_use_block_treated_as_error()
    test_hyperextension_check_get_job_result_unknown_id_returns_none()
    test_hyperextension_check_job_expires_after_ttl()
    test_hyperextension_check_downsample_caps_frame_count()
    test_hyperextension_check_build_prompt_includes_side_fields()
    # test_coaching_frame_hyperextension_llm_hybrid_end_to_end()는 pytest monkeypatch
    # 픽스처가 있어야 해서(다른 테스트들처럼 인자 없이 직접 호출 불가) 이 수동 체크
    # 블록에는 포함하지 않는다 — pytest 실행(python3 -m pytest tests/)으로만 검증한다.
    print("\nALL MANUAL CHECKS PASSED")
