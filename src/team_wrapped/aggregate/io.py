"""Atomic writer for derived/<family>.json (spec 7.6)."""
from __future__ import annotations

import json
import os
from pathlib import Path


def write_json(path, payload) -> Path:
    """Write via a temporary file and os.replace, so readers never see half a file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
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
