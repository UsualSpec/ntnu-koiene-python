from __future__ import annotations

import re
from datetime import datetime, timedelta
from urllib.parse import parse_qs, urlparse

import requests
from bs4 import BeautifulSoup, Tag

from .models import Cabin, DayAvailability, TransportOption, TravelTimes

OVERVIEW_URL = "https://www.koiene.no/koieneres/alle/ledigekoier.php"
MATRIX_URL = "https://koiene.org.ntnu.no/koiematrisa.php?l=1"
DETAIL_PAGE_URL = "https://koiene.org.ntnu.no/koiene/koiene.php"
DETAIL_URL = "https://www.koiene.no/koieneres/alle/ledigekoier_detaljer.php"


class KoieneClient:
    def __init__(self, session: requests.Session | None = None):
        self._session = session or requests.Session()
        self._session.headers["User-Agent"] = "hutten/0.1 (koiene-scraper)"
        self._matrix_cache: dict[str, dict] | None = None

    def fetch_day(self, date: str) -> list[Cabin]:
        """Fetch availability for all cabins on a single date."""
        return self.fetch_range(date, date)

    def fetch_range(self, start: str, end: str) -> list[Cabin]:
        """Fetch availability for all cabins across a date range (inclusive)."""
        matrix = self._fetch_matrix()
        k_to_name: dict[str, str] = {}
        for name, info in matrix.items():
            k = info.get("k", "")
            if k:
                k_to_name[k] = name

        start_dt = datetime.strptime(start, "%Y-%m-%d")
        end_dt = datetime.strptime(end, "%Y-%m-%d")

        cabins_by_name: dict[str, Cabin] = {}
        current = start_dt
        while current <= end_dt:
            window_end = min(current + timedelta(days=6), end_dt)
            self._fetch_overview_window(
                current.strftime("%Y-%m-%d"), cabins_by_name
            )
            current = window_end + timedelta(days=1)

        target_dates = []
        current = start_dt
        while current <= end_dt:
            target_dates.append(current.strftime("%Y-%m-%d"))
            current += timedelta(days=1)

        for cabin in cabins_by_name.values():
            cabin.dates = [d for d in cabin.dates if d.date in target_dates]
            info = matrix.get(cabin.name)
            if not info:
                km = re.search(r"k=([^&]+)", cabin.info_url)
                if km:
                    canonical = k_to_name.get(km.group(1), "")
                    info = matrix.get(canonical, {})
            if info:
                cabin.capacity = info.get("beds", 0)
                cabin.table_places = info.get("table_places", 0)
                cabin.year_built = info.get("year_built", 0)
                cabin.terrain = info.get("terrain", "")
                cabin.difficulty = info.get("difficulty", 0)
                cabin.bike = info.get("bike", False)
                cabin.summit_trip = info.get("summit_trip", False)
                cabin.hunting_fishing = info.get("hunting_fishing", "")
                cabin.guitar = info.get("guitar", False)
                cabin.waffle_iron = info.get("waffle_iron", False)
                cabin.specialities = info.get("specialities", "")
                cabin.walking_time_summer_min = info.get("walking_time_summer_min", 0)
                cabin.walking_time_winter_min = info.get("walking_time_winter_min", 0)
                cabin.total_time_summer_min = info.get("total_time_summer_min", 0)
                cabin.total_time_winter_min = info.get("total_time_winter_min", 0)
                cabin.transport = info.get("transport", "")

        self._enrich_prices(list(cabins_by_name.values()))
        return list(cabins_by_name.values())

    def _enrich_prices(self, cabins: list[Cabin]) -> None:
        for cabin in cabins:
            if cabin.price_member > 0:
                continue
            try:
                resp = self._session.get(
                    DETAIL_URL,
                    params={"k": cabin.name, "d": "2026-08-18", "s": 1},
                )
                resp.raise_for_status()
            except requests.RequestException:
                continue
            text = resp.text
            m = re.search(
                r"Kr\.\s*(\d+[\.,]?\d*)\s+for\s+NTNUI-medlemmer", text
            )
            if m:
                cabin.price_member = int(float(m.group(1).replace(",", ".")))
            m = re.search(r"Kr\.\s*(\d+[\.,]?\d*)\s+for\s+gjester", text)
            if m:
                cabin.price_guest = int(float(m.group(1).replace(",", ".")))

    def fetch_detail(self, cabin: Cabin) -> None:
        """Fetch and parse the full detail page for a cabin."""
        km = re.search(r"k=([^&]+)", cabin.info_url)
        if not km:
            return
        k_param = km.group(1)

        try:
            resp = self._session.get(DETAIL_PAGE_URL, params={"k": k_param, "l": 1})
            resp.raise_for_status()
        except requests.RequestException:
            return

        soup = BeautifulSoup(resp.text, "html.parser")
        self._parse_detail_sidebar(soup, cabin)
        self._parse_detail_difficulty(soup, cabin)
        self._parse_detail_images(soup, cabin)
        self._parse_detail_descriptions(soup, cabin)
        self._parse_detail_travel_tables(soup, cabin)

    def _parse_detail_sidebar(self, soup: BeautifulSoup, cabin: Cabin) -> None:
        """Parse sidebar info: area, beds, terrain, altitude, GPS, map, URLs."""
        details = soup.select_one(".koie-detaljer ul")
        if not details:
            return

        for li in details.find_all("li"):
            text = li.get_text(strip=True)

            # Area (first bold item)
            if not cabin.area:
                b = li.find("b")
                if b and not any(
                    kw in text.lower()
                    for kw in ["beds", "terrain", "altitude", "map", "weather", "picture"]
                ):
                    cabin.area = b.get_text(strip=True)
                    continue

            if "Beds:" in text:
                m = re.search(r"Beds:\s*(\d+)", text)
                if m:
                    cabin.capacity = int(m.group(1))
            elif "Terrain:" in text:
                m = re.search(r"Terrain:\s*(.+)", text)
                if m:
                    cabin.terrain = m.group(1).strip()
            elif "Altitude:" in text:
                m = re.search(r"Altitude:\s*(\d+)m", text)
                if m:
                    cabin.altitude = int(m.group(1))
            elif "Map:" in text:
                b = li.find("b")
                if b:
                    cabin.map_name = b.get_text(strip=True)
            elif "Weather" in text:
                a = li.find("a")
                if a:
                    cabin.weather_url = a.get("href", "")
            elif "pictures" in text.lower() or "album" in text.lower():
                a = li.find("a")
                if a:
                    cabin.flickr_url = a.get("href", "")

        # GPS from popover
        popover = soup.find(id="popover")
        if popover:
            data_content = popover.get("data-content", "")
            lat_m = re.search(r"Latitude:\s*([\d.]+)", data_content)
            lon_m = re.search(r"Longitude:\s*([\d.]+)", data_content)
            if lat_m:
                cabin.gps_latitude = float(lat_m.group(1))
            if lon_m:
                cabin.gps_longitude = float(lon_m.group(1))
            cabin.map_reference = popover.get_text(strip=True)

        # KML URL from script
        script = soup.find("script", string=re.compile(r"kartfil"))
        if script:
            m = re.search(r"kartfil=\"([^\"]+)\"", script.string or "")
            if m:
                kml_path = m.group(1).replace("\\/", "/")
                cabin.kml_url = f"https://koiene.org.ntnu.no/koiene/{kml_path}"

    def _parse_detail_difficulty(self, soup: BeautifulSoup, cabin: Cabin) -> None:
        """Parse difficulty level and description."""
        diff_div = soup.select_one(".vanskelighetsgrad")
        if not diff_div:
            return

        # Count logo images (non-negated = filled)
        logo_div = soup.select_one(".vanskelighetsgrad-bilde")
        if logo_div:
            imgs = logo_div.find_all("img")
            filled = sum(1 for img in imgs if "negate" not in (img.get("src", "")))
            if filled > 0:
                cabin.difficulty = filled

        # Description after ›
        text = diff_div.get_text()
        m = re.search(r"›\s*(.+)", text)
        if m:
            cabin.difficulty_description = m.group(1).strip()

    def _parse_detail_images(self, soup: BeautifulSoup, cabin: Cabin) -> None:
        """Parse image URLs from detail page."""
        cabin.images = []
        for link in soup.select(".koiebilde-stor a, .koiebilde-liten a"):
            href = link.get("href", "")
            if href and ".jpg" in href.lower():
                cabin.images.append(href)

    def _parse_detail_descriptions(self, soup: BeautifulSoup, cabin: Cabin) -> None:
        """Parse cabin description, route description, and parking info."""
        # Cabin description
        desc_div = soup.select_one(".beskrivelse")
        if desc_div:
            cabin.cabin_description = desc_div.get_text(separator="\n", strip=True)

        # Route description (between <h3>Route description</h3> and next <h3>)
        for h3 in soup.find_all("h3"):
            if "Route description" in h3.get_text():
                parts = []
                for sibling in h3.next_siblings:
                    if isinstance(sibling, Tag) and sibling.name == "h3":
                        break
                    if isinstance(sibling, Tag):
                        parts.append(sibling.get_text(separator="\n", strip=True))
                    elif isinstance(sibling, str):
                        parts.append(sibling.strip())
                cabin.route_description = "\n".join(p for p in parts if p)
                break

        # Parking info
        for h3 in soup.find_all("h3"):
            if "Parking" in h3.get_text():
                parts = []
                for sibling in h3.next_siblings:
                    if isinstance(sibling, Tag) and sibling.name == "h3":
                        break
                    if isinstance(sibling, Tag) and sibling.get("id") == "gradering":
                        break
                    if isinstance(sibling, Tag):
                        parts.append(sibling.get_text(separator="\n", strip=True))
                    elif isinstance(sibling, str):
                        parts.append(sibling.strip())
                cabin.parking_info = "\n".join(p for p in parts if p)
                break

    def _parse_detail_travel_tables(self, soup: BeautifulSoup, cabin: Cabin) -> None:
        """Parse facts, travel time, and transport tables."""
        tables = soup.find_all("table")

        for table in tables:
            text = table.get_text()
            if "FACTS" in text and "Bed" in text:
                self._parse_facts_table(table, cabin)
            elif "TRAVEL" in text and "TIME" in text:
                self._parse_travel_time_table(table, cabin)
            elif "TRANS-" in text and "PORT" in text:
                self._parse_transport_table(table, cabin)

    def _parse_facts_table(self, table: Tag, cabin: Cabin) -> None:
        """Parse facts table for cabin attributes."""
        rows = table.find_all("tr")
        for row in rows:
            cells = row.find_all("td")
            if len(cells) < 10:
                continue

            try:
                cabin.capacity = int(cells[1].get_text(strip=True))
                cabin.table_places = int(cells[2].get_text(strip=True))
                cabin.year_built = int(cells[3].get_text(strip=True))
            except (ValueError, IndexError):
                pass

            if len(cells) > 4:
                cabin.terrain = cells[4].get_text(strip=True)
            if len(cells) > 5:
                cabin.bike = cells[5].get_text(strip=True) == "x"
            if len(cells) > 6:
                cabin.summit_trip = cells[6].get_text(strip=True) in ("x", "(x)")
            if len(cells) > 7:
                cabin.hunting_fishing = cells[7].get_text(strip=True)
            if len(cells) > 8:
                cabin.guitar = cells[8].get_text(strip=True) == "x"
            if len(cells) > 9:
                cabin.waffle_iron = cells[9].get_text(strip=True) == "x"
            if len(cells) > 10:
                cabin.specialities = cells[10].get_text(strip=True)
            break  # Only first data row

    def _parse_travel_time_table(self, table: Tag, cabin: Cabin) -> None:
        """Parse travel time table for car and public transport times."""
        def parse_time(text: str) -> int:
            text = text.strip().replace("**", "")
            m = re.match(r"(\d+):(\d+)", text)
            if m:
                return int(m.group(1)) * 60 + int(m.group(2))
            return 0

        rows = table.find_all("tr")
        for row in rows:
            cells = row.find_all("td")
            if len(cells) < 12:
                continue

            # Car times
            cabin.private_car = TravelTimes(
                driving_min=parse_time(cells[1].get_text()),
                summer_walking_min=parse_time(cells[2].get_text()),
                summer_total_min=parse_time(cells[3].get_text()),
                winter_walking_min=parse_time(cells[4].get_text()),
                winter_total_min=parse_time(cells[5].get_text()),
            )

            # Public transport
            cabin.pt_type = cells[6].get_text(strip=True)
            cabin.public_transport = TravelTimes(
                driving_min=parse_time(cells[7].get_text()),
                summer_walking_min=parse_time(cells[8].get_text()),
                summer_total_min=parse_time(cells[9].get_text()),
                winter_walking_min=parse_time(cells[10].get_text()),
                winter_total_min=parse_time(cells[11].get_text()),
            )
            break  # Only first data row

    def _parse_transport_table(self, table: Tag, cabin: Cabin) -> None:
        """Parse transport options table."""
        cabin.transport_options = []
        rows = table.find_all("tr")
        for row in rows:
            cells = row.find_all("td")
            if len(cells) < 4:
                continue

            # Use separator to preserve line breaks
            numbers_raw = cells[1].get_text(separator="\n").strip()
            alternatives_raw = cells[2].get_text(separator="\n").strip()
            routes_raw = cells[3].get_text(separator="\n").strip()
            exits_raw = cells[4].get_text(separator="\n").strip() if len(cells) > 4 else ""

            numbers = [n.strip() for n in numbers_raw.split("\n") if n.strip()]
            alternatives = [a.strip() for a in alternatives_raw.split("\n") if a.strip()]
            routes = [r.strip() for r in routes_raw.split("\n") if r.strip()]
            exits = [e.strip() for e in exits_raw.split("\n") if e.strip()]

            # Pair them up - some rows may have blank lines for spacing
            max_len = max(len(alternatives), len(routes), len(exits))
            for i in range(max_len):
                cabin.transport_options.append(
                    TransportOption(
                        number=alternatives[i] if i < len(alternatives) else "",
                        route_via=routes[i] if i < len(routes) else "",
                        exit=exits[i] if i < len(exits) else "",
                    )
                )
            break  # Only first data row

    def _fetch_matrix(self) -> dict[str, dict]:
        if self._matrix_cache is not None:
            return self._matrix_cache

        resp = self._session.get(MATRIX_URL)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        result: dict[str, dict] = {}
        k_to_name: dict[str, str] = {}
        tables = soup.find_all("table", class_="stripet")

        if len(tables) >= 1:
            self._parse_size_table(tables[0], result, k_to_name)
        if len(tables) >= 2:
            self._parse_difficulty_table(tables[1], result, k_to_name)

        self._matrix_cache = result
        return result

    def _parse_size_table(
        self, table: Tag, result: dict[str, dict], k_to_name: dict[str, str]
    ) -> None:
        rows = table.find_all("tr")
        for row in rows:
            cells = row.find_all(["td", "th"])
            if len(cells) < 10:
                continue

            name_th = cells[0].find("a")
            if not name_th:
                continue
            name = name_th.get_text(strip=True)
            k_param = ""
            href = name_th.get("href", "")
            km = re.search(r"k=([^&]+)", href)
            if km:
                k_param = km.group(1)

            try:
                beds = int(cells[1].get_text(strip=True))
                table_places = int(cells[2].get_text(strip=True))
                year = int(cells[3].get_text(strip=True))
            except (ValueError, IndexError):
                continue

            terrain = cells[4].get_text(strip=True) if len(cells) > 4 else ""
            bike = cells[5].get_text(strip=True) == "x" if len(cells) > 5 else False
            summit = cells[6].get_text(strip=True) in ("x", "(x)") if len(cells) > 6 else False
            hunting = cells[7].get_text(strip=True) if len(cells) > 7 else ""
            guitar = cells[8].get_text(strip=True) == "x" if len(cells) > 8 else False
            waffle = cells[9].get_text(strip=True) == "x" if len(cells) > 9 else False
            specs = cells[10].get_text(strip=True) if len(cells) > 10 else ""

            result[name] = {
                "k": k_param,
                "beds": beds,
                "table_places": table_places,
                "year_built": year,
                "terrain": terrain,
                "bike": bike,
                "summit_trip": summit,
                "hunting_fishing": hunting,
                "guitar": guitar,
                "waffle_iron": waffle,
                "specialities": specs,
            }
            if k_param:
                k_to_name[k_param] = name

    def _parse_difficulty_table(
        self, table: Tag, result: dict[str, dict], k_to_name: dict[str, str]
    ) -> None:
        rows = table.find_all("tr")
        for row in rows:
            cells = row.find_all(["td", "th"])
            if len(cells) < 2:
                continue

            name_cell = cells[0].find("a") or cells[0].find("b")
            if not name_cell:
                continue
            name = name_cell.get_text(strip=True).rstrip("*")

            diff_text = cells[1].get_text(strip=True)
            try:
                difficulty = int(diff_text)
            except ValueError:
                continue

            def parse_time(text: str) -> int:
                text = text.strip().replace("**", "")
                m = re.match(r"(\d+):(\d+)", text)
                if m:
                    return int(m.group(1)) * 60 + int(m.group(2))
                return 0

            transport = cells[7].get_text(strip=True).replace("\n", " ") if len(cells) > 7 else ""
            pt_walking_summer = parse_time(cells[9].get_text()) if len(cells) > 9 else 0
            pt_total_summer = parse_time(cells[10].get_text()) if len(cells) > 10 else 0
            pt_walking_winter = parse_time(cells[11].get_text()) if len(cells) > 11 else 0
            pt_total_winter = parse_time(cells[12].get_text()) if len(cells) > 12 else 0

            if name in result:
                result[name]["difficulty"] = difficulty
                result[name]["walking_time_summer_min"] = pt_walking_summer
                result[name]["walking_time_winter_min"] = pt_walking_winter
                result[name]["total_time_summer_min"] = pt_total_summer
                result[name]["total_time_winter_min"] = pt_total_winter
                result[name]["transport"] = transport

    def _fetch_overview_window(
        self, start_date: str, cabins_by_name: dict[str, Cabin]
    ) -> None:
        resp = self._session.get(OVERVIEW_URL, params={"startdato": start_date})
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        table = soup.find("table", cellpadding="0")
        if not table:
            return

        rows = table.find_all("tr")
        for row in rows:
            cells = row.find_all("td")
            if len(cells) < 2:
                continue

            name_cell = cells[0]
            link = name_cell.find("a")
            if not link:
                continue
            cabin_name = link.get_text(strip=True)
            if not cabin_name:
                continue

            info_href = link.get("href", "")

            if cabin_name not in cabins_by_name:
                cabins_by_name[cabin_name] = Cabin(
                    name=cabin_name,
                    info_url=info_href,
                )
            cabin = cabins_by_name[cabin_name]

            for cell in cells[1:]:
                img = cell.find("img")
                if not img:
                    continue

                src = img.get("src", "")
                if "rutevisning.php" not in src:
                    continue

                parsed = urlparse(src)
                params = parse_qs(parsed.query)

                aap = params.get("aap", [""])[0]
                led = params.get("led", [None])[0]

                a_tag = cell.find("a")
                date_str = ""
                if a_tag and a_tag.get("href"):
                    dm = re.search(r"d=(\d{4}-\d{2}-\d{2})", a_tag["href"])
                    if dm:
                        date_str = dm.group(1)

                if not date_str:
                    continue

                available = None
                if aap == "ja" and led is not None:
                    try:
                        available = int(led)
                    except ValueError:
                        pass

                cabin.dates.append(
                    DayAvailability(date=date_str, available_beds=available)
                )
