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
4. **Kreuze an, welche Komponenten deine Anlage hat** (Pufferspeicher, Frischwassermodul/Warmwasser, Heizkreis 1, Heizkreis 2). Der Kessel steht nicht zur Wahl - den hat jede Anlage.
5. Klicke auf **Weiter**. Die Integration prüft die Verbindung.
6. Im zweiten Schritt siehst du ein Formular **"Funktionsblock-Namen bestätigen"** - je nach angekreuzten Komponenten mit Feldern für die an deiner Anlage relevanten Funktionsblöcke (FUB), z. B. "Kessel", "PufferFlex", "HK1", "HK2", "FWM". Diese sind bereits mit den ETA-Standardnamen vorausgefüllt. **Falls du einen FUB an deiner Steuerung umbenannt hast** (z. B. "Kessel" in "Holzvergaser"), trage hier den tatsächlichen Namen ein - sonst kann die Integration die zugehörigen Werte nicht finden.
7. Klicke auf **Absenden**. Die Komponentengrafiken werden automatisch auf deiner Festplatte abgelegt.

Host, Port, **Abfrageintervall**, die Komponenten und die FUB-Namen lassen sich später jederzeit über **Einstellungen -> Geräte & Dienste -> ETA Heiztechnik Web Service -> Konfigurieren** ändern, ohne die Integration neu einrichten zu müssen.

> 💡 Das **Abfrageintervall** legt fest, wie oft die Anlage ausgelesen wird (Standard 30 Sekunden, erlaubt sind 10 bis 600). Alle Werte werden pro Zyklus parallel geholt, die Steuerung wird dabei aber bewusst nur mit wenigen gleichzeitigen Anfragen belastet.

---

## 📊 Unterstützte Sensoren

Alle Entitäten werden einem gemeinsamen Gerät ("ETA Heizung") zugeordnet und (sofern physisch an deiner Anlage angeschlossen bzw. per Menübaum gefunden) automatisch ausgelesen:

* **🔥 Kessel & Umgebung:** Kesseltemperatur, Kessel-Solltemperatur, Rücklauftemperatur, Kesseldruck (bar), Restsauerstoff (%), Außentemperatur, Inhalt Pellet-Tagesbehälter (kg).
* **🗑️ Aschebox:** Verbrauch seit letzter Leerung (kg) und der eingestellte Schwellwert, ab dem geleert werden soll (kg), jeweils als eigener Sensor - plus ein dritter, kombinierter Sensor `sensor.eta_heizung_aschebox_status` mit dem Format "459/1000kg" für die Dashboard-Anzeige.
* **🛢️ Pufferspeicher:** Puffer-Ladezustand (%), sowie **alle tatsächlich vorhandenen Pufferfühler** (PufferFlex hat je nach Anlage zwischen 3 und 8 Fühlern). Die Integration erkennt die tatsächliche Anzahl automatisch über den Menübaum; Fühler 1 hat zusätzlich das Attribut `position: oben`, der zuletzt nummerierte `position: unten`.
* **♨️ Heizkreis 1:** Vorlauftemperatur, Anforderung (Zustandstext wie *Aus*, *Heizbetrieb* etc.).
* **♨️ Heizkreis 2** (nur bei Schema *2x Heizkreis*, sofern ein FUB "HK2" gefunden wird): Vorlauftemperatur, Anforderung.
* **🚰 Frischwasser-/Warmwassermodul (FWM oder WW):** Warmwassertemperatur, sowie Zirkulationstemperatur. Der Zirkulations-Sensor existiert immer und zeigt "-", falls die Anlage keinen entsprechenden Fühler hat.

### Funktionsblöcke wurden umbenannt?

Alle Funktionsblöcke (FUB) können am Gerät selbst umbenannt werden - dann heißen sie auch in den Webservices anders, und die automatische Erkennung findet sie nicht mehr über ihren Standardnamen. Deshalb fragt die Integration beim Einrichten (und in den Optionen) für jeden relevanten FUB den tatsächlichen Namen ab. ETA-Standardnamen zum Vergleich:

| Rolle | Standardname(n) |
|---|---|
| Kessel | `Kessel` |
| Pufferspeicher | `PufferFlex` (ältere Anlagen ohne Flex-Funktion: `Puffer`) |
| Frischwasser-/Warmwassermodul | `FWM`, oder `WW` bei einem reinen Warmwasserspeicher |
| Heizkreis 1 | `HK`, oder `HK1` sobald mehrere Heizkreise vorhanden sind |
| Heizkreis 2 | `HK2` |
| Außentemperatur | `Sys` |

---

## 📺 Dashboard-Vorlage für Lovelace

Es gibt **eine** Karte für alle Anlagen. Sie zeigt automatisch genau die Komponenten an, die du im Setup ausgewählt hast - fehlende Komponenten werden ausgeblendet, und die übrigen rücken nach.

