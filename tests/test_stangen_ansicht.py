"""Prüft die Ideen aus Lantek Flex3d (Patrick 24.10.2026 „Alle a“): Stangen-Übersicht mit je Stange einer Zeile,
Stangen-Detail mit Kennzahlen und Teile-Kacheln, Abwicklung der ganzen Stange (Programm und Werkstattpapiere),
Teilebaum mit Offen-Spalte und 3D-Vorschau im Reiter Schnittplan, Umschalter im Abmessungs-Fenster.

Aufruf: python tests/test_stangen_ansicht.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import json
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QMouseEvent  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import beispiel_angebot  # noqa: E402
from rohrlaser import abmessung, ausgabe, optimierung as opt, pdf, rechnen, schneidweg as sw, skizze as sk  # noqa: E402
from rohrlaser import stangen_abwicklung as sa  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402
from rohrlaser.stangen_ansicht import DETAIL, MUSTER, UEBERSICHT, gruppen, kennwerte, teil_farben  # noqa: E402


def ok(text):
    print("OK    ", text)


# ------------------------------------------------------------------ Abwicklung der Stange (rechnen)
QR = dict(form="Quadratrohr", a=40, b=40, wand=3)
qs = sk.Querschnitt(QR)
tech = dict(quelle=sw.QUELLE, a=dict(winkel=45, richtung=0, form="Gehrung", achse="über Höhe"), b={},
            konturen=[dict(art="Bohrung", d=10, x=100, seite="oben", anzahl=1),
                      dict(art="Gravur", laenge=50, x=300, seite="unten", anzahl=1)])
p = dict(pos=10, artikel="A", profil_id="QR 40x40x3", laenge=800, stueck=1, technik=json.dumps(tech))
teil = dict(ref="ix0", index=0, pos=10, artikel="A", laenge=800, von=10, bis=810, drehung=0, drehfreigabe=opt.FEST,
            naht=0)
stange = dict(nr=1, profil="QR 40x40x3", werkstoff="S235", stange=6000, end=10, greif=100, verlust=1, teile=[teil])
d = sa.stange(stange, [p], lambda _: QR)
assert d and d["umfang"] == qs.umfang == 160 and not d["fehlt"] and len(d["teile"]) == 1
assert [n for n, _, _ in d["streifen"]] == ["oben", "vorne", "unten", "hinten"] and d["naht"] == 20
t = d["teile"][0]
spitze = min(t["umriss"][:sa.PUNKTE_ENDE + 1], key=lambda q: q[0])
assert abs(spitze[0] - 10) < 1e-6 and 0 <= spitze[1] <= 40            # Gehrung: oben am längsten, an der Spitze
assert max(x for x, _ in t["umriss"]) == 810 and all(10 <= x <= 810 for x, _ in t["umriss"])
loch = t["konturen"][0]
mitte = sum(s for _, s in loch["punkte"]) / len(loch["punkte"])
assert not loch["gravur"] and abs(mitte - 20) < 1e-6 and abs(sum(x for x, _ in loch["punkte"]) / len(loch["punkte"]) - 110) < 1e-6
assert t["konturen"][1]["gravur"]
# gedreht um 90°: alles eine Fläche weiter (oben -> vorne), Naht der Stange auch
d90 = sa.stange(dict(stange, teile=[dict(teil, drehung=90)]), [p], lambda _: QR)
loch = d90["teile"][0]["konturen"][0]
assert abs(sum(s for _, s in loch["punkte"]) / len(loch["punkte"]) - 60) < 1e-6 and d90["naht"] == 60
spitze = min(d90["teile"][0]["umriss"][:sa.PUNKTE_ENDE + 1], key=lambda q: q[0])
assert 40 <= spitze[1] <= 80
assert sa.verschiebung(qs, 180) == 80 and sa.verschiebung(qs, 360) == 0
# über die Abwicklungsnaht: oben und unten gezeichnet
assert len(sa.kontur_teile([(0, -3), (0, 3)], 160)) == 2 and len(sa.kontur_teile([(0, 3), (0, 9)], 160)) == 1
# Position fehlt bzw. Profil ohne Querschnitt
assert sa.stange(dict(stange, teile=[dict(teil, ref="ix9", index=9)]), [p], lambda _: QR) is None
assert sa.stange(stange, [p], lambda _: None) is None
leer = dict(p, technik=None)
assert sa.stange(stange, [leer], lambda _: QR)["teile"][0]["konturen"] == []
# Nasen einer Steckverbindung (Patrick 25.10.2026: auf der Stange nicht zu sehen): Schnitt um die Nasenlänge innen,
# die Nasen (Breite am Umfang) bis zum Teilende, scharfe Stufe an ihren Kanten
from rohrlaser import steckverbindung as stv  # noqa: E402
_, mit_nasen, plus = stv.anwenden(stv.neu(dict(id=1), dict(id=2), QR, {}, ende="a", x=200, seite="oben"),
                                  dict(a={}, b={}, konturen=[]), dict(a={}, b={}, konturen=[]), QR, QR)
pn = dict(p, technik=json.dumps(dict(mit_nasen, quelle=sw.QUELLE)))
tn = sa.stange(stange, [pn], lambda _: QR)["teile"][0]
vorne = [(x, s_) for x, s_ in tn["umriss"] if x < 10 + plus / 2]          # Spitzen der Nasen am Teilende
breite = stv.nasen(mit_nasen["a"])["bN"]
assert plus > 0 and vorne and {round(x, 6) for x, _ in vorne} == {10.0}, vorne
assert abs(max(s_ for x, s_ in vorne if s_ < 80) - min(s_ for x, s_ in vorne if s_ < 80) - breite) < 0.01, vorne
assert any(abs(x - (10 + plus)) < 1e-6 for x, _ in tn["umriss"])          # dazwischen der Schnitt
ok("Abwicklung der Stange: Gehrung an der Spitze, Konturen an ihrer Stelle, Drehung verschiebt Teil und Naht, "
   "Konturen über die Abwicklungsnaht doppelt, ohne Position/Profil keine Abwicklung")

# ------------------------------------------------------------------ Angebot
app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
fenster = Hauptfenster(db, tmp, stumm=True)
s = fenster.angebot_oeffnen(beispiel_angebot.anlegen(db))

# vor dem Optimieren: Teilebaum mit hohlen Punkten, Stangenbild leer
baum = abmessung.teilebaum(s.kopf, s.positionen, None)
assert all(g["status"] == abmessung.OFFEN for g in baum) and len(baum) == 4
assert sum(len(g["positionen"]) for g in baum) == len(s.positionen)
assert "Noch nicht optimiert" in s.teile_baum.info.text() and s.stangen_seite.stangen == []
ok("vor dem Optimieren: Teilebaum je Abmessung, Status noch nicht optimiert, Stangenbild leer")

assert s.optimieren()
st = s.stangen_seite
paare = rechnen.anzeige_stangen(s.ergebnis, rechnen.stangen_werte(s.ergebnis, s.kopf, s.positionen, s.k, s.tabellen))
assert len(st.stangen) == len(paare) == 28 and st.uebersicht.nummern() == [x["nr"] for x, _ in paare]
assert len(st.bild.muster) < len(st.stangen)                    # Stangenmuster fasst zusammen, Übersicht nicht (F3a)
kopf = gruppen(st.stangen)
assert len(kopf) == 4 and sum(len(x) for _, x in kopf) == 28 and "12 Stangen" in kopf[0][0] and "Ausnutzung" in kopf[0][0]
farben = teil_farben(st.stangen)
assert len(farben) == 5 and st.bild.farben[st.stangen[0]["teile"][0]["ref"]].name().upper() == farben[
    st.stangen[0]["teile"][0]["ref"]].upper()
k = kennwerte(*paare[0])
assert k["teile"] == len(paare[0][0]["teile"]) and abs(k["rest"] - paare[0][1]["rest"]) < 1e-9 and k["kosten"] > 0
ok("Stangen-Übersicht: jede Stange eine Zeile (28), gruppiert nach Abmessung mit Kopfzeile, Farben wie Stangenbild")

# Umschalten und merken; Standard ist die Übersicht (Patrick 26.10.2026)
assert st.ansicht == UEBERSICHT and st.stapel.currentWidget() is st.rollen[UEBERSICHT]
st.ansicht_setzen(MUSTER)
assert db.einstellung("ansicht_stangenbild_2") == MUSTER
st.ansicht_setzen(UEBERSICHT)
assert db.einstellung("ansicht_stangenbild_2") == UEBERSICHT and st.stapel.currentWidget() is st.rollen[UEBERSICHT]
st.uebersicht.resize(1200, st.uebersicht.minimumHeight())
st.uebersicht.grab()
# Maus 1 Sekunde auf einer Stange: Fenster mit den Stangendetails, Esc schließt
u = st.uebersicht
assert u.uhr.interval() == 1000 and not u.popup.isVisible()
_wo = QPointF(u.LINKS + 20, u.stangen_y[3] + 8)
QApplication.sendEvent(u, QMouseEvent(QEvent.MouseMove, _wo, u.mapToGlobal(_wo), Qt.NoButton, Qt.NoButton,
                                      Qt.NoModifier))
assert u._ueber == 3 and u.uhr.isActive()
QTest.qWait(1200)
assert u.popup.isVisible() and u.popup.nr == 3, (u.popup.isVisible(), u.popup.nr)
txt = u.popup.text.text()
assert "Stange 3" in txt and "Nutzung" in txt and "Rest (Verschnitt)" in txt and "Pos." in txt and "Esc" in txt, txt
QTest.keyClick(u, Qt.Key_Escape)
assert not u.popup.isVisible()
u.popup_zeigen(5)
assert u.popup.isVisible() and u.popup.nr == 5
st.ansicht_setzen(DETAIL)                                           # andere Ansicht: Fenster zu
assert not u.popup.isVisible()
st.ansicht_setzen(UEBERSICHT)
ok("Übersicht ist Standard; Maus 1 s auf einer Stange zeigt die Stangendetails, Esc schließt")
y = st.uebersicht.stangen_y[13]
QTest.mouseClick(st.uebersicht, Qt.LeftButton, Qt.NoModifier, QPoint(5, y + 8))
assert st.ansicht == DETAIL and st.nr == 13 and st.detail.s["nr"] == 13 and "Stange 13" in st.detail.titel.text()
assert "Nutzung" in st.detail.werte.text() and "Rest (Verschnitt)" in st.detail.werte.text()
assert len(st.detail.kacheln.teile) == len(st.stange(13)["teile"]) and st.detail.abwicklung.daten
st.detail.k_vor.click()
assert st.nr == 14
st.detail.k_zurueck.click()
st.detail.k_zurueck.click()
assert st.nr == 12
st.ansicht_setzen(UEBERSICHT)
st.uebersicht.setFocus()
QTest.keyClick(st.uebersicht, Qt.Key_Down)
assert st.nr == 13 and st.ansicht == UEBERSICHT                  # Pfeiltasten wählen nur, Detail bleibt zu
st.ansicht_setzen(DETAIL)
st.detail.resize(1200, 900)
st.detail.kacheln.resize(1200, st.detail.kacheln.minimumHeight())
st.detail.kacheln.grab()
r, t0 = st.detail.kacheln.flaechen[0]
QTest.mouseClick(st.detail.kacheln, Qt.LeftButton, Qt.NoModifier, r.center().toPoint())
assert st.markiert == t0["ref"] and st.bild.markiert == t0["ref"] and st.detail.abwicklung.markiert == t0["ref"]
zeile = next(z for z, q in enumerate(s.positionen) if rechnen.schluessel(q, z) == t0["ref"])
QTest.mouseDClick(st.detail.kacheln, Qt.LeftButton, Qt.NoModifier, r.center().toPoint())
assert s.reiter.currentWidget() is s.pos_seite and s.pos_ansicht.currentIndex().row() == zeile
st.detail.abwicklung.resize(1200, 200)
assert not st.detail.abwicklung.grab().isNull() and st.detail.abwicklung.flaechen
st.markieren(st.stangen[-1]["teile"][0]["ref"])                   # Teil auf einer anderen Stange: Detail springt
assert st.nr == st.stangen[-1]["nr"] or any(t["ref"] == st.markiert for t in st.stange(st.nr)["teile"])
for a in (MUSTER, UEBERSICHT, DETAIL):
    st.ansicht_setzen(a)
    assert not st.grab().isNull()
ok("Umschalter Stangenmuster/Übersicht/Detail (gemerkt), Klick auf eine Zeile öffnet das Detail, Blättern, "
   "Pfeiltasten, Kacheln heben hervor, Doppelklick springt zur Position, Abwicklung im Detail")

# ------------------------------------------------------------------ Teilebaum
baum = abmessung.teilebaum(s.kopf, s.positionen, s.ergebnis)
assert all(g["status"] == abmessung.OK and g["offen"] == 0 for g in baum)
assert sum(g["eingeplant"] for g in baum) == sum(q["stueck"] for q in s.positionen)
assert s.teile_baum.baum.topLevelItemCount() == 4 and "152 von 152" in s.teile_baum.info.text()
fehlt = dict(s.ergebnis, stangen=s.ergebnis["stangen"][1:])
b2 = abmessung.teilebaum(s.kopf, s.positionen, fehlt)
assert b2[0]["status"] == abmessung.FEHLT and b2[0]["offen"] > 0
zk = s.positionen + [dict(pos=90, artikel="Schraube", art="Zukaufteil", stueck=4)]
b3 = abmessung.teilebaum(s.kopf, zk, s.ergebnis)
assert b3[-1]["status"] == abmessung.KEIN and b3[-1]["positionen"][0]["eingeplant"] is None
ok("Teilebaum: Benötigt/Eingeplant/Offen je Abmessung und Position, rot bei fehlenden Teilen, grau ohne Rohrlaser")

kopf_item = s.teile_baum.baum.topLevelItem(1)
it = kopf_item.child(0)
x = s.teile_baum.position(it)
s.teile_baum.baum.setCurrentItem(it)
assert st.markiert == x["ref"] and any(t["ref"] == x["ref"] for t in st.stange(st.nr)["teile"])
zeile_plan = s.stangen_ansicht.currentIndex().row()
assert any(t["ref"] == x["ref"] for t in rechnen.anzeige_stangen(s.ergebnis)[zeile_plan]["teile"])
assert s.teile_baum.ansicht is not None and s.teile_baum.ansicht.ansicht.netz and "Eingaben" in s.teile_baum.titel.text()
s.teile_baum.k_3d.setChecked(False)
assert not s.teile_baum.ansicht.isVisibleTo(s.teile_baum)
s.teile_baum.k_3d.setChecked(True)
s.neu_laden()
assert s.teile_baum.zeile_gewaehlt == x["zeile"]                 # Auswahl bleibt nach dem Neuladen
s.teile_baum.doppelklick.emit(x["ref"])
assert s.reiter.currentWidget() is s.pos_seite and s.pos_ansicht.currentIndex().row() == x["zeile"]
ok("Teilebaum: Auswahl hebt das Teil im Stangenbild hervor und wählt die Stange im Schnittplan, 3D-Vorschau aus den "
   "Eingaben (abschaltbar), Doppelklick zur Position")

# ------------------------------------------------------------------ Werkstattpapiere
wp = ausgabe.werkstatt(s.kopf, s.positionen, s.ergebnis, s.k, s.tabellen)
assert all(m["abwicklung"] and m["abwicklung"]["teile"] for m in wp["muster"])
ziel = tmp / "wp.pdf"
pdf.werkstatt_pdf(str(ziel), s.kopf, wp, True, s.einst)
mit = ziel.stat().st_size
ohne = tmp / "wp_ohne.pdf"
pdf.werkstatt_pdf(str(ohne), s.kopf, dict(wp, muster=[dict(m, abwicklung=None) for m in wp["muster"]]), True, s.einst)
assert mit > ohne.stat().st_size
assert s.kalkulation_pdf()
ok("Werkstattpapiere: je Stangenmuster die Abwicklung unter dem Balken (größer als ohne), Kalkulation-PDF ohne")

# ------------------------------------------------------------------ Abmessungs-Fenster
from rohrlaser.abmessung_fenster import AbmessungFenster  # noqa: E402
g = rechnen.material_abmessungen(s.kopf, s.positionen, s.ergebnis, s.k, s.tabellen)[0]
offen = []


def bedienen(d):
    d.zeigen = offen.append
    d.oeffnen(0, 7)
    d.annehmen()
    return d.result()


s.material_einstellen(bedienen)
f = offen[-1]
assert isinstance(f, AbmessungFenster) and f.stangen_seite.ansicht == DETAIL     # zuletzt gewählte Ansicht
assert len(f.stangen_seite.stangen) == g["stangen"] and f.bild is f.stangen_seite.bild
f.muster_waehlen(len(f.muster) - 1)
assert f.stangen_seite.nr == f.muster[-1]["nummern"][0]
f.teil_waehlen(f.teile[0]["ref"])
assert f.stangen_seite.markiert == f.teile[0]["ref"] and f.stangen_seite.detail.abwicklung.daten
ok("Abmessungs-Fenster: Umschalter wie im Reiter (gemerkte Ansicht), Schnittmuster und Teileliste wählen Stange/Teil")
print("Alle Prüfungen bestanden.")
