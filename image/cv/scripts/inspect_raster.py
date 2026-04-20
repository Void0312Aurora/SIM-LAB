from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

def inspect_with_rasterio(path: Path) -> dict[str, Any] | None:
    try:
        import rasterio
    except Exception:
        return None

    try:
        with rasterio.open(path) as dataset:
            bounds = dataset.bounds
            return {
                "driver": dataset.driver,
                "width_px": dataset.width,
                "height_px": dataset.height,
                "band_count": dataset.count,
                "dtype": str(dataset.dtypes[0]) if dataset.count else None,
                "crs": str(dataset.crs) if dataset.crs else None,
                "transform": tuple(dataset.transform) if dataset.transform else None,
                "bounds": {
                    "left": round(float(bounds.left), 6),
                    "bottom": round(float(bounds.bottom), 6),
                    "right": round(float(bounds.right), 6),
                    "top": round(float(bounds.top), 6),
                },
                "is_georeferenced": bool(dataset.crs),
            }
    except Exception:
        return None


def inspect_with_pillow(path: Path) -> dict[str, Any]:
    try:
        from PIL import Image
    except Exception:
        return {
            "format": None,
            "mode": None,
            "width_px": None,
            "height_px": None,
        }

    with Image.open(path) as image:
        return {
            "format": image.format,
            "mode": image.mode,
            "width_px": image.width,
            "height_px": image.height,
        }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Inspect a satellite/reference image for CV-lab readiness.",
    )
    parser.add_argument(
        "--input",
        type=Path,
        required=True,
        help="Path to the input image or raster.",
    )
    args = parser.parse_args()

    path = args.input.resolve()
    if not path.exists():
        raise FileNotFoundError(f"Input does not exist: {path}")

    raster_info = inspect_with_rasterio(path)
    image_info = inspect_with_pillow(path)

    print(f"Path: {path}")
    print(f"Format: {image_info.get('format')}")
    print(f"Mode: {image_info.get('mode')}")
    print(f"Size: {image_info.get('width_px')} x {image_info.get('height_px')}")

    if raster_info is None:
        print("Geo metadata: unavailable via rasterio")
        print("Assessment: usable for visual/CV experiments, but manual registration may be required.")
        return 0

    print(f"Driver: {raster_info.get('driver')}")
    print(f"Bands: {raster_info.get('band_count')}")
    print(f"Dtype: {raster_info.get('dtype')}")
    print(f"CRS: {raster_info.get('crs')}")
    print(f"Is georeferenced: {raster_info.get('is_georeferenced')}")
    print(f"Bounds: {raster_info.get('bounds')}")
    print(f"Transform: {raster_info.get('transform')}")

    if raster_info.get("is_georeferenced"):
        print("Assessment: ready for geospatial segmentation experiments.")
    else:
        print("Assessment: image data is readable, but geospatial registration is missing.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
