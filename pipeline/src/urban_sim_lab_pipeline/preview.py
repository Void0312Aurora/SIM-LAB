from __future__ import annotations

from pathlib import Path
import html
import json
import math
from typing import Any

from .overlay import load_overlay_polygon, load_reference_image_overlay
from .research import SUPPORTED_ENHANCEMENT_LAYERS, load_enhancement_bundle


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _format_count(items: list[Any]) -> str:
    return f"{len(items):,}"


def _load_normalized_layers(normalized_city_dir: Path) -> dict[str, Any]:
    manifest = _read_json(normalized_city_dir / "city_manifest.json")
    layers = manifest.get("layers", {})
    roads_walk_path = normalized_city_dir / layers.get("roads_walk", "roads_walk.json")
    return {
        "manifest": manifest,
        "roads": _read_json(normalized_city_dir / layers.get("roads", "roads.json")),
        "roads_walk": _read_json(roads_walk_path) if roads_walk_path.exists() else [],
        "buildings": _read_json(normalized_city_dir / layers.get("buildings", "buildings.json")),
        "pedestrian_areas": _read_json(normalized_city_dir / layers.get("pedestrian_areas", "pedestrian_areas.json")),
        "landuse": _read_json(normalized_city_dir / layers.get("landuse", "landuse.json")),
        "poi": _read_json(normalized_city_dir / layers.get("poi", "poi.json")),
        "barriers": _read_json(normalized_city_dir / layers.get("barriers", "barriers.json")),
    }


def _empty_enhancement_layers() -> dict[str, list[Any]]:
    return {layer_name: [] for layer_name in SUPPORTED_ENHANCEMENT_LAYERS}


def _aggregate_enhancement_layers(bundles: list[dict[str, Any]]) -> dict[str, list[Any]]:
    aggregated = _empty_enhancement_layers()
    for bundle in bundles:
        layers = bundle.get("layers", {})
        for layer_name in SUPPORTED_ENHANCEMENT_LAYERS:
            aggregated[layer_name].extend(layers.get(layer_name, []))
    return aggregated


def _iter_xy_pairs(value: Any):
    if isinstance(value, list):
        if len(value) >= 2 and all(isinstance(item, (int, float)) for item in value[:2]):
            yield float(value[0]), float(value[1])
            return
        for item in value:
            yield from _iter_xy_pairs(item)
    elif isinstance(value, dict):
        if "x" in value and ("z" in value or "y" in value):
            yield float(value["x"]), float(value.get("z", value.get("y", 0.0)))


def _iter_all_points(dataset: dict[str, Any]):
    overlay = dataset.get("overlay_polygon")
    if isinstance(overlay, dict):
        yield from _iter_xy_pairs(overlay.get("polygon", []))
    reference_image = dataset.get("reference_image")
    if isinstance(reference_image, dict):
        anchor_bounds = reference_image.get("anchor_bounds", {})
        if isinstance(anchor_bounds, dict):
            yield float(anchor_bounds.get("min_x", 0.0)), float(anchor_bounds.get("min_y", 0.0))
            yield float(anchor_bounds.get("max_x", 0.0)), float(anchor_bounds.get("max_y", 0.0))
    for road in dataset["roads"]:
        yield from _iter_xy_pairs(road.get("centerline", []))
    for road in dataset["roads_walk"]:
        yield from _iter_xy_pairs(road.get("centerline", []))
    for building in dataset["buildings"]:
        yield from _iter_xy_pairs(building.get("footprint", []))
    for area in dataset["pedestrian_areas"]:
        yield from _iter_xy_pairs(area.get("polygon", []))
    for area in dataset["landuse"]:
        yield from _iter_xy_pairs(area.get("polygon", []))
    for barrier in dataset["barriers"]:
        yield from _iter_xy_pairs(barrier.get("geometry", []))
    for poi in dataset["poi"]:
        if isinstance(poi, dict):
            yield from _iter_xy_pairs(poi.get("position", poi.get("center", {})))
    enhancement_layers = dataset.get("enhancement_layers", {})
    if isinstance(enhancement_layers, dict):
        for road in enhancement_layers.get("roads", []):
            yield from _iter_xy_pairs(road.get("centerline", []))
        for road in enhancement_layers.get("roads_walk", []):
            yield from _iter_xy_pairs(road.get("centerline", []))
        for area in enhancement_layers.get("pedestrian_areas", []):
            yield from _iter_xy_pairs(area.get("polygon", []))
        for area in enhancement_layers.get("landuse", []):
            yield from _iter_xy_pairs(area.get("polygon", []))
        for barrier in enhancement_layers.get("barriers", []):
            yield from _iter_xy_pairs(barrier.get("geometry", []))
        for poi in enhancement_layers.get("poi", []):
            if isinstance(poi, dict):
                yield from _iter_xy_pairs(poi.get("position", poi.get("center", {})))


def _compute_bounds(dataset: dict[str, Any]) -> dict[str, float]:
    points = list(_iter_all_points(dataset))
    if not points:
        return {
            "min_x": -1.0,
            "max_x": 1.0,
            "min_y": -1.0,
            "max_y": 1.0,
        }
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return {
        "min_x": min(xs),
        "max_x": max(xs),
        "min_y": min(ys),
        "max_y": max(ys),
    }


def _make_transform(bounds: dict[str, float]) -> tuple[int, int, float, float, float]:
    padding = 50.0
    data_width = max(1.0, bounds["max_x"] - bounds["min_x"])
    data_height = max(1.0, bounds["max_y"] - bounds["min_y"])
    svg_width = 1400
    svg_height = int(max(900.0, min(1800.0, svg_width * (data_height / data_width))))
    scale = min(
        (svg_width - padding * 2.0) / data_width,
        (svg_height - padding * 2.0) / data_height,
    )
    offset_x = (svg_width - data_width * scale) / 2.0
    offset_y = (svg_height - data_height * scale) / 2.0
    return svg_width, svg_height, scale, offset_x, offset_y


