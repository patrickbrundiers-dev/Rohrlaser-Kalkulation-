"""Roadmap Kalkulation, Phase 1 (Freigabe Patrick 12.11.2026 „Mit Phase 1 beginnen“).

Paket 1 Preissicherheit:
MAT-009 Preisalter-Warnung (preisalter.py): Materialpreis aus 'Preise'/'Lieferlängen' älter als preisalter_tage →
        HINWEIS mit Ziel Materialanfrage; 0 = aus; ohne Datum, mit €/m in der Position oder Kundenmaterial kein Hinweis.
OFFER-017 Mindermengenzuschlag als eigene Zeile (mindermenge_zeile = ja): Stückpreise ohne Anhebung, Summe gleich.
OFFER-018 Gültigkeit je Werkstoff-Kategorie (gueltigkeit_kategorie): die kürzeste gilt, länger verlängert nie.
CAM-010 „bis zu x Stück mehr passen ohne weitere Stange“ (mehrmenge.py): Hinweis mit Stückpreis, Probe-Optimierung
        ohne zusätzliche Stange; Sätze ohne Hinweis.
CAD-004 Live-Preis im Rohr-Editor: Stückpreis mit den Eingaben und Differenz zum Öffnen (live_preis.py).
GEO-018 unklare STEP-Merkmale als Frage in der Rückfrage-Mail (rueckfrage.step_fragen).
OFFER-020 Angebotstext mit Bearbeitung aus den Merkmalen (angebotstext_bearbeitung).
OFFER-010 Vorbehalt bei ungeprüften STEP-Teilen (vorbehalt_ungeprueft): Text unter der Position, leer = aus.

Aufruf: python tests/test_phase1_1211.py
"""
import datetime
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402

import beispiel_angebot as B  # noqa: E402
from rohrlaser import preisalter, rechnen  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402

app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
fenster = Hauptfenster(db, tmp, stumm=True)
KOPF = {k: v for k, v in B.KOPF.items() if k != "nummer"}
ROHR = dict(B.POSITIONEN[0])          # RR 42,4x2,0 S235, 1250 mm (Profilpreis 1,45 €/kg in den Beispieldaten)
HEUTE = datetime.date.today()


def ok(text):
    print("OK  ", text)


def angebot(*positionen, kopf=None):
    i = db.angebot_neu(dict(KOPF, **(kopf or {})))
    for p in positionen:
        db.position_neu(i, p)
    s = fenster.angebot_oeffnen(i)
    s.optimieren()
    return s


def verkauf(s):
    return s._rechnung()[1]["verkauf"]


