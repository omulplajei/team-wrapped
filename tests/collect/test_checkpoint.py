"""checkpoint.json: reading, writing, and the fetch plan a checkpoint gives each unit."""
import datetime
import json

from team_wrapped.collect.checkpoint import (Checkpoint, PrPiece, narrowest, plan_commits, plan_pull_requests,
                                             read_checkpoints, write_checkpoint)
from team_wrapped.collect.common import utc_bounds

UTC = datetime.timezone.utc
TZ = "Europe/Bucharest"
NOW = datetime.datetime(2026, 11, 27, 12, tzinfo=UTC)
D = datetime.date.fromisoformat


def at(text):
    return datetime.datetime.fromisoformat(text.replace("Z", "+00:00"))


class Window:
    """The fields of collect.Plan the planners read."""

    def __init__(self, since="2026-01-01", until="2026-12-31", timezone=TZ):
        self.since, self.until, self.timezone = since, until, timezone
        self.start, self.end = utc_bounds(since and D(since), until and D(until), timezone)


def cp(since="2026-01-01", until="2026-12-31", covered_to="2026-11-13T12:00:00Z", synced_at=None, overlap=7):
    return Checkpoint(synced_at=at(synced_at or covered_to), since=since and D(since), until=until and D(until),
                      covered_to=at(covered_to), overlap_days=overlap)


JAN1 = at("2025-12-31T22:00:00Z")           # local midnight starting 2026-01-01 in Bucharest
DEC31 = at("2026-12-31T21:59:59Z")          # the last second of 2026-12-31


# --- storage

def test_write_then_read_round_trips_and_keeps_other_metrics(tmp_path):
    write_checkpoint(tmp_path, "commits", cp())
    write_checkpoint(tmp_path, "reviews", cp(since="2026-03-01", overlap=1))
    stored = json.loads((tmp_path / "checkpoint.json").read_text())
    assert stored["commits"] == {"synced_at": "2026-11-13T12:00:00Z", "since": "2026-01-01", "until": "2026-12-31",
                                 "covered_to": "2026-11-13T12:00:00Z", "overlap_days": 7}
    checkpoints, warnings = read_checkpoints(tmp_path)
    assert warnings == [] and checkpoints == {"commits": cp(), "reviews": cp(since="2026-03-01", overlap=1)}
    assert not list(tmp_path.glob("*.tmp"))


def test_open_window_dates_are_stored_as_null(tmp_path):
    write_checkpoint(tmp_path, "commits", cp(since=None, until=None))
    assert json.loads((tmp_path / "checkpoint.json").read_text())["commits"]["since"] is None
    assert read_checkpoints(tmp_path)[0]["commits"] == cp(since=None, until=None)


def test_missing_file_is_no_checkpoint(tmp_path):
    assert read_checkpoints(tmp_path) == ({}, [])


def test_corrupt_file_is_treated_as_absent_with_a_warning(tmp_path):
    (tmp_path / "checkpoint.json").write_text("{not json")
    checkpoints, warnings = read_checkpoints(tmp_path)
    assert checkpoints == {} and len(warnings) == 1 and "checkpoint.json" in warnings[0]


def test_a_bad_entry_is_dropped_with_a_warning_and_others_kept(tmp_path):
    write_checkpoint(tmp_path, "commits", cp())
    stored = json.loads((tmp_path / "checkpoint.json").read_text())
    stored["pull_requests"] = {"synced_at": "yesterday", "since": "2026-01-01"}
    stored["reviews"] = ["not", "a", "dict"]
    (tmp_path / "checkpoint.json").write_text(json.dumps(stored))
    checkpoints, warnings = read_checkpoints(tmp_path)
    assert list(checkpoints) == ["commits"]
    assert len(warnings) == 2 and "pull_requests" in warnings[0] and "reviews" in warnings[1]


# --- commits

