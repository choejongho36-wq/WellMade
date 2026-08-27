"""
DTW(동적 시간 워핑) 기반 정상 궤적 유사도 매칭.

배경(설계 확정 근거는 claude/wellmade-squat-criteria-checklist.md "척추/허리" 섹션 v3와
claude/wellmade-squat-criteria-checklist-2026-08-27-addendum.md 참고):
- 허리 과신전/등 굽음은 사진(정지 프레임) 판정이 원리적으로 불가능하다 — DTW는 시간축을
  늘렸다 줄였다 하며 두 곡선을 맞추는 방법이라 애초에 시계열이 있어야 성립한다.
- 실시간 영상 경로에서는 "정상 스쿼트 궤적과의 패턴 유사도"로 1차 판정하고, 애매한
  구간만 LLM에 재확인시키는 하이브리드로 전환한다.
- DTW 라이브러리는 dtaidistance(정식 DTW, C 구현)로 확정했다 — fastdtw(근사)는 애매한
  구간을 늘려 LLM 호출(실질 비용)을 오히려 키울 수 있어 제외, scipy 직접구현은 정확하지만
  구현/테스트 부담 때문에 제외.
- "서버는 복잡한 계산을 하는 곳이 아니다" 원칙에 따라, mediapipe/opencv를 이용한 좌표
  추출·템플릿 생성은 로컬(오프라인 스크립트, prepare_posture_reference.py 패턴)에서만
  수행한다. 이 모듈은 이미 추출된 템플릿(숫자 배열, JSON)을 읽어 비교만 하므로 무거운
  연산이 아니다 — mediapipe/opencv를 서버 의존성에 추가하지 않는다.
- 정규화(z-score) 기준값은 쿼리마다 즉석에서 계산하지 않고, 템플릿을 만들 때 함께 저장해
  둔 고정값을 재사용한다. (이전 세션 DTW 프로토타입은 25개 렙 전체에서 한 번에 정규화
  기준을 계산해 "엄밀한 fold별 분리가 안 됨"이라는 캐비엇이 있었다 — 템플릿 쪽 기준값을
  고정해두면 쿼리 하나하나가 서로 다른 기준으로 비교되는 문제가 없다.)

아직 정하지 않은 것(이 모듈의 책임 범위 밖):
- "애매한 구간"을 정성적(육안)으로 볼지 정량적(자동 이상치 탐지)으로 볼지는 실측 곡선을
  뽑아본 뒤 정하기로 함(2026-08-27 addendum) — 이 모듈은 거리값 계산·최근접 템플릿 조회까지만
  제공하고, "몇 도 이상이면 이상치"같은 임곗값 판단은 포함하지 않는다.
- 신고 데이터 저장 스키마, 템플릿 승인 워크플로우는 별도 설계 대상.
- 실제 템플릿 데이터(dtw_templates/*.json)는 2026-08-27 생성 완료 — 측면 촬영 영상 4개
  (우혁_정상/정상2, 주영_정상, 형준_정상, 로우바·정면 촬영본 제외)에서 렙 12개 +
  Dataset/train/Good/*.jpg 8구간, 총 템플릿 20개. 만든 방법은
  ml_training/build_dtw_templates.py, 소스/제외 이유는 app/pose/dtw_templates/README.md
  참고.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

# 시상면(옆에서 본) 궤적 판정에 쓰는 기본 지표 4개. AngleFrame(app/schemas.py)의 필드 중,
# "허리 과신전/등 굽음" v3 판정 목표와 직접 관련되면서 실제로 확보한 템플릿 데이터로
# 계산 가능한 것만 추렸다:
#   - knee_angle, hip_angle: 스쿼트 깊이 궤적 자체 — DTW가 시간축을 맞출 때 기준이 되는
#     동작의 "모양"을 잡아준다.
#   - torso_length_ratio: 등 굽음 지표(get_torso_length_ratio, rules.py BACK_ROUNDING_RATIO_THRESHOLD와
#     같은 원시값).
#   - shoulder_forward_lean_deg: 목/시선이되, 상체 정렬과 연동되는 시상면 신호라 포함.
# knee_valgus_ratio(현재 고관절 과신전 의심 판정이 재해석해 쓰는 정면 지표)는 원래
# 후보였으나 뺐다 — 실제 확보된 "정상" 템플릿 소스 중 정면 촬영은 1개뿐이라(체크리스트의
# "측면 3+정면 2"라는 서술은 실제 파일과 안 맞음, 실제로는 측면 4+정면 1) 정면 지표로
# 의미 있는 템플릿을 만들 수 없었다 — 자세한 내용은 ml_training/build_dtw_templates.py
# 참고. 정면 데이터가 더 모이면 별도 템플릿 세트로 다뤄야 한다.
# knee_asymmetry_deg/knee_over_toe_ratio/heel_lift_ratio는 무릎모임·좌우비대칭·체중이동
# 판정에 쓰이는 별개 지표라 이 목적(허리/등)에서는 기본값에서 제외했다 — 필요하면 호출
# 쪽에서 metric_fields를 직접 지정해 바꿀 수 있다.
DEFAULT_METRIC_FIELDS: tuple[str, ...] = (
    "knee_angle",
    "hip_angle",
    "torso_length_ratio",
    "shoulder_forward_lean_deg",
)


class TemplateNotFoundError(RuntimeError):
    """템플릿이 하나도 없을 때 — 조용히 빈 결과를 주지 않고 명시적으로 알린다(back_rounded
    캘리브레이션 누락 안내와 같은 원칙: BACK_ROUNDED_CALIBRATION_MISSING_MESSAGE 참고)."""


@dataclass
class MetricNormalization:
    """지표별 z-score 정규화 기준값(평균/표준편차). 템플릿을 만들 때 한 번 계산해 템플릿과
    함께 저장하고, 이후 모든 쿼리 정규화에 동일하게 재사용한다."""

    means: dict[str, float]
    stds: dict[str, float]

    def to_dict(self) -> dict[str, dict[str, float]]:
        return {k: {"mean": self.means[k], "std": self.stds[k]} for k in self.means}

    @classmethod
    def from_dict(cls, data: Mapping[str, Mapping[str, float]]) -> "MetricNormalization":
        return cls(
            means={k: float(v["mean"]) for k, v in data.items()},
            stds={k: float(v["std"]) for k, v in data.items()},
        )


@dataclass
class DTWTemplate:
    """정규화까지 끝난 템플릿 궤적 1개. `curve`는 이미 z-score 정규화된 (T, F) 배열이라
    dtw_distance()에 바로 넣을 수 있다."""

    label: str
    source: str
    metric_fields: tuple[str, ...]
    normalization: MetricNormalization
    curve: np.ndarray = field(repr=False)


def extract_metric_matrix(
    frames: Sequence[Any], metric_fields: Sequence[str] = DEFAULT_METRIC_FIELDS
) -> np.ndarray:
    """AngleFrame(또는 동일한 필드를 가진 dict) 시퀀스에서 지정한 지표들만 뽑아
    (T, F) 배열로 만든다. AngleFrame의 대부분 지표는 Optional이라(하위 호환 필드), 요청한
    지표 중 하나라도 None인 프레임이 있으면 어느 지표가 몇 번째 프레임에서 비었는지까지
    포함한 에러를 던진다 — 조용히 그 프레임만 건너뛰면 DTW 시간축이 원본과 어긋나 버린다.
    """
    if len(frames) == 0:
        raise ValueError("frames가 비어 있습니다 — 최소 1프레임 이상 필요합니다.")

    rows: list[list[float]] = []
    for i, frame in enumerate(frames):
        row: list[float] = []
        for name in metric_fields:
            value = frame.get(name) if isinstance(frame, Mapping) else getattr(frame, name, None)
            if value is None:
                raise ValueError(
                    f"{i}번째 프레임에 '{name}' 지표가 없습니다(None) — DTW 매칭에는 "
                    f"metric_fields로 지정한 지표가 전체 구간에 걸쳐 있어야 합니다."
                )
            row.append(float(value))
        rows.append(row)
    return np.asarray(rows, dtype=float)


def compute_normalization(
    matrix: np.ndarray, metric_fields: Sequence[str] = DEFAULT_METRIC_FIELDS
) -> MetricNormalization:
    """행렬 전체(여러 템플릿 원본을 이어붙인 것)에서 지표별 평균/표준편차를 계산한다.
    표준편차가 0에 가까우면(지표가 거의 안 변하는 경우) 나누기 0을 피하기 위해 1.0으로
    대체한다 — 이 경우 해당 지표는 정규화 후에도 그대로 "평균과의 차이"만 남는다."""
    means = matrix.mean(axis=0)
    stds = matrix.std(axis=0)
    stds_safe = np.where(stds < 1e-8, 1.0, stds)
    return MetricNormalization(
        means=dict(zip(metric_fields, means.tolist())),
        stds=dict(zip(metric_fields, stds_safe.tolist())),
    )


def normalize_matrix(
    matrix: np.ndarray,
    metric_fields: Sequence[str],
    normalization: MetricNormalization,
) -> np.ndarray:
    """저장된 정규화 기준값으로 (T, F) 행렬을 z-score 정규화한다."""
    means = np.array([normalization.means[f] for f in metric_fields])
    stds = np.array([normalization.stds[f] for f in metric_fields])
    return (matrix - means) / stds


def dtw_distance(a: np.ndarray, b: np.ndarray) -> float:
    """두 다변량 시계열(T1, F)/(T2, F) 사이의 DTW 거리. dtaidistance(dtw_ndim)를 그대로
    쓴다 — 직접 구현하지 않는 이유는 위 모듈 docstring 참고."""
    try:
        from dtaidistance import dtw_ndim
    except ImportError as e:  # pragma: no cover - 의존성 누락은 배포 문제이지 로직 문제가 아님
        raise ImportError(
            "dtaidistance가 설치돼 있지 않습니다. ai/requirements.txt의 dtaidistance 항목을 "
            "설치했는지 확인해주세요(pip install -r ai/requirements.txt)."
        ) from e
    return float(dtw_ndim.distance(np.ascontiguousarray(a), np.ascontiguousarray(b)))


def build_template(
    label: str,
    source: str,
    frames: Sequence[Any],
    normalization: MetricNormalization,
    metric_fields: Sequence[str] = DEFAULT_METRIC_FIELDS,
) -> DTWTemplate:
    """프레임 시퀀스 하나(예: 렙 1개, 또는 이어붙인 연속 구간)를 템플릿으로 변환한다.
    normalization은 이 템플릿 하나만 보고 계산하지 않는다 — 템플릿 전체(여러 소스 영상/구간)를
    합친 뒤 compute_normalization()으로 한 번 계산한 값을 모든 템플릿에 동일하게 넘겨야
    한다(그래야 템플릿끼리도, 템플릿과 쿼리 사이도 같은 기준으로 비교된다)."""
    matrix = extract_metric_matrix(frames, metric_fields)
    normalized = normalize_matrix(matrix, metric_fields, normalization)
    return DTWTemplate(
        label=label,
        source=source,
        metric_fields=tuple(metric_fields),
        normalization=normalization,
        curve=normalized,
    )


def save_template(template: DTWTemplate, path: Path) -> None:
    """템플릿 1개를 JSON으로 저장한다. 로컬 오프라인 추출 스크립트(prepare_posture_reference.py
    패턴)가 mediapipe로 좌표를 뽑아 build_template()으로 만든 뒤 이 함수로 저장 →
    dtw_templates/ 디렉토리에 커밋하는 흐름을 상정한다."""
    payload = {
        "label": template.label,
        "source": template.source,
        "metric_fields": list(template.metric_fields),
        "normalization": template.normalization.to_dict(),
        "curve": template.curve.tolist(),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_template(path: Path) -> DTWTemplate:
    """템플릿 1개를 JSON에서 읽는다. 필수 키가 빠져 있으면 어느 파일이 문제인지 알 수
    있도록 파일명을 포함한 에러를 던진다(여러 템플릿 중 하나가 깨져 있을 때 어디를
    고쳐야 할지 바로 알 수 있게)."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return DTWTemplate(
            label=data["label"],
            source=data["source"],
            metric_fields=tuple(data["metric_fields"]),
            normalization=MetricNormalization.from_dict(data["normalization"]),
            curve=np.asarray(data["curve"], dtype=float),
        )
    except (KeyError, json.JSONDecodeError, TypeError) as e:
        raise ValueError(f"템플릿 파일 형식이 올바르지 않습니다: {path}") from e


