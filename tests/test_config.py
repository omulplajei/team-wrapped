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


@pytest.mark.parametrize("value", ["true", "null", "123"])
def test_non_string_repo_names_get_a_quote_hint(tmp_path, value):
    with pytest.raises(LoadError, match=r"YAML read it as .*put quotes around it"):
        load_config(write(tmp_path, f"org: o\nrepos: [{value}]\n"))


@pytest.mark.parametrize("name", [".", "..", "..."])
def test_dot_only_repo_names_are_rejected(tmp_path, name):
    with pytest.raises(LoadError, match="not a valid repository name"):
        load_config(write(tmp_path, f"org: o\nrepos: ['{name}']\n"))


@pytest.mark.parametrize("name", [".", "..", "..."])
def test_dot_only_group_names_are_rejected(tmp_path, name):
    with pytest.raises(LoadError, match="group name"):
        load_config(write(tmp_path, f"org: o\nrepos: [a]\ngroups: {{'{name}': [a]}}\n"))


@pytest.mark.parametrize("groups, message", [
    ("{g: a}", "empty or not a list"),
    ("{g: [[a]]}", "invalid member"),
    ("{g: [{x: 1}]}", "invalid member"),
    ("{g: [a, a]}", "lists 'a' twice"),
])
def test_bad_group_members_are_rejected(tmp_path, groups, message):
    with pytest.raises(LoadError, match=message):
        load_config(write(tmp_path, f"org: o\nrepos: [a]\ngroups: {groups}\n"))


@pytest.mark.parametrize("key", ["since", "until"])
@pytest.mark.parametrize("value", ["yesterday", "2026-13-01", "5", "[1]", "true"])
def test_bad_dates_are_rejected(tmp_path, key, value):
    with pytest.raises(LoadError, match=f"since/until must be a date like 2026-01-31"):
        load_config(write(tmp_path, f"org: o\nrepos: [a]\n{key}: {value}\n"))


def test_since_after_until_is_rejected(tmp_path):
    with pytest.raises(LoadError, match="since"):
        load_config(write(tmp_path, "org: o\nrepos: [a]\nsince: 2026-02-01\nuntil: 2026-01-01\n"))


@pytest.mark.parametrize("value, expected", [
    ("2026-01-01", "2026-01-01"),
    ("'2026-01-01'", "2026-01-01"),
    ("2026-01-01 10:00:00", "2026-01-01"),
])
def test_valid_date_forms(tmp_path, value, expected):
    config = load_config(write(tmp_path, f"org: o\nrepos: [a]\nsince: {value}\nuntil: 2027-01-01\n"))
    assert config.since == expected


def test_integer_key_with_unknown_key_is_a_load_error(tmp_path):
    with pytest.raises(LoadError, match="unknown key"):
        load_config(write(tmp_path, "org: o\nrepos: [a]\n1: x\nrepoz: y\n"))


def test_empty_groups_mapping_is_accepted(tmp_path):
    assert load_config(write(tmp_path, "org: o\nrepos: [a]\ngroups: {}\n")).groups == {}


def test_errors_name_the_config_file(tmp_path):
    path = write(tmp_path, "org: o\nrepos: [a]\ngroups: {g: [b]}\n")
    with pytest.raises(LoadError, match="config.yml"):
        load_config(path)


MIN = "org: o\nrepos: [a]\n"


def test_new_keys_have_defaults(tmp_path):
    config = load_config(write(tmp_path, MIN))
    assert config.metrics == ["commits", "pull_requests", "reviews", "comments"]
    assert config.bot_patterns == ["*[bot]"]
    assert config.aliases == {}
    assert config.timezone == "UTC"
    assert config.top_n == 5
    assert config.download_avatars is True


def test_new_keys_are_read(tmp_path):
    config = load_config(write(tmp_path, MIN + (
        "metrics: [reviews, commits, commits]\nbot_patterns: ['*[bot]', 'robot-*']\n"
        "aliases: {old-login: new-login, Dev@Example.com: new-login}\n"
        "timezone: Europe/Bucharest\ncuriosities: {top_n: 3}\navatars: {download: false}\n")))
    assert config.metrics == ["commits", "reviews"]         # canonical order, no duplicates
    assert config.bot_patterns == ["*[bot]", "robot-*"]
    assert config.aliases == {"old-login": "new-login", "Dev@Example.com": "new-login"}
    assert config.timezone == "Europe/Bucharest"
    assert config.top_n == 3
    assert config.download_avatars is False


@pytest.mark.parametrize("extra, message", [
    ("metrics: [commits, deploys]", "unknown metric"),
    ("metrics: []", "metrics"),
    ("metrics: commits", "metrics"),
    ("bot_patterns: '*[bot]'", "bot_patterns"),
    ("bot_patterns: [1]", "bot_patterns"),
    ("aliases: [a, b]", "aliases"),
    ("aliases: {a: 1}", "aliases"),
    ("aliases: {1: a}", "aliases"),
    ("aliases: {a: b@example.com}", "not an email"),
    ("timezone: Mars/Olympus", "timezone"),
    ("timezone: 5", "timezone"),
    ("curiosities: {top_n: 0}", "top_n"),
    ("curiosities: {top_n: '3'}", "top_n"),
    ("curiosities: {top_n: true}", "top_n"),
    ("curiosities: {other: 1}", "unknown curiosities"),
    ("curiosities: 3", "curiosities"),
    ("avatars: {download: 'yes please'}", "avatars.download"),
    ("avatars: {size: 1}", "unknown avatars"),
    ("avatars: no", "avatars"),
])
def test_bad_new_keys_are_rejected(tmp_path, extra, message):
    with pytest.raises(LoadError, match=message):
        load_config(write(tmp_path, MIN + extra + "\n"))
