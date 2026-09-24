"""Tests für die selbstlernende Verbrauchsprognose und die Reichweite des Lagers."""

from __future__ import annotations

import random
from datetime import date, timedelta
from statistics import median
from types import SimpleNamespace

import pytest

from eta_webservices import prognose as p

HEUTE = date(2026, 1, 20)


def tage_aus_formel(grundlast, faktor, heizgrenze, temperaturen, bis=HEUTE, rauschen=0.0, seed=1):
    zufall = random.Random(seed)
    erster = bis - timedelta(days=len(temperaturen))
    tage = []
    for i, temperatur in enumerate(temperaturen):
        kg = grundlast + faktor * max(0.0, heizgrenze - temperatur)
        kg = max(0.0, kg + zufall.gauss(0, rauschen))
        tage.append(p.Tag(erster + timedelta(days=i), kg, temperatur))
    return tage


def herbst_und_winter(anzahl=120, seed=2):
    zufall = random.Random(seed)
    return [18 - 22 * i / anzahl + zufall.gauss(0, 2.5) for i in range(anzahl)]


def test_lernt_grundlast_faktor_und_heizgrenze():
    tage = tage_aus_formel(4.0, 1.2, 15.0, herbst_und_winter(), rauschen=0.8)
    modell = p.lernen(tage, HEUTE)
    assert modell.grundlast == pytest.approx(4.0, abs=0.8)
    assert modell.faktor == pytest.approx(1.2, abs=0.1)
    assert modell.heizgrenze == pytest.approx(15.0, abs=1.0)
    assert modell.ausreisser == 0
    assert modell.korrektur == pytest.approx(1.0, abs=0.02)


@pytest.mark.parametrize("heizgrenze", [12.0, 17.0])
def test_findet_auch_eine_abweichende_heizgrenze(heizgrenze):
    tage = tage_aus_formel(3.0, 1.0, heizgrenze, herbst_und_winter(200), rauschen=0.3)
    assert p.lernen(tage, HEUTE).heizgrenze == pytest.approx(heizgrenze, abs=0.75)


def test_ohne_warme_tage_gilt_die_typische_heizgrenze():
    """Nur Wintertage: Heizgrenze und Grundlast sind nicht zu trennen."""
    temperaturen = [2 + (i % 9) - 4 for i in range(60)]
    tage = tage_aus_formel(4.0, 1.0, 15.0, temperaturen)
    modell = p.lernen(tage, HEUTE)
    assert modell.heizgrenze == p.TYPISCHE_HEIZGRENZE
    assert modell.verbrauch(0.0) == pytest.approx(19.0, abs=0.5)


def test_ausreisser_verbiegen_die_formel_nicht():
    tage = tage_aus_formel(4.0, 1.2, 15.0, herbst_und_winter(), rauschen=0.5)
    for i in (30, 60, 90):
        tage[i].verbrauch *= 3
    modell = p.lernen(tage, HEUTE)
    assert modell.ausreisser == 3
    assert modell.faktor == pytest.approx(1.2, abs=0.1)
    assert modell.korrektur > 1.0, "verbrannt wurde an den Tagen trotzdem"


def test_juengere_tage_zaehlen_mehr():
    """Neuer Brenner, gedämmtes Dach: das Modell folgt dem aktuellen Haus."""
    temperaturen = herbst_und_winter(400)
    alt = tage_aus_formel(4.0, 2.0, 15.0, temperaturen[:200], bis=HEUTE - timedelta(days=200))
    neu = tage_aus_formel(4.0, 1.0, 15.0, temperaturen[200:])
    modell = p.lernen(alt + neu, HEUTE)
    assert modell.faktor < 1.4


@pytest.mark.parametrize(
    "tage, bereit, text",
    [
        (tage_aus_formel(4, 1, 15, [5.0] * 5), False, "lernt noch (5 von 14 Tagen)"),
        (tage_aus_formel(4, 1, 15, [14.0] * 20), False, "lernt noch (0 von 7 Heiztagen)"),
        (
            tage_aus_formel(4, 1, 15, [5.0 + (i % 3) for i in range(20)]),
            False,
            "lernt noch (braucht mildere und kältere Tage)",
        ),
        (tage_aus_formel(4, 1, 15, [i * 0.5 for i in range(20)]), True, "bereit"),
    ],
)
def test_lernstand_sagt_woran_es_fehlt(tage, bereit, text):
    assert p.lernstand(tage) == (bereit, text)


def test_klima_trifft_die_monatsmitte_und_ist_stetig():
    assert p.klima(date(2026, 7, 15)) == pytest.approx(18.3)
    assert p.klima(date(2026, 1, 15)) == pytest.approx(0.9)
    silvester = p.klima(date(2026, 12, 31))
    neujahr = p.klima(date(2027, 1, 1))
    assert abs(silvester - neujahr) < 0.1
    for tag in range(365):
        d = date(2026, 1, 1) + timedelta(days=tag)
        assert abs(p.klima(d + timedelta(days=1)) - p.klima(d)) < 0.25


