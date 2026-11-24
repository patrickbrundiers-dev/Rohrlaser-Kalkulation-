"""Optimierungsplan 04.11.2026, Paket 3 (Kalkulation absichern, Betrieb):
- C1 Ampel nach dem STEP-Import: je Teil sicher / prüfen / nicht übernehmbar mit Grund, Zusammenfassung und Filter,
- D2 Laserzeit Soll/Ist je Maschine auf der Startseite (erst ab 3 nachkalkulierten Aufträgen),
- E1 „N Fehler seit gestern“ auf der Startseite mit Knopf Support-Paket,
- D1 Referenzangebote als Prüfrechnung (referenzangebote.py).
Aufruf: python tests/test_paket3.py
"""
import datetime
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm" / "step_messung"))
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import step_messen  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402

app = QApplication.instance() or QApplication([])

from rohrlaser import nachkalkulation, protokoll, step, stil  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402

tmp = Path(tempfile.mkdtemp())
stil.anwenden(app, "hell")


def ok(text):
    print("OK    ", text)


# ------------------------------------------------------------------ C1 Ampel (Logik)
assert step.ampel({"profilform": "RR"}) == ("gruen", ["Art, Profil und Konturen sicher erkannt"])
st, gr = step.ampel({"profilform": "RR", "sicherheit": "wandstaerke=unsicher;laenge=sicher"})
assert st == "gelb" and gr == ["Messung unsicher: Wandstärke"], (st, gr)
assert step.ampel({"profilform": "RR"}, profil_fehlt=True) == ("gelb", ["Profil fehlt in den Stammdaten"])
assert step.ampel({"profilform": "RR", "_normteil": "Schraube"})[0] == "gelb"
assert step.ampel({"profilform": "QR", "_form_gemessen": "RE"})[0] == "gelb"
assert step.ampel({"profilform": "RR", "pruefstatus": "prüfen"})[0] == "gelb"
assert step.ampel({"fehler": "kein Rohrteil erkannt"}) == ("rot", ["kein Rohrteil erkannt"])
assert step.ampel({"profilform": "RR", "pruefstatus": "nicht messbar"})[0] == "rot"
ok("C1 Ampel: grün sicher, gelb mit Grund (unsicher, Profil fehlt, Normteil, Art von Hand, prüfen), rot bei Fehler")

# ------------------------------------------------------------------ C1 Ampel im Prüfdialog
from rohrlaser.step_dialog import StepPruefDialog  # noqa: E402

db = Datenbank(tmp / "rohrlaser.db")
k = db.kontext()
netze = Path(tempfile.mkdtemp(dir=tmp))
mw = [dict(zip(step_messen.SPALTEN, z)) for z in step_messen.zeilen(HIER / "step_anbau" / "A01_RE60x40x3_ohne_Anbau.step",
                                                                     netze)]
gut = dict(mw[0], datei="gut.step", artikel="GUT", sicherheit="", pruefstatus="plausibel", anbauteile="")
unsicher = dict(gut, datei="unsicher.step", artikel="UNSICHER", sicherheit="wandstaerke=unsicher")
kaputt = dict(gut, datei="kaputt.step", artikel="KAPUTT", fehler="kein Rohrteil erkannt", profilform="")
d = StepPruefDialog(None, [gut, unsicher, kaputt], k, "S235-10219", 1)
amp = {z.it.text(0): z.ampel for z in d.zeilen}
assert amp == {"GUT": "gruen", "UNSICHER": "gelb"}, amp
assert d.ampel_zahlen() == (1, 1, 1), d.ampel_zahlen()
z_gelb = next(z for z in d.zeilen if z.ampel == "gelb")
assert not z_gelb.it.icon(d.SP_HINWEIS).isNull()
assert z_gelb.it.toolTip(d.SP_HINWEIS).startswith("Erkennung: prüfen – Messung unsicher: Wandstärke"), \
    z_gelb.it.toolTip(d.SP_HINWEIS)