# ------------------------------------------------------------------ MAT-009 Preisalter
zeile = next(z for z in db.zeilen("preise") if (z["profil_id"], z["werkstoff_id"]) == ("RR 42,4x2,0", "S235-10219"))
db.aendern("preise", zeile["id"], "gueltig_ab", None)      # ohne Datum: kein Hinweis
s = angebot(dict(ROHR, stueck=24))
assert not [p for p in s.freigabe_punkte() if p.ziel == preisalter.ZIEL]
vorher = verkauf(s)
alt = (HEUTE - datetime.timedelta(days=45)).isoformat()
db.aendern("preise", zeile["id"], "gueltig_ab", alt)
s.neu_laden()
punkte = [p for p in s.freigabe_punkte() if p.ziel == preisalter.ZIEL]
assert len(punkte) == 1 and punkte[0].art == "HINWEIS", punkte
assert "RR 42,4x2,0 S235-10219" in punkte[0].text and "45 Tage alt" in punkte[0].text, punkte[0].text
assert "Materialanfrage" in punkte[0].details and "Pos. 10" in punkte[0].details, punkte[0].details
assert abs(verkauf(s) - vorher) < 1e-9                 # nur Hinweis
ok(f"MAT-009 Preis seit {alt} (45 Tage): {punkte[0].text}")
# Grenze, aus, €/m in der Position, Kundenmaterial
db.einstellung_setzen("preisalter_tage", 60)
assert not preisalter.punkte(s.positionen, s.k, s.tabellen, db.einstellungen())
db.einstellung_setzen("preisalter_tage", 0)
assert not preisalter.punkte(s.positionen, s.k, s.tabellen, db.einstellungen())
db.einstellung_setzen("preisalter_tage", 30)
p = dict(s.positionen[0])
assert preisalter.alte([p], s.k, s.tabellen, db.einstellungen())
assert not preisalter.alte([dict(p, preis_m=3.0)], s.k, s.tabellen, db.einstellungen())
assert not preisalter.alte([dict(p, material_herkunft=rechnen.KUNDENMATERIAL)], s.k, s.tabellen, db.einstellungen())
# zwei Positionen derselben Abmessung: ein Punkt mit beiden Positionen
e = preisalter.alte([p, dict(p, pos=20)], s.k, s.tabellen, db.einstellungen())
assert len(e) == 1 and e[0]["zeilen"] == [0, 1] and e[0]["tage"] == 45
# Hinspringen öffnet die Materialanfrage
gerufen = []
s.material_anfragen = lambda *a, **kw: gerufen.append(1)
s.check_link("check:materialanfrage")
assert gerufen == [1]
db.aendern("preise", zeile["id"], "gueltig_ab", HEUTE.isoformat())
ok("MAT-009 Grenze 60 Tage/0 = aus, €/m und Kundenmaterial ohne Hinweis, Hinspringen → Materialanfrage")

# ------------------------------------------------------------------ OFFER-017 Mindermengenzuschlag
import json  # noqa: E402

from rohrlaser import ausgabe  # noqa: E402

db.einstellung_setzen("mindestpreis", 2000.0)
klein = angebot(dict(ROHR, stueck=2))
su = klein._rechnung()[1]
assert su["mindestpreis_gilt"], su["verkauf_kalkuliert"]
mit = klein.angebot_daten(staffeln=False)
assert not [z for z in mit["zeilen"] if z.get("mindermenge")] and mit["mindestpreis"]
db.einstellung_setzen("mindermenge_zeile", "ja")
klein = angebot(dict(ROHR, stueck=2))
ohne = klein.angebot_daten(staffeln=False)
zz = [z for z in ohne["zeilen"] if z.get("mindermenge")]
teil = next(z for z in ohne["zeilen"] if z["art"] == "teil")
assert len(zz) == 1 and zz[0]["art"] == "einmal" and "Mindermengenzuschlag" in zz[0]["text"], ohne["zeilen"]
assert "2.000,00" in zz[0]["text"] and not ohne["mindestpreis"], zz[0]["text"]
assert teil["preis"] < next(z for z in mit["zeilen"] if z["art"] == "teil")["preis"]
assert abs(ohne["netto"] - mit["netto"]) <= 0.02, (ohne["netto"], mit["netto"])
assert abs(verkauf(klein) - su["verkauf"]) < 1e-6           # Rechnung unverändert
ok(f"OFFER-017 Stückpreis {teil['preis']:.2f} € + Mindermengenzuschlag {zz[0]['preis']:.2f} € = "
   f"{ohne['netto']:.2f} € (vorher {mit['netto']:.2f} € in den Stückpreisen)")
db.einstellung_setzen("mindermenge_zeile", "nein")
db.einstellung_setzen("mindestpreis", 0.0)

# ------------------------------------------------------------------ OFFER-018 Gültigkeit je Kategorie
einst = dict(db.einstellungen(), gueltigkeit=30)
assert ausgabe.gueltigkeit_tage(einst, s.positionen, s.k) == 30
assert ausgabe.gueltigkeit_kategorien(dict(einst, gueltigkeit_kategorie="Edelstahl 14; Stahl: 10 Tage")) == \
    {"edelstahl": 14, "stahl": 10}
