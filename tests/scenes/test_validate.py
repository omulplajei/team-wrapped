import json
import shutil
from pathlib import Path

from team_wrapped.scenes.derived import DerivedData
from team_wrapped.scenes.loader import Entry, Scene, Script
from team_wrapped.scenes.scene_types import SceneType
from team_wrapped.scenes.validate import format_report, resolve_and_validate, validate_script

TYPES = {
    "stats": SceneType("stats", 8.0, ["items"], Path(".")),
    "bignumber": SceneType("bignumber", 6.0, ["value", "label"], Path(".")),
    "repogrid": SceneType("repogrid", 8.0, ["heading", "value", "names"], Path(".")),
    "sequence": SceneType("sequence", 6.0, ["heading", "steps"], Path(".")),
    "curiosity": SceneType("curiosity", 6.0, ["teaser", "records", "unit"], Path(".")),
}
CATALOG = {"summary.totals", "contributors", "repos.touched", "curiosities.busiest_day"}


def make_data(tmp_path, partial=()):
    d = tmp_path / "derived"
    d.mkdir(exist_ok=True)
    (d / "summary.json").write_text(json.dumps(
        {"scopes": {"all": {"totals": {"commits": 5}}}}))
    (d / "repos.json").write_text(json.dumps(
        {"scopes": {"all": {"touched": {"total": 2, "list": [{"name": "a"}, {"name": "b"}]}}}}))
    if not (d / "curiosities.json").exists():     # a test may write its own first
        (d / "curiosities.json").write_text(json.dumps(
            {"scopes": {"all": {"busiest_day": [{"value": 87, "date": "2026-03-14", "merged_prs": 12}]}}}))
    (d / "meta.json").write_text(json.dumps({"partial_datasets": list(partial)}))
    return DerivedData(tmp_path)


def run(tmp_path, requires, params=None, entry=None, partial=(), catalog=CATALOG, type_="stats"):
    scene = Scene(id="s", type=type_, title="S", requires=requires,
                  params={"items": []} if params is None else params)
    script = Script(id="x", title="X", period=2026, scope="all", scenes=[entry or Entry(scene="s")])
    return validate_script(script, {"s": scene}, make_data(tmp_path, partial), catalog, TYPES)


REQ = [{"dataset": "summary.totals", "fields": ["commits"]}]


def test_supported(tmp_path):
    report = run(tmp_path, REQ)
    assert report.results[0].status == "supported"
    assert report.results[0].problems == []
    assert report.ok


def test_missing_field(tmp_path):
    report = run(tmp_path, [{"dataset": "summary.totals", "fields": ["commits", "nope"]}])
    assert report.results[0].status == "unsupported"
    assert "'summary.totals' is missing field 'nope'" in report.results[0].problems
    assert not report.ok


def test_dataset_not_in_catalog(tmp_path):
    report = run(tmp_path, [{"dataset": "made.up", "fields": []}])
    assert "dataset 'made.up' is not in the catalog" in report.results[0].problems


def test_no_data_for_scope(tmp_path):
    entry = Entry(scene="s", scope="alpha")  # scope key becomes group:alpha, which has no data
    report = run(tmp_path, REQ, entry=entry)
    assert "no data for 'summary.totals' in scope 'group:alpha'" in report.results[0].problems


def test_partial_allowed_and_not_allowed(tmp_path):
    (tmp_path / "a").mkdir()   # make_data creates derived/, so each run needs its own folder
    (tmp_path / "b").mkdir()
    allowed = [{"dataset": "summary.totals", "fields": ["commits"], "allow_partial": True}]
    report = run(tmp_path / "a", allowed, partial=["summary.totals"])
    assert report.results[0].status == "partial"
    assert report.ok
    report = run(tmp_path / "b", REQ, partial=["summary.totals"])
    assert report.results[0].status == "unsupported"
    assert any("partial" in p for p in report.results[0].problems)


def test_unknown_type_and_missing_param(tmp_path):
    report = run(tmp_path, REQ, type_="nope")
    assert "unknown scene type 'nope'" in report.results[0].problems
    report = run(tmp_path, REQ, params={})
    assert "missing required param 'items'" in report.results[0].problems


def test_value_refs_must_resolve_to_required_data(tmp_path):
    good = {"items": [{"label": "C", "value": "summary.totals.commits"}]}
    assert run(tmp_path, REQ, params=good).results[0].status == "supported"
    bad = {"items": [{"label": "C", "value": "summary.totals.nope"}]}
    report = run(tmp_path, REQ, params=bad)
    assert "value 'summary.totals.nope' does not resolve to required data" in report.results[0].problems


def test_skip_vs_fail(tmp_path):
    bad_req = [{"dataset": "summary.totals", "fields": ["nope"]}]
    skip = run(tmp_path, bad_req, entry=Entry(scene="s", on_missing_data="skip"))
    assert skip.results[0].status == "unsupported" and skip.results[0].skipped
    assert skip.ok
    fail = run(tmp_path, bad_req, entry=Entry(scene="s", on_missing_data="fail"))
    assert not fail.results[0].skipped and not fail.ok


