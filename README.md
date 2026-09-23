# ETA Web-Services für Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Diese Integration liest **ETA Heizsysteme** komplett lokal über die integrierten RESTful Webservices (ETAtouch) aus - Pellet-, Stückholz- und Hackgutkessel samt Pufferspeicher, Frischwassermodul, Heizkreisen, Solaranlage und Pelletlager. Es geht nichts ins Internet.

Standardmäßig wird nur gelesen. Kessel und Heizkreise lassen sich auf Wunsch auch schalten; das muss beim Einrichten ausdrücklich freigegeben werden.

⚡ Du kreuzt im Setup an, welche Komponenten deine Anlage hat. Die Grafiken bringt die Integration selbst mit, und eine einzige Dashboard-Karte deckt alle Anlagen ab.

📈 Bei Pelletkesseln steht der Verbrauch als Energiewert bereit und lässt sich ins **Energie-Dashboard** von Home Assistant aufnehmen.

🔎 **Keine URIs von Hand.** Die internen ETA-Adressen (z. B. `/264/10891/0/11109/0`) unterscheiden sich von Anlage zu Anlage. Die Integration liest deshalb beim Einrichten einmalig den Menübaum (`/user/menu`) und sucht die Werte über ihre **Bezeichnungen** ("Kessel → Eingänge → Rücklauf"), die stabil bleiben. Im Code steht **keine einzige vollständige Adresse** - eine von einer fremden Anlage wäre geraten und könnte still den falschen Wert anzeigen. Passt ein Name nicht, sucht die Integration bei Messwerten innerhalb des richtigen Funktionsblocks noch nach der Nummer des Objekts: den hinteren drei Zahlen der Adresse, die bei jeder Anlage gleich sind.

> ℹ️ Benötigt Home Assistant **2025.8** oder neuer.

<details>
<summary>🇬🇧 <b>English summary</b></summary>

**ETA Web-Services** reads ETA heating systems (pellet, wood chip and log boilers with buffer tank, fresh water module, heating circuits, solar and pellet store) **entirely locally** via the ETAtouch RESTful webservices built into the boiler. Nothing goes to the internet. Read-only by default; switching the boiler and heating circuit modes has to be enabled explicitly.

