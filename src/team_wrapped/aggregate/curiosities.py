"""The curiosity datasets (docs/datasets.md): ranked top-N records per scope.

Windowing rules. Comment and review curiosities count the comments and reviews whose own timestamp is inside the
window. Pull-request curiosities use the PRs created or merged inside the window. Commit, day, month and streak
curiosities use the commit author date (or the PR merge date) as a local calendar date from `ctx.window`.
Ranking is by value, best first; ties go to the earlier date, then the repo name, then the PR number or sha."""
from __future__ import annotations

import datetime
from collections import Counter, defaultdict

from .common import incomplete, is_own_review, pr_authors, whole_number
from .context import Context
from .delivery_volume import has_line_stats
from .window import parse_timestamp


def _rank(entries, top_n):
    """entries: (value, sort key, record). Drops zero values, sorts best first, keeps top_n records."""
    kept = sorted((e for e in entries if e[0] > 0), key=lambda e: (-e[0], e[1]))
    return [record for _, _, record in kept[:top_n]]


def _pr_entries(counts: dict):
    return [(value, (repo, number), {"value": value, "repo": repo, "pr_number": number})
            for (repo, number), value in counts.items()]


def _pr_in_window(ctx, pr):
    return ctx.window.contains(pr.get("created_at")) or ctx.window.contains(pr.get("merged_at"))


def _prs_with_number(ctx, repos):
    return [pr for pr in ctx.records("pull_requests", repos) if whole_number(pr.get("number")) and _pr_in_window(ctx, pr)]


def _comments(ctx, repos):
    return [c for c in ctx.records("comments", repos)
            if whole_number(c.get("pr_number")) and ctx.window.contains(c.get("created_at"))]


def _reviews(ctx, repos, authors):
    return [r for r in ctx.records("reviews", repos)
            if whole_number(r.get("pr_number")) and ctx.window.contains(r.get("submitted_at"))
            and not is_own_review(r, authors)]


# Each curiosity: fn(ctx, repos, scope_data) -> (entries, enrichment_gap). `entries` feed _rank.

def _longest_comment_chain(ctx, repos, data):
    threads = Counter((c["repo"], c["pr_number"], c["thread_root_id"]) for c in _comments(ctx, repos)
                      if c.get("kind") == "review" and c.get("thread_root_id") is not None)
    longest = {}
    for (repo, number, _), size in threads.items():
        longest[(repo, number)] = max(size, longest.get((repo, number), 0))
    return _pr_entries(longest), False


def _most_commented_pr(ctx, repos, data):
    return _pr_entries(Counter((c["repo"], c["pr_number"]) for c in _comments(ctx, repos))), False


def _most_reviewed_pr(ctx, repos, data):
    return _pr_entries(Counter((r["repo"], r["pr_number"]) for r in data["reviews"])), False


def _most_review_rounds_pr(ctx, repos, data):
    return _pr_entries(Counter((r["repo"], r["pr_number"]) for r in data["reviews"]
                               if r.get("state") == "changes_requested")), False


def _enriched_pr(value_of):
    """A curiosity on an enriched pull request number; `value_of(pr)` is None when the PR lacks it."""
    def build(ctx, repos, data):
        prs = data["prs"]
        values = {(pr["repo"], pr["number"]): value_of(pr) for pr in prs}
        return _pr_entries({k: v for k, v in values.items() if v is not None}), any(v is None for v in values.values())
    return build


def _pr_field(name):
    return lambda pr: pr[name] if pr.get("enriched") and whole_number(pr.get(name)) else None


def _pr_lines(pr):
    if pr.get("enriched") and whole_number(pr.get("additions")) and whole_number(pr.get("deletions")):
        return pr["additions"] + pr["deletions"]
    return None


def _longest_lived_pr(ctx, repos, data):
    days = {}
    for pr in data["prs"]:
        start, end = parse_timestamp(pr.get("created_at")), parse_timestamp(pr.get("merged_at") or pr.get("closed_at"))
        if start and end and pr.get("state") != "open":
            days[(pr["repo"], pr["number"])] = (end - start).days
    return _pr_entries(days), False


def _biggest_commit(ctx, repos, data):
    commits = data["commits"]
    entries = []
    for c in commits:
        if has_line_stats(c) and whole_number(c.get("files_changed")) and isinstance(c.get("sha"), str):
            value = c["additions"] + c["deletions"]
            entries.append((value, (c["authored_at"], c["repo"], c["sha"]),
                            {"value": value, "repo": c["repo"], "sha": c["sha"], "files": c["files_changed"]}))
    gap = sum(1 for c in commits if not (has_line_stats(c) and whole_number(c.get("files_changed"))))
    return entries, gap > 0


