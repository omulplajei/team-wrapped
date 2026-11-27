import json
import re
import shutil
import subprocess

import pytest

from team_wrapped.cli import main
from team_wrapped.scenes.build import BuildError, build, transform_renderer
from team_wrapped.scenes.loader import LoadError, load_script


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
    scenes = {s["id"]: s for s in payload["scenes"]}
    assert [s["id"] for s in payload["scenes"]] == [
        "we-shipped", "we-looked-after-each-other", "year-in-numbers",
        "repos-touched", "we-changed-the-code", "how-many-of-us",
    ]
    assert [s["duration"] for s in payload["scenes"]] == [9.0, 6.0, 8.0, 8.0, 6.0, 10.0]
    assert scenes["we-shipped"]["partial"] == []
    assert scenes["we-changed-the-code"]["partial"] == ["delivery_volume.lines"]
    assert scenes["year-in-numbers"]["partial"] == ["delivery_volume.lines"]
    assert scenes["how-many-of-us"]["partial"] == []
    assert scenes["repos-touched"]["partial"] == []
    assert scenes["repos-touched"]["data"]["repos.touched"]["total"] == 14
    assert scenes["we-shipped"]["data"]["summary.totals"]["commits"] == 1240
    assert payload["script"]["music"] is None

    html = result.index.read_text()
    assert 'TeamWrapped.sceneTypes["stats"]' in html
    assert 'TeamWrapped.sceneTypes["headcount"]' in html
    assert 'TeamWrapped.sceneTypes["bignumber"]' in html
    assert 'TeamWrapped.sceneTypes["repogrid"]' in html
    assert 'TeamWrapped.sceneTypes["sequence"]' in html
    assert 'TeamWrapped.sceneTypes["message"]' not in html   # only used types are inlined
    assert "export default" not in html


def test_build_skips_both_line_data_scenes_when_lines_are_missing(repo_root, sample_root, tmp_path):
    data = sample_copy(sample_root, tmp_path)
    (data / "derived" / "delivery_volume.json").unlink()
    result = build("year-wrapped", repo_root, data, tmp_path / "dist")
    assert result.skipped == ["year-in-numbers", "we-changed-the-code"]
    assert [s["id"] for s in read_payload(result.index)["scenes"]] == [
        "we-shipped", "we-looked-after-each-other", "repos-touched", "how-many-of-us"]


def test_build_fails_when_a_scene_is_unsupported(repo_root, sample_root, tmp_path):
    data = sample_copy(sample_root, tmp_path)
    (data / "derived" / "summary.json").unlink()
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
    assert 'TeamWrapped.sceneTypes["x"] = ' in out
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


needs_node = pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")


