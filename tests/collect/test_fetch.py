"""Commit and pull request fetchers against canned GraphQL pages."""
import datetime

from collect_fakes import (comment_node, commit_node, history, make_client, page, pr_node, review_comment_node,
                           review_node, search, thread)

from team_wrapped.collect.commits import fetch_commits
from team_wrapped.collect.pull_requests import PullRequestBatch, fetch_pull_requests

UTC = datetime.timezone.utc
START = datetime.datetime(2025, 12, 31, 22, tzinfo=UTC)
END = datetime.datetime(2026, 12, 31, 21, 59, 59, tzinfo=UTC)
NOW = datetime.datetime(2026, 11, 27, 12, tzinfo=UTC)


def commits_route(query, variables):
    assert "history(" in query
    if variables.get("after") is None:
        return history([commit_node("a1", pr=7),
                        commit_node("m1", parents=2, at="2026-03-15T11:30:00+02:00"),
                        commit_node("u1", login=None, name="Unlinked", email="who@example.com")], cursor="C1")
    assert variables["after"] == "C1"
    return history([commit_node("b1", login=None, name="dependabot[bot]",
                                email="49699333+dependabot[bot]@users.noreply.github.com"),
                    commit_node("s1", files=None)])


def test_commits_paginate_and_map_fields():
    gh, fake = make_client(commits_route)
    records = []
    fetch_commits(gh, "sample-org", "sample-api", START, END, records)
    assert [r["sha"] for r in records] == ["a1", "m1", "u1", "b1", "s1"]
    query, variables = fake.calls[0]
    assert variables == {"owner": "sample-org", "name": "sample-api", "since": "2025-12-31T22:00:00Z",
                         "until": "2026-12-31T21:59:59Z", "first": 100}
    a1, m1, u1, b1, s1 = records
    assert a1 == {"repo": "sample-api", "sha": "a1", "author_login": "ada-dev", "author_name": "Ada",
                  "author_email": "ada@example.com", "authored_at": "2026-03-14T09:30:00Z",
                  "committed_at": "2026-03-14T09:30:00Z", "is_merge": False, "pr_number": 7, "enriched": True,
                  "additions": 10, "deletions": 2, "files_changed": 3}
    assert m1["is_merge"] is True and m1["authored_at"] == "2026-03-15T09:30:00Z"      # offsets become UTC
    assert u1["author_login"] is None and u1["author_email"] == "who@example.com"
    assert b1["author_login"] == "dependabot[bot]"        # GitHub noreply address of a bot
    assert s1["enriched"] is False and "additions" not in s1 and "files_changed" not in s1


def test_commits_of_an_empty_repository():
    gh, _ = make_client(lambda q, v: {"rateLimit": None, "repository": {"defaultBranchRef": None}})
    records = []
    fetch_commits(gh, "sample-org", "sample-empty", None, None, records)
    assert records == []


def test_bot_authors_get_the_bot_suffix():
    gh, _ = make_client(lambda q, v: history([commit_node("x", login="release-robot", typename="Bot")]))
    records = []
    fetch_commits(gh, "sample-org", "sample-api", None, None, records)
    assert records[0]["author_login"] == "release-robot[bot]"


def pr_route(query, variables):
    if "search(" in query:
        if variables.get("after") is None:
            return search([
                pr_node(1, reviews=page([review_node(11), review_node(12, state="DISMISSED"),
                                         review_node(13, login="renovate", typename="Bot", state="COMMENTED")], "R1", total=4),
                        comments=page([comment_node(21)], "K1", total=2),
                        threads=page([thread("T1", [review_comment_node(31), review_comment_node(32, reply_to=31)], "TC1")],
                                     "TH1")),
                {},                                                       # an issue: no PullRequest fields
            ], cursor="S1", count=3)
        return search([pr_node(2, state="OPEN", merged=None, login=None, isDraft=True)], count=3)
    pr_or_thread = variables["id"]
    if "reviews(" in query:
        assert pr_or_thread == "PR_1" and variables["after"] == "R1"
        return {"node": {"reviews": page([review_node(14, state="CHANGES_REQUESTED", at="2026-03-15T08:00:00+01:00"),
                                          review_node(15, state="PENDING", at=None)])}}
    if "reviewThreads(" in query:
        assert variables["after"] == "TH1"
        return {"node": {"reviewThreads": page([thread("T2", [review_comment_node(41, login="renovate")])])}}
    if "PullRequestReviewThread" in query:
        assert pr_or_thread == "T1" and variables["after"] == "TC1"
        return {"node": {"comments": page([review_comment_node(33, reply_to=31), review_comment_node(None)])}}
    assert "comments(" in query and variables["after"] == "K1"
    return {"node": {"comments": page([comment_node(22, login=None)])}}


