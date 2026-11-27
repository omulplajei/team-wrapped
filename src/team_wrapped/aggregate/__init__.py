"""The `aggregate` stage: raw JSONL in, derived JSON out (spec 5.2, 7.6)."""
from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from ..config import load_config
from .context import Context
from .contributors import build_contributors
from .io import write_family, write_meta
from .meta import build_meta
from .raw import load_raw
from .repos import build_repos


@dataclass(frozen=True)
class Family:
    """One derived file. `build(ctx)` returns `(scopes, partial_dataset_names)`: `scopes` has one entry per key of
    `ctx.scopes`, each holding that family's datasets; `partial_dataset_names` lists datasets (`family.name`, or
    the bare family name for `contributors`) computed from incomplete data. `extra` is merged into the file's
    top level, between `period` and `scopes`."""
    name: str
    build: Callable
    extra: dict = field(default_factory=dict)


# Part 2 appends summary, delivery_volume and curiosities here. Order is the order files are written.
FAMILIES = [
    Family("contributors", build_contributors),
    Family("repos", build_repos, {"basis": "activity"}),
]


def aggregate(data_root, *, now: datetime.datetime | None = None) -> list[Path]:
    """Read data/config.yml and data/raw, write data/derived/*.json. Returns the files written, meta last.
    Raises LoadError on a bad config."""
    data_root = Path(data_root)
    config = load_config(data_root / "config.yml")
    ctx = Context.build(data_root, config, load_raw(data_root, config))
    period = {"since": config.since, "until": config.until}
    written, partial = [], []
    for family in FAMILIES:
        scopes, partial_names = family.build(ctx)
        written.append(write_family(data_root, family.name, period, scopes, family.extra))
        partial.extend(n for n in partial_names if n not in partial)
    written.append(write_meta(data_root, build_meta(ctx, partial, now)))
    return written
