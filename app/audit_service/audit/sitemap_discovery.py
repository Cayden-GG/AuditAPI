import gzip
import io
import xml.etree.ElementTree as ET
import requests
import time
from urllib.parse import urlparse

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple, Union

# ---------- Constants ----------

SITEMAP_NS = "http://www.sitemaps.org/schemas/sitemap/0.9"
NS = {"sm": SITEMAP_NS}

DEFAULT_HEADERS = {
    "User-Agent": "local-lighthouse-audit/1.0 (+https://example.local)"
}

# ---------- Helper utilities ----------

def _build_base_url(domain_url: str) -> str:
    raw = (domain_url or "").strip()
    if not raw:
        raise ValueError("Domain URL is required")
    if not raw.startswith(("http://", "https://")):
        raw = f"https://{raw}"
    parsed = urlparse(raw)
    netloc = parsed.netloc or parsed.path
    if not netloc:
        raise ValueError(f"Invalid domain URL: {domain_url}")
    return f"{parsed.scheme}://{netloc}"


def _is_gzipped_url(url: str) -> bool:
    return url.lower().endswith(".gz")


def _fetch_text(url: str, timeout: int = 20, retries: int = 2, backoff_s: float = 0.7) -> str:
    """
    Fetches a URL and returns text content.
    Supports .xml and .xml.gz content. Retries on transient network failures.
    Raises requests exceptions for unrecoverable HTTP/network errors.
    """
    last_exc: Optional[Exception] = None

    for attempt in range(retries + 1):
        try:
            resp = requests.get(url, headers=DEFAULT_HEADERS, timeout=timeout)
            resp.raise_for_status()

            # if xml is zipped 
            if _is_gzipped_url(url):
                with gzip.GzipFile(fileobj=io.BytesIO(resp.content)) as gz:
                    return gz.read().decode("utf-8", errors="replace")

            # Otherwise treat as text/XML.
            resp.encoding = resp.encoding or "utf-8"
            return resp.text

        except Exception as e:
            last_exc = e
            if attempt < retries:
                time.sleep(backoff_s * (2 ** attempt))
                continue
            raise

    raise RuntimeError(f"Failed fetching {url}") from last_exc


def _parse_xml(xml_text: str) -> ET.Element:
    """
    Parse XML text into an ElementTree root element.
    Raises ET.ParseError if malformed.
    """
    # Strip leading whitespace 
    xml_text = xml_text.lstrip()
    return ET.fromstring(xml_text)


def _root_type(root: ET.Element) -> str:
    """
    Returns:
      - "index" for <sitemapindex>
      - "urlset" for <urlset>
      - "unknown" otherwise
    Works whether tags are namespaced or not by checking suffix.
    """
    tag = root.tag
    if tag.endswith("sitemapindex"):
        return "index"
    if tag.endswith("urlset"):
        return "urlset"
    return "unknown"


def _extract_locs(root: ET.Element) -> List[str]:
    """
    Extract all <loc> values under the sitemap namespace.
    In both sitemapindex and urlset formats, <loc> is the main payload.
    """
    # Namespace-aware: sm:loc
    loc_elems = root.findall(".//sm:loc", NS)
    return [el.text.strip() for el in loc_elems if el.text and el.text.strip()]


def _dedupe_preserve_order(items: Iterable[str]) -> List[str]:
    seen: Set[str] = set()
    out: List[str] = []
    for x in items:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def _extract_sitemaps_from_robots(robots_text: str) -> List[str]:
    sitemaps: List[str] = []
    for line in robots_text.splitlines():
        raw = line.split("#", 1)[0].strip()
        if not raw:
            continue
        if raw.lower().startswith("sitemap:"):
            url = raw.split(":", 1)[1].strip()
            if url:
                sitemaps.append(url)
    return _dedupe_preserve_order(sitemaps)


def _discover_start_sitemaps(
    domain_url: str,
    *,
    timeout: int,
    retries: int,
    logs: List[str],
    errors: List[Dict[str, str]],
) -> List[str]:
    base_url = _build_base_url(domain_url)
    robots_url = f"{base_url}/robots.txt"

    try:
        robots_text = _fetch_text(robots_url, timeout=timeout, retries=retries)
        logs.append(f"Fetched robots.txt: {robots_url}")
        from_robots = _extract_sitemaps_from_robots(robots_text)
        if from_robots:
            logs.append(f"Discovered {len(from_robots)} sitemap(s) from robots.txt")
            return from_robots
    except Exception as e:
        errors.append({
            "level": "warning",
            "sitemap": robots_url,
            "stage": "robots",
            "message": str(e),
        })

    for candidate in (f"{base_url}/sitemap.xml", f"{base_url}/sitemap_index.xml"):
        try:
            xml_text = _fetch_text(candidate, timeout=timeout, retries=retries)
            root = _parse_xml(xml_text)
            if _root_type(root) in ("index", "urlset"):
                logs.append(f"Discovered sitemap: {candidate}")
                return [candidate]
        except Exception as e:
            errors.append({
                "level": "warning",
                "sitemap": candidate,
                "stage": "discover",
                "message": str(e),
            })

    errors.append({
        "level": "error",
        "sitemap": base_url,
        "stage": "discover",
        "message": "No sitemap found via robots.txt or common sitemap paths",
    })
    return []

