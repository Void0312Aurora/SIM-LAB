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


def default_schema_root() -> Path:
    return Path(__file__).resolve().parents[3] / "schemas" / "json"


def validate_runtime_pack_dir(*, pack_dir: Path, schema_root: Path | None = None) -> None:
    schema_root = schema_root or default_schema_root()
    checks = [
        ("runtime-pack-manifest.schema.json", "manifest.json"),
        ("world.schema.json", "world.json"),
        ("buildings.schema.json", "buildings.json"),
        ("zones.schema.json", "zones.json"),
        ("nav-graph.schema.json", "nav_pedestrian.json"),
        ("nav-graph.schema.json", "nav_vehicle.json"),
        ("props.schema.json", "props.json"),
        ("scenario.schema.json", "scenario.json"),
    ]
    failures: list[str] = []
    for schema_name, input_name in checks:
        schema_path = schema_root / schema_name
        input_path = pack_dir / input_name
        try:
            validate_json_file(schema_path=schema_path, input_path=input_path)
        except Exception as exc:
            failures.append(f"{input_name}: {exc}")
    if failures:
        raise ValueError("\n".join(failures))
