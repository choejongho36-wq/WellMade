"""
자세 비교 인사이트 (AI-15, 신규 — API 명세 표에 없는 온보딩 캘리브레이션 확장 기능).

세션 시작 시 정면 촬영으로 어깨/골반의 좌우 기울기를 재고, 세종특별자치시 공공데이터
(data.go.kr id 15128996, "세종 똑똑건강 앱" 자세 측정 내역)로 만든 성별×연령대별 참조
분포와 비교해 "비슷한 또래에서는 몇 %에 해당하는지" 백분위 인사이트를 준다.
(예: "왼쪽 어깨가 2도 올라간 상태입니다. 비슷한 연령대에서는 39%에 해당합니다.")

기존 하체 중심 기능들과의 관계:
- 기존 정지 자세 판정(pose/rules.py)·실시간 코칭(coaching/realtime.py)은 "측면 촬영
  전제"였다. 이 기능은 좌우 높이차(관상면)를 재야 해서 처음으로 "정면 촬영"이 필요한
  지점이다 — 별도 온보딩 캘리브레이션 단계로 분리했다(기존 측면 판정 로직에는 영향 없음).
- "정상/이상"을 규칙기반으로 판정하는 다른 모듈과 달리, 이 기능은 정상/비정상을
  가르지 않는다 — "얼마나 흔한 정도인지"만 알려주는 참고 정보다. 그래서 issues/is_normal
  같은 필드 대신 percentile과 설명 문구만 반환한다.
- 참조 데이터가 "이미 계산된 소견 문장"이라 실제 운동 동작(스쿼트/런지) 데이터가 아니므로,
  ml/ 아래 다른 분류기들과는 성격이 달라 별도 패키지(app/insight/)로 분리했다.
"""

import bisect
import json
from pathlib import Path
from typing import Optional

REFERENCE_PATH = Path(__file__).parent / "data" / "posture_reference.json"

# 세종시 데이터의 60대 이상 구간(연령대별 표본이 급격히 줄어듦)은 이미
# ml_training/prepare_posture_reference.py 단계에서 "60대 이상" 하나로 합쳐뒀지만,
# 그래도 남아있는 소표본 그룹(예: 10대 남성 n=41)을 호출부가 인지할 수 있도록
# 최소 신뢰 표본 크기를 정의해 응답에 경고 플래그로 실어 보낸다.
# NOTE: MVP 잠정치 — 데이터가 쌓이는 대로 사용자 신고 기반 액티브러닝으로 조정할 예정.
MIN_RELIABLE_SAMPLE = 50

BRACKET_SIZE = 10
MAX_BRACKET = 60

_reference_cache: Optional[dict] = None


def _load_reference() -> dict:
    """참조 분포 JSON을 최초 호출 시 1회만 읽어 캐싱한다 (요청마다 파일 I/O를 반복하지
    않기 위함 — ml/*_classifier.py의 지연 로딩 패턴과 동일한 이유)."""
    global _reference_cache
    if _reference_cache is None:
        with open(REFERENCE_PATH, encoding="utf-8") as f:
            _reference_cache = json.load(f)
    return _reference_cache


