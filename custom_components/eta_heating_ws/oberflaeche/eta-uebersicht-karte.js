/**
 * ETA Übersicht - Dashboard-Karte der Integration ETA Web-Services.
 *
 * Zeigt die Anlage in einer von drei Ansichten: als Kacheln, als
 * Anlagenbild mit Leitungen oder kompakt als Liste. Die Zeichnungen
 * bewegen sich, solange das Teil arbeitet - die Flamme im Kessel, die
 * Strömung im Puffer, der Fluss in den Leitungen.
 *
 * Die Messwerte kommen aus den Entitäten in Home Assistant. Welche Teile
 * die Anlage hat, welche Entität wozu gehört und wer woran hängt, liefert
 * der Websocket-Befehl der Integration, siehe uebersicht.py. Home
 * Assistant lädt die Karte in jedem Dashboard von selbst.
 */

const KARTE = "eta-uebersicht-karte";
const ANSICHTEN = ["kacheln", "anlagenbild", "kompakt"];
const NEU_FRAGEN_NACH = 300000;
const NOCHMAL_NACH = 30000;
const LEISTUNG_AB = 0.05;
const SOLL_SENDEN_NACH = 700;
const SOLL_WARTEN = 8000;

const TEXTE = {
  de: {
    karte_beschreibung: "Die Anlage als Kacheln, als Anlagenbild mit Leitungen oder kompakt als Liste.",
    feld_titel: "Titel",
    feld_ansicht: "Ansicht",
    feld_anlage: "Anlage",
    feld_fussboden: "Fußbodenheizung statt Heizkörper",
    ansicht_kacheln: "Kacheln",
    ansicht_anlagenbild: "Anlagenbild",
    ansicht_kompakt: "Kompakt",
    titel: "ETA Heizung",
    laedt: "Die Anlage wird gelesen …",
    keine_antwort: "Die Integration antwortet nicht. Die Karte versucht es gleich noch einmal.",
    keine_anlage: "Es ist keine ETA-Anlage eingerichtet.",
    aussen: "Außen",
    stoerung: "Störung",
    keine_stoerung: "Keine Störung",
    kessel: "Kessel",
    kesseltemperatur: "Kesseltemperatur",
    soll: "Soll",
    ruecklauf: "Rücklauf",
    druck: "Anlagendruck",
    o2: "Restsauerstoff",
    behaelter: "Tagesbehälter",
    aschebox: "Aschebox",
    kessel_ein: "Kessel Ein",
    kessel_aus: "Kessel Aus",
    entaschen: "Entaschen",
    aschebox_leeren: "Aschebox leeren",
    frage_entaschen: "Kessel jetzt entaschen? Er geht dafür in den Glutabbrand.",
    frage_plan: "Aschebox-Plan abbrechen?",
    plan_abbrechen: "Plan abbrechen",
    ja: "Ja",
    nein: "Nein",
    puffer: "Pufferspeicher",
    ladezustand: "Ladezustand",
    oben: "Oben",
    unten: "Unten",
    ladepumpe: "Ladepumpe",
    laden: "Laden",
    bereit: "Bereit",
    laedt_klein: "lädt",
    bereit_klein: "bereit",
    warmwasser: "Warmwasser",
    warmwasser_zustand: "Warmwasser Zustand",
    fwm: "Frischwassermodul",
    temperatur_modul: "Temperatur am Modul",
    speichertemperatur: "Speichertemperatur",
    zirkulation: "Zirkulation",
    zirkulation_laeuft: "Zirkulation läuft",
    zapfung: "Zapfung läuft",
    warmwasser_im_puffer: "Warmwasser im Puffer",
    laeuft: "Läuft",
    ruht: "Ruht",
    aus: "Aus",
    ein: "Ein",
    heizkreis: "Heizkreis",
    vorlauf: "Vorlauf",
    raum: "Raum",
    raum_soll: "Raum Soll",
    waermer: "wärmer",
    kaelter: "kälter",
    zeitprogramm: "Zeitprogramm",
    anforderung: "Anforderung",
    heizt: "Heizt",
    modus_automatik: "Auto",
    modus_heizen: "Dauer",
    modus_absenken: "ECO",
    modus_aus: "Aus",
    betriebsart: "Betriebsart",
    lager: "Pelletlager",
    vorrat: "Vorrat",
    von: "von",
    reicht_bis: "Reicht bis",
    warnung_ab: "Warnung ab",
    foerdert: "Fördert",
    solar: "Solar",
    leistung: "Leistung",
    kollektor: "Kollektor",
    ertrag_heute: "Ertrag heute",
    heute: "Heute",
    liefert: "Liefert",
    pvm: "PV-Heizmodul",
    heizstab: "Heizstab",
    speicher_oben: "Speicher oben",
    brenner: "Brenner",
    temperatur: "Temperatur",
    leistung_soll: "Leistung Soll",
    fernleitung: "Fernleitung",
    fernpumpe: "Fernpumpe",
    an_teil: "an",
  },
  en: {
    karte_beschreibung: "The heating system as tiles, as a system diagram with pipes or as a compact list.",
    feld_titel: "Title",
    feld_ansicht: "View",
    feld_anlage: "System",
    feld_fussboden: "Underfloor heating instead of radiator",
    ansicht_kacheln: "Tiles",
    ansicht_anlagenbild: "System diagram",
    ansicht_kompakt: "Compact",
    titel: "ETA Heating",
    laedt: "Reading the system …",
    keine_antwort: "The integration does not answer. The card will try again shortly.",
    keine_anlage: "No ETA system is set up.",
    aussen: "Outside",
    stoerung: "Fault",
    keine_stoerung: "No fault",
    kessel: "Boiler",
    kesseltemperatur: "Boiler temperature",
    soll: "Target",
    ruecklauf: "Return",
    druck: "System pressure",
    o2: "Residual oxygen",
    behaelter: "Day hopper",
    aschebox: "Ash box",
    kessel_ein: "Boiler on",
    kessel_aus: "Boiler off",
    entaschen: "De-ash",
    aschebox_leeren: "Empty ash box",
    frage_entaschen: "De-ash the boiler now? It will burn down to embers first.",
    frage_plan: "Cancel the ash box plan?",
    plan_abbrechen: "Cancel plan",
    ja: "Yes",
    nein: "No",
    puffer: "Buffer tank",
    ladezustand: "State of charge",
    oben: "Top",
    unten: "Bottom",
    ladepumpe: "Charging pump",
    laden: "Charging",
    bereit: "Ready",
    laedt_klein: "charging",
    bereit_klein: "ready",
    warmwasser: "Hot water",
    warmwasser_zustand: "Hot water state",
    fwm: "Fresh water module",
    temperatur_modul: "Temperature at the module",
    speichertemperatur: "Tank temperature",
    zirkulation: "Circulation",
    zirkulation_laeuft: "Circulation running",
    zapfung: "Hot water running",
    warmwasser_im_puffer: "Hot water in buffer",
    laeuft: "Running",
    ruht: "Idle",
    aus: "Off",
    ein: "On",
    heizkreis: "Heating circuit",
    vorlauf: "Flow",
    raum: "Room",
    raum_soll: "Room target",
    waermer: "warmer",
    kaelter: "cooler",
    zeitprogramm: "Schedule",
    anforderung: "Demand",
    heizt: "Heating",
    modus_automatik: "Auto",
    modus_heizen: "Day",
    modus_absenken: "ECO",
    modus_aus: "Off",
    betriebsart: "Operating mode",
    lager: "Pellet store",
    vorrat: "Stock",
    von: "of",
    reicht_bis: "Lasts until",
    warnung_ab: "Warning below",
    foerdert: "Conveying",
    solar: "Solar",
    leistung: "Power",
    kollektor: "Collector",
    ertrag_heute: "Yield today",
    heute: "Today",
    liefert: "Delivering",
    pvm: "PV heating module",
    heizstab: "Heating rod",
    speicher_oben: "Tank top",
    brenner: "Burner",
    temperatur: "Temperature",
    leistung_soll: "Target power",
    fernleitung: "Transfer line",
    fernpumpe: "Line pump",
    an_teil: "on",
  },
};

/**
 * Die Texte, die die Anlage für "Kessel-Zustand detailliert" meldet, und
 * welches bewegte Bild dazu gehört - dieselben Listen wie in karte.py.
 */
const KESSEL_BILDER = {
  flamme: [
    "Heizen", "Heizen Start", "Anheizen", "Pellet Betrieb", "Heizen, Vorbereitung auf Messung",
    "Heizen, Teillastmessung durchführen", "Heizen, Nennlastmessung durchführen",
  ],
  zuendung: ["Zünden", "Heizversuch"],
  entaschen: ["Entaschen"],
  stoerung: ["Störung", "Störung beim Entaschen", "Wartung"],
  glut: [
    "Glutabbrand", "Glutabbrand wegen Entaschung", "Glutabbrand da ausgeschaltet",
    "Glutabbrand weil Aschebox fehlt", "Glutabbrand wegen Störung", "Glutabbrand wegen Verriegelung", "Ausbrand",
  ],
};
const PUFFER_LAEDT = ["Anfordern", "Laden", "Restwärme", "Abschöpfen"];
const WARMWASSER_LAEDT = [...PUFFER_LAEDT, "Extra Laden"];
const OHNE_FLUSS = ["Aus", "-", "", "unavailable", "unknown"];
const LAGER_FOERDERT = "Fördern";
const PLAN_LAEUFT = ["geplant", "glutabbrand", "entaschen", "leeren"];
const MODI = [["automatik", "uhr"], ["heizen", "flamme"], ["absenken", "blatt"], ["aus", "aus"]];

