"""The collect stage: units per repository and metric, statuses, errors, stops and re-runs."""
import datetime
import json

import pytest
from collect_fakes import (commit_node, comment_node, empty_routes, history, make_client, not_found, page, pr_node,
                           rate_limited, review_node, search)

from team_wrapped.aggregate.raw import load_raw
from team_wrapped.collect import collect, make_plan
from team_wrapped.config import load_config
from team_wrapped.scenes.loader import LoadError

UTC = datetime.timezone.utc
NOW = datetime.datetime(2026, 11, 27, 12, tzinfo=UTC)
CONFIG = """org: sample-org
repos: [sample-api, sample-web]
since: 2026-01-01
until: 2026-12-31
timezone: Europe/Bucharest
avatars: {download: false}
"""


@pytest.fixture
def data(tmp_path):
    root = tmp_path / "data"
    root.mkdir()
    (root / "config.yml").write_text(CONFIG)
    return root


def config_of(data):
    return load_config(data / "config.yml")


def run(data, route, plan=None, **kwargs):
    config = config_of(data)
    gh, fake = make_client(route, **{k: kwargs.pop(k) for k in ("max_requests",) if k in kwargs})
    lines = []
    result = collect(data, config, gh, plan or make_plan(config), now=NOW, log=lines.append, **kwargs)
    return result, fake, lines


def activity(query, variables):
    if "history(" in query:
        return history([commit_node(f"{variables['name']}-1"), commit_node(f"{variables['name']}-2", parents=2)])
    if "search(" in query:
        return search([pr_node(1, reviews=page([review_node(11)], total=1), comments=page([comment_node(21)], total=1))])
    raise AssertionError(query)


def read(data, repo, name):
    path = data / "raw" / repo / name
    if name.endswith(".json"):
        return json.loads(path.read_text())
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_writes_every_metric_and_status(data):
    result, fake, lines = run(data, activity)
    for repo in ("sample-api", "sample-web"):
        assert [c["sha"] for c in read(data, repo, "commits.jsonl")] == [f"{repo}-1", f"{repo}-2"]
        assert [p["number"] for p in read(data, repo, "pull_requests.jsonl")] == [1]
        assert len(read(data, repo, "reviews.jsonl")) == 1 and len(read(data, repo, "comments.jsonl")) == 1
        assert read(data, repo, "status.json") == {m: "complete" for m in ("commits", "pull_requests", "reviews", "comments")}
        detail = read(data, repo, "status-detail.json")
        assert detail["commits"]["collected_at"] == "2026-11-27T12:00:00Z" and detail["commits"]["records"] == 2
        assert detail["commits"]["window"] == {"since": "2026-01-01", "until": "2026-12-31"}
    assert len(fake.calls) == 4                     # one history page and one search page per repository
    assert not result.failed and result.stopped is None
    assert any("sample-api commits: complete" in line for line in lines)
    raw = load_raw(data, config_of(data))           # the aggregator reads it back
    assert raw.corrupt == {} and len(raw.records["commits"]) == 4
    assert raw.status["sample-web"]["comments"] == "complete"


def test_not_found_fails_the_repo_and_continues(data):
    def route(query, variables):
        if variables.get("name") == "sample-api" or "sample-api" in variables.get("q", ""):
            return not_found()
        return activity(query, variables)
    result, fake, _ = run(data, route)
    status = read(data, "sample-api", "status.json")
    assert status == {m: "failed" for m in ("commits", "pull_requests", "reviews", "comments")}
    assert "Could not resolve" in read(data, "sample-api", "status-detail.json")["pull_requests"]["reason"]
    assert not (data / "raw" / "sample-api" / "commits.jsonl").exists()
    assert read(data, "sample-web", "status.json")["commits"] == "complete"
    assert result.failed and len(fake.calls) == 3   # the PR search is not tried on a missing repository


