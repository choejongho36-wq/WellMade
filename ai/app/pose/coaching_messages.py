"""
규칙기반 자세 판정에서 재사용하는 한국어 코칭 문구 모음.

왜 이 문구들을 별도 파일로 분리했는가? RAG 지식베이스(app/rag/knowledge_base.py)가
"같은 이슈에 대해 모듈마다 표현이 미묘하게 달라지는 걸 막기 위해" 이 문구를 그대로
재사용하는 단일 출처 원칙을 쓰고 있어서, 규칙기반 판정(pose/rules.py, coaching/realtime.py)과
RAG 양쪽이 같은 상수를 가져다 쓰도록 이 파일에 모아뒀다.

스쿼트만 지원한다(런지 등 다른 종목 없음).

"""

SHALLOW_SQUAT_MESSAGE = "무릎을 조금 더 굽혀서 허벅지가 바닥과 평행해질 때까지 앉아주세요."

KNEE_VALGUS_MESSAGE = "무릎이 안쪽으로 모이고 있어요. 무릎이 발끝과 같은 방향을 향하도록 밀어주세요."

HEEL_LIFT_MESSAGE = "발뒤꿈치가 바닥에서 떨어지고 있어요. 체중을 발뒤꿈치 쪽에 실어주세요."


KNEE_OVER_TOE_MESSAGE = "무릎이 발끝보다 과도하게 앞으로 나갔어요. 발 전체에 체중을 유지하면서 무릎이 발끝 방향으로 자연스럽게 움직이도록 앉아주세요."

BACK_ROUNDED_MESSAGE = "등이 둥글게 말려 있어요. 허리를 곧게 펴고 가슴을 살짝 든 상태를 유지해주세요."

# 등 굽음 판정은 온보딩 캘리브레이션(HipFlexibilityCalibration.standing_shoulder_hip_ratio)
# 기준값이 있어야만 가능하다(rules.py의 BACK_ROUNDING_RATIO_THRESHOLD 주석 참고). 캘리브레이션이
# 없으면 이상 유무를 아예 알 수 없는데, 이걸 조용히 건너뛰면(경고 없이) 사용자는 "등 굽음은
# 항상 정상"으로 오해할 수 있다 — 어깨 말림까지 이 검사 하나로 흡수한 뒤로는 그 오해의
# 범위가 더 커져서, 왜 이 검사가 빠졌는지 명시적으로 알려준다.
BACK_ROUNDED_CALIBRATION_MISSING_MESSAGE = (
    "등이 굽었는지 정확히 확인하려면 온보딩에서 자세 캘리브레이션을 먼저 진행해주세요."
)

# (2026-08-27 폐기) 여기 있던 HIP_HYPEREXTENSION_MESSAGE(knee_valgus_ratio를 "고관절
# 과신전 의심"으로 재해석해 쓰던 문구)는 그 재해석 로직 자체가 근거 부족으로 폐기되며
# 함께 삭제했다 — 자세한 배경은 rules.py의 HIP_HYPEREXTENSION_VALGUS_THRESHOLD 자리에
# 남은 주석 참고.

# get_shoulder_forward_lean_deg()가 "목 기울기 − 상체 기울기"만 계산해서, 상체는 그대로인데
# 고개(귀)만 앞으로 떨어뜨려도 값이 커진다 — MediaPipe 랜드마크에 견갑골/어깨관절 회전을
# 직접 보여주는 점이 없어 "어깨가 말렸는지"를 이 값만으로는 구분할 수 없다(목이 숙여진 건지
# 어깨가 말린 건지 원리적으로 분간이 안 됨). 그래서 이 값은 이제 "어깨 말림"이 아니라
# 목/시선(고개가 앞으로 떨어졌는지) 전용 신호로만 쓴다 — 어깨 말림/등 굽음은 별도 지표
# (BACK_ROUNDED_MESSAGE, get_torso_length_ratio 기반)로 통합해서 판정한다.
GAZE_FORWARD_MESSAGE = "시선을 편안하게 정면에 두고, 목은 자연스럽게 유지해주세요."

