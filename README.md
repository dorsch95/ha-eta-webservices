# ETA Heiztechnik Web Service Integration für Home Assistant

[![hacs_badge](https://shields.io)](https://github.com)
[![License: MIT](https://shields.io)](LICENSE)

Diese benutzerdefinierte Integration ermöglicht es, Daten von **ETA Heizsystemen** (Pelletkessel, Stückholzkessel, Hackgut, Puffer- und Solarspeicher sowie Frischwassermodule) komplett lokal über die integrierten RESTful Webservices (ETAtouch) auszulesen.

⚡ Das Anlagenschema wird direkt im UI-Setup ausgewählt und die passenden Grafiken werden vollautomatisch im Hintergrund generiert.

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
   `https://github.com`
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

---

## 📊 Unterstützte Sensoren

Folgende Entitäten werden (sofern physisch an deiner Anlage angeschlossen) mit festen, optimierten Pfaden ausgelesen:

* **🔥 Kessel & Umgebung:** Kesseltemperatur, Rücklauftemperatur, Kesseldruck (bar), Außentemperatur, Inhalt Pellet-Tagesbehälter (kg).
* **🛢️ Pufferspeicher:** Puffer-Ladezustand (%), Fühler 1 (oben), Fühler 2, Fühler 3, Fühler 4, Fühler 5 (unten).
* **♨️ Heizkreis:** Vorlauftemperatur, Anforderung (Zustandstext wie *Aus*, *Heizbetrieb* etc.).
* **🚰 Frischwassermodul (FWM):** Warmwassertemperatur.

---

## 📺 Dashboard-Vorlage für Lovelace (Bild-Elemente)

Durch die automatische Base64-Bildgenerierung musst du keine Grafiken mehr manuell auf deinen Server kopieren. Erstelle einfach eine neue Karte vom Typ **Manuell (Umschalten auf Code-Editor)** und füge diesen YAML-Code ein. Das Hintergrundbild passt sich exakt dem im Setup gewählten Schema an:

```yaml
type: picture-elements
image: /local/community/ha-eta-webservices/kessel.png
elements:
  # --- DYNAMISCHER SCHEMAWECHSEL (HINTERGRUND) ---
  - type: image
    entity: sensor.eta_anlagenbild_pfad
    state_image:
      kessel: /local/community/ha-eta-webservices/kessel.png
      kessel_puffer: /local/community/ha-eta-webservices/kessel_puffer.png
      kessel_puffer_hk1: /local/community/ha-eta-webservices/kessel_puffer_hk1.png
      kessel_puffer_fwm: /local/community/ha-eta-webservices/kessel_puffer_fwm.png
      kessel_puffer_hk1_fwm: /local/community/ha-eta-webservices/kessel_puffer_hk1_fwm.png
      kessel_puffer_hk2: /local/community/ha-eta-webservices/kessel_puffer_hk2.png
      kessel_puffer_hk2_fwm: /local/community/ha-eta-webservices/kessel_puffer_hk2_fwm.png
    style:
      top: 50%
      left: 50%
      width: 100%
      height: 100%

  # --- MESSWERTE PLATZIEREN (Beispiele, Werte für top/left frei anpassen) ---
  - type: state-label
    entity: sensor.eta_kesseltemperatur
    style:
      top: 25%
      left: 20%
      font-weight: bold
      font-size: 16px

  - type: state-label
    entity: sensor.eta_puffer_ladezustand
    style:
      top: 15%
      left: 50%
      font-weight: bold

  - type: state-label
    entity: sensor.eta_heizkreis_anforderung
    style:
      top: 32%
      left: 80%
```

---

## 📄 Lizenz

Dieses Projekt ist unter der MIT-Lizenz lizenziert – siehe die [LICENSE](LICENSE) Datei für Details.
