"""Einzelteile ↔ Satz ↔ Schweißbaugruppe umwandeln (Patrick 06.11.2026, Freigabe „Alle Empfehlungen“ F1a–F5a):
Satz bilden mit Anzahl Sätze (ggT), Satz auflösen, Satz → Schweißbaugruppe (Editor vorbelegt), Schweißbaugruppe →
Satz (gemerkter Stand, Unterbaugruppen flach) und zurück verlustfrei; Knöpfe in Satz in 3D, Satz bearbeiten und im
Editor der Baugruppe; Stückzahlen, Konturen und Lage der Teile bleiben, Rückgängig in einem Schritt.

Aufruf: python tests/test_umwandeln.py
"""
import json
import os
import sys
import tempfile
import time
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication, QDialogButtonBox  # noqa: E402

import beispiel_angebot  # noqa: E402
from rohrlaser import baugruppe, umwandeln  # noqa: E402
from rohrlaser.angebot import BAUGRUPPE, ist_baugruppe  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402

# bg_gravur: der Editor der Baugruppe trägt 0 = „nicht gravieren“ ein, wenn das Häkchen aus ist (wie beim Anlegen)
ZUORDNUNG = {"satz", "je_satz", "bg_knoten", "je_knoten", "bg_hilfe", "bg_gravur", "geaendert", "geaendert_am"}


def ok(t):
    print("OK    ", t)


# ------------------------------------------------------------------ U1 Rechnen ohne Oberfläche
P = [dict(id=1, pos=10, art="Rohr", stueck=4), dict(id=2, pos=20, art="Rohr", stueck=8),
     dict(id=3, pos=30, art="Rohr", stueck=12), dict(id=4, pos=40, art="Rohr", stueck=7, satz="Satz 1", je_satz=7),
     dict(id=5, pos=50, art=BAUGRUPPE, stueck=1, bezeichnung="Gestell", baugruppe=json.dumps(dict(id="b1"))),
     dict(id=6, pos=60, art="Rohr", stueck=2, bg_knoten="b1")]
assert umwandeln.satz_name_vorschlag(P) == "Satz 2"
assert umwandeln.saetze_vorschlag(P, [0, 1, 2]) == 4 and umwandeln.saetze_vorschlag(P, [0, 3]) == 1
assert umwandeln.satz_bilden_pruefen(P, [0, 1, 2], "Rahmen", 4) is None
assert "nicht in ganzen Stück" in umwandeln.satz_bilden_pruefen(P, [0, 1, 2], "Rahmen", 3)
assert "Schweißbaugruppe" in umwandeln.satz_bilden_pruefen(P, [0, 5], "Rahmen", 1)        # Teil einer Baugruppe
assert "Schweißbaugruppe" in umwandeln.satz_bilden_pruefen(P, [0], "Gestell", 1)          # Name belegt
assert "Namen" in umwandeln.satz_bilden_pruefen(P, [0], " ", 1)
a = umwandeln.satz_bilden(P, [0, 1, 2], "Rahmen", 4)
assert sorted(a) == sorted([(1, "satz", "Rahmen"), (1, "je_satz", 1), (2, "satz", "Rahmen"), (2, "je_satz", 2),
                            (3, "satz", "Rahmen"), (3, "je_satz", 3)]), a
assert not any(f == "stueck" for _, f, _ in a)
assert umwandeln.satz_aufloesen(P, "Satz 1") == [(4, "satz", None), (4, "je_satz", None)]
assert umwandeln.satz_aufloesen(P, "Gestell") == []          # Baugruppe: erst in einen Satz umwandeln
assert umwandeln.staffeln_hinweis([dict(schluessel="Satz 1"), dict(schluessel="Pos. 10")], "Satz 1")
assert umwandeln.staffeln_hinweis([dict(schluessel="Pos. 10")], "Satz 1") is None
ok("U1 Satz bilden (ggT 4, Stück je Satz 1/2/3, Stückzahl bleibt), Prüfungen, Satz auflösen, Hinweis Staffeln")

# Unterbaugruppe flach (F3a): Knoten k1 mit Menge 2, Teil 3 Stück je k1 → 6 je Satz; zurück verlustfrei
BG = dict(id="b2", stamm={}, knoten=[dict(id="k1", name="Seite", menge=2)], arbeitsgaenge=[dict(id="a1", name="Richten")],
          naehte=[dict(id="n1", name="Kehlnaht", laenge=100, anzahl=4)])
