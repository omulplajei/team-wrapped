import pathlib

import pytest


@pytest.fixture
def repo_root() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parents[1]


@pytest.fixture
def sample_root(repo_root) -> pathlib.Path:
    return repo_root / "data-sample"
