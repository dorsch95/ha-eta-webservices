# ETA Heiztechnik Web Service Integration für Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Diese benutzerdefinierte Integration ermöglicht es, Daten von **ETA Heizsystemen** (Pelletkessel, Stückholzkessel, Hackgut, Puffer- und Solarspeicher sowie Frischwassermodule) komplett lokal über die integrierten RESTful Webservices (ETAtouch) auszulesen.

⚡ Das Anlagenschema wird direkt im UI-Setup ausgewählt und die passenden Grafiken werden vollautomatisch im Hintergrund generiert.

🔎 Die internen ETA-Objekt-URIs (z. B. `/264/10891/0/11109/0`) unterscheiden sich von Anlage zu Anlage. Beim Einrichten ruft die Integration deshalb einmalig den Menübaum der Anlage (`/user/menu`) ab und ermittelt die passenden URIs automatisch anhand ihrer **Bezeichnungen** (z. B. "Kessel → Eingänge → Rücklauf"), die im Gegensatz zu den Zahlen-IDs stabil bleiben. Eine manuelle Eingabe von URIs ist damit nicht nötig. Sollte ein Messwert an einer Anlage abweichend benannt sein, wird automatisch auf eine hinterlegte Standard-URI zurückgefallen.

---

## ⚙️ Vorbereitung am ETA-Kessel

Damit Home Assistant auf die Daten zugreifen kann, müssen die Webservices auf der Steuerung deiner Heizung aktiviert werden:

