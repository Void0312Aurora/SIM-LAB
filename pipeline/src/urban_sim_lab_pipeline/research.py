from __future__ import annotations

from pathlib import Path
import json
import math
import shutil
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen

from .geo import build_wgs84_to_local_transformer, read_city_manifest, wgs84_to_local_xy
from .serialization import utc_now_iso, write_json


SUPPORTED_STATIC_IMAGE_PROVIDERS = (
    "tencent",
    "tianditu-static",
    "tianditu-wmts",
)

TENCENT_KEY_ENV_CANDIDATES = (
    "TENCENT_MAP_KEY",
    "QQ_MAP_KEY",
    "TX_MAP_KEY",
    "TENCENT_LBS_KEY",
    "TX_KEY",
)

TIANDITU_KEY_ENV_CANDIDATES = (
    "TIANDITU_KEY",
    "TDT_KEY",
    "TIAN_KEY",
    "TIANDITU_TOKEN",
)

SUPPORTED_ENHANCEMENT_LAYERS = (
    "roads",
    "roads_walk",
    "pedestrian_areas",
    "landuse",
    "poi",
    "barriers",
)


def _empty_layers() -> dict[str, list[Any]]:
    return {layer_name: [] for layer_name in SUPPORTED_ENHANCEMENT_LAYERS}


def _read_simple_env(path: Path) -> dict[str, str]:
    if not path.exists():
        raise FileNotFoundError(f"Env file not found: {path}")
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("export "):
            stripped = stripped.removeprefix("export ").strip()
        if "=" in stripped:
            key, value = stripped.split("=", 1)
        elif ":" in stripped:
            key, value = stripped.split(":", 1)
        else:
            parts = stripped.split(None, 1)
            if len(parts) != 2:
                continue
            key, value = parts
        normalized_key = key.strip()
        normalized_value = value.strip().strip('"').strip("'")
        if normalized_key:
            values[normalized_key] = normalized_value
    return values


def _resolve_env_secret(env_values: dict[str, str], *, candidates: tuple[str, ...], provider_name: str) -> tuple[str, str]:
    for candidate in candidates:
        value = env_values.get(candidate)
        if value:
            return candidate, value
    candidate_text = ", ".join(candidates)
    raise KeyError(f"Could not find a {provider_name} key in the env file. Tried: {candidate_text}")


def _mask_secret(text: str, secret: str) -> str:
    if not secret:
        return text
    return text.replace(secret, "***")


def _parse_image_size(size: str) -> tuple[int, int]:
    normalized = size.lower().replace("x", "*")
    if "*" not in normalized:
        raise ValueError(f"Unsupported size format {size!r}; expected WIDTH*HEIGHT.")
    width_text, height_text = normalized.split("*", 1)
    width = int(width_text)
    height = int(height_text)
    if width <= 0 or height <= 0:
        raise ValueError("Image size must be positive.")
    return width, height


def _slippy_tile_xy(*, longitude: float, latitude: float, zoom: int) -> tuple[int, int]:
    latitude_radians = math.radians(latitude)
    tile_count = 2**zoom
    tile_x = int((longitude + 180.0) / 360.0 * tile_count)
    tile_y = int((1.0 - math.asinh(math.tan(latitude_radians)) / math.pi) / 2.0 * tile_count)
    return tile_x, tile_y


