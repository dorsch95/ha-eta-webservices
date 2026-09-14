from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import Platform

DOMAIN = "eta_webservices"
DEFAULT_PORT = 8080

PLATFORMS = [Platform.SENSOR, Platform.SWITCH]

CONF_SCHEMA = "schema"
CONF_COMPONENTS = "components"
CONF_PELLET_KWH_PER_KG = "pellet_kwh_per_kg"
CONF_ENABLE_SWITCHES = "enable_switches"
CONF_ENABLE_ERRORS = "enable_errors"

DEFAULT_ENABLE_SWITCHES = False
"""Schalter sind standardmäßig aus.

Sie schreiben in die Heizungssteuerung. Wer das will, soll es bewusst
einschalten - nicht durch ein Update dazu kommen.
"""

DEFAULT_ENABLE_ERRORS = True
CONF_FUB_NAMES = "fub_names"
CONF_SCAN_INTERVAL = "scan_interval"

DEFAULT_PELLET_KWH_PER_KG = 4.8
MIN_PELLET_KWH_PER_KG = 3.0
MAX_PELLET_KWH_PER_KG = 6.0
"""Heizwert von Holzpellets.

ENplus-A1-Pellets liegen je nach Restfeuchte zwischen etwa 4,6 und 5,0
kWh/kg; 4,8 ist der übliche Richtwert. Weil das je nach Lieferung schwankt,
lässt sich der Wert in den Optionen anpassen.
"""

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
        "discovery_prefixes": ["kessel_", "aussentemperatur"],
        "required": True,
    },
    "puffer": {
        "name": "Pufferspeicher",
        "image": "puffer",
        "roles": ["pufferflex"],
        "discovery_prefixes": ["puffer_"],
    },
    "fwm": {
        "name": "FWM",
        "image": "fwm",
        "roles": ["fwm"],
        "discovery_prefixes": ["fwm_warmwasser"],
    },
    "hk1": {
        "name": "Heizkreis 1",
        "image": "heizkreis",
        "roles": ["hk"],
        "discovery_prefixes": ["heizkreis_"],
    },
    "hk2": {
        "name": "Heizkreis 2",
        "image": "heizkreis",
        "roles": ["hk2"],
        "discovery_prefixes": ["heizkreis2_"],
    },
}
"""Die wählbaren Bausteine einer Anlage.

Jede Komponente bringt ihre eigene Grafik, ihre Funktionsblock-Rollen und
ihre Messwerte mit. Neue Komponenten (z.B. Solar) werden hier ergänzt und
bei den Sensoren über das Feld "component" zugeordnet - es gibt bewusst
keine Tabelle fertiger Anlagenschemata mehr, sonst bräuchte jede
Kombination aus n Komponenten einen eigenen Eintrag und ein eigenes Bild.
"""

DEFAULT_COMPONENTS = ["kessel", "puffer"]

