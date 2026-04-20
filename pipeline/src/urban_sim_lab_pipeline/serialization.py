from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json
from typing import Any

from shapely.geometry import LineString, MultiLineString, MultiPolygon, Polygon


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=False),
        encoding="utf-8",
    )


def _largest_polygon(geometry: Polygon | MultiPolygon) -> Polygon:
    if isinstance(geometry, Polygon):
        return geometry
    return max(geometry.geoms, key=lambda item: item.area)


def _longest_linestring(geometry: LineString | MultiLineString) -> LineString:
    if isinstance(geometry, LineString):
        return geometry
    return max(geometry.geoms, key=lambda item: item.length)


def polygon_exterior_xy(
    geometry: Polygon | MultiPolygon,
    *,
    origin_x: float,
    origin_y: float,
) -> list[list[float]]:
    polygon = _largest_polygon(geometry)
    return [
        [round(x - origin_x, 3), round(y - origin_y, 3)]
        for x, y in polygon.exterior.coords
    ]


def linestring_xy(
    geometry: LineString | MultiLineString,
    *,
    origin_x: float,
    origin_y: float,
) -> list[list[float]]:
    line = _longest_linestring(geometry)
    return [
        [round(x - origin_x, 3), round(y - origin_y, 3)]
        for x, y in line.coords
    ]
