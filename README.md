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
5. Klicke auf **Weiter**. Die Integration prüft die Verbindung.
6. Im zweiten Schritt siehst du ein Formular **"Funktionsblock-Namen bestätigen"** - je nach gewähltem Schema mit Feldern für die an deiner Anlage relevanten Funktionsblöcke (FUB), z. B. "Kessel", "PufferFlex", "HK1", "HK2", "FWM". Diese sind bereits mit den ETA-Standardnamen vorausgefüllt. **Falls du einen FUB an deiner Steuerung umbenannt hast** (z. B. "Kessel" in "Holzvergaser"), trage hier den tatsächlichen Namen ein - sonst kann die Integration die zugehörigen Werte nicht finden.
7. Klicke auf **Absenden**. Die passenden Hintergrundbilder werden automatisch auf deiner Festplatte generiert.

Host, Port, Anlagenschema und die FUB-Namen lassen sich später jederzeit über **Einstellungen -> Geräte & Dienste -> ETA Heiztechnik Web Service -> Konfigurieren** ändern, ohne die Integration neu einrichten zu müssen.

---

## 📊 Unterstützte Sensoren

Alle Entitäten werden einem gemeinsamen Gerät ("ETA Heizung") zugeordnet und (sofern physisch an deiner Anlage angeschlossen bzw. per Menübaum gefunden) automatisch ausgelesen:

* **🔥 Kessel & Umgebung:** Kesseltemperatur, Kessel-Solltemperatur, Rücklauftemperatur, Kesseldruck (bar), Restsauerstoff (%), Außentemperatur, Inhalt Pellet-Tagesbehälter (kg).
* **🗑️ Aschebox:** Verbrauch seit letzter Leerung (kg) und der eingestellte Schwellwert, ab dem geleert werden soll (kg) - jeweils als eigener Sensor, im Dashboard unten als "459/1000kg" kombiniert dargestellt.
* **🛢️ Pufferspeicher:** Puffer-Ladezustand (%), sowie **alle tatsächlich vorhandenen Pufferfühler** (PufferFlex hat je nach Anlage zwischen 3 und 8 Fühlern). Fühler 1 ist immer der oberste, der zuletzt nummerierte immer der unterste - die Integration erkennt die tatsächliche Anzahl automatisch über den Menübaum und benennt sie entsprechend ("Fühler 1 (oben)" ... "Fühler N (unten)").
* **♨️ Heizkreis 1:** Vorlauftemperatur, Anforderung (Zustandstext wie *Aus*, *Heizbetrieb* etc.).
* **♨️ Heizkreis 2** (nur bei Schema *2x Heizkreis*, sofern ein FUB "HK2" gefunden wird): Vorlauftemperatur, Anforderung.
* **🚰 Frischwasser-/Warmwassermodul (FWM oder WW):** Warmwassertemperatur, sowie Zirkulationstemperatur, sofern die Anlage einen entsprechenden Fühler hat.

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

## 📺 Dashboard-Vorlage für Lovelace (Bild-Elemente)

Durch die automatische Base64-Bildgenerierung musst du keine Grafiken mehr manuell auf deinen Server kopieren. Jede Anlagengrafik hat die Messwert-Beschriftungen (z. B. "Kessel:", "Ladezustand:", "Vorlauf HK1:") bereits fest eingebrannt – es fehlt nur noch der Wert daneben. Die folgenden Karten wurden anhand einer pixelgenauen Analyse der jeweiligen Grafik erstellt, damit die Werte exakt neben ihrer Beschriftung erscheinen.

Wähle unten die Karte passend zu deinem im Setup gewählten Anlagenschema, erstelle eine neue Karte vom Typ **Manuell** (Umschalten auf Code-Editor) und füge den YAML-Code ein.

> ℹ️ Die Außentemperatur hat kein eigenes Beschriftungsfeld auf den Grafiken. Sie wird deshalb unabhängig vom Schema oben rechts in der Ecke mit einem kleinen Haus-Symbol (`mdi:home-thermometer-outline`) dargestellt, statt eine der Grafiken anzupassen.

