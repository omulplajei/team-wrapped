"""What every dataset builder receives."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..config import Config
from .raw import RawData
from .window import Window


@dataclass
class Context:
    """Inputs for the builders. `scopes` maps every scope key (`all`, `group:<name>`) to its repository names,
    in config order. Every derived file has exactly these scope keys."""
    config: Config
    raw: RawData
    data_root: Path
    window: Window
    group_repos: dict      # group name -> repo names
    scopes: dict           # scope key -> repo names

    @classmethod
    def build(cls, data_root, config: Config, raw: RawData) -> "Context":
        scopes = {"all": list(config.repos)}
        for name, members in config.groups.items():
            scopes[f"group:{name}"] = list(members)
        return cls(config, raw, Path(data_root), Window.from_config(config),
                   {name: list(members) for name, members in config.groups.items()}, scopes)

    @property
    def metrics(self) -> list:
        return self.config.metrics

    def records(self, metric: str, repos=None) -> list:
        """Raw records of an enabled metric (empty for a disabled one), optionally limited to some repos.
        Records are not window-filtered: use `ctx.window.contains(ts)` / `date_in_window(ts)` on the right field."""
        records = self.raw.records.get(metric, [])
        if repos is None:
            return records
        wanted = set(repos)
        return [r for r in records if r["repo"] in wanted]
