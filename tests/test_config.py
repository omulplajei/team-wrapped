import pytest

from team_wrapped.config import load_config
from team_wrapped.scenes.loader import LoadError

GOOD = """
org: sample-org
since: 2026-01-01
until: 2026-12-31
repos: [sample-api, sample-web, sample-docs]
groups:
  alpha: [sample-api, sample-web]
  beta: [sample-docs]
metrics: [commits, pull_requests]
timezone: UTC
"""


def write(tmp_path, text):
    path = tmp_path / "config.yml"
    path.write_text(text)
    return path


def test_loads_a_valid_config(tmp_path):
    config = load_config(write(tmp_path, GOOD))
    assert config.org == "sample-org"
    assert config.repos == ["sample-api", "sample-web", "sample-docs"]
    assert config.groups == {"alpha": ["sample-api", "sample-web"], "beta": ["sample-docs"]}
    assert (config.since, config.until) == ("2026-01-01", "2026-12-31")     # YAML dates become ISO strings


def test_groups_and_dates_are_optional(tmp_path):
    config = load_config(write(tmp_path, "org: o\nrepos: [a]\n"))
    assert config.groups == {} and config.since is None and config.until is None


@pytest.mark.parametrize("text, message", [
    ("repos: [a]\n", "org"),
    ("org: 'bad org!'\nrepos: [a]\n", "org"),
    ("org: o\n", "repos"),
    ("org: o\nrepos: []\n", "repos"),
    ("org: o\nrepos: a\n", "repos"),
    ("org: o\nrepos: [a, a]\n", "duplicate"),
    ("org: o\nrepos: ['a/b']\n", "repository name"),
    ("org: o\nrepos: [a]\ngroups: [x]\n", "groups"),
    ("org: o\nrepos: [a]\ngroups: {g: [b]}\n", "not in repos"),
    ("org: o\nrepos: [a]\ngroups: {g: []}\n", "empty"),
    ("org: o\nrepos: [a]\ngroups: {'bad name': [a]}\n", "group name"),
    ("org: o\nrepos: [a]\nrepoz: [b]\n", "unknown key"),
    ("- just\n- a list\n", "mapping"),
])
def test_invalid_configs_are_rejected(tmp_path, text, message):
    with pytest.raises(LoadError, match=message):
        load_config(write(tmp_path, text))


def test_missing_file_and_bad_yaml(tmp_path):
    with pytest.raises(LoadError, match="not found"):
        load_config(tmp_path / "nope.yml")
    with pytest.raises(LoadError, match="config.yml"):
        load_config(write(tmp_path, "org: [unclosed\n"))
