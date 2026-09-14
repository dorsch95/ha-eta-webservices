from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import Platform

DOMAIN = "eta_webservices"
DEFAULT_PORT = 8080

PLATFORMS = [Platform.SENSOR]

CONF_SCHEMA = "schema"
CONF_FUB_NAMES = "fub_names"
CONF_SCAN_INTERVAL = "scan_interval"

DEFAULT_SCAN_INTERVAL = 30
MIN_SCAN_INTERVAL = 10
MAX_SCAN_INTERVAL = 600

REQUEST_TIMEOUT = 8
MENU_TIMEOUT = 20
MAX_PARALLEL_REQUESTS = 5

SCHEMAS = {
    "Kessel": "kessel",
    "Kessel + Puffer": "kessel_puffer",
    "Kessel + Puffer + 1x Heizkreis": "kessel_puffer_hk1",
    "Kessel + Puffer + FWM": "kessel_puffer_fwm",
    "Kessel + Puffer + 1x Heizkreis + FWM": "kessel_puffer_hk1_fwm",
    "Kessel + Puffer + 2x Heizkreis": "kessel_puffer_hk2",
    "Kessel + Puffer + 2x Heizkreis + FWM": "kessel_puffer_hk2_fwm",
}

STATIC_URIs = {
    "kessel_temperatur": {
        "uri": "/264/10891/0/11109/0",
        "name": "Kesseltemperatur",
        "icon": "mdi:thermometer",
        "device_class": SensorDeviceClass.TEMPERATURE,
        "state_class": SensorStateClass.MEASUREMENT,
        "default_unit": "°C",
    },
    "ruecklauf_temperatur": {
        "uri": "/264/10891/0/11160/0",
        "name": "Rücklauftemperatur",
        "icon": "mdi:thermometer",
        "device_class": SensorDeviceClass.TEMPERATURE,
        "state_class": SensorStateClass.MEASUREMENT,
        "default_unit": "°C",
    },
    "kessel_druck": {
        "uri": "/264/10891/0/0/12180",
        "name": "Kesseldruck",
        "icon": "mdi:gauge",
        "device_class": SensorDeviceClass.PRESSURE,
        "state_class": SensorStateClass.MEASUREMENT,
        "default_unit": "bar",
    },
    "pellet_tagesbehälter": {
        "uri": "/264/10891/0/0/12011",
        "name": "Pellet Inhalt Tagesbehälter",
        "icon": "mdi:weight-kilogram",
        "device_class": SensorDeviceClass.WEIGHT,
        "state_class": SensorStateClass.MEASUREMENT,
        "default_unit": "kg",
    },
    "aussentemperatur": {
        "uri": "/120/10241/0/11127/0",
        "name": "Außentemperatur",
        "icon": "mdi:thermometer",
        "device_class": SensorDeviceClass.TEMPERATURE,
        "state_class": SensorStateClass.MEASUREMENT,
        "default_unit": "°C",
    },
    "kessel_soll": {
        "uri": "/264/10891/0/0/13953",
        "name": "Kessel Solltemperatur",
        "icon": "mdi:thermostat",
        "device_class": SensorDeviceClass.TEMPERATURE,
        "state_class": SensorStateClass.MEASUREMENT,
        "default_unit": "°C",
    },
    "restsauerstoff": {
        "uri": "/264/10891/0/11108/2060",
        "name": "Restsauerstoff",
        "icon": "mdi:percent",
        "device_class": None,
        "state_class": SensorStateClass.MEASUREMENT,
        "default_unit": "%",
    },
    "aschebox_verbrauch": {
        "uri": "/264/10891/0/0/12013",
        "name": "Aschebox Verbrauch seit Leerung",
        "icon": "mdi:trash-can",
        "device_class": SensorDeviceClass.WEIGHT,
        "state_class": SensorStateClass.MEASUREMENT,
        "default_unit": "kg",
    },
    "aschebox_schwelle": {
        "uri": "/264/10891/0/0/12120",
        "name": "Aschebox Leeren nach",
        "icon": "mdi:trash-can-outline",
        "device_class": SensorDeviceClass.WEIGHT,
        "state_class": SensorStateClass.MEASUREMENT,
        "default_unit": "kg",
    },
    "puffer_ladezustand": {
        "uri": "/120/10601/0/0/12528",
        "name": "Puffer Ladezustand",
        "icon": "mdi:battery-charging-60",
        "device_class": None,
        "state_class": SensorStateClass.MEASUREMENT,
        "default_unit": "%",
    },
    "heizkreis_vorlauf": {
        "uri": "/120/10101/0/11060/0",
        "name": "Heizkreis Vorlauftemperatur",
        "icon": "mdi:thermometer",
        "device_class": SensorDeviceClass.TEMPERATURE,
        "state_class": SensorStateClass.MEASUREMENT,
        "default_unit": "°C",
    },
    "heizkreis_anforderung": {
        "uri": "/120/10101/0/11124/2001",
        "name": "Heizkreis Anforderung",
        "icon": "mdi:heat-wave",
        "is_string": True,
    },
    "fwm_warmwasser": {
        "uri": "/79/10531/0/11148/0",
        "name": "FWM Warmwassertemperatur",
        "icon": "mdi:water-thermometer",
        "device_class": SensorDeviceClass.TEMPERATURE,
        "state_class": SensorStateClass.MEASUREMENT,
        "default_unit": "°C",
    },
}

