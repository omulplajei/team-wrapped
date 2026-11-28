"""collect (fake gh) into a temporary data root, then aggregate on what it wrote."""
import datetime
import json

from collect_fakes import (comment_node, commit_node, git_actor, history, make_client, page, pr_node,
                           review_comment_node, review_node, search, thread)

from team_wrapped.aggregate import aggregate
from team_wrapped.collect import collect, make_plan
from team_wrapped.config import load_config

UTC = datetime.timezone.utc
CONFIG = """org: sample-org
repos: [sample-api, sample-web]
groups:
  alpha: [sample-api]
since: 2026-01-01
until: 2026-12-31
timezone: Europe/Bucharest
"""


def route(query, variables):
    if "history(" in query:
        if variables["name"] == "sample-web":
            return history([commit_node("w1", login="grace-codes", email="grace@example.com")])
        return history([
            commit_node("a1", at="2026-03-10T09:00:00Z", additions=100, deletions=10, files=4, pr=1),
            commit_node("a2", at="2026-03-11T09:00:00Z", additions=5, deletions=1, files=1),
            commit_node("m1", at="2026-03-12T09:00:00Z", parents=2),
            commit_node("u1", at="2026-04-01T09:00:00Z", login=None, name="Someone", email="someone@example.com"),
            commit_node("b1", at="2026-05-01T09:00:00Z", login="renovate", typename="Bot", email="bot@example.com"),
        ])
    if "search(" in query:
        if "sample-web" in variables["q"]:
            return search([])
        return search([
            pr_node(1, created="2026-03-09T09:00:00Z", merged="2026-03-12T09:00:00Z",
                    reviews=page([review_node(11, login="grace-codes"), review_node(12, login="ada-dev", state="COMMENTED"),
                                  review_node(13, login="linus-sample", state="CHANGES_REQUESTED")], total=3),
                    comments=page([comment_node(21, login="ada-dev")], total=1),
                    threads=page([thread("T1", [review_comment_node(31), review_comment_node(32, reply_to=31, login="ada-dev"),
                                                review_comment_node(33, reply_to=31)])])),
            pr_node(2, login="renovate", typename="Bot", created="2026-05-02T09:00:00Z", merged=None, state="OPEN"),
        ])
    raise AssertionError(query)


def test_collect_then_aggregate(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    (data / "config.yml").write_text(CONFIG)
    config = load_config(data / "config.yml")
    gh, _ = make_client(route)
    result = collect(data, config, gh, make_plan(config), fetch=lambda url: ("image/png", b"png"),
                     now=datetime.datetime(2026, 11, 27, tzinfo=UTC), log=lambda s: None)
    assert not result.failed and result.avatars_failed == []
    aggregate(data, now=datetime.datetime(2026, 11, 27, tzinfo=UTC))
    derived = data / "derived"
    summary = json.loads((derived / "summary.json").read_text())["scopes"]
    assert summary["all"]["totals"] == {"commits": 6, "merged_prs": 1, "reviews": 2, "comments": 4}   # own review out
    assert summary["group:alpha"]["totals"]["commits"] == 5
    contributors = json.loads((derived / "contributors.json").read_text())["scopes"]["all"]
    assert contributors["by_kind"] == {"human": 3, "unlinked": 1, "bot": 1}
    assert {c.get("login"): c["avatar_file"] for c in contributors["list"]}["renovate[bot]"] == "avatars/renovate_bot.png"
    curiosities = json.loads((derived / "curiosities.json").read_text())["scopes"]["all"]
    assert curiosities["longest_comment_chain"][0]["value"] == 3
    meta = json.loads((derived / "meta.json").read_text())
    assert meta["partial_datasets"] == [] and meta["enrichment_coverage"] == {"commits": 1.0, "pull_requests": 1.0}
    assert meta["status"]["sample-web"] == {m: "complete" for m in ("commits", "pull_requests", "reviews", "comments")}
    text = "".join(p.read_text() for p in derived.iterdir())
    assert "@" not in text and "Someone" not in text


AI_CONFIG = CONFIG + """bot_patterns: ['*[bot]', claude, cursoragent, 'Deployment Script']
bot_names: {claude: Claude, cursoragent: Cursor}
"""


def co_author_route(query, variables):
    if "history(" in query:
        if variables["name"] == "sample-web":
            return history([])
        return history([
            commit_node("a1", at="2026-03-10T09:00:00Z", additions=100, deletions=10, files=4, co_authors=[
                git_actor("claude", "Claude", "claude@example.com"),
                git_actor("pair-dev", "Pair", "pair@example.com"),
                git_actor(None, "Deployment Script", "deploy@example.com"),
                git_actor("ada-dev", "Ada", "ada@example.com")]),                  # the author again: dropped
            commit_node("a2", at="2026-06-11T09:00:00Z", login="grace-codes", email="grace@example.com", additions=5,
                        deletions=1, files=1, co_authors=[git_actor("cursoragent", "Cursor Agent", "cursor@example.com"),
                                                          git_actor("claude", "Claude", "claude@example.com")]),
        ])
    if "search(" in query:
        return search([])
    raise AssertionError(query)


def test_collect_then_aggregate_counts_co_authors_as_contributors(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    (data / "config.yml").write_text(AI_CONFIG)
    config = load_config(data / "config.yml")
    gh, fake = make_client(co_author_route)
    urls = []
    result = collect(data, config, gh, make_plan(config), fetch=lambda url: urls.append(url) or ("image/png", b"png"),
                     now=datetime.datetime(2026, 11, 27, tzinfo=UTC), log=lambda s: None)
    assert not result.failed and result.avatars_failed == []
    assert all("authors(first: 10)" in q for q, _ in fake.calls if "history(" in q)
    raw = [json.loads(line) for line in (data / "raw" / "sample-api" / "commits.jsonl").read_text().splitlines()]
    assert [len(r["co_authors"]) for r in raw] == [3, 2]
    assert sorted(u.split("/")[-1] for u in urls) == [f"{n}.png?size=200" for n in
                                                      ("ada-dev", "claude", "cursoragent", "grace-codes", "pair-dev")]
    aggregate(data, now=datetime.datetime(2026, 11, 27, tzinfo=UTC))
    derived = data / "derived"
    contributors = json.loads((derived / "contributors.json").read_text())["scopes"]["all"]
    assert contributors["by_kind"] == {"human": 3, "unlinked": 0, "bot": 3}
    entries = {c.get("login", c.get("name")): c for c in contributors["list"]}
    assert {k: (c["kind"], c.get("name")) for k, c in entries.items()} == {
        "ada-dev": ("human", None), "grace-codes": ("human", None), "pair-dev": ("human", None),
        "claude": ("bot", "Claude"), "cursoragent": ("bot", "Cursor"),
        "Deployment Script": ("bot", "Deployment Script")}
    assert entries["claude"]["avatar_file"] == "avatars/claude.png"
    assert (entries["claude"]["first_activity"], entries["claude"]["last_activity"]) == ("2026-03-10", "2026-06-11")
    summary = json.loads((derived / "summary.json").read_text())["scopes"]["all"]
    assert summary["totals"]["commits"] == 2
    volume = json.loads((derived / "delivery_volume.json").read_text())["scopes"]["all"]
    assert volume["lines"] == {"total_additions": 105, "total_deletions": 11, "total_net": 94}
    text = "".join(p.read_text() for p in derived.iterdir())
    assert "@" not in text and "Pair" not in text and "Cursor Agent" not in text