Erstelle eine neue Karte vom Typ **Manuell** (oben rechts auf Code-Editor umschalten) und füge den YAML-Code ein. Es ist **nichts zu löschen und nichts anzupassen**.

<details>
<summary><b>Wie das funktioniert</b> (aufklappen)</summary>

Die Karte ist ein `grid` mit vier Spalten. Jede Komponente ist eine eigene `picture-elements`-Karte, eingepackt in eine `conditional`-Karte, die auf eine Marker-Entität prüft (`sensor.eta_heizung_komponente_*`). Diese Marker legt die Integration nur für die Komponenten an, die du ausgewählt hast.

Blendet `conditional` eine Karte aus, setzt Home Assistant `display: none` - die Karte fällt aus dem Grid-Layout, und die verbleibenden Komponenten rutschen nach links. Weil das Grid feste Spalten hat, bleibt jede Komponente dabei gleich groß.

Die Beschriftungen stecken **nicht** in den Grafiken, sondern kommen aus `prefix` der `state-label`-Elemente. Deshalb genügen vier Grafiken statt einer für jede mögliche Kombination - und du kannst jede Beschriftung im YAML frei ändern.

> ⚠️ `picture-elements` kennt nur diese Elementtypen: `conditional`, `icon`, `image`, `service-button` (alias `action-button`), `state-badge`, `state-icon`, `state-label`. Ein `type: markdown` gibt es **nicht** - eine frühere Version dieser README hat das fälschlich verwendet, was zu "Konfigurationsfehler: Unknown type encountered" führte.

</details>

```yaml
type: grid
columns: 4
square: false
cards:
  - type: conditional
    conditions:
      - condition: state
        entity: sensor.eta_heizung_komponente_kessel
        state: kessel
    card:
      type: picture-elements
      image: /local/community/ha-eta-webservices/kessel.png
      elements:
        - type: state-label
          entity: sensor.eta_heizung_aussentemperatur
          prefix: "Außen: "
          style: {top: 4%, left: 6%, transform: "translate(0, -50%)", color: "#9aa5b1", font-size: 105%}
        - type: state-label
          entity: sensor.eta_heizung_kesseltemperatur
          prefix: "Kessel: "
          style: {top: 12%, left: 6%, transform: "translate(0, -50%)", color: "#e8615f", font-size: 105%}
        - type: state-label
          entity: sensor.eta_heizung_kessel_solltemperatur
          prefix: "Soll: "
          style: {top: 19%, left: 6%, transform: "translate(0, -50%)", color: "#e2867f", font-size: 105%}
        - type: state-label
          entity: sensor.eta_heizung_rucklauftemperatur
          prefix: "Rücklauf: "
          style: {top: 26%, left: 6%, transform: "translate(0, -50%)", color: "#7b88e0", font-size: 105%}
        - type: state-label
          entity: sensor.eta_heizung_kesseldruck
          prefix: "Druck: "
          style: {top: 33%, left: 6%, transform: "translate(0, -50%)", color: "#d3a15a", font-size: 105%}
        - type: state-label
          entity: sensor.eta_heizung_pellet_inhalt_tagesbehalter
          prefix: "Behälter: "
          style: {top: 40%, left: 6%, transform: "translate(0, -50%)", color: "#5fbfa8", font-size: 105%}
        - type: state-label
          entity: sensor.eta_heizung_aschebox_status
          prefix: "Aschebox: "
          style: {top: 47%, left: 6%, transform: "translate(0, -50%)", color: "#a98fd0", font-size: 105%}
        - type: state-label
          entity: sensor.eta_heizung_restsauerstoff
          prefix: "Restsauerstoff: "
          style: {top: 54%, left: 6%, transform: "translate(0, -50%)", color: "#d89a6a", font-size: 105%}

  - type: conditional
    conditions:
      - condition: state
        entity: sensor.eta_heizung_komponente_pufferspeicher
        state: puffer
    card:
      type: picture-elements
      image: /local/community/ha-eta-webservices/puffer.png
      elements:
        - type: state-label
          entity: sensor.eta_heizung_puffer_ladezustand
          prefix: "Ladezustand: "
          style: {top: 12%, left: 50%, color: "#d5d9de", font-size: 110%}
        - type: state-label
          entity: sensor.eta_heizung_puffer_fuhler_1
          style: {top: 36%, left: 50%, color: "#ffffff", font-size: 115%}
        - type: state-label
          entity: sensor.eta_heizung_puffer_fuhler_2
          style: {top: 62%, left: 50%, color: "#ffffff", font-size: 115%}
        - type: state-label
          entity: sensor.eta_heizung_puffer_fuhler_3
          style: {top: 88%, left: 50%, color: "#ffffff", font-size: 115%}

  - type: conditional
    conditions:
      - condition: state
        entity: sensor.eta_heizung_komponente_fwm
        state: fwm
    card:
      type: picture-elements
      image: /local/community/ha-eta-webservices/fwm.png
      elements:
        - type: state-label
          entity: sensor.eta_heizung_fwm_warmwassertemperatur
          prefix: "Warmwasser: "
          style: {top: 12%, left: 50%, color: "#d5d9de", font-size: 110%}
        - type: state-label
          entity: sensor.eta_heizung_fwm_zirkulation
          prefix: "Zirkulation: "
          style: {top: 19%, left: 50%, color: "#9aa5b1", font-size: 100%}

  - type: conditional
    conditions:
      - condition: state
        entity: sensor.eta_heizung_komponente_heizkreis_1
        state: hk1
    card:
      type: picture-elements
      image: /local/community/ha-eta-webservices/heizkreis.png
      elements:
        - type: state-label
          entity: sensor.eta_heizung_heizkreis_vorlauftemperatur
          prefix: "Vorlauf HK1: "
          style: {top: 12%, left: 50%, color: "#e8615f", font-size: 105%}
        - type: state-label
          entity: sensor.eta_heizung_heizkreis_anforderung
          prefix: "HK1: "
          style: {top: 19%, left: 50%, color: "#d5d9de", font-size: 100%}

  - type: conditional
    conditions:
      - condition: state
        entity: sensor.eta_heizung_komponente_heizkreis_2
        state: hk2
    card:
      type: picture-elements
      image: /local/community/ha-eta-webservices/heizkreis.png
      elements:
        - type: state-label
          entity: sensor.eta_heizung_heizkreis_2_vorlauftemperatur
          prefix: "Vorlauf HK2: "
          style: {top: 12%, left: 50%, color: "#e8615f", font-size: 105%}
        - type: state-label
          entity: sensor.eta_heizung_heizkreis_2_anforderung
          prefix: "HK2: "
          style: {top: 19%, left: 50%, color: "#d5d9de", font-size: 100%}
```

