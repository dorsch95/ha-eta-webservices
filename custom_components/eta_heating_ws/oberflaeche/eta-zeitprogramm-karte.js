/**
 * ETA Zeitprogramm - Dashboard-Karte der Integration ETA Web-Services.
 *
 * Zeigt die Heizzeiten jedes Heizkreises als Wochenbalken, auf Wunsch
 * auch die Ladezeiten des Puffers und die Zeiten fürs Warmwasser. Ein Tipp
 * auf einen Tag öffnet ihn zum Bearbeiten; die Änderung lässt sich auf
 * weitere Tage übernehmen. Gelesen und geschrieben wird über die Websocket-Befehle
 * der Integration, siehe zeitprogramm.py. Home Assistant lädt die Karte in
 * jedem Dashboard von selbst.
 */

const KARTE = "eta-zeitprogramm-karte";
const TAGE = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"];
const FENSTER_JE_TAG = 3;
const NEU_LESEN_NACH = 60000;

const TEXTE = {
  de: {
    titel: "Zeitprogramm",
    laden: "Zeitprogramm wird von der Heizung gelesen …",
    keins:
      "Kein Zeitprogramm zum Bearbeiten gefunden. Dafür muss in den Einstellungen " +
      "der ETA-Integration der Schreibzugriff eingeschaltet sein.",
    nicht_lesbar: "Das Zeitprogramm ließ sich nicht lesen:",
    erneut: "Erneut versuchen",
    neu_lesen: "Neu lesen",
    gesteuert: (name) =>
      `Wird vom Zeitplan „${name}“ vorgegeben. Änderungen bitte dort vornehmen.`,
    zeitplan_oeffnen: "Zeitplan öffnen",
    gesperrt: (name) =>
      `Dieser Heizkreis folgt dem Zeitplan „${name}“. Zum Ändern direkt in der Karte ` +
      "unter Einstellungen → Geräte & Dienste → ETA Web-Services → Konfigurieren " +
      "die Auswahl des Zeitplans leeren.",
    absenkung: "ganztägig Absenkung",
    tippen: "Zum Ändern einen Tag antippen.",
    fenster: "Zeitfenster",
    von: "von",
    bis: "bis",
    hinzufuegen: "+ Zeitfenster",
    entfernen: "Zeitfenster entfernen",
    leer: "Ohne Zeitfenster gilt den ganzen Tag die Absenkung.",
    leer_laden: "Ohne Zeitfenster gilt an diesem Tag den ganzen Tag der Wert außerhalb.",
    keine_fenster: "keine Zeitfenster",
    gilt_fuer: "Gilt für",
    werktage: "Mo–Fr",
    wochenende: "Sa–So",
    alle: "Alle Tage",
    abbrechen: "Abbrechen",
    speichern: "Speichern",
    speichert: "Wird gespeichert …",
    gespeichert: "Gespeichert",
    fehler_reihenfolge: "„bis“ muss nach „von“ liegen.",
    fehler_ueberlappung: "Zeitfenster dürfen sich nicht überschneiden.",
    fehler_temperatur: (min, max) => `Temperatur zwischen ${min} und ${max} °C.`,
    fehler_tage: "Mindestens einen Tag wählen.",
    fehler_absenkung: (min, max) => `Außerhalb der Zeitfenster zwischen ${min} und ${max} °C.`,
    sonst: (wert) => `sonst ${wert} °C`,
    absenk_feld: "Außerhalb der Zeitfenster",
    kurz: ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"],
    karte_beschreibung: "Heizzeiten der ETA-Heizung ansehen und ändern.",
    feld_titel: "Titel",
    feld_heizkreis: "Heizkreis (leer: alle)",
    feld_anzeigen: "Anzeigen",
    art_heizzeiten: "Heizzeiten",
    art_puffer: "Ladezeiten Puffer",
    art_warmwasser: "Warmwasser",
    feld_farbe_heizzeit: "Farbe Heizzeit",
    feld_farbe_absenkzeit: "Farbe Absenkzeit",
  },
  en: {
    titel: "Heating schedule",
    laden: "Reading the schedule from the boiler …",
    keins:
      "No editable schedule found. Write access has to be enabled in the options " +
      "of the ETA integration.",
    nicht_lesbar: "The schedule could not be read:",
    erneut: "Try again",
    neu_lesen: "Read again",
    gesteuert: (name) => `Set by the schedule “${name}”. Please make changes there.`,
    zeitplan_oeffnen: "Open schedule",
    gesperrt: (name) =>
      `This heating circuit follows the schedule “${name}”. To edit it in this card, ` +
      "clear the schedule under Settings → Devices & services → ETA Web-Services → Configure.",
    absenkung: "setback all day",
    tippen: "Tap a day to change it.",
    fenster: "Time slot",
    von: "from",
    bis: "to",
    hinzufuegen: "+ Time slot",
    entfernen: "Remove time slot",
    leer: "Without time slots the setback applies all day.",
    leer_laden: "Without time slots the value outside the slots applies all day.",
    keine_fenster: "no time slots",
    gilt_fuer: "Apply to",
    werktage: "Mon–Fri",
    wochenende: "Sat–Sun",
    alle: "All days",
    abbrechen: "Cancel",
    speichern: "Save",
    speichert: "Saving …",
    gespeichert: "Saved",
    fehler_reihenfolge: "“to” has to be after “from”.",
    fehler_ueberlappung: "Time slots must not overlap.",
    fehler_temperatur: (min, max) => `Temperature between ${min} and ${max} °C.`,
    fehler_tage: "Choose at least one day.",
    fehler_absenkung: (min, max) => `Outside the time slots between ${min} and ${max} °C.`,
    sonst: (wert) => `otherwise ${wert} °C`,
    absenk_feld: "Outside the time slots",
    kurz: ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"],
    karte_beschreibung: "View and change the heating times of the ETA boiler.",
    feld_titel: "Title",
    feld_heizkreis: "Heating circuit (empty: all)",
    feld_anzeigen: "Show",
    art_heizzeiten: "Heating times",
    art_puffer: "Buffer loading times",
    art_warmwasser: "Hot water",
    feld_farbe_heizzeit: "Heating time colour",
    feld_farbe_absenkzeit: "Setback colour",
  },
};