def test_standort_wird_mit_der_zeit_uebernommen():
    def tage(anzahl, waermer):
        start = HEUTE - timedelta(days=anzahl)
        return [
            p.Tag(start + timedelta(days=i), 10.0, p.klima(start + timedelta(days=i)) + waermer)
            for i in range(anzahl)
        ]

    nach_einem_monat = p.klima_abweichung(tage(30, -3.0))
    nach_einem_jahr = p.klima_abweichung(tage(365, -3.0))
    assert -2.0 < nach_einem_monat < -1.0
    assert nach_einem_jahr == pytest.approx(-3.0, abs=0.3)
    assert p.klima_abweichung([]) == 0.0


def test_herunterrechnen_findet_bestelltag_und_leeren_tag():
    konstant = p.Modell(10.0, 0.0, 15.0, 30, 30, 0.0)
    bestellen, leer = p.herunterrechnen(konstant, 100, 50, 0.0, HEUTE, {}, 0.0)
    assert bestellen == HEUTE + timedelta(days=4)
    assert leer == HEUTE + timedelta(days=9)


def test_heute_zaehlt_nur_was_noch_nicht_verbrannt_ist():
    konstant = p.Modell(10.0, 0.0, 15.0, 30, 30, 0.0)
    _, frisch = p.herunterrechnen(konstant, 25, None, 0.0, HEUTE, {}, 0.0)
    _, spaet = p.herunterrechnen(konstant, 25, None, 8.0, HEUTE, {}, 0.0)
    assert frisch == HEUTE + timedelta(days=2)
    assert spaet == HEUTE + timedelta(days=3)


def test_unter_der_warngrenze_heisst_heute_bestellen():
    konstant = p.Modell(10.0, 0.0, 15.0, 30, 30, 0.0)
    bestellen, _ = p.herunterrechnen(konstant, 40, 50, 0.0, HEUTE, {}, 0.0)
    assert bestellen == HEUTE
    assert p.herunterrechnen(konstant, 0, 50, 0.0, HEUTE, {}, 0.0) == (HEUTE, HEUTE)


def test_vorhersage_geht_dem_klimamittel_vor():
    modell = p.Modell(2.0, 1.0, 15.0, 30, 30, 0.0)
    kalt = {HEUTE + timedelta(days=i): -10.0 for i in range(7)}
    _, mit_frost = p.herunterrechnen(modell, 300, None, 0.0, HEUTE, kalt, 0.0)
    _, ohne = p.herunterrechnen(modell, 300, None, 0.0, HEUTE, {}, 0.0)
    assert mit_frost < ohne


def test_reicht_ueber_den_horizont():
    sparsam = p.Modell(0.1, 0.0, 15.0, 30, 30, 0.0)
    assert p.herunterrechnen(sparsam, 10000, 50, 0.0, HEUTE, {}, 0.0) == (None, None)


def test_gegenrechnen_mit_perfekten_tagen():
    tage = tage_aus_formel(4.0, 1.2, 15.0, herbst_und_winter())
    treffsicherheit, verglichen, prognose, tatsaechlich = p.gegenrechnen(tage)
    assert treffsicherheit >= 97
    assert verglichen == p.VERGLEICHSTAGE
    assert prognose == pytest.approx(tatsaechlich, rel=0.05)


def test_gegenrechnen_ohne_genug_tage():
    assert p.gegenrechnen(tage_aus_formel(4, 1, 15, [5.0] * 10)) == (None, 0, None, None)


def test_berechnen_solange_es_noch_lernt():
    ergebnis = p.berechnen(tage_aus_formel(4, 1, 15, [5.0] * 10), HEUTE, {}, 2000, 500, 0.0)
    assert not ergebnis.bereit
    assert ergebnis.status == "lernt noch (10 von 14 Tagen)"
    assert ergebnis.morgen_kg is None and ergebnis.reicht_bis is None


def test_berechnen_liefert_alles_und_eine_stimmige_spanne():
    tage = tage_aus_formel(4.0, 1.2, 15.0, herbst_und_winter(), rauschen=0.5)
    vorhersage = {HEUTE + timedelta(days=1): -3.0}
    ergebnis = p.berechnen(tage, HEUTE, vorhersage, 3000, 800, 5.0)
    assert ergebnis.bereit and ergebnis.status == "bereit"
    assert ergebnis.morgen_temperatur == -3.0
    assert ergebnis.morgen_quelle == "Wettervorhersage"
    assert ergebnis.morgen_kg == pytest.approx(4 + 1.2 * 18, rel=0.1)
    assert ergebnis.reicht_fruehestens <= ergebnis.reicht_bis <= ergebnis.reicht_spaetestens
    assert ergebnis.bestellen_fruehestens <= ergebnis.bestellen_bis <= ergebnis.bestellen_spaetestens
    assert ergebnis.bestellen_bis < ergebnis.reicht_bis
    assert ergebnis.reichweite_tage == (ergebnis.reicht_bis - HEUTE).days
    assert ergebnis.treffsicherheit is not None