def _fetch_binary_asset(
    *,
    url: str,
    output_path: Path,
    masked_url: str,
    provider: str,
    extra_report_fields: dict[str, Any] | None = None,
    timeout_sec: float = 30.0,
) -> dict[str, Any]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {
        "provider": provider,
        "url": masked_url,
        "output": str(output_path.resolve()),
        "requested_at": utc_now_iso(),
    }
    if extra_report_fields:
        report.update(extra_report_fields)
    try:
        with urlopen(url, timeout=timeout_sec) as response:
            payload = response.read()
            output_path.write_bytes(payload)
            content_type = response.headers.get("Content-Type") or ""
            is_image = content_type.lower().startswith("image/")
            report.update(
                {
                    "ok": is_image,
                    "http_status": getattr(response, "status", None),
                    "content_type": content_type,
                    "bytes_written": len(payload),
                }
            )
            if not is_image:
                report["response_sample"] = payload[:240].decode("utf-8", errors="ignore")
            return report
    except HTTPError as exc:
        response_sample = None
        try:
            response_sample = exc.read()[:240].decode("utf-8", errors="ignore")
        except Exception:
            response_sample = None
        report.update(
            {
                "ok": False,
                "error": f"HTTP {exc.code} {exc.reason}",
            }
        )
        if response_sample:
            report["response_sample"] = response_sample
        return report
    except URLError as exc:
        report.update(
            {
                "ok": False,
                "error": repr(exc),
            }
        )
        return report


def fetch_static_research_image(
    *,
    provider: str,
    center_lat: float,
    center_lng: float,
    zoom: int,
    output_path: Path,
    report_path: Path,
    env_file_path: Path,
    size: str = "512*512",
    maptype: str = "roadmap",
    tdt_layers: str = "vec_w,cva_w",
    tdt_layer: str = "vec",
    timeout_sec: float = 30.0,
) -> Path:
    if provider not in SUPPORTED_STATIC_IMAGE_PROVIDERS:
        supported = ", ".join(SUPPORTED_STATIC_IMAGE_PROVIDERS)
        raise ValueError(f"Unsupported static image provider {provider!r}. Supported values: {supported}")

    env_values = _read_simple_env(env_file_path)
    width, height = _parse_image_size(size)

    if provider == "tencent":
        key_name, secret = _resolve_env_secret(
            env_values,
            candidates=TENCENT_KEY_ENV_CANDIDATES,
            provider_name="Tencent",
        )
        query = urlencode(
            {
                "center": f"{center_lat:.6f},{center_lng:.6f}",
                "zoom": str(zoom),
                "size": f"{width}*{height}",
                "maptype": maptype,
                "key": secret,
            }
        )
        url = f"https://apis.map.qq.com/ws/staticmap/v2/?{query}"
        report = _fetch_binary_asset(
            url=url,
            output_path=output_path,
            masked_url=_mask_secret(url, secret),
            provider=provider,
            extra_report_fields={
                "key_name": key_name,
                "maptype": maptype,
                "center_lat": center_lat,
                "center_lng": center_lng,
                "zoom": zoom,
                "size": f"{width}*{height}",
                "kind": "staticmap",
            },
            timeout_sec=timeout_sec,
        )
        write_json(report_path, report)
        return report_path

    key_name, secret = _resolve_env_secret(
        env_values,
        candidates=TIANDITU_KEY_ENV_CANDIDATES,
        provider_name="TianDiTu",
    )

    if provider == "tianditu-static":
        query = urlencode(
            {
                "center": f"{center_lng:.6f},{center_lat:.6f}",
                "width": str(width),
                "height": str(height),
                "zoom": str(zoom),
                "layers": tdt_layers,
                "tk": secret,
            }
        )
        url = f"https://api.tianditu.gov.cn/staticimage?{query}"
        report = _fetch_binary_asset(
            url=url,
            output_path=output_path,
            masked_url=_mask_secret(url, secret),
            provider=provider,
            extra_report_fields={
                "key_name": key_name,
                "center_lat": center_lat,
                "center_lng": center_lng,
                "zoom": zoom,
                "size": f"{width}*{height}",
                "layers": tdt_layers,
                "kind": "staticimage",
            },
            timeout_sec=timeout_sec,
        )
        write_json(report_path, report)
        return report_path

    tile_x, tile_y = _slippy_tile_xy(
        longitude=center_lng,
        latitude=center_lat,
        zoom=zoom,
    )
    query = urlencode(
        {
            "SERVICE": "WMTS",
            "REQUEST": "GetTile",
            "VERSION": "1.0.0",
            "LAYER": tdt_layer,
            "STYLE": "default",
            "TILEMATRIXSET": "w",
            "FORMAT": "tiles",
            "TILEMATRIX": str(zoom),
            "TILEROW": str(tile_y),
            "TILECOL": str(tile_x),
            "tk": secret,
        }
    )
    url = f"https://t0.tianditu.gov.cn/{tdt_layer}_w/wmts?{query}"
    report = _fetch_binary_asset(
        url=url,
        output_path=output_path,
        masked_url=_mask_secret(url, secret),
        provider=provider,
        extra_report_fields={
            "key_name": key_name,
            "center_lat": center_lat,
            "center_lng": center_lng,
            "zoom": zoom,
            "tile_x": tile_x,
            "tile_y": tile_y,
            "layer": tdt_layer,
            "kind": "wmts_tile",
        },
        timeout_sec=timeout_sec,
    )
    write_json(report_path, report)
    return report_path


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_layer(output_dir: Path, layer_filename: str, payload: Any) -> None:
    write_json(output_dir / layer_filename, payload)