def _project_point(
    x: float,
    y: float,
    *,
    bounds: dict[str, float],
    scale: float,
    offset_x: float,
    offset_y: float,
    svg_height: int,
) -> tuple[float, float]:
    projected_x = offset_x + (x - bounds["min_x"]) * scale
    projected_y = svg_height - (offset_y + (y - bounds["min_y"]) * scale)
    return projected_x, projected_y


def _points_attr(
    points: list[Any],
    *,
    bounds: dict[str, float],
    scale: float,
    offset_x: float,
    offset_y: float,
    svg_height: int,
) -> str:
    projected: list[str] = []
    for x, y in _iter_xy_pairs(points):
        px, py = _project_point(
            x,
            y,
            bounds=bounds,
            scale=scale,
            offset_x=offset_x,
            offset_y=offset_y,
            svg_height=svg_height,
        )
        projected.append(f"{px:.2f},{py:.2f}")
    return " ".join(projected)


def _svg_title(label: str) -> str:
    return f"<title>{html.escape(label)}</title>"


def _canonical_linestring_key(points: list[Any]) -> tuple[tuple[float, float], ...]:
    normalized = tuple((round(x, 3), round(y, 3)) for x, y in _iter_xy_pairs(points))
    reversed_normalized = tuple(reversed(normalized))
    return min(normalized, reversed_normalized)


def _render_buildings(
    buildings: list[dict[str, Any]],
    *,
    bounds: dict[str, float],
    scale: float,
    offset_x: float,
    offset_y: float,
    svg_height: int,
) -> str:
    parts: list[str] = []
    for building in buildings:
        points = _points_attr(
            building.get("footprint", []),
            bounds=bounds,
            scale=scale,
            offset_x=offset_x,
            offset_y=offset_y,
            svg_height=svg_height,
        )
        if not points:
            continue
        name = building.get("name") or building.get("id", "building")
        usage = building.get("usage_class", "building")
        parts.append(
            "<polygon class='building' points='%s'>%s</polygon>"
            % (
                points,
                _svg_title(f"{name} | {usage}"),
            )
        )
    return "".join(parts)


def _render_roads(
    roads: list[dict[str, Any]],
    *,
    class_name: str,
    bounds: dict[str, float],
    scale: float,
    offset_x: float,
    offset_y: float,
    svg_height: int,
) -> str:
    parts: list[str] = []
    seen_geometry_keys: set[tuple[tuple[float, float], ...]] = set()
    for road in roads:
        geometry_key = _canonical_linestring_key(road.get("centerline", []))
        if geometry_key in seen_geometry_keys:
            continue
        seen_geometry_keys.add(geometry_key)
        points = _points_attr(
            road.get("centerline", []),
            bounds=bounds,
            scale=scale,
            offset_x=offset_x,
            offset_y=offset_y,
            svg_height=svg_height,
        )
        if not points:
            continue
        label = road.get("name") or road.get("id", "road")
        road_class = road.get("class", "road")
        parts.append(
            "<polyline class='%s' points='%s'>%s</polyline>"
            % (
                class_name,
                points,
                _svg_title(f"{label} | {road_class}"),
            )
        )
    return "".join(parts)


def _render_polygons(
    items: list[dict[str, Any]],
    *,
    layer_name: str,
    class_name: str,
    bounds: dict[str, float],
    scale: float,
    offset_x: float,
    offset_y: float,
    svg_height: int,
) -> str:
    parts: list[str] = []
    for item in items:
        points = _points_attr(
            item.get("polygon", []),
            bounds=bounds,
            scale=scale,
            offset_x=offset_x,
            offset_y=offset_y,
            svg_height=svg_height,
        )
        if not points:
            continue
        label = item.get("name") or item.get("id") or layer_name
        item_class = item.get("class", layer_name)
        parts.append(
            "<polygon class='%s' points='%s'>%s</polygon>"
            % (
                class_name,
                points,
                _svg_title(f"{label} | {item_class}"),
            )
        )
    return "".join(parts)


def _render_overlay_polygon(
    overlay: dict[str, Any] | None,
    *,
    bounds: dict[str, float],
    scale: float,
    offset_x: float,
    offset_y: float,
    svg_height: int,
) -> str:
    if not overlay:
        return ""
    points = _points_attr(
        overlay.get("polygon", []),
        bounds=bounds,
        scale=scale,
        offset_x=offset_x,
        offset_y=offset_y,
        svg_height=svg_height,
    )
    if not points:
        return ""
    label = overlay.get("display_name") or overlay.get("overlay_id") or "overlay polygon"
    return "<polygon class='overlay-polygon' points='%s'>%s</polygon>" % (
        points,
        _svg_title(str(label)),
    )


def _render_barriers(
    barriers: list[dict[str, Any]],
    *,
    class_name: str,
    bounds: dict[str, float],
    scale: float,
    offset_x: float,
    offset_y: float,
    svg_height: int,
) -> str:
    parts: list[str] = []
    for barrier in barriers:
        points = _points_attr(
            barrier.get("geometry", []),
            bounds=bounds,
            scale=scale,
            offset_x=offset_x,
            offset_y=offset_y,
            svg_height=svg_height,
        )
        if not points:
            continue
        label = barrier.get("name") or barrier.get("id", "barrier")
        item_class = barrier.get("class", "barrier")
        parts.append(
            "<polyline class='%s' points='%s'>%s</polyline>"
            % (
                class_name,
                points,
                _svg_title(f"{label} | {item_class}"),
            )
        )
    return "".join(parts)


