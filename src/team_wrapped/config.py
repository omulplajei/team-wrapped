"""Load and validate the private collection config (data/config.yml, spec section 4)."""
from __future__ import annotations

import datetime
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .scenes.loader import LoadError

_KNOWN_KEYS = {
    "org", "repos", "groups", "since", "until", "metrics", "commit_branches", "bot_patterns",
    "aliases", "timezone", "curiosities", "avatars", "reviewer_pairs",
}
_ORG = re.compile(r"[A-Za-z0-9-]+")
_REPO = re.compile(r"[A-Za-z0-9._-]+")
_GROUP = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*")


@dataclass(frozen=True)
class Config:
    org: str
    repos: list
    groups: dict = field(default_factory=dict)
    since: str | None = None
    until: str | None = None


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
                  since=since.isoformat() if since else None,
                  until=until.isoformat() if until else None)
