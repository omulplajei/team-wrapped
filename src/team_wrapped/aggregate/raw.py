"""Read-only loader for data/raw (spec 5.1). The aggregator never writes here."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from ..config import Config

FILES = {
    "commits": "commits.jsonl",
    "pull_requests": "pull_requests.jsonl",
    "reviews": "reviews.jsonl",
    "comments": "comments.jsonl",
}
STATUSES = ("complete", "partial", "never-run", "failed")

# Which timestamp fields count as activity inside the window (docs/datasets.md, repos).
ACTIVITY_FIELDS = {
    "commits": ("authored_at",),
    "pull_requests": ("created_at", "merged_at"),
    "reviews": ("submitted_at",),
    "comments": ("created_at",),
}


@dataclass
class RawData:
    records: dict = field(default_factory=dict)     # metric -> [record dict, `repo` always set]
    status: dict = field(default_factory=dict)      # repo -> metric -> status (enabled metrics only)
    corrupt: dict = field(default_factory=dict)     # "<repo>/<file>" -> skipped line count (non-zero only)


def _read_jsonl(path: Path, repo: str, key: str, corrupt: dict) -> list:
    records, bad = [], 0
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except ValueError:
            bad += 1
            continue
        if not isinstance(record, dict):
            bad += 1
            continue
        record["repo"] = repo
        records.append(record)
    if bad:
        corrupt[key] = bad
    return records


def _read_status(path: Path, repo: str, corrupt: dict) -> dict | None:
    """The repo's status.json as a dict, or None when the file is missing (every metric never-run)."""
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        data = None
    if not isinstance(data, dict):
        corrupt[f"{repo}/status.json"] = 1
        return None
    return data


def load_raw(data_root, config: Config) -> RawData:
    """Records for every configured repo and enabled metric, plus statuses and corrupt-line counts."""
    raw_root = Path(data_root) / "raw"
    raw = RawData(records={metric: [] for metric in config.metrics})
    for repo in config.repos:
        folder = raw_root / repo
        statuses = _read_status(folder / "status.json", repo, raw.corrupt)
        raw.status[repo] = {}
        for metric in config.metrics:
            path = folder / FILES[metric]
            present = path.is_file()
            if present:
                raw.records[metric].extend(_read_jsonl(path, repo, f"{repo}/{FILES[metric]}", raw.corrupt))
            if statuses is None:
                state = "never-run"
            elif metric in statuses:
                state = statuses[metric] if statuses[metric] in STATUSES else "failed"
            else:
                state = "complete" if present else "never-run"
            raw.status[repo][metric] = state
    return raw
