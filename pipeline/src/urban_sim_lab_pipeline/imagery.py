from __future__ import annotations

from pathlib import Path
import math
import os
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen

import numpy as np
import rasterio
from rasterio.io import MemoryFile

from .geo import local_xy_to_wgs84, read_city_manifest, wgs84_to_local_xy
from .overlay import load_overlay_polygon
from .research import TIANDITU_KEY_ENV_CANDIDATES, _read_simple_env, _resolve_env_secret
from .serialization import utc_now_iso, write_json


TIANDITU_WMTS_TILE_SIZE = 256


def _slippy_tile_x(longitude: float, zoom: int) -> int:
    tile_count = 2**zoom
    x_position = (longitude + 180.0) / 360.0 * tile_count
    safe_x_position = min(max(x_position, 0.0), float(tile_count) - 1e-9)
    return int(math.floor(safe_x_position))


def _slippy_tile_y(latitude: float, zoom: int) -> int:
    latitude_radians = math.radians(latitude)
    tile_count = 2**zoom
    y_position = (1.0 - math.asinh(math.tan(latitude_radians)) / math.pi) / 2.0 * tile_count
    safe_y_position = min(max(y_position, 0.0), float(tile_count) - 1e-9)
    return int(math.floor(safe_y_position))


def _tile_x_to_longitude(tile_x: int, zoom: int) -> float:
    tile_count = 2**zoom
    return tile_x / tile_count * 360.0 - 180.0


def _tile_y_to_latitude(tile_y: int, zoom: int) -> float:
    tile_count = 2**zoom
    n = math.pi * (1.0 - 2.0 * tile_y / tile_count)
    return math.degrees(math.atan(math.sinh(n)))


def _overlay_local_bounds(overlay_path: Path) -> dict[str, float]:
    overlay = load_overlay_polygon(overlay_path)
    polygon = overlay.get("polygon", [])
    xs = [float(point[0]) for point in polygon if isinstance(point, list) and len(point) >= 2]
    ys = [float(point[1]) for point in polygon if isinstance(point, list) and len(point) >= 2]
    if not xs or not ys:
        raise ValueError(f"Overlay polygon {overlay_path} did not contain any valid points.")
    return {
        "min_x": min(xs),
        "min_y": min(ys),
        "max_x": max(xs),
        "max_y": max(ys),
    }


def _rgba_from_payload(payload: bytes) -> np.ndarray:
    with MemoryFile(payload) as memory_file:
        with memory_file.open() as dataset:
            raster = dataset.read()
            if dataset.count == 4:
                return np.moveaxis(raster, 0, -1).astype(np.uint8, copy=False)
            if dataset.count == 3:
                rgb = np.moveaxis(raster, 0, -1).astype(np.uint8, copy=False)
                alpha = np.full((dataset.height, dataset.width, 1), 255, dtype=np.uint8)
                return np.concatenate([rgb, alpha], axis=-1)
            if dataset.count == 1:
                indexed = raster[0]
                try:
                    colormap = dataset.colormap(1)
                except ValueError:
                    colormap = {}
                if colormap:
                    lut = np.zeros((256, 4), dtype=np.uint8)
                    for color_index, rgba in colormap.items():
                        lut[int(color_index)] = np.array(rgba, dtype=np.uint8)
                    return lut[indexed]
                alpha = np.full(indexed.shape + (1,), 255, dtype=np.uint8)
                grayscale = indexed[..., None].astype(np.uint8, copy=False)
                return np.concatenate([grayscale, grayscale, grayscale, alpha], axis=-1)
    raise ValueError("Unsupported tile payload; expected PNG or JPEG imagery.")


def _alpha_composite(background: np.ndarray, foreground: np.ndarray) -> np.ndarray:
    if background.shape != foreground.shape:
        raise ValueError("Cannot alpha-composite tiles of different shapes.")
    background_float = background.astype(np.float32) / 255.0
    foreground_float = foreground.astype(np.float32) / 255.0
    foreground_alpha = foreground_float[..., 3:4]
    background_alpha = background_float[..., 3:4]
    output_alpha = foreground_alpha + background_alpha * (1.0 - foreground_alpha)
    safe_alpha = np.where(output_alpha <= 0.0, 1.0, output_alpha)
    output_rgb = (
        foreground_float[..., :3] * foreground_alpha
        + background_float[..., :3] * background_alpha * (1.0 - foreground_alpha)
    ) / safe_alpha
    output = np.concatenate([output_rgb, output_alpha], axis=-1)
    return np.clip(np.round(output * 255.0), 0, 255).astype(np.uint8)


def _fetch_binary(url: str, *, timeout_sec: float = 30.0) -> tuple[bytes, dict[str, Any]]:
    try:
        with urlopen(url, timeout=timeout_sec) as response:
            payload = response.read()
            return payload, {
                "http_status": getattr(response, "status", None),
                "content_type": response.headers.get("Content-Type"),
                "content_length_header": response.headers.get("Content-Length"),
            }
    except HTTPError as exc:
        body = ""
        try:
            body = exc.read(240).decode("utf-8", errors="ignore")
        except Exception:
            body = ""
        raise RuntimeError(f"HTTP {exc.code} {exc.reason}: {body}") from exc
    except URLError as exc:
        raise RuntimeError(repr(exc)) from exc


