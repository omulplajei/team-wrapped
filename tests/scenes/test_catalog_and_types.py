import pytest

from team_wrapped.scenes.catalog import load_catalog
from team_wrapped.scenes.loader import LoadError
from team_wrapped.scenes.scene_types import load_scene_types


def test_catalog_lists_planned_datasets(repo_root):
    names = load_catalog(repo_root / "docs" / "datasets.md")
    for expected in [
        "contributors",
        "repos.touched",
        "summary.totals",
        "summary.activity_by_weekday",
        "summary.activity_by_hour",       # two names in one table cell
        "delivery_volume.lines",
        "review_collab.outcome_mix",
        "curiosities.biggest_pr_by_lines",
        "curiosities.busiest_day",
        "curiosities.busiest_month",
        "curiosities.longest_commit_streak",
        "curiosities.longest_merge_streak",
        "curiosities.most_lines_deleted_pr",
        "curiosities.longest_comment_chain",
        "curiosities.most_reviewed_pr",
        "curiosities.most_commented_pr",
        "curiosities.most_commits_pr",
    ]:
        assert expected in names
    assert "nope.nothing" not in names


def test_catalog_from_small_file(tmp_path):
    f = tmp_path / "datasets.md"
    f.write_text("| Dataset | Fields |\n|---|---|\n| `a.b`, `a.c` | x |\n| `plain` | y |\n")
    assert load_catalog(f) == {"contributors", "a.b", "a.c"}


def test_scene_types_load_from_web(repo_root):
    types = load_scene_types(repo_root / "web")
    assert set(types) >= {"message", "stats", "headcount", "cast"}
    assert types["stats"].default_duration == 8.0
    assert types["stats"].required_params == ["items"]
    assert types["headcount"].required_params == ["groups"]
    assert types["cast"].default_duration == 14.0
    assert types["cast"].required_params == ["stages"]
    assert types["message"].dir.name == "message"


def test_scene_type_name_must_match_folder(tmp_path):
    folder = tmp_path / "scene-types" / "stats"
    folder.mkdir(parents=True)
    (folder / "type.yml").write_text("name: other\ndefault_duration: 3\n")
    with pytest.raises(LoadError, match="does not match folder"):
        load_scene_types(tmp_path)
