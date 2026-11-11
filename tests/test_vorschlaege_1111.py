"""Vorschläge 11.11.2026 nach der Recherche bei anderen Anbietern (Freigabe „Alle Empfehlungen“):
V1 Reaktionszeit Anfrage bis Angebot (Arbeitsstunden, Startseite, Auswertung je Reaktionszeit),
V2 Anfragen „Wichtigste zuerst“, V3 still gewordene Stammkunden (Startseite, Nachfass-Mail, ausblenden),
V4 eigene Angebotsregeln (Hinweis, Warnung, Rückfrage, Zuschlag, Nicht anbieten; Zuschlag in der Preisbasis),
V5 Trefferquote nach Teilemerkmalen.

Aufruf: python tests/test_vorschlaege_1111.py
"""
import datetime as dt
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
from rohrlaser import absage, angebotsregeln, automatik, rechnen, rueckfrage, vertrieb  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402

app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
db.einstellung_setzen("ablageordner", str(tmp / "Ablage"))
fenster = Hauptfenster(db, tmp, stumm=True)
KOPF = {k: v for k, v in B.KOPF.items() if k != "nummer"}
ROHR = dict(B.POSITIONEN[0])
HEUTE = dt.date(2026, 11, 11)


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


# ------------------------------------------------------------------ V1 Reaktionszeit
fr = dt.datetime(2026, 11, 13, 16, 0)            # Freitag 16:00 -> Montag 9:00 = 8 + 9 Arbeitsstunden
assert abs(vertrieb.arbeitsstunden(fr, dt.datetime(2026, 11, 16, 9, 0)) - 17) < 1e-9
assert vertrieb.reaktion(fr.isoformat(), [dict(datum="2026-11-16")]) is None          # ohne Uhrzeit: keine Zahl
assert vertrieb.reaktion(fr.isoformat(), [dict(art="nachgefasst", zeit="2026-11-16T09:00"),
                                          dict(art="mail", zeit="2026-11-17T09:00")]) == 41
assert vertrieb.klasse(3) == "bis 4 Std." and vertrieb.klasse(30) == "1 bis 3 Arbeitstage"
s = angebot(dict(ROHR, stueck=24))
vertrieb.eingang_merken(db, s.id, dt.datetime.now() - dt.timedelta(minutes=30))
pfad = s.angebot_pdf(oeffnen=False)
assert pfad and db.angebot(s.id)["versand"][-1].get("zeit"), db.angebot(s.id)["versand"]
r = vertrieb.reaktionen(db.angebote(), db.anfrage_eingaenge())
assert s.id in r and r[s.id] <= 0.6, r
text = fenster.start._reaktion_text(db.angebote())
assert "Reaktionszeit Anfrage bis Angebot" in text, text
a = absage.auswertung(db.angebote(), reaktionen=r, zeitraum=None)
assert a["reaktion"] and a["reaktion"][0]["name"] == "bis 4 Std."
ok(f"V1 Reaktionszeit: Fr 16 Uhr bis Mo 9 Uhr = 17 Std., PDF merkt die Uhrzeit, Startseite: {text.strip('; ')}")

# ------------------------------------------------------------------ V3 stille Stammkunden (Zeilen der Angebotsliste)
zeilen = [dict(id=i, kundennr="K-1", kunde="Stamm GmbH", vorgang="Beauftragt", datum=d, vk_netto=1000.0)
          for i, d in enumerate(("2026-05-01", "2026-05-29", "2026-06-26", "2026-07-24"), 1)]
zeilen += [dict(id=9, kundennr="K-2", kunde="Neu KG", vorgang="Beauftragt", datum="2026-11-01", vk_netto=500.0)]
st = vertrieb.stille_kunden(zeilen, HEUTE)
assert [x["kundennr"] for x in st] == ["K-1"] and st[0]["abstand"] == 28 and st[0]["seit"] == 110, st
assert "alle 4 Wochen" in vertrieb.still_text(st[0]) and "vor 16 Wochen" in vertrieb.still_text(st[0])
assert not vertrieb.stille_kunden(zeilen, HEUTE, aus={"K-1"})
assert not vertrieb.stille_kunden(zeilen, dt.date(2026, 8, 20))           # 27 Tage: noch nicht still
# in der Datei: Kunde mit drei Aufträgen vor Monaten
for d in ("2026-03-02", "2026-03-30", "2026-04-27"):
    i = db.angebot_neu(dict(KOPF, datum=d))
    db.position_neu(i, dict(ROHR))
    db.vorgang_setzen(i, "Beauftragt")