def node_check(path):
    result = subprocess.run(["node", "--check", str(path)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


@needs_node
def test_transform_renderer_allows_code_before_export(tmp_path):
    out = transform_renderer("x", "const fmt = (n) => n + 1;\nexport default { render() { return fmt(1); } };")
    assert "export default" not in out
    path = tmp_path / "x.js"
    path.write_text("window.TeamWrapped = {sceneTypes: {}};\n" + out)
    node_check(path)


@needs_node
def test_shipped_renderers_transform_to_valid_js(repo_root, tmp_path):
    renders = sorted((repo_root / "web" / "scene-types").glob("*/render.js"))
    assert renders
    for render in renders:
        path = tmp_path / f"{render.parent.name}.js"
        path.write_text(transform_renderer(render.parent.name, render.read_text()))
        node_check(path)


@needs_node
def test_renderers_do_not_share_top_level_scope(tmp_path):
    a = transform_renderer("a", "const helper = 1;\nexport default { n: helper };")
    b = transform_renderer("b", "const helper = 1;\nexport default { n: helper };")
    path = tmp_path / "both.js"
    path.write_text("window.TeamWrapped = {sceneTypes: {}};\n" + a + "\n" + b)
    node_check(path)


NASTY_TITLE = "</title><script>alert(1)</script>"
NASTY_TEXT = "</script><img src=x onerror=alert(1)> <!--<script> <!--TW_RENDERERS--> {{TITLE}} \u2028 &amp;"


def test_build_embeds_hostile_strings_safely(repo_root, sample_root, tmp_path):
    data = sample_copy(sample_root, tmp_path)
    (data / "scenes").mkdir(exist_ok=True)
    (data / "scenes" / "nasty.yml").write_text(json.dumps(
        {"id": "nasty", "type": "message", "title": "Nasty", "params": {"text": NASTY_TEXT}}))
    (data / "scripts").mkdir(exist_ok=True)
    (data / "scripts" / "nasty-script.yml").write_text(json.dumps(
        {"id": "nasty-script", "title": NASTY_TITLE, "scope": "all", "scenes": [{"scene": "nasty"}]}))
    result = build("nasty-script", repo_root, data, tmp_path / "dist")
    page = result.index.read_text()
    assert "</script><img" not in page
    assert "<!--<script>" not in page
    assert "<!--TW_RENDERERS-->" not in page
    assert "<!--TW_" not in page
    assert page.count("{{TITLE}}") == 1   # only the hostile data string, never rescanned
    assert NASTY_TITLE not in page
    payload = read_payload(result.index)
    assert payload["script"]["title"] == NASTY_TITLE
    assert payload["scenes"][0]["params"]["text"] == NASTY_TEXT


def test_sample_build_has_no_leftover_markers(repo_root, sample_root, tmp_path):
    page = build("year-wrapped", repo_root, sample_root, tmp_path / "dist").index.read_text()
    assert "{{" not in page
    assert "<!--TW_" not in page


def music_script(data, name, music_line):
    (data / "scripts").mkdir(exist_ok=True)
    (data / "scripts" / f"{name}.yml").write_text(
        f"id: {name}\nscope: all\nscenes:\n  - scene: how-many-of-us\nmusic: {music_line}\n")


def test_build_replaces_stale_output(repo_root, sample_root, tmp_path):
    out = tmp_path / "dist" / "year-wrapped"
    (out / "avatars").mkdir(parents=True)
    (out / "avatars" / "old.png").write_bytes(b"x")
    (out / "assets" / "music").mkdir(parents=True)
    (out / "assets" / "music" / "old.mp3").write_bytes(b"x")
    build("year-wrapped", repo_root, sample_root, tmp_path / "dist")
    assert not (out / "avatars" / "old.png").exists()
    assert not (out / "assets" / "music" / "old.mp3").exists()
    assert (out / "avatars" / "ada-dev.png").is_file()
    assert (out / "index.html").is_file()


def test_failed_builds_leave_output_untouched(repo_root, sample_root, tmp_path):
    data = sample_copy(sample_root, tmp_path)
    music_script(data, "gone", "{file: nothere.mp3}")
    out_root = tmp_path / "dist"
    # no pre-existing folder: none is created
    with pytest.raises(BuildError):
        build("gone", repo_root, data, out_root)
    assert not (out_root / "gone").exists()
    # pre-existing folder: untouched
    (out_root / "gone").mkdir(parents=True)
    (out_root / "gone" / "marker.txt").write_text("keep")
    with pytest.raises(BuildError):
        build("gone", repo_root, data, out_root)
    assert (out_root / "gone" / "marker.txt").read_text() == "keep"
    # unsupported scene
    (data / "derived" / "summary.json").unlink()
    (out_root / "year-wrapped").mkdir()
    (out_root / "year-wrapped" / "marker.txt").write_text("keep")
    with pytest.raises(BuildError):
        build("year-wrapped", repo_root, data, out_root)
    assert (out_root / "year-wrapped" / "marker.txt").read_text() == "keep"


def test_music_file_must_stay_inside_assets(repo_root, sample_root, tmp_path):
    data = sample_copy(sample_root, tmp_path)
    (data / "assets").mkdir()
    (data / "evil.mp3").write_bytes(b"evil")
    music_script(data, "evil", "{file: ../evil.mp3}")
    music_script(data, "abs", "{file: '%s'}" % (data / "evil.mp3"))
    for name, needle in [("evil", "evil.mp3"), ("abs", "evil.mp3")]:
        with pytest.raises(BuildError, match=needle):
            build(name, repo_root, data, tmp_path / "dist")
        assert not (tmp_path / "dist" / name).exists()


def test_music_name_is_url_encoded_in_src(repo_root, sample_root, tmp_path):
    data = sample_copy(sample_root, tmp_path)
    (data / "assets").mkdir()
    (data / "assets" / "my song #1.mp3").write_bytes(b"fake")
    music_script(data, "odd", "{file: 'my song #1.mp3'}")
    result = build("odd", repo_root, data, tmp_path / "dist")
    assert read_payload(result.index)["script"]["music"]["src"] == "assets/music/my%20song%20%231.mp3"
    assert (tmp_path / "dist" / "odd" / "assets" / "music" / "my song #1.mp3").read_bytes() == b"fake"


def plain_script(data, name, scope, scene):
    (data / "scripts").mkdir(exist_ok=True)
    (data / "scripts" / f"{name}.yml").write_text(
        f"id: {name}\nscope: {scope}\nscenes:\n  - scene: {scene}\n")


def test_build_copies_only_referenced_avatars(repo_root, sample_root, tmp_path):
    build("year-wrapped", repo_root, sample_root, tmp_path / "dist")
    out = tmp_path / "dist" / "year-wrapped"
    assert (out / "avatars" / "ada-dev.png").is_file()
    assert (out / "avatars" / "placeholder.png").is_file()

    data = sample_copy(sample_root, tmp_path)
    plain_script(data, "alpha-only", "alpha", "how-many-of-us")
    build("alpha-only", repo_root, data, tmp_path / "dist2")
    out = tmp_path / "dist2" / "alpha-only"
    assert (out / "avatars" / "ada-dev.png").is_file()
    assert not (out / "avatars" / "ken-t.png").exists()


def test_build_without_avatar_scenes_has_no_avatars_folder(repo_root, sample_root, tmp_path):
    data = sample_copy(sample_root, tmp_path)
    plain_script(data, "nums", "all", "year-in-numbers")
    build("nums", repo_root, data, tmp_path / "dist")
    assert not (tmp_path / "dist" / "nums" / "avatars").exists()


def test_avatar_file_must_stay_inside_data_root(repo_root, sample_root, tmp_path):
    data = sample_copy(sample_root, tmp_path)
    contributors = data / "derived" / "contributors.json"
    contributors.write_text(contributors.read_text().replace("avatars/ada-dev.png", "../../outside.png"))
    plain_script(data, "bad", "all", "how-many-of-us")
    with pytest.raises(BuildError, match="outside.png"):
        build("bad", repo_root, data, tmp_path / "dist")
    assert not (tmp_path / "dist" / "bad").exists()


def test_missing_referenced_avatar_is_skipped(repo_root, sample_root, tmp_path):
    data = sample_copy(sample_root, tmp_path)
    (data / "avatars" / "ada-dev.png").unlink()
    plain_script(data, "gap", "all", "how-many-of-us")
    build("gap", repo_root, data, tmp_path / "dist")
    out = tmp_path / "dist" / "gap"
    assert not (out / "avatars" / "ada-dev.png").exists()
    assert (out / "avatars" / "placeholder.png").is_file()


def test_music_volume_must_be_a_fraction(repo_root, sample_root, tmp_path):
    data = sample_copy(sample_root, tmp_path)
    (data / "assets").mkdir()
    (data / "assets" / "t.mp3").write_bytes(b"fake")
    music_script(data, "loud", "{file: t.mp3, volume: 30}")
    music_script(data, "mute", "{file: t.mp3, volume: 0}")
    music_script(data, "full", "{file: t.mp3, volume: 1}")
    with pytest.raises(BuildError, match="volume"):
        build("loud", repo_root, data, tmp_path / "dist")
    for name, vol in (("mute", 0), ("full", 1)):
        result = build(name, repo_root, data, tmp_path / "dist")
        assert read_payload(result.index)["script"]["music"]["volume"] == vol


def test_quiet_scope_skips_the_repos_scene(repo_root, sample_root, tmp_path):
    data = sample_copy(sample_root, tmp_path)
    repos_file = data / "derived" / "repos.json"
    repos = json.loads(repos_file.read_text())
    repos["scopes"]["group:alpha"]["touched"] = {"total": 0, "list": []}
    repos_file.write_text(json.dumps(repos))
    (data / "scripts").mkdir(exist_ok=True)
    (data / "scripts" / "quiet.yml").write_text(
        "id: quiet\ntitle: Quiet\nscope: alpha\nscenes:\n"
        "  - scene: repos-touched\n    on_missing_data: skip\n"
        "  - scene: how-many-of-us\n")
    result = build("quiet", repo_root, data, tmp_path / "dist")
    assert result.skipped == ["repos-touched"]
    assert [s["id"] for s in read_payload(result.index)["scenes"]] == ["how-many-of-us"]


def test_year_wrapped_skips_the_repos_scene_when_data_is_missing(repo_root):
    script = load_script("year-wrapped", [repo_root])
    entry = next(e for e in script.scenes if e.scene == "repos-touched")
    assert entry.on_missing_data == "skip"


def test_repos_scene_only_shows_the_scope_repositories(repo_root, sample_root, tmp_path):
    data = sample_copy(sample_root, tmp_path)
    (data / "scripts").mkdir(exist_ok=True)
    (data / "scripts" / "alpha-only.yml").write_text(
        "id: alpha-only\ntitle: Alpha\nscope: alpha\nscenes:\n  - scene: repos-touched\n")
    result = build("alpha-only", repo_root, data, tmp_path / "dist")
    html = result.index.read_text()
    assert "sample-api" in html
    assert "sample-analytics" not in html


THEME_YML = """
colors:
  background: "#112233"
  accent: "#ff8800"
font: '"Acme Sans", system-ui, sans-serif'
logo: assets/logo.png
backdrop:
  images: [assets/bg 1.png, assets/bg2.png]
  opacity: 0.4
"""


def add_theme(data, yml=THEME_YML):
    folder = data / "themes" / "brand"
    (folder / "assets").mkdir(parents=True)
    (folder / "theme.yml").write_text(yml)
    for name in ("logo.png", "bg 1.png", "bg2.png"):
        (folder / "assets" / name).write_bytes(b"png")


def test_default_build_has_no_theme_output(repo_root, sample_root, tmp_path):
    result = build("year-wrapped", repo_root, sample_root, tmp_path / "dist")
    html = result.index.read_text()
    assert 'id="tw-theme"' not in html and "tw-logo" not in html and "<!--TW_" not in html
    assert not (result.out_dir / "assets" / "theme").exists()
    assert read_payload(result.index)["script"]["theme"] is None
    assert 'id="tw-backdrop"' in html


def test_theme_is_applied_to_the_page(repo_root, sample_root, tmp_path):
    data = sample_copy(sample_root, tmp_path)
    add_theme(data)
    result = build("year-wrapped", repo_root, data, tmp_path / "dist", theme="brand")
    html = result.index.read_text()
    assert '<style id="tw-theme">:root {' in html
    assert "--tw-bg: #112233;" in html and "--tw-accent: #ff8800;" in html
    assert '--tw-font: "Acme Sans", system-ui, sans-serif;' in html
    assert html.count('<img class="tw-logo"') == 2            # start and end screens
    assert 'src="assets/theme/logo.png"' in html
    for name in ("logo.png", "bg 1.png", "bg2.png"):
        assert (result.out_dir / "assets" / "theme" / name).is_file()
    theme = read_payload(result.index)["script"]["theme"]
    assert theme == {"backdrop": {"images": ["assets/theme/bg%201.png", "assets/theme/bg2.png"], "opacity": 0.4}}


def test_script_theme_key_selects_the_theme(repo_root, sample_root, tmp_path):
    data = sample_copy(sample_root, tmp_path)
    add_theme(data)
    (data / "scripts").mkdir()
    (data / "scripts" / "branded.yml").write_text(
        "id: branded\ntheme: brand\nscope: all\nscenes:\n  - scene: how-many-of-us\n")
    result = build("branded", repo_root, data, tmp_path / "dist")
    assert "--tw-bg: #112233;" in result.index.read_text()
    # an explicit argument wins over the script's key
    other = build("branded", repo_root, data, tmp_path / "dist2", theme="default")
    assert 'id="tw-theme"' not in other.index.read_text()


def test_bad_or_unknown_theme_writes_nothing(repo_root, sample_root, tmp_path):
    data = sample_copy(sample_root, tmp_path)
    add_theme(data, yml='colors:\n  accent: "red; } body { display: none"\n')
    with pytest.raises(LoadError, match="invalid value"):
        build("year-wrapped", repo_root, data, tmp_path / "dist", theme="brand")
    with pytest.raises(LoadError, match="theme 'nope' not found"):
        build("year-wrapped", repo_root, data, tmp_path / "dist", theme="nope")
    assert not (tmp_path / "dist").exists()


def test_cli_build_theme_option(repo_root, sample_root, tmp_path, capsys):
    data = sample_copy(sample_root, tmp_path)
    add_theme(data)
    code = main(["build", "year-wrapped", "--root", str(repo_root), "--data", str(data),
                 "--out", str(tmp_path / "dist"), "--theme", "brand"])
    assert code == 0
    assert "--tw-bg: #112233;" in (tmp_path / "dist" / "year-wrapped" / "index.html").read_text()
    assert main(["build", "year-wrapped", "--root", str(repo_root), "--data", str(data),
                 "--out", str(tmp_path / "dist"), "--theme", "nope"]) == 2
    assert "theme 'nope' not found" in capsys.readouterr().err


def test_logo_reused_as_the_only_backdrop_image_is_copied_once(repo_root, sample_root, tmp_path):
    data = sample_copy(sample_root, tmp_path)
    add_theme(data, yml="logo: assets/logo.png\nbackdrop:\n  images: [assets/logo.png]\n")
    result = build("year-wrapped", repo_root, data, tmp_path / "dist", theme="brand")
    assert [p.name for p in (result.out_dir / "assets" / "theme").iterdir()] == ["logo.png"]
    theme = read_payload(result.index)["script"]["theme"]
    assert theme["backdrop"]["images"] == ["assets/theme/logo.png"]
