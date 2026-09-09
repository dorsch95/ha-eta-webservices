from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass

DOMAIN = "eta_webservices"
DEFAULT_PORT = 8080

# Feste Zuordnung der Schemen zu den Bild-Schlüsseln
SCHEMAS = {
    "Kessel": "kessel",
    "Kessel + Puffer": "kessel_puffer",
    "Kessel + Puffer + 1x Heizkreis": "kessel_puffer_hk1",
    "Kessel + Puffer + FWM": "kessel_puffer_fwm",
    "Kessel + Puffer + 1x Heizkreis + FWM": "kessel_puffer_hk1_fwm",
    "Kessel + Puffer + 2x Heizkreis": "kessel_puffer_hk2",
    "Kessel + Puffer + 2x Heizkreis + FWM": "kessel_puffer_hk2_fwm",
}

# Feste Standard-URIs (Fallback, falls die automatische Erkennung über
# /user/menu fehlschlägt). Jeder Eintrag trägt zusätzlich device_class,
# state_class und die erwartete Standard-Einheit, damit Home Assistant
# Temperaturen/Drücke/Gewichte korrekt einordnet und Verlaufsstatistiken
# führen kann - unabhängig von Icon oder Schlüsselnamen.
STATIC_URIs = {
    # --- KESSEL & UMGEBUNG ---
    "kessel_temperatur": {
        "uri": "/264/10891/0/11109/0",
        "name": "ETA Kesseltemperatur",
        "icon": "mdi:thermometer",
        "device_class": SensorDeviceClass.TEMPERATURE,
        "state_class": SensorStateClass.MEASUREMENT,
        "default_unit": "°C",
    },
    "ruecklauf_temperatur": {
        "uri": "/264/10891/0/11160/0",
        "name": "ETA Rücklauftemperatur",
        "icon": "mdi:thermometer",
        "device_class": SensorDeviceClass.TEMPERATURE,
        "state_class": SensorStateClass.MEASUREMENT,
        "default_unit": "°C",
    },
    "kessel_druck": {
        "uri": "/264/10891/0/0/12180",
        "name": "ETA Kesseldruck",
        "icon": "mdi:gauge",
        "device_class": SensorDeviceClass.PRESSURE,
        "state_class": SensorStateClass.MEASUREMENT,
        "default_unit": "bar",
    },
    "pellet_tagesbehälter": {
        "uri": "/264/10891/0/0/12011",
        "name": "ETA Pellet Inhalt Tagesbehälter",
        "icon": "mdi:weight-kilogram",
        "device_class": SensorDeviceClass.WEIGHT,
        "state_class": SensorStateClass.MEASUREMENT,
        "default_unit": "kg",
    },
    "aussentemperatur": {
        "uri": "/120/10241/0/11127/0",
        "name": "ETA Außentemperatur",
        "icon": "mdi:thermometer",
        "device_class": SensorDeviceClass.TEMPERATURE,
        "state_class": SensorStateClass.MEASUREMENT,
        "default_unit": "°C",
    },

    # --- PUFFERSPEICHER ---
    "puffer_ladezustand": {
        "uri": "/120/10601/0/0/12528",
        "name": "ETA Puffer Ladezustand",
        "icon": "mdi:battery-charging-60",
        "device_class": None,
        "state_class": SensorStateClass.MEASUREMENT,
        "default_unit": "%",
    },

    # --- HEIZKREIS 1 ---
    "heizkreis_vorlauf": {
        "uri": "/120/10101/0/11060/0",
        "name": "ETA Heizkreis Vorlauftemperatur",
        "icon": "mdi:thermometer",
        "device_class": SensorDeviceClass.TEMPERATURE,
        "state_class": SensorStateClass.MEASUREMENT,
        "default_unit": "°C",
    },
    "heizkreis_anforderung": {
        "uri": "/120/10101/0/11124/2001",
        "name": "ETA Heizkreis Anforderung",
        "icon": "mdi:heat-wave",
        "is_string": True,
    },

    # --- FRISCHWASSERMODUL ---
    "fwm_warmwasser": {
        "uri": "/79/10531/0/11148/0",
        "name": "ETA FWM Warmwassertemperatur",
        "icon": "mdi:water-thermometer",
        "device_class": SensorDeviceClass.TEMPERATURE,
        "state_class": SensorStateClass.MEASUREMENT,
        "default_unit": "°C",
    },
}

# --- PUFFERSPEICHER-FÜHLER (dynamisch) ---
# PufferFlex kann je nach Anlage zwischen PUFFER_FUEHLER_MIN und
# PUFFER_FUEHLER_MAX Temperaturfühler haben. Fühler 1 ist immer der oberste,
# der jeweils letzte (höchste Nummer) ist immer der unterste - dazwischen
# gibt es keine feste Benennung. Die tatsächliche Anzahl wird zur Laufzeit
# über den Menübaum der Anlage ermittelt (siehe uri_discovery.py). Diese
# Liste liefert nur die URIs für den Fallback, falls die Erkennung komplett
# fehlschlägt (Reihenfolge = Fühler 1, 2, 3, ...).
PUFFER_FUEHLER_MIN = 3
PUFFER_FUEHLER_MAX = 8
PUFFER_FUEHLER_FALLBACK_URIS = [
    "/120/10601/0/11327/0",
    "/120/10601/0/11328/0",
    "/120/10601/0/11329/0",
    "/120/10601/0/11330/0",
    "/120/10601/0/11331/0",
]


def puffer_fuehler_info(index, is_last):
    """Baut den Info-Eintrag (Name/Icon/Klassen) für einen Puffer-Fühler."""
    if index == 1:
        name = f"ETA Puffer Fühler {index} (oben)"
    elif is_last:
        name = f"ETA Puffer Fühler {index} (unten)"
    else:
        name = f"ETA Puffer Fühler {index}"
    return {
        "name": name,
        "icon": "mdi:thermometer-lines",
        "device_class": SensorDeviceClass.TEMPERATURE,
        "state_class": SensorStateClass.MEASUREMENT,
        "default_unit": "°C",
    }