# get_torso_shin_lean_gap_deg()가 반환하는 값(상체가 정강이보다 얼마나 더 기울었는지)이
# 임계값을 넘을 때 쓰는 문구. 원인을 "무게중심이 무너졌다"고 단정하기보다, 실제 교정
# 동작(무릎을 발끝 쪽으로 더 내밀어 정강이도 함께 기울이기)을 제안하는 톤을 유지한다 —
# 표본이 2건뿐인 잠정 신호라(rules.py의 TORSO_SHIN_LEAN_GAP_THRESHOLD_DEG 참고) 확신이
# 낮은 만큼 HIP_HYPEREXTENSION_MESSAGE와 비슷하게 조심스러운 표현을 썼다.
CENTER_OF_MASS_SHIFT_MESSAGE = (
    "무게중심이 뒤로 쏠려 있는 것처럼 보여요. "
    "무릎을 발끝 쪽으로 조금 더 내밀어서 정강이도 상체와 함께 앞으로 기울여주세요."
)


# (2026-08-27 추가) DTW 렙 패턴 유사도 판정(rules.py의 DTW_NEAREST_DISTANCE_THRESHOLD
# 참고) 임곗값을 넘었을 때 쓰는 메시지. 이 판정은 무릎/엉덩이/등/무게중심처럼 "어느
# 신체 부위가 문제인지" 특정하지 않는다 — knee_angle·hip_angle·torso_length_ratio·
# shoulder_forward_lean_deg 4개 지표를 합쳐 렙 전체의 "움직임 곡선 모양"을 정상 렙
# 20개와 통째로 비교하는 방식이라, 어느 한 부위 탓이라고 짚어 말할 근거가 없다. 그래서
# 문구도 특정 부위를 지목하지 않고 전반적인 재확인을 요청하는 톤으로 썼다. 임곗값
# 자체가 "나쁜 폼" 실측 없이 잡은 잠정치(rules.py 주석 참고)라, 다른 개별 지표
# 메시지보다 한층 더 조심스러운 표현을 썼다.
DTW_FORM_MISMATCH_MESSAGE = (
    "이번 렙의 전체적인 움직임 패턴이 정상 스쿼트와 다소 차이가 있는 것 같아요. "
    "속도를 조금 늦추고 자세를 다시 한번 확인해보세요."
)


# (2026-08-28 추가, 2026-08-28 같은 날 폐기) 정면 촬영 전용 DTW 고관절 과신전 판정에
# 쓰던 HIP_HYPEREXTENSION_FRONTAL_MESSAGE가 이 자리에 있었다 — 정면 카메라는 고관절
# 과신전(시상면 신호)을 원리적으로 촬영할 수 없다는 게 실측(영상 프레임 직접 확인)으로
# 확인됐고, 정면 지표(knee_valgus_ratio 등)가 라벨보다 촬영 인물별로 더 강하게
# 클러스터링되는 것도 함께 확인돼(checklist 2026-08-28 addendum 1번 참고) 판정 로직
# 전체(realtime.py (1.6) 블록, dtw_matching.py의 FRONTAL_METRIC_FIELDS,
# app/pose/dtw_templates_frontal/, ml_training/build_dtw_templates.py의 프론트 관련
# 함수들, 관련 테스트)와 함께 폐기했다. 대체 지표는 아직 없다 — 진짜 고관절 과신전은
# 측면 DTW+LLM 하이브리드(HIP_HYPEREXTENSION_LLM_MESSAGE, 아래 참고)로만 판정한다.


# (2026-08-28 추가) 측면 DTW+LLM 하이브리드(app/coaching/hyperextension_llm_check.py)가
# "과신전_의심"으로 판정했을 때 쓰는 문구. 이 판정은 위 정면 버전과 달리 실제 시상면
# 신호(hip_angle, torso 기울기)를 LLM이 직접 본 결과이고, 지난 세션 블라인드
# 테스트(6/6, 100%)로 검증된 경로다 — 다만 LLM 확신도가 "중"으로 나올 때도 있어(같은
# 실험 결과) 여전히 단정적이지 않은 톤을 유지한다.
HIP_HYPEREXTENSION_LLM_MESSAGE = (
    "직전 렙에서 고관절이 과도하게 젖혀지는 것처럼 보였어요. "
    "복부에 힘을 주고 골반을 중립으로 유지한 채 앉아보세요."
)
