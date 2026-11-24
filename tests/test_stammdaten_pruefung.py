"""Stammdaten-Prüfung über Zeilen hinweg (QA-005, Patrick 12.11.2026 „Alle Empfehlungen“ zum Bericht
Entwicklungspotenziale).

- je Regel ein Fall mit Treffer und einer ohne
- die mitgelieferten Beispieldaten ergeben keinen FEHLER
- Warnungen lassen sich quittieren, FEHLER nicht; die Prüfung ändert keine Stammdaten
- Knopf „Stammdaten prüfen …“ in den Stammdaten

Aufruf: python tests/test_stammdaten_pruefung.py
"""
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
from rohrlaser import stammdaten_pruefung as sp  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402


def ok(t):
    print("OK    ", t)


def regeln(m):
    return sorted({x["regel"] for x in m})


def sd(wand, v, e=1.0, m="L1", w="S235"):
    return dict(maschinen_id=m, werkstoff_id=w, kategorie=None, gas="O2", wand_bis=wand, vorschub_gross=v,
                einstechzeit=e)


def main():
    # Stundensatz 0 / leer
    assert regeln(sp.pruefen({"stundensaetze": [dict(satz_id="QS", satz=0)]})) == ["satz_null"]
    assert regeln(sp.pruefen({"stundensaetze": [dict(satz_id="QS", satz=None)]})) == ["satz_null"]
    assert not sp.pruefen({"stundensaetze": [dict(satz_id="QS", satz=55)]})
    assert regeln(sp.pruefen({"maschinen": [dict(maschinen_id="L1", satz_art="von Hand", stundensatz=0)]})) \
        == ["satz_null"]
    assert not sp.pruefen({"maschinen": [dict(maschinen_id="L1", satz_art="ermittelt", stundensatz=None)]})
    ok("Stundensatz 0 oder leer = FEHLER (ermittelter Maschinensatz nicht)")
    # Vorschub 0
    m = sp.pruefen({"schneiddaten": [sd(2, 0)]})
    assert regeln(m) == ["vorschub_null"] and m[0]["stufe"] == sp.FEHLER
    assert not sp.pruefen({"schneiddaten": [sd(2, 5000)]})
    ok("Vorschub 0 = FEHLER")
    # Wandstufe doppelt
    assert "wand_doppelt" in regeln(sp.pruefen({"schneiddaten": [sd(2, 5000), sd(2, 5000)]}))
    assert not sp.pruefen({"schneiddaten": [sd(2, 5000), sd(2, 5000, m="L2")]})
    ok("Wandstufe doppelt = FEHLER, andere Maschine nicht")
    # Vorschub steigt / Einstechzeit sinkt
    m = sp.pruefen({"schneiddaten": [sd(2, 5000, 1.0), sd(4, 6000, 0.5)]})
    assert regeln(m) == ["einstich_sinkt", "vorschub_steigt"] and all(x["stufe"] == sp.WARNUNG for x in m)
    assert not sp.pruefen({"schneiddaten": [sd(4, 3000, 2.0), sd(2, 5000, 1.0)]})
    ok("Vorschub steigt / Einstechzeit sinkt mit der Wand = WARNUNG, Reihenfolge der Zeilen egal")
    # Preis 0, €/kg Nachbar
    prof = [dict(profil_id=f"RR{a}", form="Rundrohr", a=a, wand=2) for a in (20, 25, 30)]
    pr = [dict(profil_id=f"RR{a}", werkstoff_id="S235", basis="€/kg", preis=p) for a, p in ((20, 1.5), (25, 4.0),
                                                                                           (30, 1.6))]
    m = sp.pruefen({"profile": prof, "preise": pr})
    assert regeln(m) == ["kg_nachbar"] and "RR25" in m[0]["zeile"]
    pr[1]["preis"] = 1.55
    assert not sp.pruefen({"profile": prof, "preise": pr})
    pr[1]["preis"] = 0
    assert regeln(sp.pruefen({"profile": prof, "preise": pr})) == ["preis_null"]
    ok("Preis 0 = FEHLER; €/kg mehr als doppelt so hoch wie die Nachbarabmessung = WARNUNG")
    # quittieren
    m = sp.pruefen({"schneiddaten": [sd(2, 0), sd(2, 5000), sd(4, 6000)]})
    q = [x["schluessel"] for x in m]
    assert {x["stufe"] for x in sp.pruefen({"schneiddaten": [sd(2, 0), sd(2, 5000), sd(4, 6000)]}, q)} == {sp.FEHLER}
    ok("quittierte Warnungen fehlen, FEHLER bleiben")

    with tempfile.TemporaryDirectory() as tmp:
        db = Datenbank(Path(tmp) / "t.db")
        vorher = {t: db.zeilen(t) for t in ("profile", "preise", "schneiddaten", "stundensaetze", "maschinen")}
        m = sp.pruefen_db(db)
        assert not [x for x in m if x["stufe"] == sp.FEHLER], [x["text"] for x in m if x["stufe"] == sp.FEHLER]
        ok(f"Beispieldaten ohne FEHLER ({len(m)} Warnung(en))")
        db.neu("stundensaetze", dict(satz_id="Leer", bezeichnung="Test", satz=0))
        db.neu("schneiddaten", dict(maschinen_id="L1", werkstoff_id="S235", gas="O2", wand_bis=99,
                                    vorschub_gross=100, einstechzeit=0.1))
        db.neu("schneiddaten", dict(maschinen_id="L1", werkstoff_id="S235", gas="O2", wand_bis=98,
                                    vorschub_gross=50, einstechzeit=0.5))
        m = sp.pruefen_db(db)
        assert "satz_null" in regeln(m)
        w = [x for x in m if x["stufe"] == sp.WARNUNG and "99" in x["zeile"]]
        assert w, [x["text"] for x in m]
        sp.quittieren(db, w[0]["schluessel"])
        assert w[0]["schluessel"] not in {x["schluessel"] for x in sp.pruefen_db(db)}
        ok("in der Datenbank: Treffer, Quittieren wirkt dauerhaft")
        nachher = {t: db.zeilen(t) for t in vorher}
        assert all(len(nachher[t]) >= len(vorher[t]) for t in vorher)

        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication, QPushButton
        from rohrlaser import fenster
        app = QApplication.instance() or QApplication([])  # noqa: F841
        from rohrlaser.stammdaten import TABELLE
        seite = fenster.StammdatenSeite(db, TABELLE["schneiddaten"], lambda *a, **k: None)
        assert any(b.text() == "Stammdaten prüfen …" for b in seite.findChildren(QPushButton))
        assert seite.stammdaten_pruefen(zeigen=False) == sp.pruefen_db(db)
        ok("Knopf „Stammdaten prüfen …“ in den Schneiddaten")
    print("alle Prüfungen bestanden")


if __name__ == "__main__":
    main()
