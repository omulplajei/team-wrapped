import datetime
import json

import pytest

from aggregate_helpers import comment, commit, pull_request, review

from team_wrapped.aggregate import io as agg_io
from team_wrapped.aggregate.meta import build_meta
from team_wrapped.aggregate.repos import build_repos

CONFIG = """org: sample-org
repos: [zeta, alpha, Mid]
groups:
  g1: [zeta, alpha]
  g2: [Mid]
since: 2026-01-01
until: 2026-12-31
"""
ALL_COMPLETE = {m: "complete" for m in ("commits", "pull_requests", "reviews", "comments")}


def complete(fx, *repos):
    for repo in repos:
        fx.status(repo, ALL_COMPLETE)


def touched(scopes, scope="all"):
    return [r["name"] for r in scopes[scope]["touched"]["list"]]


def test_touched_is_alphabetical_per_scope_and_total_matches(fx):
    fx.config(CONFIG)
    complete(fx, "zeta", "alpha", "Mid")
    for repo in ("zeta", "alpha", "Mid"):
        fx.raw(repo, "commits.jsonl", [commit(at="2026-05-05T10:00:00Z")])
    scopes, partial = build_repos(fx.context())
    assert touched(scopes) == ["alpha", "Mid", "zeta"]
    assert touched(scopes, "group:g1") == ["alpha", "zeta"]
    assert all(s["touched"]["total"] == len(s["touched"]["list"]) for s in scopes.values())
    assert partial == []


def test_each_metric_can_touch_a_repo_and_bots_count(fx):
    fx.config(CONFIG)
    complete(fx, "zeta", "alpha", "Mid")
    fx.raw("zeta", "commits.jsonl", [commit(login="x[bot]")])
    fx.raw("alpha", "pull_requests.jsonl", [pull_request(created="2025-12-01T00:00:00Z", merged="2026-01-02T00:00:00Z")])
    fx.raw("Mid", "reviews.jsonl", [review()])
    scopes, _ = build_repos(fx.context())
    assert touched(scopes) == ["alpha", "Mid", "zeta"]
    fx.raw("Mid", "reviews.jsonl", [])
    fx.raw("Mid", "comments.jsonl", [comment()])
    assert touched(build_repos(fx.context())[0]) == ["alpha", "Mid", "zeta"]


def test_activity_outside_the_window_or_in_disabled_metrics_does_not_touch(fx):
    fx.config(CONFIG + "metrics: [commits]\n")
    complete(fx, "zeta", "alpha", "Mid")
    fx.raw("zeta", "commits.jsonl", [commit(at="2025-12-31T23:59:59Z")])
    fx.raw("alpha", "commits.jsonl", [commit(at="2026-12-31T23:59:59Z")])
    fx.raw("Mid", "reviews.jsonl", [review()])
    scopes, _ = build_repos(fx.context())
    assert touched(scopes) == ["alpha"]
    assert touched(scopes, "group:g2") == []
    assert scopes["group:g2"]["touched"] == {"total": 0, "list": []}


def test_partial_when_an_in_scope_repo_is_not_complete_for_an_enabled_metric(fx):
    fx.config(CONFIG)
    complete(fx, "zeta", "alpha")                       # Mid has no status: never-run
    _, partial = build_repos(fx.context())
    assert partial == ["repos.touched"]
    fx.config(CONFIG + "metrics: [commits]\n")
    fx.status("Mid", {"commits": "complete", "reviews": "failed"})
    assert build_repos(fx.context())[1] == []           # failed metric is disabled, so it does not matter


@pytest.mark.parametrize("state", ["partial", "failed", "never-run"])
def test_each_incomplete_state_marks_partial(fx, state):
    fx.config(CONFIG)
    complete(fx, "zeta", "Mid")
    fx.status("alpha", {**ALL_COMPLETE, "comments": state})
    assert build_repos(fx.context())[1] == ["repos.touched"]


NOW = datetime.datetime(2026, 12, 31, 23, 0, tzinfo=datetime.timezone.utc)


