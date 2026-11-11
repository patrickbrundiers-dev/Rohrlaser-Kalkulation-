"""Plan „Neuerungen und Editor-Import“ Teil C (Patrick 10.11.2026): STEP neu einlesen im Editor mit Vorschau, von
Hand gesetzte Werte bleiben, die gemerkte Datei der Position wird direkt genommen, neuere Revision im Ordner."""
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER))

from PySide6.QtWidgets import QApplication  # noqa: E402

from rohrlaser import neu_einlesen as ne  # noqa: E402
from rohrlaser import schneidweg as sw  # noqa: E402
from rohrlaser import step  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402
from rohrlaser.schneidweg_dialog import NeuEinlesenVorschau, SchneidwegDialog  # noqa: E402

app = QApplication.instance() or QApplication([])


def ok(text):
    print("OK    ", text)


# ------------------------------------------------------------------ Regeln ohne Fenster
alt = dict(a=dict(winkel=0), b=dict(winkel=45, achse="über Höhe"), gravur=0, konturen=[
    dict(art=sw.BOHRUNG, anzahl=1, d=6.8, x=100.0, seite="oben", gewinde="M8"),
    dict(art=sw.SENKUNG, anzahl=1, d=9.0, D=16.0, x=200.0, seite="oben"),
    dict(art=sw.LANGLOCH, anzahl=1, l=30.0, b=10.0, x=300.0, seite="links"),
    dict(art=sw.BOHRUNG, anzahl=1, d=12.0, x=400.0, seite="oben")])
neu = dict(a=dict(winkel=0), b=dict(winkel=30, achse="über Höhe"), gravur=0, konturen=[
    dict(art=sw.BOHRUNG, anzahl=1, d=6.8, x=100.2, seite="oben"),
    dict(art=sw.BOHRUNG, anzahl=1, d=9.0, x=200.0, seite="oben"),
    dict(art=sw.LANGLOCH, anzahl=1, l=30.0, b=10.0, x=300.0, seite="links"),
    dict(art=sw.BOHRUNG, anzahl=1, d=12.0, x=440.0, seite="oben"),
    dict(art=sw.RECHTECK, anzahl=1, b=20.0, h=10.0, x=500.0, seite="unten")])
paare, weg, neue = ne.zuordnen(alt["konturen"], neu["konturen"])
assert paare == [(0, 0), (1, 1), (2, 2)] and weg == [3] and neue == [3, 4], (paare, weg, neue)
z = ne.vergleich(alt, neu, 1000.0, 1040.0, "QR 40x40x3", "QR 50x50x3")
arten = [a for a, _ in z]
assert arten == ["hinweis", "hinweis", "geaendert", "gleich", "neu", "neu", "weg"], z
texte = " | ".join(t for _, t in z)
for wort in ("Profil QR 50x50x3", "40,0 mm länger", "Ende B: 45,0° über Höhe → 30,0° über Höhe", "3 Konturen unverändert",
             "neu: Bohrung 12,0 bei x = 440,0", "neu: Rechteck", "entfällt: Bohrung 12,0 bei x = 400,0"):
    assert wort in texte, (wort, texte)
assert not ne.unveraendert(z) and ne.unveraendert(ne.vergleich(alt, alt, 1000.0, 1000.2, "A", "A"))
mit, behalten = ne.handwerte(alt, neu)
assert mit["konturen"][0].get("gewinde") == "M8" and mit["konturen"][1]["art"] == sw.SENKUNG and \
    mit["konturen"][1]["D"] == 16.0 and "gewinde" not in mit["konturen"][3], mit["konturen"]
assert behalten == ["Gewinde M8 an 1 Kontur", "Senkung an 1 Kontur"], behalten
assert "gewinde" not in neu["konturen"][0] and neu["konturen"][1]["art"] == sw.BOHRUNG       # Eingabe unverändert
ok("Vorschau: Profil, Länge, Enden, Konturen gleich/neu/entfällt; Handwerte (Gewinde, Senkung) an gleichen Konturen")

ordner = Path(tempfile.mkdtemp())
alt_datei, rev_b, rev_c, fremd = (ordner / n for n in ("Halter.step", "Halter_Rev B.step", "Halter-Index C.stp",
                                                       "Halterung_Rev D.step"))
