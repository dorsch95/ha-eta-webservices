"""Config- und Options-Flow für die ETA-Integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
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
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .api import ETAApiClient, ETAApiError
from .prognose_koordinator import einzige_wetter_entitaet
from .uri_discovery import async_discover_uris
from .const import (
    COMPONENTS,
    CONF_COMPONENTS,
    CONF_ENABLE_ERRORS,
    CONF_ENABLE_SWITCHES,
    CONF_FUB_NAMES,
    CONF_PELLET_KWH_PER_KG,
    CONF_PELLET_PREIS,
    CONF_PROGNOSE,
    CONF_SCAN_INTERVAL,
    CONF_WETTER,
    CONF_ZEITRAEUME,
    DEFAULT_ENABLE_ERRORS,
    DEFAULT_ENABLE_SWITCHES,
    DEFAULT_PELLET_KWH_PER_KG,
    DEFAULT_PELLET_PREIS,
    DEFAULT_PORT,
    DEFAULT_PROGNOSE,
    DEFAULT_ZEITRAEUME,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_PELLET_KWH_PER_KG,
    MAX_PELLET_PREIS,
    MAX_PUFFER_VOLUMEN,
    MAX_SCAN_INTERVAL,
    MIN_PELLET_KWH_PER_KG,
    MIN_SCAN_INTERVAL,
    PUFFER_SPEICHER,
    THERMOSTATE,
    components_from_config,
    fub_role_default,
    fub_roles_for_components,
    normalize_components,
    puffer_volumen_schluessel,
    raumfuehler_schluessel,
    zeitueberwachung_schluessel,
)


async def _test_connection(hass: HomeAssistant, host: str, port: int) -> bool:
    """Prüft, ob die Anlage erreichbar ist und Webservices aktiv sind."""
    client = ETAApiClient(hass, async_get_clientsession(hass), host, port)
    return await client.async_test_connection()


async def _anlage_pruefen(
    hass: HomeAssistant,
    host: str | None,
    port: int,
    fub_names: dict[str, str],
    komponenten: list[str],
    schreiben: bool,
) -> tuple[list[str], dict[str, dict]]:
    """Liest einmal den Menübaum und sagt, welche Schritte noch folgen.

    Erstens die angekreuzten Puffer, die ihr effektives Volumen nicht
    melden. Das ist der ältere Funktionsblock "Puffer": Er kennt das Volumen
    am Display, gibt es aber nicht an die Webservices weiter. Gefragt wird
    nur für Puffer, deren Fühler gefunden wurden.

    Zweitens - nur mit Schreibzugriff - die Heizkreise mit Raumfühler über
    die externe Schnittstelle, je mit URI und aktuellem Wert ihrer
    Zeitüberwachung in Sekunden.

    Ist der Menübaum nicht lesbar, folgt keiner der beiden Schritte.
    """
    if not host:
        return [], {}
    client = ETAApiClient(hass, async_get_clientsession(hass), host, port)
    try:
        gefunden, _ = await async_discover_uris(client, fub_names)
    except ETAApiError:
        return [], {}
    ohne_volumen = [
        komponente
        for komponente in PUFFER_SPEICHER
        if komponente in komponenten
        and f"{komponente}_volumen" not in gefunden
        and any(key.startswith(f"{komponente}_fuehler_") for key in gefunden)
    ]
    thermostate: dict[str, dict] = {}
    if not schreiben:
        return ohne_volumen, thermostate
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
    return ohne_volumen, thermostate


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


def _puffer_schema(komponenten: list[str], current: dict[str, Any]) -> vol.Schema:
    """Je Puffer ohne gemeldetes Volumen ein Feld für seine Liter, 0 = unbekannt."""
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
    key for key, info in COMPONENTS.items() if not info.get("required")
]


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


def _einstellung_felder(current: dict[str, Any], wetter: str | None = None) -> dict:
    """Komponenten, Abfrageintervall, Freigaben, Zusatzfunktionen, Heizwert, Preis, Wetter.

    Verbrauch je Zeitraum und Prognose sind abwählbar - wer nur die
    Messwerte will, bekommt dann auch nur die.

    Statt einer Liste fertiger Anlagenschemata wird hier angekreuzt, was an
    der Anlage vorhanden ist. Der Kessel steht nicht zur Wahl, den hat jede
    Anlage.
    """
    vorauswahl = [
        key for key in normalize_components(components_from_config(current))
        if key in _WAEHLBARE_KOMPONENTEN
    ]
    return {
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
        ): vol.All(
            cv.positive_int,
            vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL),
        ),
        vol.Required(
            CONF_ENABLE_ERRORS,
            default=current.get(CONF_ENABLE_ERRORS, DEFAULT_ENABLE_ERRORS),
        ): cv.boolean,
        vol.Required(
            CONF_ENABLE_SWITCHES,
            default=current.get(CONF_ENABLE_SWITCHES, DEFAULT_ENABLE_SWITCHES),
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
        ): vol.All(
            vol.Coerce(float),
            vol.Range(min=MIN_PELLET_KWH_PER_KG, max=MAX_PELLET_KWH_PER_KG),
        ),
        vol.Required(
            CONF_PELLET_PREIS,
            default=current.get(CONF_PELLET_PREIS, DEFAULT_PELLET_PREIS),
        ): vol.All(vol.Coerce(float), vol.Range(min=0, max=MAX_PELLET_PREIS)),
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

    async def _nach_fub_namen(self) -> ConfigFlowResult:
        host, port = self._adresse()
        self._ohne_volumen, self._thermostate = await _anlage_pruefen(
            self.hass,
            host,
            port,
            self._data[CONF_FUB_NAMES],
            self._data[CONF_COMPONENTS],
            bool(self._data.get(CONF_ENABLE_SWITCHES)),
        )
        if self._ohne_volumen:
            return await self.async_step_puffer()
        return await self._nach_puffer()

    async def _nach_puffer(self) -> ConfigFlowResult:
        if self._thermostate:
            return await self.async_step_raumfuehler()
        return self._fertig(self._data)

    async def async_step_puffer(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Fragt nach den Litern der Puffer, die ihr Volumen nicht melden."""
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
                return self._fertig(self._data)
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

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST]
            port = user_input[CONF_PORT]

            await self.async_set_unique_id(f"{host}:{port}")
            self._abort_if_unique_id_configured()

            if await _test_connection(self.hass, host, port):
                self._data = {
                    **user_input,
                    CONF_COMPONENTS: normalize_components(
                        user_input.get(CONF_COMPONENTS)
                    ),
                }
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
            return await self._nach_fub_namen()

        return self.async_show_form(
            step_id="fub_names",
            data_schema=_fub_names_schema(roles, {}),
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

    @property
    def _current(self) -> dict[str, Any]:
        return {**self.config_entry.data, **self.config_entry.options}

    @property
    def _bisher(self) -> dict[str, Any]:
        return self._current

    def _adresse(self) -> tuple[str | None, int]:
        return self._current.get(CONF_HOST), self._current.get(CONF_PORT, DEFAULT_PORT)

    def _fertig(self, daten: dict[str, Any]) -> ConfigFlowResult:
        return self.async_create_entry(title="", data=daten)

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            self._data = {
                **user_input,
                CONF_COMPONENTS: normalize_components(
                    user_input.get(CONF_COMPONENTS)
                ),
                CONF_WETTER: user_input.get(CONF_WETTER, ""),
            }
            if self._data.get(CONF_ENABLE_SWITCHES) and not self._current.get(
                CONF_ENABLE_SWITCHES
            ):
                return await self.async_step_switch_warning()
            return await self.async_step_fub_names()

        return self.async_show_form(
            step_id="init",
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
            return await self._nach_fub_namen()

        return self.async_show_form(
            step_id="fub_names",
            data_schema=_fub_names_schema(
                roles, self._current.get(CONF_FUB_NAMES, {})
            ),
        )
