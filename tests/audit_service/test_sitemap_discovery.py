import gzip
import xml.etree.ElementTree as ET
from types import SimpleNamespace

import pytest
import requests

from app.audit_service.audit import sitemap_discovery as sd
from app.audit_service.audit.sitemap_discovery import (
    SitemapDiscoveryResult,
    _build_base_url,
    _dedupe_preserve_order,
    _discover_start_sitemaps,
    _extract_locs,
    _extract_sitemaps_from_robots,
    _fetch_text,
    _is_gzipped_url,
    _parse_xml,
    _root_type,
    discover_urls_from_sitemaps,
)

NS = 'xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"'


def urlset(*urls, ns=True):
    body = "".join(f"<url><loc>{u}</loc></url>" for u in urls)
    return f'<?xml version="1.0"?><urlset {NS if ns else ""}>{body}</urlset>'


def index(*sitemaps):
    body = "".join(f"<sitemap><loc>{s}</loc></sitemap>" for s in sitemaps)
    return f'<?xml version="1.0"?><sitemapindex {NS}>{body}</sitemapindex>'


class FakeResponse:
    def __init__(self, status=200, content=b"", encoding=None):
        self.status_code = status
        self.content = content
        self.encoding = encoding

    @property
    def text(self):
        return self.content.decode(self.encoding or "utf-8", errors="replace")

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} error")


@pytest.fixture
def web(monkeypatch):
    """A fake internet. web.pages maps url -> text, bytes, an exception to raise or a status code.

    Anything not listed is a 404. Requests are recorded in web.requests, sleeps in web.sleeps
    """
    state = SimpleNamespace(pages={}, requests=[], sleeps=[])

    def get(url, headers=None, timeout=None):
        state.requests.append(SimpleNamespace(url=url, headers=headers, timeout=timeout))
        page = state.pages.get(url, 404)
        if isinstance(page, BaseException):
            raise page
        if isinstance(page, int):
            return FakeResponse(status=page)
        if isinstance(page, str):
            page = page.encode("utf-8")
        return FakeResponse(content=page)

    monkeypatch.setattr(sd, "requests", SimpleNamespace(get=get))
    monkeypatch.setattr(sd, "time", SimpleNamespace(sleep=state.sleeps.append))
    state.fetched = lambda: [r.url for r in state.requests]
    return state


# helpers

@pytest.mark.parametrize(
    "value, expected",
    [
        ("example.com", "https://example.com"),
        ("https://example.com", "https://example.com"),
        ("http://example.com/some/path?x=1", "http://example.com"),
        ("  https://example.com/  ", "https://example.com"),
        ("sub.example.com:8080", "https://sub.example.com:8080"),
    ],
)
def test_build_base_url(value, expected):
    assert _build_base_url(value) == expected


@pytest.mark.parametrize("value", ["", "   ", None, "https://"])
def test_build_base_url_rejects_empty_or_invalid(value):
    with pytest.raises(ValueError):
        _build_base_url(value)


@pytest.mark.parametrize("url, expected", [("a/sitemap.xml.gz", True), ("A/SITEMAP.XML.GZ", True), ("a/sitemap.xml", False)])
def test_is_gzipped_url(url, expected):
    assert _is_gzipped_url(url) is expected


def test_parse_xml_ignores_leading_whitespace_and_rejects_bad_xml():
    assert _parse_xml("\n  \t" + urlset("https://a.com")).tag.endswith("urlset")

    with pytest.raises(ET.ParseError):
        _parse_xml("<urlset><url></urlset>")


@pytest.mark.parametrize(
    "xml, expected",
    [
        (urlset("https://a.com"), "urlset"),
        (urlset("https://a.com", ns=False), "urlset"),
        (index("https://a.com/s.xml"), "index"),
        ("<html><body/></html>", "unknown"),
        ("<rss/>", "unknown"),
    ],
)
def test_root_type(xml, expected):
    assert _root_type(ET.fromstring(xml)) == expected


