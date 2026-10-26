"""Pure parsers for the Kirppari-Kalle web UI (no Home Assistant imports).

Ported from kirpparikalle-mqtt 2.0.0 (kk_mqtt.py), where they were verified
against the real service.
"""

from __future__ import annotations

from datetime import date, datetime, time as dt_time, timedelta
from html.parser import HTMLParser
import re
from zoneinfo import ZoneInfo

# The service is Finnish; its dates and opening hours are local time.
TZ = ZoneInfo("Europe/Helsinki")

METADATA_REFRESH_HOURS = (8, 20)
WEEKDAYS = {
    "maanantai": 0,
    "tiistai": 1,
    "keskiviikko": 2,
    "torstai": 3,
    "perjantai": 4,
    "lauantai": 5,
    "sunnuntai": 6,
    "ma": 0,
    "ti": 1,
    "ke": 2,
    "to": 3,
    "pe": 4,
    "la": 5,
    "su": 6,
}
# Longest names first so that "maanantai" is not matched as "ma".
WEEKDAY_PATTERN = "|".join(sorted(WEEKDAYS, key=len, reverse=True))
PRICE_RE = re.compile(r"(\d+(?:[\s\xa0]\d{3})*[,.]\d{2})\s*€")
SALE_DATE_RE = re.compile(r"(\d{2}\.\d{2}\.\d{4})")


class PageDoc(HTMLParser):
    """
    Minimal HTML reader: inner_text-like text (scripts/styles skipped,
    block elements on their own lines), tables as rows of cell texts,
    <input> values by id and <h1> texts.
    """

    BLOCK = {
        "tr",
        "div",
        "p",
        "br",
        "li",
        "table",
        "section",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
    }

    def __init__(self, html: str):
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self._skip = 0
        self._cell: list[str] | None = None
        self._row: list[str] | None = None
        self._h1: list[str] | None = None
        self.tables: list[list[list[str]]] = []
        self.inputs: dict[str, str] = {}
        self.h1: list[str] = []
        self.feed(html)
        self.close()
        self.text = "".join(self._parts)

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip += 1
            return
        if tag == "input":
            a = dict(attrs)
            if a.get("id"):
                self.inputs[a["id"]] = a.get("value") or ""
        if tag == "table":
            self.tables.append([])
        elif tag == "tr":
            self._row = []
        elif tag in ("td", "th"):
            self._cell = []
            self._parts.append("\t")
        if tag == "h1":
            self._h1 = []
        if tag in self.BLOCK:
            self._parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self._skip = max(0, self._skip - 1)
            return
        if tag in ("td", "th") and self._cell is not None:
            if self._row is not None:
                self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if self.tables:
                self.tables[-1].append(self._row)
            self._row = None
        if tag == "h1" and self._h1 is not None:
            self.h1.append(" ".join("".join(self._h1).split()))
            self._h1 = None
        if tag in self.BLOCK:
            self._parts.append("\n")

    def handle_data(self, data):
        if self._skip:
            return
        self._parts.append(data)
        if self._cell is not None:
            self._cell.append(data)
        if self._h1 is not None:
            self._h1.append(data)


def is_login_page(final_url: str, text: str) -> bool:
    lower = text.lower()

    return (
        "guest.php" in final_url
        or "page=login" in final_url.lower()
        or ("kirjaudu sisään" in lower and "kirjaudu ulos" not in lower)
    )


def parse_reservations(text: str) -> list[tuple[date, date]]:
    reservations: list[tuple[date, date]] = []

    pattern = re.compile(
        r"(\d{1,2}\.\d{1,2}\.\d{4})"
        r".{0,20}?"
        r"[-–]"
        r".{0,20}?"
        r"(\d{1,2}\.\d{1,2}\.\d{4})"
    )

    for match in pattern.finditer(text):
        start = datetime.strptime(match.group(1), "%d.%m.%Y").date()
        end = datetime.strptime(match.group(2), "%d.%m.%Y").date()
        reservations.append((start, end))

    # Kirppari-Kalle may render the same reservation multiple times.
    return list(dict.fromkeys(reservations))


def parse_clock(value: str) -> dt_time:
    value = value.strip().replace(".", ":")
    if ":" in value:
        return datetime.strptime(value, "%H:%M").time()
    return dt_time(int(value), 0)


def weekday_range(start: int, end: int) -> list[int]:
    days: list[int] = []
    current = start

    while True:
        days.append(current)
        if current == end:
            break
        current = (current + 1) % 7

    return days


def parse_opening_hours(text: str) -> dict[int, tuple[dt_time, dt_time] | None]:
    result: dict[int, tuple[dt_time, dt_time] | None] = {i: None for i in range(7)}

    for raw_line in text.splitlines():
        line = raw_line.strip().lower()

        if ":" not in line:
            continue

        match = re.match(
            rf"^({WEEKDAY_PATTERN})\b"
            rf"(?:\s*[-–]\s*({WEEKDAY_PATTERN})\b)?"
            r"\s*:\s*(.+)$",
            line,
        )

        if not match:
            continue

        start_day = WEEKDAYS[match.group(1)]
        end_day = WEEKDAYS[match.group(2)] if match.group(2) else start_day
        value = match.group(3).strip()
        days = weekday_range(start_day, end_day)

        if "suljettu" in value:
            for day in days:
                result[day] = None
            continue

        time_match = re.search(
            r"(\d{1,2}(?:[:.]\d{2})?)"
            r"\s*[-–]\s*"
            r"(\d{1,2}(?:[:.]\d{2})?)",
            value,
        )

        if not time_match:
            continue

        opening = parse_clock(time_match.group(1))
        closing = parse_clock(time_match.group(2))

        for day in days:
            result[day] = (opening, closing)

    return result