def test_commits_without_a_checkpoint_fetch_the_window_and_cap_coverage_at_the_run_start():
    fetch = plan_commits(Window(), None, NOW, 7)
    assert fetch.mode == "full" and fetch.pieces == [(JAN1, DEC31)]
    assert fetch.checkpoint == Checkpoint(synced_at=NOW, since=D("2026-01-01"), until=D("2026-12-31"),
                                          covered_to=NOW, overlap_days=7)   # until is in the future
    assert fetch.since == D("2026-01-01")


def test_a_past_window_is_covered_to_its_end():
    fetch = plan_commits(Window(until="2026-06-30"), None, NOW, 7)
    assert fetch.checkpoint.covered_to == at("2026-06-30T20:59:59Z")


def test_commits_with_a_checkpoint_fetch_from_covered_to_minus_the_overlap():
    fetch = plan_commits(Window(), cp(), NOW, 7)
    assert fetch.mode == "incremental"
    assert fetch.pieces == [(at("2026-11-06T12:00:00Z"), DEC31)]
    assert fetch.since == D("2026-11-06")
    assert fetch.checkpoint == Checkpoint(synced_at=NOW, since=D("2026-01-01"), until=D("2026-12-31"),
                                          covered_to=NOW, overlap_days=7)


def test_the_overlap_is_configurable():
    assert plan_commits(Window(), cp(), NOW, 0).pieces == [(at("2026-11-13T12:00:00Z"), DEC31)]
    assert plan_commits(Window(), cp(), NOW, 30).checkpoint.overlap_days == 30


def test_the_overlap_never_reaches_before_the_requested_since():
    fetch = plan_commits(Window(since="2026-11-10"), cp(), NOW, 7)
    assert fetch.mode == "incremental" and fetch.pieces == [(at("2026-11-09T22:00:00Z"), DEC31)]
    assert fetch.checkpoint.since == D("2026-01-01")      # the earlier coverage stays claimed


def test_an_earlier_since_also_fetches_the_missing_start():
    fetch = plan_commits(Window(), cp(since="2026-03-01"), NOW, 7)
    assert fetch.mode == "incremental"
    assert fetch.pieces == [(at("2026-11-06T12:00:00Z"), DEC31), (JAN1, at("2026-03-07T22:00:00Z"))]
    assert fetch.checkpoint.since == D("2026-01-01") and fetch.since == D("2026-01-01")


def test_pieces_that_meet_are_merged():
    fetch = plan_commits(Window(), cp(since="2026-03-01", covered_to="2026-03-05T00:00:00Z"), NOW, 7)
    assert fetch.pieces == [(JAN1, DEC31)]


def test_a_window_already_covered_fetches_nothing_and_keeps_the_coverage():
    fetch = plan_commits(Window(until="2026-06-30"), cp(), NOW, 7)
    assert fetch.mode == "incremental" and fetch.pieces == []
    assert fetch.checkpoint.covered_to == at("2026-11-13T12:00:00Z")
    assert fetch.checkpoint.until == D("2026-12-31")


def test_an_until_inside_the_overlap_fetches_up_to_that_until_only():
    fetch = plan_commits(Window(until="2026-11-10"), cp(), NOW, 7)
    assert fetch.pieces == [(at("2026-11-06T12:00:00Z"), at("2026-11-10T21:59:59Z"))]
    assert fetch.checkpoint.covered_to == at("2026-11-13T12:00:00Z")


def test_a_window_that_does_not_touch_the_coverage_is_fetched_in_full():
    later = plan_commits(Window(since="2026-12-01"), cp(), NOW, 7)
    assert later.mode == "full" and later.pieces == [(at("2026-11-30T22:00:00Z"), DEC31)]
    assert later.checkpoint.since == D("2026-12-01")
    earlier = plan_commits(Window(until="2026-02-20"), cp(since="2026-03-01"), NOW, 7)
    assert earlier.mode == "full" and earlier.checkpoint.until == D("2026-02-20")
    touching = plan_commits(Window(until="2026-02-28"), cp(since="2026-03-01"), NOW, 7)
    assert touching.mode == "incremental" and touching.checkpoint.since == D("2026-01-01")