def _age_bracket(age: int) -> int:
    """나이를 참조 데이터와 동일한 규칙(10년 단위, 60대 이상은 통합)으로 변환한다.
    prepare_posture_reference.py의 age_bracket()과 반드시 같은 규칙을 써야 한다 —
    두 곳의 로직이 어긋나면 잘못된 그룹과 비교하게 된다."""
    bracket = (age // BRACKET_SIZE) * BRACKET_SIZE
    return min(max(bracket, 10), MAX_BRACKET)


def _percentile_rank(value_abs_deg: float, sorted_abs_list: list[float]) -> Optional[float]:
    """
    "이 값 이하인 참조 인구의 비율"을 표준적인 백분위 순위로 계산한다.
    표본이 없으면(이론상 데이터 전처리 단계에서 걸러지지만 방어적으로) None을 반환한다.
    """
    if not sorted_abs_list:
        return None
    rank = bisect.bisect_right(sorted_abs_list, value_abs_deg)
    return round(rank / len(sorted_abs_list) * 100, 1)


def _side_label(signed_deg: float) -> str:
    """부호 있는 기울기 값에서 어느 쪽이 올라갔는지를 구한다.
    0.5도 미만 차이는 측정 노이즈로 보고 '거의 수평'으로 취급한다."""
    if signed_deg >= 0.5:
        return "left"
    if signed_deg <= -0.5:
        return "right"
    return "level"


def _subject_particle(word: str) -> str:
    """한국어 주격 조사(이/가)를 마지막 글자 받침 유무로 골라준다.
    '어깨'(받침 없음) -> '가', '골반'(받침 'ㄴ') -> '이' 처럼 부위 이름에 따라 문법이
    달라지므로, 하드코딩된 조사 대신 매번 계산해서 문구가 항상 자연스럽게 나오게 한다."""
    last_char = word[-1]
    has_batchim = (ord(last_char) - 0xAC00) % 28 != 0
    return "이" if has_batchim else "가"


def _describe(part_name_kr: str, signed_deg: float, side: str, percentile: Optional[float]) -> str:
    """세종시 원본 소견 문장과 같은 어투("~도 올라간 상태입니다")로 인사이트 문구를 만든다.
    사용자가 예시로 준 형식("왼쪽 어깨가 2도 올라간 상태입니다. 비슷한 연령대에서는
    39%에 해당합니다")을 그대로 따른다."""
    particle = _subject_particle(part_name_kr)
    if side == "level":
        return f"{part_name_kr}{particle} 수평에 가깝게 잘 정렬되어 있습니다."

    side_kr = "왼쪽" if side == "left" else "오른쪽"
    base = f"{side_kr} {part_name_kr}{particle} {abs(signed_deg):.1f}도 올라간 상태입니다."
    if percentile is None:
        return base
    return f"{base} 비슷한 연령대에서는 {percentile:.0f}%에 해당합니다."


def compute_posture_insight(
    shoulder_tilt_deg: float,
    pelvis_tilt_deg: float,
    gender: str,
    age: int,
) -> dict:
    """
    정면 촬영에서 계산한 어깨/골반 기울기 각도를, 같은 성별·연령대 참조 분포와 비교해
    백분위 인사이트를 만든다.

    반환값을 dict로 두는 이유는 다른 rules/coaching 모듈과 동일 — main.py가 API 응답으로
    감싸기 전, 다른 곳(세션 리포트 등)에서도 순수 값으로 재사용 가능하게 하기 위함.
    """
    reference = _load_reference()
    bracket = _age_bracket(age)
    key = f"{gender}_{bracket}"
    group = reference.get(key)

    if group is None:
        # 이론상 gender가 "M"/"F"가 아니거나 bracket 계산이 어긋나면 발생 — 참조 데이터가
        # 아예 없는 그룹이므로 백분위 없이 측정값만 반환한다(전체 응답을 실패시키지 않음).
        sample_size = 0
        shoulder_percentile = None
        pelvis_percentile = None
    else:
        sample_size = group["sample_size"]
        shoulder_percentile = _percentile_rank(abs(shoulder_tilt_deg), group["shoulder_abs_deg_sorted"])
        pelvis_percentile = _percentile_rank(abs(pelvis_tilt_deg), group["pelvis_abs_deg_sorted"])

    shoulder_side = _side_label(shoulder_tilt_deg)
    pelvis_side = _side_label(pelvis_tilt_deg)

    shoulder_message = _describe("어깨", shoulder_tilt_deg, shoulder_side, shoulder_percentile)
    pelvis_message = _describe("골반", pelvis_tilt_deg, pelvis_side, pelvis_percentile)

    low_sample_warning = sample_size > 0 and sample_size < MIN_RELIABLE_SAMPLE
    combined_message = f"{shoulder_message} {pelvis_message}"
    if low_sample_warning:
        combined_message += " (참고: 같은 연령대의 비교 표본 수가 적어 참고용으로만 봐주세요.)"
    if sample_size == 0:
        combined_message += " (비교할 참조 데이터가 없어 측정값만 안내합니다.)"

    return {
        "age_bracket": bracket,
        "sample_size": sample_size,
        "low_sample_warning": low_sample_warning,
        "shoulder_tilt_deg": round(shoulder_tilt_deg, 1),
        "shoulder_side": shoulder_side,
        "shoulder_percentile": shoulder_percentile,
        "shoulder_message": shoulder_message,
        "pelvis_tilt_deg": round(pelvis_tilt_deg, 1),
        "pelvis_side": pelvis_side,
        "pelvis_percentile": pelvis_percentile,
        "pelvis_message": pelvis_message,
        "message": combined_message,
    }
