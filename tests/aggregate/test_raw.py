import json

from team_wrapped.aggregate.raw import load_raw
from team_wrapped.config import load_config

from aggregate_helpers import comment, commit, pull_request, review


def load(fx):
    return load_raw(fx.root, load_config(fx.root / "config.yml"))


def test_records_are_loaded_per_metric_with_repo_filled(fx):
    fx.raw("alpha-api", "commits.jsonl", [commit("a"), commit("b")])
    fx.raw("beta-web", "commits.jsonl", [commit("c")])
    fx.raw("beta-web", "pull_requests.jsonl", [pull_request()])
    fx.raw("beta-web", "reviews.jsonl", [review()])
    fx.raw("beta-web", "comments.jsonl", [comment()])
    raw = load(fx)
    assert [(r["repo"], r["sha"]) for r in raw.records["commits"]] == [("alpha-api", "a"), ("alpha-api", "b"), ("beta-web", "c")]
    assert [len(raw.records[m]) for m in ("pull_requests", "reviews", "comments")] == [1, 1, 1]
    assert raw.records["reviews"][0]["repo"] == "beta-web"
    assert raw.corrupt == {}


def test_a_wrong_repo_field_is_overwritten_by_the_folder(fx):
    fx.raw("alpha-api", "commits.jsonl", [{**commit(), "repo": "somewhere-else"}])
    assert load(fx).records["commits"][0]["repo"] == "alpha-api"


def test_blank_and_corrupt_lines_are_skipped_and_counted(fx):
    fx.raw("alpha-api", "commits.jsonl", [commit("a"), "", "   ", '{"sha": "half', "[1, 2]", "not json", commit("b")])
    raw = load(fx)
    assert [r["sha"] for r in raw.records["commits"]] == ["a", "b"]
    assert raw.corrupt == {"alpha-api/commits.jsonl": 3}        # blanks are not corrupt


def test_missing_files_are_fine(fx):
    raw = load(fx)
    assert raw.records == {"commits": [], "pull_requests": [], "reviews": [], "comments": []}


def test_disabled_metrics_are_not_read(fx):
    fx.config("org: o\nrepos: [alpha-api]\nmetrics: [commits]\n")
    fx.raw("alpha-api", "reviews.jsonl", [review()])
    fx.status("alpha-api", {"commits": "complete"})
    raw = load(fx)
    assert list(raw.records) == ["commits"]
    assert raw.status == {"alpha-api": {"commits": "complete"}}


def test_no_status_file_means_never_run_for_every_metric_even_with_data(fx):
    fx.raw("alpha-api", "commits.jsonl", [commit()])
    raw = load(fx)
    assert raw.status["alpha-api"] == {m: "never-run" for m in ("commits", "pull_requests", "reviews", "comments")}
    assert raw.status["beta-web"] == raw.status["alpha-api"]


def test_status_file_values_are_used(fx):
    fx.status("alpha-api", {"commits": "partial", "pull_requests": "failed", "reviews": "never-run", "comments": "complete"})
    assert load(fx).status["alpha-api"] == {"commits": "partial", "pull_requests": "failed",
                                            "reviews": "never-run", "comments": "complete"}


def test_metric_missing_from_status_is_complete_only_if_jsonl_exists(fx):
    fx.status("alpha-api", {"commits": "partial"})
    fx.raw("alpha-api", "reviews.jsonl", [review()])
    assert load(fx).status["alpha-api"] == {"commits": "partial", "pull_requests": "never-run",
                                            "reviews": "complete", "comments": "never-run"}


def test_unknown_status_value_counts_as_failed(fx):
    fx.status("alpha-api", {"commits": "done-ish"})
    assert load(fx).status["alpha-api"]["commits"] == "failed"


def test_corrupt_status_file_is_never_run_and_reported(fx):
    fx.status("alpha-api", "{nope")
    fx.status("beta-web", "[1]")
    raw = load(fx)
    assert raw.status["alpha-api"]["commits"] == "never-run"
    assert raw.corrupt == {"alpha-api/status.json": 1, "beta-web/status.json": 1}


