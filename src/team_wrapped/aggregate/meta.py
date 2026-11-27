"""meta.json (spec section 9)."""
from __future__ import annotations

import datetime

from ..config import METRICS
from .context import Context

_ENRICHED = ("commits", "pull_requests")


def build_meta(ctx: Context, partial_datasets, now: datetime.datetime | None = None) -> dict:
    """`partial_datasets` is whatever the family builders reported; nothing is computed from it here.
    `corrupt_lines` and `skipped_metrics` are written only when there is something to report."""
    now = now or datetime.datetime.now(datetime.timezone.utc)
    if now.tzinfo is not None:
        now = now.astimezone(datetime.timezone.utc)
    coverage = {}
    for metric in _ENRICHED:
        records = ctx.raw.records.get(metric, [])
        if records:
            enriched = sum(1 for r in records if r.get("enriched") is True)
            coverage[metric] = enriched * 100 // len(records) / 100      # rounded down: 299 of 300 is 0.99, not 1.0
    meta = {
        "generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "period": {"since": ctx.config.since, "until": ctx.config.until},
        "status": {repo: dict(states) for repo, states in ctx.raw.status.items()},
        "enrichment_coverage": coverage,
        "partial_datasets": list(partial_datasets),
        "groups": {name: list(members) for name, members in ctx.group_repos.items()},
    }
    if ctx.raw.corrupt:
        meta["corrupt_lines"] = dict(sorted(ctx.raw.corrupt.items()))
    skipped = [m for m in METRICS if m not in ctx.metrics]
    if skipped:
        meta["skipped_metrics"] = skipped
    return meta
