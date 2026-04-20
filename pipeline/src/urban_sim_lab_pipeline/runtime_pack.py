from __future__ import annotations

from pathlib import Path
import math
from typing import Any

from .serialization import utc_now_iso, write_json


def _read_json(path: Path) -> Any:
    import json

    return json.loads(path.read_text(encoding="utf-8"))


def _iter_xy_points(roads: list[dict[str, Any]], buildings: list[dict[str, Any]]):
    for road in roads:
        for point in road.get("centerline", []):
            if len(point) >= 2:
                yield point[0], point[1]
    for building in buildings:
        for point in building.get("footprint", []):
            if len(point) >= 2:
                yield point[0], point[1]


def _compute_world_bounds(
    roads: list[dict[str, Any]],
    buildings: list[dict[str, Any]],
) -> dict[str, float]:
    points = list(_iter_xy_points(roads, buildings))
    if not points:
        return {
            "min_x": 0.0,
            "max_x": 0.0,
            "min_z": 0.0,
            "max_z": 0.0,
        }
    xs = [item[0] for item in points]
    zs = [item[1] for item in points]
    return {
        "min_x": round(min(xs), 3),
        "max_x": round(max(xs), 3),
        "min_z": round(min(zs), 3),
        "max_z": round(max(zs), 3),
    }


def _make_node_id(point: list[float]) -> str:
    return f"n_{point[0]:.3f}_{point[1]:.3f}".replace("-", "m").replace(".", "_")


def _road_to_graph(
    roads: list[dict[str, Any]],
    *,
    mode: str,
) -> dict[str, Any]:
    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []

    for road in roads:
        if mode == "pedestrian" and not road.get("is_pedestrian_accessible", False):
            continue
        centerline = road.get("centerline", [])
        if len(centerline) < 2:
            continue
        start = centerline[0]
        end = centerline[-1]
        start_id = _make_node_id(start)
        end_id = _make_node_id(end)
        nodes.setdefault(
            start_id,
            {
                "id": start_id,
                "position": {"x": start[0], "y": 0.0, "z": start[1]},
                "tags": [],
            },
        )
        nodes.setdefault(
            end_id,
            {
                "id": end_id,
                "position": {"x": end[0], "y": 0.0, "z": end[1]},
                "tags": [],
            },
        )
        length_m = float(road.get("length_m", 0.0))
        width_m = float(road.get("width_m", 1.0))
        capacity = max(1.0, round(width_m / 1.2, 2))
        edges.append(
            {
                "id": f"e_{road['id']}",
                "from": start_id,
                "to": end_id,
                "length_m": round(length_m, 2),
                "cost": round(length_m, 2),
                "width_m": round(width_m, 2),
                "capacity": capacity,
                "blocked": False,
                "bidirectional": True,
            }
        )

    return {
        "schema_version": "0.1.0",
        "graph_id": f"{mode}_graph",
        "mode": mode,
        "nodes": list(nodes.values()),
        "edges": edges,
    }


def _infer_zone_class(zone_id: str) -> str:
    lowered = zone_id.lower()
    if "safe" in lowered:
        return "safe_zone"
    if "evac" in lowered:
        return "evac_point"
    if "checkpoint" in lowered or "military" in lowered:
        return "military_control"
    if "outbreak" in lowered:
        return "outbreak_origin"
    return "generic_zone"


def _default_world_center(bounds: dict[str, float]) -> dict[str, float]:
    return {
        "x": round((bounds["min_x"] + bounds["max_x"]) / 2.0, 3),
        "y": 0.0,
        "z": round((bounds["min_z"] + bounds["max_z"]) / 2.0, 3),
    }


def _build_zones_from_scenario(
    scenario: dict[str, Any],
    *,
    bounds: dict[str, float],
) -> list[dict[str, Any]]:
    center = _default_world_center(bounds)
    zones = []
    seen = set()
    for spawn_rule in scenario.get("spawn_rules", []):
        zone_id = spawn_rule.get("zone_id")
        if not zone_id or zone_id in seen:
            continue
        seen.add(zone_id)
        zones.append(
            {
                "id": zone_id,
                "class": _infer_zone_class(zone_id),
                "shape": "point_hint",
                "center": center,
                "radius_m": 20.0,
            }
        )
    return zones


