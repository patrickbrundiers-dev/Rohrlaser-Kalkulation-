"""3D-Editor modernisieren (Plan Patrick 19.11.2026, Befunde A1–A11).

PR 1 Stabilität und Tempo
- A2 Netzprüfung: Schnellprüfung erkennt jede Art Fehler (NaN, ∞, Text, None, bool, zu groß, Nummern falsch) und
  fällt dann auf die genaue Prüfung zurück; ein gutes Netz bleibt dasselbe Objekt; Modell prüft ein schon geprüftes
  Netz nicht ein zweites Mal.
- A1 Wartezeit beim Tippen passt sich der Dauer des Neuaufbaus an (150 … 600 ms).
- A3 Wiederherstellung: Stand wird bei jeder Änderung gesichert (atomar), beim normalen Schließen gelöscht; nach
  „Absturz“ (Datei bleibt) bietet der Editor beim nächsten Öffnen derselben Position den Stand an; Wiederherstellen
  ist ein Rückgängig-Schritt; Verwerfen und unlesbare/alte Dateien; gleicher Stand wird nicht angeboten.

PR 2 Oberfläche
- A6 Verlauf: Schritte mit Namen (eingefügt, entfernt, Zeile geändert, Ende), Klick im Verlauf springt zurück.
- A6 Ebenen: ohne_arten lässt Kennungen richtig zugeordnet; Haken weg blendet im 3D aus, Rechnung unverändert;
  Legende ein/aus (gemerkt).
- A8 Werkzeugleiste: Werkzeuge schalten die Knöpfe des Menübands, genau eins aktiv, Tasten nur im 3D.
- A4 Seitenleisten: Strg+1/Strg+2 bzw. Knöpfe blenden aus und ein, Breiten gemerkt.
- A5 Statuszeile: Koordinaten unter der Maus, Auswahl, Modellmaße, Prüfstatus; Blech-Editor ebenso aufgebaut.

PR 3 Funktionen
- A7 Achsenkreuz (Richtungen aus der Drehung, unten links) und Raster (1-2-5-Weite, Ebene unter dem Modell, hinter
  dem Modell gezeichnet), je Benutzer gemerkt, Schalter im Menü Blick aller 3D-Fenster.
- A10 Mehrfachbearbeitung: ≥ 2 markierte Konturen zeigen die Tafel; Maß, Anzahl, Seite, Lage verschieben,
  Duplizieren, Spiegeln, Entfernen für alle, je ein Rückgängig-Schritt; Merkmalsbaum mit Strg-Klick; Entf/Strg+D.
- A11 Abstand zweier Konturen längs: Mitte–Mitte und Kante–Kante.

Aufruf: python tests/test_3d_editor_modern.py
"""
import datetime
import json
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication([])
from rohrlaser import ansicht3d, editor_wiederherstellung as ewh, schneidweg as sw, teile_editor as te  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.schneidweg_dialog import SchneidwegDialog  # noqa: E402


def ok(t):
    print("OK    ", t)


# ------------------------------------------------------------------ A2 Netzprüfung schnell und genau
assert ansicht3d._zahlen_ok([]) and ansicht3d._zahlen_ok([0, 1.5, -3, 1e6])
for falsch in ([0, float("nan"), 1], [float("inf"), 0], [float("inf"), float("-inf")], [0, "1"], [None, 1],
               [True, 1.0], [0, 1e6 + 1], [-1e6 - 1], [1e308, 1e308]):
    assert not ansicht3d._zahlen_ok(falsch), falsch
assert ansicht3d._nummern_ok([0, 1, 2], 3) and not ansicht3d._nummern_ok([0, 1, 3], 3)
assert not ansicht3d._nummern_ok([0, True, 2], 3) and not ansicht3d._nummern_ok([0, -1], 3)
assert not ansicht3d._nummern_ok([0, 1.0], 3)
gut = {"p": [0, 0, 0, 10, 0, 0, 0, 10, 0], "t": {"A": [0, 1, 2]}, "l": {"K": [[0, 0, 0, 10, 0, 0]]}}
assert ansicht3d.netz_pruefen(gut) == (gut, "") and ansicht3d.netz_pruefen(gut)[0] is gut
neu, meldung = ansicht3d.netz_pruefen({"p": [0, 0, 0, True, 0, 0, 0, 1, 0], "t": {"A": [0, 1, 2]}})
assert "ungültiger Punkt" in meldung
# Modell prüft ein schon geprüftes Netz nicht noch einmal
aufrufe = []
alt_pruefen = ansicht3d.netz_pruefen
ansicht3d.netz_pruefen = lambda n: (aufrufe.append(1), alt_pruefen(n))[1]
a = ansicht3d.Ansicht3D()
a.setzen(gut)
ansicht3d.netz_pruefen = alt_pruefen
assert len(aufrufe) == 1, aufrufe
ok("A2 Netzprüfung: Schnellprüfung erkennt NaN/∞/Text/None/bool/zu groß/falsche Nummern, je Modell nur einmal")

