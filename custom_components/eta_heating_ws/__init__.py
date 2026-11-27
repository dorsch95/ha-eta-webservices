"""ETA Web-Services - Integration für Home Assistant."""

from __future__ import annotations

import logging
import re
from datetime import timedelta
from pathlib import Path

from homeassistant.components.http import StaticPathConfig
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_call_later, async_track_time_interval
from homeassistant.helpers.start import async_at_started
from homeassistant.helpers.typing import ConfigType

from .api import ETAApiClient
from .const import (
    CONF_FEHLENDE_AUSBLENDEN,
    CONF_FUB_NAMES,
    CONF_ZUORDNUNGEN,
    CONF_ENABLE_ERRORS,
    CONF_ENABLE_SWITCHES,
    CONF_PELLET_KWH_PER_KG,
    CONF_LAGER_MAXIMUM,
    CONF_PELLET_PREIS,
    ASCHEBOX_ENTITAETEN,
    BILD_AUSWAHLEN,
    CONF_FREMDERZEUGER_ENTITAET,
    CONF_FREMDERZEUGER_FREIGEBEN_NACH,
    CONF_FREMDERZEUGER_FUEHLER,
    CONF_FREMDERZEUGER_SCHWELLE,
    CONF_FREMDERZEUGER_SPERREN_NACH,
    DEFAULT_FREMDERZEUGER_FREIGEBEN_NACH,
    DEFAULT_FREMDERZEUGER_SCHWELLE,
    DEFAULT_FREMDERZEUGER_SPERREN_NACH,
    FREMDERZEUGER_SCHALTER,
    FREMDERZEUGER_SCHWELLE_ZAHL,
    KESSEL_SPERRE,
    PELLET_PREIS_ZAHL,
    CONF_PROGNOSE,
    CONF_WEITERE_INTERVALL,
    CONF_WEITERE_JE_ABFRAGE,
    CONF_WEITERE_WERTE,
    CONF_SCAN_INTERVAL,
    CONF_SCHNELL_INTERVALL,
    CONF_WETTER,
    CONF_ZEITRAEUME,
    DEFAULT_ENABLE_ERRORS,
    DEFAULT_FEHLENDE_AUSBLENDEN,
    DEFAULT_ENABLE_SWITCHES,
    DEFAULT_PELLET_KWH_PER_KG,
    DEFAULT_PELLET_PREIS,
    DEFAULT_PROGNOSE,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SCHNELL_INTERVALL,
    DEFAULT_ZEITRAEUME,
    DOMAIN,
    PLATFORMS,
    PUFFER_SPEICHER,
    SELECTS,
    SENSORS,
    SWITCHES,
    ZAHLEN,
    URL_GRAFIKEN,
    URL_OBERFLAECHE,
    ALTE_URL_GRAFIKEN,
    THERMOSTATE,
    components_from_config,
    fremderzeuger_eingerichtet,
    fremderzeuger_sperrt,
    kessel_sperre_gewaehlt,
    puffer_volumen_schluessel,
    raumfuehler_schluessel,
    zeitplan_schluessel,
)
from . import weitere_werte
from . import zuordnung
from .aschebox import AscheboxPlan, verwaisten_plan_melden
from .fremderzeuger import Fremderzeuger
from .switch import kesselsperre_anlegen, verwaiste_sperre_aufloesen
from .aschebox import speicher as aschebox_speicher
from .raumfuehler import RaumfuehlerSender
from .aktionen import async_aktionen_registrieren
from .coordinator import (
    BLEIBT_OHNE_ADRESSE,
    ETAConfigEntry,
    ETADataUpdateCoordinator,
    puffer_fuehler_schluessel,
)
from .entitaets_ids import deutsche_namen
from .prognose_koordinator import ETAPrognoseKoordinator
from .uebernahme import UEBERNOMMEN_VON, async_uebernehmen
from .repairs import async_raumfuehler_pruefen, async_zeitplan_hinweise_entfernen
from .zeitplan import ZeitplanAbgleich
from .zeitplan import speicher as zeitplan_speicher
from .uebersicht import async_uebersicht_anmelden
from .zeitprogramm import OBERFLAECHE, async_karte_anmelden

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

