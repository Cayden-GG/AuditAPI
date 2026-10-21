from typing import Any, Dict, Iterable, List, Optional, Set, Tuple, Union
import json
import os
import shutil
import subprocess
import time
from datetime import datetime, timezone
from dataclasses import asdict

from .audit_config import LighthouseDesktopRunOptions, LighthouseMobileRunOptions
from ..writers.write_to_json import write_json_to_file

VALID_LIGHTHOUSE_CATEGORIES = {"performance", "seo", "accessibility", "best-practices", "pwa"}

# --------------- helpers ---------------

def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_lighthouse_version() -> Optional[str]:
    """
    Get Lighthouse version from CLI.
    """
    try:
        r = subprocess.run(
            ["lighthouse", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()

    except Exception:
        pass


def resolve_chrome_path(configured_path: Optional[str] = None) -> str:
    """
    Resolve a usable Chrome/Chromium binary path to reduce "no Chrome/Chromium" errors.
    """
    candidates = []
    env_path = os.getenv("CHROME_PATH")

    if env_path:
        candidates.append(env_path)

    if configured_path:
        candidates.append(configured_path)
    
    for name in ("google-chrome-stable", "google-chrome", "chromium", "chromium-browser"):
        found = shutil.which(name)
        if found:
            candidates.append(found)

    for candidate in candidates:
        if candidate and os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate

    raise RuntimeError(
        "No Chrome/Chromium installation found. Set the CHROME_PATH environment "
        "variable to a valid Chrome/Chromium binary, or install Chrome/Chromium "
        f"(checked: {', '.join(c for c in candidates if c) or 'no candidates'})."
    )


def validate_categories(only_categories: Optional[str]) -> None:
    """
    Validate user passed categories, raises RuntimeError if invalid
    
    @Args:
        only_categories (Optional[str]) -- string list of lighthouse audit categories 
    """
    if not only_categories:
        return

    requested = {c.strip() for c in only_categories.split(",") if c.strip()}
    unknown = requested - VALID_LIGHTHOUSE_CATEGORIES
    
    if unknown:
        raise RuntimeError(
            f"Unknown Lighthouse categor{'y' if len(unknown) == 1 else 'ies'}: "
            f"{', '.join(sorted(unknown))}. Valid categories are: "
            f"{', '.join(sorted(VALID_LIGHTHOUSE_CATEGORIES))}."
        )


def _classify_error(exc: Exception) -> Tuple[str, str]:
    """
    Map exceptions to FRS-style error_type and readable message.

    @Args: 
        exc (Exception) -- lighthouse exception
    
    @Returns:
        error tuple with error code and message (Tuple[str, str])
    """
    msg = str(exc)

    if isinstance(exc, subprocess.TimeoutExpired):
        return "timeout", "Lighthouse execution exceeded timeout."

    # raises RuntimeError with specific prefixes; classify by message.
    lowered = msg.lower()
    if "no json" in lowered or "produced no json" in lowered:
        return "no_json_output", "Lighthouse produced no JSON output."
    
    if "invalid json" in lowered:
        return "invalid_json", "Lighthouse returned invalid JSON."
    
    if "lighthouse failed" in lowered or "return code" in lowered:
        return "lighthouse_failed", "Lighthouse process failed."
    
    return "unknown", msg


# ---------- Lighthouse runner ----------

def run_lighthouse_json(
    url: str,
    platform: str,
    only_categories: Optional[str] = None,
    chrome_path: Optional[str] = None,
) -> Tuple[Any, float, list]:
    """
    Runs Lighthouse CLI and returns the parsed JSON report.

    @Args:
        url (str) -- client url to audit on
        platform (str) -- platform to run audit on: mobile | desktop
        only_categories (Optional[str]) -- categories to run audit on: seo | performance | accessibility
        chrome_path (optional[str]) -- path to chrome on sys to reduce chrome errors

    @Returns:
        audit data (Dict[str, Any])
    """
    cmd = []

    if platform == "desktop":
        opts = LighthouseDesktopRunOptions()
        if only_categories:
            opts.only_categories = only_categories
        cmd = [
            "lighthouse",
            url,
            f"--only-categories={opts.only_categories}",
            f"--preset={opts.preset}",
            "--mode=navigation",
            "--output=json",
            "--output-path=stdout",
            "--quiet",
            "--headless",
            "--no-sandbox",
            "--disable-gpu",
            "--disable-dev-shm-usage",
            f"--chrome-flags={opts.chrome_flags}",
            f"--max-wait-for-load={opts.max_wait_for_load_ms}",
        ]

    else:
        opts = LighthouseMobileRunOptions()
        if only_categories:
            opts.only_categories = only_categories
        cmd = [
            "lighthouse",
            url,
            "--headless",
            "--no-sandbox",
            "--disable-gpu",
            "--disable-dev-shm-usage",
            f"--only-categories={opts.only_categories}",
            f"--throttling-method={opts.throttling_method}",
            f"--form-factor={opts.form_factor}",
            "--mode=navigation",
            "--output=json",
            "--output-path=stdout",
            "--quiet",
            f"--chrome-flags={opts.chrome_flags}",
            f"--max-wait-for-load={opts.max_wait_for_load_ms}",
        ]

    env = os.environ.copy()
    if chrome_path:
        env["CHROME_PATH"] = chrome_path

    start = time.time()

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=opts.timeout_s, env=env)

    except subprocess.TimeoutExpired as e:
        raise RuntimeError(f"Lighthouse timed out for {url}") from e
    
    finally: 
        duration = time.time() - start

    if result.returncode != 0:
        raise RuntimeError(
            f"Lighthouse failed for {url}\n"
            f"Return code: {result.returncode}\n"
            f"STDERR:\n{result.stderr[:4000]}\n"
            f"STDOUT:\n{result.stdout[:1000]}"
        )

    if not result.stdout.strip():
        raise RuntimeError(
            f"Lighthouse produced no JSON for {url}.\n"
            f"STDERR:\n{result.stderr[:4000]}"
        )

    try:
        report = json.loads(result.stdout)

    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"Invalid JSON from Lighthouse for {url}\n"
            f"STDOUT head:\n{result.stdout[:500]}\n"
            f"STDERR head:\n{result.stderr[:2000]}"
        ) from e

    return report, duration, cmd