const SYMBOL_NEU_LESEN =
  "M17.65,6.35C16.2,4.9 14.21,4 12,4A8,8 0 0,0 4,12A8,8 0 0,0 12,20C15.73,20 " +
  "18.84,17.45 19.73,14H17.65C16.83,16.33 14.61,18 12,18A6,6 0 0,1 6,12A6,6 0 0,1 " +
  "12,6C13.66,6 15.14,6.69 16.22,7.78L13,11H20V4L17.65,6.35Z";
const SYMBOL_ENTFERNEN =
  "M19,6.41L17.59,5L12,10.59L6.41,5L5,6.41L10.59,12L5,17.59L6.41,19L12,13.41L17.59," +
  "19L19,17.59L13.41,12L19,6.41Z";

const THEMENFARBEN = new Set([
  "primary", "accent", "disabled", "red", "pink", "purple", "deep-purple", "indigo", "blue",
  "light-blue", "cyan", "teal", "green", "light-green", "lime", "yellow", "amber", "orange",
  "deep-orange", "brown", "light-grey", "grey", "dark-grey", "blue-grey", "black", "white",
]);

const STIL = `
  :host {
    display: block;
    --eta-gelb: #ffa100;
    --eta-grau: #474a50;
    --eta-leer: color-mix(in srgb, var(--eta-grau) 16%, transparent);
    --eta-akzent: var(--eta-grau);
    --eta-auf-gelb: var(--eta-grau);
  }
  .probe { display: none; }
  .probe.gelb { color: var(--eta-gelb); }
  .probe.grau { color: var(--eta-grau); }
  :host([dunkel]) {
    --eta-leer: var(--eta-grau);
    --eta-akzent: var(--eta-gelb);
  }
  ha-card { padding: 12px 16px 16px; container-type: inline-size; }
  button { font: inherit; cursor: pointer; }
  .kopf { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
  .titel {
    font-size: var(--ha-card-header-font-size, 1.25rem);
    color: var(--ha-card-header-color, var(--primary-text-color));
    line-height: 1.6;
  }
  .symbol {
    display: inline-flex; padding: 8px; border: none; border-radius: 50%;
    background: none; color: var(--secondary-text-color);
  }
  .symbol:hover { background: var(--secondary-background-color); }
  .symbol svg { width: 20px; height: 20px; fill: currentColor; }
  .hinweis { color: var(--secondary-text-color); padding: 8px 0; }
  .klein { font-size: 13px; }
  .unterkopf { font-weight: 500; margin: 12px 0 4px; }
  .gesteuert {
    margin: 4px 0 8px; padding: 8px 12px; border-radius: 8px;
    background: var(--secondary-background-color); font-size: 14px;
  }
  .fehler { color: var(--error-color, #db4437); }
  .ok { color: var(--success-color, #43a047); }
  .meldung { font-size: 13px; padding: 2px 0 6px 40px; }
  .skala {
    position: relative; height: 16px; margin-left: 40px;
    font-size: 11px; color: var(--secondary-text-color);
  }
  .skala span { position: absolute; transform: translateX(-50%); }
  .skala span:first-child { transform: none; }
  .skala span:last-child { transform: translateX(-100%); }
  .tag {
    display: grid; grid-template-columns: 32px 1fr; column-gap: 8px; row-gap: 2px;
    align-items: center; margin: 0 -6px; padding: 6px; border-radius: 8px;
    cursor: pointer; outline: none;
  }
  .tag:hover, .tag:focus-visible, .tag.offen { background: var(--secondary-background-color); }
  .tag.gesperrt:hover { background: none; }
  .meldung.hinweis { color: var(--secondary-text-color); }
  .kurz { font-weight: 500; }
  .kurz.heute {
    justify-self: start; padding: 0 5px; border-radius: 6px;
    background: var(--eta-gelb); color: var(--eta-auf-gelb);
  }
  .balken {
    position: relative; height: 14px; border-radius: 7px; overflow: hidden;
    background:
      repeating-linear-gradient(to right, transparent 0, transparent calc(25% - 1px),
        rgba(127, 127, 127, 0.35) calc(25% - 1px), rgba(127, 127, 127, 0.35) 25%),
      var(--eta-leer);
  }
  .block {
    position: absolute; top: 0; bottom: 0; border-radius: 7px;
    background: var(--eta-gelb);
  }
  .jetzt { position: absolute; top: 0; bottom: 0; width: 2px; background: var(--primary-text-color); }
  .text { grid-column: 2; font-size: 12px; color: var(--secondary-text-color); }
  .editor {
    display: flex; flex-direction: column; gap: 10px;
    margin: 4px 0 8px 40px; padding: 12px; border-radius: 12px;
    border: 1px solid var(--divider-color);
  }
  .zeile { display: flex; flex-direction: column; gap: 2px; }
  .nr {
    display: flex; align-items: center; justify-content: space-between; min-height: 28px;
    font-size: 13px; font-weight: 500;
  }
  .nr .symbol { padding: 4px; margin-right: -4px; }
  .am-stueck { white-space: nowrap; }
  .felder {
    display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; max-width: 340px;
  }
  .felder.zwei { grid-template-columns: repeat(2, minmax(0, 1fr)); max-width: 226px; }
  .feld {
    display: flex; flex-direction: column; gap: 2px; min-width: 0;
    font-size: 12px; color: var(--secondary-text-color);
  }
  select, input {
    box-sizing: border-box; width: 100%; height: 38px; padding: 4px 6px; border-radius: 8px;
    font: inherit; font-size: 15px; border: 1px solid var(--divider-color);
    color: var(--primary-text-color); background: var(--card-background-color);
  }
  .absenk {
    display: flex; align-items: center; justify-content: space-between; gap: 8px;
    max-width: 340px; padding-top: 8px; border-top: 1px solid var(--divider-color);
    font-size: 13px; font-weight: 500;
  }
  .absenk .eingabe {
    display: flex; align-items: center; gap: 6px; flex: 0 0 auto;
    font-weight: 400; color: var(--secondary-text-color);
  }
  .absenk input { width: 5.5em; }
  .fest {
    display: flex; align-items: center; height: 38px; padding: 0 6px;
    font-size: 15px; color: var(--primary-text-color);
  }
  .text-knopf {
    align-self: flex-start; padding: 4px 0; border: none; background: none;
    color: var(--eta-akzent); font-weight: 500;
  }
  .tage-wahl { display: flex; flex-direction: column; gap: 6px; }
  .chips {
    display: grid; grid-template-columns: repeat(7, minmax(0, 1fr)); gap: 4px; max-width: 340px;
  }
  .chips.schnell { grid-template-columns: repeat(3, minmax(0, 1fr)); }
  .chip {
    min-width: 0; min-height: 34px; padding: 4px 2px; border-radius: 17px;
    border: 1px solid var(--divider-color); background: none; color: var(--primary-text-color);
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  }
  .chip.an {
    background: var(--eta-gelb); border-color: var(--eta-gelb);
    color: var(--eta-auf-gelb); font-weight: 500;
  }
  .knoepfe { display: flex; justify-content: flex-end; gap: 8px; }
  .flach {
    padding: 8px 12px; border: none; border-radius: 18px; background: none;
    color: var(--eta-akzent); font-weight: 500;
  }
  .haupt {
    min-height: 36px; padding: 8px 18px; border: none; border-radius: 18px;
    background: var(--eta-gelb); color: var(--eta-auf-gelb); font-weight: 500;
  }
  .haupt:disabled { opacity: 0.5; cursor: default; }
  .fuss { margin-top: 6px; font-size: 12px; color: var(--secondary-text-color); }
  @container (max-width: 440px) {
    .editor { margin-left: 0; }
    .meldung { padding-left: 0; }
  }
`;

