"""Thermostat je Heizkreis mit Raumfühler über die externe Schnittstelle."""

from __future__ import annotations

from typing import Any

from homeassistant.components.climate import (
    PRESET_ECO,
    PRESET_NONE,
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import ETAApiError
from .const import BETRIEBSART_AUS, THERMOSTAT_SOLL_GRENZEN, raumfuehler_schluessel
from .coordinator import AUS_BEGRIFFE, ETAConfigEntry, ETADataUpdateCoordinator
from .entitaets_ids import ids_vorschlagen
from .switch import VERWERFEN_NACH

MODUS_ZU_BETRIEBSART = {
    HVACMode.AUTO: "automatik",
    HVACMode.HEAT: "heizen",
    HVACMode.OFF: BETRIEBSART_AUS,
}
"""Welche Betriebsart der Anlage hinter welchem Modus steht.

"Absenken" ist kein eigener Modus, sondern die Voreinstellung "Eco" -
so zeigen es auch andere Heizungen in Home Assistant.
"""


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ETAConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Legt je Heizkreis mit externer Schnittstelle einen Thermostat an."""
    coordinator = entry.runtime_data
    config = {**entry.data, **entry.options}
    entities = [
        ETAThermostat(coordinator, heizkreis, definition, config.get(raumfuehler_schluessel(heizkreis)))
        for heizkreis, definition in coordinator.thermostat_defs.items()
    ]
    ids_vorschlagen(coordinator.deutsche_namen, "climate", entities)
    async_add_entities(entities)


class ETAThermostat(CoordinatorEntity[ETADataUpdateCoordinator], ClimateEntity):
    """Raumtemperatur und Raum Soll eines Heizkreises, dazu seine Betriebsart.

    Istwert ist "Raum" - der Wert, mit dem die Anlage gerade regelt. Kommt
    kein Raumwert an, zeigt der Thermostat keinen Istwert. Die Betriebsart
    stellt er über die Auswahl desselben Heizkreises um; gibt es die nicht,
    lässt sich nur die Temperatur stellen.
    """

    _attr_has_entity_name = True
    _attr_icon = "mdi:thermostat"
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_target_temperature_step = 0.5

    def __init__(
        self,
        coordinator: ETADataUpdateCoordinator,
        heizkreis: str,
        definition: dict,
        raumfuehler: str | None,
    ) -> None:
        super().__init__(coordinator)
        praefix = definition["praefix"]
        self._praefix = praefix
        self._soll = definition["raum_soll"]
        self._betriebsart = definition["betriebsart"]
        self._raumfuehler = raumfuehler or None
        self._attr_translation_key = f"{praefix}_thermostat"
        self._attr_unique_id = (
            f"eta_static_{coordinator.config_entry.entry_id}_{praefix}_thermostat"
        )
        self._attr_device_info = coordinator.device_info

        untere, obere = THERMOSTAT_SOLL_GRENZEN
        skala = self._soll["scale"] or 1.0
        if self._soll.get("min_roh") is not None:
            untere = max(untere, self._soll["min_roh"] / skala)
        if self._soll.get("max_roh") is not None:
            obere = min(obere, self._soll["max_roh"] / skala)
        self._attr_min_temp = untere
        self._attr_max_temp = obere

        self._erwartet: float | None = None
        self._widerspruch = 0

    @property
    def _optionen(self) -> list[str]:
        """Die Betriebsarten dieses Heizkreises - aus den erkannten Tasten.

        Die stehen schon nach der Erkennung fest, auch bevor die Auswahl
        als Entität angelegt ist; beide Plattformen starten gleichzeitig.
        """
        definition = self.coordinator.select_defs.get(self._betriebsart)
        if definition is None:
            return []
        return [BETRIEBSART_AUS, *definition["tasten"]]

    @property
    def _betriebsart_aktuell(self) -> str | None:
        """Wie die Auswahl sie zeigt - samt Vorwegnahme nach dem Umschalten."""
        auswahl = self.coordinator.betriebsart_auswahl.get(self._betriebsart)
        if auswahl is not None:
            return auswahl.current_option
        return self.coordinator.betriebsart_gemeldet(self._betriebsart)

    @property
    def supported_features(self) -> ClimateEntityFeature:
        merkmale = ClimateEntityFeature.TARGET_TEMPERATURE
        optionen = self._optionen
        if "absenken" in optionen:
            merkmale |= ClimateEntityFeature.PRESET_MODE
        if BETRIEBSART_AUS in optionen:
            merkmale |= ClimateEntityFeature.TURN_OFF | ClimateEntityFeature.TURN_ON
        return merkmale

    @property
    def current_temperature(self) -> float | None:
        return self.coordinator.zahl(f"{self._praefix}_raum")

    @property
    def target_temperature(self) -> float | None:
        if self._erwartet is not None:
            return self._erwartet
        return self.coordinator.zahl(f"{self._praefix}_raum_soll")

    @property
    def hvac_modes(self) -> list[HVACMode]:
        optionen = self._optionen
        return [
            modus for modus, betriebsart in MODUS_ZU_BETRIEBSART.items() if betriebsart in optionen
        ] or [HVACMode.HEAT]

    @property
    def hvac_mode(self) -> HVACMode | None:
        if not self._optionen:
            return HVACMode.HEAT
        aktuell = self._betriebsart_aktuell
        if aktuell is None:
            return None
        if aktuell == "absenken":
            return HVACMode.HEAT
        return next(
            (modus for modus, betriebsart in MODUS_ZU_BETRIEBSART.items() if betriebsart == aktuell),
            None,
        )

    @property
    def preset_modes(self) -> list[str] | None:
        if not self.supported_features & ClimateEntityFeature.PRESET_MODE:
            return None
        return [PRESET_NONE, PRESET_ECO]

    @property
    def preset_mode(self) -> str | None:
        if "absenken" not in self._optionen:
            return None
        return PRESET_ECO if self._betriebsart_aktuell == "absenken" else PRESET_NONE

    @property
    def hvac_action(self) -> HVACAction | None:
        """Heizt, solange der Heizkreis angefordert ist."""
        if self.hvac_mode == HVACMode.OFF:
            return HVACAction.OFF
        anforderung = (self.coordinator.data or {}).get(f"{self._praefix}_anforderung")
        if anforderung is None or not anforderung.text:
            return None
        if anforderung.text.strip().casefold() in AUS_BEGRIFFE:
            return HVACAction.IDLE
        return HVACAction.HEATING

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "raumfuehler": self._raumfuehler,
            "zeitueberwachung": self.coordinator.zahl(f"{self._praefix}_zeitueberwachung"),
        }

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Stellt "Raum Soll" - begrenzt auf den erlaubten Bereich, in halben Grad."""
        temperatur = kwargs.get(ATTR_TEMPERATURE)
        if temperatur is None:
            return
        temperatur = round(float(temperatur) * 2) / 2
        if not self.min_temp <= temperatur <= self.max_temp:
            raise HomeAssistantError(
                f"Raum Soll nur zwischen {self.min_temp:g} und {self.max_temp:g} °C"
            )
        roh = str(round(temperatur * (self._soll["scale"] or 1.0)))
        try:
            await self.coordinator.client.async_set_value(self._soll["uri"], roh)
        except ETAApiError as err:
            raise HomeAssistantError(f"Raum Soll konnte nicht gesetzt werden: {err}") from err
        self._erwartet = temperatur
        self._widerspruch = 0
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        await self._betriebsart_setzen(MODUS_ZU_BETRIEBSART.get(hvac_mode))

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        await self._betriebsart_setzen("absenken" if preset_mode == PRESET_ECO else "heizen")

    async def async_turn_on(self) -> None:
        await self._betriebsart_setzen("automatik")

    async def async_turn_off(self) -> None:
        await self._betriebsart_setzen(BETRIEBSART_AUS)

    async def _betriebsart_setzen(self, betriebsart: str | None) -> None:
        """Stellt über die Auswahl um - so zeigen beide dasselbe, auch vorweg."""
        auswahl = self.coordinator.betriebsart_auswahl.get(self._betriebsart)
        if auswahl is None or betriebsart not in auswahl.options:
            raise HomeAssistantError("Diese Betriebsart gibt es an diesem Heizkreis nicht")
        await auswahl.async_select_option(betriebsart)
        self.async_write_ha_state()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Gibt den erwarteten Sollwert auf, sobald die Anlage ihn meldet.

        Wie bei Schaltern: Die Anlage übernimmt einen geschriebenen Wert
        nicht sofort in ihre Antworten.
        """
        if self._erwartet is not None:
            gemeldet = self.coordinator.zahl(f"{self._praefix}_raum_soll")
            if gemeldet is not None and abs(gemeldet - self._erwartet) < 0.05:
                self._erwartet = None
            else:
                self._widerspruch += 1
                if self._widerspruch >= VERWERFEN_NACH:
                    self._erwartet = None
        super()._handle_coordinator_update()
