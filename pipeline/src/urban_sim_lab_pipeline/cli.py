from __future__ import annotations

import argparse
from pathlib import Path
import sys

from .config import OSMNormalizeConfig
from .normalize import normalize_osm_bbox
from .runtime_pack import build_runtime_pack
from .validation import validate_json_file


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="urban-sim-lab-pipeline",
        description="Offline city compilation helpers for Urban Sim Lab.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    normalize_parser = subparsers.add_parser(
        "normalize-osm",
        help="Download a bbox from OpenStreetMap and emit a normalized city package.",
    )
    normalize_parser.add_argument(
        "--config",
        type=Path,
        required=True,
        help="Path to the OSM bbox config JSON file.",
    )
    normalize_parser.add_argument(
        "--normalized-root",
        type=Path,
        required=True,
        help="Directory where normalized city packages should be written.",
    )
    normalize_parser.add_argument(
        "--raw-root",
        type=Path,
        help="Optional directory for request snapshots and OSMnx cache.",
    )

    validate_parser = subparsers.add_parser(
        "validate-json",
        help="Validate a JSON file against a JSON Schema file.",
    )
    validate_parser.add_argument(
        "--schema",
        type=Path,
        required=True,
        help="Path to a JSON Schema file.",
    )
    validate_parser.add_argument(
        "--input",
        type=Path,
        required=True,
        help="Path to a JSON document to validate.",
    )

    pack_parser = subparsers.add_parser(
        "build-runtime-pack",
        help="Build a minimal runtime pack from a normalized city package.",
    )
    pack_parser.add_argument(
        "--normalized-city-dir",
        type=Path,
        required=True,
        help="Path to a normalized city directory containing city_manifest.json.",
    )
    pack_parser.add_argument(
        "--output-root",
        type=Path,
        required=True,
        help="Directory where runtime packs should be written.",
    )
    pack_parser.add_argument(
        "--scenario",
        type=Path,
        help="Optional scenario JSON file to include in the runtime pack.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "normalize-osm":
        config = OSMNormalizeConfig.from_path(args.config)
        output_dir = normalize_osm_bbox(
            config,
            normalized_root=args.normalized_root,
            raw_root=args.raw_root,
        )
        print(f"Normalized city package written to {output_dir}")
        return 0

    if args.command == "validate-json":
        validate_json_file(schema_path=args.schema, input_path=args.input)
        print(f"Validation OK: {args.input}")
        return 0

    if args.command == "build-runtime-pack":
        output_dir = build_runtime_pack(
            normalized_city_dir=args.normalized_city_dir,
            output_root=args.output_root,
            scenario_path=args.scenario,
        )
        print(f"Runtime pack written to {output_dir}")
        return 0

    parser.error(f"Unsupported command: {args.command}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