assert ausgabe.gueltigkeit_tage(dict(einst, gueltigkeit_kategorie="Edelstahl 14"), s.positionen, s.k) == 30
assert ausgabe.gueltigkeit_tage(dict(einst, gueltigkeit_kategorie="Stahl 10"), s.positionen, s.k) == 10
assert ausgabe.gueltigkeit_tage(dict(einst, gueltigkeit_kategorie="Stahl 60"), s.positionen, s.k) == 30
db.einstellung_setzen("gueltigkeit_kategorie", "Stahl 10")
g = angebot(dict(ROHR, stueck=24), kopf=dict(datum="2026-11-01"))
d = g.angebot_daten(staffeln=False)
assert d["gueltig_tage"] == 10
assert ausgabe.gueltig_bis(g.kopf, g.einst, g.positionen, g.k) == datetime.date(2026, 11, 11)
db.einstellung_setzen("gueltigkeit_kategorie", "")
ok("OFFER-018 Stahl 10 Tage: gültig bis 11.11.2026 statt 01.12.2026; Edelstahl 14 und Stahl 60 ändern nichts")

# ------------------------------------------------------------------ OFFER-010 Vorbehalt
gelb = dict(ROHR, stueck=24, step_merkmale=json.dumps(dict(ampel="gelb", ampel_gruende=["Gewinde unklar"])))
v = angebot(gelb, dict(ROHR, pos=20, stueck=24))
assert not any("Vorbehalt" in z["text"] for z in v.angebot_daten(staffeln=False)["zeilen"])
db.einstellung_setzen("vorbehalt_ungeprueft", "Preis unter Vorbehalt der Zeichnungsprüfung")
v = angebot(gelb, dict(ROHR, pos=20, stueck=24))
texte = [z["text"] for z in v.angebot_daten(staffeln=False)["zeilen"] if z["art"] == "teil"]
assert texte[0].endswith("\nPreis unter Vorbehalt der Zeichnungsprüfung") and "Vorbehalt" not in texte[1], texte
db.einstellung_setzen("vorbehalt_ungeprueft", "")
ok("OFFER-010 nur die gelbe Position bekommt den Vorbehalt, leer = aus")

# ------------------------------------------------------------------ CAM-010 Mehrmenge
from rohrlaser import mehrmenge  # noqa: E402

m = angebot(dict(ROHR, stueck=22))
n_st = len(m.ergebnis["stangen"])
kand = mehrmenge.kandidaten(m.kopf, m.positionen, m.ergebnis, m.k)
assert kand.get(0, 0) >= 1, (kand, [x.get("rest") for x in m.ergebnis["stangen"]])
pk = [p for p in m.freigabe_punkte() if "Stück mehr passen ohne weitere Stange" in p.text]
assert len(pk) == 1 and pk[0].art == "HINWEIS" and pk[0].ziel == "pos:0", pk
mehr = int(pk[0].text.split("bis zu ")[1].split(" ")[0])
probe = angebot(dict(ROHR, stueck=22 + mehr))
assert len(probe.ergebnis["stangen"]) == n_st, (len(probe.ergebnis["stangen"]), n_st)
assert probe._rechnung()[0][0]["preis_teil"] < m._rechnung()[0][0]["preis_teil"]
assert m.positionen[0]["stueck"] == 22                     # nur Hinweis
assert not [p for p in probe.freigabe_punkte() if "Stück mehr passen" in p.text]     # Stangen jetzt voll
assert not mehrmenge.geeignet(dict(m.positionen[0], satz="A"))
ok(f"CAM-010 {pk[0].text}; Probe mit {22 + mehr} Stück: {n_st} Stangen wie vorher")

# ------------------------------------------------------------------ CAD-004 Live-Preis
from rohrlaser import live_preis  # noqa: E402
from rohrlaser.schneidweg_dialog import SchneidwegDialog  # noqa: E402

