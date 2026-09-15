# ETA Heiztechnik Web Service Integration für Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Diese Integration liest **ETA Heizsysteme** komplett lokal über die integrierten RESTful Webservices (ETAtouch) aus - Pellet-, Stückholz- und Hackgutkessel samt Pufferspeicher, Frischwassermodul, Heizkreisen, Solaranlage und Pelletlager. Es geht nichts ins Internet.

Standardmäßig wird nur gelesen. Kessel und Heizkreise lassen sich auf Wunsch auch schalten; das muss beim Einrichten ausdrücklich freigegeben werden.

⚡ Du kreuzt im Setup an, welche Komponenten deine Anlage hat. Die passenden Grafiken landen automatisch auf deiner Festplatte, und eine einzige Dashboard-Karte deckt alle Anlagen ab.

📈 Bei Pelletkesseln steht der Verbrauch als Energiewert bereit und lässt sich ins **Energie-Dashboard** von Home Assistant aufnehmen.

🔎 Die internen ETA-Objekt-URIs (z. B. `/264/10891/0/11109/0`) unterscheiden sich von Anlage zu Anlage. Beim Einrichten ruft die Integration deshalb einmalig den Menübaum der Anlage (`/user/menu`) ab und ermittelt die passenden URIs automatisch anhand ihrer **Bezeichnungen** (z. B. "Kessel → Eingänge → Rücklauf"), die im Gegensatz zu den Zahlen-IDs stabil bleiben. Eine manuelle Eingabe von URIs ist damit nicht nötig. Im Code steht **keine einzige feste URI** - eine Adresse von einer fremden Anlage wäre geraten und könnte still den falschen Wert anzeigen. Was der Menübaum deiner Anlage nicht hergibt, bekommt trotzdem eine Entität; sie zeigt dann dauerhaft **"-"**. Findet sich zu einer ganzen Komponente nichts, meldet sich Home Assistant zusätzlich mit einem Reparatur-Hinweis.

> ℹ️ Benötigt Home Assistant **2025.8** oder neuer.

---

## ⚙️ Vorbereitung am ETA-Kessel

Damit Home Assistant auf die Daten zugreifen kann, müssen die Webservices auf der Steuerung deiner Heizung aktiviert werden:

