# 项目说明

## 项目概览

这是一个极端天气事件数据管理与展示项目。项目使用 Python 编写，核心能力包括：

- 管理五类极端气象事件：沙尘暴、寒潮、高温及静稳、强风、暴雪。
- 为每个事件维护代表点位及经纬度信息。
- 根据事件时间窗口和点位坐标调用 Open-Meteo Historical Weather API，拉取逐小时历史气象数据。
- 将事件、点位、气象时间序列和派生指标保存到 SQLite 数据库。
- 计算基础极端天气派生指标，并支持导出 CSV。
- 提供一个基于 Python 标准库 `http.server` 的本地 Web 仪表盘。

项目目前没有第三方运行依赖，`pyproject.toml` 中 `dependencies = []`，要求 Python 版本 `>=3.10`。

## 目录结构

- `README.md`：项目中文说明、快速开始命令、事件类型和数据库表说明。
- `pyproject.toml`：包元数据与命令行入口配置，注册脚本名为 `weather-db`。
- `start_dashboard.py`：一键启动仪表盘脚本，会清理指定端口上的旧进程，启动 Web 服务，并默认打开浏览器。
- `scripts/run_web.py`：手动启动 Web 仪表盘的薄封装，会把项目根目录加入 `sys.path` 后调用 `weather_events.web.main()`。
- `weather_events/`：核心 Python 包。
- `examples/`：事件和点位导入样例 CSV。
- `data/`：默认 SQLite 数据库存放目录，已被 `.gitignore` 忽略。
- `outputs/`：导出文件目录，已被 `.gitignore` 忽略。

## 核心模块

- `weather_events.models`
  - 定义 `Event`、`Location` 数据类。
  - 定义事件类型枚举值：`sandstorm`、`cold_wave`、`heat_stagnation`、`strong_wind`、`blizzard`。
  - 维护事件类型和部分子类型的中文展示标签。

- `weather_events.schema`
  - 定义 SQLite 建表 SQL。
  - 主要表包括 `events`、`locations`、`weather_timeseries`、`derived_indices`。

- `weather_events.db`
  - 封装 SQLite 访问。
  - `WeatherDatabase.init()` 会建表并执行简单迁移。
  - 事件和点位写入采用 upsert。
  - 删除事件会依赖外键级联删除相关点位、气象数据和派生指标。

- `weather_events.open_meteo`
  - 封装 Open-Meteo Archive API 调用。
  - 默认接口为 `https://archive-api.open-meteo.com/v1/archive`。
  - 默认时区为 `Asia/Shanghai`，风速单位为 `m/s`。
  - 默认拉取逐小时变量包括气温、湿度、降水、降雪、积雪深度、10 米/100 米风速、阵风、风向、短波辐射、气压、云量、蒸散和浅层土壤湿度。
  - 提供日期窗口扩展、按天分块和 API JSON 转数据库行的工具函数。

- `weather_events.analysis`
  - 根据事件类型和逐小时数据计算派生指标。
  - 通用指标包括最高/最低/变幅气温、最大阵风、风速、累计降水、累计降雪、最大积雪深度、平均短波辐射等。
  - 事件类型特有指标包括低湿度/低辐射小时数、低温小时数、降温代理值、高温小时数、静稳小时数、强阵风小时数、降雪小时数等。
  - 提供指标名、单位、阈值和计算方法的中文展示映射。

- `weather_events.cli`
  - 命令行入口，默认数据库路径为 `data/extreme_weather.sqlite`。
  - 支持初始化数据库、添加/删除事件、添加点位、列出事件、导入 CSV/JSON、拉取 Open-Meteo 数据、计算指标、导出指标 CSV。

- `weather_events.web`
  - 本地 Web 仪表盘，使用 `ThreadingHTTPServer` 和内嵌 HTML/CSS/SVG。
  - 支持按事件类型浏览事件、添加事件、添加点位、拉取气象数据、计算指标和下载 `indices.csv`。
  - 图表由服务端生成 SVG，不依赖前端框架。

## 常用命令

初始化数据库：

```powershell
python -m weather_events.cli init
```

导入示例事件和点位：

```powershell
python -m weather_events.cli import-events examples/events_seed.csv
python -m weather_events.cli import-locations examples/locations_seed.csv
```

拉取某个事件的逐小时气象数据：

```powershell
python -m weather_events.cli fetch --event-id E20250410_SANDSTORM
```

计算派生指标：

```powershell
python -m weather_events.cli analyze --event-id E20250410_SANDSTORM
```

导出指标：

```powershell
python -m weather_events.cli export-indices --out outputs/indices.csv
```

启动本地仪表盘：

```powershell
python start_dashboard.py
```

或手动启动：

```powershell
python scripts/run_web.py
```

默认访问地址：

```text
http://127.0.0.1:8000
```

## 数据库

默认数据库路径：

```text
data/extreme_weather.sqlite
```

当前工作区内该数据库存在，并包含一定量数据。一次检查结果为：

- `events`：31 条。
- `locations`：100 条。
- `weather_timeseries`：56472 条。
- `derived_indices`：638 条。

数据库表含义：

- `events`：极端事件目录，包含事件 ID、类型、子类型、名称、起止日期、区域、来源和备注。
- `locations`：事件关联点位，包含点位 ID、事件 ID、名称、省份、经纬度、点位类型和海拔。
- `weather_timeseries`：Open-Meteo 逐小时气象数据，主键为 `(event_id, location_id, time)`。
- `derived_indices`：派生指标，主键为 `(event_id, location_id, index_name)`。

## 数据文件

- `examples/events_seed.csv` 和 `examples/locations_seed.csv` 是基础示例数据。
- `examples/western_events_2006_2025.csv` 和 `examples/western_locations_2006_2025.csv` 是更大范围的西部地区事件和点位样例。
- `outputs/indices.csv` 和 `outputs/indices_cn.csv` 是导出结果样例或历史输出。

注意：部分示例 CSV 在终端中显示为乱码，README 使用 UTF-8 能正常显示。处理中文数据时优先使用 UTF-8 或 UTF-8 with BOM，并避免用错误代码页重新保存文件。

## 开发注意事项

- `.gitignore` 已忽略 `data/`、`outputs/`、虚拟环境和 Python 缓存，因此数据库和导出产物默认不应提交。
- 项目当前没有测试目录；修改核心逻辑后，至少应运行相关 CLI 命令或启动 Web 服务做基本验证。
- Web 页面中的中文文案和 CSS 均内嵌在 `weather_events.web` 中，修改界面时需要直接编辑该文件。
- `start_dashboard.py` 会尝试终止占用目标端口的进程，默认端口为 `8000`；在共享环境中使用时要注意端口清理行为。
- Open-Meteo 调用需要网络访问，`fetch` 命令可能因为 API、网络或日期范围问题失败；代码支持重试和分块拉取。
- 事件事实认定不应只依赖 Open-Meteo 数据，README 建议以中国气象局、国家气候中心、应急管理部、地方气象局等可靠来源为准。

## 事件类型编码

| 编码 | 含义 |
| --- | --- |
| `sandstorm` | 沙尘暴 |
| `cold_wave` | 寒潮 |
| `heat_stagnation` | 高温及静稳 |
| `strong_wind` | 强风 |
| `blizzard` | 暴雪 |

