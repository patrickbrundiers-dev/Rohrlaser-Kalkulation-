"""Einzelteile aufräumen und Vorschläge für alle Teile bestätigen (Patrick 04.11.2026: „Weiter aufräumen auch für
Einzelteile“, „Option, die Zusatzarbeiten bei allen Teilen im Angebot zu bestätigen oder abzulehnen“, Freigabe „Alle
Empfehlungen“ F1a F2a F3a F4a): graues Kopfband „Einzelteile“ mit Summen, zugeklappte Gruppe = nur das Band, Zeilenkopf
ohne laufende Nummer, Status nur Symbol, Stück je Satz nur mit Sätzen; gelber Knopf je Zusatzarbeit „für alle
übernehmen/ablehnen“, ✓/✗ in der Zelle, Prüffenster mit nur offenen Punkten und „Alle … annehmen“.

Aufruf: python tests/test_einzelteile_vorschlaege.py
"""
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QEvent, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QMouseEvent  # noqa: E402
from PySide6.QtWidgets import QApplication, QStyleOptionViewItem  # noqa: E402

import beispiel_angebot  # noqa: E402
from rohrlaser import arbeitsgaenge as ag, rechnen, satzgruppen  # noqa: E402
from rohrlaser.angebot_fenster import kopf_zeichen  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def ok(t):
    print("OK    ", t)


# ------------------------------------------------------------------ E1 ohne Oberfläche
pos = [dict(satz="A"), dict(), dict(), dict(satz="A"), dict(), dict(satz="B")]
folge = satzgruppen.ordnen(list(range(6)), satzgruppen.saetze(pos))
assert folge == [0, 3, 1, 2, 4, 5]
assert satzgruppen.einzel_laeufe(pos, folge) == [[1, 2, 4]]
assert satzgruppen.einzel_laeufe([dict(), dict()], [0, 1]) == []          # ohne Gruppen kein Band
assert satzgruppen.einzel_laeufe(pos, [1, 0, 3, 2, 4, 5]) == [[1], [2, 4]]  # Reihenfolge bleibt, je Abschnitt ein Band
b = satzgruppen.einzel_band([dict(stueck=4, id=7), dict(stueck=6, id=8)], [0, 1],
                            [dict(preis_position=10), dict(preis_position=5.5)], zu=True,
                            vorschlaege=[[dict(name="X")], [dict(name="X"), dict(name="Y")]])
assert b["titel"] == "▸ Einzelteile" and b["zu"] and b["id"] == 7 and b["art"] == "einzel", b
assert b["info"] == "2 Positionen · 10 Stk. · 15,50 € gesamt · 3 Vorschläge offen", b["info"]
assert not satzgruppen.einzel_band([dict(stueck=1, id=1)], [0], zu=True)["zu"]      # ein Teil: nichts zuzuklappen
assert kopf_zeichen("▾ 12") == "▾" and kopf_zeichen("└ 3") == "└" and kopf_zeichen("7") == "" and kopf_zeichen(None) == ""
ok("E1 Einzelteile-Abschnitte zwischen Sätzen, Band mit Positionen, Stück, €, Vorschlägen; Zeilenkopf ohne Nummer")

# ------------------------------------------------------------------ E2 Positionsliste
app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
aid = beispiel_angebot.anlegen(db)
rohre = [p for p in db.positionen(aid) if p.get("profil_id") and p.get("art") != "Zukaufteil"]
assert len(rohre) >= 5, len(rohre)
for p in rohre[:2]:
    db.position_aendern(p["id"], "satz", "Regal")
    db.position_aendern(p["id"], "je_satz", 1)
for p, bez in zip(rohre[2:5], ("Halter verzinkt", "Lasche verzinkt", "Konsole pulverbeschichtet")):
    db.position_aendern(p["id"], "bezeichnung", bez)
    db.position_aendern(p["id"], "zusatz", None)
    db.position_aendern(p["id"], "satz", None)
fenster = Hauptfenster(db, tmp, stumm=True)
s = fenster.angebot_oeffnen(aid)
QApplication.processEvents()
m = s.pos_modell
assert s.einzel_laeufe, "Einzelteile ohne Band"
kopf = s.einzel_laeufe[0][0]
band = s.kopf_baender[kopf]
assert band["art"] == "einzel" and band["titel"] == "▾ Einzelteile" and "Vorschläge offen" in band["info"], band
assert m.headerData(kopf, Qt.Vertical) in ("▾", "") and all(
    m.headerData(r, Qt.Vertical) in ("▾", "▸", "│", "└", "") for r in range(m.rowCount()))
c_je = next(c for c in range(m.columnCount()) if m.name(c) == "je_satz")
assert not s.pos_ansicht.isColumnHidden(c_je)                     # Angebot mit Satz: Stück je Satz sichtbar
c_st = next(c for c in range(m.columnCount()) if m.spalten[c][0] == "status")
for r in range(m.rowCount()):
    w = m.data(m.index(r, c_st), Qt.ItemDataRole.UserRole)
    if m.data(m.index(r, c_st), Qt.ItemDataRole.DecorationRole) is not None:
        assert m.data(m.index(r, c_st)) == "", (r, w)                 # nur Symbol, Text im Tooltip
        assert m.data(m.index(r, c_st), Qt.ItemDataRole.ToolTipRole)
