"""The `collect` stage (spec section 8): GitHub through `gh api graphql` in, data/raw/<repo>/*.jsonl out.

Work is done in units of one repository and metric. Commits are one unit; pull requests, reviews and comments
come from the same search and share a unit's outcome. After each unit its files and status are written
atomically, so a stopped run keeps every finished unit. A unit ends as:

- `complete`: everything in the window was fetched.
- `partial`: some was fetched (rate limit, request budget, retries used up, or a capped search); the reason is in
  status-detail.json. A rate limit or the budget also stops the run; units not reached are left untouched.
- `failed`: the repository is missing or not accessible, or GitHub rejected the query; nothing is written.
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass, field, replace
from pathlib import Path

from ..config import Config
from ..github import BudgetExhausted, GhError, NotFound, Forbidden, RateLimited, Transient
from ..scenes.loader import LoadError
from .avatars import download_avatars
from .commits import fetch_commits
from .common import iso, utc_bounds
from .pull_requests import PullRequestBatch, fetch_pull_requests
from .store import write_records, write_status

PR_METRICS = ("pull_requests", "reviews", "comments")


@dataclass(frozen=True)
class Plan:
    """What a run fetches. `since`/`until` are inclusive local dates; `start`/`end` the UTC instants sent to GitHub."""
    org: str
    repos: list
    metrics: list
    timezone: str
    since: str | None
    until: str | None
    start: datetime.datetime | None
    end: datetime.datetime | None


@dataclass
class Unit:
    repo: str
    metric: str
    status: str                 # complete, partial, failed, or `not run` (never written)
    records: int = 0            # records fetched by this run
    reason: str | None = None


@dataclass
class Result:
    units: list = field(default_factory=list)
    stopped: str | None = None          # why the run stopped early (rate limit, budget)
    requests: int = 0
    avatars_failed: list | None = None  # None when avatars were not downloaded

    @property
    def failed(self) -> bool:
        return any(u.status == "failed" for u in self.units)


def _date(flag, value):
    if value is None:
        return None
    try:
        return datetime.date.fromisoformat(value)
    except (TypeError, ValueError):
        raise LoadError(f"{flag} must be a date like 2026-01-31 (got {value!r})") from None


def make_plan(config: Config, repos=None, metrics=None, since=None, until=None) -> Plan:
    """Apply the command line filters and window overrides to the config. Raises LoadError on a bad filter."""
    if config.commit_branches != "default":
        raise LoadError("commit_branches: all is not supported by collect yet; use default (the default branch)")
    unknown = [r for r in repos or [] if r not in config.repos]
    if unknown:
        raise LoadError(f"--repo {', '.join(unknown)} not in the config repos")
    off = [m for m in metrics or [] if m not in config.metrics]
    if off:
        raise LoadError(f"--metric {', '.join(off)} not enabled in the config metrics ({', '.join(config.metrics)})")
    since_d = _date("--since", since) if since else _date("since", config.since)
    until_d = _date("--until", until) if until else _date("until", config.until)
    if since_d and until_d and since_d > until_d:
        raise LoadError("since must not be after until")
    start, end = utc_bounds(since_d, until_d, config.timezone)
    return Plan(org=config.org,
                repos=[r for r in config.repos if not repos or r in repos],
                metrics=[m for m in config.metrics if not metrics or m in metrics],
                timezone=config.timezone,
                since=since_d.isoformat() if since_d else None,
                until=until_d.isoformat() if until_d else None,
                start=start, end=end)


def describe(plan: Plan) -> list:
    """Lines describing a plan (the dry run)."""
    window = f"{plan.since or 'beginning'} to {plan.until or 'now'} ({plan.timezone})"
    bounds = f"{iso(plan.start) or '-'} .. {iso(plan.end) or '-'} UTC"
    return [f"org: {plan.org}", f"window: {window}, sent as {bounds}", f"metrics: {', '.join(plan.metrics)}",
            f"repos ({len(plan.repos)}): {', '.join(plan.repos)}"]


def _stop(error) -> bool:
    return isinstance(error, (RateLimited, BudgetExhausted))


def _finish(folder, repo, metric, status, records, reason, plan, collected_at, units, log):
    count = len(records)
    if status != "failed":
        write_records(folder, repo, metric, records)
    detail = {"collected_at": collected_at, "records": count, "window": {"since": plan.since, "until": plan.until}}
    if reason:
        detail["reason"] = reason
    write_status(folder, metric, status, detail)
    units.append(Unit(repo, metric, status, count, reason))
    log(f"{repo} {metric}: {status} ({count} records){f' - {reason}' if reason else ''}")


def _outcome(error) -> tuple:
    """(status, reason) of a unit that raised `error`."""
    if error is None:
        return "complete", None
    if isinstance(error, (RateLimited, BudgetExhausted, Transient)):
        return "partial", str(error)
    return "failed", str(error)


def collect(data_root, config: Config, gh, plan: Plan, *, avatars: bool = True, fetch=None, now=None,
            log=print) -> Result:
    """Fetch every unit of `plan` into <data_root>/raw, then (unless disabled) download avatars."""
    data_root = Path(data_root)
    now = now or datetime.datetime.now(datetime.timezone.utc)
    collected_at = iso(now)
    result = Result()
    pending = [(repo, metric) for repo in plan.repos for metric in plan.metrics]
    for repo in plan.repos:
        if result.stopped:
            break
        folder = data_root / "raw" / repo
        missing = None
        if "commits" in plan.metrics:
            records, error = [], None
            try:
                fetch_commits(gh, plan.org, repo, plan.start, plan.end, records)
            except GhError as caught:
                error = caught
            status, reason = _outcome(error)
            _finish(folder, repo, "commits", status, records, reason, plan, collected_at, result.units, log)
            if isinstance(error, (NotFound, Forbidden)):
                missing = reason
            if _stop(error):
                result.stopped = str(error)
        pr_metrics = [m for m in PR_METRICS if m in plan.metrics]
        if pr_metrics and not result.stopped:
            batch, error = PullRequestBatch(), None
            if missing:
                error = NotFound(missing)
            else:
                try:
                    fetch_pull_requests(gh, plan.org, repo, plan.start, plan.end, batch, now=now)
                except GhError as caught:
                    error = caught
            status, reason = _outcome(error)
            if status == "complete" and batch.notes:
                status, reason = "partial", "; ".join(batch.notes)
            for metric in pr_metrics:
                _finish(folder, repo, metric, status, getattr(batch, metric), reason, plan, collected_at,
                        result.units, log)
            if _stop(error):
                result.stopped = str(error)
    done = {(u.repo, u.metric) for u in result.units}
    result.units += [Unit(repo, metric, "not run") for repo, metric in pending if (repo, metric) not in done]
    result.requests = gh.requests
    if result.stopped:
        log(f"stopped: {result.stopped}. Re-run the same command to continue.")
    if avatars and config.download_avatars:
        result.avatars_failed = download_avatars(data_root, config, fetch=fetch, log=log)
    return result
