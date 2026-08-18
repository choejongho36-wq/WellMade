"""
정지 자세 1차 판정 로직 (AI-03).

"파인튜닝 금지, 규칙기반 우선"이라는 기술 원칙에 따라, 각도 계산 결과를
사전에 정의한 정상 범위(NORMAL_RANGES)와 비교하는 방식으로 구현했다.
딥러닝 분류기 대신 규칙기반을 택한 이유:
1) 스쿼트/런지의 "바른 자세" 각도 기준은 운동/재활 자료에 이미 잘 정리되어 있어,
   별도 라벨링 데이터 없이도 신뢰할 수 있는 규칙을 세울 수 있다.
2) 규칙기반은 판정 근거를 사람이 바로 설명할 수 있어(설명가능성), "왜 이상 자세로
   판정했는지"를 코칭 문구·RAG 검색 쿼리에 그대로 재사용하기 좋다.
"""

from app.pose.angles import get_hip_angle, get_knee_angle
from app.schemas import Landmark

# 스포츠의학/트레이너 자격 기준 자료를 근거로 한 값 (2026-08-18 업데이트).
#
# 주의: 아래 문헌들이 말하는 "무릎 굴곡각(knee flexion angle)"은 다리를 편 상태를 0도로
# 두고 "얼마나 굽혔는지"를 재는 값이라, get_knee_angle()이 계산하는 "관절 내각"(편 상태가
# 180도)과는 서로 보각(180 - 굴곡각) 관계다. 아래 범위는 전부 내각 기준으로 이미 변환해뒀다.
#
# [스쿼트]
# IJSPT(International Journal of Sports Physical Therapy)의 스쿼트 임상 리뷰 논문은
# 깊이를 얕음(굴곡 0~90도) / 평행(90~110도) / 깊음(110~135도)으로 나눈다.
# 이걸 내각으로 바꾸면 평행 스쿼트는 70~90도인데, WellMade는 "대퇴가 바닥과 평행한
# 지점까지" 내려가는 걸 목표로 잡아서(더 깊은 스쿼트는 개인 유연성 차이가 커 위험 부담이
# 있음) knee_angle 범위를 이 평행 구간에 맞췄다. 상한을 100도까지 살짝 넉넉하게 둔 건
# 판정이 너무 빡빡해서 정상 동작도 이상으로 잡아내는 것을 막기 위한 여유값이다.
# 참고: https://ijspt.scholasticahq.com/article/94600-a-biomechanical-review-of-the-squat-exercise-implications-for-clinical-practice
#
# 같은 논문은 엉덩이(고관절) 각도에 대해서는 "개인의 고관절 가동범위가 다 달라서 고정된
# 정상범위를 제시하기 어렵고, 각자의 가동범위 안에서 척추 중립만 지키면 된다"고 명시한다.
# 즉 hip_angle에 고정 숫자를 넣는 것 자체가 의학적으로 엄밀한 기준은 아니다.
# 그래서 아래 값은 "이 범위를 벗어나면 상체를 과도하게 숙이거나 너무 꼿꼿이 세운
# 상태"라는 느슨한 안전장치(sanity check)로만 쓰고, "이 범위 안 = 완벽한 자세"라고
# 해석하지 않는다.
#
# [런지]
# NASM(National Academy of Sports Medicine, 트레이너 자격 기준)은 상체를 세운 런지를
# "90/90 런지"라 부르며, 하단에서 앞다리·뒷다리 무릎이 둘 다 약 90도라고 명시한다.
# (참고로 Cleveland Clinic 자료는 뒷다리를 45도라고 설명하는데, 어느 각도 정의를 쓴
# 건지 불명확하고 트레이너 자격 기준인 NASM 쪽이 더 표준적이라 판단해 NASM 값을 채택함.)
# 참고: https://blog.nasm.org/training-benefits/lunge-effective-lower-body-training-exercise
# knee_angle 범위는 이 90도를 중심으로 실제 반복 동작에서 나올 수 있는 오차를 감안해
# 위아래로 여유를 뒀다. hip_angle은 "상체를 세운(upright) 런지" 전제와 일치해 기존 값을
# 유지한다.
#
# TODO: 팀 확정 필요 — 스쿼트를 "평행" 대신 "깊은 스쿼트"까지 목표로 할지, 런지의
# 뒷다리 각도를 별도로 판정에 반영할지는 제품 방향에 따라 달라지므로 재검토 필요.
NORMAL_RANGES = {
    "squat": {
        "knee_angle": (70, 100),  # 평행 스쿼트(굴곡 90~110도) 기준, IJSPT 논문 근거
        "hip_angle": (60, 100),  # 고정 정상범위 아님 — 과도한 상체 숙임/직립 감지용 여유값
    },
    "lunge": {
        "knee_angle": (75, 105),  # NASM "90/90 런지" 기준, 90도 중심으로 여유를 둠
        "hip_angle": (140, 180),  # 런지는 상체를 세운 상태(upright) 유지가 기준
    },
}