def _slugify(value: str) -> str:
    lowered = value.lower().strip()
    safe_chars = [char if char.isalnum() else "_" for char in lowered]
    slug = "".join(safe_chars).strip("_")
    while "__" in slug:
        slug = slug.replace("__", "_")
    return slug or "item"


def _first_non_empty(*values: Any) -> str | None:
    for value in values:
        if value is None:
            continue
        if isinstance(value, str):
            stripped = value.strip()
            if stripped:
                return stripped
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _coerce_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            return float(stripped)
        except ValueError:
            return None
    return None


def _coerce_lng_lat(location: Any) -> tuple[float, float] | None:
    if isinstance(location, dict):
        longitude = _coerce_number(location.get("lng", location.get("lon", location.get("x"))))
        latitude = _coerce_number(location.get("lat", location.get("y")))
        if longitude is None or latitude is None:
            return None
        return longitude, latitude
    if isinstance(location, list) and len(location) >= 2:
        first = _coerce_number(location[0])
        second = _coerce_number(location[1])
        if first is None or second is None:
            return None
        if abs(first) <= 90.0 and abs(second) <= 180.0:
            return second, first
        return first, second
    return None


def _local_path_length(points: list[list[float]]) -> float:
    if len(points) < 2:
        return 0.0
    total = 0.0
    for start, ending in zip(points, points[1:]):
        total += math.hypot(ending[0] - start[0], ending[1] - start[1])
    return round(total, 2)


def _canonical_linestring_key(points: list[Any]) -> tuple[tuple[float, float], ...]:
    normalized = tuple(
        (round(float(point[0]), 3), round(float(point[1]), 3))
        for point in points
        if isinstance(point, list) and len(point) >= 2
    )
    reversed_normalized = tuple(reversed(normalized))
    return min(normalized, reversed_normalized) if normalized else ()


def _canonical_polygon_key(points: list[Any]) -> tuple[tuple[float, float], ...]:
    normalized = [
        (round(float(point[0]), 3), round(float(point[1]), 3))
        for point in points
        if isinstance(point, list) and len(point) >= 2
    ]
    if len(normalized) > 1 and normalized[0] == normalized[-1]:
        normalized = normalized[:-1]
    if not normalized:
        return ()
    forward = tuple(normalized)
    backward = tuple(reversed(normalized))
    return min(forward, backward)


def _poi_key(item: dict[str, Any]) -> tuple[Any, ...]:
    position = item.get("position", {})
    x = round(float(position.get("x", 0.0)), 3) if isinstance(position, dict) else 0.0
    z = round(float(position.get("z", position.get("y", 0.0))), 3) if isinstance(position, dict) else 0.0
    name = str(item.get("name") or item.get("id") or "").strip().lower()
    return name, x, z


