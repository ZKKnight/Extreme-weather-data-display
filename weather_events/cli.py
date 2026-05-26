from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

from .analysis import calculate_indices
from .db import WeatherDatabase
from .models import EVENT_TYPES, Event, Location
from .open_meteo import OpenMeteoClient, date_chunks, expand_date_window, hourly_json_to_rows


DEFAULT_DB = "data/extreme_weather.sqlite"


def _db(args: argparse.Namespace) -> WeatherDatabase:
    database = WeatherDatabase(args.db)
    database.init()
    return database


def cmd_init(args: argparse.Namespace) -> None:
    _db(args)
    print(f"Initialized database: {args.db}")


def cmd_add_event(args: argparse.Namespace) -> None:
    database = _db(args)
    database.add_event(
        Event(
            event_id=args.event_id,
            event_type=args.event_type,
            name=args.name,
            start_date=args.start_date,
            end_date=args.end_date,
            region=args.region,
            source_name=args.source_name or "",
            source_url=args.source_url or "",
            notes=args.notes or "",
        )
    )
    print(f"Saved event: {args.event_id}")


def cmd_delete_event(args: argparse.Namespace) -> None:
    database = _db(args)
    deleted = database.delete_event(args.event_id)
    print(f"Deleted events: {deleted}")


def cmd_add_location(args: argparse.Namespace) -> None:
    database = _db(args)
    database.add_location(
        Location(
            location_id=args.location_id,
            event_id=args.event_id,
            name=args.name,
            province=args.province or "",
            latitude=args.latitude,
            longitude=args.longitude,
            location_type=args.location_type,
            altitude_m=args.altitude_m,
        )
    )
    print(f"Saved location: {args.location_id}")


def cmd_list_events(args: argparse.Namespace) -> None:
    database = _db(args)
    for row in database.list_events():
        print(
            f"{row['event_id']}\t{row['event_type']}\t{row['start_date']}..{row['end_date']}\t"
            f"{row['region']}\t{row['name']}"
        )


def cmd_fetch(args: argparse.Namespace) -> None:
    database = _db(args)
    event = database.get_event(args.event_id)
    if event is None:
        raise SystemExit(f"Event not found: {args.event_id}")

    locations = database.list_locations(args.event_id)
    if not locations:
        raise SystemExit(f"No locations registered for event: {args.event_id}")

    start_date, end_date = expand_date_window(
        event["start_date"],
        event["end_date"],
        days_before=args.days_before,
        days_after=args.days_after,
    )
    client = OpenMeteoClient(timeout_s=args.timeout, max_retries=args.retries)

    total = 0
    failures = []
    for location in locations:
        location_total = 0
        for chunk_start, chunk_end in date_chunks(start_date, end_date, args.chunk_days):
            try:
                data = client.fetch_hourly(
                    latitude=location["latitude"],
                    longitude=location["longitude"],
                    start_date=chunk_start,
                    end_date=chunk_end,
                )
                rows = hourly_json_to_rows(data, event["event_id"], location["location_id"])
                location_total += database.upsert_weather_rows(rows)
            except Exception as exc:
                failure = f"{location['location_id']} ({location['name']}) {chunk_start}..{chunk_end}: {exc}"
                failures.append(failure)
                print(f"Failed {failure}")
        total += location_total
        print(f"Fetched {location_total} rows for {location['location_id']} ({location['name']})")
    print(f"Saved weather rows: {total}")
    if failures:
        raise SystemExit("Some locations failed:\n" + "\n".join(failures))


def _row_to_dict(row: Any) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}


def cmd_analyze(args: argparse.Namespace) -> None:
    database = _db(args)
    event = database.get_event(args.event_id)
    if event is None:
        raise SystemExit(f"Event not found: {args.event_id}")

    locations = database.list_locations(args.event_id)
    for location in locations:
        rows = [_row_to_dict(row) for row in database.get_weather_rows(args.event_id, location["location_id"])]
        indices = calculate_indices(event["event_type"], rows)
        database.upsert_indices(args.event_id, location["location_id"], indices)
        print(f"Calculated {len(indices)} indices for {location['location_id']} ({location['name']})")


def cmd_export(args: argparse.Namespace) -> None:
    database = _db(args)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    with database.connect() as conn, out.open("w", newline="", encoding="utf-8-sig") as fh:
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
        if not rows:
            print("No derived indices to export.")
            return
        writer = csv.DictWriter(fh, fieldnames=rows[0].keys())
        writer.writeheader()
        for row in rows:
            writer.writerow(dict(row))
    print(f"Exported: {out}")


