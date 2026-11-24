"""Rückfragen nur mit Preiswirkung (OFFER-021, Patrick 12.11.2026 „Alle Empfehlungen“).

- offene Frage je Position „Werkstoff: 1.4301 oder 1.4404“: beide Antworten werden gerechnet
- Punkt unter der Schwelle (Vorgabe 3 %) fehlt in der Rückfrage; Reihenfolge nach €
- nicht rechenbare Fragen bleiben ungefiltert; die Mail an den Kunden enthält keine Preise

Aufruf: python tests/test_rueckfrage_wirkung.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from rohrlaser import rueckfrage_wirkung as rw  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402


def ok(t):
    print("OK    ", t)


def main():
    f = rw.fragen("Werkstoff: 1.4301 oder 1.4404; Oberfläche: ohne | gebeizt; Farbe: rot oder blau; Termin klären")
    assert f[0] == ("werkstoff_id", "Werkstoff", ["1.4301", "1.4404"])
    assert f[1] == ("oberflaeche", "Oberfläche", ["ohne", "gebeizt"])
    assert f[2][0] is None and f[3] == (None, "Termin klären", [])
    ok("Fragen lesen: Feld, Antworten mit „oder“ bzw. „|“, unbekannte Felder ungefiltert")

    from PySide6.QtWidgets import QApplication
    from rohrlaser.fenster import Hauptfenster
    app = QApplication.instance() or QApplication([])  # noqa: F841
    tmp = Path(tempfile.mkdtemp())
    db = Datenbank(tmp / "rohrlaser.db")
    hf = Hauptfenster(db, tmp, stumm=True)
    aid = db.angebot_neu(dict(kunde="Test", maschine="T11", stange=6000))
    db.position_neu(aid, dict(pos=10, artikel="A", profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=1000.0,
                              stueck=50, schneidweg=200, einstiche=1,
                              offene_frage="Werkstoff: S235-10219 oder 1.4301; Werkstoff: S235-10219 oder S355-10219"))
    db.position_neu(aid, dict(pos=20, artikel="B", profil_id="RR 42,4x2,0", werkstoff_id="S235-10219",
                              laenge=500.0, stueck=20, schneidweg=150, einstiche=1,
                              offene_frage="Stückzahl: 20 oder 200; Farbe: rot oder blau"))
    s = hf.angebot_oeffnen(aid)
    w = rw.wirkung(s.kopf, s.positionen, s.k, s.tabellen, db.einstellungen())
    texte = [x["text"] for x in w["fragen"]]
    assert len(w["fragen"]) == 3, texte
    assert [x["unterschied"] for x in w["fragen"]] == sorted((x["unterschied"] for x in w["fragen"]), reverse=True)
    edel = next(x for x in w["fragen"] if "1.4301" in x["text"])
    assert edel["fragen"] and edel["anteil"] >= rw.SCHWELLE
    gefragt = rw.texte(w)
    assert any("1.4301" in t for t in gefragt) and any("Farbe" in t for t in gefragt)
    unter = [x for x in w["fragen"] if x["anteil"] < rw.SCHWELLE]
    for x in unter:
        assert x["text"] + "?" not in gefragt
    assert all("€" not in t for t in gefragt)
    ok(f"je Antwort gerechnet, nach € sortiert, unter 3 % nicht gefragt ({len(unter)}), Mail ohne Preise")
    hoch = rw.wirkung(s.kopf, s.positionen, s.k, s.tabellen, db.einstellungen(), schwelle=10.0)
    assert rw.texte(hoch) == list(hoch["offen"]) and len(rw.nicht_gefragt(hoch)) == 3
    ok("Schwelle 1000 %: keine gerechnete Frage, nur die nicht rechenbaren")
    eml = tmp / "rueckfrage.eml"
    rf = s.rueckfrage(eml=eml)
    inhalt = eml.read_text(encoding="utf-8", errors="replace")
    assert "1.4301" in inhalt and "Farbe" in inhalt and rf["bericht"], rf
    assert all(x["text"] + "?" not in inhalt for x in unter)
    ok("Rückfrage an Kunden: Fragen mit Preiswirkung zuerst, Bericht mit € nur intern")
    print("alle Prüfungen bestanden")


if __name__ == "__main__":
    main()