def _build_runtime_buildings(buildings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    runtime_buildings = []
    for building in buildings:
        runtime_buildings.append(
            {
                "id": building["id"],
                "mesh_ref": None,
                "footprint": building.get("footprint", []),
                "height_m": building.get("height_m", 9.0),
                "usage_class": building.get("usage_class", "building"),
                "entrances": building.get("entrances", []),
                "capacity_estimate": building.get("capacity_estimate", 1),
                "occlusion_class": "building_mass",
            }
        )
    return runtime_buildings


def _default_scenario(pack_id: str) -> dict[str, Any]:
    return {
        "schema_version": "0.1.0",
        "scenario_id": f"scenario_{pack_id}",
        "map_pack_id": pack_id,
        "time_of_day": "day",
        "factions": {
            "civilians": {"count": 0, "behavior_profile": "panic_default"},
            "infected": {"count": 0, "behavior_profile": "aggressive_noise_seek"},
            "military": {"count": 0, "behavior_profile": "checkpoint_response", "squad_size": 4},
        },
        "spawn_rules": [],
        "goals": [],
    }


def build_runtime_pack(
    *,
    normalized_city_dir: Path,
    output_root: Path,
    scenario_path: Path | None = None,
    runtime_target: str = "godot",
    schema_version: str = "0.1.0",
) -> Path:
    manifest = _read_json(normalized_city_dir / "city_manifest.json")
    roads = _read_json(normalized_city_dir / "roads.json")
    buildings = _read_json(normalized_city_dir / "buildings.json")
    barriers = _read_json(normalized_city_dir / "barriers.json")
    landuse = _read_json(normalized_city_dir / "landuse.json")

    pack_id = f"pack_{manifest['city_id']}"
    output_dir = output_root / pack_id
    meshes_dir = output_dir / "meshes"
    meshes_dir.mkdir(parents=True, exist_ok=True)

    scenario = _read_json(scenario_path) if scenario_path else _default_scenario(pack_id)
    scenario["map_pack_id"] = pack_id

    bounds = _compute_world_bounds(roads, buildings)
    world = {
        "schema_version": schema_version,
        "bounds": bounds,
        "surfaces": landuse,
        "water": [],
        "green": [],
        "barriers": barriers,
    }
    runtime_buildings = _build_runtime_buildings(buildings)
    zones = _build_zones_from_scenario(scenario, bounds=bounds)
    nav_vehicle = _road_to_graph(roads, mode="vehicle")
    nav_pedestrian = _road_to_graph(roads, mode="pedestrian")
    props = []

    write_json(output_dir / "world.json", world)
    write_json(output_dir / "buildings.json", runtime_buildings)
    write_json(output_dir / "zones.json", zones)
    write_json(output_dir / "nav_vehicle.json", nav_vehicle)
    write_json(output_dir / "nav_pedestrian.json", nav_pedestrian)
    write_json(output_dir / "props.json", props)
    write_json(output_dir / "scenario.json", scenario)

    runtime_manifest = {
        "schema_version": schema_version,
        "pack_id": pack_id,
        "city_id": manifest["city_id"],
        "runtime_target": runtime_target,
        "compiled_at": utc_now_iso(),
        "source_manifest": str((normalized_city_dir / "city_manifest.json").resolve()),
        "coordinate_mapping": {
            "horizontal_axes": ["x", "z"],
            "up_axis": "y",
            "units": "meters",
        },
        "assets": {
            "world": "world.json",
            "buildings": "buildings.json",
            "zones": "zones.json",
            "nav_pedestrian": "nav_pedestrian.json",
            "nav_vehicle": "nav_vehicle.json",
            "props": "props.json",
            "scenario": "scenario.json",
            "meshes": [],
        },
    }
    write_json(output_dir / "manifest.json", runtime_manifest)
    return output_dir