def test_extract_locs_strips_whitespace_and_skips_blanks():
    root = ET.fromstring(
        f"<urlset {NS}><url><loc>  https://a.com/1 </loc></url><url><loc>   </loc></url><url><loc/></url>"
        "<url><loc>https://a.com/2</loc></url></urlset>"
    )

    assert _extract_locs(root) == ["https://a.com/1", "https://a.com/2"]


def test_extract_locs_reads_index_sitemaps_too():
    assert _extract_locs(ET.fromstring(index("https://a.com/1.xml", "https://a.com/2.xml"))) == [
        "https://a.com/1.xml",
        "https://a.com/2.xml",
    ]


def test_dedupe_preserves_first_occurrence_order():
    assert _dedupe_preserve_order(["b", "a", "b", "c", "a"]) == ["b", "a", "c"]
    assert _dedupe_preserve_order([]) == []


def test_extract_sitemaps_from_robots():
    robots = """
    User-agent: *
    Disallow: /private
    Sitemap: https://a.com/sitemap.xml
    sitemap:https://a.com/other.xml   # trailing comment
    # Sitemap: https://a.com/commented.xml
    SITEMAP: https://a.com/sitemap.xml
    Sitemap:
    """

    assert _extract_sitemaps_from_robots(robots) == ["https://a.com/sitemap.xml", "https://a.com/other.xml"]


def test_extract_sitemaps_from_robots_without_any():
    assert _extract_sitemaps_from_robots("User-agent: *\nDisallow:") == []
    assert _extract_sitemaps_from_robots("") == []


# _fetch_text

def test_fetch_text_returns_the_body_with_headers_and_timeout(web):
    web.pages["https://a.com/robots.txt"] = "User-agent: *"

    assert _fetch_text("https://a.com/robots.txt", timeout=7) == "User-agent: *"

    request = web.requests[0]
    assert request.timeout == 7
    assert "User-Agent" in request.headers


def test_fetch_text_decompresses_gzip(web):
    web.pages["https://a.com/s.xml.gz"] = gzip.compress("<urlset>é</urlset>".encode("utf-8"))

    assert _fetch_text("https://a.com/s.xml.gz") == "<urlset>é</urlset>"


def test_fetch_text_retries_with_exponential_backoff_then_succeeds(web, monkeypatch):
    attempts = []

    def flaky_get(url, headers=None, timeout=None):
        attempts.append(url)
        if len(attempts) < 3:
            raise requests.ConnectionError("reset")
        return FakeResponse(content=b"ok")

    monkeypatch.setattr(sd, "requests", SimpleNamespace(get=flaky_get))

    assert _fetch_text("https://a.com/x", retries=2, backoff_s=0.5) == "ok"
    assert len(attempts) == 3
    assert web.sleeps == [0.5, 1.0]


def test_fetch_text_raises_after_exhausting_retries(web):
    web.pages["https://a.com/x"] = requests.ConnectionError("down")

    with pytest.raises(requests.ConnectionError):
        _fetch_text("https://a.com/x", retries=2)

    assert len(web.requests) == 3
    assert len(web.sleeps) == 2


def test_fetch_text_raises_on_http_errors(web):
    with pytest.raises(requests.HTTPError):
        _fetch_text("https://a.com/missing", retries=0)

    assert web.sleeps == []


# _discover_start_sitemaps

def discover_start(web, domain="https://a.com"):
    logs, errors = [], []
    found = _discover_start_sitemaps(domain, timeout=5, retries=0, logs=logs, errors=errors)
    return found, logs, errors


def test_start_sitemaps_come_from_robots_txt_first(web):
    web.pages["https://a.com/robots.txt"] = "Sitemap: https://a.com/custom-sitemap.xml"

    found, logs, errors = discover_start(web)

    assert found == ["https://a.com/custom-sitemap.xml"]
    assert errors == []
    assert any("robots.txt" in line for line in logs)
    assert web.fetched() == ["https://a.com/robots.txt"]


def test_start_sitemaps_fall_back_to_common_paths_when_robots_lists_none(web):
    web.pages["https://a.com/robots.txt"] = "User-agent: *"
    web.pages["https://a.com/sitemap.xml"] = urlset("https://a.com/")

    found, _, errors = discover_start(web)

    assert found == ["https://a.com/sitemap.xml"]
    assert errors == []


