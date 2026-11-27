import json

import pytest

from team_wrapped.aggregate.context import Context
from team_wrapped.aggregate.raw import load_raw
from team_wrapped.config import load_config

BASE_CONFIG = "org: sample-org\nrepos: [alpha-api, beta-web]\n"


class Fixture:
    """A throwaway data root with hand-written config and raw files."""

    def __init__(self, root):
        self.root = root

    def config(self, text=BASE_CONFIG):
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "config.yml").write_text(text)
        return self

    def raw(self, repo, filename, records):
        """records: dicts (written as JSON) or strings (written verbatim, for corrupt lines)."""
        folder = self.root / "raw" / repo
        folder.mkdir(parents=True, exist_ok=True)
        lines = [r if isinstance(r, str) else json.dumps(r) for r in records]
        (folder / filename).write_text("\n".join(lines) + "\n")
        return self

    def status(self, repo, statuses):
        folder = self.root / "raw" / repo
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "status.json").write_text(statuses if isinstance(statuses, str) else json.dumps(statuses))
        return self

    def avatar(self, name):
        (self.root / "avatars").mkdir(exist_ok=True)
        (self.root / "avatars" / f"{name}.png").write_bytes(b"png")
        return self

    def context(self):
        config = load_config(self.root / "config.yml")
        return Context.build(self.root, config, load_raw(self.root, config))


@pytest.fixture
def fx(tmp_path):
    return Fixture(tmp_path / "data").config()
