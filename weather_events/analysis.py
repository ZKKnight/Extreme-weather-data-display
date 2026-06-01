from __future__ import annotations

from statistics import mean
from typing import Any, Iterable

INDEX_LABELS = {
    "temperature_max": "最高气温",
    "temperature_min": "最低气温",
    "temperature_range": "气温日内/过程变幅",
    "wind_gust_max_10m": "10米最大阵风风速",
    "gust_hours_ge_17_2ms": "8级及以上阵风小时数",
    "wind_speed_max_10m": "10米最大平均风速",
    "wind_speed_max_100m": "100米最大平均风速",
    "precipitation_sum": "累计降水量",
    "precipitation_max_hourly": "最大小时降水量",
    "heavy_rain_hours_ge_10": "10毫米及以上强降水小时数",
    "heavy_rain_hours_ge_20": "20毫米及以上短时强降水小时数",
    "snowfall_sum": "累计降雪量",
    "snow_depth_max": "最大积雪深度",
    "shortwave_radiation_mean": "平均短波辐射",
    "humidity_min": "最低相对湿度",
    "low_radiation_hours_le_200": "低辐照小时数",
    "cold_hours_le_0": "0摄氏度及以下低温小时数",
    "temperature_drop_proxy": "过程降温幅度代理值",
    "hot_hours_ge_35": "35摄氏度及以上高温小时数",
    "extreme_hot_hours_ge_40": "40摄氏度及以上极端高温小时数",
    "stagnant_hours_wind_le_2": "静稳小时数",
    "gust_hours_ge_24_5ms": "10级及以上阵风小时数",
    "snowfall_hours_gt_0": "降雪小时数",
    "snow_cold_hours_le_0": "降雪低温小时数",
    "freezing_precip_hours": "低温降水小时数",
    "typhoon_gust_hours_ge_24_5ms": "台风强阵风小时数",
    "convective_gust_hours_ge_17_2ms": "强对流大风小时数",
    "hail_proxy_hours": "冰雹环境代理小时数",
    "fog_proxy_hours": "大雾低能见度代理小时数",
    "high_humidity_hours_ge_95": "高湿小时数",
    "soil_moisture_min": "浅层土壤湿度最低值",
    "et0_sum": "参考蒸散累计值",
    "dry_hours_precip_eq_0": "无降水小时数",
    "fire_weather_proxy_hours": "高火险天气代理小时数",
    "low_humidity_hours_le_30": "低湿小时数",
}

METHOD_LABELS = {
    "max(temperature_2m)": "取2米气温最大值",
    "min(temperature_2m)": "取2米气温最小值",
    "max-min temperature_2m": "2米气温最大值减最小值",
    "max(wind_gusts_10m)": "取10米阵风风速最大值",
    "count(wind_gusts_10m >= 17.2)": "统计10米阵风风速不低于17.2米/秒的小时数",
    "max(wind_speed_10m)": "取10米平均风速最大值",
    "max(wind_speed_100m)": "取100米平均风速最大值",
    "sum(precipitation)": "逐小时降水量求和",
    "max(precipitation)": "取逐小时降水量最大值",
    "count(precipitation >= 10)": "统计逐小时降水量不低于10毫米的小时数",
    "count(precipitation >= 20)": "统计逐小时降水量不低于20毫米的小时数",
    "sum(snowfall)": "逐小时降雪量求和",
    "max(snow_depth)": "取积雪深度最大值",
    "mean(shortwave_radiation)": "逐小时短波辐射求平均",
    "min(relative_humidity_2m)": "取2米相对湿度最小值",
    "count(shortwave_radiation <= 200)": "统计短波辐射不高于200瓦/平方米的小时数",
    "count(temperature_2m <= 0)": "统计2米气温不高于0摄氏度的小时数",
    "first temperature_2m - min(temperature_2m)": "窗口首小时气温减过程最低气温",
    "count(temperature_2m >= 35)": "统计2米气温不低于35摄氏度的小时数",
    "count(temperature_2m >= 40)": "统计2米气温不低于40摄氏度的小时数",
    "count(wind_speed_10m <= 2)": "统计10米平均风速不高于2米/秒的小时数",
    "count(wind_gusts_10m >= 24.5)": "统计10米阵风风速不低于24.5米/秒的小时数",
    "count(snowfall > 0)": "统计降雪量大于0的小时数",
    "count(temperature_2m <= 1 and precipitation > 0)": "统计2米气温不高于1摄氏度且有降水的小时数",
    "count(relative_humidity_2m >= 95 and wind_speed_10m <= 2 and shortwave_radiation <= 100)": "统计高湿、低风速、低辐照共同出现的小时数",
    "count(relative_humidity_2m >= 95)": "统计2米相对湿度不低于95%的小时数",
    "min(soil_moisture_0_to_7cm)": "取0至7厘米浅层土壤湿度最小值",
    "sum(et0_fao_evapotranspiration)": "逐小时参考蒸散量求和",
    "count(precipitation == 0)": "统计无降水小时数",
    "count(temperature_2m >= 30 and relative_humidity_2m <= 30 and wind_speed_10m >= 5 and precipitation == 0)": "统计高温、低湿、较大风、无降水共同出现的小时数",
    "count(relative_humidity_2m <= 30)": "统计相对湿度不高于30%的小时数",
}

