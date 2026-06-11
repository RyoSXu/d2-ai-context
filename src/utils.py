from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def signed_hash(value: int | str) -> int:
    raw = int(value)
    if raw > 0x7FFFFFFF:
        return raw - 0x100000000
    return raw


def unsigned_hash(value: int | str) -> int:
    raw = int(value)
    if raw < 0:
        return raw + 0x100000000
    return raw


def get_path(data: dict[str, Any], *keys: str, default: Any = None) -> Any:
    cur: Any = data
    for key in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(key)
    return default if cur is None else cur


def display_name(definition: dict[str, Any] | None, fallback: str = "") -> str:
    if not definition:
        return fallback
    return definition.get("displayProperties", {}).get("name") or fallback


def warn(warnings: list[str], message: str) -> None:
    warnings.append(message)

