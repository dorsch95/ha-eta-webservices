"""Config- und Options-Flow für die ETA-Integration."""

from __future__ import annotations

import asyncio
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

from . import uebernahme
from . import weitere_werte as weitere
from .api import ETAApiClient, ETAApiError, ETAValue
from .prognose_koordinator import einzige_wetter_entitaet
from .uri_discovery import async_discover_uris, fub_namen_im_menue, fub_namen_vorschlagen
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
    DEFAULT_ENABLE_ERRORS,
    DEFAULT_ENABLE_SWITCHES,
    DEFAULT_FREMDERZEUGER_FREIGEBEN_NACH,
    DEFAULT_FREMDERZEUGER_NAME,
    DEFAULT_FREMDERZEUGER_SPERREN_NACH,
    DEFAULT_PELLET_KWH_PER_KG,
    FREMDERZEUGER_FELDER,
    MAX_FREMDERZEUGER_WARTEZEIT,
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


async def _test_connection(hass: HomeAssistant, host: str, port: int) -> bool:
    """Prüft, ob die Anlage erreichbar ist und Webservices aktiv sind."""
    client = ETAApiClient(hass, async_get_clientsession(hass), host, port)
    return await client.async_test_connection()


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


def _einstellung_felder(current: dict[str, Any], wetter: str | None = None) -> dict:
    """Komponenten, Abfrageintervall, Freigaben, Zusatzfunktionen, Heizwert, Preis, Wetter.

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
        {**_verbindung_felder(current), **_einstellung_felder(current, wetter)}
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


class _Anlagenschritte:
    """Die Schritte nach den Funktionsblock-Namen, gleich für Einrichten und Konfigurieren.

    Liefert die Unterklasse _adresse(), _bisher und _fertig(daten).
    """

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
            return self._fertig(_bisherige_angaben(self._data, self._bisher))
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
        return self._fertig(self._data)

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
                return self._fertig(self._data)
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
        self._neu_gewaehlt = False

    _bisher: dict[str, Any] = {}

    def _adresse(self) -> tuple[str | None, int]:
        return self._data.get(CONF_HOST), self._data.get(CONF_PORT, DEFAULT_PORT)

    def _fertig(self, daten: dict[str, Any]) -> ConfigFlowResult:
        return self.async_create_entry(title="ETA Heizung", data=daten)

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
        vorschlag = fub_namen_vorschlagen(
            roles, await _fub_namen_der_anlage(self.hass, host, port)
        )
        return self.async_show_form(
            step_id="fub_names",
            data_schema=_fub_names_schema(roles, vorschlag),
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

    def _fertig(self, daten: dict[str, Any]) -> ConfigFlowResult:
        """Speichert die Einstellungen als Optionen.

        Was das Zahlenfeld "Lager Fassungsvermögen" sich gemerkt hat, steht
        in keinem Formular und bleibt deshalb ausdrücklich erhalten. Ebenso
        das Puffervolumen eines Puffers, nach dem dieser Durchlauf nicht
        gefragt hat - beim PufferFlex steht es nur im Zahlenfeld. Ebenso
        die eingetragenen Pelletlieferungen, die Sperrtemperatur des
        Fremderzeugers - solange er einen Fühler hat -, die frei gewählten
        weiteren Werte samt ihrem Takt und dass Home Assistant den Kessel
        gesperrt hält.
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
        for schluessel in (CONF_WEITERE_WERTE, CONF_WEITERE_JE_ABFRAGE, CONF_WEITERE_INTERVALL):
            if self._current.get(schluessel):
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

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Konfigurieren beginnt mit der Wahl: Einstellungen der Anlage oder weitere Werte."""
        if user_input is not None:
            return await self.async_step_einstellungen(user_input)
        return self.async_show_menu(step_id="init", menu_options=["einstellungen", "weitere_werte"])

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
        host, port = self._adresse()
        client = ETAApiClient(self.hass, async_get_clientsession(self.hass), host, port)
        if self._menue_werte is None:
            try:
                self._menue_werte = weitere.menue_werte(await client.async_get_menu())
            except ETAApiError:
                return self.async_abort(reason="cannot_connect")
        bisher = self._weitere_bisher()
        koordinator = getattr(self.config_entry, "runtime_data", None)
        fest = set(koordinator.abfragbare_uris.values()) if koordinator is not None else set()
        gruppen: dict[str, dict[str, str]] = {}
        verschwunden = {uri: e for uri, e in bisher.items() if uri not in self._menue_werte}
        for uri, eintrag in {**self._menue_werte, **verschwunden}.items():
            if uri in bisher or uri not in fest:
                gruppen.setdefault(eintrag.get("fub") or "?", {})[uri] = weitere.bezeichnung(
                    {"pfad": eintrag.get("pfad")}
                )
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
                    eintraege.append({"uri": uri, **self._menue_werte[uri], **art})
                if not ohne:
                    self._weitere_eintraege = eintraege
                    if not eintraege:
                        return self._weitere_speichern([])
                    return await self.async_step_weitere_takt()
                errors["base"] = "werte_nicht_lesbar"
                platzhalter["ohne"] = ", ".join(
                    weitere.bezeichnung(self._menue_werte[uri]) for uri in ohne[:5]
                )
                vorgabe = [uri for uri in gewaehlt if uri not in ohne]
        return self.async_show_form(
            step_id="weitere_werte",
            data_schema=_weitere_schema(gruppen, vorgabe),
            errors=errors,
            description_placeholders=platzhalter,
            last_step=False,
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

    def _weitere_speichern(
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
        gewaehlt = {
            eintrag["uri"]: weitere.bezeichnung(eintrag) for eintrag in self._weitere_eintraege
        }
        je_abfrage, abstand = self._weitere_takt()
        schnell = [
            eintrag["uri"] for eintrag in self._weitere_eintraege if eintrag.get("schnell")
        ]
        errors: dict[str, str] = {}
        if user_input is not None:
            je_abfrage = weitere.je_abfrage(user_input.get(CONF_WEITERE_JE_ABFRAGE))
            abstand = weitere.intervall(user_input.get(CONF_WEITERE_INTERVALL), abstand)
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
                return self._weitere_speichern(eintraege, je_abfrage, abstand)
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
