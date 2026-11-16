"""Normteile ohne Preis gesammelt nachtragen (Vorschlag M6, Patrick 07.11.2026): Unterreiter „Normteile ohne Preis“
der Zukaufartikel listet alle Normteile ohne EK, der EK wird in der Zeile eingetragen und mit „Preise speichern“ für
alle auf einmal gespeichert; der Angebots-Check nennt Normteile eines Angebots ohne Preis und springt dorthin.

Aufruf: python tests/test_normteile_ohne_preis.py
"""
import json
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402

from rohrlaser import angebot_check, step, zukauf  # noqa: E402
from rohrlaser.angebot import ZUKAUFTEIL  # noqa: E402
from rohrlaser.angebot_fenster import AngebotSeite  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.normteil_preise import NormteilPreisSeite, ids_ohne_preis, ohne_preis  # noqa: E402
from rohrlaser.zukauf_seite import ZukaufBereich  # noqa: E402

TMP = Path(tempfile.mkdtemp())
app = QApplication.instance() or QApplication([])


def ok(text):
    print("OK    ", text)


db = Datenbank(TMP / "n.db")


def normteil(name, preis=None):
    werte = dict(bezeichnung=name, kategorie=step.NORMTEIL_KATEGORIE, einheit="Stück", status="aktiv",
                 aufschlag_quelle="Kategorie", angebotstext="nein", rest_lager="nein", kombiniert="nein",
                 artikeltyp=step.NORMTEIL_TYP, herkunft="STEP-Import")
    return db.zukauf_speichern(None, werte, [dict(lieferant=None, bevorzugt="ja", preiseinheit=1,
                                                  preise=[dict(ab=1, preis=preis)] if preis else [])])


m12 = normteil("ISO 4032 M12")
m16 = normteil("ISO 4032 M16")
kugel = normteil("Kugel Ø20", 0.35)
assert [a["bezeichnung"] for a in ohne_preis(db)] == ["ISO 4032 M12", "ISO 4032 M16"]
assert ids_ohne_preis(db) == {m12, m16}
ok("Liste: Normteile ohne EK (mit EK und andere Kategorien nicht)")

meldungen = []
bereich = ZukaufBereich(db, lambda t, f=False, **_: meldungen.append((t, f)))
s = bereich.normteile
assert isinstance(s, NormteilPreisSeite) and s.tabelle.rowCount() == 2
assert bereich.unter.tabText(bereich.unter.indexOf(s)) == "Normteile ohne Preis (2)"
s.neu_laden()
s.neu_laden()
from PySide6.QtWidgets import QDoubleSpinBox  # noqa: E402
felder = [w for w in s.tabelle.viewport().findChildren(QDoubleSpinBox) if not w.isHidden()]
assert len(felder) == 2, "nach erneutem Laden keine alten Eingabefelder mehr sichtbar"
s.preis_setzen(0, 0.12)
assert s.speichern() == 1 and "1 Normteil-Preis gespeichert" in meldungen[-1][0]
assert not zukauf.ek_fehlt(db.zukauf_artikel(m12)) and zukauf.ek_fehlt(db.zukauf_artikel(m16))
assert s.tabelle.rowCount() == 1 and bereich.unter.tabText(bereich.unter.indexOf(s)) == "Normteile ohne Preis (1)"
s.preis_setzen(0, 0.2)
s.speichern()
assert s.tabelle.rowCount() == 0 and not s.speichern_knopf.isEnabled() and "Alle Normteile" in s.info.text()
assert bereich.unter.tabText(bereich.unter.indexOf(s)) == "Normteile ohne Preis"
ok("Unterreiter: EK in der Zeile, „Preise speichern“ speichert alle mit Preis, Zeilen und Zähler im Reiter gehen weg")

m20 = normteil("ISO 4032 M20")
pos = [dict(pos=10, art=ZUKAUFTEIL, bezeichnung="ISO 4032 M20", stueck=4,
            zukauf=json.dumps([dict(artikel_id=m20, menge=1)])),
       dict(pos=20, art=ZUKAUFTEIL, bezeichnung="Kugel Ø20", stueck=4,
            zukauf=json.dumps([dict(artikel_id=kugel, menge=1)])),
       dict(pos=30, profil="QR 40x40x3")]
punkte = AngebotSeite._normteil_punkte(SimpleNamespace(positionen=pos, db=db))
assert len(punkte) == 1 and punkte[0].art == angebot_check.HINWEIS and punkte[0].ziel == "normteile", punkte
assert "1 Normteil ohne Einkaufspreis" in punkte[0].text and punkte[0].details == "Pos. 10", punkte[0].details
db.zukauf_ek_eintragen(m20, 0.5)
assert AngebotSeite._normteil_punkte(SimpleNamespace(positionen=pos, db=db)) == []
ok("Angebots-Check: Hinweis „1 Normteil ohne Einkaufspreis … Normteile ohne Preis“ mit Sprungziel, mit EK nichts")
print("Normteile ohne Preis: alle Tests bestanden.")
