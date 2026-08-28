# ETA Heiztechnik Web Service Integration für Home Assistant

[![hacs_badge](https://shields.io)](https://github.com)
[![License: MIT](https://shields.io)](LICENSE)

Diese benutzerdefinierte Home Assistant Integration ermöglicht es, Daten von **ETA Heizsystemen** (Pelletkessel, Stückholzkessel, Hackgut, Puffer- und Solarspeicher) lokal über die integrierten RESTful Webservices (ETAtouch) auszulesen.

⚠️ **Hinweis:** Diese Integration kommuniziert komplett lokal in deinem Netzwerk und benötigt keine aktive Internetverbindung zu meinETA, sobald die Freischaltung erfolgt ist.

---

## ⚙️ Vorbereitung am ETA-Kessel

Damit Home Assistant auf die Daten zugreifen kann, müssen die Webservices auf der Steuerung deiner Heizung aktiviert werden:

1. Registriere deinen Kessel (falls noch nicht geschehen) auf dem Portal [meinETA](https://meineta.at).
2. Gehe am Touch-Display deiner Heizung auf **Einstellungen** -> **Webservices**.
3. Schalte dort den **LAN-Zugriff** frei.
4. Gehe zu **Systemeinstellungen** -> **meinETA Zugang** und aktiviere die **Webservices**.
5. Die API der Heizung ist nun lokal unter `http://<DEINE-ETA-IP>:8080/user/var` erreichbar.

---

## 🚀 Installation via HACS

Da es sich um eine benutzerdefinierte Integration handelt, kannst du sie ganz einfach in HACS hinzufügen:

1. Navigiere in Home Assistant zu **HACS** -> **Integrationen**.
2. Klicke oben rechts auf die drei Punkte (`...`) und wähle **Benutzerdefinierte Repositories** (Custom Repositories).
3. Füge die URL dieses GitHub-Repositories ein:
   `https://github.com`
4. Wähle als Kategorie **Integration** und klicke auf **Hinzufügen**.
5. Suche nach **ETA Heiztechnik Web Service** und klicke auf **Herunterladen**.
6. **Wichtig:** Starte Home Assistant nach dem Download neu!

---

## 🛠️ Einrichtung in Home Assistant

Nach dem Neustart kannst du die Integration direkt über die Benutzeroberfläche einrichten:

1. Gehe zu **Einstellungen** -> **Geräte & Dienste** -> **Integration hinzufügen**.
2. Suche nach **ETA Heiztechnik Web Service**.
3. Gib die **IP-Adresse** deiner ETA-Heizung ein (Port ist standardmäßig `8080`).
4. Klicke auf **Absenden**. Die Integration prüft die Verbindung und erstellt automatisch die Sensoren.

---

## 📊 Standardmäßig unterstützte Sensoren

In der Grundkonfiguration liest die Integration folgende Werte aus:
* 🌡️ **Kesseltemperatur** (`°C`)
* 🔥 **Kesselstatus** (Zustandstext wie *Bereit*, *Heizen*, *Zünden* etc.)

### Weitere Sensoren hinzufügen
Jede ETA-Heizung hat je nach Ausstattung (Puffer, Solar, Heizkreise) unterschiedliche Datenpfade (URIs). Du kannst ganz einfach eigene Sensoren hinzufügen:

1. Rufe im Browser `http://<DEINE-ETA-IP>:8080/user/menu` auf, um die XML-Struktur deiner Heizung zu sehen.
2. Suche nach dem gewünschten Sensor und kopiere das Attribut `uri` (z. B. `/40/10021/0/0/12011`).
3. Öffne die Datei `custom_components/eta_webservices/const.py` in deinem Home Assistant Verzeichnis und erweitere das `TRACKED_URIs`-Verzeichnis nach folgendem Muster:

```python
"mein_neuer_sensor": {
    "uri": "/dein/kopierter/pfad", 
    "name": "ETA Wunschsensor Name",
    "icon": "mdi:water"
}
```

---

## 📺 VNC-Bildschirm einbinden (Bonus)

Da ETA-Heizungen auch per VNC erreichbar sind, kannst du das Live-Display deiner Heizung direkt in dein Home Assistant Dashboard einbetten:

1. Installiere das Add-on **Apache Guacamole** oder **NoVNC** in Home Assistant.
2. Trage dort die IP-Adresse deiner Heizung ein (VNC nutzt standardmäßig Port `5900`, meist ohne Passwort).
3. Füge eine **Webseiten-Karte (Iframe)** zu deinem Lovelace-Dashboard hinzu und verlinke auf das Add-on.

---

## 📄 Lizenz

Dieses Projekt ist unter der MIT-Lizenz lizenziert – siehe die [LICENSE](LICENSE) Datei für Details.