def test_berechnen_ohne_lager():
    tage = tage_aus_formel(4.0, 1.2, 15.0, herbst_und_winter())
    ergebnis = p.berechnen(tage, HEUTE, {}, None, None, 0.0)
    assert ergebnis.morgen_kg is not None
    assert ergebnis.morgen_quelle == "Klimamittel"
    assert ergebnis.reicht_bis is None and not ergebnis.ueber_horizont


def _lokal(text):
    return date.fromisoformat(text[:10]) if text else None


def test_tagesvorhersage_nimmt_die_mitte_von_hoch_und_tief():
    eintraege = [
        {"datetime": "2026-01-21T00:00:00+01:00", "temperature": 4.0, "templow": -2.0},
        {"datetime": "2026-01-22T00:00:00+01:00", "temperature": 6.0},
        {"datetime": "2026-01-23T00:00:00+01:00", "temperature": None},
        {"datetime": None, "temperature": 3.0},
    ]
    tage = p.tagesmittel_aus_vorhersage(eintraege, "daily", _lokal)
    assert tage == {date(2026, 1, 21): 1.0, date(2026, 1, 22): 2.0}


def test_vorhersage_in_fahrenheit():
    eintraege = [{"datetime": "2026-01-21T00:00:00", "temperature": 50.0, "templow": 32.0}]
    tage = p.tagesmittel_aus_vorhersage(eintraege, "daily", _lokal, fahrenheit=True)
    assert tage[date(2026, 1, 21)] == pytest.approx(5.0)


def test_stundenvorhersage_braucht_einen_halben_tag():
    eintraege = [
        {"datetime": f"2026-01-21T{stunde:02d}:00:00", "temperature": float(stunde)}
        for stunde in range(24)
    ] + [
        {"datetime": f"2026-01-22T{stunde:02d}:00:00", "temperature": 1.0}
        for stunde in range(6)
    ]
    tage = p.tagesmittel_aus_vorhersage(eintraege, "hourly", _lokal)
    assert tage == {date(2026, 1, 21): pytest.approx(11.5)}


def test_halbtagesvorhersage_mittelt_tag_und_nacht():
    eintraege = [
        {"datetime": "2026-01-21T06:00:00", "temperature": 6.0, "templow": 2.0},
        {"datetime": "2026-01-21T18:00:00", "temperature": 0.0},
    ]
    tage = p.tagesmittel_aus_vorhersage(eintraege, "twice_daily", _lokal)
    assert tage[date(2026, 1, 21)] == pytest.approx((6 + 2 + 0) / 3)


