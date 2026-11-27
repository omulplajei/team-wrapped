"""delivery_volume.lines (docs/datasets.md): lines added and deleted, from enriched commits."""
from __future__ import annotations

from .common import incomplete, whole_number
from .context import Context


def has_line_stats(commit: dict) -> bool:
    return bool(commit.get("enriched")) and whole_number(commit.get("additions")) and whole_number(commit.get("deletions"))


def build_delivery_volume(ctx: Context):
    """Sums `additions` and `deletions` over the enriched commits authored inside the window, merge commits
    included when they carry the numbers. The dataset is omitted (not zeros) when no commit in scope is enriched,
    and listed as partial when any in-window commit lacks the numbers or the commits status is not complete."""
    scopes, partial = {}, False
    for scope, repos in ctx.scopes.items():
        scopes[scope] = {}
        if "commits" not in ctx.metrics:
            continue
        commits = [c for c in ctx.records("commits", repos) if ctx.window.contains(c.get("authored_at"))]
        enriched = [c for c in commits if has_line_stats(c)]
        if enriched:
            additions = sum(c["additions"] for c in enriched)
            deletions = sum(c["deletions"] for c in enriched)
            scopes[scope]["lines"] = {"total_additions": additions, "total_deletions": deletions,
                                      "total_net": additions - deletions}
        partial = partial or len(enriched) < len(commits) or incomplete(ctx, repos, ["commits"])
    return scopes, ["delivery_volume.lines"] if partial else []
