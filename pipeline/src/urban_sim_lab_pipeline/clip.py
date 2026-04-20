from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any
import json

from shapely.geometry import GeometryCollection, LineString, MultiLineString, MultiPolygon, Point, Polygon

from .overlay import load_overlay_polygon
from .serialization import utc_now_iso, write_json


MIN_CLIPPED_LINE_LENGTH_M = 5.0


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _polygon_from_points(points: list[list[float]]) -> Polygon:
    polygon = Polygon([(float(point[0]), float(point[1])) for point in points])
    if not polygon.is_valid:
        polygon = polygon.buffer(0)
    if polygon.is_empty:
        raise ValueError("Overlay polygon became empty after validation.")
    if not isinstance(polygon, Polygon):
        raise ValueError("Overlay polygon must resolve to a single polygon.")
    return polygon


def _largest_polygon(geometry: Polygon | MultiPolygon) -> Polygon:
    if isinstance(geometry, Polygon):
        return geometry
    return max(geometry.geoms, key=lambda item: item.area)


def _iter_lines(geometry: Any):
    if geometry.is_empty:
        return
    if isinstance(geometry, LineString):
        yield geometry
        return
    if isinstance(geometry, MultiLineString):
        for line in geometry.geoms:
            yield line
        return
    if isinstance(geometry, GeometryCollection):
        for item in geometry.geoms:
            yield from _iter_lines(item)


def _round_xy_coords(coords) -> list[list[float]]:
    return [[round(float(x), 3), round(float(y), 3)] for x, y in coords]


def _clip_roads(roads: list[dict[str, Any]], clip_polygon: Polygon) -> list[dict[str, Any]]:
    clipped_roads: list[dict[str, Any]] = []
    for road in roads:
        centerline = road.get("centerline", [])
        if len(centerline) < 2:
            continue
        geometry = LineString(centerline)
        if geometry.is_empty:
            continue
        clipped_geometry = geometry.intersection(clip_polygon)
        segments = [segment for segment in _iter_lines(clipped_geometry) if segment.length >= MIN_CLIPPED_LINE_LENGTH_M]
        for index, segment in enumerate(segments):
            cloned = deepcopy(road)
            cloned["id"] = road["id"] if len(segments) == 1 else f"{road['id']}_clip_{index + 1}"
            cloned["centerline"] = _round_xy_coords(segment.coords)
            cloned["length_m"] = round(float(segment.length), 2)
            clipped_roads.append(cloned)
    return clipped_roads


def _point_from_dict(source: dict[str, Any]) -> Point:
    return Point(float(source.get("x", 0.0)), float(source.get("z", source.get("y", 0.0))))


def _filter_buildings(buildings: list[dict[str, Any]], clip_polygon: Polygon) -> list[dict[str, Any]]:
    filtered: list[dict[str, Any]] = []
    for building in buildings:
        footprint = building.get("footprint", [])
        if len(footprint) < 3:
            continue
        geometry = Polygon(footprint)
        if geometry.is_empty:
            continue
        if geometry.centroid.within(clip_polygon) or geometry.intersects(clip_polygon):
            filtered.append(building)
    return filtered


def _clip_polygon_layers(items: list[dict[str, Any]], clip_polygon: Polygon) -> list[dict[str, Any]]:
    filtered: list[dict[str, Any]] = []
    for item in items:
        polygon_points = item.get("polygon", [])
        if len(polygon_points) < 3:
            continue
        geometry = Polygon(polygon_points)
        clipped = geometry.intersection(clip_polygon)
        if clipped.is_empty:
            continue
        if isinstance(clipped, (Polygon, MultiPolygon)):
            largest = _largest_polygon(clipped)
            cloned = deepcopy(item)
            cloned["polygon"] = _round_xy_coords(largest.exterior.coords)
            filtered.append(cloned)
    return filtered


def _clip_barriers(barriers: list[dict[str, Any]], clip_polygon: Polygon) -> list[dict[str, Any]]:
    filtered: list[dict[str, Any]] = []
    for barrier in barriers:
        geometry_points = barrier.get("geometry", [])
        if len(geometry_points) < 2:
            continue
        geometry = LineString(geometry_points)
        clipped = geometry.intersection(clip_polygon)
        segments = [segment for segment in _iter_lines(clipped) if segment.length >= MIN_CLIPPED_LINE_LENGTH_M]
        for index, segment in enumerate(segments):
            cloned = deepcopy(barrier)
            cloned["id"] = barrier.get("id", "barrier") if len(segments) == 1 else f"{barrier.get('id', 'barrier')}_clip_{index + 1}"
            cloned["geometry"] = _round_xy_coords(segment.coords)
            filtered.append(cloned)
    return filtered


