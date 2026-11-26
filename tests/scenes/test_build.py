import json
import re
import shutil

import pytest

from team_wrapped.cli import main
from team_wrapped.scenes.build import BuildError, build, transform_renderer


def read_payload(index):
    html = index.read_text()
    match = re.search(r'<script type="application/json" id="tw-data">(.*?)</script>', html, re.S)
    return json.loads(match.group(1).replace("<\\/", "</"))


def sample_copy(sample_root, tmp_path):
    data = tmp_path / "data"
    shutil.copytree(sample_root, data)
    return data


def test_build_year_wrapped_on_sample(repo_root, sample_root, tmp_path):
    result = build("year-wrapped", repo_root, sample_root, tmp_path / "dist")
    out = tmp_path / "dist" / "year-wrapped"
    assert result.index == out / "index.html"
    assert result.skipped == []
    for name in ["player.css", "timing.js", "presets.js", "player.js", "vendor/gsap.min.js"]:
        assert (out / "assets" / name).is_file(), name
    assert (out / "avatars" / "ada-dev.png").is_file()

    payload = read_payload(result.index)
    assert [s["id"] for s in payload["scenes"]] == ["year-in-numbers", "how-many-of-us"]
    assert [s["duration"] for s in payload["scenes"]] == [8.0, 10.0]
    assert payload["scenes"][0]["partial"] == ["delivery_volume.lines"]
    assert payload["scenes"][1]["partial"] == []
    assert payload["scenes"][0]["data"]["summary.totals"]["commits"] == 1240
    assert payload["script"]["music"] is None

    html = result.index.read_text()
    assert 'TeamWrapped.sceneTypes["stats"]' in html
    assert 'TeamWrapped.sceneTypes["headcount"]' in html
    assert 'TeamWrapped.sceneTypes["message"]' not in html   # only used types are inlined
    assert "export default" not in html


def test_build_fails_when_a_scene_is_unsupported(repo_root, sample_root, tmp_path):
    data = sample_copy(sample_root, tmp_path)
    (data / "derived" / "delivery_volume.json").unlink()
    with pytest.raises(BuildError) as error:
        build("year-wrapped", repo_root, data, tmp_path / "dist")
    assert error.value.report is not None
    assert not error.value.report.ok


def test_build_skips_scenes_marked_skip(repo_root, sample_root, tmp_path):
    data = sample_copy(sample_root, tmp_path)
    (data / "derived" / "delivery_volume.json").unlink()
    (data / "scripts").mkdir()
    (data / "scripts" / "skipper.yml").write_text(
        "id: skipper\ntitle: Skipper\nscope: all\nscenes:\n"
        "  - scene: year-in-numbers\n    on_missing_data: skip\n"
        "  - scene: how-many-of-us\n")
    result = build("skipper", repo_root, data, tmp_path / "dist")
    assert result.skipped == ["year-in-numbers"]
    assert [s["id"] for s in read_payload(result.index)["scenes"]] == ["how-many-of-us"]


def test_build_copies_local_music(repo_root, sample_root, tmp_path):
    data = sample_copy(sample_root, tmp_path)
    (data / "assets").mkdir()
    (data / "assets" / "theme.mp3").write_bytes(b"fake")
    (data / "scripts").mkdir()
    (data / "scripts" / "tune.yml").write_text(
        "id: tune\nscope: all\nscenes:\n  - scene: how-many-of-us\n"
        "music: {file: theme.mp3, volume: 0.3}\n")
    result = build("tune", repo_root, data, tmp_path / "dist")
    music = read_payload(result.index)["script"]["music"]
    assert music == {"src": "assets/music/theme.mp3", "volume": 0.3, "loop": True}
    assert (tmp_path / "dist" / "tune" / "assets" / "music" / "theme.mp3").read_bytes() == b"fake"


def test_build_accepts_music_url_and_rejects_missing_file(repo_root, sample_root, tmp_path):
    data = sample_copy(sample_root, tmp_path)
    (data / "scripts").mkdir()
    (data / "scripts" / "url.yml").write_text(
        "id: url\nscope: all\nscenes:\n  - scene: how-many-of-us\nmusic: {file: 'https://example.com/a.mp3'}\n")
    (data / "scripts" / "gone.yml").write_text(
        "id: gone\nscope: all\nscenes:\n  - scene: how-many-of-us\nmusic: {file: nothere.mp3}\n")
    result = build("url", repo_root, data, tmp_path / "dist")
    assert read_payload(result.index)["script"]["music"]["src"] == "https://example.com/a.mp3"
    with pytest.raises(BuildError, match="nothere.mp3"):
        build("gone", repo_root, data, tmp_path / "dist")


def test_transform_renderer():
    out = transform_renderer("x", "export default { render() {} };")
    assert out.startswith('TeamWrapped.sceneTypes["x"] = ')
    assert "export default" not in out
    with pytest.raises(BuildError, match="must not use import"):
        transform_renderer("x", 'import a from "./a.js";\nexport default {};')
    with pytest.raises(BuildError, match="exactly one"):
        transform_renderer("x", "export default {};\nexport default {};")
    with pytest.raises(BuildError, match="exactly one"):
        transform_renderer("x", "const a = 1;")


def test_cli_build(repo_root, tmp_path, capsys):
    code = main(["build", "year-wrapped", "--root", str(repo_root), "--data", "data-sample",
                 "--out", str(tmp_path / "dist")])
    assert code == 0
    assert (tmp_path / "dist" / "year-wrapped" / "index.html").is_file()
    assert "index.html" in capsys.readouterr().out
