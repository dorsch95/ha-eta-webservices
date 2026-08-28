from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN, TRACKED_URIs

async def async_setup_entry(hass, entry, async_add_entities):
    """Sensoren basierend auf dem Coordinator registrieren."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    
    sensors = []
    for key, info in TRACKED_URIs.items():
        sensors.append(ETAWsSensor(coordinator, key, info))
        
    async_add_entities(sensors)

class ETAWsSensor(CoordinatorEntity, SensorEntity):
    """Repräsentiert einen ETA Sensor."""

    def __init__(self, coordinator, key, info):
        super().__init__(coordinator)
        self.key = key
        self.info = info
        self._attr_name = info["name"]
        self._attr_unique_id = f"eta_{coordinator.config_entry.entry_id}_{key}"
        self._attr_icon = info["icon"]

    @property
    def native_value(self):
        """Gibt den Zustand des Sensors zurück."""
        data = self.coordinator.data.get(self.key)
        if data:
            # Wenn die ETA keinen Einheiten-Typ sendet, ist es ein Text-Status (z.B. "Heizen")
            if data["unit"] == "" or data["unit"] is None:
                return data["text"]
            return data["value"]
        return None

    @property
    def native_unit_of_measurement(self):
        """Gibt die Maßeinheit zurück (falls vorhanden)."""
        data = self.coordinator.data.get(self.key)
        if data and data["unit"] != "":
            return data["unit"]
        return None
