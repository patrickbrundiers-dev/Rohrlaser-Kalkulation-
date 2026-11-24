"""Nesting-Arbeitsplatz (Patrick 23.11.2026): Strategievergleich je Abmessung im Angebot, Bild der Stangen, Teile
von Hand umsetzen (nie überbelegt), Übernehmen speichert je Abmessung und optimiert neu, lokale Hinweise, Lager-Seite
mit Zustand, Kundenangebot ohne interne Verschachtelungsdaten.

Aufruf: python tests/test_nesting_arbeitsplatz.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QPointF  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from rohrlaser import lager, nesting as ne, nesting_hinweise, nesting_vergleich as nv, rechnen  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402
from rohrlaser.nesting_dialog import segmente  # noqa: E402

app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
QR, ST = "QR 40x40x3", "S235-10219"
for laenge in (6000, 6500, 7000):
    db.neu("lieferlaengen", dict(profil_id=QR, werkstoff_id=ST, laenge=laenge))
fenster = Hauptfenster(db, tmp, stumm=True)
aid = db.angebot_neu(dict(kunde="Test", maschine="T03", stange=6000))
for i, (lg, n) in enumerate([(850, 12), (1250, 8), (430, 6), (1800, 4)]):
    db.position_neu(aid, dict(pos=10 * (i + 1), artikel=f"A{i}", profil_id=QR, werkstoff_id=ST, laenge=lg,
                              stueck=n, schneidweg=160, einstiche=1))
s = fenster.angebot_oeffnen(aid)
assert s.optimieren()
vorher = [x["stange"] for x in s.ergebnis["stangen"]]
assert set(vorher) == {6000} and not any(x.get("nesting") for x in s.ergebnis["stangen"])

# Strategievergleich: bisher + A … E (ohne Lager kein C)
v = s.nesting_vergleich()
assert len(v) == 1
namen = [z["strategie"] for z in v[0]["zeilen"]]
assert namen[0] == nv.BISHER and set(namen[1:]) == {ne.A, ne.B, ne.D, ne.E, ne.F, ne.G, ne.H}, namen
a = next(z for z in v[0]["zeilen"] if z["strategie"] == ne.A)
b = next(z for z in v[0]["zeilen"] if z["strategie"] == nv.BISHER)
assert a["gekauft_m"] < b["gekauft_m"], (a, b)
assert all(nv.text(z, "ausnutzung").endswith("%") or z["zuschnitt"] for z in v[0]["zeilen"])
print("OK     Strategievergleich je Abmessung")

# Bild: Segmente lückenlos von 0 bis Stangenlänge
g = v[0]["gruppe"]
for laenge, f, _ in v[0]["plaene"][ne.A].stangen:
    seg = segmente(g, laenge, f)
    assert abs(seg[0][1]) < 1e-9 and abs(seg[-1][2] - laenge) < 1e-6
    assert all(abs(x[2] - y[1]) < 1e-6 for x, y in zip(seg, seg[1:])), seg
print("OK     Stangenbild lückenlos (Endbeschnitt, Teile, Schnitte, Rest, Greiferrest)")

# Dialog: Strategie A übernehmen -> gespeichert, neu optimiert, gemischte Längen
from rohrlaser import nesting_dialog  # noqa: E402


def mit_a(d):
    d.show()
    r = next(i for i, z in enumerate(d.vergleich[0]["zeilen"]) if z["strategie"] == ne.A)
    d.tabelle.selectRow(r)
    assert d.strategie_uebernehmen() == ne.A
    assert d.k_ok.isEnabled()
    d.grab().save(str(tmp / "nesting_arbeitsplatz.png"))
    return True


assert s.nesting_arbeitsplatz(dialog=mit_a)
schl = v[0]["schluessel"]
assert db.angebot(aid)["nesting"] == {schl: ne.A}
nachher = [x["stange"] for x in s.ergebnis["stangen"]]
assert sum(nachher) < sum(vorher) and all(x.get("nesting") == ne.A for x in s.ergebnis["stangen"]), nachher
print("OK     Strategie übernommen:", sorted(nachher), "statt", len(vorher), "× 6 m")

# Belegung von Hand: ein Teil umsetzen; Ziel zu voll -> Meldung, nichts geändert
d = nesting_dialog.NestingDialog(s.nesting_vergleich(), s.positionen, s)
d.resize(1300, 800)
d.show()
app.processEvents()
r = next(i for i, z in enumerate(d.vergleich[0]["zeilen"]) if z["strategie"] == nv.BISHER)
d.tabelle.selectRow(r)
st = d.bild.stangen
voll = max(range(len(st)), key=lambda i: sum(t.laenge for t, _ in st[i][1]))
leer = min(range(len(st)), key=lambda i: sum(t.laenge for t, _ in st[i][1]))
lang_i = max(range(len(st[leer][1])), key=lambda n: st[leer][1][n][0].laenge)
d.bild.auswahl = (leer, lang_i)
d.ziel_gewaehlt(voll)
assert d.hand_stangen is None and ("Passt nicht" in d.hinweis.text() or d.bild.stangen == st), d.hinweis.text()
d.bild.auswahl = (voll, 0)
d.ziel_gewaehlt(-1)                                        # auf eine neue Stange
assert d.hand_stangen is not None and len(d.hand_stangen) == len(st) + (1 if len(st[voll][1]) > 1 else 0)
ne.pruefe(g, d.hand_stangen, [], None)
d.rueckgaengig()
assert d.bild.stangen == st
d.bild.auswahl = (voll, 0)
d.ziel_gewaehlt(-1)
hand = d.hand_uebernehmen()
assert hand and sum(len(x["teile"]) for x in hand) == 30
# Klick ins Bild: Teil treffen
y = d.bild.OBEN + 3
i, n = d.bild.treffer(QPointF(d.bild.LINKS + 40 * d.bild._skala() + 2, y))
assert i == 0 and n == 0, (i, n)
print("OK     Belegung von Hand: prüfen, umsetzen, rückgängig, übernehmen")

assert s.nesting_arbeitsplatz(dialog=lambda d: (d.tabelle.selectRow(0), d.bild.setzen(
    d.aktuell()["gruppe"], d.vergleich[0]["plaene"][nv.BISHER].stangen), setattr(d, "hand_stangen", d.bild.stangen),
    d.hand_uebernehmen(), True)[-1])
assert db.angebot(aid)["stangen_hand"] and all(x.get("nesting") == rechnen.NESTING_HAND for x in s.ergebnis["stangen"])
print("OK     Belegung von Hand gespeichert und neu optimiert")

# Wie bisher: alles zurück
assert s.nesting_arbeitsplatz(dialog=lambda d: (d.bisher_uebernehmen(), True)[-1])
assert db.angebot(aid)["nesting"] is None and db.angebot(aid)["stangen_hand"] is None
assert [x["stange"] for x in s.ergebnis["stangen"]] == vorher
print("OK     Wie bisher: gleicher Plan wie vorher")

# Hinweise (lokal, nur Text)
hw = nesting_hinweise.hinweise(s.nesting_vergleich()[0])
assert any("günstiger ein als bisher" in h or "belegt" in h for h in hw), hw
print("OK     Lokale Hinweise:", hw[:2])

# Kundenangebot: keine Verschachtelungsdetails, keine Einkaufspreise
db.nesting_speichern(aid, {schl: ne.B}, {})
s.neu_laden()
assert s.optimieren()
from rohrlaser import akte_pdf  # noqa: E402
pfad = tmp / "kunde.pdf"
akte_pdf.schreiben(pfad, s.akte_sammeln(bilder=False), s.einst, "kunde")
txt = " ".join(akte_pdf.text_der_seiten(pfad))
assert txt and akte_pdf.kunde_pruefen(pfad) == []
for wort in ("Strategie", "Verschachtelung", "Einkauf", "kalkulatorisch", "Reststück", "Lieferlänge"):
    assert wort not in txt, wort
print("OK     Kundenangebot ohne interne Verschachtelungsdaten")

# Lager-Seite: Zustand und verwertbar (nur mit Lager)
db.einstellung_setzen("lager_aktiv", "ja")
db.einstellung_setzen("reste_aktiv", "ja")
fenster.lager_anwenden()
seite = fenster.lager
(rid,) = lager.zugang(db, "Rest", QR, ST, 2600, 1)
(kurz,) = lager.zugang(db, "Rest", QR, ST, 300, 1)
seite.neu_laden()
zeile = next(i for i, z in enumerate(seite.zeilen) if z["id"] == rid)
seite.tabelle.selectRow(zeile)
assert seite.zustand("gesperrt", "krumm") == "gesperrt"
z = next(z for z in seite.zeilen if z["id"] == rid)
assert z["status"] == "gesperrt" and z["verwertbar"] == "nein"
assert next(z for z in seite.zeilen if z["id"] == kurz)["verwertbar"].startswith("nein")
seite.tabelle.selectRow(next(i for i, z in enumerate(seite.zeilen) if z["id"] == rid))
seite.zustand("frei")
assert next(z for z in seite.zeilen if z["id"] == rid)["verwertbar"] == "ja"
# mit Lager: Strategie C setzt den Rest ein
s.einst = db.einstellungen()
v = s.nesting_vergleich()
assert any(z["strategie"] == ne.C for z in v[0]["zeilen"]), [z["strategie"] for z in v[0]["zeilen"]]
pc = v[0]["plaene"][ne.C]
assert pc.werte["reste"] >= 1 and lager.posten(db, rid)["kennung"] in pc.werte["rest_kennungen"]
print("OK     Lager: Zustand, verwertbar, Strategie C mit Rest")
fenster.close()
db.schliessen()
print("Alle Tests OK")
