"""Feste Tabellen der Integration.

Hier steht, welche Komponenten es gibt und welche Entitäten je Komponente
entstehen - Name, Einheit, Geräteklasse und Übersetzungsschlüssel. Was
sich von Anlage zu Anlage unterscheidet, steht bewusst nicht hier: Die
zugehörigen ETA-Objekt-URIs ermittelt uri_discovery zur Laufzeit aus dem
Menübaum.
"""

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import Platform

DOMAIN = "eta_webservices"
DEFAULT_PORT = 8080

URL_GRAFIKEN = f"/{DOMAIN}/grafiken"
"""Unter dieser Adresse liefert Home Assistant die Kachelgrafiken aus.

Die Dateien liegen im Ordner grafiken/ der Integration und kommen mit
jedem Update mit. Je Komponente genau eine Kachel (255x501); die
Beschriftungen stecken bewusst nicht im Bild, sondern kommen in der
Dashboard-Karte aus state-label-Elementen - sonst bräuchte jede Sprache
und jeder Heizkreis eine eigene Grafik.
"""

PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]

CONF_SCHEMA = "schema"
CONF_COMPONENTS = "components"
CONF_PELLET_KWH_PER_KG = "pellet_kwh_per_kg"
CONF_ENABLE_SWITCHES = "enable_switches"
CONF_ENABLE_ERRORS = "enable_errors"

DEFAULT_ENABLE_SWITCHES = False
"""Schalter schreiben in die Steuerung und sind deshalb standardmäßig aus."""

DEFAULT_ENABLE_ERRORS = True
CONF_FUB_NAMES = "fub_names"
CONF_SCAN_INTERVAL = "scan_interval"

DEFAULT_PELLET_KWH_PER_KG = 4.8
MIN_PELLET_KWH_PER_KG = 3.0
MAX_PELLET_KWH_PER_KG = 6.0
"""Heizwert von Holzpellets in kWh/kg.

ENplus A1 liegt je nach Restfeuchte zwischen etwa 4,6 und 5,0; 4,8 ist der
übliche Richtwert. In den Optionen an die eigene Lieferung anpassbar.
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
    "hk3": {
        "name": "Heizkreis 3",
        "image": "heizkreis",
        "roles": ["hk3"],
        "discovery_prefixes": ["heizkreis3_"],
    },
    "hk4": {
        "name": "Heizkreis 4",
        "image": "heizkreis",
        "roles": ["hk4"],
        "discovery_prefixes": ["heizkreis4_"],
    },
    "lager": {
        "name": "Pelletlager",
        "image": "lager",
        "roles": ["lager"],
        "discovery_prefixes": ["lager_"],
    },
    "solar": {
        "name": "Solar",
        "image": "solar",
        "roles": ["solar"],
        "discovery_prefixes": ["solar_"],
    },
}
"""Die wählbaren Bausteine einer Anlage.

Jede Komponente bringt Grafik, Funktionsblock-Rollen und Messwerte mit.
Sensoren ordnen sich über ihr Feld "component" hier zu.
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
        "nur_fuer_auswahl": True,
    },
    "heizkreis2_schalter": {
        "component": "hk2",
        "translation_key": "heizkreis2_schalter",
        "icon": "mdi:radiator",
        "nur_fuer_auswahl": True,
    },
    "heizkreis3_schalter": {
        "component": "hk3",
        "translation_key": "heizkreis3_schalter",
        "icon": "mdi:radiator",
        "nur_fuer_auswahl": True,
    },
    "heizkreis4_schalter": {
        "component": "hk4",
        "translation_key": "heizkreis4_schalter",
        "icon": "mdi:radiator",
        "nur_fuer_auswahl": True,
    },
}
"""Schaltbare Funktionen, je Komponente eine.

Die zu schreibenden Rohwerte stehen nicht hier, sondern kommen aus
/user/varinfo.

"nur_fuer_auswahl" markiert die Ein/Aus-Tasten der Heizkreise. Sie werden
gesucht und geprüft, ergeben aber keinen eigenen Schalter: Am Heizkreis
gibt es vier Betriebsarten, von denen immer genau eine gilt, und "Aus"
ist eine davon. Ein zusätzlicher Ein/Aus-Schalter daneben wäre ein
zweiter Bedienweg für dieselbe Sache. Die Auswahl braucht die Taste
trotzdem - sie schaltet damit auf "Aus".
"""

