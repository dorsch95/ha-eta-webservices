# ETA Heiztechnik Web Service Integration für Home Assistant

[![hacs_badge](https://shields.io)](https://github.com)
[![License: MIT](https://shields.io)](LICENSE)

Diese benutzerdefinierte Home Assistant Integration ermöglicht es, Daten von **ETA Heizsystemen** (Pelletkessel, Stückholzkessel, Hackgut, Puffer- und Solarspeicher sowie Frischwassermodule) lokal über die integrierten RESTful Webservices (ETAtouch) auszulesen.

✨ **Highlight:** Die Integration verfügt über eine **vollautomatische Erkennung (Autodiscovery)**. Sie scannt beim Start das Menü deiner Heizung und erstellt exakt nur die Sensoren, die an deiner Anlage auch wirklich physisch verbaut und angeschlossen sind!

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
4. Klicke auf **Absenden**. Die Integration prüft die Verbindung, scannt das Menü und erstellt automatisch deine Geräte-Struktur.

---

## 📊 Automatisch erkannte Sensoren

Je nach Ausstattung deiner ETA-Heizung werden folgende Entitäten automatisch ermittelt und angelegt:

* **🔥 Kessel & Umgebung:** Kesseltemperatur, Rücklauftemperatur, Kesseldruck, Außentemperatur, Inhalt Pellet-Tagesbehälter (kg).
* **🛢️ Pufferspeicher:** Puffer-Ladezustand (%), Fühler 1 (oben), Fühler 2, Fühler 3 (unten), sowie optional Fühler 4 und Fühler 5.
* **♨️ Heizkreis:** Vorlauftemperatur, Anforderung (Status).
* **🚰 Frischwassermodul (FWM):** Warmwassertemperatur.

---

## 📺 Dashboard-Vorlagen für Lovelace

Du kannst die Daten auf deinem Dashboard entweder als übersichtliche Tabelle oder optisch als Bild-Elemente darstellen.

### Option A: Die Tabellen-Ansicht (Empfohlen & am einfachsten)
Erstellt eine saubere, strukturierte Listenansicht aller Werte. Kopiere diesen Code in ein leeres "Manuell"-Dashboard-Element:

```yaml
type: grid
cards:
  - type: entities
    title: 🔥 Kessel & Werte
    entities:
      - entity: sensor.eta_kesseltemperatur
      - entity: sensor.eta_rucklauftemperatur
      - entity: sensor.eta_kesseldruck
      - entity: sensor.eta_pellet_inhalt_tagesbehalter
      - entity: sensor.eta_aussentemperatur
  - type: entities
    title: 🛢️ Pufferspeicher
    entities:
      - entity: sensor.eta_puffer_ladezustand
      - entity: sensor.eta_puffer_fuhler_1_oben
      - entity: sensor.eta_puffer_fuhler_2
      - entity: sensor.eta_puffer_fuhler_3
      - entity: sensor.eta_puffer_fuhler_4
      - entity: sensor.eta_puffer_fuhler_5
  - type: entities
    title: 🚰 Heizkreis & Warmwasser
    entities:
      - entity: sensor.eta_heizkreis_vorlauftemperatur
      - entity: sensor.eta_heizkreis_anforderung
      - entity: sensor.eta_fwm_warmwassertemperatur
columns: 1
square: false
```

### Option B: Die Bild-Modul-Ansicht (Für Kiosk-Tablets)
Wenn du transparente Hintergrundbilder für deine Komponenten nutzt (z.B. im Format 1000x500px im Ordner `www/` hinterlegt), kannst du die Werte pixelgenau auf den Grafiken platzieren:

```yaml
type: vertical-stack
cards:
  # Kessel-Modul
  - type: picture-elements
    image: /local/community/eta_webservices/kessel.png
    elements:
      - type: state-label
        entity: sensor.eta_kesseltemperatur
        style:
          top: 50%
          left: 50%
          font-weight: bold
  # Puffer-Modul
  - type: picture-elements
    image: /local/community/eta_webservices/puffer.png
    elements:
      - type: state-label
        entity: sensor.eta_puffer_fuhler_1_oben
        style: top: 20%; left: 50%;
      - type: state-label
        entity: sensor.eta_puffer_fuhler_3
        style: top: 50%; left: 50%;
      - type: state-label
        entity: sensor.eta_puffer_fuhler_5
        style: top: 80%; left: 50%;
```

---

## 📄 Lizenz

Dieses Projekt ist unter der MIT-Lizenz lizenziert – siehe die [LICENSE](LICENSE) Datei für Details.
