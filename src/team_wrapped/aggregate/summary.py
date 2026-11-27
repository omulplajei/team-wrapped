"""summary.totals (docs/datasets.md): commits, merged PRs, reviews and comments inside the window."""
from __future__ import annotations

from .common import Resolver, incomplete, is_own_review, pr_authors
from .context import Context

# totals key -> (metric, timestamp field)
_TOTALS = {
    "commits": ("commits", "authored_at"),
    "merged_prs": ("pull_requests", "merged_at"),
    "reviews": ("reviews", "submitted_at"),
    "comments": ("comments", "created_at"),
}


def build_summary(ctx: Context):
    """Every commit counts (merge commits and bots included), as does every comment of either kind, whoever wrote
    it. Reviews by the pull request's own author are left out when that PR is in the raw data. Only totals of
    enabled metrics are written. `summary.totals` is partial when any in-scope status for those metrics is not complete."""
    resolver = Resolver(ctx.config.aliases)
    authors = pr_authors(ctx, resolver) if "reviews" in ctx.metrics else {}
    keys = {key: spec for key, spec in _TOTALS.items() if spec[0] in ctx.metrics}
    scopes, partial = {}, False
    for scope, repos in ctx.scopes.items():
        totals = {}
        for key, (metric, stamp) in keys.items():
            records = (r for r in ctx.records(metric, repos) if ctx.window.contains(r.get(stamp)))
            if key == "reviews":
                records = (r for r in records if not is_own_review(r, authors, resolver))
            totals[key] = sum(1 for _ in records)
        scopes[scope] = {"totals": totals}
        partial = partial or incomplete(ctx, repos, [metric for metric, _ in keys.values()])
    return scopes, ["summary.totals"] if partial else []