for i, d in enumerate((alt_datei, rev_b, rev_c, fremd)):
    d.write_text("x", encoding="utf-8")
    os.utime(d, (time.time() - 1000 + 100 * i,) * 2)
assert ne.stamm("Halter_Rev B.step") == ne.stamm("halter v2.stp") == ne.stamm("Halter.STEP") == "halter"
assert ne.neuere_revision(alt_datei) == rev_c and ne.neuere_revision(rev_b) == rev_c and ne.neuere_revision(rev_c) is None
assert ne.neuere_revision(ordner / "fehlt.step") is None
ok("Neuere Revision: gleicher Name ohne Anhang (Rev, Index, v), nur jüngere Dateien, andere Teile nicht")

# ------------------------------------------------------------------ im Editor
if step.messprogramm(HIER.parent / "programm") is None:
    print("OK: Neu einlesen (ohne Messprogramm nur die Regeln)")
    sys.exit(0)

db = Datenbank(Path(tempfile.mkdtemp()) / "rohrlaser.db")
f = Hauptfenster(db, stumm=True)
quelle = ordner / "K04.step"
shutil.copy(HIER / "step_konturen" / "K04_RE60x40x3_Senkung_Flowdrill.step", quelle)
a = db.angebot_neu(dict(kundennr="K-1", kunde="Test"))
s = f.angebot_oeffnen(a)
s.step_importieren([str(quelle)], "S235-10219", 1)
p = next(x for x in s.positionen if x.get("profil_id"))
assert Path(step.herkunft(p)["datei"]) == quelle and s.step_der_position(p) == quelle
gemessen = []
echt = s.step_messen


def messen(dateien=None, **kw):
    gemessen.append(dateien)
    return echt(dateien=dateien) if dateien else None           # ohne Datei: Dateidialog, hier „nichts gewählt“


s.step_messen = messen
mess = s.step_neu_lesen(p)
assert gemessen == [[str(quelle)]] and mess, gemessen
neuer = ordner / "K04_Rev B.step"
shutil.copy(quelle, neuer)
os.utime(neuer, (time.time() + 60,) * 2)
assert s.step_neu_lesen(p, wahl="neuer") and gemessen[-1] == [str(neuer)]
assert s.step_neu_lesen(p, wahl="andere") is None and gemessen[-1] is None        # Dateidialog (hier: nichts gewählt)
assert s.step_neu_lesen(p, wahl=None) and gemessen[-1] == [str(quelle)]            # stumm: gemerkte Datei
ok("Gemerkte Datei der Position wird direkt gemessen; neuere Revision und andere Datei wählbar")


def dialog():
    return SchneidwegDialog(s, p, s.k.profile[p["profil_id"]], s.kopf, s.k, s.tabellen, db, s.positionen,
                            step_lesen=lambda: mess)


d = dialog()
vorher = d.eingaben()
n = len(vorher["konturen"])
assert n >= 3, n
gesehen = []
assert d.step_einlesen(vorschau=lambda zeilen, behalten: gesehen.append((zeilen, behalten)) or True)
gravur = [t for t in gesehen[0][1] if t.startswith("Gravurlänge")]      # Positionsgravur: nicht in der Datei
assert ne.unveraendert(gesehen[0][0]) and gesehen[0][1] == gravur, gesehen
assert len(d.eingaben()["konturen"]) == n and d.eingaben().get("gravur") == vorher.get("gravur")
ok(f"Dieselbe Datei neu eingelesen: Vorschau meldet {n} Konturen unverändert, nichts verloren")

# Handwert setzen (Gewinde an der ersten Bohrung), eine Kontur löschen, eine verschieben -> Vorschau, Abbrechen, Übernehmen
from rohrlaser.schneidweg_dialog import GEWINDE_SPALTE  # noqa: E402
bohr, combo = next((r, d.tabelle.cellWidget(r, GEWINDE_SPALTE)) for r in range(d.tabelle.rowCount())
                   if d.tabelle.cellWidget(r, 0).currentText() == sw.BOHRUNG)
hand = next(combo.itemText(i) for i in range(combo.count()) if combo.itemText(i).startswith("M")
            and combo.itemText(i) != combo.currentText())
combo.setCurrentText(hand)
assert d.eingaben()["konturen"][bohr].get("gewinde") == hand
bohr_x = d.eingaben()["konturen"][bohr]["x"]
d.tabelle.removeRow(next(r for r in range(d.tabelle.rowCount()) if r != bohr))


