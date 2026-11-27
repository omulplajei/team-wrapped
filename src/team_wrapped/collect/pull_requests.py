"""pull_requests.jsonl, reviews.jsonl and comments.jsonl from one search over the repository's pull requests.

The search returns each pull request with its first reviews, conversation comments and review threads inlined;
longer connections are completed with `node(id:)` follow-ups, so every record of a pull request is complete
before it is kept. GitHub search returns at most 1000 results per query: a larger result splits the `updated`
range in halves until each half fits."""
from __future__ import annotations

import datetime
from dataclasses import dataclass, field

from . import queries
from .common import actor_login, iso, pages, timestamp, whole

GITHUB_EPOCH = datetime.datetime(2008, 1, 1, tzinfo=datetime.timezone.utc)
SEARCH_CAP = 1000
_MIN_SPLIT = datetime.timedelta(minutes=1)
_PR_STATES = {"OPEN": "open", "CLOSED": "closed", "MERGED": "merged"}
_REVIEW_STATES = {"APPROVED": "approved", "CHANGES_REQUESTED": "changes_requested", "COMMENTED": "commented"}


@dataclass
class PullRequestBatch:
    """What a fetch produced so far. `notes` explain anything known to be missing (the data is then partial)."""
    pull_requests: list = field(default_factory=list)
    reviews: list = field(default_factory=list)
    comments: list = field(default_factory=list)
    notes: list = field(default_factory=list)
    seen: set = field(default_factory=set)


def _rest(gh, query: str, node_id: str, key: str, conn: dict) -> list:
    """All nodes of a connection: the inlined page plus follow-up pages when it has more."""
    nodes = list(conn.get("nodes") or [])
    info = conn.get("pageInfo") or {}
    if info.get("hasNextPage") and info.get("endCursor") and node_id:
        after = info["endCursor"]
        while after:
            data = gh.graphql(query, id=node_id, after=after, first=queries.FOLLOW_UP_PAGE)
            page = ((data.get("node") or {}).get(key)) or {}
            nodes.extend(page.get("nodes") or [])
            more = page.get("pageInfo") or {}
            after = more.get("endCursor") if more.get("hasNextPage") else None
    return [n for n in nodes if isinstance(n, dict)]


def _review(repo, number, node):
    state = _REVIEW_STATES.get(node.get("state"))
    if state is None:                    # DISMISSED and PENDING are not reviews the team gave
        return None
    record = {"repo": repo, "pr_number": number}
    if whole(node.get("databaseId")):
        record["review_id"] = node["databaseId"]
    record.update(reviewer_login=actor_login(node.get("author")), state=state,
                  submitted_at=timestamp(node.get("submittedAt")))
    return record


def _comment(repo, number, node, kind, root=None):
    if not whole(node.get("databaseId")):
        return None
    reply = (node.get("replyTo") or {}).get("databaseId") if kind == "review" else None
    return {"repo": repo, "pr_number": number, "author_login": actor_login(node.get("author")), "kind": kind,
            "created_at": timestamp(node.get("createdAt")), "comment_id": node["databaseId"],
            "in_reply_to_id": reply if whole(reply) else None, "thread_root_id": root}


def _pull_request(gh, repo: str, node: dict, batch: PullRequestBatch) -> None:
    number, node_id = node["number"], node.get("id")
    reviews = _rest(gh, queries.PR_REVIEWS, node_id, "reviews", node.get("reviews") or {})
    conversation = _rest(gh, queries.PR_COMMENTS, node_id, "comments", node.get("comments") or {})
    threads = _rest(gh, queries.PR_THREADS, node_id, "reviewThreads", node.get("reviewThreads") or {})
    comments = [c for c in (_comment(repo, number, n, "conversation") for n in conversation) if c]
    review_comment_total = 0
    for thread in threads:
        conn = thread.get("comments") or {}
        nodes = _rest(gh, queries.THREAD_COMMENTS, thread.get("id"), "comments", conn)
        review_comment_total += conn.get("totalCount") if whole(conn.get("totalCount")) else len(nodes)
        root = nodes[0].get("databaseId") if nodes and whole(nodes[0].get("databaseId")) else None
        comments += [c for c in (_comment(repo, number, n, "review", root) for n in nodes) if c]
    record = {
        "repo": repo, "number": number, "author_login": actor_login(node.get("author")),
        "created_at": timestamp(node.get("createdAt")), "merged_at": timestamp(node.get("mergedAt")),
        "closed_at": timestamp(node.get("closedAt")), "state": _PR_STATES.get(node.get("state"), "open"),
        "base_branch": node.get("baseRefName"),
        "labels": [l["name"] for l in ((node.get("labels") or {}).get("nodes") or []) if isinstance(l, dict) and l.get("name")],
        "draft": bool(node.get("isDraft")),
        "comment_count": _total(node.get("comments"), len(conversation)) + review_comment_total,
        "review_count": _total(node.get("reviews"), len(reviews)),
        "enriched": True,
    }
    enrichment = {"commit_count": (node.get("commits") or {}).get("totalCount"), "changed_files": node.get("changedFiles"),
                  "additions": node.get("additions"), "deletions": node.get("deletions")}
    if all(whole(v) for v in enrichment.values()):
        record.update(enrichment)
    else:
        record["enriched"] = False
    batch.pull_requests.append(record)
    batch.reviews += [r for r in (_review(repo, number, n) for n in reviews) if r]
    batch.comments += comments
    batch.seen.add(number)


def _total(conn, fallback: int) -> int:
    total = (conn or {}).get("totalCount")
    return total if whole(total) else fallback


def _search_text(org, repo, end, lo, hi) -> str:
    parts = [f"repo:{org}/{repo}", "is:pr", "sort:created-asc"]
    if end:
        parts.append(f"created:<={iso(end)}")
    if lo and hi:
        parts.append(f"updated:{iso(lo)}..{iso(hi)}")
    elif lo:
        parts.append(f"updated:>={iso(lo)}")
    return " ".join(parts)


def _search(gh, org, repo, end, lo, hi, batch: PullRequestBatch, now) -> None:
    text = _search_text(org, repo, end, lo, hi)
    for index, conn in enumerate(pages(gh, queries.SEARCH_PULL_REQUESTS, ("search",), required=1, q=text,
                                       first=queries.SEARCH_PAGE)):
        if index == 0 and whole(conn.get("issueCount")) and conn["issueCount"] > SEARCH_CAP:
            low, high = lo or GITHUB_EPOCH, hi or now
            if high - low > _MIN_SPLIT:
                middle = (low + (high - low) / 2).replace(microsecond=0)
                _search(gh, org, repo, end, low, middle, batch, now)
                _search(gh, org, repo, end, middle + datetime.timedelta(seconds=1), high, batch, now)
                return
            batch.notes.append(f"{conn['issueCount']} pull requests updated between {iso(low)} and {iso(high)}: "
                               f"search returns only the first {SEARCH_CAP}")
        for node in conn.get("nodes") or []:
            if isinstance(node, dict) and whole(node.get("number")) and node["number"] not in batch.seen:
                _pull_request(gh, repo, node, batch)


def fetch_pull_requests(gh, org: str, repo: str, start, end, batch: PullRequestBatch, now=None) -> None:
    """Fill `batch` with the pull requests created by `end` and updated since `start` (UTC datetimes, either may
    be None), with their reviews and comments. The aggregator applies the exact window."""
    now = now or datetime.datetime.now(datetime.timezone.utc)
    _search(gh, org, repo, end, start, None, batch, now)