GRAFIKEN = Path(__file__).parent / "grafiken"


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Stellt Kachelgrafiken und Dashboard-Karten bereit und meldet die Aktionen an.

    Bis Version 0.20 wurden die Grafiken bei jedem Start in den www-Ordner
    des Nutzers geschrieben. Jetzt liefert Home Assistant sie direkt aus dem
    Ordner der Integration aus; ohne Zwischenspeicher im Browser, damit
    geänderte Grafiken nach einem Update sofort ankommen (siehe
    karte.bildadresse). Die alten Adressen bleiben für Karten von vor dem
    Umbenennen. Ebenso die Karte "ETA Zeitprogramm", siehe zeitprogramm.py.
    """
    await hass.http.async_register_static_paths(
        [
            *(
                StaticPathConfig(pfad, str(GRAFIKEN), cache_headers=False)
                for pfad in (URL_GRAFIKEN, *ALTE_URL_GRAFIKEN)
            ),
            StaticPathConfig(URL_OBERFLAECHE, str(OBERFLAECHE), cache_headers=False),
        ]
    )
    async_aktionen_registrieren(hass)
    async_karte_anmelden(hass)
    async_uebersicht_anmelden(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ETAConfigEntry) -> bool:
    """Setzt die Integration über einen Config Entry auf."""
    if UEBERNOMMEN_VON in entry.data:
        await async_uebernehmen(hass, entry)
    config = {**entry.data, **entry.options}
    host = config[CONF_HOST]
    port = config[CONF_PORT]
    components = components_from_config(config)
    fub_name_overrides = config.get(CONF_FUB_NAMES, {})
    scan_interval = config.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    pellet_kwh_per_kg = config.get(
        CONF_PELLET_KWH_PER_KG, DEFAULT_PELLET_KWH_PER_KG
    )

    client = ETAApiClient(hass, async_get_clientsession(hass), host, port)
    coordinator = ETADataUpdateCoordinator(
        hass,
        entry,
        client,
        scan_interval,
        components,
        pellet_kwh_per_kg,
        enable_switches=config.get(CONF_ENABLE_SWITCHES, DEFAULT_ENABLE_SWITCHES),
        enable_errors=config.get(CONF_ENABLE_ERRORS, DEFAULT_ENABLE_ERRORS),
    )
    coordinator.fehlende_ausblenden = bool(
        config.get(CONF_FEHLENDE_AUSBLENDEN, DEFAULT_FEHLENDE_AUSBLENDEN)
    )
    coordinator.zuordnungen = zuordnung.gueltige(config.get(CONF_ZUORDNUNGEN))

    coordinator.pellet_preis = config.get(CONF_PELLET_PREIS, DEFAULT_PELLET_PREIS)
    coordinator.lager_maximum_eingetragen = float(config.get(CONF_LAGER_MAXIMUM) or 0)
    sperrt = fremderzeuger_sperrt(config, components)
    coordinator.kessel_sperre = kessel_sperre_gewaehlt(config) or bool(sperrt)
    coordinator.schnell_intervall = config.get(
        CONF_SCHNELL_INTERVALL, DEFAULT_SCHNELL_INTERVALL
    )
    coordinator.puffer_volumen_eingetragen = {
        komponente: float(config.get(puffer_volumen_schluessel(komponente)) or 0)
        for komponente in PUFFER_SPEICHER
    }
    coordinator.weitere_werte_setzen(
        config.get(CONF_WEITERE_WERTE),
        config.get(CONF_WEITERE_JE_ABFRAGE),
        config.get(CONF_WEITERE_INTERVALL),
    )
    coordinator.mit_prognose = config.get(CONF_PROGNOSE, DEFAULT_PROGNOSE)
    coordinator.mit_zeitraeumen = config.get(CONF_ZEITRAEUME, DEFAULT_ZEITRAEUME)
    coordinator.deutsche_namen = await hass.async_add_executor_job(deutsche_namen)
    await coordinator.async_discover(fub_name_overrides)
    await coordinator.async_config_entry_first_refresh()

    if coordinator.mit_prognose and _prognose_moeglich(hass, coordinator):
        coordinator.prognose = ETAPrognoseKoordinator(
            hass,
            entry,
            coordinator,
            config.get(CONF_WETTER),
            lambda: _statistik_ids(hass, entry),
            lambda: _puffer_quellen(hass, entry, coordinator),
        )

    if _aschebox_moeglich(coordinator):
        coordinator.aschebox = AscheboxPlan(hass, coordinator)
        await coordinator.aschebox.laden()
    else:
        await verwaisten_plan_melden(
            hass, entry.entry_id, endgueltig=not coordinator.enable_switches
        )

    coordinator.kesselsperre = kesselsperre_anlegen(coordinator)
    if coordinator.kesselsperre is not None:
        entry.async_on_unload(coordinator.async_add_listener(coordinator.kesselsperre.abgleichen))
    await verwaiste_sperre_aufloesen(hass, coordinator)
    if fremderzeuger_eingerichtet(config, components):
        coordinator.fremderzeuger = Fremderzeuger(
            hass,
            coordinator,
            config.get(CONF_FREMDERZEUGER_ENTITAET),
            sperrt,
            config.get(CONF_FREMDERZEUGER_SPERREN_NACH, DEFAULT_FREMDERZEUGER_SPERREN_NACH),
            config.get(CONF_FREMDERZEUGER_FREIGEBEN_NACH, DEFAULT_FREMDERZEUGER_FREIGEBEN_NACH),
            config.get(CONF_FREMDERZEUGER_FUEHLER),
            config.get(CONF_FREMDERZEUGER_SCHWELLE, DEFAULT_FREMDERZEUGER_SCHWELLE),
        )

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    if coordinator.fremderzeuger is not None:
        coordinator.fremderzeuger.starten()
        entry.async_on_unload(coordinator.fremderzeuger.beenden)
    if coordinator.aschebox is not None:
        coordinator.aschebox.starten()
        entry.async_on_unload(coordinator.aschebox.stoppen)
    _verwaiste_entitaeten_entfernen(hass, entry, coordinator)
    if coordinator.prognose is not None:
        entry.async_on_unload(async_at_started(hass, _prognose_starten(coordinator)))
    _raumfuehler_starten(hass, entry, coordinator, config)
    _zeitplaene_starten(hass, entry, coordinator, config)
    _schnelle_abfrage_starten(hass, entry, coordinator)
    _weitere_abfrage_starten(hass, entry, coordinator)
    coordinator.zeitprogramme_im_hintergrund_pruefen()
    return True


def _weitere_abfrage_starten(
    hass: HomeAssistant, entry: ETAConfigEntry, coordinator: ETADataUpdateCoordinator
) -> None:
    """Liest die frei gewählten Werte im eigenen Takt, Portion für Portion, siehe weitere_werte.py.

    Jede Abfrage bestellt die nächste: Der Abstand ist nach dem Start
    kürzer als danach, siehe ETADataUpdateCoordinator.weitere_abstand.
    """
    if not coordinator.weitere_werte:
        return

    lauf: dict = {}

    def stoppen() -> None:
        lauf["beendet"] = True
        abmelden = lauf.pop("abmelden", None)
        if abmelden is not None:
            abmelden()

    def planen() -> None:
        if not lauf.get("beendet"):
            lauf["abmelden"] = async_call_later(hass, coordinator.weitere_abstand, takt)

    async def takt(_jetzt) -> None:
        """Ein unerwarteter Fehler beendet die Abfrage - sonst stünde er bei jedem Takt im Protokoll."""
        lauf.pop("abmelden", None)
        try:
            await coordinator.async_weitere_lesen()
        except Exception:
            _LOGGER.exception(
                "ETA: Die Abfrage der weiteren Werte ist an einem Fehler gescheitert und ruht "
                "bis zum nächsten Laden der Integration"
            )
            return
        planen()

    planen()
    entry.async_on_unload(stoppen)


def _schnelle_abfrage_starten(
    hass: HomeAssistant, entry: ETAConfigEntry, coordinator: ETADataUpdateCoordinator
) -> None:
    """Liest die schnelle Gruppe im eigenen Takt, siehe async_schnell_lesen.

    Nur, wenn der Takt kürzer ist als das Abfrageintervall - sonst liest
    die volle Abfrage dieselben Werte ohnehin so oft.
    """
    sekunden = coordinator.schnell_intervall
    if sekunden <= 0 or sekunden >= coordinator.update_interval.total_seconds():
        return

    lauf: dict = {}

    def stoppen() -> None:
        abmelden = lauf.pop("abmelden", None)
        if abmelden is not None:
            abmelden()

    async def takt(_jetzt) -> None:
        """Ein unerwarteter Fehler beendet die schnelle Abfrage - sonst stünde er alle paar Sekunden im Protokoll."""
        try:
            await coordinator.async_schnell_lesen()
        except Exception:
            _LOGGER.exception(
                "ETA: Die schnelle Abfrage ist an einem Fehler gescheitert und ruht "
                "bis zum nächsten Laden der Integration"
            )
            stoppen()

    lauf["abmelden"] = async_track_time_interval(hass, takt, timedelta(seconds=sekunden))
    entry.async_on_unload(stoppen)


def _aschebox_moeglich(coordinator: ETADataUpdateCoordinator) -> bool:
    """Den Aschebox-Plan gibt es nur, wenn alles dafür bestätigt ist.

    Er schaltet den Kessel über seine Ein/Aus-Taste, drückt die
    Entaschentaste und liest dafür den Kessel-Zustand und den Verbrauch
    seit dem Leeren. Stammt einer dieser Messwerte aus einer Zuordnung von
    Hand, gibt es den Plan nicht, siehe zuordnung.STEUERND: Ein falsch
    zugeordneter Eintrag ließe ihn sonst zur falschen Zeit schalten.
    """
    return (
        coordinator.entaschen_def is not None
        and "kessel_schalter" in coordinator.switch_defs
        and bool(coordinator.sensor_defs.get("kessel_zustand", {}).get("uri"))
        and not zuordnung.STEUERND & coordinator.von_hand
    )


def _raumfuehler_starten(
    hass: HomeAssistant,
    entry: ETAConfigEntry,
    coordinator: ETADataUpdateCoordinator,
    config: dict,
) -> None:
    """Startet je Heizkreis mit gewähltem Thermometer den Sender.

    Nur für Heizkreise, deren Thermostat die Anlage bestätigt hat - also
    mit freigegebenem Schreibzugriff und externer Schnittstelle. Für alle
    anderen verschwindet ein Hinweis zu einem stummen Thermometer.
    """
    for heizkreis in THERMOSTATE:
        if heizkreis not in coordinator.thermostat_defs or not config.get(
            raumfuehler_schluessel(heizkreis)
        ):
            async_raumfuehler_pruefen(hass, entry.entry_id, heizkreis, None, False)
    for heizkreis in coordinator.thermostat_defs:
        entity_id = config.get(raumfuehler_schluessel(heizkreis))
        if not entity_id:
            continue
        sender = RaumfuehlerSender(hass, coordinator, heizkreis, entity_id)
        sender.starten()
        entry.async_on_unload(sender.stoppen)
        _LOGGER.info("ETA: %s schreibt %s als Raumtemperatur", heizkreis, entity_id)


def _zeitplaene_starten(
    hass: HomeAssistant,
    entry: ETAConfigEntry,
    coordinator: ETADataUpdateCoordinator,
    config: dict,
) -> None:
    """Startet je Heizkreis mit gewähltem Zeitplan den Abgleich.

    Nur für Heizkreise, deren Zeitprogramm die Anlage als beschreibbar
    gemeldet hat - also mit freigegebenem Schreibzugriff. Wird einer erst
    später beschreibbar (siehe zeitprogramme_nachpruefen), startet sein
    Abgleich dann. Hinweise zu Heizkreisen ohne Zeitplan oder ohne
    Schreibzugriff verschwinden gleich - zu ihnen läuft kein Abgleich mehr.
    """
    for heizkreis in THERMOSTATE:
        if not config.get(CONF_ENABLE_SWITCHES) or not config.get(zeitplan_schluessel(heizkreis)):
            async_zeitplan_hinweise_entfernen(hass, entry.entry_id, heizkreis)

    def starten(heizkreis: str) -> None:
        entity_id = config.get(zeitplan_schluessel(heizkreis))
        if not entity_id:
            async_zeitplan_hinweise_entfernen(hass, entry.entry_id, heizkreis)
            return
        if heizkreis in coordinator.zeitplan_abgleiche:
            return
        abgleich = ZeitplanAbgleich(hass, coordinator, heizkreis, entity_id)
        coordinator.zeitplan_abgleiche[heizkreis] = abgleich
        abgleich.starten()
        entry.async_on_unload(abgleich.stoppen)
        _LOGGER.info("ETA: %s übernimmt den Zeitplan %s", heizkreis, entity_id)

    for heizkreis in list(coordinator.zeitprogramm_defs):
        if heizkreis in THERMOSTATE:
            starten(heizkreis)
    coordinator.bei_neuem_zeitprogramm = starten


def _prognose_moeglich(hass: HomeAssistant, coordinator: ETADataUpdateCoordinator) -> bool:
    """Die Prognose lernt aus der Langzeitstatistik von Gesamtverbrauch
    und Außentemperatur - ohne Recorder oder einen der beiden Werte nicht.
    """
    if "recorder" not in getattr(hass.config, "components", set()):
        return False
    return all(
        coordinator.sensor_defs.get(key, {}).get("uri")
        for key in ("pellet_gesamtverbrauch", "aussentemperatur")
    )


def _statistik_ids(hass: HomeAssistant, entry: ETAConfigEntry) -> tuple[str | None, str | None]:
    """Unter welchen Entitäts-IDs Gesamtverbrauch und Außentemperatur gerade stehen.

    Jedes Mal neu nachgeschlagen, weil der Nutzer sie umbenennen kann;
    Home Assistant zieht die Statistik dann mit um.
    """
    registry = er.async_get(hass)
    return tuple(
        registry.async_get_entity_id(
            "sensor", DOMAIN, f"eta_static_{entry.entry_id}_{key}"
        )
        for key in ("pellet_gesamtverbrauch", "aussentemperatur")
    )


def _puffer_quellen(
    hass: HomeAssistant, entry: ETAConfigEntry, coordinator: ETADataUpdateCoordinator
) -> list[dict]:
    """Je Puffer mit bekanntem Volumen: Fühler, ihre Entitäts-IDs und das Volumen.

    Die Entitäts-IDs braucht die Prognose für die Statistik, die Schlüssel
    für die aktuellen Werte. Ein Puffer, dessen Fühler nicht alle im
    Register stehen, fehlt - mit einem Teil der Fühler wäre das Mittel
    schief.
    """
    registry = er.async_get(hass)
    quellen = []
    for komponente in PUFFER_SPEICHER:
        volumen = coordinator.volumen(komponente)
        schluessel = puffer_fuehler_schluessel(coordinator.sensor_defs, komponente)
        if not volumen or not schluessel:
            continue
        ids = [
            registry.async_get_entity_id("sensor", DOMAIN, f"eta_static_{entry.entry_id}_{key}")
            for key in schluessel
        ]
        if all(ids):
            quellen.append({"ids": ids, "schluessel": schluessel, "volumen": volumen})
    return quellen


def _prognose_starten(coordinator: ETADataUpdateCoordinator):
    """Rechnet die Prognose erst, wenn Home Assistant ganz gestartet ist.

    Vorher gibt es die Wetter-Entitäten womöglich noch nicht, und der
    Start soll nicht auf die Statistik warten.
    """

    async def starten(_hass: HomeAssistant) -> None:
        await coordinator.prognose.async_refresh()

    return starten


_EIGENE_ENTITAETEN = {
    "animationen": "kessel",
    "aschebox_status": "kessel",
    "aschebox_faellig": "kessel",
    "pellet_energie_gesamt": "kessel",
    "lager_niedrig": "lager",
    "lager_fuellstand": "lager",
    "fremderzeuger_heizt": "fremderzeuger",
    **{key: definition["component"] for key, definition in BILD_AUSWAHLEN.items()},
}
_PROGNOSE = {
    "pellet_prognose_morgen": "kessel",
    "pellet_prognose_treffsicherheit": "kessel",
    "pellet_prognose_status": "kessel",
    "lager_reicht_bis": "lager",
    "lager_bestellen_bis": "lager",
    "lager_reichweite": "lager",
}
_ZEITRAUM = {"pellet_verbrauch_heute", "pellet_verbrauch_woche", "pellet_verbrauch_jahr"}
_KOSTEN = {"pellet_kosten_heute", "pellet_kosten_woche", "pellet_kosten_jahr"}
_ENTFALLEN = {"puffer_energieinhalt", *(f"{komponente}_volumen" for komponente in PUFFER_SPEICHER)}
"""Schlüssel früherer Entitäten, die es nicht mehr gibt.