def load_templates(directory: Path) -> list[DTWTemplate]:
    """디렉토리 안의 *.json 템플릿을 전부 읽는다. 템플릿이 아직 없으면(디렉토리가 비어
    있으면) 빈 리스트를 반환한다 — "템플릿이 없다"는 상태 자체는 정상적인 개발 중 상태라,
    여기서는 에러를 던지지 않는다(실제로 매칭을 시도할 때 TemplateNotFoundError로 알린다)."""
    if not directory.exists():
        return []
    return [load_template(p) for p in sorted(directory.glob("*.json"))]


@dataclass
class NearestMatch:
    label: str
    distance: float


def nearest_normal_distance(
    frames: Sequence[Any],
    templates: Sequence[DTWTemplate],
    metric_fields: Sequence[str] | None = None,
) -> tuple[NearestMatch, list[NearestMatch]]:
    """쿼리 구간(렙 1개 등)을 템플릿 전체와 비교해, 가장 가까운 템플릿과 거리·전체
    거리 목록(오름차순)을 반환한다.

    "이 거리가 크면 이상이다"라는 임곗값 판단은 이 함수의 책임이 아니다 — 애매한 구간을
    정성/정량 중 어느 방식으로 가릴지가 아직 미정(2026-08-27 addendum 2번)이라, 판단은
    호출하는 쪽(향후 realtime.py의 판정 로직)에서 이 거리값들을 보고 하도록 남겨둔다.
    """
    if not templates:
        raise TemplateNotFoundError(
            "템플릿이 하나도 로드되지 않았습니다 — app/pose/dtw_templates/에 템플릿 JSON을 "
            "추가한 뒤 다시 시도해주세요(로컬 오프라인 스크립트로 생성, 체크리스트 문서 참고)."
        )

    fields = tuple(metric_fields) if metric_fields is not None else templates[0].metric_fields
    for t in templates:
        if t.metric_fields != fields:
            raise ValueError(
                f"템플릿 '{t.source}'의 metric_fields({t.metric_fields})가 나머지 템플릿과 "
                f"다릅니다({fields}) — 같은 지표 집합으로 만든 템플릿끼리만 비교할 수 있습니다."
            )

    # 쿼리는 첫 템플릿의 정규화 기준값을 그대로 쓴다 — 모든 템플릿이 같은 정규화 기준으로
    # 만들어졌다는 전제이므로(compute_normalization을 템플릿 전체에 대해 한 번만 호출하는
    # 사용법을 따른다면 항상 성립한다) 어떤 템플릿의 것을 골라도 동일하다.
    matrix = extract_metric_matrix(frames, fields)
    normalized_query = normalize_matrix(matrix, fields, templates[0].normalization)

    matches = [
        NearestMatch(label=t.label, distance=dtw_distance(normalized_query, t.curve))
        for t in templates
    ]
    matches.sort(key=lambda m: m.distance)
    return matches[0], matches
