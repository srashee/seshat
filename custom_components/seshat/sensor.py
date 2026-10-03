"""Native sensors: no state-database writes or external broker."""

from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .const import DOMAIN


async def async_setup_entry(hass, entry, async_add_entities):
    controller = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            SeshatSensor(controller, key, name, unit)
            for key, name, unit in (
                ("person", "Front Door Recognized Person", None),
                ("confidence", "Front Door Face Confidence", None),
                ("processing_ms", "Front Door Face Processing Time", "ms"),
            )
        ]
    )


class SeshatSensor(SensorEntity):
    _attr_should_poll = False

    def __init__(self, controller, key, name, unit):
        self.controller, self.key = controller, key
        self._attr_name = name
        self._attr_unique_id = f"{controller.entry.entry_id}_{key}"
        self._attr_native_unit_of_measurement = unit
        self._attr_icon = "mdi:face-recognition" if key == "person" else "mdi:gauge"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, controller.entry.entry_id)},
            "name": "Seshat Front Door",
            "manufacturer": "Seshat",
        }

    async def async_added_to_hass(self):
        self.async_on_remove(
            async_dispatcher_connect(self.hass, self.controller.signal, self.async_write_ha_state)
        )

    @property
    def available(self):
        return self.controller.available

    @property
    def native_value(self):
        return (self.controller.result or {}).get(self.key)

    @property
    def extra_state_attributes(self):
        if self.key == "person" and self.available:
            return self.controller.result
        return None
