"""Incremental collection: checkpoints per repository and metric, delta fetches, and re-runs that merge by key."""
import datetime
import json

import pytest
from collect_fakes import (commit_node, history, make_client, not_found, page, pr_node, rate_limited, review_node,
                           search)

from team_wrapped.aggregate import aggregate
from team_wrapped.aggregate.raw import load_raw
from team_wrapped.collect import collect, make_plan
from team_wrapped.config import load_config

UTC = datetime.timezone.utc
RUN1 = datetime.datetime(2026, 11, 13, 12, tzinfo=UTC)
RUN2 = datetime.datetime(2026, 11, 27, 12, tzinfo=UTC)
METRICS = ("commits", "pull_requests", "reviews", "comments")
CONFIG = """org: sample-org
repos: [sample-api]
since: 2026-01-01
until: 2026-12-31
timezone: Europe/Bucharest
avatars: {download: false}
"""


def parse(text):
    return datetime.datetime.fromisoformat(text.replace("Z", "+00:00"))


def _range(q, field):
    """(low, high) instants of `field:` in a search string; None where open."""
    for token in q.split():
        if token.startswith(field + ":"):
            value = token[len(field) + 1:]
            if value.startswith(">="):
                return parse(value[2:]), None
            if value.startswith("<="):
                return None, parse(value[2:])
            low, high = value.split("..")
            return parse(low), parse(high)
    return None, None


def _inside(moment, bounds):
    low, high = bounds
    return (low is None or moment >= low) and (high is None or moment <= high)


class World:
    """A repository's history and pull requests; answers queries by their filters, like GitHub does."""

    def __init__(self, commits=(), prs=()):
        self.commits = list(commits)        # commit nodes
        self.prs = list(prs)                # (pr node, updatedAt)

    def __call__(self, query, variables):
        if "history(" in query:
            since, until = variables.get("since"), variables.get("until")
            bounds = (since and parse(since), until and parse(until))
            return history([c for c in self.commits if _inside(parse(c["committedDate"]), bounds)])
        if "search(" in query:
            q = variables["q"]
            created, updated = _range(q, "created"), _range(q, "updated")
            return search([node for node, at in self.prs
                           if _inside(parse(node["createdAt"]), created) and _inside(parse(at), updated)])
        raise AssertionError(query)


@pytest.fixture
def data(tmp_path):
    root = tmp_path / "data"
    root.mkdir()
    (root / "config.yml").write_text(CONFIG)
    return root


def run(data, route, now, plan=None, **kwargs):
    config = load_config(data / "config.yml")
    gh, fake = make_client(route, **{k: kwargs.pop(k) for k in ("max_requests",) if k in kwargs})
    lines = []
    result = collect(data, config, gh, plan or make_plan(config), now=now, log=lines.append, **kwargs)
    return result, fake, lines


def plan(data, **kwargs):
    return make_plan(load_config(data / "config.yml"), **kwargs)


def checkpoint(data, repo="sample-api"):
    return json.loads((data / "raw" / repo / "checkpoint.json").read_text())


def read(data, name, repo="sample-api"):
    return [json.loads(line) for line in (data / "raw" / repo / name).read_text().splitlines()]


def histories(fake):
    return [(v.get("since"), v.get("until")) for q, v in fake.calls if "history(" in q]


def searches(fake):
    return [v["q"].split("sort:created-asc ")[1] for q, v in fake.calls if "search(" in q]


def quiet(query, variables):
    return World()(query, variables)


# --- writing checkpoints

def test_a_complete_run_writes_a_checkpoint_capped_at_the_run_start(data):
    run(data, quiet, RUN1)
    stored = checkpoint(data)
    assert set(stored) == set(METRICS)
    assert stored["commits"] == {"synced_at": "2026-11-13T12:00:00Z", "since": "2026-01-01", "until": "2026-12-31",
                                 "covered_to": "2026-11-13T12:00:00Z", "overlap_days": 7}
    assert stored["reviews"] == stored["pull_requests"] == stored["comments"]
    assert stored["pull_requests"]["overlap_days"] == 1
    assert stored["pull_requests"]["covered_to"] == "2026-11-13T12:00:00Z"


def test_a_partial_unit_does_not_advance_its_checkpoint(data):
    run(data, quiet, RUN1)
    before = checkpoint(data)

    def flaky(query, variables):
        if "history(" in query:
            return 1, "", "gh: HTTP 503"
        return quiet(query, variables)
    run(data, flaky, RUN2)
    after = checkpoint(data)
    assert after["commits"] == before["commits"]
    assert after["pull_requests"]["synced_at"] == "2026-11-27T12:00:00Z"        # that unit completed


