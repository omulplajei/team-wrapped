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


def run(data, fetch):
    urls = []

    def recording(url):
        urls.append(url)
        return fetch(url)
    failed = download_avatars(data, load_config(data / "config.yml"), fetch=recording, log=lambda s: None)
    return failed, urls


def test_downloads_each_linked_login_once_with_the_aggregator_file_names(data):
    (data / "avatars").mkdir()
    (data / "avatars" / "ken-t.png").write_bytes(b"old")            # already there: kept, not fetched
    failed, urls = run(data, lambda url: ("image/png", PNG))
    assert sorted(urls) == ["https://github.com/Grace-Codes.png?size=200", "https://github.com/ada-dev.png?size=200",
                            "https://github.com/renovate.png?size=200"]
    names = sorted(p.name for p in (data / "avatars").iterdir())
    assert names == ["ada-dev.png", "grace-codes.png", "ken-t.png", "renovate_bot.png"]
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
    assert not (data / "avatars").exists() or not any((data / "avatars").glob("*.png"))


def test_the_default_fetcher_refuses_other_hosts():
    with pytest.raises(ValueError):
        avatars.fetch_url("http://github.com/x.png")
    with pytest.raises(ValueError):
        avatars.fetch_url("https://example.com/x.png")
    handler = avatars._GitHubOnly()
    with pytest.raises(OSError):
        handler.redirect_request(None, None, 302, "Found", {}, "https://example.com/evil.png")
