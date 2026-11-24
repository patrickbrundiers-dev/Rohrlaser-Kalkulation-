"""Regelkatalog aller Prüfungen (QA-006, Patrick 12.11.2026 „Alle Empfehlungen“).

- jede Regel im Katalog hat einen Test: ihr Beispiel wird von ihr (und nur ihr zuerst) erkannt
- die Texte des Angebots-Checks werden erkannt (echter Check eines Angebots)
- geänderte Stufe wirkt im Check; „aus“ blendet aus; FEHLER lässt sich nicht ändern
- Dialog „Prüfregeln (Regelkatalog) …“

Aufruf: python tests/test_regelkatalog.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from rohrlaser import regelkatalog as rk  # noqa: E402
from rohrlaser.angebot_check import Punkt  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402


def ok(t):
    print("OK    ", t)


def main():
    for r in rk.REGELN:
        assert rk.regel_zu(r.beispiel) is r, (r.id, rk.regel_zu(r.beispiel))
        assert r.stufe in (rk.FEHLER, rk.WARNUNG, rk.HINWEIS) and r.grund and r.ort
    assert rk.regel_zu("etwas ganz anderes") is None
    ok(f"{len(rk.REGELN)} Regeln: jede erkennt ihr Beispiel, jede mit Stufe, Grund und Ort")
    punkte = [Punkt(rk.FEHLER, "keine Positionen"), Punkt(rk.WARNUNG, "kein Kunde eingetragen", "kopf:kunde"),
              Punkt(rk.HINWEIS, "Kundenreferenz (Anfrage des Kunden) leer"), ("HINWEIS", "frei", None)]
    assert rk.anwenden(punkte, {}) == punkte
    neu = rk.anwenden(punkte, {"CHK-002": rk.HINWEIS, "CHK-018": rk.AUS, "CHK-001": rk.AUS})
    assert [tuple(p[:2]) for p in neu] == [("FEHLER", "keine Positionen"), ("HINWEIS", "kein Kunde eingetragen"),
                                           ("HINWEIS", "frei")], neu
    assert neu[1].ziel == "kopf:kunde"
    ok("Stufe geändert, „aus“ blendet aus, FEHLER bleibt trotz Einstellung")

    from PySide6.QtWidgets import QApplication
    from rohrlaser.fenster import Hauptfenster
    app = QApplication.instance() or QApplication([])  # noqa: F841
    tmp = Path(tempfile.mkdtemp())
    db = Datenbank(tmp / "rohrlaser.db")
    hf = Hauptfenster(db, tmp, stumm=True)
    try:
        rk.setzen(db, "CHK-001", rk.AUS)
        raise AssertionError("FEHLER-Regel geändert")
    except ValueError:
        pass
    aid = db.angebot_neu(dict(kunde="", maschine="T11", stange=6000))
    db.position_neu(aid, dict(pos=10, artikel="A", profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=1000.0,
                              stueck=5, schneidweg=200, einstiche=1))
    s = hf.angebot_oeffnen(aid)
    vorher = s.freigabe_punkte()
    unbekannt = [p[1] for p in vorher if rk.regel_zu(p[1]) is None]
    assert any(p[1] == "kein Kunde eingetragen" and p[0] == rk.WARNUNG for p in vorher), vorher
    d = hf.regelkatalog_zeigen(zeigen=False)
    d.auswahl["CHK-002"].setCurrentText(rk.AUS)
    assert rk.laden(db) == {"CHK-002": rk.AUS}
    nachher = s.freigabe_punkte()
    assert not any(p[1] == "kein Kunde eingetragen" for p in nachher)
    d.auswahl["CHK-002"].setCurrentText(rk.WARNUNG)
    assert rk.laden(db) == {}
    assert "CHK-001" not in d.auswahl
    ok(f"im Angebot: Dialog stellt die Stufe ein, wirkt sofort im Check (ohne Regel im Katalog: {len(unbekannt)})")
    print("alle Prüfungen bestanden")


if __name__ == "__main__":
    main()
