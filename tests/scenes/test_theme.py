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
  background: "#252f38"
  accent: "#009cde"
  controls-bg: "rgba(23, 43, 77, 0.85)"
font: '"Effra", system-ui, sans-serif'
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
    assert theme.colors["background"] == "#252f38"
    assert theme.colors["text"] == DEFAULT_COLORS["text"]          # untouched tokens keep their default
    assert theme.font == '"Effra", system-ui, sans-serif'
    assert theme.logo == (folder / "assets" / "logo.png").resolve()
    assert theme.backdrop_images == [(folder / "assets" / "bg1.png").resolve(), (folder / "assets" / "bg2.png").resolve()]
    assert theme.backdrop_opacity == 0.4


def test_css_overrides_only_lists_what_differs(tmp_path):
    make_theme(tmp_path, yml=FULL)
    css = css_overrides(load_theme("brand", [tmp_path]))
    assert css.startswith(":root {") and css.endswith("}")
    assert "--tw-bg: #252f38;" in css
    assert "--tw-accent: #009cde;" in css
    assert "--tw-controls-bg: rgba(23, 43, 77, 0.85);" in css
    assert '--tw-font: "Effra", system-ui, sans-serif;' in css
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
