"""Prüft „Position als neue Position kopieren“ (Patrick 30.10.2026, position_kopie.py): Einheiten wie die
Positionsliste (Baugruppe mit Teilen, erste Satzzeile = ganzer Satz, sonst einzeln), eindeutige Artikelnummer und
Satzname, Positionsnummer in der Lücke hinter dem Original oder am Ende; im Programm: Duplizieren mit allen Daten
(Technik, Zusatz, 3D-Netz, Staffeln, Satz in 3D), Rückgängig, Übernehmen aus einem anderen Angebot (auch fremd), das
Quellangebot bleibt unverändert, Lesemodus/fremd gesperrt, Rechtsklick, Strg+Umschalt+D, Neue Position.

Aufruf: python tests/test_position_kopie.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication, QDialog, QDialogButtonBox, QPushButton  # noqa: E402

import beispiel_angebot  # noqa: E402
import beispiel_baugruppe  # noqa: E402
from rohrlaser import baugruppe, neue_position, position_kopie as pk  # noqa: E402
from rohrlaser.angebot import BAUGRUPPE  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402
from rohrlaser.position_kopie_dialog import UebernehmenDialog, zeilen_text  # noqa: E402


def ok(text):
    print("OK    ", text)


def k1_logik():
    bg = '{"id": "b1", "knoten": [], "arbeitsgaenge": [], "naehte": [], "stamm": {}}'
    p = [dict(id=1, pos=10, artikel="A"), dict(id=2, pos=20, artikel="B", satz="S", je_satz=2),
         dict(id=3, pos=30, artikel="C"), dict(id=4, pos=40, artikel="D", satz="S", je_satz=1),
         dict(id=5, pos=50, art=BAUGRUPPE, artikel="BG", baugruppe=bg, satz="BG"),
         dict(id=6, pos=60, artikel="T1", bg_knoten="b1", satz="BG", je_satz=2),
         dict(id=7, pos=70, artikel="T2", bg_knoten="b1", satz="BG", je_satz=1), dict(id=8, pos=80, artikel="E")]
    assert pk.einheiten(p, [0]) == [(pk.EINZEL, [0])]
    assert pk.einheiten(p, [1]) == [(pk.SATZ, [1, 3])]                      # erste Satzzeile = ganzer Satz
    assert pk.einheiten(p, [3]) == [(pk.EINZEL, [3])]
    assert pk.einheiten(p, [4]) == [(pk.BG, [4, 5, 6])] and pk.einheiten(p, [4, 5]) == [(pk.BG, [4, 5, 6])]
    assert pk.einheiten(p, [6, 0]) == [(pk.EINZEL, [0]), (pk.EINZEL, [6])]
    assert pk.einheiten(p, []) == [] and pk.einheiten(p, [99]) == []
    ok("K1 Einheiten wie die Positionsliste: Baugruppe mit Teilen, erste Satzzeile = Satz, sonst einzeln")
    assert pk.frei("A", {"A", "A-2"}, "{}-{}") == "A-3" and pk.frei("S", set()) == "S"
    assert pk.luecke(p, 10, 1) == [15] and pk.luecke(p, 10, 3) == [12, 14, 16]
    assert pk.luecke(p, 10, 10) is None and pk.luecke(p, 80, 2) == [90, 100]
    assert pk.luecke([dict(pos=10), dict(pos=11)], 10, 1) is None
    paare, saetze = pk.kopien(p, pk.einheiten(p, [0]), p, gleiches=True)
    assert len(paare) == 1 and paare[0][1]["artikel"] == "A-2" and paare[0][1]["pos"] == 90
    assert "id" not in paare[0][1] and "nr" not in paare[0][1] and saetze == {}
    paare, saetze = pk.kopien(p, pk.einheiten(p, [1]), p, gleiches=True)
    assert [w["artikel"] for _, w in paare] == ["B-2", "D-2"] and saetze == {"S": "S (2)"}
    assert {w["satz"] for _, w in paare} == {"S (2)"} and [w["je_satz"] for _, w in paare] == [2, 1]
    paare, _ = pk.kopien(p, pk.einheiten(p, [3, 5]), p, gleiches=True)     # Teil aus Satz bzw. BG: eigenständig
    assert all("satz" not in w and "bg_knoten" not in w and "je_satz" not in w for _, w in paare)
    paare, saetze = pk.kopien(p, pk.einheiten(p, [4]), p, gleiches=True)
    kopf = baugruppe.lesen(paare[0][1]["baugruppe"])
    assert kopf["id"] != "b1" and all(baugruppe.zuordnung(w)[0] == kopf["id"] for _, w in paare[1:])
    assert [w["artikel"] for _, w in paare] == ["BG-2", "T1-2", "T2-2"]
    assert {w["satz"] for _, w in paare} == {"BG-2"} and saetze == {"BG": "BG-2"}
    paare, saetze = pk.kopien(p, pk.einheiten(p, [1, 0]), [dict(pos=5, artikel="A")], gleiches=False)
    assert [w["artikel"] for _, w in paare] == ["A", "B", "D"] and [w["pos"] for _, w in paare] == [15, 25, 35]
    assert saetze == {"S": "S"}                                             # anderes Angebot: Artikel bleibt
    ok("K2 Kopien: Artikel/Satz/Baugruppe eindeutig im selben Angebot, Lücke hinter dem Original, sonst ans Ende")
    st = [dict(id=1, schluessel="10", menge=5, stufe_id=7), dict(id=2, schluessel="S", menge=2, stufe_id=8),
          dict(id=3, schluessel="S", menge=4, stufe_id=8), dict(id=4, schluessel="30", menge=9, stufe_id=9)]
    paare, saetze = pk.kopien(p, pk.einheiten(p, [0, 1]), p, gleiches=True)
    erg = pk.staffeln_kopieren(st, [dict(id=7, gewinn=12), dict(id=8)], paare, saetze)
    assert [(s_.get("gewinn"), [(z["schluessel"], z["menge"]) for z in zs]) for s_, zs in erg] == [
        (12, [("90", 5)]), (None, [("S (2)", 2), ("S (2)", 4)])], erg
    ok("K3 Staffeln: je Position über die neue Pos.-Nummer, je Satz über den neuen Namen, Stufen bleiben zusammen")


def k4_programm():
    app = QApplication.instance() or QApplication([])
    tmp = Path(tempfile.mkdtemp())
    db = Datenbank(tmp / "rohrlaser.db")
    f = Hauptfenster(db, tmp, stumm=True)
    a = beispiel_angebot.anlegen(db)
    s = f.angebot_oeffnen(a)
    p10 = s.positionen[0]
    db.position_aendern(p10["id"], "zusatz", '[{"name": "Entgraten", "menge": 1}]')
    db.position_aendern(p10["id"], "gravur", 120.0)
    db.netz_speichern(p10["id"], b"netz-10")
    db.satz_daten_speichern(a, "Rahmen", {"stoesse": [{"a": 1}]})
    s.neu_laden()
    vorher = [(p["pos"], p["artikel"]) for p in s.positionen]
    n_st = len(db.staffeln(a))
    assert s.position_duplizieren([0]) == 1
    kopie = s.positionen[1]
    assert (kopie["pos"], kopie["artikel"]) == (15, "4711-001-2"), (kopie["pos"], kopie["artikel"])
    for feld in ("profil_id", "werkstoff_id", "laenge", "stueck", "schneidweg", "einstiche", "zusatz", "gravur"):
        assert kopie[feld] == s.positionen[0][feld], feld
    assert db.netz(kopie["id"]) == b"netz-10"
    assert sorted(z["menge"] for z in db.staffeln(a) if z["schluessel"] == "15") == [24, 50, 100]
    assert [p["pos"] for p in s.positionen] == [10, 15, 20, 30, 40, 50]
    assert s._markierte_zeilen() == [1]
    ok("K4 Duplizieren: alle Eingaben, 3D-Netz, Staffeln; Pos. 15 direkt hinter Pos. 10, Artikel eindeutig, markiert")
    assert s.rueckgaengig()
    assert [(p["pos"], p["artikel"]) for p in s.positionen] == vorher and len(db.staffeln(a)) == n_st, ([(p["pos"], p["artikel"]) for p in s.positionen], vorher, len(db.staffeln(a)), n_st)
    ok("K5 Rückgängig nimmt die Kopie samt Staffeln wieder weg")
    satz = next(r for r, p in enumerate(s.positionen) if p.get("satz") == "Rahmen")
    assert s.position_duplizieren([satz]) == 2
    neu = [p for p in s.positionen if p.get("satz") == "Rahmen (2)"]
    assert [p["artikel"] for p in neu] == ["4711-003-2", "4711-004-2"] and [p["je_satz"] for p in neu] == [3, 4]
    assert db.satz_daten(a)["Rahmen (2)"] == {"stoesse": [{"a": 1}]}
    assert sorted(z["menge"] for z in db.staffeln(a) if z["schluessel"] == "Rahmen (2)") == [2, 4, 8]
    assert s.positionen[-2]["satz"] == "Rahmen (2)" or s.positionen[-1]["satz"] == "Rahmen (2)"
    ok("K6 Ganzer Satz: neuer Satzname „Rahmen (2)“, Satz in 3D und Staffeln des Satzes mit")
    # aus einem anderen Angebot übernehmen (Baugruppe mit Teilen und eine Position), Quelle bleibt unverändert
    b = beispiel_baugruppe.anlegen(db)
    quelle_vorher = db.positionen(b)
    staffel_vorher = db.staffeln(b)
    n = len(s.positionen)
    letzte = max(p["pos"] for p in s.positionen)
    d_ok = []

    def bedienen(d):
        assert d.angebot_waehlen(b)
        assert [t[0] for _, t in zeilen_text(d.positionen)] == ["100", "10", "20", "30"]
        d.markieren([0])
        assert "4 Position(en)" in d.info.text()
        d._ok()
        d_ok.append(d)
        return QDialog.Accepted
    assert s.positionen_uebernehmen(dialog=bedienen) == 4
    neu = s.positionen[n:]
    assert [p["pos"] for p in neu] == [letzte + 10 * (k + 1) for k in range(4)]
    assert [p["artikel"] for p in neu] == ["R1", "Rohr", "Strebe", "Lasche"]
    bg = baugruppe.lesen(neu[0]["baugruppe"])
    assert all(baugruppe.zuordnung(p)[0] == bg["id"] for p in neu[1:])
    assert sorted(z["menge"] for z in db.staffeln(a) if z["schluessel"] == "Rahmen R1") == \
        sorted(z["menge"] for z in staffel_vorher)
    assert db.positionen(b) == quelle_vorher and db.staffeln(b) == staffel_vorher
    zeilen, _ = s._rechnung()[:2]
    assert len(zeilen) == len(s.positionen)
    ok("K7 Aus anderem Angebot: Baugruppe mit Teilen und Staffeln ans Ende, Quelle unverändert, rechnet")
    db.con.execute("UPDATE angebote SET fremd='MK' WHERE id=?", (b,))
    db.con.commit()
    assert s.positionen_uebernehmen(quelle=b, zeilen=[1], staffeln=False) == 1
    assert s.positionen[-1]["artikel"] == "Rohr" and "bg_knoten" not in {k for k, v in s.positionen[-1].items() if v}
    sb = f.angebot_oeffnen(b)
    assert sb.position_duplizieren([0]) == 0 and sb.positionen_uebernehmen(quelle=a, zeilen=[0]) == 0
    db.nur_lesen = "Test"
    try:
        assert s.position_duplizieren([0]) == 0
    finally:
        db.nur_lesen = False
    ok("K8 Fremdes Angebot als Quelle (nur gelesen), Einzelteil wird eigenständig; fremd/Lesemodus als Ziel gesperrt")
    # Rechtsklick, Kürzel, Neue Position
    s.pos_ansicht.selectRow(0)
    aktionen = s._pos_menue_anpassen()
    assert {"Position duplizieren", "Positionen aus anderem Angebot übernehmen …"} <= set(aktionen)
    assert f.kuerzel_aktionen["duplizieren"].shortcut().toString() == "Ctrl+Shift+D"
    f.show()
    f.reiter.setCurrentWidget(s)
    s.reiter.setCurrentWidget(s.pos_seite)
    s.pos_ansicht.setFocus()
    s.pos_ansicht.selectRow(0)
    app.processEvents()
    n = len(s.positionen)
    f.kuerzel("duplizieren")
    assert len(s.positionen) == n + 1
    assert neue_position.UEBERNEHMEN in [x.text() for x in neue_position.TypDialog().findChildren(QPushButton)]
    assert s.position_neu(typ=neue_position.UEBERNEHMEN, dialog=lambda d: QDialog.Rejected) is None
    d = UebernehmenDialog(s, db, a)
    assert all(x["id"] != a for x in d._liste) and not d.knoepfe.button(QDialogButtonBox.Ok).isEnabled()
    d.suche.setText("Strebe")
    assert [x["id"] for x in d._liste] == [b]
    ok("K9 Rechtsklick „Position duplizieren“/„Aus anderem Angebot …“, Strg+Umschalt+D, Neue Position → Aus anderem "
       "Angebot, Suche nach Artikel")
    for x in (s, sb):
        x.close()
    app.processEvents()


if __name__ == "__main__":
    k1_logik()
    k4_programm()
    print("Alle Prüfungen bestanden.")
