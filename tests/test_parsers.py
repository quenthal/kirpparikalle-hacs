"""Parser tests (no Home Assistant)."""

from datetime import date, datetime, time, timedelta

from custom_components.kirpparikalle.coordinator import final_read_due, next_update_delay
from custom_components.kirpparikalle.parsers import (
    TZ,
    PageDoc,
    parse_balance,
    parse_data_updated,
    parse_opening_hours,
    parse_reservations,
    parse_sales,
    sale_key,
)

from .conftest import COMPANY_HTML, RESERVATIONS_HTML, SALES_ROWS, sales_html


def test_sales_page():
    doc = PageDoc(sales_html(SALES_ROWS, "11.00"))
    assert parse_balance(doc) == 11.0
    assert parse_data_updated(doc.text) == datetime(2026, 10, 3, 11, 55, tzinfo=TZ)
    stats = {}
    sales = parse_sales(doc.tables, stats)
    assert stats == {"tables": 1, "rows": 2, "undated": 0}
    # Same keys as kirpparikalle-mqtt.
    assert sale_key(sales[0]) == "03.10.2026|55|Talvisaappaat, 30|8.00"


def test_balance_fallback_to_text():
    assert parse_balance(PageDoc("<h2>Saldo</h2><div>1 234,50 €</div>")) == 1234.5


def test_metadata_pages():
    assert parse_reservations(PageDoc(RESERVATIONS_HTML).text) == [
        (date(2026, 10, 3), date(2026, 10, 10))
    ]
    company = PageDoc(COMPANY_HTML)
    assert company.h1 == ["Esimerkkikirppis"]
    hours = parse_opening_hours(company.text)
    assert hours[0] is None
    assert hours[5] == (time(10), time(16))


def test_opening_hours_formats():
    hours = parse_opening_hours("Ti-Pe: 10.00-18.00\nLa: 10:30–16:00")
    assert hours[1] == (time(10), time(18))
    assert hours[5] == (time(10, 30), time(16))


def test_schedule():
    hours = parse_opening_hours("Lauantai - Sunnuntai: 10-16\nMaanantai - Perjantai: 10-18")
    reservations = [(date(2026, 10, 3), date(2026, 10, 10))]
    saturday = date(2026, 10, 3)

    def at(h, m):
        return datetime(2026, 10, 3, h, m, tzinfo=TZ)

    meta = at(20, 0)
    # Before opening: wake up at opening.
    assert next_update_delay(reservations, hours, at(9, 30), None, meta) == timedelta(minutes=30)
    # Open: every 5 minutes.
    assert next_update_delay(reservations, hours, at(12, 0), None, meta) == timedelta(minutes=5)
    # Closed: final read 10 min after closing, once.
    assert next_update_delay(reservations, hours, at(16, 0), None, meta) == timedelta(minutes=10)
    assert final_read_due(hours, at(16, 12), None)
    assert not final_read_due(hours, at(16, 12), saturday)
    # After the final read: keepalive.
    assert next_update_delay(reservations, hours, at(16, 15), saturday, meta) == timedelta(hours=1)
    # No reservation: keepalive or metadata refresh, whichever first.
    assert next_update_delay([], hours, at(19, 30), None, meta) == timedelta(minutes=30)
