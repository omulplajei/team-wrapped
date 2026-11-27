from aggregate_helpers import ALL_COMPLETE, comment, commit, pull_request, review

from team_wrapped.aggregate.curiosities import build_curiosities

CONFIG = """org: sample-org
repos: [alpha-api, beta-web]
groups:
  alpha: [alpha-api]
since: 2026-01-01
until: 2026-12-31
timezone: Europe/Bucharest
"""


def setup(fx, config=CONFIG, status=ALL_COMPLETE):
    fx.config(config)
    for repo in ("alpha-api", "beta-web"):
        fx.status(repo, status)
    return fx


def run(fx, scope="all"):
    scopes, partial = build_curiosities(fx.context())
    return scopes[scope], partial


def pr(number, **extra):
    return pull_request(number, merged="2026-05-02T10:00:00Z", enriched=True, **extra)


def test_comment_curiosities(fx):
    setup(fx)
    fx.raw("alpha-api", "comments.jsonl", [
        comment(1, cid=1), comment(1, cid=2, in_reply_to_id=1, thread_root_id=1), comment(1, cid=3, in_reply_to_id=1, thread_root_id=1),
        comment(1, cid=4),                                                   # a second, shorter thread on PR 1
        comment(2, cid=5), comment(2, cid=6, in_reply_to_id=5, thread_root_id=5, at="2025-06-01T10:00:00Z"),  # outside window
        comment(3, cid=7, kind="conversation", thread_root_id=None), comment(3, cid=8, kind="conversation", thread_root_id=None),
        comment(3, cid=9, kind="conversation", thread_root_id=None), comment(3, cid=10, kind="conversation", thread_root_id=None)])
    data, partial = run(fx)
    assert data["longest_comment_chain"] == [{"value": 3, "repo": "alpha-api", "pr_number": 1},
                                             {"value": 1, "repo": "alpha-api", "pr_number": 2}]
    assert data["most_commented_pr"] == [{"value": 4, "repo": "alpha-api", "pr_number": 1},
                                         {"value": 4, "repo": "alpha-api", "pr_number": 3},
                                         {"value": 1, "repo": "alpha-api", "pr_number": 2}]
    assert partial == []


def test_ties_break_by_repo_then_number_and_top_n_applies(fx):
    setup(fx, CONFIG + "curiosities: {top_n: 2}\n")
    fx.raw("beta-web", "reviews.jsonl", [review(5, login="u1"), review(5, login="u2")])
    fx.raw("alpha-api", "reviews.jsonl", [review(9, login="u1"), review(9, login="u2"), review(2, login="u1"), review(2, login="u2")])
    data, _ = run(fx)
    assert data["most_reviewed_pr"] == [{"value": 2, "repo": "alpha-api", "pr_number": 2},
                                        {"value": 2, "repo": "alpha-api", "pr_number": 9}]
    assert run(fx, "group:alpha")[0]["most_reviewed_pr"][0]["repo"] == "alpha-api"


def test_reviews_exclude_the_pr_author_and_rounds_count_changes_requested(fx):
    setup(fx)
    fx.raw("alpha-api", "pull_requests.jsonl", [pull_request(1, login="ada-dev")])
    fx.raw("alpha-api", "reviews.jsonl", [
        review(1, login="ada-dev"), review(1, login="grace-codes", state="changes_requested"),
        review(1, login="grace-codes", state="changes_requested", at="2026-03-16T10:00:00Z"),
        review(1, login="linus", state="approved"),
        review(2, login="grace-codes")])
    data, partial = run(fx)
    assert data["most_reviewed_pr"][0] == {"value": 3, "repo": "alpha-api", "pr_number": 1}
    assert data["most_review_rounds_pr"] == [{"value": 2, "repo": "alpha-api", "pr_number": 1}]
    assert "curiosities.most_review_rounds_pr" not in partial


def test_pr_size_curiosities_use_enriched_prs_and_flag_gaps(fx):
    setup(fx)
    fx.raw("alpha-api", "pull_requests.jsonl", [
        pr(1, commit_count=4, changed_files=10, additions=100, deletions=20),
        pr(2, commit_count=9, changed_files=2, additions=5, deletions=500),
        pull_request(3, merged="2026-05-03T10:00:00Z"),                                     # not enriched
        pr(4, commit_count=0, changed_files=0, additions=0, deletions=0),                   # zero: never written
        pull_request(5, created="2024-01-01T10:00:00Z", merged="2024-01-02T10:00:00Z", enriched=True,
                     commit_count=99, changed_files=99, additions=99, deletions=99)])       # outside window
    data, partial = run(fx)
    assert data["most_commits_pr"] == [{"value": 9, "repo": "alpha-api", "pr_number": 2}, {"value": 4, "repo": "alpha-api", "pr_number": 1}]
    assert data["most_files_pr"][0] == {"value": 10, "repo": "alpha-api", "pr_number": 1}
    assert data["biggest_pr_by_lines"][0] == {"value": 505, "repo": "alpha-api", "pr_number": 2}
    assert data["most_lines_deleted_pr"][0] == {"value": 500, "repo": "alpha-api", "pr_number": 2}
    assert {"curiosities.most_commits_pr", "curiosities.most_files_pr", "curiosities.biggest_pr_by_lines",
            "curiosities.most_lines_deleted_pr"} <= set(partial)
    assert "curiosities.longest_lived_pr" not in partial


