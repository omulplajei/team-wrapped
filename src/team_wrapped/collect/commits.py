"""commits.jsonl from the default branch history (one GraphQL query per 100 commits, stats and co-authors
included)."""
from __future__ import annotations

from . import queries
from .common import actor_login, iso, noreply_login, pages, timestamp, whole


def _text(value) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def _git_actor(actor) -> dict | None:
    """{"login", "name", "email"} of a GitActor node (login None when unlinked), or None when it names nobody."""
    if not isinstance(actor, dict):
        return None
    name, email = _text(actor.get("name")), _text(actor.get("email"))
    login = actor_login(actor.get("user")) or noreply_login(email)
    return {"login": login, "name": name, "email": email} if login or name or email else None


def _identities(who: dict) -> set:
    """The keys an author is known by, for de-duplication: the login, else the email, else the name (lower-cased)."""
    keys = set()
    if who["login"]:
        keys.add(("login", who["login"].lower()))
    if who["email"]:
        keys.add(("email", who["email"].lower()))
    if not keys and who["name"]:
        keys.add(("name", who["name"]))
    return keys


def co_authors(node: dict, primary: dict) -> list:
    """Every author of `node` after the first (the `Co-authored-by:` trailers), without the primary author and
    without repeats. An author is a repeat when it shares a login or an email with one already kept."""
    authors = node.get("authors")
    nodes = authors.get("nodes") if isinstance(authors, dict) else None
    nodes = nodes[1:] if isinstance(nodes, list) else []
    seen = _identities(primary)
    found = []
    for actor in nodes:
        who = _git_actor(actor)
        if who is None or _identities(who) & seen:
            continue
        seen |= _identities(who)
        found.append(who)
    return found


def commit_record(repo: str, node: dict) -> dict | None:
    if not isinstance(node, dict) or not isinstance(node.get("oid"), str):
        return None
    author = node.get("author") or {}
    login = actor_login(author.get("user")) or noreply_login(author.get("email"))
    prs = ((node.get("associatedPullRequests") or {}).get("nodes") or [])
    number = prs[0].get("number") if prs and isinstance(prs[0], dict) else None
    record = {
        "repo": repo,
        "sha": node["oid"],
        "author_login": login,
        "author_name": author.get("name"),
        "author_email": author.get("email"),
        "authored_at": timestamp(node.get("authoredDate")),
        "committed_at": timestamp(node.get("committedDate")),
        "is_merge": ((node.get("parents") or {}).get("totalCount") or 0) > 1,
        "pr_number": number if whole(number) else None,
        "enriched": False,
    }
    primary = {"login": login, "name": _text(author.get("name")), "email": _text(author.get("email"))}
    stats = node.get("additions"), node.get("deletions"), node.get("changedFilesIfAvailable")
    if all(whole(v) for v in stats):
        record.update(enriched=True, additions=stats[0], deletions=stats[1], files_changed=stats[2])
    record["co_authors"] = co_authors(node, primary)
    return record


def fetch_commits(gh, org: str, repo: str, start, end, out: list) -> None:
    """Append the default-branch commits committed in [start, end] (UTC datetimes, either may be None) to `out`,
    page by page, so a caller that catches an error keeps what was fetched."""
    path = ("repository", "defaultBranchRef", "target", "history")
    for conn in pages(gh, queries.COMMITS, path, required=1, owner=org, name=repo, since=iso(start), until=iso(end),
                      first=queries.COMMIT_PAGE):
        for node in conn.get("nodes") or []:
            record = commit_record(repo, node)
            if record:
                out.append(record)
