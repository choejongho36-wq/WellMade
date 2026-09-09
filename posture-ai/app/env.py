"""
.env 파일에서 환경변수를 읽어들이는 헬퍼.

API 키를 코드에 직접 적으면 그대로 git에 올라간다. 그렇다고 매번
`export ANTHROPIC_API_KEY=...`를 치는 것도 잊기 쉬워서, 로컬 개발에서는
.env 파일을 쓰는 쪽이 현실적이다.

라이브러리 모듈(comment.py)이 아니라 진입점(api_mvp2, main_mvp2, scripts)에서만
호출한다 — import만 했는데 환경변수가 몰래 바뀌는 것은 추적하기 어려운
부작용이고, 테스트에서 환경을 통제하기도 어려워지기 때문이다.

python-dotenv가 없어도 동작한다. 없으면 조용히 건너뛰고, 셸에서 export한
환경변수를 그대로 쓴다.
"""

from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = PROJECT_ROOT / ".env"


def load_env(path: Path | None = None) -> bool:
    """
    .env 파일을 읽어 환경변수에 반영한다.

    이미 셸에 설정된 값은 덮어쓰지 않는다(override=False). CI나 운영
    환경에서 주입한 값을 로컬 .env가 조용히 가로채면 사고가 난다.

    Returns:
        실제로 파일을 읽었으면 True.
    """
    env_path = path or ENV_PATH
    if not env_path.exists():
        return False

    try:
        from dotenv import load_dotenv  # noqa: PLC0415 - 선택적 의존성
    except ImportError:
        return _load_env_minimal(env_path)

    load_dotenv(env_path, override=False)
    return True


def _load_env_minimal(env_path: Path) -> bool:
    """
    python-dotenv 미설치 환경용 최소 파서.

    KEY=VALUE 한 줄 형식과 # 주석만 지원한다. 따옴표, 여러 줄 값, 변수
    치환 같은 것은 처리하지 않는다 — 그런 게 필요해지면 python-dotenv를
    설치하는 것이 맞다.
    """
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value
    return True
