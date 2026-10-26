"""Sales update event entity for Kirppari-Kalle."""

from __future__ import annotations

from homeassistant.components.event import EventEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import KirppariKalleConfigEntry
from .const import EVENT_TYPE_SALES_UPDATE
from .entity import KirppariKalleEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: KirppariKalleConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities([SalesUpdateEvent(entry.runtime_data, "sales_update")])


class SalesUpdateEvent(KirppariKalleEntity, EventEntity):
    """Fires when the balance or the sold items change."""

    _attr_event_types = [EVENT_TYPE_SALES_UPDATE]

    def __init__(self, coordinator, key: str) -> None:
        super().__init__(coordinator, key)
        self._seen_seq = coordinator.data.event_seq

    @callback
    def _handle_coordinator_update(self) -> None:
        data = self.coordinator.data
        if data.event_seq != self._seen_seq and data.last_event:
            self._seen_seq = data.event_seq
            attributes = {k: v for k, v in data.last_event.items() if k != "event_type"}
            self._trigger_event(EVENT_TYPE_SALES_UPDATE, attributes)
        super()._handle_coordinator_update()
