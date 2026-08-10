"""수집 출처 추적(provenance) 공용 유틸.

모든 수집 스크립트는 이 모듈을 통해
  1) 원본 응답을 data/raw/ 에 그대로 보존하고
  2) data/provenance.json 에 수집 이력(엔드포인트/파라미터/시각/건수)을 남긴다.

목적: 보고서에 등장하는 모든 수치를 원본 응답 파일까지 역추적 가능하게 만든다.
"""

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "data")
RAW_DIR = os.path.join(DATA_DIR, "raw")
MANIFEST_PATH = os.path.join(DATA_DIR, "provenance.json")


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _stamp() -> str:
    return datetime.now().strftime("%Y%m%dT%H%M%S")


def save_raw(source: str, payload: Any) -> str:
    """원본 응답을 가공 없이 저장하고 저장 경로(리포지토리 상대경로)를 반환."""
    os.makedirs(RAW_DIR, exist_ok=True)
    filename = f"{source}_{_stamp()}.json"
    path = os.path.join(RAW_DIR, filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return os.path.relpath(path, ROOT).replace("\\", "/")


def record(
    source: str,
    endpoint: str,
    params: Dict[str, Any],
    http_status: int,
    row_count: int,
    raw_path: Optional[str] = None,
    outputs: Optional[List[str]] = None,
    notes: str = "",
) -> Dict[str, Any]:
    """수집 이력 1건을 provenance.json 에 append 한다.

    params 에 API 키가 들어 있으면 마스킹해서 기록한다.
    """
    masked = {
        k: ("<masked>" if any(t in k.lower() for t in ("key", "token", "secret")) else v)
        for k, v in params.items()
    }
    entry = {
        "source": source,
        "endpoint": endpoint,
        "params": masked,
        "collected_at": _now(),
        "http_status": http_status,
        "row_count": row_count,
        "raw_path": raw_path,
        "outputs": outputs or [],
        "notes": notes,
    }

    history: List[Dict[str, Any]] = []
    if os.path.exists(MANIFEST_PATH):
        with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
            try:
                history = json.load(f)
            except json.JSONDecodeError:
                history = []

    history.append(entry)
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

    return entry


ENV_PATH = os.path.join(ROOT, ".env")


def load_env() -> None:
    """리포지토리 루트의 .env 를 읽어 환경변수에 채운다(외부 의존성 없음).

    이미 설정된 환경변수가 우선한다. .env 는 .gitignore 대상이라 커밋되지 않는다.
    """
    if not os.path.exists(ENV_PATH):
        return
    with open(ENV_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip("'\"")
            if key and key not in os.environ:
                os.environ[key] = value


def require_env(name: str, how_to_get: str) -> str:
    """API 키를 환경변수(또는 .env)에서 읽는다. 없으면 즉시 중단한다.

    키가 없을 때 대체 수치를 지어내지 않는 것이 이 함수의 존재 이유다.
    """
    load_env()
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(
            f"\n[중단] {name} 키를 찾을 수 없습니다."
            f"\n       발급 방법: {how_to_get}"
            f"\n       입력 위치: {ENV_PATH} 파일에 아래 한 줄 추가"
            f"\n                  {name}=발급받은키\n"
        )
    return value
