from team_wrapped.cli import main


def test_validate_year_wrapped_on_sample(repo_root, capsys):
    code = main(["validate-script", "year-wrapped", "--root", str(repo_root), "--data", "data-sample"])
    out = capsys.readouterr().out
    assert code == 0
    assert "year-in-numbers: partial" in out
    assert "how-many-of-us: supported" in out
    assert "capability-commits: supported" in out


def test_validate_reports_failure(tmp_path, repo_root, capsys):
    root = tmp_path / "repo"
    (root / "docs").mkdir(parents=True)
    (root / "docs" / "datasets.md").write_text("| `summary.totals` | x |\n")
    (root / "web" / "scene-types" / "stats").mkdir(parents=True)
    (root / "web" / "scene-types" / "stats" / "type.yml").write_text(
        "name: stats\ndefault_duration: 8\nrequired_params: [items]\n")
    (root / "scenes").mkdir()
    (root / "scenes" / "s.yml").write_text(
        "id: s\ntype: stats\nrequires:\n  - {dataset: summary.totals, fields: [commits]}\nparams: {items: []}\n")
    (root / "scripts").mkdir()
    (root / "scripts" / "x.yml").write_text("id: x\nscenes:\n  - scene: s\n")
    (root / "data").mkdir()  # no derived data at all
    code = main(["validate-script", "x", "--root", str(root), "--data", "data"])
    out = capsys.readouterr().out
    assert code == 1
    assert "s: unsupported" in out
    assert "no data for 'summary.totals' in scope 'all'" in out


def test_validate_missing_script_exits_2(repo_root, capsys):
    code = main(["validate-script", "nope", "--root", str(repo_root), "--data", "data-sample"])
    assert code == 2
    assert "script 'nope' not found" in capsys.readouterr().err
