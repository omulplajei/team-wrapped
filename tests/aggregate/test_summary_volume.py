from aggregate_helpers import ALL_COMPLETE, comment, commit, pull_request, review

from team_wrapped.aggregate.delivery_volume import build_delivery_volume
from team_wrapped.aggregate.summary import build_summary

CONFIG = """org: sample-org
repos: [alpha-api, beta-web]
groups:
  alpha: [alpha-api]
since: 2026-01-01
until: 2026-12-31
timezone: Europe/Bucharest
"""


def setup(fx, status=ALL_COMPLETE, config=CONFIG):
    fx.config(config)
    for repo in ("alpha-api", "beta-web"):
        fx.status(repo, status)
    return fx


def test_totals_count_window_records_per_scope(fx):
    setup(fx)
    fx.raw("alpha-api", "commits.jsonl", [
        commit("a"), commit("m", is_merge=True), commit("bot", login="renovate[bot]"),
        commit("old", at="2025-12-31T22:30:00Z"),        # 00:30 on Jan 1 in Bucharest: inside
        commit("out", at="2025-12-31T21:30:00Z")])
    fx.raw("beta-web", "commits.jsonl", [commit("b")])
    fx.raw("alpha-api", "pull_requests.jsonl", [
        pull_request(1, merged="2026-04-01T10:00:00Z"), pull_request(2), pull_request(3, merged="2027-01-01T10:00:00Z")])
    fx.raw("alpha-api", "reviews.jsonl", [review(1), review(1, login="ada-dev"), review(99, login="ada-dev")])
    fx.raw("alpha-api", "comments.jsonl", [comment(1, login="ada-dev"), comment(1, cid=2, kind="conversation", thread_root_id=None)])
    scopes, partial = build_summary(fx.context())
    assert scopes["all"]["totals"] == {"commits": 5, "merged_prs": 1, "reviews": 2, "comments": 2}
    assert scopes["group:alpha"]["totals"] == {"commits": 4, "merged_prs": 1, "reviews": 2, "comments": 2}
    assert partial == []


def test_totals_only_for_enabled_metrics_and_partial_by_status(fx):
    setup(fx, config=CONFIG + "metrics: [commits, comments]\n")
    fx.status("beta-web", {"commits": "partial", "comments": "complete"})
    fx.raw("alpha-api", "commits.jsonl", [commit("a")])
    scopes, partial = build_summary(fx.context())
    assert scopes["all"]["totals"] == {"commits": 1, "comments": 0}
    assert scopes["group:alpha"]["totals"] == {"commits": 1, "comments": 0}
    assert partial == ["summary.totals"]


def test_totals_not_partial_when_only_a_disabled_metric_is_incomplete(fx):
    setup(fx, config=CONFIG + "metrics: [commits]\n")
    fx.status("beta-web", {"commits": "complete", "pull_requests": "failed"})
    assert build_summary(fx.context())[1] == []


def test_lines_sum_enriched_commits_and_are_partial_with_unenriched_ones(fx):
    setup(fx)
    fx.raw("alpha-api", "commits.jsonl", [
        commit("a", enriched=True, additions=100, deletions=30, files_changed=3),
        commit("m", is_merge=True, enriched=True, additions=5, deletions=0, files_changed=1),
        commit("u"),
        commit("old", at="2025-06-01T10:00:00Z", enriched=True, additions=999, deletions=999, files_changed=1)])
    fx.raw("beta-web", "commits.jsonl", [commit("b", enriched=True, additions=10, deletions=40, files_changed=2)])
    scopes, partial = build_delivery_volume(fx.context())
    assert scopes["all"]["lines"] == {"total_additions": 110, "total_deletions": 70, "total_net": 40}      # merge skipped
    assert scopes["group:alpha"]["lines"] == {"total_additions": 100, "total_deletions": 30, "total_net": 70}
    assert partial == ["delivery_volume.lines"]