def audit_urls_with_lighthouse(
    urls: List[str],
    *,
    only_categories: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Runs Lighthouse for each URL for each specified category

    @Args:
        urls (list[str]) -- list of urls to audit 
        only_categories (Optional[str]) -- string list of categories to run audit on 
    
    @Return:
        return audit data with meta config 
    """

    validate_categories(only_categories)

    lighthouse_version = _get_lighthouse_version()
    run_at = _utc_now_iso()
    desktop_opts = LighthouseDesktopRunOptions()
    mobile_opts = LighthouseMobileRunOptions()

    if only_categories:
        desktop_opts.only_categories = only_categories
        mobile_opts.only_categories = only_categories

    chrome_path = resolve_chrome_path(desktop_opts.chrome_path)
    desktop_opts.chrome_path = chrome_path
    mobile_opts.chrome_path = chrome_path

    results: Dict[str, Any] = {}
    logs: List[str] = []

    for url in urls:
        url_start = time.time()
        logs.append(f"Starting Lighthouse for {url}")

        try:
            desktop_report, duration, cmd = run_lighthouse_json(
                url, "desktop", only_categories=only_categories, chrome_path=chrome_path
            )
            mobile_report, duration, cmd = run_lighthouse_json(
                url, "mobile", only_categories=only_categories, chrome_path=chrome_path
            )

            desktop_categories = desktop_report.get("categories", {}) or {}
            mobile_categories = mobile_report.get("categories", {}) or {}
            final_url = desktop_report.get("finalUrl") or desktop_report.get("requestedUrl") or url

            results[url] = {
                "status": "success",
                "mobile": {
                    "audits": mobile_report.get("audits", {}) or {},
                    "categories": mobile_categories,
                },
                "desktop": {
                    "audits": desktop_report.get("audits", {}) or {},
                    "categories": desktop_categories,
                },
                "final_url": final_url,
                "diagnostics": {
                    "fetch_time": desktop_report.get("fetchTime"),
                    "timing_s": round(duration, 3),
                    "command": cmd,
                }
            }

            logs.append(f"Completed Lighthouse for {url} in {round(duration, 2)}s")

        except Exception as e:
            error_type, message = _classify_error(e)

            stderr_head = ""
            if isinstance(e, RuntimeError):
                stderr_head = str(e)[:2000]

            results[url] = {
                "status": "error",
                "error_type": error_type,
                "message": message,
                "stderr_head": stderr_head,
                "diagnostics": {
                    "timing_s": round(time.time() - url_start, 3),
                },
            }

            logs.append(f"Failed Lighthouse for {url}: {error_type} - {message}")
    # return report
    normalized_categories = (only_categories or "performance,seo").replace(" ", "")
    return {
        "meta": {
            "tool": "lighthouse-automation",
            "run_at": run_at,
            "lighthouse_version": lighthouse_version,
            "mode": "navigation",
            "categories": normalized_categories,
            "devices": ["mobile", "desktop"],
            "config": {
                "only_categories": normalized_categories,
                "mobile": asdict(mobile_opts),
                "desktop": asdict(desktop_opts),
            },
            "tested_urls": urls,
        },
        "lighthouse_data": results,
        "logs": logs,
    }