function uhrzeit(viertel) {
  const stunden = String(Math.floor(viertel / 4)).padStart(2, "0");
  const minuten = String((viertel % 4) * 15).padStart(2, "0");
  return `${stunden}:${minuten}`;
}

function sicher(text) {
  return String(text ?? "").replace(
    /[&<>"']/g,
    (zeichen) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[zeichen]
  );
}

/** Eine Farbe aus den Einstellungen als CSS: Name der HA-Palette, eigener Wert oder [r, g, b]. */
function cssFarbe(wert) {
  if (Array.isArray(wert) && wert.length === 3) return `rgb(${wert.map(Number).join(", ")})`;
  if (typeof wert !== "string" || !wert.trim()) return null;
  return THEMENFARBEN.has(wert) ? `var(--${wert}-color)` : wert.trim();
}

function rgb(text) {
  const zahlen = String(text).match(/[\d.]+/g);
  return zahlen && zahlen.length >= 3 ? zahlen.slice(0, 3).map(Number) : null;
}

/** Relative Helligkeit nach WCAG, 0 (schwarz) bis 1 (weiß). */
function helligkeit(farbe) {
  const [r, g, b] = farbe.map((wert) => {
    const anteil = wert / 255;
    return anteil <= 0.03928 ? anteil / 12.92 : ((anteil + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function kontrast(a, b) {
  const [hell, dunkel] = [helligkeit(a), helligkeit(b)].sort((x, y) => y - x);
  return (hell + 0.05) / (dunkel + 0.05);
}

function uhrzeiten(von, bis, gewaehlt) {
  let html = "";
  for (let viertel = von; viertel <= bis; viertel += 1) {
    const an = viertel === gewaehlt ? " selected" : "";
    html += `<option value="${viertel}"${an}>${uhrzeit(viertel)}</option>`;
  }
  return html;
}

class EtaZeitprogrammKarte extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._konfig = {};
    this._programme = null;
    this._fehler = null;
    this._laedt = false;
    this._gelesen = 0;
    this._bearbeitung = null;
    this._speichert = false;
    this._meldung = null;
    this._sichtbar = () => {
      if (document.visibilityState === "visible") this._auffrischen();
    };
    this.shadowRoot.addEventListener("click", (e) => this._klick(e));
    this.shadowRoot.addEventListener("keydown", (e) => this._taste(e));
    this.shadowRoot.addEventListener("input", (e) => this._eingabe(e));
    this.shadowRoot.addEventListener("change", (e) => this._eingabe(e));
  }

  static getStubConfig() {
    return { anzeigen: ["heizzeiten"] };
  }

  static getConfigForm() {
    const t = TEXTE[sprache(document.documentElement.lang)];
    return {
      schema: [
        { name: "titel", selector: { text: {} } },
        {
          name: "heizkreis",
          selector: {
            select: {
              mode: "dropdown",
              options: ["hk1", "hk2", "hk3", "hk4"].map((wert, i) => ({
                value: wert,
                label: `HK ${i + 1}`,
              })),
            },
          },
        },
        {
          name: "anzeigen",
          selector: {
            select: {
              multiple: true,
              mode: "list",
              options: ["heizzeiten", "puffer", "warmwasser"].map((art) => ({
                value: art,
                label: t[`art_${art}`],
              })),
            },
          },
        },
        {
          name: "",
          type: "grid",
          schema: [
            { name: "farbe_heizzeit", selector: { ui_color: {} } },
            { name: "farbe_absenkzeit", selector: { ui_color: {} } },
          ],
        },
      ],
      computeLabel: (feld) => t[`feld_${feld.name}`],
    };
  }

  setConfig(konfig) {
    this._konfig = konfig || {};
    for (const [name, schluessel] of [["--eta-gelb", "farbe_heizzeit"], ["--eta-grau", "farbe_absenkzeit"]]) {
      const farbe = cssFarbe(this._konfig[schluessel]);
      if (farbe) this.style.setProperty(name, farbe);
      else this.style.removeProperty(name);
    }
    this._zeichnen();
  }

  set hass(hass) {
    const erstes = !this._hass;
    const dunkel = Boolean(hass?.themes?.darkMode);
    const gewechselt = dunkel !== this.hasAttribute("dunkel");
    this._hass = hass;
    this.toggleAttribute("dunkel", dunkel);
    if (gewechselt) this._lesbar();
    if (erstes) this._laden();
  }

  /**
   * Schrift, die auf den gewählten Farben lesbar bleibt.
   *
   * Auf Heizzeit-Farbe (Speichern, gewählte Tage, heute) Graphitgrau wie
   * bei ETA, sonst Schwarz oder Weiß. Textknöpfe im hellen Design in der
   * Absenkzeit-Farbe, im dunklen in der Heizzeit-Farbe - ist die zu blass,
   * in der normalen Schriftfarbe.
   */
  _lesbar() {
    const proben = [".probe.gelb", ".probe.grau"].map((art) => this.shadowRoot.querySelector(art));
    if (proben.some((probe) => !probe)) return;
    const [gelb, grau] = proben.map((probe) => rgb(getComputedStyle(probe).color));
    if (!gelb || !grau) return;
    const weiss = [255, 255, 255];
    const schwarz = [0, 0, 0];
    let auf;
    if (kontrast(gelb, grau) >= 3.5) auf = "var(--eta-grau)";
    else auf = kontrast(gelb, weiss) > kontrast(gelb, schwarz) ? "#ffffff" : "#000000";
    this.style.setProperty("--eta-auf-gelb", auf);
    const dunkel = this.hasAttribute("dunkel");
    const akzent = dunkel ? gelb : grau;
    const grund = dunkel ? [28, 28, 28] : weiss;
    this.style.setProperty(
      "--eta-akzent",
      kontrast(akzent, grund) >= 3 ? (dunkel ? "var(--eta-gelb)" : "var(--eta-grau)") : "var(--primary-text-color)"
    );
  }

  connectedCallback() {
    document.addEventListener("visibilitychange", this._sichtbar);
    this._auffrischen();
  }

  disconnectedCallback() {
    document.removeEventListener("visibilitychange", this._sichtbar);
  }

  getCardSize() {
    return 7;
  }

  getGridOptions() {
    return { columns: 12, min_columns: 6 };
  }

  get _t() {
    return TEXTE[sprache(this._hass?.locale?.language || this._hass?.language)];
  }

  _auffrischen() {
    if (this._hass && !this._bearbeitung && Date.now() - this._gelesen > NEU_LESEN_NACH) {
      this._laden();
    }
  }

  async _laden() {
    if (!this._hass || this._laedt) return;
    this._laedt = true;
    this._zeichnen();
    try {
      const antwort = await this._hass.callWS({ type: "eta_heating_ws/zeitprogramme" });
      this._programme = antwort.programme;
      this._fehler = null;
      this._gelesen = Date.now();
    } catch (err) {
      this._fehler = err?.message || String(err);
    }
    this._laedt = false;
    this._zeichnen();
  }

  /**
   * Was die Karte zeigt: ab Werk nur Heizzeiten. Unter "Anzeigen" lassen
   * sich Ladezeiten des Puffers und Warmwasser dazunehmen; "heizkreis"
   * wählt unter den Heizzeiten einen Heizkreis aus.
   */
  _auswahl() {
    const gesucht = String(this._konfig.heizkreis || "").toLowerCase();
    const anzeigen = this._konfig.anzeigen;
    const arten = Array.isArray(anzeigen) && anzeigen.length ? anzeigen : ["heizzeiten"];
    return (this._programme || []).filter((hk) => {
      const art = hk.art || "heizzeiten";
      if (!arten.includes(art)) return false;
      if (art !== "heizzeiten" || !gesucht) return true;
      return hk.programm.toLowerCase() === gesucht || hk.name.toLowerCase() === gesucht;
    });
  }

  _schluessel(hk) {
    return `${hk.eintrag}|${hk.programm}`;
  }

  _finden(schluessel) {
    return (this._programme || []).find((hk) => this._schluessel(hk) === schluessel);
  }

  _zahl(wert) {
    return new Intl.NumberFormat(this._hass?.locale?.language || "de", {
      minimumFractionDigits: 1,
      maximumFractionDigits: 1,
    }).format(wert);
  }

  _beschreibung(hk, tag) {
    const fenster = hk.tage[tag];
    const absenk = hk.absenkung?.[tag];
    const stueck = (text) => `<span class="am-stueck">${sicher(text)}</span>`;
    if (!fenster.length) {
      const zusatz = absenk == null ? "" : ` · ${this._zahl(absenk)} °C`;
      const text = hk.art && hk.art !== "heizzeiten" ? this._t.keine_fenster : this._t.absenkung;
      return stueck(`${text}${zusatz}`);
    }
    const teile = fenster.map((f) => {
      const zeit = `${uhrzeit(f.beginn)}–${uhrzeit(f.ende)}`;
      return stueck(f.temperatur == null ? zeit : `${zeit} · ${this._zahl(f.temperatur)} °C`);
    });
    if (absenk != null) teile.push(stueck(this._t.sonst(this._zahl(absenk))));
    return teile.join(", ");
  }

  _ersatztemperatur(hk) {
    for (const tag of TAGE) {
      const belegt = (hk.tage?.[tag] || []).find((f) => f.temperatur != null);
      if (belegt) return belegt.temperatur;
    }
    return Math.min(Math.max(20, hk.temperatur_min), hk.temperatur_max);
  }

  _zeichnen() {
    const t = this._t;
    const liste = this._auswahl();
    const titel =
      this._konfig.titel || (liste.length === 1 ? `${t.titel} · ${liste[0].name}` : t.titel);
    let inhalt;
    if (!this._programme) {
      inhalt = this._fehler
        ? `<div class="fehler">${t.nicht_lesbar} ${sicher(this._fehler)}</div>
           <button class="text-knopf" data-aktion="laden">${t.erneut}</button>`
        : `<div class="hinweis">${t.laden}</div>`;
    } else if (!liste.length) {
      inhalt = `<div class="hinweis">${t.keins}</div>`;
    } else {
      const anlagen = new Set(liste.map((hk) => hk.eintrag)).size;
      inhalt = liste.map((hk) => this._abschnitt(hk, liste.length > 1, anlagen > 1)).join("");
      if (!this._bearbeitung && liste.some((hk) => !hk.zeitplan && hk.tage)) {
        inhalt += `<div class="fuss">${t.tippen}</div>`;
      }
    }
    this.shadowRoot.innerHTML = `
      <style>${STIL}</style>
      <ha-card>
        <div class="kopf">
          <div class="titel">${sicher(titel)}</div>
          <button class="symbol" data-aktion="laden" title="${t.neu_lesen}"
            aria-label="${t.neu_lesen}" ${this._laedt ? "disabled" : ""}>
            <svg viewBox="0 0 24 24"><path d="${SYMBOL_NEU_LESEN}"></path></svg>
          </button>
        </div>
        ${inhalt}
      </ha-card>
      <span class="probe gelb"></span><span class="probe grau"></span>`;
    this._lesbar();
  }

  _abschnitt(hk, mehrere, anlagen) {
    const t = this._t;
    const schluessel = this._schluessel(hk);
    let html = "";
    if (mehrere) {
      const anlage = anlagen ? ` · ${sicher(hk.anlage)}` : "";
      html += `<div class="unterkopf">${sicher(hk.name)}${anlage}</div>`;
    }
    if (hk.fehler) {
      return `${html}
        <div class="fehler">${t.nicht_lesbar} ${sicher(hk.fehler)}</div>
        <button class="text-knopf" data-aktion="laden">${t.erneut}</button>`;
    }
    if (hk.zeitplan) {
      const name = this._hass?.states?.[hk.zeitplan]?.attributes?.friendly_name || hk.zeitplan;
      html += `<div class="gesteuert">${sicher(t.gesteuert(name))}
        <button class="text-knopf" data-aktion="zeitplan" data-entity="${sicher(hk.zeitplan)}">
          ${t.zeitplan_oeffnen}</button></div>`;
    }
    html += `<div class="skala"><span style="left:0">0</span><span style="left:25%">6</span>
      <span style="left:50%">12</span><span style="left:75%">18</span>
      <span style="left:100%">24</span></div>`;
    const jetzt = new Date();
    const heute = TAGE[(jetzt.getDay() + 6) % 7];
    const jetztAnteil = ((jetzt.getHours() * 60 + jetzt.getMinutes()) / 1440) * 100;
    TAGE.forEach((tag, i) => {
      const offen =
        this._bearbeitung?.schluessel === schluessel && this._bearbeitung?.tag === tag;
      const fenster = offen ? this._bearbeitung.fenster : hk.tage[tag];
      const klassen = ["tag", offen ? "offen" : "", hk.zeitplan ? "gesperrt" : ""].join(" ");
      const knopf = `role="button" tabindex="0" data-aktion="${hk.zeitplan ? "gesperrt" : "tag"}"`;
      html += `
        <div class="${klassen}" ${knopf} data-hk="${sicher(schluessel)}" data-tag="${tag}">
          <div class="kurz ${tag === heute ? "heute" : ""}">${t.kurz[i]}</div>
          <div class="balken">${this._bloecke(fenster)}${
            tag === heute ? `<div class="jetzt" style="left:${jetztAnteil}%"></div>` : ""
          }</div>
          <div class="text">${this._beschreibung(hk, tag)}</div>
        </div>`;
      if (offen) html += this._editor(hk);
      if (this._meldung?.schluessel === schluessel && this._meldung?.tag === tag && !offen) {
        html += `<div class="meldung ${this._meldung.art}">${sicher(this._meldung.text)}</div>`;
      }
    });
    return html;
  }

  _bloecke(fenster) {
    return fenster
      .filter((f) => f.ende > f.beginn)
      .map(
        (f) =>
          `<div class="block" style="left:${(f.beginn / 96) * 100}%;` +
          `width:${((f.ende - f.beginn) / 96) * 100}%"></div>`
      )
      .join("");
  }

  _editor(hk) {
    const t = this._t;
    const b = this._bearbeitung;
    const zeilen = b.fenster
      .map((f, i) => {
        let temperatur = "";
        if (hk.mit_temperatur && hk.temperatur_aenderbar) {
          temperatur = `<label class="feld"><span>°C</span><input type="number" inputmode="decimal"
               step="0.5" min="${hk.temperatur_min}" max="${hk.temperatur_max}"
               value="${Number.isFinite(f.temperatur) ? f.temperatur : ""}"
               data-feld="temperatur" data-index="${i}"></label>`;
        } else if (hk.mit_temperatur) {
          const wert = Number.isFinite(f.temperatur) ? this._zahl(f.temperatur) : "–";
          temperatur = `<div class="feld"><span>°C</span><span class="fest">${wert}</span></div>`;
        }
        return `
          <div class="zeile">
            <div class="nr">
              <span>${t.fenster} ${i + 1}</span>
              <button class="symbol" data-aktion="entfernen" data-index="${i}"
                title="${t.entfernen}" aria-label="${t.entfernen}">
                <svg viewBox="0 0 24 24"><path d="${SYMBOL_ENTFERNEN}"></path></svg>
              </button>
            </div>
            <div class="felder ${hk.mit_temperatur ? "" : "zwei"}">
              <label class="feld"><span>${t.von}</span>
                <select data-feld="beginn" data-index="${i}">${uhrzeiten(0, 95, f.beginn)}</select>
              </label>
              <label class="feld"><span>${t.bis}</span>
                <select data-feld="ende" data-index="${i}">${uhrzeiten(1, 96, f.ende)}</select>
              </label>
              ${temperatur}
            </div>
          </div>`;
      })
      .join("");
    const chips = TAGE.map(
      (tag, i) =>
        `<button class="chip ${b.tage.has(tag) ? "an" : ""}" data-aktion="tag-wahl"
          data-tag="${tag}" aria-pressed="${b.tage.has(tag)}">${t.kurz[i]}</button>`
    ).join("");
    const problem = this._problem(hk);
    const meldung =
      this._meldung?.schluessel === b.schluessel && this._meldung?.tag === b.tag
        ? `<div class="meldung ${this._meldung.art}" style="padding-left:0">
             ${sicher(this._meldung.text)}</div>`
        : "";
    return `
      <div class="editor">
        ${zeilen}
        ${
          b.fenster.length
            ? ""
            : `<div class="hinweis klein">${
                hk.art && hk.art !== "heizzeiten" ? t.leer_laden : t.leer
              }</div>`
        }
        ${
          b.fenster.length < FENSTER_JE_TAG
            ? `<button class="text-knopf" data-aktion="hinzufuegen">${t.hinzufuegen}</button>`
            : ""
        }
        ${
          hk.mit_absenkung
            ? `<label class="absenk"><span>${t.absenk_feld}</span><span class="eingabe">
                 <input type="number" inputmode="decimal" step="0.5"
                   min="${hk.absenkung_min}" max="${hk.absenkung_max}"
                   value="${Number.isFinite(b.absenkung) ? b.absenkung : ""}"
                   data-feld="absenkung">°C</span></label>`
            : ""
        }
        <div class="tage-wahl">
          <span class="klein">${t.gilt_fuer}</span>
          <div class="chips">${chips}</div>
          <div class="chips schnell">
            <button class="chip" data-aktion="tage" data-tage="werktage">${t.werktage}</button>
            <button class="chip" data-aktion="tage" data-tage="wochenende">${t.wochenende}</button>
            <button class="chip" data-aktion="tage" data-tage="alle">${t.alle}</button>
          </div>
        </div>
        <div class="problem fehler klein" ${problem ? "" : "hidden"}>${problem || ""}</div>
        ${meldung}
        <div class="knoepfe">
          <button class="flach" data-aktion="abbrechen">${t.abbrechen}</button>
          <button class="haupt" data-aktion="speichern"
            ${problem || this._speichert ? "disabled" : ""}>
            ${this._speichert ? t.speichert : t.speichern}</button>
        </div>
      </div>`;
  }

  _problem(hk) {
    const t = this._t;
    const b = this._bearbeitung;
    if (b.fenster.some((f) => f.ende <= f.beginn)) return t.fehler_reihenfolge;
    const sortiert = [...b.fenster].sort((x, y) => x.beginn - y.beginn);
    if (sortiert.some((f, i) => i > 0 && f.beginn < sortiert[i - 1].ende)) {
      return t.fehler_ueberlappung;
    }
    if (
      hk.mit_temperatur &&
      hk.temperatur_aenderbar &&
      b.fenster.some(
        (f) =>
          !Number.isFinite(f.temperatur) ||
          f.temperatur < hk.temperatur_min ||
          f.temperatur > hk.temperatur_max
      )
    ) {
      return t.fehler_temperatur(this._zahl(hk.temperatur_min), this._zahl(hk.temperatur_max));
    }
    if (
      hk.mit_absenkung &&
      b.absenkung != null &&
      (b.absenkung < hk.absenkung_min || b.absenkung > hk.absenkung_max)
    ) {
      return t.fehler_absenkung(this._zahl(hk.absenkung_min), this._zahl(hk.absenkung_max));
    }
    if (!b.tage.size) return t.fehler_tage;
    return null;
  }

  _oeffnen(schluessel, tag) {
    const hk = this._finden(schluessel);
    if (!hk || hk.zeitplan || !hk.tage) return;
    if (this._bearbeitung?.schluessel === schluessel && this._bearbeitung?.tag === tag) {
      this._bearbeitung = null;
    } else {
      const ersatz = this._ersatztemperatur(hk);
      this._bearbeitung = {
        schluessel,
        tag,
        fenster: hk.tage[tag].map((f) => ({
          beginn: f.beginn,
          ende: f.ende,
          temperatur: !hk.mit_temperatur
            ? null
            : hk.temperatur_aenderbar
              ? f.temperatur ?? ersatz
              : f.temperatur,
        })),
        absenkung: hk.mit_absenkung ? hk.absenkung?.[tag] ?? null : null,
        tage: new Set([tag]),
      };
    }
    this._meldung = null;
    this._zeichnen();
  }

  _klick(e) {
    const ziel = e.target.closest("[data-aktion]");
    if (!ziel || ziel.disabled) return;
    const b = this._bearbeitung;
    const hk = b ? this._finden(b.schluessel) : null;
    switch (ziel.dataset.aktion) {
      case "laden":
        this._bearbeitung = null;
        this._laden();
        return;
      case "tag":
        this._oeffnen(ziel.dataset.hk, ziel.dataset.tag);
        return;
      case "gesperrt":
        this._gesperrt(ziel.dataset.hk, ziel.dataset.tag);
        return;
      case "zeitplan":
        this.dispatchEvent(
          new CustomEvent("hass-more-info", {
            detail: { entityId: ziel.dataset.entity },
            bubbles: true,
            composed: true,
          })
        );
        return;
      case "hinzufuegen": {
        const letztes = [...b.fenster].sort((x, y) => x.beginn - y.beginn).pop();
        const beginn = letztes ? Math.min(letztes.ende + 4, 92) : 24;
        b.fenster.push({
          beginn,
          ende: Math.min(beginn + 8, 96),
          temperatur:
            hk.mit_temperatur && hk.temperatur_aenderbar
              ? letztes?.temperatur ?? this._ersatztemperatur(hk)
              : null,
        });
        break;
      }
      case "entfernen":
        b.fenster.splice(Number(ziel.dataset.index), 1);
        break;
      case "tag-wahl":
        if (b.tage.has(ziel.dataset.tag)) b.tage.delete(ziel.dataset.tag);
        else b.tage.add(ziel.dataset.tag);
        break;
      case "tage":
        b.tage = new Set(
          { werktage: TAGE.slice(0, 5), wochenende: TAGE.slice(5), alle: TAGE }[ziel.dataset.tage]
        );
        break;
      case "abbrechen":
        this._bearbeitung = null;
        break;
      case "speichern":
        this._speichern();
        return;
      default:
        return;
    }
    this._meldung = null;
    this._zeichnen();
  }

  _taste(e) {
    if (e.key !== "Enter" && e.key !== " ") return;
    const aktion = e.target.dataset?.aktion;
    if (aktion === "tag") {
      e.preventDefault();
      this._oeffnen(e.target.dataset.hk, e.target.dataset.tag);
    } else if (aktion === "gesperrt") {
      e.preventDefault();
      this._gesperrt(e.target.dataset.hk, e.target.dataset.tag);
    }
  }

  _gesperrt(schluessel, tag) {
    const hk = this._finden(schluessel);
    if (!hk?.zeitplan) return;
    const name = this._hass?.states?.[hk.zeitplan]?.attributes?.friendly_name || hk.zeitplan;
    const offen = this._meldung?.schluessel === schluessel && this._meldung?.tag === tag;
    this._meldung = offen ? null : { schluessel, tag, art: "hinweis", text: this._t.gesperrt(name) };
    this._zeichnen();
  }

  _eingabe(e) {
    const feld = e.target.dataset?.feld;
    const b = this._bearbeitung;
    if (!feld || !b) return;
    if (feld === "absenkung") {
      const wert = e.target.valueAsNumber;
      b.absenkung = Number.isFinite(wert) ? wert : null;
    } else {
      const fenster = b.fenster[Number(e.target.dataset.index)];
      fenster[feld] = feld === "temperatur" ? e.target.valueAsNumber : Number(e.target.value);
    }
    const hk = this._finden(b.schluessel);
    const problem = this._problem(hk);
    const anzeige = this.shadowRoot.querySelector(".problem");
    anzeige.textContent = problem || "";
    anzeige.hidden = !problem;
    this.shadowRoot.querySelector('[data-aktion="speichern"]').disabled =
      Boolean(problem) || this._speichert;
    const zeile = this.shadowRoot.querySelector(".tag.offen .balken");
    if (zeile) zeile.querySelectorAll(".block").forEach((block) => block.remove());
    if (zeile) zeile.insertAdjacentHTML("afterbegin", this._bloecke(b.fenster));
  }

  async _speichern() {
    const b = this._bearbeitung;
    const hk = b && this._finden(b.schluessel);
    if (!hk || this._problem(hk) || this._speichert) return;
    this._speichert = true;
    this._meldung = null;
    this._zeichnen();
    try {
      const neu = await this._hass.callWS({
        type: "eta_heating_ws/zeitprogramm_setzen",
        eintrag: hk.eintrag,
        programm: hk.programm,
        tage: TAGE.filter((tag) => b.tage.has(tag)),
        fenster: [...b.fenster]
          .sort((x, y) => x.beginn - y.beginn)
          .map((f) => ({
            beginn: f.beginn,
            ende: f.ende,
            temperatur: hk.mit_temperatur && hk.temperatur_aenderbar ? f.temperatur : null,
          })),
        absenkung: hk.mit_absenkung ? b.absenkung : null,
      });
      this._programme = this._programme.map((alt) =>
        this._schluessel(alt) === b.schluessel ? neu : alt
      );
      this._bearbeitung = null;
      this._gelesen = Date.now();
      const meldung = { schluessel: b.schluessel, tag: b.tag, art: "ok", text: `✓ ${this._t.gespeichert}` };
      this._meldung = meldung;
      setTimeout(() => {
        if (this._meldung === meldung) {
          this._meldung = null;
          this._zeichnen();
        }
      }, 4000);
    } catch (err) {
      this._meldung = {
        schluessel: b.schluessel,
        tag: b.tag,
        art: "fehler",
        text: err?.message || String(err),
      };
    }
    this._speichert = false;
    this._zeichnen();
  }
}

function sprache(code) {
  return String(code || "de").toLowerCase().startsWith("de") ? "de" : "en";
}

/**
 * Erst anmelden, wenn Home Assistant steht.
 *
 * Die Karte lädt früh, noch vor der Oberfläche. Die ersetzt beim Start die
 * Liste der Bausteine im Browser (window.customElements) durch eine eigene;
 * was davor angemeldet wurde, fände sie nicht mehr. Ist <home-assistant>
 * angemeldet, gilt schon die neue Liste.
 */
function anmelden() {
  if (!customElements.get(KARTE)) {
    customElements.define(KARTE, EtaZeitprogrammKarte);
  }
}

customElements.whenDefined("home-assistant").then(anmelden);

window.customCards = window.customCards || [];
if (!window.customCards.some((karte) => karte.type === KARTE)) {
  window.customCards.push({
    type: KARTE,
    name: "ETA Zeitprogramm",
    description: TEXTE[sprache(document.documentElement.lang)].karte_beschreibung,
    preview: false,
    documentationURL: "https://github.com/dorsch95/ha-eta-webservices#zeitprogramm-auf-dem-dashboard",
  });
}
