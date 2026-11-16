"""Echter Materialpreis zurück in die Kalkulation (Plan Angebotskalkulation 16.11.2026, Paket K3): Bestellpreis der
gewählten Lieferantenantwort als EK-Meterpreis Ist in der Nachkalkulation, Material Ist in der Auswertung der
Aufträge, Hinweis im Angebots-Check ab 5 % mit „Erledigen“ (Stammdaten Preise, Rückgängig).

Aufruf: python tests/test_bestellpreis.py
"""
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402

from rohrlaser import auftraege as au, auftrag_av as av, auftrag_auswertung as aw  # noqa: E402
from rohrlaser import bestellpreis as bp, lieferantenangebote as la, nachkalkulation as nk  # noqa: E402
from rohrlaser import nachkalk_rueckmeldung as nr  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def ok(t):
    print("OK:", t)


app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
f = Hauptfenster(db, tmp, stumm=True)
PROFIL, WERKSTOFF = "RR 42,4x2,0", "S235-10219"


def angebot():
    a = db.angebot_neu(dict(kunde="Becker GmbH", kundennr="10023", stange=6000, maschine="T03"))
    db.position_neu(a, dict(pos=1, artikel="R-1", bezeichnung="Teil", profil_id=PROFIL, werkstoff_id=WERKSTOFF,
                            laenge=1000, stueck=40, schneidweg=300, einstiche=2))
    s = f.angebot_oeffnen(a)
    s.optimieren()
    s.neu_laden()
    return a, s


a, s = angebot()
gr = nk.gruppen(s.ergebnis, s.kopf, s.positionen, s.k, s.tabellen)
kalk_m = gr[0]["meterpreis"]
from rohrlaser import rechnen  # noqa: E402
db.preisbasis_speichern(a, rechnen.preisbasis_aus(s.kopf, s.positionen, s.k, s.tabellen))   # wie beim Angebots-PDF
f.angebot_schliessen(a)
i = la.erfassen(db, a, "Stahl Müller", PROFIL, WERKSTOFF, "€/m", round(kalk_m * 1.2, 2))
la.uebernehmen(db, a, i)                 # gewählt = bestellt (Stammdaten Preise jetzt 20 % höher)
assert bp.eigene(db, a, db.kontext())[(PROFIL, WERKSTOFF)]["je_m"] == round(kalk_m * 1.2, 2)

assert f.angebote.vorgang_setzen("Beauftragt", angebot_id=a, auftrag=("PO-1", "2026-12-01"))
uid = au.uebernehmen(db, [a])
av.alle_uebernehmen(db, uid)
av.freigeben(db, uid, "Test")
assert nr.uebernehmen(db, uid) >= 1
ist = db.angebot(a)["nachkalkulation"]
key = gr[0]["schluessel"]
assert ist["meterpreis"][key] == round(kalk_m * 1.2, 2) and nr.aus_rueckmeldung(ist, "meterpreis", bg_id=key), ist
assert abs(bp.material_faktor(ist) - 1.2) < 0.01, bp.material_faktor(ist)
ok("Bestellpreis als EK-Meterpreis Ist in der Nachkalkulation, Material Ist ÷ Soll = 1,2")

c = aw.kosten(au.auftrag(db, uid), aw.material_faktoren(db, au.auftrag(db, uid)))
assert c["mit_material"] and abs(c["material_ist"] / c["material"] - 1.2) < 0.01 and c["ist"] > c["kalk"], c
assert aw.kosten(au.auftrag(db, uid))["material_ist"] == c["material"]          # ohne Faktoren wie bisher
ok("Auswertung: Material Ist mit dem Bestellpreis")

# von Hand eingetragener Meterpreis geht vor
s = f.angebot_oeffnen(a)
seite = s.nachkalk
seite.neu_laden()
it = seite.gruppen.item(0, 6)
assert "Bestellpreis" in it.toolTip()
it.setText("9,99")
ist = db.angebot(a)["nachkalkulation"]
assert ist["meterpreis"][key] == 9.99 and not nr.aus_rueckmeldung(ist, "meterpreis", bg_id=key)
nr.uebernehmen(db, uid)
assert db.angebot(a)["nachkalkulation"]["meterpreis"][key] == 9.99
f.angebot_schliessen(a)
ok("Nachkalkulation zeigt die Herkunft, von Hand eingetragen geht vor")

# neues Angebot rechnet mit einem niedrigeren Preis (Stammdaten später gesenkt) -> Hinweis + Erledigen
pz = next(z for z in db.zeilen("preise") if z.get("profil_id") == PROFIL and z.get("werkstoff_id") == WERKSTOFF)
db.aendern("preise", pz["id"], "preis", round(kalk_m, 2))
b, s2 = angebot()
liste = s2._bestellpreis_liste()
assert len(liste) == 1 and abs(liste[0]["prozent"] - 0.2) < 0.02, liste
p = [x for x in s2.freigabe_punkte() if getattr(x, "aktion", None) == bp.AKTION]
assert len(p) == 1 and "Stahl Müller" in p[0].text and "über dem kalkulierten" in p[0].text, p
assert s2.check_erledigen([bp.AKTION]) == [bp.AKTION]
assert next(z for z in db.zeilen("preise") if z["id"] == pz["id"])["preis"] == round(kalk_m * 1.2, 2)
s2 = f.angebot_oeffnen(b)
assert not s2._bestellpreis_liste()
ok("Angebots-Check: letzter Bestellpreis 20 % über dem kalkulierten -> Hinweis, Erledigen übernimmt ihn")

aend = bp.uebernehmen(db, [dict(liste[0])])
bp.zurueck(db, aend)
assert next(z for z in db.zeilen("preise") if z["id"] == pz["id"])["preis"] == round(kalk_m * 1.2, 2)
db.aendern("preise", pz["id"], "preis", 1.0)
aend = bp.uebernehmen(db, [dict(liste[0])])
bp.zurueck(db, aend)
assert next(z for z in db.zeilen("preise") if z["id"] == pz["id"])["preis"] == 1.0
ok("Rückgängig stellt den alten Preis her")
print("test_bestellpreis OK")