def _render_poi(
    poi_items: list[dict[str, Any]],
    *,
    class_name: str,
    bounds: dict[str, float],
    scale: float,
    offset_x: float,
    offset_y: float,
    svg_height: int,
) -> str:
    parts: list[str] = []
    for item in poi_items:
        if not isinstance(item, dict):
            continue
        positions = list(_iter_xy_pairs(item.get("position", item.get("center", {}))))
        if not positions:
            continue
        x, y = positions[0]
        px, py = _project_point(
            x,
            y,
            bounds=bounds,
            scale=scale,
            offset_x=offset_x,
            offset_y=offset_y,
            svg_height=svg_height,
        )
        label = item.get("name") or item.get("id", "poi")
        item_class = item.get("class", "poi")
        parts.append(
            "<circle class='%s' cx='%.2f' cy='%.2f' r='4.5'>%s</circle>"
            % (
                class_name,
                px,
                py,
                _svg_title(f"{label} | {item_class}"),
            )
        )
    return "".join(parts)


def _render_reference_image(
    reference_image: dict[str, Any] | None,
    *,
    bounds: dict[str, float],
    scale: float,
    offset_x: float,
    offset_y: float,
    svg_height: int,
) -> str:
    if not reference_image:
        return ""
    anchor_bounds = reference_image.get("anchor_bounds", {})
    if not isinstance(anchor_bounds, dict):
        return ""
    min_x = float(anchor_bounds.get("min_x", 0.0))
    min_y = float(anchor_bounds.get("min_y", 0.0))
    max_x = float(anchor_bounds.get("max_x", 0.0))
    max_y = float(anchor_bounds.get("max_y", 0.0))
    top_left = _project_point(
        min_x,
        max_y,
        bounds=bounds,
        scale=scale,
        offset_x=offset_x,
        offset_y=offset_y,
        svg_height=svg_height,
    )
    bottom_right = _project_point(
        max_x,
        min_y,
        bounds=bounds,
        scale=scale,
        offset_x=offset_x,
        offset_y=offset_y,
        svg_height=svg_height,
    )
    width = bottom_right[0] - top_left[0]
    height = bottom_right[1] - top_left[1]
    if width <= 0 or height <= 0:
        return ""
    label = str(reference_image.get("display_name") or reference_image.get("overlay_id") or "reference image")
    image_href = reference_image.get("image_href")
    if not isinstance(image_href, str) or not image_href:
        return ""
    opacity = max(0.05, min(1.0, float(reference_image.get("opacity", 0.72))))
    return (
        "<g class='reference-layer'>"
        "<image class='reference-image' href='%s' x='%.2f' y='%.2f' width='%.2f' height='%.2f' opacity='%.3f' preserveAspectRatio='none'>%s</image>"
        "<rect class='reference-frame' x='%.2f' y='%.2f' width='%.2f' height='%.2f'>%s</rect>"
        "</g>"
        % (
            html.escape(image_href),
            top_left[0],
            top_left[1],
            width,
            height,
            opacity,
            _svg_title(label),
            top_left[0],
            top_left[1],
            width,
            height,
            _svg_title(f"{label} bounds"),
        )
    )


def _project_points(
    points: list[Any],
    *,
    bounds: dict[str, float],
    scale: float,
    offset_x: float,
    offset_y: float,
    svg_height: int,
) -> list[tuple[float, float]]:
    return [
        _project_point(
            x,
            y,
            bounds=bounds,
            scale=scale,
            offset_x=offset_x,
            offset_y=offset_y,
            svg_height=svg_height,
        )
        for x, y in _iter_xy_pairs(points)
    ]


def _polyline_label_anchor(projected_points: list[tuple[float, float]]) -> tuple[float, float, float] | None:
    if len(projected_points) < 2:
        return None
    segment_lengths = []
    total_length = 0.0
    for start, ending in zip(projected_points, projected_points[1:]):
        dx = ending[0] - start[0]
        dy = ending[1] - start[1]
        segment_length = math.hypot(dx, dy)
        segment_lengths.append(segment_length)
        total_length += segment_length
    if total_length <= 0.0:
        return None

    target = total_length / 2.0
    traversed = 0.0
    for index, segment_length in enumerate(segment_lengths):
        start = projected_points[index]
        ending = projected_points[index + 1]
        if traversed + segment_length >= target:
            ratio = 0.0 if segment_length == 0.0 else (target - traversed) / segment_length
            px = start[0] + (ending[0] - start[0]) * ratio
            py = start[1] + (ending[1] - start[1]) * ratio
            angle = math.degrees(math.atan2(ending[1] - start[1], ending[0] - start[0]))
            if angle > 90.0:
                angle -= 180.0
            if angle < -90.0:
                angle += 180.0
            return px, py, angle
        traversed += segment_length
    return None


def _polygon_label_anchor(projected_points: list[tuple[float, float]]) -> tuple[float, float] | None:
    if len(projected_points) < 3:
        return None
    cleaned = projected_points[:-1] if projected_points[0] == projected_points[-1] else projected_points
    if not cleaned:
        return None
    area_acc = 0.0
    cx_acc = 0.0
    cy_acc = 0.0
    for index, point in enumerate(cleaned):
        next_point = cleaned[(index + 1) % len(cleaned)]
        cross = point[0] * next_point[1] - next_point[0] * point[1]
        area_acc += cross
        cx_acc += (point[0] + next_point[0]) * cross
        cy_acc += (point[1] + next_point[1]) * cross
    if abs(area_acc) < 1e-9:
        xs = [point[0] for point in cleaned]
        ys = [point[1] for point in cleaned]
        return (sum(xs) / len(xs), sum(ys) / len(ys))
    area_acc *= 0.5
    return (cx_acc / (6.0 * area_acc), cy_acc / (6.0 * area_acc))


