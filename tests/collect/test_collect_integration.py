"""collect (fake gh) into a temporary data root, then aggregate on what it wrote."""
import datetime
import json

from collect_fakes import (comment_node, commit_node, history, make_client, page, pr_node, review_comment_node,
                           review_node, search, thread)

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
