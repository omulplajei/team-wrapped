"""Contributor avatars (spec section 6): `https://github.com/<login>.png` into data/avatars/, once per login.

Files are named exactly as the aggregator looks them up (`contributors.avatar_name` of the lower-cased login).
A failed download leaves the contributor on the placeholder; failed logins are listed in raw/avatars-failed.json.
Bots use their app's account name (`renovate[bot]` -> github.com/renovate.png). `gh` is not used here."""
from __future__ import annotations

import re
import urllib.parse
import urllib.request
from pathlib import Path

from ..aggregate.common import Resolver
from ..aggregate.contributors import avatar_name
from ..aggregate.io import write_json
from ..aggregate.raw import load_raw

MAX_BYTES = 1_000_000
TIMEOUT = 15
FAILED_FILE = "avatars-failed.json"     # under raw/; the aggregator does not read it
_HOSTS = {"github.com", "avatars.githubusercontent.com"}   # github.com/<login>.png redirects to the CDN
_LOGIN = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]{0,38}(\[bot\])?")
_LOGIN_FIELDS = ("author_login", "reviewer_login")
_DELETED = {"ghost"}


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


def download_avatars(data_root, config, fetch=None, log=print) -> list:
    """Download missing avatars. Returns the logins that failed (also written to raw/avatars-failed.json)."""
    data_root = Path(data_root)
    fetch = fetch or fetch_url
    folder = data_root / "avatars"
    failed, downloaded = [], 0
    for login in _logins(data_root, config):
        path = folder / f"{avatar_name(login.lower())}.png"
        if path.is_file():
            continue
        if not _LOGIN.fullmatch(login):
            failed.append(login)
            continue
        account = login[:-5] if login.endswith("[bot]") else login
        try:
            content_type, body = fetch(f"https://github.com/{urllib.parse.quote(account)}.png?size=200")
        except Exception:           # noqa: BLE001 - any failure falls back to the placeholder
            failed.append(login)
            continue
        if not str(content_type).lower().startswith("image/") or not body or len(body) > MAX_BYTES:
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
