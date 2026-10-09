#!/usr/bin/env python3
"""Query NTNUI cabins. All time limits are minutes; winter approaches may require skis."""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import date, datetime, timezone
import json
import sys

from koiene import (KoieneClient, by_beds, by_beds_all, by_difficulty, by_price,
                    any_available, by_walking_time, by_total_time, by_public_transport_time,
                    by_capacity, by_altitude, by_terrain, by_amenity, available_stays)


def positive(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be positive")
    return number


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    dates = parser.add_mutually_exclusive_group()
    dates.add_argument("--date", help="One overnight date, default today")
    dates.add_argument("--from", dest="date_from", help="First overnight date (YYYY-MM-DD)")
    parser.add_argument("--to", help="Last overnight date, inclusive (YYYY-MM-DD)")
    parser.add_argument("--min-beds", type=positive)
    parser.add_argument("--require-all", action="store_true", help="Require beds on every queried date")
    parser.add_argument("--max-price", type=positive)
    parser.add_argument("--max-guest-price", type=positive)
    parser.add_argument("--max-difficulty", type=int, choices=range(1, 6))
    parser.add_argument("--available-only", action="store_true", help="At least one bed bookable now")
    parser.add_argument("--season", choices=["summer", "winter"], default="summer")
    parser.add_argument("--max-walking-time", type=positive, metavar="MINUTES", help="Approach from public transport")
    parser.add_argument("--max-total-time", type=positive, metavar="MINUTES", help="Public transport plus approach")
    parser.add_argument("--max-public-transport-time", type=positive, metavar="MINUTES", help="Vehicle/boat time only; published estimate has no seasonal split")
    parser.add_argument("--strict-time-limits", action="store_true", help="Use < rather than <= for all time limits")
    parser.add_argument("--exclude-school-bus", action="store_true", help="Exclude matrix routes flagged as school-days only")
    parser.add_argument("--min-capacity", type=positive)
    parser.add_argument("--min-altitude", type=positive, metavar="METRES")
    parser.add_argument("--max-altitude", type=positive, metavar="METRES")
    parser.add_argument("--terrain", choices=["F", "T", "M"], help="Forest, timberline, mountain")
    parser.add_argument("--amenity", action="append", default=[], help="Require text in specialities; repeatable")
    parser.add_argument("--name", action="append", default=[], help="Keep names containing any supplied text")
    parser.add_argument("--exclude-name", action="append", default=[], help="Exclude names containing text; repeatable")
    parser.add_argument("--nights", type=positive, help="Minimum consecutive nights; output matching stays")
    parser.add_argument("--weekend", action="store_true", help="Friday check-in; defaults to two nights")
    parser.add_argument("--whole-cabin", action="store_true", help="Require all beds for the stay")
    parser.add_argument("--include-unreleased", action="store_true", help="For stay search only: include listed beds not yet released; NOT bookable now")
    parser.add_argument("--detail", action="store_true")
    args = parser.parse_args()
    if bool(args.date_from) != bool(args.to):
        parser.error("--from and --to must be supplied together")
    start = args.date_from or args.date or date.today().isoformat()
    end = args.to or start
    try:
        if date.fromisoformat(end) < date.fromisoformat(start):
            parser.error("--to must be on or after --from")
    except ValueError:
        parser.error("dates must use YYYY-MM-DD")
    if args.min_altitude and args.max_altitude and args.min_altitude > args.max_altitude:
        parser.error("minimum altitude exceeds maximum")
    search_stays = bool(args.nights or args.weekend or args.whole_cabin)
    if args.include_unreleased and not search_stays:
        parser.error("--include-unreleased requires --nights, --weekend or --whole-cabin")
    if args.require_all and not args.min_beds:
        parser.error("--require-all requires --min-beds")
    if args.include_unreleased and (args.require_all or args.available_only):
        parser.error("--include-unreleased cannot be combined with bookable-only filters")

    client = KoieneClient()
    cabins = client.fetch_range(start, end)
    if args.max_difficulty:
        cabins = by_difficulty(cabins, args.max_difficulty)
    summer = args.season == "summer"
    for limit, fn in [(args.max_walking_time, by_walking_time), (args.max_total_time, by_total_time)]:
        if limit:
            cabins = fn(cabins, limit, summer=summer, strict=args.strict_time_limits)
    if args.max_public_transport_time:
        cabins = by_public_transport_time(cabins, args.max_public_transport_time, strict=args.strict_time_limits)
    if args.exclude_school_bus:
        cabins = [c for c in cabins if not c.shortest_route_school_days_only]
    if args.min_capacity:
        cabins = by_capacity(cabins, args.min_capacity)
    if args.name:
        cabins = [c for c in cabins if any(n.casefold() in c.name.casefold() for n in args.name)]
    cabins = [c for c in cabins if not any(n.casefold() in c.name.casefold() for n in args.exclude_name)]
    if args.terrain:
        cabins = by_terrain(cabins, args.terrain)
    for amenity in args.amenity:
        cabins = by_amenity(cabins, amenity)
    if args.max_price:
        cabins = by_price(cabins, args.max_price)
    if args.max_guest_price:
        cabins = by_price(cabins, args.max_guest_price, guest=True)
    if args.available_only:
        cabins = any_available(cabins)
    if args.min_beds and (not search_stays or args.require_all):
        cabins = (by_beds_all if args.require_all else by_beds)(cabins, args.min_beds)
    if args.detail or args.min_altitude or args.max_altitude:
        for cabin in cabins:
            client.fetch_detail(cabin)
    if args.min_altitude or args.max_altitude:
        cabins = by_altitude(cabins, args.min_altitude or 0, args.max_altitude)
    records = []
    for cabin in cabins:
        record = asdict(cabin)
        # Preserve the existing CLI's public-transport type field and GPS object.
        record["public_transport"]["type"] = cabin.pt_type
        if cabin.gps_latitude:
            record["gps"] = {"latitude": cabin.gps_latitude, "longitude": cabin.gps_longitude}
        if search_stays:
            stays = available_stays(cabin, nights=args.nights or (2 if args.weekend else 1),
                                    min_beds=args.min_beds or 1, weekend=args.weekend,
                                    whole_cabin=args.whole_cabin, include_unreleased=args.include_unreleased)
            if not stays:
                continue
            record["matching_stays"] = stays
        records.append(record)
    output = {"fetched_at": datetime.now(timezone.utc).isoformat(),
              "date": None if args.date_from else start, "date_from": start, "date_to": end,
              "season": args.season, "strict_time_limits": args.strict_time_limits,
              "total_cabins": len(records), "warnings": client.warnings,
              "availability_note": "Listed beds on unreleased dates are not bookable now. Dates are overnight dates; checkout follows the last night. Check cabin notices and transport timetables.",
              "cabins": records}
    json.dump(output, sys.stdout, indent=2, ensure_ascii=False)
    print()


if __name__ == "__main__":
    main()