const STIL = `
  :host {
    display: block;
    --karte: var(--ha-card-background, var(--card-background-color, #fff));
    --rand: var(--ha-card-border-color, var(--divider-color, #dfe3e8));
    --text: var(--primary-text-color, #1a1c20);
    --text-2: var(--secondary-text-color, #59606b);
    --flaeche: rgba(127, 127, 127, .14);
    --buehne: rgba(127, 127, 127, .08);
    --rund: 12px;
    --metall: #c3c9d2; --metall-hell: #dde2e9; --metall-dunkel: #8b93a0; --kammer: #1d2025;
    --akzent: #ff9b00; --auf-akzent: #1a1c20;
    --heiss: #e5484d; --kalt: #3b82f6; --pellet: #c8963e; --pellet-hell: #dcb062; --pellet-dunkel: #a87a2c;
    --sonne: #f2a900; --zelle: #6d7786; --pv: #2c56b0;
  }
  :host([vollbild]) { padding: 12px 16px 16px; box-sizing: border-box; }
  :host([dunkel]) {
    --metall: #5a606b; --metall-hell: #7a818d; --metall-dunkel: #3b4049; --kammer: #0a0b0d;
    --heiss: #f0595e; --kalt: #5b9bff; --pellet: #d1a04a; --pellet-hell: #e3b96c;
    --sonne: #ffc02e; --zelle: #4c5562; --pv: #3d68c9;
  }
  .eta { position: relative; color: var(--text); container-type: inline-size; }
  .eta-defs { position: absolute; width: 0; height: 0; overflow: hidden; }
  .eta-meldung { padding: 16px; border-radius: var(--rund); background: var(--karte); border: 1px solid var(--rand); color: var(--text-2); }
  .eta-kopf { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 10px 16px; margin: 2px 2px 14px; }
  .eta-titel { margin: 0; font-size: var(--ha-card-header-font-size, 1.25rem); font-weight: 500; line-height: 1.2; color: var(--ha-card-header-color, var(--text)); }
  .eta-chips { display: flex; flex-wrap: wrap; gap: 8px; }
  .eta-chip { display: inline-flex; align-items: center; gap: 7px; height: 30px; padding: 0 12px; border-radius: 15px; background: var(--karte); border: 1px solid var(--rand); color: var(--text); font: inherit; font-size: 13px; font-weight: 500; white-space: nowrap; }
  button.eta-chip { cursor: pointer; }
  .eta-chip.klein { height: 26px; padding: 0 10px; font-size: 12px; background: var(--flaeche); border-color: transparent; }
  .eta-chip .eta-icon { width: 16px; height: 16px; }
  .eta-chip[data-art="stoer"] { background: var(--heiss); border-color: transparent; color: #fff; }
  .eta-chip[data-art="stoer"] .eta-punkt { background: #fff; }
  .eta-punkt { width: 8px; height: 8px; border-radius: 50%; background: var(--metall-dunkel); flex: none; }
  .eta-punkt[data-an] { background: var(--akzent); animation: eta-puls 2s ease-in-out infinite; }
  .eta-icon { width: 20px; height: 20px; flex: none; fill: none; stroke: currentColor; stroke-width: 1.8; stroke-linecap: round; stroke-linejoin: round; }
  .eta-dreht { animation: eta-drehen 2.4s linear infinite; }

  .eta-raster { columns: 288px; column-gap: 16px; }
  .eta-raster > .eta-kachel { break-inside: avoid; margin: 0 0 16px; }
  .eta-kachel { background: var(--karte); border: 1px solid var(--rand); border-radius: var(--rund); box-shadow: var(--ha-card-box-shadow, none); padding: 16px; display: flex; flex-direction: column; gap: 14px; min-width: 0; box-sizing: border-box; }
  .eta-kachelkopf { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 6px 10px; min-height: 26px; }
  .eta-kachelkopf h3 { margin: 0; font-size: 16px; font-weight: 500; }
  .eta-buehne { display: flex; flex-wrap: wrap; align-items: center; gap: 12px 16px; padding: 14px; border-radius: 12px; background: var(--buehne); min-height: 132px; }
  [data-info] { cursor: pointer; }
  [data-info]:focus-visible, .eta-knopf:focus-visible, .eta-modus:focus-visible, button.eta-chip:focus-visible { outline: 2px solid var(--akzent); outline-offset: 2px; }
  .eta-figur { width: min(var(--b, 110px), 46%); flex: none; }
  .eta-svg { display: block; width: 100%; height: auto; overflow: visible; }
  .eta-haupt { flex: 1 1 96px; display: flex; flex-direction: column; gap: 2px; min-width: 0; }
  .eta-label { font-size: 12px; color: var(--text-2); }
  .eta-zahl { font-size: 34px; font-weight: 500; line-height: 1.1; font-variant-numeric: tabular-nums; white-space: nowrap; }
  .eta-zahl small { font-size: .5em; font-weight: 500; color: var(--text-2); margin-left: .25em; }
  .eta-neben { font-size: 13px; color: var(--text-2); font-variant-numeric: tabular-nums; }
  .eta-zeilen { margin: 0; display: flex; flex-direction: column; }
  .eta-zeilen div { display: flex; justify-content: space-between; align-items: baseline; gap: 12px; padding: 8px 0; border-top: 1px solid var(--rand); }
  .eta-zeilen div:first-child { border-top: 0; padding-top: 0; }
  .eta-zeilen dt { color: var(--text-2); }
  .eta-zeilen dd { margin: 0; font-weight: 500; font-variant-numeric: tabular-nums; text-align: right; display: inline-flex; align-items: center; justify-content: flex-end; gap: 6px; }
  .eta-zeilen dd .eta-icon { width: 16px; height: 16px; }
  .eta-messung { display: flex; flex-direction: column; gap: 6px; }
  .eta-messung-kopf { display: flex; justify-content: space-between; align-items: baseline; gap: 12px; }
  .eta-messung-kopf span { color: var(--text-2); }
  .eta-messung-kopf b { font-weight: 500; font-variant-numeric: tabular-nums; }
  .eta-balken { position: relative; height: 8px; border-radius: 4px; background: var(--flaeche); overflow: hidden; }
  .eta-balken i { display: block; height: 100%; border-radius: 4px; background: var(--metall-dunkel); transition: width .6s ease; }
  .eta-balken[data-art="pellet"] i { background: var(--pellet); }
  .eta-balken u { position: absolute; top: 0; bottom: 0; width: 2px; background: var(--text); }
  .eta-knoepfe { display: grid; grid-template-columns: repeat(auto-fit, minmax(72px, 1fr)); gap: 8px; }
  .eta-knopf { min-height: 54px; padding: 6px 4px; border: 0; border-radius: 12px; background: var(--flaeche); color: var(--text); font: inherit; font-size: 12px; font-weight: 500; line-height: 1.2; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 4px; cursor: pointer; transition: transform .1s; }
  .eta-knopf:active { transform: scale(.97); }
  .eta-knopf[aria-pressed="true"] { background: var(--akzent); color: var(--auf-akzent); }
  .eta-frage { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 8px 12px; padding: 10px 12px; border-radius: 12px; background: var(--flaeche); }
  .eta-frage span { flex: 1 1 160px; }
  .eta-frage div { display: flex; gap: 8px; }
  .eta-frage button { min-height: 40px; min-width: 64px; padding: 0 14px; border: 0; border-radius: 10px; background: var(--karte); color: var(--text); font: inherit; font-weight: 500; cursor: pointer; }
  .eta-frage button[data-aktion="ja"] { background: var(--akzent); color: var(--auf-akzent); }
  .eta-modi { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 2px; padding: 3px; border-radius: 12px; background: var(--flaeche); }
  .eta-modus { min-height: 48px; padding: 4px 2px; border: 0; border-radius: 9px; background: transparent; color: var(--text-2); font: inherit; font-size: 11px; font-weight: 500; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 2px; cursor: pointer; }
  .eta-modus .eta-icon { width: 18px; height: 18px; }
  .eta-modus[aria-pressed="true"] { background: var(--akzent); color: var(--auf-akzent); }

  .eta-soll { display: flex; align-items: center; gap: 8px; padding: 4px 4px 4px 12px; border-radius: 12px; background: var(--flaeche); }
  .eta-soll span { flex: 1; min-width: 0; color: var(--text-2); }
  .eta-soll b { min-width: 68px; text-align: center; font-size: 17px; font-weight: 500; font-variant-numeric: tabular-nums; white-space: nowrap; }
  .eta-rund { width: 44px; height: 44px; flex: none; border: 0; border-radius: 50%; background: var(--karte); color: var(--text); cursor: pointer; display: flex; align-items: center; justify-content: center; }
  .eta-rund:disabled { opacity: .4; cursor: default; }
  .eta-rund:focus-visible { outline: 2px solid var(--akzent); outline-offset: 2px; }

  .eta-tank { width: 100%; display: flex; flex-direction: column; align-items: center; }
  .eta-tank-stutzen { width: 30%; height: 9px; border-radius: 5px 5px 0 0; background: var(--metall); }
  .eta-tank-koerper { position: relative; width: 100%; height: var(--tankhoehe, 208px); box-sizing: border-box; border: 4px solid var(--metall); border-radius: 24px; overflow: hidden; background: var(--metall-dunkel); }
  .eta-tank-stroemung { position: absolute; inset: 0; opacity: 0; background: repeating-linear-gradient(180deg, rgba(255, 255, 255, 0) 0 14px, rgba(255, 255, 255, .2) 14px 18px); -webkit-mask-image: linear-gradient(90deg, transparent 4%, #000 35%, #000 65%, transparent 96%); mask-image: linear-gradient(90deg, transparent 4%, #000 35%, #000 65%, transparent 96%); transition: opacity .4s; }
  .eta-tank[data-laedt] .eta-tank-stroemung { opacity: 1; animation: eta-stroemen 1.1s linear infinite; }
  .eta-tank-fuehler { position: absolute; inset: 0; margin: 0; padding: 4px 0; list-style: none; display: flex; flex-direction: column; }
  .eta-tank-fuehler li { flex: 1; display: flex; align-items: center; justify-content: center; min-height: 0; }
  .eta-tank-fuehler span { padding: 1px 8px; border-radius: 10px; background: rgba(0, 0, 0, .34); color: #fff; font-size: 12.5px; line-height: 1.35; font-weight: 500; font-variant-numeric: tabular-nums; white-space: nowrap; }
  .eta-tank-kombi { position: absolute; left: 6px; right: 6px; top: 6px; height: calc(36% - 10px); box-sizing: border-box; border: 2px solid rgba(255, 255, 255, .88); border-radius: 14px; background: rgba(0, 0, 0, .28); display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 3px; color: #fff; font-size: 12.5px; font-weight: 500; font-variant-numeric: tabular-nums; white-space: nowrap; }
  .eta-tank-kombi .eta-hahn { position: static; transform: none; width: 24px; }
  .eta-tank[data-kombi] .eta-tank-fuehler { top: 36%; }
  .eta-hahn { position: absolute; left: 50%; top: 50%; width: 46%; transform: translate(-50%, -50%); fill: #fff; }

  .eta-svg [class^="z-"] { display: none; }
  [data-zustand="flamme"] .z-flamme, [data-zustand="glut"] .z-glut, [data-zustand="zuendung"] .z-zuendung, [data-zustand="entaschen"] .z-entaschen, [data-zustand="stoerung"] .z-stoerung { display: inline; }
  [data-zustand="entaschen"] .k-rost { display: none; }
  .k-anzeige { fill: var(--akzent); }
  [data-zustand="aus"] .k-anzeige { fill: var(--metall-dunkel); }
  [data-zustand="stoerung"] .k-anzeige { fill: var(--heiss); animation: eta-blinken 1s steps(2, jump-none) infinite; }
  .k-schein { opacity: 0; }
  [data-zustand="flamme"] .k-schein { opacity: 1; animation: eta-scheinen 1.6s ease-in-out infinite; }
  [data-zustand="glut"] .k-schein { opacity: .5; animation: eta-scheinen 3s ease-in-out infinite; }
  [data-zustand="zuendung"] .k-schein { opacity: .6; animation: eta-scheinen .45s ease-in-out infinite; }
  .zf { fill: none; stroke: #fff3b0; stroke-width: 2.6; stroke-linecap: round; stroke-linejoin: round; filter: drop-shadow(0 0 3px #ffb020); animation: eta-zucken .8s steps(1, end) infinite; animation-delay: calc(var(--i) * -.27s); }
  .fl { transform-box: fill-box; transform-origin: 50% 100%; animation: eta-lodern 1.1s ease-in-out infinite; }
  .fl2 { animation-duration: .8s; animation-delay: -.3s; }
  .fl3 { animation-duration: .6s; animation-delay: -.15s; }
  .gl { animation: eta-glimmen 1.8s ease-in-out infinite; animation-delay: calc(var(--i) * -.37s); }
  .gluehen { animation: eta-glimmen .7s ease-in-out infinite; }
  .funke { animation: eta-funke .9s ease-out infinite; animation-delay: calc(var(--i) * -.15s); }
  .klappe { transform-box: fill-box; transform-origin: center; animation: eta-kippen 1.6s ease-in-out infinite; animation-delay: calc(var(--i) * -.18s); }
  .asche { animation: eta-fallen 1.1s ease-in infinite; animation-delay: calc(var(--i) * -.23s); }
  .blink { animation: eta-blinken 1s steps(2, jump-none) infinite; }

  .h-rippe { fill: var(--metall); }
  .h-sammler { fill: var(--metall-dunkel); }
  .h-vor, .h-rueck { fill: none; stroke: var(--metall-dunkel); stroke-width: 6; stroke-linecap: round; }
  .h-fluss, .f-fluss, .fe-fluss { display: none; fill: none; stroke: #fff; stroke-opacity: .8; stroke-width: 2.4; stroke-linecap: round; stroke-dasharray: .1 10; }
  .h-schleife, .h-schleife-an { fill: none; stroke-width: 5; stroke-linecap: round; stroke-linejoin: round; }
  .h-schleife { stroke: var(--metall-dunkel); }
  .h-schleife-an { display: none; }
  [data-aktiv] .h-schleife-an { display: inline; }
  .h-wellen path { fill: none; stroke: var(--heiss); stroke-width: 3; stroke-linecap: round; opacity: 0; }
  [data-aktiv] .h-rippe { fill: var(--heiss); fill-opacity: var(--d); }
  [data-aktiv] .h-vor { stroke: var(--heiss); }
  [data-aktiv] .h-rueck { stroke: var(--kalt); }
  [data-aktiv] .h-fluss { display: inline; animation: eta-fluss-kurz .7s linear infinite; }
  [data-aktiv] .h-wellen path { animation: eta-aufsteigen 2.4s ease-out infinite; animation-delay: calc(var(--i) * -.8s); }

  .l-schnecke { fill: none; stroke: var(--metall-hell); stroke-width: 2.6; stroke-linejoin: round; }
  [data-foerdert] .l-schnecke { animation: eta-schnecke .6s linear infinite; }

  .s-sonne circle { fill: var(--metall-dunkel); }
  .s-strahlen { transform-origin: 32px 28px; }
  .s-strahlen line { stroke: var(--metall-dunkel); stroke-width: 3.5; stroke-linecap: round; }
  .s-zelle { fill: var(--zelle); }
  [data-aktiv] .s-sonne circle { fill: var(--sonne); }
  [data-aktiv] .s-strahlen { animation: eta-drehen 14s linear infinite; }
  [data-aktiv] .s-strahlen line { stroke: var(--sonne); }
  [data-aktiv] .s-zelle { fill: var(--f); animation: eta-leuchten 3s ease-in-out infinite; animation-delay: calc(var(--i) * -.25s); }

  .f-platte { fill: var(--metall); }
  .f-vor, .f-rueck, .f-warm, .f-kalt, .f-griff { fill: none; stroke: var(--metall-dunkel); stroke-width: 6; stroke-linecap: round; stroke-linejoin: round; }
  .f-griff { stroke-width: 4; }
  [data-fliesst] .f-platte { fill: var(--f); animation: eta-leuchten 1.6s ease-in-out infinite; animation-delay: calc(var(--i) * -.2s); }
  [data-fliesst] .f-vor { stroke: var(--heiss); }
  [data-fliesst] .f-rueck { stroke: var(--kalt); }
  [data-fliesst] .f-fluss.prim, [data-zapft] .f-fluss.sek { display: inline; animation: eta-fluss-kurz .7s linear infinite; }
  [data-zapft] .f-warm { stroke: var(--heiss); }
  [data-zapft] .f-kalt { stroke: var(--kalt); }
  .f-tropfen { fill: var(--kalt); opacity: 0; }
  [data-zapft] .f-tropfen { animation: eta-tropfen 1s ease-in infinite; animation-delay: calc(var(--i) * -.5s); }

  .fe-rohr { fill: none; stroke: var(--metall-dunkel); stroke-width: 6; stroke-linecap: round; stroke-linejoin: round; }
  .fe-boden { fill: none; stroke: var(--metall); stroke-width: 2.5; stroke-linecap: round; }
  .fe-pumpe { fill: var(--karte); stroke: var(--metall-dunkel); stroke-width: 3; }
  .fe-rad { fill: none; stroke: var(--metall-dunkel); stroke-width: 3; stroke-linecap: round; transform-origin: 24px 26px; }
  [data-pumpt] .fe-rohr, [data-pumpt] .fe-pumpe { stroke: var(--heiss); }
  [data-pumpt] .fe-rad { stroke: var(--heiss); animation: eta-drehen 1.2s linear infinite; }
  [data-pumpt] .fe-fluss { display: inline; animation: eta-fluss-kurz .7s linear infinite; }

  .p-zelle { fill: var(--pv); }
  .p-blitz { fill: var(--metall-dunkel); }
  [data-aktiv] .p-blitz { fill: #ffcf33; animation: eta-blitz 1.3s ease-in-out infinite; }
  [data-aktiv] .p-zelle { animation: eta-leuchten 2.6s ease-in-out infinite; animation-delay: calc(var(--i) * -.2s); }

  .b-anzeige { fill: var(--metall-dunkel); }
  .b-flamme { display: none; }
  [data-aktiv] .b-flamme { display: inline; }
  [data-aktiv] .b-anzeige { fill: var(--akzent); }

  .eta-szene { gap: 20px; padding: 20px; }
  .eta-bild { position: relative; display: grid; grid-auto-flow: column; grid-auto-columns: max-content; justify-content: space-between; align-items: center; column-gap: 52px; padding: 8px 4px; }
  .eta-bild[data-dicht] { column-gap: 30px; }
  .eta-bild[data-dicht] .eta-station .eta-figur { width: calc(var(--b, 110px) * .78); }
  .eta-bild[data-dicht] .eta-tank-koerper { height: calc(var(--tankhoehe, 208px) * .86); }
  .eta-bild[data-dicht] .eta-schild .eta-zahl { font-size: 20px; }
  .eta-bild[data-dicht] .eta-name { font-size: 13px; }
  .eta-bild[data-dicht] .eta-schild .eta-neben { font-size: 12px; }
  .eta-bild[data-dicht] .eta-tank-fuehler span { font-size: 11.5px; padding: 0 6px; }
  .eta-bild[data-dicht] .eta-tank-kombi { font-size: 11.5px; }
  .eta-bild[data-dicht] .eta-station.quer { gap: 10px; }
  .eta-anschluss { display: none; }
  .eta-bild[data-schmal] .eta-anschluss { display: inline; }
  .eta-leitungen { position: absolute; inset: 0; width: 100%; height: 100%; pointer-events: none; overflow: visible; }
  .eta-rohr { fill: none; stroke: var(--metall); stroke-width: 6; stroke-linecap: round; stroke-linejoin: round; }
  .eta-rohr[data-art="strom"] { stroke-width: 4; }
  .eta-rohr[data-aktiv][data-art="heiss"] { stroke: var(--heiss); }
  .eta-rohr[data-aktiv][data-art="pellets"] { stroke: var(--pellet); }
  .eta-rohr[data-aktiv][data-art="strom"] { stroke: var(--sonne); }
  .eta-rohr-fluss { fill: none; stroke: #fff; stroke-opacity: .9; stroke-width: 2.4; stroke-linecap: round; stroke-linejoin: round; stroke-dasharray: .1 13; animation: eta-fluss .85s linear infinite; }
  .eta-spalte { position: relative; display: flex; flex-direction: column; align-items: center; gap: 22px; min-width: 0; }
  .eta-verbraucher { align-items: stretch; gap: 14px; }
  .eta-station { position: relative; display: flex; flex-direction: column; align-items: center; gap: 10px; text-align: center; min-width: 0; }
  .eta-station.quer { flex-direction: row; text-align: left; gap: 14px; }
  .eta-station.quer.links { flex-direction: row-reverse; text-align: right; }
  .eta-bild:not([data-schmal]) .eta-station.oben { order: -1; }
  .eta-station .eta-figur { width: var(--b, 110px); }
  .eta-schild { display: flex; flex-direction: column; gap: 1px; min-width: 0; }
  .eta-station:not(.quer) .eta-schild { max-width: 168px; }
  .eta-name { font-size: 14px; font-weight: 500; }
  .eta-schild .eta-zahl { font-size: 24px; }
  .eta-schild .eta-neben { font-size: 12.5px; }
  .eta-szenenfuss { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 16px 24px; padding-top: 16px; border-top: 1px solid var(--rand); }
  .eta-kennzahlen { margin: 0; display: flex; flex-wrap: wrap; gap: 12px 28px; }
  .eta-kennzahlen div { display: flex; flex-direction: column; gap: 1px; }
  .eta-kennzahlen dt { font-size: 12px; color: var(--text-2); }
  .eta-kennzahlen dd { margin: 0; font-size: 15px; font-weight: 500; font-variant-numeric: tabular-nums; }
  .eta-szenenfuss .eta-bedienung { flex: 1 1 300px; max-width: 420px; display: flex; flex-direction: column; gap: 8px; }
  .eta-bild[data-schmal] { display: flex; flex-direction: column; align-items: stretch; gap: 18px; padding: 0; }
  .eta-bild[data-schmal] .eta-leitungen { display: none; }
  .eta-bild[data-schmal] .eta-spalte { display: contents; }
  .eta-bild[data-schmal] .eta-station { flex-direction: row; align-items: center; text-align: left; gap: 14px; padding-left: 22px; }
  .eta-bild[data-schmal] .eta-station .eta-figur { --b: 88px !important; }
  .eta-bild[data-schmal] [data-art="puffer"] .eta-figur { --tankhoehe: 176px !important; }
  .eta-bild[data-schmal] [data-art="puffer"][data-kombi] .eta-figur { --tankhoehe: 232px !important; }
  .eta-bild[data-schmal] .eta-station::before { content: ""; position: absolute; left: 3px; top: -9px; bottom: -9px; width: 6px; border-radius: 3px; background-color: var(--metall); }
  .eta-bild[data-schmal] .eta-station[data-erste]::before { top: 50%; }
  .eta-bild[data-schmal] .eta-station[data-letzte]::before { bottom: 50%; }
  .eta-bild[data-schmal] .eta-station[data-fluss]::before { background-color: var(--heiss); background-image: radial-gradient(circle, rgba(255, 255, 255, .95) 1.2px, transparent 1.7px); background-size: 6px 13px; animation: eta-schiene .85s linear infinite; }
  .eta-bild[data-schmal] .eta-station[data-fluss="pellets"]::before { background-color: var(--pellet); }
  .eta-bild[data-schmal] .eta-station[data-fluss="strom"]::before { background-color: var(--sonne); }

  .eta-kompakt { max-width: 480px; margin: 0 auto; }
  .eta-kompakt-kopf { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
  .eta-kompakt-kopf h3 { margin: 0; font-size: 18px; font-weight: 500; }
  .eta-kompakt .eta-buehne { justify-content: space-between; padding: 12px; min-height: 0; }
  .eta-kompakt .eta-figur { width: var(--b); }
  .eta-kompakt .eta-haupt { flex: 0 1 auto; }
  .eta-kompakt .eta-zahl { font-size: 30px; }
  .eta-kompakt .eta-neben { white-space: nowrap; }
  .eta-gruppe { display: flex; align-items: center; gap: 10px; }
  .eta-liste { display: flex; flex-direction: column; }
  .eta-reihe { display: flex; align-items: center; gap: 12px; min-height: 56px; padding: 6px 0; border-top: 1px solid var(--rand); }
  .eta-reihe:first-child { border-top: 0; }
  .eta-reihe[data-aktion] { cursor: pointer; }
  .eta-reihe[data-aktion]:focus-visible { outline: 2px solid var(--akzent); outline-offset: 2px; }
  .eta-pfeil { color: var(--text-2); transition: transform .2s; }
  [aria-expanded="true"] .eta-pfeil { transform: rotate(180deg); }
  .eta-klappe { display: flex; flex-direction: column; gap: 8px; padding: 2px 0 14px; }
  .eta-symbol { width: 36px; height: 36px; flex: none; border-radius: 10px; background: var(--flaeche); display: flex; align-items: center; justify-content: center; color: var(--text-2); }
  .eta-symbol[data-an] { background: var(--akzent); color: var(--auf-akzent); }
  .eta-reihe-text { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 3px; }
  .eta-reihe-text b { font-weight: 500; }
  .eta-reihe-text span { font-size: 12px; color: var(--text-2); }
  .eta-reihe-wert { font-size: 17px; font-weight: 500; font-variant-numeric: tabular-nums; white-space: nowrap; }

  @keyframes eta-puls { 0%, 100% { box-shadow: 0 0 0 0 rgba(255, 155, 0, .55); } 50% { box-shadow: 0 0 0 5px rgba(255, 155, 0, 0); } }
  @keyframes eta-blinken { 0% { opacity: 1; } 100% { opacity: .25; } }
  @keyframes eta-scheinen { 0%, 100% { opacity: .75; } 50% { opacity: 1; } }
  @keyframes eta-lodern { 0%, 100% { transform: scale(1, 1) skewX(0deg); } 25% { transform: scale(.93, 1.09) skewX(-4deg); } 50% { transform: scale(1.05, .93) skewX(2deg); } 75% { transform: scale(.96, 1.06) skewX(4deg); } }
  @keyframes eta-zucken { 0% { opacity: 1; } 16% { opacity: .1; } 30% { opacity: 1; } 50% { opacity: 0; } 62% { opacity: 1; } 80% { opacity: .25; } }
  @keyframes eta-blitz { 0%, 100% { filter: drop-shadow(0 0 2px rgba(255, 207, 51, .5)); opacity: .85; } 50% { filter: drop-shadow(0 0 7px rgba(255, 207, 51, .95)); opacity: 1; } }
  @keyframes eta-glimmen { 0%, 100% { opacity: .45; } 50% { opacity: 1; } }
  @keyframes eta-funke { 0% { transform: translate(0, 0); opacity: 1; } 100% { transform: translate(var(--dx), var(--dy)); opacity: 0; } }
  @keyframes eta-kippen { 0%, 35% { transform: scaleY(1); } 50% { transform: scaleY(.1); } 65%, 100% { transform: scaleY(1); } }
  @keyframes eta-fallen { 0% { transform: translateY(0); opacity: 0; } 15% { opacity: 1; } 100% { transform: translateY(19px); opacity: 0; } }
  @keyframes eta-aufsteigen { 0% { transform: translateY(5px); opacity: 0; } 30% { opacity: .85; } 100% { transform: translateY(-7px); opacity: 0; } }
  @keyframes eta-fluss-kurz { to { stroke-dashoffset: -10.1; } }
  @keyframes eta-fluss { to { stroke-dashoffset: -13.1; } }
  @keyframes eta-schiene { to { background-position: 0 13px; } }
  @keyframes eta-stroemen { to { background-position: 0 18px; } }
  @keyframes eta-tropfen { 0% { transform: translateY(0); opacity: 0; } 20% { opacity: 1; } 100% { transform: translateY(13px); opacity: 0; } }
  @keyframes eta-schnecke { to { transform: translateX(12px); } }
  @keyframes eta-drehen { to { transform: rotate(360deg); } }
  @keyframes eta-leuchten { 0%, 100% { fill-opacity: .78; } 50% { fill-opacity: 1; } }

  .eta[data-ruhe] *, .eta[data-ruhe] *::before { animation: none !important; }
  @media (prefers-reduced-motion: reduce) { .eta *, .eta *::before { animation: none !important; transition: none !important; } }
  @container (max-width: 480px) {
    .eta-zahl { font-size: 30px; }
    .eta-szene { padding: 14px; }
  }
`;

