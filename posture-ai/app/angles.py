"""
각도 계산 Tool 모음 (요구사항정의서 5장 Tool 명세 대응).

설계 원칙(프로젝트 종합정리 1.2): "판단은 LLM, 계산은 코드".
이 모듈의 모든 함수는 순수 함수(pure function)다 — 같은 입력에는
항상 같은 출력을 반환하며(NFR-06 재현성), LLM이나 랜덤 요소가 전혀
개입하지 않는다(NFR-03 안전성).

좌표계: MediaPipe 정규화 좌표 기준 x는 오른쪽으로, y는 "아래로" 증가한다.
"""

from __future__ import annotations

import math

XY = tuple[float, float]


def _tilt_angle_deg(left_xy: XY, right_xy: XY) -> float:
    """
    좌우 한 쌍의 좌표를 잇는 선분이 수평선과 이루는 각도(도)를 반환한다.
    0도 = 완전히 수평(좌우 높이 동일). 부호 규약은 아래 주석 참고.
    """
    dx = right_xy[0] - left_xy[0]
    dy = right_xy[1] - left_xy[1]
    # atan2(dy, |dx|)를 쓴다 — dx 부호와 무관하게 결과가 항상 -90~90도
    # 범위에 들어오고, 부호가 dy와 정확히 일치한다.
    #
    # 예전엔 atan2(dy, dx) 그대로 쓰고 ±180 근처를 -90~90으로 접어
    # 넣는(wrap) 방식이었는데, 이게 구조적으로 틀렸다. MediaPipe는
    # 좌/우를 피사체 본인 기준으로 명명해서, 카메라를 정면으로 마주본
    # 일반적인 사진에서는 dx(=right.x - left.x)가 "항상" 음수다(피사체의
    # 오른쪽이 화면에서는 왼쪽에 찍히므로). dx가 음수일 때 atan2는 2/3
    # 사분면에 값을 주는데, 거기서 180을 더하거나 빼서 접어 넣으면
    # dy의 부호와 최종 결과의 부호가 반대로 뒤집힌다 — 즉 "일반적인
    # 정면 사진 전체"에서 왼쪽/오른쪽 판정이 계속 반대로 나오고 있었다
    # (실측 검증 중 발견: sample27.jpg는 실제로 오른쪽 어깨가 더
    # 낮은데(right_shoulder.y > left_shoulder.y), 코드는 "왼쪽이
    # 낮다"고 판정했다). 기존 회귀 테스트가 이걸 못 잡은 이유는, 부호를
    # 검증하는 테스트는 비현실적인 좌표(dx 양수)를 썼고, 현실적인
    # 좌표(dx 음수)를 쓴 테스트는 크기(abs(angle)<10)만 확인하고 부호는
    # 확인 안 했기 때문이다.
    angle_rad = math.atan2(dy, abs(dx))
    return math.degrees(angle_rad)
# 부호 규약(y가 아래로 증가하는 이미지 좌표계 기준, 항상 -90~90도):
#   양수 -> 오른쪽이 더 아래로 처짐 (오른쪽 어깨/골반이 낮음)
#   음수 -> 왼쪽이 더 아래로 처짐 (왼쪽 어깨/골반이 낮음)
#   0    -> 완전 수평
#   MediaPipe가 좌/우를 화면 기준이 아닌 피사체 본인 기준으로 명명하므로,
#   dx의 부호와 무관하게(abs 처리) dy의 부호만으로 판정한다.


def calculate_shoulder_tilt(left_shoulder_xy: XY, right_shoulder_xy: XY) -> float:
    """
    정면 기준 어깨 좌우 비대칭 각도 계산 (Tool: calculate_shoulder_tilt).

    Args:
        left_shoulder_xy: (x, y) 왼쪽 어깨 좌표
        right_shoulder_xy: (x, y) 오른쪽 어깨 좌표

    Returns:
        angle_deg: 수평 대비 기울어진 각도(도). 절대값이 클수록 비대칭이 큼.
    """
    return round(_tilt_angle_deg(left_shoulder_xy, right_shoulder_xy), 2)


def calculate_pelvis_tilt(left_hip_xy: XY, right_hip_xy: XY) -> float:
    """정면 기준 골반 좌우 비대칭 각도 계산 (Tool: calculate_pelvis_tilt)."""
    return round(_tilt_angle_deg(left_hip_xy, right_hip_xy), 2)


def calculate_forward_head(ear_xy: XY, shoulder_xy: XY) -> float:
    """
    측면 기준 전방머리자세(CVA 대체 지표) 각도 계산 (Tool: calculate_forward_head).

    귀-어깨를 잇는 선이 수직선(vertical)과 이루는 각도를 반환한다.
    0도에 가까울수록 귀가 어깨 바로 위(중립), 값이 클수록 귀가 어깨보다
    앞으로(전방으로) 나가 있음을 의미한다. 요구사항정의서 6장에 따라 이
    값은 절대 진단 기준이 아닌 참고용 정성 평가에만 사용한다.

    Args:
        ear_xy: (x, y) 귀 좌표
        shoulder_xy: (x, y) 어깨 좌표
    """
    dx = ear_xy[0] - shoulder_xy[0]
    dy = ear_xy[1] - shoulder_xy[1]  # 위로 갈수록 y는 작아짐 (음수)
    angle_rad = math.atan2(dx, -dy)  # 수직 기준(위쪽=0도)으로 측정
    return round(math.degrees(angle_rad), 2)