def test_open_windows():
    fetch = plan_commits(Window(since=None, until=None), cp(since=None, until=None), NOW, 7)
    assert fetch.pieces == [(at("2026-11-06T12:00:00Z"), None)] and fetch.checkpoint.since is None
    earlier = plan_commits(Window(since=None, until=None), cp(), NOW, 7)
    assert earlier.pieces == [(at("2026-11-06T12:00:00Z"), None), (None, at("2026-01-07T22:00:00Z"))]
    assert earlier.checkpoint.since is None


# --- pull requests

def test_pull_requests_without_a_checkpoint_search_the_window():
    fetch = plan_pull_requests(Window(), None, NOW)
    assert fetch.mode == "full" and fetch.pieces == [PrPiece(JAN1, None, DEC31)]
    assert fetch.checkpoint == Checkpoint(synced_at=NOW, since=D("2026-01-01"), until=D("2026-12-31"),
                                          covered_to=NOW, overlap_days=1)


def test_pull_requests_updated_since_the_last_sync_minus_a_day():
    fetch = plan_pull_requests(Window(), cp(), NOW)
    assert fetch.mode == "incremental"
    assert fetch.pieces == [PrPiece(at("2026-11-12T12:00:00Z"), None, DEC31)]       # piece A only
    assert fetch.since == D("2026-11-12")
    assert fetch.checkpoint == Checkpoint(synced_at=NOW, since=D("2026-01-01"), until=D("2026-12-31"),
                                          covered_to=NOW, overlap_days=1)


def test_a_later_until_adds_the_newly_created_range():
    fetch = plan_pull_requests(Window(), cp(until="2026-06-30", covered_to="2026-06-30T20:59:59Z",
                                           synced_at="2026-07-02T08:00:00Z"), NOW)
    june30 = at("2026-06-30T20:59:59Z")
    assert fetch.pieces == [PrPiece(at("2026-07-01T08:00:00Z"), None, june30),                 # A
                            PrPiece(JAN1, june30 + datetime.timedelta(seconds=1), DEC31)]       # B
    assert fetch.checkpoint.until == D("2026-12-31") and fetch.checkpoint.covered_to == NOW


def test_a_smaller_until_still_refreshes_the_known_creation_range():
    fetch = plan_pull_requests(Window(until="2026-06-30"), cp(), NOW)
    assert fetch.pieces == [PrPiece(at("2026-11-12T12:00:00Z"), None, DEC31)]
    assert fetch.checkpoint.until == D("2026-12-31")


def test_an_earlier_since_falls_back_to_the_whole_window_with_a_notice():
    fetch = plan_pull_requests(Window(), cp(since="2026-03-01"), NOW)
    assert fetch.mode == "full" and fetch.pieces == [PrPiece(JAN1, None, DEC31)]
    assert "2026-03-01" in fetch.notice
    assert fetch.checkpoint.since == D("2026-01-01")


def test_open_until_and_a_checkpoint_until_add_an_open_created_range():
    fetch = plan_pull_requests(Window(until=None), cp(until="2026-06-30"), NOW)
    assert fetch.pieces[1] == PrPiece(JAN1, at("2026-06-30T21:00:00Z"), None)
    assert fetch.checkpoint.until is None and fetch.checkpoint.covered_to == NOW


def test_metrics_sharing_one_search_use_the_narrowest_claim():
    a = cp(since="2026-01-01", until="2026-12-31", covered_to="2026-11-20T00:00:00Z")
    b = cp(since="2026-03-01", until="2026-06-30", covered_to="2026-11-10T00:00:00Z", synced_at="2026-11-10T00:00:00Z")
    assert narrowest([a, b]) == Checkpoint(synced_at=at("2026-11-10T00:00:00Z"), since=D("2026-03-01"),
                                           until=D("2026-06-30"), covered_to=at("2026-11-10T00:00:00Z"),
                                           overlap_days=7)
    assert narrowest([a, None]) is None and narrowest([a]) == a
    assert narrowest([cp(since=None, until=None), a]).since == D("2026-01-01")