const sym = (d, klasse = "") => `<svg class="eta-icon ${klasse}" viewBox="0 0 24 24" aria-hidden="true">${d}</svg>`;
const UMLAUF = '<path d="M5 12a7 7 0 0 1 12-5l2 2"/><path d="M19 5v4h-4"/><path d="M19 12a7 7 0 0 1-12 5l-2-2"/><path d="M5 19v-4h4"/>';
const ICON = {
  flamme: sym('<path d="M12 3c.6 3.2 4.5 5 4.5 9.5a4.5 4.5 0 0 1-9 0c0-2 .9-3.4 2-4.5.2 1.8 1 2.7 2 3-.3-3 .1-5.6.5-8z"/>'),
  uhr: sym('<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/>'),
  blatt: sym('<path d="M5 19C5 10 10 5 19 5c0 9-5 14-14 14z"/><path d="M5 19c3-5 6-8 10-10"/>'),
  aus: sym('<path d="M12 3v8"/><path d="M6.3 7.2a8 8 0 1 0 11.4 0"/>'),
  besen: sym('<path d="M14.5 3.5l6 6"/><path d="M12 6l6 6-4.5 4.5-6-6z"/><path d="M7.5 10.5L3 20.5l10-4.5"/>'),
  box: sym('<path d="M4 8h16l-1.5 11h-13z"/><path d="M9 8V5h6v3"/>'),
  thermo: sym('<path d="M10 14.5V5a2 2 0 1 1 4 0v9.5a4 4 0 1 1-4 0z"/>'),
  minus: sym('<path d="M6 12h12"/>'),
  plus: sym('<path d="M12 6v12M6 12h12"/>'),
  pfeil: sym('<path d="M6 9l6 6 6-6"/>', "eta-pfeil"),
  haken: sym('<path d="M5 12.5l4.5 4.5L19 7.5"/>'),
  warn: sym('<path d="M12 4l9 16H3z"/><path d="M12 10v4.5M12 17.5v.01"/>'),
  umlauf: sym(UMLAUF),
  umlaufAn: sym(UMLAUF, "eta-dreht"),
  blitz: sym('<path d="M13 3 5 13h6l-1 8 8-10h-6z"/>'),
  rohr: sym('<path d="M3 8h5a3 3 0 0 1 3 3v2a3 3 0 0 0 3 3h7"/>'),
  tropfen: sym('<path d="M12 3.5s6 6.3 6 10.7a6 6 0 0 1-12 0c0-4.4 6-10.7 6-10.7z"/>'),
  heizung: sym('<rect x="3" y="6" width="18" height="11" rx="2"/><path d="M8 6v11M12 6v11M16 6v11M6 17v3M18 17v3"/>'),
  lager: sym('<path d="M5 21V10l7-6 7 6v11z"/><path d="M5 15h14"/>'),
  sonne: sym('<circle cx="12" cy="12" r="4"/><path d="M12 2v2.5M12 19.5V22M2 12h2.5M19.5 12H22M4.9 4.9l1.8 1.8M17.3 17.3l1.8 1.8M4.9 19.1l1.8-1.8M17.3 6.7l1.8-1.8"/>'),
};

const DEFS = `<svg class="eta-defs" aria-hidden="true"><defs>
  <radialGradient id="eta-schein" cx=".5" cy="1" r=".95"><stop offset="0" stop-color="#ff9b00" stop-opacity=".8"/><stop offset="1" stop-color="#ff9b00" stop-opacity="0"/></radialGradient>
  <linearGradient id="eta-boden" gradientUnits="userSpaceOnUse" x1="0" y1="46" x2="0" y2="94"><stop offset="0" style="stop-color:var(--heiss)"/><stop offset="1" style="stop-color:var(--kalt)"/></linearGradient>
  <pattern id="eta-pellets" width="24" height="15" patternUnits="userSpaceOnUse">
    <rect width="24" height="15" fill="var(--pellet)"/>
    <rect x="2" y="2" width="8.5" height="3.4" rx="1.7" fill="var(--pellet-hell)"/>
    <rect x="14" y="4.5" width="7.5" height="3.4" rx="1.7" fill="var(--pellet-dunkel)"/>
    <rect x="5" y="9" width="8.5" height="3.4" rx="1.7" fill="var(--pellet-dunkel)"/>
    <rect x="16" y="10.5" width="6.5" height="3.2" rx="1.6" fill="var(--pellet-hell)"/>
  </pattern>
</defs></svg>`;