Die Sensoren "Puffer effektives Volumen" und "Puffer Energieinhalt".
"""
_STOERUNG = {"aktive_fehler", "stoerung"}


def entitaet_vorgesehen(
    key: str,
    components: list[str],
    enable_switches: bool,
    enable_errors: bool,
    mit_kosten: bool = False,
    mit_prognose: bool = True,
    mit_zeitraeumen: bool = True,
    kessel_sperre: bool = False,
    ofenfuehler: bool = False,
    ofenschalter: bool = False,
    weitere: frozenset[str] | set[str] = frozenset(),
) -> bool | None:
    """Sagt, ob eine Entität mit dieser Einrichtung noch entstehen kann.

    Entscheidet allein nach der Einrichtung - Komponenten und Freigaben -,
    nie danach, was die Anlage gerade meldet. Ein kurzer Aussetzer beim
    Start darf keine Entität samt ihren Anpassungen löschen. None heißt:
    unbekannter Schlüssel, nicht anfassen.
    """
    aktiv = set(components)
    if key in _ENTFALLEN:
        return False
    if weitere_werte.gewaehlt(key):
        return key in weitere
    if key in SENSORS:
        return SENSORS[key]["component"] in aktiv
    if key in SWITCHES:
        definition = SWITCHES[key]
        return (
            enable_switches
            and definition["component"] in aktiv
            and not definition.get("nur_fuer_auswahl")
        )
    if key == KESSEL_SPERRE["translation_key"]:
        return enable_switches and kessel_sperre and KESSEL_SPERRE["component"] in aktiv
    if key in SELECTS:
        return enable_switches and SELECTS[key]["component"] in aktiv
    if key in ZAHLEN:
        definition = ZAHLEN[key]
        return (
            enable_switches or bool(definition.get("sonst_in_home_assistant"))
        ) and definition["component"] in aktiv
    if key in ASCHEBOX_ENTITAETEN:
        return enable_switches and "kessel" in aktiv
    if key in _STOERUNG:
        return enable_errors
    if key in _ZEITRAUM:
        return mit_zeitraeumen and "kessel" in aktiv
    if key in _KOSTEN:
        return mit_kosten and mit_zeitraeumen and "kessel" in aktiv
    if key in _PROGNOSE:
        return mit_prognose and _PROGNOSE[key] in aktiv
    if key == FREMDERZEUGER_SCHWELLE_ZAHL:
        return ofenfuehler and "fremderzeuger" in aktiv
    if key == FREMDERZEUGER_SCHALTER:
        return ofenschalter and "fremderzeuger" in aktiv
    if key == PELLET_PREIS_ZAHL:
        return "kessel" in aktiv or "lager" in aktiv
    if key in _EIGENE_ENTITAETEN:
        return _EIGENE_ENTITAETEN[key] in aktiv
    thermostat = next(
        (hk for hk, d in THERMOSTATE.items() if key == f"{d['praefix']}_thermostat"), None
    )
    if thermostat:
        return enable_switches and thermostat in aktiv
    fuehler = re.fullmatch(r"(puffer\d?)_fuehler_\d+", key)
    if fuehler:
        return fuehler.group(1) in aktiv
    if key.startswith("komponente_"):
        return key.removeprefix("komponente_") in aktiv
    return None


_HAENGT_AN = {
    "aschebox_faellig": ("aschebox_verbrauch",),
    "aschebox_status": ("aschebox_verbrauch", "aschebox_schwelle"),
    "pellet_energie_gesamt": ("pellet_gesamtverbrauch",),
    "lager_niedrig": ("lager_vorrat",),
    "lager_fuellstand": ("lager_vorrat",),
    **{key: ("pellet_gesamtverbrauch",) for key in sorted(_ZEITRAUM | _KOSTEN)},
    **{
        key: (
            "pellet_gesamtverbrauch",
            "aussentemperatur",
            *(("lager_vorrat",) if komponente == "lager" else ()),
        )
        for key, komponente in _PROGNOSE.items()
    },
}
"""Entitäten ohne eigene Adresse, die es nur gibt, solange die Anlage diese Messwerte führt.

