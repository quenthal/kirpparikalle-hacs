"""The integration end to end with a fake service."""

from __future__ import annotations

from contextlib import ExitStack, contextmanager
from unittest.mock import patch

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_capture_events

from custom_components.kirpparikalle.api import InvalidAuth
from custom_components.kirpparikalle.const import (
    CONF_COMPANY_ID,
    CONF_SHOP_NAME,
    DOMAIN,
    EVENT_SALES_UPDATE,
)

from .conftest import FakeApi

# Saturday inside the reservation, shop open 10-16 (Helsinki time).
OPEN_TIME = "2026-10-03 12:00:00+03:00"


@pytest.fixture
def api() -> FakeApi:
    return FakeApi()


@pytest.fixture
async def entry(hass: HomeAssistant, api: FakeApi, freezer) -> MockConfigEntry:
    freezer.move_to(OPEN_TIME)
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Esimerkkikirppis",
        unique_id="myyja:101",
        data={
            CONF_USERNAME: "myyja",
            CONF_PASSWORD: "salasana",
            CONF_COMPANY_ID: "101",
            CONF_SHOP_NAME: "Esimerkkikirppis",
        },
    )
    entry.add_to_hass(hass)
    with _patched(api):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry


@contextmanager
def _patched(api: FakeApi):
    """Fake API and no real HTTP session."""
    with ExitStack() as stack:
        stack.enter_context(
            patch("custom_components.kirpparikalle.KirppariKalleApi", return_value=api)
        )
        stack.enter_context(patch("custom_components.kirpparikalle.async_create_clientsession"))
        yield


def _state(hass: HomeAssistant, key: str, platform: str = "sensor"):
    entity_id = er.async_get(hass).async_get_entity_id(platform, DOMAIN, f"myyja:101_{key}")
    assert entity_id, key
    return hass.states.get(entity_id)


async def test_setup_logs_in_and_reads(hass: HomeAssistant, entry, api: FakeApi) -> None:
    assert entry.state is ConfigEntryState.LOADED
    # No session at start -> login, then the pages.
    assert api.calls[:2] == ["myreservations", "login"]
    assert "mysales" in api.calls

    assert float(_state(hass, "balance").state) == 11.0
    assert _state(hass, "sold_count").state == "2"
    assert _state(hass, "reservation_active", "binary_sensor").state == "on"
    assert _state(hass, "reservation_start").state == "2026-10-03T07:00:00+00:00"
    assert _state(hass, "data_updated_at").state == "2026-10-03T08:55:00+00:00"
    assert _state(hass, "balance").attributes["unit_of_measurement"] == "EUR"


async def test_new_sale_fires_events(hass: HomeAssistant, entry, api: FakeApi, freezer) -> None:
    events = async_capture_events(hass, EVENT_SALES_UPDATE)
    coordinator = entry.runtime_data
    event_before = _state(hass, "sales_update", "event").state

    # First read was the baseline: nothing fired.
    assert events == []

    api.sales_rows.append((70, "Sadehaalari, 116", "5,00"))
    api.balance = "16.00"
    freezer.tick(300)
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert len(events) == 1
    data = events[0].data
    assert data["balance"] == 16.0
    assert data["balance_change"] == 5.0
    assert data["new_sales"] == [
        {"date": "03.10.2026", "number": 70, "name": "Sadehaalari, 116", "price": 5.0}
    ]
    assert data["removed_sales"] == []

    event_state = _state(hass, "sales_update", "event")
    assert event_state.state != event_before
    assert event_state.attributes["balance_change"] == 5.0
    assert float(_state(hass, "balance").state) == 16.0

    # No change -> no event.
    freezer.tick(300)
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert len(events) == 1


async def test_restart_does_not_repeat_sales(
    hass: HomeAssistant, entry, api: FakeApi, freezer
) -> None:
    events = async_capture_events(hass, EVENT_SALES_UPDATE)
    with _patched(api):
        assert await hass.config_entries.async_reload(entry.entry_id)
        await hass.async_block_till_done()
    assert events == []
    assert _state(hass, "sold_count").state == "2"


async def test_expired_session_relogs(hass: HomeAssistant, entry, api: FakeApi, freezer) -> None:
    api.logged_in = False
    api.calls.clear()
    freezer.tick(300)
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert api.calls[:2] == ["myreservations", "login"] or api.calls[:2] == ["mysales", "login"]
    assert entry.runtime_data.last_update_success


async def test_rejected_password_starts_reauth(
    hass: HomeAssistant, entry, api: FakeApi, freezer
) -> None:
    api.logged_in = False
    api.login_error = InvalidAuth()
    freezer.tick(300)
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    flows = hass.config_entries.flow.async_progress()
    assert [f["context"]["source"] for f in flows] == ["reauth"]
