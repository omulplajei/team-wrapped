import pytest

from team_wrapped.scenes.loader import LoadError
from team_wrapped.scenes.theme import DEFAULT_COLORS, DEFAULT_THEME, css_overrides, load_theme


def make_theme(root, name="brand", yml="", files=("logo.png", "bg1.png", "bg2.png")):
    folder = root / "themes" / name
    (folder / "assets").mkdir(parents=True)
    (folder / "theme.yml").write_text(yml)
    for f in files:
        (folder / "assets" / f).write_bytes(b"png")
    return folder


FULL = """
name: brand
colors:
  background: "#112233"
  accent: "#ff8800"
  controls-bg: "rgba(23, 43, 77, 0.85)"
font: '"Acme Sans", system-ui, sans-serif'
logo: assets/logo.png
backdrop:
  images: [assets/bg1.png, assets/bg2.png]
  opacity: 0.4
"""


def test_default_theme_needs_no_files(tmp_path):
    assert load_theme("default", [tmp_path]) is DEFAULT_THEME
    assert css_overrides(DEFAULT_THEME) == ""


def test_full_theme_is_loaded_and_merged_over_the_defaults(tmp_path):
    folder = make_theme(tmp_path, yml=FULL)
    theme = load_theme("brand", [tmp_path])
    assert theme.name == "brand"
    assert theme.colors["background"] == "#112233"
    assert theme.colors["text"] == DEFAULT_COLORS["text"]          # untouched tokens keep their default
    assert theme.font == '"Acme Sans", system-ui, sans-serif'
    assert theme.logo == (folder / "assets" / "logo.png").resolve()
    assert theme.backdrop_images == [(folder / "assets" / "bg1.png").resolve(), (folder / "assets" / "bg2.png").resolve()]
    assert theme.backdrop_opacity == 0.4


def test_css_overrides_only_lists_what_differs(tmp_path):
    make_theme(tmp_path, yml=FULL)
    css = css_overrides(load_theme("brand", [tmp_path]))
    assert css.startswith(":root {") and css.endswith("}")
    assert "--tw-bg: #112233;" in css
    assert "--tw-accent: #ff8800;" in css
    assert "--tw-controls-bg: rgba(23, 43, 77, 0.85);" in css
    assert '--tw-font: "Acme Sans", system-ui, sans-serif;' in css
    assert "--tw-text" not in css and "--tw-folder-top" not in css


def test_later_root_overrides_earlier(tmp_path):
    shared, private = tmp_path / "shared", tmp_path / "private"
    shared.mkdir(); private.mkdir()
    make_theme(shared, yml='colors:\n  accent: "#111111"\n')
    make_theme(private, yml='colors:\n  accent: "#222222"\n')
    assert load_theme("brand", [shared, private]).colors["accent"] == "#222222"
    assert load_theme("brand", [shared]).colors["accent"] == "#111111"


@pytest.mark.parametrize("yml, message", [
    ("colours: {}\n", "unknown keys"),
    ("name: other\n", "does not match"),
    ("colors:\n  nope: '#fff'\n", "unknown colour 'nope'"),
    ("colors:\n  accent: 'red; } body { display: none'\n", "invalid value"),
    ("colors:\n  accent: 5\n", "invalid value"),
    ("font: 'x; } y {'\n", "font"),
    ("logo: ../outside.png\n", "inside the theme folder"),
    ("logo: /etc/passwd\n", "inside the theme folder"),
    ("logo: assets/missing.png\n", "not found"),
    ("backdrop:\n  images: [assets/bg1.png]\n  opacity: 2\n", "opacity"),
    ("backdrop:\n  speed: 3\n", "unknown keys"),
])
def test_invalid_themes_are_rejected(tmp_path, yml, message):
    make_theme(tmp_path, yml=yml)
    (tmp_path / "themes" / "outside.png").write_bytes(b"png")
    with pytest.raises(LoadError, match=message):
        load_theme("brand", [tmp_path])


def test_unknown_theme_is_an_error(tmp_path):
    with pytest.raises(LoadError, match="theme 'nope' not found"):
        load_theme("nope", [tmp_path])


@pytest.mark.parametrize("name", ["../x", "/abs", "a/b", "", ".hidden"])
def test_invalid_theme_names_are_rejected(tmp_path, name):
    with pytest.raises(LoadError, match="invalid theme name"):
        load_theme(name, [tmp_path])


def _font_theme(tmp_path, font):
    import yaml
    make_theme(tmp_path, yml=yaml.safe_dump({"font": font}))
    return load_theme("brand", [tmp_path])