def test_loading_never_writes_to_raw(fx):
    fx.raw("alpha-api", "commits.jsonl", [commit(), "junk"])
    fx.status("alpha-api", {"commits": "complete"})
    before = {p: p.read_bytes() for p in (fx.root / "raw").rglob("*") if p.is_file()}
    load(fx)
    after = {p: p.read_bytes() for p in (fx.root / "raw").rglob("*") if p.is_file()}
    assert before == after
    assert json.loads((fx.root / "raw/alpha-api/status.json").read_text()) == {"commits": "complete"}


def test_duplicate_commits_keep_the_last_record_at_the_first_position(fx):
    fx.raw("alpha-api", "commits.jsonl", [commit("a"), commit("b"), commit("a", enriched=True, additions=4, deletions=1)])
    fx.raw("beta-web", "commits.jsonl", [commit("a")])                 # same sha, other repo: kept
    commits = load(fx).records["commits"]
    assert [(r["repo"], r["sha"], r["enriched"]) for r in commits] == [
        ("alpha-api", "a", True), ("alpha-api", "b", False), ("beta-web", "a", False)]


def test_duplicate_pull_requests_keep_the_enriched_last_version(fx):
    fx.raw("alpha-api", "pull_requests.jsonl", [pull_request(1), pull_request(2),
                                                pull_request(1, enriched=True, commit_count=3)])
    prs = load(fx).records["pull_requests"]
    assert [(r["number"], r["enriched"]) for r in prs] == [(1, True), (2, False)]


def test_duplicate_comments_are_keyed_by_comment_id(fx):
    fx.raw("alpha-api", "comments.jsonl", [comment(cid=1), comment(cid=2), comment(cid=1, at="2026-03-16T10:00:00Z"), comment(cid="x")])
    comments = load(fx).records["comments"]
    assert [(r["comment_id"], r["created_at"][:10]) for r in comments] == [
        (1, "2026-03-16"), (2, "2026-03-15"), ("x", "2026-03-15")]


def test_duplicate_reviews_use_review_id_or_fall_back_to_the_content_key(fx):
    fx.raw("alpha-api", "reviews.jsonl", [
        review(review_id=7, state="commented"), review(review_id=8), review(review_id=7),
        review(pr=2), review(pr=2), review(pr=2, state="commented")])
    reviews = load(fx).records["reviews"]
    assert [(r.get("review_id"), r["pr_number"], r["state"]) for r in reviews] == [
        (7, 1, "approved"), (8, 1, "approved"), (None, 2, "approved"), (None, 2, "commented")]


def test_records_with_invalid_keys_are_corrupt_and_never_crash(fx):
    fx.raw("alpha-api", "commits.jsonl", [commit("a"), {**commit(), "sha": ["x"]}, {**commit(), "sha": 5}])
    fx.raw("alpha-api", "pull_requests.jsonl", [pull_request(1), {**pull_request(), "number": [1]},
                                                {**pull_request(), "number": "1"}, {**pull_request(), "number": True}])
    fx.raw("alpha-api", "reviews.jsonl", [review(), review(review_id=[1]), {**review(), "pr_number": {"a": 1}},
                                          {**review(), "reviewer_login": ["x"]}])
    fx.raw("alpha-api", "comments.jsonl", [comment(), comment(cid=[1]), comment(cid=2, thread_root_id={"a": 1}),
                                           comment(cid=3, in_reply_to_id=[1]), comment(cid=4, in_reply_to_id="9")])
    raw = load(fx)
    assert [len(raw.records[m]) for m in ("commits", "pull_requests", "reviews", "comments")] == [1, 1, 1, 2]
    assert raw.corrupt == {"alpha-api/commits.jsonl": 2, "alpha-api/pull_requests.jsonl": 3,
                           "alpha-api/reviews.jsonl": 3, "alpha-api/comments.jsonl": 3}
