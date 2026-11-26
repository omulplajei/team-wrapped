"""Read the derived files written by `aggregate` (spec section 7.6)."""
from __future__ import annotations

import json
from pathlib import Path


class DerivedData:
    def __init__(self, data_root):
        self.data_root = Path(data_root)
        self._cache: dict[str, dict | None] = {}

    @staticmethod
    def scope_key(scope: str) -> str:
        if scope == "all" or scope.startswith(("group:", "repo:")):
            return scope
        return f"group:{scope}"

    def _file(self, family: str) -> dict | None:
        if family not in self._cache:
            path = self.data_root / "derived" / f"{family}.json"
            self._cache[family] = json.loads(path.read_text()) if path.is_file() else None
        return self._cache[family]

    def meta(self) -> dict:
        return self._file("meta") or {}

    def partial_datasets(self) -> set[str]:
        return set(self.meta().get("partial_datasets", []))

    def dataset(self, name: str, scope_key: str):
        family, _, rest = name.partition(".")
        data = self._file(family)
        if data is None:
            return None
        node = data.get("scopes", {}).get(scope_key)
        if node is None:
            return None
        return node.get(rest) if rest else node


def has_field(node, path: str) -> bool:
    """True if `path` exists. Through a list, it must exist on at least one item."""
    if isinstance(node, list):
        return any(has_field(item, path) for item in node)
    head, _, rest = path.partition(".")
    if not isinstance(node, dict) or head not in node:
        return False
    return not rest or has_field(node[head], rest)


def resolve_ref(datasets: dict, ref: str):
    """Resolve e.g. 'summary.totals.commits' against {dataset name: dataset}."""
    parts = ref.split(".")
    for take in (2, 1):
        if len(parts) > take - 1 and ".".join(parts[:take]) in datasets:
            node = datasets[".".join(parts[:take])]
            for key in parts[take:]:
                if not isinstance(node, dict) or key not in node:
                    return None
                node = node[key]
            return node
    return None
