"""Prüfung „Programm war heute sehr langsam“ (Patrick 04.11.2026): Jede Änderung im Angebot rechnete seit 0.9.235
deutlich mehr als vorher. Beschleunigt, Ergebnisse unverändert:
- Wiederholteil-Suche: rechnet nur neu, wenn sich ANDERE Angebote oder suchrelevante Werte ändern (nicht bei
  Stückzahl, Pos.-Nr., Bezeichnung oder dem eigenen Speichern); Vergleich nur mit Zeilen gleicher Länge ± 0,5 mm.
  Ergebnis gleich wie das bisherige Verfahren (hier als Referenz kopiert), auch mit Zufallsdaten.
- Grundwerte-Check: nutzt die schon gerechnete Kalkulation (eine Kalkulation je Neuladen weniger).
- Vorgang des Angebots ohne das ganze Angebot (Schnittplan, Staffeln) zu lesen; Fracht mit dem schon gelesenen
  Angebot.
- Erkennung der Zusatzarbeiten je Text gemerkt.

Aufruf: python tests/test_langsam_0411.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import json
import os
import random
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

APP = QApplication.instance() or QApplication([])
import beispiel_angebot  # noqa: E402
from rohrlaser import grundwerte, rechnen, zusatz_erkennung  # noqa: E402
from rohrlaser import wiederholteile as wt  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402
from rohrlaser.nachkalkulation import rueckblick  # noqa: E402


def ok(t):
    print("OK    ", t, flush=True)


# ------------------------------------------------------------------ Referenz: auswerten bis 0.9.256 (unverändert)
def ref_auswerten(zeilen, kundennr, positionen):
    _txt, einstufen = wt._txt, wt.einstufen
    kandidaten = [p for p in positionen if _txt(p.get("artikel")) or _txt(p.get("profil_id"))]
    staffeln, nachkalk = {}, {}
    aus = {}
    nach_artikel, nach_profil = {}, {}
    for i, z in enumerate(zeilen):
        nach_artikel.setdefault(_txt(z.get("artikel")).casefold(), []).append(i)
        nach_profil.setdefault(_txt(z.get("profil_id")), []).append(i)
    for p in kandidaten:
        liste = []
        art_p, profil_p = _txt(p.get("artikel")).casefold(), _txt(p.get("profil_id"))
        moegliche = set(nach_artikel.get(art_p, ()) if art_p else ()) | set(nach_profil.get(profil_p, ()) if profil_p else ())
        for z in (zeilen[i] for i in sorted(moegliche)):
            art = einstufen(p, z, kundennr, z["_kundennr"])
            if art is None:
                continue
            if z["angebot_id"] not in staffeln:
                try:
                    staffeln[z["angebot_id"]] = json.loads(z["_sp"]) if z["_sp"] else None
                except ValueError:
                    staffeln[z["angebot_id"]] = None
            angebot = dict(id=z["angebot_id"], nummer=z["_nummer"], kunde=z["_kunde"], kundennr=z["_kundennr"],
                           datum=z["_datum"], vorgang=z["_vorgang"] or "Entwurf", fremd=bool(z["_fremd"]))
            alt = {f: z[f] for f in wt.FELDER}
            if z["angebot_id"] not in nachkalk:
                try:
                    nachkalk[z["angebot_id"]] = json.loads(z["_nkj"]) if z.get("_nkj") else None
                except ValueError:
                    nachkalk[z["angebot_id"]] = None
            liste.append(wt.Treffer(art, alt, angebot, wt.preis_aus_staffeln(staffeln[z["angebot_id"]], z["pos"],
                                                                              z["stueck"]),
                                    bool(z["_nk"]), wt.unterschiede(p, alt), rueckblick(nachkalk[z["angebot_id"]],
                                                                                         z["id"]),
                                    wt.aenderungen(p, alt) if art != wt.AEHNLICH else []))     # neue Revision (B1)
        if liste:
            liste.sort(key=lambda t: str(t.angebot["datum"] or ""), reverse=True)
            liste.sort(key=lambda t: (wt.RANG[t.art], t.angebot["vorgang"] != "Beauftragt"))
            aus[p["id"]] = liste
    return aus


# ------------------------------------------------------------------ 1 Wiederholteile: gleich wie vorher (Zufall)
rnd = random.Random(4112026)
PROFILE = ["RR 42,4x2,0", " RR 42,4x2,0", "QR 40x40x3", "RE 60x40x3", "", None]
LAENGEN = [100.0, 100.4, 100.5, 100.5000001, 100.6, 99.5, 99.49, 250, 250.3, 1200.0, None, "x", True,
           float("nan"), float("inf")]


def zufall_pos(i, angebot_id=None):
    p = dict(id=i, angebot_id=angebot_id, pos=10 * i, art=None, artikel=rnd.choice(["A-1", "a-1 ", "B-2", "", None]),
             bezeichnung="Teil", profil_id=rnd.choice(PROFILE), werkstoff_id=rnd.choice(["S235", "S355", None]),
             laenge=rnd.choice(LAENGEN), stueck=rnd.choice([1, 5, 24]),
             schneidweg=rnd.choice([None, 0, 400.0, 403.0, 410.0]), klein_n=rnd.choice([None, 0, 2]),
             mittel_n=rnd.choice([None, 1]), gross_n=None)
    for f, _ in wt.UEBERNEHMBAR:
        p[f] = rnd.choice([None, None, 7.5])
    return p


for runde in range(40):
    zeilen = []
    for j in range(rnd.randint(0, 120)):
        z = zufall_pos(1000 + j, angebot_id=rnd.randint(1, 15))
        z.update(_nummer=f"A-{z['angebot_id']}", _kunde="K", _kundennr=rnd.choice(["K1", "K2", None]),
                 _datum=rnd.choice(["2026-09-01", "2026-10-01", None]), _vorgang=rnd.choice(["Beauftragt", None]),
                 _fremd=0, _sp=None, _nk=0, _nkj=None)
        zeilen.append(z)
    positionen = [zufall_pos(i) for i in range(1, rnd.randint(1, 25))]
    kundennr = rnd.choice(["K1", "K2", ""])
    neu, ref = wt.auswerten(zeilen, kundennr, positionen), ref_auswerten(zeilen, kundennr, positionen)
    assert neu == ref, f"Runde {runde}: Treffer anders"
ok("Wiederholteile: Treffer, Reihenfolge und Werte gleich wie das bisherige Verfahren (40 Zufallsrunden, auch "
   "Grenzlängen ± 0,5 mm, leere/ungültige Längen, nan, inf)")

# ------------------------------------------------------------------ 1b Konfliktkopien: gleich wie vorher (Zufall)
from rohrlaser import austausch  # noqa: E402


def ref_kopie_von(p, namen):
    for n in namen:
        if n == p.name:
            continue
        stamm, endung = (n[:-len(Path(n).suffix)], Path(n).suffix) if Path(n).suffix else (n, "")
        if endung != (p.suffix if endung else "") or not p.name.startswith(stamm):
            continue
        rest = p.name[len(stamm):len(p.name) - len(endung)] if endung else p.name[len(stamm):]
        if rest and rest[0] in austausch.KOPIE_TRENNER and not rest.endswith(austausch.NEU):
            return n
    return None


TEILE = ["haupt", "00042", "00042 (1)", "haupt-PC01", "Angebote_2026-11", "a", "a b", "a-b", "a_b(1)", ".x", "x.",
         "haupt (Konflikt-Kopie)", "Rohrlaser_PB", "Rohrlaser_PB-PC2"]
ENDUNGEN = ["", ".sqlite", ".nummer", ".neu", ".json", ".sqlite.neu", "."]
for runde in range(60):
    namen = list(dict.fromkeys(rnd.choice(TEILE) + rnd.choice(["", " (1)", "-PC", "_2", " Kopie", "x"])
                               + rnd.choice(ENDUNGEN) for _ in range(rnd.randint(1, 40))))
    index = austausch.kopien_index(namen)
    for n in namen:
        soll = ref_kopie_von(Path(n), namen)
        assert austausch.kopie_von(Path(n), namen) == soll == austausch.kopie_von(Path(n), namen, index), (n, namen)
ok("Konfliktkopien: gleiches Original wie das bisherige Verfahren (60 Zufallsordner), ohne jeden Namen mit jedem "
   "zu vergleichen")
groß = [f"{i:05d}.nummer" for i in range(3000)] + ["00042 (1).nummer", "00077-PC2.nummer"]
import time  # noqa: E402
t0 = time.perf_counter()
index = austausch.kopien_index(groß)
funde = {n: austausch.kopie_von(Path(n), groß, index) for n in groß}
dauer = time.perf_counter() - t0
assert {n: o for n, o in funde.items() if o} == {"00042 (1).nummer": "00042.nummer", "00077-PC2.nummer": "00077.nummer"}
assert dauer < 2.0, f"3.000 Nummern-Dateien: {dauer:.1f} s"
ok(f"3.000 Nummern-Dateien auf Konfliktkopien geprüft in {dauer:.2f} s")

# ------------------------------------------------------------------ 2 Angebot: Stückzahl ändern rechnet nicht neu
db = Datenbank(Path(tempfile.mkdtemp()) / "rohrlaser.db")
f = Hauptfenster(db, stumm=True)
alt_id = beispiel_angebot.anlegen(db, dict(datum="2026-09-12"))
db.vorgang_setzen(alt_id, "Beauftragt")
assert db.vorgang(alt_id) == db.angebot(alt_id)["vorgang"] == "Beauftragt"
assert db.vorgang(999999) is None
neu_id = beispiel_angebot.anlegen(db)
s = f.angebot_oeffnen(neu_id)
assert s.optimieren()
treffer = s.wiederholteile_suchen()
assert treffer, "Beispielangebot hat Wiederholteile"
n = [0]
auswerten = wt.auswerten


def zaehlen(*a, **k):
    n[0] += 1
    return auswerten(*a, **k)


wt.auswerten = zaehlen
try:
    m = s.pos_modell
    c = next(i for i, (_, fd) in enumerate(m.spalten) if fd is not None and getattr(fd, "name", None) == "stueck")
    for wert in ("7", "8", "9"):
        assert m.setData(m.index(0, c), wert, Qt.EditRole)
    assert n[0] == 0, f"Stückzahl ändern rechnete die Wiederholteil-Suche {n[0]}x neu"
    assert s.wiederholteile_suchen() is s._wt
    ok("Stückzahl ändern: Wiederholteil-Suche nicht neu gerechnet (eigenes Speichern zählt nicht)")
    db.position_aendern(db.positionen(alt_id)[0]["id"], "prog_zeit", 9.25)       # anderes Angebot geändert
    neu = s.wiederholteile_suchen()
    assert n[0] == 1, n[0]
    assert neu == wt.suchen(db, neu_id, s.kopf.get("kundennr"), s.positionen)
    p0 = s.positionen[0]
    db.position_aendern(p0["id"], "laenge", rechnen._n(p0.get("laenge")) + 3)     # suchrelevant im eigenen
    s.neu_laden()
    assert n[0] >= 2, n[0]
    assert s.wiederholteile_suchen() == wt.suchen(db, neu_id, s.kopf.get("kundennr"), s.positionen)
    ok("Andere Angebote oder Länge geändert: Suche neu, Ergebnis wie frisch gesucht")
finally:
    wt.auswerten = auswerten

# ------------------------------------------------------------------ 2b Angebots-Check: teure Punkte nach 1 s Ruhe
from rohrlaser.angebot_fenster import AngebotSeite  # noqa: E402
assert len(s.k_aktuell.maschinen) >= 2, "Beispieldaten mit mehreren Maschinen (Maschinenvergleich)"
aufrufe = []
alt_mp, alt_kp = AngebotSeite._maschinen_punkt, AngebotSeite._kalk_punkte
AngebotSeite._maschinen_punkt = lambda self: aufrufe.append("m") or alt_mp(self)
AngebotSeite._kalk_punkte = lambda self, summen, *rest: aufrufe.append("k") or alt_kp(self, summen, *rest)
AngebotSeite.CHECK_SOFORT = False
try:
    for wert in ("11", "12"):
        assert m.setData(m.index(0, c), wert, Qt.EditRole)
    assert aufrufe == [], f"Änderung rechnete Maschinenvergleich/Kalkulationsbasis sofort: {aufrufe}"
    assert s._check_uhr.isActive() and s._check_uhr.interval() == AngebotSeite.CHECK_RUHE_MS
    from PySide6.QtTest import QTest  # noqa: E402
    for _ in range(100):                 # automatisches Optimieren nach der Änderung startet die Ruhe neu
        QTest.qWait(100)
        if not s._check_uhr.isActive() and "_check_daten" not in s.__dict__:
            break
    assert aufrufe == ["m", "k"], aufrufe            # einmal nach der Ruhe, nicht je Änderung
    AngebotSeite.CHECK_SOFORT = True
    soll = s.freigabe_punkte()
    assert s._punkte == soll, (s._punkte, soll)
    ok("Angebots-Check: Maschinenvergleich und Kalkulationsbasis einmal nach 1 s Ruhe, Ergebnis wie sofort gerechnet")
    AngebotSeite.CHECK_SOFORT = False
    aufrufe.clear()
    assert m.setData(m.index(0, c), "13", Qt.EditRole)
    s._check_daten = s.__dict__.get("_check_daten") or ((), (), None)
    f.offen.pop(neu_id)                 # wie nach dem Schließen: die Seite ist nicht mehr offen
    s._check_jetzt()
    f.offen[neu_id] = s
    assert aufrufe == [], f"geschlossene Seite rechnete den Check noch: {aufrufe}"
    ok("Angebots-Check: geschlossenes Angebot rechnet nach der Ruhe nichts mehr")
finally:
    AngebotSeite._maschinen_punkt, AngebotSeite._kalk_punkte = alt_mp, alt_kp
    AngebotSeite.CHECK_SOFORT = None

# ------------------------------------------------------------------ 3 Grundwerte-Check mit schon gerechneten Summen
k, tab, einst = s.k, s.tabellen, s.einst
m_id = s.kopf.get("maschine")
m_leer = dict(k.maschinen[m_id], **{n_: None for n_ in grundwerte.RICHTWERTE})
import dataclasses  # noqa: E402
k_leer = dataclasses.replace(k, maschinen=dict(k.maschinen, **{m_id: m_leer}))
_, summen = rechnen.kalkulation(s.kopf, s.positionen, s.ergebnis, k_leer, tab, einst)
w1 = grundwerte.wirkung(s.kopf, s.positionen, s.ergebnis, k_leer, tab, einst)
w2 = grundwerte.wirkung(s.kopf, s.positionen, s.ergebnis, k_leer, tab, einst, summen=summen)
assert w1 == w2 and w1 is not None, (w1, w2)
ok("Grundwerte-Check: Wirkung mit den schon gerechneten Summen gleich wie selbst gerechnet")

# ------------------------------------------------------------------ 4 Zusatzarbeiten-Erkennung gemerkt
katalog = tab.get("zusatzarbeiten") or ()
for text in ("Rahmen verzinkt", "nicht verzinkt, pulverbeschichtet RAL 7016", "", "Halter entgraten"):
    a = zusatz_erkennung.treffer(text, katalog)
    b = zusatz_erkennung._treffer(str(text), zusatz_erkennung._muster_liste(katalog)) if text.strip() else []
    assert a == b, (text, a, b)
    a.append(("x", "y"))
    assert zusatz_erkennung.treffer(text, katalog) == b, "Merker durch Aufrufer verändert"
ok("Zusatzarbeiten-Erkennung: gemerkte Treffer gleich wie gerechnet, Kopie je Aufruf")

# ------------------------------------------------------------------ 5 Kalkulationen je Neuladen
z = [0]
kalk = rechnen.kalkulation


def kalk_zaehlen(*a, **kw):
    z[0] += 1
    return kalk(*a, **kw)


rechnen.kalkulation = kalk_zaehlen
AngebotSeite.CHECK_SOFORT = False       # wie mit Bildschirm: der Angebots-Check rechnet erst nach der Ruhe
try:
    s.neu_laden()
finally:
    rechnen.kalkulation = kalk
    AngebotSeite.CHECK_SOFORT = None
assert z[0] <= 2, f"{z[0]} Kalkulationen je Neuladen (höchstens 2)"
ok(f"Neuladen: {z[0]} Kalkulation(en) statt 3")
db.schliessen()
print("Alle Prüfungen bestanden.")