def _merge_unique_items(
    base_items: list[dict[str, Any]],
    extra_items: list[dict[str, Any]],
    *,
    key_builder,
) -> list[dict[str, Any]]:
    merged = list(base_items)
    seen_ids = {str(item.get("id")) for item in base_items if str(item.get("id") or "").strip()}
    seen_keys = {key_builder(item) for item in base_items}
    for item in extra_items:
        item_id = str(item.get("id") or "").strip()
        item_key = key_builder(item)
        if item_id and item_id in seen_ids:
            continue
        if item_key in seen_keys:
            continue
        merged.append(item)
        if item_id:
            seen_ids.add(item_id)
        seen_keys.add(item_key)
    return merged


def load_enhancement_bundle(path: Path) -> dict[str, Any]:
    payload = _read_json(path)
    coordinate_space = payload.get("coordinate_space")
    if coordinate_space != "local_meters":
        raise ValueError(
            f"Unsupported enhancement bundle coordinate_space {coordinate_space!r}; expected 'local_meters'."
        )
    layers = payload.get("layers")
    if not isinstance(layers, dict):
        raise ValueError("Enhancement bundle must define a 'layers' object.")
    normalized_layers = _empty_layers()
    for layer_name in SUPPORTED_ENHANCEMENT_LAYERS:
        layer_items = layers.get(layer_name, [])
        if not isinstance(layer_items, list):
            raise ValueError(f"Enhancement layer {layer_name!r} must be a list.")
        normalized_layers[layer_name] = layer_items
    payload["layers"] = normalized_layers
    payload.setdefault("bundle_id", path.stem)
    payload.setdefault("display_name", payload["bundle_id"])
    payload["source_path"] = str(path.resolve())
    return payload


def _build_bundle(
    *,
    bundle_id: str,
    display_name: str,
    source: dict[str, Any],
    notes: list[str],
    layers: dict[str, list[Any]],
) -> dict[str, Any]:
    stats = {
        layer_name: len(layer_items)
        for layer_name, layer_items in layers.items()
        if layer_items
    }
    return {
        "bundle_id": bundle_id,
        "display_name": display_name,
        "coordinate_space": "local_meters",
        "compiled_at": utc_now_iso(),
        "source": source,
        "notes": notes,
        "layers": layers,
        "stats": stats,
    }


