import json

from aggregate_helpers import comment, commit, pull_request, review

from team_wrapped.aggregate.contributors import avatar_name, bot_matcher, build_contributors

CONFIG = """org: sample-org
repos: [alpha-api, beta-web, gamma-docs]
groups:
  alpha: [alpha-api, beta-web]
  gamma: [gamma-docs]
"""


def build(fx):
    scopes, partial = build_contributors(fx.context())
    assert partial == []
    return scopes


def by_login(scope):
    return {c.get("login", c["id"]): c for c in scope["list"]}


def test_every_author_kind_is_counted_once_across_metrics(fx):
    fx.config(CONFIG)
    fx.raw("alpha-api", "commits.jsonl", [commit(login="ada-dev"), commit("b", login=None, email="x@example.com", name="X")])
    fx.raw("alpha-api", "pull_requests.jsonl", [pull_request(login="ada-dev"), pull_request(2, login="grace-codes")])
    fx.raw("beta-web", "reviews.jsonl", [review(login="linus-sample"), review(login="renovate[bot]")])
    fx.raw("beta-web", "comments.jsonl", [comment(login="ken-t"), comment(login="Ada-Dev", cid=2)])
    scope = build(fx)["all"]
    assert scope["total"] == 6
    assert scope["by_kind"] == {"human": 4, "unlinked": 1, "bot": 1}
    assert list(scope["by_kind"]) == ["human", "unlinked", "bot"]
    ada = [c for c in scope["list"] if c.get("login", "").lower() == "ada-dev"]
    assert len(ada) == 1                       # case-insensitive logins collapse
    assert ada[0]["repos"] == ["alpha-api", "beta-web"]


def test_entry_shape_matches_the_sample_and_dates_are_local(fx):
    fx.config(CONFIG.replace("repos:", "timezone: Europe/Bucharest\nrepos:", 1))
    fx.raw("alpha-api", "commits.jsonl", [commit(at="2026-12-31T23:30:00Z"), commit("b", at="2026-03-01T10:00:00Z")])
    fx.avatar("ada-dev")
    (entry,) = build(fx)["all"]["list"]
    assert list(entry) == ["id", "login", "kind", "avatar_file", "repos", "groups", "first_activity", "last_activity"]
    assert entry["avatar_file"] == "avatars/ada-dev.png"
    assert (entry["first_activity"], entry["last_activity"]) == ("2026-03-01", "2027-01-01")
    assert entry["groups"] == ["alpha"]
    assert entry["id"].startswith("c") and len(entry["id"]) == 11


def test_id_is_a_hash_of_the_lowercased_login(fx):
    import hashlib
    fx.raw("alpha-api", "commits.jsonl", [commit(login="Ada-Dev")])
    (entry,) = build(fx)["all"]["list"]
    assert entry["id"] == "c" + hashlib.sha1(b"ada-dev").hexdigest()[:10]


def test_missing_avatar_falls_back_to_the_placeholder_and_bot_names_are_sanitised(fx):
    fx.raw("alpha-api", "commits.jsonl", [commit(login="dependabot[bot]"), commit("b", login="ghost-user")])
    fx.avatar("dependabot_bot")
    scope = by_login(build(fx)["all"])
    assert scope["dependabot[bot]"]["avatar_file"] == "avatars/dependabot_bot.png"
    assert scope["ghost-user"]["avatar_file"] == "avatars/placeholder.png"
    assert avatar_name("a/../b[bot]") == "a_.._b_bot"


def test_bots_match_case_insensitively_and_brackets_are_literal():
    is_bot = bot_matcher(["*[bot]", "Robot-?"])
    assert is_bot("renovate[bot]") and is_bot("RENOVATE[BOT]") and is_bot("robot-1")
    assert not is_bot("ken-t") and not is_bot("bot") and not is_bot("robot-12")      # fnmatch would match ken-t


def test_bot_unlinked_and_human_kinds_and_order(fx):
    fx.raw("alpha-api", "commits.jsonl", [
        commit("1", login="zed", email="z@example.com"),
        commit("2", login="dependabot[bot]", email="d@example.com"),
        commit("3", login=None, email="nobody@example.com", name="Nobody"),
        commit("4", login="abe", email="a@example.com"),
        commit("5", login=None, email="", name="Name Only"),
    ])
    scope = build(fx)["all"]
    assert [(c["kind"], c.get("login")) for c in scope["list"]] == [
        ("human", "abe"), ("human", "zed"), ("unlinked", None), ("unlinked", None), ("bot", "dependabot[bot]")]
    unlinked = [c for c in scope["list"] if c["kind"] == "unlinked"]
    assert all("login" not in c and c["avatar_file"] == "avatars/placeholder.png" for c in unlinked)


def test_unlinked_commits_merge_by_email_case_insensitively_or_fall_back_to_name(fx):
    fx.raw("alpha-api", "commits.jsonl", [
        commit("1", login=None, email="Same@Example.com", name="One"),
        commit("2", login=None, email="same@example.com", name="Two"),
        commit("3", login=None, email=None, name="Solo"),
        commit("4", login=None, email=None, name="Solo"),
        commit("5", login=None, email=None, name=None),
    ])
    assert build(fx)["all"]["total"] == 2


