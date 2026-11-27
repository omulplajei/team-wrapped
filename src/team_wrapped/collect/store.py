"""Writes under data/raw/<repo>/ (spec 5.1). Every file is replaced atomically (temporary file + os.replace)."""
from __future__ import annotations

import json
import os
from pathlib import Path

from ..aggregate.io import write_json
from ..aggregate.raw import FILES, read_jsonl, record_identity

DETAIL_FILE = "status-detail.json"     # reasons and times; the aggregator ignores it


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def write_records(folder: Path, repo: str, metric: str, records: list) -> int:
    """Merge `records` into <metric>.jsonl by key (spec 5.1): a fetched record replaces the stored one with the same
    key, stored records that were not fetched again are kept, and nothing is duplicated. Records whose key fields
    are invalid are dropped. Returns the number of records in the file."""
    path = folder / FILES[metric]
    merged = {}
    if path.is_file():
        for record in read_jsonl(path, repo, metric, path.name, {}):
            merged[record_identity(metric, record)] = record
    for record in records:
        identity = record_identity(metric, record)
        if identity is not None:
            merged[identity] = record
    _write_text(path, "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in merged.values()))
    return len(merged)


def _read_dict(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def write_status(folder: Path, metric: str, status: str, detail: dict) -> None:
    """Set one metric in status.json (plain strings, as the aggregator reads them) and its detail
    (`reason`, `collected_at`, `records`, `window`) in status-detail.json. Other metrics are kept."""
    statuses = _read_dict(folder / "status.json")
    statuses[metric] = status
    write_json(folder / "status.json", statuses)
    details = _read_dict(folder / DETAIL_FILE)
    details[metric] = {"status": status, **detail}
    write_json(folder / DETAIL_FILE, details)


def read_details(folder: Path) -> dict:
    return _read_dict(folder / DETAIL_FILE)
