"""Sensor-Entitäten für die ETA-Heizung."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.restore_state import ExtraStoredData, RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import ASCHEBOX_PHASEN
from .coordinator import ETAConfigEntry, ETADataUpdateCoordinator, puffer_fuehler_schluessel
from .entitaets_ids import ids_vorschlagen
from . import prognose
from .prognose_koordinator import ETAPrognoseKoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ETAConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Registriert alle Sensoren dieser Anlage."""
    coordinator = entry.runtime_data

    entities: list[SensorEntity] = [
        (ETAMeasurementSensor if info.get("uri") else ETAPlaceholderSensor)(
            coordinator, key, info
        )
        for key, info in coordinator.sensor_defs.items()
        if "platform" not in info
    ]

    entities.append(ETAAscheboxStatusSensor(coordinator))
    if coordinator.mit_zeitraeumen and coordinator.sensor_defs.get(
        "pellet_gesamtverbrauch", {}
    ).get("uri"):
        for zeitraum in ZEITRAEUME:
            entities.append(ETAPelletZeitraumSensor(coordinator, zeitraum))
            if coordinator.pellet_preis > 0:
                entities.append(ETAPelletZeitraumSensor(coordinator, zeitraum, kosten=True))
    if "lager_vorrat" in coordinator.sensor_defs:
        entities.append(ETALagerFuellstandSensor(coordinator))
    if "puffer" in coordinator.puffer_mit_volumen:
        entities.append(ETAPufferEnergieSensor(coordinator))
    if coordinator.prognose is not None:
        schluessel = list(PROGNOSE)
        if "lager_vorrat" not in coordinator.sensor_defs:
            schluessel = [key for key in schluessel if not key.startswith("lager_")]
        entities.extend(
            ETAPrognoseSensor(coordinator.prognose, coordinator, key) for key in schluessel
        )
    entities.append(_pellet_energie(coordinator))
    if coordinator.aschebox is not None:
        entities.append(ETAAscheboxPlanSensor(coordinator))
    if coordinator.enable_errors:
        entities.append(ETAErrorSensor(coordinator))
    entities.extend(
        ETAComponentMarkerSensor(coordinator, key) for key in coordinator.components
    )

    ids_vorschlagen(coordinator.deutsche_namen, "sensor", entities)
    async_add_entities(entities)


def _pellet_energie(coordinator: ETADataUpdateCoordinator) -> SensorEntity:
    """Baut den Energiewert aus dem Gesamtverbrauch der Anlage.

    Führt eine Anlage den Gesamtverbrauch nicht - Hackgut- und
    Stückholzkessel messen ihren Verbrauch nicht -, entsteht ein
    Platzhalter mit "-", der sich dem Energie-Dashboard nicht anbietet.
    """
    if coordinator.sensor_defs.get("pellet_gesamtverbrauch", {}).get("uri"):
        return ETAPelletEnergySensor(
            coordinator, "pellet_energie_gesamt", "pellet_gesamtverbrauch"
        )
    return ETAPlaceholderSensor(
        coordinator,
        "pellet_energie_gesamt",
        {"translation_key": "pellet_energie_gesamt", "icon": "mdi:lightning-bolt"},
    )


def _nachkommastellen(coordinator: ETADataUpdateCoordinator, key: str) -> int:
    """So viele Nachkommastellen, wie die Anlage für diesen Wert angibt.

    Die Anlage nennt sie zu jedem Messwert (decPlaces), passend zu ihrer
    eigenen Messauflösung - beim Kesseldruck etwa zwei, bei Zählerständen
    in Kilogramm keine. Liegt beim Einrichten noch kein Wert vor, bleibt
    es bei einer Stelle.
    """
    reading = (coordinator.data or {}).get(key)
    if reading is None or reading.is_text or reading.dec_places is None:
        return 1
    return max(0, min(reading.dec_places, 3))


