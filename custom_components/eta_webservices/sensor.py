from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass
)
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN, STATIC_URIs

async def async_setup_entry(hass, entry, async_add_entities):
    """Registriert Sensoren, die Daten vom Kessel geliefert haben."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    
    sensors = []
    
    for key, info in STATIC_URIs.items():
        if key in coordinator.data:
            sensors.append(ETAStaticSensor(coordinator, key, info))
            
    # Den Bildpfad-Sensor immer erstellen
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
        
        # --- KORREKTUR: Dem System sagen, dass es sich um echte Messwerte handelt ---
        if info.get("icon") == "mdi:thermometer" or "temperatur" in key:
            self._attr_device_class = SensorDeviceClass.TEMPERATURE
            self._attr_state_class = SensorStateClass.MEASUREMENT
        elif info.get("icon") == "mdi:gauge":
            self._attr_device_class = SensorDeviceClass.PRESSURE
            self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self):
        data = self.coordinator.data.get(self.key)
        if data:
            val = data["value"]
            # Wenn es eine Zahl ist, runden wir sie sauber auf 1 Dezimalstelle
            if isinstance(val, (int, float)):
                return round(float(val), 1)
            return val
        return None

    @property
    def native_unit_of_measurement(self):
        data = self.coordinator.data.get(self.key)
        if data and data["unit"] != "":
            return data["unit"]
        # Standard-Einheit setzen, falls die ETA im XML mal patzt
        if "temperatur" in self.key:
            return "°C"
        return None

class ETASystemImageSensor(CoordinatorEntity, SensorEntity):
    """Sensor, der das gewählte Schema-Bild ausgibt."""
    def __init__(self, coordinator):
        super().__init__(coordinator)
        self.coordinator = coordinator
        self._attr_name = "ETA Anlagenbild Pfad"
        self._attr_unique_id = f"eta_style_{coordinator.config_entry.entry_id}_image"
        self._attr_icon = "mdi:image"

    @property
    def native_value(self):
        return self.coordinator.system_image_path