- Install via HACS, restart, then **Settings → Devices & services → Add integration → ETA Web-Services**. Enter the boiler's IP address (port 8080) and tick the components your system has.
- Values are found by their **names** in the boiler's menu tree, not by fixed addresses. The search uses the German menu names, which is what practically all systems in Germany, Austria and Switzerland report. If a name doesn't match, measured values are also found by the object's number inside its function block - so with a different display language, enter your function block names as your display shows them. Buttons and switches are only found by name.
- Entity IDs are the same in every Home Assistant language (e.g. `sensor.eta_heizung_kesseltemperatur`), so the dashboard card below works everywhere. Display names are translated.
- The ready-made dashboard card: **Developer tools → Actions → "ETA Web-Services: Create dashboard card"**, then paste the response as a manual card in a *Panel* view.
- Problems or a system that reports different values: open an [issue](https://github.com/dorsch95/ha-eta-webservices/issues/new/choose) and attach the **diagnostics file** (device page → *Download diagnostics*). It contains the complete menu tree, the IP address is redacted.

</details>

---

## ⚙️ Vorbereitung am ETA-Kessel

Damit Home Assistant auf die Daten zugreifen kann, müssen die Webservices auf der Steuerung deiner Heizung aktiviert werden:

1. Stelle sicher, dass auf deiner Anlage **Systemsoftware x.20.0 oder neuer** läuft.
2. Registriere deine Anlage auf dem Portal [meinETA](https://meineta.at), falls noch nicht geschehen.
3. Gehe am Touch-Display deiner Heizung unten links auf den **Werkzeugkasten** (Einstellungen).
4. Öffne **Internet & Schnittstellen** -> **meinETA Zugang**.
5. Aktiviere dort die **Webservices**.

Danach ist die Heizung im Heimnetz unter `http://<DEINE-ETA-IP>:8080/user/menu` erreichbar. Du kannst das im Browser prüfen: Erscheint eine XML-Seite mit dem Menübaum deiner Anlage, ist alles bereit.

---

## 🚀 Installation via HACS

1. **HACS** öffnen, nach **ETA Web-Services** suchen und **Herunterladen**.
2. Home Assistant vollständig neu starten.

<details>
<summary>Nicht gefunden? So fügst du das Repository von Hand hinzu</summary>

Solange die Aufnahme in den HACS-Store noch läuft, geht es über ein benutzerdefiniertes Repository:

1. In **HACS** oben rechts auf die drei Punkte (`...`) -> **Benutzerdefinierte Repositories**.
2. `https://github.com/dorsch95/ha-eta-webservices` einfügen, Kategorie **Integration**, **Hinzufügen**.
3. Danach wie oben: suchen, herunterladen, Home Assistant neu starten.

</details>

---

## 🛠️ Einrichtung in Home Assistant

Nach dem Neustart kannst du die Integration direkt über die Benutzeroberfläche einrichten:

1. Gehe zu **Einstellungen** -> **Geräte & Dienste** -> **Integration hinzufügen**.
2. Suche nach **ETA Web-Services**.
3. Gib die **IP-Adresse** deiner ETA-Heizung ein (Port ist standardmäßig `8080`).
4. **Kreuze an, welche Komponenten deine Anlage hat** (Pufferspeicher, Frischwassermodul/Warmwasser, Heizkreis 1 bis 4, Solaranlage, Pelletlager, TWIN). Der Kessel steht nicht zur Wahl - den hat jede Anlage. **TWIN** kreuzt an, wer einen Stückholzkessel mit angebautem Pelletteil (SH TWIN) hat: Dann erscheinen Pelletverbrauch, Tagesbehälter und Aschebox wie bei einem Pelletkessel mit auf der Kessel-Kachel.
5. Entscheide, ob **Störungsmeldungen** ausgelesen werden sollen (standardmäßig an) und ob Home Assistant **Kessel und Heizkreise schalten** darf (standardmäßig **aus**). Schaltest du das ein, erscheint danach ein Hinweis, was das bedeutet.
6. Der **Heizwert deiner Pellets** steht auf 4,8 kWh/kg. Das ist der übliche Richtwert für ENplus A1; steht auf deinem Lieferschein ein anderer Wert, trage ihn hier ein.
7. Klicke auf **Weiter**. Die Integration prüft die Verbindung.
8. Im zweiten Schritt siehst du ein Formular **"Funktionsblock-Namen bestätigen"** - je nach angekreuzten Komponenten mit Feldern für die an deiner Anlage relevanten Funktionsblöcke (FUB), z. B. "Kessel", "PufferFlex", "HK", "HK2", "FWM". Diese sind bereits mit den ETA-Standardnamen vorausgefüllt. **Falls du einen FUB an deiner Steuerung umbenannt hast** (z. B. "Kessel" in "Holzvergaser"), trage hier den tatsächlichen Namen ein - sonst kann die Integration die zugehörigen Werte nicht finden.
9. Klicke auf **Absenden**.

Alle Einstellungen lassen sich später jederzeit über **Einstellungen -> Geräte & Dienste -> ETA Web-Services -> Konfigurieren** ändern, ohne die Integration neu einrichten zu müssen. Nur die **IP-Adresse** steht woanders: Bekommt die Heizung eine neue, trägst du sie im Drei-Punkte-Menü der Integration unter **Neu konfigurieren** ein.

> 💡 Das **Abfrageintervall** legt fest, wie oft die Anlage ausgelesen wird (Standard 30 Sekunden, erlaubt sind 10 bis 600). Die Integration legt dafür einen **Variablensatz** auf der Anlage an und liest damit alle Messwerte mit einer einzigen Anfrage statt mit einer pro Wert. Kennt deine Anlage keine Variablensätze, werden die Werte parallel einzeln gelesen - dann wird die Steuerung bewusst nur mit wenigen gleichzeitigen Anfragen belastet.

---

## 📊 Unterstützte Sensoren

Alle Entitäten hängen an einem gemeinsamen Gerät ("ETA Heizung"). Die vollständige Liste steht unten; erklärungsbedürftig sind nur diese:

* **Pufferfühler:** alle tatsächlich vorhandenen (PufferFlex hat 3 bis 9). Die Anzahl erkennt die Integration selbst; Fühler 1 trägt das Attribut `position: oben`, der letzte `position: unten`.
* **Zirkulationspumpe:** ob sie gerade läuft - nicht, wie warm das Zirkulationswasser ist.
* **`sensor.eta_heizung_aschebox_status`:** Verbrauch und Schwelle in einem Text ("459/1000kg"), weil die Dashboard-Karte zwei Werte nicht zusammenführen kann.
* **`sensor.eta_heizung_aktive_fehler`:** Anzahl der Störungen, die Meldungen selbst in den Attributen.
* **Drei Melder** (`binary_sensor`): Störung liegt an, Aschebox fällig, Pelletvorrat niedrig.
* **Schalter und Betriebsart** entstehen nur bei freigegebenem Schreibzugriff - siehe unten.
* **Komponenten-Marker** (Diagnose): je Komponente eine Entität, über die die Dashboard-Karte erkennt, was vorhanden ist.

Es entstehen nur Entitäten für die Komponenten, die du angekreuzt hast.

Innerhalb einer angekreuzten Komponente gibt es jeden Sensor **immer**. Findet die Integration einen Wert im Menübaum deiner Anlage nicht, zeigt der Sensor "-" statt eines Werts. Das ist Absicht: Restsauerstoff hat jeder Kessel, einen Kesseldruck nicht jeder - und eine Entität, die je nach Anlage da ist oder fehlt, bricht Dashboards, Automatisierungen und Statistiken.

### Alle Entitäten im Überblick

<details>
<summary>Vollständige Liste (aufklappen)</summary>

Es entstehen nur die Entitäten der Komponenten, die du angekreuzt hast. Schalter und Betriebsart nur bei freigegebenem Schreibzugriff.

| Entität | Bedeutung | Einheit |
|---|---|---|
| **Kessel** | | |
| `sensor.eta_heizung_aschebox_leeren_nach` | Aschebox Leeren nach | kg |
| `sensor.eta_heizung_aschebox_verbrauch_seit_leerung` | Aschebox Verbrauch seit Leerung | kg |
| `sensor.eta_heizung_aussentemperatur` | Außentemperatur | °C |
| `sensor.eta_heizung_kessel_solltemperatur` | Kessel Solltemperatur | °C |
| `sensor.eta_heizung_kessel_zustand` | Kessel Zustand | Text |
| `sensor.eta_heizung_kesseldruck` | Kesseldruck | bar |
| `sensor.eta_heizung_kesseltemperatur` | Kesseltemperatur | °C |
| `sensor.eta_heizung_pellet_gesamtverbrauch` | Pellet Gesamtverbrauch | kg |
| `sensor.eta_heizung_pellet_inhalt_tagesbehalter` | Pellet Inhalt Tagesbehälter | kg |
| `sensor.eta_heizung_restsauerstoff` | Restsauerstoff | % |
| `sensor.eta_heizung_rucklauftemperatur` | Rücklauftemperatur | °C |
| `sensor.eta_heizung_verbrauch_seit_entaschung` | Verbrauch seit Entaschung | kg |
| `switch.eta_heizung_kessel` | Kessel | Schalter |
| **Pufferspeicher** | | |
| `sensor.eta_heizung_puffer_ladezustand` | Puffer Ladezustand | % |
| **FWM** | | |
| `sensor.eta_heizung_fwm_warmwassertemperatur` | FWM Warmwassertemperatur | °C |
| `sensor.eta_heizung_fwm_zirkulationspumpe` | FWM Zirkulationspumpe | Text |
| **Heizkreis 1** | | |
| `select.eta_heizung_heizkreis_1_betriebsart` | Heizkreis 1 Betriebsart | Auswahl |
| `sensor.eta_heizung_heizkreis_anforderung` | Heizkreis Anforderung | Text |
| `sensor.eta_heizung_heizkreis_vorlauftemperatur` | Heizkreis Vorlauftemperatur | °C |
| **Heizkreis 2** | | |
| `select.eta_heizung_heizkreis_2_betriebsart` | Heizkreis 2 Betriebsart | Auswahl |
| `sensor.eta_heizung_heizkreis_2_anforderung` | Heizkreis 2 Anforderung | Text |
| `sensor.eta_heizung_heizkreis_2_vorlauftemperatur` | Heizkreis 2 Vorlauftemperatur | °C |
| **Heizkreis 3** | | |
| `select.eta_heizung_heizkreis_3_betriebsart` | Heizkreis 3 Betriebsart | Auswahl |
| `sensor.eta_heizung_heizkreis_3_anforderung` | Heizkreis 3 Anforderung | Text |
| `sensor.eta_heizung_heizkreis_3_vorlauftemperatur` | Heizkreis 3 Vorlauftemperatur | °C |
| **Heizkreis 4** | | |
| `select.eta_heizung_heizkreis_4_betriebsart` | Heizkreis 4 Betriebsart | Auswahl |
| `sensor.eta_heizung_heizkreis_4_anforderung` | Heizkreis 4 Anforderung | Text |
| `sensor.eta_heizung_heizkreis_4_vorlauftemperatur` | Heizkreis 4 Vorlauftemperatur | °C |
| **Pelletlager** | | |
| `sensor.eta_heizung_lager_austragung` | Lager Austragung | Text |
| `sensor.eta_heizung_lager_fassungsvermogen` | Lager Fassungsvermögen | kg |
| `sensor.eta_heizung_lager_vorrat` | Lager Vorrat | kg |
| `sensor.eta_heizung_lager_warngrenze` | Lager Warngrenze | kg |
| **Solar** | | |
| `sensor.eta_heizung_solar_ertrag_gestern` | Solar Ertrag gestern | kWh |
| `sensor.eta_heizung_solar_ertrag_heute` | Solar Ertrag heute | kWh |
| `sensor.eta_heizung_solar_kollektortemperatur` | Solar Kollektortemperatur | °C |
| `sensor.eta_heizung_solar_leistung` | Solar Leistung | kW |
| `sensor.eta_heizung_solar_warmemenge` | Solar Wärmemenge | kWh |
| **Unabhängig von den Komponenten** | | |
| `sensor.eta_heizung_aschebox_status` | "459/1000kg" für die Dashboard-Anzeige | |
| `sensor.eta_heizung_pellet_energieverbrauch_gesamt` | Gesamtverbrauch in kWh fürs Energie-Dashboard | |
| `sensor.eta_heizung_aktive_fehler` | Anzahl der anstehenden Störungen | |
| `sensor.eta_heizung_puffer_fuhler_1` … `_9` | je gefundenem Pufferfühler einer | |
| `sensor.eta_heizung_komponente_*` | Marker je Komponente für die Dashboard-Karte | |
| `binary_sensor.eta_heizung_storung` | an, sobald eine Störung ansteht | |
| `binary_sensor.eta_heizung_aschebox_leeren` | an, sobald die Schwelle erreicht ist | |
| `binary_sensor.eta_heizung_pelletvorrat_niedrig` | an, sobald der Vorrat die Warngrenze erreicht | |

</details>

### Fehlt der Wert dauerhaft oder gerade nur nicht?

Jeder Sensor hat dafür das Attribut `status`:

| `status` | Anzeige | Bedeutung |
|---|---|---|
| `ok` | der Wert | alles in Ordnung |
| `nicht_vorhanden` | `-` | Stand schon beim Einrichten nicht im Menübaum - diese Anlage hat den Wert nicht |
| `nicht_erreichbar` | *Nicht verfügbar* | Den Wert gibt es, er kam nur bei den letzten Abfragen nicht an |

Ein einzelner Aussetzer ändert nichts: Der letzte bekannte Wert bleibt stehen, damit ein Timeout keinen Sensor flackern lässt. Erst wenn ein Wert **zweimal hintereinander** ausbleibt, wird der Sensor als nicht erreichbar gemeldet - statt weiter eine alte Zahl zu zeigen.

In einer Automatisierung abfragbar:

```jinja2
{{ state_attr('sensor.eta_heizung_kesseldruck', 'status') == 'nicht_vorhanden' }}
```

### Funktionsblöcke wurden umbenannt?

Alle Funktionsblöcke (FUB) können am Gerät selbst umbenannt werden - dann heißen sie auch in den Webservices anders, und die automatische Erkennung findet sie nicht mehr über ihren Standardnamen. Deshalb fragt die Integration beim Einrichten (und in den Optionen) für jeden relevanten FUB den tatsächlichen Namen ab. ETA-Standardnamen zum Vergleich:

| Rolle | Standardname(n) |
|---|---|
| Kessel | `Kessel` |
| Pelletteil des SH TWIN | `Twin` |
| Pufferspeicher | `PufferFlex` (ältere Anlagen ohne Flex-Funktion: `Puffer`) |
| Frischwasser-/Warmwassermodul | `FWM`, oder `WW` bei einem reinen Warmwasserspeicher |
| Heizkreis 1 | `HK` (auch `HK1` oder `HK 1` wird gefunden) |
| Heizkreis 2 | `HK2` oder `HK 2` |
| Heizkreis 3 | `HK3` oder `HK 3` |
| Heizkreis 4 | `HK4` oder `HK 4` |
| Pelletlager | `Lager` |
| Solaranlage | `Solar` |
| Außentemperatur | `Sys` |

---

## 📺 Dashboard-Vorlage für Lovelace

Es gibt **eine** Karte für alle Anlagen. Sie zeigt genau die Komponenten, die du im Setup ausgewählt hast, und passt sich an die Bildschirmbreite an.

### Einrichten

1. Öffne **Entwicklerwerkzeuge -> Aktionen**, wähle **ETA Web-Services: Dashboard-Karte erzeugen** und klicke auf **Aktion ausführen**. Die Antwort darunter ist die fertige Karte - zugeschnitten auf deine Anlage: nur deine Komponenten, genau deine Pufferfühler, deine Entitäten. Kopiere sie komplett.
2. Lege im Dashboard eine **neue Ansicht** an (Stift oben rechts, dann `+`).
3. Wähle als Ansichtstyp **Panel (1 Karte)**. Das ist wichtig: In der normalen Ansicht begrenzt Home Assistant Karten auf etwa 500 Pixel Breite, und die Beschriftungen werden abgeschnitten.
4. Füge in dieser Ansicht eine Karte vom Typ **Manuell** ein und ersetze den Inhalt durch die kopierte Antwort.

Es ist nichts zu löschen und nichts anzupassen. Die Grafiken liefert die Integration selbst aus. Baust du deine Anlage später um, führ die Aktion einfach noch einmal aus.

Alternativ gibt es die **universelle Karte**, die ohne Anpassung zu jeder Anlage passt: **➡️ [dashboard/eta-karte.yaml](dashboard/eta-karte.yaml)**. Sie ist deutlich länger, weil sie alle Komponenten und Fühlerzahlen enthält und das Passende per Bedingung einblendet.

> ℹ️ **Update von Version 0.20 oder älter:** Füge die Karte einmal neu ein. Die Grafiken kommen jetzt direkt aus der Integration statt aus deinem `www`-Ordner, außerdem hat die Heizkreis-Kachel neue Tasten für die Betriebsart. Die alte Karte funktioniert bis dahin weiter. Danach kannst du den Ordner `www/community/ha-eta-webservices` löschen - er wird nicht mehr gebraucht.

### Wie sich die Karte anpasst

Je schmaler die Ansicht, desto weniger Spalten - sonst wird jede Kachel so schmal, dass die Beschriftungen abgeschnitten werden:

| Breite | Spalten | Beschriftungen |
|---|---|---|
| unter 768 px (Handy) | 2 | gekürzt (`RL:`, `Asche:`, `O₂:`) |
| 768 bis 1039 px (Tablet) | 3 | vollständig |
| ab 1040 px (Desktop) | 4 | vollständig |

Alle drei Varianten sind in einer echten Home-Assistant-Instanz bei 412, 900, 1100 und 1400 Pixel Breite geprüft worden.

<details>
<summary><b>Wie das funktioniert</b> (aufklappen)</summary>

Ein `vertical-stack` aus drei `conditional`-Karten mit `condition: screen` - sichtbar ist nur die zur Fensterbreite passende. Jede davon ist ein `grid` mit fester Spaltenzahl, in dem jede Komponente wiederum eine `conditional`-Karte ist, die auf ihre Marker-Entität prüft (`sensor.eta_heizung_komponente_*`). Ausgeblendete Karten fallen per `display: none` aus dem Grid, die übrigen rücken nach und behalten dabei ihre Größe.

Die Beschriftungen stecken **nicht** in den Grafiken, sondern in `prefix` der `state-label`-Elemente. Deshalb genügt eine Grafik je Komponente, und jede Beschriftung lässt sich im YAML ändern.

> ℹ️ `picture-elements` kennt nur diese Elementtypen: `conditional`, `icon`, `image`, `service-button` (alias `action-button`), `state-badge`, `state-icon`, `state-label`. Ein `type: markdown` gibt es dort **nicht**.

</details>

> ℹ️ Die Entitäts-IDs sind **in jeder Spracheinstellung gleich** - die Kesseltemperatur heißt auch in einem englischen Home Assistant `sensor.eta_heizung_kesseltemperatur`, nur der angezeigte Name ist übersetzt. Deshalb passt die Karte überall. Hast du eine Entität umbenannt, setzt die Aktion *Dashboard-Karte erzeugen* den neuen Namen von selbst ein.

### Pufferfühler

Die Karte zeigt **so viele Fühler, wie deine Anlage hat** - drei bis neun. Du musst nichts anpassen.

Dahinter steckt für jede mögliche Anzahl ein eigener Block, der genau dann greift, wenn Fühler *N* vorhanden und Fühler *N+1* nicht vorhanden ist. Die Fühler verteilen sich dabei gleichmäßig über die Speicherhöhe, denn Fühler 1 misst oben und der letzte unten - beide tragen das Attribut `position` mit `oben` bzw. `unten`.

Wie viele du hast, steht unter **Entwicklerwerkzeuge -> Zustände** (`sensor.eta_heizung_puffer_fuhler_`).

### Beschriftungen ändern

Jede Beschriftung steht als `prefix` im YAML, nicht im Bild. Aus `prefix: 'Kessel: '` wird also einfach `prefix: 'Vorlauf Kessel: '`. Mit `suffix` lässt sich zusätzlich etwas hinter den Wert setzen.

Denk daran, die Änderung in allen drei Bildschirm-Varianten zu machen.

### Meldungen von Spook

Werkzeuge wie [Spook](https://spook.boo) melden bei der **universellen** Karte *"unbekannte Entitäten"*: Sie nennt bewusst auch Heizkreis 2 bis 4 und die Pufferfühler 6 bis 9, jeweils abgesichert durch eine Bedingung, und Spook wertet Bedingungen nicht aus. Angezeigt wird trotzdem nichts Falsches. Die Karte aus der Aktion *Dashboard-Karte erzeugen* nennt nur Entitäten, die es bei dir gibt - dann bleibt Spook still.

> 💡 `top`/`left` verankern in Lovelace die **Mitte** des Elements. Die linksbündigen Beschriftungen im Kessel-Block nutzen deshalb `transform: 'translate(0, -50%)'`. Alle Werte lassen sich im visuellen Editor per Drag & Drop feinjustieren.

---

## 🪵 Was deine Anlage liefert

Die Integration sieht für jeden Kessel gleich aus - welche Werte ankommen, entscheidet die Anlage. Du musst nichts zusätzlich auswählen: Sie sieht im Menübaum nach, und was nicht da ist, zeigt `-`.

| | Gesamtverbrauch | Wärmemengenmessung |
|---|---|---|
| **Pellets** | immer | je nach Anlage |
| **Hackgut** | nein | je nach Anlage |
| **Stückholz** | nein | je nach Anlage |
| **Solar** | – | je nach Anlage |

**Ohne Gesamtverbrauch** gibt es keinen Energiewert fürs Energie-Dashboard - Hackgut- und Stückholzkessel messen ihren Verbrauch nicht. Die Sensoren heißen trotzdem "Pellet...", weil die Umrechnung über den Heizwert an Pellets hängt.

**Bei der Solaranlage** gibt es die Kollektortemperatur immer. Leistung, Wärmemenge, Ertrag heute und Ertrag gestern nur mit **Wärmemengenmessung**. `sensor.eta_heizung_solar_warmemenge` liefert Langzeitstatistik, etwa für eine Statistik-Karte. Ins Energie-Dashboard gehört sie nicht: Dessen Bereich *Solarpanel* ist für Strom aus einer PV-Anlage gedacht, und Home Assistant würde die Wärme mit deinem Stromverbrauch verrechnen.

---

## ⚡ Pelletverbrauch im Energie-Dashboard

Die Integration rechnet den Pelletverbrauch in Energie um und stellt ihn als `sensor.eta_heizung_pellet_energieverbrauch_gesamt` in kWh bereit. Damit lässt er sich neben Strom und Gas ins Energie-Dashboard aufnehmen:

**Einstellungen -> Dashboards -> Energie -> Gasverbrauch hinzufügen** und den Sensor auswählen. Danach siehst du deinen Heizverbrauch pro Tag, Monat und Jahr, bei hinterlegtem Pelletpreis auch die Kosten.

Grundlage ist der **Gesamtverbrauch** deiner Anlage (`Zählerstände -> Gesamtverbrauch`) mal dem eingestellten Heizwert. Dieser Zähler springt nie zurück.

Der Zähler *Verbrauch seit Aschebox leeren* wird dafür **nicht** verwendet: Er sagt, wann die Aschebox zu leeren ist, und hat mit dem Verbrauch der Anlage nichts zu tun. Führt eine Anlage den Gesamtverbrauch nicht, zeigt der Energiesensor `-` - dann bietet sich im Energie-Dashboard auch keine Quelle an, die nie etwas liefert.

> ⚠️ Ändere den Heizwert möglichst nur einmal beim Einrichten. Bei einer nachträglichen Änderung springt der Sensorwert, und Home Assistant wertet einen Sprung nach unten als Zählerrücksetzung - der Gesamtverbrauch fällt dadurch einmalig zu hoch aus.

---

## 🔌 Kessel und Heizkreise schalten

Schalter sind **standardmäßig ausgeschaltet** - sie schreiben in die Heizungssteuerung, und dazu soll niemand durch ein Update kommen. Einschalten kannst du sie beim Einrichten oder später unter **Konfigurieren**; dabei erscheint ein Hinweis, was das bedeutet.

Ist der Schreibzugriff freigegeben und findet die Integration am Kessel eine **Ein/Aus-Taste**, legt sie dafür einen Schalter an: `switch.eta_heizung_kessel`.

**Heizkreise bekommen keinen Ein/Aus-Schalter.** Dort gibt es stattdessen die Betriebsart-Auswahl, in der "Aus" einer von vier Einträgen ist - ein zusätzlicher Schalter daneben wäre ein zweiter Bedienweg für dieselbe Sache.

In der Dashboard-Karte erscheint der Kesselschalter als **antippbares Symbol unten rechts**; auf den Heizkreis-Kacheln steht die Betriebsart als Text und öffnet beim Antippen die Auswahl. Beides erscheint nur, wenn es die Entität wirklich gibt - ohne freigegebenen Schreibzugriff bleibt die Kachel wie bisher.

Ein Schalter entsteht nur, wenn **alle** folgenden Punkte zutreffen:

* Im Menübaum des Funktionsblocks gibt es ein Objekt namens *Ein/Aus Taste* (oder *E/A Taste*, *On/off button*, *I/O key*).
* Deine Anlage meldet diese Variable über `/user/varinfo` ausdrücklich als **beschreibbar**.
* Sie kennt dafür **genau zwei** Zustände, und einer davon heißt erkennbar "Aus".

Die Rohwerte für Ein und Aus werden **nicht geraten**, sondern von der Anlage abgefragt. Trifft einer der Punkte nicht zu, entsteht kein Schalter - lieber keiner als einer, der einen falschen Wert in die Heizungssteuerung schreibt.

> ℹ️ Dafür braucht die ETAtouch-Schnittstelle deiner Anlage **Version 1.2** oder neuer. Welche sie meldet, zeigt Home Assistant unter **Einstellungen -> Geräte & Dienste -> ETA Web-Services** als Softwarestand des Geräts.

Erscheint kein Schalter, obwohl deine Anlage einen haben sollte, zeigt der Diagnose-Export unter `schreibzugriff`, was gefunden wurde. Den Grund nennt das **Debug-Protokoll**: Es nennt für jeden Kandidaten den Grund (*nicht beschreibbar*, *hat N Zustände statt zwei*, *unklar, welcher Zustand 'aus' bedeutet*). Dafür in der `configuration.yaml`:

```yaml
logger:
  logs:
    custom_components.eta_webservices: debug
```

> ⚠️ Der Schalter greift direkt in die Heizungssteuerung ein. Im Winter einen Heizkreis oder den Kessel per Automation abzuschalten kann Räume auskühlen lassen; für den Frostschutz ist weiterhin die Anlage selbst zuständig.

### Betriebsart je Heizkreis

Findet die Integration am Heizkreis zusätzlich die Tasten **Auto**, **Heizen** und **Absenken**, entsteht daraus eine Auswahl: `select.eta_heizung_heizkreis_1_betriebsart` bis `..._4_betriebsart`.

| Auswahl | Was geschieht |
|---|---|
| Auto | Der Heizkreis folgt seinem Zeitprogramm |
| Dauer | Dauerhaft Heizbetrieb |
| ECO | Dauerhaft Absenkbetrieb |
| Aus | Der Heizkreis wird über seine Ein/Aus-Taste abgeschaltet |

Die Bezeichnungen folgen dem Display der Anlage. In Automatisierungen zählen dagegen die internen Werte `automatik`, `heizen`, `absenken` und `aus`.

An der Anlage sind das vier getrennte Tasten, die sich wie Radioknöpfe verhalten: Läuft der Heizkreis, steht genau eine der drei Betriebsarten auf "Ein"; ist er aus, stehen alle drei auf "Aus". Home Assistant fasst sie zu einer Auswahl zusammen. Wählst du aus dem Zustand "Aus" heraus eine Betriebsart, wird der Heizkreis vorher eingeschaltet - sonst bliebe die Auswahl wirkungslos.

Die Auswahl entsteht nur, wenn die Integration die Ein/Aus-Taste des Heizkreises findet - ohne sie gäbe es keinen Weg nach "Aus" und zurück. Als eigene Entität erscheint diese Taste aber nicht.

---

## 🚨 Störungen der Heizung

Die Integration liest die anstehenden Störungen direkt aus der Anlage und stellt sie als `sensor.eta_heizung_aktive_fehler` bereit. Der Zustand ist die Anzahl, die Meldungen stehen in den Attributen:

```yaml
fehler:
  - funktionsblock: Kessel
    meldung: Wasserdruck zu niedrig 1,20 bar
    prioritaet: Error
    zeit: '2026-09-14 11:02:31'
    hinweis: Heizungswasser nachfüllen!
```

Für Automatisierungen genügt meist `binary_sensor.eta_heizung_storung` - er ist an, sobald etwas ansteht. Den Klartext der Meldungen liefert dieser Ausdruck:

```jinja2
{{ state_attr('sensor.eta_heizung_aktive_fehler', 'fehler')
   | map(attribute='meldung') | join(', ') }}
```

Fertig verpackt gibt es das als Blueprint **Störung melden** - siehe unten.

---

## 🧩 Fertige Automatisierungen (Blueprints)

Im Ordner [`blueprints/automation/eta_webservices`](blueprints/automation/eta_webservices) liegen drei gebrauchsfertige Automatisierungen:

| Blueprint | Wofür |
|---|---|
| **Störung melden** | Push-Nachricht, sobald eine Störung ansteht - mit dem Klartext der Meldung |
| **Aschebox leeren** | Erinnerung, sobald die Schwelle der Anlage erreicht ist |
| **Heizkreis auf ECO bei offenem Fenster** | Setzt den Heizkreis auf ECO, solange ein Fenster offen steht, und stellt danach die Betriebsart von vorher wieder her. Ein Heizkreis auf *Aus* bleibt aus |

**Einbauen:** Die gewünschte `.yaml` nach `config/blueprints/automation/eta_webservices/` kopieren (Ordner ggf. anlegen) und Home Assistant neu starten. Danach unter **Einstellungen -> Automatisierungen & Szenen -> Blueprints** auswählen.

Der dritte braucht die Betriebsart-Auswahl, also einen freigegebenen Schreibzugriff.

---

## 🩺 Fehlersuche

Die Integration findet die Werte über die **Namen** im Menübaum deiner Anlage, nicht über feste Adressen. Passt ein Name nicht, sucht sie Messwerte zusätzlich über ihre Nummer im selben Funktionsblock. Fehlt dann noch etwas, ist es an deiner Anlage meist schlicht nicht verbaut.

**Eine ganze Komponente ohne Werte** meldet Home Assistant selbst als **Reparatur** (**Einstellungen -> System -> Reparaturen**). Der Hinweis nennt die Komponente und den Weg zu **Konfigurieren**, wo du den tatsächlichen Funktionsblock-Namen einträgst; er verschwindet von selbst, sobald die Werte gefunden werden. War die Heizung gar nicht erreichbar, erscheint er nicht - dann meldet Home Assistant "Wird eingerichtet" und versucht es von selbst weiter.

**Ein einzelner Messwert** steht im Diagnose-Export: **Einstellungen -> Geräte & Dienste -> ETA Web-Services -> Gerät "ETA Heizung" -> Diagnose herunterladen**. Darin steht je Messwert die abgefragte Adresse, der zuletzt angekommene Wert, unter `"nicht_gefunden"` alles ohne Treffer, unter `"ueber_kennung_gefunden"` die Werte, die nicht über ihren Namen, sondern über ihre Nummer gefunden wurden, unter `"schreibzugriff"`, welche Schalter erkannt wurden, und unter `"menuebaum"` der **vollständige Menübaum** deiner Anlage. Mehr braucht es nicht, um die Integration an eine abweichende Anlage anzupassen. Die IP-Adresse ist geschwärzt, die Datei kann also an ein [Issue](https://github.com/dorsch95/ha-eta-webservices/issues/new/choose) angehängt werden - das Formular dort fragt nach allem Nötigen.

**Lässt sich die Integration gar nicht einrichten**, gibt es keinen Diagnose-Export. Dann fragt [`tools/eta_bericht.py`](tools/eta_bericht.py) die Anlage direkt. Die Datei ist in sich geschlossen - herunterladen, auf einem Rechner im selben Netz ablegen, starten. Nötig ist nur Python, keine Zusatzpakete:

```bash
python3 eta_bericht.py 10.0.0.173
```

Heraus kommt `eta_bericht.txt` mit Webservice-Version, allen Funktionsblöcken, den schaltbar aussehenden Objekten samt Beschreibung, den aktiven Störungen und dem vollständigen Menübaum - IP ebenfalls geschwärzt. Das Skript liest nur; einzige Ausnahme ist ein Variablensatz, den die Anlage ohnehin nur im Arbeitsspeicher hält und der am Ende wieder entfernt wird.

---

## 🧪 Entwicklung

Die Testsuite läuft gegen ein echtes Home Assistant, aber ohne laufende Instanz und ohne echte Heizung - die Anlage wird durch einen aufgezeichneten Menübaum ersetzt:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements_test.txt
pytest
```

Dieselben Tests laufen zusammen mit `hassfest` und der HACS-Validierung bei jedem Push automatisch in GitHub Actions.

Grundlage für die Attrappe ist die offizielle Dokumentation *ETAtouch RESTful Webservices* (Version 1.2); ihre Antworten bilden deren Beispiele nach, inklusive `advTextOffset`, an dem sich Textvariablen erkennen lassen.

Ein Teil der Tests prüft nicht den Code, sondern dieses README: dass die Dashboard-Karte nur gültige Elementtypen verwendet, dass jede darin genannte Entität wirklich entsteht, und dass die Entitäts-IDs in jeder Sprache gleich bleiben.

---

## 📄 Lizenz

Dieses Projekt ist unter der MIT-Lizenz lizenziert – siehe die [LICENSE](LICENSE) Datei für Details.
