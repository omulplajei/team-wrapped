"""`collect` and `status` on the command line, with a fake gh."""
import pytest
from collect_fakes import commit_node, history, make_client, not_found, pr_node, search

from team_wrapped import cli
from team_wrapped.cli import main
from team_wrapped.collect import avatars

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