def test_stunden_werden_zu_vollstaendigen_tagen():
    def stunden(tag, anzahl, wert):
        return [(tag * 24 + h, wert) for h in range(anzahl)]

    def datum(zeit):
        return HEUTE - timedelta(days=5) + timedelta(days=int(zeit // 24))

    verbrauch = stunden(0, 24, 0.5) + stunden(1, 12, 0.5) + stunden(2, 24, 0.5) + stunden(5, 3, 1.0)
    verbrauch.append((2 * 24 + 3, None))
    temperatur = stunden(0, 24, 3.0) + stunden(1, 24, 3.0) + stunden(2, 22, -1.0) + stunden(5, 3, 0.0)
    tage = p.tage_aus_stunden(verbrauch, temperatur, datum, HEUTE)
    assert [(t.datum, t.verbrauch, t.temperatur) for t in tage] == [
        (HEUTE - timedelta(days=5), 12.0, 3.0),
        (HEUTE - timedelta(days=3), 12.0, -1.0),
    ]


def _simuliertes_haus(seed):
    """Ein Haus mit eigenem Standort, launischen Wintern und Ausreißern."""
    zufall = random.Random(seed)
    wahr = p.Modell(
        zufall.uniform(2, 6), zufall.uniform(0.6, 1.8), [13.0, 15.5, 17.0][seed % 3], 0, 0, 0
    )
    ort = zufall.uniform(-3, 2)
    start = date(2025, 9, 1)
    tage, winter = [], 0.0
    for i in range(600):
        d = start + timedelta(days=i)
        if i % 30 == 0:
            winter = zufall.gauss(0, 1.5)
        temperatur = p.klima(d) + ort + winter + zufall.gauss(0, 3.0)
        kg = max(0.0, wahr.verbrauch(temperatur) + zufall.gauss(0, 0.15 * wahr.verbrauch(temperatur) + 0.5))
        if zufall.random() < 0.03:
            kg *= zufall.choice([0.1, 2.5])
        tage.append(p.Tag(d, kg, temperatur))
    return tage, start, zufall


def test_simulierte_winter_treffen_den_leeren_tag():
    """Vierzig Häuser: gelernt wird bis zu einem Stichtag, dann wird der
    Vorrat mit dem tatsächlichen Verbrauch heruntergerechnet und mit der
    Schätzung verglichen - ohne Wettervorhersage, also nur mit dem, was
    das Modell über Haus und Standort gelernt hat.
    """
    fehler, in_spanne, nah = [], 0, []
    for seed in range(40):
        tage, start, zufall = _simuliertes_haus(seed)
        gelernt = zufall.choice([60, 90, 120, 200])
        heute = start + timedelta(days=gelernt)
        vorrat = zufall.uniform(1500, 4000)
        ergebnis = p.berechnen(
            tage[:gelernt], heute, {}, vorrat, None, 0.0, (None, 0, None, None)
        )
        rest, wirklich = vorrat, None
        for tag in tage[gelernt:]:
            rest -= tag.verbrauch
            if rest <= 0:
                wirklich = tag.datum
                break
        if wirklich is None or ergebnis.reicht_bis is None:
            continue
        fehler.append((ergebnis.reicht_bis - wirklich).days)
        if ergebnis.reicht_fruehestens <= wirklich <= ergebnis.reicht_spaetestens:
            in_spanne += 1
        if (wirklich - heute).days <= 60:
            nah.append(abs(fehler[-1]))
    assert len(fehler) >= 30
    assert abs(median(fehler)) <= 5, "keine Schlagseite zu früh oder zu spät"
    assert median(abs(f) for f in fehler) <= 14
    assert in_spanne / len(fehler) >= 0.7, "die Spanne umfasst meistens den echten Tag"
    assert not nah or median(nah) <= 4, "kurz vor leer auf wenige Tage genau"


class _Zustaende:
    def __init__(self, wetter):
        self._wetter = wetter

    def get(self, entity_id):
        return object() if entity_id in self._wetter else None

    def async_entity_ids(self, domain):
        return [e for e in self._wetter if e.startswith(f"{domain}.")]


class _Dienste:
    def __init__(self, antworten):
        self.antworten = antworten
        self.aufrufe = []

    async def async_call(self, domain, service, daten, blocking, return_response):
        from homeassistant.exceptions import HomeAssistantError

        self.aufrufe.append(daten["type"])
        antwort = self.antworten.get(daten["type"])
        if antwort is None:
            raise HomeAssistantError("nicht unterstützt")
        return {daten["entity_id"]: {"forecast": antwort}}


def _mit_wetter(hass, wetter=("weather.zuhause",), antworten=None):
    hass.states = _Zustaende(list(wetter))
    hass.services = _Dienste(antworten or {})
    hass.config.units = SimpleNamespace(temperature_unit="°C")
    return hass


async def test_vorhersage_weicht_auf_stundenwerte_aus(hass):
    from eta_webservices.prognose_koordinator import async_vorhersage

    stunden = [
        {"datetime": f"2026-01-21T{h:02d}:00:00+00:00", "temperature": -4.0} for h in range(24)
    ]
    _mit_wetter(hass, antworten={"hourly": stunden})
    tage = await async_vorhersage(hass, "weather.zuhause")
    assert hass.services.aufrufe == ["daily", "twice_daily", "hourly"]
    assert list(tage.values()) and all(v == -4.0 for v in tage.values())


async def test_ohne_wetter_keine_vorhersage(hass):
    from eta_webservices.prognose_koordinator import async_vorhersage

    _mit_wetter(hass, wetter=())
    assert await async_vorhersage(hass, "weather.gibt_es_nicht") == {}
    assert await async_vorhersage(hass, None) == {}
    assert hass.services.aufrufe == []


def test_nur_eine_wetter_entitaet_wird_von_selbst_genommen(hass):
    from eta_webservices.prognose_koordinator import einzige_wetter_entitaet

    assert einzige_wetter_entitaet(_mit_wetter(hass, ("weather.zuhause",))) == "weather.zuhause"
    assert einzige_wetter_entitaet(_mit_wetter(hass, ("weather.a", "weather.b"))) is None
    assert einzige_wetter_entitaet(_mit_wetter(hass, ())) is None


def _stundenwerte(tage, zeitzone):
    """Stundenwerte, wie sie die Langzeitstatistik liefert."""
    from datetime import datetime

    verbrauch, temperatur = [], []
    for tag in tage:
        mitternacht = datetime(tag.datum.year, tag.datum.month, tag.datum.day, tzinfo=zeitzone)
        for stunde in range(24):
            zeit = (mitternacht + timedelta(hours=stunde)).timestamp()
            verbrauch.append((zeit, tag.verbrauch / 24))
            temperatur.append((zeit, tag.temperatur))
    return verbrauch, temperatur


@pytest.fixture
def prognose_koordinator(hass, entry, monkeypatch):
    from homeassistant.util import dt as dt_util

    from eta_webservices import prognose_koordinator as modul

    zone = dt_util.get_default_time_zone()
    jetzt = SimpleNamespace(wert=dt_util.as_local(dt_util.utcnow()).replace(
        year=2026, month=1, day=20, hour=14
    ))
    monkeypatch.setattr(modul.dt_util, "now", lambda: jetzt.wert)
    tage = tage_aus_formel(4.0, 1.2, 15.0, herbst_und_winter(), bis=HEUTE)
    verbrauch, temperatur = _stundenwerte(tage, zone)
    heute_morgen = _stundenwerte([p.Tag(HEUTE, 24 * 0.5, 0.0)], zone)
    abrufe = []

    async def stundenwerte(_hass, verbrauch_id, temperatur_id, heute, puffer_ids=()):
        abrufe.append((verbrauch_id, temperatur_id, heute))
        return verbrauch + heute_morgen[0][:10], temperatur + heute_morgen[1][:10], []

    monkeypatch.setattr(modul, "async_stundenwerte", stundenwerte)
    _mit_wetter(
        hass,
        antworten={
            "daily": [
                {"datetime": "2026-01-21T12:00:00+00:00", "temperature": 1.0, "templow": -5.0}
            ]
        },
    )
    haupt = SimpleNamespace(data={"lager_vorrat": _wert(3000), "lager_warngrenze": _wert(500)})
    koordinator = modul.ETAPrognoseKoordinator(
        hass, entry, haupt, None, lambda: ("sensor.verbrauch", "sensor.aussen")
    )
    koordinator.abrufe = abrufe
    return koordinator


def _wert(zahl):
    from eta_webservices.api import ETAValue

    return ETAValue(zahl, str(zahl), "kg", False, 0)


async def test_koordinator_rechnet_aus_statistik_und_vorhersage(prognose_koordinator):
    ergebnis = await prognose_koordinator._async_update_data()
    assert ergebnis.bereit
    assert ergebnis.lerntage == 120
    assert prognose_koordinator.wetter_id == "weather.zuhause"
    assert prognose_koordinator.vorhersage_tage == 1
    assert ergebnis.morgen_temperatur == -2.0
    assert ergebnis.morgen_quelle == "Wettervorhersage"
    assert ergebnis.reicht_bis > HEUTE
    assert ergebnis.bestellen_bis < ergebnis.reicht_bis
    assert prognose_koordinator.abrufe == [("sensor.verbrauch", "sensor.aussen", HEUTE)]


async def test_koordinator_rechnet_die_gegenprobe_nur_einmal_am_tag(
    prognose_koordinator, monkeypatch
):
    zaehler = []
    original = p.gegenrechnen
    monkeypatch.setattr(p, "gegenrechnen", lambda tage: zaehler.append(1) or original(tage))
    erstes = await prognose_koordinator._async_update_data()
    zweites = await prognose_koordinator._async_update_data()
    assert len(zaehler) == 1
    assert erstes.treffsicherheit == zweites.treffsicherheit


async def test_leeres_wetterfeld_heisst_keine_vorhersage(prognose_koordinator):
    prognose_koordinator.wetter_wahl = ""
    ergebnis = await prognose_koordinator._async_update_data()
    assert prognose_koordinator.wetter_id is None
    assert ergebnis.morgen_quelle == "Klimamittel"


async def test_ohne_statistik_ids_wartet_die_prognose(prognose_koordinator):
    prognose_koordinator._statistik_ids = lambda: (None, "sensor.aussen")
    ergebnis = await prognose_koordinator._async_update_data()
    assert not ergebnis.bereit
    assert ergebnis.status == "wartet auf Gesamtverbrauch und Außentemperatur"


async def test_unlesbare_statistik_gibt_einen_status(prognose_koordinator, monkeypatch):
    from homeassistant.exceptions import HomeAssistantError

    from eta_webservices import prognose_koordinator as modul

    async def kaputt(*_args):
        raise HomeAssistantError("Recorder nicht bereit")

    monkeypatch.setattr(modul, "async_stundenwerte", kaputt)
    ergebnis = await prognose_koordinator._async_update_data()
    assert ergebnis.status == "Verlauf nicht lesbar"


async def _mit_prognose(hass, entry, monkeypatch, komponenten=None):
    import eta_webservices
    from eta_webservices import sensor as sensor_platform

    from .conftest import entity_name

    hass.config.components = {"recorder"}
    gestartet = []
    monkeypatch.setattr(
        eta_webservices, "async_at_started", lambda _hass, ziel: gestartet.append(ziel) or (lambda: None)
    )
    if komponenten:
        entry.data["components"] = komponenten
    assert await eta_webservices.async_setup_entry(hass, entry)
    entitaeten: list = []
    await sensor_platform.async_setup_entry(hass, entry, entitaeten.extend)
    return entry.runtime_data, {entity_name(e): e for e in entitaeten}, gestartet


async def test_ohne_recorder_keine_prognose(hass, entry):
    from .test_sensors import setup_integration

    coordinator, by_name = await setup_integration(hass, entry)
    assert coordinator.prognose is None
    assert "Pelletprognose morgen" not in by_name


async def test_prognose_sensoren_entstehen_mit_recorder(hass, entry, monkeypatch):
    coordinator, by_name, gestartet = await _mit_prognose(hass, entry, monkeypatch)
    assert coordinator.prognose is not None
    assert len(gestartet) == 1, "gerechnet wird erst nach dem Start"
    assert {"Pelletprognose morgen", "Pelletprognose Treffsicherheit", "Pelletprognose Status"} <= set(by_name)
    assert "Lager reicht bis" not in by_name, "ohne Lager keine Reichweite"
    status = by_name["Pelletprognose Status"]
    assert status.native_value == "startet"
    assert status.entity_category == "diagnostic"


async def test_prognose_mit_lager(hass, entry, monkeypatch):
    coordinator, by_name, _ = await _mit_prognose(
        hass, entry, monkeypatch, ["kessel", "lager"]
    )
    reicht = by_name["Lager reicht bis"]
    reichweite = by_name["Lager Reichweite"]
    bestellen = by_name["Lager bestellen bis"]
    assert reicht.device_class == "date"
    assert reichweite.native_unit_of_measurement == "d"
    assert reicht.unique_id == f"eta_static_{entry.entry_id}_lager_reicht_bis"
    assert reicht.device_info == coordinator.device_info

    ergebnis = p.Ergebnis(
        status="bereit",
        bereit=True,
        modell=p.Modell(4.0, 1.234, 15.0, 100, 80, 1.5, 2, 1.03),
        lerntage=100,
        heiztage=80,
        morgen_kg=18.44,
        morgen_temperatur=-2.04,
        morgen_quelle="Wettervorhersage",
        reicht_bis=date(2026, 3, 1),
        reicht_fruehestens=date(2026, 2, 20),
        reicht_spaetestens=date(2026, 3, 12),
        bestellen_bis=date(2026, 2, 10),
        reichweite_tage=40,
        treffsicherheit=91,
        verglichene_tage=14,
        gestern_prognose=17.26,
        gestern_tatsaechlich=18.0,
        klima_abweichung=-0.84,
    )
    coordinator.prognose.data = ergebnis
    assert reicht.native_value == date(2026, 3, 1)
    assert reicht.extra_state_attributes == {
        "datum": "01.03.2026",
        "fruehestens": "2026-02-20",
        "spaetestens": "2026-03-12",
    }
    assert bestellen.native_value == date(2026, 2, 10)
    assert reichweite.native_value == 40
    assert by_name["Pelletprognose morgen"].native_value == 18.4
    assert by_name["Pelletprognose morgen"].extra_state_attributes == {
        "temperatur": -2.0,
        "quelle": "Wettervorhersage",
    }
    assert by_name["Pelletprognose Treffsicherheit"].native_value == 91
    status = by_name["Pelletprognose Status"]
    assert status.native_value == "bereit"
    assert status.icon == "mdi:check-circle-outline"
    assert status.extra_state_attributes["kg_je_grad_kaelter"] == 1.23
    assert status.extra_state_attributes["standort_waermer_als_mittel"] == -0.8

    ergebnis.reicht_bis = None
    ergebnis.reichweite_tage = None
    ergebnis.ueber_horizont = True
    assert reicht.native_value is None
    assert reicht.extra_state_attributes["hinweis"] == "reicht länger als zwei Jahre"


async def test_prognose_steht_in_der_diagnose(hass, entry, monkeypatch):
    import json

    from eta_webservices.diagnostics import async_get_config_entry_diagnostics

    coordinator, _, _ = await _mit_prognose(hass, entry, monkeypatch)
    diagnose = await async_get_config_entry_diagnostics(hass, entry)
    assert diagnose["prognose"] == {
        "aktiv": True,
        "wetter_gewaehlt": "automatisch",
        "wetter_genutzt": None,
        "vorhersage_tage": 0,
        "puffer_ausgeglichene_tage": 0,
        "status": "noch nicht gerechnet",
    }
    tage = tage_aus_formel(4.0, 1.2, 15.0, herbst_und_winter())
    coordinator.prognose.data = p.berechnen(tage, HEUTE, {}, 3000, 500, 0.0)
    diagnose = await async_get_config_entry_diagnostics(hass, entry)
    assert diagnose["prognose"]["status"] == "bereit"
    assert len(diagnose["prognose"]["letzte_tage"]) == p.VERGLEICHSTAGE
    json.dumps(diagnose)


async def test_diagnose_ohne_prognose(hass, entry):
    from eta_webservices.diagnostics import async_get_config_entry_diagnostics

    from .test_sensors import setup_integration

    await setup_integration(hass, entry)
    diagnose = await async_get_config_entry_diagnostics(hass, entry)
    assert diagnose["prognose"] == {"aktiv": False}


async def test_statistik_ids_kommen_aus_dem_register(hass, entry, monkeypatch):
    from eta_webservices import _statistik_ids

    hass.entity_registry.anlegen(
        "sensor.mein_verbrauch", f"eta_static_{entry.entry_id}_pellet_gesamtverbrauch", entry.entry_id
    )
    assert _statistik_ids(hass, entry) == ("sensor.mein_verbrauch", None)


def test_prognose_entitaeten_werden_mit_ihrer_komponente_aufgeraeumt():
    from eta_webservices import entitaet_vorgesehen

    assert entitaet_vorgesehen("pellet_prognose_morgen", ["kessel"], False, False)
    assert entitaet_vorgesehen("lager_reicht_bis", ["kessel"], False, False) is False
    assert entitaet_vorgesehen("lager_reichweite", ["kessel", "lager"], False, False)


def test_puffertemperaturen_nur_wenn_alle_fuehler_da_sind():
    daten = {"puffer_fuehler_1": _wert(70), "puffer_fuehler_2": _wert(50)}
    assert p.puffer_temperaturen(daten, ["puffer_fuehler_1", "puffer_fuehler_2"]) == [70.0, 50.0]
    assert p.puffer_temperaturen(daten, ["puffer_fuehler_1", "puffer_fuehler_3"]) == []
    assert p.puffer_temperaturen(None, ["puffer_fuehler_1"]) == []


def test_energieinhalt_zaehlt_nur_waerme_ueber_dem_bezug():
    assert p.puffer_energieinhalt([70.0, 50.0, 30.0, 20.0], 1000) == pytest.approx(
        (40 + 20 + 0 + 0) / 4 * 1.163
    )
    assert p.puffer_energieinhalt([], 1000) is None
    assert p.puffer_energieinhalt([60.0], None) is None


def test_tagesende_ist_die_letzte_stunde_mit_allen_fuehlern():
    def stunde(zeit):
        return HEUTE + timedelta(days=int(zeit // 24)), int(zeit % 24)

    oben = [(22, 70.0), (23, 68.0), (47, 50.0)]
    unten = [(22, 40.0), (23, 38.0)]
    assert p.puffer_tagesenden([oben, unten], stunde) == {HEUTE: 53.0}


def test_puffer_ausgleich_schiebt_pellets_zum_richtigen_tag():
    tage = [
        p.Tag(HEUTE - timedelta(days=2), 20.0, 0.0),
        p.Tag(HEUTE - timedelta(days=1), 30.0, 0.0),
        p.Tag(HEUTE, 10.0, 0.0),
    ]
    enden = {
        HEUTE - timedelta(days=2): 50.0,
        HEUTE - timedelta(days=1): 60.0,
        HEUTE: 50.0,
    }
    kwh_je_kelvin, kwh_je_kg = 1.0, 1.0
    ausgeglichen, anzahl = p.puffer_ausgleichen(tage, enden, kwh_je_kelvin, kwh_je_kg)
    assert anzahl == 2, "der erste Tag hat kein Tagesende davor"
    assert [t.verbrauch for t in ausgeglichen] == [20.0, 20.0, 20.0]


def _puffer_haus(seed, volumen, kwh_je_kg):
    """Ein Haus mit Puffer, der um Mitternacht mal fast leer, mal voll ist."""
    zufall = random.Random(seed)
    wahr = p.Modell(zufall.uniform(2, 6), zufall.uniform(0.6, 1.8), 15.0, 0, 0, 0)
    kwh_je_kelvin = volumen * p.WASSER_KWH_JE_LITER_KELVIN
    start = date(2025, 10, 1)
    tage, enden, vorher = [], {start - timedelta(days=1): 45.0}, 45.0
    for i in range(200):
        d = start + timedelta(days=i)
        temperatur = p.klima(d) + zufall.gauss(0, 3.0)
        bedarf = max(0.0, wahr.verbrauch(temperatur) + zufall.gauss(0, 0.08 * wahr.verbrauch(temperatur) + 0.3))
        ende = zufall.uniform(35, 70)
        tage.append(p.Tag(d, max(0.0, bedarf + (ende - vorher) * kwh_je_kelvin / kwh_je_kg), temperatur))
        enden[d] = vorher = ende
    return tage, enden, kwh_je_kelvin


def test_simulierter_puffer_macht_die_tage_treffsicherer():
    kwh_je_kg = 4.8 * p.KESSEL_WIRKUNGSGRAD
    ohne, mit = [], []
    for seed in range(20):
        tage, enden, kwh_je_kelvin = _puffer_haus(seed, 1000, kwh_je_kg)
        ohne.append(p.gegenrechnen(tage, 30)[0])
        ausgeglichen, _ = p.puffer_ausgleichen(tage, enden, kwh_je_kelvin, kwh_je_kg)
        mit.append(p.gegenrechnen(ausgeglichen, 30)[0])
    assert median(mit) >= median(ohne) + 10
    assert median(mit) >= 88


async def test_koordinator_gleicht_den_puffer_aus(prognose_koordinator, monkeypatch):
    from homeassistant.util import dt as dt_util

    from eta_webservices import prognose_koordinator as modul

    zone = dt_util.get_default_time_zone()
    haupt = prognose_koordinator.haupt
    haupt.pellet_kwh_per_kg = 4.8
    haupt.data["puffer_fuehler_1"] = _wert(60)
    haupt.data["puffer_fuehler_2"] = _wert(40)
    prognose_koordinator._puffer_quellen = lambda: [
        {
            "ids": ["sensor.oben", "sensor.unten"],
            "schluessel": ["puffer_fuehler_1", "puffer_fuehler_2"],
            "volumen": 1000,
        }
    ]

    ohne_puffer = await prognose_koordinator._async_update_data()
    original = modul.async_stundenwerte

    async def mit_puffer(_hass, verbrauch_id, temperatur_id, heute, puffer_ids=()):
        verbrauch, temperatur, _ = await original(_hass, verbrauch_id, temperatur_id, heute)
        assert list(puffer_ids) == ["sensor.oben", "sensor.unten"]
        from datetime import datetime

        reihe = []
        for i in range(1, 30):
            tag = HEUTE - timedelta(days=i)
            zeit = datetime(tag.year, tag.month, tag.day, 23, tzinfo=zone).timestamp()
            reihe.append((zeit, 40.0 if i % 2 else 50.0))
        return verbrauch, temperatur, [reihe, reihe]

    monkeypatch.setattr(modul, "async_stundenwerte", mit_puffer)
    prognose_koordinator._gegenrechnung_bis = None
    ergebnis = await prognose_koordinator._async_update_data()
    assert prognose_koordinator.puffer_tage >= 20
    assert ergebnis.bereit
    assert ergebnis.lerntage == ohne_puffer.lerntage
    assert ergebnis.modell.faktor != ohne_puffer.modell.faktor


async def test_ohne_volumen_kein_ausgleich(prognose_koordinator):
    prognose_koordinator.haupt.pellet_kwh_per_kg = 4.8
    prognose_koordinator._puffer_quellen = lambda: [
        {"ids": ["sensor.oben"], "schluessel": ["puffer_fuehler_1"], "volumen": None}
    ]
    await prognose_koordinator._async_update_data()
    assert prognose_koordinator.puffer_tage == 0


def test_mehrere_puffer_zaehlen_zusammen():
    """Die Wärme aller Puffer addiert sich; es zählen nur Tage, die jeder kennt."""
    from eta_webservices import prognose as p

    erster = ({date(2026, 1, 1): 50.0, date(2026, 1, 2): 60.0}, 1.0)
    zweiter = ({date(2026, 1, 2): 40.0, date(2026, 1, 3): 45.0}, 0.5)
    assert p.puffer_energie_enden([erster, zweiter]) == {date(2026, 1, 2): 80.0}
    assert p.puffer_energie_enden([erster]) == {date(2026, 1, 1): 50.0, date(2026, 1, 2): 60.0}
    assert p.puffer_energie_enden([]) == {}


async def test_puffer_quellen_mit_zwei_puffern(hass, entry, menu_xml):
    """Je Puffer mit effektivem Volumen eine Quelle, mit den Fühlern oben zuerst."""
    from eta_webservices import _puffer_quellen

    from .test_puffer import ZWEITER_PUFFER, mit_fub
    from .test_sensors import setup_integration

    hass.session.menu = mit_fub(menu_xml, ZWEITER_PUFFER)
    entry.data["components"] = ["kessel", "puffer", "puffer2"]
    coordinator, _ = await setup_integration(hass, entry)
    for key in coordinator.sensor_defs:
        if "_fuehler_" in key:
            hass.entity_registry.anlegen(
                f"sensor.{key}", f"eta_static_{entry.entry_id}_{key}", entry.entry_id
            )
    quellen = _puffer_quellen(hass, entry, coordinator)
    assert [q["schluessel"][0] for q in quellen] == ["puffer_fuehler_1", "puffer2_fuehler_1"]
    assert [len(q["ids"]) for q in quellen] == [5, 3]
    assert [q["volumen"] for q in quellen] == [825, 825]


async def test_prognose_laesst_sich_abwaehlen(hass, entry, monkeypatch):
    entry.data["prognose"] = False
    coordinator, by_name, gestartet = await _mit_prognose(
        hass, entry, monkeypatch, ["kessel", "lager"]
    )
    assert coordinator.prognose is None
    assert gestartet == []
    assert not [n for n in by_name if "prognose" in n.lower() or n.startswith("Lager reicht")]


def test_abgewaehlte_prognose_wird_aufgeraeumt():
    from eta_webservices import entitaet_vorgesehen

    for key in ("pellet_prognose_morgen", "lager_reicht_bis", "lager_reichweite"):
        assert entitaet_vorgesehen(key, ["kessel", "lager"], False, False, mit_prognose=False) is False
        assert entitaet_vorgesehen(key, ["kessel", "lager"], False, False, mit_prognose=True)