def test_a_failed_unit_does_not_advance_its_checkpoint(data):
    run(data, quiet, RUN1)
    before = checkpoint(data)
    run(data, lambda q, v: not_found(), RUN2)
    assert checkpoint(data) == before


def test_a_budget_or_rate_limit_stop_does_not_advance_the_checkpoint(data):
    run(data, quiet, RUN1)
    before = checkpoint(data)
    result, _, _ = run(data, quiet, RUN2, max_requests=1)
    assert "budget" in result.stopped
    after = checkpoint(data)
    assert after["commits"]["synced_at"] == "2026-11-27T12:00:00Z" and after["reviews"] == before["reviews"]

    def limited(query, variables):
        return rate_limited() if "history(" in query else quiet(query, variables)
    run(data, limited, RUN2 + datetime.timedelta(days=1))
    assert checkpoint(data)["commits"]["synced_at"] == "2026-11-27T12:00:00Z"


def test_no_checkpoint_on_a_first_run_means_a_full_fetch(data):
    _, fake, lines = run(data, quiet, RUN1)
    assert histories(fake) == [("2025-12-31T22:00:00Z", "2026-12-31T21:59:59Z")]
    assert searches(fake) == ["created:<=2026-12-31T21:59:59Z updated:>=2025-12-31T22:00:00Z"]
    assert "sample-api commits: complete (0 records)" in lines


# --- what a second run fetches

def test_commits_fetch_from_covered_to_minus_the_overlap(data):
    run(data, quiet, RUN1)
    _, fake, lines = run(data, quiet, RUN2)
    assert histories(fake) == [("2026-11-06T12:00:00Z", "2026-12-31T21:59:59Z")]
    assert "sample-api commits: complete (0 new/updated records, since 2026-11-06)" in lines
    assert checkpoint(data)["commits"]["covered_to"] == "2026-11-27T12:00:00Z"


def test_the_overlap_days_option(data):
    run(data, quiet, RUN1)
    _, fake, _ = run(data, quiet, RUN2, overlap_days=0)
    assert histories(fake) == [("2026-11-13T12:00:00Z", "2026-12-31T21:59:59Z")]
    assert checkpoint(data)["commits"]["overlap_days"] == 0


def test_an_earlier_since_adds_the_missing_start(data):
    run(data, quiet, RUN1, plan=plan(data, since="2026-03-01"))
    _, fake, _ = run(data, quiet, RUN2)
    assert histories(fake) == [("2026-11-06T12:00:00Z", "2026-12-31T21:59:59Z"),
                               ("2025-12-31T22:00:00Z", "2026-03-07T22:00:00Z")]
    assert checkpoint(data)["commits"]["since"] == "2026-01-01"


def test_pull_requests_fetch_the_recently_updated_and_the_newly_created(data):
    run(data, quiet, RUN1, plan=plan(data, until="2026-06-30"))
    _, fake, _ = run(data, quiet, RUN2)
    assert searches(fake) == [
        "created:<=2026-06-30T20:59:59Z updated:>=2026-11-12T12:00:00Z",                          # A
        "created:2026-06-30T21:00:00Z..2026-12-31T21:59:59Z updated:>=2025-12-31T22:00:00Z",      # B
    ]
    assert checkpoint(data)["reviews"]["until"] == "2026-12-31"


def test_pull_requests_with_an_earlier_since_fetch_the_whole_window_with_a_notice(data):
    run(data, quiet, RUN1, plan=plan(data, since="2026-03-01"))
    _, fake, lines = run(data, quiet, RUN2)
    assert searches(fake) == ["created:<=2026-12-31T21:59:59Z updated:>=2025-12-31T22:00:00Z"]
    assert any("before the checkpoint" in line and "2026-03-01" in line for line in lines)
    assert checkpoint(data)["pull_requests"]["since"] == "2026-01-01"


def test_full_ignores_the_checkpoints_and_writes_new_ones(data):
    run(data, quiet, RUN1)
    _, fake, lines = run(data, quiet, RUN2, full=True)
    assert histories(fake) == [("2025-12-31T22:00:00Z", "2026-12-31T21:59:59Z")]
    assert searches(fake) == ["created:<=2026-12-31T21:59:59Z updated:>=2025-12-31T22:00:00Z"]
    assert checkpoint(data)["comments"]["synced_at"] == "2026-11-27T12:00:00Z"