def find_active_reservation(
    reservations: list[tuple[date, date]],
    today: date,
) -> tuple[date, date] | None:
    for start, end in reservations:
        if start <= today <= end:
            return start, end
    return None


def reservation_window(
    reservation: tuple[date, date] | None,
    opening_hours: dict[int, tuple[dt_time, dt_time] | None],
) -> tuple[datetime | None, datetime | None]:
    """
    Convert reservation dates into the actual first opening time
    and last closing time inside the reservation.
    """
    if reservation is None:
        return None, None

    start_date, end_date = reservation

    current = start_date
    start_dt = None

    while current <= end_date:
        hours = opening_hours.get(current.weekday())
        if hours is not None:
            opening, _ = hours
            start_dt = datetime.combine(current, opening, tzinfo=TZ)
            break
        current += timedelta(days=1)

    current = end_date
    end_dt = None

    while current >= start_date:
        hours = opening_hours.get(current.weekday())
        if hours is not None:
            _, closing = hours
            end_dt = datetime.combine(current, closing, tzinfo=TZ)
            break
        current -= timedelta(days=1)

    return start_dt, end_dt


def relevant_reservation(
    reservations: list[tuple[date, date]],
    opening_hours: dict[int, tuple[dt_time, dt_time] | None],
    now: datetime,
) -> tuple[date, date] | None:
    """
    Return the current reservation while its real sales window has not ended.
    Otherwise return the next future reservation.
    """
    candidates = sorted(reservations, key=lambda item: item[0])

    for reservation in candidates:
        _, end_dt = reservation_window(reservation, opening_hours)
        if end_dt is not None and now < end_dt:
            return reservation

    return None


def is_open(
    opening_hours: dict[int, tuple[dt_time, dt_time] | None],
    now: datetime,
) -> bool:
    hours = opening_hours.get(now.weekday())
    if hours is None:
        return False

    opening, closing = hours
    current = now.time().replace(second=0, microsecond=0)

    return opening <= current < closing


def next_metadata_refresh(now: datetime) -> datetime:
    """Return the next local metadata refresh time: 08:00 or 20:00."""
    for hour in METADATA_REFRESH_HOURS:
        candidate = now.replace(
            hour=hour,
            minute=0,
            second=0,
            microsecond=0,
        )
        if now < candidate:
            return candidate

    return (now + timedelta(days=1)).replace(
        hour=METADATA_REFRESH_HOURS[0],
        minute=0,
        second=0,
        microsecond=0,
    )


def parse_balance(doc: PageDoc) -> float:
    """
    The page animates the visible balance with JavaScript; the exact value
    is in a hidden field. Falls back to the visible "Saldo 12,34 €" text.
    """
    value = doc.inputs.get("client_balance_float", "").strip()

    if not value:
        match = re.search(
            r"Saldo\s+([0-9\s]+(?:[,.][0-9]{1,2})?)\s*€",
            doc.text,
            re.IGNORECASE,
        )
        if not match:
            raise RuntimeError("Saldoa ei löytynyt mysales-sivulta.")
        value = match.group(1)

    return round(
        float(value.replace("\xa0", "").replace(" ", "").replace(",", ".")),
        2,
    )


def parse_data_updated(text: str) -> datetime | None:
    """ "Tiedot päivitetty: 26.10.2026 11:40" on the sales page."""
    match = re.search(
        r"Tiedot p(?:ä|&auml;)ivitetty:\s*(\d{1,2}\.\d{1,2}\.\d{4})\s+(\d{1,2}:\d{2})",
        text,
    )
    if not match:
        return None
    return datetime.strptime(f"{match.group(1)} {match.group(2)}", "%d.%m.%Y %H:%M").replace(
        tzinfo=TZ
    )


def parse_sales(
    tables: list[list[list[str]]],
    stats: dict | None = None,
) -> list[dict]:
    """
    Sold items from the sales tables: a header row (Nro, Nimi, Hinta, ...),
    date rows with a single cell and item rows. Columns are found by header
    name, so hidden extra columns (Määrä, ALV, ...) do not matter.
    Keys stay compatible with the 1.x text parser (date|number|name|price).
    """
    sales: list[dict] = []
    seen: set[str] = set()
    stats = stats if stats is not None else {}
    stats.update(tables=0, rows=0, undated=0)

    for table in tables:
        cols: dict[str, int] | None = None
        current_date: str | None = None

        for row in table:
            lower = [cell.lower() for cell in row]

            if "nro" in lower and "nimi" in lower and "hinta" in lower:
                cols = {name: lower.index(name) for name in ("nro", "nimi", "hinta")}
                stats["tables"] += 1
                continue

            if cols is None:
                continue

            cells = [cell for cell in row if cell]
            if len(cells) == 1:
                date_match = SALE_DATE_RE.match(cells[0])
                if date_match:
                    current_date = date_match.group(1)
                continue

            if len(row) <= max(cols.values()):
                continue

            number = row[cols["nro"]]
            price = PRICE_RE.search(row[cols["hinta"]])
            if not number.isdigit() or not price:
                continue

            if not current_date:
                stats["undated"] += 1
                continue

            sale = {
                "date": current_date,
                "number": int(number),
                "name": row[cols["nimi"]].strip(),
                "price": round(
                    float(price.group(1).replace("\xa0", "").replace(" ", "").replace(",", ".")),
                    2,
                ),
            }
            key = sale_key(sale)
            if key not in seen:
                seen.add(key)
                sales.append(sale)
                stats["rows"] += 1

    return sales


def sale_key(sale: dict) -> str:
    return f"{sale['date']}|{sale['number']}|{sale['name']}|{sale['price']:.2f}"


def reservation_id(reservation: tuple[date, date]) -> str:
    return f"{reservation[0].isoformat()}/{reservation[1].isoformat()}"
