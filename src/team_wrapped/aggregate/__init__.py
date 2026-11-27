"""The `aggregate` stage: raw JSONL in, derived JSON out (spec 5.2, 7.6)."""
from __future__ import annotations

import dataclasses
import datetime
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from ..config import load_config
from .context import Context
from .contributors import build_contributors
from .curiosities import build_curiosities
from .delivery_volume import build_delivery_volume
from .io import write_family, write_meta
from .meta import build_meta
from .raw import load_raw
from .repos import build_repos
from .summary import build_summary


@dataclass(frozen=True)
class Family:
    """One derived file. `build(ctx)` returns `(scopes, partial_dataset_names)`: `scopes` has one entry per key of
    `ctx.scopes`, each holding that family's datasets; `partial_dataset_names` lists datasets (`family.name`, or
    the bare family name for `contributors`) computed from incomplete data. `extra` is merged into the file's
    top level, between `period` and `scopes`."""
    name: str
    build: Callable
    extra: dict = field(default_factory=dict)


# Order is the order files are written.
FAMILIES = [
    Family("contributors", build_contributors),
    Family("repos", build_repos, {"basis": "activity"}),
    Family("summary", build_summary),
    Family("delivery_volume", build_delivery_volume),
    Family("curiosities", build_curiosities),
]


def aggregate(data_root, *, now: datetime.datetime | None = None,
              since: str | None = None, until: str | None = None) -> list[Path]:
    """Read data/config.yml and data/raw, write data/derived/*.json. Returns the files written, meta last.
    `since`/`until` (YYYY-MM-DD) override the configured window for this run. Raises LoadError on a bad config."""
    data_root = Path(data_root)
    config = load_config(data_root / "config.yml")
    if since or until:
        config = dataclasses.replace(config, since=since or config.since, until=until or config.until)
    ctx = Context.build(data_root, config, load_raw(data_root, config))
    period = {"since": config.since, "until": config.until}
    written, partial = [], set()
    for family in FAMILIES:
        scopes, partial_names = family.build(ctx)
        written.append(write_family(data_root, family.name, period, scopes, family.extra))
        partial.update(partial_names)
    written.append(write_meta(data_root, build_meta(ctx, sorted(partial), now)))
    return written
