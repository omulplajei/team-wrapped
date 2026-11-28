"""Load and validate the private collection config (data/config.yml, spec section 4)."""
from __future__ import annotations

import datetime
import re
from dataclasses import dataclass, field
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml

from .scenes.loader import LoadError

_KNOWN_KEYS = {
    "org", "repos", "groups", "since", "until", "metrics", "commit_branches", "bot_patterns", "bot_names",
    "aliases", "timezone", "curiosities", "avatars", "reviewer_pairs", "group_info",
}
CATEGORIES = ("core", "extension", "support")
METRICS = ("commits", "pull_requests", "reviews", "comments")
DEFAULT_BOT_PATTERNS = ("*[bot]",)
_ORG = re.compile(r"[A-Za-z0-9-]+")
_REPO = re.compile(r"[A-Za-z0-9._-]+")
_GROUP = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*")


@dataclass(frozen=True)
class Config:
    org: str
    repos: list
    groups: dict = field(default_factory=dict)
    group_info: dict = field(default_factory=dict)   # group -> {"label": str, "category": str | None}, every group
    since: str | None = None
    until: str | None = None
    metrics: list = field(default_factory=lambda: list(METRICS))
    bot_patterns: list = field(default_factory=lambda: list(DEFAULT_BOT_PATTERNS))
    bot_names: dict = field(default_factory=dict)   # bot login -> display name
    aliases: dict = field(default_factory=dict)
    timezone: str = "UTC"
    top_n: int = 5                  # curiosities.top_n
    download_avatars: bool = True   # avatars.download
    commit_branches: str = "default"    # `default` or `all`; `collect` supports `default` only for now


def _date(path, value) -> datetime.date | None:
    if value is None:
        return None
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    if isinstance(value, str):
        try:
            return datetime.date.fromisoformat(value)
        except ValueError:
            pass
    raise LoadError(f"{path}: since/until must be a date like 2026-01-31")


def _metrics(path, value) -> list:
    if value is None:
        return list(METRICS)
    if not isinstance(value, list) or not value:
        raise LoadError(f"{path}: metrics must be a non-empty list of {', '.join(METRICS)}")
    unknown = [m for m in value if m not in METRICS]
    if unknown:
        raise LoadError(f"{path}: unknown metric(s) {unknown}; choose from {', '.join(METRICS)}")
    return [m for m in METRICS if m in value]       # canonical order, duplicates collapse


def _bot_patterns(path, value) -> list:
    if value is None:
        return list(DEFAULT_BOT_PATTERNS)
    if not isinstance(value, list) or not all(isinstance(v, str) and v for v in value):
        raise LoadError(f"{path}: bot_patterns must be a list of non-empty strings")
    return list(value)


def _bot_names(path, value) -> dict:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise LoadError(f"{path}: bot_names must be a mapping of bot login to display name")
    for login, name in value.items():
        if not isinstance(login, str) or not login.strip() or not isinstance(name, str) or not name.strip():
            raise LoadError(f"{path}: bot_names must map a login (text) to a display name (text); "
                            f"got {login!r}: {name!r}")
    return {login.strip(): name.strip() for login, name in value.items()}


def _aliases(path, value) -> dict:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise LoadError(f"{path}: aliases must be a mapping of alias to canonical login")
    for alias, canonical in value.items():
        if not isinstance(alias, str) or not alias or not isinstance(canonical, str) or not canonical:
            raise LoadError(f"{path}: aliases must map a login or email (text) to a login (text); "
                            f"got {alias!r}: {canonical!r}")
        if "@" in canonical:
            raise LoadError(f"{path}: alias '{alias}' must map to a login, not an email")
    return dict(value)


def _timezone(path, value) -> str:
    if value is None:
        return "UTC"
    try:
        if not isinstance(value, str) or not value:
            raise ValueError(value)
        ZoneInfo(value)
    except (ValueError, ZoneInfoNotFoundError, OSError) as error:
        raise LoadError(f"{path}: timezone must be an IANA name like Europe/Bucharest "
                        f"(got {value!r})") from error
    return value


def _top_n(path, section) -> int:
    if section is None:
        return 5
    if not isinstance(section, dict):
        raise LoadError(f"{path}: curiosities must be a mapping (top_n: 5)")
    unknown = set(section) - {"top_n"}
    if unknown:
        raise LoadError(f"{path}: unknown curiosities key(s) {sorted(map(str, unknown))}")
    value = section.get("top_n", 5)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise LoadError(f"{path}: curiosities.top_n must be an integer of at least 1")
    return value


def _download_avatars(path, section) -> bool:
    if section is None:
        return True
    if not isinstance(section, dict):
        raise LoadError(f"{path}: avatars must be a mapping (download: true)")
    unknown = set(section) - {"download"}
    if unknown:
        raise LoadError(f"{path}: unknown avatars key(s) {sorted(map(str, unknown))}")
    value = section.get("download", True)
    if not isinstance(value, bool):
        raise LoadError(f"{path}: avatars.download must be true or false")
    return value


