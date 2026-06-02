SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS events (
    event_id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL CHECK (
        event_type IN (
            'sandstorm', 'cold_wave', 'heat_stagnation', 'strong_wind', 'blizzard',
            'heavy_rain', 'freezing_rain', 'hail',
            'wildfire_weather', 'drought'
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
);


CREATE TABLE IF NOT EXISTS locations (
    location_id TEXT PRIMARY KEY,
    event_id TEXT NOT NULL,
    name TEXT NOT NULL,
    province TEXT DEFAULT '',
    latitude REAL NOT NULL,
    longitude REAL NOT NULL,
    location_type TEXT DEFAULT 'representative_point',
    altitude_m REAL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (event_id) REFERENCES events(event_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS weather_timeseries (
    event_id TEXT NOT NULL,
    location_id TEXT NOT NULL,
    time TEXT NOT NULL,
    temperature_2m REAL,
    relative_humidity_2m REAL,
    precipitation REAL,
    snowfall REAL,
    snow_depth REAL,
    wind_speed_10m REAL,
    wind_speed_100m REAL,
    wind_gusts_10m REAL,
    wind_direction_10m REAL,
    shortwave_radiation REAL,
    direct_radiation REAL,
    diffuse_radiation REAL,
    pressure_msl REAL,
    cloud_cover REAL,
    et0_fao_evapotranspiration REAL,
    soil_moisture_0_to_7cm REAL,
    fetched_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (event_id, location_id, time),
    FOREIGN KEY (event_id) REFERENCES events(event_id) ON DELETE CASCADE,
    FOREIGN KEY (location_id) REFERENCES locations(location_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS derived_indices (
    event_id TEXT NOT NULL,
    location_id TEXT NOT NULL,
    index_name TEXT NOT NULL,
    index_value REAL,
    unit TEXT DEFAULT '',
    calculation_method TEXT DEFAULT '',
    threshold TEXT DEFAULT '',
    calculated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (event_id, location_id, index_name),
    FOREIGN KEY (event_id) REFERENCES events(event_id) ON DELETE CASCADE,
    FOREIGN KEY (location_id) REFERENCES locations(location_id) ON DELETE CASCADE
);
"""