def import_tencent_place_search(
    *,
    normalized_city_dir: Path,
    input_json_path: Path,
    output_bundle_path: Path,
    bundle_id: str | None = None,
    display_name: str | None = None,
    include_subpois: bool = True,
) -> Path:
    manifest = read_city_manifest(normalized_city_dir)
    transformer = build_wgs84_to_local_transformer(manifest)
    payload = _read_json(input_json_path)
    status = payload.get("status")
    if status not in (None, 0):
        raise ValueError(f"Tencent place search payload status is not OK: {status!r}")
    data = payload.get("data")
    if not isinstance(data, list):
        raise ValueError("Tencent place search payload does not contain a data[] list.")

    poi_items: list[dict[str, Any]] = []

    def append_poi(item: dict[str, Any], *, parent_record_id: str | None = None, item_index: int = 0) -> None:
        raw_id = _first_non_empty(item.get("id"), item.get("uid"), item.get("title"), f"idx_{item_index}")
        title = _first_non_empty(item.get("title"), item.get("name"), raw_id)
        location = _coerce_lng_lat(item.get("location"))
        if raw_id is None or title is None or location is None:
            return
        longitude, latitude = location
        local_x, local_y = wgs84_to_local_xy(
            longitude,
            latitude,
            manifest=manifest,
            transformer=transformer,
        )
        category = _first_non_empty(item.get("category"), item.get("type"), "tencent_place")
        poi_id = f"poi_tencent_{_slugify(str(raw_id))}"
        if parent_record_id:
            poi_id = f"{poi_id}_sub_{_slugify(parent_record_id)}"
        poi_items.append(
            {
                "id": poi_id,
                "class": _slugify(category),
                "name": title,
                "address": _first_non_empty(item.get("address")),
                "position": {"x": local_x, "z": local_y},
                "linked_building_id": None,
                "parent_poi_id": f"poi_tencent_{_slugify(parent_record_id)}" if parent_record_id else None,
                "source": {
                    "provider": "Tencent Maps",
                    "dataset": "WebService Place Search",
                    "record_id": str(raw_id),
                    "query_path": str(input_json_path.resolve()),
                },
                "confidence": 0.82 if parent_record_id else 0.88,
                "location_wgs84": {"lng": round(longitude, 6), "lat": round(latitude, 6)},
                "category_raw": category,
            }
        )

    for index, item in enumerate(data):
        if not isinstance(item, dict):
            continue
        append_poi(item, item_index=index)
        if include_subpois:
            subpois = item.get("sub_pois", item.get("subpois", []))
            if isinstance(subpois, list):
                parent_id = _first_non_empty(item.get("id"), item.get("uid"), f"idx_{index}")
                for sub_index, subpoi in enumerate(subpois):
                    if isinstance(subpoi, dict):
                        append_poi(subpoi, parent_record_id=parent_id, item_index=sub_index)

    bundle = _build_bundle(
        bundle_id=bundle_id or f"{manifest['city_id']}_tencent_place_search_v1",
        display_name=display_name or "Tencent Place Search Import",
        source={
            "provider": "Tencent Maps",
            "dataset": "WebService Place Search",
            "license": "See Tencent LBS terms and local research notes",
        },
        notes=[
            "Imported from a saved Tencent place search JSON response.",
            "Coordinates were projected into the normalized city's local meter-space using city_manifest.local_crs and origin.",
        ],
        layers={
            **_empty_layers(),
            "poi": poi_items,
        },
    )
    write_json(output_bundle_path, bundle)
    return output_bundle_path


def _decode_tencent_polyline(polyline: Any) -> list[tuple[float, float]]:
    if isinstance(polyline, str):
        points: list[tuple[float, float]] = []
        for chunk in polyline.split(";"):
            if not chunk.strip():
                continue
            parts = [part.strip() for part in chunk.split(",")]
            if len(parts) < 2:
                continue
            first = _coerce_number(parts[0])
            second = _coerce_number(parts[1])
            if first is None or second is None:
                continue
            if abs(first) <= 90.0 and abs(second) <= 180.0:
                points.append((second, first))
            else:
                points.append((first, second))
        return points

    if isinstance(polyline, list):
        if polyline and all(isinstance(item, dict) for item in polyline):
            points = []
            for item in polyline:
                lng_lat = _coerce_lng_lat(item)
                if lng_lat is not None:
                    points.append(lng_lat)
            return points

        if polyline and all(isinstance(item, list) and len(item) >= 2 for item in polyline):
            points = []
            for item in polyline:
                lng_lat = _coerce_lng_lat(item)
                if lng_lat is not None:
                    points.append(lng_lat)
            return points

        numeric_values = [_coerce_number(item) for item in polyline]
        if numeric_values and all(value is not None for value in numeric_values):
            coors = [float(value) for value in numeric_values if value is not None]
            if len(coors) >= 4 and len(coors) % 2 == 0:
                decoded = coors[:2]
                for index in range(2, len(coors)):
                    decoded.append(decoded[index - 2] + coors[index] / 1000000.0)
                points = []
                for index in range(0, len(decoded), 2):
                    latitude = decoded[index]
                    longitude = decoded[index + 1]
                    points.append((longitude, latitude))
                return points
    return []


def _route_name(route: dict[str, Any], *, fallback: str) -> str:
    route_name = _first_non_empty(route.get("direction"), route.get("mode"))
    if route_name:
        return route_name
    steps = route.get("steps", [])
    if isinstance(steps, list):
        for step in steps:
            if not isinstance(step, dict):
                continue
            road_name = _first_non_empty(step.get("road_name"), step.get("dir_desc"))
            if road_name:
                return road_name
    return fallback


