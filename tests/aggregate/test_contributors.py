import json

from aggregate_helpers import ALL_COMPLETE, comment, commit, pull_request, review

from team_wrapped.aggregate.contributors import avatar_name, bot_matcher, build_contributors

CONFIG = """org: sample-org
repos: [alpha-api, beta-web, gamma-docs]
groups:
  alpha: [alpha-api, beta-web]
  gamma: [gamma-docs]
"""


def build(fx):
    for repo in fx.context().config.repos:
        fx.status(repo, ALL_COMPLETE)
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
    assert entry["id"] == "c001"


def test_ids_are_sequential_after_sorting_and_stable_across_scopes(fx):
    fx.config(CONFIG)
    fx.raw("alpha-api", "commits.jsonl", [commit("1", login="zed"), commit("2", login="abe"),
                                          commit("3", login=None, email="guess@example.com", name="G"),
                                          commit("4", login="x[bot]")])
    fx.raw("gamma-docs", "commits.jsonl", [commit("5", login="zed")])
    scopes = build(fx)
    assert [(c.get("login"), c["id"]) for c in scopes["all"]["list"]] == [
        ("abe", "c001"), ("zed", "c002"), (None, "c003"), ("x[bot]", "c004")]
    assert [(c["login"], c["id"]) for c in scopes["group:gamma"]["list"]] == [("zed", "c002")]
    assert "guess" not in json.dumps(scopes)


def test_partial_when_an_in_scope_repo_is_not_complete(fx):
    fx.config(CONFIG)
    fx.raw("alpha-api", "commits.jsonl", [commit()])
    fx.status("alpha-api", {"commits": "partial", "pull_requests": "complete", "reviews": "complete", "comments": "complete"})
    for repo in ("beta-web", "gamma-docs"):
        fx.status(repo, ALL_COMPLETE)
    assert build_contributors(fx.context())[1] == ["contributors"]
    fx.status("alpha-api", ALL_COMPLETE)
    assert build_contributors(fx.context())[1] == []
    fx.status("gamma-docs", {**ALL_COMPLETE, "reviews": "failed"})          # only a group scope sees it, still partial
    assert build_contributors(fx.context())[1] == ["contributors"]


def test_unlinked_author_named_like_a_login_does_not_merge_into_it(fx):
    fx.raw("alpha-api", "commits.jsonl", [commit("1", login="ada-dev"),
                                          commit("2", login=None, email=None, name="Ada-Dev"),
                                          commit("3", login=None, email="ada-dev", name="x")])
    scope = build(fx)["all"]
    assert scope["by_kind"] == {"human": 1, "unlinked": 2, "bot": 0}


def test_email_alias_does_not_override_an_existing_login(fx):
    fx.config(CONFIG + "aliases:\n  shared@example.com: ada-dev\n")
    fx.raw("alpha-api", "commits.jsonl", [commit("1", login="grace-codes", email="shared@example.com"),
                                          commit("2", login=None, email="shared@example.com", name="S")])
    assert sorted(by_login(build(fx)["all"])) == ["ada-dev", "grace-codes"]


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


def test_bots_get_a_display_name_and_people_never_do(fx):
    fx.config(CONFIG + "bot_patterns: ['*[bot]', 'helper-*']\n")
    fx.raw("alpha-api", "commits.jsonl", [
        commit("1", login="sample-bot[bot]"), commit("2", login="helper-robot"),
        commit("3", login="ada-dev", name="Ada Lovelace"),
        commit("4", login=None, email="nobody@example.com", name="Nobody Known"),
    ])
    entries = build(fx)["all"]["list"]
    names = {(c["kind"], c.get("login")): c.get("name") for c in entries}
    assert names == {("human", "ada-dev"): None, ("unlinked", None): None,
                     ("bot", "helper-robot"): "helper-robot", ("bot", "sample-bot[bot]"): "sample-bot"}
    assert all("name" not in c for c in entries if c["kind"] != "bot")
    bot = next(c for c in entries if c.get("login") == "sample-bot[bot]")
    assert list(bot)[:4] == ["id", "login", "name", "kind"]
    assert "Ada Lovelace" not in json.dumps(entries) and "Nobody Known" not in json.dumps(entries)


def co(login=None, name=None, email=None):
    return {"login": login, "name": name, "email": email}


AI_CONFIG = CONFIG + """bot_patterns: ['*[bot]', claude, cursoragent, 'Deployment *', 'jenkins ci']
bot_names: {claude: Claude, cursoragent: Cursor}
"""


def test_co_authors_are_contributors_like_the_primary_author(fx):
    fx.config(CONFIG)
    fx.raw("alpha-api", "commits.jsonl", [
        commit("1", login="ada-dev", at="2026-03-14T09:30:00Z", co_authors=[co("grace-codes", "Grace", "g@example.com")]),
    ])
    fx.raw("gamma-docs", "commits.jsonl", [
        commit("2", login="ada-dev", at="2026-05-01T09:30:00Z", co_authors=[co("grace-codes", "Grace", "g@example.com")]),
    ])
    scopes = build(fx)
    grace = by_login(scopes["all"])["grace-codes"]
    assert grace["kind"] == "human" and "name" not in grace              # a co-author-only human still counts
    assert grace["repos"] == ["alpha-api", "gamma-docs"] and grace["groups"] == ["alpha", "gamma"]
    assert (grace["first_activity"], grace["last_activity"]) == ("2026-03-14", "2026-05-01")
    assert sorted(by_login(scopes["group:gamma"])) == ["ada-dev", "grace-codes"]
    assert scopes["all"]["by_kind"] == {"human": 2, "unlinked": 0, "bot": 0}


