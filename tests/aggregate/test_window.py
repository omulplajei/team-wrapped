import datetime
from zoneinfo import ZoneInfo

import pytest

from team_wrapped.aggregate.window import Window, in_window, local_date, parse_timestamp

BUC = ZoneInfo("Europe/Bucharest")
UTC = ZoneInfo("UTC")
D = datetime.date


def test_parse_accepts_z_offsets_and_naive_as_utc():
    expected = datetime.datetime(2026, 3, 14, 9, 30, tzinfo=datetime.timezone.utc)
    assert parse_timestamp("2026-03-14T09:30:00Z") == expected
    assert parse_timestamp("2026-03-14T11:30:00+02:00") == expected
    assert parse_timestamp("2026-03-14T09:30:00") == expected


@pytest.mark.parametrize("value", [None, "", "yesterday", 5, "2026-13-01T00:00:00Z"])
def test_parse_returns_none_for_unusable_values(value):
    assert parse_timestamp(value) is None


def test_local_date_crosses_the_year_boundary_east_of_utc():
    assert local_date("2026-12-31T23:30:00Z", UTC) == D(2026, 12, 31)
    assert local_date("2026-12-31T23:30:00Z", BUC) == D(2027, 1, 1)         # UTC+2 in winter


def test_local_date_follows_dst():
    # Bucharest is UTC+2 until 2026-03-29 03:00 local, then UTC+3
    assert local_date("2026-03-28T21:59:00Z", BUC) == D(2026, 3, 28)
    assert local_date("2026-03-28T22:00:00Z", BUC) == D(2026, 3, 29)
    assert local_date("2026-10-24T20:59:00Z", BUC) == D(2026, 10, 24)       # summer: +3
    assert local_date("2026-10-24T21:00:00Z", BUC) == D(2026, 10, 25)
    assert local_date("2026-10-25T21:30:00Z", BUC) == D(2026, 10, 25)       # back to +2 after the change
    assert local_date("2026-10-25T22:00:00Z", BUC) == D(2026, 10, 26)


def test_local_date_west_of_utc():
    assert local_date("2026-01-01T03:00:00Z", ZoneInfo("America/New_York")) == D(2025, 12, 31)


def test_window_is_inclusive_on_both_ends_in_local_time():
    since, until = D(2026, 1, 1), D(2026, 12, 31)
    assert in_window("2026-12-31T21:59:59Z", BUC, since, until)             # Dec 31 23:59:59 local
    assert not in_window("2026-12-31T22:00:00Z", BUC, since, until)         # Jan 1 local
    assert not in_window("2025-12-31T21:59:59Z", BUC, since, until)         # Dec 31 23:59:59 local, 2025
    assert in_window("2025-12-31T22:00:00Z", BUC, since, until)             # Jan 1 00:00 local
    assert in_window("2026-12-31T23:30:00Z", UTC, since, until)
    assert not in_window("2026-12-31T23:30:00Z", BUC, since, until)


def test_open_ended_bounds():
    assert in_window("1999-01-01T00:00:00Z", UTC, None, None)
    assert in_window("1999-01-01T00:00:00Z", UTC, None, D(2000, 1, 1))
    assert not in_window("2001-01-01T00:00:00Z", UTC, None, D(2000, 1, 1))
    assert not in_window("1999-01-01T00:00:00Z", UTC, D(2000, 1, 1), None)


def test_unusable_timestamps_are_outside_the_window():
    assert not in_window(None, UTC, None, None)
    assert not in_window("garbage", UTC, None, None)


def test_window_object():
    window = Window(BUC, D(2027, 1, 1), None)
    assert window.contains("2026-12-31T23:30:00Z")
    assert window.date_in_window("2026-12-31T23:30:00Z") == D(2027, 1, 1)
    assert window.date_in_window("2026-12-31T21:00:00Z") is None
    assert window.local_date("2026-12-31T21:00:00Z") == D(2026, 12, 31)
    assert window.local_datetime("2026-12-31T21:00:00Z").hour == 23