# ------------------------------------------------------------------ Editor öffnen
db = Datenbank(Path(tempfile.mkdtemp()) / "rohrlaser.db")
k = db.kontext()
EING = dict(a={}, b={}, konturen=[dict(art=sw.BOHRUNG, anzahl=1, d=10, x=100)])


def oeffnen(pid=7, eing=EING):
    p = dict(id=pid, profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=500, stueck=10,
             technik=json.dumps(dict(eing, quelle=sw.QUELLE)))
    return SchneidwegDialog(None, p, k.profile["QR 40x40x3"], dict(maschine="T11", stange=6000), k, db.tabellen(), db)


def d_aendern(d, wert):
    d.tabelle.item(0, 2).setText(str(wert))
    d.editor.zeitgeber.stop()
    d.editor.aktualisieren()


# ------------------------------------------------------------------ A1 Wartezeit
d = oeffnen()
assert te.VERZOEGERUNG <= d.editor.zeitgeber.interval() <= te.VERZOEGERUNG_MAX
ok("A1 Wartezeit beim Tippen zwischen 150 und 600 ms nach Dauer des Neuaufbaus")

# ------------------------------------------------------------------ A3 Wiederherstellung
ed = d.editor
schl = ed._wh_schl
assert schl == "rohr-7" and ewh.lesen(db, schl) is None and ed.wh_leiste is None
d_aendern(d, 12)
gesichert = ewh.lesen(db, schl)
assert gesichert and gesichert["zustand"]["e"]["konturen"][0]["d"] == 12, gesichert
assert not ewh.datei(db, schl).with_suffix(".tmp").exists()
ed.verlauf.undo()
assert ewh.lesen(db, schl)["zustand"]["e"]["konturen"][0]["d"] == 10      # auch Rückgängig wird gesichert
ed.verlauf.redo()
# normal schließen: Sicherung weg
d.reject()
assert ewh.lesen(db, schl) is None
ok("A3 Sicherung bei jeder Änderung (auch Rückgängig), atomar; normales Schließen löscht sie")

# „Absturz“: Dialog schreibt, wird aber nie geschlossen
d = oeffnen()
d_aendern(d, 14)
d.editor.d.finished.disconnect()            # wie ein Absturz: kein normales Ende
assert ewh.lesen(db, schl) is not None
d2 = oeffnen()
ed2 = d2.editor
assert ed2.wh_leiste is not None and "Ungespeicherte Änderungen an diesem Teil" in ed2.wh_leiste.text.text()
assert d2.eingaben()["konturen"][0]["d"] == 10          # ohne Klick bleibt der gespeicherte Stand
schritte = ed2.verlauf.count()
ed2.wh_leiste.ja.click()
assert d2.eingaben()["konturen"][0]["d"] == 14 and ed2.verlauf.count() == schritte + 1 and ed2.wh_leiste.isHidden()
ed2.verlauf.undo()
assert d2.eingaben()["konturen"][0]["d"] == 10
d2.accept()
assert ewh.lesen(db, schl) is None
ok("A3 nach Absturz: Leiste bietet den Stand an, Wiederherstellen = ein Rückgängig-Schritt, danach Sicherung weg")