def bohrung(dlg):
    return next(z for z in dlg.eingaben()["konturen"] if z.get("x") == bohr_x and z["art"] == sw.BOHRUNG)


stand = json.dumps(d.eingaben(), sort_keys=True, default=str)
gesehen.clear()
assert d.step_einlesen(vorschau=lambda zeilen, behalten: gesehen.append((zeilen, behalten))) is False     # Abbrechen
assert json.dumps(d.eingaben(), sort_keys=True, default=str) == stand, "Abbrechen ändert nichts"
zeilen, behalten = gesehen[0]
assert [a_ for a_, _ in zeilen].count("neu") == 1 and behalten == [f"Gewinde {hand} an 1 Kontur"] + gravur, (zeilen, behalten)
assert d.step_einlesen(vorschau=lambda zeilen, behalten: True)
e = d.eingaben()
assert len(e["konturen"]) == n and bohrung(d).get("gewinde") == hand, bohrung(d)
assert d.step_einlesen(vorschau=lambda zeilen, behalten: False)                     # ohne Handwerte
assert bohrung(d).get("gewinde") != hand
ok("Vorschau zeigt die fehlende Kontur als neu; Abbrechen ändert nichts; Gewinde von Hand bleibt, ohne Haken nicht")

v = NeuEinlesenVorschau(d, zeilen, behalten, dict(datei="K04.step"))
assert "neu:" in v.liste.text() and v.hand.isChecked() and f"Gewinde {hand}" in v.hand.text() and "K04.step" in \
    v.findChildren(type(v.liste))[0].text()
v2 = NeuEinlesenVorschau(d, [], [])
assert "Keine Änderung" in v2.liste.text() and not v2.hand.isVisibleTo(v2)
ok("Vorschau-Dialog: Liste farbig, Haken „Von Hand gesetzte Werte behalten“ nur mit Handwerten")

# ------------------------------------------------------------------ A1: Knopf in den anderen Editoren (hier Blech)
from PySide6.QtWidgets import QDialog  # noqa: E402

blech_datei = ordner / "B02.step"
shutil.copy(HIER / "step_bleche" / "B02_Blech_400x200x4_Bohrungen.step", blech_datei)
del s.step_messen                   # wieder die echte Messung
s.step_importieren([str(blech_datei)], "S235-10219", 3)
zb = next(r for r, x in enumerate(s.positionen) if "B02" in str(x.get("artikel")))
pb = dict(s.positionen[zb])
db.position_aendern(pb["id"], "stueck", 7)
s.neu_laden()
ablauf = []


def im_editor(dlg):
    assert dlg.step_neu_knopf.text() == "STEP neu einlesen …" and dlg.art_knopf is not None
    ablauf.append(dlg.step_neu_los(wahl="gemerkt"))
    return QDialog.Rejected


s.blech_bearbeiten(zb, dialog=im_editor)
assert ablauf and ablauf[0] is not None, ablauf
nach = next(x for x in s.positionen if x.get("pos") == pb["pos"])
assert nach["stueck"] == 7 and nach.get("artikel") == pb["artikel"], (nach.get("stueck"), nach.get("artikel"))
ok("Blech-Editor: Knopf „STEP neu einlesen …“ misst die gemerkte Datei neu, Pos.-Nummer und Stückzahl bleiben")

d_rohr = dialog()
assert not hasattr(d_rohr, "step_neu_knopf") and d_rohr.step_knopf.text() == "STEP neu einlesen …"
ok("Rohr-Editor behält seinen eigenen Knopf mit Vorschau")

# ------------------------------------------------------------------ A5: STEP-Datei ins Editor-Fenster ziehen
from PySide6.QtCore import QMimeData, QPoint, QUrl  # noqa: E402
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QDragEnterEvent  # noqa: E402


def ziehen(dlg, pfad, klasse):
    daten = QMimeData()
    daten.setUrls([QUrl.fromLocalFile(str(pfad))])
    ev = klasse(QPoint(5, 5), Qt.CopyAction, daten, Qt.LeftButton, Qt.NoModifier)
    ev._daten = daten
    return ev


