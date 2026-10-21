import json
import re
from pathlib import Path

import numpy as np
from pydantic import BaseModel

from app.audit_service.writers.write_to_json import write_json_to_file


def test_writes_pretty_utf8_json_and_creates_the_directory(tmp_path):
    out = tmp_path / "a" / "b"

    path = write_json_to_file({"name": "Café ☕", "n": 1}, output_dir=str(out), filename="data.json")

    assert path == str(out / "data.json")
    text = (out / "data.json").read_text(encoding="utf-8")
    assert "Café ☕" in text
    assert text.startswith('{\n  "name"')
    assert json.loads(text) == {"name": "Café ☕", "n": 1}


def test_default_filename_is_timestamped(tmp_path):
    path = write_json_to_file({}, output_dir=str(tmp_path))

    assert re.fullmatch(r"audit_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}\.json", Path(path).name)


def test_overwrites_an_existing_file(tmp_path):
    write_json_to_file({"v": 1}, output_dir=str(tmp_path), filename="data.json")
    write_json_to_file({"v": 2}, output_dir=str(tmp_path), filename="data.json")

    assert json.loads((tmp_path / "data.json").read_text()) == {"v": 2}


class Model(BaseModel):
    value: int


class Unprintable:
    def __str__(self):
        return "custom-object"


def test_non_json_types_are_converted(tmp_path):
    data = {
        "path": Path("some/where"),
        "tags": {"b", "a"},
        "np_int": np.int64(5),
        "np_float": np.float64(1.5),
        "model": Model(value=3),
        "other": Unprintable(),
    }

    path = write_json_to_file(data, output_dir=str(tmp_path), filename="data.json")

    assert json.loads(Path(path).read_text()) == {
        "path": "some/where",
        "tags": ["a", "b"],
        "np_int": 5,
        "np_float": 1.5,
        "model": {"value": 3},
        "other": "custom-object",
    }
