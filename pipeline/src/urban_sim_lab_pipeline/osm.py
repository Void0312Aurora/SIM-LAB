from __future__ import annotations

from pathlib import Path

import osmnx as ox

from .config import OSMNormalizeConfig


def configure_osmnx(config: OSMNormalizeConfig, raw_root: Path | None = None) -> None:
    ox.settings.use_cache = config.use_cache
    ox.settings.log_console = False
    ox.settings.requests_timeout = config.overpass_timeout
    if config.overpass_memory_mb is not None:
        ox.settings.overpass_memory = config.overpass_memory_mb * 1024 * 1024
    if config.cache_folder:
        ox.settings.cache_folder = config.cache_folder
    elif raw_root is not None:
        ox.settings.cache_folder = str(raw_root / "osmnx_cache")


def fetch_road_graph(config: OSMNormalizeConfig):
    return ox.graph.graph_from_bbox(
        config.bbox.as_tuple(),
        network_type=config.network_type,
        simplify=True,
        retain_all=True,
    )


def fetch_buildings(config: OSMNormalizeConfig):
    return ox.features.features_from_bbox(
        config.bbox.as_tuple(),
        {"building": True},
    )