@pytest.mark.parametrize("font", [
    '"x', "'x", '"a" "b"', " ", "Arial\n", 'a; } b {',
    ", ".join(f"f{i}" for i in range(11)), "a" * 201,
])
def test_bad_fonts_are_rejected(tmp_path, font):
    with pytest.raises(LoadError, match="font"):
        _font_theme(tmp_path, font)


@pytest.mark.parametrize("font", ['"Acme Sans", system-ui, sans-serif', "Arial", "'Segoe UI', Roboto"])
def test_good_fonts_are_accepted(tmp_path, font):
    assert _font_theme(tmp_path, font).font == font


@pytest.mark.parametrize("value", ["#fff\n", "rgb(1,2,3)\n"])
def test_colour_with_trailing_newline_is_rejected(tmp_path, value):
    import yaml
    make_theme(tmp_path, yml=yaml.safe_dump({"colors": {"accent": value}}))
    with pytest.raises(LoadError, match="invalid value"):
        load_theme("brand", [tmp_path])


@pytest.mark.parametrize("value", ["#fff", "rgba(1, 2, 3, 0.5)"])
def test_good_colours_are_accepted(tmp_path, value):
    import yaml
    make_theme(tmp_path, yml=yaml.safe_dump({"colors": {"accent": value}}))
    assert load_theme("brand", [tmp_path]).colors["accent"] == value


def test_nul_in_asset_path_is_a_load_error(tmp_path):
    make_theme(tmp_path, yml='logo: "a\\0b.png"\n')
    with pytest.raises(LoadError):
        load_theme("brand", [tmp_path])


def test_empty_logo_is_a_load_error(tmp_path):
    make_theme(tmp_path, yml='logo: ""\n')
    with pytest.raises(LoadError):
        load_theme("brand", [tmp_path])


@pytest.mark.parametrize("yml", ["colors: []\n", 'colors: ""\n'])
def test_colors_must_be_a_mapping(tmp_path, yml):
    make_theme(tmp_path, yml=yml)
    with pytest.raises(LoadError, match="colors must be a mapping"):
        load_theme("brand", [tmp_path])


def test_null_colors_and_backdrop_mean_defaults(tmp_path):
    make_theme(tmp_path, yml="colors:\nbackdrop:\n")
    assert load_theme("brand", [tmp_path]).colors == DEFAULT_COLORS


def test_backdrop_must_be_a_mapping(tmp_path):
    make_theme(tmp_path, yml="backdrop: []\n")
    with pytest.raises(LoadError, match="backdrop"):
        load_theme("brand", [tmp_path])


def test_malformed_yaml_names_the_file(tmp_path):
    make_theme(tmp_path, yml="colors: [unclosed\n")
    with pytest.raises(LoadError, match="theme.yml"):
        load_theme("brand", [tmp_path])


def test_symlink_escaping_the_theme_folder_is_rejected(tmp_path):
    folder = make_theme(tmp_path, yml="logo: assets/link.png\n")
    outside = tmp_path / "secret.png"
    outside.write_bytes(b"png")
    try:
        (folder / "assets" / "link.png").symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks not supported")
    with pytest.raises(LoadError, match="inside the theme folder"):
        load_theme("brand", [tmp_path])


def test_same_file_name_in_different_folders_is_rejected(tmp_path):
    folder = make_theme(tmp_path, yml="logo: assets/logo.png\nbackdrop:\n  images: [assets/bg/logo.png]\n",
                        files=("logo.png",))
    (folder / "assets" / "bg").mkdir()
    (folder / "assets" / "bg" / "logo.png").write_bytes(b"other")
    with pytest.raises(LoadError, match="same file name"):
        load_theme("brand", [tmp_path])


def test_same_file_name_differing_by_case_is_rejected(tmp_path):
    folder = make_theme(tmp_path, yml="logo: assets/a/Logo.png\nbackdrop:\n  images: [assets/b/logo.png]\n",
                        files=())
    for sub, name in (("a", "Logo.png"), ("b", "logo.png")):
        (folder / "assets" / sub).mkdir()
        (folder / "assets" / sub / name).write_bytes(sub.encode())
    with pytest.raises(LoadError, match="same file name"):
        load_theme("brand", [tmp_path])


def test_logo_reused_as_a_backdrop_image_is_allowed(tmp_path):
    make_theme(tmp_path, yml="logo: assets/logo.png\nbackdrop:\n  images: [assets/logo.png]\n")
    theme = load_theme("brand", [tmp_path])
    assert theme.backdrop_images == [theme.logo]
