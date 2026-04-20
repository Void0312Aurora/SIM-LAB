from __future__ import annotations

from pathlib import Path
import json

from pydantic import BaseModel, Field, field_validator


class BBoxConfig(BaseModel):
    west: float
    south: float
    east: float
    north: float

    @field_validator("east")
    @classmethod
    def east_must_exceed_west(cls, value: float, info) -> float:
        west = info.data.get("west")
        if west is not None and value <= west:
            raise ValueError("bbox.east must be greater than bbox.west")
        return value

    @field_validator("north")
    @classmethod
    def north_must_exceed_south(cls, value: float, info) -> float:
        south = info.data.get("south")
        if south is not None and value <= south:
            raise ValueError("bbox.north must be greater than bbox.south")
        return value

    def as_tuple(self) -> tuple[float, float, float, float]:
        return (self.west, self.south, self.east, self.north)

    def as_wgs84_bbox(self) -> list[float]:
        return [self.west, self.south, self.east, self.north]


class OSMNormalizeConfig(BaseModel):
    city_id: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    bbox: BBoxConfig
    network_type: str = "drive"
    include_walk_network: bool = True
    walk_network_type: str | None = "walk"
    overpass_timeout: int = Field(default=180, ge=30)
    overpass_memory_mb: int | None = Field(default=1024, ge=128)
    use_cache: bool = True
    cache_folder: str | None = None

    @classmethod
    def from_path(cls, path: Path) -> "OSMNormalizeConfig":
        return cls.model_validate(json.loads(path.read_text(encoding="utf-8")))