const reihe = (anzahl, zeichnen) => Array.from({ length: anzahl }, (_, i) => zeichnen(i)).join("");

const kesselBild = () => `<svg class="eta-svg" viewBox="14 0 132 170" aria-hidden="true">
  <rect x="102" y="2" width="20" height="22" rx="3" fill="var(--metall-dunkel)"/>
  <rect x="16" y="18" width="128" height="140" rx="12" fill="var(--metall)"/>
  <path d="M16 30a12 12 0 0 1 12-12h104a12 12 0 0 1 12 12v16H16z" fill="var(--metall-hell)"/>
  <rect x="28" y="25" width="42" height="14" rx="3.5" fill="var(--kammer)"/>
  <rect class="k-anzeige" x="31.5" y="28.5" width="19" height="7" rx="1.5"/>
  <circle cx="57.5" cy="32" r="2" fill="var(--metall-dunkel)"/><circle cx="64" cy="32" r="2" fill="var(--metall-dunkel)"/>
  <rect x="28" y="54" width="104" height="72" rx="9" fill="var(--metall-dunkel)"/>
  <rect x="37" y="62" width="86" height="56" rx="6" fill="var(--kammer)"/>
  <rect class="k-schein" x="37" y="62" width="86" height="56" rx="6" fill="url(#eta-schein)"/>
  <g class="z-flamme">
    <path class="fl" fill="#ff7a1a" d="M80 66C86 78 100 84 100 96C100 104 91 108 80 108C69 108 60 104 60 96C60 88 66 84 69 76C72 81 74 83 76 82C77 76 77 71 80 66Z"/>
    <path class="fl fl2" fill="#ffb020" d="M80 78C85 86 93 90 93 98C93 104 87 108 80 108C73 108 67 104 67 98C67 93 71 90 73 85C75 88 77 89 78 88C78 84 78 81 80 78Z"/>
    <path class="fl fl3" fill="#ffe08a" d="M80 90C83 94 87 97 87 101C87 105 84 108 80 108C76 108 73 105 73 101C73 97 77 94 80 90Z"/>
  </g>
  <g class="z-glut">
    ${[50, 60, 70, 80, 90, 100, 110].map((x, i) => `<ellipse cx="${x}" cy="${i % 2 ? 104 : 105.5}" rx="6" ry="3.4" fill="#8f2a10"/>`).join("")}
    ${[54, 65, 76, 87, 98, 107].map((x, i) => `<ellipse class="gl" style="--i:${i}" cx="${x}" cy="${i % 2 ? 105 : 103.5}" rx="5" ry="2.8" fill="#ff6a24"/>`).join("")}
  </g>
  <g class="z-zuendung">
    ${[60, 69, 91, 100].map((x, i) => `<ellipse cx="${x}" cy="${i % 2 ? 105 : 104}" rx="5" ry="2.7" fill="var(--pellet)"/>`).join("")}
    <ellipse class="gluehen" cx="80" cy="105" rx="10" ry="4.2" fill="#ff7a1a"/>
    <ellipse class="gluehen" cx="80" cy="105" rx="5" ry="2.1" fill="#ffe08a"/>
    <path class="zf" style="--i:0" d="M80 103 73 94 77 91 67 79"/>
    <path class="zf" style="--i:1" d="M80 103 87 93 83 90 93 77"/>
    <path class="zf" style="--i:2" d="M80 103 81 93 78 89 80 76"/>
    ${[[-14, -20], [16, -18], [-6, -27], [8, -29], [-20, -11], [22, -9]].map(([dx, dy], i) => `<circle class="funke" style="--i:${i};--dx:${dx}px;--dy:${dy}px" cx="80" cy="101" r="2" fill="#ffe08a"/>`).join("")}
  </g>
  <g class="z-entaschen">
    ${reihe(5, (i) => `<rect class="klappe" style="--i:${i}" x="${46 + i * 14}" y="88" width="12" height="6" rx="2" fill="#8a909a"/>`)}
    ${[50, 58, 66, 74, 82, 90, 98, 106].map((x, i) => `<circle class="asche" style="--i:${i}" cx="${x}" cy="97" r="1.6" fill="#a9aeb6"/>`).join("")}
    <path d="M44 118q36 -10 72 0z" fill="#8d939c"/>
  </g>
  <g class="z-stoerung blink">
    <path d="M80 72 102 108H58z" fill="#f5b301" stroke="#f5b301" stroke-width="6" stroke-linejoin="round"/>
    <rect x="77.8" y="82" width="4.4" height="14" rx="2.2" fill="#1d2025"/><circle cx="80" cy="102" r="2.7" fill="#1d2025"/>
  </g>
  <rect class="k-rost" x="45" y="108" width="70" height="3.5" rx="1.75" fill="#737984"/>
  <rect x="28" y="132" width="104" height="16" rx="4" fill="var(--metall-dunkel)"/>
  <rect x="66" y="138" width="28" height="4" rx="2" fill="var(--metall-hell)"/>
  <rect x="26" y="158" width="16" height="9" rx="2" fill="var(--metall-dunkel)"/><rect x="118" y="158" width="16" height="9" rx="2" fill="var(--metall-dunkel)"/>
</svg>`;

const heizkreisBild = () => `<svg class="eta-svg" viewBox="0 0 150 106" aria-hidden="true">
  <g class="h-wellen">${[46, 78, 110].map((x, i) => `<path style="--i:${i}" d="M${x} 28c-5-6 5-10 0-17"/>`).join("")}</g>
  <path class="h-vor" d="M4 46h20"/><path class="h-rueck" d="M4 94h20"/>
  ${reihe(8, (i) => `<rect class="h-rippe" style="--d:${(1 - i * 0.075).toFixed(2)}" x="${24 + i * 14}" y="38" width="10" height="64" rx="5"/>`)}
  <rect class="h-sammler" x="22" y="42" width="116" height="8" rx="4"/><rect class="h-sammler" x="22" y="90" width="116" height="8" rx="4"/>
  <path class="h-fluss" d="M26 46h108"/><path class="h-fluss" d="M134 94H26"/>
  <circle cx="143" cy="46" r="6" fill="var(--metall-dunkel)"/>
</svg>`;

/** Der Heizkreis als Fußbodenheizung: eine Rohrschleife im Boden, vorn warm, hinten abgekühlt. */
const fussbodenBild = () => {
  const schleife = "M24 46H128a6 6 0 0 1 0 12H38a6 6 0 0 0 0 12H128a6 6 0 0 1 0 12H38a6 6 0 0 0 0 12H24";
  return `<svg class="eta-svg" viewBox="0 0 150 106" aria-hidden="true">
    <g class="h-wellen">${[46, 78, 110].map((x, i) => `<path style="--i:${i}" d="M${x} 28c-5-6 5-10 0-17"/>`).join("")}</g>
    <rect x="16" y="36" width="126" height="68" rx="9" fill="var(--metall)" fill-opacity=".3"/>
    <path class="h-vor" d="M4 46h20"/><path class="h-rueck" d="M4 94h20"/>
    <path class="h-schleife" d="${schleife}"/><path class="h-schleife-an" stroke="url(#eta-boden)" d="${schleife}"/>
    <path class="h-fluss" d="${schleife}"/>
  </svg>`;
};

const lagerBild = (anteil) => {
  const y = (76 * (1 - anteil)).toFixed(1);
  let zick = "M-12 6";
  for (let x = -6, oben = true; x <= 108; x += 6, oben = !oben) zick += `L${x} ${oben ? 1 : 11}`;
  return `<svg class="eta-svg" viewBox="0 0 150 170" aria-hidden="true">
    <path d="M14 46 75 10l61 36z" fill="var(--metall-dunkel)" stroke="var(--metall-dunkel)" stroke-width="6" stroke-linejoin="round"/>
    <path d="M22 46h106v88l-30 22H52l-30-22z" fill="var(--metall)"/>
    <rect x="32" y="54" width="86" height="76" rx="4" fill="var(--kammer)"/>
    <svg x="32" y="54" width="86" height="76" viewBox="0 0 86 76">
      <rect x="0" y="${y}" width="86" height="76" fill="url(#eta-pellets)"/>
      <rect x="0" y="${y}" width="86" height="3" fill="#fff" fill-opacity=".28"/>
    </svg>
    <rect x="46" y="152" width="98" height="14" rx="7" fill="var(--metall-dunkel)"/>
    <svg x="50" y="153" width="90" height="12" viewBox="0 0 90 12"><path class="l-schnecke" d="${zick}"/></svg>
  </svg>`;
};

const paneel = (klasse, farben) => {
  let zellen = "";
  for (let r = 0; r < 3; r++) {
    for (let c = 0; c < 4; c++) {
      zellen += `<rect class="${klasse}" style="${farben ? `--f:${farben[r]};` : ""}--i:${r * 4 + c}" x="${4 + c * 25}" y="${4 + r * 15}" width="21" height="12" rx="1.5"/>`;
    }
  }
  return `<g transform="translate(36 56) skewX(-16)"><rect x="0" y="0" width="104" height="50" rx="4" fill="var(--metall-dunkel)"/>${zellen}</g>
    <rect x="71" y="106" width="6" height="7" fill="var(--metall-dunkel)"/><rect x="53" y="111" width="42" height="5" rx="2.5" fill="var(--metall-dunkel)"/>`;
};

const solarBild = () => {
  const strahlen = reihe(8, (k) => {
    const w = (k * Math.PI) / 4, c = Math.cos(w), s = Math.sin(w);
    return `<line x1="${(32 + 17 * c).toFixed(1)}" y1="${(28 + 17 * s).toFixed(1)}" x2="${(32 + 23 * c).toFixed(1)}" y2="${(28 + 23 * s).toFixed(1)}"/>`;
  });
  return `<svg class="eta-svg" viewBox="0 0 150 118" aria-hidden="true">
    <g class="s-sonne"><g class="s-strahlen">${strahlen}</g><circle cx="32" cy="28" r="12"/></g>
    ${paneel("s-zelle", ["var(--heiss)", "#9a5fb0", "var(--kalt)"])}
  </svg>`;
};

const pvmBild = () => `<svg class="eta-svg" viewBox="0 0 150 118" aria-hidden="true">
  <path class="p-blitz" d="M40 4 24 30h10l-5 20 18-27H36l6-19z"/>
  ${paneel("p-zelle")}
</svg>`;

const fwmBild = () => `<svg class="eta-svg" viewBox="0 0 150 112" aria-hidden="true">
  <path class="f-vor" d="M6 34h26"/><path class="f-rueck" d="M6 80h26"/>
  <path class="f-warm" d="M106 34h20a10 10 0 0 1 10 10v8"/><path class="f-griff" d="M122 34v-9M115 25h14"/>
  <path class="f-kalt" d="M106 80h36"/>
  <rect x="30" y="10" width="78" height="92" rx="10" fill="var(--metall)"/>
  <rect x="42" y="22" width="54" height="68" rx="5" fill="var(--metall-dunkel)"/>
  ${reihe(6, (i) => `<rect class="f-platte" style="--f:${i % 2 ? "var(--kalt)" : "var(--heiss)"};--i:${i}" x="${47.5 + i * 7.5}" y="27" width="4.5" height="58" rx="2.25"/>`)}
  <path class="f-fluss prim" d="M8 34h22"/><path class="f-fluss prim" d="M30 80H8"/>
  <path class="f-fluss sek" d="M108 34h18a10 10 0 0 1 10 10v6"/><path class="f-fluss sek" d="M142 80h-34"/>
  ${reihe(2, (i) => `<path class="f-tropfen" style="--i:${i}" d="M136 58c2.4 3.4 4 5.2 4 7.4a4 4 0 0 1-8 0c0-2.2 1.6-4 4-7.4z"/>`)}
</svg>`;

const fernBild = () => {
  const weg = "M4 26H44a8 8 0 0 1 8 8v30a8 8 0 0 0 8 8h30a8 8 0 0 0 8-8V34a8 8 0 0 1 8-8h40";
  return `<svg class="eta-svg" viewBox="0 0 150 84" aria-hidden="true">
    <path class="fe-boden" d="M34 46H116M42 52l-5 6M66 52l-5 6M80 52l-5 6M94 52l-5 6M112 52l-5 6"/>
    <path class="fe-rohr" d="${weg}"/><path class="fe-fluss" d="${weg}"/>
    <circle class="fe-pumpe" cx="24" cy="26" r="11"/>
    <g class="fe-rad"><path d="M24 26v-7M24 26l6 3.5M24 26l-6 3.5"/></g>
  </svg>`;
};

const brennerBild = () => `<svg class="eta-svg" viewBox="20 0 110 106" aria-hidden="true">
  <rect x="40" y="6" width="70" height="94" rx="10" fill="var(--metall)"/>
  <path d="M40 16a10 10 0 0 1 10-10h50a10 10 0 0 1 10 10v12H40z" fill="var(--metall-hell)"/>
  <rect x="49" y="12" width="24" height="10" rx="2.5" fill="var(--kammer)"/><rect class="b-anzeige" x="51.5" y="14.5" width="10" height="5" rx="1"/>
  <rect x="54" y="44" width="42" height="36" rx="6" fill="var(--kammer)"/>
  <g class="b-flamme">
    <path class="fl" fill="#3b82f6" d="M75 50c5 7 10 10 10 17a10 9 0 0 1-20 0c0-5 3-7 5-11 1 2 2 3 3 2 0-3 0-5 2-8z"/>
    <path class="fl fl2" fill="#b7d4ff" d="M75 61c3 4 5 5 5 9a5 5 0 0 1-10 0c0-3 3-5 5-9z"/>
  </g>
</svg>`;

const HAHN = `<svg class="eta-hahn" viewBox="0 0 48 36" aria-hidden="true">
  <path d="M13 6h16v4h-6v5h-4v-5h-6z"/><path d="M6 15h24a9 9 0 0 1 9 9v7h-9v-6H6z"/>
</svg>`;

const STUFEN = [[20, [47, 111, 208]], [35, [90, 107, 200]], [45, [138, 92, 180]], [55, [184, 80, 138]], [65, [217, 71, 90]], [80, [229, 65, 45]]];

