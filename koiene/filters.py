from __future__ import annotations

from .models import Cabin


def by_beds(cabins: list[Cabin], min_beds: int) -> list[Cabin]:
    """Keep cabins that have at least min_beds available on any queried date."""
    result = []
    for cabin in cabins:
        for d in cabin.dates:
            if d.available_beds is not None and d.available_beds >= min_beds:
                result.append(cabin)
                break
    return result


def by_beds_all(cabins: list[Cabin], min_beds: int) -> list[Cabin]:
    """Keep cabins that have at least min_beds available on every queried date."""
    result = []
    for cabin in cabins:
        if not cabin.dates:
            continue
        if all(
            d.available_beds is not None and d.available_beds >= min_beds
            for d in cabin.dates
        ):
            result.append(cabin)
    return result


def by_price(cabins: list[Cabin], max_price: int, guest: bool = False) -> list[Cabin]:
    """Keep cabins within the price limit."""
    return [
        c
        for c in cabins
        if 0 < (c.price_guest if guest else c.price_member) <= max_price
    ]


def by_difficulty(cabins: list[Cabin], max_difficulty: int) -> list[Cabin]:
    """Keep cabins with difficulty <= max_difficulty."""
    return [c for c in cabins if 0 < c.difficulty <= max_difficulty]


def any_available(cabins: list[Cabin], date: str | None = None) -> list[Cabin]:
    """Keep cabins that have at least 1 bed available on the given date (or any date)."""
    result = []
    for cabin in cabins:
        if date:
            beds = cabin.available_on(date)
            if beds is not None and beds > 0:
                result.append(cabin)
        else:
            if any(
                d.available_beds is not None and d.available_beds > 0
                for d in cabin.dates
            ):
                result.append(cabin)
    return result


def by_walking_time(cabins: list[Cabin], max_minutes: int, summer: bool = True, strict: bool = False) -> list[Cabin]:
    """Keep cabins within the walking time limit (in minutes) from bus stop."""
    result = []
    for c in cabins:
        t = c.walking_time_summer_min if summer else c.walking_time_winter_min
        if 0 < t and (t < max_minutes if strict else t <= max_minutes):
            result.append(c)
    return result


def by_total_time(cabins: list[Cabin], max_minutes: int, summer: bool = True, strict: bool = False) -> list[Cabin]:
    """Keep cabins within the total travel time limit (in minutes) by public transport."""
    result = []
    for c in cabins:
        t = c.total_time_summer_min if summer else c.total_time_winter_min
        if 0 < t and (t < max_minutes if strict else t <= max_minutes):
            result.append(c)
    return result


def by_public_transport_time(cabins: list[Cabin], max_minutes: int, strict: bool = False) -> list[Cabin]:
    """Vehicle/boat travel only, excluding the walk. Source has no seasonal split."""
    return [c for c in cabins if 0 < c.public_transport_min and
            (c.public_transport_min < max_minutes if strict else c.public_transport_min <= max_minutes)]


def by_capacity(cabins: list[Cabin], min_capacity: int) -> list[Cabin]:
    return [c for c in cabins if c.capacity >= min_capacity]


def by_altitude(cabins: list[Cabin], minimum: int = 0, maximum: int | None = None) -> list[Cabin]:
    return [c for c in cabins if c.altitude > 0 and c.altitude >= minimum
            and (maximum is None or c.altitude <= maximum)]


def by_terrain(cabins: list[Cabin], terrain: str) -> list[Cabin]:
    """F = forest, T = timberline, M = mountain; mixed terrain can match either."""
    return [c for c in cabins if terrain.upper() in c.terrain.upper().split("/")]


def by_amenity(cabins: list[Cabin], amenity: str) -> list[Cabin]:
    return [c for c in cabins if amenity.casefold() in c.specialities.casefold()]


def available_stays(cabin: Cabin, nights: int = 1, min_beds: int = 1,
                    weekend: bool = False, whole_cabin: bool = False,
                    include_unreleased: bool = False) -> list[dict]:
    """Contiguous overnight dates; weekend starts Friday. Checkout is the next day.

    include_unreleased uses listed inventory, never implies ordinary booking is open.
    """
    from datetime import date, timedelta
    if nights < 1 or min_beds < 1:
        raise ValueError("Nights and minimum beds must be positive")
    needed = max(min_beds, cabin.capacity) if whole_cabin else min_beds
    if whole_cabin and cabin.capacity <= 0:
        return []
    days = {date.fromisoformat(d.date): d for d in cabin.dates}
    result = []
    for start in sorted(days):
        if weekend and start.weekday() != 4:
            continue
        stay = [days.get(start + timedelta(days=i)) for i in range(nights)]
        values = [((d.listed_beds if include_unreleased else d.available_beds)
                   if d and d.status in {"available", "not_yet_open"} else None) for d in stay]
        if all(v is not None and v >= needed for v in values):
            result.append({"check_in": start.isoformat(),
                           "check_out": (start + timedelta(days=nights)).isoformat(),
                           "min_beds": min(values),
                           "booking_open": all(d.booking_open is True for d in stay)})
    return result


def by_stay(cabins: list[Cabin], **kwargs) -> list[Cabin]:
    return [c for c in cabins if available_stays(c, **kwargs)]