1. Registriere deinen Kessel (falls noch nicht geschehen) auf dem Portal [meinETA](https://meineta.at).
2. Gehe am Touch-Display deiner Heizung auf **Einstellungen** -> **Webservices**.
3. Schalte dort den **LAN-Zugriff** frei.
4. Gehe zu **Systemeinstellungen** -> **meinETA Zugang** und activiere die **Webservices**.
5. Die API der Heizung ist nun lokal unter `http://<DEINE-ETA-IP>:8080/user/var` erreichbar.

---

## 🚀 Installation via HACS

Da es sich um eine benutzerdefinierte Integration handelt, fügst du sie wie folgt in HACS hinzu:

1. Navigiere in Home Assistant zu **HACS** -> **Integrationen**.
2. Klicke oben rechts auf die drei Punkte (`...`) und wähle **Benutzerdefinierte Repositories** (Custom Repositories).
3. Füge die URL dieses GitHub-Repositories ein:
   `https://github.com/dorsch95/ha-eta-webservices`
4. Wähle als Kategorie **Integration** und klicke auf **Hinzufügen**.
5. Suche nach **ETA Heiztechnik Web Service** und klicke auf **Herunterladen**.
6. **Wichtig:** Starte Home Assistant nach dem Download vollständig neu!

---

## 🛠️ Einrichtung in Home Assistant

Nach dem Neustart kannst du die Integration direkt über die Benutzeroberfläche einrichten:

1. Gehe zu **Einstellungen** -> **Geräte & Dienste** -> **Integration hinzufügen**.
2. Suche nach **ETA Heiztechnik Web Service**.
3. Gib die **IP-Adresse** deiner ETA-Heizung ein (Port ist standardmäßig `8080`).
4. Wähle im **Dropdown-Menü dein passendes Anlagenschema** aus (z. B. *Kessel + Puffer + 1x Heizkreis + FWM*).
5. Klicke auf **Absenden**. Die Integration prüft die Verbindung und generiert die passenden Hintergrundbilder vollautomatisch auf deiner Festplatte.

Host, Port und Anlagenschema lassen sich später jederzeit über **Einstellungen -> Geräte & Dienste -> ETA Heiztechnik Web Service -> Konfigurieren** ändern, ohne die Integration neu einrichten zu müssen.

---

## 📊 Unterstützte Sensoren

Alle Entitäten werden einem gemeinsamen Gerät ("ETA Heizung") zugeordnet und (sofern physisch an deiner Anlage angeschlossen bzw. per Menübaum gefunden) automatisch ausgelesen:

* **🔥 Kessel & Umgebung:** Kesseltemperatur, Rücklauftemperatur, Kesseldruck (bar), Außentemperatur, Inhalt Pellet-Tagesbehälter (kg).
* **🛢️ Pufferspeicher:** Puffer-Ladezustand (%), sowie **alle tatsächlich vorhandenen Pufferfühler** (PufferFlex hat je nach Anlage zwischen 3 und 8 Fühlern). Fühler 1 ist immer der oberste, der zuletzt nummerierte immer der unterste - die Integration erkennt die tatsächliche Anzahl automatisch über den Menübaum und benennt sie entsprechend ("Fühler 1 (oben)" ... "Fühler N (unten)").
* **♨️ Heizkreis:** Vorlauftemperatur, Anforderung (Zustandstext wie *Aus*, *Heizbetrieb* etc.).
* **🚰 Frischwassermodul (FWM):** Warmwassertemperatur.

> Ein zweiter Heizkreis (HK2), Kessel-Solltemperatur, Aschebox und Restsauerstoff sind auf den Anlagengrafiken bereits als Beschriftungsfelder vorgesehen, werden aber aktuell noch nicht als Sensor ausgelesen (siehe Dashboard-Vorlagen unten).

---

## 📺 Dashboard-Vorlage für Lovelace (Bild-Elemente)

Durch die automatische Base64-Bildgenerierung musst du keine Grafiken mehr manuell auf deinen Server kopieren. Jede Anlagengrafik hat die Messwert-Beschriftungen (z. B. "Kessel:", "Ladezustand:", "Vorlauf HK1:") bereits fest eingebrannt – es fehlt nur noch der Wert daneben. Die folgenden Karten wurden anhand einer pixelgenauen Analyse der jeweiligen Grafik erstellt, damit die Werte exakt neben ihrer Beschriftung erscheinen.

Wähle unten die Karte passend zu deinem im Setup gewählten Anlagenschema, erstelle eine neue Karte vom Typ **Manuell** (Umschalten auf Code-Editor) und füge den YAML-Code ein.

> ℹ️ Für **Kessel Soll**, **Aschebox**, **Restsauerstoff** sowie **Heizkreis 2** sind auf den Grafiken bereits Beschriftungsfelder vorgesehen, es gibt dafür aber noch keine passenden Sensoren in der Integration (siehe `# TODO`-Kommentare in den Karten unten). Die einzelnen Puffer-Fühler (1–5) sowie die Außentemperatur haben keine eigene Beschriftung auf den Grafiken und werden daher hier nicht platziert – sie stehen aber weiterhin als normale Sensoren zur Verfügung und können z. B. in einer separaten Entities-Karte angezeigt werden.

### Kessel

```yaml
type: picture-elements
image: /local/community/ha-eta-webservices/kessel.png
elements:
  - type: state-label
    entity: sensor.eta_kesseltemperatur
    style:
      top: 5.5%
      left: 11%
      font-weight: bold
      font-size: 16px
  - type: state-label
    entity: sensor.eta_rucklauftemperatur
    style:
      top: 19.9%
      left: 14%
      font-weight: bold
      font-size: 16px
  - type: state-label
    entity: sensor.eta_kesseldruck
    style:
      top: 27.5%
      left: 19%
      font-weight: bold
      font-size: 16px
  - type: state-label
    entity: sensor.eta_pellet_inhalt_tagesbehalter
    style:
      top: 34.7%
      left: 19%
      font-weight: bold
      font-size: 16px
```

### Kessel + Puffer

```yaml
type: picture-elements
image: /local/community/ha-eta-webservices/kessel_puffer.png
elements:
  - type: state-label
    entity: sensor.eta_kesseltemperatur
    style:
      top: 5.5%
      left: 11%
      font-weight: bold
      font-size: 16px
  - type: state-label
    entity: sensor.eta_rucklauftemperatur
    style:
      top: 19.9%
      left: 14%
      font-weight: bold
      font-size: 16px
  - type: state-label
    entity: sensor.eta_kesseldruck
    style:
      top: 27.5%
      left: 19%
      font-weight: bold
      font-size: 16px
  - type: state-label
    entity: sensor.eta_pellet_inhalt_tagesbehalter
    style:
      top: 34.7%
      left: 19%
      font-weight: bold
      font-size: 16px
  - type: state-label
    entity: sensor.eta_puffer_ladezustand
    style:
      top: 12.7%
      left: 45%
      font-weight: bold
      font-size: 16px
```

### Kessel + Puffer + 1x Heizkreis

```yaml
type: picture-elements
image: /local/community/ha-eta-webservices/kessel_puffer_hk1.png
elements:
  - type: state-label
    entity: sensor.eta_kesseltemperatur
    style:
      top: 5.5%
      left: 11%
      font-weight: bold
      font-size: 16px
  - type: state-label
    entity: sensor.eta_rucklauftemperatur
    style:
      top: 19.9%
      left: 14%
      font-weight: bold
      font-size: 16px
  - type: state-label
    entity: sensor.eta_kesseldruck
    style:
      top: 27.5%
      left: 19%
      font-weight: bold
      font-size: 16px
  - type: state-label
    entity: sensor.eta_pellet_inhalt_tagesbehalter
    style:
      top: 34.7%
      left: 19%
      font-weight: bold
      font-size: 16px
  - type: state-label
    entity: sensor.eta_puffer_ladezustand
    style:
      top: 12.7%
      left: 45%
      font-weight: bold
      font-size: 16px
  - type: state-label
    entity: sensor.eta_heizkreis_vorlauftemperatur
    style:
      top: 12.7%
      left: 67%
      font-weight: bold
      font-size: 16px
  - type: state-label
    entity: sensor.eta_heizkreis_anforderung
    style:
      top: 20.4%
      left: 72%
      font-weight: bold
      font-size: 16px
```

### Kessel + Puffer + FWM

```yaml
type: picture-elements
image: /local/community/ha-eta-webservices/kessel_puffer_fwm.png
elements:
  - type: state-label
    entity: sensor.eta_kesseltemperatur
    style:
      top: 5.5%
      left: 11%
      font-weight: bold
      font-size: 16px
  - type: state-label
    entity: sensor.eta_rucklauftemperatur
    style:
      top: 19.9%
      left: 14%
      font-weight: bold
      font-size: 16px
  - type: state-label
    entity: sensor.eta_kesseldruck
    style:
      top: 27.5%
      left: 19%
      font-weight: bold
      font-size: 16px
  - type: state-label
    entity: sensor.eta_pellet_inhalt_tagesbehalter
    style:
      top: 34.7%
      left: 19%
      font-weight: bold
      font-size: 16px
  - type: state-label
    entity: sensor.eta_puffer_ladezustand
    style:
      top: 12.7%
      left: 45%
      font-weight: bold
      font-size: 16px
  - type: state-label
    entity: sensor.eta_fwm_warmwassertemperatur
    style:
      top: 12.7%
      left: 65%
      font-weight: bold
      font-size: 16px
```

### Kessel + Puffer + 1x Heizkreis + FWM

```yaml
type: picture-elements
image: /local/community/ha-eta-webservices/kessel_puffer_hk1_fwm.png
elements:
  - type: state-label
    entity: sensor.eta_kesseltemperatur
    style:
      top: 5.5%
      left: 11%
      font-weight: bold
      font-size: 16px
  - type: state-label
    entity: sensor.eta_rucklauftemperatur
    style:
      top: 19.9%
      left: 14%
      font-weight: bold
      font-size: 16px
  - type: state-label
    entity: sensor.eta_kesseldruck
    style:
      top: 27.5%
      left: 19%
      font-weight: bold
      font-size: 16px
  - type: state-label
    entity: sensor.eta_pellet_inhalt_tagesbehalter
    style:
      top: 34.7%
      left: 19%
      font-weight: bold
      font-size: 16px
  - type: state-label
    entity: sensor.eta_puffer_ladezustand
    style:
      top: 12.7%
      left: 45%
      font-weight: bold
      font-size: 16px
  - type: state-label
    entity: sensor.eta_fwm_warmwassertemperatur
    style:
      top: 12.7%
      left: 65%
      font-weight: bold
      font-size: 16px
  - type: state-label
    entity: sensor.eta_heizkreis_vorlauftemperatur
    style:
      top: 12.7%
      left: 86%
      font-weight: bold
      font-size: 14px
  - type: state-label
    entity: sensor.eta_heizkreis_anforderung
    style:
      top: 20.4%
      left: 90%
      font-weight: bold
      font-size: 14px
```

### Kessel + Puffer + 2x Heizkreis

```yaml
type: picture-elements
image: /local/community/ha-eta-webservices/kessel_puffer_hk2.png
elements:
  - type: state-label
    entity: sensor.eta_kesseltemperatur
    style:
      top: 5.5%
      left: 11%
      font-weight: bold
      font-size: 16px
  - type: state-label
    entity: sensor.eta_rucklauftemperatur
    style:
      top: 19.9%
      left: 14%
      font-weight: bold
      font-size: 16px
  - type: state-label
    entity: sensor.eta_kesseldruck
    style:
      top: 27.5%
      left: 19%
      font-weight: bold
      font-size: 16px
  - type: state-label
    entity: sensor.eta_pellet_inhalt_tagesbehalter
    style:
      top: 34.7%
      left: 19%
      font-weight: bold
      font-size: 16px
  - type: state-label
    entity: sensor.eta_puffer_ladezustand
    style:
      top: 12.7%
      left: 45%
      font-weight: bold
      font-size: 16px
  - type: state-label
    entity: sensor.eta_heizkreis_vorlauftemperatur
    style:
      top: 12.7%
      left: 67%
      font-weight: bold
      font-size: 16px
  - type: state-label
    entity: sensor.eta_heizkreis_anforderung
    style:
      top: 20.4%
      left: 72%
      font-weight: bold
      font-size: 16px
  # TODO: "Vorlauf HK2" (top: 27.0%, left: 67%) - noch kein Sensor für einen 2. Heizkreis vorhanden
  # TODO: "Anforderung HK2" (top: 34.7%, left: 72%) - noch kein Sensor für einen 2. Heizkreis vorhanden
```

### Kessel + Puffer + 2x Heizkreis + FWM

```yaml
type: picture-elements
image: /local/community/ha-eta-webservices/kessel_puffer_hk2_fwm.png
elements:
  - type: state-label
    entity: sensor.eta_kesseltemperatur
    style:
      top: 5.5%
      left: 11%
      font-weight: bold
      font-size: 16px
  - type: state-label
    entity: sensor.eta_rucklauftemperatur
    style:
      top: 19.9%
      left: 14%
      font-weight: bold
      font-size: 16px
  - type: state-label
    entity: sensor.eta_kesseldruck
    style:
      top: 27.5%
      left: 19%
      font-weight: bold
      font-size: 16px
  - type: state-label
    entity: sensor.eta_pellet_inhalt_tagesbehalter
    style:
      top: 34.7%
      left: 19%
      font-weight: bold
      font-size: 16px
  - type: state-label
    entity: sensor.eta_puffer_ladezustand
    style:
      top: 12.7%
      left: 45%
      font-weight: bold
      font-size: 16px
  - type: state-label
    entity: sensor.eta_fwm_warmwassertemperatur
    style:
      top: 12.7%
      left: 65%
      font-weight: bold
      font-size: 16px
  - type: state-label
    entity: sensor.eta_heizkreis_vorlauftemperatur
    style:
      top: 12.7%
      left: 86%
      font-weight: bold
      font-size: 14px
  - type: state-label
    entity: sensor.eta_heizkreis_anforderung
    style:
      top: 20.4%
      left: 90%
      font-weight: bold
      font-size: 14px
  # TODO: "Vorlauf HK2" (top: 27.0%, left: 86%) - noch kein Sensor für einen 2. Heizkreis vorhanden
  # TODO: "Anforderung HK2" (top: 34.7%, left: 90%) - noch kein Sensor für einen 2. Heizkreis vorhanden
```

> 💡 `top`/`left` verankern in Lovelace standardmäßig die **Mitte** des Elements. Solltest du eine andere Home-Assistant-Theme, Bildschirmgröße oder Kartenbreite verwenden, kannst du die Werte im visuellen Editor per Drag & Drop feinjustieren.

---

## 📄 Lizenz

Dieses Projekt ist unter der MIT-Lizenz lizenziert – siehe die [LICENSE](LICENSE) Datei für Details.