def test_year_wrapped_on_sample(repo_root, sample_root):
    resolved = resolve_and_validate("year-wrapped", repo_root, sample_root)
    statuses = {r.scene_id: r.status for r in resolved.report.results}
    assert statuses == {
        "we-shipped": "supported",
        "we-looked-after-each-other": "supported",
        "repos-touched": "supported",
        "we-changed-the-code": "partial",
        "year-in-numbers": "partial",
        "curiosity-busiest-month": "supported",
        "curiosity-busiest-day": "supported",
        "curiosity-longest-streak": "supported",
        "curiosity-longest-conversation": "supported",
        "curiosity-most-reviewed-pr": "supported",
        "curiosity-most-commits-pr": "partial",
        "curiosity-spring-cleaning": "partial",
        "how-many-of-us": "supported",
    }
    assert resolved.report.ok
    text = format_report(resolved.report)
    assert "year-in-numbers: partial" in text
    assert "we-changed-the-code: partial" in text
    assert "how-many-of-us: supported" in text
    assert "repos-touched: supported" in text


def test_every_curiosity_scene_file_is_valid_on_the_sample(repo_root, sample_root, tmp_path):
    ids = sorted(p.stem for p in (repo_root / "scenes").glob("curiosity-*.yml"))
    assert len(ids) == 9
    data = tmp_path / "data"
    shutil.copytree(sample_root, data)
    (data / "scripts").mkdir(exist_ok=True)
    (data / "scripts" / "all-curiosities.yml").write_text(
        "id: all-curiosities\nscope: all\nscenes:\n" + "".join(f"  - scene: {i}\n" for i in ids))
    resolved = resolve_and_validate("all-curiosities", repo_root, data)
    statuses = {r.scene_id: r.status for r in resolved.report.results}
    assert all(v in ("supported", "partial") for v in statuses.values())
    assert sorted(i for i, v in statuses.items() if v == "partial") == [
        "curiosity-most-commits-pr", "curiosity-spring-cleaning"]


def test_top_level_value_is_a_literal_for_types_that_do_not_require_it(tmp_path):
    report = run(tmp_path, REQ, params={"value": "a caption", "items": []})
    assert report.results[0].status == "supported"


def test_bignumber_refs_resolve(tmp_path):
    params = {"value": "summary.totals.commits", "label": "Commits",
              "supporting": [{"label": "Same", "value": "summary.totals.commits"}]}
    report = run(tmp_path, REQ, params=params, type_="bignumber")
    assert report.results[0].status == "supported"


