"""Config flow tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.kirpparikalle.api import CannotConnect, InvalidAuth, Shop
from custom_components.kirpparikalle.const import CONF_COMPANY_ID, CONF_SHOP_NAME, DOMAIN

API = "custom_components.kirpparikalle.config_flow.KirppariKalleApi"
SETUP = "custom_components.kirpparikalle.async_setup_entry"
USER = {CONF_USERNAME: "myyja", CONF_PASSWORD: "salasana"}


async def _start(hass: HomeAssistant):
    return await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )


async def test_several_shops(hass: HomeAssistant) -> None:
    shops = [Shop("100", "Kirppis A"), Shop("101", "Kirppis B")]
    result = await _start(hass)
    assert result["type"] is FlowResultType.FORM

    with (
        patch(f"{API}.discover_shops", AsyncMock(return_value=shops)),
        patch(SETUP, return_value=True),
    ):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], USER)
        assert result["step_id"] == "shop"
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_COMPANY_ID: "101"}
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Kirppis B"
    assert result["result"].unique_id == "myyja:101"
    assert result["data"] == {**USER, CONF_COMPANY_ID: "101", CONF_SHOP_NAME: "Kirppis B"}


async def test_single_shop(hass: HomeAssistant) -> None:
    result = await _start(hass)
    with (
        patch(f"{API}.discover_shops", AsyncMock(return_value=[Shop("default", "Ainoa")])),
        patch(SETUP, return_value=True),
    ):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], USER)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Ainoa"


async def test_errors_then_success(hass: HomeAssistant) -> None:
    result = await _start(hass)
    for error, key in ((InvalidAuth(), "invalid_auth"), (CannotConnect(), "cannot_connect")):
        with patch(f"{API}.discover_shops", AsyncMock(side_effect=error)):
            result = await hass.config_entries.flow.async_configure(result["flow_id"], USER)
        assert result["errors"] == {"base": key}

    with (
        patch(f"{API}.discover_shops", AsyncMock(return_value=[Shop("default", "Ainoa")])),
        patch(SETUP, return_value=True),
    ):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], USER)
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_already_configured(hass: HomeAssistant) -> None:
    MockConfigEntry(domain=DOMAIN, unique_id="myyja:default").add_to_hass(hass)
    result = await _start(hass)
    with patch(f"{API}.discover_shops", AsyncMock(return_value=[Shop("default", "Ainoa")])):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], USER)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reauth(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="myyja:101",
        data={**USER, CONF_COMPANY_ID: "101", CONF_SHOP_NAME: "Kirppis B"},
    )
    entry.add_to_hass(hass)
    result = await entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"

    with patch(f"{API}.login", AsyncMock(side_effect=InvalidAuth)):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_PASSWORD: "vanha"}
        )
    assert result["errors"] == {"base": "invalid_auth"}

    with patch(f"{API}.login", AsyncMock()) as login, patch(SETUP, return_value=True):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_PASSWORD: "uusi"}
        )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_PASSWORD] == "uusi"
    login.assert_awaited_once_with("myyja", "uusi", "101")
