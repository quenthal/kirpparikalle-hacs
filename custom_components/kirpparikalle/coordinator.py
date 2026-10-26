"""Data update coordinator for Kirppari-Kalle."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time as dt_time, timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import AuthExpired, CannotConnect, InvalidAuth, KirppariKalleApi, LoginFailed
from .const import (
    CONF_COMPANY_ID,
    CONF_SHOP_NAME,
    DOMAIN,
    EVENT_SALES_UPDATE,
    EVENT_TYPE_SALES_UPDATE,
    FINAL_READ_DELAY,
    KEEPALIVE_INTERVAL,
    SALES_INTERVAL,
    STORAGE_VERSION,
)
from .parsers import (
    TZ,
    find_active_reservation,
    is_open,
    next_metadata_refresh,
    parse_balance,
    parse_data_updated,
    parse_opening_hours,
    parse_reservations,
    parse_sales,
    relevant_reservation,
    reservation_id,
    reservation_window,
    sale_key,
)

_LOGGER = logging.getLogger(__name__)

OpeningHours = dict[int, tuple[dt_time, dt_time] | None]


@dataclass
class KirppariKalleData:
    """What the entities show."""

    shop: str
    reservation_start: datetime | None = None
    reservation_end: datetime | None = None
    reservation_active: bool = False
    balance: float | None = None
    sold_count: int | None = None
    checked_at: datetime | None = None
    data_updated_at: datetime | None = None
    last_event: dict[str, Any] | None = None
    event_seq: int = 0
    sales: list[dict] = field(default_factory=list)


def final_read_due(opening_hours: OpeningHours, now: datetime, done_for: date | None) -> bool:
    """True once per open day, FINAL_READ_DELAY after closing time."""
    hours = opening_hours.get(now.weekday())
    if hours is None or done_for == now.date():
        return False
    closing = datetime.combine(now.date(), hours[1], tzinfo=TZ)
    return now >= closing + FINAL_READ_DELAY


def next_update_delay(
    reservations: list[tuple[date, date]],
    opening_hours: OpeningHours,
    now: datetime,
    final_read_done_for: date | None,
    next_meta: datetime | None,
) -> timedelta:
    """
    SALES_INTERVAL while selling; otherwise wake up for the next interesting
    moment (opening, the final read, metadata refresh), at most
    KEEPALIVE_INTERVAL later so the session stays alive.
    """
    if find_active_reservation(reservations, now.date()) and is_open(opening_hours, now):
        return SALES_INTERVAL

    candidates = [now + KEEPALIVE_INTERVAL]
    if next_meta is not None:
        candidates.append(next_meta)

    if find_active_reservation(reservations, now.date()):
        hours = opening_hours.get(now.weekday())
        if hours is not None:
            opening = datetime.combine(now.date(), hours[0], tzinfo=TZ)
            closing = datetime.combine(now.date(), hours[1], tzinfo=TZ)
            if now < opening:
                candidates.append(opening)
            if final_read_done_for != now.date() and now < closing + FINAL_READ_DELAY:
                candidates.append(closing + FINAL_READ_DELAY)

    wake = min(candidates)
    return max(timedelta(minutes=1), wake - now)


class KirppariKalleCoordinator(DataUpdateCoordinator[KirppariKalleData]):
    """Reads Kirppari-Kalle on a schedule and detects new sales."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, api: KirppariKalleApi) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=SALES_INTERVAL,
        )
        self.api = api
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}"
        )
        self._baseline: dict[str, Any] | None = None
        self._shop: str = entry.data.get(CONF_SHOP_NAME) or entry.title
        self._reservations: list[tuple[date, date]] = []
        self._hours: OpeningHours = {}
        self._next_meta: datetime | None = None
        self._final_read_done_for: date | None = None
        self._last_event: dict[str, Any] | None = None
        self._event_seq = 0

    async def _async_setup(self) -> None:
        self._baseline = await self._store.async_load()

    async def _async_update_data(self) -> KirppariKalleData:
        try:
            return await self._read()
        except AuthExpired:
            _LOGGER.debug("Session expired, logging in")
        except CannotConnect as err:
            raise UpdateFailed(f"Kirppari-Kalle is not reachable ({err})") from None

        try:
            await self.api.login(
                self.config_entry.data[CONF_USERNAME],
                self.config_entry.data[CONF_PASSWORD],
                self.config_entry.data[CONF_COMPANY_ID],
            )
        except InvalidAuth:
            raise ConfigEntryAuthFailed("Kirppari-Kalle rejected the credentials") from None
        except (CannotConnect, LoginFailed, AuthExpired) as err:
            raise UpdateFailed(f"Login failed ({type(err).__name__}: {err})") from None

        try:
            return await self._read()
        except (AuthExpired, CannotConnect) as err:
            raise UpdateFailed(f"Reading failed after login ({type(err).__name__})") from None

    async def _read(self) -> KirppariKalleData:
        now = datetime.now(TZ)
        loaded_page = False

        if self._next_meta is None or now >= self._next_meta:
            reservations_doc = await self.api.page("myreservations")
            company_doc = await self.api.page("companydetails")
            self._reservations = parse_reservations(reservations_doc.text)
            self._hours = parse_opening_hours(company_doc.text)
            self._shop = next((h for h in company_doc.h1 if h), self._shop)
            self._next_meta = next_metadata_refresh(now)
            loaded_page = True
            if not any(self._hours.values()):
                _LOGGER.warning("No opening hours found; sales will not be read")

        active = find_active_reservation(self._reservations, now.date())
        open_now = is_open(self._hours, now)
        final_read = bool(
            active and not open_now and final_read_due(self._hours, now, self._final_read_done_for)
        )

        if active and (open_now or final_read):
            doc = await self.api.page("mysales")
            loaded_page = True
            balance = parse_balance(doc)
            stats: dict = {}
            sales = parse_sales(doc.tables, stats)
            total = round(sum(sale["price"] for sale in sales), 2)
            if sales and abs(total - balance) > 0.005:
                _LOGGER.warning(
                    "Sold items total %.2f does not match the balance %.2f (%d rows)",
                    total,
                    balance,
                    len(sales),
                )
            await self._process_sales(active, balance, sales, now, parse_data_updated(doc.text))
            if final_read:
                self._final_read_done_for = now.date()

        if not loaded_page:
            # Keepalive: the session expires if it is not used.
            await self.api.page("myreservations")

        self.update_interval = next_update_delay(
            self._reservations,
            self._hours,
            now,
            self._final_read_done_for,
            self._next_meta,
        )
        return self._build_data(now)

    def _build_data(self, now: datetime) -> KirppariKalleData:
        relevant = relevant_reservation(self._reservations, self._hours, now)
        start, end = reservation_window(relevant, self._hours)
        baseline = self._baseline or {}
        sales = baseline.get("sales") or []

        def ts(key: str) -> datetime | None:
            value = baseline.get(key)
            return datetime.fromisoformat(value) if value else None

        return KirppariKalleData(
            shop=self._shop,
            reservation_start=start,
            reservation_end=end,
            reservation_active=bool(start and end and start <= now < end),
            balance=baseline.get("balance"),
            sold_count=len(sales) if baseline else None,
            checked_at=ts("checked_at"),
            data_updated_at=ts("data_updated_at"),
            last_event=self._last_event,
            event_seq=self._event_seq,
            sales=sales,
        )

    async def _process_sales(
        self,
        reservation: tuple[date, date],
        balance: float,
        sales: list[dict],
        now: datetime,
        data_updated: datetime | None,
    ) -> None:
        previous = self._baseline
        new_baseline = {
            "reservation_id": reservation_id(reservation),
            "balance": balance,
            "sales": sales,
            "checked_at": now.isoformat(),
            "data_updated_at": data_updated.isoformat() if data_updated else None,
        }

        if previous is None or previous.get("reservation_id") != new_baseline["reservation_id"]:
            # A new reservation: the first read is the starting point.
            await self._save_baseline(new_baseline)
            return

        old_balance = round(float(previous.get("balance") or 0), 2)
        old_sales = previous.get("sales") or []
        old_keys = {sale_key(sale) for sale in old_sales}
        new_keys = {sale_key(sale) for sale in sales}
        new_sales = [sale for sale in sales if sale_key(sale) not in old_keys]
        removed_sales = [sale for sale in old_sales if sale_key(sale) not in new_keys]

        await self._save_baseline(new_baseline)

        if balance == old_balance and not new_sales and not removed_sales:
            return

        payload = {
            "event_type": EVENT_TYPE_SALES_UPDATE,
            "shop": self._shop,
            "entry_id": self.config_entry.entry_id,
            "observed_at": now.isoformat(),
            "previous_balance": old_balance,
            "balance": balance,
            "balance_change": round(balance - old_balance, 2),
            "new_sales": new_sales,
            "removed_sales": removed_sales,
        }
        self._last_event = payload
        self._event_seq += 1
        self.hass.bus.async_fire(EVENT_SALES_UPDATE, payload)
        _LOGGER.debug(
            "Sales update: %.2f -> %.2f, new %d, removed %d",
            old_balance,
            balance,
            len(new_sales),
            len(removed_sales),
        )

    async def _save_baseline(self, baseline: dict[str, Any]) -> None:
        self._baseline = baseline
        await self._store.async_save(baseline)