@pytest.mark.parametrize("text", ["{oops", "[1, 2]", '{"commits": {"synced_at": 5}}'])
def test_a_corrupt_checkpoint_is_treated_as_absent_with_a_warning(data, text):
    run(data, quiet, RUN1)
    (data / "raw" / "sample-api" / "checkpoint.json").write_text(text)
    result, fake, lines = run(data, quiet, RUN2)
    assert not result.failed
    assert histories(fake) == [("2025-12-31T22:00:00Z", "2026-12-31T21:59:59Z")]
    assert any(line.startswith("sample-api: checkpoint.json") for line in lines)
    assert checkpoint(data)["commits"]["synced_at"] == "2026-11-27T12:00:00Z"


def test_a_metric_filter_uses_what_every_shared_metric_covers(data):
    run(data, quiet, RUN1, plan=plan(data, metrics=["reviews"]))
    _, fake, _ = run(data, quiet, RUN2, plan=plan(data, metrics=["pull_requests", "reviews"]))
    assert searches(fake) == ["created:<=2026-12-31T21:59:59Z updated:>=2025-12-31T22:00:00Z"]   # PRs: none yet
    _, fake, _ = run(data, quiet, RUN2 + datetime.timedelta(days=1), plan=plan(data, metrics=["reviews"]))
    assert searches(fake) == ["created:<=2026-12-31T21:59:59Z updated:>=2026-11-26T12:00:00Z"]


def test_the_aggregator_ignores_the_checkpoint(data):
    run(data, quiet, RUN1)
    (data / "raw" / "sample-api" / "checkpoint.json").write_text("{not even json")
    raw = load_raw(data, load_config(data / "config.yml"))
    assert raw.corrupt == {} and raw.status["sample-api"] == {m: "complete" for m in METRICS}
    aggregate(data, now=RUN1)
    assert json.loads((data / "derived" / "meta.json").read_text())["partial_datasets"] == []


# --- end to end: a first run, two weeks of activity, the same command again

def world_v1():
    return World(
        commits=[commit_node("c1", at="2026-02-10T09:00:00Z", pr=1),
                 commit_node("c2", at="2026-06-01T09:00:00Z"),
                 commit_node("c3", at="2026-11-10T09:00:00Z", login="grace-codes", email="grace@example.com")],
        prs=[(pr_node(1, created="2026-02-09T09:00:00Z", merged="2026-02-11T09:00:00Z",
                      reviews=page([review_node(11, at="2026-02-10T10:00:00Z")], total=1)), "2026-02-11T09:00:00Z"),
             (pr_node(2, created="2026-11-11T09:00:00Z", merged=None, state="OPEN",
                      reviews=page([review_node(21, state="COMMENTED", at="2026-11-12T10:00:00Z")], total=1)),
              "2026-11-12T10:00:00Z")])


def world_v2():
    world = world_v1()
    world.commits.append(commit_node("c4", at="2026-11-20T09:00:00Z"))
    world.prs[1] = (pr_node(2, created="2026-11-11T09:00:00Z", merged="2026-11-21T09:00:00Z",
                            reviews=page([review_node(21, state="COMMENTED", at="2026-11-12T10:00:00Z"),
                                          review_node(22, login="linus-sample", at="2026-11-20T10:00:00Z")], total=2)),
                    "2026-11-21T09:00:00Z")
    return world


def test_a_second_run_fetches_only_the_delta_and_merges_it(data):
    first, _, _ = run(data, world_v1(), RUN1)
    assert {u.metric: u.records for u in first.units} == {"commits": 3, "pull_requests": 2, "reviews": 2,
                                                          "comments": 0}
    second, _, lines = run(data, world_v2(), RUN2)
    fetched = {u.metric: u.records for u in second.units}
    assert fetched == {"commits": 2, "pull_requests": 1, "reviews": 2, "comments": 0}     # c3 is in the overlap
    assert all(u.status == "complete" for u in second.units)
    assert "sample-api pull_requests: complete (1 new/updated records, since 2026-11-12)" in lines
    commits = read(data, "commits.jsonl")
    assert [c["sha"] for c in commits] == ["c1", "c2", "c3", "c4"]                         # no duplicate c3
    prs = {p["number"]: p for p in read(data, "pull_requests.jsonl")}
    assert len(read(data, "pull_requests.jsonl")) == 2
    assert prs[2]["state"] == "merged" and prs[2]["merged_at"] == "2026-11-21T09:00:00Z"   # the later version wins
    assert prs[1]["state"] == "merged"                                                      # kept, not re-fetched
    assert sorted(r["review_id"] for r in read(data, "reviews.jsonl")) == [11, 21, 22]
    aggregate(data, now=RUN2)
    totals = json.loads((data / "derived" / "summary.json").read_text())["scopes"]["all"]["totals"]
    assert totals == {"commits": 4, "merged_prs": 2, "reviews": 3, "comments": 0}
