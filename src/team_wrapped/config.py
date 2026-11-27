"""Load and validate the private collection config (data/config.yml, spec section 4)."""
from __future__ import annotations

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


def _date(value) -> str | None:
    return None if value is None else str(value)


def load_config(path) -> Config:
    path = Path(path)
    if not path.is_file():
        raise LoadError(f"config file not found: {path}")
    try:
        data = yaml.safe_load(path.read_text())
    except yaml.YAMLError as error:
        raise LoadError(f"{path}: invalid YAML ({error})") from error
    if not isinstance(data, dict):
        raise LoadError(f"{path}: must be a mapping")
    unknown = set(data) - _KNOWN_KEYS
    if unknown:
        raise LoadError(f"{path}: unknown key(s) {sorted(unknown)}")

    org = data.get("org")
    if not isinstance(org, str) or not _ORG.fullmatch(org):
        raise LoadError(f"{path}: org must be a GitHub organisation name")

    repos = data.get("repos")
    if not isinstance(repos, list) or not repos:
        raise LoadError(f"{path}: repos must be a non-empty list")
    seen = set()
    for repo in repos:
        if not isinstance(repo, str) or not _REPO.fullmatch(repo):
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
            missing = [m for m in members if m not in seen]
            if missing:
                raise LoadError(f"{path}: group '{name}' has repositories not in repos: {missing}")
            groups[name] = list(members)

    return Config(org=org, repos=list(repos), groups=groups,
                  since=_date(data.get("since")), until=_date(data.get("until")))
