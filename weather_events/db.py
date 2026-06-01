from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Iterable

from .models import EVENT_TYPES, Event, Location
from .schema import SCHEMA_SQL


class WeatherDatabase:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def init(self) -> None:
        with self.connect() as conn:
            conn.executescript(SCHEMA_SQL)
            self._migrate(conn)

    def _migrate(self, conn: sqlite3.Connection) -> None:
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(events)").fetchall()}
        if "event_subtype" not in columns:
            conn.execute("ALTER TABLE events ADD COLUMN event_subtype TEXT DEFAULT ''")
        self._migrate_event_type_check(conn)

    def _migrate_event_type_check(self, conn: sqlite3.Connection) -> None:
        row = conn.execute("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'events'").fetchone()
        table_sql = row["sql"] if row else ""
        if all(f"'{event_type}'" in table_sql for event_type in EVENT_TYPES):
            return

        conn.execute("PRAGMA foreign_keys = OFF")
        try:
            conn.execute(
                """
                CREATE TABLE events_new (
                    event_id TEXT PRIMARY KEY,
                    event_type TEXT NOT NULL CHECK (
                        event_type IN (
                            'sandstorm', 'cold_wave', 'heat_stagnation', 'strong_wind', 'blizzard',
                            'heavy_rain', 'freezing_rain', 'typhoon', 'thunderstorm_hail', 'fog'
                        )
                    ),
                    event_subtype TEXT DEFAULT '',
                    name TEXT NOT NULL,
                    start_date TEXT NOT NULL,
                    end_date TEXT NOT NULL,
                    region TEXT NOT NULL,
                    source_name TEXT DEFAULT '',
                    source_url TEXT DEFAULT '',
                    notes TEXT DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                INSERT INTO events_new (
                    event_id, event_type, event_subtype, name, start_date, end_date, region,
                    source_name, source_url, notes, created_at, updated_at
                )
                SELECT
                    event_id, event_type, COALESCE(event_subtype, ''), name, start_date, end_date, region,
                    COALESCE(source_name, ''), COALESCE(source_url, ''), COALESCE(notes, ''),
                    created_at, updated_at
                FROM events
                """
            )
            conn.execute("DROP TABLE events")
            conn.execute("ALTER TABLE events_new RENAME TO events")
        finally:
            conn.execute("PRAGMA foreign_keys = ON")

    def add_event(self, event: Event) -> None:
        if event.event_type not in EVENT_TYPES:
            raise ValueError(f"Unsupported event_type: {event.event_type}")
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO events (
                    event_id, event_type, event_subtype, name, start_date, end_date, region,
                    source_name, source_url, notes, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(event_id) DO UPDATE SET
                    event_type=excluded.event_type,
                    event_subtype=excluded.event_subtype,
                    name=excluded.name,
                    start_date=excluded.start_date,
                    end_date=excluded.end_date,
                    region=excluded.region,
                    source_name=excluded.source_name,
                    source_url=excluded.source_url,
                    notes=excluded.notes,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (
                    event.event_id,
                    event.event_type,
                    event.event_subtype,
                    event.name,
                    event.start_date,
                    event.end_date,
                    event.region,
                    event.source_name,
                    event.source_url,
                    event.notes,
                ),
            )

    def delete_event(self, event_id: str) -> int:
        with self.connect() as conn:
            cur = conn.execute("DELETE FROM events WHERE event_id = ?", (event_id,))
            return cur.rowcount

    def add_location(self, location: Location) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO locations (
                    location_id, event_id, name, province, latitude, longitude,
                    location_type, altitude_m
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(location_id) DO UPDATE SET
                    event_id=excluded.event_id,
                    name=excluded.name,
                    province=excluded.province,
                    latitude=excluded.latitude,
                    longitude=excluded.longitude,
                    location_type=excluded.location_type,
                    altitude_m=excluded.altitude_m
                """,
                (
                    location.location_id,
                    location.event_id,
                    location.name,
                    location.province,
                    location.latitude,
                    location.longitude,
                    location.location_type,
                    location.altitude_m,
                ),
            )

    def get_event(self, event_id: str) -> sqlite3.Row | None:
        with self.connect() as conn:
            return conn.execute("SELECT * FROM events WHERE event_id = ?", (event_id,)).fetchone()

    def list_events(self) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute("SELECT * FROM events ORDER BY start_date DESC, event_id").fetchall()

    def list_locations(self, event_id: str) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute(
                "SELECT * FROM locations WHERE event_id = ? ORDER BY location_id", (event_id,)
            ).fetchall()

    def upsert_weather_rows(self, rows: Iterable[dict[str, Any]]) -> int:
        columns = [
            "event_id",
            "location_id",
            "time",
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
        sql = f"""
            INSERT INTO weather_timeseries ({", ".join(columns)})
            VALUES ({", ".join("?" for _ in columns)})
            ON CONFLICT(event_id, location_id, time) DO UPDATE SET
                {", ".join(f"{col}=excluded.{col}" for col in columns[3:])},
                fetched_at=CURRENT_TIMESTAMP
        """
        payload = [tuple(row.get(col) for col in columns) for row in rows]
        if not payload:
            return 0
        with self.connect() as conn:
            conn.executemany(sql, payload)
        return len(payload)

    def upsert_indices(self, event_id: str, location_id: str, indices: dict[str, tuple[Any, str, str, str]]) -> None:
        with self.connect() as conn:
            conn.executemany(
                """
                INSERT INTO derived_indices (
                    event_id, location_id, index_name, index_value, unit,
                    calculation_method, threshold, calculated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(event_id, location_id, index_name) DO UPDATE SET
                    index_value=excluded.index_value,
                    unit=excluded.unit,
                    calculation_method=excluded.calculation_method,
                    threshold=excluded.threshold,
                    calculated_at=CURRENT_TIMESTAMP
                """,
                [
                    (event_id, location_id, name, value, unit, method, threshold)
                    for name, (value, unit, method, threshold) in indices.items()
                ],
            )

    def get_weather_rows(self, event_id: str, location_id: str) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute(
                """
                SELECT * FROM weather_timeseries
                WHERE event_id = ? AND location_id = ?
                ORDER BY time
                """,
                (event_id, location_id),
            ).fetchall()