BETRIEBSART_TASTEN = {
    "automatik": "Auto Taste",
    "heizen": "Heizen Taste",
    "absenken": "Absenken Taste",
}
"""Die drei Tasten, die zusammen die Betriebsart eines Heizkreises ergeben.

Sie verhalten sich wie Radioknöpfe: Läuft der Heizkreis, steht genau eine
auf "Ein"; ist er aus, stehen alle drei auf "Aus".
"""

BETRIEBSART_AUS = "aus"
"""Der vierte Eintrag der Auswahl, der keiner eigenen Taste entspricht."""

SELECTS = {
    "heizkreis_betriebsart": {
        "component": "hk1",
        "role": "hk",
        "schalter": "heizkreis_schalter",
        "translation_key": "heizkreis_betriebsart",
        "icon": "mdi:home-thermometer",
    },
    "heizkreis2_betriebsart": {
        "component": "hk2",
        "role": "hk2",
        "schalter": "heizkreis2_schalter",
        "translation_key": "heizkreis2_betriebsart",
        "icon": "mdi:home-thermometer",
    },
    "heizkreis3_betriebsart": {
        "component": "hk3",
        "role": "hk3",
        "schalter": "heizkreis3_schalter",
        "translation_key": "heizkreis3_betriebsart",
        "icon": "mdi:home-thermometer",
    },
    "heizkreis4_betriebsart": {
        "component": "hk4",
        "role": "hk4",
        "schalter": "heizkreis4_schalter",
        "translation_key": "heizkreis4_betriebsart",
        "icon": "mdi:home-thermometer",
    },
}
"""Je Heizkreis eine Auswahl der Betriebsart."""

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