Mit ausgeblendeten fehlenden Werten entstehen sie nicht, wenn einer
ihrer Messwerte fehlt, siehe sensor.py und binary_sensor.py. Verbrauch
je Zeitraum, Kosten und Prognose gibt es in jedem Fall nur mit
Gesamtverbrauch - die Prognose braucht dazu die Außentemperatur, siehe
_prognose_moeglich.
"""

def abhaengige(schluessel: set[str]) -> set[str]:
    """Diese Messwerte samt den Entitäten, die an ihnen hängen, siehe _HAENGT_AN."""
    return schluessel | {
        key for key, quellen in _HAENGT_AN.items() if any(q in schluessel for q in quellen)
    }


def ohne_adresse(coordinator: ETADataUpdateCoordinator) -> set[str]:
    """Die Sensoren dieser Anlage, die nur als Platzhalter bestehen und dauerhaft "-" zeigen.

    Nicht dazu gehört der aus den Fühlern gerechnete Ladezustand eines
    Puffers: Er hat keine Adresse, aber einen Wert. Ebenso wenig, was auch
    ohne Adresse bleibt, siehe BLEIBT_OHNE_ADRESSE.
    """
    gerechnet = {f"{k}_ladezustand" for k in coordinator.puffer_mit_berechnetem_ladezustand}
    return {
        key
        for key, info in coordinator.sensor_defs.items()
        if not info.get("uri") and "platform" not in info
    } - gerechnet - BLEIBT_OHNE_ADRESSE


def platzhalter(coordinator: ETADataUpdateCoordinator) -> set[str]:
    """Die Platzhalter dieser Anlage samt den Entitäten, die an ihnen hängen."""
    return abhaengige(ohne_adresse(coordinator))


def entitaeten_abmelden(hass: HomeAssistant, entry: ETAConfigEntry, schluessel: set[str]) -> None:
    """Nimmt die Entitäten zu diesen Schlüsseln aus der Entity Registry.

    Aufgerufen im Augenblick, in dem der Nutzer fehlende Werte ausblendet
    oder eine Zuordnung von Hand aufhebt, mit dem, was die Anlage in
    diesem Augenblick nicht führt - siehe config_flow.py. Beim Start räumt
    die Integration solche Einträge bewusst nicht weg, siehe
    entitaet_vorgesehen: Ein Aussetzer der Anlage darf keine Entität samt
    ihren Anpassungen löschen.
    """
    registry = er.async_get(hass)
    praefix = f"eta_static_{entry.entry_id}_"
    for eintrag in er.async_entries_for_config_entry(registry, entry.entry_id):
        if eintrag.unique_id.startswith(praefix) and (
            eintrag.unique_id.removeprefix(praefix) in schluessel
        ):
            _LOGGER.info("ETA: %s führt die Anlage nicht, entfernt", eintrag.entity_id)
            registry.async_remove(eintrag.entity_id)


def _verwaiste_entitaeten_entfernen(
    hass: HomeAssistant, entry: ETAConfigEntry, coordinator: ETADataUpdateCoordinator
) -> None:
    """Entfernt Entitäten, die diese Einrichtung nicht mehr hervorbringt.

    Wird eine Komponente abgewählt oder der Schreibzugriff entzogen, blieben
    ihre Entitäten sonst dauerhaft als "Nicht verfügbar" stehen.
    """
    registry = er.async_get(hass)
    praefixe = (f"eta_static_{entry.entry_id}_", f"eta_switch_{entry.entry_id}_")
    for eintrag in er.async_entries_for_config_entry(registry, entry.entry_id):
        praefix = next((p for p in praefixe if eintrag.unique_id.startswith(p)), None)
        if praefix is None:
            continue
        key = eintrag.unique_id.removeprefix(praefix)
        vorgesehen = entitaet_vorgesehen(
            key,
            coordinator.components,
            coordinator.enable_switches,
            coordinator.enable_errors,
            coordinator.pellet_preis > 0,
            coordinator.mit_prognose,
            coordinator.mit_zeitraeumen,
            coordinator.kessel_sperre,
            coordinator.fremderzeuger is not None and bool(coordinator.fremderzeuger.fuehler),
            coordinator.fremderzeuger is not None and coordinator.fremderzeuger.eigener_schalter,
            set(coordinator.weitere_werte),
        )
        if vorgesehen is False:
            _LOGGER.info(
                "ETA: %s wird nicht mehr bereitgestellt, entfernt", eintrag.entity_id
            )
            registry.async_remove(eintrag.entity_id)


async def async_migrate_entry(hass: HomeAssistant, entry: ETAConfigEntry) -> bool:
    """Holt IP-Adresse und Port aus den Optionen in die Daten des Eintrags.

    Bis Version 0.20 ließen sich beide sowohl über Konfigurieren (landet in
    den Optionen) als auch über Neu konfigurieren (landet in den Daten)
    ändern. Beim Start gewinnen die Optionen - eine Änderung über Neu
    konfigurieren blieb dadurch wirkungslos. Übernommen wird der Wert aus
    den Optionen, weil das der ist, mit dem die Integration bisher lief.
    """
    if entry.version > 1:
        return False
    if entry.minor_version >= 2:
        return True

    daten = dict(entry.data)
    optionen = dict(entry.options)
    for schluessel in (CONF_HOST, CONF_PORT):
        if schluessel in optionen:
            daten[schluessel] = optionen.pop(schluessel)

    unique_id = entry.unique_id
    neue_id = f"{daten[CONF_HOST]}:{daten[CONF_PORT]}"
    vergeben = hass.config_entries.async_entry_for_domain_unique_id(DOMAIN, neue_id)
    if vergeben is None or vergeben.entry_id == entry.entry_id:
        unique_id = neue_id

    hass.config_entries.async_update_entry(
        entry, data=daten, options=optionen, unique_id=unique_id, minor_version=2
    )
    return True


async def async_remove_entry(hass: HomeAssistant, entry: ETAConfigEntry) -> None:
    """Löscht, was die Integration zu dieser Anlage gespeichert hat.

    Den gelernten Aschebox-Plan und welche Zeitpläne freigegeben sind - sonst
    blieben ihre Dateien nach dem Entfernen für immer liegen.
    """
    await aschebox_speicher(hass, entry.entry_id).async_remove()
    await zeitplan_speicher(hass, entry.entry_id).async_remove()


async def async_unload_entry(hass: HomeAssistant, entry: ETAConfigEntry) -> bool:
    """Entlädt die Integration und gibt den Variablensatz frei.

    Die Anlage hält Variablensätze im Arbeitsspeicher.
    """
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        await entry.runtime_data.async_varset_aufraeumen()
    return unload_ok
