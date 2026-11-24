"""Prüft die Reihenfolge der Positionen im Angebot (Patrick 29.10.2026, reihenfolge.py): nach oben/unten, an den
Anfang/ans Ende, Drag & Drop am Zeilenkopf; Baugruppen wandern mit ihren Teilen, Sätze mit ihren Positionen;
Positionsnummern bleiben aufsteigend (eigenes Schema bleibt), Staffeln je Position und ein aktueller Schnittplan
ziehen mit; Kalkulation und PDF in der neuen Reihenfolge; Rückgängig; Lesemodus/fremde Angebote gesperrt.

Aufruf: python tests/test_reihenfolge.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import beispiel_angebot  # noqa: E402
import beispiel_baugruppe  # noqa: E402
from rohrlaser import ausgabe, reihenfolge as rf  # noqa: E402
from rohrlaser.angebot import BAUGRUPPE  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def ok(text):
    print("OK    ", text)


def r1_bloecke():
    bg = '{"id": "b1", "knoten": [], "arbeitsgaenge": [], "naehte": [], "stamm": {}}'
    p = [dict(pos=10, artikel="A"), dict(pos=20, artikel="B", satz="S"), dict(pos=30, artikel="C"),
         dict(pos=40, artikel="D", satz="S"), dict(pos=50, art=BAUGRUPPE, artikel="BG", baugruppe=bg),
         dict(pos=60, artikel="T1", bg_knoten="b1"), dict(pos=70, artikel="T2", bg_knoten="b1"),
         dict(pos=80, artikel="E")]
    assert rf.bloecke(p) == [(None, [0]), (("satz", "S"), [1, 3]), (None, [2]), (("bg", "b1"), [4, 5, 6]),
                             (None, [7])], rf.bloecke(p)
    assert rf.anzeige(p) == [0, 1, 3, 2, 4, 5, 6, 7]
    assert rf.verschieben(p, [2], rf.OBEN) == [0, 2, 1, 3, 4, 5, 6, 7]          # an dem ganzen Satz vorbei
    assert rf.verschieben(p, [3], rf.OBEN) == [0, 3, 1, 2, 4, 5, 6, 7]          # innerhalb des Satzes
    assert rf.verschieben(p, [1], rf.UNTEN) == [0, 2, 1, 3, 4, 5, 6, 7]         # erste Zeile = ganzer Satz
    assert rf.verschieben(p, [4], rf.OBEN) == [0, 1, 3, 4, 5, 6, 2, 7]          # Baugruppe mit ihren Teilen
    assert rf.verschieben(p, [6], rf.OBEN) == [0, 1, 3, 2, 4, 6, 5, 7]          # Teil innerhalb der Baugruppe
    assert rf.verschieben(p, [5], rf.OBEN) is None                              # erstes Teil: bleibt unter der BG
    assert rf.verschieben(p, [0], rf.OBEN) is None and rf.verschieben(p, [7], rf.UNTEN) is None
    assert rf.verschieben(p, [0, 7], rf.UNTEN) == [1, 3, 0, 2, 4, 5, 6, 7]      # ganz unten bleibt, A eins tiefer
    assert rf.verschieben(p, [2, 7], rf.ANFANG) == [2, 7, 0, 1, 3, 4, 5, 6]
    assert rf.verschieben(p, [0], rf.ENDE) == [1, 3, 2, 4, 5, 6, 7, 0]
    assert rf.einsetzen(p, 7, 0) == [7, 0, 1, 3, 2, 4, 5, 6]                    # Drag & Drop vor A
    assert rf.einsetzen(p, 0, None) == [1, 3, 2, 4, 5, 6, 7, 0]                 # ans Ende
    assert rf.einsetzen(p, 0, 5) == [1, 3, 2, 4, 5, 6, 0, 7]                    # mitten in die BG: dahinter
    assert rf.einsetzen(p, 6, 5) == [0, 1, 3, 2, 4, 6, 5, 7]                    # innerhalb der BG
    assert rf.einsetzen(p, 0, 1) is None
    ok("R1 Blöcke wie die Positionsliste; hoch/runter, Anfang/Ende, Drag & Drop; Baugruppe mit Teilen, Satz zusammen")
    neu, nummern = rf.anordnung(p, [7, 0, 1, 3, 2, 4, 5, 6])
    assert nummern == [10, 20, 30, 40, 50, 60, 70, 80] and [x["artikel"] for x in neu][:2] == ["E", "A"]
    assert [x["nr"] for x in neu] == list(range(1, 9))
    eigen = [dict(x) for x in p]
    eigen[4]["pos"] = 100                                                       # eigenes Schema: BG 100
    assert rf.nummern(eigen, [7, 0, 1, 3, 2, 4, 5, 6]) == [80, 10, 20, 40, 30, 100, 60, 70]
    assert rf.nummern(eigen, [0, 1, 3, 2, 4, 5, 6, 7], True) == [10, 20, 30, 40, 50, 60, 70, 80]
    lueck = [dict(x) for x in p[:3]]
    lueck[1]["pos"] = None
    assert rf.nummern(lueck, [2, 1, 0]) == [10, None, 30]
    assert rf.staffel_schluessel(p, [7, 0, 1, 3, 2, 4, 5, 6], nummern) == {
        "80": "10", "10": "20", "30": "50", "50": "60", "60": "70", "70": "80"}      # Satz S zählt über den Namen
    erg = dict(stangen=[dict(belegung="10×500 | 80×400", teile=[dict(index=0, ref="id1", pos=10, laenge=500),
                                                                dict(index=7, ref="ix7", pos=80, laenge=400)])],
               fehler=[dict(index=2, pos=30, artikel="C", anzahl=1)])
    u = rf.ergebnis_umstellen(erg, p, [7, 0, 1, 3, 2, 4, 5, 6], nummern)
    t = u["stangen"][0]["teile"]
    assert (t[0]["index"], t[0]["pos"], t[1]["index"], t[1]["ref"], t[1]["pos"]) == (1, 20, 0, "ix0", 10)
    assert u["stangen"][0]["belegung"] == "20×500 | 10×400" and u["fehler"][0] == dict(index=4, pos=50, artikel="C",
                                                                                         anzahl=1)
    assert erg["stangen"][0]["belegung"] == "10×500 | 80×400"                   # Original unverändert
    ok("R2 Positionsnummern: aufsteigend neu verteilt, eigenes Schema bleibt, neu vergeben 10/20/30; Staffeln und "
       "Schnittplan mit den neuen Nummern")


def r3_programm():
    app = QApplication.instance() or QApplication([])
    tmp = Path(tempfile.mkdtemp())
    db = Datenbank(tmp / "rohrlaser.db")
    f = Hauptfenster(db, tmp, stumm=True)
    a = beispiel_angebot.anlegen(db)
    s = f.angebot_oeffnen(a)
    s.optimieren()
    assert s.stand_optimierung() == "aktuell"
    db.staffel_neu(a, dict(schluessel="50", menge=50))
    s.neu_laden()
    schl = {st["id"]: st["schluessel"] for st in db.staffeln(a)}      # Beispiel: Satz „Rahmen“, Pos. 10, neu 50
    vorher = [(p["pos"], p["artikel"]) for p in s.positionen]
    preis = {p["artikel"]: z["preis_teil"] for p, z in zip(s.positionen, s._rechnung()[0])}
    stangen = len(s.ergebnis["stangen"])
    assert s.positionen_verschieben(rf.UNTEN, [0])
    nachher = [(p["pos"], p["artikel"]) for p in s.positionen]
    assert nachher[:2] == [(vorher[0][0], vorher[1][1]), (vorher[1][0], vorher[0][1])], nachher
    assert [p["nr"] for p in s.positionen] == list(range(1, len(vorher) + 1))
    assert s._markierte_zeilen() == [1]
    assert s.stand_optimierung() == "aktuell" and len(s.ergebnis["stangen"]) == stangen
    t = next(t for st in s.ergebnis["stangen"] for t in st["teile"] if t["artikel"] == vorher[0][1])
    assert t["index"] == 1 and t["pos"] == vorher[1][0], t
    zeilen = s._rechnung()[0]
    assert {p["artikel"]: z["preis_teil"] for p, z in zip(s.positionen, zeilen)} == preis
    doc = ausgabe.angebot(s.kopf, s.positionen, zeilen, s.k, s.einst, ergebnis=s.ergebnis)
    zeilen_pdf = [(z["pos"], z["artikel"]) for z in doc["zeilen"] if z.get("artikel")]
    assert zeilen_pdf[:2] == nachher[:2], zeilen_pdf
    ok("R3 Nach unten: Positionsnummern aufsteigend, Auswahl folgt, Schnittplan bleibt aktuell, Preise gleich, PDF "
       "in der neuen Reihenfolge")
    # Staffel je Position: „50“ gehört weiter zum selben Teil, das jetzt Pos. 10 ist
    assert s.positionen_verschieben(rf.ANFANG, [4])
    assert s.positionen[0]["artikel"] == vorher[4][1] and s.positionen[0]["pos"] == vorher[0][0]
    neu = {st["id"]: st["schluessel"] for st in db.staffeln(a)}
    jetzt = {p_["artikel"]: str(p_["pos"]) for p_ in s.positionen}
    assert neu == {i: alt if alt == "Rahmen" else jetzt[next(v[1] for v in vorher if str(v[0]) == alt)]
                   for i, alt in schl.items()}, (schl, neu)
    assert s.positionen_verschieben(rf.ENDE, [3]) is False                      # Satz steht schon am Ende
    assert s.positionen_verschieben(rf.ANFANG, [3])                             # erste Zeile des Satzes: ganzer Satz
    assert [p.get("satz") for p in s.positionen][:2] == ["Rahmen", "Rahmen"]
    ok("R4 An den Anfang/ans Ende: Staffel je Position zieht mit, Satz wandert ganz")
    assert s.rueckgaengig() and s.rueckgaengig() and s.rueckgaengig()
    assert [(p["pos"], p["artikel"]) for p in s.positionen] == vorher
    assert {st["id"]: st["schluessel"] for st in db.staffeln(a)} == schl and s.stand_optimierung() == "aktuell"
    ok("R5 Rückgängig stellt Reihenfolge, Nummern, Staffeln und Schnittplan wieder her")
    # Drag & Drop am Zeilenkopf: letzte Zeile vor die erste ziehen
    kopf = s.pos_ansicht.verticalHeader()
    assert kopf.sectionsMovable()
    n = len(s.positionen)
    kopf.moveSection(kopf.visualIndex(n - 1), 0)
    for _ in range(5):
        app.processEvents()
    assert s.positionen[0]["artikel"] == vorher[-1][1] and s.positionen[0]["pos"] == vorher[0][0]
    assert all(kopf.visualIndex(r) == r for r in range(n))
    ok("R6 Drag & Drop am Zeilenkopf: Position vor die erste gezogen, Nummern aufsteigend")
    assert s.positionsnummern_vergeben() is False                     # schon 10, 20, 30 …
    db.position_aendern(s.positionen[0]["id"], "pos", 5)
    s.neu_laden()
    assert s.positionsnummern_vergeben() and [p["pos"] for p in s.positionen] == [10 * (k + 1) for k in range(n)]
    ok("R7 Positionsnummern neu vergeben: 10, 20, 30 … in der Reihenfolge der Liste")
    # Rechtsklick-Menü und Kürzel
    aktionen = s._pos_menue_anpassen()
    assert {"Nach oben", "Nach unten", "An den Anfang", "Ans Ende"} <= set(aktionen)
    assert f.kuerzel_aktionen["hoch"].shortcut().toString() == "Alt+Up"
    f.show()
    f.reiter.setCurrentWidget(s)
    s.reiter.setCurrentWidget(s.pos_seite)
    s.pos_ansicht.setFocus()
    app.processEvents()
    s.pos_ansicht.selectRow(1)
    erster = s.positionen[1]["artikel"]
    f.kuerzel("hoch")
    assert s.positionen[0]["artikel"] == erster
    ok("R8 Rechtsklick Nach oben/unten/Anfang/Ende, Alt+↑/↓ in der Positionsliste")
    # Baugruppe wandert mit ihren Teilen
    b = beispiel_baugruppe.anlegen(db)
    sb = f.angebot_oeffnen(b)
    db.position_neu(b, dict(pos=40, artikel="Extra", profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=500,
                            stueck=1))
    sb.neu_laden()
    alt = [p["artikel"] for p in sb.positionen]
    assert alt == ["R1", "Rohr", "Strebe", "Lasche", "Extra"]
    assert sb.positionen_verschieben(rf.OBEN, [4])
    assert [p["artikel"] for p in sb.positionen] == ["Extra", "R1", "Rohr", "Strebe", "Lasche"]
    assert [p["pos"] for p in sb.positionen] == [40, 100, 10, 20, 30]           # eigenes Schema bleibt
    assert sb.positionen_verschieben(rf.UNTEN, [2])                             # Teil innerhalb der Baugruppe
    assert [p["artikel"] for p in sb.positionen] == ["Extra", "R1", "Strebe", "Rohr", "Lasche"]
    assert sb.positionen_verschieben(rf.OBEN, [1])                              # BG samt Teilen über Extra
    assert [p["artikel"] for p in sb.positionen] == ["R1", "Strebe", "Rohr", "Lasche", "Extra"]
    assert sb.positionen_verschieben(rf.OBEN, [1]) is False                     # erstes Teil bleibt unter der BG
    ok("R9 Baugruppe wandert mit ihren Teilen, Teile innerhalb der Baugruppe umstellbar, eigenes Nummernschema bleibt")
    db.nur_lesen = True
    try:
        assert sb.positionen_verschieben(rf.UNTEN, [0]) is False
    finally:
        db.nur_lesen = False
    assert [p["artikel"] for p in sb.positionen][0] == "R1"
    ok("R10 Lesemodus: Reihenfolge gesperrt")
    for x in (s, sb):
        x.close()
    app.processEvents()
    _ = Qt


if __name__ == "__main__":
    r1_bloecke()
    r3_programm()
    print("Alle Prüfungen bestanden.")
