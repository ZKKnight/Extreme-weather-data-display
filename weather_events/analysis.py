from __future__ import annotations

from statistics import mean
from typing import Any, Iterable


def _values(rows: Iterable[dict[str, Any]], key: str) -> list[float]:
    return [float(row[key]) for row in rows if row.get(key) is not None]


def _count_ge(values: list[float], threshold: float) -> int:
    return sum(1 for value in values if value >= threshold)


def _count_le(values: list[float], threshold: float) -> int:
    return sum(1 for value in values if value <= threshold)


def calculate_indices(event_type: str, rows: list[dict[str, Any]]) -> dict[str, tuple[Any, str, str, str]]:
    if not rows:
        return {}

    temp = _values(rows, "temperature_2m")
    wind10 = _values(rows, "wind_speed_10m")
    wind100 = _values(rows, "wind_speed_100m")
    gust = _values(rows, "wind_gusts_10m")
    radiation = _values(rows, "shortwave_radiation")
    precipitation = _values(rows, "precipitation")
    snowfall = _values(rows, "snowfall")
    snow_depth = _values(rows, "snow_depth")
    humidity = _values(rows, "relative_humidity_2m")

    indices: dict[str, tuple[Any, str, str, str]] = {}

    if temp:
        indices["temperature_max"] = (max(temp), "degC", "max(temperature_2m)", "")
        indices["temperature_min"] = (min(temp), "degC", "min(temperature_2m)", "")
        indices["temperature_range"] = (max(temp) - min(temp), "degC", "max-min temperature_2m", "")
    if gust:
        indices["wind_gust_max_10m"] = (max(gust), "m/s", "max(wind_gusts_10m)", "")
        indices["gust_hours_ge_17_2ms"] = (_count_ge(gust, 17.2), "h", "count(wind_gusts_10m >= 17.2)", "8级风")
    if wind10:
        indices["wind_speed_max_10m"] = (max(wind10), "m/s", "max(wind_speed_10m)", "")
    if wind100:
        indices["wind_speed_max_100m"] = (max(wind100), "m/s", "max(wind_speed_100m)", "近似风机轮毂高度")
    if precipitation:
        indices["precipitation_sum"] = (sum(precipitation), "mm", "sum(precipitation)", "")
    if snowfall:
        indices["snowfall_sum"] = (sum(snowfall), "cm", "sum(snowfall)", "")
    if snow_depth:
        indices["snow_depth_max"] = (max(snow_depth), "m", "max(snow_depth)", "")
    if radiation:
        indices["shortwave_radiation_mean"] = (mean(radiation), "W/m2", "mean(shortwave_radiation)", "")

    if event_type == "sandstorm":
        if humidity:
            indices["humidity_min"] = (min(humidity), "%", "min(relative_humidity_2m)", "")
        if radiation:
            low_radiation_hours = _count_le(radiation, 200)
            indices["low_radiation_hours_le_200"] = (
                low_radiation_hours,
                "h",
                "count(shortwave_radiation <= 200)",
                "沙尘遮蔽粗略阈值",
            )
    elif event_type == "cold_wave":
        if temp:
            indices["cold_hours_le_0"] = (_count_le(temp, 0), "h", "count(temperature_2m <= 0)", "0 degC")
            indices["temperature_drop_proxy"] = (
                temp[0] - min(temp),
                "degC",
                "first temperature_2m - min(temperature_2m)",
                "寒潮降温代理指标",
            )
    elif event_type == "heat_stagnation":
        if temp:
            indices["hot_hours_ge_35"] = (_count_ge(temp, 35), "h", "count(temperature_2m >= 35)", "35 degC")
            indices["extreme_hot_hours_ge_40"] = (_count_ge(temp, 40), "h", "count(temperature_2m >= 40)", "40 degC")
        if wind10:
            indices["stagnant_hours_wind_le_2"] = (_count_le(wind10, 2), "h", "count(wind_speed_10m <= 2)", "静稳粗略阈值")
    elif event_type == "strong_wind":
        if gust:
            indices["gust_hours_ge_24_5ms"] = (_count_ge(gust, 24.5), "h", "count(wind_gusts_10m >= 24.5)", "10级风")
    elif event_type == "blizzard":
        if snowfall:
            indices["snowfall_hours_gt_0"] = (_count_ge(snowfall, 0.01), "h", "count(snowfall > 0)", "")
        if temp:
            indices["snow_cold_hours_le_0"] = (_count_le(temp, 0), "h", "count(temperature_2m <= 0)", "0 degC")

    return indices
