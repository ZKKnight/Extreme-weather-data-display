# Extreme Weather Event Database

Python 初版功能：

- 管理五类极端气象事件：沙尘暴、寒潮、高温及静稳、强风、暴雪。
- 为事件添加代表点位。
- 根据事件时间和点位经纬度自动调用 Open-Meteo Historical Weather API。
- 将逐小时气象数据保存到 SQLite。
- 计算基础派生指标并导出 CSV。
- 提供本地 Web 界面进行事件、点位、数据拉取和指标查看。

## 快速开始

```powershell
python -m weather_events.cli init
python -m weather_events.cli import-events examples/events_seed.csv
python -m weather_events.cli import-locations examples/locations_seed.csv
# 若需要加载近20年全国范围事件库，可改用：
python -m weather_events.cli import-events examples/national_events_2006_2025.csv
python -m weather_events.cli import-locations examples/national_locations_2006_2025.csv
python -m weather_events.cli fetch --event-id E20250410_SANDSTORM
python -m weather_events.cli analyze --event-id E20250410_SANDSTORM
python -m weather_events.cli export-indices --out outputs/indices.csv
```

默认数据库路径为 `data/extreme_weather.sqlite`。

## 本地界面

推荐使用一键启动脚本，会先释放端口，再启动服务并自动打开浏览器：

```powershell
python start_dashboard.py
```

也可以手动启动：

```powershell
python scripts/run_web.py
```

打开：

```text
http://127.0.0.1:8000
```

## 事件类型编码

| 编码 | 中文含义 |
| --- | --- |
| `sandstorm` | 沙尘暴 |
| `cold_wave` | 寒潮 |
| `heat_stagnation` | 高温及静稳 |
| `strong_wind` | 强风 |
| `blizzard` | 暴雪 |
| `heavy_rain` | 强降水/暴雨洪涝 |
| `freezing_rain` | 冰冻/冻雨/雨凇 |
| `hail` | 冰雹 |
| `wildfire_weather` | 森林草原火险/高火险天气 |
| `drought` | 干旱 |

## 数据库表

- `events`：极端事件目录。
- `locations`：事件关联点位。
- `weather_timeseries`：Open-Meteo 逐小时气象数据。
- `derived_indices`：派生极端天气指标。

## 注意

Open-Meteo 适合提供事件发生期间的再分析气象序列。事件本身的认定建议继续以中国气象局、国家气候中心、应急管理部、地方气象局等可靠来源为准。