def test_meta_shape(fx):
    fx.config(CONFIG)
    complete(fx, "zeta")
    fx.status("alpha", {"commits": "partial"})
    fx.raw("zeta", "commits.jsonl", [commit(enriched=True), commit("b"), commit("c"), commit("d", enriched=True)])
    fx.raw("zeta", "pull_requests.jsonl", [pull_request(enriched=True)])
    meta = build_meta(fx.context(), ["repos.touched"], NOW)
    assert meta["generated_at"] == "2026-12-31T23:00:00Z"
    assert meta["period"] == {"since": "2026-01-01", "until": "2026-12-31"}
    assert meta["status"]["zeta"] == ALL_COMPLETE
    assert meta["status"]["alpha"] == {"commits": "partial", "pull_requests": "never-run",
                                       "reviews": "never-run", "comments": "never-run"}
    assert meta["enrichment_coverage"] == {"commits": 0.5, "pull_requests": 1.0}
    assert meta["partial_datasets"] == ["repos.touched"]
    assert meta["groups"] == {"g1": ["zeta", "alpha"], "g2": ["Mid"]}
    assert "corrupt_lines" not in meta and "skipped_metrics" not in meta


def test_meta_omits_coverage_for_metrics_without_records_or_disabled(fx):
    fx.config(CONFIG + "metrics: [commits, reviews]\n")
    fx.raw("zeta", "commits.jsonl", [commit()])
    fx.raw("zeta", "pull_requests.jsonl", [pull_request(enriched=True)])       # disabled: not read
    meta = build_meta(fx.context(), [], NOW)
    assert meta["enrichment_coverage"] == {"commits": 0.0}
    assert meta["skipped_metrics"] == ["pull_requests", "comments"]
    assert set(meta["status"]["zeta"]) == {"commits", "reviews"}
    fx.config(CONFIG)
    fx.raw("zeta", "commits.jsonl", [])
    assert build_meta(fx.context(), [], NOW)["enrichment_coverage"] == {"pull_requests": 1.0}


def test_meta_reports_corrupt_lines_and_defaults_the_clock(fx):
    fx.config(CONFIG)
    fx.raw("zeta", "commits.jsonl", [commit(), "junk", "junk2"])
    meta = build_meta(fx.context(), [])
    assert meta["corrupt_lines"] == {"zeta/commits.jsonl": 2}
    assert meta["generated_at"].endswith("Z")
    assert meta["partial_datasets"] == []


def test_write_family_layout_and_atomicity(tmp_path):
    path = agg_io.write_family(tmp_path / "d", "repos", {"since": None, "until": None}, {"all": {}}, {"basis": "activity"})
    assert path == tmp_path / "d" / "derived" / "repos.json"
    assert list(json.loads(path.read_text())) == ["period", "basis", "scopes"]
    assert path.read_text().endswith("\n")
    assert [p.name for p in path.parent.iterdir()] == ["repos.json"]


def test_failed_write_keeps_the_old_file_and_leaves_no_temp(tmp_path):
    path = agg_io.write_json(tmp_path / "x.json", {"ok": 1})
    with pytest.raises(TypeError):
        agg_io.write_json(path, {"bad": object()})
    assert json.loads(path.read_text()) == {"ok": 1}
    assert [p.name for p in tmp_path.iterdir()] == ["x.json"]


def test_coverage_rounds_down_and_requires_boolean_true(fx):
    fx.config(CONFIG)
    records = [commit(str(i), enriched=True) for i in range(299)] + [commit("last")]
    fx.raw("zeta", "commits.jsonl", records)
    fx.raw("zeta", "pull_requests.jsonl", [pull_request(1, enriched="yes"), pull_request(2, enriched=True),
                                           pull_request(3, enriched=True)])
    coverage = build_meta(fx.context(), [], NOW)["enrichment_coverage"]
    assert coverage == {"commits": 0.99, "pull_requests": 0.66}
