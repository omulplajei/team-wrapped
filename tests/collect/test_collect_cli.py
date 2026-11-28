"""`collect` and `status` on the command line, with a fake gh."""
import json

import pytest
from collect_fakes import commit_node, history, make_client, not_found, pr_node, search

from team_wrapped import cli
from team_wrapped.cli import main
from team_wrapped.collect import avatars
from team_wrapped.github import GitHub

CONFIG = """org: sample-org
repos: [sample-api, sample-web]
since: 2026-01-01
until: 2026-12-31
timezone: Europe/Bucharest
"""


def route(query, variables):
    if "history(" in query:
        if variables["name"] == "sample-web":
            return not_found()
        return history([commit_node("a1", login="ada-dev")])
    if "search(" in query:
        return search([pr_node(1)])
    raise AssertionError(query)


@pytest.fixture
def root(tmp_path):
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "config.yml").write_text(CONFIG)
    return tmp_path


@pytest.fixture
def fake(monkeypatch):
    made = {}

    def factory(**kwargs):
        gh, runner = make_client(route, **kwargs)
        made["runner"], made["kwargs"] = runner, kwargs
        return gh
    monkeypatch.setattr(cli, "GitHub", factory)
    monkeypatch.setattr(avatars, "fetch_url", lambda url: ("image/png", b"png"))
    return made


def test_dry_run_prints_the_plan_without_calls(root, fake, capsys):
    code = main(["collect", "--root", str(root), "--dry-run", "--repo", "sample-api", "--metric", "commits",
                 "--since", "2026-07-01"])
    out = capsys.readouterr().out
    assert code == 0 and fake == {}
    assert "sample-api" in out and "sample-web" not in out
    assert "2026-07-01 to 2026-12-31 (Europe/Bucharest)" in out and "2026-06-30T21:00:00Z" in out
    assert "metrics: commits" in out
    assert not (root / "data" / "raw").exists()


def test_collect_runs_reports_and_fails_on_a_failed_repo(root, fake, capsys):
    code = main(["collect", "--root", str(root), "--max-requests", "50"])
    out = capsys.readouterr().out
    assert code == 1 and fake["kwargs"] == {"max_requests": 50}
    assert "sample-api commits: complete (1 records)" in out
    assert "sample-web commits: failed" in out
    table = out[out.index("repo"):]
    assert "sample-api" in table and "failed" in table and "requests:" in out
    assert (root / "data" / "avatars" / "ada-dev.png").read_bytes() == b"png"


def test_no_avatars_skips_the_download(root, fake, monkeypatch, capsys):
    def boom(url):
        raise AssertionError("no download expected")
    monkeypatch.setattr(avatars, "fetch_url", boom)
    assert main(["collect", "--root", str(root), "--repo", "sample-api", "--no-avatars"]) == 0
    assert not (root / "data" / "avatars").exists()


@pytest.mark.parametrize("args, message", [
    (["--metric", "deploys"], "metric"),
    (["--repo", "sample-gone"], "not in the config"),
    (["--since", "yesterday"], "--since"),
])
def test_bad_filters_are_errors(root, fake, capsys, args, message):
    assert main(["collect", "--root", str(root), *args]) == 2
    assert message in capsys.readouterr().err


def test_status_reads_statuses_and_counts_without_network(root, fake, capsys):
    main(["collect", "--root", str(root), "--no-avatars"])
    capsys.readouterr()
    fake.clear()
    assert main(["status", "--root", str(root)]) == 0
    out = capsys.readouterr().out
    assert fake == {}
    lines = {}
    for line in out.splitlines():
        if line.startswith("sample-"):
            lines.setdefault(line.split()[0], line)          # the table row comes before the reasons
    assert "complete (1)" in lines["sample-api"] and lines["sample-web"].count("failed") == 4
    assert "last collected 20" in lines["sample-api"]
    assert "Could not resolve" in out


def test_status_before_any_collection(root, capsys):
    assert main(["status", "--root", str(root)]) == 0
    assert capsys.readouterr().out.count("never-run") == 8