### Mehr als drei Pufferfühler

Die Karte oben zeigt drei Fühler. Hat deine Anlage mehr (PufferFlex kann bis zu 8), ergänze im Puffer-Block weitere Zeilen und verteile die `top`-Werte gleichmäßig zwischen 36 % und 88 %:

```yaml
        - type: state-label
          entity: sensor.eta_heizung_puffer_fuhler_4
          style: {top: 75%, left: 50%, color: "#ffffff", font-size: 115%}
```

Wie viele du hast, steht unter **Entwicklerwerkzeuge -> Zustände** (`sensor.eta_heizung_puffer_fuhler_`). Fühler 1 ist immer oben, der letzte immer unten - beide tragen das Attribut `position` mit `oben` bzw. `unten`.

### Beschriftungen ändern

Jede Beschriftung steht als `prefix` im YAML, nicht im Bild. Aus

```yaml
          prefix: "Kessel: "
```

wird also einfach

```yaml
          prefix: "Vorlauf Kessel: "
```

Mit `suffix` lässt sich zusätzlich etwas hinter den Wert setzen.

> 💡 `top`/`left` verankern in Lovelace die **Mitte** des Elements. Die linksbündigen Beschriftungen im Kessel-Block nutzen deshalb `transform: "translate(0, -50%)"`. Alle Werte lassen sich im visuellen Editor per Drag & Drop feinjustieren.

---


## 🩺 Wenn ein Wert fehlt

Die Integration findet die Werte über die **Namen** im Menübaum deiner Anlage, nicht über feste Adressen. Fehlt ein Wert, liegt das fast immer daran, dass ein Funktionsblock umbenannt wurde oder die Hardware an deiner Anlage nicht verbaut ist.

Unter **Einstellungen -> Geräte & Dienste -> ETA Heiztechnik Web Service -> Gerät "ETA Heizung" -> Diagnose herunterladen** bekommst du eine Datei, die für jeden Messwert zeigt:

* ob seine Adresse im Menübaum **gefunden** wurde (`"quelle": "menuebaum"`) oder auf den Standardwert zurückgefallen ist (`"quelle": "standard"`),
* welche Adresse tatsächlich abgefragt wird,
* welcher Wert zuletzt angekommen ist,
* und unter `"nicht_gefunden"` eine Liste aller Werte ohne Treffer.

Die IP-Adresse ist in dieser Datei geschwärzt, du kannst sie also bedenkenlos an ein [Issue](https://github.com/dorsch95/ha-eta-webservices/issues) anhängen.

---

## 🧪 Entwicklung

Die Testsuite läuft gegen ein echtes Home Assistant, aber ohne laufende Instanz und ohne echte Heizung - die Anlage wird durch einen aufgezeichneten Menübaum ersetzt:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements_test.txt
pytest
```

Dieselben Tests laufen zusammen mit `hassfest` und der HACS-Validierung bei jedem Push automatisch in GitHub Actions.

---

## 📄 Lizenz

Dieses Projekt ist unter der MIT-Lizenz lizenziert – siehe die [LICENSE](LICENSE) Datei für Details.
