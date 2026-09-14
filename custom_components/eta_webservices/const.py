from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import Platform

DOMAIN = "eta_webservices"
DEFAULT_PORT = 8080

PLATFORMS = [Platform.SENSOR]

CONF_SCHEMA = "schema"
CONF_COMPONENTS = "components"
CONF_FUB_NAMES = "fub_names"
CONF_SCAN_INTERVAL = "scan_interval"

DEFAULT_SCAN_INTERVAL = 30
MIN_SCAN_INTERVAL = 10
MAX_SCAN_INTERVAL = 600

REQUEST_TIMEOUT = 8
MENU_TIMEOUT = 20
MAX_PARALLEL_REQUESTS = 5

COMPONENTS = {
    "kessel": {
        "name": "Kessel",
        "image": "kessel",
        "roles": ["kessel", "sys"],
        "required": True,
    },
    "puffer": {"name": "Pufferspeicher", "image": "puffer", "roles": ["pufferflex"]},
    "fwm": {"name": "FWM", "image": "fwm", "roles": ["fwm"]},
    "hk1": {"name": "Heizkreis 1", "image": "heizkreis", "roles": ["hk"]},
    "hk2": {"name": "Heizkreis 2", "image": "heizkreis", "roles": ["hk2"]},
}
"""Die wählbaren Bausteine einer Anlage.

Jede Komponente bringt ihre eigene Grafik, ihre Funktionsblock-Rollen und
ihre Messwerte mit. Neue Komponenten (z.B. Solar) werden hier ergänzt und
bei den Sensoren über das Feld "component" zugeordnet - es gibt bewusst
keine Tabelle fertiger Anlagenschemata mehr, sonst bräuchte jede
Kombination aus n Komponenten einen eigenen Eintrag und ein eigenes Bild.
"""

DEFAULT_COMPONENTS = ["kessel", "puffer"]

LEGACY_SCHEMA_COMPONENTS = {
    "Kessel": ["kessel"],
    "Kessel + Puffer": ["kessel", "puffer"],
    "Kessel + Puffer + 1x Heizkreis": ["kessel", "puffer", "hk1"],
    "Kessel + Puffer + FWM": ["kessel", "puffer", "fwm"],
    "Kessel + Puffer + 1x Heizkreis + FWM": ["kessel", "puffer", "hk1", "fwm"],
    "Kessel + Puffer + 2x Heizkreis": ["kessel", "puffer", "hk1", "hk2"],
    "Kessel + Puffer + 2x Heizkreis + FWM": ["kessel", "puffer", "hk1", "hk2", "fwm"],
}
"""Übersetzt die festen Anlagenschemata bis Version 0.14 in Komponenten."""

