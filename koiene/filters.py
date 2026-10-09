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
        if (c.price_guest if guest else c.price_member) <= max_price
    ]


def by_difficulty(cabins: list[Cabin], max_difficulty: int) -> list[Cabin]:
    """Keep cabins with difficulty <= max_difficulty."""
    return [c for c in cabins if c.difficulty <= max_difficulty]


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


def by_walking_time(cabins: list[Cabin], max_minutes: int, summer: bool = True) -> list[Cabin]:
    """Keep cabins within the walking time limit (in minutes) from bus stop."""
    result = []
    for c in cabins:
        t = c.walking_time_summer_min if summer else c.walking_time_winter_min
        if 0 < t <= max_minutes:
            result.append(c)
    return result


def by_total_time(cabins: list[Cabin], max_minutes: int, summer: bool = True) -> list[Cabin]:
    """Keep cabins within the total travel time limit (in minutes) by public transport."""
    result = []
    for c in cabins:
        t = c.total_time_summer_min if summer else c.total_time_winter_min
        if 0 < t <= max_minutes:
            result.append(c)
    return result
