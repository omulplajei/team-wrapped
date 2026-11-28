"""data/raw/<repo>/checkpoint.json: what each metric has already collected, so a later run fetches only the delta.

One entry per metric, written only when that metric's unit ends `complete` (the aggregator ignores the file):

    {"synced_at": "<UTC start of the run that wrote it>", "since": "YYYY-MM-DD" | null,
     "until": "YYYY-MM-DD" | null, "covered_to": "<UTC instant>", "overlap_days": N}

`since`/`until` are the local dates of the collected window (null when open). `covered_to` is how far the data
on disk is known to be complete, never later than `synced_at` (a window usually ends in the future).

The planners turn a checkpoint and the requested window into the ranges to fetch and the checkpoint to write
when the unit completes:

- Commits cover [since, covered_to]. A run fetches from `covered_to - overlap` (late pushes and rebases keep old
  commit dates) to the requested end, plus the start when the requested since is earlier. A window that does
  not touch the covered range is fetched in full and replaces the checkpoint.
- Pull requests (with their reviews and comments) cover those created by `until` and updated since `since`, as
  of `synced_at`. A run re-fetches A: those updated since `synced_at - 1 day` in the known creation range, and
  B: those created after the checkpoint's `until` up to the requested one. A requested since earlier than the
  checkpoint's falls back to the whole window.
"""
from __future__ import annotations

import datetime
import json
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple
from zoneinfo import ZoneInfo

from ..aggregate.io import write_json
from .common import iso, utc_bounds

CHECKPOINT_FILE = "checkpoint.json"
PR_OVERLAP_DAYS = 1                 # pull requests updated within a day before the last sync are fetched again
_SECOND = datetime.timedelta(seconds=1)


@dataclass(frozen=True)
class Checkpoint:
    synced_at: datetime.datetime
    since: datetime.date | None
    until: datetime.date | None
    covered_to: datetime.datetime
    overlap_days: int

    def to_json(self) -> dict:
        return {"synced_at": iso(self.synced_at), "since": _day(self.since), "until": _day(self.until),
                "covered_to": iso(self.covered_to), "overlap_days": self.overlap_days}

    @classmethod
    def from_json(cls, value) -> "Checkpoint":
        """Raises ValueError on anything malformed."""
        if not isinstance(value, dict):
            raise ValueError("not an object")
        overlap = value.get("overlap_days")
        if not isinstance(overlap, int) or isinstance(overlap, bool) or overlap < 0:
            raise ValueError("overlap_days must be a whole number")
        return cls(synced_at=_instant(value.get("synced_at")), since=_date(value.get("since")),
                   until=_date(value.get("until")), covered_to=_instant(value.get("covered_to")),
                   overlap_days=overlap)


def _day(value):
    return value.isoformat() if value else None


def _date(value):
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"bad date {value!r}")
    return datetime.date.fromisoformat(value)


def _instant(value) -> datetime.datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError(f"bad UTC instant {value!r}")
    return datetime.datetime.fromisoformat(value[:-1] + "+00:00")


def read_checkpoints(folder) -> tuple:
    """({metric: Checkpoint}, [warning]). A missing file is no checkpoint; an unreadable file or entry is
    treated as absent (that metric is fetched in full) and explained in a warning."""
    path = Path(folder) / CHECKPOINT_FILE
    if not path.is_file():
        return {}, []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        return {}, [f"{CHECKPOINT_FILE} unreadable ({error}); fetching in full"]
    if not isinstance(data, dict):
        return {}, [f"{CHECKPOINT_FILE} is not an object; fetching in full"]
    checkpoints, warnings = {}, []
    for metric, entry in data.items():
        try:
            checkpoints[metric] = Checkpoint.from_json(entry)
        except ValueError as error:
            warnings.append(f"{CHECKPOINT_FILE} entry {metric} ignored ({error}); fetching it in full")
    return checkpoints, warnings


def write_checkpoint(folder, metric: str, checkpoint: Checkpoint) -> None:
    """Set one metric's entry (atomic temporary file + os.replace); other entries are kept, unreadable ones dropped."""
    path = Path(folder) / CHECKPOINT_FILE
    current, _ = read_checkpoints(folder)
    current[metric] = checkpoint
    write_json(path, {name: entry.to_json() for name, entry in current.items()})


def narrowest(checkpoints: list) -> Checkpoint | None:
    """What every one of `checkpoints` covers (pull requests, reviews and comments share one search); None when
    any is missing."""
    if not checkpoints or any(c is None for c in checkpoints):
        return None
    sinces = [c.since for c in checkpoints if c.since is not None]
    untils = [c.until for c in checkpoints if c.until is not None]
    return Checkpoint(synced_at=min(c.synced_at for c in checkpoints), since=max(sinces) if sinces else None,
                      until=min(untils) if untils else None, covered_to=min(c.covered_to for c in checkpoints),
                      overlap_days=min(c.overlap_days for c in checkpoints))


