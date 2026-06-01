from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


EventType = Literal[
    "sandstorm",
    "cold_wave",
    "heat_stagnation",
    "strong_wind",
    "blizzard",
    "heavy_rain",
    "freezing_rain",
    "typhoon",
    "hail",
    "fog",
    "wildfire_weather",
    "drought",
]

EVENT_TYPES: tuple[str, ...] = (
    "sandstorm",
    "cold_wave",
    "heat_stagnation",
    "strong_wind",
    "blizzard",
    "heavy_rain",
    "freezing_rain",
    "typhoon",
    "hail",
    "fog",
    "wildfire_weather",
    "drought",
)

EVENT_TYPE_LABELS: dict[str, str] = {
    "sandstorm": "沙尘暴",
    "cold_wave": "寒潮",
    "heat_stagnation": "高温及静稳",
    "strong_wind": "强风",
    "blizzard": "暴雪",
    "heavy_rain": "强降水/暴雨洪涝",
    "freezing_rain": "冰冻/冻雨/雨凇",
    "typhoon": "台风/热带气旋",
    "hail": "冰雹",
    "fog": "大雾/低能见度",
    "wildfire_weather": "森林草原火险/高火险天气",
    "drought": "干旱",
}

EVENT_SUBTYPE_LABELS: dict[str, str] = {
    "heat": "高温",
    "stagnation": "静稳",
}


@dataclass(frozen=True)
class Event:
    event_id: str
    event_type: EventType
    name: str
    start_date: str
    end_date: str
    region: str
    event_subtype: str = ""
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