def import_tencent_route(
    *,
    normalized_city_dir: Path,
    input_json_path: Path,
    output_bundle_path: Path,
    route_index: int = 0,
    route_mode: str = "walking",
    bundle_id: str | None = None,
    display_name: str | None = None,
) -> Path:
    manifest = read_city_manifest(normalized_city_dir)
    transformer = build_wgs84_to_local_transformer(manifest)
    payload = _read_json(input_json_path)
    status = payload.get("status")
    if status not in (None, 0):
        raise ValueError(f"Tencent route payload status is not OK: {status!r}")
    result = payload.get("result", {})
    routes = result.get("routes")
    if not isinstance(routes, list) or not routes:
        raise ValueError("Tencent route payload does not contain result.routes[].")
    if route_index < 0 or route_index >= len(routes):
        raise IndexError(f"Requested route_index {route_index} outside available range 0..{len(routes) - 1}")

    route = routes[route_index]
    if not isinstance(route, dict):
        raise ValueError("Selected route entry is not an object.")
    polyline = route.get("polyline")
    points_wgs84 = _decode_tencent_polyline(polyline)
    if len(points_wgs84) < 2:
        raise ValueError("Selected Tencent route does not contain a decodable polyline with at least two points.")

    centerline = [
        list(
            wgs84_to_local_xy(
                longitude,
                latitude,
                manifest=manifest,
                transformer=transformer,
            )
        )
        for longitude, latitude in points_wgs84
    ]
    inferred_mode = str(route.get("mode") or route_mode or "walking").strip().lower()
    is_drive_mode = inferred_mode == "driving"
    target_layer = "roads" if is_drive_mode else "roads_walk"
    network_role = "drive" if is_drive_mode else "walk"
    route_record_id = f"{route_index}"
    route_distance = _coerce_number(route.get("distance"))
    route_name = _route_name(route, fallback=f"Tencent {network_role} route {route_index}")
    road_item = {
        "id": f"road_{network_role}_tencent_{route_index}",
        "source_record_id": route_record_id,
        "class": "tencent_route_reference",
        "network_role": network_role,
        "name": route_name,
        "centerline": centerline,
        "length_m": round(route_distance, 2) if route_distance is not None else _local_path_length(centerline),
        "lanes": None,
        "width_m": 8.0 if is_drive_mode else 3.0,
        "is_vehicle_accessible": is_drive_mode,
        "is_pedestrian_accessible": not is_drive_mode,
        "source": {
            "provider": "Tencent Maps",
            "dataset": "WebService Route Planning",
            "record_id": route_record_id,
            "query_path": str(input_json_path.resolve()),
        },
        "confidence": 0.78,
        "polyline_wgs84": [
            {"lng": round(longitude, 6), "lat": round(latitude, 6)}
            for longitude, latitude in points_wgs84
        ],
    }

    layers = _empty_layers()
    layers[target_layer] = [road_item]
    bundle = _build_bundle(
        bundle_id=bundle_id or f"{manifest['city_id']}_tencent_{network_role}_route_v1",
        display_name=display_name or f"Tencent {network_role.title()} Route Import",
        source={
            "provider": "Tencent Maps",
            "dataset": "WebService Route Planning",
            "license": "See Tencent LBS terms and local research notes",
        },
        notes=[
            "Imported from a saved Tencent route planning JSON response.",
            "The returned polyline was decoded using Tencent's documented delta-compressed route format and projected into local meter-space.",
        ],
        layers=layers,
    )
    write_json(output_bundle_path, bundle)
    return output_bundle_path


