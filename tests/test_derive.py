import json
import shutil

import pytest

from team_wrapped.cli import main
from team_wrapped.config import Config, load_config
from team_wrapped.derive import derive_repos, write_repos


def config(repos, groups=None, since=None, until=None):
    return Config(org="sample-org", repos=repos, groups=groups or {}, since=since, until=until)


def test_derive_lists_every_repo_sorted_and_counted():
    out = derive_repos(config(["sample-web", "sample-api", "sample-docs"]))
    assert out["basis"] == "configuration"
    assert list(out["scopes"]) == ["all"]
    touched = out["scopes"]["all"]["touched"]
    assert touched == {"total": 3, "list": [{"name": "sample-api"}, {"name": "sample-docs"}, {"name": "sample-web"}]}


def test_derive_adds_one_scope_per_group():
    out = derive_repos(config(["c", "a", "b"], {"g1": ["c", "a"], "g2": ["b"]}, "2026-01-01", "2026-12-31"))
    assert list(out["scopes"]) == ["all", "group:g1", "group:g2"]
    assert out["scopes"]["group:g1"]["touched"] == {"total": 2, "list": [{"name": "a"}, {"name": "c"}]}
    assert out["scopes"]["group:g2"]["touched"]["total"] == 1
    assert out["period"] == {"since": "2026-01-01", "until": "2026-12-31"}


def test_sample_config_matches_the_sample_derived_file(repo_root, sample_root):
    derived = derive_repos(load_config(sample_root / "config.yml"))
    shipped = json.loads((sample_root / "derived" / "repos.json").read_text())
    assert derived == shipped       # the shipped sample stays consistent with its config


def test_write_repos_creates_the_file(tmp_path):
    path = write_repos(config(["a", "b"]), tmp_path)
    assert path == tmp_path / "derived" / "repos.json"
    assert json.loads(path.read_text())["scopes"]["all"]["touched"]["total"] == 2
    assert path.read_text().endswith("\n")


def test_cli_derive_repos(repo_root, sample_root, tmp_path, capsys):
    data = tmp_path / "data"
    shutil.copytree(sample_root, data)
    (data / "derived" / "repos.json").unlink()
    code = main(["derive-repos", "--root", str(repo_root), "--data", str(data)])
    assert code == 0
    assert "14 repositories, 2 groups" in capsys.readouterr().out
    assert (data / "derived" / "repos.json").is_file()


def test_cli_derive_repos_reports_errors(repo_root, tmp_path, capsys):
    (tmp_path / "data").mkdir()
    code = main(["derive-repos", "--root", str(repo_root), "--data", str(tmp_path / "data")])
    assert code == 2
    assert "not found" in capsys.readouterr().err


def test_sorting_is_case_insensitive():
    out = derive_repos(config(["b", "A", "c"]))
    assert [r["name"] for r in out["scopes"]["all"]["touched"]["list"]] == ["A", "b", "c"]
    out = derive_repos(config(["B", "a"]))
    assert [r["name"] for r in out["scopes"]["all"]["touched"]["list"]] == ["a", "B"]


def test_failed_write_leaves_existing_file_untouched(tmp_path, monkeypatch):
    path = write_repos(config(["a"]), tmp_path)
    before = path.read_text()

    def boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr("team_wrapped.derive.json.dumps", boom)
    with pytest.raises(RuntimeError):
        write_repos(config(["a", "b"]), tmp_path)
    assert path.read_text() == before
    assert list(path.parent.glob("*.tmp")) == []
