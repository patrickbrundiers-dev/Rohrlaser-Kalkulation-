"""Prüft Zeiten und Kosten je Arbeitsschritt (J1–J10): Stundensätze und Zeitvorgaben (Stammdaten), Snapshot im
Angebot, Rechenregeln (Gesamtzeit = Rüstzeit + Zeit je Einheit × Menge, Kosten = Minuten / 60 × Stundensatz),
parallele Personalzeit, keine Doppelzählung und den Reiter 'Zeiten & Arbeitskosten'.

Aufruf: python tests/test_zeiten.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402

from rohrlaser import rechnen  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402
from rohrlaser.zeiten_seite import ZeitenSeite  # noqa: E402

EPS = 1e-6


def ok(text):
    print("OK    ", text)


app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
fenster = Hauptfenster(db, tmp, stumm=True)
fenster.resize(1920, 1080)


def angebot(**kopf):
    a = db.angebot_neu(dict(dict(kunde="Test", kundennr="4711"), **kopf))
    for pos, profil, laenge, stueck in ((10, "QR 40x40x3", 800, 4), (20, "QR 40x40x3", 900, 6),
                                        (30, "RR 48,3x2,6", 1000, 10)):
        db.position_neu(a, dict(pos=pos, artikel=f"T{pos}", profil_id=profil, werkstoff_id="S235-10219",
                                laenge=laenge, stueck=stueck, schneidweg=320, einstiche=2))
    s = fenster.angebot_oeffnen(a)
    assert s.optimieren()
    return a, s


def rechnung(s):
    return rechnen.kalkulation(s.kopf, s.positionen, s.ergebnis, s.k, s.tabellen, s.einst)


def schritt(summen, name):
    return next(z for z in summen["zeiten"] if z["schritt"] == name)


def zb_setzen(a, s, aenderung):
    zb = s.kopf["zeitbasis"]
    aenderung(zb)
    db.zeitbasis_speichern(a, zb)
    s.neu_laden()
    return rechnung(s)[1]


# ------------------------------------------------------------------ J1 Vorgaben ändern den Preis nicht
a, s = angebot()
_, summen = rechnung(s)
zb = s.kopf["zeitbasis"]
assert isinstance(zb, dict) and summen["zeitbasis_gespeichert"], "Snapshot beim Anlegen des Angebots"
assert {x["schritt"] for x in zb["schritte"]} >= set(rechnen.SCHRITTE_FEST)
satz_m = summen["satz_maschine"]
for name in rechnen.SCHRITTE_FEST:
    if name != "Programmierung":
        assert abs(schritt(summen, name)["satz"] - satz_m) < EPS, name
assert schritt(summen, "Programmierung")["satz_id"] == "Programmierung"     # Vorgabe: Stundensatz Programmierung
alt = dict(s.kopf, zeitbasis=None)                                  # wie ein Angebot vor Schema 13
_, summen_alt = rechnen.kalkulation(alt, s.positionen, s.ergebnis, s.k, s.tabellen, s.einst)
assert abs(summen_alt["verkauf"] - summen["verkauf"]) < EPS and not summen_alt["zeitbasis_gespeichert"]
assert summen["arbeitsschritte"] == 0
ok(f"J1 Vorgaben: alle festen Schritte mit Maschinenstundensatz {satz_m:.2f} €/h, weitere Schritte 0, "
   f"Verkaufspreis wie ohne Snapshot ({summen['verkauf']:.2f} €)")

# ------------------------------------------------------------------ J2 Gesamtzeit und Kosten je Teil
teile = summen["teile"]
assert teile == 20
summen = zb_setzen(a, s, lambda zb: next(x for x in zb["schritte"] if x["schritt"] == "Entgraten / Nachbearbeitung")
                   .update(ruestzeit=10, ruest_bezug="Angebot", zeit=30, bezug="Teil", satz="Nachbearbeitung"))
e = schritt(summen, "Entgraten / Nachbearbeitung")
satz_nb = s.kopf["zeitbasis"]["saetze"]["Nachbearbeitung"]
assert abs(e["gesamt_min"] - (10 + 30 * teile / 60)) < EPS, e
assert abs(e["kosten"] - e["gesamt_min"] / 60 * satz_nb) < EPS
assert abs(summen["arbeitsschritte"] - e["kosten"]) < EPS
assert e["quelle"] == "von Hand (Angebot)"
ok(f"J2 Entgraten: 10 min + 30 s × {teile} Teile = {e['gesamt_min']:.1f} min, × {satz_nb:.2f} €/h = "
   f"{e['kosten']:.2f} € (Formel: {e['formel']})")

# ------------------------------------------------------------------ J3 Rüstzeit je Abmessung
summen = zb_setzen(a, s, lambda zb: next(x for x in zb["schritte"] if x["schritt"] == "Entgraten / Nachbearbeitung")
                   .update(ruest_bezug="Abmessung"))
e = schritt(summen, "Entgraten / Nachbearbeitung")
assert summen["abmessungen"] == 2 and e["n_ruest"] == 2
assert abs(e["gesamt_min"] - (2 * 10 + 30 * teile / 60)) < EPS
assert abs(summen["arbeitsschritte"] - e["kosten"]) < EPS, "Umlage auf die Teile ergibt wieder die Summe"
ok("J3 Rüstzeit je Abmessung: 2 Abmessungen × 10 min, Umlage auf die Teile je Abmessung ergibt die Summe")

# ------------------------------------------------------------------ J4 Bezug Stange und Position
for bezug, menge in (("Stange", summen["stangen"]), ("Position", 3)):
    summen = zb_setzen(a, s, lambda zb: next(x for x in zb["schritte"] if x["schritt"] == "Verpackung")
                       .update(ruestzeit=0, zeit=60, bezug=bezug))
    v = schritt(summen, "Verpackung")
    assert v["menge"] == menge and abs(v["gesamt_min"] - menge) < EPS, (bezug, v)
    e = schritt(summen, "Entgraten / Nachbearbeitung")
    assert abs(summen["arbeitsschritte"] - e["kosten"] - v["kosten"]) < 1e-4
ok(f"J4 Zeit je Stange ({summen['stangen']} Stangen) und je Position (3) richtig gezählt und auf die Teile umgelegt")

# ------------------------------------------------------------------ J5 parallele Personalzeit
k = rechnen.zeit_summen(summen["zeiten"])
e = schritt(summen, "Entgraten / Nachbearbeitung")                      # Vorgabe: parallel zur Maschine
pr = schritt(summen, "Programmierung")                                   # Vorgabe: Personal, parallel
assert pr["art"] == "Personal" and pr["parallel"] and pr["gesamt_min"] > 0
assert e["parallel"] and abs(k["durchlauf_min"] - (k["maschine_min"] + k["personal_min"] - e["gesamt_min"]
                                                   - pr["gesamt_min"])) < EPS
summen = zb_setzen(a, s, lambda zb: next(x for x in zb["schritte"] if x["schritt"] == "Verpackung")
                   .update(parallel="ja"))
k2 = rechnen.zeit_summen(summen["zeiten"])
v = schritt(summen, "Verpackung")
assert abs(k2["durchlauf_min"] - (k["durchlauf_min"] - v["gesamt_min"])) < EPS
assert abs(k2["arbeitskosten"] - k["arbeitskosten"]) < EPS, "parallel ändert die Kosten nicht"
ok("J5 parallele Personalzeit zählt nicht zur Durchlaufzeit, Kosten bleiben gleich")

# ------------------------------------------------------------------ J6 keine Doppelzählung
z = summen
mit_zeit = sum(x["kosten"] for x in z["zeiten"])
einzeln = (z["laser_schneiden"] + z["gewinde"] + z["ruesten_maschine"] + z["ruesten_abmessungen"]
           + z["stangenwechsel_kosten"] + z["arbeitsschritte"] + z["programmierung"] + z["zusatz"])
assert abs(mit_zeit - einzeln) < 1e-4, (mit_zeit, einzeln)
kosten = rechnen.kostenarten(z, s.einst)
werte = {n: w for (_, w, _), (_, n, _) in zip(kosten, rechnen.KOSTENARTEN)}
herstell = sum(werte[n] for n in ("material", "laser_schneiden", "gewinde", "ruesten_maschine",
                                  "ruesten_abmessungen", "stangenwechsel_kosten", "arbeitsschritte", "zusatz",
                                  "zuschlag_material", "zuschlag_fertigung", "zuschlag_fremdleistung"))
assert abs(herstell - z["herstell"]) < 1e-4, (herstell, z["herstell"])
gruppen = [n for _, namen, summe in rechnen.KOSTEN_GRUPPEN if not summe for n in namen]
assert len(gruppen) == len(set(gruppen))
ok("J6 jede Kostenart genau einmal: Summe der Arbeitsschritte = Einzelkosten, Kostenarten ergeben die Herstellkosten")

# ------------------------------------------------------------------ J7 Snapshot gegen spätere Änderungen
vk = z["verkauf"]
nb = next(r for r in db.zeilen("stundensaetze") if r["satz_id"] == "Nachbearbeitung")
db.aendern("stundensaetze", nb["id"], "satz", 99)
m = dict(db.zeilen("maschinen")[0])
db.aendern("maschinen", m["id"], "stundensatz", (m["stundensatz"] or 0) + 50)
s.neu_laden()
_, z = rechnung(s)
assert abs(z["verkauf"] - vk) < EPS, "spätere Änderung der Einstellungen ändert das Angebot nicht"
assert s.zeiten_seite.aus_einstellungen()
_, z = rechnung(s)
assert s.kopf["zeitbasis"]["saetze"]["Nachbearbeitung"] == 99 and z["verkauf"] > vk
assert schritt(z, "Entgraten / Nachbearbeitung")["kosten"] == 0, "Vorgaben der Einstellungen gelten wieder"
a2, s2 = angebot()
assert s2.kopf["zeitbasis"]["saetze"]["Nachbearbeitung"] == 99, "neues Angebot übernimmt die aktuellen Einstellungen"
ok("J7 Snapshot: Änderungen in den Einstellungen gelten erst nach 'Stundensätze aus Einstellungen' bzw. für neue "
   "Angebote")

# ------------------------------------------------------------------ J8 eigener Stundensatz für einen festen Schritt
_, z = rechnung(s2)
alt_rm = z["ruesten_maschine"]
z = zb_setzen(a2, s2, lambda zb: next(x for x in zb["schritte"] if x["schritt"] == "Rüsten Maschine")
              .update(satz="Rüstpersonal"))
rp = s2.kopf["zeitbasis"]["saetze"]["Rüstpersonal"]
r = schritt(z, "Rüsten Maschine")
assert r["satz_id"] == "Rüstpersonal" and abs(z["ruesten_maschine"] - z["ruestzeit"] / 60 * rp) < EPS
assert abs(r["kosten"] - z["ruesten_maschine"]) < EPS and abs(alt_rm - z["ruesten_maschine"]) > EPS
ok(f"J8 Rüsten Maschine mit Satz Rüstpersonal ({rp:.2f} €/h) statt Maschinensatz: Kostenart und Arbeitsschritt gleich")

# ------------------------------------------------------------------ J9 Nullwerte im Reiter ausgeblendet
zs = s2.zeiten_seite
assert isinstance(zs, ZeitenSeite)
namen = [x["schritt"] for x in zs.modell.zeilen]
sichtbar = [n for r, n in enumerate(namen) if not zs.ansicht.isRowHidden(r)]
assert "Laser schneiden" in sichtbar and "Verpackung" not in sichtbar and "Gewinde Festpreis" not in sichtbar
assert "Rüsten Maschine" in sichtbar
zs.alle.setChecked(True)
assert not any(zs.ansicht.isRowHidden(r) for r in range(len(namen)))
zs.alle.setChecked(False)
assert "Arbeitskosten" in zs.summen.text() and "<td>Personalzeit</td>" in zs.summen.text(), "Programmierung = Personalzeit"
assert "Programmierung" in sichtbar
zs.setzen(dict(z, zeiten=[x for x in z["zeiten"] if x["schritt"] != "Programmierung"]))
assert "<td>Personalzeit</td>" not in zs.summen.text(), "Personalzeit 0 ausgeblendet"
ok(f"J9 Reiter zeigt {len(sichtbar)} von {len(namen)} Schritten (ohne Zeit und Kosten ausgeblendet, Laser immer), "
   "'Alle Arbeitsschritte zeigen' zeigt alle")

# ------------------------------------------------------------------ J10 Ändern im Reiter, ältere Angebote
r = namen.index("Qualitätskontrolle")
assert zs.modell.setData(zs.modell.index(r, 4), "45")
_, z = rechnung(s2)
q = schritt(z, "Qualitätskontrolle")
assert q["zeit_einheit_s"] == 45 and q["quelle"] == "von Hand (Angebot)" and z["arbeitsschritte"] > 0
assert not zs.ansicht.isRowHidden(next(i for i, x in enumerate(zs.modell.zeilen) if x["schritt"] == "Qualitätskontrolle"))
assert "Weitere Arbeitsschritte" in s2.uebersicht_bereich.einzeln.text()
assert "Personalzeit" in s2.uebersicht_bereich.zeiten.text()
r = next(i for i, x in enumerate(zs.modell.zeilen) if x["schritt"] == "Laser schneiden")
assert not zs.modell.bearbeitbar(r, 4) and zs.modell.bearbeitbar(r, 6)
db.zeitbasis_speichern(a2, None)                                         # wie ein Angebot vor Schema 13
s2.neu_laden()
assert "nicht im Angebot gespeichert" in zs.hinweis.text()
assert zs.modell.setData(zs.modell.index(r, 6), "100")
assert s2.kopf["zeitbasis"]["maschine"]["stundensatz"] == 100 and "nicht im Angebot" not in zs.hinweis.text()
ok("J10 Zeit im Reiter geändert (Quelle 'von Hand'), Übersicht zeigt Zeiten und weitere Arbeitsschritte; älteres "
   "Angebot ohne Snapshot erhält ihn beim ersten Ändern")

pfad = Path(s2.csv_export())
text = pfad.read_text(encoding="utf-8-sig")
assert "Arbeitsschritt;Art;Menge" in text and "Laser schneiden;Maschine" in text and "Programmierung;Personal" in text and "Verpackung;" not in text
assert "Weitere Arbeitsschritte je Teil [€]" in text
pfad = Path(s2.kalkulation_pdf())
assert pfad.stat().st_size > 2000
try:
    from pypdf import PdfReader
    inhalt = "".join(seite.extract_text() for seite in PdfReader(pfad).pages)
    assert "Zeiten und Arbeitskosten je Arbeitsschritt" in inhalt and "Stangenwechsel" in inhalt
except ImportError:
    pass
ok("CSV-Export und Kalkulation (PDF) enthalten die Arbeitsschritte mit Zeit oder Kosten")

print("OK: Zeiten und Kosten je Arbeitsschritt")
