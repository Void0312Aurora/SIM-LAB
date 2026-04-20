from __future__ import annotations

from pathlib import Path
import re
from typing import Any

import osmnx as ox
import pandas as pd
from shapely.geometry import LineString, MultiLineString, MultiPolygon, Polygon

from .config import OSMNormalizeConfig
from .osm import configure_osmnx, fetch_buildings, fetch_road_graph
from .serialization import linestring_xy, polygon_exterior_xy, utc_now_iso, write_json


HIGHWAY_WIDTHS_M = {
    "motorway": 25.0,
    "trunk": 20.0,
    "primary": 16.0,
    "secondary": 12.0,
    "tertiary": 10.0,
    "residential": 8.0,
    "living_street": 6.0,
    "service": 6.0,
    "unclassified": 7.0,
}


def _first_scalar(value: Any) -> Any:
    if isinstance(value, list):
        return value[0] if value else None
    return value


def _stringify(value: Any) -> str | None:
    value = _first_scalar(value)
    if value is None or pd.isna(value):
        return None
    return str(value)


def _extract_float(value: Any) -> float | None:
    value = _first_scalar(value)
    if value is None or pd.isna(value):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    match = re.search(r"-?\d+(?:\.\d+)?", str(value))
    if match:
        return float(match.group(0))
    return None


def _extract_int(value: Any) -> int | None:
    number = _extract_float(value)
    if number is None:
        return None
    return int(round(number))


def _normalize_highway_class(value: Any) -> str:
    raw = _stringify(value)
    return raw or "unknown"


def _estimate_road_width(highway_class: str, width_value: Any) -> float:
    explicit = _extract_float(width_value)
    if explicit is not None and explicit > 0:
        return round(explicit, 2)
    return HIGHWAY_WIDTHS_M.get(highway_class, 8.0)


def _is_pedestrian_accessible(highway_class: str) -> bool:
    return highway_class not in {"motorway", "motorway_link", "trunk", "trunk_link"}


def _estimate_height_m(height_value: Any, levels_value: Any) -> float:
    explicit_height = _extract_float(height_value)
    if explicit_height is not None and explicit_height > 0:
        return round(explicit_height, 2)
    levels = _extract_int(levels_value)
    if levels is not None and levels > 0:
        return round(levels * 3.2, 2)
    return 9.0


def _estimate_capacity(area_m2: float, levels_value: Any) -> int:
    levels = _extract_int(levels_value) or 1
    return max(1, int((area_m2 * levels) / 25.0))


def _reset_feature_index(gdf):
    df = gdf.reset_index()
    columns = list(df.columns)
    if len(columns) >= 2:
        df = df.rename(columns={columns[0]: "osm_element_type", columns[1]: "osm_id"})
    df = df.rename(
        columns={
            column: str(column).replace(":", "_").replace(".", "_").replace("-", "_")
            for column in df.columns
        }
    )
    return df


def _project_to_local_origin(edges_gdf, buildings_gdf) -> tuple[float, float]:
    bounds = []
    if not edges_gdf.empty:
        bounds.append(edges_gdf.total_bounds)
    if not buildings_gdf.empty:
        bounds.append(buildings_gdf.total_bounds)
    if not bounds:
        raise ValueError("No roads or buildings were retrieved for the configured area")
    minx = min(item[0] for item in bounds)
    miny = min(item[1] for item in bounds)
    maxx = max(item[2] for item in bounds)
    maxy = max(item[3] for item in bounds)
    return ((minx + maxx) / 2.0, (miny + maxy) / 2.0)


def _serialize_roads(edges_gdf, *, origin_x: float, origin_y: float) -> list[dict[str, Any]]:
    roads: list[dict[str, Any]] = []
    for row in edges_gdf.reset_index().itertuples(index=False):
        geometry = getattr(row, "geometry", None)
        if not isinstance(geometry, (LineString, MultiLineString)):
            continue
        highway_class = _normalize_highway_class(getattr(row, "highway", None))
        width_m = _estimate_road_width(highway_class, getattr(row, "width", None))
        osmid = _stringify(getattr(row, "osmid", None)) or f"{row.u}-{row.v}-{row.key}"
        roads.append(
            {
                "id": f"road_osm_{row.u}_{row.v}_{row.key}",
                "source_record_id": osmid,
                "class": highway_class,
                "name": _stringify(getattr(row, "name", None)),
                "centerline": linestring_xy(
                    geometry,
                    origin_x=origin_x,
                    origin_y=origin_y,
                ),
                "length_m": round(float(getattr(row, "length", geometry.length)), 2),
                "lanes": _extract_int(getattr(row, "lanes", None)),
                "width_m": width_m,
                "is_vehicle_accessible": True,
                "is_pedestrian_accessible": _is_pedestrian_accessible(highway_class),
                "source": {
                    "provider": "OpenStreetMap",
                    "dataset": "OSM road graph via OSMnx",
                    "record_id": osmid,
                },
                "confidence": 1.0,
            }
        )
    return roads


