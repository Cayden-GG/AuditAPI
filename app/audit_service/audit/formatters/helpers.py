import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
import numpy as np

def load_input_file(path: str) -> Dict[str, Any]:
    """
    Loads json inputted file
    
    Args: 
        path (str, required): relative path to the json file 
    
    Returns: 
        The json data as a python Dict
    """
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def safe_get(d: Any, path: List[Any], default: Any = None) -> Any:
    """
    Safely traverse nested dict/list structures.

    Args: 
        d (Any, required): obj with the possibly unknown data structure
        path (List[Any], required): path of key to the value you expect to find.
        default (Any, optional): default value if the expected key fails

    Returns: 
        list of value if path was correct, else default provided.

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
    Calcualte average of provided values with numpy mean
    This will not fail and crash if values are NoneType

    Args: 
        values (List[float], required): list of values to average

    Returns: 
        Average value (float) of the provided list 
    """
    if not values:
        return None
    return float(np.mean(values))


def top_n_by_key(items: List[Dict[str, Any]], key: str, n: int = 3) -> List[Dict[str, Any]]:
    """
    Fetchs the top n items safely from the provided list of items

    Args: 
        items (List[Dict[str, Any]], required): list of Dict items
        key (str, required): key in Dict to sort by
        n (int, optional, default=3): number of items to fetch

    Returns: 
        list of n dict items
    """
    if not items:
        return []
    # Only keep items that actually have the key
    filtered = [x for x in items if isinstance(x, dict) and key in x]
    return sorted(filtered, key=lambda x: x.get(key, 0), reverse=True)[:n]


def count_status_200(requests: List[Dict[str, Any]]) -> Tuple[int, int]:
    """
    Counts number of 200 status and non-200 status requests

    Args: 
        requests (List[Dict[str, Any]], required): list of requests items
        
    Returns: 
        Tuple with 200 and non-200 request counts (int)
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
    Fetches data in the nested url data

    Args: 
        key (str, required): key of the value being fetched
        audit_category (str, required): audit category ["seo_data", "performance_data"]
        per_url (Dict[str, Dict[str, Any]], required): category data for a certain url

    Returns: 
        A list of values (float) fetched from the url data
    """
    vals: List[float] = []
    for _, d in per_url.items():
        v = d.get(key, {})
        if isinstance(v, dict) and isinstance(v.get("value"), (int, float)):
            vals.append(float(v["value"]))
    return vals


def get_audit_metric(d, key, aid):
    """
    Fetches nested diagnostic data

    Args: 
        d (Dict, required): dict with diagnostics data
        key (str, required): key of the value being fetched
        aid (str, reuired): data audit id 

    Returns:
        value 
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
    logs.append({"level": level, "message": message})


def add_error(
    errors: List[Dict[str, str]],
    *,
    url: str,
    stage: str,
    message: str,
    level: str = "error",
) -> None:
    errors.append({
        "level": level,
        "url": url,
        "stage": stage,
        "message": message,
    })