Q = [dict(id=10, pos=10, art=BAUGRUPPE, stueck=3, bezeichnung="Rahmen", artikel="R-1", baugruppe=json.dumps(BG),
          zeit_manuell=5),
     dict(id=11, pos=20, art="Rohr", stueck=9, bg_knoten="b2", je_knoten=3, satz="Rahmen", je_satz=3),
     dict(id=12, pos=30, art="Rohr", stueck=18, bg_knoten="b2/k1", je_knoten=3, satz="Rahmen", je_satz=6,
          bg_hilfe="Vorrichtung")]
e = umwandeln.bg_zu_satz(Q, "b2")
assert e["satz"] == "Rahmen" and e["loeschen"] == [10]
assert (12, "bg_knoten", None) in e["aenderungen"] and (12, "bg_hilfe", None) in e["aenderungen"]
assert not any(f in ("stueck", "je_satz") for _, f, _ in e["aenderungen"]), e["aenderungen"]
merk = e["daten"][umwandeln.MERK]
assert merk["baugruppe"]["naehte"][0]["id"] == "n1" and merk["position"]["zeit_manuell"] == 5
assert merk["teile"]["12"] == dict(bg_knoten="b2/k1", je_knoten=3, bg_hilfe="Vorrichtung", je_satz=6)
nach = [dict(q, **{f: w for pid, f, w in e["aenderungen"] if pid == q["id"]}) for q in Q[1:]]
assert [(q["satz"], q["je_satz"], q["stueck"], q.get("bg_knoten")) for q in nach] == [("Rahmen", 3, 9, None),
                                                                                       ("Rahmen", 6, 18, None)]
v = umwandeln.satz_zu_bg(nach, "Rahmen", e["daten"])
assert v["wieder"] and v["position"]["stueck"] == 3 and v["position"]["bezeichnung"] == "Rahmen"
assert v["vorwahl"] == {11: ("", 3, None), 12: ("k1", 3, "Vorrichtung")}, v["vorwahl"]
assert baugruppe.lesen(v["position"]["baugruppe"])["naehte"][0]["id"] == "n1" and v["extra"]["zeit_manuell"] == 5
nach[1].update(je_satz=4, stueck=12)                        # inzwischen geändert: direkt unter die Baugruppe
assert umwandeln.satz_zu_bg(nach, "Rahmen", e["daten"])["vorwahl"][12] == ("", 4, None)
nach[1]["stueck"] = 18                                       # 9 ÷ 3 = 3, 18 ÷ 4 = 4,5: keine ganze Anzahl Sätze
assert "keine ganze Anzahl" in umwandeln.satz_zu_bg_pruefen(nach, "Rahmen")
assert umwandeln.satz_zu_bg(nach, "Rahmen", e["daten"]) is None
ok("U2 Schweißbaugruppe → Satz: Unterbaugruppe flach (6 je Satz), Stückzahl bleibt, Stand gemerkt; zurück mit "
   "Knoten, Stück je Knoten und Positionierhilfe; geänderte Teile direkt unter die Baugruppe")

# ------------------------------------------------------------------ U3 im Programm
app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
aid = beispiel_angebot.anlegen(db)
rohre = [p for p in db.positionen(aid) if p.get("profil_id") and p.get("art") != "Zukaufteil"][:3]
for p, st in zip(rohre, (4, 8, 12)):
    db.position_aendern(p["id"], "stueck", st)
    db.position_aendern(p["id"], "satz", None)
    db.position_aendern(p["id"], "je_satz", None)
fenster = Hauptfenster(db, tmp, stumm=True)
s = fenster.angebot_oeffnen(aid)
ids = [p["id"] for p in rohre]


def zeilen():
    return [next(r for r, q in enumerate(s.positionen) if q["id"] == i) for i in ids]


def teile():
    return [next(q for q in s.positionen if q["id"] == i) for i in ids]


vorher = {q["id"]: {k: v for k, v in q.items() if k not in ZUORDNUNG} for q in teile()}


def unveraendert(t):
    for q in teile():
        jetzt = {k: v for k, v in q.items() if k not in ZUORDNUNG}
        assert jetzt == vorher[q["id"]], (t, {k: (vorher[q["id"]].get(k), v) for k, v in jetzt.items()
                                              if vorher[q["id"]].get(k) != v})


s.pos_ansicht.selectionModel().clearSelection()
s.pos_ansicht.selectRow(zeilen()[0])
sichtbar = s._pos_menue_anpassen()
assert "Als Satz zusammenfassen …" in sichtbar and "Schweißbaugruppe → Satz" not in sichtbar
assert "Satz auflösen (Einzelteile)" not in sichtbar


