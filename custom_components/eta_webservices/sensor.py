from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN

async def async_setup_entry(hass, entry, async_add_entities):
    """Registriert Sensoren für alle für diese Anlage bekannten Messwerte."""
    coordinator = hass.data[DOMAIN][entry.entry_id]

    sensors = [
        ETAStaticSensor(coordinator, key, info)
        for key, info in coordinator.sensor_defs.items()
    ]

    sensors.append(ETASystemImageSensor(coordinator))
    sensors.append(ETAAscheboxStatusSensor(coordinator))

    async_add_entities(sensors)

class ETAStaticSensor(CoordinatorEntity, SensorEntity):
    """Repräsentiert einen ETA Sensor mit fester URI."""
    _attr_has_entity_name = True

    def __init__(self, coordinator, key, info):
        super().__init__(coordinator)
        self.key = key
        self._default_unit = info.get("default_unit")
        self._attr_name = info["name"]
        self._attr_unique_id = f"eta_static_{coordinator.config_entry.entry_id}_{key}"
        self._attr_icon = info["icon"]
        self._attr_device_info = coordinator.device_info
        self._attr_device_class = info.get("device_class")
        self._attr_state_class = info.get("state_class")

    @property
    def native_value(self):
        data = self.coordinator.data.get(self.key)
        if data:
            val = data["value"]
            if isinstance(val, (int, float)):
                return round(float(val), 1)
            return val
        return None

    @property
    def native_unit_of_measurement(self):
        data = self.coordinator.data.get(self.key)
        if data and data["unit"] != "":
            return data["unit"]
        return self._default_unit

class ETASystemImageSensor(CoordinatorEntity, SensorEntity):
    """Sensor, der das gewählte Schema-Bild ausgibt."""
    _attr_has_entity_name = True

    def __init__(self, coordinator):
        super().__init__(coordinator)
        self.coordinator = coordinator
        self._attr_name = "Anlagenbild Pfad"
        self._attr_unique_id = f"eta_style_{coordinator.config_entry.entry_id}_image"
        self._attr_icon = "mdi:image"
        self._attr_device_info = coordinator.device_info

    @property
    def native_value(self):
        return self.coordinator.system_image_path

class ETAAscheboxStatusSensor(CoordinatorEntity, SensorEntity):
    """Kombinierte Anzeige 'Verbrauch/Schwellwert' für die Aschebox, z.B. '459/1000'.

    picture-elements-Karten unterstützen kein `type: markdown`-Element, daher
    wird die Kombination hier serverseitig berechnet und als normaler Sensor
    bereitgestellt, den eine einfache state-label-Karte referenzieren kann.
    """
    _attr_has_entity_name = True

    def __init__(self, coordinator):
        super().__init__(coordinator)
        self.coordinator = coordinator
        self._attr_name = "Aschebox Status"
        self._attr_unique_id = f"eta_static_{coordinator.config_entry.entry_id}_aschebox_status"
        self._attr_icon = "mdi:trash-can"
        self._attr_device_info = coordinator.device_info

    @property
    def native_value(self):
        verbrauch = self.coordinator.data.get("aschebox_verbrauch")
        schwelle = self.coordinator.data.get("aschebox_schwelle")
        if not verbrauch or not schwelle:
            return None
        try:
            return f"{round(verbrauch['value']):.0f}/{round(schwelle['value']):.0f}"
        except (TypeError, ValueError):
            return None

    @property
    def native_unit_of_measurement(self):
        return "kg"
