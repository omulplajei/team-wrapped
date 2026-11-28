"""The contributor registry (spec section 6): who was active inside the window. No emails reach the output."""
from __future__ import annotations

import re

from .common import Resolver, incomplete
from .context import Context
from .raw import ACTIVITY_FIELDS

PLACEHOLDER_AVATAR = "avatars/placeholder.png"
_KIND_ORDER = {"human": 0, "unlinked": 1, "bot": 2}
# metric -> (login field, email field, name field)
_AUTHOR_FIELDS = {
    "commits": ("author_login", "author_email", "author_name"),
    "pull_requests": ("author_login", None, None),
    "reviews": ("reviewer_login", None, None),
    "comments": ("author_login", None, None),
}


def bot_matcher(patterns):
    """Case-insensitive glob matcher. Only `*` and `?` are wildcards: unlike fnmatch, brackets are literal,
    so `*[bot]` means a login ending in `[bot]` and not one ending in b, o or t."""
    compiled = []
    for pattern in patterns:
        regex = "".join(".*" if c == "*" else "." if c == "?" else re.escape(c) for c in pattern)
        compiled.append(re.compile(regex, re.IGNORECASE | re.DOTALL))
    return lambda login: any(rx.fullmatch(login) for rx in compiled)


def avatar_name(login: str) -> str:
    """File stem the collector uses for a login: `dependabot[bot]` is `dependabot_bot`."""
    return re.sub(r"[^A-Za-z0-9._-]", "_", login.replace("]", ""))


def bot_name(login: str) -> str:
    """Display name of a bot: its login without the trailing `[bot]` (`sample-bot[bot]` is `sample-bot`)."""
    return login[:-5] if login.lower().endswith("[bot]") and len(login) > 5 else login


def _activity(ctx: Context):
    """-> {key: {"logins": set, "repos": {repo: [first, last]}}}, from activity inside the window."""
    resolver = Resolver(ctx.config.aliases)
    people: dict = {}
    for metric in ctx.metrics:
        login_f, email_f, name_f = _AUTHOR_FIELDS[metric]
        for record in ctx.records(metric):
            dates = [d for d in (ctx.window.date_in_window(record.get(f)) for f in ACTIVITY_FIELDS[metric]) if d]
            if not dates:
                continue
            who = resolver.resolve(record.get(login_f), record.get(email_f) if email_f else None,
                                   record.get(name_f) if name_f else None)
            if who is None:
                continue
            key, login = who
            person = people.setdefault(key, {"logins": set(), "repos": {}})
            if login:
                person["logins"].add(login)
            span = person["repos"].setdefault(record["repo"], [min(dates), max(dates)])
            span[0], span[1] = min(span[0], min(dates)), max(span[1], max(dates))
    return people


def _avatar(ctx: Context, login) -> str:
    if login:
        for stem in (avatar_name(login), avatar_name(login.lower())):
            if (ctx.data_root / "avatars" / f"{stem}.png").is_file():
                return f"avatars/{stem}.png"
    return PLACEHOLDER_AVATAR


def _sort_key(key, person, is_bot):
    login = min(person["logins"]) if person["logins"] else None
    kind = "unlinked" if login is None else "bot" if is_bot(login) else "human"
    return _KIND_ORDER[kind], (login or "").lower(), key


def build_contributors(ctx: Context):
    """-> (scopes, partial dataset names). Ids are sequential (`c001`, ...) in the deterministic sort order, assigned
    once over everyone so a person keeps the id in every scope; nothing in them is derived from an email or name.
    The dataset is partial when any in-scope repository's status for an enabled metric is not complete."""
    is_bot = bot_matcher(ctx.config.bot_patterns)
    groups_of = {}
    for group, members in ctx.group_repos.items():
        for repo in members:
            groups_of.setdefault(repo, set()).add(group)
    people = _activity(ctx)
    ids = {}
    for rank, key in enumerate(sorted(people, key=lambda k: _sort_key(k, people[k], is_bot)), 1):
        ids[key] = f"c{rank:03d}"
    scopes, partial = {}, False
    for scope, repos in ctx.scopes.items():
        in_scope = set(repos)
        entries = []
        for key, person in people.items():
            spans = {r: s for r, s in person["repos"].items() if r in in_scope}
            if not spans:
                continue
            login = min(person["logins"]) if person["logins"] else None
            kind = "unlinked" if login is None else "bot" if is_bot(login) else "human"
            entry = {"id": ids[key]}
            if login:
                entry["login"] = login
            if kind == "bot":                # only bots: a person's name never reaches derived/
                entry["name"] = bot_name(login)
            entry.update({
                "kind": kind,
                "avatar_file": _avatar(ctx, login),
                "repos": sorted(spans),
                "groups": sorted({g for r in spans for g in groups_of.get(r, ())}),
                "first_activity": min(s[0] for s in spans.values()).isoformat(),
                "last_activity": max(s[1] for s in spans.values()).isoformat(),
            })
            entries.append(entry)
        entries.sort(key=lambda e: e["id"])
        by_kind = {kind: sum(1 for e in entries if e["kind"] == kind) for kind in _KIND_ORDER}
        scopes[scope] = {"total": len(entries), "by_kind": by_kind, "list": entries}
        partial = partial or incomplete(ctx, repos, ctx.metrics)
    return scopes, ["contributors"] if partial else []