assert d_rohr.acceptDrops()
ev = ziehen(d_rohr, quelle, QDragEnterEvent)
d_rohr.dragEnterEvent(ev)
assert ev.isAccepted()
ev = ziehen(d_rohr, ordner / "notiz.txt", QDragEnterEvent)
ev.ignore()
d_rohr.dragEnterEvent(ev)
assert not ev.isAccepted(), "andere Dateien nimmt der Editor nicht"
d_rohr.tabelle.removeRow(0)
assert len(d_rohr.eingaben()["konturen"]) == n - 1
gesehen.clear()
assert d_rohr.step_datei_einlesen(quelle, vorschau=lambda zeilen, behalten: gesehen.append(zeilen) or True)
assert len(d_rohr.eingaben()["konturen"]) == n and [a_ for a_, _ in gesehen[0]].count("neu") == 1
ok("STEP-Datei ins Editor-Fenster gezogen: gemessen und mit Vorschau eingelesen; andere Dateien abgelehnt")

# ------------------------------------------------------------------ A7: Teilwahl mit Bild
from rohrlaser.schneidweg_dialog import PROFIL_UEBERNEHMEN, TeilWahlDialog  # noqa: E402

blech_m = s.step_messen(dateien=[str(blech_datei)])[0]
rohr_a, rohr_b = dict(mess[0], artikel="X-1"), dict(mess[0], artikel="X-2")
tw = TeilWahlDialog(d_rohr, [rohr_a, blech_m, rohr_b], [rohr_a, rohr_b], "X-2")
assert tw.liste.count() == 3 and tw.liste.currentRow() == 2, tw.liste.currentRow()
assert not tw.liste.item(1).flags() & Qt.ItemIsEnabled and tw.liste.item(0).flags() & Qt.ItemIsEnabled
assert not tw.liste.item(0).icon().isNull(), "3D-Bild aus dem Netz der Messung"
t0 = tw.liste.item(0).text()
assert t0.startswith("X-1\n") and "Rechteckrohr 60 × 40 × 3" in t0 and "mm" in t0 and "Kontur" in t0, t0
gefragt = []
d7 = dialog()
assert d7.step_einlesen([rohr_a, blech_m, rohr_b], vorschau=lambda z_, b_: True,
                        teilwahl=lambda alle, wahl: gefragt.append((len(alle), len(wahl))) or wahl[1])
assert gefragt == [(3, 2)], gefragt
assert d7.step_einlesen([rohr_a, rohr_b], teilwahl=lambda alle, wahl: None) is False          # abgebrochen
ok("Teilwahl mit Bild: alle Teile der Datei, Rohre wählbar, Blech grau, Teil mit der Artikelnummer vorgewählt")

# ------------------------------------------------------------------ A6: Profil aus Datei übernehmen
pid_alt = p["profil_id"]
anderes = next(i for i, pr in s.k.profile.items() if pr.get("form") == s.k.profile[pid_alt].get("form") and i != pid_alt
               and float(pr.get("a") or 0) > float(s.k.profile[pid_alt].get("a") or 0))
db.position_aendern(p["id"], "profil_id", anderes)
s.neu_laden()
zr = next(r for r, x in enumerate(s.positionen) if x["id"] == p["id"])
assert s.positionen[zr]["profil_id"] == anderes
vorschauen = []


def profil_wechsel(dlg):
    def v(zeilen_, behalten_):
        vorschauen.append(zeilen_)
        return PROFIL_UEBERNEHMEN
    assert dlg.step_einlesen(mess, vorschau=v)
    assert dlg.profil_aus_datei == pid_alt and dlg.p["profil_id"] == pid_alt
    return QDialog.Accepted


assert s.schneidweg_berechnen(zr, dialog=profil_wechsel, ueberschreiben=True)
assert any(a_ == "hinweis" and f"Profil {pid_alt}" in t_ for a_, t_ in vorschauen[0]), vorschauen[0]
assert next(x for x in db.positionen(a) if x["id"] == p["id"])["profil_id"] == pid_alt
vp = NeuEinlesenVorschau(d_rohr, vorschauen[0], [], dict(datei="K04.step"), pid_alt)
assert not vp.profil_knopf.isHidden() and pid_alt in vp.profil_text.text()
vp.profil_knopf.setChecked(True)
assert vp.profil_knopf.text().startswith("✓") and NeuEinlesenVorschau(d_rohr, [], []).profil_knopf.isHidden()
ok(f"Profil aus Datei übernehmen: Position wechselt von {anderes} auf {pid_alt}, Knopf nur bei anderem Profil")
print("OK: Neu einlesen")
