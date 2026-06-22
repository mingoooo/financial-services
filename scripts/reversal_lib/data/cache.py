from __future__ import annotations

import json
import time
from pathlib import Path

CACHE_DIR = Path('.cache/bullish-reversal-scanner')
NO_CACHE = False


def cache_path(kind: str, key: str) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / f"{kind}_{key.replace('/', '_')}.json"


def load_cache(kind: str, key: str, max_age_seconds: int):
    if NO_CACHE:
        return None
    path = cache_path(kind, key)
    if not path.exists():
        return None
    if time.time() - path.stat().st_mtime > max_age_seconds:
        return None
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return None


def save_cache(kind: str, key: str, payload) -> None:
    if NO_CACHE:
        return
    cache_path(kind, key).write_text(json.dumps(payload), encoding='utf-8')