/** Die Farbe einer Temperatur im Speicher: blau bei 20 °C, rot ab 80 °C. */
function farbe(grad) {
  const rgb = (c) => `rgb(${c.join(",")})`;
  if (grad <= STUFEN[0][0]) return rgb(STUFEN[0][1]);
  for (let i = 1; i < STUFEN.length; i++) {
    if (grad <= STUFEN[i][0]) {
      const [t0, c0] = STUFEN[i - 1], [t1, c1] = STUFEN[i], f = (grad - t0) / (t1 - t0);
      return rgb(c0.map((c, k) => Math.round(c + (c1[k] - c) * f)));
    }
  }
  return rgb(STUFEN[STUFEN.length - 1][1]);
}

function e(text) {
  return String(text ?? "").replace(/[&<>"']/g, (z) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[z]);
}

function sprache(code) {
  return String(code || "de").toLowerCase().startsWith("de") ? "de" : "en";
}

/**
 * Ein Speicher, gefärbt nach seinen Temperaturen von oben nach unten.
 * Ohne Fühler mit Wert bleibt er grau. Die Werte stehen im Speicher;
 * mit hahn stattdessen ein Wasserhahn - so zeigt sich der
 * Warmwasserspeicher. kombi: der Text für den Warmwasserbereich, der
 * oben im Kombispeicher abgesetzt steht; die Fühler rücken darunter.
 */
function tank(grade, texte, { laedt = false, hahn = false, kombi = null } = {}) {
  const bekannt = grade.filter((g) => g !== null);
  const farben = grade.map((g) => farbe(g ?? bekannt[0] ?? 20));
  const ab = kombi === null ? 0 : 36;
  const stopps = farben.map((f, i) => `${f} ${(ab + ((i + 0.5) / farben.length) * (100 - ab)).toFixed(1)}%`);
  if (ab) stopps.unshift(`${farben[0]} 0%`);
  const verlauf = !bekannt.length ? "" : stopps.length > 1 ? `background: linear-gradient(180deg, ${stopps.join(", ")})` : `background: ${farben[0]}`;
  const bereich = kombi === null ? "" : `<div class="eta-tank-kombi">${HAHN}<b>${e(kombi)}</b></div>`;
  const innen = hahn ? HAHN : `${bereich}<ol class="eta-tank-fuehler">${texte.map((t) => `<li><span>${e(t)}</span></li>`).join("")}</ol>`;
  return `<div class="eta-tank" ${laedt ? "data-laedt" : ""} ${ab ? "data-kombi" : ""}><div class="eta-tank-stutzen"></div><div class="eta-tank-koerper" style="${verlauf}"><div class="eta-tank-stroemung"></div>${innen}</div></div>`;
}

/**
 * Gleicht den gezeigten Baum an einen neu gezeichneten an, ohne ihn zu
 * ersetzen. Was gleich bleibt, behält seine laufende Animation - sonst
 * finge die Flamme bei jedem neuen Messwert von vorn an. Kinder eines
 * Knotens mit data-fest bleiben unberührt: die ausgemessenen Leitungen.
 * Ebenso die Merkmale in GEMESSEN, die erst das Ausmessen setzt.
 */
const GEMESSEN = ["data-schmal", "data-dicht", "data-erste", "data-letzte"];

function angleichen(alt, neu) {
  if (alt.nodeType !== neu.nodeType || alt.nodeName !== neu.nodeName) {
    alt.replaceWith(neu);
    return;
  }
  if (alt.nodeType === Node.TEXT_NODE) {
    if (alt.data !== neu.data) alt.data = neu.data;
    return;
  }
  if (alt.nodeType !== Node.ELEMENT_NODE) return;
  for (const merkmal of [...alt.attributes]) {
    if (!neu.hasAttribute(merkmal.name) && !GEMESSEN.includes(merkmal.name)) alt.removeAttribute(merkmal.name);
  }
  for (const merkmal of [...neu.attributes]) {
    if (alt.getAttribute(merkmal.name) !== merkmal.value) alt.setAttribute(merkmal.name, merkmal.value);
  }
  if (alt.hasAttribute("data-fest")) return;
  const alte = [...alt.childNodes], neue = [...neu.childNodes];
  neue.forEach((kind, i) => (i < alte.length ? angleichen(alte[i], kind) : alt.appendChild(kind)));
  alte.slice(neue.length).forEach((kind) => kind.remove());
}

/** Ein orthogonaler Leitungsweg mit runden Ecken. */
function pfad(punkte, r = 12) {
  const p = punkte.filter((q, i) => i === 0 || Math.hypot(q[0] - punkte[i - 1][0], q[1] - punkte[i - 1][1]) > 0.5);
  const f = (q) => `${q[0].toFixed(1)} ${q[1].toFixed(1)}`;
  let d = `M${f(p[0])}`;
  for (let i = 1; i < p.length - 1; i++) {
    const a = p[i - 1], b = p[i], c = p[i + 1];
    const l1 = Math.hypot(b[0] - a[0], b[1] - a[1]), l2 = Math.hypot(c[0] - b[0], c[1] - b[1]), rr = Math.min(r, l1 / 2, l2 / 2);
    const s = [b[0] + ((a[0] - b[0]) / l1) * rr, b[1] + ((a[1] - b[1]) / l1) * rr];
    const z = [b[0] + ((c[0] - b[0]) / l2) * rr, b[1] + ((c[1] - b[1]) / l2) * rr];
    d += ` L${f(s)} Q${f(b)} ${f(z)}`;
  }
  return `${d} L${f(p[p.length - 1])}`;
}

/** Wo eine Leitung an der Zeichnung eines Teils ansetzt, als Anteil von Breite und Höhe. */
const AUS = { lager: [0.96, 0.935], kessel: [0.985, 0.3], solar: [0.885, 0.69], pvm: [0.885, 0.69], brenner: [0.82, 0.5], puffer: [1, 0.14], fernleitung: [0.975, 0.31] };
const EIN = { kessel: [0.015, 0.82], puffer: [0, 0.14], fernleitung: [0.025, 0.31], heizkreis: [0.04, 0.434], fwm: [0.04, 0.304], speicher: [0, 0.55] };

/**
 * Liest die Anlage aus den Entitäten: je Teil, was die Karte zeigt.
 *
 * Ein Wert ist null, wenn es seine Entität nicht gibt oder die Anlage
 * dafür "-" meldet, etwa bei einem Warmwasserspeicher ohne Zirkulation -
 * dann fehlt die Zeile. Meldet die Entität nichts, steht ein Strich.
 *
 * Beim Warmwasserspeicher sind Laden und Zirkulation zweierlei: laedt
 * kommt von der Ladepumpe, ohne sie vom Zustand. Das Frischwassermodul
 * erwärmt Wasser (fliesst), solange seine Pufferpumpe läuft - bei
 * laufender Zirkulation und beim Zapfen. zapft heißt deshalb: Die
 * Pufferpumpe läuft, die Zirkulation nicht.
 * fussboden: die Heizkreise, die als Fußbodenheizung gezeichnet werden.
 */
function anlageLesen(hass, struktur, t, fussboden) {
  const stand = (schluessel) => {
    const id = struktur.entitaeten[schluessel];
    return id ? hass.states[id] : undefined;
  };
  const wert = (schluessel) => {
    const s = stand(schluessel);
    if (!s) return null;
    if (s.state === "-") return null;
    const fehlt = s.state === "unavailable" || s.state === "unknown";
    const einheit = fehlt ? "" : s.attributes.unit_of_measurement || "";
    const text = fehlt ? "–" : hass.formatEntityState ? hass.formatEntityState(s) : `${s.state}${einheit ? ` ${einheit}` : ""}`;
    const zahl = einheit && text.endsWith(einheit) ? text.slice(0, -einheit.length).trim() : text;
    const n = fehlt || s.state === "" || Number.isNaN(Number(s.state)) ? null : Number(s.state);
    return { id: s.entity_id, text, zahl, einheit, roh: fehlt ? "" : s.state, n };
  };
  const an = (w) => Boolean(w) && (w.n === null ? !OHNE_FLUSS.includes(w.roh) : w.n > 0);
  const ueber = (w) => Boolean(w) && w.n !== null && w.n > LEISTUNG_AB;
  const mehrere = (art) => struktur.teile.filter((teil) => teil.art === art).length > 1;

  const lesen = {
    kessel() {
      const zustand = wert("kessel_zustand");
      const bild = Object.keys(KESSEL_BILDER).find((b) => KESSEL_BILDER[b].includes(zustand?.roh)) || "aus";
      const schalter = stand("kessel_schalter");
      const plan = wert("aschebox_plan");
      const asche = wert("aschebox_verbrauch"), schwelle = wert("aschebox_schwelle");
      return {
        name: t.kessel,
        zustand,
        bild,
        temperatur: wert("kessel_temperatur"),
        soll: wert("kessel_soll"),
        zeilen: [[t.ruecklauf, wert("ruecklauf_temperatur")], [t.druck, wert("kessel_druck")], [t.o2, wert("restsauerstoff")], [t.behaelter, wert("pellet_tagesbehälter")]].filter(([, w]) => w),
        asche,
        ascheStatus: wert("aschebox_status"),
        ascheAnteil: asche && schwelle && asche.n !== null && schwelle.n ? Math.min(asche.n / schwelle.n, 1) : null,
        schalter: schalter ? { id: schalter.entity_id, an: schalter.state === "on" } : null,
        entaschen: struktur.entitaeten.kessel_entaschen || null,
        leeren: struktur.entitaeten.aschebox_leeren_um || null,
        abbrechen: struktur.entitaeten.aschebox_plan_abbrechen || null,
        plan: plan && PLAN_LAEUFT.includes(plan.roh) ? plan : null,
      };
    },
    puffer(teil) {
      const fuehler = [];
      for (let nr = 1; struktur.entitaeten[`${teil.id}_fuehler_${nr}`]; nr++) fuehler.push(wert(`${teil.id}_fuehler_${nr}`));
      const zustand = wert(`${teil.id}_zustand`);
      const kombi = wert(`${teil.id}_warmwasser`), kombiZustand = wert(`${teil.id}_warmwasser_zustand`);
      return {
        name: mehrere("puffer") ? teil.block : t.puffer,
        fuehler: fuehler.filter(Boolean),
        ladung: wert(`${teil.id}_ladezustand`),
        energie: wert(`${teil.id}_energieinhalt`),
        ladepumpe: wert(`${teil.id}_ladepumpe`),
        zustand,
        laedt: PUFFER_LAEDT.includes(zustand?.roh),
        kombi: kombi ? { temperatur: kombi, zustand: kombiZustand, laedt: WARMWASSER_LAEDT.includes(kombiZustand?.roh) } : null,
      };
    },
    warmwasser(teil) {
      const fwm = teil.bauart === "fwm";
      const zirkulation = wert(`${teil.id}_zirkulationspumpe`), zustand = wert(`${teil.id}_zustand`);
      const ladepumpe = wert(`${teil.id}_ladepumpe`), pufferpumpe = wert(`${teil.id}_pufferpumpe`);
      const zirkuliert = an(zirkulation);
      const fliesst = fwm && (pufferpumpe ? an(pufferpumpe) : zirkuliert);
      return {
        name: mehrere("warmwasser") ? teil.block : fwm ? t.fwm : t.warmwasser,
        bauart: teil.bauart,
        temperatur: wert(`${teil.id}_warmwasser`),
        zustand,
        zirkulation,
        zirkuliert,
        ladepumpe,
        laedt: !fwm && (ladepumpe ? an(ladepumpe) : WARMWASSER_LAEDT.includes(zustand?.roh)),
        fliesst,
        zapft: Boolean(pufferpumpe) && fliesst && !zirkuliert,
      };
    },
    heizkreis(teil) {
      const praefix = teil.nummer === 1 ? "heizkreis" : `heizkreis${teil.nummer}`;
      const anforderung = wert(`${praefix}_anforderung`);
      const modus = stand(`${praefix}_betriebsart`);
      const thermostat = stand(`${praefix}_thermostat`);
      const raumSoll = thermostat?.attributes?.temperature;
      return {
        name: `${t.heizkreis} ${teil.nummer}`,
        boden: fussboden.includes(teil.id),
        vorlauf: wert(`${praefix}_vorlauf`),
        anforderung,
        heizt: an(anforderung),
        raum: [wert(`${praefix}_raum`)].find((w) => w && w.roh !== "") || null,
        raumSoll: typeof raumSoll === "number" ? `${raumSoll.toLocaleString(hass.locale?.language || "de", { minimumFractionDigits: 1, maximumFractionDigits: 1 })} °C` : null,
        programm: wert(`${praefix}_zeitprogramm`),
        modus: modus && modus.state !== "unavailable" && modus.state !== "unknown" ? { id: modus.entity_id, wert: modus.state } : null,
        thermostat: thermostat?.entity_id || null,
        soll: typeof raumSoll === "number"
          ? { wert: raumSoll, min: thermostat.attributes.min_temp ?? 10, max: thermostat.attributes.max_temp ?? 30, schritt: thermostat.attributes.target_temp_step || 0.5 }
          : null,
      };
    },
    lager() {
      const vorrat = wert("lager_vorrat"), maximum = wert("lager_maximum"), warnung = wert("lager_warngrenze");
      const fuellstand = wert("lager_fuellstand"), zustand = wert("lager_zustand");
      const anteil = fuellstand && fuellstand.n !== null ? fuellstand.n / 100 : vorrat && maximum && vorrat.n !== null && maximum.n ? vorrat.n / maximum.n : null;
      return {
        name: t.lager,
        vorrat,
        maximum,
        warnung,
        anteil: anteil === null ? null : Math.max(0, Math.min(anteil, 1)),
        warnAnteil: warnung && maximum && warnung.n !== null && maximum.n ? Math.min(warnung.n / maximum.n, 1) : null,
        zustand,
        foerdert: zustand?.roh === LAGER_FOERDERT,
        reichtBis: wert("lager_reicht_bis"),
      };
    },
    solar() {
      const leistung = wert("solar_leistung");
      return { name: t.solar, leistung, aktiv: ueber(leistung), kollektor: wert("solar_kollektor"), heute: wert("solar_ertrag_heute") };
    },
    pvm() {
      const leistung = wert("pvm_heizstab");
      return { name: t.pvm, leistung, aktiv: ueber(leistung), oben: wert("pvm_temperatur_oben"), heute: wert("pvm_ertrag_heute") };
    },
    brenner() {
      const anforderung = wert("brenner_anforderung");
      return { name: t.brenner, anforderung, aktiv: an(anforderung), temperatur: wert("brenner_temperatur"), leistung: wert("brenner_leistung_soll") };
    },
    fernleitung() {
      const pumpe = wert("fernleitung_pumpe");
      return { name: t.fernleitung, pumpe, pumpt: an(pumpe) };
    },
  };

  const teile = struktur.teile.filter((teil) => lesen[teil.art]).map((teil) => ({ ...teil, ...lesen[teil.art](teil) }));
  const stoerung = stand("stoerung");
  const animationen = stand("animationen");
  return {
    teile,
    schreiben: struktur.schreiben,
    aussen: wert("aussentemperatur"),
    stoerung: stoerung?.state === "on",
    fehler: struktur.entitaeten.aktive_fehler || struktur.entitaeten.stoerung || null,
    ruhe: animationen?.state === "off",
  };
}

class EtaUebersichtKarte extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this.shadowRoot.innerHTML = `<style>${STIL}</style><div class="eta"></div>`;
    this._wurzel = this.shadowRoot.querySelector(".eta");
    this._konfig = {};
    this._struktur = null;
    this._fehler = false;
    this._gefragt = 0;
    this._fragt = false;
    this._staende = {};
    this._gezeichnet = "";
    this._frage = null;
    this._offen = null;
    this._wunsch = {};
    this._sollTakt = {};
    this._kanten = [];
    this._gemessen = "";
    this._beobachter = new ResizeObserver(() => this._leitungen(true));
    this.shadowRoot.addEventListener("click", (ereignis) => this._klick(ereignis));
    this.shadowRoot.addEventListener("keydown", (ereignis) => {
      if ((ereignis.key === "Enter" || ereignis.key === " ") && ereignis.target.matches?.("[data-info]:not(button), [data-aktion]:not(button)")) {
        ereignis.preventDefault();
        this._klick(ereignis);
      }
    });
  }

  static getStubConfig() {
    return { ansicht: "kacheln" };
  }

  /**
   * Die Einstellungen der Karte. Die Anlage steht nur zur Wahl, wenn es
   * mehrere gibt. Je Heizkreis lässt sich statt des Heizkörpers eine
   * Fußbodenheizung zeigen - was verbaut ist, weiß die Anlage nicht.
   */
  static async getConfigForm() {
    const t = TEXTE[sprache(document.documentElement.lang)];
    let anlagen = [];
    try {
      const antwort = await document.querySelector("home-assistant")?.hass?.callWS({ type: "eta_heating_ws/uebersicht" });
      anlagen = antwort?.anlagen || [];
    } catch (fehler) {
      anlagen = [];
    }
    const auswahl = (name, optionen) => ({ name, selector: { select: { mode: "dropdown", options: optionen } } });
    const heizkreise = [...new Map(anlagen.flatMap((a) => a.teile).filter((teil) => teil.art === "heizkreis").map((teil) => [teil.id, teil])).values()];
    return {
      schema: [
        { name: "titel", selector: { text: {} } },
        auswahl("ansicht", ANSICHTEN.map((wert) => ({ value: wert, label: t[`ansicht_${wert}`] }))),
        ...(anlagen.length > 1 ? [auswahl("anlage", anlagen.map((a) => ({ value: a.eintrag, label: a.titel })))] : []),
        ...(heizkreise.length
          ? [{ name: "fussboden", selector: { select: { multiple: true, mode: "list", options: heizkreise.map((teil) => ({ value: teil.id, label: `${t.heizkreis} ${teil.nummer}` })) } } }]
          : []),
      ],
      computeLabel: (feld) => t[`feld_${feld.name}`],
    };
  }

  setConfig(konfig) {
    this._konfig = konfig || {};
    this._staende = {};
    this._zeichnen();
  }

  set hass(hass) {
    this._hass = hass;
    this.toggleAttribute("dunkel", Boolean(hass?.themes?.darkMode));
    this._fragen();
    this._zeichnen();
  }

  /**
   * Füllt die Karte eine ganze Ansicht ("Panel"), bekommt sie einen Rand -
   * Home Assistant lässt dort keinen.
   */
  set layout(layout) {
    this.toggleAttribute("vollbild", layout === "panel");
  }

  set isPanel(vollbild) {
    this.toggleAttribute("vollbild", Boolean(vollbild));
  }

  connectedCallback() {
    this._beobachter.observe(this._wurzel);
  }

  disconnectedCallback() {
    this._beobachter.disconnect();
  }

  getCardSize() {
    return this._ansicht === "kompakt" ? 8 : 10;
  }

  getGridOptions() {
    return this._ansicht === "kompakt" ? { columns: 6, min_columns: 6 } : { columns: "full", min_columns: 6 };
  }

  get _ansicht() {
    return ANSICHTEN.includes(this._konfig.ansicht) ? this._konfig.ansicht : "kacheln";
  }

  get _t() {
    return TEXTE[sprache(this._hass?.locale?.language || this._hass?.language)];
  }

  /**
   * Fragt die Integration nach der Anlage - beim ersten Mal, danach alle
   * paar Minuten, falls sich die Einrichtung geändert hat. Ohne Antwort
   * bald noch einmal.
   */
  async _fragen() {
    const abstand = this._struktur ? NEU_FRAGEN_NACH : NOCHMAL_NACH;
    if (this._fragt || !this._hass?.callWS || (this._gefragt && Date.now() - this._gefragt < abstand)) return;
    this._fragt = true;
    this._gefragt = Date.now();
    try {
      const antwort = await this._hass.callWS({ type: "eta_heating_ws/uebersicht" });
      const anlagen = antwort?.anlagen || [];
      this._struktur = anlagen.find((a) => a.eintrag === this._konfig.anlage) || anlagen[0] || { leer: true };
      this._fehler = false;
    } catch (fehler) {
      this._fehler = true;
    }
    this._fragt = false;
    this._staende = {};
    this._zeichnen();
  }

  /** Zeichnet nur, wenn sich eine der Entitäten der Anlage geändert hat. */
  _zeichnen() {
    if (!this._hass) return;
    const struktur = this._struktur;
    if (struktur && !struktur.leer) {
      const ids = Object.values(struktur.entitaeten);
      const neu = ids.some((id) => this._hass.states[id] !== this._staende[id]) || !Object.keys(this._staende).length;
      if (!neu && !this._neuZeichnen) return;
      this._staende = Object.fromEntries(ids.map((id) => [id, this._hass.states[id]]));
      this._staende[""] = true;
    }
    this._neuZeichnen = false;
    const html = this._html();
    if (html === this._gezeichnet) return;
    this._gezeichnet = html;
    const vorlage = document.createElement("template");
    vorlage.innerHTML = html;
    angleichen(this._wurzel, vorlage.content.firstElementChild);
    this._leitungen(false);
  }

  _html() {
    const t = this._t;
    if (!this._struktur) return `<div class="eta"><div class="eta-meldung">${e(this._fehler ? t.keine_antwort : t.laedt)}</div></div>`;
    if (this._struktur.leer) return `<div class="eta"><div class="eta-meldung">${e(t.keine_anlage)}</div></div>`;
    const fussboden = Array.isArray(this._konfig.fussboden) ? this._konfig.fussboden : [];
    const anlage = anlageLesen(this._hass, this._struktur, t, fussboden);
    const inhalt = this._ansicht === "anlagenbild" ? this._bild(anlage) : this._ansicht === "kompakt" ? this._kompakt(anlage) : this._kacheln(anlage);
    return `<div class="eta" ${anlage.ruhe ? "data-ruhe" : ""}>${DEFS}${inhalt}</div>`;
  }

  /* Bausteine */

  _info(w) {
    return w?.id ? `data-info="${e(w.id)}" tabindex="0" role="button"` : "";
  }

  _chip(text, an, art = "") {
    return `<span class="eta-chip klein" ${art ? `data-art="${art}"` : ""}><i class="eta-punkt" ${an ? "data-an" : ""}></i>${e(text)}</span>`;
  }

  _zeilen(paare) {
    const zeilen = paare.filter(([, w]) => w);
    if (!zeilen.length) return "";
    return `<dl class="eta-zeilen">${zeilen.map(([name, w]) => `<div ${this._info(w)}><dt>${e(name)}</dt><dd>${w.html || e(w.text)}</dd></div>`).join("")}</dl>`;
  }

  _haupt(label, w, neben = "") {
    return `<div class="eta-haupt"><span class="eta-label">${e(label)}</span><span class="eta-zahl">${e(w ? w.zahl : "–")}<small>${e(w ? w.einheit : "")}</small></span>${neben ? `<span class="eta-neben">${e(neben)}</span>` : ""}</div>`;
  }

  _figur(inhalt, breite, stil = "") {
    return `<div class="eta-figur" style="--b:${breite}px;${stil}">${inhalt}</div>`;
  }

  _kopf(anlage) {
    const t = this._t;
    const kessel = anlage.teile.find((teil) => teil.art === "kessel");
    const titel = this._konfig.titel ?? t.titel;
    const chips = [];
    if (anlage.aussen) chips.push(`<button type="button" class="eta-chip" data-info="${e(anlage.aussen.id)}">${ICON.thermo}${e(t.aussen)} ${e(anlage.aussen.text)}</button>`);
    if (kessel?.zustand) chips.push(`<button type="button" class="eta-chip" data-info="${e(kessel.zustand.id)}"><i class="eta-punkt" ${kessel.bild !== "aus" && kessel.bild !== "stoerung" ? "data-an" : ""}></i>${e(t.kessel)}: ${e(kessel.zustand.text)}</button>`);
    if (anlage.fehler) chips.push(`<button type="button" class="eta-chip" ${anlage.stoerung ? 'data-art="stoer"' : ""} data-info="${e(anlage.fehler)}">${anlage.stoerung ? ICON.warn : ICON.haken}${e(anlage.stoerung ? t.stoerung : t.keine_stoerung)}</button>`);
    return `<div class="eta-kopf">${titel ? `<h2 class="eta-titel">${e(titel)}</h2>` : "<span></span>"}<div class="eta-chips">${chips.join("")}</div></div>`;
  }

  /** Die Tasten am Kessel - nur mit Schreibzugriff und nur, was die Anlage hat. */
  _bedienung(kessel, anlage) {
    const t = this._t;
    if (!anlage.schreiben || !kessel) return "";
    const knoepfe = [];
    if (kessel.schalter) knoepfe.push(`<button type="button" class="eta-knopf" data-aktion="kessel" aria-pressed="${kessel.schalter.an}">${ICON.aus}<span>${e(kessel.schalter.an ? t.kessel_ein : t.kessel_aus)}</span></button>`);
    if (kessel.entaschen) knoepfe.push(`<button type="button" class="eta-knopf" data-aktion="entaschen" aria-pressed="${kessel.bild === "entaschen"}">${ICON.besen}<span>${e(t.entaschen)}</span></button>`);
    if (kessel.entaschen && kessel.leeren) knoepfe.push(`<button type="button" class="eta-knopf" data-info="${e(kessel.leeren)}" aria-pressed="${Boolean(kessel.plan)}">${ICON.box}<span>${e(t.aschebox_leeren)}</span></button>`);
    if (!knoepfe.length) return "";
    const frage = this._frage
      ? `<div class="eta-frage" role="alertdialog"><span>${e(t[`frage_${this._frage}`])}</span><div><button type="button" data-aktion="ja">${e(t.ja)}</button><button type="button" data-aktion="nein">${e(t.nein)}</button></div></div>`
      : kessel.plan && kessel.abbrechen
        ? `<div class="eta-frage"><span>${e(kessel.plan.text)}</span><div><button type="button" data-aktion="plan">${e(t.plan_abbrechen)}</button></div></div>`
        : "";
    return `<div class="eta-bedienung">${frage}<div class="eta-knoepfe">${knoepfe.join("")}</div></div>`;
  }

  _modi(heizkreis, anlage) {
    const t = this._t;
    if (!anlage.schreiben || !heizkreis.modus) return "";
    return `<div class="eta-modi" role="group" aria-label="${e(t.betriebsart)} ${e(heizkreis.name)}">${MODI.map(([modus, symbol]) => `<button type="button" class="eta-modus" data-aktion="modus" data-ziel="${e(heizkreis.modus.id)}" data-modus="${modus}" aria-pressed="${heizkreis.modus.wert === modus}">${ICON[symbol]}<span>${e(t[`modus_${modus}`])}</span></button>`).join("")}</div>`;
  }

  /**
   * Raum Soll mit zwei Tasten - nur mit Schreibzugriff und Thermostat.
   * Gezeigt wird sofort der gewünschte Wert, siehe _sollStellen.
   */
  _raumSoll(h, anlage) {
    const t = this._t;
    if (!anlage.schreiben || !h.soll || !h.thermostat) return "";
    const wunsch = this._wunsch[h.thermostat];
    if (wunsch && (wunsch.bis < Date.now() || Math.abs(wunsch.wert - h.soll.wert) < 0.01)) delete this._wunsch[h.thermostat];
    const wert = this._wunsch[h.thermostat]?.wert ?? h.soll.wert;
    const text = `${wert.toLocaleString(this._hass.locale?.language || "de", { minimumFractionDigits: 1, maximumFractionDigits: 1 })} °C`;
    const taste = (ziel, symbol, name) => `<button type="button" class="eta-rund" data-aktion="soll" data-ziel="${e(h.thermostat)}" data-wert="${ziel}" aria-label="${e(name)}" ${ziel < h.soll.min || ziel > h.soll.max ? "disabled" : ""}>${ICON[symbol]}</button>`;
    return `<div class="eta-soll" role="group" aria-label="${e(t.raum_soll)} ${e(h.name)}"><span>${e(t.raum_soll)}</span>${taste(wert - h.soll.schritt, "minus", t.kaelter)}<b>${e(text)}</b>${taste(wert + h.soll.schritt, "plus", t.waermer)}</div>`;
  }

  _heizkreisStatus(h) {
    const t = this._t;
    if (h.modus?.wert === "aus") return t.aus;
    if (h.heizt) return t.heizt;
    return h.programm ? h.programm.text : t.aus;
  }

  _umlauf(w, an) {
    return w ? { ...w, html: `${an ? ICON.umlaufAn : ICON.umlauf}${e(w.text)}` } : null;
  }

  _pufferBild(p, breite, hoehe) {
    const grade = p.fuehler.map((f) => f.n);
    const zeilen = p.fuehler.length;
    const mindest = Math.max(hoehe, zeilen * 26) + (p.kombi ? 44 : 0);
    const kombi = p.kombi ? p.kombi.temperatur.text : null;
    return this._figur(tank(grade.length ? grade : [null], p.fuehler.map((f) => f.text), { laedt: p.laedt, kombi }), breite, `--tankhoehe:${mindest}px`);
  }

  _warmwasserBild(w, breite, hoehe) {
    if (w.bauart === "fwm") return this._figur(fwmBild(), breite);
    const grad = w.temperatur?.n ?? null;
    return this._figur(tank(grad === null ? [null] : [grad, grad - 24], [], { hahn: true, laedt: w.laedt }), breite, `--tankhoehe:${hoehe}px`);
  }

  /** Was beim Warmwasser gerade geschieht, und ob es dafür arbeitet - für Schild und Punkt. */
  _warmwasserStatus(w) {
    const t = this._t;
    const arbeitet = w.laedt || w.fliesst;
    if (w.zapft) return [t.zapfung, true];
    if (w.zustand && w.zustand.roh) return [w.zustand.text, arbeitet];
    if (w.bauart === "fwm" && w.zirkuliert) return [t.zirkulation_laeuft, true];
    return [w.laedt ? t.laden : t.bereit, arbeitet];
  }

  _warmwasserMerkmale(w) {
    return `${w.fliesst ? "data-fliesst" : ""} ${w.zapft ? "data-zapft" : ""}`;
  }

  /* Ansicht: Kacheln */

  _kacheln(anlage) {
    const t = this._t;
    const kachel = (teil, merkmale, kopf, inhalt) => `<article class="eta-kachel" data-art="${teil.art}" ${merkmale}><header class="eta-kachelkopf"><h3>${e(teil.name)}</h3>${kopf}</header>${inhalt}</article>`;
    const zeichnen = {
      kessel: (k) => kachel(k, `data-zustand="${k.bild}"`, k.zustand ? this._chip(k.zustand.text, k.bild !== "aus" && k.bild !== "stoerung", k.bild === "stoerung" ? "stoer" : "") : "", `
        <div class="eta-buehne" ${this._info(k.temperatur)}>${this._figur(kesselBild(), 116)}${this._haupt(t.kesseltemperatur, k.temperatur, k.soll ? `${t.soll} ${k.soll.text}` : "")}</div>
        ${this._zeilen(k.zeilen)}
        ${k.asche ? `<div class="eta-messung" ${this._info(k.ascheStatus || k.asche)}><div class="eta-messung-kopf"><span>${e(t.aschebox)}</span><b>${e((k.ascheStatus || k.asche).text)}</b></div>${k.ascheAnteil === null ? "" : `<div class="eta-balken"><i style="width:${(k.ascheAnteil * 100).toFixed(1)}%"></i></div>`}</div>` : ""}
        ${this._bedienung(k, anlage)}`),
      puffer: (p) => kachel(p, "", p.zustand ? this._chip(p.zustand.text, p.laedt) : "", `
        <div class="eta-buehne" ${this._info(p.ladung || p.fuehler[0])}>${this._pufferBild(p, 112, 208)}${p.ladung ? this._haupt(t.ladezustand, p.ladung, p.energie ? p.energie.text : "") : p.fuehler.length ? this._haupt(t.oben, p.fuehler[0]) : ""}</div>
        ${this._zeilen([...(p.kombi ? [[t.warmwasser, p.kombi.temperatur], [t.warmwasser_zustand, p.kombi.zustand]] : []), ...(p.ladung && p.fuehler.length ? [[t.oben, p.fuehler[0]], [t.unten, p.fuehler[p.fuehler.length - 1]]] : []), [t.ladepumpe, p.ladepumpe]])}`),
      warmwasser: (w) => kachel(w, this._warmwasserMerkmale(w), this._chip(...this._warmwasserStatus(w)), `
        <div class="eta-buehne" ${this._info(w.temperatur)}>${this._warmwasserBild(w, w.bauart === "fwm" ? 124 : 96, 108)}${this._haupt(w.bauart === "fwm" ? t.temperatur_modul : t.speichertemperatur, w.temperatur)}</div>
        ${this._zeilen([[t.ladepumpe, w.ladepumpe], [t.zirkulation, this._umlauf(w.zirkulation, w.zirkuliert)]])}`),
      heizkreis: (h) => kachel(h, h.heizt ? "data-aktiv" : "", this._chip(this._heizkreisStatus(h), h.heizt), `
        <div class="eta-buehne" ${h.thermostat ? `data-info="${e(h.thermostat)}" tabindex="0" role="button"` : this._info(h.vorlauf)}>${this._figur(h.boden ? fussbodenBild() : heizkreisBild(), 132)}${this._haupt(t.vorlauf, h.vorlauf)}</div>
        ${this._zeilen([[t.raum, h.raum && h.raumSoll && !(anlage.schreiben && h.soll) ? { ...h.raum, text: `${h.raum.text} · ${t.soll} ${h.raumSoll}` } : h.raum], [t.zeitprogramm, h.programm], [t.anforderung, h.anforderung]])}
        ${this._raumSoll(h, anlage)}
        ${this._modi(h, anlage)}`),
      lager: (l) => kachel(l, l.foerdert ? "data-foerdert" : "", l.zustand ? this._chip(l.zustand.text, l.foerdert) : "", `
        <div class="eta-buehne" ${this._info(l.vorrat)}>${this._figur(lagerBild(l.anteil ?? 0), 118)}${this._haupt(t.vorrat, l.vorrat, l.anteil !== null && l.maximum ? `${Math.round(l.anteil * 100)} % ${t.von} ${l.maximum.text}` : "")}</div>
        ${l.anteil === null ? "" : `<div class="eta-messung"><div class="eta-balken" data-art="pellet"><i style="width:${(l.anteil * 100).toFixed(1)}%"></i>${l.warnAnteil === null ? "" : `<u style="left:${(l.warnAnteil * 100).toFixed(1)}%"></u>`}</div></div>`}
        ${this._zeilen([[t.reicht_bis, l.reichtBis], [t.warnung_ab, l.warnung]])}`),
      solar: (s) => kachel(s, s.aktiv ? "data-aktiv" : "", this._chip(s.aktiv ? t.liefert : t.ruht, s.aktiv), `
        <div class="eta-buehne" ${this._info(s.leistung)}>${this._figur(solarBild(), 132)}${this._haupt(t.leistung, s.leistung)}</div>
        ${this._zeilen([[t.kollektor, s.kollektor], [t.ertrag_heute, s.heute]])}`),
      pvm: (p) => kachel(p, p.aktiv ? "data-aktiv" : "", this._chip(p.aktiv ? t.heizt : t.ruht, p.aktiv), `
        <div class="eta-buehne" ${this._info(p.leistung)}>${this._figur(pvmBild(), 132)}${this._haupt(t.heizstab, p.leistung)}</div>
        ${this._zeilen([[t.speicher_oben, p.oben], [t.ertrag_heute, p.heute]])}`),
      brenner: (b) => kachel(b, b.aktiv ? "data-aktiv" : "", this._chip(b.aktiv ? t.heizt : t.ruht, b.aktiv), `
        <div class="eta-buehne" ${this._info(b.temperatur || b.anforderung)}>${this._figur(brennerBild(), 96)}${this._haupt(t.temperatur, b.temperatur)}</div>
        ${this._zeilen([[t.anforderung, b.anforderung], [t.leistung_soll, b.leistung]])}`),
      fernleitung: (f) => kachel(f, f.pumpt ? "data-pumpt" : "", this._chip(f.pumpt ? t.laeuft : t.ruht, f.pumpt), `
        <div class="eta-buehne" ${this._info(f.pumpe)}>${this._figur(fernBild(), 132)}${this._haupt(t.fernpumpe, f.pumpe)}</div>`),
    };
    return `${this._kopf(anlage)}<div class="eta-raster">${anlage.teile.map((teil) => zeichnen[teil.art](teil)).join("")}</div>`;
  }

  /* Ansicht: Anlagenbild */

  /**
   * Stellt die Teile in Spalten: links die Erzeuger, dann je Stufe, was
   * an der vorigen hängt. Die Leitungen dazu merkt sich die Karte in
   * _kanten und misst sie nach dem Zeichnen aus, siehe _leitungen. Jede
   * Verbindung ist genau eine Linie; Vor- und Rücklauf zeigt die Karte
   * nicht getrennt.
   */
  _bild(anlage) {
    const t = this._t;
    const nachId = Object.fromEntries(anlage.teile.map((teil) => [teil.id, teil]));
    const quelle = (teil) => (teil.von && nachId[teil.von] ? teil.von : null);
    const erzeugt = (teil) => ["solar", "pvm", "brenner"].includes(teil.art);
    const tiefe = (teil, schutz = 0) => {
      if (teil.art === "kessel" || schutz > 20) return 0;
      if (teil.art === "lager") return -1;
      const von = quelle(teil);
      if (erzeugt(teil)) return von ? tiefe(nachId[von], schutz + 1) - 1 : 0;
      return von ? tiefe(nachId[von], schutz + 1) + 1 : 1;
    };
    const anschluss = (teil) => {
      const von = quelle(teil);
      const mehrere = anlage.teile.filter((x) => x.art === "puffer" || x.art === "fernleitung").length > 1;
      return mehrere && von && nachId[von].art !== "kessel" ? `<span class="eta-anschluss"> · ${e(t.an_teil)} ${e(nachId[von].name)}</span>` : "";
    };
    const schild = (teil, w, neben, text = null) => `<div class="eta-schild"><span class="eta-name">${e(teil.name)}</span><span class="eta-zahl">${e(text ?? (w ? w.zahl : "–"))}<small>${e(text === null && w ? w.einheit : "")}</small></span><span class="eta-neben">${e(neben)}${erzeugt(teil) ? "" : anschluss(teil)}</span></div>`;
    const station = (teil, klasse, merkmale, info, bild, text) => `<div class="eta-station ${klasse}" data-id="${teil.id}" data-art="${teil.art}" ${merkmale} ${info}>${bild}${text}</div>`;
    const rang = { solar: 1, kessel: 0, brenner: 2, pvm: 3, lager: 0, fernleitung: 0, puffer: 1, heizkreis: 2, warmwasser: 3 };

    const zeichnen = {
      lager: (l) => station(l, "", l.foerdert ? 'data-foerdert data-fluss="pellets"' : "", this._info(l.vorrat), this._figur(lagerBild(l.anteil ?? 0), 128), schild(l, l.vorrat, l.reichtBis ? `${t.reicht_bis} ${l.reichtBis.text}` : "")),
      kessel: (k) => station(k, "", `data-zustand="${k.bild}" ${k.bild === "flamme" ? "data-fluss" : ""}`, this._info(k.temperatur), this._figur(kesselBild(), 132), schild(k, k.temperatur, [k.zustand?.text, k.soll ? `${t.soll} ${k.soll.text}` : ""].filter(Boolean).join(" · "))),
      solar: (s) => station(s, "quer links oben", s.aktiv ? "data-aktiv data-fluss" : "", this._info(s.leistung), this._figur(solarBild(), 92), schild(s, s.leistung, s.kollektor ? `${t.kollektor} ${s.kollektor.text}` : "")),
      pvm: (p) => station(p, "quer links", p.aktiv ? 'data-aktiv data-fluss="strom"' : "", this._info(p.leistung), this._figur(pvmBild(), 92), schild(p, p.leistung, p.heute ? `${t.heute} ${p.heute.text}` : "")),
      brenner: (b) => station(b, "quer links", b.aktiv ? "data-aktiv data-fluss" : "", this._info(b.temperatur || b.anforderung), this._figur(brennerBild(), 72), schild(b, b.temperatur, b.anforderung ? `${t.anforderung} ${b.anforderung.text}` : "")),
      puffer: (p) => station(p, "", `${p.laedt ? "data-fluss" : ""} ${p.kombi ? "data-kombi" : ""}`, this._info(p.ladung || p.fuehler[0]), this._pufferBild(p, 118, 236), schild(p, p.ladung || p.fuehler[0], [p.energie?.text, p.zustand?.text, p.kombi ? `${t.warmwasser} ${p.kombi.temperatur.text}` : ""].filter(Boolean).join(" · "))),
      fernleitung: (f) => station(f, "", f.pumpt ? "data-pumpt data-fluss" : "", this._info(f.pumpe), this._figur(fernBild(), 156), schild(f, null, f.pumpe ? `${t.fernpumpe} ${f.pumpe.text}` : "", f.pumpt ? t.laeuft : t.ruht)),
      heizkreis: (h) => station(h, "quer", h.heizt ? "data-aktiv data-fluss" : "", h.thermostat ? `data-info="${e(h.thermostat)}" tabindex="0" role="button"` : this._info(h.vorlauf), this._figur(h.boden ? fussbodenBild() : heizkreisBild(), 96), schild(h, h.vorlauf, [h.modus ? t[`modus_${h.modus.wert}`] : "", this._heizkreisStatus(h)].filter(Boolean).join(" · "))),
      warmwasser: (w) => station(w, "quer", `${this._warmwasserMerkmale(w)} ${w.laedt || w.fliesst ? "data-fluss" : ""}`, this._info(w.temperatur), this._warmwasserBild(w, 96, 78), schild(w, w.temperatur, [this._warmwasserStatus(w)[0], w.zirkulation ? `${t.zirkulation} ${w.zirkulation.text}` : ""].filter(Boolean).join(" · "))),
    };

    const kanten = [];
    const kante = (von, nach, art, aktiv, aus, ein) => kanten.push({ von, nach, art, aktiv, aus, ein });
    const eingang = (teil) => EIN[teil.art === "warmwasser" ? teil.bauart : teil.art];
    const aktiv = (teil) => Boolean(teil.laedt || teil.heizt || teil.pumpt || teil.fliesst);
    for (const teil of anlage.teile) {
      const von = quelle(teil);
      if (teil.art === "lager" && nachId.kessel) kante(teil.id, "kessel", "pellets", teil.foerdert, AUS.lager, EIN.kessel);
      if (!von || teil.art === "lager" || teil.art === "kessel") continue;
      if (erzeugt(teil)) {
        kante(teil.id, von, teil.art === "pvm" ? "strom" : "heiss", teil.aktiv, AUS[teil.art], { solar: [0, 0.14], brenner: [0, 0.74], pvm: [0, 0.88] }[teil.art]);
      } else if (nachId[von].art === "kessel" && teil.art === "puffer") {
        kante(von, teil.id, "heiss", nachId[von].bild === "flamme", AUS.kessel, [0, 0.27]);
      } else {
        kante(von, teil.id, "heiss", aktiv(teil), AUS[nachId[von].art], eingang(teil));
      }
    }
    this._kanten = kanten;

    const sortiert = anlage.teile.map((teil, platz) => ({ teil, platz, spalte: tiefe(teil) })).sort((a, b) => a.spalte - b.spalte || rang[a.teil.art] - rang[b.teil.art] || a.platz - b.platz);
    const spalten = [...new Set(sortiert.map((x) => x.spalte))].map((nr) => {
      const drin = sortiert.filter((x) => x.spalte === nr);
      const quer = drin.every((x) => x.teil.art === "heizkreis" || x.teil.art === "warmwasser");
      return `<div class="eta-spalte ${quer ? "eta-verbraucher" : ""}">${drin.map((x) => zeichnen[x.teil.art](x.teil)).join("")}</div>`;
    });
    const kessel = nachId.kessel;
    const kennzahlen = kessel ? [...kessel.zeilen, [t.aschebox, kessel.ascheStatus || kessel.asche]].filter(([, w]) => w) : [];
    const fuss = this._bedienung(kessel, anlage);
    return `${this._kopf(anlage)}<section class="eta-kachel eta-szene">
      <div class="eta-bild"><svg class="eta-leitungen" aria-hidden="true" data-fest></svg>${spalten.join("")}</div>
      ${kennzahlen.length || fuss ? `<div class="eta-szenenfuss"><dl class="eta-kennzahlen">${kennzahlen.map(([name, w]) => `<div ${this._info(w)}><dt>${e(name)}</dt><dd>${e(w.text)}</dd></div>`).join("")}</dl>${fuss}</div>` : ""}
    </section>`;
  }

  /**
   * Misst aus, wo die Zeichnungen stehen, und legt die Leitungen
   * dazwischen. Passt das Bild nicht in die Breite, rückt es erst enger
   * zusammen und wird dann zur Liste mit einer Leitung am Rand.
   */
  _leitungen(neuMessen) {
    const bild = this._wurzel.querySelector(".eta-bild");
    if (!bild) return;
    const svg = bild.querySelector(".eta-leitungen");
    const breite = Math.round(bild.getBoundingClientRect().width);
    const merkmal = `${breite}|${JSON.stringify(this._kanten)}|${bild.querySelectorAll(".eta-station").length}`;
    if (!neuMessen && merkmal === this._gemessen && svg.childNodes.length) return;
    if (!breite) return;
    this._gemessen = merkmal;
    svg.innerHTML = "";
    bild.removeAttribute("data-schmal");
    bild.removeAttribute("data-dicht");
    if (bild.scrollWidth > bild.clientWidth + 1) {
      bild.setAttribute("data-dicht", "");
      if (bild.scrollWidth > bild.clientWidth + 1) {
        bild.removeAttribute("data-dicht");
        bild.setAttribute("data-schmal", "");
      }
    }
    const stationen = [...bild.querySelectorAll(".eta-station")];
    stationen.forEach((el, i) => {
      el.toggleAttribute("data-erste", i === 0);
      el.toggleAttribute("data-letzte", i === stationen.length - 1);
    });
    if (bild.hasAttribute("data-schmal")) return;
    const rahmen = bild.getBoundingClientRect();
    svg.setAttribute("viewBox", `0 0 ${rahmen.width} ${rahmen.height}`);
    const anker = (id, [fx, fy]) => {
      const figur = bild.querySelector(`[data-id="${id}"] .eta-figur`);
      if (!figur) return null;
      const r = figur.getBoundingClientRect();
      return [r.left - rahmen.left + r.width * fx, r.top - rahmen.top + r.height * fy];
    };
    const wege = [];
    for (const kante of this._kanten) {
      const p = anker(kante.von, kante.aus), q = anker(kante.nach, kante.ein);
      if (!p || !q) continue;
      const mitte = (p[0] + q[0]) / 2;
      wege.push({ ...kante, d: pfad([p, [mitte, p[1]], [mitte, q[1]], q]) });
    }
    wege.sort((a, b) => a.aktiv - b.aktiv);
    svg.innerHTML = wege.map((w) => `<path class="eta-rohr" data-art="${w.art}" ${w.aktiv ? "data-aktiv" : ""} d="${w.d}"/>`).join("") + wege.filter((w) => w.aktiv).map((w) => `<path class="eta-rohr-fluss" d="${w.d}"/>`).join("");
  }

  /* Ansicht: Kompakt */

  _kompakt(anlage) {
    const t = this._t;
    const kessel = anlage.teile.find((teil) => teil.art === "kessel");
    const erster = anlage.teile.find((teil) => teil.art === "puffer");
    const mehrere = anlage.teile.filter((teil) => teil.art === "puffer").length > 1;
    const zeile = (symbol, an, name, neben, w, extra = "") => `<div class="eta-reihe" ${this._info(w)}><span class="eta-symbol" ${an ? "data-an" : ""}>${ICON[symbol]}</span><div class="eta-reihe-text"><b>${e(name)}</b>${extra}${neben ? `<span>${e(neben)}</span>` : ""}</div><span class="eta-reihe-wert">${e(w ? w.text : "–")}</span></div>`;
    const balken = (anteil, art = "") => (anteil === null ? "" : `<div class="eta-balken" ${art ? `data-art="${art}"` : ""}><i style="width:${(anteil * 100).toFixed(1)}%"></i></div>`);
    const reihen = {
      kessel: () => "",
      puffer: (p) =>
        (p === erster ? "" : zeile("thermo", p.laedt, p.name, [p.energie?.text, p.zustand?.text].filter(Boolean).join(" · "), p.ladung || p.fuehler[0])) +
        (p.kombi ? zeile("tropfen", p.kombi.laedt, mehrere ? `${t.warmwasser} ${p.name}` : t.warmwasser_im_puffer, p.kombi.zustand?.text || "", p.kombi.temperatur) : ""),
      warmwasser: (w) => zeile("tropfen", w.laedt || w.fliesst, w.name, [this._warmwasserStatus(w)[0], w.zirkulation ? `${t.zirkulation} ${w.zirkulation.text}` : ""].filter(Boolean).join(" · "), w.temperatur),
      heizkreis: (h) => {
        const neben = [h.modus ? t[`modus_${h.modus.wert}`] : "", this._heizkreisStatus(h), h.raum ? `${t.raum} ${h.raum.text}` : ""].filter(Boolean).join(" · ");
        const stellen = `${this._raumSoll(h, anlage)}${this._modi(h, anlage)}`;
        if (!stellen) return zeile("heizung", h.heizt, h.name, neben, h.vorlauf);
        const offen = this._offen === h.id;
        return `<div class="eta-reihe" data-aktion="aufklappen" data-teil="${h.id}" tabindex="0" role="button" aria-expanded="${offen}"><span class="eta-symbol" ${h.heizt ? "data-an" : ""}>${ICON.heizung}</span><div class="eta-reihe-text"><b>${e(h.name)}</b><span>${e(neben)}</span></div><span class="eta-reihe-wert">${e(h.vorlauf ? h.vorlauf.text : "–")}</span>${ICON.pfeil}</div>${offen ? `<div class="eta-klappe">${stellen}</div>` : ""}`;
      },
      lager: (l) => zeile("lager", l.foerdert, l.name, l.reichtBis ? `${t.reicht_bis} ${l.reichtBis.text}` : "", l.vorrat, balken(l.anteil, "pellet")),
      solar: (s) => zeile("sonne", s.aktiv, s.name, [s.kollektor ? `${t.kollektor} ${s.kollektor.text}` : "", s.heute ? `${t.heute} ${s.heute.text}` : ""].filter(Boolean).join(" · "), s.leistung),
      pvm: (p) => zeile("blitz", p.aktiv, p.name, [p.oben ? `${t.speicher_oben} ${p.oben.text}` : "", p.heute ? `${t.heute} ${p.heute.text}` : ""].filter(Boolean).join(" · "), p.leistung),
      brenner: (b) => zeile("flamme", b.aktiv, b.name, b.anforderung ? `${t.anforderung} ${b.anforderung.text}` : "", b.temperatur),
      fernleitung: (f) => zeile("rohr", f.pumpt, f.name, f.pumpt ? t.laeuft : t.ruht, f.pumpe),
    };
    const liste = anlage.teile.map((teil) => reihen[teil.art](teil)).join("") + (kessel?.asche ? zeile("box", false, t.aschebox, "", kessel.ascheStatus || kessel.asche, balken(kessel.ascheAnteil)) : "");
    const titel = this._konfig.titel ?? t.titel;
    const pufferTeil = erster
      ? `<div class="eta-gruppe" ${this._info(erster.ladung || erster.fuehler[0])}>${this._figur(tank(erster.fuehler.length ? erster.fuehler.map((f) => f.n) : [null], [], { laedt: erster.laedt }), 36, "--tankhoehe:78px")}<div class="eta-haupt"><span class="eta-label">${e(erster.name)}</span><span class="eta-zahl" style="font-size:24px">${e((erster.ladung || erster.fuehler[0])?.zahl ?? "–")}<small>${e((erster.ladung || erster.fuehler[0])?.einheit ?? "")}</small></span>${erster.energie ? `<span class="eta-neben">${e(erster.energie.text)}</span>` : ""}</div></div>`
      : "";
    return `<section class="eta-kachel eta-kompakt" data-zustand="${kessel ? kessel.bild : "aus"}">
      <header class="eta-kompakt-kopf"><h3>${e(titel)}</h3>${kessel?.zustand ? this._chip(`${t.kessel}: ${kessel.zustand.text}`, kessel.bild !== "aus" && kessel.bild !== "stoerung", kessel.bild === "stoerung" ? "stoer" : "") : ""}</header>
      ${kessel ? `<div class="eta-buehne"><div class="eta-gruppe" ${this._info(kessel.temperatur)}>${this._figur(kesselBild(), 60)}${this._haupt(t.kessel, kessel.temperatur, anlage.aussen ? `${t.aussen} ${anlage.aussen.text}` : "")}</div>${pufferTeil}</div>` : ""}
      <div class="eta-liste">${liste}</div>
      ${this._bedienung(kessel, anlage)}
    </section>`;
  }

  /* Bedienen */

  _klick(ereignis) {
    const knopf = ereignis.target.closest("[data-aktion]");
    if (knopf) {
      this._aktion(knopf);
      return;
    }
    const info = ereignis.target.closest("[data-info]");
    if (info) {
      this.dispatchEvent(new CustomEvent("hass-more-info", { detail: { entityId: info.dataset.info }, bubbles: true, composed: true }));
    }
  }

  /**
   * Stellt Raum Soll. Die Karte zeigt den neuen Wert sofort und schickt
   * ihn erst nach einer kurzen Pause - wer mehrmals tippt, schreibt nur
   * einmal auf die Anlage. Kommt der Wert nicht zurück, steht nach ein
   * paar Sekunden wieder der alte da.
   */
  _sollStellen(thermostat, wert) {
    this._wunsch[thermostat] = { wert, bis: Date.now() + SOLL_WARTEN };
    clearTimeout(this._sollTakt[thermostat]);
    this._sollTakt[thermostat] = setTimeout(() => {
      this._hass.callService("climate", "set_temperature", { entity_id: thermostat, temperature: wert });
      setTimeout(() => {
        this._neuZeichnen = true;
        this._zeichnen();
      }, SOLL_WARTEN);
    }, SOLL_SENDEN_NACH);
  }

  /**
   * Führt eine Taste aus. Entaschen und das Abbrechen des Aschebox-Plans
   * fragen vorher in der Karte nach, wie die bisherige Karte.
   */
  _aktion(knopf) {
    const aktion = knopf.dataset.aktion;
    const entitaeten = this._struktur?.entitaeten || {};
    const dienst = (bereich, name, daten) => this._hass.callService(bereich, name, daten);
    if (aktion === "kessel" && entitaeten.kessel_schalter) {
      dienst("switch", knopf.getAttribute("aria-pressed") === "true" ? "turn_off" : "turn_on", { entity_id: entitaeten.kessel_schalter });
    } else if (aktion === "modus") {
      dienst("select", "select_option", { entity_id: knopf.dataset.ziel, option: knopf.dataset.modus });
    } else if (aktion === "aufklappen") {
      this._offen = this._offen === knopf.dataset.teil ? null : knopf.dataset.teil;
    } else if (aktion === "soll") {
      this._sollStellen(knopf.dataset.ziel, Number(knopf.dataset.wert));
    } else if (aktion === "entaschen" || aktion === "plan") {
      this._frage = aktion;
    } else if (aktion === "ja" || aktion === "nein") {
      const ziel = this._frage === "entaschen" ? entitaeten.kessel_entaschen : entitaeten.aschebox_plan_abbrechen;
      if (aktion === "ja" && ziel) dienst("button", "press", { entity_id: ziel });
      this._frage = null;
    } else {
      return;
    }
    this._neuZeichnen = true;
    this._zeichnen();
  }
}

/**
 * Erst anmelden, wenn Home Assistant steht - siehe eta-zeitprogramm-karte.js.
 */
function anmelden() {
  if (!customElements.get(KARTE)) {
    customElements.define(KARTE, EtaUebersichtKarte);
  }
}

customElements.whenDefined("home-assistant").then(anmelden);

window.customCards = window.customCards || [];
if (!window.customCards.some((karte) => karte.type === KARTE)) {
  window.customCards.push({
    type: KARTE,
    name: "ETA Übersicht",
    description: TEXTE[sprache(document.documentElement.lang)].karte_beschreibung,
    preview: false,
    documentationURL: "https://github.com/dorsch95/ha-eta-webservices#-dashboard-karte",
  });
}
