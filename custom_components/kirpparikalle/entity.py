"""Base entity for Kirppari-Kalle."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import KirppariKalleCoordinator


class KirppariKalleEntity(CoordinatorEntity[KirppariKalleCoordinator]):
    """One device per flea market (config entry)."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: KirppariKalleCoordinator, key: str) -> None:
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self._attr_unique_id = f"{entry.unique_id}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, str(entry.unique_id))},
            name=entry.title,
            manufacturer="Kirppari-Kalle (unofficial integration)",
            model="Myynnin seuranta",
            entry_type=DeviceEntryType.SERVICE,
        )