# ---------- Sitemap discovery ----------

@dataclass
class SitemapDiscoveryResult:
    sitemap_indexes: List[str]
    sitemaps: List[str]           
    urls: List[str]               
    per_sitemap: List[Dict[str, Any]]   
    errors: List[Dict[str, str]]
    logs: List[str]

def discover_urls_from_sitemaps(
    domain_url: str,
    *,
    timeout: int = 20,
    retries: int = 2,
    max_sitemaps: int = 500,
) -> SitemapDiscoveryResult:
    """
    Given a domain URL, discover a sitemap via robots.txt or common locations,
    recursively resolves sitemap indexes and returns a deduped URL list.
    """
    errors: List[Dict[str, str]] = []
    logs: List[str] = []

    if domain_url.lower().endswith((".xml", ".xml.gz")):
        start_sitemaps = [domain_url]
    else:
        start_sitemaps = _discover_start_sitemaps(
            domain_url, timeout=timeout, retries=retries, logs=logs, errors=errors
        )
        if not start_sitemaps:
            return SitemapDiscoveryResult(
                sitemap_indexes=[],
                sitemaps=[],
                urls=[],
                per_sitemap=[],
                errors=errors,
                logs=logs,
            )

    to_visit: List[str] = list(start_sitemaps)
    visited: Set[str] = set()

    sitemap_indexes: List[str] = []
    urlset_sitemaps: List[str] = []

    # BFS/DFS through sitemap references
    while to_visit:
        if len(visited) >= max_sitemaps:
            break

        sitemap_url = to_visit.pop()
        if sitemap_url in visited:
            continue
        visited.add(sitemap_url)
        
        # fail softly if xml fetch fails
        try: 
            xml_text = _fetch_text(sitemap_url, timeout=timeout, retries=retries)
            logs.append(f"Fetched sitemap: {sitemap_url}")
        except Exception as e:
            errors.append({
                "level": "error",
                "sitemap": sitemap_url,
                "stage": "fetch",
                "message": str(e),
            })
            continue

        # fail softly if xml parse fails
        try:
            root = _parse_xml(xml_text)
        except ET.ParseError:
            errors.append({
                "level": "error",
                "sitemap": sitemap_url,
                "stage": "parse",
                "message": "Invalid XML",
            })
            continue

        stype = _root_type(root)
        logs.append(f"Detected sitemap type '{stype}' for {sitemap_url}")

        locs = _extract_locs(root)

        if stype == "index":
            sitemap_indexes.append(sitemap_url)
            # locs are other sitemaps (indexes or urlsets)
            to_visit.extend(locs)
        elif stype == "urlset":
            urlset_sitemaps.append(sitemap_url)
        else:
            errors.append({
                "level": "warning",
                "sitemap": sitemap_url,
                "stage": "classify",
                "message": "Unknown sitemap root element",
            })
            logs.append(f"Skipped unknown sitemap format: {sitemap_url}")
        continue

    # Fetch each urlset sitemap and extract URLs
    per_sitemap: List[Dict[str, Any]] = []
    all_urls: List[str] = []

    for sm_url in _dedupe_preserve_order(urlset_sitemaps):
        try:
            xml_text = _fetch_text(sm_url, timeout=timeout, retries=retries)
            logs.append(f"Fetched URL sitemap: {sm_url}")
            root = _parse_xml(xml_text)
        except Exception as e:
            errors.append({
                "level": "error",
                "sitemap": sm_url,
                "stage": "fetch/parse",
                "message": str(e),
            })
            continue

        # Defensive: ensure it is urlset
        if _root_type(root) != "urlset":
            continue

        urls = _extract_locs(root)
        urls = _dedupe_preserve_order(urls)

        per_sitemap.append({
            "sitemap": sm_url,
            "count": len(urls),
            "urls": urls,
        })
        all_urls.extend(urls)

    all_urls = _dedupe_preserve_order(all_urls)

    return SitemapDiscoveryResult(
        sitemap_indexes=_dedupe_preserve_order(sitemap_indexes),
        sitemaps=_dedupe_preserve_order(urlset_sitemaps),
        urls=all_urls,
        per_sitemap=per_sitemap,
        errors=errors,
        logs=logs,
    )