info = d.ampel_info.text()
assert "1 sicher erkannt" in info and "1 prüfen" in info and "1 nicht übernehmbar" in info, info
assert not d.nur_pruefen.isHidden()
d.nur_pruefen.setChecked(True)
z_gruen = next(z for z in d.zeilen if z.ampel == "gruen")
assert z_gruen.it.isHidden() and not z_gelb.it.isHidden()
assert z_gruen.it.parent().isHidden()            # Gruppe nur mit sicheren Teilen ebenfalls weg
d.nur_pruefen.setChecked(False)
assert not z_gruen.it.isHidden() and not z_gruen.it.parent().isHidden()
d.close()
d2 = StepPruefDialog(None, [gut], k, "S235-10219", 1)
assert d2.ampel_zahlen() == (1, 0, 0) and d2.nur_pruefen.isHidden()
d2.close()
ok("C1 Prüfdialog: Punkt in der Spalte Hinweis, Grund im Tooltip, „1 sicher · 1 prüfen · 1 nicht übernehmbar“, "
   "Filter „Nur zu prüfende“")

# ------------------------------------------------------------------ E1 Fehler seit gestern
ordner = tmp / "Protokoll"
ordner.mkdir()
(ordner / "fehler.log.1").write_text(
    "2026-11-01 08:00:00,000 ERROR Unerwarteter Fehler\nTraceback (most recent call last):\n  x\nKeyError: 'alt'\n",
    encoding="utf-8")
(ordner / "fehler.log").write_text(
    "2026-11-03 09:00:00,000 INFO Start Rohrlaser 0.9.259\n"
    "2026-11-03 10:15:00,123 ERROR Unerwarteter Fehler\nTraceback (most recent call last):\n"
    "  File \"x.py\", line 1\nZeroDivisionError: division by zero\n"
    "2026-11-04 07:30:00,000 INFO Lesemodus: Änderung abgewiesen\n"
    "2026-11-04 11:00:00,000 ERROR Unerwarteter Fehler\nTraceback (most recent call last):\nValueError: kaputt\n",
    encoding="utf-8")
f = protokoll.fehler_seit(ordner, datetime.datetime(2026, 11, 3))
assert [t for _, t in f] == ["ZeroDivisionError: division by zero", "ValueError: kaputt"], f
assert len(protokoll.fehler_seit(ordner, datetime.datetime(2026, 10, 1))) == 3
assert protokoll.fehler_seit(tmp / "fehlt", datetime.datetime(2026, 1, 1)) == []
ok("E1 Fehler aus fehler.log und fehler.log.1 ab Zeitpunkt, mit letzter Zeile des Tracebacks")

from rohrlaser.fenster import Hauptfenster  # noqa: E402

fe = Hauptfenster(db, stumm=True)
s = fe.start
s.fehler_laden(jetzt=datetime.datetime(2026, 11, 4, 12, 0))
assert "2 Fehler seit gestern" in s.fehler.text() and "ValueError: kaputt" in s.fehler.text(), s.fehler.text()
assert not s.support_knopf.isHidden()
aufgerufen = []
fe.support_paket = lambda *a, **kw: aufgerufen.append(1)
s.support_knopf.click()
assert aufgerufen == [1]
s.fehler_laden(jetzt=datetime.datetime(2026, 11, 20, 12, 0))
assert "Keine Fehler seit gestern" in s.fehler.text() and s.support_knopf.isHidden()
ok("E1 Startseite: „2 Fehler seit gestern“ mit Knopf Support-Paket; ohne Fehler nur ein grauer Hinweis")

# ------------------------------------------------------------------ D2 Laserzeit Soll/Ist je Maschine


def fall(maschine, soll, ist, erfasst=True):
    return dict(nummer="A", datum="", ist={}, soll=dict(maschine=maschine, zeilen=[
        ["Laserzeit", "laserzeit", "h", soll, ist, 0, 0, erfasst]]))


fl = [fall("T11", 1.0, 1.2), fall("T11", 2.0, 2.1), fall("T11", 1.0, 1.0), fall("T11", 5.0, 0, erfasst=False),
      fall("T12", 1.0, 0.5), fall("T12", 1.0, 0.5)]
