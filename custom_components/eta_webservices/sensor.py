from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN, STATIC_URIs

async def async_setup_entry(hass, entry, async_add_entities):
    """Registriert Sensoren, die Daten vom Kessel geliefert haben."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    
    sensors = []
    
    # 1. Nur Sensoren erstellen, für die echte Daten im Koordinator gelandet sind
    for key, info in STATIC_URIs.items():
        if key in coordinator.data:
            sensors.append(ETAStaticSensor(coordinator, key, info))
            
    # 2. Den Bildpfad-Sensor immer erstellen
    sensors.append(ETASystemImageSensor(coordinator))
        
    async_add_entities(sensors)

class ETAStaticSensor(CoordinatorEntity, SensorEntity):
    """Repräsentiert einen ETA Sensor mit fester URI."""
    def __init__(self, coordinator, key, info):
        super().__init__(coordinator)
        self.key = key
        self._attr_name = info["name"]
        self._attr_unique_id = f"eta_static_{coordinator.config_entry.entry_id}_{key}"
        self._attr_icon = info["icon"]

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
    """Sensor, der das gewählte Schema-Bild ausgibt."""
    def __init__(self, coordinator):
        super().__init__(coordinator)
        self.coordinator = coordinator
        self._attr_name = "ETA精 Anlagenbild Pfad"
        self._attr_unique_id = f"eta_style_{coordinator.config_entry.entry_id}_image"
        self._attr_icon = "mdi:image"

    @property
    def native_value(self):
        return self.coordinator.system_image_path
