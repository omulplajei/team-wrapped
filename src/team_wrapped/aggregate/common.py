"""Helpers shared by the statistic families (summary, delivery_volume, curiosities)."""
from __future__ import annotations

from .context import Context


def incomplete(ctx: Context, repos, metrics) -> bool:
    """True when any in-scope repository's status for any of `metrics` is not `complete`. A metric that is
    disabled has no status and does not count."""
    return any(ctx.raw.status[repo][metric] != "complete"
               for repo in repos for metric in metrics if metric in ctx.metrics)


def pr_authors(ctx: Context) -> dict:
    """(repo, PR number) -> lower-cased author login, for every known pull request (not window-filtered)."""
    return {(pr["repo"], pr.get("number")): pr["author_login"].lower()
            for pr in ctx.records("pull_requests") if isinstance(pr.get("author_login"), str)}


def is_own_review(review: dict, authors: dict) -> bool:
    """A review written by the PR's own author. Unknown PRs and missing logins are never "own"."""
    login = review.get("reviewer_login")
    author = authors.get((review["repo"], review.get("pr_number")))
    return isinstance(login, str) and author is not None and login.lower() == author


def whole_number(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)
