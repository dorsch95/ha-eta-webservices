DOMAIN = "eta_webservices"
DEFAULT_PORT = 8080

# Die exakten Datenpunkt-URIs mit angehängtem /2002 für den echten Istwert
TRACKED_URIs = {
    "kessel_temperatur": {
        "uri": "/264/10891/0/11109/2002", 
        "name": "ETA Kesseltemperatur",
        "icon": "mdi:thermometer"
    },
    "aussentemperatur": {
        "uri": "/120/10241/0/11127/2002", 
        "name": "ETA Außentemperatur",
        "icon": "mdi:thermometer"
    },
    "puffer_fühler_1": {
        "uri": "/120/10601/0/11327/2002", 
        "name": "ETA Puffer Fühler 1 (oben)",
        "icon": "mdi:thermometer-lines"
    },
    "puffer_fühler_2": {
        "uri": "/120/10601/0/11328/2002", 
        "name": "ETA Puffer Fühler 2",
        "icon": "mdi:thermometer-lines"
    },
    "puffer_fühler_3": {
        "uri": "/120/10601/0/11329/2002", 
        "name": "ETA Puffer Fühler 3",
        "icon": "mdi:thermometer-lines"
    },
    "puffer_fühler_4": {
        "uri": "/120/10601/0/11330/2002", 
        "name": "ETA Puffer Fühler 4",
        "icon": "mdi:thermometer-lines"
    },
    "puffer_fühler_5": {
        "uri": "/120/10601/0/11331/2002", 
        "name": "ETA Puffer Fühler 5 (unten)",
        "icon": "mdi:thermometer-lines"
    }
}
