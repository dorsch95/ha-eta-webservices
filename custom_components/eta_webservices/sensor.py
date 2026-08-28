from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.device_registry import DeviceInfo
from .const import DOMAIN, SENSOR_DEFINITIONS

async def async_setup_entry(hass, entry, async_add_entities):
    config_data = hass.data[DOMAIN][entry.entry_id]
    coordinator = config_data["coordinator"]
    detected_uris = config_data["detected_uris"]
    
    sensors = []
    # 1. Die echten Temperatursensoren registrieren
    for key in detected_uris.keys():
        if key in SENSOR_DEFINITIONS:
            sensors.append(ETAAutodiscoveredSensor(coordinator, key, SENSOR_DEFINITIONS[key]))
            
    # 2. Den Bild-Sensor hinzufügen
    sensors.append(ETASystemImageSensor(coordinator))
        
    async_add_entities(sensors)

class ETAAutodiscoveredSensor(CoordinatorEntity, SensorEntity):
    def __init__(self, coordinator, key, config_info):
        super().__init__(coordinator)
        self.key = key
        self._attr_name = config_info["friendly_name"]
        self._attr_unique_id = f"eta_auto_{coordinator.config_entry.entry_id}_{key}"
        self._attr_icon = config_info["icon"]

    @property
    def native_value(self):
        data = self.coordinator.data.get(self.key)
        if data:
            return data["text"] if data["unit"] == "" or data["unit"] is None else data["value"]
        return None

    @property
    def native_unit_of_measurement(self):
        data = self.coordinator.data.get(self.key)
        if data and data["unit"] != "":
            return data["unit"]
        return None

class ETASystemImageSensor(CoordinatorEntity, SensorEntity):
    """Sensor, der den Pfad zum ausgewählten Anlagenbild ausgibt."""
    def __init__(self, coordinator):
        super().__init__(coordinator)
        self.coordinator = coordinator
        self._attr_name = "ETA Anlagenbild Pfad"
        self._attr_unique_id = f"eta_style_{coordinator.config_entry.entry_id}_image"
        self._attr_icon = "mdi:image"

    @property
    def native_value(self):
        # Gibt den Pfad z.B. '/local/community/eta_webservices/kessel_puffer.png' aus
        return self.coordinator.system_image_path