def augment_normalized_city(
    *,
    normalized_city_dir: Path,
    enhancement_bundle_paths: list[Path],
    output_dir: Path,
    city_id: str | None = None,
    display_name: str | None = None,
) -> Path:
    source_dir = normalized_city_dir.resolve()
    target_dir = output_dir.resolve()
    if source_dir != target_dir:
        if target_dir.exists():
            raise FileExistsError(f"Output directory already exists: {target_dir}")
        shutil.copytree(source_dir, target_dir)
    manifest = read_city_manifest(target_dir)
    layers = manifest.get("layers", {})

    roads = _read_json(target_dir / layers.get("roads", "roads.json"))
    roads_walk = _read_json(target_dir / layers.get("roads_walk", "roads_walk.json"))
    buildings = _read_json(target_dir / layers.get("buildings", "buildings.json"))
    poi = _read_json(target_dir / layers.get("poi", "poi.json"))
    landuse = _read_json(target_dir / layers.get("landuse", "landuse.json"))
    pedestrian_areas = _read_json(target_dir / layers.get("pedestrian_areas", "pedestrian_areas.json"))
    barriers = _read_json(target_dir / layers.get("barriers", "barriers.json"))

    loaded_bundles = [load_enhancement_bundle(path) for path in enhancement_bundle_paths]
    for bundle in loaded_bundles:
        bundle_layers = bundle.get("layers", {})
        roads = _merge_unique_items(
            roads,
            bundle_layers.get("roads", []),
            key_builder=lambda item: _canonical_linestring_key(item.get("centerline", [])),
        )
        roads_walk = _merge_unique_items(
            roads_walk,
            bundle_layers.get("roads_walk", []),
            key_builder=lambda item: _canonical_linestring_key(item.get("centerline", [])),
        )
        poi = _merge_unique_items(
            poi,
            bundle_layers.get("poi", []),
            key_builder=_poi_key,
        )
        barriers = _merge_unique_items(
            barriers,
            bundle_layers.get("barriers", []),
            key_builder=lambda item: _canonical_linestring_key(item.get("geometry", [])),
        )
        landuse = _merge_unique_items(
            landuse,
            bundle_layers.get("landuse", []),
            key_builder=lambda item: _canonical_polygon_key(item.get("polygon", [])),
        )
        pedestrian_areas = _merge_unique_items(
            pedestrian_areas,
            bundle_layers.get("pedestrian_areas", []),
            key_builder=lambda item: _canonical_polygon_key(item.get("polygon", [])),
        )

        source_ref = bundle.get("source", {})
        provider = str(source_ref.get("provider") or "Research Import")
        dataset = str(source_ref.get("dataset") or bundle.get("display_name") or bundle.get("bundle_id") or "enhancement")
        bundle_source = {
            "provider": provider,
            "dataset": dataset,
            "version": str(bundle.get("bundle_id") or bundle.get("display_name") or "v1"),
            "license": str(source_ref.get("license") or "See local research notes"),
        }
        existing_sources = manifest.get("sources", [])
        if bundle_source not in existing_sources:
            existing_sources.append(bundle_source)
            manifest["sources"] = existing_sources

    if city_id:
        manifest["city_id"] = city_id
    if display_name:
        manifest["display_name"] = display_name
    manifest["compiled_at"] = utc_now_iso()
    manifest["stats"] = {
        "road_count": len(roads),
        "walk_road_count": len(roads_walk),
        "building_count": len(buildings),
    }

    write_json(target_dir / "city_manifest.json", manifest)
    _write_layer(target_dir, layers.get("roads", "roads.json"), roads)
    _write_layer(target_dir, layers.get("roads_walk", "roads_walk.json"), roads_walk)
    _write_layer(target_dir, layers.get("poi", "poi.json"), poi)
    _write_layer(target_dir, layers.get("landuse", "landuse.json"), landuse)
    _write_layer(target_dir, layers.get("pedestrian_areas", "pedestrian_areas.json"), pedestrian_areas)
    _write_layer(target_dir, layers.get("barriers", "barriers.json"), barriers)
    return target_dir
