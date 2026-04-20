from __future__ import annotations

from pathlib import Path
from typing import Any

from shapely.geometry import LineString, Point, Polygon

from .geo import read_city_manifest
from .research import load_enhancement_bundle
from .serialization import utc_now_iso, write_json
from .validation import load_json


def _load_buildings(normalized_city_dir: Path) -> list[dict[str, Any]]:
    manifest = read_city_manifest(normalized_city_dir)
    layers = manifest.get("layers", {})
    buildings_path = normalized_city_dir / layers.get("buildings", "buildings.json")
    buildings = load_json(buildings_path)
    if not isinstance(buildings, list):
        raise ValueError("Expected buildings layer to be a list.")
    return buildings


def _building_polygon(building: dict[str, Any]) -> Polygon | None:
    footprint = building.get("footprint")
    if not isinstance(footprint, list) or len(footprint) < 4:
        return None
    polygon = Polygon(footprint)
    if polygon.is_empty:
        return None
    if not polygon.is_valid:
        polygon = polygon.buffer(0)
    if polygon.is_empty:
        return None
    return polygon


def _load_normalized_routes(normalized_city_dir: Path) -> list[dict[str, Any]]:
    manifest = read_city_manifest(normalized_city_dir)
    layers = manifest.get("layers", {})
    route_items: list[dict[str, Any]] = []
    for layer_name in ("roads", "roads_walk"):
        layer_path = normalized_city_dir / layers.get(layer_name, f"{layer_name}.json")
        payload = load_json(layer_path)
        if not isinstance(payload, list):
            raise ValueError(f"Expected normalized layer {layer_name!r} to be a list.")
        for item in payload:
            if isinstance(item, dict):
                route_items.append(
                    {
                        "scope": "normalized",
                        "scope_id": str(manifest.get("city_id") or normalized_city_dir.name),
                        "scope_display_name": str(
                            manifest.get("display_name") or manifest.get("city_id") or normalized_city_dir.name
                        ),
                        "scope_path": str(layer_path.resolve()),
                        "layer_name": layer_name,
                        "route": item,
                    }
                )
    return route_items


def _load_bundle_routes(bundle_path: Path) -> list[dict[str, Any]]:
    bundle = load_enhancement_bundle(bundle_path)
    route_items: list[dict[str, Any]] = []
    for layer_name in ("roads", "roads_walk"):
        for item in bundle.get("layers", {}).get(layer_name, []):
            if isinstance(item, dict):
                route_items.append(
                    {
                        "scope": "enhancement_bundle",
                        "scope_id": str(bundle.get("bundle_id") or bundle_path.stem),
                        "scope_display_name": str(
                            bundle.get("display_name") or bundle.get("bundle_id") or bundle_path.stem
                        ),
                        "scope_path": str(bundle_path.resolve()),
                        "layer_name": layer_name,
                        "route": item,
                    }
                )
    return route_items


def _line_from_route(route: dict[str, Any]) -> LineString | None:
    centerline = route.get("centerline")
    if not isinstance(centerline, list) or len(centerline) < 2:
        return None
    line = LineString(centerline)
    if line.is_empty:
        return None
    return line


def _route_length_m(route: dict[str, Any], line: LineString) -> float:
    length_value = route.get("length_m")
    if isinstance(length_value, (int, float)):
        return round(float(length_value), 3)
    return round(float(line.length), 3)


def _segment_conflicts(
    *,
    centerline: list[Any],
    polygon: Polygon,
    min_intersection_length_m: float,
) -> list[dict[str, Any]]:
    conflicts: list[dict[str, Any]] = []
    for index, (point_a, point_b) in enumerate(zip(centerline, centerline[1:])):
        if not isinstance(point_a, list) or not isinstance(point_b, list):
            continue
        if len(point_a) < 2 or len(point_b) < 2:
            continue
        segment = LineString([point_a, point_b])
        if segment.is_empty or not segment.intersects(polygon):
            continue
        intersection = segment.intersection(polygon)
        intersection_length = float(getattr(intersection, "length", 0.0))
        if intersection_length < min_intersection_length_m:
            continue
        conflicts.append(
            {
                "segment_index": index,
                "segment_length_m": round(float(segment.length), 3),
                "intersection_length_m": round(intersection_length, 3),
                "from": [round(float(point_a[0]), 3), round(float(point_a[1]), 3)],
                "to": [round(float(point_b[0]), 3), round(float(point_b[1]), 3)],
            }
        )
    return conflicts


