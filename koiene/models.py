from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class DayAvailability:
    date: str
    available_beds: int | None = None  # None = closed

    def __repr__(self) -> str:
        beds = f"{self.available_beds} beds" if self.available_beds is not None else "closed"
        return f"DayAvailability({self.date}, {beds})"


@dataclass
class TransportOption:
    number: str
    route_via: str
    exit: str


@dataclass
class TravelTimes:
    """Travel times in minutes. 0 = not available."""
    driving_min: int = 0
    summer_walking_min: int = 0
    summer_total_min: int = 0
    winter_walking_min: int = 0
    winter_total_min: int = 0


@dataclass
class Cabin:
    name: str
    info_url: str

    # From matrix (static info)
    capacity: int = 0
    table_places: int = 0
    year_built: int = 0
    terrain: str = ""
    difficulty: int = 0
    price_member: int = 0
    price_guest: int = 0
    bike: bool = False
    summit_trip: bool = False
    hunting_fishing: str = ""
    guitar: bool = False
    waffle_iron: bool = False
    specialities: str = ""
    walking_time_summer_min: int = 0
    walking_time_winter_min: int = 0
    total_time_summer_min: int = 0
    total_time_winter_min: int = 0
    transport: str = ""
    dates: list[DayAvailability] = field(default_factory=list)

    # From detail page
    area: str = ""
    difficulty_description: str = ""
    altitude: int = 0
    gps_latitude: float = 0.0
    gps_longitude: float = 0.0
    map_reference: str = ""
    map_name: str = ""
    weather_url: str = ""
    flickr_url: str = ""
    kml_url: str = ""
    images: list[str] = field(default_factory=list)
    cabin_description: str = ""
    route_description: str = ""
    parking_info: str = ""
    transport_options: list[TransportOption] = field(default_factory=list)
    private_car: TravelTimes = field(default_factory=TravelTimes)
    public_transport: TravelTimes = field(default_factory=TravelTimes)
    pt_type: str = ""

    def available_on(self, date: str) -> int | None:
        for d in self.dates:
            if d.date == date:
                return d.available_beds
        return None

    def __repr__(self) -> str:
        return f"Cabin({self.name}, capacity={self.capacity}, dates={len(self.dates)})"
