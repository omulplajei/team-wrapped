"""Themes: colours, font, logo and backdrop images for the player page (spec section 14)."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .loader import LoadError

DEFAULT_COLORS = {
    "background": "#0f1115",
    "text": "#f2f3f5",
    "accent": "#5eead4",
    "warning": "#e6b450",
    "surface": "#3a3d44",
    "controls-bg": "rgba(0, 0, 0, 0.55)",
    "button-bg": "#f2f3f5",
    "button-text": "#0f1115",
    "focus": "#8ab4ff",
    "folder-top": "#f4c75f",
    "folder-bottom": "#e0a93b",
    "folder-tab": "#d99a2b",
    "folder-text": "#2a1f05",
    "cat-core": "#7fd49a",
    "cat-extension": "#7aaef0",
    "cat-support": "#b49cf0",
    "cat-none": "#9aa0a8",
}

_VARIABLES = {key: "--tw-" + {"background": "bg"}.get(key, key) for key in DEFAULT_COLORS}

_NUMBER = r"\d+(?:\.\d+)?%?"
_COLOR = re.compile(
    rf"#(?:[0-9a-fA-F]{{3}}|[0-9a-fA-F]{{4}}|[0-9a-fA-F]{{6}}|[0-9a-fA-F]{{8}})"
    rf"|rgba?\(\s*{_NUMBER}\s*(?:,\s*{_NUMBER}\s*){{2,3}}\)"
)
_WORD = r"[A-Za-z_-][A-Za-z0-9_-]*"  # an unquoted family word must not start with a digit
_FAMILY = rf"\"[A-Za-z0-9 ._-]+\"|'[A-Za-z0-9 ._-]+'|{_WORD}(?: {_WORD})*"
_FONT = re.compile(rf"(?:{_FAMILY})(?:\s*,\s*(?:{_FAMILY})){{0,9}}")
_THEME_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*")
_IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg")
_LOGO_NAME = re.compile(r"[a-z][a-z0-9-]*")
_KEYS = {"name", "colors", "font", "logo", "logos", "backdrop"}
_BACKDROP_KEYS = {"images", "opacity"}


@dataclass(frozen=True)
class Theme:
    name: str
    colors: dict
    font: str | None = None
    logo: Path | None = None
    logos: dict = field(default_factory=dict)
    backdrop_images: list = field(default_factory=list)
    backdrop_opacity: float = 0.35
    dir: Path | None = None


DEFAULT_THEME = Theme(name="default", colors=dict(DEFAULT_COLORS))


def _asset(folder: Path, value, what: str) -> Path:
    if not isinstance(value, str) or not value:
        raise LoadError(f"{folder}: {what} must be a file path")
    inside = f"{folder}: {what} '{value}' must stay inside the theme folder"
    if Path(value).is_absolute():
        raise LoadError(inside)
    try:
        path = (folder / value).resolve()
        if not path.is_relative_to(folder.resolve()):
            raise LoadError(inside)
    except (ValueError, OSError):
        raise LoadError(inside) from None
    if not path.is_file():
        raise LoadError(f"{folder}: {what} '{value}' not found")
    if path.suffix.lower() not in _IMAGE_SUFFIXES:
        raise LoadError(f"{folder}: {what} '{value}' must be an image file ({', '.join(_IMAGE_SUFFIXES)})")
    return path


def load_theme(name: str, roots) -> Theme:
    if not _THEME_NAME.fullmatch(name):
        raise LoadError(f"invalid theme name '{name}'")
    found = None
    for root in roots:
        candidate = Path(root) / "themes" / name
        if (candidate / "theme.yml").is_file():
            found = candidate  # later roots override earlier ones
    if found is None:
        if name == "default":
            return DEFAULT_THEME
        searched = ", ".join(str(r) for r in roots)
        raise LoadError(f"theme '{name}' not found in: {searched}")

    try:
        data = yaml.safe_load((found / "theme.yml").read_text()) or {}
    except yaml.YAMLError as error:
        raise LoadError(f"{found / 'theme.yml'}: invalid YAML: {error}") from None
    if not isinstance(data, dict):
        raise LoadError(f"{found / 'theme.yml'}: must be a mapping")
    unknown = set(data) - _KEYS
    if unknown:
        raise LoadError(f"{found / 'theme.yml'}: unknown keys {sorted(unknown)}")
    if data.get("name", name) != name:
        raise LoadError(f"{found / 'theme.yml'}: name '{data.get('name')}' does not match folder '{name}'")

    colors = dict(DEFAULT_COLORS)
    given = data.get("colors")
    if given is None:
        given = {}
    if not isinstance(given, dict):
        raise LoadError(f"{found / 'theme.yml'}: colors must be a mapping")
    for key, value in given.items():
        if key not in DEFAULT_COLORS:
            raise LoadError(f"{found / 'theme.yml'}: unknown colour '{key}'")
        if not isinstance(value, str) or not _COLOR.fullmatch(value):
            raise LoadError(f"{found / 'theme.yml'}: colour '{key}' has an invalid value")
        colors[key] = value

    font = data.get("font")
    if font is not None and (not isinstance(font, str) or len(font) > 200 or not _FONT.fullmatch(font)):
        raise LoadError(f"{found / 'theme.yml'}: font has an invalid value")

    logo = _asset(found, data["logo"], "logo") if "logo" in data else None

    given_logos = data.get("logos")
    if given_logos is None:
        given_logos = {}
    if not isinstance(given_logos, dict):
        raise LoadError(f"{found / 'theme.yml'}: logos must be a mapping of name to file")
    logos = {}
    for logo_name, value in given_logos.items():
        if not isinstance(logo_name, str) or not _LOGO_NAME.fullmatch(logo_name):
            raise LoadError(f"{found / 'theme.yml'}: logo name {logo_name!r} must be lowercase letters, digits and dashes")
        logos[logo_name] = _asset(found, value, f"logo '{logo_name}'")

    backdrop = data.get("backdrop")
    if backdrop is None:
        backdrop = {}
    if not isinstance(backdrop, dict) or set(backdrop) - _BACKDROP_KEYS:
        raise LoadError(f"{found / 'theme.yml'}: backdrop has unknown keys or is not a mapping")
    images = backdrop.get("images") or []
    if not isinstance(images, list):
        raise LoadError(f"{found / 'theme.yml'}: backdrop images must be a list")
    opacity = backdrop.get("opacity", 0.35)
    if isinstance(opacity, bool) or not isinstance(opacity, (int, float)) or not 0 <= opacity <= 1:
        raise LoadError(f"{found / 'theme.yml'}: backdrop opacity must be a number between 0 and 1")

    backdrop_images = [_asset(found, v, "backdrop image") for v in images]
    by_name: dict = {}
    for path in dict.fromkeys(([logo] if logo else []) + list(logos.values()) + backdrop_images):
        by_name.setdefault(path.name.casefold(), []).append(path.name)
    names = [n for group in by_name.values() if len(group) > 1 for n in group]
    if names:
        raise LoadError(f"{found / 'theme.yml'}: assets with the same file name: {sorted(names)}")

    return Theme(
        name=name,
        colors=colors,
        font=font,
        logo=logo,
        logos=logos,
        backdrop_images=backdrop_images,
        backdrop_opacity=float(opacity),
        dir=found,
    )


def css_overrides(theme: Theme) -> str:
    """CSS variable overrides for the page: only what differs from the defaults."""
    declarations = [
        f"{_VARIABLES[key]}: {value};"
        for key, value in theme.colors.items()
        if value != DEFAULT_COLORS[key]
    ]
    if theme.font:
        declarations.append(f"--tw-font: {theme.font};")
    return ":root { " + " ".join(declarations) + " }" if declarations else ""
