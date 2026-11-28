"""The `collect` stage (spec section 8): GitHub through `gh api graphql` in, data/raw/<repo>/*.jsonl out.

Work is done in units of one repository and metric. Commits are one unit; pull requests, reviews and comments
come from the same search and share a unit's outcome. After each unit its files and status are written
atomically, so a stopped run keeps every finished unit. A unit ends as:

- `complete`: everything in the window was fetched.
- `partial`: some was fetched (rate limit, request budget, retries used up, or a capped search); the reason is in
  status-detail.json. A rate limit or the budget also stops the run; units not reached are left untouched.
- `failed`: the repository is missing or not accessible, or GitHub rejected the query; nothing is written.

A unit that ends `complete` also advances its entry in checkpoint.json, so the next run fetches only what changed
since (checkpoint.py); `full` ignores the checkpoints.
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass, field, replace
from pathlib import Path

from ..config import Config
from ..github import BudgetExhausted, GhError, NotFound, Forbidden, RateLimited, Transient
from ..scenes.loader import LoadError
from .avatars import app_id_lookup, download_avatars
from .checkpoint import narrowest, plan_commits, plan_pull_requests, read_checkpoints, write_checkpoint
from .commits import fetch_commits
from .common import iso, utc_bounds
from .pull_requests import PullRequestBatch, fetch_pull_requests
from .store import write_records, write_status

PR_METRICS = ("pull_requests", "reviews", "comments")
DEFAULT_OVERLAP_DAYS = 7


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


def unit_fetches(folder, plan: Plan, now, *, full=False, overlap_days=DEFAULT_OVERLAP_DAYS) -> tuple:
    """(commits Fetch or None, pull request Fetch or None, [warning]) for one repository of `plan`."""
    checkpoints, warnings = ({}, []) if full else read_checkpoints(folder)
    commits = plan_commits(plan, checkpoints.get("commits"), now, overlap_days) if "commits" in plan.metrics \
        else None
    shared = [m for m in PR_METRICS if m in plan.metrics]
    prs = plan_pull_requests(plan, narrowest([checkpoints.get(m) for m in shared]), now) if shared else None
    return commits, prs, warnings


def _what(fetch) -> str:
    """How a unit's fetch is described in the plan: `full` or `incremental from <date>`."""
    if fetch.mode == "full":
        return "full"
    if not fetch.pieces:
        return "incremental, nothing to fetch (window already covered)"
    return f"incremental from {fetch.since or 'the beginning'}"


def describe_fetches(data_root, plan: Plan, now, *, full=False, overlap_days=DEFAULT_OVERLAP_DAYS) -> list:
    """Per repository and metric, what a run would fetch (the dry run; reads checkpoints, no API calls)."""
    lines = []
    for repo in plan.repos:
        commits, prs, warnings = unit_fetches(Path(data_root) / "raw" / repo, plan, now, full=full,
                                              overlap_days=overlap_days)
        lines += [f"{repo}: {warning}" for warning in warnings]
        for metric in plan.metrics:
            fetch = commits if metric == "commits" else prs
            lines.append(f"{repo} {metric}: {_what(fetch)}{f' ({fetch.notice})' if fetch.notice else ''}")
    return lines


def _finish(folder, repo, metric, status, records, reason, plan, collected_at, units, log, fetch):
    count = len(records)
    if status != "failed":
        write_records(folder, repo, metric, records)
    detail = {"collected_at": collected_at, "records": count, "window": {"since": plan.since, "until": plan.until},
              "fetch": fetch.mode}
    if reason:
        detail["reason"] = reason
    write_status(folder, metric, status, detail)
    if status == "complete":
        write_checkpoint(folder, metric, fetch.checkpoint)
    units.append(Unit(repo, metric, status, count, reason))
    what = f"{count} records" if fetch.mode == "full" else \
        f"{count} new/updated records, since {fetch.since or 'the beginning'}"
    log(f"{repo} {metric}: {status} ({what}){f' - {reason}' if reason else ''}")


def _outcome(error) -> tuple:
    """(status, reason) of a unit that raised `error`."""
    if error is None:
        return "complete", None
    if isinstance(error, (RateLimited, BudgetExhausted, Transient)):
        return "partial", str(error)
    return "failed", str(error)


def collect(data_root, config: Config, gh, plan: Plan, *, avatars: bool = True, fetch=None, now=None,
            log=print, full: bool = False, overlap_days: int = DEFAULT_OVERLAP_DAYS) -> Result:
    """Fetch every unit of `plan` into <data_root>/raw, then (unless disabled) download avatars. `now` is the run
    start: checkpoints record it and never claim coverage past it. `full` ignores existing checkpoints."""
    data_root = Path(data_root)
    now = now or datetime.datetime.now(datetime.timezone.utc)
    collected_at = iso(now)
    result = Result()
    pending = [(repo, metric) for repo in plan.repos for metric in plan.metrics]
    for repo in plan.repos:
        if result.stopped:
            break
        folder = data_root / "raw" / repo
        commit_fetch, pr_fetch, warnings = unit_fetches(folder, plan, now, full=full, overlap_days=overlap_days)
        for warning in warnings:
            log(f"{repo}: {warning}")
        missing = None
        if commit_fetch:
            records, error = [], None
            try:
                for since, until in commit_fetch.pieces:
                    fetch_commits(gh, plan.org, repo, since, until, records)
            except GhError as caught:
                error = caught
            status, reason = _outcome(error)
            _finish(folder, repo, "commits", status, records, reason, plan, collected_at, result.units, log,
                    commit_fetch)
            if isinstance(error, (NotFound, Forbidden)):
                missing = reason
            if _stop(error):
                result.stopped = str(error)
        pr_metrics = [m for m in PR_METRICS if m in plan.metrics]
        if pr_fetch and not result.stopped:
            batch, error = PullRequestBatch(), None
            if missing:
                error = NotFound(missing)
            else:
                if pr_fetch.notice:
                    log(f"{repo} pull requests: {pr_fetch.notice}")
                try:
                    for piece in pr_fetch.pieces:
                        fetch_pull_requests(gh, plan.org, repo, piece.updated_from, piece.created_to, batch, now=now,
                                            created_from=piece.created_from)
                except GhError as caught:
                    error = caught
            status, reason = _outcome(error)
            if status == "complete" and batch.notes:
                status, reason = "partial", "; ".join(batch.notes)
            for metric in pr_metrics:
                _finish(folder, repo, metric, status, getattr(batch, metric), reason, plan, collected_at,
                        result.units, log, pr_fetch)
            if _stop(error):
                result.stopped = str(error)
    done = {(u.repo, u.metric) for u in result.units}
    result.units += [Unit(repo, metric, "not run") for repo, metric in pending if (repo, metric) not in done]
    result.requests = gh.requests
    if result.stopped:
        log(f"stopped: {result.stopped}. Re-run the same command to continue.")
    if avatars and config.download_avatars:
        result.avatars_failed = download_avatars(data_root, config, fetch=fetch, app_id=app_id_lookup(gh), log=log)
    return result