def test_bignumber_unresolved_hero_and_supporting(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    bad_hero = {"value": "summary.totals.nope", "label": "X"}
    report = run(tmp_path / "a", REQ, params=bad_hero, type_="bignumber")
    assert "value 'summary.totals.nope' does not resolve to required data" in report.results[0].problems
    bad_sub = {"value": "summary.totals.commits", "label": "X",
               "supporting": [{"label": "Y", "value": "summary.totals.nope"}]}
    report = run(tmp_path / "b", REQ, params=bad_sub, type_="bignumber")
    assert "value 'summary.totals.nope' does not resolve to required data" in report.results[0].problems


def test_value_must_be_a_number(tmp_path):
    params = {"items": [{"label": "C", "value": "summary.totals"}]}   # a whole dataset, not a number
    report = run(tmp_path, REQ, params=params)
    assert "value 'summary.totals' is not a number" in report.results[0].problems
    assert report.results[0].status == "unsupported"


def test_bignumber_requires_value_and_label(tmp_path):
    report = run(tmp_path, REQ, params={"value": "summary.totals.commits"}, type_="bignumber")
    assert "missing required param 'label'" in report.results[0].problems


REPO_REQ = [{"dataset": "repos.touched", "fields": ["total", "list.name"]}]


def test_repogrid_names_must_resolve_to_a_list(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    (tmp_path / "c").mkdir()
    ok = {"heading": "Across {count}", "value": "repos.touched.total", "names": "repos.touched.list"}
    assert run(tmp_path / "a", REPO_REQ, params=ok, type_="repogrid").results[0].status == "supported"
    not_a_list = dict(ok, names="repos.touched.total")
    report = run(tmp_path / "b", REPO_REQ, params=not_a_list, type_="repogrid")
    assert "names 'repos.touched.total' does not resolve to a list" in report.results[0].problems
    missing = dict(ok, names="repos.touched.nope")
    report = run(tmp_path / "c", REPO_REQ, params=missing, type_="repogrid")
    assert "names 'repos.touched.nope' does not resolve to a list" in report.results[0].problems


def test_sequence_steps_values_are_checked(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    (tmp_path / "c").mkdir()
    ok = {"heading": "H", "steps": [
        {"value": "summary.totals.commits", "label": "Commits"},
        {"text": "and left"},
        {"value": "summary.totals.commits", "label": "Again"},
    ]}
    assert run(tmp_path / "a", REQ, params=ok, type_="sequence").results[0].status == "supported"
    bad = {"heading": "H", "steps": [{"value": "summary.totals.nope", "label": "X"}]}
    report = run(tmp_path / "b", REQ, params=bad, type_="sequence")
    assert "value 'summary.totals.nope' does not resolve to required data" in report.results[0].problems
    not_a_number = {"heading": "H", "steps": [{"value": "summary.totals", "label": "X"}]}
    report = run(tmp_path / "c", REQ, params=not_a_number, type_="sequence")
    assert "value 'summary.totals' is not a number" in report.results[0].problems


CUR_REQ = [{"dataset": "curiosities.busiest_day", "fields": ["value", "date"]}]


def test_curiosity_records_must_resolve_to_a_list(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    (tmp_path / "c").mkdir()
    ok = {"teaser": "T", "records": "curiosities.busiest_day", "unit": "commits"}
    assert run(tmp_path / "a", CUR_REQ, params=ok, type_="curiosity").results[0].status == "supported"
    report = run(tmp_path / "b", CUR_REQ, params=dict(ok, records="curiosities.busiest_day.value"), type_="curiosity")
    assert "records 'curiosities.busiest_day.value' does not resolve to a list" in report.results[0].problems
    report = run(tmp_path / "c", CUR_REQ, params=dict(ok, records="curiosities.nope"), type_="curiosity")
    assert "records 'curiosities.nope' does not resolve to a list" in report.results[0].problems


def _records_run(tmp_path, records, requires=CUR_REQ, params_extra=None):
    (tmp_path / "derived").mkdir(parents=True, exist_ok=True)
    (tmp_path / "derived" / "curiosities.json").write_text(json.dumps(
        {"scopes": {"all": {"busiest_day": records}}}))
    params = {"teaser": "T", "records": "curiosities.busiest_day", "unit": "commits", **(params_extra or {})}
    return run(tmp_path, requires, params=params, type_="curiosity").results[0]


def test_curiosity_first_record_must_carry_every_required_field(tmp_path):
    bad = _records_run(tmp_path / "a", [{"value": 5}, {"value": 4, "date": "2026-03-14"}])
    assert bad.status == "unsupported"
    assert "records 'curiosities.busiest_day': first record is missing field 'date'" in bad.problems
    ok = _records_run(tmp_path / "b", [{"value": 5, "date": "2026-03-14"}])
    assert ok.status == "supported"


def test_curiosity_first_record_value_must_be_a_number(tmp_path):
    bad = _records_run(tmp_path / "a", [{"value": "87", "date": "2026-03-14"}])
    assert bad.status == "unsupported"
    assert "records 'curiosities.busiest_day': first record's 'value' is not a number" in bad.problems
    keyed = _records_run(tmp_path / "b", [{"value": 1, "merged_prs": "x", "date": "d"}],
                         params_extra={"value_key": "merged_prs"})
    assert "records 'curiosities.busiest_day': first record's 'merged_prs' is not a number" in keyed.problems


def test_curiosity_records_must_contain_objects(tmp_path):
    bad = _records_run(tmp_path / "a", [5, 6])
    assert "records 'curiosities.busiest_day' must contain objects" in bad.problems


FLOW_REQ = [{"dataset": "commit_flow.groups", "fields": ["name", "commits"]},
            {"dataset": "commit_flow.window", "fields": ["days", "start"]}]
FLOW_PARAMS = {"groups": "commit_flow.groups", "window": "commit_flow.window"}
FLOW_TYPES = {"flow": SceneType("flow", 10.0, ["groups", "window"], Path("."))}


def _flow_run(tmp_path, flow, params=None):
    data = make_data(tmp_path)
    (tmp_path / "derived" / "commit_flow.json").write_text(json.dumps({"scopes": {"all": flow}}))
    scene = Scene(id="s", type="flow", title="S", requires=FLOW_REQ, params=params or FLOW_PARAMS)
    script = Script(id="x", title="X", period=2026, scope="all", scenes=[Entry(scene="s")])
    catalog = CATALOG | {"commit_flow.groups", "commit_flow.window"}
    return validate_script(script, {"s": scene}, data, catalog, FLOW_TYPES).results[0]


GOOD_FLOW = {"groups": [{"name": "alpha", "label": "Alpha", "total": 1, "commits": [[0, 5]]}],
             "window": {"days": 365, "start": "2026-01-01"}}


def test_commit_flow_groups_and_window_validate(tmp_path):
    assert _flow_run(tmp_path, GOOD_FLOW).status == "supported"


def test_commit_flow_params_must_resolve(tmp_path):
    result = _flow_run(tmp_path, GOOD_FLOW, {"groups": "commit_flow.window", "window": "commit_flow.groups"})
    assert "groups 'commit_flow.window' does not resolve to a list" in result.problems
    assert "window 'commit_flow.groups' does not resolve to an object" in result.problems


def test_commit_flow_first_group_needs_its_fields(tmp_path):
    result = _flow_run(tmp_path, dict(GOOD_FLOW, groups=[{"name": "alpha"}]))
    assert "groups 'commit_flow.groups': first group is missing field 'commits'" in result.problems
    assert "groups 'commit_flow.groups' must contain objects" in _flow_run(tmp_path, dict(GOOD_FLOW, groups=[1])).problems