def _commit_branches(path, value) -> str:
    if value is None:
        return "default"
    if value not in ("default", "all"):
        raise LoadError(f"{path}: commit_branches must be default or all (got {value!r})")
    return value


def _group_info(path, value, groups) -> dict:
    """One entry per configured group: `label` (default the group name) and `category` (default None)."""
    if value is None:
        value = {}
    if not isinstance(value, dict):
        raise LoadError(f"{path}: group_info must be a mapping of group name to label and category")
    unknown_groups = [g for g in value if g not in groups]
    if unknown_groups:
        raise LoadError(f"{path}: group_info names groups that are not in groups: {sorted(map(str, unknown_groups))}")
    info = {}
    for name in groups:
        entry = value.get(name)
        if entry is None:
            entry = {}
        if not isinstance(entry, dict):
            raise LoadError(f"{path}: group_info.{name} must be a mapping (label, category)")
        unknown = set(entry) - {"label", "category"}
        if unknown:
            raise LoadError(f"{path}: unknown group_info.{name} field(s) {sorted(map(str, unknown))}")
        label = entry.get("label", name)
        if not isinstance(label, str) or not label.strip():
            raise LoadError(f"{path}: group_info.{name}.label must be non-empty text")
        category = entry.get("category")
        if category is not None and (not isinstance(category, str) or category not in CATEGORIES):
            raise LoadError(f"{path}: group_info.{name}.category must be one of {', '.join(CATEGORIES)}")
        info[name] = {"label": label.strip(), "category": category}
    return info


def load_config(path) -> Config:
    path = Path(path)
    if not path.is_file():
        raise LoadError(f"config file not found: {path}")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as error:
        raise LoadError(f"{path}: invalid YAML ({error})") from error
    except ValueError as error:     # YAML reads 2026-13-01 as a date and fails
        raise LoadError(f"{path}: since/until must be a date like 2026-01-31 ({error})") from error
    if not isinstance(data, dict):
        raise LoadError(f"{path}: must be a mapping")
    unknown = set(data) - _KNOWN_KEYS
    if unknown:
        raise LoadError(f"{path}: unknown key(s) {sorted(map(str, unknown))}")

    org = data.get("org")
    if not isinstance(org, str) or not _ORG.fullmatch(org):
        raise LoadError(f"{path}: org must be a GitHub organisation name")

    repos = data.get("repos")
    if not isinstance(repos, list) or not repos:
        raise LoadError(f"{path}: repos must be a non-empty list")
    seen = set()
    for repo in repos:
        if not isinstance(repo, str):
            raise LoadError(f"{path}: '{repo}' is not a valid repository name "
                            f"(YAML read it as {type(repo).__name__}; put quotes around it)")
        if not _REPO.fullmatch(repo) or not repo.strip("."):
            raise LoadError(f"{path}: '{repo}' is not a valid repository name")
        if repo in seen:
            raise LoadError(f"{path}: duplicate repository '{repo}'")
        seen.add(repo)

    raw_groups = data.get("groups")
    groups: dict = {}
    if raw_groups is not None:
        if not isinstance(raw_groups, dict):
            raise LoadError(f"{path}: groups must be a mapping of group name to repositories")
        for name, members in raw_groups.items():
            if not isinstance(name, str) or not _GROUP.fullmatch(name):
                raise LoadError(f"{path}: '{name}' is not a valid group name")
            if not isinstance(members, list) or not members:
                raise LoadError(f"{path}: group '{name}' is empty or not a list")
            listed = set()
            for m in members:
                if not isinstance(m, str):
                    raise LoadError(f"{path}: group '{name}' has an invalid member {m!r}")
                if m in listed:
                    raise LoadError(f"{path}: group '{name}' lists '{m}' twice")
                listed.add(m)
            missing = [m for m in members if m not in seen]
            if missing:
                raise LoadError(f"{path}: group '{name}' has repositories not in repos: {missing}")
            groups[name] = list(members)

    since, until = _date(path, data.get("since")), _date(path, data.get("until"))
    if since and until and since > until:
        raise LoadError(f"{path}: since must not be after until")
    return Config(org=org, repos=list(repos), groups=groups,
                  group_info=_group_info(path, data.get("group_info"), groups),
                  since=since.isoformat() if since else None,
                  until=until.isoformat() if until else None,
                  metrics=_metrics(path, data.get("metrics")),
                  bot_patterns=_bot_patterns(path, data.get("bot_patterns")),
                  bot_names=_bot_names(path, data.get("bot_names")),
                  aliases=_aliases(path, data.get("aliases")),
                  timezone=_timezone(path, data.get("timezone")),
                  top_n=_top_n(path, data.get("curiosities")),
                  download_avatars=_download_avatars(path, data.get("avatars")),
                  commit_branches=_commit_branches(path, data.get("commit_branches")))