auf = [x for x in automatik.aufgaben(db, HEUTE) if x["art"] == "still"]
assert len(auf) == 1 and auf[0]["kundennr"] == KOPF["kundennr"] and "Lange nichts bestellt" in auf[0]["text"], auf
mail = fenster.stiller_kunde(KOPF["kundennr"], wahl="mail")
inhalt = Path(mail).read_text(encoding="utf-8", errors="replace")
assert mail and "4711-001 Holm links" in inhalt and "X-Unsent: 1" in inhalt, inhalt[:400]
assert fenster.stiller_kunde(KOPF["kundennr"], wahl="aus") == "aus"
assert not [x for x in automatik.aufgaben(db, HEUTE) if x["art"] == "still"]
db.einstellung_setzen(vertrieb.STILL_AUS, "{}")
db.einstellung_setzen("stille_kunden", "nein")
assert not [x for x in automatik.aufgaben(db, HEUTE) if x["art"] == "still"]
db.einstellung_setzen("stille_kunden", "ja")
ok("V3 Stammkunde sonst alle 4 Wochen, seit 16 Wochen still: Startseite, Nachfass-Mail mit Artikeln, ausblenden, aus")

# ------------------------------------------------------------------ V2 Wichtigste Anfragen zuerst


class A:
    def __init__(self, name, kunde, gesperrt=None):
        self.schluessel, self.kunde, self.gesperrt = name, kunde, gesperrt


werte = vertrieb.kunden_werte(zeilen + [dict(id=20, kundennr="K-3", kunde="Klein", vorgang="Abgelehnt",
                                             datum="2026-10-01", vk_netto=200.0)])
liste = [A("klein", "K-3"), A("stamm", "K-1"), A("unbekannt", None), A("gesperrt", "K-1", gesperrt="AB"),
         A("eilig", None)]
folge = [a.schluessel for a in vertrieb.sortieren(liste, werte, {"eilig": ("rot", None, "")})]
assert folge == ["eilig", "stamm", "klein", "unbekannt", "gesperrt"], folge
w, t = vertrieb.wichtigkeit(werte, "K-1")
assert w > 0 and t.startswith("Kunde vergibt ca.") and "üblich 1.000 €" in t, t
# Anfrage-Karte: Kunde der Datei (3 Aufträge) vor einem unbekannten; Vorgabe bleibt die Dringlichkeit
karte = fenster.start.anfragen
neu = [A("fremd", None), A("bekannt", KOPF["kundennr"])]
for x in neu:
    x.dateien, x.zeit = [], None
assert [a.schluessel for a in karte._ampel_sortieren(list(neu))] == ["fremd", "bekannt"] and not karte._wichtig
db.einstellung_setzen("anfragen_sortierung", vertrieb.SORT_WICHTIG)
assert [a.schluessel for a in karte._ampel_sortieren(list(neu))] == ["bekannt", "fremd"]
assert karte._wichtig["bekannt"].startswith("Kunde vergibt ca.") and not karte._wichtig["fremd"]
db.einstellung_setzen("anfragen_sortierung", vertrieb.SORT_DRINGLICH)
ok(f"V2 Wichtigste zuerst: rote Ampel oben, dann nach erwartetem Wert ({t}), gesperrte ans Ende")

# ------------------------------------------------------------------ V4 eigene Angebotsregeln
db.einstellung_setzen("preisluecke_schwelle", 0)
basis = angebot(dict(ROHR, stueck=24))
vorher = verkauf(basis)
kat = rechnen.kategorie(ROHR["werkstoff_id"], basis.k)
assert [r["name"] for r in db.zeilen("angebotsregeln")] == [r["name"] for r in angebotsregeln.beispiele()]
assert all(r["aktiv"] == "nein" for r in db.zeilen("angebotsregeln"))       # Beispiele aus: nichts ändert sich


def regel(**w):
    return dict({f: None for f in ("kundennr", "kategorie", "werkstoff_id", "profilform", "wand_von", "wand_bis",
                                   "laenge_von", "laenge_bis", "stueck_von", "stueck_bis", "konturen_ab", "merkmal",
                                   "zusatzarbeit", "zuschlag", "text", "bemerkung")}, aktiv="ja", **w)


ids = [db.neu("angebotsregeln", regel(name="Test Zuschlag", kategorie=kat, wand_von=1.5, wirkung="Zuschlag",
                                       zuschlag=10.0, text="dünnwandig genau")),
       db.neu("angebotsregeln", regel(name="Test Warnung", laenge_von=1000.0, wirkung="Warnung",
                                       text="lange Teile prüfen")),
       db.neu("angebotsregeln", regel(name="Test Rückfrage", stueck_bis=30, wirkung="Rückfrage",
                                       text="Gibt es eine Jahresmenge?")),
       db.neu("angebotsregeln", regel(name="Test Nein", kundennr="K-NIE", wirkung="Nicht anbieten",
                                       text="gesperrt"))]
