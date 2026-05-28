from __future__ import annotations

import argparse
import html
import json
import sqlite3
from collections import defaultdict
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, unquote, urlparse

from .analysis import calculate_indices, display_index_name, display_method, display_threshold, display_unit
from .db import WeatherDatabase
from .models import EVENT_TYPES, EVENT_TYPE_LABELS, EVENT_SUBTYPE_LABELS, Event, Location
from .open_meteo import OpenMeteoClient, date_chunks, expand_date_window, hourly_json_to_rows


DEFAULT_DB = "data/extreme_weather.sqlite"


class PartialFetchError(RuntimeError):
    def __init__(self, total_rows: int, failures: list[str]) -> None:
        self.total_rows = total_rows
        self.failures = failures
        message = f"已保存 {total_rows} 条；失败点位：{'；'.join(failures)}"
        super().__init__(message)


def esc(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}


def safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def event_subtype_label(event: sqlite3.Row | dict[str, Any]) -> str:
    try:
        subtype = event["event_subtype"]
    except (KeyError, IndexError):
        subtype = ""
    event_type = event["event_type"]
    if not subtype and event_type == "heat_stagnation":
        subtype = "heat"
    return EVENT_SUBTYPE_LABELS.get(subtype, "")


class WeatherDashboard:
    def __init__(self, db_path: str | Path) -> None:
        self.database = WeatherDatabase(db_path)
        self.database.init()

    def events(self, event_type: str | None = None) -> list[sqlite3.Row]:
        if event_type in EVENT_TYPES:
            with self.database.connect() as conn:
                return conn.execute(
                    "SELECT * FROM events WHERE event_type = ? ORDER BY start_date DESC, event_id",
                    (event_type,),
                ).fetchall()
        return self.database.list_events()

    def selected_event(self, event_id: str | None, events: list[sqlite3.Row] | None = None) -> sqlite3.Row | None:
        if event_id:
            event = self.database.get_event(event_id)
            if event and (events is None or any(item["event_id"] == event["event_id"] for item in events)):
                return event
        events = events if events is not None else self.events()
        return events[0] if events else None

    def event_counts(self, event_id: str) -> dict[str, int]:
        with self.database.connect() as conn:
            return {
                "locations": conn.execute(
                    "SELECT COUNT(*) FROM locations WHERE event_id = ?", (event_id,)
                ).fetchone()[0],
                "weather_rows": conn.execute(
                    "SELECT COUNT(*) FROM weather_timeseries WHERE event_id = ?", (event_id,)
                ).fetchone()[0],
                "indices": conn.execute(
                    "SELECT COUNT(*) FROM derived_indices WHERE event_id = ?", (event_id,)
                ).fetchone()[0],
            }

    def indices(self, event_id: str) -> list[sqlite3.Row]:
        with self.database.connect() as conn:
            return conn.execute(
                """
                SELECT
                    l.name AS location_name, l.province, d.index_name, d.index_value,
                    d.unit, d.threshold, d.calculation_method
                FROM derived_indices d
                JOIN locations l ON l.location_id = d.location_id
                WHERE d.event_id = ?
                ORDER BY l.location_id, d.index_name
                """,
                (event_id,),
            ).fetchall()

    def daily_series(self, event_id: str) -> list[dict[str, Any]]:
        with self.database.connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    substr(w.time, 1, 10) AS day,
                    l.name AS location_name,
                    w.temperature_2m,
                    w.wind_speed_10m,
                    w.wind_gusts_10m,
                    w.shortwave_radiation,
                    w.precipitation,
                    w.snowfall,
                    w.snow_depth,
                    w.relative_humidity_2m
                FROM weather_timeseries w
                JOIN locations l ON l.location_id = w.location_id
                WHERE w.event_id = ?
                ORDER BY l.location_id, w.time
                """,
                (event_id,),
            ).fetchall()

        grouped: dict[tuple[str, str], dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
        for row in rows:
            key = (row["location_name"], row["day"])
            for field in (
                "temperature_2m",
                "wind_speed_10m",
                "wind_gusts_10m",
                "shortwave_radiation",
                "precipitation",
                "snowfall",
                "snow_depth",
                "relative_humidity_2m",
            ):
                value = safe_float(row[field])
                if value is not None:
                    grouped[key][field].append(value)

        series = []
        for (location_name, day), values in grouped.items():
            item: dict[str, Any] = {"location_name": location_name, "day": day}
            if values["temperature_2m"]:
                item["temperature_max"] = max(values["temperature_2m"])
                item["temperature_min"] = min(values["temperature_2m"])
                item["temperature_mean"] = sum(values["temperature_2m"]) / len(values["temperature_2m"])
                item["cold_hours_le_0"] = sum(1 for value in values["temperature_2m"] if value <= 0)
                item["hot_hours_ge_35"] = sum(1 for value in values["temperature_2m"] if value >= 35)
                item["hot_hours_ge_40"] = sum(1 for value in values["temperature_2m"] if value >= 40)
            if values["wind_speed_10m"]:
                item["wind_speed_mean"] = sum(values["wind_speed_10m"]) / len(values["wind_speed_10m"])
                item["stagnant_hours"] = sum(1 for value in values["wind_speed_10m"] if value <= 2)
            if values["wind_gusts_10m"]:
                item["wind_gust_max"] = max(values["wind_gusts_10m"])
                item["gust_hours_ge_17_2"] = sum(1 for value in values["wind_gusts_10m"] if value >= 17.2)
                item["gust_hours_ge_24_5"] = sum(1 for value in values["wind_gusts_10m"] if value >= 24.5)
            if values["shortwave_radiation"]:
                daylight = [value for value in values["shortwave_radiation"] if value > 0]
                item["shortwave_mean"] = sum(daylight) / len(daylight) if daylight else 0
                item["low_radiation_hours"] = sum(1 for value in values["shortwave_radiation"] if value <= 200)
            if values["precipitation"]:
                item["precipitation_sum"] = sum(values["precipitation"])
            if values["snowfall"]:
                item["snowfall_sum"] = sum(values["snowfall"])
                item["snowfall_hours_gt_0"] = sum(1 for value in values["snowfall"] if value > 0)
            if values["snow_depth"]:
                item["snow_depth_max"] = max(values["snow_depth"])
            if values["relative_humidity_2m"]:
                item["humidity_min"] = min(values["relative_humidity_2m"])
            series.append(item)
        return sorted(series, key=lambda item: (item["location_name"], item["day"]))

    def render(
        self,
        selected_event_id: str | None = None,
        message: str = "",
        event_type_filter: str | None = None,
    ) -> str:
        active_filter = event_type_filter if event_type_filter in EVENT_TYPES else EVENT_TYPES[0]
        events = self.events(active_filter or None)
        selected = self.selected_event(selected_event_id, events)
        selected_id = selected["event_id"] if selected else ""
        locations = self.database.list_locations(selected_id) if selected else []
        indices = self.indices(selected_id) if selected else []
        counts = self.event_counts(selected_id) if selected else {"locations": 0, "weather_rows": 0, "indices": 0}

        return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>极端气象事件数据库</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f6f7f9;
      --surface: #ffffff;
      --surface-2: #eef2f6;
      --border: #d7dde5;
      --text: #1f2933;
      --muted: #667085;
      --accent: #1f6feb;
      --accent-dark: #185abc;
      --danger: #b42318;
      --good: #16794c;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: "Microsoft YaHei", "Segoe UI", Arial, sans-serif;
      font-size: 14px;
      letter-spacing: 0;
    }}
    header {{
      height: 58px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 0 24px;
      border-bottom: 1px solid var(--border);
      background: var(--surface);
    }}
    h1 {{ margin: 0; font-size: 18px; font-weight: 650; }}
    h2 {{ margin: 0 0 12px; font-size: 15px; font-weight: 650; }}
    main {{
      display: grid;
      grid-template-columns: 330px minmax(0, 1fr);
      min-height: calc(100vh - 58px);
    }}
    aside {{
      border-right: 1px solid var(--border);
      background: var(--surface);
      padding: 16px;
      overflow: auto;
    }}
    section {{ padding: 18px 22px; }}
    .stack {{ display: grid; gap: 14px; }}
    .panel {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 14px;
    }}
    .event-list {{ display: grid; gap: 8px; }}
    .category-list {{ display: grid; gap: 8px; }}
    .category-row {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      min-height: 38px;
      padding: 8px 10px;
      border: 1px solid var(--border);
      border-radius: 8px;
      color: inherit;
      text-decoration: none;
      background: #fff;
    }}
    .category-row.active {{ border-color: var(--accent); background: #edf4ff; color: var(--accent); }}
    .event-row {{
      display: block;
      padding: 10px;
      border: 1px solid var(--border);
      border-radius: 8px;
      color: inherit;
      text-decoration: none;
      background: #fff;
    }}
    .event-row.active {{ border-color: var(--accent); box-shadow: inset 3px 0 0 var(--accent); }}
    .event-row strong {{ display: block; line-height: 1.35; }}
    .muted {{ color: var(--muted); font-size: 12px; }}
    .badge {{
      display: inline-flex;
      align-items: center;
      height: 22px;
      padding: 0 8px;
      border-radius: 999px;
      background: var(--surface-2);
      color: #344054;
      font-size: 12px;
      white-space: nowrap;
    }}
    .stats {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 10px;
    }}
    .stat {{
      padding: 12px;
      background: var(--surface-2);
      border-radius: 8px;
    }}
    .stat b {{ display: block; font-size: 22px; line-height: 1.1; }}
    form.grid {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 10px;
      align-items: end;
    }}
    form.event-form {{
      display: grid;
      grid-template-columns: minmax(0, 1fr);
      gap: 10px;
    }}
    .form-row {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 10px;
      align-items: end;
    }}
    .readonly-field {{
      min-height: 34px;
      display: flex;
      align-items: center;
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 7px 9px;
      background: var(--surface-2);
      color: #344054;
    }}
    label {{ display: grid; gap: 5px; color: var(--muted); font-size: 12px; }}
    input, select, textarea {{
      width: 100%;
      min-height: 34px;
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 7px 9px;
      background: #fff;
      color: var(--text);
      font: inherit;
    }}
    textarea {{ min-height: 70px; resize: vertical; }}
    button, .button {{
      min-height: 34px;
      border: 1px solid var(--accent);
      border-radius: 6px;
      padding: 7px 12px;
      background: var(--accent);
      color: #fff;
      font: inherit;
      cursor: pointer;
      text-decoration: none;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      white-space: nowrap;
    }}
    button:hover, .button:hover {{ background: var(--accent-dark); }}
    button.secondary {{ background: #fff; color: var(--accent); }}
    button.secondary:hover {{ background: #edf4ff; }}
    button.danger {{ background: #fff; color: var(--danger); border-color: #f0b8b2; }}
    button.danger:hover {{ background: #fff4f2; }}
    .actions {{ display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }}
    table {{ width: 100%; border-collapse: collapse; background: #fff; }}
    th, td {{ border-bottom: 1px solid var(--border); padding: 8px 7px; text-align: left; vertical-align: top; }}
    th {{ background: #f9fafb; color: #475467; font-weight: 650; }}
    .scroll {{ overflow: auto; max-height: 430px; border: 1px solid var(--border); border-radius: 8px; }}
    .chart-grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
    }}
    .chart-card {{
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 10px;
      background: #fff;
      min-width: 0;
    }}
    .chart-title {{ margin: 0 0 8px; font-size: 13px; font-weight: 650; }}
    .chart-card svg {{ display: block; width: 100%; height: 220px; overflow: visible; }}
    .chart-axis {{ stroke: #98a2b3; stroke-width: 1; }}
    .chart-grid-line {{ stroke: #e4e7ec; stroke-width: 1; }}
    .chart-label {{ fill: #667085; font-size: 10px; }}
    .chart-legend {{ display: flex; flex-wrap: wrap; gap: 8px; margin-top: 8px; }}
    .legend-item {{ display: inline-flex; align-items: center; gap: 5px; color: var(--muted); font-size: 12px; }}
    .legend-swatch {{ width: 10px; height: 10px; border-radius: 2px; display: inline-block; }}
    .message {{
      margin-bottom: 14px;
      padding: 10px 12px;
      border: 1px solid #b7d7c5;
      border-radius: 8px;
      background: #effaf4;
      color: var(--good);
    }}
    .wide {{ grid-column: span 2; }}
    .full {{ grid-column: 1 / -1; }}
    @media (max-width: 980px) {{
      main {{ grid-template-columns: 1fr; }}
      aside {{ border-right: 0; border-bottom: 1px solid var(--border); }}
      form.grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .form-row {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>极端气象事件数据库</h1>
    <div class="actions">
      <span class="badge">SQLite</span>
      <span class="badge">Open-Meteo Historical Weather API</span>
    </div>
  </header>
  <main>
    <aside>
      <div class="stack">
        <div class="panel">
          <h2>极端气象类别</h2>
          {self.render_category_nav(active_filter)}
        </div>
        <div class="panel">
          <h2>{esc(EVENT_TYPE_LABELS[active_filter])}事件</h2>
          <div class="event-list">{self.render_event_list(events, selected_id, active_filter)}</div>
        </div>
        <div class="panel">
          <h2>新增{esc(EVENT_TYPE_LABELS[active_filter])}事件</h2>
          {self.render_event_form(active_filter)}
        </div>
      </div>
    </aside>
    <section>
      {f'<div class="message">{esc(message)}</div>' if message else ''}
      {self.render_selected_event(selected, locations, indices, counts, active_filter)}
    </section>
  </main>
</body>
</html>"""

    def render_category_nav(self, active_filter: str) -> str:
        items = []
        for key in EVENT_TYPES:
            active = " active" if key == active_filter else ""
            items.append(
                f'<a class="category-row{active}" href="/?type={quote(key)}">'
                f'<strong>{esc(EVENT_TYPE_LABELS[key])}</strong><span>›</span></a>'
            )
        return f'<div class="category-list">{"".join(items)}</div>'

    def render_event_list(self, events: list[sqlite3.Row], selected_id: str, event_type_filter: str = "") -> str:
        if not events:
            return '<p class="muted">暂无事件</p>'
        items = []
        for event in events:
            active = " active" if event["event_id"] == selected_id else ""
            label = EVENT_TYPE_LABELS.get(event["event_type"], event["event_type"])
            subtype = event_subtype_label(event)
            label_text = f"{label}/{subtype}" if subtype else label
            href = f"/?event_id={quote(event['event_id'])}"
            if event_type_filter:
                href += f"&type={quote(event_type_filter)}"
            items.append(
                f"""<a class="event-row{active}" href="{href}">
  <strong>{esc(event['name'])}</strong>
  <span class="muted">{esc(label_text)} · {esc(event['start_date'])} 至 {esc(event['end_date'])}</span><br>
  <span class="muted">{esc(event['region'])}</span>
</a>"""
            )
        return "\n".join(items)

    def render_event_form(self, event_type: str) -> str:
        subtype_field = ""
        if event_type == "heat_stagnation":
            subtype_field = """<label>子类别<select name="event_subtype">
  <option value="heat">高温</option>
  <option value="stagnation">静稳</option>
</select></label>"""
        return f"""<form class="event-form" method="post" action="/events/add">
  <input type="hidden" name="event_type" value="{esc(event_type)}">
  <label>类别<span class="readonly-field">{esc(EVENT_TYPE_LABELS[event_type])}</span></label>
  {subtype_field}
  <label>编号<input name="event_id" required placeholder="E20250410_SANDSTORM"></label>
  <label>名称<input name="name" required></label>
  <div class="form-row">
    <label>开始日期<input type="date" name="start_date" required></label>
    <label>结束日期<input type="date" name="end_date" required></label>
  </div>
  <label>区域<input name="region" required></label>
  <label>来源名称<input name="source_name"></label>
  <label>来源链接<input name="source_url"></label>
  <label>备注<textarea name="notes"></textarea></label>
  <button type="submit">保存事件</button>
</form>"""

    def render_selected_event(
        self,
        selected: sqlite3.Row | None,
        locations: list[sqlite3.Row],
        indices: list[sqlite3.Row],
        counts: dict[str, int],
        active_filter: str,
    ) -> str:
        if selected is None:
            label = EVENT_TYPE_LABELS.get(active_filter, active_filter)
            return f"""<div class="stack">
  <div class="panel">
    <h2>{esc(label)}工作区</h2>
    <p class="muted">请先在左侧新增该类别的极端气象事件。新增后可为事件添加点位、拉取 Open-Meteo 历史气象数据并计算指标。</p>
  </div>
</div>"""
        label = EVENT_TYPE_LABELS.get(selected["event_type"], selected["event_type"])
        subtype = event_subtype_label(selected)
        label_text = f"{label}/{subtype}" if subtype else label
        source = (
            f'<a href="{esc(selected["source_url"])}" target="_blank" rel="noreferrer">{esc(selected["source_name"] or "来源")}</a>'
            if selected["source_url"]
            else esc(selected["source_name"])
        )
        return f"""<div class="stack">
  <div class="panel">
    <div class="actions" style="justify-content: space-between;">
      <div>
        <h2>{esc(selected['name'])}</h2>
        <div class="muted">{esc(selected['event_id'])} · {esc(label_text)} · {esc(selected['start_date'])} 至 {esc(selected['end_date'])}</div>
        <div class="muted">{esc(selected['region'])}{' · ' + source if source else ''}</div>
      </div>
      <form method="post" action="/events/delete">
        <input type="hidden" name="event_id" value="{esc(selected['event_id'])}">
        <input type="hidden" name="event_type" value="{esc(selected['event_type'])}">
        <button class="danger" type="submit">删除事件</button>
      </form>
    </div>
  </div>
  <div class="stats">
    <div class="stat"><b>{counts['locations']}</b><span class="muted">点位</span></div>
    <div class="stat"><b>{counts['weather_rows']}</b><span class="muted">气象序列</span></div>
    <div class="stat"><b>{counts['indices']}</b><span class="muted">派生指标</span></div>
  </div>
  <div class="panel">
    <h2>数据操作</h2>
    <div class="actions">
      <form method="post" action="/events/fetch">
        <input type="hidden" name="event_id" value="{esc(selected['event_id'])}">
        <input type="hidden" name="event_type" value="{esc(selected['event_type'])}">
        <button type="submit">拉取气象数据</button>
      </form>
      <form method="post" action="/events/analyze">
        <input type="hidden" name="event_id" value="{esc(selected['event_id'])}">
        <input type="hidden" name="event_type" value="{esc(selected['event_type'])}">
        <button class="secondary" type="submit">计算指标</button>
      </form>
      <a class="button" href="/export/indices.csv">导出指标 CSV</a>
    </div>
  </div>
  <div class="panel">
    <h2>新增点位</h2>
    {self.render_location_form(selected['event_id'], selected['event_type'])}
  </div>
  <div class="panel">
    <h2>点位列表</h2>
    {self.render_locations(locations)}
  </div>
  <div class="panel">
    <h2>指标结果</h2>
    {self.render_indices(indices)}
  </div>
  <div class="panel">
    <h2>数据图表</h2>
    {self.render_event_charts(selected['event_id'], selected['event_type'])}
  </div>
</div>"""

    def render_location_form(self, event_id: str, event_type: str) -> str:
        return f"""<form class="grid" method="post" action="/locations/add">
  <input type="hidden" name="event_id" value="{esc(event_id)}">
  <input type="hidden" name="event_type" value="{esc(event_type)}">
  <label>点位编号<input name="location_id" required placeholder="E20250410_JIUQUAN"></label>
  <label>名称<input name="name" required></label>
  <label>省份<input name="province"></label>
  <label>类型<input name="location_type" value="representative_point"></label>
  <label>纬度<input type="number" step="0.000001" name="latitude" required></label>
  <label>经度<input type="number" step="0.000001" name="longitude" required></label>
  <label>海拔<input type="number" step="0.1" name="altitude_m"></label>
  <button type="submit">保存点位</button>
</form>"""

    def render_locations(self, locations: list[sqlite3.Row]) -> str:
        if not locations:
            return '<p class="muted">暂无点位</p>'
        rows = []
        for location in locations:
            rows.append(
                f"""<tr>
  <td>{esc(location['location_id'])}</td>
  <td>{esc(location['name'])}</td>
  <td>{esc(location['province'])}</td>
  <td>{esc(location['latitude'])}</td>
  <td>{esc(location['longitude'])}</td>
  <td>{esc(location['location_type'])}</td>
</tr>"""
            )
        return f"""<div class="scroll"><table>
  <thead><tr><th>编号</th><th>名称</th><th>省份</th><th>纬度</th><th>经度</th><th>类型</th></tr></thead>
  <tbody>{''.join(rows)}</tbody>
</table></div>"""

    def render_indices(self, indices: list[sqlite3.Row]) -> str:
        if not indices:
            return '<p class="muted">暂无指标</p>'
        rows = []
        for item in indices:
            rows.append(
                f"""<tr>
  <td>{esc(item['location_name'])}</td>
  <td>{esc(display_index_name(item['index_name']))}</td>
  <td>{esc(round(item['index_value'], 4) if item['index_value'] is not None else '')}</td>
  <td>{esc(display_unit(item['unit']))}</td>
  <td>{esc(display_threshold(item['threshold']))}</td>
  <td>{esc(display_method(item['calculation_method']))}</td>
</tr>"""
            )
        return f"""<div class="scroll"><table>
  <thead><tr><th>点位</th><th>指标</th><th>数值</th><th>单位</th><th>阈值</th><th>方法</th></tr></thead>
  <tbody>{''.join(rows)}</tbody>
</table></div>"""

    def render_event_charts(self, event_id: str, event_type: str) -> str:
        series = self.daily_series(event_id)
        if not series:
            return '<p class="muted">暂无气象序列。请先点击“拉取气象数据”。</p>'
        configs = self.chart_configs(event_type)
        charts = [self.render_chart(series, **config) for config in configs]
        charts.extend(self.render_category_feature_charts(series, event_type))
        return f'<div class="chart-grid">{"".join(charts)}</div>'

    def chart_configs(self, event_type: str) -> list[dict[str, Any]]:
        common_temp = {
            "title": "日最高气温变化",
            "field": "temperature_max",
            "unit": "摄氏度",
            "mode": "line",
            "color": "#d92d20",
        }
        if event_type == "sandstorm":
            return [
                {
                    "title": "最大阵风风速变化",
                    "field": "wind_gust_max",
                    "unit": "米/秒",
                    "mode": "line",
                    "color": "#7a5c00",
                    "threshold": 17.2,
                    "threshold_label": "8级风",
                },
                {
                    "title": "平均短波辐射变化",
                    "field": "shortwave_mean",
                    "unit": "瓦/平方米",
                    "mode": "line",
                    "color": "#f79009",
                },
            ]
        if event_type == "cold_wave":
            return [
                {
                    "title": "日最低气温变化",
                    "field": "temperature_min",
                    "unit": "摄氏度",
                    "mode": "line",
                    "color": "#175cd3",
                    "threshold": 0,
                    "threshold_label": "0摄氏度",
                },
                {
                    "title": "最大阵风风速变化",
                    "field": "wind_gust_max",
                    "unit": "米/秒",
                    "mode": "line",
                    "color": "#475467",
                },
            ]
        if event_type == "heat_stagnation":
            return [
                {**common_temp, "threshold": 35, "threshold_label": "35摄氏度"},
                {
                    "title": "静稳小时数变化",
                    "field": "stagnant_hours",
                    "unit": "小时",
                    "mode": "bar",
                    "color": "#12b76a",
                },
            ]
        if event_type == "strong_wind":
            return [
                {
                    "title": "最大阵风风速变化",
                    "field": "wind_gust_max",
                    "unit": "米/秒",
                    "mode": "line",
                    "color": "#7f56d9",
                    "threshold": 24.5,
                    "threshold_label": "10级风",
                },
                {
                    "title": "10米平均风速变化",
                    "field": "wind_speed_mean",
                    "unit": "米/秒",
                    "mode": "line",
                    "color": "#0e9384",
                },
            ]
        if event_type == "blizzard":
            return [
                {
                    "title": "累计降雪量变化",
                    "field": "snowfall_sum",
                    "unit": "厘米",
                    "mode": "bar",
                    "color": "#2e90fa",
                },
                {
                    "title": "最大积雪深度变化",
                    "field": "snow_depth_max",
                    "unit": "米",
                    "mode": "line",
                    "color": "#175cd3",
                },
            ]
        return [common_temp]

    def render_category_feature_charts(self, series: list[dict[str, Any]], event_type: str) -> list[str]:
        if event_type == "sandstorm":
            return [
                self.render_scatter_chart(
                    series,
                    "风速-辐照耦合关系",
                    "wind_gust_max",
                    "shortwave_mean",
                    "最大阵风（米/秒）",
                    "平均短波辐射（瓦/平方米）",
                    "#b54708",
                ),
                self.render_location_total_bar(
                    series,
                    "低辐照小时数对比",
                    "low_radiation_hours",
                    "小时",
                    "#f79009",
                    "短波辐射不高于200瓦/平方米",
                ),
            ]
        if event_type == "cold_wave":
            return [
                self.render_temperature_drop_chart(series),
                self.render_location_total_bar(series, "低温持续小时数", "cold_hours_le_0", "小时", "#2e90fa", "2米气温不高于0摄氏度"),
            ]
        if event_type == "heat_stagnation":
            return [
                self.render_stacked_location_bar(
                    series,
                    "高温小时构成",
                    [("hot_hours_ge_35", "35摄氏度及以上", "#f79009"), ("hot_hours_ge_40", "40摄氏度及以上", "#d92d20")],
                    "小时",
                ),
                self.render_location_total_bar(series, "静稳小时数对比", "stagnant_hours", "小时", "#12b76a", "10米平均风速不高于2米/秒"),
            ]
        if event_type == "strong_wind":
            return [
                self.render_location_max_bar(series, "阵风峰值排名", "wind_gust_max", "米/秒", "#7f56d9", "事件期间日最大阵风的最高值"),
                self.render_stacked_location_bar(
                    series,
                    "大风超限小时数",
                    [("gust_hours_ge_17_2", "8级及以上", "#f79009"), ("gust_hours_ge_24_5", "10级及以上", "#d92d20")],
                    "小时",
                ),
            ]
        if event_type == "blizzard":
            return [
                self.render_stacked_location_bar(
                    series,
                    "降雪与低温持续性",
                    [("snowfall_hours_gt_0", "降雪小时", "#2e90fa"), ("cold_hours_le_0", "低温小时", "#175cd3")],
                    "小时",
                ),
                self.render_scatter_chart(
                    series,
                    "降雪-积雪响应关系",
                    "snowfall_sum",
                    "snow_depth_max",
                    "日降雪量（厘米）",
                    "最大积雪深度（米）",
                    "#175cd3",
                ),
            ]
        return []

    def aggregate_by_location(self, series: list[dict[str, Any]], field: str, mode: str = "sum") -> list[dict[str, Any]]:
        grouped: dict[str, list[float]] = defaultdict(list)
        for item in series:
            value = item.get(field)
            if value is not None:
                grouped[item["location_name"]].append(float(value))
        rows = []
        for location, values in grouped.items():
            if not values:
                continue
            if mode == "max":
                value = max(values)
            elif mode == "min":
                value = min(values)
            else:
                value = sum(values)
            rows.append({"location_name": location, "value": value})
        return sorted(rows, key=lambda row: row["value"], reverse=True)

    def render_location_total_bar(self, series: list[dict[str, Any]], title: str, field: str, unit: str, color: str, note: str) -> str:
        return self.render_horizontal_bar_chart(title, self.aggregate_by_location(series, field, "sum"), unit, color, note)

    def render_location_max_bar(self, series: list[dict[str, Any]], title: str, field: str, unit: str, color: str, note: str) -> str:
        return self.render_horizontal_bar_chart(title, self.aggregate_by_location(series, field, "max"), unit, color, note)

    def render_temperature_drop_chart(self, series: list[dict[str, Any]]) -> str:
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for item in series:
            if item.get("temperature_mean") is not None and item.get("temperature_min") is not None:
                grouped[item["location_name"]].append(item)
        rows = []
        for location, items in grouped.items():
            items = sorted(items, key=lambda item: item["day"])
            start_temp = float(items[0]["temperature_mean"])
            min_temp = min(float(item["temperature_min"]) for item in items)
            rows.append({"location_name": location, "value": max(0, start_temp - min_temp)})
        return self.render_horizontal_bar_chart("过程降温幅度", rows, "摄氏度", "#175cd3", "首日平均气温减过程最低气温")

    def render_horizontal_bar_chart(
        self,
        title: str,
        rows: list[dict[str, Any]],
        unit: str,
        color: str,
        note: str,
    ) -> str:
        if not rows:
            return f'<div class="chart-card"><p class="chart-title">{esc(title)}</p><p class="muted">暂无可绘制数据</p></div>'
        max_value = max(row["value"] for row in rows) or 1
        width = 520
        height = max(190, 44 + len(rows) * 34)
        left = 92
        right = 42
        top = 24
        bar_h = 18
        gap = 14
        plot_w = width - left - right
        parts = [
            f'<div class="chart-card"><p class="chart-title">{esc(title)}</p>',
            f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="{esc(title)}">',
        ]
        for index, row in enumerate(rows):
            y = top + index * (bar_h + gap)
            bar_w = plot_w * row["value"] / max_value
            parts.append(f'<text class="chart-label" x="4" y="{y + 13}">{esc(row["location_name"])}</text>')
            parts.append(f'<rect x="{left}" y="{y}" width="{plot_w}" height="{bar_h}" fill="#eef2f6"></rect>')
            parts.append(f'<rect x="{left}" y="{y}" width="{bar_w:.2f}" height="{bar_h}" fill="{color}" opacity="0.85"></rect>')
            parts.append(f'<text class="chart-label" x="{left + bar_w + 6:.2f}" y="{y + 13}">{esc(round(row["value"], 1))}</text>')
        parts.append(f'<text class="chart-label" x="{left}" y="{height - 8}">{esc(note)} · {esc(unit)}</text>')
        parts.append("</svg></div>")
        return "".join(parts)

    def render_stacked_location_bar(self, series: list[dict[str, Any]], title: str, fields: list[tuple[str, str, str]], unit: str) -> str:
        locations = sorted({item["location_name"] for item in series})
        rows = []
        for location in locations:
            values = []
            for field, label, color in fields:
                total = sum(float(item.get(field) or 0) for item in series if item["location_name"] == location)
                values.append((field, label, color, total))
            rows.append((location, values))
        max_total = max((sum(value[3] for value in values) for _, values in rows), default=0) or 1
        width = 520
        height = max(190, 48 + len(rows) * 34)
        left = 92
        top = 24
        plot_w = width - left - 42
        bar_h = 18
        parts = [
            f'<div class="chart-card"><p class="chart-title">{esc(title)}</p>',
            f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="{esc(title)}">',
        ]
        for row_index, (location, values) in enumerate(rows):
            y = top + row_index * 32
            x = left
            parts.append(f'<text class="chart-label" x="4" y="{y + 13}">{esc(location)}</text>')
            parts.append(f'<rect x="{left}" y="{y}" width="{plot_w}" height="{bar_h}" fill="#eef2f6"></rect>')
            for _, _, color, value in values:
                w = plot_w * value / max_total
                parts.append(f'<rect x="{x:.2f}" y="{y}" width="{w:.2f}" height="{bar_h}" fill="{color}" opacity="0.85"></rect>')
                x += w
        parts.append(f'<text class="chart-label" x="{left}" y="{height - 8}">{esc(unit)}</text>')
        parts.append("</svg>")
        legend = "".join(
            f'<span class="legend-item"><span class="legend-swatch" style="background:{color}"></span>{esc(label)}</span>'
            for _, label, color in fields
        )
        parts.append(f'<div class="chart-legend">{legend}</div></div>')
        return "".join(parts)

    def render_scatter_chart(
        self,
        series: list[dict[str, Any]],
        title: str,
        x_field: str,
        y_field: str,
        x_label: str,
        y_label: str,
        color: str,
    ) -> str:
        points = [item for item in series if item.get(x_field) is not None and item.get(y_field) is not None]
        if not points:
            return f'<div class="chart-card"><p class="chart-title">{esc(title)}</p><p class="muted">暂无可绘制数据</p></div>'
        width = 520
        height = 220
        left = 48
        right = 18
        top = 18
        bottom = 42
        plot_w = width - left - right
        plot_h = height - top - bottom
        xs = [float(item[x_field]) for item in points]
        ys = [float(item[y_field]) for item in points]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        if min_x == max_x:
            max_x += 1
        if min_y == max_y:
            max_y += 1

        def x_pos(value: float) -> float:
            return left + (value - min_x) * plot_w / (max_x - min_x)

        def y_pos(value: float) -> float:
            return top + (max_y - value) * plot_h / (max_y - min_y)

        parts = [
            f'<div class="chart-card"><p class="chart-title">{esc(title)}</p>',
            f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="{esc(title)}">',
            f'<line class="chart-axis" x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_h}"></line>',
            f'<line class="chart-axis" x1="{left}" y1="{top + plot_h}" x2="{left + plot_w}" y2="{top + plot_h}"></line>',
        ]
        for item in points:
            parts.append(
                f'<circle cx="{x_pos(float(item[x_field])):.2f}" cy="{y_pos(float(item[y_field])):.2f}" r="3.2" fill="{color}" opacity="0.65"></circle>'
            )
        parts.append(f'<text class="chart-label" x="{left}" y="{height - 8}">{esc(x_label)}</text>')
        parts.append(f'<text class="chart-label" x="{width - 150}" y="12">{esc(y_label)}</text>')
        parts.append("</svg></div>")
        return "".join(parts)

    def render_chart(
        self,
        series: list[dict[str, Any]],
        title: str,
        field: str,
        unit: str,
        mode: str,
        color: str,
        threshold: float | None = None,
        threshold_label: str = "",
    ) -> str:
        locations = sorted({item["location_name"] for item in series if item.get(field) is not None})
        if not locations:
            return f'<div class="chart-card"><p class="chart-title">{esc(title)}</p><p class="muted">暂无可绘制数据</p></div>'
        days = sorted({item["day"] for item in series if item.get(field) is not None})
        values = [float(item[field]) for item in series if item.get(field) is not None]
        if threshold is not None:
            values.append(float(threshold))
        min_value = min(values)
        max_value = max(values)
        if min_value == max_value:
            min_value -= 1
            max_value += 1
        padding = (max_value - min_value) * 0.08
        min_value -= padding
        max_value += padding

        width = 520
        height = 220
        left = 48
        right = 18
        top = 18
        bottom = 36
        plot_w = width - left - right
        plot_h = height - top - bottom
        palette = [color, "#175cd3", "#12b76a", "#f04438", "#7f56d9", "#0e9384"]

        def x_pos(day: str) -> float:
            if len(days) <= 1:
                return left + plot_w / 2
            return left + days.index(day) * plot_w / (len(days) - 1)

        def y_pos(value: float) -> float:
            return top + (max_value - value) * plot_h / (max_value - min_value)

        parts = [
            f'<div class="chart-card"><p class="chart-title">{esc(title)}</p>',
            f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="{esc(title)}">',
            f'<line class="chart-axis" x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_h}"></line>',
            f'<line class="chart-axis" x1="{left}" y1="{top + plot_h}" x2="{left + plot_w}" y2="{top + plot_h}"></line>',
        ]
        for tick in range(5):
            value = min_value + (max_value - min_value) * tick / 4
            y = y_pos(value)
            parts.append(f'<line class="chart-grid-line" x1="{left}" y1="{y:.2f}" x2="{left + plot_w}" y2="{y:.2f}"></line>')
            parts.append(f'<text class="chart-label" x="4" y="{y + 3:.2f}">{esc(round(value, 1))}</text>')
        if threshold is not None:
            y = y_pos(threshold)
            parts.append(f'<line x1="{left}" y1="{y:.2f}" x2="{left + plot_w}" y2="{y:.2f}" stroke="#d92d20" stroke-dasharray="5 4"></line>')
            parts.append(f'<text class="chart-label" x="{left + plot_w - 52}" y="{y - 4:.2f}" fill="#d92d20">{esc(threshold_label)}</text>')

        for index, location in enumerate(locations[:6]):
            loc_series = [item for item in series if item["location_name"] == location and item.get(field) is not None]
            loc_color = palette[index % len(palette)]
            if mode == "bar":
                bar_w = max(2, plot_w / max(1, len(days) * len(locations[:6])) * 0.7)
                for item in loc_series:
                    x = x_pos(item["day"]) + (index - (len(locations[:6]) - 1) / 2) * bar_w
                    y = y_pos(float(item[field]))
                    parts.append(
                        f'<rect x="{x:.2f}" y="{y:.2f}" width="{bar_w:.2f}" height="{top + plot_h - y:.2f}" fill="{loc_color}" opacity="0.75"></rect>'
                    )
            else:
                points = " ".join(f'{x_pos(item["day"]):.2f},{y_pos(float(item[field])):.2f}' for item in loc_series)
                parts.append(f'<polyline points="{points}" fill="none" stroke="{loc_color}" stroke-width="2.2"></polyline>')
                for item in loc_series:
                    parts.append(f'<circle cx="{x_pos(item["day"]):.2f}" cy="{y_pos(float(item[field])):.2f}" r="2.5" fill="{loc_color}"></circle>')
        if days:
            parts.append(f'<text class="chart-label" x="{left}" y="{height - 10}">{esc(days[0])}</text>')
            parts.append(f'<text class="chart-label" x="{left + plot_w - 62}" y="{height - 10}">{esc(days[-1])}</text>')
        parts.append(f'<text class="chart-label" x="{width - 58}" y="12">{esc(unit)}</text>')
        parts.append("</svg>")
        legend = "".join(
            f'<span class="legend-item"><span class="legend-swatch" style="background:{palette[index % len(palette)]}"></span>{esc(location)}</span>'
            for index, location in enumerate(locations[:6])
        )
        parts.append(f'<div class="chart-legend">{legend}</div></div>')
        return "".join(parts)

    def add_event(self, form: dict[str, list[str]]) -> str:
        event = Event(
            event_id=required(form, "event_id"),
            event_type=required(form, "event_type"),  # type: ignore[arg-type]
            event_subtype=optional(form, "event_subtype"),
            name=required(form, "name"),
            start_date=required(form, "start_date"),
            end_date=required(form, "end_date"),
            region=required(form, "region"),
            source_name=optional(form, "source_name"),
            source_url=optional(form, "source_url"),
            notes=optional(form, "notes"),
        )
        self.database.add_event(event)
        return event.event_id

    def add_location(self, form: dict[str, list[str]]) -> str:
        altitude = optional(form, "altitude_m")
        location = Location(
            location_id=required(form, "location_id"),
            event_id=required(form, "event_id"),
            name=required(form, "name"),
            province=optional(form, "province"),
            latitude=float(required(form, "latitude")),
            longitude=float(required(form, "longitude")),
            location_type=optional(form, "location_type") or "representative_point",
            altitude_m=float(altitude) if altitude else None,
        )
        self.database.add_location(location)
        return location.event_id

    def fetch_event(self, event_id: str) -> int:
        event = self.database.get_event(event_id)
        if event is None:
            raise ValueError(f"Event not found: {event_id}")
        locations = self.database.list_locations(event_id)
        if not locations:
            raise ValueError(f"No locations for event: {event_id}")

        start, end = expand_date_window(event["start_date"], event["end_date"])
        client = OpenMeteoClient(timeout_s=45, max_retries=4)
        total = 0
        failures = []
        for location in locations:
            location_total = 0
            for chunk_start, chunk_end in date_chunks(start, end, chunk_days=14):
                try:
                    data = client.fetch_hourly(
                        latitude=location["latitude"],
                        longitude=location["longitude"],
                        start_date=chunk_start,
                        end_date=chunk_end,
                    )
                    rows = hourly_json_to_rows(data, event_id, location["location_id"])
                    location_total += self.database.upsert_weather_rows(rows)
                except Exception as exc:
                    failures.append(
                        f"{location['location_id']}（{location['name']}）"
                        f"{chunk_start}至{chunk_end}：{exc}"
                    )
            total += location_total
        if failures:
            raise PartialFetchError(total, failures)
        return total

    def analyze_event(self, event_id: str) -> int:
        event = self.database.get_event(event_id)
        if event is None:
            raise ValueError(f"Event not found: {event_id}")
        count = 0
        for location in self.database.list_locations(event_id):
            rows = [row_to_dict(row) for row in self.database.get_weather_rows(event_id, location["location_id"])]
            indices = calculate_indices(event["event_type"], rows)
            self.database.upsert_indices(event_id, location["location_id"], indices)
            count += len(indices)
        return count

    def export_indices_csv(self) -> bytes:
        with self.database.connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    e.event_id, e.event_type, e.name AS event_name, e.start_date, e.end_date, e.region,
                    l.location_id, l.name AS location_name, l.province, l.latitude, l.longitude,
                    d.index_name, d.index_value, d.unit, d.threshold, d.calculation_method
                FROM derived_indices d
                JOIN events e ON e.event_id = d.event_id
                JOIN locations l ON l.location_id = d.location_id
                ORDER BY e.start_date DESC, e.event_id, l.location_id, d.index_name
                """
            ).fetchall()
        headers = rows[0].keys() if rows else [
            "event_id", "event_type", "event_name", "start_date", "end_date", "region",
            "location_id", "location_name", "province", "latitude", "longitude",
            "index_name", "index_value", "unit", "threshold", "calculation_method",
        ]
        lines = [",".join(headers)]
        for row in rows:
            values = []
            for key in headers:
                value = "" if row[key] is None else str(row[key])
                if key == "index_name":
                    value = display_index_name(value)
                elif key == "unit":
                    value = display_unit(value)
                elif key == "threshold":
                    value = display_threshold(value)
                elif key == "calculation_method":
                    value = display_method(value)
                values.append(json.dumps(value, ensure_ascii=False))
            lines.append(",".join(values))
        return ("\ufeff" + "\n".join(lines) + "\n").encode("utf-8")


def required(form: dict[str, list[str]], key: str) -> str:
    value = optional(form, key)
    if not value:
        raise ValueError(f"Missing field: {key}")
    return value


def optional(form: dict[str, list[str]], key: str) -> str:
    values = form.get(key, [""])
    return values[0].strip() if values else ""


def make_handler(app: WeatherDashboard) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            query = parse_qs(parsed.query)
            if parsed.path == "/":
                self.send_html(
                    app.render(
                        query.get("event_id", [None])[0],
                        query.get("message", [""])[0],
                        query.get("type", [""])[0],
                    )
                )
            elif parsed.path == "/export/indices.csv":
                payload = app.export_indices_csv()
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/csv; charset=utf-8")
                self.send_header("Content-Disposition", 'attachment; filename="indices.csv"')
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
            else:
                self.send_error(HTTPStatus.NOT_FOUND)

        def do_POST(self) -> None:
            try:
                form = self.read_form()
                parsed = urlparse(self.path)
                if parsed.path == "/events/add":
                    event_id = app.add_event(form)
                    self.redirect(event_id, "事件已保存", optional(form, "event_type"))
                elif parsed.path == "/events/delete":
                    event_id = required(form, "event_id")
                    event_type = optional(form, "event_type")
                    app.database.delete_event(event_id)
                    self.redirect("", "事件已删除", event_type)
                elif parsed.path == "/locations/add":
                    event_id = app.add_location(form)
                    self.redirect(event_id, "点位已保存", optional(form, "event_type"))
                elif parsed.path == "/events/fetch":
                    event_id = required(form, "event_id")
                    try:
                        total = app.fetch_event(event_id)
                        self.redirect(event_id, f"气象数据已拉取：{total} 条", optional(form, "event_type"))
                    except PartialFetchError as exc:
                        self.redirect(event_id, f"部分气象数据已拉取：{exc}", optional(form, "event_type"))
                elif parsed.path == "/events/analyze":
                    event_id = required(form, "event_id")
                    total = app.analyze_event(event_id)
                    self.redirect(event_id, f"指标已计算：{total} 项", optional(form, "event_type"))
                else:
                    self.send_error(HTTPStatus.NOT_FOUND)
            except Exception as exc:
                self.redirect(optional(parse_qs(urlparse(self.path).query), "event_id"), f"操作失败：{exc}")

        def read_form(self) -> dict[str, list[str]]:
            length = int(self.headers.get("Content-Length", "0"))
            payload = self.rfile.read(length).decode("utf-8")
            return parse_qs(payload, keep_blank_values=True)

        def redirect(self, event_id: str, message: str, event_type: str = "") -> None:
            target = f"/?message={quote(message)}"
            params = []
            if event_id:
                params.append(f"event_id={quote(event_id)}")
            if event_type in EVENT_TYPES:
                params.append(f"type={quote(event_type)}")
            params.append(f"message={quote(message)}")
            target = f"/?{'&'.join(params)}"
            self.send_response(HTTPStatus.SEE_OTHER)
            self.send_header("Location", target)
            self.end_headers()

        def send_html(self, body: str) -> None:
            payload = body.encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format: str, *args: Any) -> None:
            return

    return Handler


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Extreme weather event dashboard")
    parser.add_argument("--db", default=DEFAULT_DB, help=f"SQLite database path, default: {DEFAULT_DB}")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    app = WeatherDashboard(args.db)
    server = ThreadingHTTPServer((args.host, args.port), make_handler(app))
    print(f"Dashboard running at http://{args.host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
