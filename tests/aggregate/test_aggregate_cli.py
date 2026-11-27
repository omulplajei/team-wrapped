import datetime
import json

from aggregate_helpers import commit, pull_request, review

from team_wrapped import aggregate as agg
from team_wrapped.cli import main

FAMILY_FILES = ["contributors.json", "repos.json", "summary.json", "delivery_volume.json", "curiosities.json", "commit_flow.json"]
CONFIG = """org: sample-org
repos: [alpha-api, beta-web]
groups:
  alpha: [alpha-api]
since: 2026-01-01
until: 2026-12-31
timezone: Europe/Bucharest
"""


def populate(fx):
    fx.config(CONFIG)
    fx.raw("alpha-api", "commits.jsonl", [commit(email="ada@example.com"), commit("b", login=None, email="u@example.com", name="U"), "junk"])
    fx.raw("alpha-api", "pull_requests.jsonl", [pull_request(enriched=True)])
    fx.raw("alpha-api", "reviews.jsonl", [review(login="renovate[bot]")])
    fx.status("alpha-api", {"commits": "complete", "pull_requests": "complete", "reviews": "complete", "comments": "complete"})


def test_aggregate_writes_every_family(fx):
    populate(fx)
    written = agg.aggregate(fx.root, now=datetime.datetime(2026, 12, 31, 23, tzinfo=datetime.timezone.utc))
    assert [p.name for p in written] == FAMILY_FILES + ["meta.json"]
    derived = fx.root / "derived"
    contributors = json.loads((derived / "contributors.json").read_text())
    assert list(contributors["scopes"]) == ["all", "group:alpha"]
    assert contributors["scopes"]["all"]["by_kind"] == {"human": 1, "unlinked": 1, "bot": 1}
    assert contributors["period"] == {"since": "2026-01-01", "until": "2026-12-31"}
    repos = json.loads((derived / "repos.json").read_text())
    assert repos["basis"] == "activity"
    assert repos["scopes"]["all"]["touched"] == {"total": 1, "list": [{"name": "alpha-api"}]}
    meta = json.loads((derived / "meta.json").read_text())
    assert meta["generated_at"] == "2026-12-31T23:00:00Z"
    assert "repos.touched" in meta["partial_datasets"]        # beta-web was never run
    assert meta["partial_datasets"] == sorted(set(meta["partial_datasets"]))
    assert meta["corrupt_lines"] == {"alpha-api/commits.jsonl": 1}
    assert "scopes" not in meta
    assert "@" not in "".join(p.read_text() for p in derived.iterdir())


def test_aggregate_is_idempotent_and_leaves_raw_alone(fx):
    populate(fx)
    raw_before = {p: p.read_bytes() for p in (fx.root / "raw").rglob("*") if p.is_file()}
    agg.aggregate(fx.root)
    first = {p.name: p.read_text() for p in (fx.root / "derived").iterdir() if p.name != "meta.json"}
    agg.aggregate(fx.root)
    assert {p.name: p.read_text() for p in (fx.root / "derived").iterdir() if p.name != "meta.json"} == first
    assert {p: p.read_bytes() for p in (fx.root / "raw").rglob("*") if p.is_file()} == raw_before


def test_families_registry_is_extensible(fx, monkeypatch):
    populate(fx)
    seen = []

    def builder(ctx):
        seen.append(list(ctx.scopes))
        return {scope: {"x": {"n": len(ctx.records("commits", repos))}} for scope, repos in ctx.scopes.items()}, ["demo.x"]

    monkeypatch.setattr(agg, "FAMILIES", [*agg.FAMILIES, agg.Family("demo", builder)])
    written = agg.aggregate(fx.root)
    assert [p.name for p in written] == FAMILY_FILES + ["demo.json", "meta.json"]
    assert seen == [["all", "group:alpha"]]
    assert json.loads((fx.root / "derived/demo.json").read_text())["scopes"]["all"]["x"] == {"n": 2}
    assert "demo.x" in json.loads((fx.root / "derived/meta.json").read_text())["partial_datasets"]


def test_cli_end_to_end(fx, tmp_path, capsys):
    populate(fx)
    assert main(["aggregate", "--root", str(tmp_path), "--data", "data"]) == 0
    out = capsys.readouterr().out
    assert out.count("wrote ") == len(FAMILY_FILES) + 1 and "meta.json" in out
    assert (fx.root / "derived" / "contributors.json").is_file()


def test_cli_reports_config_errors_with_exit_1(fx, tmp_path, capsys):
    fx.config("org: o\nrepos: [a]\nmetrics: [bogus]\n")
    assert main(["aggregate", "--root", str(tmp_path), "--data", "data"]) == 1
    err = capsys.readouterr().err
    assert err.startswith("error: ") and "bogus" in err


def test_cli_reports_a_missing_config(tmp_path, capsys):
    assert main(["aggregate", "--root", str(tmp_path), "--data", "nope"]) == 1
    assert "config file not found" in capsys.readouterr().err


def test_since_and_until_override_the_configured_window(fx):
    populate(fx)
    agg.aggregate(fx.root, since="2026-02-01", until="2026-02-28")
    derived = fx.root / "derived"
    assert json.loads((derived / "summary.json").read_text())["period"] == {"since": "2026-02-01", "until": "2026-02-28"}
    assert json.loads((derived / "meta.json").read_text())["period"] == {"since": "2026-02-01", "until": "2026-02-28"}
    assert main(["aggregate", "--root", str(fx.root.parent), "--data", fx.root.name, "--since", "2026-03-01"]) == 0
    assert json.loads((derived / "summary.json").read_text())["period"] == {"since": "2026-03-01", "until": "2026-12-31"}
