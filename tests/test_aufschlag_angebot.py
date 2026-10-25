"""Prüft den Aufschlag Bleche und Aufschlag Zukaufteile je Angebot (Patrick 25.10.2026, „gilt für alle im Angebot“):
- A1 neue Angebote: Vorgabe 10 % aus den Einstellungen, ersetzt Artikel-/Kategorieaufschlag (Bleche und Zukaufteile
     getrennt), ein Positionsaufschlag geht vor
- A2 ältere Angebote (Feld leer): Regeln wie bisher, Preis unverändert
- A3 Anzeige: Zeilen unter Zuschlag Fremdleistung nur, wenn das Angebot Bleche bzw. Zukaufteile hat; Vorgaben aus
     Einstellungen setzt zurück

Aufruf: python tests/test_aufschlag_angebot.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import json
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402

from rohrlaser import rechnen, zukauf  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def ok(text):
    print("OK    ", text)


def nah(a, b, text, eps=1e-6):
    assert abs(float(a) - float(b)) < eps, f"{text}: {a} != {b}"


app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "a.db")
assert db.einstellung("aufschlag_blech") == 0.10 and db.einstellung("aufschlag_zukauf") == 0.10
ind = dict(aufschlag_quelle=zukauf.INDIVIDUELL, aufschlag_methode=zukauf.PROZENT)
bezug = [dict(lieferant="L", preiseinheit=1, preise=[dict(ab=1, preis=2.0)])]
schraube = db.zukauf_speichern(None, dict(artikelnr="Z-1", bezeichnung="Schraube", kategorie="Normteile",
                                          einheit="Stück", aufschlag_wert=25, **ind), bezug)
blech = db.zukauf_speichern(None, dict(artikelnr="B-1", bezeichnung="Lasche", kategorie="Kaufteile", einheit="Stück",
                                       artikeltyp=zukauf.BLECH, aufschlag_wert=40, **ind),
                            [dict(lieferant="L", preiseinheit=1, preise=[dict(ab=1, preis=5.0)])])


def eintrag(aid, menge, aufschlag=None):
    return dict(artikel_id=aid, menge=menge, aufschlag=aufschlag, stand=db.zukauf_stand(aid))


def angebot(**kopf):
    a = db.angebot_neu(dict(kunde="Test", maschine="T11", **kopf))
    db.position_neu(a, dict(pos=10, artikel="A", profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=800,
                            stueck=10, schneidweg=300, einstiche=2))
    return a


def zukauf_setzen(a, eintraege):
    p = db.positionen(a)[0]
    db.position_aendern(p["id"], "zukauf", json.dumps(eintraege))


def gruppen(a):
    kopf, pos, k, tab = db.angebot(a), db.positionen(a), db.kontext(), db.tabellen()
    einst = rechnen.einstellungen_angebot(kopf, db.einstellungen())
    _, s = rechnen.kalkulation(kopf, pos, rechnen.optimieren(kopf, pos, k), k, tab, einst)
    return {g["stand"]["artikelnr"]: g for g in s["zukauf"]}, s


# ------------------------------------------------------------------ A1 neue Angebote
a = angebot()
kopf = db.angebot(a)
assert kopf["aufschlag_blech"] == 10 and kopf["aufschlag_zukauf"] == 10, kopf
zukauf_setzen(a, [eintrag(schraube, 2), eintrag(blech, 1)])
g, s = gruppen(a)
nah(g["Z-1"]["vk"], 20 * 2.0 * 1.10, "Schraube +10 % statt Artikel 25 %")
nah(g["B-1"]["vk"], 10 * 5.0 * 1.10, "Blech +10 % statt Artikel 40 %")
assert "Aufschlag im Angebot" in g["Z-1"]["regel"], g["Z-1"]["regel"]
db.angebot_aendern(a, "aufschlag_blech", 30)
g, _ = gruppen(a)
nah(g["B-1"]["vk"], 10 * 5.0 * 1.30, "Aufschlag Bleche 30 %")
nah(g["Z-1"]["vk"], 20 * 2.0 * 1.10, "Zukaufteile bleiben 10 %")
zukauf_setzen(a, [eintrag(schraube, 2, aufschlag=50), eintrag(blech, 1)])
g, _ = gruppen(a)
nah(g["Z-1"]["vk"], 20 * 2.0 * 1.50, "Positionsaufschlag geht vor")
# Blech ohne Artikeltyp, aber Kategorie Blechteile (ältere Artikel) zählt als Blech
e = dict(artikel_id=None, stand=dict(kategorie="Blechteile"))
assert zukauf.ist_blech(e) and not zukauf.ist_blech(dict(artikel_id=None, stand=dict(kategorie="Normteile")))
ok("A1 neue Angebote: Aufschlag Bleche bzw. Zukaufteile 10 % ersetzt Artikelaufschläge, Positionsaufschlag geht vor")

# ------------------------------------------------------------------ A2 ältere Angebote
alt = angebot()
db.angebot_aendern(alt, "aufschlag_blech", None)
db.angebot_aendern(alt, "aufschlag_zukauf", None)
zukauf_setzen(alt, [eintrag(schraube, 2), eintrag(blech, 1)])
g, _ = gruppen(alt)
nah(g["Z-1"]["vk"], 20 * 2.0 * 1.25, "älteres Angebot: Artikelaufschlag 25 %")
nah(g["B-1"]["vk"], 10 * 5.0 * 1.40, "älteres Angebot: Artikelaufschlag 40 %")
ok("A2 ältere Angebote ohne Aufschlag im Angebot rechnen wie bisher (Artikel, Kategorie, Standard)")

# ------------------------------------------------------------------ A3 Anzeige
fenster = Hauptfenster(db, tmp, stumm=True)
fenster.resize(1920, 1080)
fenster.show()
ohne = angebot()
s = fenster.angebot_oeffnen(ohne)
kb = s.kopf_bereich
kb.kalkulation_aufklappen(True)
app.processEvents()


def sichtbar(name):
    return kb.zeilen[name][1].isVisibleTo(kb), kb.zeilen_erweitert[name][1].isVisibleTo(kb)


assert sichtbar("aufschlag_blech") == (False, False) and sichtbar("aufschlag_zukauf") == (False, False)
assert "Aufschlag" not in kb.kalk_kurz.text()
zukauf_setzen(ohne, [eintrag(schraube, 2)])
s.neu_laden()
assert sichtbar("aufschlag_zukauf") == (True, False) and sichtbar("aufschlag_blech") == (False, False)
zukauf_setzen(ohne, [eintrag(schraube, 2), eintrag(blech, 1)])
s.neu_laden()
assert sichtbar("aufschlag_zukauf") == (True, False) and sichtbar("aufschlag_blech") == (True, False)
assert kb.felder["aufschlag_blech"].value() == 10
w = kb.felder["aufschlag_blech"]
w.setValue(25)
w.editingFinished.emit()
assert db.angebot(ohne)["aufschlag_blech"] == 25 and "background" in kb.felder["aufschlag_blech"].styleSheet()
s.kalkulation_zuruecksetzen()
assert db.angebot(ohne)["aufschlag_blech"] == 10
# älteres Angebot: leeres Feld steht unter Erweiterte Einstellungen (nicht der Wert der Einstellungen)
s2 = fenster.angebot_oeffnen(alt)
s2.kopf_bereich.kalkulation_aufklappen(True)
app.processEvents()
kb = s2.kopf_bereich
kb.erweitert_bereich.aufklappen(True)
assert sichtbar("aufschlag_zukauf") == (False, True) and kb.erweitert["aufschlag_zukauf"].value() == 0
ok("A3 Zeilen nur mit Blechen bzw. Zukaufteilen im Angebot, gelb bei Abweichung, Vorgaben setzen zurück")
