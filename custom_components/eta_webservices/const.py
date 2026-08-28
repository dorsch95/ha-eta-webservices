DOMAIN = "eta_webservices"
DEFAULT_PORT = 8080

# Exakte Definitionen basierend auf deiner Kessel- und Pufferkonfiguration
# Der Code sucht nach dem 'search_name' im XML-Menü der Heizung
SENSOR_DEFINITIONS = {
    # --- KESSEL & UMGEBUNG ---
    "kessel_temperatur": {
        "search_name": "Kessel",
        "friendly_name": "ETA Kesseltemperatur",
        "icon": "mdi:thermometer"
    },
    "ruecklauf_temperatur": {
        "search_name": "Rücklauf",
        "friendly_name": "ETA Rücklauftemperatur",
        "icon": "mdi:thermometer"
    },
    "kessel_druck": {
        "search_name": "Kesseldruck",
        "friendly_name": "ETA Kesseldruck",
        "icon": "mdi:gauge"
    },
    "pellet_tagesbehälter": {
        "search_name": "Inhalt Pelletsbehälter",
        "friendly_name": "ETA Pellet Inhalt Tagesbehälter",
        "icon": "mdi:weight-kilogram"
    },
    "aussentemperatur": {
        "search_name": "Außentemperaturfühler",
        "friendly_name": "ETA Außentemperatur",
        "icon": "mdi:thermometer"
    },

    # --- PUFFERSPEICHER ---
    "puffer_ladezustand": {
        "search_name": "Ladezustand",
        "friendly_name": "ETA Puffer Ladezustand",
        "icon": "mdi:battery-charging-60"
    },
    "puffer_fuehler_1": {
        "search_name": "Fühler 1 (oben)",
        "friendly_name": "ETA Puffer Fühler 1 (oben)",
        "icon": "mdi:thermometer-lines"
    },
    "puffer_fuehler_2": {
        "search_name": "Fühler 2",
        "friendly_name": "ETA Puffer Fühler 2",
        "icon": "mdi:thermometer-lines"
    },
    "puffer_fuehler_3": {
        "search_name": "Fühler 3",
        "friendly_name": "ETA Puffer Fühler 3",
        "icon": "mdi:thermometer-lines"
    },
    "puffer_fuehler_4": {
        "search_name": "Fühler 4",
        "friendly_name": "ETA Puffer Fühler 4",
        "icon": "mdi:thermometer-lines"
    },
    "puffer_fuehler_5": {
        "search_name": "Fühler 5",
        "friendly_name": "ETA Puffer Fühler 5",
        "icon": "mdi:thermometer-lines"
    },

    # --- HEIZKREIS ---
    "heizkreis_vorlauf": {
        "search_name": "Vorlauf",
        "friendly_name": "ETA Heizkreis Vorlauftemperatur",
        "icon": "mdi:thermometer"
    },
    "heizkreis_anforderung": {
        "search_name": "Anforderung",
        "friendly_name": "ETA Heizkreis Anforderung",
        "icon": "mdi:heat-wave"
    },

    # --- FRISCHWASSERMODUL ---
    "fwm_warmwasser": {
        "search_name": "Warmwasser",
        "friendly_name": "ETA FWM Warmwassertemperatur",
        "icon": "mdi:water-thermometer"
    },

    # --- WARMWASSERSPEICHER (Platzhalter) ---
    "wws_temperatur_platzhalter": {
        "search_name": "Warmwasserspeicher_Platzhalter",
        "friendly_name": "ETA WWS Temperatur (Bereit)",
        "icon": "mdi:water-boiler"
    }
}