def cmd_import_events(args: argparse.Namespace) -> None:
    database = _db(args)
    path = Path(args.path)
    count = 0
    if path.suffix.lower() == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        events = payload.get("events", payload)
    else:
        with path.open("r", newline="", encoding="utf-8-sig") as fh:
            events = list(csv.DictReader(fh))

    for item in events:
        database.add_event(
            Event(
                event_id=item["event_id"],
                event_type=item["event_type"],
                name=item["name"],
                start_date=item["start_date"],
                end_date=item["end_date"],
                region=item["region"],
                source_name=item.get("source_name", ""),
                source_url=item.get("source_url", ""),
                notes=item.get("notes", ""),
            )
        )
        count += 1
    print(f"Imported events: {count}")


def cmd_import_locations(args: argparse.Namespace) -> None:
    database = _db(args)
    path = Path(args.path)
    count = 0
    with path.open("r", newline="", encoding="utf-8-sig") as fh:
        for item in csv.DictReader(fh):
            altitude = item.get("altitude_m") or None
            database.add_location(
                Location(
                    location_id=item["location_id"],
                    event_id=item["event_id"],
                    name=item["name"],
                    province=item.get("province", ""),
                    latitude=float(item["latitude"]),
                    longitude=float(item["longitude"]),
                    location_type=item.get("location_type") or "representative_point",
                    altitude_m=float(altitude) if altitude is not None else None,
                )
            )
            count += 1
    print(f"Imported locations: {count}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Extreme weather event database")
    parser.add_argument("--db", default=DEFAULT_DB, help=f"SQLite database path, default: {DEFAULT_DB}")
    sub = parser.add_subparsers(required=True)

    init = sub.add_parser("init", help="Initialize database")
    init.set_defaults(func=cmd_init)

    add_event = sub.add_parser("add-event", help="Add or update an extreme weather event")
    add_event.add_argument("--event-id", required=True)
    add_event.add_argument("--event-type", required=True, choices=EVENT_TYPES)
    add_event.add_argument("--name", required=True)
    add_event.add_argument("--start-date", required=True)
    add_event.add_argument("--end-date", required=True)
    add_event.add_argument("--region", required=True)
    add_event.add_argument("--source-name")
    add_event.add_argument("--source-url")
    add_event.add_argument("--notes")
    add_event.set_defaults(func=cmd_add_event)

    delete_event = sub.add_parser("delete-event", help="Delete an event and cascading data")
    delete_event.add_argument("--event-id", required=True)
    delete_event.set_defaults(func=cmd_delete_event)

    add_location = sub.add_parser("add-location", help="Add or update an event location")
    add_location.add_argument("--event-id", required=True)
    add_location.add_argument("--location-id", required=True)
    add_location.add_argument("--name", required=True)
    add_location.add_argument("--latitude", type=float, required=True)
    add_location.add_argument("--longitude", type=float, required=True)
    add_location.add_argument("--province")
    add_location.add_argument("--location-type", default="representative_point")
    add_location.add_argument("--altitude-m", type=float)
    add_location.set_defaults(func=cmd_add_location)

    list_events = sub.add_parser("list-events", help="List events")
    list_events.set_defaults(func=cmd_list_events)

    fetch = sub.add_parser("fetch", help="Fetch Open-Meteo hourly weather data for an event")
    fetch.add_argument("--event-id", required=True)
    fetch.add_argument("--days-before", type=int, default=1)
    fetch.add_argument("--days-after", type=int, default=1)
    fetch.add_argument("--timeout", type=int, default=60)
    fetch.add_argument("--retries", type=int, default=4)
    fetch.add_argument("--chunk-days", type=int, default=14)
    fetch.set_defaults(func=cmd_fetch)

    analyze = sub.add_parser("analyze", help="Calculate derived indices for an event")
    analyze.add_argument("--event-id", required=True)
    analyze.set_defaults(func=cmd_analyze)

    export = sub.add_parser("export-indices", help="Export derived indices to CSV")
    export.add_argument("--out", required=True)
    export.set_defaults(func=cmd_export)

    import_events = sub.add_parser("import-events", help="Import events from CSV or JSON")
    import_events.add_argument("path")
    import_events.set_defaults(func=cmd_import_events)

    import_locations = sub.add_parser("import-locations", help="Import locations from CSV")
    import_locations.add_argument("path")
    import_locations.set_defaults(func=cmd_import_locations)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