def satz_fenster(d):
    assert d.saetze_feld.value() == 4 and d.name_feld.text().startswith("Satz ")
    d.name_feld.setText("Rahmen")
    d.saetze_feld.setValue(3)
    assert not d.knoepfe.button(QDialogButtonBox.Ok).isEnabled() and "nicht in ganzen" in d.fehler.text()
    d.saetze_feld.setValue(4)
    assert d.tabelle.item(2, 3).text() == "3"
    d._ok()
    return d.result()


assert s.als_satz(zeilen(), dialog=satz_fenster) == "Rahmen"
assert [(q["satz"], q["je_satz"], q["stueck"]) for q in teile()] == [("Rahmen", 1, 4), ("Rahmen", 2, 8),
                                                                     ("Rahmen", 3, 12)]
unveraendert("Satz bilden")
s.rueckgaengig()
assert all(not q.get("satz") for q in teile()) and [q["stueck"] for q in teile()] == [4, 8, 12]
s.wiederholen()
assert all(q["satz"] == "Rahmen" for q in teile())
ok("U3 Rechtsklick „Als Satz zusammenfassen …“: Fenster (Vorschlag 4 Sätze, 3 geht nicht), Stückzahlen bleiben, "
   "ein Schritt Rückgängig")

# ------------------------------------------------------------------ U4 Satz → Schweißbaugruppe → Satz → Baugruppe
s.pos_ansicht.selectionModel().clearSelection()
s.pos_ansicht.selectRow(zeilen()[0])
sichtbar = s._pos_menue_anpassen()
assert {"Satz auflösen (Einzelteile)", "Satz → Schweißbaugruppe …"} <= set(sichtbar)
editor = []


def bg_ok(d):
    editor.append(d)
    assert d.anzahl.value() == 4 and d.bezeichnung.text() == "Rahmen"
    assert {t["_id"]: (t["drin"], t["je"]) for t in d.teile if t["_id"] in ids} == {
        ids[0]: (True, 1), ids[1]: (True, 2), ids[2]: (True, 3)}
    d._ok()
    return d.result()


assert s.satz_zu_bg(zeilen()[0], dialog=bg_ok)
bgs = baugruppe.baugruppen(s.positionen)
assert len(bgs) == 1
bg_id, (i_bg, bg) = next(iter(bgs.items()))
assert s.positionen[i_bg]["stueck"] == 4 and baugruppe.name(s.positionen[i_bg]) == "Rahmen"
assert [(q["bg_knoten"], q["je_knoten"], q["stueck"], q["satz"]) for q in teile()] == [
    (bg_id, 1, 4, "Rahmen"), (bg_id, 2, 8, "Rahmen"), (bg_id, 3, 12, "Rahmen")]
unveraendert("Satz → Baugruppe")
# Naht, Arbeitsgang und Unterbaugruppe dazu (wie im Editor), dann zurück in einen Satz
bg["naehte"] = [dict(id="n9", name="Kehlnaht", laenge=50, anzahl=2)]
bg["arbeitsgaenge"] = [dict(id="a9", name="Richten", zeit=3)]
bg["knoten"] = [dict(id="k9", name="Seite", menge=2)]
db.position_aendern(s.positionen[i_bg]["id"], "baugruppe", baugruppe.speichern(bg))
db.position_aendern(s.positionen[i_bg]["id"], "zeit_manuell", 7)
db.position_aendern(ids[2], "bg_knoten", f"{bg_id}/k9")
db.position_aendern(ids[2], "je_knoten", 1)       # 1 je Seite × 2 Seiten = 2 je Baugruppe → 8 Stück
s.neu_laden()
assert teile()[2]["je_satz"] == 2 and teile()[2]["stueck"] == 8
vorher[ids[2]]["stueck"] = 8
s.pos_ansicht.selectionModel().clearSelection()
s.pos_ansicht.selectRow(zeilen()[1])
assert "Schweißbaugruppe → Satz" in s._pos_menue_anpassen()
assert s.bg_zu_satz([zeilen()[1]]) == "Rahmen"
assert not baugruppe.baugruppen(s.positionen) and not any(ist_baugruppe(q) for q in s.positionen)
assert [(q["satz"], q["je_satz"], q["stueck"], q.get("bg_knoten")) for q in teile()] == [
    ("Rahmen", 1, 4, None), ("Rahmen", 2, 8, None), ("Rahmen", 2, 8, None)]
