"""The gh transport: argument building, error classification, retries, rate limits and the request budget."""
import datetime
import json

import pytest

from team_wrapped import github
from team_wrapped.github import BudgetExhausted, Forbidden, GhError, GitHub, NotFound, RateLimited, Transient

RESET = "2026-11-27T15:42:00Z"


def ok(data):
    return 0, json.dumps({"data": data}), ""


def graphql_error(kind, message="boom"):
    return 1, json.dumps({"data": None, "errors": [{"type": kind, "message": message}]}), f"gh: {message}"


class Script:
    """A fake runner: returns the queued responses in order and records each argument list."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, args):
        self.calls.append(args)
        return self.responses.pop(0)


def client(*responses, **kwargs):
    runner = Script(*responses)
    sleeps = []
    return GitHub(runner, sleep=sleeps.append, **kwargs), runner, sleeps


def test_builds_gh_arguments_without_a_shell():
    gh, runner, _ = client(ok({"x": 1}))
    assert gh.graphql("query($owner: String!) { x }", owner="123", first=50, after=None, flag=True) == {"x": 1}
    args = runner.calls[0]
    assert args[:3] == ["gh", "api", "graphql"]
    assert ["-f", "query=query($owner: String!) { x }"] == args[3:5]
    assert ["-f", "owner=123"] == args[5:7]          # text stays text even when it looks like a number
    assert ["-F", "first=50"] == args[7:9]
    assert ["-F", "flag=true"] == args[9:11]
    assert not any("after" in a for a in args)       # None variables are omitted (GraphQL null)
    assert gh.requests == 1


@pytest.mark.parametrize("response, error", [
    (graphql_error("NOT_FOUND", "Could not resolve to a Repository"), NotFound),
    (graphql_error("FORBIDDEN", "Resource not accessible"), Forbidden),
    ((1, "", "gh: Not Found (HTTP 404)"), NotFound),
    ((1, "", "gh: Must have admin rights (HTTP 403)"), Forbidden),
    ((1, "", "gh: Bad credentials (HTTP 401)"), Forbidden),
    (graphql_error("SOMETHING", "Field 'x' doesn't exist"), GhError),
])
def test_classifies_errors(response, error):
    gh, _, _ = client(response)
    with pytest.raises(error):
        gh.graphql("q")


def test_transient_errors_retry_with_backoff_then_succeed():
    gh, runner, sleeps = client((1, "", "gh: HTTP 502: Bad Gateway"), (1, "", "dial tcp: connection reset"), ok({"x": 2}))
    assert gh.graphql("q") == {"x": 2}
    assert len(runner.calls) == 3 and sleeps == [2.0, 4.0] and gh.requests == 3


def test_transient_errors_give_up_after_the_retry_limit():
    gh, _, sleeps = client(*[(1, "", "gh: HTTP 503")] * 4, retries=3)
    with pytest.raises(Transient):
        gh.graphql("q")
    assert len(sleeps) == 3


def test_primary_rate_limit_stops_with_the_reset_time():
    gh, _, sleeps = client(ok({"rateLimit": {"remaining": 10, "resetAt": RESET}}),
                           graphql_error("RATE_LIMITED", "API rate limit exceeded"))
    gh.graphql("q")
    with pytest.raises(RateLimited) as caught:
        gh.graphql("q")
    assert caught.value.reset_at == datetime.datetime(2026, 11, 27, 15, 42, tzinfo=datetime.timezone.utc)
    assert "resume after" in str(caught.value) and sleeps == []


def test_exhausted_points_stop_before_the_next_request():
    gh, runner, _ = client(ok({"rateLimit": {"remaining": 0, "resetAt": RESET}}))
    gh.graphql("q")
    with pytest.raises(RateLimited):
        gh.graphql("q")
    assert len(runner.calls) == 1


def test_secondary_rate_limit_waits_then_retries():
    gh, _, sleeps = client((1, "", "gh: You have exceeded a secondary rate limit (HTTP 403)"), ok({"x": 3}))
    assert gh.graphql("q") == {"x": 3}
    assert sleeps == [60.0]


def test_secondary_rate_limit_stops_after_the_retry_limit():
    gh, _, _ = client(*[(1, "", "gh: You have exceeded a secondary rate limit")] * 3, retries=2)
    with pytest.raises(RateLimited, match="resume after"):
        gh.graphql("q")


def test_budget_stops_cleanly():
    gh, runner, _ = client(ok({}), ok({}), max_requests=2)
    gh.graphql("q")
    gh.graphql("q")
    with pytest.raises(BudgetExhausted):
        gh.graphql("q")
    assert len(runner.calls) == 2


def test_error_messages_never_carry_tokens():
    gh, _, _ = client((1, "", "gh: weird failure ghp_abcdefghijklmnopqrstuvwxyz0123456789 Authorization: token gho_SECRET123"))
    with pytest.raises(GhError) as caught:
        gh.graphql("q")
    assert "ghp_" not in str(caught.value) and "SECRET" not in str(caught.value)


def test_missing_gh_is_a_clear_error(monkeypatch):
    def missing(*args, **kwargs):
        raise FileNotFoundError("gh")
    monkeypatch.setattr(github.subprocess, "run", missing)
    with pytest.raises(GhError, match="gh auth login"):
        GitHub().graphql("q")