lv = angebot(dict(ROHR, stueck=24))
p0 = lv.positionen[0]
d = SchneidwegDialog(lv, p0, lv.k.profile[p0["profil_id"]], lv.kopf, lv.k, lv.tabellen, lv.db, lv.positionen)
d.rechnen()
jetzt, start = d.live_preis()
assert abs(jetzt - start) < 1e-6 and abs(start - lv._rechnung()[0][0]["preis_teil"]) < 0.1, (jetzt, start)
assert live_preis.text(jetzt, start)[1] == "Stückpreis wie beim Öffnen"
alt_eingaben = d.eingaben
d.eingaben = lambda: dict(alt_eingaben(), konturen=[dict(art="Bohrung", anzahl=12, d=12)])
d.rechnen()
jetzt2, start2 = d.live_preis()
assert start2 == start and jetzt2 > start + 0.01, (jetzt2, start)
wert, tip = live_preis.text(jetzt2, start2)
assert "(+" in wert and "beim Öffnen" in tip, (wert, tip)
assert lv.positionen[0] == p0                           # nur Anzeige
assert SchneidwegDialog(lv, dict(p0, id=None), lv.k.profile[p0["profil_id"]], lv.kopf, lv.k, lv.tabellen,
                        neu=True).live_preis() is None
ok(f"CAD-004 Live-Preis: 12 Bohrungen Ø12 → {wert} (beim Öffnen {start:.2f} €)")

# ------------------------------------------------------------------ GEO-018 Rückfrage aus dem Prüfstatus
from rohrlaser import rueckfrage  # noqa: E402

fr = rueckfrage.step_fragen([
    dict(ROHR, step_merkmale=json.dumps(dict(ampel="gelb", ampel_gruende=["Gewinde ja/nein unklar"]))),
    dict(ROHR, pos=20, artikel="4711-002", step_merkmale=json.dumps(dict(merkmale=[
        dict(merkmal="Werkstoff", wert="", status="nicht erkannt", grund="nicht in der STEP"),
        dict(merkmal="Länge", wert="1250", status="sicher")]))),
    dict(ROHR, pos=30, step_merkmale=json.dumps(dict(geprueft=True, ampel="gelb", ampel_gruende=["x"]))),
    dict(ROHR, pos=40)])
assert fr == ["Pos. 10 4711-001: bitte bestätigen – Gewinde ja/nein unklar",
              "Pos. 20 4711-002: bitte bestätigen – Werkstoff (nicht in der STEP)"], fr
assert fr[1] in rueckfrage.punkte([], [dict(ROHR, pos=20, artikel="4711-002", step_merkmale=json.dumps(dict(
    merkmale=[dict(merkmal="Werkstoff", wert="", status="nicht erkannt", grund="nicht in der STEP")])))], [None])
ok("GEO-018 gelbe Gründe und offene Merkmale als Fragen, bestätigte und ohne STEP nicht")

# ------------------------------------------------------------------ OFFER-020 Bearbeitung im Angebotstext
tech = json.dumps(dict(a=dict(winkel=45), b=dict(winkel=0), konturen=[
    dict(art="Bohrung", anzahl=4, d=8), dict(art="Bohrung", anzahl=2, d=10), dict(art="Langloch", anzahl=1, l=20, b=8),
    dict(art="Gravur", anzahl=1)]))
assert ausgabe.bearbeitung_text(dict(ROHR, technik=tech)) == "Bearbeitung: Gehrung 45°, 6 × Bohrung, 1 × Langloch"
assert ausgabe.bearbeitung_text(dict(ROHR)) == ""
bt = angebot(dict(ROHR, stueck=24, technik=tech))
assert "Bearbeitung:" not in bt.angebot_daten(staffeln=False)["zeilen"][0]["text"]
db.einstellung_setzen("angebotstext_bearbeitung", "ja")
bt = angebot(dict(ROHR, stueck=24, technik=tech))
t0 = bt.angebot_daten(staffeln=False)["zeilen"][0]["text"]
assert "\nBearbeitung: Gehrung 45°, 6 × Bohrung, 1 × Langloch" in t0, t0
db.einstellung_setzen("angebotstext_bearbeitung", "nein")
ok("OFFER-020 Angebotstext: " + t0.replace("\n", " | "))

print("Alle Tests Phase 1 bestanden.")