w = nachkalkulation.laserzeit_je_maschine(db, fl=fl)
assert len(w) == 1 and w[0]["maschine"] == "T11" and w[0]["n"] == 3, w
assert abs(w[0]["prozent"] - 7.5) < 1e-9, w
assert [x["maschine"] for x in nachkalkulation.laserzeit_je_maschine(db, mindestens=2, fl=fl)] == ["T11", "T12"]
s.laserzeit_laden()
assert s.laserzeit.isHidden()                    # ohne Nachkalkulationen nichts
nachkalkulation_alt = nachkalkulation.laserzeit_je_maschine
nachkalkulation.laserzeit_je_maschine = lambda db_: nachkalkulation_alt(db_, mindestens=2, fl=fl)
s.laserzeit_laden()
nachkalkulation.laserzeit_je_maschine = nachkalkulation_alt
t = s.laserzeit.text()
assert "T11 <b>+7 %</b> (3 Aufträge)" in t and "−50 %" in t and not s.laserzeit.isHidden(), t
ok(f"D2 Startseite: Laserzeit Ist gegen Soll je Maschine erst ab 3 Aufträgen ({s.laserzeit.text()[:60]} …)")
QTest.qWait(10)
fe.close()

# ------------------------------------------------------------------ D1 Referenzangebote
from rohrlaser import referenzangebote  # noqa: E402

db2 = Datenbank(tmp / "ref.db")
a = db2.angebot_neu(dict(kunde="Referenz", maschine="T11", stange=6000))
db2.position_neu(a, dict(pos=10, artikel="R1", profil_id="RR 42,4x2,0", werkstoff_id="S235-10219", laenge=500.0,
                         stueck=20, schneidweg=400.0, einstiche=4))
assert referenzangebote.liste(db2) == []
r = referenzangebote.festhalten(db2, a)
assert r["nummer"] and r["verkauf"] > 0, r
assert [x["angebot_id"] for x in referenzangebote.liste(db2)] == [a]
erg = referenzangebote.pruefen(db2)
assert len(erg) == 1 and erg[0]["status"] == "gleich", erg
db2.position_aendern(db2.positionen(a)[0]["id"], "stueck", 40)
erg = referenzangebote.pruefen(db2)
assert erg[0]["status"] == "abweichung" and erg[0]["prozent"] != 0, erg
assert "abweichend" in referenzangebote.text(erg)
referenzangebote.entfernen(db2, a)
assert referenzangebote.liste(db2) == []
ok("D1 Referenzangebot festhalten, nachrechnen (gleich bzw. Abweichung in %), entfernen")

# ------------------------------------------------------------------ D1 in der Oberfläche
fe2 = Hauptfenster(db2, stumm=True)
s2 = fe2.angebot_oeffnen(a)
QTest.qWait(50)
s2.weitere.menu().aboutToShow.emit()
assert not s2.referenz_aktion.isChecked()
r = s2.referenz_umschalten()
assert r and referenzangebote.ist_referenz(db2, a)
s2.weitere.menu().aboutToShow.emit()
assert s2.referenz_aktion.isChecked()
erg = fe2.referenzen_pruefen()
assert erg[0]["status"] == "gleich" and fe2.referenz_dialog.isVisible()
assert any(x.text() == "Referenzangebote prüfen …" for m in fe2.menuBar().actions() if m.menu()
           for x in m.menu().actions())
fe2.referenz_dialog.close()
assert s2.referenz_umschalten() is None and not referenzangebote.ist_referenz(db2, a)
fe2.close()
ok("D1 Ausgaben → Als Referenzangebot festhalten (Haken), Hilfe → Referenzangebote prüfen … mit Tabelle")

# ------------------------------------------------------------------ E2 Testlauf in gleich langen Teilen
sys.path.insert(0, str(HIER))
import alle  # noqa: E402

dauer = alle.laufzeiten()
assert len(dauer) > 200, len(dauer)
teile = [alle.teil(alle.TESTS, k, 3) for k in (1, 2, 3)]
namen = [n for t in teile for n, _ in t]
assert sorted(namen) == sorted(n for n, _ in alle.TESTS) and len(set(namen)) == len(namen)
summen = [sum(dauer.get(n, alle.UNBEKANNT_S) for n, _ in t) for t in teile]
assert max(summen) - min(summen) <= 0.05 * max(summen), summen
assert [n for n, _ in teile[0]] == [n for n, _ in alle.TESTS if (n, _) in teile[0]]    # Reihenfolge wie TESTS
ok(f"E2 drei gleich lange Teile für drei Rechner: {', '.join(f'{s / 60:.0f} min' for s in summen)} Rechenzeit")
print("Alle Prüfungen Paket 3 bestanden.")
