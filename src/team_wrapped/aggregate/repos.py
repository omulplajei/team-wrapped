"""repos.touched (spec 7.6): repositories with activity inside the window."""
from __future__ import annotations

from .context import Context
from .raw import ACTIVITY_FIELDS


def _touched_repos(ctx: Context) -> set:
    touched = set()
    for metric in ctx.metrics:
        for record in ctx.records(metric):
            if record["repo"] not in touched and any(ctx.window.contains(record.get(f))
                                                      for f in ACTIVITY_FIELDS[metric]):
                touched.add(record["repo"])
    return touched


def build_repos(ctx: Context):
    touched = _touched_repos(ctx)
    scopes, partial = {}, False
    for scope, repos in ctx.scopes.items():
        names = sorted((r for r in repos if r in touched), key=lambda n: (n.lower(), n))
        scopes[scope] = {"touched": {"total": len(names), "list": [{"name": n} for n in names]}}
        partial = partial or any(ctx.raw.status[r][m] != "complete" for r in repos for m in ctx.metrics)
    return scopes, ["repos.touched"] if partial else []