# --- C7(경추 7번) 근사 -------------------------------------------------------
# BlazePose 33개 랜드마크에 C7이 없다 (MVP3_설계결정.md Q3). 임상 논문은
# 신체에 물리 마커를 붙여 C7 극돌기를 직접 촬영하므로 좌표 근사 공식이
# 애초에 필요 없고, MediaPipe 기반 실무 프로젝트들도 C7을 근사하기보다
# 우회하는 쪽이 일반적이었다 — 즉 이 근사식은 확립된 표준이 아니라
# 이 프로젝트가 직접 정한 잠정값이다. 실사진으로 검증 전까지 TODO로 남긴다.
#
# 채택한 근사: 골반->어깨(트렁크) 방향을 어깨 위로 그대로 연장한 지점을
# C7으로 본다. 몸통이 곧게 펴져 있을 때는 합리적이지만, 숙인 자세일수록
# 오차가 커진다는 한계가 있다 (해당 자세를 측정하려는 지표 자체와 상충).
# 그래서 round_shoulder 판정은 정량 수치보다 정성 경향을 우선한다
# (thresholds.classify_round_shoulder의 note 참고).
NECK_RATIO = 0.15  # TODO(MVP3-실측): 실사진 10장 이상으로 육안 대조 후 보정


def approximate_c7(shoulder_xy: XY, hip_xy: XY, neck_ratio: float = NECK_RATIO) -> XY:
    """
    C7(경추 7번) 좌표를 골반-어깨 연장선으로 근사한다.

    Args:
        shoulder_xy: (x, y) 근접 측 어깨 좌표
        hip_xy: (x, y) 근접 측 골반 좌표
        neck_ratio: 트렁크(골반-어깨) 길이 대비 목 길이 비율. 기본값은
            일반적인 인체 비례(목 길이 ≈ 몸통 길이의 12~18%)를 참고한 잠정치.

    Returns:
        (x, y) C7 근사 좌표. 골반-어깨 길이가 0에 가까우면(좌표 오검출)
        어깨 좌표를 그대로 반환한다.
    """
    dx = shoulder_xy[0] - hip_xy[0]
    dy = shoulder_xy[1] - hip_xy[1]
    trunk_len = math.hypot(dx, dy)
    if trunk_len < 1e-9:
        return shoulder_xy

    neck_len = neck_ratio * trunk_len
    ux, uy = dx / trunk_len, dy / trunk_len
    return (shoulder_xy[0] + neck_len * ux, shoulder_xy[1] + neck_len * uy)


def calculate_shoulder_angle(shoulder_xy: XY, c7_xy: XY) -> float:
    """
    측면 기준 라운드숄더(어깨 전방 돌출) 각도 계산 (Tool: calculate_shoulder_angle).

    견봉(어깨)-C7(경추 7번)을 잇는 선이 수직선과 이루는 예각을 90도에서
    뺀 값을 반환한다(=수평 기준 각도, 항상 0~90도 범위). 요구사항정의서
    6장 기준: 52도 이하이면 라운드숄더 경향으로 참고.

    이 방향-무관(direction-invariant) 계산이 필요한 이유: 단순
    atan2(-dy, dx)는 촬영 방향(좌/우 프로필)에 따라 부호가 뒤집힌다.
    실측 검증(sample42.jpg, MVP3) 중 발견 — 거의 안 말린 정상 자세인데
    촬영 방향 때문에 음수(-99.83도)로 나와 classify_round_shoulder가
    "주의"로 오판하는 사례가 있었다. abs()로 촬영 방향 의존성을 없애면
    같은 좌표가 77.77도(정상)로 정확히 계산된다. (round_shoulder_ml
    실험에서 먼저 발견하고 고친 것을 여기 프로덕션 코드에도 반영함.)

    Args:
        shoulder_xy: (x, y) 견봉(어깨) 좌표. pixel_xy()로 종횡비 보정된
            값을 넣을 것 — 정규화 좌표를 그대로 넣으면 정사각형이 아닌
            사진에서 각도가 왜곡된다.
        c7_xy: (x, y) C7 좌표 (측면 사진에서는 목 뒤쪽 기준점으로 근사)
    """
    dx = abs(shoulder_xy[0] - c7_xy[0])
    dy = abs(shoulder_xy[1] - c7_xy[1])
    angle_from_vertical = math.degrees(math.atan2(dx, dy))
    return round(90.0 - angle_from_vertical, 2)
