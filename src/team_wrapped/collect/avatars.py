"""Contributor avatars (spec section 6): `https://github.com/<login>.png` into data/avatars/, once per login.

Files are named exactly as the aggregator looks them up (`contributors.avatar_name` of the lower-cased login).
A failed download leaves the contributor on the placeholder; failed logins are listed in raw/avatars-failed.json.
Bots use their app's account name (`sample-bot[bot]` -> github.com/sample-bot.png). Some apps have no such account
page, so when that fails for a `[bot]` login the app is looked up with `gh api apps/<name>` and its avatar is taken
from avatars.githubusercontent.com/in/<app id>. That lookup is the only `gh` call here.
The shared placeholder (data/avatars/placeholder.png) is written when missing."""
from __future__ import annotations

import re
import urllib.parse
import urllib.request
from pathlib import Path

from ..aggregate.common import Resolver
from ..aggregate.contributors import avatar_name
from ..aggregate.io import write_json
from ..aggregate.raw import load_raw
from .placeholder import ensure_placeholder, placeholder_png  # noqa: F401 - re-exported

MAX_BYTES = 1_000_000
TIMEOUT = 15
FAILED_FILE = "avatars-failed.json"     # under raw/; the aggregator does not read it
_HOSTS = {"github.com", "avatars.githubusercontent.com"}   # github.com/<login>.png redirects to the CDN
_LOGIN = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]{0,38}(\[bot\])?")
_LOGIN_FIELDS = ("author_login", "reviewer_login")
_DELETED = {"ghost"}
ACCOUNT_AVATAR = "https://github.com/{account}.png?size=200"
APP_AVATAR = "https://avatars.githubusercontent.com/in/{app_id}?s=200"


def _check(url: str) -> None:
    parts = urllib.parse.urlsplit(url)
    if parts.scheme != "https" or parts.hostname not in _HOSTS:
        raise ValueError(f"refusing to fetch {url}")


class _GitHubOnly(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        try:
            _check(newurl)
        except ValueError as error:
            raise OSError(str(error)) from None
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch_url(url: str) -> tuple:
    """(content type, body) of an https GitHub avatar URL. Reads at most MAX_BYTES + 1 bytes."""
    _check(url)
    opener = urllib.request.build_opener(_GitHubOnly)
    with opener.open(urllib.request.Request(url, headers={"User-Agent": "team-wrapped"}), timeout=TIMEOUT) as response:
        return response.headers.get("Content-Type", ""), response.read(MAX_BYTES + 1)


def _logins(data_root: Path, config) -> list:
    """Distinct canonical logins (aliases applied) found in the raw records, by lower-cased login."""
    resolver = Resolver(config.aliases)
    found = {}
    raw = load_raw(data_root, config)
    for records in raw.records.values():
        for record in records:
            for name in _LOGIN_FIELDS:
                who = resolver.resolve(record.get(name), None, None)
                if who and who[1].lower() not in _DELETED:
                    found.setdefault(who[1].lower(), who[1])
    return sorted(found.values(), key=str.lower)


def _app_id(value) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else None


def app_id_lookup(gh):
    """account -> GitHub app id, through `gh api apps/<account>` on a `GitHub` client (so it counts against its
    request budget). Raises on any failure or a response without a positive integer id."""
    def lookup(account: str) -> int:
        found = _app_id(gh.rest(f"apps/{account}").get("id"))
        if found is None:
            raise ValueError(f"app {account} has no usable id")
        return found
    return lookup


def _default_app_id(account: str) -> int:
    from ..github import GitHub
    return app_id_lookup(GitHub())(account)


def _image(fetch, url: str):
    """The body of an image at `url`, or None when the fetch fails or the answer is not a usable image."""
    try:
        content_type, body = fetch(url)
    except Exception:               # noqa: BLE001 - any failure falls back to the placeholder
        return None
    if not str(content_type).lower().startswith("image/") or not body or len(body) > MAX_BYTES:
        return None
    return body


def _app_image(fetch, app_id, account: str):
    try:
        found = _app_id(app_id(account))
    except Exception:               # noqa: BLE001 - any failure falls back to the placeholder
        return None
    if found is None:
        return None
    return _image(fetch, APP_AVATAR.format(app_id=found))


def missing_avatars(data_root, config) -> list:
    """Logins found in the raw records whose avatar file is not there yet (what a download would try)."""
    folder = Path(data_root) / "avatars"
    return [login for login in _logins(Path(data_root), config)
            if not (folder / f"{avatar_name(login.lower())}.png").is_file()]


def download_avatars(data_root, config, fetch=None, app_id=None, log=print) -> list:
    """Download missing avatars and make sure the placeholder exists. Returns the logins that failed (also written
    to raw/avatars-failed.json). `fetch(url) -> (content type, body)` and `app_id(account) -> int` are injectable."""
    data_root = Path(data_root)
    fetch = fetch or fetch_url
    app_id = app_id or _default_app_id
    folder = data_root / "avatars"
    ensure_placeholder(folder)
    failed, downloaded = [], 0
    for login in missing_avatars(data_root, config):
        path = folder / f"{avatar_name(login.lower())}.png"
        if not _LOGIN.fullmatch(login):
            failed.append(login)
            continue
        is_app = login.endswith("[bot]")
        account = login[:-5] if is_app else login
        body = _image(fetch, ACCOUNT_AVATAR.format(account=urllib.parse.quote(account)))
        if body is None and is_app:
            body = _app_image(fetch, app_id, account)
        if body is None:
            failed.append(login)
            continue
        folder.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_bytes(body)
        tmp.replace(path)
        downloaded += 1
    failed.sort()
    write_json(data_root / "raw" / FAILED_FILE, failed)
    log(f"avatars: {downloaded} downloaded, {len(failed)} failed (placeholder used)")
    return failed
