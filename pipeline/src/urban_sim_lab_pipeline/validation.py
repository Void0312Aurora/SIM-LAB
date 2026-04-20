from __future__ import annotations

from pathlib import Path
import json
from typing import Any

from jsonschema import Draft202012Validator


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_json_file(*, schema_path: Path, input_path: Path) -> None:
    schema = load_json(schema_path)
    payload = load_json(input_path)
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(payload), key=lambda item: list(item.absolute_path))
    if errors:
        lines = []
        for error in errors:
            location = ".".join(str(part) for part in error.absolute_path) or "<root>"
            lines.append(f"{location}: {error.message}")
        raise ValueError("\n".join(lines))
