"""commits.jsonl from the default branch history (one GraphQL query per 100 commits, stats included)."""
from __future__ import annotations

from . import queries
from .common import actor_login, iso, noreply_login, pages, timestamp, whole


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
    stats = node.get("additions"), node.get("deletions"), node.get("changedFilesIfAvailable")
    if all(whole(v) for v in stats):
        record.update(enriched=True, additions=stats[0], deletions=stats[1], files_changed=stats[2])
    return record


def fetch_commits(gh, org: str, repo: str, start, end, out: list) -> None:
    """Append the default-branch commits committed in [start, end] (UTC datetimes, either may be None) to `out`,
    page by page, so a caller that catches an error keeps what was fetched."""
    path = ("repository", "defaultBranchRef", "target", "history")
    for conn in pages(gh, queries.COMMITS, path, required=1, owner=org, name=repo, since=iso(start), until=iso(end), first=100):
        for node in conn.get("nodes") or []:
            record = commit_record(repo, node)
            if record:
                out.append(record)
