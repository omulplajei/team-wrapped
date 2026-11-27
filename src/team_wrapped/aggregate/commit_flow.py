"""commit_flow.groups and commit_flow.window (docs/datasets.md): one year of commits per capability, as blocks."""
from __future__ import annotations

from .common import incomplete
from .context import Context
from .delivery_volume import has_line_stats, is_merge


def build_commit_flow(ctx: Context):
    """Only scope `all`. `groups` lists every configured group in config order (a group without qualifying commits
    keeps an empty `commits`); a repository in several groups counts in each. A commit is `[day, lines]`: `day` is
    the whole local calendar days since the window start, `lines` additions + deletions (0 when the commit is not
    enriched). Merge commits and commits outside the window are left out. Commits are ordered by day, then authored
    timestamp, then sha. Nothing is written (empty scope) when no groups are configured or the window lacks
    `since` or `until`, since the day offsets need both. Partial when any in-window non-merge commit of a grouped
    repository is not enriched or a grouped repository's commits status is not complete."""
    window = ctx.window
    if "commits" not in ctx.metrics or not ctx.group_repos or window.since is None or window.until is None:
        return {"all": {}}, []
    groups, partial = [], False
    for name, repos in ctx.group_repos.items():
        found = []
        for c in ctx.records("commits", repos):
            day = window.date_in_window(c.get("authored_at"))
            if day is None or is_merge(c):
                continue
            lines = c["additions"] + c["deletions"] if has_line_stats(c) else 0
            partial = partial or not has_line_stats(c)
            found.append(((day - window.since).days, str(c["authored_at"]), str(c["sha"]), lines))
        found.sort(key=lambda t: t[:3])
        info = ctx.config.group_info.get(name, {})
        group = {"name": name, "label": info.get("label") or name}
        if info.get("category"):
            group["category"] = info["category"]
        group["total"] = len(found)
        group["commits"] = [[day, lines] for day, _, _, lines in found]
        groups.append(group)
        partial = partial or incomplete(ctx, repos, ["commits"])
    flow = {"groups": groups, "window": {"days": (window.until - window.since).days + 1,
                                         "start": window.since.isoformat()}}
    return {"all": flow}, ["commit_flow.groups"] if partial else []