def _classify_conflict(
    *,
    line: LineString,
    polygon: Polygon,
    start_inside: bool,
    end_inside: bool,
) -> str:
    if line.within(polygon):
        return "route_within_building"
    if (start_inside or end_inside) and not line.crosses(polygon):
        return "endpoint_anchor_overlap"
    if line.crosses(polygon) and not start_inside and not end_inside:
        return "mid_route_crossing"
    if start_inside or end_inside:
        return "endpoint_and_mid_overlap"
    return "building_overlap"


def audit_route_building_conflicts(
    *,
    normalized_city_dir: Path,
    output_json_path: Path,
    enhancement_bundle_paths: list[Path] | None = None,
    include_normalized_roads: bool = False,
    min_intersection_length_m: float = 1.0,
) -> Path:
    buildings = _load_buildings(normalized_city_dir)
    building_records = []
    for building in buildings:
        polygon = _building_polygon(building)
        if polygon is None:
            continue
        building_records.append((building, polygon))

    route_records: list[dict[str, Any]] = []
    if include_normalized_roads:
        route_records.extend(_load_normalized_routes(normalized_city_dir))
    for bundle_path in enhancement_bundle_paths or []:
        route_records.extend(_load_bundle_routes(bundle_path))

    conflicts: list[dict[str, Any]] = []
    route_conflict_keys: set[tuple[str, str, str]] = set()
    scope_counts: dict[str, int] = {}

    for route_record in route_records:
        route = route_record["route"]
        line = _line_from_route(route)
        if line is None:
            continue
        centerline = route.get("centerline", [])
        start_point = Point(centerline[0])
        end_point = Point(centerline[-1])
        route_scope_key = (
            route_record["scope"],
            route_record["scope_path"],
            str(route.get("id") or ""),
            route_record["layer_name"],
        )
        scope_counts[route_record["scope_path"]] = scope_counts.get(route_record["scope_path"], 0) + 1

        for building, polygon in building_records:
            if not line.intersects(polygon):
                continue
            intersection = line.intersection(polygon)
            intersection_length = float(getattr(intersection, "length", 0.0))
            if intersection_length < min_intersection_length_m:
                continue

            start_inside = bool(polygon.covers(start_point))
            end_inside = bool(polygon.covers(end_point))
            segment_conflicts = _segment_conflicts(
                centerline=centerline,
                polygon=polygon,
                min_intersection_length_m=min_intersection_length_m,
            )
            classification = _classify_conflict(
                line=line,
                polygon=polygon,
                start_inside=start_inside,
                end_inside=end_inside,
            )
            route_conflict_keys.add(route_scope_key)
            conflicts.append(
                {
                    "scope": route_record["scope"],
                    "scope_id": route_record["scope_id"],
                    "scope_display_name": route_record["scope_display_name"],
                    "scope_path": route_record["scope_path"],
                    "layer_name": route_record["layer_name"],
                    "route_id": route.get("id"),
                    "route_name": route.get("name"),
                    "network_role": route.get("network_role"),
                    "route_length_m": _route_length_m(route, line),
                    "building_id": building.get("id"),
                    "building_name": building.get("name"),
                    "classification": classification,
                    "intersection_length_m": round(intersection_length, 3),
                    "start_inside_building": start_inside,
                    "end_inside_building": end_inside,
                    "line_crosses_building": bool(line.crosses(polygon)),
                    "segment_conflicts": segment_conflicts,
                }
            )

    conflicts.sort(
        key=lambda item: (
            -float(item.get("intersection_length_m") or 0.0),
            str(item.get("scope_id") or ""),
            str(item.get("route_id") or ""),
            str(item.get("building_id") or ""),
        )
    )

    report = {
        "audit_type": "route_building_conflicts",
        "generated_at": utc_now_iso(),
        "normalized_city_dir": str(normalized_city_dir.resolve()),
        "include_normalized_roads": include_normalized_roads,
        "enhancement_bundle_paths": [str(path.resolve()) for path in (enhancement_bundle_paths or [])],
        "min_intersection_length_m": round(float(min_intersection_length_m), 3),
        "summary": {
            "building_count": len(building_records),
            "route_count": len(route_records),
            "source_route_counts": scope_counts,
            "conflict_count": len(conflicts),
            "route_with_conflict_count": len(route_conflict_keys),
        },
        "conflicts": conflicts,
    }
    write_json(output_json_path, report)
    return output_json_path
