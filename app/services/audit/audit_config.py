from dataclasses import dataclass
from typing import List, Optional

# Lighthouse audit IDs you want to keep (these match Lighthouse JSON keys)
PERFORMANCE_AUDIT_IDS = [
    "first-contentful-paint",
    "largest-contentful-paint",
    "speed-index",
    "total-blocking-time",
    "mainthread-work-breakdown",
    "diagnostics",
    "network-requests",
    "network-server-latency",
    "metrics",
    "resource-summary",
]

SEO_AUDIT_IDS = [
    "meta-description",
    "document-title",
    "link-text",
    "image-alt",
    "robots-txt",
    "indexing",
    "hreflang",
    "canonical",
    "structured-data",
    "crawlable-anchors",
    "http-status-code",
    "is-crawlable",
    "tap-targets",
    "viewport",
    "plugins",
    "charset",
]

ACCESSIBILITY_AUDIT_IDS = [
    "color-contrast",
    "image-alt",
    "label",
    "link-name",
    "button-name",
    "document-title",
    "html-has-lang",
    "html-lang-valid",
    "meta-viewport",
    "aria-allowed-attr",
    "aria-required-attr",
    "aria-roles",
    "aria-valid-attr",
    "aria-valid-attr-value",
    "aria-hidden-body",
    "tabindex",
    "heading-order",
    "bypass",
]

@dataclass
class LighthouseDesktopRunOptions:
    preset: str = "desktop"  # "desktop" or "mobile"
    timeout_s: int = 240
    chrome_path: str = "/usr/bin/chromium"
    chrome_flags: str = "--headless --no-sandbox --disable-gpu --disable-dev-shm-usage"
    max_wait_for_load_ms: int = 45000
    only_categories: str = "performance"
    audit_ids: Optional[List[str]] = None  # if None, uses DEFAULT_AUDIT_IDS

@dataclass
class LighthouseMobileRunOptions:
    form_factor: str = "mobile"
    throttling_method: str = "simulate"
    timeout_s: int = 240
    chrome_path: str = "/usr/bin/chromium"
    chrome_flags: str = "--headless --no-sandbox --disable-gpu --disable-dev-shm-usage"
    max_wait_for_load_ms: int = 45000
    only_categories: str = "performance"
    audit_ids: Optional[List[str]] = None  # if None, uses DEFAULT_AUDIT_IDS