def _build_tianditu_tile_url(
    *,
    layer: str,
    tile_x: int,
    tile_y: int,
    zoom: int,
    key: str,
    subdomain: str,
) -> str:
    query = urlencode(
        {
            "SERVICE": "WMTS",
            "REQUEST": "GetTile",
            "VERSION": "1.0.0",
            "LAYER": layer,
            "STYLE": "default",
            "TILEMATRIXSET": "w",
            "FORMAT": "tiles",
            "TILEMATRIX": str(zoom),
            "TILEROW": str(tile_y),
            "TILECOL": str(tile_x),
            "tk": key,
        }
    )
    return f"https://{subdomain}.tianditu.gov.cn/{layer}_w/wmts?{query}"


def _local_anchor_bounds_for_tile_range(
    *,
    manifest: dict[str, Any],
    zoom: int,
    min_tile_x: int,
    min_tile_y: int,
    max_tile_x: int,
    max_tile_y: int,
) -> dict[str, float]:
    west_longitude = _tile_x_to_longitude(min_tile_x, zoom)
    east_longitude = _tile_x_to_longitude(max_tile_x + 1, zoom)
    north_latitude = _tile_y_to_latitude(min_tile_y, zoom)
    south_latitude = _tile_y_to_latitude(max_tile_y + 1, zoom)
    corners_wgs84 = [
        (west_longitude, north_latitude),
        (east_longitude, north_latitude),
        (east_longitude, south_latitude),
        (west_longitude, south_latitude),
    ]
    corners_local = [wgs84_to_local_xy(lon, lat, manifest=manifest) for lon, lat in corners_wgs84]
    xs = [point[0] for point in corners_local]
    ys = [point[1] for point in corners_local]
    return {
        "min_x": round(min(xs), 3),
        "min_y": round(min(ys), 3),
        "max_x": round(max(xs), 3),
        "max_y": round(max(ys), 3),
    }