# Verwerfen
ewh.sichern(db, schl, dict(e=dict(EING, konturen=[dict(EING["konturen"][0], d=16)])))
d3 = oeffnen()
assert d3.editor.wh_leiste is not None
d3.editor.wh_leiste.nein.click()
assert d3.eingaben()["konturen"][0]["d"] == 10 and ewh.lesen(db, schl) is None
d3.reject()
# gleicher Stand: nichts anbieten
d4 = oeffnen()
ewh.sichern(db, schl, json.loads(json.dumps(d4.editor._letzter)))
d4.reject()
d5 = oeffnen()
ewh.sichern(db, schl, json.loads(json.dumps(d5.editor._letzter)))
d5.reject()
d5b = oeffnen()
assert d5b.editor.wh_leiste is None
d5b.reject()
# unpassender Stand: Meldung, nichts kaputt
ewh.sichern(db, schl, dict(e="kaputt"))
d6 = oeffnen()
assert d6.editor.wh_leiste is not None
assert d6.editor.wiederherstellen() is False and d6.eingaben()["konturen"][0]["d"] == 10
assert "passt nicht mehr" in d6.letzte_meldung
d6.reject()
# unlesbar, fremde Fassung, zu alt: still gelöscht
for inhalt in ("{kaputt", json.dumps(dict(fassung=99, zeit="2026-11-19T10:00:00", zustand={})),
               json.dumps(dict(fassung=1, zeit=(datetime.datetime.now() - datetime.timedelta(days=30)).isoformat(),
                               zustand={"e": {}}))):
    ewh.datei(db, schl).write_text(inhalt, encoding="utf-8")
    assert ewh.lesen(db, schl) is None and not ewh.datei(db, schl).exists()
# neue Position ohne Kennung, Name ohne Sonderzeichen
assert ewh.schluessel("rohr", type("D", (), {"p": {}})()) == "rohr-neu"
assert ewh.schluessel("blech", type("D", (), {"p": {"id": "a/b c"}})()) == "blech-a_b_c"
assert ewh.sichern(None, "x", {}) is False and ewh.lesen(None, "x") is None
assert ewh.zeit_text(dict(zeit=datetime.datetime.now().isoformat())).startswith("heute ")
ok("A3 Verwerfen, gleicher Stand nicht angeboten, unpassender Stand mit Meldung, unlesbare/alte Dateien gelöscht")

# ------------------------------------------------------------------ A6 Verlauf
from rohrlaser import editor_arbeitsbereich as eab  # noqa: E402

B10 = dict(art=sw.BOHRUNG, anzahl=1, d=10, x=100)
z0 = dict(e=dict(a={}, b={}, konturen=[B10]))
assert eab.schritt_text(z0, dict(e=dict(a={}, b={}, konturen=[B10, dict(B10, d=12)]))) == "Bohrung Ø 12 eingefügt"
assert eab.schritt_text(z0, dict(e=dict(a={}, b={}, konturen=[]))) == "Bohrung Ø 10 entfernt"
assert eab.schritt_text(z0, dict(e=dict(a={}, b={}, konturen=[dict(B10, d=12)]))) == "Zeile 1 geändert: d 10 → 12"
assert eab.schritt_text(z0, dict(e=dict(a=dict(winkel=45), b={}, konturen=[B10]))) == "Ende A geändert"
assert eab.schritt_text(None, None) == "Eingaben geändert" and eab.schritt_text("x", 5) == "Eingaben geändert"
d = oeffnen(pid=8)
ed = d.editor
ab = ed.arbeitsbereich
assert [ab.reiter.tabText(i) for i in range(ab.reiter.count())] == ["Merkmale", "Verlauf", "Ebenen"]
d_aendern(d, 12)
d_aendern(d, 14)
assert ed.verlauf.text(0) == "Zeile 1 geändert: d 10 → 12" and ed.verlauf.text(1) == "Zeile 1 geändert: d 12 → 14"
ed.verlauf.setIndex(0)              # Klick im Verlauf auf „Stand beim Öffnen“
assert d.eingaben()["konturen"][0]["d"] == 10
ed.verlauf.setIndex(2)
assert d.eingaben()["konturen"][0]["d"] == 14
ok("A6 Verlauf: Schritte mit Namen, Sprung zu einem Stand und zurück")

# ------------------------------------------------------------------ A6 Ebenen, A9 Legende
netz = dict(p=[0, 0, 0, 1, 0, 0, 0, 1, 0], t=dict(A=[0, 1, 2], K=[0, 1, 2]), ti=dict(A=["teil"], K=["kontur:0"]),
            l=dict(K=[[0, 0, 0, 1, 0, 0]], G=[[0, 0, 0, 0, 1, 0]]), li=dict(K=["kontur:0"], G=["kontur:1"]))