PUFFER_FUEHLER_MAX = 8

PUFFER_FUEHLER_FALLBACK_URIS = [
    "/120/10601/0/11327/0",
    "/120/10601/0/11328/0",
    "/120/10601/0/11329/0",
]
"""Rückfallebene, falls der Menübaum nicht gelesen werden kann.

PufferFlex hat immer mindestens drei Fühler (oben, Mitte, unten); mehr
werden nur angelegt, wenn sie im Menübaum tatsächlich gefunden wurden -
sonst entstünden Entitäten, die dauerhaft ohne Wert bleiben.
"""


def puffer_fuehler_info(index, is_last):
    """Baut den Info-Eintrag (Name/Icon/Klassen) für einen Puffer-Fühler."""
    if index == 1:
        position = "oben"
    elif is_last:
        position = "unten"
    else:
        position = None
    return {
        "name": f"Puffer Fühler {index}",
        "position": position,
        "icon": "mdi:thermometer-lines",
        "device_class": SensorDeviceClass.TEMPERATURE,
        "state_class": SensorStateClass.MEASUREMENT,
        "default_unit": "°C",
    }


DISCOVERY_ONLY_SENSORS = {
    "heizkreis2_vorlauf": {
        "name": "Heizkreis 2 Vorlauftemperatur",
        "icon": "mdi:thermometer",
        "device_class": SensorDeviceClass.TEMPERATURE,
        "state_class": SensorStateClass.MEASUREMENT,
        "default_unit": "°C",
    },
    "heizkreis2_anforderung": {
        "name": "Heizkreis 2 Anforderung",
        "icon": "mdi:heat-wave",
        "is_string": True,
    },
}

OPTIONAL_SENSORS = {
    "fwm_zirkulation": {
        "name": "FWM Zirkulation",
        "icon": "mdi:water-thermometer",
        "default_unit": "°C",
    },
}

FUB_ROLE_DEFAULT_NAMES = {
    "kessel": ["Kessel"],
    "sys": ["Sys"],
    "pufferflex": ["PufferFlex", "Puffer"],
    "fwm": ["FWM", "WW"],
    "hk": ["HK", "HK1"],
    "hk2": ["HK2"],
}

SCHEMA_FUB_ROLES = {
    "Kessel": ["kessel", "sys"],
    "Kessel + Puffer": ["kessel", "sys", "pufferflex"],
    "Kessel + Puffer + 1x Heizkreis": ["kessel", "sys", "pufferflex", "hk"],
    "Kessel + Puffer + FWM": ["kessel", "sys", "pufferflex", "fwm"],
    "Kessel + Puffer + 1x Heizkreis + FWM": ["kessel", "sys", "pufferflex", "hk", "fwm"],
    "Kessel + Puffer + 2x Heizkreis": ["kessel", "sys", "pufferflex", "hk", "hk2"],
    "Kessel + Puffer + 2x Heizkreis + FWM": ["kessel", "sys", "pufferflex", "hk", "hk2", "fwm"],
}


def fub_role_default(role, roles_in_schema):
    """Liefert den sinnvollsten Standardnamen für ein Formularfeld.

    Bei zwei Heizkreisen heißt der erste laut ETA-Konvention "HK1" statt
    "HK" - das wird hier als Vorbelegung berücksichtigt.
    """
    if role == "hk" and "hk2" in roles_in_schema:
        return "HK1"
    return FUB_ROLE_DEFAULT_NAMES[role][0]