def test_aliases_merge_logins_and_emails_into_a_canonical_login(fx):
    fx.config(CONFIG + "aliases:\n  ada-old: ada-dev\n  Ada@Home.example.com: ada-dev\n")
    fx.raw("alpha-api", "commits.jsonl", [
        commit("1", login="ada-dev"),
        commit("2", login="ada-old"),
        commit("3", login=None, email="ada@home.example.com", name="Ada"),
        commit("4", login=None, email="other@example.com", name="Other"),
    ])
    fx.raw("gamma-docs", "reviews.jsonl", [review(login="Ada-Old")])
    scope = build(fx)["all"]
    assert scope["total"] == 2
    ada = [c for c in scope["list"] if c["kind"] == "human"]
    assert [c["login"] for c in ada] == ["ada-dev"]
    assert ada[0]["repos"] == ["alpha-api", "gamma-docs"]
    assert ada[0]["groups"] == ["alpha", "gamma"]


def test_alias_to_a_bot_login_makes_a_bot(fx):
    fx.config(CONFIG + "aliases:\n  robot@example.com: release[bot]\n")
    fx.raw("alpha-api", "commits.jsonl", [commit(login=None, email="robot@example.com", name="R")])
    assert build(fx)["all"]["list"][0]["kind"] == "bot"


def test_only_activity_inside_the_window_counts(fx):
    fx.config(CONFIG + "since: 2026-02-01\nuntil: 2026-02-28\n")
    fx.raw("alpha-api", "commits.jsonl", [
        commit("1", login="early", at="2026-01-31T21:00:00Z"),
        commit("2", login="inside", at="2026-02-01T00:00:00Z"),
        commit("3", login="late", at="2026-03-01T00:00:00Z"),
    ])
    fx.raw("alpha-api", "pull_requests.jsonl", [
        pull_request(1, login="opened-before", created="2026-01-10T10:00:00Z", merged="2026-02-10T10:00:00Z"),
        pull_request(2, login="no-dates", created=None)])
    scope = build(fx)["all"]
    assert sorted(by_login(scope)) == ["inside", "opened-before"]
    assert by_login(scope)["opened-before"]["first_activity"] == "2026-02-10"


def test_disabled_metrics_contribute_nobody(fx):
    fx.config(CONFIG + "metrics: [commits]\n")
    fx.raw("alpha-api", "commits.jsonl", [commit(login="author")])
    fx.raw("alpha-api", "reviews.jsonl", [review(login="reviewer")])
    assert sorted(by_login(build(fx)["all"])) == ["author"]


def test_group_scopes_keep_contributors_who_touched_a_group_repo(fx):
    fx.config(CONFIG)
    fx.raw("alpha-api", "commits.jsonl", [commit(login="in-alpha", at="2026-01-05T10:00:00Z")])
    fx.raw("gamma-docs", "commits.jsonl", [commit(login="in-gamma"), commit("b", login="in-alpha", at="2026-06-05T10:00:00Z")])
    scopes = build(fx)
    assert list(scopes) == ["all", "group:alpha", "group:gamma"]
    assert scopes["all"]["total"] == 2
    alpha, gamma = by_login(scopes["group:alpha"]), by_login(scopes["group:gamma"])
    assert list(alpha) == ["in-alpha"] and alpha["in-alpha"]["repos"] == ["alpha-api"]
    assert alpha["in-alpha"]["last_activity"] == "2026-01-05"       # activity is scoped too
    assert sorted(gamma) == ["in-alpha", "in-gamma"]
    assert scopes["group:gamma"]["by_kind"] == {"human": 2, "unlinked": 0, "bot": 0}


def test_empty_scopes_still_have_all_keys(fx):
    scope = build(fx)["all"]
    assert scope == {"total": 0, "by_kind": {"human": 0, "unlinked": 0, "bot": 0}, "list": []}


def test_no_email_reaches_the_output(fx):
    fx.config(CONFIG + "aliases:\n  alias@example.com: ada-dev\n")
    fx.raw("alpha-api", "commits.jsonl", [
        commit("1", login="ada-dev", email="ada@example.com"),
        commit("2", login=None, email="private@example.com", name="Private Person"),
        commit("3", login=None, email="alias@example.com", name="A"),
        commit("4", login=None, email="", name="Plain Name"),
    ])
    text = json.dumps(build(fx))
    assert "@" not in text
    assert "example.com" not in text and "Private" not in text


def test_output_is_deterministic_regardless_of_input_order(fx):
    records = [commit(str(i), login=f"dev{i % 4}", at=f"2026-0{1 + i % 3}-10T10:00:00Z") for i in range(12)]
    records += [commit("u", login=None, email="u@example.com"), commit("b", login="x[bot]")]
    fx.raw("alpha-api", "commits.jsonl", records)
    first = json.dumps(build(fx))
    fx.raw("alpha-api", "commits.jsonl", list(reversed(records)))
    assert json.dumps(build(fx)) == first