def test_a_missing_robots_txt_is_only_a_warning(web):
    web.pages["https://a.com/sitemap.xml"] = urlset("https://a.com/")

    found, _, errors = discover_start(web)

    assert found == ["https://a.com/sitemap.xml"]
    assert [(e["level"], e["stage"]) for e in errors] == [("warning", "robots")]


def test_sitemap_index_xml_is_tried_when_sitemap_xml_is_missing_or_not_a_sitemap(web):
    web.pages["https://a.com/sitemap.xml"] = "<html><body>Not found page</body></html>"
    web.pages["https://a.com/sitemap_index.xml"] = index("https://a.com/p.xml")

    found, _, errors = discover_start(web)

    assert found == ["https://a.com/sitemap_index.xml"]
    # the missing robots.txt is the only problem, a page that is not a sitemap is skipped quietly
    assert [e["stage"] for e in errors] == ["robots"]


def test_no_sitemap_anywhere_is_an_error(web):
    found, _, errors = discover_start(web)

    assert found == []
    assert errors[-1] == {
        "level": "error",
        "sitemap": "https://a.com",
        "stage": "discover",
        "message": "No sitemap found via robots.txt or common sitemap paths",
    }


def test_the_domain_is_normalised_before_probing(web):
    web.pages["https://a.com/robots.txt"] = "Sitemap: https://a.com/s.xml"

    found, _, _ = discover_start(web, domain="a.com/some/page")

    assert found == ["https://a.com/s.xml"]


# discover_urls_from_sitemaps

def discover(web, domain="https://a.com", **kwargs):
    return discover_urls_from_sitemaps(domain, retries=0, **kwargs)


def test_discovers_urls_through_robots_and_a_plain_sitemap(web):
    web.pages["https://a.com/robots.txt"] = "Sitemap: https://a.com/sitemap.xml"
    web.pages["https://a.com/sitemap.xml"] = urlset("https://a.com/", "https://a.com/about")

    result = discover(web)

    assert isinstance(result, SitemapDiscoveryResult)
    assert result.urls == ["https://a.com/", "https://a.com/about"]
    assert result.sitemaps == ["https://a.com/sitemap.xml"]
    assert result.sitemap_indexes == []
    assert result.per_sitemap == [
        {"sitemap": "https://a.com/sitemap.xml", "count": 2, "urls": ["https://a.com/", "https://a.com/about"]}
    ]
    assert result.errors == []


@pytest.mark.parametrize("path", ["sitemap.xml", "deep/sitemap.xml.gz"])
def test_a_direct_sitemap_url_skips_discovery(web, path):
    content = urlset("https://a.com/1")
    web.pages[f"https://a.com/{path}"] = gzip.compress(content.encode()) if path.endswith(".gz") else content

    result = discover(web, domain=f"https://a.com/{path}")

    assert result.urls == ["https://a.com/1"]
    assert "https://a.com/robots.txt" not in web.fetched()


def test_sitemap_indexes_are_followed_recursively(web):
    web.pages["https://a.com/sitemap.xml"] = index("https://a.com/pages.xml", "https://a.com/more-index.xml")
    web.pages["https://a.com/pages.xml"] = urlset("https://a.com/p1", "https://a.com/p2")
    web.pages["https://a.com/more-index.xml"] = index("https://a.com/posts.xml")
    web.pages["https://a.com/posts.xml"] = urlset("https://a.com/post1")

    result = discover(web, domain="https://a.com/sitemap.xml")

    assert sorted(result.urls) == ["https://a.com/p1", "https://a.com/p2", "https://a.com/post1"]
    assert sorted(result.sitemap_indexes) == ["https://a.com/more-index.xml", "https://a.com/sitemap.xml"]
    assert sorted(result.sitemaps) == ["https://a.com/pages.xml", "https://a.com/posts.xml"]