SWITCHES = {
    "kessel_schalter": {
        "component": "kessel",
        "translation_key": "kessel_schalter",
        "icon": "mdi:power",
    },
    "heizkreis_schalter": {
        "component": "hk1",
        "translation_key": "heizkreis_schalter",
        "icon": "mdi:radiator",
    },
    "heizkreis2_schalter": {
        "component": "hk2",
        "translation_key": "heizkreis2_schalter",
        "icon": "mdi:radiator",
    },
}
"""Schaltbare Funktionen, je Komponente eine.

Welche Zustände geschaltet werden, steht nicht hier: Die Rohwerte
kommen aus /user/varinfo, direkt von der Anlage. Nur so lässt sich
ausschließen, dass ein falscher Wert in die Steuerung geschrieben wird.
"""

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
        "translation_key": "kessel_temperatur",
        "icon": "mdi:thermometer",
        "device_class": SensorDeviceClass.TEMPERATURE,
        "state_class": SensorStateClass.MEASUREMENT,
        "default_unit": "°C",
    },
    "ruecklauf_temperatur": {
        "component": "kessel",
        "uri": "/264/10891/0/11160/0",
        "name": "Rücklauftemperatur",
        "translation_key": "ruecklauf_temperatur",
        "icon": "mdi:thermometer",
        "device_class": SensorDeviceClass.TEMPERATURE,
        "state_class": SensorStateClass.MEASUREMENT,
        "default_unit": "°C",
    },
    "kessel_druck": {
        "component": "kessel",
        "uri": "/264/10891/0/0/12180",
        "name": "Kesseldruck",
        "translation_key": "kessel_druck",
        "icon": "mdi:gauge",
        "device_class": SensorDeviceClass.PRESSURE,
        "state_class": SensorStateClass.MEASUREMENT,
        "default_unit": "bar",
    },
    "pellet_tagesbehälter": {
        "component": "kessel",
        "uri": "/264/10891/0/0/12011",
        "name": "Pellet Inhalt Tagesbehälter",
        "translation_key": "pellet_tagesbehaelter",
        "icon": "mdi:weight-kilogram",
        "device_class": SensorDeviceClass.WEIGHT,
        "state_class": SensorStateClass.MEASUREMENT,
        "default_unit": "kg",
    },
    "aussentemperatur": {
        "component": "kessel",
        "uri": "/120/10241/0/11127/0",
        "name": "Außentemperatur",
        "translation_key": "aussentemperatur",
        "icon": "mdi:thermometer",
        "device_class": SensorDeviceClass.TEMPERATURE,
        "state_class": SensorStateClass.MEASUREMENT,
        "default_unit": "°C",
    },
    "kessel_soll": {
        "component": "kessel",
        "uri": "/264/10891/0/0/13953",
        "name": "Kessel Solltemperatur",
        "translation_key": "kessel_soll",
        "icon": "mdi:thermostat",
        "device_class": SensorDeviceClass.TEMPERATURE,
        "state_class": SensorStateClass.MEASUREMENT,
        "default_unit": "°C",
    },
    "restsauerstoff": {
        "component": "kessel",
        "uri": "/264/10891/0/11108/2060",
        "name": "Restsauerstoff",
        "translation_key": "restsauerstoff",
        "icon": "mdi:percent",
        "device_class": None,
        "state_class": SensorStateClass.MEASUREMENT,
        "default_unit": "%",
    },
    "aschebox_verbrauch": {
        "component": "kessel",
        "uri": "/264/10891/0/0/12013",
        "name": "Aschebox Verbrauch seit Leerung",
        "translation_key": "aschebox_verbrauch",
        "icon": "mdi:trash-can",
        "device_class": SensorDeviceClass.WEIGHT,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "default_unit": "kg",
    },
    "entaschung_verbrauch": {
        "component": "kessel",
        "uri": "/264/10891/0/0/12012",
        "name": "Verbrauch seit Entaschung",
        "translation_key": "entaschung_verbrauch",
        "icon": "mdi:fire",
        "device_class": SensorDeviceClass.WEIGHT,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "default_unit": "kg",
    },
    "aschebox_schwelle": {
        "component": "kessel",
        "uri": "/264/10891/0/0/12120",
        "name": "Aschebox Leeren nach",
        "translation_key": "aschebox_schwelle",
        "icon": "mdi:trash-can-outline",
        "device_class": SensorDeviceClass.WEIGHT,
        "state_class": SensorStateClass.MEASUREMENT,
        "default_unit": "kg",
    },
    "puffer_ladezustand": {
        "component": "puffer",
        "uri": "/120/10601/0/0/12528",
        "name": "Puffer Ladezustand",
        "translation_key": "puffer_ladezustand",
        "icon": "mdi:battery-charging-60",
        "device_class": None,
        "state_class": SensorStateClass.MEASUREMENT,
        "default_unit": "%",
    },
    "heizkreis_vorlauf": {
        "component": "hk1",
        "uri": "/120/10101/0/11060/0",
        "name": "Heizkreis Vorlauftemperatur",
        "translation_key": "heizkreis_vorlauf",
        "icon": "mdi:thermometer",
        "device_class": SensorDeviceClass.TEMPERATURE,
        "state_class": SensorStateClass.MEASUREMENT,
        "default_unit": "°C",
    },
    "heizkreis_anforderung": {
        "component": "hk1",
        "uri": "/120/10101/0/11124/2001",
        "name": "Heizkreis Anforderung",
        "translation_key": "heizkreis_anforderung",
        "icon": "mdi:heat-wave",
        "is_string": True,
    },
    "fwm_warmwasser": {
        "component": "fwm",
        "uri": "/79/10531/0/11148/0",
        "name": "FWM Warmwassertemperatur",
        "translation_key": "fwm_warmwasser",
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
        "translation_key": f"puffer_fuehler_{index}",
        "component": "puffer",
        "position": position,
        "icon": "mdi:thermometer-lines",
        "device_class": SensorDeviceClass.TEMPERATURE,
        "state_class": SensorStateClass.MEASUREMENT,
        "default_unit": "°C",
    }


DISCOVERY_ONLY_SENSORS = {
    "kessel_zustand": {
        "component": "kessel",
        "name": "Kessel Zustand",
        "translation_key": "kessel_zustand",
        "icon": "mdi:fire",
        "is_string": True,
    },
    "heizkreis2_vorlauf": {
        "component": "hk2",
        "name": "Heizkreis 2 Vorlauftemperatur",
        "translation_key": "heizkreis2_vorlauf",
        "icon": "mdi:thermometer",
        "device_class": SensorDeviceClass.TEMPERATURE,
        "state_class": SensorStateClass.MEASUREMENT,
        "default_unit": "°C",
    },
    "heizkreis2_anforderung": {
        "component": "hk2",
        "name": "Heizkreis 2 Anforderung",
        "translation_key": "heizkreis2_anforderung",
        "icon": "mdi:heat-wave",
        "is_string": True,
    },
}

OPTIONAL_SENSORS = {
    "fwm_zirkulation": {
        "component": "fwm",
        "name": "FWM Zirkulation",
        "translation_key": "fwm_zirkulation",
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