def _select_named_roads(roads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    selected: dict[str, dict[str, Any]] = {}
    for road in roads:
        name = str(road.get("name") or "").strip()
        if not name:
            continue
        if float(road.get("length_m", 0.0)) < 60.0:
            continue
        current = selected.get(name)
        if current is None or float(road.get("length_m", 0.0)) > float(current.get("length_m", 0.0)):
            selected[name] = road
    return list(selected.values())


def _render_road_labels(
    roads: list[dict[str, Any]],
    *,
    class_name: str,
    bounds: dict[str, float],
    scale: float,
    offset_x: float,
    offset_y: float,
    svg_height: int,
) -> str:
    parts: list[str] = []
    for road in _select_named_roads(roads):
        projected_points = _project_points(
            road.get("centerline", []),
            bounds=bounds,
            scale=scale,
            offset_x=offset_x,
            offset_y=offset_y,
            svg_height=svg_height,
        )
        anchor = _polyline_label_anchor(projected_points)
        if anchor is None:
            continue
        px, py, angle = anchor
        label = str(road.get("name", "")).strip()
        parts.append(
            "<text class='%s' x='%.2f' y='%.2f' transform='rotate(%.2f %.2f %.2f)'>%s</text>"
            % (class_name, px, py, angle, px, py, html.escape(label))
        )
    return "".join(parts)


def _render_building_labels(
    buildings: list[dict[str, Any]],
    *,
    bounds: dict[str, float],
    scale: float,
    offset_x: float,
    offset_y: float,
    svg_height: int,
) -> str:
    parts: list[str] = []
    for building in buildings:
        label = str(building.get("name") or "").strip()
        if not label:
            continue
        projected_points = _project_points(
            building.get("footprint", []),
            bounds=bounds,
            scale=scale,
            offset_x=offset_x,
            offset_y=offset_y,
            svg_height=svg_height,
        )
        anchor = _polygon_label_anchor(projected_points)
        if anchor is None:
            continue
        parts.append(
            "<text class='building-label' x='%.2f' y='%.2f'>%s</text>"
            % (anchor[0], anchor[1], html.escape(label))
        )
    return "".join(parts)


def _nice_grid_step(data_width: float, data_height: float) -> float:
    target = max(data_width, data_height) / 8.0
    if target <= 0:
        return 100.0
    exponent = math.floor(math.log10(target))
    magnitude = 10**exponent
    for ratio in [1.0, 2.0, 5.0, 10.0]:
        step = magnitude * ratio
        if step >= target:
            return step
    return magnitude * 10.0


def _render_grid(
    *,
    bounds: dict[str, float],
    scale: float,
    offset_x: float,
    offset_y: float,
    svg_width: int,
    svg_height: int,
) -> str:
    data_width = max(1.0, bounds["max_x"] - bounds["min_x"])
    data_height = max(1.0, bounds["max_y"] - bounds["min_y"])
    step = _nice_grid_step(data_width, data_height)
    start_x = math.floor(bounds["min_x"] / step) * step
    end_x = math.ceil(bounds["max_x"] / step) * step
    start_y = math.floor(bounds["min_y"] / step) * step
    end_y = math.ceil(bounds["max_y"] / step) * step

    parts: list[str] = []

    current_x = start_x
    while current_x <= end_x + 1e-9:
        x1, y1 = _project_point(
            current_x,
            bounds["min_y"],
            bounds=bounds,
            scale=scale,
            offset_x=offset_x,
            offset_y=offset_y,
            svg_height=svg_height,
        )
        x2, y2 = _project_point(
            current_x,
            bounds["max_y"],
            bounds=bounds,
            scale=scale,
            offset_x=offset_x,
            offset_y=offset_y,
            svg_height=svg_height,
        )
        parts.append(
            "<line class='grid-line' x1='%.2f' y1='%.2f' x2='%.2f' y2='%.2f' />"
            % (x1, y1, x2, y2)
        )
        current_x += step

    current_y = start_y
    while current_y <= end_y + 1e-9:
        x1, y1 = _project_point(
            bounds["min_x"],
            current_y,
            bounds=bounds,
            scale=scale,
            offset_x=offset_x,
            offset_y=offset_y,
            svg_height=svg_height,
        )
        x2, y2 = _project_point(
            bounds["max_x"],
            current_y,
            bounds=bounds,
            scale=scale,
            offset_x=offset_x,
            offset_y=offset_y,
            svg_height=svg_height,
        )
        parts.append(
            "<line class='grid-line' x1='%.2f' y1='%.2f' x2='%.2f' y2='%.2f' />"
            % (x1, y1, x2, y2)
        )
        current_y += step

    return "".join(parts)


def _summary_items(dataset: dict[str, Any], bounds: dict[str, float]) -> str:
    manifest = dataset["manifest"]
    overlay = dataset.get("overlay_polygon")
    reference_image = dataset.get("reference_image")
    enhancement_bundles = dataset.get("enhancement_bundles", [])
    enhancement_layers = dataset.get("enhancement_layers", _empty_enhancement_layers())
    unique_drive_road_count = len(
        {
            _canonical_linestring_key(road.get("centerline", []))
            for road in dataset["roads"]
            if road.get("centerline")
        }
    )
    unique_walk_road_count = len(
        {
            _canonical_linestring_key(road.get("centerline", []))
            for road in dataset["roads_walk"]
            if road.get("centerline")
        }
    )
    named_road_count = len(
        {
            str(road.get("name")).strip()
            for road in dataset["roads"] + dataset["roads_walk"]
            if str(road.get("name") or "").strip()
        }
    )
    named_building_count = len([building for building in dataset["buildings"] if str(building.get("name") or "").strip()])
    items = [
        ("City ID", manifest.get("city_id", "<unknown>")),
        ("Display Name", manifest.get("display_name", "<unknown>")),
        ("Drive Roads", _format_count(dataset["roads"])),
        ("Walk Roads", _format_count(dataset["roads_walk"])),
        ("Unique Drive Shapes", f"{unique_drive_road_count:,}"),
        ("Unique Walk Shapes", f"{unique_walk_road_count:,}"),
        ("Named Roads", f"{named_road_count:,}"),
        ("Buildings", _format_count(dataset["buildings"])),
        ("Named Buildings", f"{named_building_count:,}"),
        ("Pedestrian Areas", _format_count(dataset["pedestrian_areas"])),
        ("Landuse", _format_count(dataset["landuse"])),
        ("POI", _format_count(dataset["poi"])),
        ("Barriers", _format_count(dataset["barriers"])),
        (
            "Local Bounds",
            "x %.1f..%.1f, y %.1f..%.1f"
            % (bounds["min_x"], bounds["max_x"], bounds["min_y"], bounds["max_y"]),
        ),
        ("Orientation", "North Up, East Right"),
    ]
    if isinstance(overlay, dict):
        items.append(("Active Overlay", str(overlay.get("display_name") or overlay.get("overlay_id") or "polygon")))
    if isinstance(reference_image, dict):
        items.append(
            (
                "Reference Image",
                str(reference_image.get("display_name") or reference_image.get("overlay_id") or "reference"),
            )
        )
    if enhancement_bundles:
        items.append(("Research Bundles", f"{len(enhancement_bundles):,}"))
        items.append(("Research POI", f"{len(enhancement_layers.get('poi', [])):,}"))
        items.append(("Research Walk", f"{len(enhancement_layers.get('roads_walk', [])):,}"))
    return "".join(
        "<div class='metric'><span>%s</span><strong>%s</strong></div>"
        % (html.escape(label), html.escape(value))
        for label, value in items
    )


def _layer_controls(dataset: dict[str, Any]) -> str:
    enhancement_layers = dataset.get("enhancement_layers", _empty_enhancement_layers())
    items = [
        ("grid", "Grid", True),
        ("reference-image", "Reference Image", dataset.get("reference_image") is not None),
        ("overlay-polygon", "Clip Overlay", dataset.get("overlay_polygon") is not None),
        ("landuse", f"Landuse ({_format_count(dataset['landuse'])})", True),
        ("pedestrian", f"Pedestrian Areas ({_format_count(dataset['pedestrian_areas'])})", True),
        ("drive-roads", f"Drive Roads ({_format_count(dataset['roads'])})", True),
        ("walk-roads", f"Walk Roads ({_format_count(dataset['roads_walk'])})", True),
        ("road-labels", "Road Labels", True),
        ("buildings", f"Buildings ({_format_count(dataset['buildings'])})", True),
        ("building-labels", "Building Labels", True),
        ("barriers", f"Barriers ({_format_count(dataset['barriers'])})", True),
        ("poi", f"POI ({_format_count(dataset['poi'])})", True),
        ("research-landuse", f"Research Landuse ({_format_count(enhancement_layers['landuse'])})", bool(enhancement_layers["landuse"])),
        ("research-pedestrian", f"Research Pedestrian ({_format_count(enhancement_layers['pedestrian_areas'])})", bool(enhancement_layers["pedestrian_areas"])),
        ("research-drive-roads", f"Research Drive Routes ({_format_count(enhancement_layers['roads'])})", bool(enhancement_layers["roads"])),
        ("research-walk-roads", f"Research Walk Routes ({_format_count(enhancement_layers['roads_walk'])})", bool(enhancement_layers["roads_walk"])),
        ("research-barriers", f"Research Barriers ({_format_count(enhancement_layers['barriers'])})", bool(enhancement_layers["barriers"])),
        ("research-poi", f"Research POI ({_format_count(enhancement_layers['poi'])})", bool(enhancement_layers["poi"])),
    ]
    return "".join(
        "<label class='toggle'><input type='checkbox' data-layer='%s'%s /><span>%s</span></label>"
        % (
            layer_id,
            " checked" if checked else "",
            html.escape(label),
        )
        for layer_id, label, checked in items
    )


def render_normalized_city_preview(
    *,
    normalized_city_dir: Path,
    output_html: Path,
    title: str | None = None,
    overlay_polygon_path: Path | None = None,
    reference_image_config_path: Path | None = None,
    enhancement_bundle_paths: list[Path] | None = None,
) -> Path:
    dataset = _load_normalized_layers(normalized_city_dir)
    dataset["overlay_polygon"] = load_overlay_polygon(overlay_polygon_path) if overlay_polygon_path else None
    dataset["reference_image"] = (
        load_reference_image_overlay(reference_image_config_path) if reference_image_config_path else None
    )
    dataset["enhancement_bundles"] = [
        load_enhancement_bundle(path)
        for path in (enhancement_bundle_paths or [])
    ]
    dataset["enhancement_layers"] = _aggregate_enhancement_layers(dataset["enhancement_bundles"])
    bounds = _compute_bounds(dataset)
    svg_width, svg_height, scale, offset_x, offset_y = _make_transform(bounds)
    manifest = dataset["manifest"]
    page_title = title or f"Urban Sim Lab Preview | {manifest.get('display_name', manifest.get('city_id', 'normalized-city'))}"

    grid_svg = _render_grid(
        bounds=bounds,
        scale=scale,
        offset_x=offset_x,
        offset_y=offset_y,
        svg_width=svg_width,
        svg_height=svg_height,
    )
    landuse_svg = _render_polygons(
        dataset["landuse"],
        layer_name="landuse",
        class_name="landuse",
        bounds=bounds,
        scale=scale,
        offset_x=offset_x,
        offset_y=offset_y,
        svg_height=svg_height,
    )
    overlay_polygon_svg = _render_overlay_polygon(
        dataset.get("overlay_polygon"),
        bounds=bounds,
        scale=scale,
        offset_x=offset_x,
        offset_y=offset_y,
        svg_height=svg_height,
    )
    reference_image_svg = _render_reference_image(
        dataset.get("reference_image"),
        bounds=bounds,
        scale=scale,
        offset_x=offset_x,
        offset_y=offset_y,
        svg_height=svg_height,
    )
    pedestrian_svg = _render_polygons(
        dataset["pedestrian_areas"],
        layer_name="pedestrian_area",
        class_name="pedestrian-area",
        bounds=bounds,
        scale=scale,
        offset_x=offset_x,
        offset_y=offset_y,
        svg_height=svg_height,
    )
    drive_roads_svg = _render_roads(
        dataset["roads"],
        class_name="drive-road",
        bounds=bounds,
        scale=scale,
        offset_x=offset_x,
        offset_y=offset_y,
        svg_height=svg_height,
    )
    walk_roads_svg = _render_roads(
        dataset["roads_walk"],
        class_name="walk-road",
        bounds=bounds,
        scale=scale,
        offset_x=offset_x,
        offset_y=offset_y,
        svg_height=svg_height,
    )
    buildings_svg = _render_buildings(
        dataset["buildings"],
        bounds=bounds,
        scale=scale,
        offset_x=offset_x,
        offset_y=offset_y,
        svg_height=svg_height,
    )
    barriers_svg = _render_barriers(
        dataset["barriers"],
        class_name="barrier",
        bounds=bounds,
        scale=scale,
        offset_x=offset_x,
        offset_y=offset_y,
        svg_height=svg_height,
    )
    poi_svg = _render_poi(
        dataset["poi"],
        class_name="poi",
        bounds=bounds,
        scale=scale,
        offset_x=offset_x,
        offset_y=offset_y,
        svg_height=svg_height,
    )
    road_labels_svg = _render_road_labels(
        dataset["roads"] + dataset["roads_walk"],
        class_name="road-label",
        bounds=bounds,
        scale=scale,
        offset_x=offset_x,
        offset_y=offset_y,
        svg_height=svg_height,
    )
    enhancement_layers = dataset["enhancement_layers"]
    research_landuse_svg = _render_polygons(
        enhancement_layers["landuse"],
        layer_name="research_landuse",
        class_name="research-landuse",
        bounds=bounds,
        scale=scale,
        offset_x=offset_x,
        offset_y=offset_y,
        svg_height=svg_height,
    )
    research_pedestrian_svg = _render_polygons(
        enhancement_layers["pedestrian_areas"],
        layer_name="research_pedestrian_area",
        class_name="research-pedestrian-area",
        bounds=bounds,
        scale=scale,
        offset_x=offset_x,
        offset_y=offset_y,
        svg_height=svg_height,
    )
    research_drive_roads_svg = _render_roads(
        enhancement_layers["roads"],
        class_name="research-drive-road",
        bounds=bounds,
        scale=scale,
        offset_x=offset_x,
        offset_y=offset_y,
        svg_height=svg_height,
    )
    research_walk_roads_svg = _render_roads(
        enhancement_layers["roads_walk"],
        class_name="research-walk-road",
        bounds=bounds,
        scale=scale,
        offset_x=offset_x,
        offset_y=offset_y,
        svg_height=svg_height,
    )
    research_barriers_svg = _render_barriers(
        enhancement_layers["barriers"],
        class_name="research-barrier",
        bounds=bounds,
        scale=scale,
        offset_x=offset_x,
        offset_y=offset_y,
        svg_height=svg_height,
    )
    research_poi_svg = _render_poi(
        enhancement_layers["poi"],
        class_name="research-poi",
        bounds=bounds,
        scale=scale,
        offset_x=offset_x,
        offset_y=offset_y,
        svg_height=svg_height,
    )
    building_labels_svg = _render_building_labels(
        dataset["buildings"],
        bounds=bounds,
        scale=scale,
        offset_x=offset_x,
        offset_y=offset_y,
        svg_height=svg_height,
    )

    html_text = f"""<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>{html.escape(page_title)}</title>
    <style>
      :root {{
        color-scheme: light;
        --bg: #f6f1e8;
        --panel: rgba(255, 252, 246, 0.9);
        --ink: #1e2430;
        --muted: #5c6473;
        --accent: #0e5a62;
        --road: #314a67;
        --walk-road: #2e7d5d;
        --building-fill: #d36a3d;
        --building-stroke: #7d3213;
        --landuse-fill: rgba(90, 148, 102, 0.18);
        --landuse-stroke: rgba(51, 89, 58, 0.5);
        --ped-fill: rgba(55, 145, 145, 0.18);
        --ped-stroke: rgba(9, 90, 90, 0.5);
        --barrier: #b53333;
        --poi: #d6a11d;
        --research-road: #8a5a14;
        --research-walk-road: #b97d17;
        --research-landuse-fill: rgba(175, 126, 52, 0.14);
        --research-landuse-stroke: rgba(130, 86, 22, 0.45);
        --research-ped-fill: rgba(224, 142, 69, 0.14);
        --research-ped-stroke: rgba(158, 88, 17, 0.45);
        --research-barrier: #8a3f1a;
        --research-poi: #9d3d27;
        --grid: rgba(0, 0, 0, 0.08);
      }}

      * {{
        box-sizing: border-box;
      }}

      body {{
        margin: 0;
        font-family: "Iowan Old Style", "Palatino Linotype", "Book Antiqua", serif;
        color: var(--ink);
        background:
          radial-gradient(circle at top left, rgba(255, 255, 255, 0.85), transparent 30%),
          linear-gradient(135deg, #efe7da 0%, var(--bg) 48%, #e8efe6 100%);
      }}

      .layout {{
        min-height: 100vh;
        display: grid;
        grid-template-columns: 340px 1fr;
      }}

      .panel {{
        padding: 28px 24px;
        backdrop-filter: blur(12px);
        background: var(--panel);
        border-right: 1px solid rgba(0, 0, 0, 0.08);
      }}

      .eyebrow {{
        margin: 0 0 8px;
        font-size: 12px;
        letter-spacing: 0.14em;
        text-transform: uppercase;
        color: var(--accent);
      }}

      h1 {{
        margin: 0 0 12px;
        font-size: 32px;
        line-height: 1.05;
      }}

      .lead {{
        margin: 0 0 24px;
        font-size: 15px;
        line-height: 1.5;
        color: var(--muted);
      }}

      .metrics {{
        display: grid;
        gap: 10px;
        margin-bottom: 24px;
      }}

      .metric {{
        display: grid;
        gap: 2px;
        padding: 10px 12px;
        background: rgba(255, 255, 255, 0.65);
        border: 1px solid rgba(0, 0, 0, 0.06);
        border-radius: 12px;
      }}

      .metric span {{
        font-size: 12px;
        color: var(--muted);
        text-transform: uppercase;
        letter-spacing: 0.08em;
      }}

      .metric strong {{
        font-size: 16px;
      }}

      .toggles {{
        display: grid;
        gap: 10px;
      }}

      .toggle {{
        display: flex;
        align-items: center;
        gap: 10px;
        padding: 10px 12px;
        background: rgba(255, 255, 255, 0.6);
        border-radius: 10px;
        border: 1px solid rgba(0, 0, 0, 0.05);
        cursor: pointer;
      }}

      .toggle input {{
        inline-size: 16px;
        block-size: 16px;
      }}

      .canvas {{
        padding: 26px;
      }}

      .map-frame {{
        position: relative;
        inline-size: 100%;
        min-block-size: calc(100vh - 52px);
        background: rgba(255, 255, 255, 0.58);
        border: 1px solid rgba(0, 0, 0, 0.08);
        border-radius: 24px;
        overflow: hidden;
        box-shadow: 0 20px 50px rgba(42, 51, 61, 0.08);
      }}

      svg {{
        inline-size: 100%;
        block-size: auto;
        display: block;
        background:
          linear-gradient(180deg, rgba(255, 255, 255, 0.28), rgba(255, 255, 255, 0.04)),
          #f8f6f1;
      }}

      .grid-line {{
        stroke: var(--grid);
        stroke-width: 1;
      }}

      .overlay-polygon {{
        fill: rgba(209, 54, 54, 0.08);
        stroke: #b53333;
        stroke-width: 3;
        stroke-dasharray: 14 10;
      }}

      .reference-image {{
        pointer-events: none;
      }}

      .reference-frame {{
        fill: none;
        stroke: rgba(66, 69, 77, 0.35);
        stroke-width: 1.5;
        stroke-dasharray: 8 6;
      }}

      .drive-road {{
        fill: none;
        stroke: var(--road);
        stroke-width: 2.3;
        stroke-linecap: round;
        stroke-linejoin: round;
        opacity: 0.9;
      }}

      .walk-road {{
        fill: none;
        stroke: var(--walk-road);
        stroke-width: 1.8;
        stroke-linecap: round;
        stroke-linejoin: round;
        stroke-dasharray: 7 5;
        opacity: 0.85;
      }}

      .building {{
        fill: var(--building-fill);
        fill-opacity: 0.5;
        stroke: var(--building-stroke);
        stroke-width: 1.2;
      }}

      .road-label,
      .building-label {{
        font-family: "STSong", "Songti SC", "Noto Serif CJK SC", serif;
        fill: #1b2030;
        paint-order: stroke;
        stroke: rgba(255, 252, 246, 0.96);
        stroke-width: 3.2;
        stroke-linejoin: round;
        pointer-events: none;
      }}

      .road-label {{
        font-size: 14px;
      }}

      .building-label {{
        font-size: 15px;
        text-anchor: middle;
      }}

      .landuse {{
        fill: var(--landuse-fill);
        stroke: var(--landuse-stroke);
        stroke-width: 1.4;
      }}

      .pedestrian-area {{
        fill: var(--ped-fill);
        stroke: var(--ped-stroke);
        stroke-width: 1.4;
      }}

      .barrier {{
        fill: none;
        stroke: var(--barrier);
        stroke-width: 2.1;
        stroke-dasharray: 8 6;
      }}

      .poi {{
        fill: var(--poi);
        stroke: #72550c;
        stroke-width: 1.2;
      }}

      .research-drive-road {{
        fill: none;
        stroke: var(--research-road);
        stroke-width: 2.4;
        stroke-linecap: round;
        stroke-linejoin: round;
        opacity: 0.88;
      }}

      .research-walk-road {{
        fill: none;
        stroke: var(--research-walk-road);
        stroke-width: 2.1;
        stroke-linecap: round;
        stroke-linejoin: round;
        stroke-dasharray: 10 6;
        opacity: 0.92;
      }}

      .research-landuse {{
        fill: var(--research-landuse-fill);
        stroke: var(--research-landuse-stroke);
        stroke-width: 1.5;
      }}

      .research-pedestrian-area {{
        fill: var(--research-ped-fill);
        stroke: var(--research-ped-stroke);
        stroke-width: 1.5;
      }}

      .research-barrier {{
        fill: none;
        stroke: var(--research-barrier);
        stroke-width: 2.2;
        stroke-dasharray: 6 5;
      }}

      .research-poi {{
        fill: var(--research-poi);
        stroke: #fff5ef;
        stroke-width: 1.3;
      }}

      .note {{
        margin-top: 22px;
        font-size: 13px;
        line-height: 1.55;
        color: var(--muted);
      }}

      .map-overlay {{
        position: absolute;
        inset: 18px 18px auto auto;
        display: grid;
        gap: 12px;
        pointer-events: none;
      }}

      .compass {{
        inline-size: 112px;
        padding: 12px 12px 10px;
        border-radius: 16px;
        background: rgba(255, 252, 246, 0.86);
        border: 1px solid rgba(0, 0, 0, 0.08);
        box-shadow: 0 14px 28px rgba(42, 51, 61, 0.08);
      }}

      .compass svg {{
        background: transparent;
      }}

      .overlay-copy {{
        margin-top: 6px;
        font-size: 11px;
        line-height: 1.35;
        color: var(--muted);
        text-align: center;
      }}

      .scale-bar {{
        padding: 10px 12px;
        border-radius: 14px;
        background: rgba(255, 252, 246, 0.86);
        border: 1px solid rgba(0, 0, 0, 0.08);
        box-shadow: 0 14px 28px rgba(42, 51, 61, 0.08);
      }}

      .scale-bar strong {{
        display: block;
        font-size: 11px;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        color: var(--muted);
        margin-bottom: 6px;
      }}

      .scale-line {{
        position: relative;
        inline-size: 120px;
        block-size: 12px;
        border-bottom: 3px solid var(--ink);
      }}

      .scale-line::before,
      .scale-line::after {{
        content: "";
        position: absolute;
        inset-block-end: -3px;
        inline-size: 2px;
        block-size: 12px;
        background: var(--ink);
      }}

      .scale-line::before {{
        inset-inline-start: 0;
      }}

      .scale-line::after {{
        inset-inline-end: 0;
      }}

      @media (max-width: 1080px) {{
        .layout {{
          grid-template-columns: 1fr;
        }}

        .panel {{
          border-right: 0;
          border-bottom: 1px solid rgba(0, 0, 0, 0.08);
        }}

        .map-frame {{
          min-block-size: auto;
        }}
      }}
    </style>
  </head>
  <body>
    <div class="layout">
      <aside class="panel">
        <p class="eyebrow">Urban Sim Lab</p>
        <h1>{html.escape(manifest.get("display_name", manifest.get("city_id", "normalized-city")))}</h1>
        <p class="lead">
          Normalized city package preview. This view is drawn from local meter-space coordinates,
          with north fixed upward and east fixed to the right for direct field comparison.
        </p>
        <div class="metrics">{_summary_items(dataset, bounds)}</div>
        <div class="toggles">{_layer_controls(dataset)}</div>
        <p class="note">
          Drive roads, walk roads, labels, and the optional clip polygon can be toggled independently.
          Reference images assume north-up screenshots, and research bundles are intended for local validation,
          not direct redistribution of third-party raw data.
        </p>
      </aside>
      <main class="canvas">
        <div class="map-frame">
          <div class="map-overlay" aria-hidden="true">
            <div class="compass">
              <svg viewBox="0 0 100 100" role="presentation">
                <circle cx="50" cy="50" r="34" fill="rgba(255,255,255,0.4)" stroke="rgba(0,0,0,0.15)" stroke-width="1.5" />
                <line x1="50" y1="20" x2="50" y2="80" stroke="#1e2430" stroke-width="2" />
                <line x1="20" y1="50" x2="80" y2="50" stroke="rgba(30,36,48,0.35)" stroke-width="1.5" />
                <path d="M50 8 L58 32 L50 26 L42 32 Z" fill="#b53333" />
                <text x="50" y="15" text-anchor="middle" font-size="12" font-family="Georgia, serif" fill="#b53333">N</text>
                <text x="86" y="54" text-anchor="middle" font-size="11" font-family="Georgia, serif" fill="#1e2430">E</text>
                <text x="50" y="94" text-anchor="middle" font-size="11" font-family="Georgia, serif" fill="#1e2430">S</text>
                <text x="14" y="54" text-anchor="middle" font-size="11" font-family="Georgia, serif" fill="#1e2430">W</text>
              </svg>
              <div class="overlay-copy">North is up. East is right.</div>
            </div>
            <div class="scale-bar">
              <strong>Engineering Scale</strong>
              <div class="scale-line"></div>
              <div class="overlay-copy">Local meter space</div>
            </div>
          </div>
          <svg viewBox="0 0 {svg_width} {svg_height}" role="img" aria-label="{html.escape(page_title)}">
            <g data-layer-group="grid">{grid_svg}</g>
            <g data-layer-group="reference-image">{reference_image_svg}</g>
            <g data-layer-group="overlay-polygon">{overlay_polygon_svg}</g>
            <g data-layer-group="landuse">{landuse_svg}</g>
            <g data-layer-group="pedestrian">{pedestrian_svg}</g>
            <g data-layer-group="drive-roads">{drive_roads_svg}</g>
            <g data-layer-group="walk-roads">{walk_roads_svg}</g>
            <g data-layer-group="road-labels">{road_labels_svg}</g>
            <g data-layer-group="buildings">{buildings_svg}</g>
            <g data-layer-group="building-labels">{building_labels_svg}</g>
            <g data-layer-group="barriers">{barriers_svg}</g>
            <g data-layer-group="poi">{poi_svg}</g>
            <g data-layer-group="research-landuse">{research_landuse_svg}</g>
            <g data-layer-group="research-pedestrian">{research_pedestrian_svg}</g>
            <g data-layer-group="research-drive-roads">{research_drive_roads_svg}</g>
            <g data-layer-group="research-walk-roads">{research_walk_roads_svg}</g>
            <g data-layer-group="research-barriers">{research_barriers_svg}</g>
            <g data-layer-group="research-poi">{research_poi_svg}</g>
          </svg>
        </div>
      </main>
    </div>
    <script>
      for (const input of document.querySelectorAll("[data-layer]")) {{
        const update = () => {{
          const layer = document.querySelector(`[data-layer-group="${{input.dataset.layer}}"]`);
          if (layer) {{
            layer.style.display = input.checked ? "" : "none";
          }}
        }};
        input.addEventListener("change", update);
        update();
      }}
    </script>
  </body>
</html>
"""

    output_html.parent.mkdir(parents=True, exist_ok=True)
    output_html.write_text(html_text, encoding="utf-8")
    return output_html