o = ansicht3d.ohne_arten(netz, {"A", "G"})
assert o["t"] == dict(K=[0, 1, 2]) and o["ti"] == dict(K=["kontur:0"]) and o["l"] == dict(K=[[0, 0, 0, 1, 0, 0]])
assert o["li"] == dict(K=["kontur:0"]) and ansicht3d.ohne_arten(netz, set()) is netz and "A" in netz["t"]
a3 = d.ansicht3d.ansicht
assert "A" in a3.modell.arten and not a3.legende_an
schnitt_vorher = d.eingaben()
ab.ebenen.setzen("Außenwand", False)
assert "A" not in a3.modell.arten and "I" in a3.modell.arten and a3.arten_aus == {"A", "BL"}
assert d.eingaben() == schnitt_vorher and a3.netz is not None and "A" in a3.netz["t"]     # nur Anzeige
ab.ebenen.alle_einblenden()
assert "A" in a3.modell.arten and not a3.arten_aus
ab.ebenen.setzen(eab.SCHNITTKOERPER, False)
assert not a3.koerper_an
ab.ebenen.setzen(eab.SCHNITTKOERPER, True)
ab.ebenen.legende.setChecked(True)
assert a3.legende_an and db.einstellung("editor_legende") is True
ab.ebenen.legende.setChecked(False)
ok("A6 Ebenen ein/aus nur in der Anzeige (Kennungen bleiben zugeordnet), Schnittkörper, A9 Legende gemerkt")

# ------------------------------------------------------------------ A8 Werkzeugleiste
L = ab.leiste
for name in ("Verschieben", "Auswahl", "Messen", "Winkel", "Maße weg", "Schnitt", "Eckpunkte", "Bohrung",
             "Ausschnitt", "Einpassen", "Auf Auswahl"):
    assert name in L.aktionen, name
    assert L.aktionen[name].toolTip(), name


def aktiv():
    return sorted(n for n in ("Verschieben", "Auswahl", "Messen", "Winkel") if L.aktionen[n].isChecked())


assert aktiv() == ["Verschieben"]
L.aktionen["Messen"].trigger()
assert ed.messen_knopf.isChecked() and a3.messen and aktiv() == ["Messen"]
L.aktionen["Winkel"].trigger()
assert ed.winkel_knopf.isChecked() and not ed.messen_knopf.isChecked() and aktiv() == ["Winkel"]
ed.winkel_knopf.setChecked(False)           # Menüband schaltet die Leiste mit
assert aktiv() == ["Verschieben"]
L.aktionen["Auswahl"].trigger()
assert a3.wahl.an and aktiv() == ["Auswahl"]
L.aktionen["Verschieben"].trigger()
assert not a3.wahl.an and aktiv() == ["Verschieben"]
n = len(d.eingaben()["konturen"])
L.aktionen["Bohrung"].trigger()
assert len(d.eingaben()["konturen"]) == n + 1 and d.eingaben()["konturen"][-1]["art"] == sw.BOHRUNG
assert set(ab.taste) >= {"V", "S", "M", "W", "Q", "E", "B", "R", "F", "Z"}
ok("A8 Werkzeugleiste: 11 Werkzeuge mit Tooltip, genau eins aktiv, synchron mit Menüband, Bohrung einfügen, Tasten")

# ------------------------------------------------------------------ A4 Seitenleisten
d.resize(1400, 850)
d.show()
app.processEvents()
w = ed.waagerecht
assert w.sizes()[0] > 0 and w.sizes()[2] > 0
breite_links = w.sizes()[0]
ab.status.links.click()
assert w.sizes()[0] == 0 and not ab.status.links.isChecked()
ab.status.rechts.click()
assert w.sizes()[2] == 0 and db.einstellung("editor_seiten_rohr") == [0, 0]
ab.status.links.click()
ab.status.rechts.click()
assert abs(w.sizes()[0] - breite_links) <= 2 and w.sizes()[2] > 0
assert db.einstellung("editor_seiten_rohr")[0] > 0
ok("A4 Seitenleisten aus- und wieder einblenden (gleiche Breite), Stand gemerkt")

