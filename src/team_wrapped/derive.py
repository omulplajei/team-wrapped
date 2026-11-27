"""Derive datasets from the collection config (spec section 7.6)."""
from __future__ import annotations

import json
import os
from pathlib import Path

from .config import Config


def _touched(names) -> dict:
    ordered = sorted(names, key=lambda n: (n.lower(), n))
    return {"touched": {"total": len(ordered), "list": [{"name": n} for n in ordered]}}


def derive_repos(config: Config) -> dict:
    """`repos.json` content. Until activity is collected every configured repository counts as touched."""
    scopes = {"all": _touched(config.repos)}
    for name, members in config.groups.items():
        scopes[f"group:{name}"] = _touched(members)
    return {
        "period": {"since": config.since, "until": config.until},
        "basis": "configuration",
        "scopes": scopes,
    }


def write_repos(config: Config, data_root) -> Path:
    path = Path(data_root) / "derived" / "repos.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_text(json.dumps(derive_repos(config), indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return path