THRESHOLD_LABELS = {
    "0 degC": "0摄氏度",
    "35 degC": "35摄氏度",
    "40 degC": "40摄氏度",
    "10 mm/h": "10毫米/小时",
    "20 mm/h": "20毫米/小时",
}

UNIT_LABELS = {
    "degC": "摄氏度",
    "m/s": "米/秒",
    "mm": "毫米",
    "cm": "厘米",
    "m": "米",
    "W/m2": "瓦/平方米",
    "mm/h": "毫米/小时",
    "h": "小时",
    "%": "%",
}


def display_index_name(index_name: str) -> str:
    return INDEX_LABELS.get(index_name, index_name)


def display_method(method: str) -> str:
    return METHOD_LABELS.get(method, method)


def display_threshold(threshold: str) -> str:
    return THRESHOLD_LABELS.get(threshold, threshold)


def display_unit(unit: str) -> str:
    return UNIT_LABELS.get(unit, unit)


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
    soil_moisture = _values(rows, "soil_moisture_0_to_7cm")
    et0 = _values(rows, "et0_fao_evapotranspiration")

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
        indices["precipitation_max_hourly"] = (max(precipitation), "mm", "max(precipitation)", "")
    if snowfall:
        indices["snowfall_sum"] = (sum(snowfall), "cm", "sum(snowfall)", "")
    if snow_depth:
        indices["snow_depth_max"] = (max(snow_depth), "m", "max(snow_depth)", "")
    if radiation:
        indices["shortwave_radiation_mean"] = (mean(radiation), "W/m2", "mean(shortwave_radiation)", "")
    if soil_moisture:
        indices["soil_moisture_min"] = (min(soil_moisture), "", "min(soil_moisture_0_to_7cm)", "")
    if et0:
        indices["et0_sum"] = (sum(et0), "mm", "sum(et0_fao_evapotranspiration)", "")

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
    elif event_type == "heavy_rain":
        if precipitation:
            indices["heavy_rain_hours_ge_10"] = (
                _count_ge(precipitation, 10),
                "h",
                "count(precipitation >= 10)",
                "10 mm/h",
            )
            indices["heavy_rain_hours_ge_20"] = (
                _count_ge(precipitation, 20),
                "h",
                "count(precipitation >= 20)",
                "20 mm/h",
            )
    elif event_type == "freezing_rain":
        if temp:
            indices["cold_hours_le_0"] = (_count_le(temp, 0), "h", "count(temperature_2m <= 0)", "0 degC")
        if temp and precipitation:
            freezing_hours = sum(
                1
                for row in rows
                if row.get("temperature_2m") is not None
                and row.get("precipitation") is not None
                and float(row["temperature_2m"]) <= 1
                and float(row["precipitation"]) > 0
            )
            indices["freezing_precip_hours"] = (
                freezing_hours,
                "h",
                "count(temperature_2m <= 1 and precipitation > 0)",
                "0-1摄氏度降水",
            )
    elif event_type == "typhoon":
        if gust:
            indices["typhoon_gust_hours_ge_24_5ms"] = (
                _count_ge(gust, 24.5),
                "h",
                "count(wind_gusts_10m >= 24.5)",
                "10级风",
            )
        if precipitation:
            indices["heavy_rain_hours_ge_10"] = (
                _count_ge(precipitation, 10),
                "h",
                "count(precipitation >= 10)",
                "10 mm/h",
            )
    elif event_type == "hail":
        if gust:
            indices["convective_gust_hours_ge_17_2ms"] = (
                _count_ge(gust, 17.2),
                "h",
                "count(wind_gusts_10m >= 17.2)",
                "8级风",
            )
        if gust and precipitation:
            hail_proxy_hours = sum(
                1
                for row in rows
                if row.get("wind_gusts_10m") is not None
                and row.get("precipitation") is not None
                and float(row["wind_gusts_10m"]) >= 17.2
                and float(row["precipitation"]) >= 10
            )
            indices["hail_proxy_hours"] = (
                hail_proxy_hours,
                "h",
                "count(wind_gusts_10m >= 17.2)",
                "强阵风叠加强降水",
            )
    elif event_type == "fog":
        if humidity:
            indices["high_humidity_hours_ge_95"] = (
                _count_ge(humidity, 95),
                "h",
                "count(relative_humidity_2m >= 95)",
                "95%",
            )
        if humidity and wind10 and radiation:
            fog_hours = sum(
                1
                for row in rows
                if row.get("relative_humidity_2m") is not None
                and row.get("wind_speed_10m") is not None
                and row.get("shortwave_radiation") is not None
                and float(row["relative_humidity_2m"]) >= 95
                and float(row["wind_speed_10m"]) <= 2
                and float(row["shortwave_radiation"]) <= 100
            )
            indices["fog_proxy_hours"] = (
                fog_hours,
                "h",
                "count(relative_humidity_2m >= 95 and wind_speed_10m <= 2 and shortwave_radiation <= 100)",
                "高湿低风速低辐照",
            )
    elif event_type == "wildfire_weather":
        if humidity:
            indices["low_humidity_hours_le_30"] = (
                _count_le(humidity, 30),
                "h",
                "count(relative_humidity_2m <= 30)",
                "30%",
            )
        if precipitation:
            indices["dry_hours_precip_eq_0"] = (
                sum(1 for value in precipitation if value == 0),
                "h",
                "count(precipitation == 0)",
                "无降水",
            )
        if temp and humidity and wind10 and precipitation:
            fire_hours = sum(
                1
                for row in rows
                if row.get("temperature_2m") is not None
                and row.get("relative_humidity_2m") is not None
                and row.get("wind_speed_10m") is not None
                and row.get("precipitation") is not None
                and float(row["temperature_2m"]) >= 30
                and float(row["relative_humidity_2m"]) <= 30
                and float(row["wind_speed_10m"]) >= 5
                and float(row["precipitation"]) == 0
            )
            indices["fire_weather_proxy_hours"] = (
                fire_hours,
                "h",
                "count(temperature_2m >= 30 and relative_humidity_2m <= 30 and wind_speed_10m >= 5 and precipitation == 0)",
                "高温低湿有风无雨",
            )
    elif event_type == "drought":
        if precipitation:
            indices["dry_hours_precip_eq_0"] = (
                sum(1 for value in precipitation if value == 0),
                "h",
                "count(precipitation == 0)",
                "无降水",
            )
        if temp:
            indices["hot_hours_ge_35"] = (_count_ge(temp, 35), "h", "count(temperature_2m >= 35)", "35 degC")

    return indices
