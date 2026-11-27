"""Record builders for hand-written raw fixtures."""


def commit(sha="a1", login="ada-dev", email="ada@example.com", name="Ada", at="2026-03-14T09:30:00Z", **extra):
    return {"sha": sha, "author_login": login, "author_name": name, "author_email": email,
            "authored_at": at, "committed_at": at, "is_merge": False, "pr_number": None,
            "enriched": False, **extra}


def pull_request(number=1, login="ada-dev", created="2026-03-14T09:30:00Z", merged=None, **extra):
    return {"number": number, "author_login": login, "created_at": created, "merged_at": merged,
            "closed_at": merged, "state": "merged" if merged else "open", "base_branch": "main",
            "labels": [], "draft": False, "comment_count": 0, "review_count": 0, "enriched": False, **extra}


def review(pr=1, login="grace-codes", at="2026-03-15T10:00:00Z", **extra):
    return {"pr_number": pr, "reviewer_login": login, "state": "approved", "submitted_at": at, **extra}


def comment(pr=1, login="grace-codes", at="2026-03-15T10:05:00Z", cid=1, **extra):
    return {"pr_number": pr, "author_login": login, "kind": "review", "created_at": at,
            "comment_id": cid, "in_reply_to_id": None, "thread_root_id": cid, **extra}


ALL_COMPLETE = {"commits": "complete", "pull_requests": "complete", "reviews": "complete", "comments": "complete"}