class ETABaseSensor(CoordinatorEntity[ETADataUpdateCoordinator], SensorEntity):
    """Gemeinsame Basis aller ETA-Sensoren."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: ETADataUpdateCoordinator, key: str) -> None:
        super().__init__(coordinator)
        self._key = key
        self._attr_unique_id = f"eta_static_{coordinator.config_entry.entry_id}_{key}"
        self._attr_device_info = coordinator.device_info


class ETAMeasurementSensor(ETABaseSensor):
    """Ein von der Anlage gelesener Messwert.

    Die Einheit stammt fest aus der Sensordefinition, nicht aus der
    XML-Antwort: eine wechselnde Einheit verwirft die Langzeitstatistik.
    """

    _missing_value = None

    def __init__(
        self,
        coordinator: ETADataUpdateCoordinator,
        key: str,
        info: dict,
    ) -> None:
        super().__init__(coordinator, key)
        self._attr_translation_key = info["translation_key"]
        self._attr_icon = info["icon"]
        self._attr_device_class = info.get("device_class")
        self._attr_state_class = info.get("state_class")

        if not info.get("is_string"):
            self._attr_native_unit_of_measurement = info.get("default_unit")
            if info.get("suggested_unit"):
                self._attr_suggested_unit_of_measurement = info["suggested_unit"]
            self._attr_suggested_display_precision = _nachkommastellen(
                coordinator, key
            )

        self._position = info.get("position")
        self._zustaende = info.get("zustaende")
        if self._zustaende:
            self._attr_options = list(dict.fromkeys(self._zustaende.values()))

    @property
    def available(self) -> bool:
        """Ein Wert, der mehrfach ausbleibt, gilt als nicht erreichbar."""
        if not super().available:
            return False
        return self.coordinator.sensor_status(self._key) != "nicht_erreichbar"

    @property
    def extra_state_attributes(self) -> dict:
        attribute = {"status": self.coordinator.sensor_status(self._key)}
        if self._position:
            attribute["position"] = self._position
        return attribute

    @property
    def native_value(self):
        reading = self.coordinator.data.get(self._key)
        if reading is None:
            return self._missing_value
        if self._zustaende:
            return self.coordinator.zustand(self._key)
        return reading.display


class ETAPlaceholderSensor(ETAMeasurementSensor):
    """Ein Messwert, den der Menübaum dieser Anlage nicht hergibt.

    Die Entität entsteht trotzdem und zeigt dauerhaft "-", damit
    Dashboards und Automatisierungen nicht je nach Anlage ins Leere
    zeigen. Einheit, Geräte- und Zustandsklasse bleiben leer - Home
    Assistant lehnt einen Sensor mit numerischer Geräteklasse und dem
    Zustand "-" sonst ab.
    """

    _attr_device_class = None
    _attr_state_class = None
    _attr_native_unit_of_measurement = None
    _attr_suggested_display_precision = None

    def __init__(
        self,
        coordinator: ETADataUpdateCoordinator,
        key: str,
        info: dict,
    ) -> None:
        super().__init__(coordinator, key, info)
        self._attr_device_class = None
        self._attr_state_class = None
        self._attr_native_unit_of_measurement = None
        self._attr_suggested_unit_of_measurement = None
        self._attr_suggested_display_precision = None
        self._attr_options = None

    @property
    def native_value(self) -> str:
        return "-"


class ETAAscheboxStatusSensor(ETABaseSensor):
    """Kombinierte Anzeige "Verbrauch/Schwellwert", z.B. "459/1000kg".

    picture-elements-Karten können keine zwei Werte zusammenführen. Die
    Einheit steckt im Text selbst, weil ein Textwert keine
    unit_of_measurement tragen darf.

    Führt die Anlage einen der beiden Werte gar nicht - ein Kessel ohne
    Aschebox, oder gar kein Kessel-Block -, steht dort "-" wie bei jedem
    Messwert, den die Anlage nicht kennt, statt "Unbekannt".
    """

    _attr_icon = "mdi:trash-can"
    _attr_translation_key = "aschebox_status"

    def __init__(self, coordinator: ETADataUpdateCoordinator) -> None:
        super().__init__(coordinator, "aschebox_status")

    @property
    def native_value(self):
        defs = self.coordinator.sensor_defs
        if not all(defs.get(key, {}).get("uri") for key in ("aschebox_verbrauch", "aschebox_schwelle")):
            return "-"
        verbrauch = self.coordinator.data.get("aschebox_verbrauch")
        schwelle = self.coordinator.data.get("aschebox_schwelle")
        if verbrauch is None or schwelle is None:
            return None
        try:
            return f"{float(verbrauch.value):.0f}/{float(schwelle.value):.0f}kg"
        except (TypeError, ValueError):
            return None


class ETAAscheboxPlanSensor(SensorEntity):
    """In welchem Schritt der Aschebox-Plan gerade ist, siehe aschebox.py.

    Die Attribute nennen die gewünschte Zeit, wann der Kessel ausgeht und
    wie lange Glutabbrand und Entaschung zuletzt gedauert haben.
    """

    _attr_has_entity_name = True
    _attr_translation_key = "aschebox_plan"
    _attr_icon = "mdi:delete-clock"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = list(ASCHEBOX_PHASEN)
    _attr_should_poll = False

    def __init__(self, coordinator: ETADataUpdateCoordinator) -> None:
        self._key = "aschebox_plan"
        self._plan = coordinator.aschebox
        self._attr_unique_id = f"eta_static_{coordinator.config_entry.entry_id}_aschebox_plan"
        self._attr_device_info = coordinator.device_info

    @property
    def native_value(self) -> str:
        return self._plan.phase

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        aktiv = self._plan.phase != "aus"
        gelernt = self._plan.gelernt
        return {
            "ziel": self._plan.ziel.isoformat() if aktiv and self._plan.ziel else None,
            "abschalten_um": (
                self._plan.abschalten_um.isoformat() if aktiv and self._plan.abschalten_um else None
            ),
            "vorlauf_minuten": round(self._plan.dauer.total_seconds() / 60),
            "gemessen_minuten": None if gelernt is None else round(gelernt.total_seconds() / 60),
        }

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self._plan.zuhoeren(self._geaendert))

    @callback
    def _geaendert(self) -> None:
        self.async_write_ha_state()


class ETALagerFuellstandSensor(ETABaseSensor):
    """Wie voll das Pelletlager ist, in Prozent vom maximalen Vorrat.

    Beide Werte stammen aus der Anlage: "Vorrat" und "Maximaler Vorrat",
    den der Nutzer dort für seinen Lagerraum eingestellt hat. Die
    Lager-Kachel wählt danach ihr Bild.
    """

    _attr_icon = "mdi:silo"
    _attr_translation_key = "lager_fuellstand"
    _attr_native_unit_of_measurement = "%"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 0

    def __init__(self, coordinator: ETADataUpdateCoordinator) -> None:
        super().__init__(coordinator, "lager_fuellstand")

    @property
    def native_value(self):
        vorrat = self.coordinator.data.get("lager_vorrat")
        maximum = self.coordinator.data.get("lager_maximum")
        if vorrat is None or maximum is None:
            return None
        try:
            vorrat_kg, maximum_kg = float(vorrat.value), float(maximum.value)
        except (TypeError, ValueError):
            return None
        if maximum_kg <= 0:
            return None
        return round(max(0.0, vorrat_kg / maximum_kg * 100))


class ETAPufferEnergieSensor(ETABaseSensor):
    """Wie viel nutzbare Wärme im Pufferspeicher steckt, in kWh.

    Aus Volumen und Pufferfühlern: Jeder Fühler steht für einen gleich
    großen Teil des Speichers, gezählt wird die Wärme über
    prognose.PUFFER_BEZUG. Das Volumen ist das effektive, das PufferFlex
    selbst meldet; beim älteren Funktionsblock "Puffer" trägt es der Nutzer
    ein. Fehlt ein Fühler, bleibt der Wert leer, statt schief zu sein.

    Nur für den ersten Puffer - weitere fließen in die Prognose ein, ohne
    eigene Entität.
    """

    _attr_icon = "mdi:heat-wave"
    _attr_device_class = SensorDeviceClass.ENERGY_STORAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "kWh"
    _attr_suggested_display_precision = 1

    def __init__(self, coordinator: ETADataUpdateCoordinator, komponente: str = "puffer") -> None:
        super().__init__(coordinator, f"{komponente}_energieinhalt")
        self._attr_translation_key = f"{komponente}_energieinhalt"
        self._komponente = komponente
        self._fuehler = puffer_fuehler_schluessel(coordinator.sensor_defs, komponente)

    @property
    def native_value(self) -> float | None:
        werte = prognose.puffer_temperaturen(self.coordinator.data, self._fuehler)
        inhalt = prognose.puffer_energieinhalt(werte, self.coordinator.volumen(self._komponente))
        return round(inhalt, 2) if inhalt is not None else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "volumen_liter": self.coordinator.volumen(self._komponente),
            "volumen_quelle": self.coordinator.volumen_quelle(self._komponente),
            "ab_temperatur": prognose.PUFFER_BEZUG,
        }


ZEITRAEUME = ("heute", "woche", "jahr")
"""Die Zeiträume, für die Verbrauch und Kosten gezählt werden."""


def zeitraum_beginn(zeitraum: str, jetzt: datetime) -> datetime:
    """Der Beginn des laufenden Zeitraums in Ortszeit.

    Heute beginnt um Mitternacht, die Woche am Montag, das Jahr am
    1. Januar.
    """
    tag = jetzt.date()
    if zeitraum == "woche":
        tag -= timedelta(days=tag.weekday())
    elif zeitraum == "jahr":
        tag = date(tag.year, 1, 1)
    return dt_util.start_of_local_day(tag)


class _Zaehlerstand(ExtraStoredData):
    """Was ein Zeitraum-Sensor über einen Neustart hinweg behalten muss."""

    def __init__(self, beginn: datetime | None, basis: float | None) -> None:
        self.beginn = beginn
        self.basis = basis

    def as_dict(self) -> dict[str, Any]:
        return {
            "beginn": self.beginn.isoformat() if self.beginn else None,
            "basis": self.basis,
        }


class ETAPelletZeitraumSensor(ETABaseSensor, RestoreEntity):
    """Pelletverbrauch oder -kosten seit Beginn des Tages, der Woche, des Jahres.

    Grundlage ist der Gesamtverbrauch der Anlage, ein Zähler, der nie
    zurückspringt. Zu Beginn jedes Zeitraums merkt sich der Sensor dessen
    Stand; angezeigt wird der Zuwachs seitdem. Den gemerkten Stand
    behält er über einen Neustart von Home Assistant hinweg. Beim ersten
    Einrichten beginnt die Zählung mit dem Einrichten, nicht rückwirkend.

    Die Kosten rechnen den Verbrauch mit dem eingestellten Pelletpreis in
    Euro je Tonne um.
    """

    _attr_state_class = SensorStateClass.TOTAL

    def __init__(
        self, coordinator: ETADataUpdateCoordinator, zeitraum: str, kosten: bool = False
    ) -> None:
        key = f"pellet_{'kosten' if kosten else 'verbrauch'}_{zeitraum}"
        super().__init__(coordinator, key)
        self._attr_translation_key = key
        self._zeitraum = zeitraum
        self._kosten = kosten
        self._beginn: datetime | None = None
        self._basis: float | None = None
        if kosten:
            self._attr_device_class = SensorDeviceClass.MONETARY
            self._attr_native_unit_of_measurement = "EUR"
            self._attr_suggested_display_precision = 2
            self._attr_icon = "mdi:cash"
        else:
            self._attr_device_class = SensorDeviceClass.WEIGHT
            self._attr_native_unit_of_measurement = "kg"
            self._attr_suggested_display_precision = 0
            self._attr_icon = "mdi:fire"

    def _gesamt(self) -> float | None:
        wert = (self.coordinator.data or {}).get("pellet_gesamtverbrauch")
        if wert is None:
            return None
        try:
            return float(wert.value)
        except (TypeError, ValueError):
            return None

    def _pruefen(self) -> None:
        """Beginnt bei Bedarf einen neuen Zeitraum."""
        beginn = zeitraum_beginn(self._zeitraum, dt_util.now())
        gesamt = self._gesamt()
        if self._beginn != beginn:
            self._beginn = beginn
            self._basis = gesamt
        elif self._basis is None or (gesamt is not None and gesamt < self._basis):
            self._basis = gesamt

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        gespeichert = await self.async_get_last_extra_data()
        if gespeichert is not None:
            daten = gespeichert.as_dict()
            if daten.get("beginn"):
                self._beginn = dt_util.parse_datetime(daten["beginn"])
            self._basis = daten.get("basis")
        self._pruefen()
        self.async_on_remove(
            async_track_time_change(
                self.hass, self._neuer_tag, hour=0, minute=0, second=5
            )
        )

    @callback
    def _neuer_tag(self, _jetzt: datetime) -> None:
        """Um Mitternacht auf null, auch wenn die Anlage gerade schweigt."""
        self._pruefen()
        self.async_write_ha_state()

    @callback
    def _handle_coordinator_update(self) -> None:
        self._pruefen()
        super()._handle_coordinator_update()

    @property
    def extra_restore_state_data(self) -> _Zaehlerstand:
        return _Zaehlerstand(self._beginn, self._basis)

    @property
    def last_reset(self) -> datetime | None:
        return self._beginn

    @property
    def native_value(self) -> float | None:
        gesamt = self._gesamt()
        if gesamt is None or self._basis is None:
            return None
        verbrauch = max(0.0, gesamt - self._basis)
        if self._kosten:
            return round(verbrauch * self.coordinator.pellet_preis / 1000, 2)
        return verbrauch


class ETAErrorSensor(ETABaseSensor):
    """Zeigt, wie viele Fehler an der Anlage anstehen.

    Die Meldungen stehen in den Attributen, mit Funktionsblock, Priorität
    und Zeitpunkt.
    """

    _attr_translation_key = "aktive_fehler"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: ETADataUpdateCoordinator) -> None:
        super().__init__(coordinator, "aktive_fehler")

    @property
    def icon(self) -> str:
        return "mdi:alert-circle" if self.coordinator.errors else "mdi:check-circle"

    @property
    def native_value(self) -> int:
        return len(self.coordinator.errors)

    @property
    def extra_state_attributes(self) -> dict:
        return {"fehler": [fehler.as_dict() for fehler in self.coordinator.errors]}


class ETAPelletEnergySensor(ETABaseSensor):
    """Rechnet den Gesamtverbrauch in Kilogramm in Energie um.

    Das Energie-Dashboard nimmt nur Quellen an, die Energie in kWh als
    aufsummierenden Zähler liefern.
    """

    _attr_icon = "mdi:lightning-bolt"
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = "kWh"
    _attr_suggested_display_precision = 0

    def __init__(
        self, coordinator: ETADataUpdateCoordinator, key: str, quelle: str
    ) -> None:
        super().__init__(coordinator, key)
        self._attr_translation_key = key
        self._quelle = quelle

    @property
    def native_value(self):
        verbrauch = self.coordinator.data.get(self._quelle)
        if verbrauch is None:
            return None
        try:
            return float(verbrauch.value) * self.coordinator.pellet_kwh_per_kg
        except (TypeError, ValueError):
            return None


class ETAComponentMarkerSensor(ETABaseSensor):
    """Meldet, dass eine Anlagenkomponente eingerichtet ist.

    Dashboard-Karten blenden ihre Kacheln darüber ein. Der Marker liefert
    konstant den Komponentenschlüssel und bleibt auch bei gestörter
    Abfrage verfügbar.
    """

    _attr_icon = "mdi:puzzle-outline"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: ETADataUpdateCoordinator, component: str) -> None:
        super().__init__(coordinator, f"komponente_{component}")
        self._component = component
        self._attr_translation_key = f"komponente_{component}"

    @property
    def available(self) -> bool:
        return True

    @property
    def native_value(self):
        return self._component

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Der Name des Funktionsblocks - die Karte schreibt ihn über die Puffer."""
        return {"funktionsblock": self.coordinator.funktionsblock(self._component)}