Die **Puffer-Fühler** sind ein Sonderfall: Je nach Anlage hat PufferFlex zwischen 3 und 8 Fühlern, wofür sich nicht sinnvoll eine feste Karten-Vorlage pro Anzahl schreiben lässt. Statt eine feste Anzahl anzunehmen, enthält jede Puffer-Karte unten ein `markdown`-Element mit einem kleinen Jinja-Template, das direkt über der Pufferspeicher-Grafik automatisch **genau so viele Fühler-Zeilen untereinander anzeigt, wie an deiner Anlage tatsächlich gefunden wurden** (3 bis 8) – ganz ohne Anpassung des YAML-Codes. Fühler 1 wird dabei immer als "(oben)", der letzte gefundene immer als "(unten)" beschriftet.

**Aschebox** und **FWM/WW** sind ebenfalls dynamisch: Die Aschebox-Beschriftung zeigt "Verbrauch/Schwellwert" kombiniert an (z. B. "459/1000kg"), und die FWM-Beschriftung zeigt Warmwasser- sowie (falls vorhanden) Zirkulationstemperatur - jeweils über ein kleines `markdown`-Element, das nur die tatsächlich vorhandenen Werte anzeigt.

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
    entity: sensor.eta_kessel_solltemperatur
    style:
      top: 12.7%
      left: 15%
      font-weight: bold
      font-size: 14px
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
    entity: sensor.eta_restsauerstoff
    style:
      top: 48.7%
      left: 20%
      font-weight: bold
      font-size: 14px
  # Zeigt "Verbrauch/Schwellwert" kombiniert an, z.B. "459/1000kg"
  - type: markdown
    style:
      top: 41.3%
      left: 15%
      font-weight: bold
      font-size: 14px
    content: |
      {%- if has_value('sensor.eta_aschebox_verbrauch_seit_leerung') and has_value('sensor.eta_aschebox_leeren_nach') -%}
      {{ states('sensor.eta_aschebox_verbrauch_seit_leerung') | float | round(0) | int }}/{{ states('sensor.eta_aschebox_leeren_nach') | float | round(0) | int }}{{ state_attr('sensor.eta_aschebox_leeren_nach', 'unit_of_measurement') }}
      {%- endif -%}
  - type: icon
    icon: mdi:home-thermometer-outline
    style:
      top: 6%
      left: 88%
      color: white
      text-shadow: 1px 1px 2px black
  - type: state-label
    entity: sensor.eta_aussentemperatur
    style:
      top: 6%
      left: 95%
      color: white
      font-weight: bold
      font-size: 14px
      text-shadow: 1px 1px 2px black
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
    entity: sensor.eta_kessel_solltemperatur
    style:
      top: 12.7%
      left: 15%
      font-weight: bold
      font-size: 14px
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
    entity: sensor.eta_restsauerstoff
    style:
      top: 48.7%
      left: 20%
      font-weight: bold
      font-size: 14px
  # Zeigt "Verbrauch/Schwellwert" kombiniert an, z.B. "459/1000kg"
  - type: markdown
    style:
      top: 41.3%
      left: 15%
      font-weight: bold
      font-size: 14px
    content: |
      {%- if has_value('sensor.eta_aschebox_verbrauch_seit_leerung') and has_value('sensor.eta_aschebox_leeren_nach') -%}
      {{ states('sensor.eta_aschebox_verbrauch_seit_leerung') | float | round(0) | int }}/{{ states('sensor.eta_aschebox_leeren_nach') | float | round(0) | int }}{{ state_attr('sensor.eta_aschebox_leeren_nach', 'unit_of_measurement') }}
      {%- endif -%}
  - type: state-label
    entity: sensor.eta_puffer_ladezustand
    style:
      top: 12.7%
      left: 45%
      font-weight: bold
      font-size: 16px
  # Zeigt automatisch alle tatsächlich vorhandenen Pufferfühler (3-8) untereinander an
  - type: markdown
    style:
      top: 58%
      left: 38%
      width: 30%
      color: white
      font-weight: bold
      font-size: 12px
      text-align: center
      text-shadow: 1px 1px 2px black
    content: |
      {%- set valid = namespace(list=[]) -%}
      {%- for n in range(1, 9) -%}
        {%- if has_value('sensor.eta_puffer_fuehler_' ~ n) -%}
          {%- set valid.list = valid.list + [n] -%}
        {%- endif -%}
      {%- endfor -%}
      {%- for n in valid.list -%}
        {%- set eid = 'sensor.eta_puffer_fuehler_' ~ n -%}
        {%- if n == valid.list[0] -%}
          {%- set suffix = ' (oben)' -%}
        {%- elif n == valid.list[-1] -%}
          {%- set suffix = ' (unten)' -%}
        {%- else -%}
          {%- set suffix = '' -%}
        {%- endif -%}
        {%- if not loop.first -%}<br>{%- endif -%}
        **Fühler {{ n }}{{ suffix }}:** {{ states(eid) }} {{ state_attr(eid, 'unit_of_measurement') }}
      {%- endfor -%}
  - type: icon
    icon: mdi:home-thermometer-outline
    style:
      top: 6%
      left: 88%
      color: white
      text-shadow: 1px 1px 2px black
  - type: state-label
    entity: sensor.eta_aussentemperatur
    style:
      top: 6%
      left: 95%
      color: white
      font-weight: bold
      font-size: 14px
      text-shadow: 1px 1px 2px black
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
    entity: sensor.eta_kessel_solltemperatur
    style:
      top: 12.7%
      left: 15%
      font-weight: bold
      font-size: 14px
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
    entity: sensor.eta_restsauerstoff
    style:
      top: 48.7%
      left: 20%
      font-weight: bold
      font-size: 14px
  # Zeigt "Verbrauch/Schwellwert" kombiniert an, z.B. "459/1000kg"
  - type: markdown
    style:
      top: 41.3%
      left: 15%
      font-weight: bold
      font-size: 14px
    content: |
      {%- if has_value('sensor.eta_aschebox_verbrauch_seit_leerung') and has_value('sensor.eta_aschebox_leeren_nach') -%}
      {{ states('sensor.eta_aschebox_verbrauch_seit_leerung') | float | round(0) | int }}/{{ states('sensor.eta_aschebox_leeren_nach') | float | round(0) | int }}{{ state_attr('sensor.eta_aschebox_leeren_nach', 'unit_of_measurement') }}
      {%- endif -%}
  - type: state-label
    entity: sensor.eta_puffer_ladezustand
    style:
      top: 12.7%
      left: 45%
      font-weight: bold
      font-size: 16px
  # Zeigt automatisch alle tatsächlich vorhandenen Pufferfühler (3-8) untereinander an
  - type: markdown
    style:
      top: 58%
      left: 38%
      width: 30%
      color: white
      font-weight: bold
      font-size: 12px
      text-align: center
      text-shadow: 1px 1px 2px black
    content: |
      {%- set valid = namespace(list=[]) -%}
      {%- for n in range(1, 9) -%}
        {%- if has_value('sensor.eta_puffer_fuehler_' ~ n) -%}
          {%- set valid.list = valid.list + [n] -%}
        {%- endif -%}
      {%- endfor -%}
      {%- for n in valid.list -%}
        {%- set eid = 'sensor.eta_puffer_fuehler_' ~ n -%}
        {%- if n == valid.list[0] -%}
          {%- set suffix = ' (oben)' -%}
        {%- elif n == valid.list[-1] -%}
          {%- set suffix = ' (unten)' -%}
        {%- else -%}
          {%- set suffix = '' -%}
        {%- endif -%}
        {%- if not loop.first -%}<br>{%- endif -%}
        **Fühler {{ n }}{{ suffix }}:** {{ states(eid) }} {{ state_attr(eid, 'unit_of_measurement') }}
      {%- endfor -%}
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
  - type: icon
    icon: mdi:home-thermometer-outline
    style:
      top: 6%
      left: 88%
      color: white
      text-shadow: 1px 1px 2px black
  - type: state-label
    entity: sensor.eta_aussentemperatur
    style:
      top: 6%
      left: 95%
      color: white
      font-weight: bold
      font-size: 14px
      text-shadow: 1px 1px 2px black
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
    entity: sensor.eta_kessel_solltemperatur
    style:
      top: 12.7%
      left: 15%
      font-weight: bold
      font-size: 14px
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
    entity: sensor.eta_restsauerstoff
    style:
      top: 48.7%
      left: 20%
      font-weight: bold
      font-size: 14px
  # Zeigt "Verbrauch/Schwellwert" kombiniert an, z.B. "459/1000kg"
  - type: markdown
    style:
      top: 41.3%
      left: 15%
      font-weight: bold
      font-size: 14px
    content: |
      {%- if has_value('sensor.eta_aschebox_verbrauch_seit_leerung') and has_value('sensor.eta_aschebox_leeren_nach') -%}
      {{ states('sensor.eta_aschebox_verbrauch_seit_leerung') | float | round(0) | int }}/{{ states('sensor.eta_aschebox_leeren_nach') | float | round(0) | int }}{{ state_attr('sensor.eta_aschebox_leeren_nach', 'unit_of_measurement') }}
      {%- endif -%}
  - type: state-label
    entity: sensor.eta_puffer_ladezustand
    style:
      top: 12.7%
      left: 45%
      font-weight: bold
      font-size: 16px
  # Zeigt automatisch alle tatsächlich vorhandenen Pufferfühler (3-8) untereinander an
  - type: markdown
    style:
      top: 58%
      left: 38%
      width: 30%
      color: white
      font-weight: bold
      font-size: 12px
      text-align: center
      text-shadow: 1px 1px 2px black
    content: |
      {%- set valid = namespace(list=[]) -%}
      {%- for n in range(1, 9) -%}
        {%- if has_value('sensor.eta_puffer_fuehler_' ~ n) -%}
          {%- set valid.list = valid.list + [n] -%}
        {%- endif -%}
      {%- endfor -%}
      {%- for n in valid.list -%}
        {%- set eid = 'sensor.eta_puffer_fuehler_' ~ n -%}
        {%- if n == valid.list[0] -%}
          {%- set suffix = ' (oben)' -%}
        {%- elif n == valid.list[-1] -%}
          {%- set suffix = ' (unten)' -%}
        {%- else -%}
          {%- set suffix = '' -%}
        {%- endif -%}
        {%- if not loop.first -%}<br>{%- endif -%}
        **Fühler {{ n }}{{ suffix }}:** {{ states(eid) }} {{ state_attr(eid, 'unit_of_measurement') }}
      {%- endfor -%}
  # Zeigt Warmwasser- und (falls vorhanden) Zirkulationstemperatur an
  - type: markdown
    style:
      top: 12.7%
      left: 65%
      color: white
      font-weight: bold
      font-size: 14px
      text-align: center
      text-shadow: 1px 1px 2px black
    content: |
      {%- set lines = [] -%}
      {%- if has_value('sensor.eta_fwm_warmwassertemperatur') -%}
        {%- set lines = lines + [states('sensor.eta_fwm_warmwassertemperatur') ~ ' ' ~ state_attr('sensor.eta_fwm_warmwassertemperatur', 'unit_of_measurement')] -%}
      {%- endif -%}
      {%- if has_value('sensor.eta_fwm_zirkulation') -%}
        {%- set lines = lines + [states('sensor.eta_fwm_zirkulation') ~ ' ' ~ state_attr('sensor.eta_fwm_zirkulation', 'unit_of_measurement') ~ ' (Zirk.)'] -%}
      {%- endif -%}
      {{ lines | join('<br>') }}
  - type: icon
    icon: mdi:home-thermometer-outline
    style:
      top: 6%
      left: 88%
      color: white
      text-shadow: 1px 1px 2px black
  - type: state-label
    entity: sensor.eta_aussentemperatur
    style:
      top: 6%
      left: 95%
      color: white
      font-weight: bold
      font-size: 14px
      text-shadow: 1px 1px 2px black
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
    entity: sensor.eta_kessel_solltemperatur
    style:
      top: 12.7%
      left: 15%
      font-weight: bold
      font-size: 14px
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
    entity: sensor.eta_restsauerstoff
    style:
      top: 48.7%
      left: 20%
      font-weight: bold
      font-size: 14px
  # Zeigt "Verbrauch/Schwellwert" kombiniert an, z.B. "459/1000kg"
  - type: markdown
    style:
      top: 41.3%
      left: 15%
      font-weight: bold
      font-size: 14px
    content: |
      {%- if has_value('sensor.eta_aschebox_verbrauch_seit_leerung') and has_value('sensor.eta_aschebox_leeren_nach') -%}
      {{ states('sensor.eta_aschebox_verbrauch_seit_leerung') | float | round(0) | int }}/{{ states('sensor.eta_aschebox_leeren_nach') | float | round(0) | int }}{{ state_attr('sensor.eta_aschebox_leeren_nach', 'unit_of_measurement') }}
      {%- endif -%}
  - type: state-label
    entity: sensor.eta_puffer_ladezustand
    style:
      top: 12.7%
      left: 45%
      font-weight: bold
      font-size: 16px
  # Zeigt automatisch alle tatsächlich vorhandenen Pufferfühler (3-8) untereinander an
  - type: markdown
    style:
      top: 58%
      left: 38%
      width: 30%
      color: white
      font-weight: bold
      font-size: 12px
      text-align: center
      text-shadow: 1px 1px 2px black
    content: |
      {%- set valid = namespace(list=[]) -%}
      {%- for n in range(1, 9) -%}
        {%- if has_value('sensor.eta_puffer_fuehler_' ~ n) -%}
          {%- set valid.list = valid.list + [n] -%}
        {%- endif -%}
      {%- endfor -%}
      {%- for n in valid.list -%}
        {%- set eid = 'sensor.eta_puffer_fuehler_' ~ n -%}
        {%- if n == valid.list[0] -%}
          {%- set suffix = ' (oben)' -%}
        {%- elif n == valid.list[-1] -%}
          {%- set suffix = ' (unten)' -%}
        {%- else -%}
          {%- set suffix = '' -%}
        {%- endif -%}
        {%- if not loop.first -%}<br>{%- endif -%}
        **Fühler {{ n }}{{ suffix }}:** {{ states(eid) }} {{ state_attr(eid, 'unit_of_measurement') }}
      {%- endfor -%}
  # Zeigt Warmwasser- und (falls vorhanden) Zirkulationstemperatur an
  - type: markdown
    style:
      top: 12.7%
      left: 65%
      color: white
      font-weight: bold
      font-size: 14px
      text-align: center
      text-shadow: 1px 1px 2px black
    content: |
      {%- set lines = [] -%}
      {%- if has_value('sensor.eta_fwm_warmwassertemperatur') -%}
        {%- set lines = lines + [states('sensor.eta_fwm_warmwassertemperatur') ~ ' ' ~ state_attr('sensor.eta_fwm_warmwassertemperatur', 'unit_of_measurement')] -%}
      {%- endif -%}
      {%- if has_value('sensor.eta_fwm_zirkulation') -%}
        {%- set lines = lines + [states('sensor.eta_fwm_zirkulation') ~ ' ' ~ state_attr('sensor.eta_fwm_zirkulation', 'unit_of_measurement') ~ ' (Zirk.)'] -%}
      {%- endif -%}
      {{ lines | join('<br>') }}
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
  - type: icon
    icon: mdi:home-thermometer-outline
    style:
      top: 6%
      left: 88%
      color: white
      text-shadow: 1px 1px 2px black
  - type: state-label
    entity: sensor.eta_aussentemperatur
    style:
      top: 6%
      left: 95%
      color: white
      font-weight: bold
      font-size: 14px
      text-shadow: 1px 1px 2px black
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
    entity: sensor.eta_kessel_solltemperatur
    style:
      top: 12.7%
      left: 15%
      font-weight: bold
      font-size: 14px
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
    entity: sensor.eta_restsauerstoff
    style:
      top: 48.7%
      left: 20%
      font-weight: bold
      font-size: 14px
  # Zeigt "Verbrauch/Schwellwert" kombiniert an, z.B. "459/1000kg"
  - type: markdown
    style:
      top: 41.3%
      left: 15%
      font-weight: bold
      font-size: 14px
    content: |
      {%- if has_value('sensor.eta_aschebox_verbrauch_seit_leerung') and has_value('sensor.eta_aschebox_leeren_nach') -%}
      {{ states('sensor.eta_aschebox_verbrauch_seit_leerung') | float | round(0) | int }}/{{ states('sensor.eta_aschebox_leeren_nach') | float | round(0) | int }}{{ state_attr('sensor.eta_aschebox_leeren_nach', 'unit_of_measurement') }}
      {%- endif -%}
  - type: state-label
    entity: sensor.eta_puffer_ladezustand
    style:
      top: 12.7%
      left: 45%
      font-weight: bold
      font-size: 16px
  # Zeigt automatisch alle tatsächlich vorhandenen Pufferfühler (3-8) untereinander an
  - type: markdown
    style:
      top: 58%
      left: 38%
      width: 30%
      color: white
      font-weight: bold
      font-size: 12px
      text-align: center
      text-shadow: 1px 1px 2px black
    content: |
      {%- set valid = namespace(list=[]) -%}
      {%- for n in range(1, 9) -%}
        {%- if has_value('sensor.eta_puffer_fuehler_' ~ n) -%}
          {%- set valid.list = valid.list + [n] -%}
        {%- endif -%}
      {%- endfor -%}
      {%- for n in valid.list -%}
        {%- set eid = 'sensor.eta_puffer_fuehler_' ~ n -%}
        {%- if n == valid.list[0] -%}
          {%- set suffix = ' (oben)' -%}
        {%- elif n == valid.list[-1] -%}
          {%- set suffix = ' (unten)' -%}
        {%- else -%}
          {%- set suffix = '' -%}
        {%- endif -%}
        {%- if not loop.first -%}<br>{%- endif -%}
        **Fühler {{ n }}{{ suffix }}:** {{ states(eid) }} {{ state_attr(eid, 'unit_of_measurement') }}
      {%- endfor -%}
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
  - type: state-label
    entity: sensor.eta_heizkreis_2_vorlauftemperatur
    style:
      top: 27.0%
      left: 67%
      font-weight: bold
      font-size: 16px
  - type: state-label
    entity: sensor.eta_heizkreis_2_anforderung
    style:
      top: 34.7%
      left: 72%
      font-weight: bold
      font-size: 16px
  - type: icon
    icon: mdi:home-thermometer-outline
    style:
      top: 6%
      left: 88%
      color: white
      text-shadow: 1px 1px 2px black
  - type: state-label
    entity: sensor.eta_aussentemperatur
    style:
      top: 6%
      left: 95%
      color: white
      font-weight: bold
      font-size: 14px
      text-shadow: 1px 1px 2px black
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
    entity: sensor.eta_kessel_solltemperatur
    style:
      top: 12.7%
      left: 15%
      font-weight: bold
      font-size: 14px
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
    entity: sensor.eta_restsauerstoff
    style:
      top: 48.7%
      left: 20%
      font-weight: bold
      font-size: 14px
  # Zeigt "Verbrauch/Schwellwert" kombiniert an, z.B. "459/1000kg"
  - type: markdown
    style:
      top: 41.3%
      left: 15%
      font-weight: bold
      font-size: 14px
    content: |
      {%- if has_value('sensor.eta_aschebox_verbrauch_seit_leerung') and has_value('sensor.eta_aschebox_leeren_nach') -%}
      {{ states('sensor.eta_aschebox_verbrauch_seit_leerung') | float | round(0) | int }}/{{ states('sensor.eta_aschebox_leeren_nach') | float | round(0) | int }}{{ state_attr('sensor.eta_aschebox_leeren_nach', 'unit_of_measurement') }}
      {%- endif -%}
  - type: state-label
    entity: sensor.eta_puffer_ladezustand
    style:
      top: 12.7%
      left: 45%
      font-weight: bold
      font-size: 16px
  # Zeigt automatisch alle tatsächlich vorhandenen Pufferfühler (3-8) untereinander an
  - type: markdown
    style:
      top: 58%
      left: 38%
      width: 30%
      color: white
      font-weight: bold
      font-size: 12px
      text-align: center
      text-shadow: 1px 1px 2px black
    content: |
      {%- set valid = namespace(list=[]) -%}
      {%- for n in range(1, 9) -%}
        {%- if has_value('sensor.eta_puffer_fuehler_' ~ n) -%}
          {%- set valid.list = valid.list + [n] -%}
        {%- endif -%}
      {%- endfor -%}
      {%- for n in valid.list -%}
        {%- set eid = 'sensor.eta_puffer_fuehler_' ~ n -%}
        {%- if n == valid.list[0] -%}
          {%- set suffix = ' (oben)' -%}
        {%- elif n == valid.list[-1] -%}
          {%- set suffix = ' (unten)' -%}
        {%- else -%}
          {%- set suffix = '' -%}
        {%- endif -%}
        {%- if not loop.first -%}<br>{%- endif -%}
        **Fühler {{ n }}{{ suffix }}:** {{ states(eid) }} {{ state_attr(eid, 'unit_of_measurement') }}
      {%- endfor -%}
  # Zeigt Warmwasser- und (falls vorhanden) Zirkulationstemperatur an
  - type: markdown
    style:
      top: 12.7%
      left: 65%
      color: white
      font-weight: bold
      font-size: 14px
      text-align: center
      text-shadow: 1px 1px 2px black
    content: |
      {%- set lines = [] -%}
      {%- if has_value('sensor.eta_fwm_warmwassertemperatur') -%}
        {%- set lines = lines + [states('sensor.eta_fwm_warmwassertemperatur') ~ ' ' ~ state_attr('sensor.eta_fwm_warmwassertemperatur', 'unit_of_measurement')] -%}
      {%- endif -%}
      {%- if has_value('sensor.eta_fwm_zirkulation') -%}
        {%- set lines = lines + [states('sensor.eta_fwm_zirkulation') ~ ' ' ~ state_attr('sensor.eta_fwm_zirkulation', 'unit_of_measurement') ~ ' (Zirk.)'] -%}
      {%- endif -%}
      {{ lines | join('<br>') }}
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
  - type: state-label
    entity: sensor.eta_heizkreis_2_vorlauftemperatur
    style:
      top: 27.0%
      left: 86%
      font-weight: bold
      font-size: 14px
  - type: state-label
    entity: sensor.eta_heizkreis_2_anforderung
    style:
      top: 34.7%
      left: 90%
      font-weight: bold
      font-size: 14px
  - type: icon
    icon: mdi:home-thermometer-outline
    style:
      top: 6%
      left: 88%
      color: white
      text-shadow: 1px 1px 2px black
  - type: state-label
    entity: sensor.eta_aussentemperatur
    style:
      top: 6%
      left: 95%
      color: white
      font-weight: bold
      font-size: 14px
      text-shadow: 1px 1px 2px black
```

> 💡 `top`/`left` verankern in Lovelace standardmäßig die **Mitte** des Elements. Solltest du eine andere Home-Assistant-Theme, Bildschirmgröße oder Kartenbreite verwenden, kannst du die Werte im visuellen Editor per Drag & Drop feinjustieren.

---

## 📄 Lizenz

Dieses Projekt ist unter der MIT-Lizenz lizenziert – siehe die [LICENSE](LICENSE) Datei für Details.
