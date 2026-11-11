"""Kalkulation genauer (Plan 11.11.2026, Freigabe „Alle Empfehlungen“):
A1 Preislücke beim Tonnenpreis (preisluecke.py): Hinweis im Angebots-Check, „Erledigen“ legt den ähnlichen
   Profilpreis an, Rückgängig löscht ihn; Schwelle 0 = aus.
A2 Mindestbetrag je Angebot auch an der Abrechnungsregel (vor dem der Zusatzarbeit).
A3 Gleiches Teil in mehreren Positionen: Programmierung einmal (Einstellung programmierung_gleich; von Hand
   eingetragene Zeit bleibt je Position; festgeschriebene Angebote von davor rechnen wie verschickt).
B1 Schnittschema je Mengenstufe im Kalkulations-PDF.
C1 Plausibilität: Stückpreis fällt mit der Menge, teurerer Werkstoff und dickere Wand werden nicht billiger, ein Teil
   in zwei Positionen kostet so viel wie in einer.

Aufruf: python tests/test_kalkulation_1111.py
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
from PySide6.QtWidgets import QApplication  # noqa: E402

import beispiel_angebot as B  # noqa: E402
from rohrlaser import preisluecke, rechnen  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402
from rohrlaser.stammdaten import ZUSATZ_STRAHLEN  # noqa: E402

app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
fenster = Hauptfenster(db, tmp, stumm=True)
KOPF = {k: v for k, v in B.KOPF.items() if k != "nummer"}
ROHR = dict(B.POSITIONEN[0])          # RR 42,4x2,0 S235, 1250 mm (Profilpreis 1,45 €/kg in den Beispieldaten)


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


# ------------------------------------------------------------------ C1 Plausibilität (vor A1: ohne neue Preise)
mengen = [verkauf(angebot(dict(ROHR, stueck=n))) / n for n in (10, 24, 100, 500)]
assert all(a > b for a, b in zip(mengen, mengen[1:])), mengen
ok(f"C1 Stückpreis fällt mit der Menge: {', '.join(f'{x:.2f}' for x in mengen)} €")
eine = verkauf(angebot(dict(ROHR, stueck=24)))
zwei = angebot(dict(ROHR, stueck=12), dict(ROHR, pos=11, stueck=12))
assert abs(verkauf(zwei) - eine) < 0.02, (verkauf(zwei), eine)
ok(f"A3/C1 gleiches Teil in zwei Positionen = eine Position: {verkauf(zwei):.2f} € = {eine:.2f} €")
su = zwei._rechnung()[1]
assert su["programmierung_gleich"] == 2 and abs(su["programmierung_min"] - 5.0) < 1e-9, su["programmierung_min"]
assert any("einmal programmiert" in z["quelle"] for z in su["zeiten"] if z["schritt"] == "Programmierung")

# A3: Zeit von Hand bleibt je Position, Einstellung nein = wie bisher
hand = angebot(dict(ROHR, stueck=12, prog_zeit=8), dict(ROHR, pos=11, stueck=12))
assert abs(hand._rechnung()[1]["programmierung_min"] - 13.0) < 1e-9
db.einstellung_setzen("programmierung_gleich", "nein")
aus = angebot(dict(ROHR, stueck=12), dict(ROHR, pos=11, stueck=12))
assert abs(aus._rechnung()[1]["programmierung_min"] - 10.0) < 1e-9 and verkauf(aus) > eine + 1
db.einstellung_setzen("programmierung_gleich", "ja")
# andere Artikel-Nr. bzw. andere Länge: kein gleiches Teil
anders = angebot(dict(ROHR, stueck=12), dict(ROHR, pos=11, stueck=12, laenge=1200.0))
assert abs(anders._rechnung()[1]["programmierung_min"] - 10.0) < 1e-9
# festgeschrieben vor dem 11.11.2026 (ohne Merker): Programmierung je Position wie verschickt
pb = rechnen.preisbasis_aus(zwei.kopf, zwei.positionen, zwei.k_aktuell, zwei.tabellen_aktuell)
assert pb["einstellungen"]["programmierung_gleich"] == "ja"
pb["einstellungen"].pop("programmierung_gleich")
e = rechnen.preisbasis_anwenden(dict(zwei.kopf, preisbasis=pb), zwei.k_aktuell, zwei.tabellen_aktuell)[1]["einstellungen"]
assert e["programmierung_gleich"] == "nein"
ok("A3 von Hand bleibt je Position, Einstellung nein und alte Angebote wie bisher, andere Länge getrennt")

# ------------------------------------------------------------------ A1 Preislücke beim Tonnenpreis
s235 = verkauf(angebot(dict(ROHR, stueck=24)))
s = angebot(dict(ROHR, stueck=24, werkstoff_id="S355-10219"))
vorher = verkauf(s)
assert vorher < s235                                    # Befund 11.11.: S355 ohne Profilpreis billiger als S235
punkte = [x for x in s.freigabe_punkte() if getattr(x, "aktion", None) == preisluecke.AKTION]
assert len(punkte) == 1 and punkte[0].art == "WARNUNG" and "Tonnenpreis 1,05 €/kg" in punkte[0].text, punkte
assert "1,45 €/kg" in punkte[0].text and "1,52 €/kg" in punkte[0].details, punkte[0].details   # × 1050/1000
assert s.check_erledigen([preisluecke.AKTION]) == [preisluecke.AKTION]
zeile = rechnen.preis_zeile("RR 42,4x2,0", "S355-10219", s.k, s.tabellen)
assert zeile and zeile["basis"] == "€/kg" and zeile["preis"] == 1.52 and "Preislücke" in zeile["bemerkung"]
s.optimieren()
nachher = verkauf(s)
assert nachher > s235 > vorher, (vorher, s235, nachher)
assert not [x for x in s.freigabe_punkte() if getattr(x, "aktion", None) == preisluecke.AKTION]
ok(f"A1 S355 ohne Profilpreis: Warnung, Erledigen legt 1,52 €/kg an: {vorher:.2f} → {nachher:.2f} € "
   f"(S235 {s235:.2f} €)")
db.loeschen("preise", [zeile["id"]])                   # wie „Rückgängig“
s.neu_laden()

# Schwelle 0 = aus; Kundenmaterial und Preis im Angebot zählen nicht
db.einstellung_setzen("preisluecke_schwelle", 0)
assert not preisluecke.punkte(s.kopf, s.positionen, s.k, s.tabellen, db.einstellungen())
db.einstellung_setzen("preisluecke_schwelle", 10)
p = dict(s.positionen[0])
assert not preisluecke.luecken(s.kopf, [dict(p, preis_m=3.0)], s.k, s.tabellen, db.einstellungen())
assert preisluecke.luecken(s.kopf, [p], s.k, s.tabellen, db.einstellungen())
# ähnlicher Profilpreis nicht deutlich über dem Tonnenpreis: kein Hinweis
billig = [dict(z, preis=1.10) if z.get("profil_id") == "RR 42,4x2,0" else z for z in s.tabellen["preise"]]
assert not preisluecke.luecken(s.kopf, [p], s.k, dict(s.tabellen, preise=billig), db.einstellungen())
ok("A1 Schwelle 0 = aus, Preis im Angebot und Tonnenpreis über ähnlichen Preisen ohne Hinweis")

# ------------------------------------------------------------------ C1 Werkstoff und Wand nach Preisangleich
dick = angebot(dict(ROHR, stueck=24, profil_id="RR 42,4x2,6"))
assert preisluecke.luecken(dick.kopf, dick.positionen, dick.k, dick.tabellen, db.einstellungen())
dick.check_erledigen([preisluecke.AKTION])
dick.optimieren()
assert verkauf(dick) > s235, (verkauf(dick), s235)
ok(f"C1 Wand 2,6 nach Erledigen teurer als 2,0: {verkauf(dick):.2f} € > {s235:.2f} €")

# ------------------------------------------------------------------ A2 Mindestbetrag je Angebot an der Regel
strahlen = next(z for z in db.zeilen("zusatzarbeiten") if z["name"] == ZUSATZ_STRAHLEN)
stand = rechnen.zusatz_stand(strahlen, rechnen.stundensaetze(db.tabellen()))
e_neu = dict(name=ZUSATZ_STRAHLEN, menge=None, preis=None, text=None, stand=stand)
pz = dict(ROHR, stueck=2, zusatz=json.dumps([e_neu], ensure_ascii=False))
s = angebot(pz)
kat = rechnen.kategorie(ROHR["werkstoff_id"], s.k)
regel = dict(name="Strahlen mind. 80", zusatzarbeit=ZUSATZ_STRAHLEN, zuordnung="nur Preis", aktiv="ja",
             kategorie=kat, preis=0.40, art="€/kg", mindest=80.0)
tab = dict(s.tabellen, arbeitsgang_regeln=[regel])
z = rechnen.zusatz_werte(s.positionen[0], s.k, tab)[0]
assert z["mindest"] == 80.0 and z["regel"] == "Strahlen mind. 80"
zus = rechnen._zusatz_umlegen(s.positionen, [0], [0], s.k, tab)
assert abs(zus[0][0]["teil"] * 2 - 80.0) < 1e-9, zus[0][0]
ohne = rechnen._zusatz_umlegen(s.positionen, [0], [0], s.k, dict(tab, arbeitsgang_regeln=[dict(regel, mindest=None)]))
assert abs(ohne[0][0]["teil"] * 2 - strahlen["mindest"]) < 1e-9 and strahlen["mindest"] == 60    # wie bisher
ok(f"A2 Regel mit Mindestbetrag 80 € je Angebot vor den 60 € der Zusatzarbeit: 2 Teile je {zus[0][0]['teil']:.2f} €")

# ------------------------------------------------------------------ B1 Schnittschema je Stufe im Kalkulations-PDF
from rohrlaser import pdf  # noqa: E402
s = fenster.angebot_oeffnen(B.anlegen(db))
s.optimieren()
s.staffelpreise_rechnen()
s = fenster.angebot_oeffnen(s.id)
sp = (s.kopf.get("staffelpreise") or {}).get("zeilen")
teile = pdf._schnittschema_stufen(sp)
assert teile and "Schnittschema je Mengenstufe" in teile[2].text
pfad = s.kalkulation_pdf()
import pypdfium2  # noqa: E402
text = "".join(seite.get_textpage().get_text_range() for seite in pypdfium2.PdfDocument(str(pfad)))
assert "Schnittschema je Mengenstufe" in text and "6.000 × 25" in text
assert pdf._schnittschema_stufen([dict(menge=5, stufe=1)]) == []
ok("B1 Kalkulations-PDF mit Schnittschema je Mengenstufe")
print("ALLE OK")
