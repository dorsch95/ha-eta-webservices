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

# Deine exakten, festen Wunsch-Pfade ohne fehleranfälliges Suchen
STATIC_URIs = {
    # --- KESSEL & UMGEBUNG ---
    "kessel_temperatur": {
        "uri": "/264/10891/0/11109/0",
        "name": "ETA Kesseltemperatur",
        "icon": "mdi:thermometer"
    },
    "ruecklauf_temperatur": {
        "uri": "/264/10891/0/11160/0",
        "name": "ETA Rücklauftemperatur",
        "icon": "mdi:thermometer"
    },
    "kessel_druck": {
        "uri": "/264/10891/0/0/12180",
        "name": "ETA Kesseldruck",
        "icon": "mdi:gauge"
    },
    "pellet_tagesbehälter": {
        "uri": "/264/10891/0/0/12011",
        "name": "ETA Pellet Inhalt Tagesbehälter",
        "icon": "mdi:weight-kilogram"
    },
    "aussentemperatur": {
        "uri": "/120/10241/0/11127/0",
        "name": "ETA Außentemperatur",
        "icon": "mdi:thermometer"
    },

    # --- PUFFERSPEICHER ---
    "puffer_ladezustand": {
        "uri": "/120/10601/0/0/12528",
        "name": "ETA Puffer Ladezustand",
        "icon": "mdi:battery-charging-60"
    },
    "puffer_fuehler_1": {
        "uri": "/120/10601/0/11327/0",
        "name": "ETA Puffer Fühler 1 (oben)",
        "icon": "mdi:thermometer-lines"
    },
    "puffer_fuehler_2": {
        "uri": "/120/10601/0/11328/0",
        "name": "ETA Puffer Fühler 2",
        "icon": "mdi:thermometer-lines"
    },
    "puffer_fuehler_3": {
        "uri": "/120/10601/0/11329/0",
        "name": "ETA Puffer Fühler 3",
        "icon": "mdi:thermometer-lines"
    },
    "puffer_fuehler_4": {
        "uri": "/120/10601/0/11330/0",
        "name": "ETA Puffer Fühler 4",
        "icon": "mdi:thermometer-lines"
    },
    "puffer_fuehler_5": {
        "uri": "/120/10601/0/11331/0",
        "name": "ETA Puffer Fühler 5",
        "icon": "mdi:thermometer-lines"
    },

    # --- HEIZKREIS ---
    "heizkreis_vorlauf": {
        "uri": "/120/10101/0/11060/0",
        "name": "ETA Heizkreis Vorlauftemperatur",
        "icon": "mdi:thermometer"
    },
    "heizkreis_anforderung": {
        "uri": "/120/10101/0/11124/2001",
        "name": "ETA Heizkreis Anforderung",
        "icon": "mdi:heat-wave"
    },

    # --- FRISCHWASSERMODUL ---
    "fwm_warmwasser": {
        "uri": "/79/10531/0/11148/0",
        "name": "ETA FWM Warmwassertemperatur",
        "icon": "mdi:water-thermometer"
    }
}
