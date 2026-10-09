#!/usr/bin/env python3
"""CLI for querying NTNUI Koiene cabin availability."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date

from koiene import KoieneClient, by_beds, by_beds_all, by_difficulty, by_price, any_available, by_walking_time, by_total_time


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Query NTNUI Koiene cabin availability"
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--date",
        help="Single date to query (YYYY-MM-DD, default: today)",
    )
    group.add_argument(
        "--from",
        dest="date_from",
        help="Start date for range (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--to",
        help="End date for range (YYYY-MM-DD, inclusive)",
    )
    parser.add_argument("--min-beds", type=int, help="Minimum available beds")
    parser.add_argument("--require-all", action="store_true", help="Require min-beds on ALL dates (not just any)")
    parser.add_argument("--max-price", type=int, help="Max price (member)")
    parser.add_argument("--max-guest-price", type=int, help="Max price (guest)")
    parser.add_argument(
        "--max-difficulty", type=int, choices=range(1, 6), help="Max difficulty (1-5)"
    )
    parser.add_argument("--available-only", action="store_true", help="Only cabins with beds available")
    parser.add_argument("--max-walking-time", type=int, metavar="MINUTES", help="Max walking time from bus stop (minutes, summer)")
    parser.add_argument("--max-total-time", type=int, metavar="MINUTES", help="Max total travel time by PT (minutes, summer)")
    parser.add_argument("--detail", action="store_true", help="Fetch full detail pages for each cabin")
    args = parser.parse_args()

    if args.date_from and not args.to:
        parser.error("--from requires --to")

    target_date = args.date or date.today().isoformat()

    client = KoieneClient()

    if args.date_from:
        cabins = client.fetch_range(args.date_from, args.to)
    else:
        cabins = client.fetch_day(target_date)

    if args.min_beds:
        if args.require_all:
            cabins = by_beds_all(cabins, args.min_beds)
        else:
            cabins = by_beds(cabins, args.min_beds)
    if args.max_price:
        cabins = by_price(cabins, args.max_price, guest=False)
    if args.max_guest_price:
        cabins = by_price(cabins, args.max_guest_price, guest=True)
    if args.max_difficulty:
        cabins = by_difficulty(cabins, args.max_difficulty)
    if args.available_only:
        cabins = any_available(cabins)
    if args.max_walking_time:
        cabins = by_walking_time(cabins, args.max_walking_time)
    if args.max_total_time:
        cabins = by_total_time(cabins, args.max_total_time)

    if args.detail:
        for cabin in cabins:
            client.fetch_detail(cabin)

    output = {
        "date": target_date,
        "date_from": args.date_from,
        "date_to": args.to,
        "total_cabins": len(cabins),
        "cabins": [
            {
                "name": c.name,
                "info_url": c.info_url,
                "capacity": c.capacity,
                "table_places": c.table_places,
                "year_built": c.year_built,
                "terrain": c.terrain,
                "difficulty": c.difficulty,
                "difficulty_description": c.difficulty_description,
                "price_member": c.price_member,
                "price_guest": c.price_guest,
                "bike": c.bike,
                "summit_trip": c.summit_trip,
                "hunting_fishing": c.hunting_fishing,
                "guitar": c.guitar,
                "waffle_iron": c.waffle_iron,
                "specialities": c.specialities,
                "walking_time_summer_min": c.walking_time_summer_min,
                "walking_time_winter_min": c.walking_time_winter_min,
                "total_time_summer_min": c.total_time_summer_min,
                "total_time_winter_min": c.total_time_winter_min,
                "transport": c.transport,
                "dates": [
                    {"date": d.date, "available_beds": d.available_beds}
                    for d in c.dates
                ],
                # Detail page fields (only present if --detail)
                **({"area": c.area} if c.area else {}),
                **({"altitude": c.altitude} if c.altitude else {}),
                **({"gps": {"latitude": c.gps_latitude, "longitude": c.gps_longitude}} if c.gps_latitude else {}),
                **({"map_reference": c.map_reference} if c.map_reference else {}),
                **({"map_name": c.map_name} if c.map_name else {}),
                **({"weather_url": c.weather_url} if c.weather_url else {}),
                **({"flickr_url": c.flickr_url} if c.flickr_url else {}),
                **({"kml_url": c.kml_url} if c.kml_url else {}),
                **({"images": c.images} if c.images else {}),
                **({"cabin_description": c.cabin_description} if c.cabin_description else {}),
                **({"route_description": c.route_description} if c.route_description else {}),
                **({"parking_info": c.parking_info} if c.parking_info else {}),
                **({"private_car": {
                    "driving_min": c.private_car.driving_min,
                    "summer_walking_min": c.private_car.summer_walking_min,
                    "summer_total_min": c.private_car.summer_total_min,
                    "winter_walking_min": c.private_car.winter_walking_min,
                    "winter_total_min": c.private_car.winter_total_min,
                }} if c.private_car.driving_min else {}),
                **({"public_transport": {
                    "type": c.pt_type,
                    "driving_min": c.public_transport.driving_min,
                    "summer_walking_min": c.public_transport.summer_walking_min,
                    "summer_total_min": c.public_transport.summer_total_min,
                    "winter_walking_min": c.public_transport.winter_walking_min,
                    "winter_total_min": c.public_transport.winter_total_min,
                }} if c.pt_type else {}),
                **({"transport_options": [
                    {"number": t.number, "route_via": t.route_via, "exit": t.exit}
                    for t in c.transport_options
                ]} if c.transport_options else {}),
            }
            for c in cabins
        ],
    }

    json.dump(output, sys.stdout, indent=2, ensure_ascii=False)
    print()


if __name__ == "__main__":
    main()
