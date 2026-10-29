"""Stundensatz-Ermittlung je Maschine (Plan Patrick 29.10.2026, „A b a a a“).

- Rechenweg des Plans: 650.000 € / 10 Jahre, 6 % Zins, 60 m² × 8 €, 3 % Instandhaltung, 8.000 € Wartung, 30 kW ×
  0,25 €/kWh, 4 €/h Verschleiß, Bediener 38 €/h × 50 %, 25 % Gemeinkosten, 15 h × 220 Tage × 75 % = 97,60 €/h.
- „von Hand“ (leer, alle bisherigen Maschinen): eingetragener Satz gilt, Schneidgas nur mit 'Gas zusätzlich' = ja.
- „ermittelt“: der gerechnete Satz gilt (auch im Snapshot neuer Angebote), Schneidgas kommt immer dazu.
- Dialog und Knopf in den Maschinen-Stammdaten, Prüfspalte.

Aufruf: python tests/test_stundensatz.py
"""
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER))
from PySide6.QtWidgets import QApplication  # noqa: E402

import beispiel_baugruppe as bsp  # noqa: E402
from rohrlaser import rechnen, stundensatz, stundensatz_dialog  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import StammdatenSeite  # noqa: E402
from rohrlaser.stammdaten import MASCHINEN, pruefen  # noqa: E402

app = QApplication.instance() or QApplication([])


def ok(text):
    print("OK    ", text)


PLAN = dict(anschaffung=650000, nutzungsdauer=10, flaeche=60, instandhaltung=3, wartung=8000, leistung_kw=30,
            verschleiss=4, bediener_anteil=50, schicht_stunden=15)

# ------------------------------------------------------------------ Rechenweg
zeilen, h, satz = stundensatz.posten(PLAN, {})
assert h == 2475, h
assert abs(satz - 97.5997) < 1e-3, satz
w = {t: (j, eh) for t, _, j, eh in zeilen}
assert w["Feste Kosten"][0] == 117760 and abs(w["Feste Kosten"][1] - 47.58) < 0.005
assert w["Strom"][1] == 7.5 and w["Bediener"][1] == 19.0 and abs(w["Gemeinkosten"][1] - 19.52) < 0.005
assert stundensatz.ermitteln({}, {}) is None and stundensatz.ermitteln(PLAN, dict(arbeitstage=0)) is None
assert stundensatz.wirksam(dict(PLAN, stundensatz=150), {}) == 150, "von Hand"
assert stundensatz.wirksam(dict(PLAN, stundensatz=150, satz_art="ermittelt"), {}) == 97.6
assert stundensatz.wirksam(dict(stundensatz=150, satz_art="ermittelt"), {}) == 150, "nicht rechenbar: Feld gilt"
ok("Rechenweg wie im Plan: 117.760 €/Jahr ÷ 2.475 h + Strom 7,50 + Verschleiß 4 + Bediener 19 + 25 % = 97,60 €/h")

# ------------------------------------------------------------------ Gas nicht doppelt
assert not stundensatz.gas_rechnen({}) and not stundensatz.gas_rechnen(dict(gas_zusatz="nein"))
assert stundensatz.gas_rechnen(dict(gas_zusatz="ja")) and stundensatz.gas_rechnen(dict(satz_art="ermittelt"))
tmp = Path(tempfile.mkdtemp())


def angebot(maschine):
    db = Datenbank(tmp / f"a{len(list(tmp.iterdir()))}.db")
    db.einstellung_setzen("gaspreis_n2", 0.9)
    for x in db.zeilen("schneiddaten"):
        if x.get("gas") == "N₂":
            db.aendern("schneiddaten", x["id"], "duese", 2.0)
            db.aendern("schneiddaten", x["id"], "gasdruck", 15.0)
    for x in db.zeilen("maschinen"):
        for n, v in dict(maschine, gas_o2=3.0).items():
            db.aendern("maschinen", x["id"], n, v)
    a = bsp.anlegen(db)
    db.position_neu(a, dict(pos=200, artikel="VA-1", profil_id="RR 42,4x2,0", werkstoff_id="1.4301", laenge=720,
                            stueck=40, schneidweg=290, einstiche=2))
    kopf, pos, k, tab = db.angebot(a), db.positionen(a), db.kontext(), db.tabellen()
    erg = rechnen.optimieren(kopf, pos, k, tab, db.einstellungen())
    db.ergebnis_speichern(a, erg)
    kopf = db.angebot(a)
    e = rechnen.einstellungen_angebot(kopf, db.einstellungen())
    return db, a, rechnen.kalkulation(kopf, pos, kopf["ergebnis"], k, tab, e)