def test_rate_limit_stops_with_a_resume_message_and_keeps_what_was_fetched(data):
    def route(query, variables):
        if "search(" in query and variables.get("after") is None:
            return search([pr_node(1)], cursor="S1", count=2)
        if "search(" in query:
            return rate_limited()
        return activity(query, variables)
    result, _, lines = run(data, route)
    assert "resume after" in result.stopped and any("resume after" in line for line in lines)
    status = read(data, "sample-api", "status.json")
    assert status == {"commits": "complete", "pull_requests": "partial", "reviews": "partial", "comments": "partial"}
    assert [p["number"] for p in read(data, "sample-api", "pull_requests.jsonl")] == [1]
    assert "rate limit" in read(data, "sample-api", "status-detail.json")["reviews"]["reason"]
    assert not (data / "raw" / "sample-web").exists()          # not reached: untouched, still never-run
    assert [(u.repo, u.status) for u in result.units if u.status == "not run"] == [
        ("sample-web", "not run")] * 4
    assert not result.failed


def test_budget_exhaustion_stops_cleanly(data):
    result, fake, _ = run(data, activity, max_requests=1)
    assert len(fake.calls) == 1 and "budget" in result.stopped
    assert read(data, "sample-api", "status.json") == {"commits": "complete", "pull_requests": "partial",
                                                       "reviews": "partial", "comments": "partial"}


def test_transient_errors_retry_then_succeed(data):
    failures = iter([(1, "", "gh: HTTP 502"), (1, "", "gh: HTTP 504")])

    def route(query, variables):
        if "history(" in query and variables["name"] == "sample-api":
            failure = next(failures, None)
            if failure:
                return failure
        return activity(query, variables)
    result, _, _ = run(data, route)
    assert read(data, "sample-api", "status.json")["commits"] == "complete"
    assert result.requests == 6


def test_transient_errors_past_the_limit_leave_the_unit_partial(data):
    def route(query, variables):
        if "history(" in query and variables["name"] == "sample-api":
            if variables.get("after") is None:
                return history([commit_node("a1")], cursor="C1")
            return 1, "", "gh: HTTP 503"
        return activity(query, variables)
    result, _, _ = run(data, route)
    assert read(data, "sample-api", "status.json")["commits"] == "partial"
    assert [c["sha"] for c in read(data, "sample-api", "commits.jsonl")] == ["a1"]
    assert read(data, "sample-web", "status.json")["commits"] == "complete"
    assert result.stopped is None


def test_a_capped_search_marks_the_pull_request_metrics_partial(data):
    def route(query, variables):
        if "search(" in query:
            return search([pr_node(1)], count=5000)
        return activity(query, variables)
    config = config_of(data)
    plan = make_plan(config, repos=["sample-api"], since="2026-11-27", until="2026-11-27")
    gh, _ = make_client(route)
    collect(data, config, gh, plan, now=datetime.datetime(2026, 11, 26, 22, 0, 30, tzinfo=UTC), log=lambda s: None)
    assert read(data, "sample-api", "status.json")["pull_requests"] == "partial"
    assert "1000" in read(data, "sample-api", "status-detail.json")["pull_requests"]["reason"]


def test_rerun_overwrites_without_duplicates(data):
    run(data, activity)
    first = {p: p.read_text() for p in (data / "raw").rglob("*.jsonl")}
    run(data, activity)
    assert {p: p.read_text() for p in (data / "raw").rglob("*.jsonl")} == first
    assert len(read(data, "sample-api", "commits.jsonl")) == 2


def test_a_partial_rerun_keeps_earlier_records(data):
    run(data, activity)

    def fewer(query, variables):
        if "history(" in query:
            return history([commit_node(f"{variables['name']}-2", parents=2, additions=99)])
        return activity(query, variables)
    run(data, fewer)
    commits = read(data, "sample-api", "commits.jsonl")
    assert [c["sha"] for c in commits] == ["sample-api-1", "sample-api-2"] and commits[1]["additions"] == 99