def _filter_poi(poi_items: list[dict[str, Any]], clip_polygon: Polygon) -> list[dict[str, Any]]:
    filtered: list[dict[str, Any]] = []
    for item in poi_items:
        if not isinstance(item, dict):
            continue
        position = item.get("position")
        center = item.get("center")
        point_source = position if isinstance(position, dict) else center if isinstance(center, dict) else None
        if point_source is None:
            continue
        if _point_from_dict(point_source).within(clip_polygon):
            filtered.append(item)
    return filtered


def clip_normalized_city(
    *,
    normalized_city_dir: Path,
    polygon_config_path: Path,
    output_dir: Path,
) -> Path:
    overlay = load_overlay_polygon(polygon_config_path)
    clip_polygon = _polygon_from_points(overlay["polygon"])

    manifest = _read_json(normalized_city_dir / "city_manifest.json")
    layers = manifest.get("layers", {})
    roads = _read_json(normalized_city_dir / layers.get("roads", "roads.json"))
    roads_walk_path = normalized_city_dir / layers.get("roads_walk", "roads_walk.json")
    roads_walk = _read_json(roads_walk_path) if roads_walk_path.exists() else []
    buildings = _read_json(normalized_city_dir / layers.get("buildings", "buildings.json"))
    pedestrian_areas = _read_json(normalized_city_dir / layers.get("pedestrian_areas", "pedestrian_areas.json"))
    landuse = _read_json(normalized_city_dir / layers.get("landuse", "landuse.json"))
    poi = _read_json(normalized_city_dir / layers.get("poi", "poi.json"))
    barriers = _read_json(normalized_city_dir / layers.get("barriers", "barriers.json"))
    terrain = _read_json(normalized_city_dir / layers.get("terrain", "terrain.json"))

    clipped_roads = _clip_roads(roads, clip_polygon)
    clipped_walk_roads = _clip_roads(roads_walk, clip_polygon)
    clipped_buildings = _filter_buildings(buildings, clip_polygon)
    clipped_pedestrian_areas = _clip_polygon_layers(pedestrian_areas, clip_polygon)
    clipped_landuse = _clip_polygon_layers(landuse, clip_polygon)
    clipped_poi = _filter_poi(poi, clip_polygon)
    clipped_barriers = _clip_barriers(barriers, clip_polygon)

    output_dir.mkdir(parents=True, exist_ok=True)

    manifest_out = deepcopy(manifest)
    manifest_out["city_id"] = output_dir.name
    manifest_out["display_name"] = overlay.get(
        "display_name",
        f"{manifest.get('display_name', output_dir.name)} | clipped",
    )
    manifest_out["compiled_at"] = utc_now_iso()
    manifest_out["stats"]["road_count"] = len(clipped_roads)
    if "walk_road_count" in manifest_out.get("stats", {}) or clipped_walk_roads:
        manifest_out["stats"]["walk_road_count"] = len(clipped_walk_roads)
    manifest_out["stats"]["building_count"] = len(clipped_buildings)

    write_json(output_dir / "city_manifest.json", manifest_out)
    write_json(output_dir / layers.get("roads", "roads.json"), clipped_roads)
    if roads_walk_path.exists() or "roads_walk" in layers:
        write_json(output_dir / layers.get("roads_walk", "roads_walk.json"), clipped_walk_roads)
    write_json(output_dir / layers.get("buildings", "buildings.json"), clipped_buildings)
    write_json(output_dir / layers.get("pedestrian_areas", "pedestrian_areas.json"), clipped_pedestrian_areas)
    write_json(output_dir / layers.get("landuse", "landuse.json"), clipped_landuse)
    write_json(output_dir / layers.get("poi", "poi.json"), clipped_poi)
    write_json(output_dir / layers.get("barriers", "barriers.json"), clipped_barriers)
    write_json(output_dir / layers.get("terrain", "terrain.json"), terrain)
    return output_dir