def write_checkpoint_file(root, repo="sample-api", covered_to="2026-11-13T12:00:00Z", **metrics):
    entry = {"synced_at": covered_to, "since": "2026-01-01", "until": "2026-12-31", "covered_to": covered_to,
             "overlap_days": 7}
    folder = root / "data" / "raw" / repo
    folder.mkdir(parents=True, exist_ok=True)
    stored = {m: dict(entry) for m in ("commits", "pull_requests", "reviews", "comments")}
    for metric in ("pull_requests", "reviews", "comments"):
        stored[metric]["overlap_days"] = 1
    stored.update(metrics)
    (folder / "checkpoint.json").write_text(json.dumps(stored))


def test_dry_run_prints_full_or_incremental_per_repo_and_metric(root, fake, capsys):
    write_checkpoint_file(root)
    assert main(["collect", "--root", str(root), "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert fake == {}
    assert "sample-api commits: incremental from 2026-11-06" in out
    assert "sample-api reviews: incremental from 2026-11-12" in out
    assert "sample-web commits: full" in out and "sample-web comments: full" in out
    assert main(["collect", "--root", str(root), "--dry-run", "--overlap-days", "0"]) == 0
    assert "sample-api commits: incremental from 2026-11-13" in capsys.readouterr().out
    assert main(["collect", "--root", str(root), "--dry-run", "--full"]) == 0
    assert "sample-api commits: full" in capsys.readouterr().out


def test_full_and_overlap_reach_the_collector(root, fake, monkeypatch, capsys):
    seen = {}

    def spy(*args, **kwargs):
        seen.update(kwargs)
        raise SystemExit(0)
    monkeypatch.setattr(cli, "collect", spy)
    with pytest.raises(SystemExit):
        main(["collect", "--root", str(root), "--full", "--overlap-days", "3"])
    assert seen["full"] is True and seen["overlap_days"] == 3
    with pytest.raises(SystemExit):
        main(["collect", "--root", str(root)])
    assert seen["full"] is False and seen["overlap_days"] == 7


def test_negative_overlap_is_rejected(root, capsys):
    with pytest.raises(SystemExit):
        main(["collect", "--root", str(root), "--overlap-days", "-1"])
    assert "overlap" in capsys.readouterr().err


def test_status_shows_the_last_sync_and_covered_range(root, fake, capsys):
    main(["collect", "--root", str(root), "--no-avatars"])
    write_checkpoint_file(root, covered_to="2026-11-13T12:00:00Z",
                          comments={"synced_at": "2026-11-01T08:30:00Z", "since": "2026-03-01", "until": "2026-12-31",
                                    "covered_to": "2026-11-01T08:30:00Z", "overlap_days": 1})
    capsys.readouterr()
    assert main(["status", "--root", str(root)]) == 0
    out = capsys.readouterr().out
    section = out[out.index("checkpoints"):]
    rows = [line.split("  ") for line in section.splitlines()]
    rows = [[cell.strip() for cell in row if cell.strip()] for row in rows]
    assert ["sample-api", "commits", "2026-11-13 12:00", "2026-01-01 .. 2026-11-13 12:00"] in rows
    assert ["sample-api", "pull_requests, reviews", "2026-11-13 12:00", "2026-01-01 .. 2026-11-13 12:00"] in rows
    assert ["sample-api", "comments", "2026-11-01 08:30", "2026-03-01 .. 2026-11-01 08:30"] in rows
    assert not any(row and row[0] == "sample-web" for row in rows)       # failed: no checkpoint
    assert max(len(line) for line in section.splitlines()) <= 100


def test_status_reports_an_unreadable_checkpoint(root, capsys):
    folder = root / "data" / "raw" / "sample-api"
    folder.mkdir(parents=True)
    (folder / "checkpoint.json").write_text("{broken")
    assert main(["status", "--root", str(root)]) == 0
    assert "sample-api: checkpoint.json unreadable" in capsys.readouterr().out


def collected(root):
    """Raw data from a normal run, without avatars."""
    assert main(["collect", "--root", str(root), "--repo", "sample-api", "--no-avatars"]) == 0


def test_avatars_only_downloads_missing_avatars_from_the_raw_data_without_fetching_repos(root, fake, capsys):
    collected(root)
    raw = root / "data" / "raw" / "sample-api"
    before = {p.name: p.read_bytes() for p in raw.iterdir()}
    fake.clear()
    capsys.readouterr()
    assert main(["collect", "--root", str(root), "--avatars-only"]) == 0
    out = capsys.readouterr().out
    assert fake["runner"].calls == []                       # nothing asked of GitHub: the account avatar worked
    assert {p.name: p.read_bytes() for p in raw.iterdir()} == before
    assert (root / "data" / "avatars" / "ada-dev.png").read_bytes() == b"png"
    assert (root / "data" / "avatars" / "placeholder.png").is_file()
    assert json.loads((root / "data" / "raw" / "avatars-failed.json").read_text()) == []
    assert "avatars: 1 downloaded, 0 failed" in out


def test_avatars_only_uses_the_app_route_for_bots_and_exits_1_on_failures(root, fake, monkeypatch, capsys):
    folder = root / "data" / "raw" / "sample-api"
    folder.mkdir(parents=True)
    (folder / "commits.jsonl").write_text(json.dumps({"sha": "a", "author_login": "sample-bot[bot]"}) + "\n"
                                          + json.dumps({"sha": "b", "author_login": "helper-bot[bot]"}) + "\n")

    def fetch(url):
        if url.startswith("https://github.com/"):
            raise OSError("HTTP 404")
        return "image/png", b"app"
    monkeypatch.setattr(avatars, "fetch_url", fetch)

    made = {}

    def factory(**kwargs):
        def runner(args):
            made.setdefault("calls", []).append(args)
            if args[2] == "apps/sample-bot":
                return 0, json.dumps({"id": 5}), ""
            return 1, json.dumps({"message": "Not Found"}), "gh: Not Found (HTTP 404)"
        made["kwargs"] = kwargs
        return GitHub(runner, sleep=lambda s: None, **kwargs)
    monkeypatch.setattr(cli, "GitHub", factory)
    assert main(["collect", "--root", str(root), "--avatars-only"]) == 1
    out = capsys.readouterr().out
    assert sorted(c[2] for c in made["calls"]) == ["apps/helper-bot", "apps/sample-bot"]
    assert (root / "data" / "avatars" / "sample-bot_bot.png").read_bytes() == b"app"
    assert json.loads((folder.parent / "avatars-failed.json").read_text()) == ["helper-bot[bot]"]
    assert "avatars failed (placeholder used): helper-bot[bot]" in out


def test_avatars_only_dry_run_counts_what_would_be_downloaded(root, fake, capsys):
    collected(root)
    fake.clear()
    capsys.readouterr()
    assert main(["collect", "--root", str(root), "--avatars-only", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert fake == {}
    assert "dry run: 1 avatar would be downloaded" in out
    assert not (root / "data" / "avatars").exists()
    assert not (root / "data" / "raw" / "avatars-failed.json").exists()


@pytest.mark.parametrize("args", [["--repo", "sample-api"], ["--metric", "commits"], ["--since", "2026-07-01"],
                                  ["--until", "2026-07-01"], ["--full"], ["--max-requests", "5"], ["--no-avatars"]])
def test_avatars_only_refuses_flags_about_fetching_repositories(root, fake, capsys, args):
    assert main(["collect", "--root", str(root), "--avatars-only", *args]) == 2
    err = capsys.readouterr().err
    assert "--avatars-only" in err and args[0] in err
    assert fake == {} and not (root / "data" / "raw").exists()


def test_avatars_only_needs_raw_data(root, fake, capsys):
    assert main(["collect", "--root", str(root), "--avatars-only"]) == 2
    assert "run collect first" in capsys.readouterr().err