def test_pr_in_window_when_created_or_merged_inside(fx):
    setup(fx)
    fx.raw("alpha-api", "pull_requests.jsonl", [
        pull_request(1, created="2025-12-01T10:00:00Z", merged="2026-01-05T10:00:00Z", enriched=True, commit_count=3),
        pull_request(2, created="2026-12-30T10:00:00Z", merged="2027-01-05T10:00:00Z", enriched=True, commit_count=2)])
    data, partial = run(fx)
    assert [r["pr_number"] for r in data["most_commits_pr"]] == [1, 2]


def test_most_commits_complete_when_all_enriched(fx):
    setup(fx)
    fx.raw("alpha-api", "pull_requests.jsonl", [pr(1, commit_count=3)])
    assert "curiosities.most_commits_pr" not in run(fx)[1]


def test_longest_lived_pr_skips_open_and_counts_whole_days(fx):
    setup(fx)
    fx.raw("alpha-api", "pull_requests.jsonl", [
        pull_request(1, created="2026-03-01T12:00:00Z", merged="2026-03-11T11:00:00Z"),            # 9 days
        pull_request(2, created="2026-03-01T12:00:00Z", state="closed", closed_at="2026-03-04T12:00:00Z", merged_at=None),
        pull_request(3, created="2026-01-01T12:00:00Z"),                                           # open
        pull_request(4, created="2026-03-01T12:00:00Z", merged="2026-03-01T15:00:00Z")])           # 0 days
    data, partial = run(fx)
    assert data["longest_lived_pr"] == [{"value": 9, "repo": "alpha-api", "pr_number": 1},
                                        {"value": 3, "repo": "alpha-api", "pr_number": 2}]
    assert "curiosities.longest_lived_pr" not in partial


def test_biggest_commit(fx):
    setup(fx)
    fx.raw("alpha-api", "commits.jsonl", [
        commit("a", enriched=True, additions=10, deletions=5, files_changed=2),
        commit("b", enriched=True, additions=15, deletions=0, files_changed=7, at="2026-02-01T10:00:00Z"),
        commit("c", enriched=True, additions=0, deletions=0, files_changed=0),
        commit("u")])
    data, partial = run(fx)
    assert data["biggest_commit"] == [{"value": 15, "repo": "alpha-api", "sha": "b", "files": 7},     # earlier date wins
                                      {"value": 15, "repo": "alpha-api", "sha": "a", "files": 2}]
    assert "curiosities.biggest_commit" in partial


def test_busiest_day_and_month_use_local_dates(fx):
    setup(fx)
    fx.raw("alpha-api", "commits.jsonl", [
        commit("a", at="2026-03-14T09:30:00Z"), commit("b", at="2026-03-14T20:00:00Z"),
        commit("c", at="2026-03-14T22:30:00Z"),                                  # 00:30 on the 15th locally
        commit("d", at="2026-04-02T09:00:00Z")])
    fx.raw("beta-web", "commits.jsonl", [commit("e", at="2026-03-14T08:00:00Z")])
    fx.raw("alpha-api", "pull_requests.jsonl", [pull_request(1, merged="2026-03-14T10:00:00Z"), pull_request(2, merged="2026-03-20T10:00:00Z")])
    fx.raw("beta-web", "pull_requests.jsonl", [pull_request(3, merged="2026-03-14T11:00:00Z")])
    data, partial = run(fx)
    assert data["busiest_day"][0] == {"value": 3, "date": "2026-03-14", "merged_prs": 2}
    assert data["busiest_day"][1] == {"value": 1, "date": "2026-03-15", "merged_prs": 0}
    assert data["busiest_month"] == [{"value": 4, "month": "2026-03", "merged_prs": 3},
                                     {"value": 1, "month": "2026-04", "merged_prs": 0}]
    group = run(fx, "group:alpha")[0]
    assert group["busiest_day"][0] == {"value": 2, "date": "2026-03-14", "merged_prs": 1}
    assert not {"curiosities.busiest_day", "curiosities.busiest_month"} & set(partial)


def test_streaks_pick_runs_and_the_earliest_on_ties(fx):
    setup(fx)
    days = ["2026-03-10", "2026-03-11", "2026-03-12", "2026-05-01", "2026-05-02", "2026-05-03", "2026-07-01", "2026-12-31", "2025-12-31"]
    fx.raw("alpha-api", "commits.jsonl", [commit(d, at=f"{d}T10:00:00Z") for d in days])
    fx.raw("alpha-api", "pull_requests.jsonl", [pull_request(i, merged=f"2026-06-0{i}T10:00:00Z") for i in (1, 2)])
    data, _ = run(fx)
    assert data["longest_commit_streak"][:2] == [{"value": 3, "from": "2026-03-10", "to": "2026-03-12"},
                                                 {"value": 3, "from": "2026-05-01", "to": "2026-05-03"}]
    assert data["longest_commit_streak"][-1]["value"] == 1
    assert data["longest_merge_streak"] == [{"value": 2, "from": "2026-06-01", "to": "2026-06-02"}]


def test_empty_datasets_are_omitted_and_disabled_metrics_skip_curiosities(fx):
    setup(fx, CONFIG + "metrics: [commits, reviews]\n")
    fx.raw("alpha-api", "commits.jsonl", [commit("a")])
    data, partial = run(fx)
    assert set(data) == {"longest_commit_streak"}               # busiest_* need pull_requests too
    assert partial == ["curiosities.biggest_commit"]      # the commit is not enriched


def test_status_makes_curiosities_partial(fx):
    setup(fx)
    fx.status("beta-web", {"comments": "failed", "commits": "complete", "pull_requests": "complete", "reviews": "complete"})
    fx.raw("alpha-api", "comments.jsonl", [comment(1)])
    _, partial = run(fx)
    assert partial == ["curiosities.longest_comment_chain", "curiosities.most_commented_pr"]