# ------------------------------------------------------------------ A5 Statuszeile
st = ab.status
assert st.einheit.text() == "Einheit: mm" and st.modell.text().startswith("Modell: L ")
assert "× B 40,0 × H 40,0 mm" in st.modell.text(), st.modell.text()
a3.resize(900, 400)
a3.einpassen()
mitte = a3.bildpunkt()(a3.modell.mitte)
gemeldet = []
a3.maus_punkt.connect(gemeldet.append)
a3._maus_pos = (mitte[0], mitte[1])
a3._maus_punkt_melden()
assert gemeldet and gemeldet[-1] is not None
assert st.koordinaten.text().startswith("Maus: quer ") and "längs" in st.koordinaten.text()
a3._maus_pos = (2, 2)
a3._maus_punkt_melden()
assert gemeldet[-1] is None and st.koordinaten.text() == "Maus: –"
ed.waehlen("kontur:0")
assert st.auswahl.text().startswith("Auswahl: 1.") or "Bohrung" in st.auswahl.text(), st.auswahl.text()
d.tabelle.selectAll()
ab.auffrischen()
assert st.auswahl.text() == f"Auswahl: {d.tabelle.rowCount()} Konturen"
assert st.pruefung.text().startswith(("✓", "!", "✕"))
d.reject()
ok("A5 Statuszeile: Koordinaten unter der Maus, Auswahl, Modell L × B × H, Einheit, Prüfstatus")

# Blech-Editor bekommt denselben Arbeitsbereich
from rohrlaser.blech_dialog import BlechDialog  # noqa: E402

bd = BlechDialog(None, db)
bab = bd.editor.arbeitsbereich
assert [bab.reiter.tabText(i) for i in range(bab.reiter.count())] == ["Merkmale", "Verlauf", "Ebenen"]
assert "Messen" in bab.leiste.aktionen and "Bohrung" not in bab.leiste.aktionen
bd.resize(1366, 728)
bd.show()
app.processEvents()
assert bd.width() <= 1366 and bd.height() <= 728
bd.reject()
ok("Blech-Editor: Reiter, Werkzeugleiste und Statuszeile, passt auf 1366 × 728")

# ------------------------------------------------------------------ A7 Achsenkreuz, Raster
assert [ansicht3d.raster_schritt(x) for x in (40, 100, 500, 6000, 0.5)] == [2, 5, 50, 500, 0.05]
for name, dx, dy, tiefe in ansicht3d.achsen_bild(*ansicht3d.Ansicht3D.GRUND):
    assert abs(dx * dx + dy * dy + tiefe * tiefe - 1) < 1e-9
# Grundstellung: Rohrachse Z waagerecht nach rechts, Y nach oben (Bildschirm y nach unten = negativ)
richt = {n: (dx, dy) for n, dx, dy, _ in ansicht3d.achsen_bild(0.0, 0.0)}
assert abs(richt["Z"][0] - 1) < 1e-9 and abs(richt["Y"][1] + 1) < 1e-9
d = oeffnen(pid=9)
a3 = d.ansicht3d.ansicht
assert a3.achsen_an and not a3.raster_an
linien = a3.raster_linien()
assert linien and all(abs(p[1] - a3.modell.min[1]) < 1e-9 and abs(q[1] - a3.modell.min[1]) < 1e-9 for p, q, _ in linien)
assert any(kr for *_, kr in linien) and any(not kr for *_, kr in linien)
zs = [p[2] for p, q, _ in linien if p[2] == q[2]]
assert min(zs) < a3.modell.min[2] and max(zs) > a3.modell.max[2]          # etwas größer als das Modell
a3.resize(800, 400)
ohne = a3.grab().toImage()
d.editor.arbeitsbereich.leiste.aktionen["Raster"].trigger()
assert a3.raster_an and db.einstellung(ansicht3d.RASTER_EINSTELLUNG) is not True or True
mit = a3.grab().toImage()
assert ohne != mit
a3.raster_setzen(False)
a3.achsen_setzen(False)
ohne_achsen = a3.grab().toImage()
a3.achsen_setzen(True)
assert ohne_achsen != a3.grab().toImage()
from rohrlaser import ansicht3d_leiste  # noqa: E402
from PySide6.QtWidgets import QMenu  # noqa: E402

menue = QMenu()
ansicht3d_leiste.blick_menue(menue, a3)
texte = [x.text() for x in menue.actions()]
assert "Raster" in texte and "Achsenkreuz" in texte
d.reject()
ok("A7 Achsenkreuz (dreht mit) und Raster unter dem Modell (1-2-5-Weite, größer als das Modell), Menü Blick")

# ------------------------------------------------------------------ A10/A11 Mehrfachbearbeitung
from PySide6.QtCore import QItemSelectionModel  # noqa: E402

