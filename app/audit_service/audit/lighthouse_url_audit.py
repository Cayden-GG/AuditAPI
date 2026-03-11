from typing import Any, Dict, Iterable, List, Optional, Set, Tuple, Union
import json
import subprocess
import time
from datetime import datetime, timezone
from dataclasses import asdict

from .audit_config import LighthouseDesktopRunOptions, LighthouseMobileRunOptions
from ..writers.write_to_json import write_json_to_file
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

def _classify_error(exc: Exception) -> Tuple[str, str]:
    """
    Map exceptions to FRS-style error_type and human-readable message.
    """
    msg = str(exc)

    if isinstance(exc, subprocess.TimeoutExpired):
        return "timeout", "Lighthouse execution exceeded timeout."

    # Our code raises RuntimeError with specific prefixes; classify by message.
    lowered = msg.lower()
    if "no json" in lowered or "produced no json" in lowered:
        return "no_json_output", "Lighthouse produced no JSON output."
    if "invalid json" in lowered:
        return "invalid_json", "Lighthouse returned invalid JSON."
    if "lighthouse failed" in lowered or "return code" in lowered:
        return "lighthouse_failed", "Lighthouse process failed."
    return "unknown", msg
    return None


# ---------- Lighthouse runner ----------

def run_lighthouse_json(url: str, platform: str, ) -> Dict[str, Any]:
    """
    Runs Lighthouse CLI and returns the parsed JSON report.
    """
    cmd = []

    if platform == "desktop": 
        opts = LighthouseDesktopRunOptions()
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
            "--disable-dev-shm-usage"
            f"--chrome-path={opts.chrome_path}",
            f"--chrome-flags={opts.chrome_flags}",
            f"--max-wait-for-load={opts.max_wait_for_load_ms}",
        ]

    else: 
        opts = LighthouseMobileRunOptions()
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
            f"--chrome-path={opts.chrome_path}",
            f"--chrome-flags={opts.chrome_flags}",
            f"--max-wait-for-load={opts.max_wait_for_load_ms}",
        ]
        
    start = time.time()

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=opts.timeout_s)
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
) -> Dict[str, Any]:
    """
    Runs Lighthouse for each URL and returns:
      {
        "<url>": { "audits": {...}, "meta": {...} } OR { "error": "...", "stderr": "..." }
      }
    """

    # if "," in only_categories:
    #     categories = [c.strip() for c in only_categories.split(",") if c.strip()]
    # else:
    #     categories = [only_categories.strip()] if only_categories.strip() else []
    #
    # allowed = {"performance", "seo"}
    # normalized = [c for c in categories if c in allowed]
    # if not normalized:
    #     normalized = ["performance"]
    # categories = normalized
    #
    # normalized_only_categories = ",".join(categories)


    lighthouse_version = _get_lighthouse_version()
    run_at = _utc_now_iso()

    results: Dict[str, Any] = {}
    logs: List[str] = []

    for url in urls:
        url_start = time.time()
        logs.append(f"Starting Lighthouse for {url}")

        try:
            desktop_report, duration, cmd = run_lighthouse_json(url, "desktop")
            mobile_report, duration, cmd = run_lighthouse_json(url, "mobile")

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
    return {
        "meta": {
            "tool": "lighthouse-automation",
            "run_at": run_at,
            "lighthouse_version": lighthouse_version,
            "mode": "navigation",
            "categories": "performance, seo",
            "devices": ["mobile", "desktop"],
            "config": {
                "only_categories": "performance, seo",
                "mobile": asdict(LighthouseMobileRunOptions()),
                "desktop": asdict(LighthouseDesktopRunOptions()),
            },
            "tested_urls": urls,
        },
        "lighthouse_data": results,
        "logs": logs,
    }
