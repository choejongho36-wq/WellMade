"""
DTW 정상 렙 템플릿(app/pose/dtw_templates/*.json) 로딩 — S3 묶음 파일 + 로컬 캐시 폴백
(2026-08-28 추가).

배경: 사용자와 논의 — 템플릿을 파일 하나씩 git에 커밋해서 쓰는 지금 구조는 (1) 신고
사례를 템플릿에 반영하는 승인 워크플로우가 "코드 커밋 + 재배포"에 묶여 있어 템플릿이
몇백 개 규모로 늘어나면 운영이 안 되고(승인할 때마다 배포 이벤트가 생김), (2) 그렇다고
저장 "용량" 자체가 문제인 건 아니다(템플릿 20개=284KB, 몇백 개도 몇 MB 수준) — 그래서
S3(오브젝트 스토리지)로 "코드"와 "데이터"를 분리하기로 했다. checklist 2026-08-27
addendum 1번("서버는 저장만, 계산은 로컬")과 같은 결의 결정이다 — 이번엔 "코드 저장소
vs 데이터 저장소" 분리.

설계 — 왜 파일 하나씩이 아니라 "묶음 파일" 하나인가: 서버가 시작할 때 템플릿을 파일
개수만큼 개별 GET으로 받아오면, 템플릿이 몇백 개가 됐을 때 네트워크 왕복이 그만큼
늘어나 시작 시간이 눈에 띄게 느려진다(사용자 지적). 그래서 템플릿 전체를 JSON 배열
하나(묶음 파일)로 만들어 S3에 올려두고, 서버는 시작할 때 딱 1번의 GET으로 전체를
받아온다 — 템플릿이 20개든 5,000개든 요청 횟수는 항상 1번이다. 묶음 파일은
ml_training/build_dtw_templates.py의 --step bundle로 로컬에서 만든 뒤, 사람이 검토·승인
후 수동으로(예: aws s3 cp) S3에 업로드한다 — 이 모듈 자체는 업로드를 하지 않는다(자격증명을
다루는 코드는 최소화한다는 원칙 — hyperextension_llm_check.py도 마찬가지로 호출만 하고
발급/관리는 다루지 않는다).

로딩 순서 — 3단계, 각 단계 실패는 조용히 다음 단계로:
  1) S3 설정(DTW_TEMPLATES_S3_BUCKET/KEY/REGION)이 전부 있으면 S3에서 묶음을 받아온다.
     성공하면 로컬 캐시 파일에도 그대로 저장해둔다(2번 폴백을 위한 안전망).
  2) S3 설정이 없거나 S3 요청이 실패했으면(권한 문제·일시 장애·버킷에 아직 아무것도
     없음 등) 로컬 캐시 파일이 있으면 그걸 쓴다 — "마지막으로 성공했던 버전"으로
     서버가 계속 뜰 수 있게 하는 안전망. 서버가 재시작을 반복해도(같은 배포 안에서는)
     캐시가 남아있는 한 매번 S3에 새로 요청할 필요는 없다는 뜻이기도 하다.
  3) 그것도 없으면(로컬 개발 환경, S3 설정 전 등) 기존 방식대로
     app/pose/dtw_templates/ 디렉토리의 개별 JSON 파일들을 그대로 읽는다 — 이 모듈이
     없던 시절과 완전히 동일하게 동작하는 하위 호환 경로. **AWS_BEDROCK_REGION이
     그렇듯, 이 환경(현재 배포 전 상태)에는 S3 관련 환경변수가 하나도 없어 이 3단계로
     항상 폴백한다.**

AWS Bedrock(hyperextension_llm_check.py)과 의도적으로 분리된 별도 환경변수를 쓴다 — S3
버킷과 Bedrock 모델은 서로 다른 AWS 리소스라 이름을 재사용하면 안 된다.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from app.pose.dtw_matching import DTWTemplate, load_templates, load_templates_from_bundle

try:
    import boto3
    from botocore.exceptions import BotoCoreError, ClientError

    _BOTO3_AVAILABLE = True
except ImportError:  # pragma: no cover - requirements.txt에 boto3가 없는 예외적인 환경 대비
    _BOTO3_AVAILABLE = False

S3_BUCKET_ENV_VAR = "DTW_TEMPLATES_S3_BUCKET"
S3_KEY_ENV_VAR = "DTW_TEMPLATES_S3_KEY"
S3_REGION_ENV_VAR = "DTW_TEMPLATES_S3_REGION"

# ai/ 기준 .cache/ 아래 — .gitignore에 추가해뒀다(비밀값은 아니지만 배포 산출물이라
# 커밋 대상이 아니다). 이 파일(dtw_template_store.py)의 위치(app/pose/) 기준 상대경로로
# 잡아, 배포 환경에서 작업 디렉토리가 달라져도 항상 같은 위치를 가리키게 한다 — realtime.py의
# DTW_TEMPLATES_DIR과 동일한 원칙.
DEFAULT_LOCAL_CACHE_PATH = (
    Path(__file__).resolve().parent.parent.parent / ".cache" / "dtw_templates_bundle.json"
)


def _fetch_bundle_from_s3(bucket: str, key: str, region: str) -> Optional[bytes]:
    """S3에서 묶음 파일을 받아온다. boto3 미설치, 권한 없음, 버킷/키 없음, 네트워크
    장애 등 어떤 이유로든 실패하면 None을 반환한다 — 위 모듈 docstring의 "각 단계 실패는
    조용히 다음 단계로" 원칙. 실패 사유를 세분화해 호출부에 알려도 realtime.py 쪽에서는
    결국 "템플릿을 못 구했다"는 동일한 취급(TemplateNotFoundError)만 하므로, 여기서
    예외를 넓게 잡는 것이 hyperextension_llm_check.py의 _run_job()과 같은 이유로
    타당하다."""
    if not _BOTO3_AVAILABLE:
        return None
    try:
        client = boto3.client("s3", region_name=region)
        response = client.get_object(Bucket=bucket, Key=key)
        return response["Body"].read()
    except (BotoCoreError, ClientError):
        # 권한 없음, 버킷/키 없음, 네트워크 장애 등 — 위 함수 docstring 참고.
        return None


def load_templates_for_store(
    local_template_dir: Path,
    cache_path: Path = DEFAULT_LOCAL_CACHE_PATH,
) -> list[DTWTemplate]:
    """모듈 docstring의 3단계 순서(S3 → 로컬 캐시 → 디렉토리)로 템플릿을 읽는다.
    realtime.py의 _get_dtw_templates()가 프로세스당 한 번만 이 함수를 호출해 결과를
    캐싱하므로, 이 함수 자체는 매 요청마다 불리지 않는다(S3 GET이 요청마다 나가지
    않는다는 뜻)."""
    bucket = os.environ.get(S3_BUCKET_ENV_VAR)
    key = os.environ.get(S3_KEY_ENV_VAR)
    region = os.environ.get(S3_REGION_ENV_VAR)

    if bucket and key and region:
        data = _fetch_bundle_from_s3(bucket, key, region)
        if data is not None:
            try:
                templates = load_templates_from_bundle(data)
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                cache_path.write_bytes(data)
                return templates
            except ValueError:
                # S3에는 접근했지만 받아온 내용이 깨져 있음(예: 잘못된 파일이 업로드됨).
                # 아래 로컬 캐시로 폴백해 최소한 지난번 성공한 버전으로는 뜨게 한다.
                pass

    if cache_path.exists():
        try:
            return load_templates_from_bundle(cache_path.read_bytes())
        except ValueError:
            # 캐시 파일 자체가 깨져 있는 극히 드문 경우 — 아래 디렉토리 폴백으로 넘어간다.
            pass

    return load_templates(local_template_dir)
