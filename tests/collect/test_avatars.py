"""Avatar download: names shared with the aggregator, validation, fallback and the failure list."""
import json

import pytest

from team_wrapped.collect import avatars
from team_wrapped.collect.avatars import download_avatars
from team_wrapped.config import load_config

PNG = b"\x89PNG\r\n\x1a\nfake"


@pytest.fixture
def data(tmp_path):
    root = tmp_path / "data"
    (root / "raw" / "sample-api").mkdir(parents=True)
    (root / "config.yml").write_text("org: sample-org\nrepos: [sample-api]\naliases: {Old-Ada: ada-dev}\n")
    rows = {
        "commits.jsonl": [{"sha": "a", "author_login": "Old-Ada"}, {"sha": "b", "author_login": None, "author_email": "x@example.com"}],
        "pull_requests.jsonl": [{"number": 1, "author_login": "renovate[bot]"}, {"number": 2, "author_login": "ghost"}],
        "reviews.jsonl": [{"pr_number": 1, "review_id": 1, "reviewer_login": "Grace-Codes"}],
        "comments.jsonl": [{"pr_number": 1, "comment_id": 1, "author_login": "ken-t"},
                           {"pr_number": 1, "comment_id": 2, "author_login": "bad/login"}],
    }
    for name, records in rows.items():
        (root / "raw" / "sample-api" / name).write_text("".join(json.dumps(r) + "\n" for r in records))
    return root


def no_app(account):
    raise LookupError(f"no app {account}")


def run(data, fetch, app_id=no_app):
    urls = []

    def recording(url):
        urls.append(url)
        return fetch(url)
    failed = download_avatars(data, load_config(data / "config.yml"), fetch=recording, app_id=app_id,
                              log=lambda s: None)
    return failed, urls


def pngs(data):
    return sorted(p.name for p in (data / "avatars").glob("*.png") if p.name != "placeholder.png")


def test_downloads_each_linked_login_once_with_the_aggregator_file_names(data):
    (data / "avatars").mkdir()
    (data / "avatars" / "ken-t.png").write_bytes(b"old")            # already there: kept, not fetched
    failed, urls = run(data, lambda url: ("image/png", PNG))
    assert sorted(urls) == ["https://github.com/Grace-Codes.png?size=200", "https://github.com/ada-dev.png?size=200",
                            "https://github.com/renovate.png?size=200"]
    assert pngs(data) == ["ada-dev.png", "grace-codes.png", "ken-t.png", "renovate_bot.png"]
    assert (data / "avatars" / "ken-t.png").read_bytes() == b"old"
    assert failed == ["bad/login"]
    assert json.loads((data / "raw" / "avatars-failed.json").read_text()) == ["bad/login"]


def test_bad_content_type_size_or_errors_fall_back(data):
    def fetch(url):
        if "ada-dev" in url:
            return "text/html", b"<html>"
        if "renovate" in url:
            return "image/png", b"x" * (avatars.MAX_BYTES + 1)
        raise OSError("timed out")
    failed, _ = run(data, fetch)
    assert failed == ["Grace-Codes", "ada-dev", "bad/login", "ken-t", "renovate[bot]"]
    assert pngs(data) == []


def test_the_default_fetcher_refuses_other_hosts():
    with pytest.raises(ValueError):
        avatars.fetch_url("http://github.com/x.png")
    with pytest.raises(ValueError):
        avatars.fetch_url("https://example.com/x.png")
    handler = avatars._GitHubOnly()
    with pytest.raises(OSError):
        handler.redirect_request(None, None, 302, "Found", {}, "https://example.com/evil.png")


def only_bots_fail(url):
    if "github.com/renovate.png" in url:
        raise OSError("HTTP 404")
    return "image/png", PNG


def test_a_bot_whose_account_avatar_fails_falls_back_to_its_app_avatar(data):
    asked = []

    def app_id(account):
        asked.append(account)
        return 2740
    failed, urls = run(data, lambda url: ("image/png", b"app") if "/in/" in url else only_bots_fail(url), app_id)
    assert asked == ["renovate"]
    assert "https://avatars.githubusercontent.com/in/2740?s=200" in urls
    assert (data / "avatars" / "renovate_bot.png").read_bytes() == b"app"
    assert failed == ["bad/login"]


def test_humans_never_use_the_app_route(data):
    asked = []

    def fetch(url):
        if "Grace-Codes" in url:
            raise OSError("HTTP 404")
        return "image/png", PNG
    failed, urls = run(data, fetch, lambda account: asked.append(account) or 1)
    assert asked == [] and not any("/in/" in u for u in urls)
    assert failed == ["Grace-Codes", "bad/login"]