def _datum(wert: date | None) -> str | None:
    return wert.isoformat() if wert else None


def _deutsch(wert: date | None) -> str | None:
    return wert.strftime("%d.%m.%Y") if wert else None


def _gerundet(wert: float | None, stellen: int = 1) -> float | None:
    return round(wert, stellen) if wert is not None else None


PROGNOSE = {
    "pellet_prognose_morgen": {
        "icon": "mdi:crystal-ball",
        "device_class": SensorDeviceClass.WEIGHT,
        "unit": "kg",
        "wert": lambda e: _gerundet(e.morgen_kg),
    },
    "pellet_prognose_treffsicherheit": {
        "icon": "mdi:bullseye-arrow",
        "unit": "%",
        "wert": lambda e: e.treffsicherheit,
    },
    "pellet_prognose_status": {
        "icon": "mdi:school-outline",
        "category": EntityCategory.DIAGNOSTIC,
        "wert": lambda e: e.status,
    },
    "lager_reicht_bis": {
        "icon": "mdi:calendar-end",
        "device_class": SensorDeviceClass.DATE,
        "wert": lambda e: e.reicht_bis,
    },
    "lager_bestellen_bis": {
        "icon": "mdi:cart-arrow-down",
        "device_class": SensorDeviceClass.DATE,
        "wert": lambda e: e.bestellen_bis,
    },
    "lager_reichweite": {
        "icon": "mdi:timer-sand",
        "device_class": SensorDeviceClass.DURATION,
        "unit": UnitOfTime.DAYS,
        "wert": lambda e: e.reichweite_tage,
    },
}
"""Die Sensoren der Verbrauchsprognose; die mit lager_ nur, wenn es ein Lager gibt."""


