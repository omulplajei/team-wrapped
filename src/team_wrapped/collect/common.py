"""Small helpers shared by the fetchers."""
from __future__ import annotations

import datetime
import re
from zoneinfo import ZoneInfo

from ..aggregate.window import parse_timestamp
from ..github import NotFound

_NOREPLY = re.compile(r"(?:\d+\+)?([A-Za-z0-9-]+(?:\[bot\])?)@users\.noreply\.github\.com", re.IGNORECASE)


def iso(moment: datetime.datetime | None) -> str | None:
    """`2026-03-14T09:30:00Z`, the raw-file timestamp form."""
    if moment is None:
        return None
    return moment.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def utc_bounds(since, until, timezone: str):
    """(start, end): local midnight starting `since` and the last second of `until`, both in UTC; None when open."""
    tz = ZoneInfo(timezone)
    start = end = None
    if since:
        start = datetime.datetime.combine(since, datetime.time(), tz).astimezone(datetime.timezone.utc)
    if until:
        end = (datetime.datetime.combine(until + datetime.timedelta(days=1), datetime.time(), tz)
               - datetime.timedelta(seconds=1)).astimezone(datetime.timezone.utc)
    return start, end


def timestamp(value) -> str | None:
    """A GitHub timestamp (any offset) as a UTC `...Z` string, or None."""
    return iso(parse_timestamp(value))


def actor_login(actor) -> str | None:
    """Login of a GraphQL actor. GitHub returns a Bot's login without `[bot]`; it is appended so `*[bot]` matches.
    A deleted account (`author: null`) has no login."""
    if not isinstance(actor, dict) or not isinstance(actor.get("login"), str) or not actor["login"]:
        return None
    login = actor["login"]
    if actor.get("__typename") == "Bot" and not login.endswith("[bot]"):
        login += "[bot]"
    return login


def noreply_login(email) -> str | None:
    """The login in a GitHub noreply address (`123+dependabot[bot]@users.noreply.github.com`), else None."""
    match = _NOREPLY.fullmatch(email) if isinstance(email, str) else None
    return match.group(1) if match else None


def whole(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def pages(gh, query: str, path, required: int = 0, **variables):
    """Yield the connection page found at `path` (keys from `data`) for each page, following `endCursor`.
    A missing connection ends the walk, except that the first `required` keys must exist (else NotFound)."""
    after = None
    while True:
        data = gh.graphql(query, after=after, **variables)
        conn = data
        for depth, key in enumerate(path):
            conn = conn.get(key) if isinstance(conn, dict) else None
            if conn is None and depth < required:
                raise NotFound(f"{key} not found")
        if not isinstance(conn, dict):
            return
        yield conn
        info = conn.get("pageInfo") or {}
        if not info.get("hasNextPage") or not info.get("endCursor"):
            return
        after = info["endCursor"]
