import json

from aggregate_helpers import ALL_COMPLETE, commit

from team_wrapped import aggregate as agg
from team_wrapped.aggregate.commit_flow import build_commit_flow
from team_wrapped.aggregate.io import dumps

CONFIG = """org: sample-org
repos: [alpha-api, beta-web, gamma-cli]
groups:
  zeta: [beta-web]
  alpha: [alpha-api, beta-web]
  empty: [gamma-cli]
group_info:
  alpha: {label: Core Alpha, category: core}
  zeta: {category: support}
since: 2026-01-01
until: 2026-12-31
timezone: Europe/Bucharest
"""


def setup(fx, config=CONFIG, status=ALL_COMPLETE):
    fx.config(config)
    for repo in ("alpha-api", "beta-web", "gamma-cli"):
        fx.status(repo, status)
    return fx


def enriched(sha, at, add=10, dele=5, **extra):
    return commit(sha, at=at, enriched=True, additions=add, deletions=dele, files_changed=1, **extra)


def flow(fx):
    scopes, partial = build_commit_flow(fx.context())
    assert list(scopes) == ["all"]
    return scopes["all"], partial


def test_groups_in_config_order_with_info_and_empty_groups_listed(fx):
    setup(fx)
    fx.raw("alpha-api", "commits.jsonl", [enriched("a", "2026-01-03T10:00:00Z", 100, 20)])
    data, partial = flow(fx)
    assert [g["name"] for g in data["groups"]] == ["zeta", "alpha", "empty"]
    assert data["groups"][1] == {"name": "alpha", "label": "Core Alpha", "category": "core", "total": 1,
                                 "commits": [[2, 120]]}
    assert data["groups"][0] == {"name": "zeta", "label": "zeta", "category": "support", "total": 0, "commits": []}
    assert data["groups"][2] == {"name": "empty", "label": "empty", "total": 0, "commits": []}   # no category key
    assert data["window"] == {"days": 365, "start": "2026-01-01"}
    assert partial == []


def test_days_are_local_calendar_days_at_the_midnight_boundary(fx):
    setup(fx)
    fx.raw("alpha-api", "commits.jsonl", [
        enriched("in", "2025-12-31T22:00:00Z"),       # 00:00 Jan 1 in Bucharest: day 0
        enriched("out", "2025-12-31T21:59:59Z"),      # Dec 31 local: outside
        enriched("last", "2026-12-31T21:59:59Z"),     # 23:59:59 Dec 31 local: day 364
        enriched("after", "2026-12-31T22:00:00Z")])   # Jan 1 2027 local: outside
    commits = flow(fx)[0]["groups"][1]["commits"]
    assert [d for d, _ in commits] == [0, 364]


def test_merges_excluded_order_deterministic_and_repo_overlap_counts_in_each_group(fx):
    setup(fx)
    fx.raw("beta-web", "commits.jsonl", [
        enriched("b2", "2026-02-01T10:00:00Z", 1, 1), enriched("b1", "2026-02-01T10:00:00Z", 2, 2),
        enriched("early", "2026-02-01T08:00:00Z", 3, 3), commit("m", at="2026-02-01T09:00:00Z", is_merge=True),
        enriched("a-day2", "2026-02-02T08:00:00Z", 4, 4)])
    fx.raw("alpha-api", "commits.jsonl", [enriched("x", "2026-02-01T09:30:00Z", 5, 5)])
    data, _ = flow(fx)
    zeta, alpha = data["groups"][0], data["groups"][1]
    assert zeta["commits"] == [[31, 6], [31, 4], [31, 2], [32, 8]]      # early, then sha b1 before b2 (same instant)
    assert zeta["total"] == 4
    assert alpha["commits"] == [[31, 6], [31, 10], [31, 4], [31, 2], [32, 8]]
    assert alpha["total"] == 5


def test_unenriched_commits_have_zero_lines_and_make_the_dataset_partial(fx):
    setup(fx)
    fx.raw("alpha-api", "commits.jsonl", [commit("n", at="2026-03-01T10:00:00Z"), enriched("e", "2026-03-02T10:00:00Z")])
    data, partial = flow(fx)
    assert data["groups"][1]["commits"] == [[59, 0], [60, 15]]
    assert partial == ["commit_flow.groups"]


def test_partial_when_a_grouped_repo_commits_status_is_not_complete(fx):
    setup(fx)
    fx.status("gamma-cli", {**ALL_COMPLETE, "commits": "partial"})
    assert flow(fx)[1] == ["commit_flow.groups"]


def test_an_unenriched_commit_outside_the_window_or_a_merge_does_not_make_it_partial(fx):
    setup(fx)
    fx.raw("alpha-api", "commits.jsonl", [commit("old", at="2025-01-01T10:00:00Z"),
                                          commit("m", at="2026-03-01T10:00:00Z", is_merge=True)])
    assert flow(fx)[1] == []


def test_nothing_is_written_without_groups_a_bounded_window_or_commits(fx):
    for text in ("org: o\nrepos: [a]\nsince: 2026-01-01\nuntil: 2026-12-31\n",
                 "org: o\nrepos: [a]\ngroups: {g: [a]}\nsince: 2026-01-01\n",
                 "org: o\nrepos: [a]\ngroups: {g: [a]}\nuntil: 2026-12-31\n",
                 "org: o\nrepos: [a]\ngroups: {g: [a]}\nsince: 2026-01-01\nuntil: 2026-12-31\nmetrics: [reviews]\n"):
        fx.config(text)
        assert build_commit_flow(fx.context()) == ({"all": {}}, [])


def test_window_days_follow_the_bounds(fx):
    setup(fx, CONFIG.replace("2026-12-31", "2026-01-10"))
    assert flow(fx)[0]["window"] == {"days": 10, "start": "2026-01-01"}


def test_aggregate_writes_compact_idempotent_commit_flow_without_people(fx):
    setup(fx)
    fx.raw("alpha-api", "commits.jsonl", [enriched("a", "2026-01-03T10:00:00Z"), enriched("b", "2026-01-04T10:00:00Z")])
    agg.aggregate(fx.root)
    path = fx.root / "derived" / "commit_flow.json"
    first = path.read_bytes()
    data = json.loads(first)
    assert list(data) == ["period", "scopes"] and list(data["scopes"]) == ["all"]
    assert data["scopes"]["all"]["groups"][1]["commits"] == [[2, 15], [3, 15]]
    assert '\n            [2, 15],\n            [3, 15]\n          ]' in first.decode()
    for secret in ("ada", "@", "sha"):
        assert secret not in first.decode()
    agg.aggregate(fx.root)
    assert path.read_bytes() == first


def test_dumps_matches_indented_json_except_for_pair_lists():
    payload = {"a": [1, 2], "b": {}, "c": [], "d": [{"x": "y\u00e9"}], "e": None, "f": [[1], [2]], "g": [[1, 2], "s"]}
    plain = {k: v for k, v in payload.items() if k != "f"}
    assert dumps(plain) == json.dumps(plain, indent=2)
    assert json.loads(dumps(payload)) == payload
    assert dumps({"f": [[1, 2], [3, 4]]}) == '{\n  "f": [\n    [1, 2],\n    [3, 4]\n  ]\n}'