def test_filters_by_repo_and_metric_and_keeps_other_statuses(data):
    run(data, activity)
    config = config_of(data)
    result, fake, _ = run(data, activity, plan=make_plan(config, repos=["sample-web"], metrics=["commits"]))
    assert len(fake.calls) == 1 and [(u.repo, u.metric) for u in result.units] == [("sample-web", "commits")]
    assert read(data, "sample-web", "status.json")["reviews"] == "complete"


def test_plan_validates_filters_and_converts_the_window(data):
    config = config_of(data)
    plan = make_plan(config)
    assert plan.start == datetime.datetime(2025, 12, 31, 22, tzinfo=UTC)          # Europe/Bucharest is UTC+2
    assert plan.end == datetime.datetime(2026, 12, 31, 21, 59, 59, tzinfo=UTC)
    summer = make_plan(config, since="2026-07-01", until="2026-07-31")             # UTC+3 in summer
    assert (summer.start, summer.end) == (datetime.datetime(2026, 6, 30, 21, tzinfo=UTC),
                                          datetime.datetime(2026, 7, 31, 20, 59, 59, tzinfo=UTC))
    assert (summer.since, summer.until) == ("2026-07-01", "2026-07-31")
    with pytest.raises(LoadError, match="not in the config"):
        make_plan(config, repos=["sample-gone"])
    with pytest.raises(LoadError, match="metric"):
        make_plan(config, metrics=["deploys"])
    with pytest.raises(LoadError, match="--since"):
        make_plan(config, since="2026-13-01")
    with pytest.raises(LoadError, match="after"):
        make_plan(config, since="2026-08-01", until="2026-07-01")


def test_open_window_has_no_bounds(tmp_path):
    (tmp_path / "config.yml").write_text("org: sample-org\nrepos: [sample-api]\n")
    plan = make_plan(load_config(tmp_path / "config.yml"))
    assert plan.start is None and plan.end is None


def test_metrics_outside_the_config_are_rejected(tmp_path):
    (tmp_path / "config.yml").write_text("org: sample-org\nrepos: [sample-api]\nmetrics: [commits]\n")
    with pytest.raises(LoadError, match="not enabled"):
        make_plan(load_config(tmp_path / "config.yml"), metrics=["reviews"])


def test_all_branches_is_rejected(tmp_path):
    (tmp_path / "config.yml").write_text("org: sample-org\nrepos: [sample-api]\ncommit_branches: all\n")
    with pytest.raises(LoadError, match="commit_branches"):
        make_plan(load_config(tmp_path / "config.yml"))


def test_empty_activity_is_complete(data):
    run(data, empty_routes)
    assert read(data, "sample-api", "status.json")["commits"] == "complete"
    assert read(data, "sample-api", "commits.jsonl") == []


def test_bot_avatars_fall_back_to_the_app_lookup_through_the_same_client(data):
    (data / "config.yml").write_text(CONFIG.replace("avatars: {download: false}\n", "repos: [sample-api]\n")
                                     .replace("repos: [sample-api, sample-web]\n", ""))

    def route(query, variables):
        if query is None:                    # gh api apps/<name>: the REST lookup
            return 0, json.dumps({"id": 77}), ""
        if "history(" in query:
            return history([commit_node("a1", login="sample-bot", typename="Bot")])
        return empty_routes(query, variables)
    urls = []

    def fetch(url):
        urls.append(url)
        if url.startswith("https://github.com/sample-bot"):
            raise OSError("HTTP 404")
        return "image/png", b"png"
    result, fake, _ = run(data, route, fetch=fetch)
    assert result.avatars_failed == []
    assert (None, {}) in fake.calls
    assert urls[-1] == "https://avatars.githubusercontent.com/in/77?s=200"
    assert (data / "avatars" / "sample-bot_bot.png").read_bytes() == b"png"
    assert (data / "avatars" / "placeholder.png").is_file()
