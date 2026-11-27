"""A fake `gh` for collector tests: routes each GraphQL call to canned data. Never touches the network."""
import json

from team_wrapped.github import GitHub

RATE = {"remaining": 4000, "resetAt": "2026-11-27T15:42:00Z"}


def page(nodes, cursor=None, total=None, **extra):
    """A connection page. `cursor` set means there is a next page."""
    conn = {"pageInfo": {"hasNextPage": cursor is not None, "endCursor": cursor}, "nodes": nodes, **extra}
    if total is not None:
        conn["totalCount"] = total
    return conn


def actor(login, typename="User"):
    return {"login": login, "__typename": typename} if login else None


def commit_node(oid, at="2026-03-14T09:30:00Z", login="ada-dev", name="Ada", email="ada@example.com",
                parents=1, additions=10, deletions=2, files=3, pr=None, typename="User"):
    return {"oid": oid, "committedDate": at, "authoredDate": at, "additions": additions, "deletions": deletions,
            "changedFilesIfAvailable": files, "parents": {"totalCount": parents},
            "author": {"name": name, "email": email, "user": actor(login, typename)},
            "associatedPullRequests": {"nodes": [{"number": pr}] if pr else []}}


def history(nodes, cursor=None):
    return {"rateLimit": RATE, "repository": {"defaultBranchRef": {"target": {"history": page(nodes, cursor)}}}}


def review_node(rid, login="grace-codes", state="APPROVED", at="2026-03-15T10:00:00Z", typename="User"):
    return {"databaseId": rid, "state": state, "submittedAt": at, "author": actor(login, typename)}


def comment_node(cid, login="grace-codes", at="2026-03-15T10:05:00Z", typename="User"):
    return {"databaseId": cid, "createdAt": at, "author": actor(login, typename)}


def review_comment_node(cid, reply_to=None, login="grace-codes", at="2026-03-15T10:05:00Z"):
    return {"databaseId": cid, "createdAt": at, "author": actor(login),
            "replyTo": {"databaseId": reply_to} if reply_to else None}


def thread(tid, comments, cursor=None):
    return {"id": tid, "comments": page(comments, cursor, total=len(comments) + (1 if cursor else 0))}


def pr_node(number, login="ada-dev", created="2026-03-14T09:30:00Z", merged="2026-03-16T09:00:00Z",
            state="MERGED", reviews=None, comments=None, threads=None, typename="User", **extra):
    reviews, comments, threads = reviews or page([], total=0), comments or page([], total=0), threads or page([])
    node = {"id": f"PR_{number}", "number": number, "author": actor(login, typename), "createdAt": created,
            "mergedAt": merged, "closedAt": merged, "state": state, "baseRefName": "main", "isDraft": False,
            "labels": {"nodes": [{"name": "feature"}]}, "commits": {"totalCount": 4}, "changedFiles": 5,
            "additions": 120, "deletions": 30, "reviews": reviews, "comments": comments, "reviewThreads": threads}
    node.update(extra)
    return node


def search(nodes, cursor=None, count=None):
    return {"rateLimit": RATE, "search": {"issueCount": len(nodes) if count is None else count, **page(nodes, cursor)}}


class FakeGh:
    """Runner for `GitHub`. `route(query, variables)` returns a data dict, or an (exit, stdout, stderr) tuple to fail."""

    def __init__(self, route):
        self.route = route
        self.calls = []

    def __call__(self, args):
        query, variables = None, {}
        for flag, value in zip(args[3::2], args[4::2]):
            key, _, text = value.partition("=")
            if key == "query":
                query = text
            else:
                variables[key] = int(text) if flag == "-F" and text.lstrip("-").isdigit() else text
        self.calls.append((query, variables))
        result = self.route(query, variables)
        if isinstance(result, tuple):
            return result
        return 0, json.dumps({"data": result}), ""


def make_client(route, **kwargs):
    fake = FakeGh(route)
    return GitHub(fake, sleep=lambda s: None, **kwargs), fake


def not_found(message="Could not resolve to a Repository with the name 'sample-org/sample-gone'."):
    return 1, json.dumps({"data": {"repository": None}, "errors": [{"type": "NOT_FOUND", "message": message}]}), \
        f"gh: {message}"


def rate_limited():
    return 1, json.dumps({"errors": [{"type": "RATE_LIMITED", "message": "API rate limit exceeded"}]}), \
        "gh: API rate limit exceeded"


def empty_routes(query, variables):
    """No activity anywhere."""
    if "history(" in query:
        return history([])
    if "search(" in query:
        return search([])
    raise AssertionError(query)
