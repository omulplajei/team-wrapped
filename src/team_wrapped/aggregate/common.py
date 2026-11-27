"""Helpers shared by the statistic families (summary, delivery_volume, curiosities)."""
from __future__ import annotations

from .context import Context


def incomplete(ctx: Context, repos, metrics) -> bool:
    """True when any in-scope repository's status for any of `metrics` is not `complete`. A metric that is
    disabled has no status and does not count."""
    return any(ctx.raw.status[repo][metric] != "complete"
               for repo in repos for metric in metrics if metric in ctx.metrics)


def _text(value):
    return value.strip() if isinstance(value, str) and value.strip() else None


class Resolver:
    """Maps the author fields of a record to one identity, applying `aliases` (alias -> canonical login)."""

    def __init__(self, aliases):
        self.aliases = {str(k).strip().lower(): v for k, v in aliases.items()}

    def resolve(self, login, email, name):
        """(identity key, login or None), or None when the record names nobody. Keys are type-prefixed
        (`login:`, `email:`, `name:`) so an unlinked author named like a login never merges into it. A login alias
        applies to a login; an email alias applies only when the record has no login."""
        login, email, name = _text(login), _text(email), _text(name)
        if login:
            login = self.aliases.get(login.lower()) or login
        elif email and self.aliases.get(email.lower()):
            login = self.aliases[email.lower()]
        if login:
            return f"login:{login.lower()}", login
        if email:
            return f"email:{email.lower()}", None
        return (f"name:{name}", None) if name else None

    def login_key(self, login):
        """Lower-cased canonical login of a login field, or None."""
        who = self.resolve(login, None, None)
        return who[1].lower() if who else None


def pr_authors(ctx: Context, resolver: Resolver) -> dict:
    """(repo, PR number) -> lower-cased canonical author login, for every known pull request (not window-filtered)."""
    return {(pr["repo"], pr.get("number")): resolver.login_key(pr.get("author_login"))
            for pr in ctx.records("pull_requests") if resolver.login_key(pr.get("author_login"))}


def is_own_review(review: dict, authors: dict, resolver: Resolver) -> bool:
    """A review written by the PR's own author (aliases resolved). Unknown PRs and missing logins are never "own"."""
    login = resolver.login_key(review.get("reviewer_login"))
    author = authors.get((review["repo"], review.get("pr_number")))
    return login is not None and author is not None and login == author


def whole_number(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)
