"""
빠른 수동 검증용 스크립트 (정식 테스트 스위트 아님, 임시 확인용).
- 정지 자세 판정(/ai/pose/analyze)과 실시간 코칭 판정(/ai/coaching/frame)이
  기대한 방향으로 동작하는지 TestClient로 확인한다.
"""

from fastapi.testclient import TestClient

from app.main import app

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
    print("\nALL MANUAL CHECKS PASSED")
