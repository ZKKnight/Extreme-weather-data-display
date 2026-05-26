from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


EventType = Literal["sandstorm", "cold_wave", "heat_stagnation", "strong_wind", "blizzard"]

EVENT_TYPES: tuple[str, ...] = (
    "sandstorm",
    "cold_wave",
    "heat_stagnation",
    "strong_wind",
    "blizzard",
)

EVENT_TYPE_LABELS: dict[str, str] = {
    "sandstorm": "沙尘暴",
    "cold_wave": "寒潮",
    "heat_stagnation": "高温及静稳",
    "strong_wind": "强风",
    "blizzard": "暴雪",
}


@dataclass(frozen=True)
class Event:
    event_id: str
    event_type: EventType
    name: str
    start_date: str
    end_date: str
    region: str
    source_name: str = ""
    source_url: str = ""
    notes: str = ""


@dataclass(frozen=True)
class Location:
    location_id: str
    event_id: str
    name: str
    latitude: float
    longitude: float
    province: str = ""
    location_type: str = "representative_point"
    altitude_m: float | None = None
