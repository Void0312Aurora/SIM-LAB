from __future__ import annotations

import argparse
from pathlib import Path
import sys

from .audit import audit_route_building_conflicts
from .config import OSMNormalizeConfig
from .clip import clip_normalized_city
from .imagery import build_tianditu_reference_mosaic
from .normalize import normalize_osm_bbox
from .preview import render_normalized_city_preview
from .research import (
    SUPPORTED_STATIC_IMAGE_PROVIDERS,
    augment_normalized_city,
    fetch_static_research_image,
    import_tencent_place_search,
    import_tencent_route,
)
from .runtime_pack import build_runtime_pack
from .validation import default_schema_root, validate_json_file, validate_runtime_pack_dir


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

    validate_pack_parser = subparsers.add_parser(
        "validate-runtime-pack",
        help="Validate a runtime pack directory against the known schema set.",
    )
    validate_pack_parser.add_argument(
        "--pack-dir",
        type=Path,
        required=True,
        help="Path to a runtime pack directory.",
    )
    validate_pack_parser.add_argument(
        "--schema-root",
        type=Path,
        default=default_schema_root(),
        help="Directory containing runtime pack schema files.",
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

    preview_parser = subparsers.add_parser(
        "preview-normalized-city",
        help="Render a self-contained HTML preview for a normalized city package.",
    )
    preview_parser.add_argument(
        "--normalized-city-dir",
        type=Path,
        required=True,
        help="Path to a normalized city directory containing city_manifest.json.",
    )
    preview_parser.add_argument(
        "--output-html",
        type=Path,
        required=True,
        help="Path to the generated HTML preview file.",
    )
    preview_parser.add_argument(
        "--title",
        type=str,
        help="Optional title override for the preview page.",
    )
    preview_parser.add_argument(
        "--overlay-polygon",
        type=Path,
        help="Optional local-meter polygon config to overlay on the preview.",
    )
    preview_parser.add_argument(
        "--reference-image-config",
        type=Path,
        help="Optional local-meter reference image overlay config for a north-up screenshot.",
    )
    preview_parser.add_argument(
        "--enhancement-bundle",
        type=Path,
        action="append",
        default=[],
        help="Optional enhancement bundle JSON to draw as research overlays on the preview. Repeatable.",
    )

    clip_parser = subparsers.add_parser(
        "clip-normalized-city",
        help="Clip a normalized city package with a local-meter polygon overlay.",
    )
    clip_parser.add_argument(
        "--normalized-city-dir",
        type=Path,
        required=True,
        help="Path to the source normalized city directory.",
    )
    clip_parser.add_argument(
        "--polygon-config",
        type=Path,
        required=True,
        help="Path to a local-meter polygon overlay JSON file.",
    )
    clip_parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Directory where the clipped normalized city package should be written.",
    )

    tencent_place_parser = subparsers.add_parser(
        "import-tencent-place-search",
        help="Convert a saved Tencent place search JSON response into a local-meter enhancement bundle.",
    )
    tencent_place_parser.add_argument(
        "--normalized-city-dir",
        type=Path,
        required=True,
        help="Path to a normalized city directory containing city_manifest.json.",
    )
    tencent_place_parser.add_argument(
        "--input-json",
        type=Path,
        required=True,
        help="Saved Tencent place search JSON response.",
    )
    tencent_place_parser.add_argument(
        "--output-bundle",
        type=Path,
        required=True,
        help="Path to the generated enhancement bundle JSON file.",
    )
    tencent_place_parser.add_argument(
        "--bundle-id",
        type=str,
        help="Optional bundle_id override.",
    )
    tencent_place_parser.add_argument(
        "--display-name",
        type=str,
        help="Optional display name override.",
    )
    tencent_place_parser.add_argument(
        "--no-subpois",
        action="store_true",
        help="Do not emit subpois from the Tencent payload.",
    )

    tencent_route_parser = subparsers.add_parser(
        "import-tencent-route",
        help="Convert a saved Tencent route planning JSON response into a local-meter enhancement bundle.",
    )
    tencent_route_parser.add_argument(
        "--normalized-city-dir",
        type=Path,
        required=True,
        help="Path to a normalized city directory containing city_manifest.json.",
    )
    tencent_route_parser.add_argument(
        "--input-json",
        type=Path,
        required=True,
        help="Saved Tencent route planning JSON response.",
    )
    tencent_route_parser.add_argument(
        "--output-bundle",
        type=Path,
        required=True,
        help="Path to the generated enhancement bundle JSON file.",
    )
    tencent_route_parser.add_argument(
        "--route-index",
        type=int,
        default=0,
        help="Which result.routes entry to import. Defaults to 0.",
    )
    tencent_route_parser.add_argument(
        "--route-mode",
        type=str,
        default="walking",
        help="Fallback route mode label when the payload does not specify one.",
    )
    tencent_route_parser.add_argument(
        "--bundle-id",
        type=str,
        help="Optional bundle_id override.",
    )
    tencent_route_parser.add_argument(
        "--display-name",
        type=str,
        help="Optional display name override.",
    )

    augment_parser = subparsers.add_parser(
        "augment-normalized-city",
        help="Merge one or more local-meter enhancement bundles into a normalized city package.",
    )
    augment_parser.add_argument(
        "--normalized-city-dir",
        type=Path,
        required=True,
        help="Path to the source normalized city directory.",
    )
    augment_parser.add_argument(
        "--enhancement-bundle",
        type=Path,
        action="append",
        required=True,
        help="Enhancement bundle JSON path. Repeatable.",
    )
    augment_parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Directory where the augmented normalized city package should be written.",
    )
    augment_parser.add_argument(
        "--city-id",
        type=str,
        help="Optional city_id override for the augmented package.",
    )
    augment_parser.add_argument(
        "--display-name",
        type=str,
        help="Optional display_name override for the augmented package.",
    )

    audit_parser = subparsers.add_parser(
        "audit-route-building-conflicts",
        help="Audit route centerlines that intersect building footprints.",
    )
    audit_parser.add_argument(
        "--normalized-city-dir",
        type=Path,
        required=True,
        help="Path to a normalized city directory containing city_manifest.json.",
    )
    audit_parser.add_argument(
        "--enhancement-bundle",
        type=Path,
        action="append",
        default=[],
        help="Optional enhancement bundle JSON paths to audit. Repeatable.",
    )
    audit_parser.add_argument(
        "--include-normalized-roads",
        action="store_true",
        help="Also audit roads.json and roads_walk.json from the normalized city package.",
    )
    audit_parser.add_argument(
        "--min-intersection-length-m",
        type=float,
        default=1.0,
        help="Ignore route/building overlaps shorter than this threshold.",
    )
    audit_parser.add_argument(
        "--output-json",
        type=Path,
        required=True,
        help="Path to the generated audit JSON report.",
    )

    static_image_parser = subparsers.add_parser(
        "fetch-static-research-image",
        help="Fetch a Tencent or TianDiTu research image and write a masked fetch report.",
    )
    static_image_parser.add_argument(
        "--provider",
        type=str,
        choices=SUPPORTED_STATIC_IMAGE_PROVIDERS,
        required=True,
        help="Which imagery provider to query.",
    )
    static_image_parser.add_argument(
        "--center-lat",
        type=float,
        required=True,
        help="Center latitude in WGS84 degrees.",
    )
    static_image_parser.add_argument(
        "--center-lng",
        type=float,
        required=True,
        help="Center longitude in WGS84 degrees.",
    )
    static_image_parser.add_argument(
        "--zoom",
        type=int,
        required=True,
        help="Zoom level for the request.",
    )
    static_image_parser.add_argument(
        "--size",
        type=str,
        default="512*512",
        help="Requested raster size formatted as WIDTH*HEIGHT.",
    )
    static_image_parser.add_argument(
        "--maptype",
        type=str,
        default="roadmap",
        help="Tencent maptype, for example roadmap / satellite / hybrid.",
    )
    static_image_parser.add_argument(
        "--tdt-layers",
        type=str,
        default="vec_w,cva_w",
        help="TianDiTu staticimage layers parameter, for example vec_w,cva_w or img_w,cia_w.",
    )
    static_image_parser.add_argument(
        "--tdt-layer",
        type=str,
        default="vec",
        help="TianDiTu WMTS layer name, for example vec / img / cia.",
    )
    static_image_parser.add_argument(
        "--env-file",
        type=Path,
        required=True,
        help="Path to the local env file that stores provider API keys.",
    )
    static_image_parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Path to the downloaded image or response payload.",
    )
    static_image_parser.add_argument(
        "--report",
        type=Path,
        required=True,
        help="Path to the masked JSON fetch report.",
    )

    tdt_mosaic_parser = subparsers.add_parser(
        "build-tianditu-reference-mosaic",
        help="Fetch TianDiTu WMTS tiles for an overlay area, stitch them, and emit a reference-image config.",
    )
    tdt_mosaic_parser.add_argument(
        "--normalized-city-dir",
        type=Path,
        required=True,
        help="Path to a normalized city directory containing city_manifest.json.",
    )
    tdt_mosaic_parser.add_argument(
        "--overlay-polygon",
        type=Path,
        required=True,
        help="Path to a local-meter overlay polygon config that defines the target area.",
    )
    tdt_mosaic_parser.add_argument(
        "--env-file",
        type=Path,
        required=True,
        help="Path to the local env file that stores the TianDiTu key.",
    )
    tdt_mosaic_parser.add_argument(
        "--output-image",
        type=Path,
        required=True,
        help="Path to the stitched PNG reference image.",
    )
    tdt_mosaic_parser.add_argument(
        "--output-config",
        type=Path,
        required=True,
        help="Path to the generated reference image config JSON.",
    )
    tdt_mosaic_parser.add_argument(
        "--report",
        type=Path,
        required=True,
        help="Path to the generated JSON fetch/stitch report.",
    )
    tdt_mosaic_parser.add_argument(
        "--zoom",
        type=int,
        default=17,
        help="WMTS zoom level. Defaults to 17.",
    )
    tdt_mosaic_parser.add_argument(
        "--base-layer",
        type=str,
        default="img",
        help="TianDiTu WMTS base layer, for example img or vec.",
    )
    tdt_mosaic_parser.add_argument(
        "--label-layer",
        type=str,
        default="cia",
        help="Optional TianDiTu WMTS label layer, for example cia or cva.",
    )
    tdt_mosaic_parser.add_argument(
        "--no-label-layer",
        action="store_true",
        help="Do not request or composite any label layer.",
    )
    tdt_mosaic_parser.add_argument(
        "--padding-tiles",
        type=int,
        default=0,
        help="Extra WMTS tiles to include around the requested overlay bounds.",
    )
    tdt_mosaic_parser.add_argument(
        "--opacity",
        type=float,
        default=0.72,
        help="Default reference image opacity written into the config.",
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

    if args.command == "validate-runtime-pack":
        validate_runtime_pack_dir(pack_dir=args.pack_dir, schema_root=args.schema_root)
        print(f"Runtime pack validation OK: {args.pack_dir}")
        return 0

    if args.command == "preview-normalized-city":
        output_path = render_normalized_city_preview(
            normalized_city_dir=args.normalized_city_dir,
            output_html=args.output_html,
            title=args.title,
            overlay_polygon_path=args.overlay_polygon,
            reference_image_config_path=args.reference_image_config,
            enhancement_bundle_paths=args.enhancement_bundle,
        )
        print(f"Normalized city preview written to {output_path}")
        return 0

    if args.command == "clip-normalized-city":
        output_dir = clip_normalized_city(
            normalized_city_dir=args.normalized_city_dir,
            polygon_config_path=args.polygon_config,
            output_dir=args.output_dir,
        )
        print(f"Clipped normalized city package written to {output_dir}")
        return 0

    if args.command == "import-tencent-place-search":
        output_path = import_tencent_place_search(
            normalized_city_dir=args.normalized_city_dir,
            input_json_path=args.input_json,
            output_bundle_path=args.output_bundle,
            bundle_id=args.bundle_id,
            display_name=args.display_name,
            include_subpois=not args.no_subpois,
        )
        print(f"Tencent place search bundle written to {output_path}")
        return 0

    if args.command == "import-tencent-route":
        output_path = import_tencent_route(
            normalized_city_dir=args.normalized_city_dir,
            input_json_path=args.input_json,
            output_bundle_path=args.output_bundle,
            route_index=args.route_index,
            route_mode=args.route_mode,
            bundle_id=args.bundle_id,
            display_name=args.display_name,
        )
        print(f"Tencent route bundle written to {output_path}")
        return 0

    if args.command == "augment-normalized-city":
        output_path = augment_normalized_city(
            normalized_city_dir=args.normalized_city_dir,
            enhancement_bundle_paths=args.enhancement_bundle,
            output_dir=args.output_dir,
            city_id=args.city_id,
            display_name=args.display_name,
        )
        print(f"Augmented normalized city package written to {output_path}")
        return 0

    if args.command == "audit-route-building-conflicts":
        output_path = audit_route_building_conflicts(
            normalized_city_dir=args.normalized_city_dir,
            enhancement_bundle_paths=args.enhancement_bundle,
            include_normalized_roads=args.include_normalized_roads,
            min_intersection_length_m=args.min_intersection_length_m,
            output_json_path=args.output_json,
        )
        print(f"Route/building audit written to {output_path}")
        return 0

    if args.command == "fetch-static-research-image":
        output_path = fetch_static_research_image(
            provider=args.provider,
            center_lat=args.center_lat,
            center_lng=args.center_lng,
            zoom=args.zoom,
            output_path=args.output,
            report_path=args.report,
            env_file_path=args.env_file,
            size=args.size,
            maptype=args.maptype,
            tdt_layers=args.tdt_layers,
            tdt_layer=args.tdt_layer,
        )
        print(f"Static research image fetch report written to {output_path}")
        return 0

    if args.command == "build-tianditu-reference-mosaic":
        output_path = build_tianditu_reference_mosaic(
            normalized_city_dir=args.normalized_city_dir,
            overlay_polygon_path=args.overlay_polygon,
            env_file_path=args.env_file,
            output_image_path=args.output_image,
            output_config_path=args.output_config,
            output_report_path=args.report,
            zoom=args.zoom,
            base_layer=args.base_layer,
            label_layer=None if args.no_label_layer else args.label_layer,
            padding_tiles=args.padding_tiles,
            image_opacity=args.opacity,
        )
        print(f"TianDiTu reference mosaic report written to {output_path}")
        return 0

    parser.error(f"Unsupported command: {args.command}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