# 정상범위를 살짝 벗어나도 confidence가 완만하게 낮아지도록, "이만큼 벗어나면 신뢰도 0"으로
# 보는 여유 각도(도). 값이 클수록 관대하게(천천히) 신뢰도가 떨어진다.
# TODO: 팀 확정 필요 — 사용자 테스트 후 조정.
CONFIDENCE_TOLERANCE_DEG = 20


def _range_confidence(value: float, low: float, high: float) -> float:
    """
    값이 [low, high] 범위 안이면 1.0에 가깝게, 범위를 벗어날수록 0.0에 가깝게
    선형으로 신뢰도를 계산한다.

    왜 이진(정상/이상) 판정 말고 신뢰도까지 계산하는가?
    - 하네스(AI-07)가 "confidence < 0.7이면 재분석 도구 호출"처럼 신뢰도를 기준으로
      다음 행동을 스스로 결정해야 하므로, True/False만으로는 정보가 부족하다.
    """
    if low <= value <= high:
        # 범위 중앙에 가까울수록 1.0, 경계에 가까울수록 0.8까지 완만하게 낮춘다
        # (경계값도 "정상"이므로 confidence가 너무 낮아지지 않도록 하한을 둠).
        mid = (low + high) / 2
        half_width = (high - low) / 2 or 1
        distance_ratio = abs(value - mid) / half_width
        return max(0.8, 1.0 - 0.2 * distance_ratio)

    # 범위를 벗어난 정도에 비례해 신뢰도를 낮추고, CONFIDENCE_TOLERANCE_DEG 이상 벗어나면 0으로 수렴.
    over = (low - value) if value < low else (value - high)
    return max(0.0, 1.0 - over / CONFIDENCE_TOLERANCE_DEG)


def judge_static_pose(landmarks: list[Landmark], exercise_type: str, side: str = "auto") -> dict:
    """
    정지 자세 1장을 규칙기반으로 판정한다.

    반환값을 Pydantic 모델이 아닌 dict로 두는 이유: main.py가 API 응답으로 감싸기 전에,
    하네스(AI-07)나 세션 리포트(AI-12) 같은 다른 모듈에서도 가볍게 재사용할 수 있도록
    순수 값 형태를 유지하기 위함 (불필요하게 스키마 모듈에 의존하지 않게 함).
    """
    ranges = NORMAL_RANGES.get(exercise_type)
    if ranges is None:
        raise ValueError(f"지원하지 않는 운동 종목: {exercise_type}")

    knee_angle = get_knee_angle(landmarks, side)
    hip_angle = get_hip_angle(landmarks, side)

    knee_low, knee_high = ranges["knee_angle"]
    hip_low, hip_high = ranges["hip_angle"]

    issues = []
    if not (knee_low <= knee_angle <= knee_high):
        issues.append(
            {
                "part": "knee",
                "message": f"무릎 각도가 {knee_angle:.1f}도로 정상 범위({knee_low}~{knee_high}도)를 벗어났습니다.",
            }
        )
    if not (hip_low <= hip_angle <= hip_high):
        issues.append(
            {
                "part": "hip",
                "message": f"엉덩이(고관절) 각도가 {hip_angle:.1f}도로 정상 범위({hip_low}~{hip_high}도)를 벗어났습니다.",
            }
        )

    knee_conf = _range_confidence(knee_angle, knee_low, knee_high)
    hip_conf = _range_confidence(hip_angle, hip_low, hip_high)
    # 두 관절 중 더 낮은 신뢰도를 최종 신뢰도로 사용한다 (가장 취약한 부위가 전체 판정을 좌우하게 함).
    confidence = min(knee_conf, hip_conf)

    return {
        "is_normal": len(issues) == 0,
        "confidence": round(confidence, 2),
        "issues": issues,
    }
