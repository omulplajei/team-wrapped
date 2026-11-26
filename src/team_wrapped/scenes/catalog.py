"""Read dataset names from the catalog document (docs/datasets.md)."""
from __future__ import annotations

import re
from pathlib import Path

_NAME = re.compile(r"`([a-z_]+\.[a-z_]+)`")


def load_catalog(path) -> set[str]:
    """`family.name` names in the first column of the tables, plus `contributors`."""
    names = {"contributors"}
    for line in Path(path).read_text().splitlines():
        if line.startswith("|"):
            cells = line.split("|")
            if len(cells) > 1:
                names.update(_NAME.findall(cells[1]))
    return names