def test_lines_complete_when_every_commit_is_enriched(fx):
    setup(fx)
    fx.raw("alpha-api", "commits.jsonl", [commit("a", enriched=True, additions=1, deletions=0, files_changed=1)])
    scopes, partial = build_delivery_volume(fx.context())
    assert scopes["all"]["lines"]["total_net"] == 1 and partial == []


def test_lines_omitted_not_zero_without_enriched_commits(fx):
    setup(fx)
    fx.raw("alpha-api", "commits.jsonl", [commit("a")])
    scopes, partial = build_delivery_volume(fx.context())
    assert scopes == {"all": {}, "group:alpha": {}}
    assert partial == ["delivery_volume.lines"]


def test_lines_absent_and_not_partial_when_commits_disabled_or_empty(fx):
    setup(fx, config=CONFIG + "metrics: [reviews]\n")
    assert build_delivery_volume(fx.context()) == ({"all": {}, "group:alpha": {}}, [])
    fx2 = setup(fx.__class__(fx.root.parent / "other"))
    scopes, partial = build_delivery_volume(fx2.context())
    assert scopes == {"all": {}, "group:alpha": {}} and partial == []


def test_lines_partial_when_commit_status_incomplete(fx):
    setup(fx)
    fx.status("beta-web", {"commits": "partial"})
    fx.raw("alpha-api", "commits.jsonl", [commit("a", enriched=True, additions=1, deletions=1, files_changed=1)])
    assert build_delivery_volume(fx.context())[1] == ["delivery_volume.lines"]


def test_own_reviews_are_excluded_through_aliases(fx):
    setup(fx, config=CONFIG + "aliases:\n  ada-old: ada-dev\n")
    fx.raw("alpha-api", "pull_requests.jsonl", [pull_request(1, login="ada-old", merged="2026-04-01T10:00:00Z")])
    fx.raw("alpha-api", "reviews.jsonl", [review(1, login="Ada-Dev"), review(1, login="grace-codes")])
    scopes, _ = build_summary(fx.context())
    assert scopes["all"]["totals"]["reviews"] == 1


def test_merge_commits_neither_add_lines_nor_make_the_dataset_partial(fx):
    setup(fx)
    fx.raw("alpha-api", "commits.jsonl", [
        commit("a", enriched=True, additions=10, deletions=2, files_changed=1),
        commit("m", is_merge=True),                                                    # no stats, merge: ignored
        commit("m2", is_merge=True, enriched=True, additions=500, deletions=500, files_changed=9)])
    scopes, partial = build_delivery_volume(fx.context())
    assert scopes["all"]["lines"] == {"total_additions": 10, "total_deletions": 2, "total_net": 8}
    assert partial == []


def test_only_merge_commits_means_no_lines_dataset(fx):
    setup(fx)
    fx.raw("alpha-api", "commits.jsonl", [commit("m", is_merge=True, enriched=True, additions=5, deletions=5, files_changed=1)])
    assert build_delivery_volume(fx.context()) == ({"all": {}, "group:alpha": {}}, [])


def test_enriched_must_be_the_boolean_true(fx):
    setup(fx)
    fx.raw("alpha-api", "commits.jsonl", [commit("a", enriched="false", additions=10, deletions=2, files_changed=1),
                                          commit("b", enriched=1, additions=10, deletions=2, files_changed=1)])
    scopes, partial = build_delivery_volume(fx.context())
    assert scopes == {"all": {}, "group:alpha": {}} and partial == ["delivery_volume.lines"]


def test_cheap_then_enriched_version_of_a_commit_counts_once(fx):
    setup(fx)
    fx.raw("alpha-api", "commits.jsonl", [commit("a"), commit("a", enriched=True, additions=3, deletions=1, files_changed=1)])
    scopes, partial = build_delivery_volume(fx.context())
    assert scopes["all"]["lines"]["total_additions"] == 3 and partial == []
