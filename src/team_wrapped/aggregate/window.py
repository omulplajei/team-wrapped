"""Timestamps, time zones and the reporting window (spec 5.2: inclusive, evaluated in the configured zone)."""
from __future__ import annotations

import datetime
from dataclasses import dataclass
from zoneinfo import ZoneInfo


def parse_timestamp(value) -> datetime.datetime | None:
    """An ISO 8601 string as an aware UTC datetime. None for anything unusable (missing, not text, malformed)."""
    if not isinstance(value, str) or not value:
        return None
    text = value[:-1] + "+00:00" if value[-1] in "Zz" else value
    try:
        parsed = datetime.datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.timezone.utc)
    return parsed.astimezone(datetime.timezone.utc)


def local_datetime(value, tz: ZoneInfo) -> datetime.datetime | None:
    parsed = parse_timestamp(value)
    return parsed.astimezone(tz) if parsed else None


def local_date(value, tz: ZoneInfo) -> datetime.date | None:
    """The calendar date a timestamp falls on in `tz` (23:30Z on Dec 31 is Jan 1 in Europe/Bucharest)."""
    local = local_datetime(value, tz)
    return local.date() if local else None


def in_window(value, tz: ZoneInfo, since: datetime.date | None, until: datetime.date | None) -> bool:
    """True when the local date of `value` lies in [since, until]; either bound may be None. Unusable values are out."""
    day = local_date(value, tz)
    if day is None:
        return False
    return (since is None or day >= since) and (until is None or day <= until)


@dataclass(frozen=True)
class Window:
    """The configured window and time zone, bundled for the builders."""
    tz: ZoneInfo
    since: datetime.date | None = None
    until: datetime.date | None = None

    @classmethod
    def from_config(cls, config) -> "Window":
        return cls(ZoneInfo(config.timezone),
                   datetime.date.fromisoformat(config.since) if config.since else None,
                   datetime.date.fromisoformat(config.until) if config.until else None)

    def local_datetime(self, value) -> datetime.datetime | None:
        return local_datetime(value, self.tz)

    def local_date(self, value) -> datetime.date | None:
        """Local date of a timestamp whatever the window, or None."""
        return local_date(value, self.tz)

    def contains(self, value) -> bool:
        return in_window(value, self.tz, self.since, self.until)

    def date_in_window(self, value) -> datetime.date | None:
        """Local date of a timestamp when it is inside the window, else None. Use it for day/month grouping."""
        return self.local_date(value) if self.contains(value) else None