def _commit_days(ctx, data):
    return Counter(d for d in (ctx.window.date_in_window(c.get("authored_at")) for c in data["commits"]) if d)


def _merge_days(ctx, data):
    return Counter(d for d in (ctx.window.date_in_window(pr.get("merged_at")) for pr in data["all_prs"]) if d)


def _busiest_day(ctx, repos, data):
    merges = _merge_days(ctx, data)
    return [(n, (day.isoformat(),), {"value": n, "date": day.isoformat(), "merged_prs": merges.get(day, 0)})
            for day, n in _commit_days(ctx, data).items()], False


def _busiest_month(ctx, repos, data):
    months, merged = Counter(), Counter()
    for day, n in _commit_days(ctx, data).items():
        months[(day.year, day.month)] += n
    for day, n in _merge_days(ctx, data).items():
        merged[(day.year, day.month)] += n
    return [(n, (f"{y:04d}-{m:02d}",), {"value": n, "month": f"{y:04d}-{m:02d}", "merged_prs": merged.get((y, m), 0)})
            for (y, m), n in months.items()], False


def _streaks(days):
    """Maximal runs of consecutive dates -> (length, (from,), record)."""
    runs, ordered = [], sorted(days)
    start = prev = None
    for day in ordered + [None]:
        if start is not None and (day is None or day - prev != datetime.timedelta(days=1)):
            runs.append(((prev - start).days + 1, (start.isoformat(),),
                         {"value": (prev - start).days + 1, "from": start.isoformat(), "to": prev.isoformat()}))
            start = None
        if day is not None:
            start = day if start is None else start
            prev = day
    return runs


def _longest_commit_streak(ctx, repos, data):
    return _streaks(_commit_days(ctx, data)), False


def _longest_merge_streak(ctx, repos, data):
    return _streaks(_merge_days(ctx, data)), False


# name -> (metrics that must be enabled, builder)
_CURIOSITIES = {
    "longest_comment_chain": (("comments",), _longest_comment_chain),
    "most_commented_pr": (("comments",), _most_commented_pr),
    "most_commits_pr": (("pull_requests",), _enriched_pr(_pr_field("commit_count"))),
    "most_files_pr": (("pull_requests",), _enriched_pr(_pr_field("changed_files"))),
    "biggest_pr_by_lines": (("pull_requests",), _enriched_pr(_pr_lines)),
    "most_lines_deleted_pr": (("pull_requests",), _enriched_pr(_pr_field("deletions"))),
    "most_reviewed_pr": (("reviews",), _most_reviewed_pr),
    "longest_lived_pr": (("pull_requests",), _longest_lived_pr),
    "most_review_rounds_pr": (("reviews",), _most_review_rounds_pr),
    "biggest_commit": (("commits",), _biggest_commit),
    "busiest_day": (("commits", "pull_requests"), _busiest_day),
    "busiest_month": (("commits", "pull_requests"), _busiest_month),
    "longest_commit_streak": (("commits",), _longest_commit_streak),
    "longest_merge_streak": (("pull_requests",), _longest_merge_streak),
}


def build_curiosities(ctx: Context):
    """-> (scopes, partial names). A curiosity whose metrics are not all enabled is omitted, as is an empty one.
    It is partial when an in-scope status of its metrics is not complete, or (enriched ones) when an in-window
    commit or PR in scope lacks the numbers."""
    authors = pr_authors(ctx) if "reviews" in ctx.metrics else {}
    scopes, partial = {}, set()
    for scope, repos in ctx.scopes.items():
        data = {
            "prs": _prs_with_number(ctx, repos) if "pull_requests" in ctx.metrics else [],
            "all_prs": ctx.records("pull_requests", repos),
            "commits": [c for c in ctx.records("commits", repos) if ctx.window.contains(c.get("authored_at"))],
            "reviews": _reviews(ctx, repos, authors) if "reviews" in ctx.metrics else [],
        }
        datasets = {}
        for name, (needs, build) in _CURIOSITIES.items():
            if not all(m in ctx.metrics for m in needs):
                continue
            entries, gap = build(ctx, repos, data)
            if gap or incomplete(ctx, repos, needs):
                partial.add(f"curiosities.{name}")
            records = _rank(entries, ctx.config.top_n)
            if records:
                datasets[name] = records
        scopes[scope] = datasets
    return scopes, sorted(partial)
