from __future__ import annotations

import base64
import mimetypes
from pathlib import Path
import json
from typing import Any


def load_overlay_polygon(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    coordinate_space = payload.get("coordinate_space")
    if coordinate_space != "local_meters":
        raise ValueError(
            f"Unsupported overlay coordinate_space {coordinate_space!r}; expected 'local_meters'."
        )
    polygon = payload.get("polygon")
    if not isinstance(polygon, list) or len(polygon) < 3:
        raise ValueError("Overlay polygon must contain at least three points.")
    for index, point in enumerate(polygon):
        if (
            not isinstance(point, list)
            or len(point) < 2
            or not isinstance(point[0], (int, float))
            or not isinstance(point[1], (int, float))
        ):
            raise ValueError(f"Overlay polygon point #{index} is invalid: {point!r}")
    return payload


def load_reference_image_overlay(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    coordinate_space = payload.get("coordinate_space")
    if coordinate_space != "local_meters":
        raise ValueError(
            f"Unsupported reference image coordinate_space {coordinate_space!r}; expected 'local_meters'."
        )
    anchor_bounds = payload.get("anchor_bounds")
    if not isinstance(anchor_bounds, dict):
        raise ValueError("Reference image overlay must define anchor_bounds.")
    required_keys = ["min_x", "min_y", "max_x", "max_y"]
    for key in required_keys:
        if not isinstance(anchor_bounds.get(key), (int, float)):
            raise ValueError(f"Reference image anchor_bounds.{key} must be numeric.")
    if float(anchor_bounds["max_x"]) <= float(anchor_bounds["min_x"]):
        raise ValueError("Reference image anchor_bounds.max_x must be greater than min_x.")
    if float(anchor_bounds["max_y"]) <= float(anchor_bounds["min_y"]):
        raise ValueError("Reference image anchor_bounds.max_y must be greater than min_y.")

    image_path_raw = payload.get("image_path")
    if not isinstance(image_path_raw, str) or not image_path_raw.strip():
        raise ValueError("Reference image overlay must define a non-empty image_path.")
    resolved_image_path = Path(image_path_raw)
    if not resolved_image_path.is_absolute():
        resolved_image_path = (path.parent / resolved_image_path).resolve()
    if not resolved_image_path.exists():
        raise FileNotFoundError(f"Reference image file does not exist: {resolved_image_path}")

    mime_type, _ = mimetypes.guess_type(str(resolved_image_path))
    if not mime_type:
        mime_type = "application/octet-stream"
    encoded = base64.b64encode(resolved_image_path.read_bytes()).decode("ascii")
    payload["resolved_image_path"] = str(resolved_image_path)
    payload["image_href"] = f"data:{mime_type};base64,{encoded}"
    payload.setdefault("display_name", payload.get("overlay_id", "reference image"))
    payload.setdefault("opacity", 0.72)
    return payload