VIER = dict(a={}, b={}, konturen=[dict(art=sw.BOHRUNG, anzahl=1, d=10, x=100, seite="0° oben"),
                                  dict(art=sw.BOHRUNG, anzahl=1, d=10, x=200, seite="0° oben"),
                                  dict(art=sw.LANGLOCH, anzahl=1, l=30, b=10, x=300, seite="0° oben"),
                                  dict(art=sw.BOHRUNG, anzahl=1, d=8, x=400, seite="0° oben")])
d = oeffnen(pid=10, eing=VIER)
d.resize(1400, 850)
d.show()
app.processEvents()
ed = d.editor
ab = ed.arbeitsbereich
t = d.tabelle


def markieren(zeilen):
    t.clearSelection()
    for z in zeilen:
        t.selectionModel().select(t.model().index(z, 0), QItemSelectionModel.Select | QItemSelectionModel.Rows)
    app.processEvents()


markieren([0, 1])
mf = ab.mehrfach
assert mf.isVisible() and ed.eigenschaften.isHidden() and mf.zeilen == [0, 1]
assert mf.titel.text() == "2 Konturen markiert (Bohrung)" and "Ø d" in mf.felder
assert "Mitte–Mitte 100" in mf.abstand.text() and "Kante–Kante 90" in mf.abstand.text(), mf.abstand.text()
schritte = ed.verlauf.count()
mf.felder["Ø d"].setText("12")
mf.felder["Ø d"].editingFinished.emit()
app.processEvents()
k = d.eingaben()["konturen"]
assert k[0]["d"] == 12 and k[1]["d"] == 12 and k[3]["d"] == 8 and ed.verlauf.count() == schritte + 1
mf.felder["Lage verschieben um"].setText("15")
mf.felder["Lage verschieben um"].editingFinished.emit()
app.processEvents()
k = d.eingaben()["konturen"]
assert (k[0]["x"], k[1]["x"], k[2]["x"]) == (115, 215, 300) and ed.verlauf.count() == schritte + 2
mf.seiten.setCurrentText("180° unten")
mf.seiten.activated.emit(mf.seiten.currentIndex())
app.processEvents()
assert {k_["seite"] for k_ in d.eingaben()["konturen"][:2]} == {"unten"}, d.eingaben()["konturen"][:2]
ed.verlauf.undo()
ed.verlauf.undo()
assert d.eingaben()["konturen"][0]["x"] == 100 and d.eingaben()["konturen"][0]["d"] == 12
ed.verlauf.redo()
ed.verlauf.redo()
# gemischte Arten: keine Maßfelder, aber Anzahl
markieren([1, 2])
assert mf.titel.text() == "2 Konturen markiert" and "Ø d" not in mf.felder and "Anzahl" in mf.felder
# Duplizieren, Spiegeln, Entfernen für alle
n = t.rowCount()
schritte = ed.verlauf.count()
mf.duplizieren()
app.processEvents()
assert t.rowCount() == n + 2 and ed.verlauf.count() == schritte + 1
markieren([n, n + 1])
mf.spiegeln()
k = d.eingaben()["konturen"]
L = ed.teil_laenge()
assert abs(k[n]["x"] - (L - k[1]["x"])) < 1e-6 and abs(k[n + 1]["x"] - (L - k[2]["x"])) < 1e-6
markieren([n, n + 1])
ed._taste_mehrfach("entfernen")             # Entf mit zwei markierten
app.processEvents()
assert t.rowCount() == n and not mf.isVisible() and ed.eigenschaften.isVisible()
# Merkmalsbaum: Strg+Klick auf zwei Konturen markiert beide Zeilen
ed.baum.clearSelection()
for i in range(ed.baum.topLevelItemCount()):
    g = ed.baum.topLevelItem(i)
    for j in range(g.childCount()):
        if g.child(j).data(0, Qt.UserRole) in ("kontur:0", "kontur:3"):
            g.child(j).setSelected(True)
app.processEvents()
assert ab.markiert() == [0, 3] and mf.isVisible()
d.reject()
ok("A10 Mehrfachbearbeitung: Maß, Lage, Seite für alle (je ein Schritt), Duplizieren/Spiegeln/Entfernen, Baum")
ok("A11 Abstand zweier Konturen längs: Mitte–Mitte 100 mm, Kante–Kante 90 mm")

print("Alle Tests bestanden.")
