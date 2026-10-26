"""Sensors for Kirppari-Kalle."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import KirppariKalleConfigEntry
from .coordinator import KirppariKalleData
from .entity import KirppariKalleEntity


@dataclass(frozen=True, kw_only=True)
class KirppariKalleSensorDescription(SensorEntityDescription):
    value_fn: Callable[[KirppariKalleData], float | int | datetime | None]


SENSORS: tuple[KirppariKalleSensorDescription, ...] = (
    KirppariKalleSensorDescription(
        key="balance",
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement="EUR",
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=2,
        value_fn=lambda d: d.balance,
    ),
    KirppariKalleSensorDescription(
        key="sold_count",
        value_fn=lambda d: d.sold_count,
    ),
    KirppariKalleSensorDescription(
        key="reservation_start",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda d: d.reservation_start,
    ),
    KirppariKalleSensorDescription(
        key="reservation_end",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda d: d.reservation_end,
    ),
    KirppariKalleSensorDescription(
        key="checked_at",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.checked_at,
    ),
    KirppariKalleSensorDescription(
        key="data_updated_at",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.data_updated_at,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: KirppariKalleConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(KirppariKalleSensor(coordinator, desc) for desc in SENSORS)


class KirppariKalleSensor(KirppariKalleEntity, SensorEntity):
    entity_description: KirppariKalleSensorDescription

    def __init__(self, coordinator, description: KirppariKalleSensorDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> float | int | datetime | None:
        return self.entity_description.value_fn(self.coordinator.data)