def test_co_authors_outside_the_window_or_of_a_disabled_metric_do_not_count(fx):
    fx.config(CONFIG + "since: 2026-02-01\n")
    fx.raw("alpha-api", "commits.jsonl", [commit("1", login="ada-dev", at="2026-01-10T09:00:00Z",
                                                 co_authors=[co("early-pair")])])
    assert build(fx)["all"]["total"] == 0
    fx.config(CONFIG + "metrics: [reviews]\n")
    assert build(fx)["all"]["total"] == 0


def test_ai_co_authors_matched_by_bot_patterns_are_bots_with_their_configured_names(fx):
    fx.config(AI_CONFIG)
    fx.raw("alpha-api", "commits.jsonl", [
        commit("1", login="ada-dev", co_authors=[co("claude", "Claude", "c@example.com")]),
        commit("2", login="grace-codes", co_authors=[co("Cursoragent", "Cursor Agent", "cursor@example.com"),
                                                     co("Copilot[bot]", "Copilot", "copilot@example.com")]),
    ])
    scope = build(fx)["all"]
    names = {c["login"]: (c["kind"], c.get("name")) for c in scope["list"]}
    assert names == {"ada-dev": ("human", None), "grace-codes": ("human", None), "claude": ("bot", "Claude"),
                     "Cursoragent": ("bot", "Cursor"),          # bot_names keys match case-insensitively
                     "Copilot[bot]": ("bot", "Copilot")}       # not in bot_names: the login without [bot]
    assert scope["by_kind"] == {"human": 2, "unlinked": 0, "bot": 3}


def test_bot_names_only_name_bots(fx):
    fx.config(CONFIG + "bot_names: {ada-dev: Ada Lovelace, 'sample-bot[bot]': Sample Helper}\n")
    fx.raw("alpha-api", "commits.jsonl", [commit("1", login="ada-dev"), commit("2", login="sample-bot[bot]")])
    entries = by_login(build(fx)["all"])
    assert "name" not in entries["ada-dev"] and entries["ada-dev"]["kind"] == "human"
    assert entries["sample-bot[bot]"]["name"] == "Sample Helper"


def test_unlinked_service_identities_matched_by_name_are_bots_named_after_the_service(fx):
    fx.config(AI_CONFIG)
    fx.raw("alpha-api", "commits.jsonl", [
        commit("1", login=None, email="deploy@example.com", name="Deployment Script"),
        commit("2", login="ada-dev", co_authors=[co(None, "Jenkins CI", "jenkins@example.com")]),
        commit("3", login=None, email="person@example.com", name="Private Person"),
        commit("4", login=None, email="other@example.com", name="Ada Deployment"),     # patterns match the whole name
    ])
    scope = build(fx)["all"]
    assert scope["by_kind"] == {"human": 1, "unlinked": 2, "bot": 2}
    bots = [c for c in scope["list"] if c["kind"] == "bot"]
    assert sorted(c["name"] for c in bots) == ["Deployment Script", "Jenkins CI"]
    assert all("login" not in c and c["avatar_file"] == "avatars/placeholder.png" for c in bots)
    assert list(bots[0])[:3] == ["id", "name", "kind"]
    unlinked = [c for c in scope["list"] if c["kind"] == "unlinked"]
    assert all("name" not in c for c in unlinked)
    text = json.dumps(scope)
    assert "Private Person" not in text and "Ada Deployment" not in text and "@" not in text


def test_a_login_is_never_matched_by_its_author_name(fx):
    fx.config(AI_CONFIG)
    fx.raw("alpha-api", "commits.jsonl", [commit("1", login="ops-person", name="Deployment Script")])
    (entry,) = build(fx)["all"]["list"]
    assert entry["kind"] == "human" and "name" not in entry


def test_aliases_apply_to_co_authors(fx):
    fx.config(CONFIG + "aliases:\n  ada-old: ada-dev\n  ada@home.example.com: ada-dev\n")
    fx.raw("alpha-api", "commits.jsonl", [
        commit("1", login="grace-codes", co_authors=[co("Ada-Old", "Ada", "a@example.com")]),
        commit("2", login="grace-codes", co_authors=[co(None, "Ada", "Ada@Home.example.com")]),
    ])
    fx.raw("gamma-docs", "commits.jsonl", [commit("3", login="ada-dev")])
    scope = build(fx)["all"]
    assert sorted(by_login(scope)) == ["ada-dev", "grace-codes"]
    assert by_login(scope)["ada-dev"]["repos"] == ["alpha-api", "gamma-docs"]


def test_unlinked_co_authors_merge_with_unlinked_authors_by_email(fx):
    fx.raw("alpha-api", "commits.jsonl", [
        commit("1", login=None, email="pair@example.com", name="Pair"),
        commit("2", login="ada-dev", co_authors=[co(None, "Pair Programmer", "PAIR@example.com"), "bad", 5]),
        commit("3", login="ada-dev", co_authors="not a list"),
    ])
    assert build(fx)["all"]["by_kind"] == {"human": 1, "unlinked": 1, "bot": 0}
