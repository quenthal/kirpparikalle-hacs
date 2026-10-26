"""The Kirppari-Kalle integration (unofficial)."""

from __future__ import annotations

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .api import KirppariKalleApi
from .coordinator import KirppariKalleCoordinator

PLATFORMS = [Platform.BINARY_SENSOR, Platform.EVENT, Platform.SENSOR]

type KirppariKalleConfigEntry = ConfigEntry[KirppariKalleCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: KirppariKalleConfigEntry) -> bool:
    """Set up Kirppari-Kalle from a config entry."""
    # Own cookie jar per entry: the login is bound to one flea market.
    session = async_create_clientsession(hass, auto_cleanup=False, cookie_jar=aiohttp.CookieJar())
    api = KirppariKalleApi(session)
    coordinator = KirppariKalleCoordinator(hass, entry, api)

    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception:
        await api.close()
        raise

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: KirppariKalleConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.api.close()
    return unloaded
