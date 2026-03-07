"""
Writes JSON data to disk with UTF-8 encoding and pretty formatting.

If filename is not provided, a timestamped filename is generated.
"""

from pathlib import Path
from datetime import datetime
import json
from typing import Any, Dict


def _json_fallback(value: Any) -> Any:
    try:
        import numpy as np  # type: ignore

        if isinstance(value, np.generic):
            return value.item()
    except Exception:
        pass

    if isinstance(value, Path):
        return str(value)

    if isinstance(value, set):
        return sorted(value)

    if hasattr(value, "model_dump"):
        return value.model_dump()

    return str(value)

def write_json_to_file(data: Dict[str, Any], output_dir: str = "outputs", filename: str | None = None):
    """ Writes .json file from inputted data

    Args: 
        data (Dict, required): data to be witten to json file
        output_dir (str, optional, default = "outputs/"): output directory that json file will be saved to 
        filename (str, optional, default="audit_{timestamp}.json"): output json file, filename
    
    Returns:
        str: json filepath 
    """
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    if filename is None:
        timestamp = datetime.utcnow().strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"audit_{timestamp}.json"

    output_path = Path(output_dir) / filename

    payload = json.dumps(data, indent=2, ensure_ascii=False, default=_json_fallback)

    with output_path.open("w", encoding="utf-8") as f:
        f.write(payload)

    return str(output_path)

