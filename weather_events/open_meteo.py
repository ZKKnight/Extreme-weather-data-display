from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any
from urllib.parse import urlencode
from urllib.request import urlopen


ARCHIVE_ENDPOINT = "https://archive-api.open-meteo.com/v1/archive"

DEFAULT_HOURLY_VARIABLES = [
    "temperature_2m",
    "relative_humidity_2m",
    "precipitation",
    "snowfall",
    "snow_depth",
    "wind_speed_10m",
    "wind_speed_100m",
    "wind_gusts_10m",
    "wind_direction_10m",
    "shortwave_radiation",
    "direct_radiation",
    "diffuse_radiation",
    "pressure_msl",
    "cloud_cover",
    "et0_fao_evapotranspiration",
    "soil_moisture_0_to_7cm",
]


class OpenMeteoClient:
    def __init__(self, endpoint: str = ARCHIVE_ENDPOINT, timeout_s: int = 60) -> None:
        self.endpoint = endpoint
        self.timeout_s = timeout_s

    def fetch_hourly(
        self,
        latitude: float,
        longitude: float,
        start_date: str,
        end_date: str,
        variables: list[str] | None = None,
        timezone: str = "Asia/Shanghai",
    ) -> dict[str, Any]:
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "start_date": start_date,
            "end_date": end_date,
            "hourly": ",".join(variables or DEFAULT_HOURLY_VARIABLES),
            "wind_speed_unit": "ms",
            "timezone": timezone,
        }
        url = f"{self.endpoint}?{urlencode(params)}"
        with urlopen(url, timeout=self.timeout_s) as response:
            payload = response.read().decode("utf-8")
        data = json.loads(payload)
        if "error" in data:
            raise RuntimeError(f"Open-Meteo API error: {data.get('reason', data)}")
        return data


def expand_date_window(start_date: str, end_date: str, days_before: int = 1, days_after: int = 1) -> tuple[str, str]:
    start = date.fromisoformat(start_date) - timedelta(days=days_before)
    end = date.fromisoformat(end_date) + timedelta(days=days_after)
    return start.isoformat(), end.isoformat()


def hourly_json_to_rows(data: dict[str, Any], event_id: str, location_id: str) -> list[dict[str, Any]]:
    hourly = data.get("hourly", {})
    times = hourly.get("time", [])
    rows: list[dict[str, Any]] = []
    for idx, timestamp in enumerate(times):
        row = {"event_id": event_id, "location_id": location_id, "time": timestamp}
        for key, values in hourly.items():
            if key == "time":
                continue
            row[key] = values[idx] if idx < len(values) else None
        rows.append(row)
    return rows
