from __future__ import annotations

import argparse
from pathlib import Path
import sys

from .config import OSMNormalizeConfig
from .normalize import normalize_osm_bbox


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

    parser.error(f"Unsupported command: {args.command}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
