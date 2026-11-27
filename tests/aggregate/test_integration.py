"""aggregate end to end on a hand-built raw tree, then the shipped year-wrapped script against its output."""
import datetime
import json

from aggregate_helpers import ALL_COMPLETE, comment, commit, pull_request, review

from team_wrapped.aggregate import aggregate
from team_wrapped.scenes.build import build
from team_wrapped.scenes.validate import resolve_and_validate

CONFIG = """org: sample-org
repos: [alpha-api, alpha-web, beta-cli]
groups:
  alpha: [alpha-api, alpha-web]
  beta: [beta-cli]
since: 2026-01-01
until: 2026-12-31
timezone: Europe/Bucharest
bot_patterns: ["*[bot]"]
"""
NOW = datetime.datetime(2026, 12, 31, 23, tzinfo=datetime.timezone.utc)


def populate(fx):
    fx.config(CONFIG)
    for repo in ("alpha-api", "alpha-web", "beta-cli"):
        fx.status(repo, ALL_COMPLETE)
    days = [f"2026-03-{d:02d}" for d in range(10, 14)]
    fx.raw("alpha-api", "commits.jsonl", [
        *[commit(f"a{i}", at=f"{d}T09:00:00Z", enriched=True, additions=10 * (i + 1), deletions=i, files_changed=i + 1)
          for i, d in enumerate(days)],
        commit("merge", at="2026-03-14T09:00:00Z", is_merge=True),                       # not enriched
        commit("bot", login="renovate[bot]", email="bot@example.com", at="2026-05-01T09:00:00Z"),
        commit("anon", login=None, email="who@example.com", name="Who", at="2026-06-01T09:00:00Z")])
    fx.raw("alpha-web", "commits.jsonl", [commit("w1", login="grace-codes", at="2026-03-12T09:00:00Z")])
    fx.raw("beta-cli", "commits.jsonl", [commit("c1", login="linus", at="2026-09-01T09:00:00Z")])
    fx.raw("alpha-api", "pull_requests.jsonl", [
        pull_request(1, created="2026-03-01T09:00:00Z", merged="2026-03-14T09:00:00Z", enriched=True,
                     commit_count=7, changed_files=12, additions=400, deletions=90),
        pull_request(2, login="grace-codes", created="2026-03-15T09:00:00Z", merged="2026-03-16T09:00:00Z")])
    fx.raw("beta-cli", "pull_requests.jsonl", [pull_request(1, login="linus", created="2026-09-01T09:00:00Z",
                                                            merged="2026-09-02T09:00:00Z", enriched=True, commit_count=1,
                                                            changed_files=1, additions=3, deletions=1)])
    fx.raw("alpha-api", "reviews.jsonl", [
        review(1, login="grace-codes"), review(1, login="linus", state="changes_requested"),
        review(1, login="linus", state="approved"), review(1, login="ada-dev"), review(2, login="ada-dev")])
    fx.raw("alpha-api", "comments.jsonl", [
        comment(1, cid=1), comment(1, cid=2, in_reply_to_id=1, thread_root_id=1), comment(1, cid=3, in_reply_to_id=1, thread_root_id=1),
        comment(1, cid=4, login="ada-dev", kind="conversation", thread_root_id=None)])
    fx.avatar("placeholder").avatar("ada-dev")


def tree(root):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in (root / "derived").rglob("*") if p.is_file()}


def test_aggregate_output_feeds_the_year_wrapped_script(fx, repo_root, tmp_path):
    populate(fx)
    aggregate(fx.root, now=NOW)
    derived = fx.root / "derived"
    assert sorted(p.name for p in derived.iterdir()) == [
        "commit_flow.json", "contributors.json", "curiosities.json", "delivery_volume.json", "meta.json", "repos.json", "summary.json"]
    for name in ("contributors", "repos", "summary", "delivery_volume", "curiosities"):
        assert list(json.loads((derived / f"{name}.json").read_text())["scopes"]) == ["all", "group:alpha", "group:beta"]
    meta = json.loads((derived / "meta.json").read_text())
    assert meta["partial_datasets"] == sorted(set(meta["partial_datasets"]))
    assert "delivery_volume.lines" in meta["partial_datasets"] and "summary.totals" not in meta["partial_datasets"]
    totals = json.loads((derived / "summary.json").read_text())["scopes"]["all"]["totals"]
    assert totals == {"commits": 9, "merged_prs": 3, "reviews": 4, "comments": 4}      # ada-dev's review of her own PR 1 is out

    for scope_name in ("all", "alpha", "beta"):
        script = (repo_root / "scripts" / "year-wrapped.yml").read_text().replace("scope: all", f"scope: {scope_name}", 1)
        (fx.root / "scripts").mkdir(exist_ok=True)
        (fx.root / "scripts" / f"yw-{scope_name}.yml").write_text(script.replace("id: year-wrapped", f"id: yw-{scope_name}", 1))
        report = resolve_and_validate(f"yw-{scope_name}", repo_root, fx.root).report
        shape_problems = [(r.scene_id, r.problems) for r in report.results
                          if any("missing field" in p or "does not resolve" in p or "not a number" in p for p in r.problems)]
        assert report.ok
        if scope_name != "beta":            # beta has no comments or reviews: its scenes are skipped for missing data
            assert shape_problems == []

    results = {r.scene_id: r for r in resolve_and_validate("year-wrapped", repo_root, fx.root).report.results}
    assert all(not r.skipped for r in results.values())
    assert {s: r.status for s, r in results.items() if r.status == "partial"} == {
        "year-in-numbers": "partial", "we-changed-the-code": "partial", "curiosity-most-commits-pr": "partial",
        "curiosity-spring-cleaning": "partial"}
    built = build("year-wrapped", repo_root, fx.root, tmp_path / "dist")
    assert built.skipped == []


def test_aggregate_is_byte_identical_when_run_twice_with_a_fixed_clock(fx):
    populate(fx)
    aggregate(fx.root, now=NOW)
    first = tree(fx.root)
    aggregate(fx.root, now=NOW)
    assert tree(fx.root) == first
    aggregate(fx.root, now=NOW + datetime.timedelta(hours=1))
    changed = {name for name, data in tree(fx.root).items() if data != first[name]}
    assert changed == {"derived/meta.json"}
