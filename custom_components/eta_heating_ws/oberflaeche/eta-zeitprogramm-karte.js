/**
 * ETA Zeitprogramm - Dashboard-Karte der Integration ETA Web-Services.
 *
 * Zeigt die Heizzeiten jedes Heizkreises als Wochenbalken. Ein Tipp auf
 * einen Tag öffnet ihn zum Bearbeiten; die Änderung lässt sich auf weitere
 * Tage übernehmen. Gelesen und geschrieben wird über die Websocket-Befehle
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
    absenkung: "ganztägig Absenkung",
    tippen: "Zum Ändern einen Tag antippen.",
    fenster: "Zeitfenster",
    von: "von",
    bis: "bis",
    hinzufuegen: "+ Zeitfenster",
    entfernen: "Zeitfenster entfernen",
    leer: "Ohne Zeitfenster gilt den ganzen Tag die Absenkung.",
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
    kurz: ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"],
    karte_beschreibung: "Heizzeiten der ETA-Heizung ansehen und ändern.",
    feld_titel: "Titel",
    feld_heizkreis: "Heizkreis (leer: alle)",
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
    absenkung: "setback all day",
    tippen: "Tap a day to change it.",
    fenster: "Time slot",
    von: "from",
    bis: "to",
    hinzufuegen: "+ Time slot",
    entfernen: "Remove time slot",
    leer: "Without time slots the setback applies all day.",
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
    kurz: ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"],
    karte_beschreibung: "View and change the heating times of the ETA boiler.",
    feld_titel: "Title",
    feld_heizkreis: "Heating circuit (empty: all)",
  },
};

const SYMBOL_NEU_LESEN =
  "M17.65,6.35C16.2,4.9 14.21,4 12,4A8,8 0 0,0 4,12A8,8 0 0,0 12,20C15.73,20 " +
  "18.84,17.45 19.73,14H17.65C16.83,16.33 14.61,18 12,18A6,6 0 0,1 6,12A6,6 0 0,1 " +
  "12,6C13.66,6 15.14,6.69 16.22,7.78L13,11H20V4L17.65,6.35Z";
const SYMBOL_ENTFERNEN =
  "M19,6.41L17.59,5L12,10.59L6.41,5L5,6.41L10.59,12L5,17.59L6.41,19L12,13.41L17.59," +
  "19L19,17.59L13.41,12L19,6.41Z";

const STIL = `
  :host { display: block; }
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
  .meldung { font-size: 13px; padding: 2px 0 6px 36px; }
  .skala {
    position: relative; height: 16px; margin-left: 36px;
    font-size: 11px; color: var(--secondary-text-color);
  }
  .skala span { position: absolute; transform: translateX(-50%); }
  .skala span:first-child { transform: none; }
  .skala span:last-child { transform: translateX(-100%); }
  .tag {
    display: grid; grid-template-columns: 28px 1fr; column-gap: 8px; row-gap: 2px;
    align-items: center; margin: 0 -6px; padding: 6px; border-radius: 8px;
    cursor: pointer; outline: none;
  }
  .tag:hover, .tag:focus-visible, .tag.offen { background: var(--secondary-background-color); }
  .tag.gesperrt { cursor: default; }
  .tag.gesperrt:hover { background: none; }
  .kurz { font-weight: 500; }
  .kurz.heute { color: var(--primary-color); }
  .balken {
    position: relative; height: 14px; border-radius: 7px; overflow: hidden;
    background:
      repeating-linear-gradient(to right, transparent 0, transparent calc(25% - 1px),
        rgba(127, 127, 127, 0.35) calc(25% - 1px), rgba(127, 127, 127, 0.35) 25%),
      var(--secondary-background-color);
  }
  .tag.offen .balken { background-color: var(--card-background-color); }
  .block {
    position: absolute; top: 0; bottom: 0; border-radius: 7px;
    background: var(--state-climate-heat-color, #ff8100);
  }
  .jetzt { position: absolute; top: 0; bottom: 0; width: 2px; background: var(--primary-text-color); }
  .text { grid-column: 2; font-size: 12px; color: var(--secondary-text-color); }
  .editor {
    display: flex; flex-direction: column; gap: 10px;
    margin: 4px 0 8px 36px; padding: 12px; border-radius: 12px;
    border: 1px solid var(--divider-color);
  }
  .zeile { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 10px; }
  .nr {
    flex: 1 0 100%; display: flex; align-items: center; justify-content: space-between;
    font-size: 13px; color: var(--secondary-text-color);
  }
  .nr .symbol { padding: 4px; }
  .am-stueck { white-space: nowrap; }
  .feld { display: inline-flex; align-items: center; gap: 6px; }
  select, input {
    box-sizing: border-box; font: inherit; height: 36px; padding: 4px 8px; border-radius: 8px;
    border: 1px solid var(--divider-color);
    color: var(--primary-text-color); background: var(--card-background-color);
  }
  input[type="number"] { width: 4.5em; }
  .text-knopf {
    align-self: flex-start; padding: 4px 0; border: none; background: none;
    color: var(--primary-color); font-weight: 500;
  }
  .tage-wahl { display: flex; flex-direction: column; gap: 6px; }
  .chips { display: flex; flex-wrap: wrap; gap: 6px; }
  .chip {
    min-width: 40px; min-height: 32px; padding: 4px 10px; border-radius: 16px;
    border: 1px solid var(--divider-color); background: none; color: var(--primary-text-color);
  }
  .chip.an {
    background: var(--primary-color); border-color: var(--primary-color);
    color: var(--text-primary-color, #fff);
  }
  .knoepfe { display: flex; justify-content: flex-end; gap: 8px; }
  .flach {
    padding: 8px 12px; border: none; border-radius: 18px; background: none;
    color: var(--primary-color); font-weight: 500;
  }
  .haupt {
    min-height: 36px; padding: 8px 18px; border: none; border-radius: 18px;
    background: var(--primary-color); color: var(--text-primary-color, #fff); font-weight: 500;
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
    this._heizkreise = null;
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
    return {};
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
      ],
      computeLabel: (feld) => (feld.name === "titel" ? t.feld_titel : t.feld_heizkreis),
    };
  }

  setConfig(konfig) {
    this._konfig = konfig || {};
    this._zeichnen();
  }

  set hass(hass) {
    const erstes = !this._hass;
    this._hass = hass;
    if (erstes) this._laden();
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
      this._heizkreise = antwort.heizkreise;
      this._fehler = null;
      this._gelesen = Date.now();
    } catch (err) {
      this._fehler = err?.message || String(err);
    }
    this._laedt = false;
    this._zeichnen();
  }

  _auswahl() {
    const gesucht = String(this._konfig.heizkreis || "").toLowerCase();
    return (this._heizkreise || []).filter(
      (hk) =>
        !gesucht || hk.heizkreis.toLowerCase() === gesucht || hk.name.toLowerCase() === gesucht
    );
  }

  _schluessel(hk) {
    return `${hk.eintrag}|${hk.heizkreis}`;
  }

  _finden(schluessel) {
    return (this._heizkreise || []).find((hk) => this._schluessel(hk) === schluessel);
  }

  _zahl(wert) {
    return new Intl.NumberFormat(this._hass?.locale?.language || "de", {
      minimumFractionDigits: 1,
      maximumFractionDigits: 1,
    }).format(wert);
  }

  _beschreibung(hk, fenster) {
    if (!fenster.length) return sicher(this._t.absenkung);
    return fenster
      .map((f) => {
        const zeit = `${uhrzeit(f.beginn)}–${uhrzeit(f.ende)}`;
        const text = f.temperatur == null ? zeit : `${zeit} · ${this._zahl(f.temperatur)} °C`;
        return `<span class="am-stueck">${sicher(text)}</span>`;
      })
      .join(", ");
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
    if (!this._heizkreise) {
      inhalt = this._fehler
        ? `<div class="fehler">${t.nicht_lesbar} ${sicher(this._fehler)}</div>
           <button class="text-knopf" data-aktion="laden">${t.erneut}</button>`
        : `<div class="hinweis">${t.laden}</div>`;
    } else if (!liste.length) {
      inhalt = `<div class="hinweis">${t.keins}</div>`;
    } else {
      const anlagen = new Set(liste.map((hk) => hk.eintrag)).size;
      inhalt = liste.map((hk) => this._heizkreis(hk, liste.length > 1, anlagen > 1)).join("");
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
      </ha-card>`;
  }

  _heizkreis(hk, mehrere, anlagen) {
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
      const knopf = hk.zeitplan ? "" : 'role="button" tabindex="0" data-aktion="tag"';
      html += `
        <div class="${klassen}" ${knopf} data-hk="${sicher(schluessel)}" data-tag="${tag}">
          <div class="kurz ${tag === heute ? "heute" : ""}">${t.kurz[i]}</div>
          <div class="balken">${this._bloecke(fenster)}${
            tag === heute ? `<div class="jetzt" style="left:${jetztAnteil}%"></div>` : ""
          }</div>
          <div class="text">${this._beschreibung(hk, hk.tage[tag])}</div>
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
        const temperatur = hk.mit_temperatur
          ? `<label class="feld"><input type="number" inputmode="decimal" step="0.5"
               min="${hk.temperatur_min}" max="${hk.temperatur_max}"
               value="${Number.isFinite(f.temperatur) ? f.temperatur : ""}"
               data-feld="temperatur" data-index="${i}"><span>°C</span></label>`
          : "";
        return `
          <div class="zeile">
            <div class="nr">
              <span>${t.fenster} ${i + 1}</span>
              <button class="symbol" data-aktion="entfernen" data-index="${i}"
                title="${t.entfernen}" aria-label="${t.entfernen}">
                <svg viewBox="0 0 24 24"><path d="${SYMBOL_ENTFERNEN}"></path></svg>
              </button>
            </div>
            <label class="feld"><span>${t.von}</span>
              <select data-feld="beginn" data-index="${i}">${uhrzeiten(0, 95, f.beginn)}</select>
            </label>
            <label class="feld"><span>${t.bis}</span>
              <select data-feld="ende" data-index="${i}">${uhrzeiten(1, 96, f.ende)}</select>
            </label>
            ${temperatur}
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
        ${b.fenster.length ? "" : `<div class="hinweis klein">${t.leer}</div>`}
        ${
          b.fenster.length < FENSTER_JE_TAG
            ? `<button class="text-knopf" data-aktion="hinzufuegen">${t.hinzufuegen}</button>`
            : ""
        }
        <div class="tage-wahl">
          <span class="klein">${t.gilt_fuer}</span>
          <div class="chips">${chips}</div>
          <div class="chips">
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
      b.fenster.some(
        (f) =>
          !Number.isFinite(f.temperatur) ||
          f.temperatur < hk.temperatur_min ||
          f.temperatur > hk.temperatur_max
      )
    ) {
      return t.fehler_temperatur(this._zahl(hk.temperatur_min), this._zahl(hk.temperatur_max));
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
          temperatur: hk.mit_temperatur ? f.temperatur ?? ersatz : null,
        })),
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
          temperatur: hk.mit_temperatur ? letztes?.temperatur ?? this._ersatztemperatur(hk) : null,
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
    if ((e.key === "Enter" || e.key === " ") && e.target.dataset?.aktion === "tag") {
      e.preventDefault();
      this._oeffnen(e.target.dataset.hk, e.target.dataset.tag);
    }
  }

  _eingabe(e) {
    const feld = e.target.dataset?.feld;
    const b = this._bearbeitung;
    if (!feld || !b) return;
    const fenster = b.fenster[Number(e.target.dataset.index)];
    fenster[feld] = feld === "temperatur" ? e.target.valueAsNumber : Number(e.target.value);
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
        heizkreis: hk.heizkreis,
        tage: TAGE.filter((tag) => b.tage.has(tag)),
        fenster: [...b.fenster]
          .sort((x, y) => x.beginn - y.beginn)
          .map((f) => ({
            beginn: f.beginn,
            ende: f.ende,
            temperatur: hk.mit_temperatur ? f.temperatur : null,
          })),
      });
      this._heizkreise = this._heizkreise.map((alt) =>
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