@pytest.mark.xfail(
    strict=True,
    reason="child sitemaps are popped from the end of the to-visit list, so URLs from the sitemaps listed last in "
    "an index come first and --max-urls keeps those instead of the first listed",
)
def test_urls_follow_the_order_the_sitemaps_are_listed_in(web):
    web.pages["https://a.com/sitemap.xml"] = index("https://a.com/first.xml", "https://a.com/second.xml")
    web.pages["https://a.com/first.xml"] = urlset("https://a.com/home")
    web.pages["https://a.com/second.xml"] = urlset("https://a.com/blog")

    result = discover(web, domain="https://a.com/sitemap.xml")

    assert result.urls == ["https://a.com/home", "https://a.com/blog"]


def test_urls_are_deduplicated_across_sitemaps(web):
    web.pages["https://a.com/sitemap.xml"] = index("https://a.com/1.xml", "https://a.com/2.xml")
    web.pages["https://a.com/1.xml"] = urlset("https://a.com/x", "https://a.com/x", "https://a.com/y")
    web.pages["https://a.com/2.xml"] = urlset("https://a.com/y", "https://a.com/z")

    result = discover(web, domain="https://a.com/sitemap.xml")

    assert sorted(result.urls) == ["https://a.com/x", "https://a.com/y", "https://a.com/z"]
    assert sorted(len(s["urls"]) for s in result.per_sitemap) == [2, 2]


def test_a_sitemap_that_lists_itself_does_not_loop(web):
    web.pages["https://a.com/sitemap.xml"] = index("https://a.com/sitemap.xml", "https://a.com/p.xml")
    web.pages["https://a.com/p.xml"] = urlset("https://a.com/1")

    result = discover(web, domain="https://a.com/sitemap.xml")

    assert result.urls == ["https://a.com/1"]


def test_max_sitemaps_caps_how_many_are_visited(web):
    children = [f"https://a.com/{i}.xml" for i in range(10)]
    web.pages["https://a.com/sitemap.xml"] = index(*children)
    for i, child in enumerate(children):
        web.pages[child] = urlset(f"https://a.com/page{i}")

    result = discover(web, domain="https://a.com/sitemap.xml", max_sitemaps=4)

    assert len(result.sitemaps) == 3
    assert len(result.urls) == 3


def test_a_failing_child_sitemap_is_recorded_and_the_rest_still_used(web):
    web.pages["https://a.com/sitemap.xml"] = index("https://a.com/good.xml", "https://a.com/bad.xml")
    web.pages["https://a.com/good.xml"] = urlset("https://a.com/ok")

    result = discover(web, domain="https://a.com/sitemap.xml")

    assert result.urls == ["https://a.com/ok"]
    assert [(e["sitemap"], e["stage"], e["level"]) for e in result.errors] == [("https://a.com/bad.xml", "fetch", "error")]


def test_invalid_xml_is_recorded_as_a_parse_error(web):
    web.pages["https://a.com/sitemap.xml"] = "<urlset><url>"

    result = discover(web, domain="https://a.com/sitemap.xml")

    assert result.urls == []
    assert result.errors == [{"level": "error", "sitemap": "https://a.com/sitemap.xml", "stage": "parse", "message": "Invalid XML"}]


def test_an_unknown_root_element_is_a_warning(web):
    web.pages["https://a.com/sitemap.xml"] = "<feed><entry/></feed>"

    result = discover(web, domain="https://a.com/sitemap.xml")

    assert result.urls == []
    assert [(e["level"], e["stage"]) for e in result.errors] == [("warning", "classify")]
    assert any("unknown" in line.lower() for line in result.logs)


def test_nothing_found_returns_an_empty_result_with_the_errors(web):
    result = discover(web)

    assert (result.urls, result.sitemaps, result.sitemap_indexes, result.per_sitemap) == ([], [], [], [])
    assert result.errors[-1]["message"].startswith("No sitemap found")


@pytest.mark.xfail(
    strict=True,
    reason="_extract_locs only matches namespaced <loc> elements, so a sitemap written without the sitemaps.org "
    "xmlns is detected as a urlset but yields no URLs",
)
def test_a_sitemap_without_a_namespace_still_yields_its_urls(web):
    web.pages["https://a.com/sitemap.xml"] = urlset("https://a.com/1", "https://a.com/2", ns=False)

    result = discover(web, domain="https://a.com/sitemap.xml")

    assert result.urls == ["https://a.com/1", "https://a.com/2"]