lauf = s.einzel_laeufe[0]
assert len(lauf) > 1, s.einzel_laeufe
s.band_klick(kopf, "klick", 10)                                # ▸: zuklappen
QApplication.processEvents()
assert all(s.pos_ansicht.isRowHidden(r) for r in lauf[1:]) and not s.pos_ansicht.isRowHidden(kopf)
assert s.kopf_baender[kopf]["zu"] and s.pos_unter.kopf_zu(kopf) and s.pos_unter.hoehe(kopf) == 0
assert db.einstellung("ansicht_gruppen_zu")[str(aid)]["einzel"] == [s.positionen[kopf]["id"]]
s.gruppen_alle(False)
assert not s.einzel_zu and not any(s.pos_ansicht.isRowHidden(r) for r in lauf)
s.band_klick(kopf, "rechts", 99)                               # markiert den ganzen Abschnitt
assert sorted({i.row() for i in s.pos_ansicht.selectionModel().selectedRows()}) == sorted(lauf)
ok("E2 Band Einzelteile, zuklappen = nur Band (gemerkt), alle Gruppen, Zeilenkopf ohne Nummer, Status nur Symbol")

# ------------------------------------------------------------------ E3 Vorschläge je Zusatzarbeit für alle Teile
je_name = s.vorschlaege_je_name()
assert "Feuerverzinken" in je_name and len(je_name["Feuerverzinken"]) == 2, je_name
texte = [e[0] for e in s.vorschlag_menue_aktionen() if e]
assert any(t.startswith("Feuerverzinken · 2 Teile") for t in texte) and "    ✓ für alle übernehmen" in texte, texte
s._vorschlag_menue_fuellen()
assert any(a.text() == "Alle Vorschläge übernehmen" for a in s.vorschlag_menue.actions())
zeilen_fvz = list(je_name["Feuerverzinken"])
assert s.vorschlaege_uebernehmen(namen={"Feuerverzinken"}) == 2
for r in zeilen_fvz:
    assert "Feuerverzinken" in [x["name"] for x in rechnen.zusatz_liste(s.positionen[r])]
assert "Feuerverzinken" not in s.vorschlaege_je_name()
rest = s.vorschlaege_je_name()
assert rest, "Pulverbeschichten-Vorschlag fehlt"
name, zeilen = next(iter(rest.items()))
assert s.vorschlaege_ablehnen(namen={name}) == len(zeilen)
assert name not in s.vorschlaege_je_name()
assert all(name in ag.lesen(s.positionen[r])["abgelehnt"] for r in zeilen)
ok("E3 gelber Knopf: je Zusatzarbeit für alle übernehmen bzw. ablehnen, Rest bleibt offen")

# ------------------------------------------------------------------ E4 ✓/✗ in der Zelle
db.position_aendern(s.positionen[zeilen[0]]["id"], "arbeitsgaenge", None)      # Ablehnung zurück: wieder offen
s.neu_laden()
QApplication.processEvents()
r = next(r for r, vs in enumerate(m.vorschlaege) if vs)
c_z = next(c for c in range(m.columnCount()) if m.spalten[c][0] == "zusatz")
s.pos_ansicht.setColumnHidden(c_z, False)
s.pos_ansicht.setColumnWidth(c_z, 220)
d = s.pos_ansicht.itemDelegate()
o = QStyleOptionViewItem()
o.rect = s.pos_ansicht.visualRect(m.index(r, c_z))
o.font = s.pos_ansicht.font()
k = d.vorschlag_knoepfe(o, m.index(r, c_z))
assert k and k[0].right() < k[1].left() and o.rect.contains(k[1]), (k, o.rect)
assert d.vorschlag_knoepfe(o, m.index(r, c_st)) is None
ziel = k[1].center()
for t in (QEvent.MouseButtonPress, QEvent.MouseButtonRelease):
    e = QMouseEvent(t, QPointF(ziel), QPointF(ziel), Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
    assert d.editorEvent(e, m, o, m.index(r, c_z))
assert not m.vorschlaege[r] and ag.lesen(s.positionen[r])["abgelehnt"], "✗ hat nicht abgelehnt"
ok("E4 ✓/✗ rechts in der Zelle Gewinde · Zusatzarbeiten: Vorschläge der Position annehmen bzw. ablehnen")

# ------------------------------------------------------------------ E5 Prüffenster
for p in s.positionen:
    if p.get("arbeitsgaenge"):
        db.position_aendern(p["id"], "arbeitsgaenge", None)
s.neu_laden()
dlg = s.arbeitsgaenge_vorschlagen(dialog=lambda d: None)
assert dlg.zeilen and all(z["status"] != ag.IM_ANGEBOT for z in dlg.zeilen)       # nur offene Punkte
namen = [z["arbeitsgang"] for z in dlg.zeilen]
assert namen == sorted(namen, key=namen.index), namen                              # gleiche untereinander
dlg.alle_zeigen.setChecked(True)
assert any(z["status"] == ag.IM_ANGEBOT for z in dlg.zeilen)
dlg.alle_zeigen.setChecked(False)
offen = [z for z in dlg.zeilen if z["status"] == ag.VORSCHLAG]
name = offen[0]["arbeitsgang"]
gleiche = [z for z in offen if z["arbeitsgang"] == name]
dlg.waehlen(offen[0]["position_id"], name)
assert len(dlg.gleiche()) == len(gleiche)
if len(gleiche) > 1:
    assert not dlg.alle_ja_knopf.isHidden() and dlg.alle_ja_knopf.text().startswith(f"Alle {len(gleiche)} „{name}“")
assert dlg.alle_gleichen(True) == len(gleiche)
assert not any(z["arbeitsgang"] == name and z["status"] == ag.VORSCHLAG for z in dlg.alle_zeilen)
ok("E5 Prüffenster: nur offene Punkte, nach Arbeitsgang, „Alle … annehmen“ für alle Positionen")
print("OK: Einzelteile und Vorschläge")