class PrPiece(NamedTuple):
    """One pull request search: `updated:>=updated_from`, `created:created_from..created_to` (None = open)."""
    updated_from: datetime.datetime | None
    created_from: datetime.datetime | None
    created_to: datetime.datetime | None


@dataclass(frozen=True)
class Fetch:
    mode: str                       # full or incremental
    pieces: list                    # commits: [(from, to)] UTC ranges; pull requests: [PrPiece]
    checkpoint: Checkpoint          # written when the unit completes
    since: datetime.date | None     # earliest local date fetched, for messages (None: from the beginning)
    notice: str | None = None


# None is open: the earliest start, the latest end.
def _min_start(*values):
    return None if any(v is None for v in values) else min(values)


def _max_end(*values):
    return None if any(v is None for v in values) else max(values)


def _before(a, b) -> bool:
    """Start `a` is earlier than start `b` (None is the earliest)."""
    return b is not None and (a is None or a < b)


def _capped(end, now):
    return now if end is None else min(end, now)


def _local_day(moment, timezone):
    return moment.astimezone(ZoneInfo(timezone)).date() if moment else None


def _since_date(plan):
    return datetime.date.fromisoformat(plan.since) if plan.since else None


def _until_date(plan):
    return datetime.date.fromisoformat(plan.until) if plan.until else None


def _full(plan, now, overlap_days, pieces, notice=None) -> Fetch:
    checkpoint = Checkpoint(synced_at=now, since=_since_date(plan), until=_until_date(plan),
                            covered_to=_capped(plan.end, now), overlap_days=overlap_days)
    return Fetch("full", pieces, checkpoint, _since_date(plan), notice)


def plan_commits(plan, checkpoint: Checkpoint | None, now, overlap_days: int) -> Fetch:
    """The history ranges to fetch for the window of `plan` (since/until dates, start/end instants, timezone)."""
    start, end = plan.start, plan.end
    if checkpoint is None:
        return _full(plan, now, overlap_days, [(start, end)])
    covered_from, _ = utc_bounds(checkpoint.since, None, plan.timezone)
    touches = (start is None or start <= checkpoint.covered_to) and \
              (end is None or covered_from is None or end + _SECOND >= covered_from)
    if not touches:
        return _full(plan, now, overlap_days, [(start, end)])
    overlap = datetime.timedelta(days=overlap_days)
    pieces = []
    lo = checkpoint.covered_to - overlap
    lo = lo if start is None else max(start, lo)
    if end is None or lo <= end:
        pieces.append((lo, end))
    if _before(start, covered_from):
        head = (start, covered_from + overlap if end is None else min(covered_from + overlap, end))
        if pieces and pieces[0][0] <= head[1]:
            pieces = [(start, pieces[0][1])]
        else:
            pieces.append(head)
    since = _since_date(plan)
    new = Checkpoint(synced_at=now,
                     since=None if since is None or checkpoint.since is None else min(since, checkpoint.since),
                     until=None if plan.until is None or checkpoint.until is None
                     else max(_until_date(plan), checkpoint.until),
                     covered_to=max(checkpoint.covered_to, _capped(end, now)), overlap_days=overlap_days)
    first = _min_start(*(p[0] for p in pieces)) if pieces else checkpoint.covered_to
    return Fetch("incremental", pieces, new, _local_day(first, plan.timezone))


def plan_pull_requests(plan, checkpoint: Checkpoint | None, now) -> Fetch:
    """The pull request searches for the window of `plan`."""
    whole = [PrPiece(plan.start, None, plan.end)]
    if checkpoint is None:
        return _full(plan, now, PR_OVERLAP_DAYS, whole)
    since = _since_date(plan)
    if checkpoint.since is not None and (since is None or since < checkpoint.since):
        notice = (f"since {since or 'the beginning'} is before the checkpoint's {checkpoint.since}; "
                  f"fetching the whole window")
        return _full(plan, now, PR_OVERLAP_DAYS, whole, notice)
    _, known_end = utc_bounds(None, checkpoint.until, plan.timezone)
    keep_from, _ = utc_bounds(checkpoint.since, None, plan.timezone)
    delta_from = checkpoint.synced_at - datetime.timedelta(days=PR_OVERLAP_DAYS)
    pieces = [PrPiece(delta_from, None, known_end)]
    until = _until_date(plan)
    if checkpoint.until is not None and (until is None or until > checkpoint.until):
        pieces.append(PrPiece(keep_from, known_end + _SECOND, plan.end))
    new_until = None if until is None or checkpoint.until is None else max(until, checkpoint.until)
    _, new_end = utc_bounds(None, new_until, plan.timezone)
    new = Checkpoint(synced_at=now, since=checkpoint.since, until=new_until, covered_to=_capped(new_end, now),
                     overlap_days=PR_OVERLAP_DAYS)
    return Fetch("incremental", pieces, new, _local_day(delta_from, plan.timezone))
