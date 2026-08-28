DOMAIN = "eta_webservices"
DEFAULT_PORT = 8080

# Hier trägst du deine ETA-Sensor-Pfade ein (findest du unter http://<ETA-IP>:8080/user/menu)
TRACKED_URIs = {
    "kessel_temperatur": {
        "uri": "/40/10021/0/0/12001", 
        "name": "ETA Kesseltemperatur",
        "icon": "mdi:thermometer"
    },
    "kessel_status": {
        "uri": "/40/10021/0/0/12080", 
        "name": "ETA Kesselstatus",
        "icon": "mdi:fire"
    }
}