SENSORS = {
    "kessel_temperatur": {
        "component": "kessel",
        "name": "Kesseltemperatur",
        "translation_key": "kessel_temperatur",
        "icon": "mdi:thermometer",
        "device_class": SensorDeviceClass.TEMPERATURE,
        "state_class": SensorStateClass.MEASUREMENT,
        "default_unit": "°C",
    },
    "ruecklauf_temperatur": {
        "component": "kessel",
        "name": "Rücklauftemperatur",
        "translation_key": "ruecklauf_temperatur",
        "icon": "mdi:thermometer",
        "device_class": SensorDeviceClass.TEMPERATURE,
        "state_class": SensorStateClass.MEASUREMENT,
        "default_unit": "°C",
    },
    "kessel_druck": {
        "component": "kessel",
        "name": "Kesseldruck",
        "translation_key": "kessel_druck",
        "icon": "mdi:gauge",
        "device_class": SensorDeviceClass.PRESSURE,
        "state_class": SensorStateClass.MEASUREMENT,
        "default_unit": "bar",
    },
    "pellet_tagesbehälter": {
        "component": "kessel",
        "name": "Pellet Inhalt Tagesbehälter",
        "translation_key": "pellet_tagesbehaelter",
        "icon": "mdi:weight-kilogram",
        "device_class": SensorDeviceClass.WEIGHT,
        "state_class": SensorStateClass.MEASUREMENT,
        "default_unit": "kg",
    },
    "aussentemperatur": {
        "component": "kessel",
        "name": "Außentemperatur",
        "translation_key": "aussentemperatur",
        "icon": "mdi:thermometer",
        "device_class": SensorDeviceClass.TEMPERATURE,
        "state_class": SensorStateClass.MEASUREMENT,
        "default_unit": "°C",
    },
    "kessel_soll": {
        "component": "kessel",
        "name": "Kessel Solltemperatur",
        "translation_key": "kessel_soll",
        "icon": "mdi:thermostat",
        "device_class": SensorDeviceClass.TEMPERATURE,
        "state_class": SensorStateClass.MEASUREMENT,
        "default_unit": "°C",
    },
    "restsauerstoff": {
        "component": "kessel",
        "name": "Restsauerstoff",
        "translation_key": "restsauerstoff",
        "icon": "mdi:percent",
        "device_class": None,
        "state_class": SensorStateClass.MEASUREMENT,
        "default_unit": "%",
    },
    "pellet_gesamtverbrauch": {
        "component": "kessel",
        "name": "Pellet Gesamtverbrauch",
        "translation_key": "pellet_gesamtverbrauch",
        "icon": "mdi:counter",
        "device_class": SensorDeviceClass.WEIGHT,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "default_unit": "kg",
    },
    "aschebox_verbrauch": {
        "component": "kessel",
        "name": "Aschebox Verbrauch seit Leerung",
        "translation_key": "aschebox_verbrauch",
        "icon": "mdi:trash-can",
        "device_class": SensorDeviceClass.WEIGHT,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "default_unit": "kg",
    },
    "entaschung_verbrauch": {
        "component": "kessel",
        "name": "Verbrauch seit Entaschung",
        "translation_key": "entaschung_verbrauch",
        "icon": "mdi:fire",
        "device_class": SensorDeviceClass.WEIGHT,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "default_unit": "kg",
    },
    "aschebox_schwelle": {
        "component": "kessel",
        "name": "Aschebox Leeren nach",
        "translation_key": "aschebox_schwelle",
        "icon": "mdi:trash-can-outline",
        "device_class": SensorDeviceClass.WEIGHT,
        "state_class": SensorStateClass.MEASUREMENT,
        "default_unit": "kg",
    },
    "puffer_ladezustand": {
        "component": "puffer",
        "name": "Puffer Ladezustand",
        "translation_key": "puffer_ladezustand",
        "icon": "mdi:battery-charging-60",
        "device_class": None,
        "state_class": SensorStateClass.MEASUREMENT,
        "default_unit": "%",
    },
    "heizkreis_vorlauf": {
        "component": "hk1",
        "name": "Heizkreis Vorlauftemperatur",
        "translation_key": "heizkreis_vorlauf",
        "icon": "mdi:thermometer",
        "device_class": SensorDeviceClass.TEMPERATURE,
        "state_class": SensorStateClass.MEASUREMENT,
        "default_unit": "°C",
    },
    "heizkreis_anforderung": {
        "component": "hk1",
        "name": "Heizkreis Anforderung",
        "translation_key": "heizkreis_anforderung",
        "icon": "mdi:heat-wave",
        "is_string": True,
    },
    "fwm_warmwasser": {
        "component": "fwm",
        "name": "FWM Warmwassertemperatur",
        "translation_key": "fwm_warmwasser",
        "icon": "mdi:water-thermometer",
        "device_class": SensorDeviceClass.TEMPERATURE,
        "state_class": SensorStateClass.MEASUREMENT,
        "default_unit": "°C",
    },
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
    "heizkreis3_vorlauf": {
        "component": "hk3",
        "name": "Heizkreis 3 Vorlauftemperatur",
        "translation_key": "heizkreis3_vorlauf",
        "icon": "mdi:thermometer",
        "device_class": SensorDeviceClass.TEMPERATURE,
        "state_class": SensorStateClass.MEASUREMENT,
        "default_unit": "°C",
    },
    "heizkreis3_anforderung": {
        "component": "hk3",
        "name": "Heizkreis 3 Anforderung",
        "translation_key": "heizkreis3_anforderung",
        "icon": "mdi:heat-wave",
        "is_string": True,
    },
    "heizkreis4_vorlauf": {
        "component": "hk4",
        "name": "Heizkreis 4 Vorlauftemperatur",
        "translation_key": "heizkreis4_vorlauf",
        "icon": "mdi:thermometer",
        "device_class": SensorDeviceClass.TEMPERATURE,
        "state_class": SensorStateClass.MEASUREMENT,
        "default_unit": "°C",
    },
    "heizkreis4_anforderung": {
        "component": "hk4",
        "name": "Heizkreis 4 Anforderung",
        "translation_key": "heizkreis4_anforderung",
        "icon": "mdi:heat-wave",
        "is_string": True,
    },
    "lager_vorrat": {
        "component": "lager",
        "name": "Lager Vorrat",
        "translation_key": "lager_vorrat",
        "icon": "mdi:silo",
        "device_class": SensorDeviceClass.WEIGHT,
        "state_class": SensorStateClass.MEASUREMENT,
        "default_unit": "kg",
    },
    "lager_warngrenze": {
        "component": "lager",
        "name": "Lager Warngrenze",
        "translation_key": "lager_warngrenze",
        "icon": "mdi:alert-outline",
        "device_class": SensorDeviceClass.WEIGHT,
        "state_class": SensorStateClass.MEASUREMENT,
        "default_unit": "kg",
    },
    "lager_maximum": {
        "component": "lager",
        "name": "Lager Fassungsvermögen",
        "translation_key": "lager_maximum",
        "icon": "mdi:silo-outline",
        "device_class": SensorDeviceClass.WEIGHT,
        "state_class": SensorStateClass.MEASUREMENT,
        "default_unit": "kg",
    },
    "lager_zustand": {
        "component": "lager",
        "name": "Lager Austragung",
        "translation_key": "lager_zustand",
        "icon": "mdi:screw-lag",
        "is_string": True,
    },
    "solar_kollektor": {
        "component": "solar",
        "name": "Solar Kollektortemperatur",
        "translation_key": "solar_kollektor",
        "icon": "mdi:solar-panel-large",
        "device_class": SensorDeviceClass.TEMPERATURE,
        "state_class": SensorStateClass.MEASUREMENT,
        "default_unit": "°C",
    },
    "solar_leistung": {
        "component": "solar",
        "name": "Solar Leistung",
        "translation_key": "solar_leistung",
        "icon": "mdi:flash",
        "device_class": SensorDeviceClass.POWER,
        "state_class": SensorStateClass.MEASUREMENT,
        "default_unit": "kW",
    },
    "solar_waermemenge": {
        "component": "solar",
        "name": "Solar Wärmemenge",
        "translation_key": "solar_waermemenge",
        "icon": "mdi:sun-thermometer",
        "device_class": SensorDeviceClass.ENERGY,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "default_unit": "kWh",
    },
    "solar_ertrag_heute": {
        "component": "solar",
        "name": "Solar Ertrag heute",
        "translation_key": "solar_ertrag_heute",
        "icon": "mdi:weather-sunny",
        "device_class": SensorDeviceClass.ENERGY,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "default_unit": "kWh",
    },
    "solar_ertrag_gestern": {
        "component": "solar",
        "name": "Solar Ertrag gestern",
        "translation_key": "solar_ertrag_gestern",
        "icon": "mdi:weather-sunset-down",
        "device_class": SensorDeviceClass.ENERGY,
        "default_unit": "kWh",
    },
    "fwm_zirkulationspumpe": {
        "component": "fwm",
        "name": "FWM Zirkulationspumpe",
        "translation_key": "fwm_zirkulationspumpe",
        "icon": "mdi:pump",
        "is_string": True,
    },
}

PUFFER_FUEHLER_MAX = 9
"""Mehr Fühler kennt PufferFlex nicht."""

PUFFER_FUEHLER_MINDEST = 3
"""So viele Fühler bekommt ein Puffer, wenn der Menübaum keine nennt.

PufferFlex hat immer mindestens drei (oben, Mitte, unten).
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


FUB_ROLE_DEFAULT_NAMES = {
    "kessel": ["Kessel"],
    "sys": ["Sys"],
    "pufferflex": ["PufferFlex", "Puffer"],
    "fwm": ["FWM", "WW"],
    "hk": ["HK", "HK1"],
    "hk2": ["HK2"],
    "hk3": ["HK3"],
    "hk4": ["HK4"],
    "lager": ["Lager"],
    "solar": ["Solar"],
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
