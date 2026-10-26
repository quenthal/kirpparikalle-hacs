"""Binary sensor for Kirppari-Kalle."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import KirppariKalleConfigEntry
from .entity import KirppariKalleEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: KirppariKalleConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities([ReservationActiveSensor(entry.runtime_data, "reservation_active")])


class ReservationActiveSensor(KirppariKalleEntity, BinarySensorEntity):
    """On during the sales period (first opening to last closing)."""

    @property
    def is_on(self) -> bool:
        return self.coordinator.data.reservation_active
