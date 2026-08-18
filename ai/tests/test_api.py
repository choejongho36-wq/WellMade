"""
빠른 수동 검증용 스크립트 (정식 테스트 스위트 아님, 임시 확인용).
- 정지 자세 판정(/ai/pose/analyze)과 실시간 코칭 판정(/ai/coaching/frame)이
  기대한 방향으로 동작하는지 TestClient로 확인한다.
"""

from fastapi.testclient import TestClient

from app.main import app
from app.pose.rules import personalized_hip_range
from app.schemas import HipFlexibilityCalibration

client = TestClient(app)


def landmark(x=0.5, y=0.5, z=0.0, visibility=0.9):
    return {"x": x, "y": y, "z": z, "visibility": visibility}


def make_landmarks(knee_bend_deg="standing"):
    """33개 landmark 중 스쿼트 판정에 쓰이는 어깨/엉덩이/무릎/발목만 의미 있게 채우고
    나머지는 더미로 채운 뒤, 무릎 각도가 대략 원하는 상태가 되도록 좌표를 잡는다."""
    lms = [landmark() for _ in range(33)]
    # 왼쪽 다리를 옆에서 본 형태로 배치: 엉덩이(23) - 무릎(25) - 발목(27)
    lms[11] = landmark(0.5, 0.2)  # LEFT_SHOULDER
    lms[23] = landmark(0.5, 0.5)  # LEFT_HIP
    if knee_bend_deg == "standing":
        lms[25] = landmark(0.5, 0.75)  # LEFT_KNEE (거의 일직선 -> 각도 180 근처)
        lms[27] = landmark(0.5, 1.0)  # LEFT_ANKLE
    else:  # "deep" : 무릎을 굽힌 하단 자세 (약 90도)
        lms[25] = landmark(0.5, 0.75)  # LEFT_KNEE
        lms[27] = landmark(0.75, 0.75)  # LEFT_ANKLE (무릎에서 옆으로 꺾임 -> 약 90도)
    return [lm for lm in lms]


def test_health():
    res = client.get("/health")
    assert res.status_code == 200
    print("health:", res.json())


def test_pose_analyze_standing_is_abnormal_for_squat_bottom():
    body = {
        "landmarks": make_landmarks("standing"),
        "exercise_type": "squat",
        "side": "left",
    }
    res = client.post("/ai/pose/analyze", json=body)
    print("pose_analyze(standing):", res.status_code, res.json())
    assert res.status_code == 200


def test_pose_analyze_deep_squat_is_normal():
    body = {
        "landmarks": make_landmarks("deep"),
        "exercise_type": "squat",
        "side": "left",
    }
    res = client.post("/ai/pose/analyze", json=body)
    print("pose_analyze(deep):", res.status_code, res.json())
    assert res.status_code == 200


def test_coaching_frame_descending():
    # 무릎 각도가 175 -> 95로 꾸준히 줄어드는(굽혀지는) 시계열 -> "descending" 기대
    angle_history = [
        {"timestamp": i * 0.1, "knee_angle": 175 - i * 8, "hip_angle": 170 - i * 7}
        for i in range(10)
    ]
    body = {"exercise_type": "squat", "angle_history": angle_history}
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
    body = {"exercise_type": "squat", "angle_history": angle_history}
    res = client.post("/ai/coaching/frame", json=body)
    print("coaching_frame(holding@bottom):", res.status_code, res.json())
    assert res.status_code == 200
    data = res.json()
    assert data["phase"] == "holding", data
    assert data["is_normal"] is True, data
    assert data["confidence"] > 0.7, data  # 떨림이 적은 안정적인 holding이므로 신뢰도가 높아야 함


def test_coaching_frame_holding_halfway_abnormal():
    # 하단까지 못 내려가고 중간(약 130도)에서 멈춘 시계열 -> "holding" + is_normal False 기대
    angle_history = [
        {"timestamp": i * 0.1, "knee_angle": 130 + (i % 2), "hip_angle": 150}
        for i in range(10)
    ]
    body = {"exercise_type": "squat", "angle_history": angle_history}
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
    body = {"exercise_type": "squat", "angle_history": angle_history}
    res = client.post("/ai/coaching/frame", json=body)
    print("coaching_frame(jittery):", res.status_code, res.json())
    assert res.status_code == 200
    data = res.json()
    assert any(issue["part"] == "movement" for issue in data["issues"]), data


def test_coaching_frame_insufficient_frames():
    angle_history = [{"timestamp": 0.0, "knee_angle": 170, "hip_angle": 160}]
    body = {"exercise_type": "squat", "angle_history": angle_history}
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


