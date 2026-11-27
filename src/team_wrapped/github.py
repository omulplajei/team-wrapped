"""`gh api graphql` wrapper (spec section 8): one transport for every collector call.

No token handling here: `gh` reads its own credentials (`gh auth login`). Calls are argument lists, never a shell.
Errors are classified so the collector can decide per repository and metric:

- `RateLimited`: the primary limit is spent (stop, resume after `reset_at`), or a secondary limit outlasted the retries.
- `Transient`: 5xx or network trouble that outlasted the retries.
- `NotFound`, `Forbidden`: the repository (or the token's access to it) is the problem; other repositories may work.
- `BudgetExhausted`: `--max-requests` reached.
- `GhError`: anything else (a bad query, `gh` missing).
"""
from __future__ import annotations

import datetime
import json
import re
import subprocess
import time
from typing import Callable

Runner = Callable[[list], tuple]        # args -> (returncode, stdout, stderr)

_TOKEN = re.compile(r"\b(gh[pousr]_[A-Za-z0-9_]+|github_pat_[A-Za-z0-9_]+)|((?:token|bearer)\s+)\S+", re.IGNORECASE)
_TRANSIENT = re.compile(r"HTTP 5\d\d|\b50[234]\b|timed? ?out|timeout|connection (reset|refused)|EOF|"
                        r"temporarily unavailable|could not connect|network is unreachable|no such host",
                        re.IGNORECASE)


class GhError(Exception):
    """A call failed in a way retries do not fix."""


class NotFound(GhError):
    pass


class Forbidden(GhError):
    pass


class Transient(GhError):
    pass


class BudgetExhausted(GhError):
    pass


class RateLimited(GhError):
    def __init__(self, reset_at: datetime.datetime | None, secondary: bool = False):
        self.reset_at, self.secondary = reset_at, secondary
        kind = "secondary rate limit" if secondary else "API rate limit"
        when = reset_at.astimezone().strftime("%H:%M") if reset_at else "an hour"
        super().__init__(f"{kind} reached; resume after {when}")


def redact(text: str, limit: int = 300) -> str:
    """One line of at most `limit` characters with anything token-like removed."""
    text = _TOKEN.sub(lambda m: (m.group(2) or "") + "[redacted]", " ".join(str(text).split()))
    return text if len(text) <= limit else text[: limit - 1] + "…"


def subprocess_runner(args: list) -> tuple:
    try:
        done = subprocess.run(args, capture_output=True, text=True, timeout=180, check=False)
    except FileNotFoundError as error:
        raise GhError("the gh CLI was not found; install it and run `gh auth login`") from error
    except subprocess.TimeoutExpired:
        return 124, "", "gh timed out"
    return done.returncode, done.stdout, done.stderr


def _parse_time(value) -> datetime.datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(datetime.timezone.utc)
    except ValueError:
        return None


def _arguments(query: str, variables: dict) -> list:
    args = ["gh", "api", "graphql", "-f", f"query={query}"]
    for name, value in variables.items():
        if value is None:
            continue                     # an omitted variable is null to GraphQL
        if isinstance(value, bool):
            args += ["-F", f"{name}={'true' if value else 'false'}"]
        elif isinstance(value, int):
            args += ["-F", f"{name}={value}"]
        else:                            # -f keeps text as text (a repo named "123" stays a string)
            args += ["-f", f"{name}={value}"]
    return args


class GitHub:
    """GraphQL client. `runner` is injectable for tests; `sleep` too. `requests` counts every `gh` call."""

    def __init__(self, runner: Runner | None = None, *, max_requests: int | None = None, retries: int = 3,
                 backoff: float = 2.0, secondary_wait: float = 60.0, sleep=time.sleep, now=None):
        self.runner = runner or subprocess_runner
        self.max_requests, self.retries, self.backoff = max_requests, retries, backoff
        self.secondary_wait, self.sleep = secondary_wait, sleep
        self.now = now or (lambda: datetime.datetime.now(datetime.timezone.utc))
        self.requests = 0
        self.remaining: int | None = None
        self.reset_at: datetime.datetime | None = None

    def graphql(self, query: str, **variables) -> dict:
        """The `data` object of the response. Raises one of the errors above."""
        args = _arguments(query, variables)
        attempt = 0
        while True:
            if self.remaining is not None and self.remaining <= 0:
                raise RateLimited(self.reset_at)
            if self.max_requests is not None and self.requests >= self.max_requests:
                raise BudgetExhausted(f"request budget of {self.max_requests} reached")
            self.requests += 1
            try:
                return self._call(args)
            except Transient:
                if attempt >= self.retries:
                    raise
                self.sleep(self.backoff * 2 ** attempt)
            except RateLimited as error:
                if not error.secondary:
                    raise
                if attempt >= self.retries:
                    raise RateLimited(self.now() + datetime.timedelta(seconds=self.secondary_wait * 5), True) from None
                self.sleep(self.secondary_wait * (attempt + 1))
            attempt += 1

    def _call(self, args: list) -> dict:
        code, stdout, stderr = self.runner(args)
        try:
            body = json.loads(stdout) if stdout and stdout.strip() else None
        except ValueError:
            body = None
        if isinstance(body, dict):
            limit = (body.get("data") or {}).get("rateLimit") if isinstance(body.get("data"), dict) else None
            if isinstance(limit, dict):
                self.remaining = limit.get("remaining") if isinstance(limit.get("remaining"), int) else None
                self.reset_at = _parse_time(limit.get("resetAt")) or self.reset_at
            errors = body.get("errors")
            if errors:
                raise self._classify_graphql(errors if isinstance(errors, list) else [errors])
            if code == 0 and isinstance(body.get("data"), dict):
                return body["data"]
        if code == 0 and body is None:
            raise GhError("gh returned no JSON")
        raise self._classify_text(f"{stderr} {stdout if body is None else ''}")

    def _classify_graphql(self, errors: list) -> GhError:
        first = errors[0] if isinstance(errors[0], dict) else {"message": str(errors[0])}
        kinds = {e.get("type") for e in errors if isinstance(e, dict)}
        message = redact(first.get("message") or "GraphQL error")
        if "secondary rate limit" in message.lower():
            return RateLimited(None, secondary=True)
        if "RATE_LIMITED" in kinds:
            return RateLimited(self.reset_at)
        if "NOT_FOUND" in kinds:
            return NotFound(message)
        if "FORBIDDEN" in kinds or "INSUFFICIENT_SCOPES" in kinds:
            return Forbidden(message)
        return GhError(message)

    def _classify_text(self, text: str) -> GhError:
        lower = text.lower()
        message = redact(text.replace("gh: ", "", 1).strip() or "gh failed")
        if "secondary rate limit" in lower or "abuse detection" in lower:
            return RateLimited(None, secondary=True)
        if "rate limit" in lower:
            return RateLimited(self.reset_at)
        if "http 404" in lower or "not found" in lower:
            return NotFound(message)
        if "http 403" in lower or "http 401" in lower:
            return Forbidden(message)
        if _TRANSIENT.search(text):
            return Transient(message)
        return GhError(message)