s = angebot(dict(ROHR, stueck=24))
su = s._rechnung()[1]
fracht = su.get("fracht") or 0.0
assert su["regel"] > 0 and abs(su["regel"] - 0.10 * (vorher - fracht)) < 0.06 * (vorher - fracht), (su["regel"], vorher)
assert verkauf(s) > vorher + 0.08 * (vorher - fracht)
assert any(t == "Zuschlag Angebotsregeln" for t, _, _ in rechnen.KOSTENARTEN)
punkte = s.freigabe_punkte()
regel_punkte = [p for p in punkte if "Angebotsregel" in (p.details or "")]
texte = {p.text: p.art for p in regel_punkte}
assert len(regel_punkte) == len(texte) == 3, [p.text for p in regel_punkte]          # jede Regel genau einmal
assert texte.get("Zuschlag 10 % durch Angebotsregel „Test Zuschlag“: dünnwandig genau") == "HINWEIS", texte
assert texte.get("lange Teile prüfen") == "WARNUNG" and texte.get("Rückfrage: Gibt es eine Jahresmenge?") == "WARNUNG"
assert not any("gesperrt" in t for t in texte)                     # anderer Kunde
assert "Rückfrage: Gibt es eine Jahresmenge?" in rueckfrage.punkte(punkte)
nie = angebot(dict(ROHR, stueck=24), kopf=dict(kundennr="K-NIE"))
assert any(p.art == "FEHLER" and "Nicht anbieten" in p.text for p in nie.freigabe_punkte())
# Preisbasis: Zuschlag-Regeln festgeschrieben; Snapshot von davor ohne Zuschlag (wie verschickt)
pb = rechnen.preisbasis_aus(s.kopf, s.positionen, s.k_aktuell, s.tabellen_aktuell)
assert [r["name"] for r in pb["angebotsregeln"]] == ["Test Zuschlag"]
tab = rechnen.preisbasis_anwenden(dict(s.kopf, preisbasis=pb), s.k_aktuell, s.tabellen_aktuell)[1]
assert [r["name"] for r in tab["angebotsregeln"]] == ["Test Zuschlag"]
pb.pop("angebotsregeln")
assert rechnen.preisbasis_anwenden(dict(s.kopf, preisbasis=pb), s.k_aktuell, s.tabellen_aktuell)[1][
    "angebotsregeln"] == []
# Regel ausschalten: Preis wie vorher
db.aendern("angebotsregeln", ids[0], "aktiv", "nein")
s2 = angebot(dict(ROHR, stueck=24))
assert abs(verkauf(s2) - vorher) < 0.01 and not s2._rechnung()[1].get("regel")
db.loeschen("angebotsregeln", ids)
ok(f"V4 Angebotsregeln: Zuschlag 10 % ({vorher:.2f} -> {verkauf(s):.2f} €), Warnung, Rückfrage in der Rückfrage-"
   "Mail, Nicht anbieten als Fehler, Zuschlag in der Preisbasis, alte Angebote ohne")

# ------------------------------------------------------------------ V5 Trefferquote nach Teilemerkmalen
m = vertrieb.merkmale(db.positionen_merkmale(), db.kontext())
x = m[s.id]
assert x == dict(form="Rundrohr", wand="Wand bis 2 mm", laenge="Länge über 1 bis 3 m", konturen="keine Innenkonturen",
                 stueck="11 bis 100 Stück"), x
a = absage.auswertung(db.angebote(), merkmale=m, zeitraum=None)
assert {g["name"] for g in a["form"]} >= {"Rundrohr"} and a["stueck"][0]["name"] == "11 bis 100 Stück"
fenster.bereich.admin = True
d = fenster.angebots_auswertung()
namen = [d.reiter.tabText(i) for i in range(d.reiter.count())]
assert {"Je Profilform", "Je Wandstärke", "Je Teilelänge", "Je Komplexität", "Je Stückzahl",
        "Je Reaktionszeit"} <= set(namen), namen
assert d.tabellen["form"].rowCount() >= 1 and d.tabellen["reaktion"].rowCount() >= 1
ok("V5 Auswertung je Profilform, Wand, Länge, Komplexität, Stückzahl und Reaktionszeit")
print("ALLE OK")
