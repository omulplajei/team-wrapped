import pytest

from team_wrapped.scenes.loader import Entry, LoadError, load_scene, load_script


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def make_root(tmp_path, name):
    root = tmp_path / name
    root.mkdir()
    return root


def test_load_script_reads_entries_and_defaults(tmp_path):
    shared = make_root(tmp_path, "shared")
    write(shared / "scripts/s.yml", """
id: s
title: S title
period: 2026
scope: all
scenes:
  - scene: a
  - scene: b
    on_missing_data: skip
    duration: 5
""")
    script = load_script("s", [shared])
    assert script.title == "S title"
    assert script.period == 2026
    assert script.scope == "all"
    assert script.transition == "fade"
    assert script.music is None
    assert script.scenes == [Entry(scene="a"), Entry(scene="b", on_missing_data="skip", duration=5)]


def test_load_scene_defaults(tmp_path):
    shared = make_root(tmp_path, "shared")
    write(shared / "scenes/m.yml", "id: m\ntype: message\nparams: {text: hi}\n")
    scene = load_scene("m", [shared])
    assert scene.type == "message"
    assert scene.title == "m"          # title defaults to the id
    assert scene.requires == []
    assert scene.params == {"text": "hi"}
    assert scene.duration is None


def test_later_root_overrides_earlier(tmp_path):
    shared = make_root(tmp_path, "shared")
    private = make_root(tmp_path, "private")
    write(shared / "scenes/m.yml", "id: m\ntype: message\nparams: {text: shared}\n")
    write(private / "scenes/m.yml", "id: m\ntype: message\nparams: {text: private}\n")
    assert load_scene("m", [shared, private]).params["text"] == "private"
    assert load_scene("m", [shared]).params["text"] == "shared"


def test_missing_file_raises(tmp_path):
    shared = make_root(tmp_path, "shared")
    with pytest.raises(LoadError, match="scene 'nope' not found"):
        load_scene("nope", [shared])


def test_id_must_match_file_name(tmp_path):
    shared = make_root(tmp_path, "shared")
    write(shared / "scenes/m.yml", "id: other\ntype: message\n")
    with pytest.raises(LoadError, match="does not match file name"):
        load_scene("m", [shared])


def test_script_rejects_bad_on_missing_data_and_unknown_keys(tmp_path):
    shared = make_root(tmp_path, "shared")
    write(shared / "scripts/bad1.yml", "id: bad1\nscenes:\n  - scene: a\n    on_missing_data: maybe\n")
    write(shared / "scripts/bad2.yml", "id: bad2\nscenes:\n  - scene: a\n    durtion: 3\n")
    write(shared / "scripts/bad3.yml", "id: bad3\nscenes: []\n")
    with pytest.raises(LoadError, match="on_missing_data"):
        load_script("bad1", [shared])
    with pytest.raises(LoadError, match="unknown entry keys"):
        load_script("bad2", [shared])
    with pytest.raises(LoadError, match="non-empty list"):
        load_script("bad3", [shared])


def test_scene_requires_a_type(tmp_path):
    shared = make_root(tmp_path, "shared")
    write(shared / "scenes/m.yml", "id: m\n")
    with pytest.raises(LoadError, match="needs a 'type'"):
        load_scene("m", [shared])