_, _, (z_hand, s_hand) = angebot({})
assert s_hand["schneidgas"] == 0 and s_hand["satz_maschine"] == 150, (s_hand["schneidgas"], s_hand["satz_maschine"])
_, _, (z_zus, s_zus) = angebot(dict(gas_zusatz="ja"))
assert s_zus["schneidgas"] > 0 and s_zus["satz_maschine"] == 150
db_e, a_e, (z_erm, s_erm) = angebot(dict(PLAN, satz_art="ermittelt"))
assert s_erm["satz_maschine"] == 97.6 and s_erm["schneidgas"] > 0
from rohrlaser.rechnen import gas_kosten  # noqa: E402
assert gas_kosten(dict(gas="N₂", duese=2, gasdruck=15), dict(satz_art="ermittelt"), dict(gaspreis_n2=0.9), 60, 60)[0] > 0
assert gas_kosten(dict(gas="N₂", duese=2, gasdruck=15), dict(satz_art="ermittelt"),
                  dict(gaspreis_n2=0.9, gas_rechnen="nein"), 60, 60) == (0.0, None, None), "Schalter für alle aus"
nah = abs(s_erm["schneidgas"] - s_zus["schneidgas"]) < 1e-9
assert nah, "Gas je Teil unabhängig vom Satz"
ok(f"von Hand 150 €/h: kein Gas; mit 'Gas zusätzlich' = ja: {s_zus['schneidgas']:.2f} € Gas; ermittelt 97,60 €/h "
   "plus dasselbe Gas")

# Snapshot: der ermittelte Satz steht in der Zeitbasis des Angebots, spätere Änderungen ändern es nicht
kopf = db_e.angebot(a_e)
assert kopf["zeitbasis"]["maschine"]["stundensatz"] == 97.6 and kopf["zeitbasis"]["maschine"]["satz_art"] == "ermittelt"
for x in db_e.zeilen("maschinen"):
    db_e.aendern("maschinen", x["id"], "anschaffung", 900000)
assert db_e.angebot(a_e)["zeitbasis"]["maschine"]["stundensatz"] == 97.6
assert "Stundensatz Maschine 97,6 statt" in " ".join(rechnen.zeitbasis_abweichungen(
    kopf["zeitbasis"], rechnen.zeitbasis_aus(kopf["maschine"], db_e.kontext(), db_e.tabellen())))
ok("Angebot speichert den ermittelten Satz; neue Anschaffung ändert nur neue Angebote (Abweichung angezeigt)")

# ------------------------------------------------------------------ Prüfspalte, Dialog, Knopf
k = Datenbank(tmp / "p.db").kontext()
assert pruefen(MASCHINEN, dict(maschinen_id="X", satz_art="ermittelt"), k).startswith("WARNUNG: Stundensatz ermittelt")
assert "Stundensatz fehlt" not in pruefen(MASCHINEN, dict(PLAN, maschinen_id="X", satz_art="ermittelt"), k)

d = stundensatz_dialog.StundensatzDialog(None, dict(PLAN, stundensatz=150, maschinen_id="T11"), {})
assert abs(d.satz - 97.6) < 0.01 and d.knopf.isEnabled() and "150,00 €/h" in d.vergleich.text()
d.felder["leistung_kw"].setValue(40)
assert abs(d.satz - (97.5997 + 10 * 0.25 * 1.25)) < 0.01, d.satz
d.felder["anschaffung"].setValue(0)
assert d.satz is not None
leer = stundensatz_dialog.StundensatzDialog(None, dict(maschinen_id="T11"), {})
assert leer.satz is None and not leer.knopf.isEnabled()

db = Datenbank(tmp / "s.db")
meldungen = []
seite = StammdatenSeite(db, MASCHINEN, lambda text, fehler=False: meldungen.append(text))
t11 = next(z for z in seite.modell.daten if z["maschinen_id"] == "T11")
werte = dict({n: PLAN[n] for n in stundensatz.FELDER}, satz_art="ermittelt", stundensatz=97.6)
assert seite.stundensatz_ermitteln(werte, zeile=t11) == werte
neu = next(z for z in db.zeilen("maschinen") if z["maschinen_id"] == "T11")
assert neu["satz_art"] == "ermittelt" and neu["stundensatz"] == 97.6 and neu["anschaffung"] == 650000
assert "97,60 €/h" in meldungen[-1]
ok("Prüfspalte warnt bei 'ermittelt' ohne Werte; Dialog rechnet live, Übernehmen nur wenn rechenbar; Knopf speichert")
print("OK: Stundensatz-Ermittlung")