@pytest.mark.parametrize("app_id, app_fetch", [
    (no_app, None),                                                   # the app lookup fails
    (lambda account: "2740", None),                                   # not an integer id
    (lambda account: True, None),
    (lambda account: 0, None),
    (lambda account: 2740, lambda url: ("text/html", b"<html>")),     # the app avatar is not an image
    (lambda account: 2740, lambda url: ("image/png", b"x" * (avatars.MAX_BYTES + 1))),
    (lambda account: 2740, lambda url: ("image/png", b"")),
])
def test_any_app_route_failure_keeps_the_placeholder(data, app_id, app_fetch):
    def fetch(url):
        if "/in/" in url:
            if app_fetch is None:
                raise AssertionError("no app avatar fetch expected")
            return app_fetch(url)
        return only_bots_fail(url)
    failed, _ = run(data, fetch, app_id)
    assert failed == ["bad/login", "renovate[bot]"]
    assert not (data / "avatars" / "renovate_bot.png").exists()
    assert json.loads((data / "raw" / "avatars-failed.json").read_text()) == ["bad/login", "renovate[bot]"]


def test_the_app_lookup_uses_the_rest_helper_and_validates_the_id():
    class Gh:
        def __init__(self, body):
            self.body, self.paths = body, []

        def rest(self, path):
            self.paths.append(path)
            return self.body
    gh = Gh({"id": 2740, "slug": "sample-bot"})
    assert avatars.app_id_lookup(gh)("sample-bot") == 2740
    assert gh.paths == ["apps/sample-bot"]
    for body in ({}, {"id": "2740"}, {"id": True}, {"id": -1}):
        with pytest.raises(ValueError):
            avatars.app_id_lookup(Gh(body))("sample-bot")


def test_the_placeholder_is_written_when_missing_and_never_overwritten(data):
    run(data, lambda url: ("image/png", PNG))
    placeholder = data / "avatars" / "placeholder.png"
    assert placeholder.read_bytes() == avatars.placeholder_png()
    placeholder.write_bytes(b"mine")
    run(data, lambda url: ("image/png", PNG))
    assert placeholder.read_bytes() == b"mine"


def test_the_placeholder_is_written_even_when_there_is_nobody_to_download(tmp_path):
    root = tmp_path / "data"
    root.mkdir()
    (root / "config.yml").write_text("org: sample-org\nrepos: [sample-api]\n")
    assert download_avatars(root, load_config(root / "config.yml"), fetch=no_app, app_id=no_app, log=lambda s: None) == []
    assert (root / "avatars" / "placeholder.png").is_file()


def test_the_placeholder_is_a_deterministic_128px_png():
    import struct
    import zlib
    body = avatars.placeholder_png()
    assert body == avatars.placeholder_png()
    assert body.startswith(b"\x89PNG\r\n\x1a\n") and len(body) < 20_000
    width, height, depth, colour = struct.unpack(">IIBB", body[16:26])
    assert (width, height, depth, colour) == (128, 128, 8, 6)          # 8-bit RGBA
    chunks, at = {}, 8
    while at < len(body):
        length, kind = struct.unpack(">I4s", body[at:at + 8])
        chunks.setdefault(kind, b"")
        chunks[kind] += body[at + 8:at + 8 + length]
        assert zlib.crc32(kind + body[at + 8:at + 8 + length]) == struct.unpack(">I", body[at + 8 + length:at + 12 + length])[0]
        at += 12 + length
    pixels = zlib.decompress(chunks[b"IDAT"])
    assert len(pixels) == 128 * (1 + 128 * 4)
    row = lambda y: pixels[y * 513 + 1:(y + 1) * 513]
    corner, centre = row(0)[0:4], row(64)[64 * 4:64 * 4 + 4]
    assert corner[3] == 0                                              # transparent outside the circle
    assert centre[3] == 255 and centre[0] == centre[1] == centre[2]    # opaque neutral grey inside


def test_co_author_logins_are_downloaded_too(data):
    folder = data / "raw" / "sample-api"
    (folder / "commits.jsonl").write_text(json.dumps({"sha": "c", "author_login": "Old-Ada", "co_authors": [
        {"login": "claude", "name": "Claude", "email": "c@example.com"},
        {"login": "Copilot[bot]", "name": "Copilot", "email": "copilot@example.com"},
        {"login": "old-ada", "name": "Ada", "email": "ada@example.com"},           # alias: same person as the author
        {"login": None, "name": "Deployment Script", "email": "deploy@example.com"}]}) + "\n"
        + json.dumps({"sha": "d", "author_login": "ken-t", "co_authors": "malformed"}) + "\n")
    failed, urls = run(data, lambda url: ("image/png", PNG))
    assert "https://github.com/claude.png?size=200" in urls and "https://github.com/Copilot.png?size=200" in urls
    assert sum("ada-dev" in u for u in urls) == 1
    assert {"claude.png", "copilot_bot.png", "ada-dev.png"} <= set(pngs(data))
    assert avatars.missing_avatars(data, load_config(data / "config.yml")) == ["bad/login"]