STATIC_URIs = {
    "kessel_temperatur": {
        "component": "kessel",
        "uri": "/264/10891/0/11109/0",
        "name": "Kesseltemperatur",
        "icon": "mdi:thermometer",
        "device_class": SensorDeviceClass.TEMPERATURE,
        "state_class": SensorStateClass.MEASUREMENT,
        "default_unit": "°C",
    },
    "ruecklauf_temperatur": {
        "component": "kessel",
        "uri": "/264/10891/0/11160/0",
        "name": "Rücklauftemperatur",
        "icon": "mdi:thermometer",
        "device_class": SensorDeviceClass.TEMPERATURE,
        "state_class": SensorStateClass.MEASUREMENT,
        "default_unit": "°C",
    },
    "kessel_druck": {
        "component": "kessel",
        "uri": "/264/10891/0/0/12180",
        "name": "Kesseldruck",
        "icon": "mdi:gauge",
        "device_class": SensorDeviceClass.PRESSURE,
        "state_class": SensorStateClass.MEASUREMENT,
        "default_unit": "bar",
    },
    "pellet_tagesbehälter": {
        "component": "kessel",
        "uri": "/264/10891/0/0/12011",
        "name": "Pellet Inhalt Tagesbehälter",
        "icon": "mdi:weight-kilogram",
        "device_class": SensorDeviceClass.WEIGHT,
        "state_class": SensorStateClass.MEASUREMENT,
        "default_unit": "kg",
    },
    "aussentemperatur": {
        "component": "kessel",
        "uri": "/120/10241/0/11127/0",
        "name": "Außentemperatur",
        "icon": "mdi:thermometer",
        "device_class": SensorDeviceClass.TEMPERATURE,
        "state_class": SensorStateClass.MEASUREMENT,
        "default_unit": "°C",
    },
    "kessel_soll": {
        "component": "kessel",
        "uri": "/264/10891/0/0/13953",
        "name": "Kessel Solltemperatur",
        "icon": "mdi:thermostat",
        "device_class": SensorDeviceClass.TEMPERATURE,
        "state_class": SensorStateClass.MEASUREMENT,
        "default_unit": "°C",
    },
    "restsauerstoff": {
        "component": "kessel",
        "uri": "/264/10891/0/11108/2060",
        "name": "Restsauerstoff",
        "icon": "mdi:percent",
        "device_class": None,
        "state_class": SensorStateClass.MEASUREMENT,
        "default_unit": "%",
    },
    "aschebox_verbrauch": {
        "component": "kessel",
        "uri": "/264/10891/0/0/12013",
        "name": "Aschebox Verbrauch seit Leerung",
        "icon": "mdi:trash-can",
        "device_class": SensorDeviceClass.WEIGHT,
        "state_class": SensorStateClass.MEASUREMENT,
        "default_unit": "kg",
    },
    "aschebox_schwelle": {
        "component": "kessel",
        "uri": "/264/10891/0/0/12120",
        "name": "Aschebox Leeren nach",
        "icon": "mdi:trash-can-outline",
        "device_class": SensorDeviceClass.WEIGHT,
        "state_class": SensorStateClass.MEASUREMENT,
        "default_unit": "kg",
    },
    "puffer_ladezustand": {
        "component": "puffer",
        "uri": "/120/10601/0/0/12528",
        "name": "Puffer Ladezustand",
        "icon": "mdi:battery-charging-60",
        "device_class": None,
        "state_class": SensorStateClass.MEASUREMENT,
        "default_unit": "%",
    },
    "heizkreis_vorlauf": {
        "component": "hk1",
        "uri": "/120/10101/0/11060/0",
        "name": "Heizkreis Vorlauftemperatur",
        "icon": "mdi:thermometer",
        "device_class": SensorDeviceClass.TEMPERATURE,
        "state_class": SensorStateClass.MEASUREMENT,
        "default_unit": "°C",
    },
    "heizkreis_anforderung": {
        "component": "hk1",
        "uri": "/120/10101/0/11124/2001",
        "name": "Heizkreis Anforderung",
        "icon": "mdi:heat-wave",
        "is_string": True,
    },
    "fwm_warmwasser": {
        "component": "fwm",
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
        "component": "puffer",
        "position": position,
        "icon": "mdi:thermometer-lines",
        "device_class": SensorDeviceClass.TEMPERATURE,
        "state_class": SensorStateClass.MEASUREMENT,
        "default_unit": "°C",
    }


DISCOVERY_ONLY_SENSORS = {
    "heizkreis2_vorlauf": {
        "component": "hk2",
        "name": "Heizkreis 2 Vorlauftemperatur",
        "icon": "mdi:thermometer",
        "device_class": SensorDeviceClass.TEMPERATURE,
        "state_class": SensorStateClass.MEASUREMENT,
        "default_unit": "°C",
    },
    "heizkreis2_anforderung": {
        "component": "hk2",
        "name": "Heizkreis 2 Anforderung",
        "icon": "mdi:heat-wave",
        "is_string": True,
    },
}

OPTIONAL_SENSORS = {
    "fwm_zirkulation": {
        "component": "fwm",
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

def normalize_components(components):
    """Bringt eine Komponentenauswahl in eine gültige, feste Reihenfolge.

    Der Kessel ist nicht abwählbar, und die Reihenfolge bestimmt später die
    Anordnung der Kacheln im Dashboard - deshalb wird hier nicht die
    Eingabereihenfolge des Nutzers übernommen, sondern die aus COMPONENTS.
    """
    gewaehlt = set(components or [])
    gewaehlt |= {key for key, info in COMPONENTS.items() if info.get("required")}
    return [key for key in COMPONENTS if key in gewaehlt]


def components_from_config(config):
    """Ermittelt die Komponenten eines Config Entry.

    Einträge, die vor der Umstellung auf Komponenten angelegt wurden,
    tragen noch ein festes Anlagenschema - das wird hier übersetzt.
    """
    if config.get(CONF_COMPONENTS):
        return normalize_components(config[CONF_COMPONENTS])
    schema = config.get(CONF_SCHEMA)
    if schema in LEGACY_SCHEMA_COMPONENTS:
        return normalize_components(LEGACY_SCHEMA_COMPONENTS[schema])
    return normalize_components(DEFAULT_COMPONENTS)


def fub_roles_for_components(components):
    """Alle Funktionsblock-Rollen, die für diese Komponenten gebraucht werden."""
    rollen = []
    for key in normalize_components(components):
        for rolle in COMPONENTS[key]["roles"]:
            if rolle not in rollen:
                rollen.append(rolle)
    return rollen


def fub_role_default(role, roles_in_schema):
    """Liefert den sinnvollsten Standardnamen für ein Formularfeld.

    Bei zwei Heizkreisen heißt der erste laut ETA-Konvention "HK1" statt
    "HK" - das wird hier als Vorbelegung berücksichtigt.
    """
    if role == "hk" and "hk2" in roles_in_schema:
        return "HK1"
    return FUB_ROLE_DEFAULT_NAMES[role][0]