def build_tianditu_reference_mosaic(
    *,
    normalized_city_dir: Path,
    overlay_polygon_path: Path,
    env_file_path: Path,
    output_image_path: Path,
    output_config_path: Path,
    output_report_path: Path,
    zoom: int = 17,
    base_layer: str = "img",
    label_layer: str | None = "cia",
    padding_tiles: int = 0,
    image_opacity: float = 0.72,
    subdomain: str = "t0",
    timeout_sec: float = 30.0,
) -> Path:
    manifest = read_city_manifest(normalized_city_dir)
    overlay_bounds = _overlay_local_bounds(overlay_polygon_path)
    local_corners = [
        (overlay_bounds["min_x"], overlay_bounds["min_y"]),
        (overlay_bounds["max_x"], overlay_bounds["min_y"]),
        (overlay_bounds["max_x"], overlay_bounds["max_y"]),
        (overlay_bounds["min_x"], overlay_bounds["max_y"]),
    ]
    wgs84_corners = [local_xy_to_wgs84(x, y, manifest=manifest) for x, y in local_corners]
    longitudes = [point[0] for point in wgs84_corners]
    latitudes = [point[1] for point in wgs84_corners]

    min_tile_x = _slippy_tile_x(min(longitudes), zoom) - padding_tiles
    max_tile_x = _slippy_tile_x(max(longitudes), zoom) + padding_tiles
    min_tile_y = _slippy_tile_y(max(latitudes), zoom) - padding_tiles
    max_tile_y = _slippy_tile_y(min(latitudes), zoom) + padding_tiles
    tile_count = 2**zoom
    min_tile_x = max(0, min_tile_x)
    min_tile_y = max(0, min_tile_y)
    max_tile_x = min(tile_count - 1, max_tile_x)
    max_tile_y = min(tile_count - 1, max_tile_y)
    if min_tile_x > max_tile_x or min_tile_y > max_tile_y:
        raise ValueError("Computed tile range is invalid; check overlay bounds and zoom level.")

    env_values = _read_simple_env(env_file_path)
    key_name, key = _resolve_env_secret(
        env_values,
        candidates=TIANDITU_KEY_ENV_CANDIDATES,
        provider_name="TianDiTu",
    )

    mosaic_width = (max_tile_x - min_tile_x + 1) * TIANDITU_WMTS_TILE_SIZE
    mosaic_height = (max_tile_y - min_tile_y + 1) * TIANDITU_WMTS_TILE_SIZE
    base_mosaic = np.zeros((mosaic_height, mosaic_width, 4), dtype=np.uint8)
    label_mosaic = np.zeros((mosaic_height, mosaic_width, 4), dtype=np.uint8) if label_layer else None
    fetched_tiles: list[dict[str, Any]] = []

    for tile_y in range(min_tile_y, max_tile_y + 1):
        for tile_x in range(min_tile_x, max_tile_x + 1):
            tile_top = (tile_y - min_tile_y) * TIANDITU_WMTS_TILE_SIZE
            tile_left = (tile_x - min_tile_x) * TIANDITU_WMTS_TILE_SIZE
            tile_bottom = tile_top + TIANDITU_WMTS_TILE_SIZE
            tile_right = tile_left + TIANDITU_WMTS_TILE_SIZE

            base_url = _build_tianditu_tile_url(
                layer=base_layer,
                tile_x=tile_x,
                tile_y=tile_y,
                zoom=zoom,
                key=key,
                subdomain=subdomain,
            )
            base_payload, base_response = _fetch_binary(base_url, timeout_sec=timeout_sec)
            base_mosaic[tile_top:tile_bottom, tile_left:tile_right] = _rgba_from_payload(base_payload)
            fetched_tiles.append(
                {
                    "layer": base_layer,
                    "tile_x": tile_x,
                    "tile_y": tile_y,
                    "http_status": base_response.get("http_status"),
                    "content_type": base_response.get("content_type"),
                    "bytes": len(base_payload),
                }
            )

            if label_layer and label_mosaic is not None:
                label_url = _build_tianditu_tile_url(
                    layer=label_layer,
                    tile_x=tile_x,
                    tile_y=tile_y,
                    zoom=zoom,
                    key=key,
                    subdomain=subdomain,
                )
                label_payload, label_response = _fetch_binary(label_url, timeout_sec=timeout_sec)
                label_mosaic[tile_top:tile_bottom, tile_left:tile_right] = _rgba_from_payload(label_payload)
                fetched_tiles.append(
                    {
                        "layer": label_layer,
                        "tile_x": tile_x,
                        "tile_y": tile_y,
                        "http_status": label_response.get("http_status"),
                        "content_type": label_response.get("content_type"),
                        "bytes": len(label_payload),
                    }
                )

    composed = base_mosaic if label_mosaic is None else _alpha_composite(base_mosaic, label_mosaic)
    output_image_path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(
        output_image_path,
        "w",
        driver="PNG",
        width=mosaic_width,
        height=mosaic_height,
        count=4,
        dtype="uint8",
    ) as dataset:
        dataset.write(np.moveaxis(composed, -1, 0))

    anchor_bounds = _local_anchor_bounds_for_tile_range(
        manifest=manifest,
        zoom=zoom,
        min_tile_x=min_tile_x,
        min_tile_y=min_tile_y,
        max_tile_x=max_tile_x,
        max_tile_y=max_tile_y,
    )

    relative_image_path = Path(
        os.path.relpath(output_image_path.resolve(), start=output_config_path.parent.resolve())
    )

    overlay_id = output_config_path.stem.replace(".local", "")
    config_payload = {
        "overlay_id": overlay_id,
        "display_name": f"TianDiTu WMTS {base_layer}{'+' + label_layer if label_layer else ''} z{zoom}",
        "coordinate_space": "local_meters",
        "image_path": str(relative_image_path),
        "anchor_bounds": anchor_bounds,
        "opacity": round(max(0.05, min(1.0, image_opacity)), 3),
        "notes": [
            "Generated from TianDiTu WMTS tiles for local research preview.",
            "This is a north-up reference mosaic, not project truth data.",
            "Manual alignment may still be required for final preview tuning.",
        ],
        "source": {
            "provider": "TianDiTu",
            "dataset": "WMTS",
            "base_layer": base_layer,
            "label_layer": label_layer,
            "zoom": zoom,
        },
    }
    output_config_path.parent.mkdir(parents=True, exist_ok=True)
    write_json(output_config_path, config_payload)

    report_payload = {
        "provider": "tianditu-wmts",
        "ok": True,
        "requested_at": utc_now_iso(),
        "normalized_city_dir": str(normalized_city_dir.resolve()),
        "overlay_polygon_path": str(overlay_polygon_path.resolve()),
        "env_file_path": str(env_file_path.resolve()),
        "key_name": key_name,
        "base_layer": base_layer,
        "label_layer": label_layer,
        "zoom": zoom,
        "subdomain": subdomain,
        "padding_tiles": padding_tiles,
        "requested_local_bounds": overlay_bounds,
        "requested_bbox_wgs84": {
            "min_lng": round(min(longitudes), 6),
            "min_lat": round(min(latitudes), 6),
            "max_lng": round(max(longitudes), 6),
            "max_lat": round(max(latitudes), 6),
        },
        "tile_range": {
            "min_x": min_tile_x,
            "max_x": max_tile_x,
            "min_y": min_tile_y,
            "max_y": max_tile_y,
            "count_x": max_tile_x - min_tile_x + 1,
            "count_y": max_tile_y - min_tile_y + 1,
            "count_total": (max_tile_x - min_tile_x + 1) * (max_tile_y - min_tile_y + 1),
        },
        "output_image_path": str(output_image_path.resolve()),
        "output_config_path": str(output_config_path.resolve()),
        "output_image_size_px": {
            "width": mosaic_width,
            "height": mosaic_height,
        },
        "anchor_bounds": anchor_bounds,
        "tiles": fetched_tiles,
    }
    write_json(output_report_path, report_payload)
    return output_report_path
