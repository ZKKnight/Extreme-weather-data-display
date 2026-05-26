# Extreme Weather Event Database

Python 初版功能：

- 管理五类极端气象事件：沙尘暴、寒潮、高温及静稳、强风、暴雪。
- 为事件添加代表点位。
- 根据事件时间和点位经纬度自动调用 Open-Meteo Historical Weather API。
- 将逐小时气象数据保存到 SQLite。
- 计算基础派生指标并导出 CSV。

## 快速开始

```powershell
python -m weather_events.cli init
python -m weather_events.cli import-events examples/events_seed.csv
python -m weather_events.cli import-locations examples/locations_seed.csv
python -m weather_events.cli fetch --event-id E20250410_SANDSTORM
python -m weather_events.cli analyze --event-id E20250410_SANDSTORM
python -m weather_events.cli export-indices --out outputs/indices.csv
```

默认数据库路径为 `data/extreme_weather.sqlite`。

## 事件类型编码

| 编码 | 中文含义 |
| --- | --- |
| `sandstorm` | 沙尘暴 |
| `cold_wave` | 寒潮 |
| `heat_stagnation` | 高温及静稳 |
| `strong_wind` | 强风 |
| `blizzard` | 暴雪 |

## 数据库表

- `events`：极端事件目录。
- `locations`：事件关联点位。
- `weather_timeseries`：Open-Meteo 逐小时气象数据。
- `derived_indices`：派生极端天气指标。

## 注意

Open-Meteo 适合提供事件发生期间的再分析气象序列。事件本身的认定建议继续以中国气象局、国家气候中心、应急管理部、地方气象局等可靠来源为准。
