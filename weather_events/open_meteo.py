from __future__ import annotations

import json
import socket
import ssl
import time
from datetime import date, timedelta
from typing import Any
from urllib.parse import urlencode
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


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
    def __init__(
        self,
        endpoint: str = ARCHIVE_ENDPOINT,
        timeout_s: int = 60,
        max_retries: int = 3,
        retry_backoff_s: float = 1.5,
    ) -> None:
        self.endpoint = endpoint
        self.timeout_s = timeout_s
        self.max_retries = max_retries
        self.retry_backoff_s = retry_backoff_s

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
        payload = self._get(url)
        data = json.loads(payload)
        if "error" in data:
            raise RuntimeError(f"Open-Meteo API error: {data.get('reason', data)}")
        return data

    def _get(self, url: str) -> str:
        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                request = Request(url, headers={"User-Agent": "extreme-weather-data-display/0.1"})
                with urlopen(request, timeout=self.timeout_s) as response:
                    return response.read().decode("utf-8")
            except HTTPError as exc:
                if exc.code < 500 or attempt == self.max_retries:
                    raise RuntimeError(f"Open-Meteo HTTP {exc.code}: {exc.reason}") from exc
                last_error = exc
            except (URLError, TimeoutError, socket.timeout, ssl.SSLError, ConnectionResetError) as exc:
                last_error = exc
                if attempt == self.max_retries:
                    break
            time.sleep(self.retry_backoff_s * attempt)
        raise RuntimeError(f"Open-Meteo request failed after {self.max_retries} attempts: {last_error}") from last_error


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