def _serialize_buildings(buildings_gdf, *, origin_x: float, origin_y: float) -> list[dict[str, Any]]:
    buildings: list[dict[str, Any]] = []
    for row in _reset_feature_index(buildings_gdf).itertuples(index=False):
        geometry = getattr(row, "geometry", None)
        if not isinstance(geometry, (Polygon, MultiPolygon)):
            continue
        osm_id = _stringify(getattr(row, "osm_id", None)) or "unknown"
        height_m = _estimate_height_m(
            getattr(row, "height", None),
            getattr(row, "building_levels", None),
        )
        area_m2 = float(geometry.area)
        buildings.append(
            {
                "id": f"building_osm_{osm_id}",
                "source_record_id": osm_id,
                "footprint": polygon_exterior_xy(
                    geometry,
                    origin_x=origin_x,
                    origin_y=origin_y,
                ),
                "height_m": height_m,
                "levels": _extract_int(getattr(row, "building_levels", None)),
                "usage_class": _stringify(getattr(row, "building", None)) or "building",
                "name": _stringify(getattr(row, "name", None)),
                "entrances": [],
                "capacity_estimate": _estimate_capacity(
                    area_m2,
                    getattr(row, "building_levels", None),
                ),
                "source": {
                    "provider": "OpenStreetMap",
                    "dataset": "OSM building features via OSMnx",
                    "record_id": osm_id,
                },
                "confidence": 0.9,
            }
        )
    return buildings


def normalize_osm_bbox(
    config: OSMNormalizeConfig,
    *,
    normalized_root: Path,
    raw_root: Path | None = None,
    schema_version: str = "0.1.0",
) -> Path:
    configure_osmnx(config, raw_root=raw_root)

    road_graph = fetch_road_graph(config)
    building_features = fetch_buildings(config)

    road_graph_proj = ox.projection.project_graph(road_graph)
    buildings_proj = ox.projection.project_gdf(building_features)
    _, edges_gdf = ox.convert.graph_to_gdfs(
        road_graph_proj,
        nodes=True,
        edges=True,
        fill_edge_geometry=True,
    )

    origin_x, origin_y = _project_to_local_origin(edges_gdf, buildings_proj)
    city_dir = normalized_root / config.city_id
    city_dir.mkdir(parents=True, exist_ok=True)

    roads = _serialize_roads(edges_gdf, origin_x=origin_x, origin_y=origin_y)
    buildings = _serialize_buildings(buildings_proj, origin_x=origin_x, origin_y=origin_y)

    manifest = {
        "schema_version": schema_version,
        "city_id": config.city_id,
        "display_name": config.display_name,
        "local_crs": str(edges_gdf.crs or buildings_proj.crs),
        "origin": {
            "x": round(origin_x, 3),
            "y": round(origin_y, 3),
        },
        "units": "meters",
        "bbox_wgs84": config.bbox.as_wgs84_bbox(),
        "sources": [
            {
                "provider": "OpenStreetMap",
                "dataset": "OSM via OSMnx",
                "version": ox.__version__,
                "license": "ODbL-1.0",
            }
        ],
        "compiled_at": utc_now_iso(),
        "layers": {
            "roads": "roads.json",
            "pedestrian_areas": "pedestrian_areas.json",
            "buildings": "buildings.json",
            "landuse": "landuse.json",
            "poi": "poi.json",
            "barriers": "barriers.json",
            "terrain": "terrain.json",
        },
        "stats": {
            "road_count": len(roads),
            "building_count": len(buildings),
        },
    }

    if raw_root is not None:
        raw_dir = raw_root / config.city_id
        raw_dir.mkdir(parents=True, exist_ok=True)
        write_json(
            raw_dir / "request.json",
            {
                "city_id": config.city_id,
                "display_name": config.display_name,
                "bbox_wgs84": config.bbox.as_wgs84_bbox(),
                "network_type": config.network_type,
                "compiled_at": manifest["compiled_at"],
            },
        )

    write_json(city_dir / "city_manifest.json", manifest)
    write_json(city_dir / "roads.json", roads)
    write_json(city_dir / "buildings.json", buildings)
    write_json(city_dir / "pedestrian_areas.json", [])
    write_json(city_dir / "landuse.json", [])
    write_json(city_dir / "poi.json", [])
    write_json(city_dir / "barriers.json", [])
    write_json(city_dir / "terrain.json", {})
    return city_dir