def test_pull_requests_reviews_and_comments():
    gh, fake = make_client(pr_route)
    batch = PullRequestBatch()
    fetch_pull_requests(gh, "sample-org", "sample-api", START, END, batch, now=NOW)
    query, variables = fake.calls[0]
    assert variables["q"] == ("repo:sample-org/sample-api is:pr sort:created-asc created:<=2026-12-31T21:59:59Z "
                              "updated:>=2025-12-31T22:00:00Z")
    pr1, pr2 = batch.pull_requests
    assert pr1 == {"repo": "sample-api", "number": 1, "author_login": "ada-dev", "created_at": "2026-03-14T09:30:00Z",
                   "merged_at": "2026-03-16T09:00:00Z", "closed_at": "2026-03-16T09:00:00Z", "state": "merged",
                   "base_branch": "main", "labels": ["feature"], "draft": False, "comment_count": 2 + 4,
                   "review_count": 4, "enriched": True, "commit_count": 4, "changed_files": 5, "additions": 120,
                   "deletions": 30}
    assert pr2["state"] == "open" and pr2["author_login"] is None and pr2["draft"] is True
    assert [(r["review_id"], r["reviewer_login"], r["state"]) for r in batch.reviews] == [
        (11, "grace-codes", "approved"), (13, "renovate[bot]", "commented"), (14, "grace-codes", "changes_requested")]
    assert batch.reviews[2]["submitted_at"] == "2026-03-15T07:00:00Z"
    assert batch.reviews[0] == {"repo": "sample-api", "pr_number": 1, "review_id": 11, "reviewer_login": "grace-codes",
                                "state": "approved", "submitted_at": "2026-03-15T10:00:00Z"}
    by_id = {c["comment_id"]: c for c in batch.comments}
    assert sorted(by_id) == [21, 22, 31, 32, 33, 41]                  # the comment without an id is dropped
    assert by_id[21] == {"repo": "sample-api", "pr_number": 1, "author_login": "grace-codes", "kind": "conversation",
                         "created_at": "2026-03-15T10:05:00Z", "comment_id": 21, "in_reply_to_id": None,
                         "thread_root_id": None}
    assert by_id[22]["author_login"] is None
    assert (by_id[31]["kind"], by_id[31]["thread_root_id"], by_id[31]["in_reply_to_id"]) == ("review", 31, None)
    assert (by_id[32]["thread_root_id"], by_id[32]["in_reply_to_id"]) == (31, 31)
    assert (by_id[33]["thread_root_id"], by_id[33]["in_reply_to_id"]) == (31, 31)
    assert (by_id[41]["thread_root_id"], by_id[41]["author_login"]) == (41, "renovate")
    assert batch.notes == []


def test_more_than_1000_results_split_the_updated_range():
    seen = []

    def route(query, variables):
        q = variables["q"]
        seen.append(q)
        if "updated:>=" in q:
            return search([pr_node(1)], count=1500)
        lo, hi = q.split("updated:")[1].split("..")
        if lo.startswith("2025-12-31"):                     # the first half: still too many once, then fine
            return search([pr_node(2)], count=1200) if hi.startswith("2026-06") else search([pr_node(2)])
        return search([pr_node(3), pr_node(2)])
    gh, _ = make_client(route)
    batch = PullRequestBatch()
    fetch_pull_requests(gh, "sample-org", "sample-api", START, END, batch, now=NOW)
    assert sorted({pr["number"] for pr in batch.pull_requests}) == [2, 3]
    assert seen[1].endswith("updated:2025-12-31T22:00:00Z..2026-06-15T05:00:00Z")      # halves of [since, now]
    assert seen[2].endswith("updated:2025-12-31T22:00:00Z..2026-03-24T13:30:00Z")
    assert seen[3].endswith("updated:2026-03-24T13:30:01Z..2026-06-15T05:00:00Z")
    assert seen[4].endswith("updated:2026-06-15T05:00:01Z..2026-11-27T12:00:00Z")
    assert batch.notes == []


def test_a_range_that_cannot_be_split_is_noted():
    gh, _ = make_client(lambda q, v: search([pr_node(1)], count=5000))
    batch = PullRequestBatch()
    fetch_pull_requests(gh, "sample-org", "sample-api", NOW - datetime.timedelta(seconds=30), None, batch, now=NOW)
    assert batch.notes and "1000" in batch.notes[0]
    assert [pr["number"] for pr in batch.pull_requests] == [1]


def test_a_created_range_is_sent_and_kept_when_splitting():
    seen = []

    def route(query, variables):
        seen.append(variables["q"])
        return search([pr_node(5)], count=1500 if len(seen) == 1 else 1)
    gh, _ = make_client(route)
    batch = PullRequestBatch()
    created_from = datetime.datetime(2026, 6, 30, 21, tzinfo=UTC)
    fetch_pull_requests(gh, "sample-org", "sample-api", START, END, batch, now=NOW, created_from=created_from)
    assert seen[0] == ("repo:sample-org/sample-api is:pr sort:created-asc "
                       "created:2026-06-30T21:00:00Z..2026-12-31T21:59:59Z updated:>=2025-12-31T22:00:00Z")
    assert all("created:2026-06-30T21:00:00Z..2026-12-31T21:59:59Z updated:" in q for q in seen[1:])
    open_end = PullRequestBatch()
    fetch_pull_requests(gh, "sample-org", "sample-api", None, None, open_end, now=NOW, created_from=created_from)
    assert seen[-1] == "repo:sample-org/sample-api is:pr sort:created-asc created:>=2026-06-30T21:00:00Z"