1. Stelle sicher, dass auf deiner Anlage **Systemsoftware 1.20.0 oder neuer** läuft.
2. Registriere deine Anlage auf dem Portal [meinETA](https://meineta.at), falls noch nicht geschehen.
3. **Beantrage dort den LAN-Zugriff** für deine Anlage. Ohne diesen Schritt bleiben die Webservices aus, auch wenn du sie am Display einschaltest.
4. Gehe am Touch-Display deiner Heizung unten links auf den **Werkzeugkasten** (Einstellungen).
5. Öffne **Internet & Schnittstellen** -> **meinETA Zugang**.
6. Aktiviere dort die **Webservices**.

Danach ist die Heizung im Heimnetz unter `http://<DEINE-ETA-IP>:8080/user/menu` erreichbar. Du kannst das im Browser prüfen: Erscheint eine XML-Seite mit dem Menübaum deiner Anlage, ist alles bereit.

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
4. **Kreuze an, welche Komponenten deine Anlage hat** (Pufferspeicher, Frischwassermodul/Warmwasser, Heizkreis 1 bis 4, Solaranlage, Pelletlager). Der Kessel steht nicht zur Wahl - den hat jede Anlage.
5. Entscheide, ob **Störungsmeldungen** ausgelesen werden sollen (standardmäßig an) und ob Home Assistant **Kessel und Heizkreise schalten** darf (standardmäßig **aus**). Schaltest du das ein, erscheint danach ein Hinweis, was das bedeutet.
6. Der **Heizwert deiner Pellets** steht auf 4,8 kWh/kg. Das ist der übliche Richtwert für ENplus A1; steht auf deiner Lieferscheinung ein anderer Wert, trage ihn hier ein.
7. Klicke auf **Weiter**. Die Integration prüft die Verbindung.
8. Im zweiten Schritt siehst du ein Formular **"Funktionsblock-Namen bestätigen"** - je nach angekreuzten Komponenten mit Feldern für die an deiner Anlage relevanten Funktionsblöcke (FUB), z. B. "Kessel", "PufferFlex", "HK1", "HK2", "FWM". Diese sind bereits mit den ETA-Standardnamen vorausgefüllt. **Falls du einen FUB an deiner Steuerung umbenannt hast** (z. B. "Kessel" in "Holzvergaser"), trage hier den tatsächlichen Namen ein - sonst kann die Integration die zugehörigen Werte nicht finden.
9. Klicke auf **Absenden**. Die Komponentengrafiken werden automatisch auf deiner Festplatte abgelegt.

Alle Einstellungen lassen sich später jederzeit über **Einstellungen -> Geräte & Dienste -> ETA Heiztechnik Web Service -> Konfigurieren** ändern, ohne die Integration neu einrichten zu müssen. Über das Drei-Punkte-Menü der Integration geht es alternativ mit **Neu konfigurieren**.

> 💡 Das **Abfrageintervall** legt fest, wie oft die Anlage ausgelesen wird (Standard 30 Sekunden, erlaubt sind 10 bis 600). Die Integration legt dafür einen **Variablensatz** auf der Anlage an und liest damit alle Messwerte mit einer einzigen Anfrage statt mit einer pro Wert. Kennt deine Anlage keine Variablensätze, werden die Werte parallel einzeln gelesen - dann wird die Steuerung bewusst nur mit wenigen gleichzeitigen Anfragen belastet.

---

## 📊 Unterstützte Sensoren

Alle Entitäten werden einem gemeinsamen Gerät ("ETA Heizung") zugeordnet und (sofern physisch an deiner Anlage angeschlossen bzw. per Menübaum gefunden) automatisch ausgelesen:

* **🔥 Kessel & Umgebung:** Kesseltemperatur, Kessel-Solltemperatur, Rücklauftemperatur, Kesseldruck (bar), Restsauerstoff (%), Außentemperatur, Inhalt Pellet-Tagesbehälter (kg) sowie der **Kesselzustand** als Text (*Heizen*, *Aus* usw.).
* **🗑️ Aschebox:** Verbrauch seit der letzten Leerung (kg) und der Schwellwert, ab dem geleert werden soll (kg) - plus ein kombinierter Sensor `sensor.eta_heizung_aschebox_status` im Format "459/1000kg" für die Dashboard-Anzeige.
* **📊 Verbrauch:** Gesamtverbrauch der Anlage (kg), Verbrauch seit der letzten Entaschung (kg) und der umgerechnete Energieverbrauch (kWh). Alle liefern Langzeitstatistik, sind also über Monate auswertbar.
* **🌾 Pelletlager:** Vorrat im Lagerraum, die an der Anlage eingestellte Warngrenze, das Fassungsvermögen und der Zustand der Austragung. Dazu `binary_sensor.eta_heizung_pelletvorrat_niedrig`, sobald der Vorrat die Warngrenze erreicht - mit dem Füllstand in Prozent als Attribut.
* **🛢️ Pufferspeicher:** Ladezustand (%) sowie **alle tatsächlich vorhandenen Pufferfühler** (PufferFlex hat je nach Anlage 3 bis 8). Die Anzahl erkennt die Integration selbst über den Menübaum; Fühler 1 trägt das Attribut `position: oben`, der zuletzt nummerierte `position: unten`.
* **♨️ Heizkreis 1 bis 4:** jeweils Vorlauftemperatur und Anforderung (Zustandstext wie *Aus* oder *Heizbetrieb*). Heizkreis 3 und 4 sind für größere Anlagen gedacht; kreuze nur an, was du wirklich hast.
* **☀️ Solaranlage:** Kollektortemperatur. Bei einer Anlage **mit Wärmemengenmessung** zusätzlich Leistung (kW), Wärmemenge (kWh), Ertrag heute und Ertrag gestern - siehe unten.
* **🚰 Frischwasser-/Warmwassermodul (FWM oder WW):** Warmwassertemperatur und der Zustand der **Zirkulationspumpe** - also ob sie gerade läuft, nicht wie warm das Zirkulationswasser ist. Hat deine Anlage keine Zirkulationspumpe, zeigt der Sensor `-`.
* **🚨 Störung** (im Setup abwählbar): `binary_sensor.eta_heizung_storung` ist an, sobald mindestens eine Störung anliegt - damit reicht in einer Automatisierung ein Gerätetrigger, statt eine Zahl mit Null zu vergleichen.
* **🗑️ Aschebox leeren:** `binary_sensor.eta_heizung_aschebox_leeren` ist an, sobald seit der letzten Leerung so viel verbrannt wurde, wie an der Anlage als Schwelle eingestellt ist. Beide Werte kommen von der Heizung, hier wird nur verglichen.
* **🚨 Aktive Fehler** (im Setup abwählbar): Anzahl der anstehenden Störungen. Die Meldungen selbst stehen in den Attributen, mit Funktionsblock, Priorität und Zeitpunkt - etwa *"Wasserdruck zu niedrig 1,20 bar"* mit dem Hinweis *"Heizungswasser nachfüllen!"*.
* **🔌 Schalter** für Kessel und Heizkreise sowie je Heizkreis eine **Betriebsart** (Automatik, Heizen, Absenken, Aus), sofern deine Anlage sie zulässt - siehe unten.
* **🧩 Komponenten-Marker** (Diagnose): je gewählter Komponente eine Entität, über die die Dashboard-Karte erkennt, was vorhanden ist.

Es entstehen nur Entitäten für die Komponenten, die du angekreuzt hast.

Innerhalb einer angekreuzten Komponente gibt es jeden Sensor **immer**. Findet die Integration einen Wert im Menübaum deiner Anlage nicht, zeigt der Sensor "-" statt eines Werts. Das ist Absicht: Restsauerstoff hat jeder Kessel, einen Kesseldruck nicht jeder - und eine Entität, die je nach Anlage da ist oder fehlt, bricht Dashboards, Automatisierungen und Statistiken.

### Alle Entitäten im Überblick

<details>
<summary>Vollständige Liste (aufklappen)</summary>

Es entstehen nur die Entitäten der Komponenten, die du angekreuzt hast. Schalter und Betriebsart nur bei freigegebenem Schreibzugriff.

**Kessel**

| Entität | Bedeutung | Einheit |
|---|---|---|
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

**Pufferspeicher**

| Entität | Bedeutung | Einheit |
|---|---|---|
| `sensor.eta_heizung_puffer_ladezustand` | Puffer Ladezustand | % |

**FWM**

| Entität | Bedeutung | Einheit |
|---|---|---|
| `sensor.eta_heizung_fwm_warmwassertemperatur` | FWM Warmwassertemperatur | °C |
| `sensor.eta_heizung_fwm_zirkulationspumpe` | FWM Zirkulationspumpe | Text |

**Heizkreis 1**

| Entität | Bedeutung | Einheit |
|---|---|---|
| `select.eta_heizung_heizkreis_1_betriebsart` | Heizkreis 1 Betriebsart | Auswahl |
| `sensor.eta_heizung_heizkreis_anforderung` | Heizkreis Anforderung | Text |
| `sensor.eta_heizung_heizkreis_vorlauftemperatur` | Heizkreis Vorlauftemperatur | °C |
| `switch.eta_heizung_heizkreis_1` | Heizkreis 1 | Schalter |

**Heizkreis 2**

| Entität | Bedeutung | Einheit |
|---|---|---|
| `select.eta_heizung_heizkreis_2_betriebsart` | Heizkreis 2 Betriebsart | Auswahl |
| `sensor.eta_heizung_heizkreis_2_anforderung` | Heizkreis 2 Anforderung | Text |
| `sensor.eta_heizung_heizkreis_2_vorlauftemperatur` | Heizkreis 2 Vorlauftemperatur | °C |
| `switch.eta_heizung_heizkreis_2` | Heizkreis 2 | Schalter |

**Heizkreis 3**

| Entität | Bedeutung | Einheit |
|---|---|---|
| `select.eta_heizung_heizkreis_3_betriebsart` | Heizkreis 3 Betriebsart | Auswahl |
| `sensor.eta_heizung_heizkreis_3_anforderung` | Heizkreis 3 Anforderung | Text |
| `sensor.eta_heizung_heizkreis_3_vorlauftemperatur` | Heizkreis 3 Vorlauftemperatur | °C |
| `switch.eta_heizung_heizkreis_3` | Heizkreis 3 | Schalter |

**Heizkreis 4**

| Entität | Bedeutung | Einheit |
|---|---|---|
| `select.eta_heizung_heizkreis_4_betriebsart` | Heizkreis 4 Betriebsart | Auswahl |
| `sensor.eta_heizung_heizkreis_4_anforderung` | Heizkreis 4 Anforderung | Text |
| `sensor.eta_heizung_heizkreis_4_vorlauftemperatur` | Heizkreis 4 Vorlauftemperatur | °C |
| `switch.eta_heizung_heizkreis_4` | Heizkreis 4 | Schalter |

**Pelletlager**

| Entität | Bedeutung | Einheit |
|---|---|---|
| `sensor.eta_heizung_lager_austragung` | Lager Austragung | Text |
| `sensor.eta_heizung_lager_fassungsvermogen` | Lager Fassungsvermögen | kg |
| `sensor.eta_heizung_lager_vorrat` | Lager Vorrat | kg |
| `sensor.eta_heizung_lager_warngrenze` | Lager Warngrenze | kg |

**Solar**

| Entität | Bedeutung | Einheit |
|---|---|---|
| `sensor.eta_heizung_solar_ertrag_gestern` | Solar Ertrag gestern | kWh |
| `sensor.eta_heizung_solar_ertrag_heute` | Solar Ertrag heute | kWh |
| `sensor.eta_heizung_solar_kollektortemperatur` | Solar Kollektortemperatur | °C |
| `sensor.eta_heizung_solar_leistung` | Solar Leistung | kW |
| `sensor.eta_heizung_solar_warmemenge` | Solar Wärmemenge | kWh |

**Unabhängig von den Komponenten**

| Entität | Bedeutung |
|---|---|
| `sensor.eta_heizung_aschebox_status` | "459/1000kg" für die Dashboard-Anzeige |
| `sensor.eta_heizung_pellet_energieverbrauch_gesamt` | Gesamtverbrauch in kWh fürs Energie-Dashboard |
| `sensor.eta_heizung_aktive_fehler` | Anzahl der anstehenden Störungen |
| `sensor.eta_heizung_puffer_fuhler_1` … `_8` | je gefundenem Pufferfühler einer |
| `sensor.eta_heizung_komponente_*` | Marker je Komponente für die Dashboard-Karte |
| `binary_sensor.eta_heizung_storung` | an, sobald eine Störung ansteht |
| `binary_sensor.eta_heizung_aschebox_leeren` | an, sobald die Schwelle erreicht ist |
| `binary_sensor.eta_heizung_pelletvorrat_niedrig` | an, sobald der Vorrat die Warngrenze erreicht |

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
| Pufferspeicher | `PufferFlex` (ältere Anlagen ohne Flex-Funktion: `Puffer`) |
| Frischwasser-/Warmwassermodul | `FWM`, oder `WW` bei einem reinen Warmwasserspeicher |
| Heizkreis 1 | `HK`, oder `HK1` sobald mehrere Heizkreise vorhanden sind |
| Heizkreis 2 | `HK2` |
| Heizkreis 3 | `HK3` |
| Heizkreis 4 | `HK4` |
| Pelletlager | `Lager` |
| Solaranlage | `Solar` |
| Außentemperatur | `Sys` |

---

## 📺 Dashboard-Vorlage für Lovelace

Es gibt **eine** Karte für alle Anlagen. Sie zeigt genau die Komponenten, die du im Setup ausgewählt hast, und passt sich an die Bildschirmbreite an.

Die Karte ist lang (sie enthält jede Komponente dreimal, einmal je Bildschirmgröße), deshalb steht sie als eigene Datei im Repo:

**➡️ [dashboard/eta-karte.yaml](dashboard/eta-karte.yaml)** — Inhalt kopieren und wie unten beschrieben einfügen.

### Einrichten

1. Lege im Dashboard eine **neue Ansicht** an (Stift oben rechts, dann `+`).
2. Wähle als Ansichtstyp **Panel (1 Karte)**. Das ist wichtig: In der normalen Ansicht begrenzt Home Assistant Karten auf etwa 500 Pixel Breite, und die Beschriftungen werden abgeschnitten.
3. Füge in dieser Ansicht eine Karte vom Typ **Manuell** ein und ersetze den Inhalt durch den aus `eta-karte.yaml`.

Es ist nichts zu löschen und nichts anzupassen.

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

Die Karte ist ein `vertical-stack` aus drei `conditional`-Karten mit `condition: screen`. Angezeigt wird nur die Variante, die zur aktuellen Fensterbreite passt; die anderen beiden blendet Home Assistant aus.

Jede Variante ist ein `grid` mit fester Spaltenzahl. Darin ist jede Komponente wiederum eine `conditional`-Karte, die auf eine Marker-Entität prüft (`sensor.eta_heizung_komponente_*`). Diese Marker legt die Integration nur für die Komponenten an, die du ausgewählt hast.

Blendet `conditional` eine Komponente aus, setzt Home Assistant `display: none` - die Karte fällt aus dem Grid-Layout, und die verbleibenden Komponenten rücken nach. Weil das Grid feste Spalten hat, bleibt jede Komponente dabei gleich groß.

Die Beschriftungen stecken **nicht** in den Grafiken, sondern kommen aus `prefix` der `state-label`-Elemente. Deshalb genügt eine Grafik je Komponente statt einer für jede mögliche Kombination - und du kannst jede Beschriftung im YAML frei ändern.

> ℹ️ `picture-elements` kennt nur diese Elementtypen: `conditional`, `icon`, `image`, `service-button` (alias `action-button`), `state-badge`, `state-icon`, `state-label`. Ein `type: markdown` gibt es dort **nicht**.

</details>

> ℹ️ Die Entitäts-IDs in der Karte gelten für eine **deutschsprachige** Home-Assistant-Installation. Home Assistant bildet Entitäts-IDs aus dem übersetzten Namen; bei englischer Spracheinstellung heißt die Kesseltemperatur entsprechend `sensor.eta_heizung_boiler_temperature`. Deine bestehenden Entitäten behalten ihre ID in jedem Fall.

### Pufferfühler

Die Karte zeigt **so viele Fühler, wie deine Anlage hat** - drei bis acht. Du musst nichts anpassen.

Dahinter steckt für jede mögliche Anzahl ein eigener Block, der genau dann greift, wenn Fühler *N* vorhanden und Fühler *N+1* nicht vorhanden ist. Die Fühler verteilen sich dabei gleichmäßig über die Speicherhöhe, denn Fühler 1 misst oben und der letzte unten - beide tragen das Attribut `position` mit `oben` bzw. `unten`.

Wie viele du hast, steht unter **Entwicklerwerkzeuge -> Zustände** (`sensor.eta_heizung_puffer_fuhler_`).

### Beschriftungen ändern

Jede Beschriftung steht als `prefix` im YAML, nicht im Bild. Aus `prefix: 'Kessel: '` wird also einfach `prefix: 'Vorlauf Kessel: '`. Mit `suffix` lässt sich zusätzlich etwas hinter den Wert setzen.

Denk daran, die Änderung in allen drei Bildschirm-Varianten zu machen - oder passe [`dashboard/karte_bauen.py`](dashboard/karte_bauen.py) an und erzeuge die Datei neu:

```bash
python dashboard/karte_bauen.py
```

> 💡 `top`/`left` verankern in Lovelace die **Mitte** des Elements. Die linksbündigen Beschriftungen im Kessel-Block nutzen deshalb `transform: 'translate(0, -50%)'`. Alle Werte lassen sich im visuellen Editor per Drag & Drop feinjustieren.

---


## ☀️ Solaranlage

Kreuzt du **Solaranlage** an, liest die Integration die **Kollektortemperatur** aus (`sensor.eta_heizung_solar_kollektortemperatur`).

Vier weitere Werte gibt es nur, wenn deine Solaranlage eine **Wärmemengenmessung** hat:

| Sensor | Bedeutung |
|---|---|
| `sensor.eta_heizung_solar_leistung` | aktuelle Leistung in kW |
| `sensor.eta_heizung_solar_warmemenge` | Wärmemenge insgesamt in kWh |
| `sensor.eta_heizung_solar_ertrag_heute` | Ertrag seit Mitternacht |
| `sensor.eta_heizung_solar_ertrag_gestern` | Ertrag des Vortags |

**Du musst nichts zusätzlich auswählen.** Die Integration schaut im Menübaum deiner Anlage nach, ob es diese Werte gibt. Hat deine Anlage keine Wärmemengenmessung, zeigen die vier Sensoren dauerhaft "-".

`sensor.eta_heizung_solar_warmemenge` liefert Langzeitstatistik und lässt sich als **Solarertrag** ins Energie-Dashboard aufnehmen (**Einstellungen -> Dashboards -> Energie -> Solarpanel hinzufügen**).

---

## 🪵 Was dein Kesseltyp liefert

Die Integration sieht für jeden Kessel gleich aus - welche Werte ankommen, entscheidet die Anlage. Was sie nicht führt, zeigt `-`.

| | Gesamtverbrauch | Wärmemengenmessung |
|---|---|---|
| **Pellets** | immer | je nach Anlage |
| **Hackgut** | nein | je nach Anlage |
| **Stückholz** | nein | je nach Anlage |
| **Solar** | – | je nach Anlage |

**Ohne Gesamtverbrauch** gibt es keinen Energiewert für das Energie-Dashboard - Hackgut- und Stückholzkessel messen ihren Verbrauch nicht. Die Sensoren heißen trotzdem "Pellet...", weil die Umrechnung über den Heizwert an Pellets hängt; bei anderen Brennstoffen bleiben sie leer.

**Ohne Wärmemengenmessung** fehlen an der Solaranlage Leistung, Wärmemenge und die Erträge. Die Kollektortemperatur gibt es immer.

Du musst nichts davon auswählen: Die Integration sieht im Menübaum deiner Anlage nach.

---

## ⚡ Pelletverbrauch im Energie-Dashboard

Die Integration rechnet den Pelletverbrauch in Energie um und stellt ihn als `sensor.eta_heizung_pellet_energieverbrauch_gesamt` in kWh bereit. Damit lässt er sich neben Strom und Gas ins Energie-Dashboard aufnehmen:

**Einstellungen -> Dashboards -> Energie -> Gasverbrauch hinzufügen** und den Sensor auswählen. Danach siehst du deinen Heizverbrauch pro Tag, Monat und Jahr, bei hinterlegtem Pelletpreis auch die Kosten.

Grundlage ist der **Gesamtverbrauch** deiner Anlage (`Zählerstände -> Gesamtverbrauch`) mal dem eingestellten Heizwert. Dieser Zähler springt nie zurück.

Der Zähler *Verbrauch seit Aschebox leeren* wird dafür **nicht** verwendet: Er sagt, wann die Aschebox zu leeren ist, und hat mit dem Verbrauch der Anlage nichts zu tun. Führt eine Anlage den Gesamtverbrauch nicht, zeigt der Energiesensor `-` - dann bietet sich im Energie-Dashboard auch keine Quelle an, die nie etwas liefert.

> ⚠️ Ändere den Heizwert möglichst nur einmal beim Einrichten. Bei einer nachträglichen Änderung springt der Sensorwert, und Home Assistant wertet einen Sprung nach unten als Zählerrücksetzung - der Gesamtverbrauch fällt dadurch einmalig zu hoch aus.

---

## 🔧 Wenn eine Komponente keine Werte liefert

Findet die Integration im Menübaum nichts zu einer angekreuzten Komponente, legt sie eine **Reparatur** an (**Einstellungen -> System -> Reparaturen**). Der Hinweis nennt die Komponente und führt direkt zu den Optionen, wo du den tatsächlichen Funktionsblock-Namen eintragen kannst.

Der Hinweis verschwindet von selbst, sobald die Werte gefunden werden. War die Heizung gar nicht erreichbar, erscheint er nicht - dann liegt es an der Verbindung und nicht an den Namen. Home Assistant meldet in dem Fall stattdessen "Wird eingerichtet" und versucht es von selbst weiter, denn ohne Menübaum ist keine einzige Adresse bekannt.

---

## 🔌 Kessel und Heizkreise schalten

Schalter sind **standardmäßig ausgeschaltet** - sie schreiben in die Heizungssteuerung, und dazu soll niemand durch ein Update kommen. Einschalten kannst du sie beim Einrichten oder später unter **Konfigurieren**; dabei erscheint ein Hinweis, was das bedeutet.

Ist der Schreibzugriff freigegeben und findet die Integration an einem Funktionsblock eine **Ein/Aus-Taste**, legt sie dafür einen Schalter an: `switch.eta_heizung_kessel` sowie `switch.eta_heizung_heizkreis_1` bis `switch.eta_heizung_heizkreis_4`.

In der Dashboard-Karte erscheinen sie als **antippbares Symbol unten rechts** in der jeweiligen Kachel; die Betriebsart steht als Text darüber und öffnet beim Antippen die Auswahl. Beides erscheint nur, wenn es die Entität wirklich gibt - ohne freigegebenen Schreibzugriff bleibt die Kachel wie bisher.

Ein Schalter entsteht nur, wenn **alle** folgenden Punkte zutreffen:

* Im Menübaum des Funktionsblocks gibt es ein Objekt namens *Ein/Aus Taste* (oder *E/A Taste*, *On/off button*, *I/O key*).
* Deine Anlage meldet diese Variable über `/user/varinfo` ausdrücklich als **beschreibbar**.
* Sie kennt dafür **genau zwei** Zustände, und einer davon heißt erkennbar "Aus".

Die Rohwerte für Ein und Aus werden **nicht geraten**, sondern von der Anlage abgefragt. Trifft einer der Punkte nicht zu, entsteht kein Schalter - lieber keiner als einer, der einen falschen Wert in die Heizungssteuerung schreibt.

> ℹ️ Dafür braucht deine Anlage Webservice-Version **1.2** oder neuer. Welche Version sie meldet, zeigt Home Assistant unter **Einstellungen -> Geräte & Dienste -> ETA Heiztechnik Web Service**.

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
| Automatik | Der Heizkreis folgt seinem Zeitprogramm |
| Heizen | Dauerhaft Heizbetrieb |
| Absenken | Dauerhaft Absenkbetrieb |
| Aus | Der Heizkreis wird über seine Ein/Aus-Taste abgeschaltet |

An der Anlage sind das vier getrennte Tasten, die sich wie Radioknöpfe verhalten: Läuft der Heizkreis, steht genau eine der drei Betriebsarten auf "Ein"; ist er aus, stehen alle drei auf "Aus". Home Assistant fasst sie zu einer Auswahl zusammen. Wählst du aus dem Zustand "Aus" heraus eine Betriebsart, wird der Heizkreis vorher eingeschaltet - sonst bliebe die Auswahl wirkungslos.

Die Auswahl entsteht nur zusammen mit dem Schalter desselben Heizkreises. Ohne ihn gäbe es keinen Weg zurück aus "Aus".

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

Für Automatisierungen genügt meist `binary_sensor.eta_heizung_storung` - er ist an, sobald etwas ansteht. Wer die Meldungen im Text haben will, nimmt den Zähler:

```yaml
automation:
  - alias: ETA Störung melden
    triggers:
      - trigger: numeric_state
        entity_id: sensor.eta_heizung_aktive_fehler
        above: 0
    actions:
      - action: notify.persistent_notification
        data:
          title: Störung an der Heizung
          message: >-
            {{ state_attr('sensor.eta_heizung_aktive_fehler', 'fehler')
               | map(attribute='meldung') | join(', ') }}
```

---

## 🧩 Fertige Automatisierungen (Blueprints)

Im Ordner [`blueprints/automation/eta_webservices`](blueprints/automation/eta_webservices) liegen drei gebrauchsfertige Automatisierungen:

| Blueprint | Wofür |
|---|---|
| **Störung melden** | Push-Nachricht, sobald eine Störung ansteht - mit dem Klartext der Meldung |
| **Aschebox leeren** | Erinnerung, sobald die Schwelle der Anlage erreicht ist |
| **Heizkreis absenken bei offenem Fenster** | Setzt den Heizkreis auf Absenken, solange ein Fenster offen steht, und danach zurück |

**Einbauen:** Die gewünschte `.yaml` nach `config/blueprints/automation/eta_webservices/` kopieren (Ordner ggf. anlegen) und Home Assistant neu starten. Danach unter **Einstellungen -> Automatisierungen & Szenen -> Blueprints** auswählen.

Der dritte braucht die Betriebsart-Auswahl, also einen freigegebenen Schreibzugriff.

---

## 🩺 Wenn ein einzelner Wert fehlt

Fehlt nicht eine ganze Komponente, sondern ein einzelner Messwert, hilft der Diagnose-Export weiter. Die Integration findet die Werte über die **Namen** im Menübaum deiner Anlage, nicht über feste Adressen - fehlt einer, ist er an deiner Anlage meist anders benannt oder schlicht nicht verbaut.

Unter **Einstellungen -> Geräte & Dienste -> ETA Heiztechnik Web Service -> Gerät "ETA Heizung" -> Diagnose herunterladen** bekommst du eine Datei, die für jeden Messwert zeigt:

* welche Adresse tatsächlich abgefragt wird,
* welcher Wert zuletzt angekommen ist,
* und unter `"nicht_gefunden"` eine Liste aller Werte ohne Treffer.

Die IP-Adresse ist in dieser Datei geschwärzt, du kannst sie also bedenkenlos an ein [Issue](https://github.com/dorsch95/ha-eta-webservices/issues) anhängen.

### Bericht direkt von der Anlage

Reicht der Diagnose-Export nicht, weil die Integration den Wert gar nicht erst anlegt, fragt [`tools/eta_bericht.py`](tools/eta_bericht.py) die Anlage direkt. Die Datei ist in sich geschlossen: herunterladen, auf einem beliebigen Rechner in deinem Netz ablegen und mit der IP-Adresse deiner Heizung starten. Nötig ist nur Python, keine Zusatzpakete:

```bash
python3 eta_bericht.py 10.0.0.173
```

Heraus kommt `eta_bericht.txt` mit der Webservice-Version, allen Funktionsblöcken, den schaltbar aussehenden Objekten samt ihrer Beschreibung (`isWritable`, mögliche Werte), den aktiven Störungen und dem vollständigen Menübaum. Die IP-Adresse ist auch hier geschwärzt.

Das Skript liest nur. Einzige Ausnahme ist ein Variablensatz, den die Anlage ohnehin nur im Arbeitsspeicher hält und der am Ende wieder entfernt wird - er prüft, ob die Sammelabfrage funktioniert.

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

Ein Teil der Tests prüft nicht den Code, sondern dieses README: dass die Dashboard-Karte nur gültige Elementtypen verwendet, dass jede darin genannte Entität wirklich entsteht, und dass sich die Entitäts-IDs einer deutschsprachigen Installation nicht ändern.

---

## 📄 Lizenz

Dieses Projekt ist unter der MIT-Lizenz lizenziert – siehe die [LICENSE](LICENSE) Datei für Details.