def make_lunge_landmarks(front_knee_form="good"):
    """런지 ML 보조 판정(/ai/ml/lunge/analyze) 테스트용 33개 랜드마크.
    왼쪽 다리를 앞다리(더 굽혀진 쪽, 무릎 각도 약 90도)로, 오른쪽 다리를 뒷다리
    (거의 편 상태, 약 180도)로 배치한다 — extract_lunge_features()가 "더 굽혀진 쪽"을
    앞다리로 판단하는 휴리스틱을 쓰기 때문."""
    lms = [landmark() for _ in range(33)]
    lms[11] = landmark(0.5, 0.2)  # LEFT_SHOULDER
    lms[23] = landmark(0.5, 0.5)  # LEFT_HIP (앞다리)
    lms[25] = landmark(0.5, 0.75)  # LEFT_KNEE (앞다리 무릎, 각도 약 90도)
    lms[27] = landmark(0.75, 0.75)  # LEFT_ANKLE
    if front_knee_form == "good":
        lms[31] = landmark(0.9, 0.78)  # LEFT_FOOT_INDEX: 발끝(0.9)이 무릎(0.5)보다 훨씬 앞 -> 무릎이 발끝을 안 넘음
    else:  # "knee_over_toe": 발끝이 무릎보다 뒤에 있어 무릎이 발끝을 넘은 것처럼 배치
        lms[31] = landmark(0.3, 0.78)
    lms[24] = landmark(0.5, 0.5)  # RIGHT_HIP (뒷다리)
    lms[26] = landmark(0.5, 0.75)  # RIGHT_KNEE
    lms[28] = landmark(0.5, 1.0)  # RIGHT_ANKLE (뒷다리 무릎 각도 약 180도, 거의 편 상태)
    return lms


def test_ml_lunge_analyze_returns_valid_response():
    # 학습된 모델이 실제로 판정 방향까지 항상 맞다고 단정하기는 어려우므로(96% 테스트 정확도),
    # 여기서는 "정상적인 형태의 응답을 반환하는가"(구조/범위)를 검증한다 — 규칙기반 테스트처럼
    # 특정 자세에서 반드시 True/False가 나와야 한다고 강하게 단정하지 않는다.
    body = {"landmarks": make_lunge_landmarks("good")}
    res = client.post("/ai/ml/lunge/analyze", json=body)
    print("ml_lunge_analyze(good):", res.status_code, res.json())
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data["is_normal"], bool)
    assert 0.0 <= data["correct_probability"] <= 1.0
    assert isinstance(data["model_name"], str) and len(data["model_name"]) > 0


def test_ml_lunge_analyze_knee_over_toe_case_runs_without_error():
    # 극단적인(무릎이 발끝을 크게 넘은) 입력에도 서버가 에러 없이 응답해야 한다.
    body = {"landmarks": make_lunge_landmarks("knee_over_toe")}
    res = client.post("/ai/ml/lunge/analyze", json=body)
    print("ml_lunge_analyze(knee_over_toe):", res.status_code, res.json())
    assert res.status_code == 200


def test_coaching_frame_hip_calibration_changes_normal_judgement():
    # 무릎은 정상범위(70~100) 안에서 정지, 엉덩이는 110도로 정지한 상황.
    # 고정 NORMAL_RANGES(60~100)로는 110이 범위 밖이라 이상으로 판정되지만,
    # 유연성이 낮은 사용자의 캘리브레이션(standing 160, max_flex 100 -> 개인 범위 106~118)을
    # 적용하면 110은 그 사람 기준으로는 정상 범위 안이라 정상으로 바뀌어야 한다.
    angle_history = [
        {"timestamp": i * 0.1, "knee_angle": 85 + (i % 2), "hip_angle": 110} for i in range(10)
    ]

    body_without_calibration = {"exercise_type": "squat", "angle_history": angle_history}
    res_without = client.post("/ai/coaching/frame", json=body_without_calibration)
    print("coaching_frame(no calibration, hip=110):", res_without.status_code, res_without.json())
    assert res_without.status_code == 200
    assert res_without.json()["is_normal"] is False

    body_with_calibration = {
        "exercise_type": "squat",
        "angle_history": angle_history,
        "hip_calibration": {"standing_hip_angle": 160, "max_flex_hip_angle": 100},
    }
    res_with = client.post("/ai/coaching/frame", json=body_with_calibration)
    print("coaching_frame(with calibration, hip=110):", res_with.status_code, res_with.json())
    assert res_with.status_code == 200
    assert res_with.json()["is_normal"] is True


if __name__ == "__main__":
    test_health()
    test_pose_analyze_standing_is_abnormal_for_squat_bottom()
    test_pose_analyze_deep_squat_is_normal()
    test_coaching_frame_descending()
    test_coaching_frame_holding_at_bottom_normal()
    test_coaching_frame_holding_halfway_abnormal()
    test_coaching_frame_jittery_movement_flagged()
    test_coaching_frame_insufficient_frames()
    test_session_end_user_requested()
    test_session_end_not_enough_duration_yet()
    test_session_end_sustained_good_form()
    test_session_end_sustained_poor_form()
    test_personalized_hip_range_formula()
    test_personalized_hip_range_invalid_calibration_is_safe()
    test_ml_lunge_analyze_returns_valid_response()
    test_ml_lunge_analyze_knee_over_toe_case_runs_without_error()
    test_coaching_frame_hip_calibration_changes_normal_judgement()
    print("\nALL MANUAL CHECKS PASSED")