class ETAPrognoseSensor(CoordinatorEntity[ETAPrognoseKoordinator], SensorEntity):
    """Ein Wert der selbstlernenden Verbrauchsprognose.

    Hängt am Prognose-Koordinator, der stündlich rechnet, gehört aber zum
    selben Gerät wie alle anderen Entitäten der Anlage. Solange das Modell
    noch lernt, bleiben die Werte leer und der Status sagt, worauf es
    wartet.
    """

    _attr_has_entity_name = True

    def __init__(
        self,
        prognose: ETAPrognoseKoordinator,
        haupt: ETADataUpdateCoordinator,
        key: str,
    ) -> None:
        super().__init__(prognose)
        self._key = key
        art = PROGNOSE[key]
        self._wert = art["wert"]
        self._attr_translation_key = key
        self._attr_unique_id = f"eta_static_{haupt.config_entry.entry_id}_{key}"
        self._attr_device_info = haupt.device_info
        self._attr_icon = art["icon"]
        self._attr_device_class = art.get("device_class")
        self._attr_native_unit_of_measurement = art.get("unit")
        self._attr_entity_category = art.get("category")
        if art.get("unit"):
            self._attr_suggested_display_precision = 0

    @property
    def native_value(self):
        if self.coordinator.data is None:
            return "startet" if self._key == "pellet_prognose_status" else None
        return self._wert(self.coordinator.data)

    @property
    def icon(self) -> str:
        if self._key == "pellet_prognose_status":
            bereit = self.coordinator.data is not None and self.coordinator.data.bereit
            return "mdi:check-circle-outline" if bereit else "mdi:school-outline"
        return self._attr_icon

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        e = self.coordinator.data
        if e is None:
            return None
        if self._key == "pellet_prognose_morgen":
            return {
                "temperatur": _gerundet(e.morgen_temperatur),
                "quelle": e.morgen_quelle,
            }
        if self._key == "pellet_prognose_treffsicherheit":
            return {
                "verglichene_tage": e.verglichene_tage,
                "gestern_prognose_kg": _gerundet(e.gestern_prognose),
                "gestern_tatsaechlich_kg": _gerundet(e.gestern_tatsaechlich),
            }
        if self._key == "pellet_prognose_status":
            m = e.modell
            return {
                "lerntage": e.lerntage,
                "heiztage": e.heiztage,
                "grundlast_kg_je_tag": _gerundet(m.grundlast) if m else None,
                "kg_je_grad_kaelter": _gerundet(m.faktor, 2) if m else None,
                "heizgrenze": _gerundet(m.heizgrenze) if m else None,
                "ausreisser": m.ausreisser if m else None,
                "standort_waermer_als_mittel": _gerundet(e.klima_abweichung),
                "wetter": self.coordinator.wetter_id,
                "vorhersage_tage": self.coordinator.vorhersage_tage,
                "puffer_ausgeglichene_tage": self.coordinator.puffer_tage,
            }
        if self._key == "lager_reicht_bis":
            attribute = {
                "datum": _deutsch(e.reicht_bis),
                "fruehestens": _datum(e.reicht_fruehestens),
                "spaetestens": _datum(e.reicht_spaetestens),
            }
            if e.ueber_horizont:
                attribute["hinweis"] = "reicht länger als zwei Jahre"
            return attribute
        if self._key == "lager_bestellen_bis":
            return {
                "datum": _deutsch(e.bestellen_bis),
                "fruehestens": _datum(e.bestellen_fruehestens),
                "spaetestens": _datum(e.bestellen_spaetestens),
            }
        return None
