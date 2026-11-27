"""Atomic writer for derived/<family>.json (spec 7.6)."""
from __future__ import annotations

import json
import os
from pathlib import Path


def _is_pair_list(value) -> bool:
    return (isinstance(value, list) and bool(value)
            and all(isinstance(p, list) and p and all(isinstance(n, (int, float)) and not isinstance(n, bool) for n in p)
                    for p in value))


def dumps(value, level: int = 0) -> str:
    """`json.dumps(value, indent=2)`, except that a list of number lists (commit_flow's `[day, lines]` pairs) puts
    one pair on each line, so a year of commits stays small."""
    pad, inner = "  " * level, "  " * (level + 1)
    if _is_pair_list(value):
        return "[\n" + ",\n".join(inner + json.dumps(p) for p in value) + "\n" + pad + "]"
    if isinstance(value, dict) and value:
        items = [f"{inner}{json.dumps(k)}: {dumps(v, level + 1)}" for k, v in value.items()]
        return "{\n" + ",\n".join(items) + "\n" + pad + "}"
    if isinstance(value, list) and value:
        return "[\n" + ",\n".join(inner + dumps(v, level + 1) for v in value) + "\n" + pad + "]"
    return json.dumps(value)


def write_json(path, payload) -> Path:
    """Write via a temporary file and os.replace, so readers never see half a file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_text(dumps(payload) + "\n", encoding="utf-8")
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return path


def write_family(data_root, name: str, period: dict, scopes: dict, extra: dict | None = None) -> Path:
    """`{"period": ..., **extra, "scopes": ...}` to derived/<name>.json."""
    return write_json(Path(data_root) / "derived" / f"{name}.json", {"period": period, **(extra or {}), "scopes": scopes})


def write_meta(data_root, meta: dict) -> Path:
    return write_json(Path(data_root) / "derived" / "meta.json", meta)
