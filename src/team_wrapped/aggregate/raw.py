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


def _whole(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _scalar(value) -> bool:
    return _whole(value) or isinstance(value, str)


def _optional_scalar(value) -> bool:
    return value is None or _scalar(value)


def _text(value) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def clean_co_authors(value) -> list:
    """A commit's `co_authors` made safe: anything but a list is an empty list, entries that are not mappings or
    name nobody are dropped, and a field that is not text becomes null."""
    if not isinstance(value, list):
        return []
    found = []
    for entry in value:
        if not isinstance(entry, dict):
            continue
        who = {f: _text(entry.get(f)) for f in ("login", "name", "email")}
        if any(who.values()):
            found.append(who)
    return found


def co_authors(record: dict) -> list:
    """The co-authors of a commit record (none when the field is absent, as in records from older collectors)."""
    return clean_co_authors(record.get("co_authors"))


def record_identity(metric: str, record: dict):
    """The de-duplication key of a record (without the repo), or None when a key field is missing or has the wrong type."""
    if metric == "commits":
        return (record.get("sha"),) if isinstance(record.get("sha"), str) else None
    if metric == "pull_requests":
        return (record.get("number"),) if _whole(record.get("number")) else None
    if not _whole(record.get("pr_number")):
        return None
    if metric == "comments":
        ok = _scalar(record.get("comment_id")) and all(_optional_scalar(record.get(f))
                                                       for f in ("thread_root_id", "in_reply_to_id"))
        return (record["comment_id"],) if ok else None
    if record.get("review_id") is not None:
        return ("id", record["review_id"]) if _scalar(record["review_id"]) else None
    fallback = tuple(record.get(f) for f in ("pr_number", "reviewer_login", "submitted_at", "state"))
    return ("content", *fallback) if all(_optional_scalar(v) for v in fallback) else None


def read_jsonl(path: Path, repo: str, metric: str, key: str, corrupt: dict) -> list:
    """Records of one file. A repeated key keeps the last record, at the position of the first (append-only files)."""
    records, bad = {}, 0
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
        identity = record_identity(metric, record)
        if identity is None:
            bad += 1
            continue
        record["repo"] = repo
        if metric == "commits" and "co_authors" in record:
            record["co_authors"] = clean_co_authors(record["co_authors"])
        records[identity] = record
    if bad:
        corrupt[key] = bad
    return list(records.values())


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
                raw.records[metric].extend(read_jsonl(path, repo, metric, f"{repo}/{FILES[metric]}", raw.corrupt))
            if statuses is None:
                state = "never-run"
            elif metric in statuses:
                state = statuses[metric] if statuses[metric] in STATUSES else "failed"
            else:
                state = "complete" if present else "never-run"
            raw.status[repo][metric] = state
    return raw