unveraendert("Baugruppe → Satz")
merk = db.satz_daten(aid)["Rahmen"][umwandeln.MERK]
assert merk["baugruppe"]["naehte"][0]["id"] == "n9" and merk["position"]["zeit_manuell"] == 7
time.sleep(1.1)        # Sekundenwechsel: vk_am (Zeitpunkt des Verkaufspreises) ist kein Schritt (14.11.2026)
s.rueckgaengig()
assert baugruppe.baugruppen(s.positionen) and umwandeln.MERK not in (db.satz_daten(aid).get("Rahmen") or {})
s.wiederholen()
assert not baugruppe.baugruppen(s.positionen)


def bg_wieder(d):
    t = {t["_id"]: (t["knoten"], t["je"]) for t in d.teile if t["_id"] in ids}
    assert t == {ids[0]: ("", 1), ids[1]: ("", 2), ids[2]: ("k9", 1)}, t
    assert [n["id"] for n in d.bg["naehte"]] == ["n9"] and [k["id"] for k in d.bg["knoten"]] == ["k9"]
    d._ok()
    return d.result()


assert s.satz_zu_bg(satz="Rahmen", dialog=bg_wieder)
(bg_id2, (i_bg, bg2)), = baugruppe.baugruppen(s.positionen).items()
assert [n["id"] for n in bg2["naehte"]] == ["n9"] and [a_["id"] for a_ in bg2["arbeitsgaenge"]
                                                         if not a_.get("vk")] == ["a9"]     # ohne Vorschläge (A2)
assert s.positionen[i_bg]["zeit_manuell"] == 7 and s.positionen[i_bg]["stueck"] == 4
assert [(q["je_knoten"], q["stueck"]) for q in teile()] == [(1, 4), (2, 8), (1, 8)]
assert umwandeln.MERK not in (db.satz_daten(aid).get("Rahmen") or {})
unveraendert("Satz → Baugruppe (wieder)")
ok("U4 Satz → Schweißbaugruppe (Editor vorbelegt) → Satz (Unterbaugruppe flach, gemerkt) → Baugruppe mit Nähten, "
   "Arbeitsgängen, Knoten und Feldern wieder; Rückgängig je ein Schritt")

# ------------------------------------------------------------------ U5 Knöpfe in den Editoren
def bg_aufloesen(d):
    assert set(d.umwandeln_knoepfe) == {"satz", "auf"} and d.umwandeln_knoepfe["auf"].isEnabled()
    d.umwandeln_knoepfe["auf"].click()
    return d.result()


assert s.baugruppe_bearbeiten([zeilen()[0]], dialog=bg_aufloesen)
assert not baugruppe.baugruppen(s.positionen)
assert [(q.get("satz"), q.get("je_satz"), q["stueck"], q.get("bg_knoten")) for q in teile()] == [
    (None, None, 4, None), (None, None, 8, None), (None, None, 8, None)]
unveraendert("Editor Baugruppe → Einzelteile")
assert s.als_satz(zeilen(), name="Regal", saetze=4) == "Regal"


def satz3d_bg(d):
    assert set(d.umwandeln_knoepfe) == {"bg", "auf"}
    d.umwandeln_knoepfe["bg"].click()
    return d.result()


s.umwandeln_folge = lambda d: (d._ok(), d.result())[1]
assert s.satz_3d(satz="Regal", dialog=satz3d_bg)
(_, (i_bg, _)), = baugruppe.baugruppen(s.positionen).items()
assert s.positionen[i_bg]["stueck"] == 4 and baugruppe.name(s.positionen[i_bg]) == "Regal"


def bg_satz(d):
    d.umwandeln_knoepfe["satz"].click()
    return d.result()


assert s.baugruppe_bearbeiten([i_bg], dialog=bg_satz)
assert not baugruppe.baugruppen(s.positionen) and all(q["satz"] == "Regal" for q in teile())


def satz_dialog_auf(d):
    d.umwandeln_knoepfe["auf"].click()
    return d.result()


assert s.satz_bearbeiten(satz="Regal", dialog=satz_dialog_auf)
assert all(not q.get("satz") for q in teile()) and [q["stueck"] for q in teile()] == [4, 8, 8]
unveraendert("Editoren")
ok("U5 Knöpfe: Editor der Baugruppe „In Einzelteile auflösen“/„In Satz umwandeln“, Satz in 3D „In "
   "Schweißbaugruppe umwandeln …“, Satz bearbeiten „Satz auflösen“")
print("OK: Einzelteile, Sätze und Schweißbaugruppen umwandeln")
