"""
Shared helpers for the lighthouse formatters
Safe data access, aggregation utilities and log / error structures
"""
import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
import numpy as np

def load_input_file(path: str) -> Dict[str, Any]:
    """
    Loads json inputted file

    @Args:
        path (str) -- relative path to the json file

    @Returns:
        json data (Dict[str, Any])
    """
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def safe_get(d: Any, path: List[Any], default: Any = None) -> Any:
    """
    Safely traverse nested dict/list structures.

    @Args:
        d (Any) -- obj with the possibly unknown data structure
        path (List[Any]) -- path of keys to the value you expect to find
        default (Any) -- default value if the expected key fails

    @Returns:
        value at the path if it was correct, else the default provided (Any)

    Example:
      safe_get(obj, ["results", url, "audits", "network-requests", "details", "items"], [])
    """
    cur = d
    for key in path:
        try:
            if isinstance(cur, dict):
                cur = cur.get(key, default)
            elif isinstance(cur, list) and isinstance(key, int):
                cur = cur[key]
            else:
                return default
            
        except Exception:
            return default

    return cur if cur is not None else default


def safe_average(values: List[float]) -> Optional[float]:
    """
    Calculates the average of the provided values with numpy mean
    Returns None instead of crashing when there are no values

    @Args:
        values (List[float]) -- list of values to average

    @Returns:
        average of the provided list, None if the list is empty (Optional[float])
    """
    if not values:
        return None
    
    return float(np.mean(values))


def top_n_by_key(items: List[Dict[str, Any]], key: str, n: int = 3) -> List[Dict[str, Any]]:
    """
    Fetches the top n items safely from the provided list of items

    @Args:
        items (List[Dict[str, Any]]) -- list of Dict items
        key (str) -- key in Dict to sort by
        n (int) -- number of items to fetch

    @Returns:
        top n items sorted by key, highest first (List[Dict[str, Any]])
    """
    if not items:
        return []
    
    # Only keep items that actually have the key
    filtered = [x for x in items if isinstance(x, dict) and key in x]

    return sorted(filtered, key=lambda x: x.get(key, 0), reverse=True)[:n]


def count_status_200(requests: List[Dict[str, Any]]) -> Tuple[int, int]:
    """
    Counts number of 200 status and non-200 status requests

    @Args:
        requests (List[Dict[str, Any]]) -- list of requests items

    @Returns:
        200 and non-200 request counts (Tuple[int, int])
    """
    if not requests:
        return (0, 0)
    ok = 0
    total = 0
    for r in requests:
        if not isinstance(r, dict):
            continue

        total += 1

        if r.get("statusCode") == 200:
            ok += 1

    return (ok, total - ok)


def collect(key: str, per_url: Dict[str, Dict[str, Any]]) -> List[float]:
    """
    Collects the numeric "value" of a metric across every url's data

    @Args:
        key (str) -- key of the metric being collected
        per_url (Dict[str, Dict[str, Any]]) -- reduced audit data keyed by url

    @Returns:
        metric values found across the urls (List[float])
    """
    vals: List[float] = []
    for _, d in per_url.items():
        v = d.get(key, {})

        if isinstance(v, dict) and isinstance(v.get("value"), (int, float)):
            vals.append(float(v["value"]))

    return vals


def get_audit_metric(d, key, aid):
    """
    Fetches a value from a reduced audit section, e.g. diagnostics

    @Args:
        d (Dict) -- reduced audit data for one url
        key (str) -- key of the value being fetched
        aid (str) -- audit section id the value lives under

    @Returns:
        value for the key, None if the section or key is missing (Any)
    """
    items = d.get(aid, {})
    if not items:
        return None
    
    if isinstance(items, dict):
        return items.get(key)
    
    if isinstance(items, list) and items:
        first = items[0]
        
        if isinstance(first, dict):
            return first.get(key)
        
    return None
    # return value if isinstance(value, (int, float)) else None


# -----------------------------
# Logging / errors structures
# -----------------------------

@dataclass
class LogEvent:
    level: str  # "info" | "warning" | "error"
    message: str


def log(logs: List[Dict[str, str]], level: str, message: str) -> None:
    """Appends a log entry to the passed log list

    @Args:
        logs (List[Dict[str, str]]) -- log list to add to
        level (str) -- severity level: info | warning | error
        message (str) -- log message
    """
    logs.append({"level": level, "message": message})


def add_error(
    errors: List[Dict[str, str]],
    *,
    url: str,
    stage: str,
    message: str,
    level: str = "error",
) -> None:
    """Appends an error entry to the passed error list

    @Args:
        errors (List[Dict[str, str]]) -- error list to add to
        url (str) -- url the error relates to
        stage (str) -- stage the error happened in, e.g. input
        message (str) -- error message
        level (str) -- severity level: warning | error
    """
    errors.append({
        "level": level,
        "url": url,
        "stage": stage,
        "message": message,
    })
