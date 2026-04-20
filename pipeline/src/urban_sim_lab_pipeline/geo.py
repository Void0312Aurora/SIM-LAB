from __future__ import annotations

from pathlib import Path
import json
from typing import Any

from pyproj import Transformer


def read_city_manifest(normalized_city_dir: Path) -> dict[str, Any]:
    return json.loads((normalized_city_dir / "city_manifest.json").read_text(encoding="utf-8"))


def build_wgs84_to_local_transformer(manifest: dict[str, Any]) -> Transformer:
    local_crs = manifest.get("local_crs")
    if not isinstance(local_crs, str) or not local_crs.strip():
        raise ValueError("city_manifest.json is missing a valid local_crs value")
    return Transformer.from_crs("EPSG:4326", local_crs, always_xy=True)


def build_local_to_wgs84_transformer(manifest: dict[str, Any]) -> Transformer:
    local_crs = manifest.get("local_crs")
    if not isinstance(local_crs, str) or not local_crs.strip():
        raise ValueError("city_manifest.json is missing a valid local_crs value")
    return Transformer.from_crs(local_crs, "EPSG:4326", always_xy=True)


def wgs84_to_local_xy(
    longitude: float,
    latitude: float,
    *,
    manifest: dict[str, Any],
    transformer: Transformer | None = None,
) -> tuple[float, float]:
    active_transformer = transformer or build_wgs84_to_local_transformer(manifest)
    projected_x, projected_y = active_transformer.transform(longitude, latitude)
    origin = manifest.get("origin", {})
    origin_x = float(origin.get("x", 0.0))
    origin_y = float(origin.get("y", 0.0))
    return (
        round(float(projected_x) - origin_x, 3),
        round(float(projected_y) - origin_y, 3),
    )


def local_xy_to_wgs84(
    x: float,
    y: float,
    *,
    manifest: dict[str, Any],
    transformer: Transformer | None = None,
) -> tuple[float, float]:
    active_transformer = transformer or build_local_to_wgs84_transformer(manifest)
    origin = manifest.get("origin", {})
    origin_x = float(origin.get("x", 0.0))
    origin_y = float(origin.get("y", 0.0))
    longitude, latitude = active_transformer.transform(x + origin_x, y + origin_y)
    return (
        round(float(longitude), 6),
        round(float(latitude), 6),
    )
