"""Config- und Options-Flow für die ETA-Integration."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    SOURCE_IMPORT,
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
    OptionsFlowWithReload,
)
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.translation import async_get_translations
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from . import abhaengige, entitaeten_abmelden, ohne_adresse
from . import uebernahme
from . import weitere_werte as weitere
from . import zuordnung
from .api import ETAApiClient, ETAApiError, ETAValue
from .coordinator import build_sensor_defs
from .prognose_koordinator import einzige_wetter_entitaet
from .uri_discovery import (
    async_discover_uris,
    fub_namen_abgleich,
    fub_namen_im_menue,
    fub_namen_vorschlagen,
    kandidaten_fuer_zuordnung,
    vorschlaege_fuer_zuordnung,
)
from .verbindungen import braucht_auswahl, felder, im_kreis, moegliche_quellen, verbindungen
from .verbindungen import feld as verbindung_feld
from .zeitplan import programm_zusammenfassen
from .const import (
    COMPONENTS,
    CONF_COMPONENTS,
    CONF_ENABLE_ERRORS,
    CONF_ENABLE_SWITCHES,
    CONF_FREMDERZEUGER_ENTITAET,
    CONF_FREMDERZEUGER_FREIGEBEN_NACH,
    CONF_FREMDERZEUGER_FUEHLER,
    CONF_FREMDERZEUGER_NAME,
    CONF_FREMDERZEUGER_SCHWELLE,
    CONF_FREMDERZEUGER_SPERREN_NACH,
    CONF_FREMDERZEUGER_SPERRT,
    CONF_FEHLENDE_AUSBLENDEN,
    CONF_FUB_NAMES,
    CONF_KESSEL_GESPERRT,
    CONF_KESSEL_SPERRE,
    CONF_LAGER_MAXIMUM,
    CONF_LIEFERUNGEN,
    CONF_WEITERE_INTERVALL,
    CONF_WEITERE_JE_ABFRAGE,
    CONF_WEITERE_SCHNELL,
    CONF_WEITERE_WERTE,
    CONF_PELLET_KWH_PER_KG,
    CONF_PELLET_PREIS,
    CONF_PROGNOSE,
    CONF_SCAN_INTERVAL,
    CONF_SCHNELL_INTERVALL,
    CONF_VERBINDUNGEN,
    CONF_WETTER,
    CONF_ZEITRAEUME,
    CONF_ZUORDNUNGEN,
    DEFAULT_ENABLE_ERRORS,
    DEFAULT_ENABLE_SWITCHES,
    DEFAULT_FREMDERZEUGER_FREIGEBEN_NACH,
    DEFAULT_FREMDERZEUGER_NAME,
    DEFAULT_FREMDERZEUGER_SPERREN_NACH,
    DEFAULT_FEHLENDE_AUSBLENDEN,
    DEFAULT_PELLET_KWH_PER_KG,
    FREMDERZEUGER_FELDER,
    MAX_FREMDERZEUGER_WARTEZEIT,
    SENSORS,
    SPERRBARE_KESSEL,
    DEFAULT_PELLET_PREIS,
    DEFAULT_PORT,
    DEFAULT_PROGNOSE,
    DEFAULT_ZEITRAEUME,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SCHNELL_INTERVALL,
    DOMAIN,
    MAX_PELLET_KWH_PER_KG,
    MAX_PELLET_PREIS,
    MAX_PUFFER_VOLUMEN,
    MAX_SCAN_INTERVAL,
    MAX_SCHNELL_INTERVALL,
    MIN_PELLET_KWH_PER_KG,
    MIN_SCAN_INTERVAL,
    PUFFER_SPEICHER,
    THERMOSTATE,
    WOCHENTAGE,
    ZEITFENSTER_JE_TAG,
    GEZAEHLTE_KOMPONENTEN,
    anzahl_komponenten,
    components_from_config,
    fub_role_default,
    kessel_sperre_gewaehlt,
    fub_roles_for_components,
    komponenten_aus_formular,
    puffer_volumen_schluessel,
    raumfuehler_schluessel,
    zeitfenster_schluessel,
    zeitplan_schluessel,
    zeitueberwachung_schluessel,
)


FELD_WERTE = "werte"
"""Das Feld, in dem der Nutzer die fehlenden Messwerte wählt, die er zuordnen will."""


async def _test_connection(hass: HomeAssistant, host: str, port: int) -> bool:
    """Prüft, ob die Anlage erreichbar ist und Webservices aktiv sind."""
    client = ETAApiClient(hass, async_get_clientsession(hass), host, port)
    return await client.async_test_connection()


async def _menue_der_anlage(hass: HomeAssistant, host: str | None, port: int) -> dict[str, Any] | None:
    """Der Menübaum der Anlage - None, wenn sie nicht antwortet."""
    if not host:
        return None
    client = ETAApiClient(hass, async_get_clientsession(hass), host, port)
    try:
        return await client.async_get_menu()
    except ETAApiError:
        return None


async def _sensor_namen(hass: HomeAssistant, schluessel) -> dict[str, str]:
    """Je Messwert der Name, den sein Sensor in der Sprache von Home Assistant trägt.

    Zwei Messwerte heißen nie gleich. Fehlt die Übersetzung, gilt der
    deutsche Name aus const.SENSORS.
    """
    texte = await async_get_translations(hass, hass.config.language, "entity", [DOMAIN])
    return {
        key: texte.get(
            f"component.{DOMAIN}.entity.sensor.{SENSORS[key]['translation_key']}.name"
        )
        or SENSORS[key]["name"]
        for key in schluessel
    }


async def _fub_namen_der_anlage(hass: HomeAssistant, host: str | None, port: int) -> list[str]:
    """Die Namen der Funktionsblöcke, wie die Anlage sie meldet - leer, wenn sie nicht antwortet."""
    if not host:
        return []
    client = ETAApiClient(hass, async_get_clientsession(hass), host, port)
    try:
        return fub_namen_im_menue(await client.async_get_menu())
    except ETAApiError:
        return []


def _einstellungen(eingabe: dict[str, Any], bisher: list[str]) -> dict[str, Any]:
    """Was vom Formular gespeichert wird: die Komponenten statt der Anzahlen.

    Die beiden Abfrageintervalle sind ganze Sekunden - das Zahlenfeld
    liefert sie als Kommazahl, siehe _zahlenfeld.
    """
    daten = {key: wert for key, wert in eingabe.items() if key not in GEZAEHLTE_KOMPONENTEN}
    daten[CONF_COMPONENTS] = komponenten_aus_formular(eingabe, bisher)
    for feld in (CONF_SCAN_INTERVAL, CONF_SCHNELL_INTERVALL):
        if feld in daten:
            daten[feld] = int(daten[feld])
    return daten


async def _anlage_pruefen(
    hass: HomeAssistant,
    host: str | None,
    port: int,
    fub_names: dict[str, str],
    komponenten: list[str],
    schreiben: bool,
) -> tuple[list[str], dict[str, dict], dict[str, dict[tuple[str, int], str]]] | None:
    """Liest einmal den Menübaum und sagt, welche Schritte noch folgen.

    Erstens die angekreuzten Puffer, die kein Gesamtvolumen melden. Das
    ist der ältere Funktionsblock "Puffer": Er führt keines, siehe
    uri_discovery.PUFFER_VOLUMEN. Gefragt wird nur für Puffer, deren Fühler
    gefunden wurden.

    Zweitens - nur mit Schreibzugriff - die Heizkreise mit Raumfühler über
    die externe Schnittstelle, je mit URI und aktuellem Wert ihrer
    Zeitüberwachung in Sekunden.

    Drittens - ebenfalls nur mit Schreibzugriff - die Heizkreise, deren
    Zeitprogramm mit allen Zeitfenstern im Menübaum steht, je mit den URIs
    der Fenster. Meldet die Anlage schon das erste Fenster als nicht
    beschreibbar, fehlt der Heizkreis - ein Zeitplan bliebe dort wirkungslos.
    Alle Fenster prüft erst das Einrichten selbst.

    Ist der Menübaum nicht lesbar, folgt keiner der Schritte - dann None.
    """
    if not host:
        return None
    client = ETAApiClient(hass, async_get_clientsession(hass), host, port)
    try:
        gefunden, _ = await async_discover_uris(client, fub_names)
    except ETAApiError:
        return None
    ohne_volumen = [
        komponente
        for komponente in PUFFER_SPEICHER
        if komponente in komponenten
        and f"{komponente}_volumen" not in gefunden
        and any(key.startswith(f"{komponente}_fuehler_") for key in gefunden)
    ]
    thermostate: dict[str, dict] = {}
    if not schreiben:
        return ohne_volumen, thermostate, {}
    zeitprogramme = {}
    for heizkreis, definition in THERMOSTATE.items():
        uris = {
            (tag, nummer): gefunden.get(zeitfenster_schluessel(definition["praefix"], tag, nummer))
            for tag in WOCHENTAGE
            for nummer in range(1, ZEITFENSTER_JE_TAG + 1)
        }
        if heizkreis in komponenten and all(uris.values()) and await _beschreibbar(client, uris):
            zeitprogramme[heizkreis] = uris
    for heizkreis, definition in THERMOSTATE.items():
        praefix = definition["praefix"]
        if heizkreis not in komponenten or f"{praefix}_raum_extern" not in gefunden:
            continue
        uri = gefunden.get(f"{praefix}_zeitueberwachung")
        sekunden = None
        if uri:
            try:
                sekunden = int(float((await client.async_get_value(uri)).value))
            except (ETAApiError, TypeError, ValueError):
                sekunden = None
        thermostate[heizkreis] = {"uri": uri, "sekunden": sekunden}
    return ohne_volumen, thermostate, zeitprogramme


async def _beschreibbar(client: ETAApiClient, uris: dict[tuple[str, int], str]) -> bool:
    """Lässt die Anlage das erste Fenster als Zeitfenster beschreiben? Ohne Antwort: ja."""
    info = await client.async_get_varinfo(next(iter(uris.values())))
    return info is None or bool(info.get("writable") and info.get("zeitfenster"))


async def _zeitueberwachung_schreiben(
    hass: HomeAssistant, host: str, port: int, uri: str, sekunden: int
) -> None:
    """Setzt die Zeitüberwachung eines Heizkreises - nur, wenn die Anlage sie als beschreibbar meldet."""
    client = ETAApiClient(hass, async_get_clientsession(hass), host, port)
    info = await client.async_get_varinfo(uri)
    if not info or not info.get("writable"):
        raise ETAApiError("Die Zeitüberwachung ist an dieser Anlage nicht beschreibbar")
    skala = info.get("scale") or 1.0
    await client.async_set_value(uri, str(round(sekunden * skala)))


MAX_ZEITUEBERWACHUNG_MINUTEN = 60
"""Mehr nimmt die Anlage nicht an (3600 Sekunden)."""


def _raumfuehler_schema(thermostate: dict[str, dict], current: dict[str, Any]) -> vol.Schema:
    """Je Heizkreis mit externer Schnittstelle: Thermometer und Zeitüberwachung.

    Das Thermometer ist freiwillig. Die Zeitüberwachung steht in Minuten da,
    vorbelegt mit dem Wert der Anlage; 0 gibt es nicht, weil die Anlage
    einen alten Wert dann womöglich nie verwirft. Steht sie an der Anlage
    auf 0 oder ist unbekannt, sind 10 Minuten vorgeschlagen.
    """
    felder: dict = {}
    for heizkreis, info in thermostate.items():
        schluessel = raumfuehler_schluessel(heizkreis)
        felder[
            vol.Optional(schluessel, description={"suggested_value": current.get(schluessel)})
        ] = EntitySelector(EntitySelectorConfig(domain="sensor", device_class="temperature"))
        if info.get("uri"):
            minuten = current.get(zeitueberwachung_schluessel(heizkreis))
            if not minuten:
                minuten = max(1, round(info["sekunden"] / 60)) if info.get("sekunden") else 10
            felder[vol.Required(zeitueberwachung_schluessel(heizkreis), default=int(minuten))] = vol.All(
                vol.Coerce(int), vol.Range(min=1, max=MAX_ZEITUEBERWACHUNG_MINUTEN)
            )
    return vol.Schema(felder)


async def _programm_der_anlage(
    hass: HomeAssistant,
    host: str | None,
    port: int,
    zeitprogramme: dict[str, dict[tuple[str, int], str]],
) -> str:
    """Was im Zeitprogramm der Anlage steht, je Heizkreis in wenigen Zeilen."""
    client = ETAApiClient(hass, async_get_clientsession(hass), host, port)
    absaetze = []
    for heizkreis, uris in zeitprogramme.items():
        werte = await asyncio.gather(
            *(client.async_get_value(uri) for uri in uris.values()), return_exceptions=True
        )
        texte = {
            fenster: wert.text if isinstance(wert, ETAValue) else None
            for fenster, wert in zip(uris, werte)
        }
        absaetze.append(f"**{COMPONENTS[heizkreis]['name']}**\n{programm_zusammenfassen(texte)}")
    return "\n\n".join(absaetze)


def _geleert(eingabe: dict[str, Any], bisher: dict[str, Any], felder) -> dict[str, None]:
    """Freiwillige Felder, die es bisher gab und die jetzt leer sind - als None.

    Konfigurieren speichert in den Optionen. Was dort fehlt, gilt weiter
    aus der Ersteinrichtung; erst ein ausdrückliches None überdeckt es.
    Ohne das ließe sich etwa die Entität eines Fremderzeugers, die beim
    Einrichten gewählt wurde, nie wieder entfernen. Das None muss bei
    jedem weiteren Speichern wieder mit - auch ein schon geleertes Feld
    zählt deshalb als "gab es bisher".
    """
    return {feld: None for feld in felder if not eingabe.get(feld) and feld in bisher}


def _bisherige_angaben(daten: dict[str, Any], bisher: dict[str, Any]) -> dict[str, Any]:
    """Die Einstellungen, wenn der Menübaum gerade nicht lesbar ist.

    Dann entfallen die Schritte für Puffervolumen, Raumfühler, Zeitpläne
    und Verbindungen. Was dort bisher eingetragen war, bleibt für die weiter
    gewählten Komponenten stehen - sonst ginge es verloren, nur weil die Anlage beim
    Speichern gerade nicht geantwortet hat. Auch ein ausdrücklich geleertes
    Feld bleibt geleert, siehe _geleert.
    """
    komponenten = daten.get(CONF_COMPONENTS, [])
    schluessel = [puffer_volumen_schluessel(k) for k in PUFFER_SPEICHER if k in komponenten]
    if daten.get(CONF_ENABLE_SWITCHES):
        schluessel += [
            feld(heizkreis)
            for heizkreis in THERMOSTATE
            if heizkreis in komponenten
            for feld in (raumfuehler_schluessel, zeitplan_schluessel)
        ]
    schluessel.append(CONF_VERBINDUNGEN)
    return {**{k: bisher[k] for k in schluessel if k in bisher}, **daten}


def _zeitplaene_schema(zeitprogramme, current: dict[str, Any]) -> vol.Schema:
    """Je Heizkreis mit beschreibbarem Zeitprogramm ein Zeitplan-Helfer, freiwillig."""
    return vol.Schema(
        {
            vol.Optional(
                zeitplan_schluessel(heizkreis),
                description={"suggested_value": current.get(zeitplan_schluessel(heizkreis))},
            ): EntitySelector(EntitySelectorConfig(domain="schedule"))
            for heizkreis in zeitprogramme
        }
    )


def _verbindungen_schema(komponenten: list[str], wege: dict[str, str | None]) -> vol.Schema:
    """Je Teil mit mehreren möglichen Quellen eine Auswahl, vorbelegt mit wege."""
    return vol.Schema(
        {
            vol.Required(verbindung_feld(teil), default=wege[teil]): SelectSelector(
                SelectSelectorConfig(
                    options=moegliche_quellen(komponenten, teil),
                    mode=SelectSelectorMode.DROPDOWN,
                    translation_key="waermequelle",
                )
            )
            for teil in felder(komponenten)
        }
    )


def _fremderzeuger_schema(current: dict[str, Any], schreiben: bool) -> vol.Schema:
    """Name, Entität und Temperaturfühler des Fremderzeugers, mit Schreibzugriff auch, welche Kessel er sperrt.

    Entität und Fühler sind beide freiwillig - eines von beiden muss
    angegeben sein, das prüft der Schritt selbst. Die Auswahl der Kessel
    und die Wartezeiten fehlen ohne Schreibzugriff: Dann zeigt die Karte
    den Fremderzeuger nur an.
    """
    wartezeit = vol.All(vol.Coerce(float), vol.Range(min=0, max=MAX_FREMDERZEUGER_WARTEZEIT))
    felder: dict = {
        vol.Required(
            CONF_FREMDERZEUGER_NAME,
            default=current.get(CONF_FREMDERZEUGER_NAME) or DEFAULT_FREMDERZEUGER_NAME,
        ): cv.string,
        vol.Optional(
            CONF_FREMDERZEUGER_ENTITAET,
            description={"suggested_value": current.get(CONF_FREMDERZEUGER_ENTITAET)},
        ): EntitySelector(
            EntitySelectorConfig(domain=["binary_sensor", "switch", "input_boolean"])
        ),
        vol.Optional(
            CONF_FREMDERZEUGER_FUEHLER,
            description={"suggested_value": current.get(CONF_FREMDERZEUGER_FUEHLER)},
        ): EntitySelector(EntitySelectorConfig(domain="sensor", device_class="temperature")),
    }
    if schreiben:
        felder.update(
            {
                vol.Optional(
                    CONF_FREMDERZEUGER_SPERRT,
                    default=[
                        kessel
                        for kessel in SPERRBARE_KESSEL
                        if kessel in (current.get(CONF_FREMDERZEUGER_SPERRT) or [])
                    ],
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=SPERRBARE_KESSEL,
                        multiple=True,
                        mode=SelectSelectorMode.LIST,
                        translation_key="sperrbare_kessel",
                    )
                ),
                vol.Required(
                    CONF_FREMDERZEUGER_SPERREN_NACH,
                    default=current.get(
                        CONF_FREMDERZEUGER_SPERREN_NACH, DEFAULT_FREMDERZEUGER_SPERREN_NACH
                    ),
                ): wartezeit,
                vol.Required(
                    CONF_FREMDERZEUGER_FREIGEBEN_NACH,
                    default=current.get(
                        CONF_FREMDERZEUGER_FREIGEBEN_NACH, DEFAULT_FREMDERZEUGER_FREIGEBEN_NACH
                    ),
                ): wartezeit,
            }
        )
    return vol.Schema(felder)


def _puffer_schema(komponenten: list[str], current: dict[str, Any]) -> vol.Schema:
    """Je Puffer ohne Gesamtvolumen an der Anlage ein Feld für seine Liter, 0 = unbekannt."""
    return vol.Schema(
        {
            vol.Required(
                puffer_volumen_schluessel(komponente),
                default=int(current.get(puffer_volumen_schluessel(komponente)) or 0),
            ): vol.All(vol.Coerce(int), vol.Range(min=0, max=MAX_PUFFER_VOLUMEN))
            for komponente in komponenten
        }
    )


_WAEHLBARE_KOMPONENTEN = [
    key
    for key, info in COMPONENTS.items()
    if not info.get("required")
    and not any(key in plaetze for plaetze in GEZAEHLTE_KOMPONENTEN.values())
]
"""Die Komponenten zum Ankreuzen - Puffer, Warmwasser und Heizkreise fragt das Formular als Anzahl."""

_HOECHSTENS = {feld: len(plaetze) for feld, plaetze in GEZAEHLTE_KOMPONENTEN.items()}


def _verbindung_felder(current: dict[str, Any]) -> dict:
    """Die Felder, über die die Anlage erreicht wird."""
    return {
        vol.Required(CONF_HOST, default=current.get(CONF_HOST)): cv.string,
        vol.Required(CONF_PORT, default=current.get(CONF_PORT, DEFAULT_PORT)): cv.port,
    }


def wetter_vorschlag(hass: HomeAssistant, current: dict[str, Any]) -> str | None:
    """Die Wetter-Entität, die im Formular vorausgewählt ist.

    Wer schon eine gewählt oder das Feld bewusst geleert hat, bekommt das
    wieder angezeigt. Sonst die einzige Wetter-Entität, falls es genau
    eine gibt - so wie sie die Prognose auch von selbst nehmen würde.
    """
    if CONF_WETTER in current:
        return current[CONF_WETTER] or None
    return einzige_wetter_entitaet(hass)


def _zahlenfeld(kleinste: float, groesste: float, ganz: bool = True) -> NumberSelector:
    """Ein Feld zum Eintippen einer Zahl zwischen kleinste und groesste.

    Ein Selector und keine bloße Zahl im Schema: Home Assistant setzt beim
    Öffnen eines Dialogs die Schreibmarke in das erste Feld, das als bloße
    Zahl oder bloßer Text im Schema steht, und rollt dorthin. Stehen wie
    bei den Einstellungen Auswahlfelder darüber, öffnete sich der Dialog
    deshalb schon nach unten gerollt, die Anzahlen standen oberhalb des
    Bildes. Felder aus Selectoren bekommen die Schreibmarke nicht. Den Wert
    liefert der Selector als Kommazahl, siehe _einstellungen.
    """
    return NumberSelector(
        NumberSelectorConfig(
            min=kleinste,
            max=groesste,
            step=1 if ganz else "any",
            mode=NumberSelectorMode.BOX,
        )
    )


def _einstellung_felder(
    current: dict[str, Any], wetter: str | None = None, neu: bool = False
) -> dict:
    """Komponenten, Abfrageintervall, Freigaben, Zusatzfunktionen, Heizwert, Preis, Wetter.

    Eine neue Einrichtung (neu) schlägt vor, fehlende Werte auszublenden.
    Eine bestehende behält ihre Platzhalter, bis der Nutzer den Haken
    setzt, siehe CONF_FEHLENDE_AUSBLENDEN.

    Verbrauch je Zeitraum und Prognose sind abwählbar - wer nur die
    Messwerte will, bekommt dann auch nur die.

    Statt einer Liste fertiger Anlagenschemata wird hier angegeben, was an
    der Anlage vorhanden ist: wie viele Pufferspeicher, Warmwasser und
    Heizkreise, dazu angekreuzt der Rest. Der Kessel steht nicht zur Wahl,
    den hat jede Anlage. Steht eine Anzahl schon in current - das Formular
    kommt nach einem Verbindungsfehler noch einmal -, bleibt sie stehen.
    """
    komponenten = components_from_config(current)
    vorauswahl = [key for key in komponenten if key in _WAEHLBARE_KOMPONENTEN]

    def anzahl(feld: str) -> str:
        if current.get(feld) is not None:
            return str(current[feld])
        return str(anzahl_komponenten(komponenten, feld))

    return {
        **{
            vol.Required(feld, default=anzahl(feld)): SelectSelector(
                SelectSelectorConfig(
                    options=[str(zahl) for zahl in range(hoechstens + 1)],
                    mode=SelectSelectorMode.DROPDOWN,
                )
            )
            for feld, hoechstens in _HOECHSTENS.items()
        },
        vol.Required(CONF_COMPONENTS, default=vorauswahl): SelectSelector(
            SelectSelectorConfig(
                options=_WAEHLBARE_KOMPONENTEN,
                multiple=True,
                mode=SelectSelectorMode.LIST,
                translation_key="components",
            )
        ),
        vol.Required(
            CONF_SCAN_INTERVAL,
            default=current.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
        ): _zahlenfeld(MIN_SCAN_INTERVAL, MAX_SCAN_INTERVAL),
        vol.Required(
            CONF_SCHNELL_INTERVALL,
            default=current.get(CONF_SCHNELL_INTERVALL, DEFAULT_SCHNELL_INTERVALL),
        ): _zahlenfeld(0, MAX_SCHNELL_INTERVALL),
        vol.Required(
            CONF_ENABLE_ERRORS,
            default=current.get(CONF_ENABLE_ERRORS, DEFAULT_ENABLE_ERRORS),
        ): cv.boolean,
        vol.Required(
            CONF_FEHLENDE_AUSBLENDEN,
            default=bool(
                current.get(CONF_FEHLENDE_AUSBLENDEN, neu or DEFAULT_FEHLENDE_AUSBLENDEN)
            ),
        ): cv.boolean,
        vol.Required(
            CONF_ENABLE_SWITCHES,
            default=current.get(CONF_ENABLE_SWITCHES, DEFAULT_ENABLE_SWITCHES),
        ): cv.boolean,
        vol.Required(
            CONF_KESSEL_SPERRE,
            default=kessel_sperre_gewaehlt(current),
        ): cv.boolean,
        vol.Required(
            CONF_ZEITRAEUME,
            default=current.get(CONF_ZEITRAEUME, DEFAULT_ZEITRAEUME),
        ): cv.boolean,
        vol.Required(
            CONF_PROGNOSE,
            default=current.get(CONF_PROGNOSE, DEFAULT_PROGNOSE),
        ): cv.boolean,
        vol.Required(
            CONF_PELLET_KWH_PER_KG,
            default=current.get(CONF_PELLET_KWH_PER_KG, DEFAULT_PELLET_KWH_PER_KG),
        ): _zahlenfeld(MIN_PELLET_KWH_PER_KG, MAX_PELLET_KWH_PER_KG, ganz=False),
        vol.Required(
            CONF_PELLET_PREIS,
            default=current.get(CONF_PELLET_PREIS, DEFAULT_PELLET_PREIS),
        ): _zahlenfeld(0, MAX_PELLET_PREIS, ganz=False),
        vol.Optional(
            CONF_WETTER, description={"suggested_value": wetter}
        ): EntitySelector(EntitySelectorConfig(domain="weather")),
    }


def _connection_schema(current: dict[str, Any], wetter: str | None = None) -> vol.Schema:
    """Das vollständige Formular beim ersten Einrichten."""
    return vol.Schema(
        {**_verbindung_felder(current), **_einstellung_felder(current, wetter, neu=True)}
    )


def _reconfigure_schema(current: dict[str, Any]) -> vol.Schema:
    """Neu konfigurieren ändert nur, wo die Anlage zu erreichen ist."""
    return vol.Schema(_verbindung_felder(current))


def _options_schema(current: dict[str, Any], wetter: str | None = None) -> vol.Schema:
    """Konfigurieren ändert alles außer der Adresse der Anlage."""
    return vol.Schema(_einstellung_felder(current, wetter))


def _schieberegler(grenzen: tuple[int, int], einheit: str | None = None) -> NumberSelector:
    """Ein Schieberegler zwischen zwei Grenzen, in Schritten von weitere_werte.SCHRITT."""
    angaben: dict[str, Any] = {"unit_of_measurement": einheit} if einheit else {}
    return NumberSelector(
        NumberSelectorConfig(
            min=grenzen[0],
            max=grenzen[1],
            step=weitere.SCHRITT,
            mode=NumberSelectorMode.SLIDER,
            **angaben,
        )
    )


def _werte_feld(auswahl: dict[str, str]) -> SelectSelector:
    """Eine Liste mit Suche: Adresse und Name je Wert, mehrere wählbar."""
    return SelectSelector(
        SelectSelectorConfig(
            options=[SelectOptionDict(value=uri, label=name) for uri, name in auswahl.items()],
            multiple=True,
            mode=SelectSelectorMode.DROPDOWN,
        )
    )


def _weitere_schema(gruppen: dict[str, dict[str, str]], vorgabe: list[str]) -> vol.Schema:
    """Je Funktionsblock der Anlage ein Feld mit seinen wählbaren Werten.

    Der Menübaum einer Anlage führt über tausend Objekte - in einer
    einzigen Liste erschlägt das. Das Feld heißt wie der Funktionsblock:
    Home Assistant zeigt den Schlüssel eines Felds, zu dem es keine
    Übersetzung gibt, und Funktionsblöcke heißen an jeder Anlage anders.
    Aufklappbare Abschnitte gehen dafür nicht - ihre Überschrift bleibt
    ohne Übersetzung in älteren Versionen von Home Assistant leer.
    """
    return vol.Schema(
        {
            vol.Optional(fub, default=[uri for uri in vorgabe if uri in werte]): _werte_feld(werte)
            for fub, werte in gruppen.items()
        }
    )


def _takt_schema(
    gewaehlt: dict[str, str], schnell: list[str], je_abfrage: int, abstand: int
) -> vol.Schema:
    """Der Takt der gewählten Werte: welche zusätzlich schnell, wie viele je Abfrage, in welchem Abstand.

    Zur Wahl für die schnelle Abfrage stehen nur die eben gewählten
    Werte, siehe weitere_werte.py.
    """
    return vol.Schema(
        {
            vol.Optional(CONF_WEITERE_SCHNELL, default=schnell): _werte_feld(gewaehlt),
            vol.Required(CONF_WEITERE_JE_ABFRAGE, default=je_abfrage): _schieberegler(
                weitere.JE_ABFRAGE_GRENZEN
            ),
            vol.Required(CONF_WEITERE_INTERVALL, default=abstand): _schieberegler(
                weitere.INTERVALL_GRENZEN, "s"
            ),
        }
    )


def _fub_names_schema(roles: list[str], defaults: dict[str, str]) -> vol.Schema:
    """Formular zur Bestätigung/Änderung der Funktionsblock-Namen.

    Jeder FUB kann an der Steuerung umbenannt werden - die Felder sind mit
    den ETA-Standardnamen vorbelegt und können überschrieben werden.
    """
    return vol.Schema(
        {
            vol.Required(
                role, default=defaults.get(role) or fub_role_default(role, roles)
            ): cv.string
            for role in roles
        }
    )


def _fehlende_schema(namen: dict[str, str], vorgabe: list[str]) -> vol.Schema:
    """Die fehlenden Messwerte zur Wahl, mit ihren Namen, mehrere wählbar."""
    return vol.Schema({vol.Optional(FELD_WERTE, default=vorgabe): _werte_feld(namen)})


def _zuordnung_schema(
    felder: dict[str, dict[str, str]], vorgaben: dict[str, str | None]
) -> vol.Schema:
    """Je gewähltem Messwert ein Feld mit den passenden Einträgen seines Funktionsblocks.

    Das Feld heißt wie der Messwert - aus demselben Grund wie in
    _weitere_schema. Ein leeres Feld heißt: nicht zuordnen.
    """
    return vol.Schema(
        {
            vol.Optional(name, description={"suggested_value": vorgaben.get(name)}): SelectSelector(
                SelectSelectorConfig(
                    options=[
                        SelectOptionDict(value=uri, label=eintrag)
                        for uri, eintrag in eintraege.items()
                    ],
                    mode=SelectSelectorMode.DROPDOWN,
                )
            )
            for name, eintraege in felder.items()
        }
    )


class _Anlagenschritte:
    """Die Schritte nach den Funktionsblock-Namen, gleich für Einrichten und Konfigurieren.

    Die Unterklasse liefert _adresse(), _bisher und _fertig(daten), dazu
    _abschluss() für das Ende der Anlagenschritte. Für die Zuordnung von
    Hand liefert sie, woraus die Einrichtung gerade besteht
    (_einrichtung, _komponenten), und was mit dem Ergebnis geschieht
    (_zuordnung_speichern, _ohne_zuordnung).
    """

    _menue: dict[str, Any] | None = None
    """Der Menübaum der Anlage, je Dialog einmal gelesen, siehe _menue_lesen."""
    _kandidaten: dict[str, dict[str, str]] | None = None
    """Je fehlendem Messwert die Einträge seines Funktionsblocks, siehe _zuordenbare."""
    _zuordnen: list[str] = []
    """Die Messwerte, die der Nutzer im ersten Schritt der Zuordnung gewählt hat."""
    _vorschlaege: dict[str, str] | None = None
    """Je Messwert die vorgeschlagene Adresse, siehe _vorschlaege_lesen."""
    _passend: dict[str, dict[str, str]] | None = None
    """Je gewähltem Messwert die gelesenen passenden Einträge, siehe _passende_lesen."""
    _verfallen: frozenset[str] = frozenset()
    """Gewählte Messwerte, deren bisherige Zuordnung gelesen wurde und nicht mehr passt."""

    async def _nach_namen(self) -> ConfigFlowResult:
        """Nach den Funktionsblock-Namen: der Fremderzeuger, wenn er gewählt ist.

        Er steht nicht im Menübaum - gefragt wird deshalb auch dann, wenn
        die Anlage gerade nicht erreichbar ist.
        """
        if "fremderzeuger" in self._data[CONF_COMPONENTS]:
            return await self.async_step_fremderzeuger()
        return await self._nach_fub_namen()

    async def async_step_fremderzeuger(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Wie der Fremderzeuger heißt, woran man erkennt, dass er heizt, und welche Kessel er sperrt.

        Ohne Entität und ohne Temperaturfühler geht es nicht weiter.
        """
        errors: dict[str, str] = {}
        if user_input is not None:
            if user_input.get(CONF_FREMDERZEUGER_ENTITAET) or user_input.get(
                CONF_FREMDERZEUGER_FUEHLER
            ):
                self._data.update(
                    {feld: user_input[feld] for feld in FREMDERZEUGER_FELDER if user_input.get(feld) is not None}
                )
                self._data.update(
                    _geleert(
                        user_input,
                        self._bisher,
                        (CONF_FREMDERZEUGER_ENTITAET, CONF_FREMDERZEUGER_FUEHLER),
                    )
                )
                return await self._nach_fub_namen()
            errors["base"] = "fremderzeuger_ohne_quelle"
        return self.async_show_form(
            step_id="fremderzeuger",
            data_schema=_fremderzeuger_schema(
                user_input or self._bisher, bool(self._data.get(CONF_ENABLE_SWITCHES))
            ),
            errors=errors,
        )

    async def _nach_fub_namen(self) -> ConfigFlowResult:
        host, port = self._adresse()
        geprueft = await _anlage_pruefen(
            self.hass,
            host,
            port,
            self._data[CONF_FUB_NAMES],
            self._data[CONF_COMPONENTS],
            bool(self._data.get(CONF_ENABLE_SWITCHES)),
        )
        if geprueft is None:
            self._online = False
            return self._fertig(_bisherige_angaben(self._data, self._bisher))
        self._online = True
        self._ohne_volumen, self._thermostate, self._zeitprogramme = geprueft
        if self._ohne_volumen:
            return await self.async_step_puffer()
        return await self._nach_puffer()

    async def _nach_puffer(self) -> ConfigFlowResult:
        if self._thermostate:
            return await self.async_step_raumfuehler()
        return await self._nach_raumfuehler()

    async def _nach_raumfuehler(self) -> ConfigFlowResult:
        if self._zeitprogramme:
            return await self.async_step_zeitplaene()
        return await self._nach_zeitplaene()

    async def _nach_zeitplaene(self) -> ConfigFlowResult:
        """Fragt nach den Verbindungen, wenn es etwas zu wählen gibt.

        Sonst bleibt die bisherige Auswahl stehen. Konfigurieren ersetzt
        die gespeicherten Optionen im Ganzen - ohne das Mitnehmen gälte
        danach wieder die ältere Auswahl aus dem Einrichten.
        """
        if braucht_auswahl(self._data[CONF_COMPONENTS]):
            return await self.async_step_verbindungen()
        if self._bisher.get(CONF_VERBINDUNGEN):
            self._data[CONF_VERBINDUNGEN] = self._bisher[CONF_VERBINDUNGEN]
        return await self._nach_verbindungen()

    async def _nach_verbindungen(self) -> ConfigFlowResult:
        """Nach den Verbindungen ist die Anlage eingerichtet, siehe _abschluss der Unterklasse."""
        return await self._abschluss()

    async def _menue_lesen(self) -> dict[str, Any] | None:
        """Der Menübaum der Anlage, je Dialog einmal gelesen - None, wenn sie nicht antwortet."""
        if self._menue is None:
            host, port = self._adresse()
            self._menue = await _menue_der_anlage(self.hass, host, port)
        return self._menue

    def _zuordnungen(self) -> dict[str, str]:
        """Die bisher von Hand zugeordneten Adressen je Messwert, siehe zuordnung.py."""
        return zuordnung.gueltige(self._einrichtung().get(CONF_ZUORDNUNGEN))

    async def _gefunden_lesen(self, zuordnungen: dict[str, str] | None = None) -> dict[str, str]:
        """Was die Erkennung im gelesenen Menübaum findet, mit den Zuordnungen von Hand."""
        gefunden, _ = await async_discover_uris(
            None,
            self._einrichtung().get(CONF_FUB_NAMES),
            zuordnungen=self._zuordnungen() if zuordnungen is None else zuordnungen,
            menue=self._menue,
        )
        return gefunden

    async def _zuordenbare(self) -> dict[str, dict[str, str]] | None:
        """Je fehlendem Messwert die Einträge seines Funktionsblocks - None ohne Menübaum.

        Fehlend heißt: von der Erkennung nicht gefunden oder schon von
        Hand zugeordnet, siehe zuordnung.fehlende. Ein Messwert, dessen
        Funktionsblock die Anlage nicht hat, steht nicht dabei.
        """
        if await self._menue_lesen() is None:
            return None
        einrichtung = self._einrichtung()
        kandidaten = kandidaten_fuer_zuordnung(
            self._menue,
            zuordnung.fehlende(
                self._komponenten(), await self._gefunden_lesen(), self._zuordnungen()
            ),
            einrichtung.get(CONF_FUB_NAMES),
        )
        return {key: eintraege for key, eintraege in kandidaten.items() if eintraege}

    def _vorschlaege_lesen(self) -> dict[str, str]:
        """Je fehlendem Messwert ohne Zuordnung die Adresse, die die Muster vermuten.

        Aus dem gelesenen Menübaum, siehe
        uri_discovery.vorschlaege_fuer_zuordnung - gelesen wird dafür
        nichts von der Anlage.
        """
        if self._vorschlaege is None:
            bisher = self._zuordnungen()
            self._vorschlaege = vorschlaege_fuer_zuordnung(
                self._menue,
                [key for key in self._kandidaten or {} if key not in bisher],
                self._einrichtung().get(CONF_FUB_NAMES),
            )
        return self._vorschlaege

    async def async_step_fehlende_werte(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Fehlende Werte von Hand zuordnen, erster Schritt: welche, siehe zuordnung.py.

        Zur Wahl stehen die Messwerte der gewählten Komponenten, die die
        Erkennung im Menübaum nicht gefunden hat, dazu die schon
        zugeordneten. Vorgewählt ist, was schon zugeordnet ist und wofür
        es einen Vorschlag gibt, siehe _vorschlaege_lesen. Mit dem
        Absenden liest der Schritt die Funktionsblöcke der gewählten
        Messwerte, siehe _passende_lesen. Antwortet die Anlage dabei gar
        nicht, bleibt der Schritt mit einer Meldung stehen - eine
        Zuordnung geht so nicht verloren.
        """
        if self._kandidaten is None:
            self._kandidaten = await self._zuordenbare()
        if self._kandidaten is None:
            return self.async_abort(reason="cannot_connect")
        if not self._kandidaten:
            return self.async_abort(reason="nichts_zuzuordnen")
        bisher = self._zuordnungen()
        vorschlaege = self._vorschlaege_lesen()
        vorgabe = [key for key in self._kandidaten if key in bisher or key in vorschlaege]
        errors: dict[str, str] = {}
        if user_input is not None:
            self._zuordnen = [
                key for key in user_input.get(FELD_WERTE) or [] if key in self._kandidaten
            ]
            if not self._zuordnen:
                return await self._ohne_zuordnung()
            self._passend = await self._passende_lesen()
            if self._passend is not None:
                return await self.async_step_werte_zuordnen()
            errors["base"] = "cannot_connect"
            vorgabe = self._zuordnen
        return self.async_show_form(
            step_id="fehlende_werte",
            data_schema=_fehlende_schema(await _sensor_namen(self.hass, self._kandidaten), vorgabe),
            errors=errors,
            last_step=False,
        )

    async def _passende_lesen(self) -> dict[str, dict[str, str]] | None:
        """Je gewähltem Messwert die Einträge seines Blocks, die nach Art und Einheit passen.

        Dazu liest der Schritt jeden Eintrag einmal - je Funktionsblock
        einige Dutzend bis wenige hundert Anfragen. Je Adresse steht der
        Weg im Block und in Klammern, was die Anlage gerade anzeigt. Was
        die Erkennung schon für einen anderen Wert, einen Schalter oder
        ein Zeitfenster nutzt, steht nicht zur Wahl.

        Eine bisherige Zuordnung bleibt zur Wahl, auch wenn ihr Eintrag
        gerade nicht lesbar war oder inzwischen anderweitig genutzt wird -
        sonst höbe ein Aussetzer der Anlage sie beim Absenden auf. Nur
        wenn ihr Eintrag gelesen wurde und nicht mehr passt, steht sie
        nicht mehr da, siehe _verfallen.

        Antwortet die Anlage auf keine der Anfragen, None.
        """
        bisher = self._zuordnungen()
        gefunden = await self._gefunden_lesen()
        belegt = {uri for key, uri in gefunden.items() if key not in self._zuordnen}
        adressen = {
            uri for key in self._zuordnen for uri in self._kandidaten[key] if uri not in belegt
        }
        host, port = self._adresse()
        client = ETAApiClient(self.hass, async_get_clientsession(self.hass), host, port)
        gelesen = await client.async_get_values({uri: uri for uri in adressen})
        if adressen and not gelesen:
            return None

        def eintrag(weg: str, uri: str) -> str:
            anzeige = zuordnung.anzeige(gelesen[uri])
            return f"{weg} ({anzeige})" if anzeige else weg

        passend: dict[str, dict[str, str]] = {}
        verfallen: set[str] = set()
        for key in self._zuordnen:
            wege = self._kandidaten[key]
            passend[key] = {
                uri: eintrag(weg, uri)
                for uri, weg in wege.items()
                if uri in gelesen and zuordnung.passt(key, gelesen[uri])
            }
            alt = bisher.get(key)
            if alt in wege and alt not in passend[key]:
                if alt in gelesen:
                    verfallen.add(key)
                else:
                    passend[key] = {alt: wege[alt], **passend[key]}
        self._verfallen = frozenset(verfallen)
        return passend

    async def async_step_werte_zuordnen(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Fehlende Werte von Hand zuordnen, zweiter Schritt: je Messwert ein Eintrag der Anlage.

        Je gewähltem Messwert ein Feld mit den Einträgen seines
        Funktionsblocks, die nach Art und Einheit zu ihm passen, siehe
        _passende_lesen. Vorgewählt ist die bisherige Zuordnung, sonst der
        Vorschlag - beides nur, wenn es passt. Ein leeres Feld hebt eine
        Zuordnung auf. Messwerte, die hier gar nicht gewählt waren,
        behalten ihre Zuordnung. Gibt es zu einem Messwert keinen
        passenden Eintrag, nennt ihn der Hinweis über dem Formular; seine
        bisherige Zuordnung bleibt dann, außer sie passt selbst nicht mehr.
        Derselbe Eintrag lässt sich nicht zwei Messwerten zuordnen.
        """
        if self._passend is None:
            return await self.async_step_fehlende_werte()
        namen = await _sensor_namen(self.hass, self._zuordnen)
        bisher = self._zuordnungen()
        vorschlaege = self._vorschlaege_lesen()
        vorgaben: dict[str, str | None] = {}
        for key in self._zuordnen:
            wahl = bisher.get(key)
            if wahl not in self._passend[key]:
                wahl = vorschlaege.get(key)
            vorgaben[namen[key]] = wahl if wahl in self._passend[key] else None
        errors: dict[str, str] = {}
        if user_input is not None:
            neu = dict(bisher)
            for key in self._zuordnen:
                uri = user_input.get(namen[key])
                if uri in self._passend[key]:
                    neu[key] = uri
                elif self._passend[key] or key in self._verfallen:
                    neu.pop(key, None)
            if len(set(neu.values())) == len(neu):
                return await self._zuordnung_speichern(neu)
            errors["base"] = "doppelt_zugeordnet"
            vorgaben = {namen[key]: user_input.get(namen[key]) for key in self._zuordnen}
        ohne = [namen[key] for key in self._zuordnen if not self._passend[key]]
        if ohne and not errors:
            errors["base"] = "ohne_passenden_eintrag"
        return self.async_show_form(
            step_id="werte_zuordnen",
            data_schema=_zuordnung_schema(
                {namen[key]: self._passend[key] for key in self._zuordnen if self._passend[key]},
                vorgaben,
            ),
            errors=errors,
            description_placeholders={"ohne": ", ".join(ohne)},
        )

    async def _weitere_werte_auswaehlen(
        self,
        *,
        step_id: str,
        gruppen: dict[str, dict[str, str]],
        menue_werte: dict[str, dict[str, Any]],
        bisher: dict[str, dict[str, Any]],
        client: ETAApiClient,
        user_input: dict[str, Any] | None,
        bei_leer: Callable[[], Awaitable[ConfigFlowResult]],
    ) -> ConfigFlowResult:
        """Die Auswahl der weiteren Werte, gleich für Einrichten und Konfigurieren.

        gruppen sind die wählbaren Werte je Funktionsblock, bisher die
        schon gewählten nach Adresse. Jeden neu gewählten Wert liest der
        Schritt einmal: So steht fest, ob er eine Zahl mit Einheit oder
        ein Text ist - und was die Anlage gar nicht lesbar liefert, wird
        nicht angenommen. Danach folgt der Takt, siehe
        _weitere_takt_formular. Ist nichts gewählt, entscheidet bei_leer.
        """
        auswahl = {uri for werte in gruppen.values() for uri in werte}
        platzhalter = {"hoechstens": str(weitere.HOECHSTENS), "ohne": ""}
        errors: dict[str, str] = {}
        vorgabe = list(bisher)
        if user_input is not None:
            gewaehlt = [
                uri
                for uri in dict.fromkeys(
                    uri for fub in gruppen for uri in user_input.get(fub) or []
                )
                if uri in auswahl
            ]
            vorgabe = gewaehlt
            neu = {uri: uri for uri in gewaehlt if uri not in bisher}
            if len(gewaehlt) > weitere.HOECHSTENS:
                errors["base"] = "zu_viele_werte"
            else:
                gelesen = await client.async_get_values(neu) if neu else {}
                eintraege = []
                ohne = []
                for uri in gewaehlt:
                    if uri in bisher:
                        eintraege.append(bisher[uri])
                        continue
                    art = weitere.einordnen(gelesen.get(uri))
                    if art is None:
                        ohne.append(uri)
                        continue
                    eintraege.append({"uri": uri, **menue_werte[uri], **art})
                if not ohne:
                    self._weitere_eintraege = eintraege
                    if not eintraege:
                        return await bei_leer()
                    return await self.async_step_weitere_takt()
                errors["base"] = "werte_nicht_lesbar"
                platzhalter["ohne"] = ", ".join(
                    weitere.bezeichnung(menue_werte[uri]) for uri in ohne[:5]
                )
                vorgabe = [uri for uri in gewaehlt if uri not in ohne]
        return self.async_show_form(
            step_id=step_id,
            data_schema=_weitere_schema(gruppen, vorgabe),
            errors=errors,
            description_placeholders=platzhalter,
            last_step=False,
        )

    async def _weitere_takt_formular(
        self,
        *,
        je_abfrage: int,
        abstand: int,
        user_input: dict[str, Any] | None,
        speichern: Callable[[list[dict[str, Any]], int, int], Awaitable[ConfigFlowResult]],
    ) -> ConfigFlowResult:
        """Der Takt der gewählten weiteren Werte, gleich für Einrichten und Konfigurieren.

        Zwei Schieberegler: wie viele Werte eine Abfrage liest und in
        welchem Abstand die Abfragen kommen, vorbelegt mit je_abfrage und
        abstand. Dazu die Wahl, welche der eben gewählten Werte zusätzlich
        die schnelle Abfrage liest. Was mit dem Ergebnis geschieht,
        entscheidet speichern.
        """
        gewaehlt = {
            eintrag["uri"]: weitere.bezeichnung(eintrag)
            for eintrag in self._weitere_eintraege
        }
        schnell = [
            eintrag["uri"]
            for eintrag in self._weitere_eintraege
            if eintrag.get("schnell")
        ]
        errors: dict[str, str] = {}
        if user_input is not None:
            je_abfrage = weitere.je_abfrage(user_input.get(CONF_WEITERE_JE_ABFRAGE))
            abstand = weitere.intervall(
                user_input.get(CONF_WEITERE_INTERVALL), abstand
            )
            schnell = [
                uri
                for uri in dict.fromkeys(user_input.get(CONF_WEITERE_SCHNELL) or [])
                if uri in gewaehlt
            ]
            if len(schnell) <= weitere.SCHNELL_HOECHSTENS:
                eintraege = [
                    {
                        **{k: v for k, v in eintrag.items() if k != "schnell"},
                        **({"schnell": True} if eintrag["uri"] in schnell else {}),
                    }
                    for eintrag in self._weitere_eintraege
                ]
                return await speichern(eintraege, je_abfrage, abstand)
            errors["base"] = "zu_viele_schnelle_werte"
        return self.async_show_form(
            step_id="weitere_takt",
            data_schema=_takt_schema(gewaehlt, schnell, je_abfrage, abstand),
            errors=errors,
            description_placeholders={
                "gewaehlt": str(len(gewaehlt)),
                "dauer": f"{weitere.abfrage_alle(len(gewaehlt), abstand, je_abfrage):g}",
                "schnell_hoechstens": str(weitere.SCHNELL_HOECHSTENS),
            },
        )

    async def async_step_verbindungen(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Wer woher seine Wärme bekommt - für die Leitungen der Karte "ETA Übersicht".

        Nur mit mehreren Puffern oder einer Fernleitung, siehe
        verbindungen.py. Eine Auswahl im Kreis wird nicht angenommen.
        """
        komponenten = self._data[CONF_COMPONENTS]
        errors: dict[str, str] = {}
        wege = verbindungen(komponenten, self._bisher.get(CONF_VERBINDUNGEN))
        if user_input is not None:
            gewaehlt = {
                teil: user_input[verbindung_feld(teil)]
                for teil in felder(komponenten)
                if user_input.get(verbindung_feld(teil))
            }
            if not im_kreis(komponenten, gewaehlt):
                self._data[CONF_VERBINDUNGEN] = gewaehlt
                return await self._nach_verbindungen()
            errors["base"] = "verbindung_im_kreis"
            wege = {**verbindungen(komponenten), **gewaehlt}
        return self.async_show_form(
            step_id="verbindungen",
            data_schema=_verbindungen_schema(komponenten, wege),
            errors=errors,
        )

    async def async_step_zeitplaene(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Je Heizkreis ein Zeitplan-Helfer, der sein Zeitprogramm vorgibt (siehe zeitplan.py)."""
        if user_input is not None:
            self._data.update(
                {
                    zeitplan_schluessel(hk): user_input[zeitplan_schluessel(hk)]
                    for hk in self._zeitprogramme
                    if user_input.get(zeitplan_schluessel(hk))
                }
            )
            self._data.update(
                _geleert(
                    user_input,
                    self._bisher,
                    [zeitplan_schluessel(hk) for hk in self._zeitprogramme],
                )
            )
            return await self._nach_zeitplaene()
        host, port = self._adresse()
        return self.async_show_form(
            step_id="zeitplaene",
            data_schema=_zeitplaene_schema(self._zeitprogramme, self._bisher),
            description_placeholders={
                "programm": await _programm_der_anlage(
                    self.hass, host, port, self._zeitprogramme
                )
            },
        )

    async def async_step_puffer(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Fragt nach den Litern der Puffer, die kein Gesamtvolumen melden."""
        if user_input is not None:
            self._data.update(user_input)
            return await self._nach_puffer()
        return self.async_show_form(
            step_id="puffer", data_schema=_puffer_schema(self._ohne_volumen, self._bisher)
        )

    async def async_step_raumfuehler(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Thermometer als Raumfühler und Zeitüberwachung je Heizkreis mit externer Schnittstelle.

        Die Zeitüberwachung ist eine Einstellung der Anlage. Sie wird nur
        geschrieben, wenn der Wert im Formular von dem der Anlage abweicht,
        und nicht in der Integration gespeichert.
        """
        errors: dict[str, str] = {}
        if user_input is not None:
            host, port = self._adresse()
            try:
                for heizkreis, info in self._thermostate.items():
                    feld = zeitueberwachung_schluessel(heizkreis)
                    if feld not in user_input or not info.get("uri"):
                        continue
                    sekunden = int(user_input[feld]) * 60
                    if sekunden != info.get("sekunden"):
                        await _zeitueberwachung_schreiben(self.hass, host, port, info["uri"], sekunden)
                        info["sekunden"] = sekunden
            except ETAApiError:
                errors["base"] = "zeitueberwachung_nicht_geschrieben"
            else:
                self._data.update(
                    {
                        raumfuehler_schluessel(hk): user_input[raumfuehler_schluessel(hk)]
                        for hk in self._thermostate
                        if user_input.get(raumfuehler_schluessel(hk))
                    }
                )
                self._data.update(
                    _geleert(
                        user_input,
                        self._bisher,
                        [raumfuehler_schluessel(hk) for hk in self._thermostate],
                    )
                )
                return await self._nach_raumfuehler()
        return self.async_show_form(
            step_id="raumfuehler",
            data_schema=_raumfuehler_schema(self._thermostate, user_input or self._bisher),
            errors=errors,
        )


class ETAConfigFlow(_Anlagenschritte, ConfigFlow, domain=DOMAIN):
    """Einrichtung der Integration in zwei Schritten.

    Ab Unterversion 2 stehen IP-Adresse und Port nur noch in den Daten des
    Eintrags, alle übrigen Einstellungen in seinen Optionen. Vorher konnten
    beide an beiden Stellen stehen - siehe async_migrate_entry.
    """

    VERSION = 1
    MINOR_VERSION = 2

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self._ohne_volumen: list[str] = []
        self._thermostate: dict[str, dict] = {}
        self._zeitprogramme: dict[str, dict[tuple[str, int], str]] = {}
        self._weitere_eintraege: list[dict[str, Any]] = []
        """Die im Schritt der weiteren Werte gewählten, bis ihr Takt feststeht."""
        self._online = False
        """Ob die Anlage beim Einrichten geantwortet hat, siehe _nach_fub_namen."""
        self._neu_gewaehlt = False

    _bisher: dict[str, Any] = {}

    def _adresse(self) -> tuple[str | None, int]:
        return self._data.get(CONF_HOST), self._data.get(CONF_PORT, DEFAULT_PORT)

    def _fertig(self, daten: dict[str, Any]) -> ConfigFlowResult:
        return self.async_create_entry(title="ETA Heizung", data=daten)

    def _einrichtung(self) -> dict[str, Any]:
        return self._data

    def _komponenten(self) -> list[str]:
        return self._data[CONF_COMPONENTS]

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ändert IP-Adresse und Port, etwa nach einem Wechsel im Heimnetz.

        Alle anderen Einstellungen gehören zu Konfigurieren. Stünden sie an
        beiden Stellen, könnte die eine die andere still überdecken.
        """
        eintrag = self._get_reconfigure_entry()
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST]
            port = user_input[CONF_PORT]
            neue_id = f"{host}:{port}"
            if (
                neue_id != eintrag.unique_id
                and self.hass.config_entries.async_entry_for_domain_unique_id(
                    DOMAIN, neue_id
                )
            ):
                return self.async_abort(reason="already_configured")

            if await _test_connection(self.hass, host, port):
                return self.async_update_reload_and_abort(
                    eintrag,
                    unique_id=neue_id,
                    data_updates={CONF_HOST: host, CONF_PORT: port},
                )
            errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_reconfigure_schema(user_input or dict(eintrag.data)),
            errors=errors,
        )

    async def async_step_wahl(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Bietet an, eine Einrichtung von vor dem Umbenennen zu übernehmen."""
        return self.async_show_menu(step_id="wahl", menu_options=["uebernahme", "neu"])

    async def async_step_neu(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Richtet trotz alter Einrichtung eine weitere Anlage neu ein."""
        self._neu_gewaehlt = True
        return await self.async_step_user()

    async def async_step_uebernahme(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Übernimmt alle alten Einrichtungen mit ihren Einstellungen.

        Ein Dialog legt genau einen Eintrag an. Gibt es mehrere alte
        Einrichtungen, kommen die übrigen über eigene Abläufe im Hintergrund
        dazu (async_step_import).
        """
        alte = uebernahme.alte_einrichtungen(self.hass)
        if not alte:
            return self.async_abort(reason="keine_alte_einrichtung")
        if user_input is None:
            return self.async_show_form(
                step_id="uebernahme",
                description_placeholders={
                    "anlagen": ", ".join(f"{e.title} ({e.unique_id})" for e in alte)
                },
            )
        erste, *weitere = alte
        for eintrag in weitere:
            self.hass.async_create_task(
                self.hass.config_entries.flow.async_init(
                    DOMAIN,
                    context={"source": SOURCE_IMPORT},
                    data={uebernahme.UEBERNOMMEN_VON: eintrag.entry_id},
                )
            )
        return await self._uebernehmen(erste)

    async def async_step_import(self, import_data: dict[str, Any]) -> ConfigFlowResult:
        """Übernimmt eine weitere alte Einrichtung, angestoßen von async_step_uebernahme."""
        alt = self.hass.config_entries.async_get_entry(
            import_data[uebernahme.UEBERNOMMEN_VON]
        )
        if alt is None or not uebernahme.ist_alte_einrichtung(alt):
            return self.async_abort(reason="keine_alte_einrichtung")
        return await self._uebernehmen(alt)

    async def _uebernehmen(self, alt: ConfigEntry) -> ConfigFlowResult:
        """Neuer Eintrag mit Daten und Optionen der alten Einrichtung.

        Den Rest zieht async_setup_entry beim ersten Start um, siehe
        uebernahme.async_uebernehmen.
        """
        daten, optionen = uebernahme.daten_und_optionen(alt)
        await self.async_set_unique_id(f"{daten[CONF_HOST]}:{daten[CONF_PORT]}")
        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title=alt.title,
            data={**daten, uebernahme.UEBERNOMMEN_VON: alt.entry_id},
            options=optionen,
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if (
            user_input is None
            and not self._neu_gewaehlt
            and uebernahme.alte_einrichtungen(self.hass)
        ):
            return await self.async_step_wahl()
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST]
            port = user_input[CONF_PORT]

            await self.async_set_unique_id(f"{host}:{port}")
            self._abort_if_unique_id_configured()

            if await _test_connection(self.hass, host, port):
                self._data = _einstellungen(user_input, [])
                if self._data.get(CONF_ENABLE_SWITCHES):
                    return await self.async_step_switch_warning()
                return await self.async_step_fub_names()
            errors["base"] = "cannot_connect"

        eingabe = user_input or {}
        return self.async_show_form(
            step_id="user",
            data_schema=_connection_schema(
                eingabe, eingabe.get(CONF_WETTER) or wetter_vorschlag(self.hass, {})
            ),
            errors=errors,
        )

    async def async_step_switch_warning(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Lässt den Schreibzugriff ausdrücklich bestätigen.

        Erscheint nur, wenn Schalter eingeschaltet werden.
        """
        if user_input is not None:
            return await self.async_step_fub_names()
        return self.async_show_form(step_id="switch_warning")

    async def async_step_fub_names(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        roles = fub_roles_for_components(self._data[CONF_COMPONENTS])

        if user_input is not None:
            self._data[CONF_FUB_NAMES] = {role: user_input[role] for role in roles}
            return await self._nach_namen()

        host, port = self._adresse()
        namen = await _fub_namen_der_anlage(self.hass, host, port)
        vorschlag, fehlende = fub_namen_abgleich(roles, namen)
        if not fehlende:
            self._data[CONF_FUB_NAMES] = vorschlag
            return await self._nach_namen()
        sichtbar = [name for name in namen if name.strip() not in weitere.NIE_GENANNT]
        return self.async_show_form(
            step_id="fub_names",
            data_schema=_fub_names_schema(roles, vorschlag),
            description_placeholders={"vorhanden": ", ".join(sichtbar) or "-"},
        )

    async def _abschluss(self) -> ConfigFlowResult:
        """Nach den Schritten der Anlage: die Auswahl zum Schluss, wenn die Anlage antwortet.

        Antwortet sie nicht, gibt es dort nichts zu wählen, und die
        Einrichtung ist fertig.
        """
        if not self._online or await self._menue_lesen() is None:
            return self._fertig(self._data)
        return await self.async_step_abschluss()

    async def async_step_abschluss(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Die Auswahl zum Schluss: abschließen, weitere Werte wählen oder fehlende zuordnen.

        Beides gibt es auch später unter Konfigurieren. Hier steht es, weil
        gerade an einer älteren Anlage manches fehlt, was sich gleich beim
        Einrichten ergänzen lässt. Nach jedem der beiden Wege steht die
        Auswahl wieder da. Das Zuordnen fehlt, wenn es nichts zuzuordnen
        gibt.
        """
        self._kandidaten = await self._zuordenbare()
        auswahl = ["fertig", "weitere_werte"]
        if self._kandidaten:
            auswahl.append("fehlende_werte")
        return self.async_show_menu(step_id="abschluss", menu_options=auswahl)

    async def async_step_fertig(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Schließt die Einrichtung ab."""
        return self._fertig(self._data)

    async def _ohne_zuordnung(self) -> ConfigFlowResult:
        return await self.async_step_abschluss()

    async def _zuordnung_speichern(self, neu: dict[str, str]) -> ConfigFlowResult:
        """Merkt sich die Zuordnungen von Hand für den Eintrag und zeigt wieder die Auswahl."""
        self._data.pop(CONF_ZUORDNUNGEN, None)
        if neu:
            self._data[CONF_ZUORDNUNGEN] = neu
        return await self.async_step_abschluss()

    async def async_step_weitere_werte(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Wählt schon beim Einrichten Werte aus dem Menübaum, siehe weitere_werte.py.

        Wie unter Konfigurieren: je Funktionsblock ein Feld, ohne die
        Messwerte, die die Integration als feste Sensoren führt. Die
        Zeitfenster der Zeitprogramme stehen zur Wahl wie dort.
        """
        werte = weitere.menue_werte(self._menue)
        fest = {
            uri
            for key, uri in (await self._gefunden_lesen()).items()
            if "_zeitfenster_" not in key and "_absenkwert_" not in key
        }
        bisher = {
            eintrag["uri"]: eintrag
            for eintrag in weitere.gewaehlte(self._data.get(CONF_WEITERE_WERTE))
        }
        host, port = self._adresse()

        async def nichts_gewaehlt() -> ConfigFlowResult:
            for schluessel in (CONF_WEITERE_WERTE, CONF_WEITERE_JE_ABFRAGE, CONF_WEITERE_INTERVALL):
                self._data.pop(schluessel, None)
            return await self.async_step_abschluss()

        return await self._weitere_werte_auswaehlen(
            step_id="weitere_werte",
            gruppen=weitere.gruppen_fuer_menue(werte, fest, bisher),
            menue_werte=werte,
            bisher=bisher,
            client=ETAApiClient(self.hass, async_get_clientsession(self.hass), host, port),
            user_input=user_input,
            bei_leer=nichts_gewaehlt,
        )

    async def async_step_weitere_takt(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Stellt den Takt der beim Einrichten gewählten Werte, siehe _weitere_takt_formular."""

        async def speichern(
            eintraege: list[dict[str, Any]], je_abfrage: int, abstand: int
        ) -> ConfigFlowResult:
            self._data[CONF_WEITERE_WERTE] = eintraege
            self._data[CONF_WEITERE_JE_ABFRAGE] = je_abfrage
            self._data[CONF_WEITERE_INTERVALL] = abstand
            return await self.async_step_abschluss()

        return await self._weitere_takt_formular(
            je_abfrage=weitere.je_abfrage(self._data.get(CONF_WEITERE_JE_ABFRAGE)),
            abstand=weitere.intervall(
                self._data.get(CONF_WEITERE_INTERVALL),
                self._data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
            ),
            user_input=user_input,
            speichern=speichern,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry) -> OptionsFlow:
        return ETAOptionsFlow()


class ETAOptionsFlow(_Anlagenschritte, OptionsFlowWithReload):
    """Nachträgliches Ändern von Komponenten, Freigaben und FUB-Namen."""

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self._ohne_volumen: list[str] = []
        self._thermostate: dict[str, dict] = {}
        self._zeitprogramme: dict[str, dict[tuple[str, int], str]] = {}
        self._menue_werte: dict[str, dict[str, Any]] | None = None
        """Die wählbaren Werte aus dem Menübaum, einmal je Dialog gelesen."""
        self._weitere_eintraege: list[dict[str, Any]] = []
        """Die im ersten Schritt gewählten Werte, bis der zweite sie speichert."""

    @property
    def _current(self) -> dict[str, Any]:
        return {**self.config_entry.data, **self.config_entry.options}

    @property
    def _bisher(self) -> dict[str, Any]:
        return self._current

    def _adresse(self) -> tuple[str | None, int]:
        return self._current.get(CONF_HOST), self._current.get(CONF_PORT, DEFAULT_PORT)

    def _einrichtung(self) -> dict[str, Any]:
        return self._current

    def _komponenten(self) -> list[str]:
        return components_from_config(self._current)

    def _fertig(self, daten: dict[str, Any]) -> ConfigFlowResult:
        """Speichert die Einstellungen als Optionen.

        Was das Zahlenfeld "Lager Fassungsvermögen" sich gemerkt hat, steht
        in keinem Formular und bleibt deshalb ausdrücklich erhalten. Ebenso
        das Puffervolumen eines Puffers, nach dem dieser Durchlauf nicht
        gefragt hat - beim PufferFlex steht es nur im Zahlenfeld. Ebenso
        die eingetragenen Pelletlieferungen, die Sperrtemperatur des
        Fremderzeugers - solange er einen Fühler hat -, die frei gewählten
        weiteren Werte samt ihrem Takt, die Zuordnungen von Hand und dass
        Home Assistant den Kessel gesperrt hält. Die weiteren Werte und die
        Zuordnungen bleiben auch leer erhalten: Stammen sie aus der
        Ersteinrichtung, gälten sonst nach dem Speichern wieder die alten.

        Gibt es nach dem Speichern
        keine Kesselsperre mehr, räumt das Einrichten das Gemerkte auf,
        siehe switch.verwaiste_sperre_aufloesen.

        Auch jedes ausdrücklich geleerte Feld (None, siehe _geleert) bleibt
        geleert, wenn dieser Durchlauf seinen Schritt gar nicht gezeigt hat
        - etwa weil der Schreibzugriff gerade aus ist. Sonst gälte danach
        wieder der Wert aus der Ersteinrichtung.
        """
        for schluessel, wert in self._current.items():
            if wert is None and schluessel not in daten:
                daten = {schluessel: None, **daten}
        for komponente in PUFFER_SPEICHER:
            schluessel = puffer_volumen_schluessel(komponente)
            if (
                komponente in daten.get(CONF_COMPONENTS, [])
                and schluessel not in daten
                and schluessel in self._current
            ):
                daten = {schluessel: self._current[schluessel], **daten}
        if self._current.get(CONF_LAGER_MAXIMUM):
            daten = {CONF_LAGER_MAXIMUM: self._current[CONF_LAGER_MAXIMUM], **daten}
        if self._current.get(CONF_LIEFERUNGEN):
            daten = {CONF_LIEFERUNGEN: self._current[CONF_LIEFERUNGEN], **daten}
        for schluessel in (
            CONF_WEITERE_WERTE,
            CONF_WEITERE_JE_ABFRAGE,
            CONF_WEITERE_INTERVALL,
            CONF_ZUORDNUNGEN,
        ):
            if schluessel in self._current and schluessel not in daten:
                daten = {schluessel: self._current[schluessel], **daten}
        if self._current.get(CONF_FREMDERZEUGER_SCHWELLE) is not None and daten.get(
            CONF_FREMDERZEUGER_FUEHLER
        ):
            daten = {
                CONF_FREMDERZEUGER_SCHWELLE: self._current[CONF_FREMDERZEUGER_SCHWELLE],
                **daten,
            }
        if self._current.get(CONF_KESSEL_GESPERRT):
            daten = {CONF_KESSEL_GESPERRT: self._current[CONF_KESSEL_GESPERRT], **daten}
        return self.async_create_entry(title="", data=daten)

    async def _abschluss(self) -> ConfigFlowResult:
        """Konfigurieren speichert nach den Schritten der Anlage.

        Setzt der Nutzer dabei den Haken, fehlende Werte auszublenden,
        verschwinden die Platzhalter mit "-" gleich mit, siehe
        _platzhalter_abmelden.
        """
        if self._data.get(CONF_FEHLENDE_AUSBLENDEN) and not self._current.get(
            CONF_FEHLENDE_AUSBLENDEN
        ):
            await self._platzhalter_abmelden()
        return self._fertig(self._data)

    async def _platzhalter_abmelden(self) -> None:
        """Nimmt die Platzhalter aus dem Register, die es mit den neuen Einstellungen nicht mehr gibt.

        Weg kommt nur, was bisher ein Platzhalter war und auch mit den
        neuen Einstellungen keine Adresse hat. Korrigiert der Nutzer im
        selben Durchlauf etwa den Namen eines Funktionsblocks, bleiben die
        Sensoren, die die Erkennung danach findet - samt ihren
        Anpassungen. Läuft die Integration gerade nicht oder antwortet die
        Anlage nicht, bleibt alles stehen.
        """
        koordinator = getattr(self.config_entry, "runtime_data", None)
        if koordinator is None or await self._menue_lesen() is None:
            return
        gefunden, fuehler = await async_discover_uris(
            None,
            self._data.get(CONF_FUB_NAMES),
            zuordnungen=self._zuordnungen(),
            menue=self._menue,
        )
        kuenftig = build_sensor_defs(
            gefunden, fuehler, self._data[CONF_COMPONENTS], fehlende_ausblenden=True
        )
        entitaeten_abmelden(
            self.hass,
            self.config_entry,
            abhaengige({key for key in ohne_adresse(koordinator) if key not in kuenftig}),
        )

    async def _ohne_zuordnung(self) -> ConfigFlowResult:
        return self.async_abort(reason="nichts_geaendert")

    async def _zuordnung_speichern(self, neu: dict[str, str]) -> ConfigFlowResult:
        """Speichert die Zuordnungen von Hand - alle anderen Einstellungen bleiben, wie sie sind.

        Hebt der Nutzer eine Zuordnung auf und sind fehlende Werte
        ausgeblendet, gibt es den Sensor danach nicht mehr - es sei denn,
        die Erkennung findet den Messwert inzwischen selbst. Sein Eintrag
        verschwindet dann gleich mit, siehe entitaeten_abmelden.
        """
        bisher = self._zuordnungen()
        if neu == bisher:
            return self.async_abort(reason="nichts_geaendert")
        aufgehoben = set(bisher) - set(neu)
        if aufgehoben and self._current.get(CONF_FEHLENDE_AUSBLENDEN):
            gefunden = await self._gefunden_lesen(neu)
            entitaeten_abmelden(
                self.hass,
                self.config_entry,
                abhaengige({key for key in aufgehoben if key not in gefunden}),
            )
        return self.async_create_entry(
            title="", data={**self.config_entry.options, CONF_ZUORDNUNGEN: neu}
        )

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Konfigurieren beginnt mit der Wahl: Einstellungen, weitere Werte oder fehlende zuordnen."""
        if user_input is not None:
            return await self.async_step_einstellungen(user_input)
        return self.async_show_menu(
            step_id="init", menu_options=["einstellungen", "weitere_werte", "fehlende_werte"]
        )

    async def async_step_weitere_werte(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Wählt Werte aus dem Menübaum, die als Sensoren erscheinen, siehe weitere_werte.py.

        Je Funktionsblock ein Feld, in der Reihenfolge der Anlage. Zur Wahl
        steht jedes Objekt des Menübaums außer den Messwerten, die die
        Integration schon als feste Sensoren führt, und außer dem Block
        Diagnose, siehe weitere_werte.GESPERRT. Jeden neu gewählten Wert liest der Schritt einmal:
        So steht fest, ob er eine Zahl mit Einheit oder ein Text ist - und
        was die Anlage gar nicht lesbar liefert, wird nicht angenommen.
        Danach folgt der Takt, siehe async_step_weitere_takt. Ist nichts
        gewählt, wird gleich gespeichert.
        """
        if self._menue_werte is None:
            if await self._menue_lesen() is None:
                return self.async_abort(reason="cannot_connect")
            self._menue_werte = weitere.menue_werte(self._menue)
        werte = self._menue_werte
        bisher = self._weitere_bisher()
        koordinator = getattr(self.config_entry, "runtime_data", None)
        fest = set(koordinator.abfragbare_uris.values()) if koordinator is not None else set()
        host, port = self._adresse()

        async def nichts_gewaehlt() -> ConfigFlowResult:
            return await self._weitere_speichern([])

        return await self._weitere_werte_auswaehlen(
            step_id="weitere_werte",
            gruppen=weitere.gruppen_fuer_menue(werte, fest, bisher),
            menue_werte=werte,
            bisher=bisher,
            client=ETAApiClient(self.hass, async_get_clientsession(self.hass), host, port),
            user_input=user_input,
            bei_leer=nichts_gewaehlt,
        )

    def _weitere_bisher(self) -> dict[str, dict[str, Any]]:
        """Die bisher gewählten weiteren Werte nach Adresse, siehe weitere_werte.gewaehlte."""
        return {
            eintrag["uri"]: eintrag
            for eintrag in weitere.gewaehlte(self._current.get(CONF_WEITERE_WERTE))
        }

    def _weitere_takt(self) -> tuple[int, int]:
        """Werte je Abfrage und Abstand der Abfragen, wie sie bisher gelten."""
        return weitere.je_abfrage(self._current.get(CONF_WEITERE_JE_ABFRAGE)), weitere.intervall(
            self._current.get(CONF_WEITERE_INTERVALL),
            self._current.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
        )

    async def _weitere_speichern(
        self, eintraege: list[dict[str, Any]], je_abfrage: int | None = None, abstand: int | None = None
    ) -> ConfigFlowResult:
        """Speichert Auswahl und Takt - alle anderen Einstellungen bleiben, wie sie sind."""
        bisher_je, bisher_abstand = self._weitere_takt()
        return self.async_create_entry(
            title="",
            data={
                **self.config_entry.options,
                CONF_WEITERE_WERTE: eintraege,
                CONF_WEITERE_JE_ABFRAGE: bisher_je if je_abfrage is None else je_abfrage,
                CONF_WEITERE_INTERVALL: bisher_abstand if abstand is None else abstand,
            },
        )

    async def async_step_weitere_takt(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Stellt den Takt der gewählten Werte, siehe weitere_werte.py.

        Zwei Schieberegler: wie viele Werte eine Abfrage liest und in
        welchem Abstand die Abfragen kommen. Dazu die Wahl, welche der eben
        gewählten Werte zusätzlich die schnelle Abfrage liest.
        """
        je_abfrage, abstand = self._weitere_takt()
        return await self._weitere_takt_formular(
            je_abfrage=je_abfrage,
            abstand=abstand,
            user_input=user_input,
            speichern=self._weitere_speichern,
        )

    async def async_step_einstellungen(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            self._data = {
                **_einstellungen(user_input, components_from_config(self._current)),
                CONF_WETTER: user_input.get(CONF_WETTER, ""),
            }
            if self._data.get(CONF_ENABLE_SWITCHES) and not self._current.get(
                CONF_ENABLE_SWITCHES
            ):
                return await self.async_step_switch_warning()
            return await self.async_step_fub_names()

        return self.async_show_form(
            step_id="einstellungen",
            data_schema=_options_schema(
                self._current, wetter_vorschlag(self.hass, self._current)
            ),
        )

    async def async_step_switch_warning(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Wie im Einrichtungsdialog: Schreibzugriff bestätigen lassen."""
        if user_input is not None:
            return await self.async_step_fub_names()
        return self.async_show_form(step_id="switch_warning")

    async def async_step_fub_names(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        roles = fub_roles_for_components(self._data[CONF_COMPONENTS])

        if user_input is not None:
            self._data[CONF_FUB_NAMES] = {role: user_input[role] for role in roles}
            return await self._nach_namen()

        host, port = self._adresse()
        vorschlag = fub_namen_vorschlagen(
            roles,
            await _fub_namen_der_anlage(self.hass, host, port),
            self._current.get(CONF_FUB_NAMES, {}),
        )
        return self.async_show_form(
            step_id="fub_names",
            data_schema=_fub_names_schema(roles, vorschlag),
        )
