"""Fragen zum Rechenweg regelbasiert beantworten (KI-002 Weg A, Patrick 12.11.2026 „Alle Empfehlungen“).

- „Warum ist Pos. 20 teurer als Pos. 10?“: Unterschiede je Baustein, größter zuerst, mit den Zahlen dahinter
- die genannten Unterschiede (mit Rest) ergeben zusammen genau den Preisunterschied je Teil
- die Antwort nennt nur vorhandene Zahlen (Preise der Kalkulation); Dialog im Menü Ausgaben

Aufruf: python tests/test_erklaerung.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from rohrlaser import rechnen  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402


def ok(t):
    print("OK    ", t)


def main():
    from PySide6.QtWidgets import QApplication
    from rohrlaser.fenster import Hauptfenster
    app = QApplication.instance() or QApplication([])  # noqa: F841
    tmp = Path(tempfile.mkdtemp())
    db = Datenbank(tmp / "rohrlaser.db")
    hf = Hauptfenster(db, tmp, stumm=True)
    aid = db.angebot_neu(dict(kunde="Test", maschine="T11", stange=6000))
    db.position_neu(aid, dict(pos=10, artikel="A", profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=500.0,
                              stueck=40, schneidweg=200, einstiche=1))
    db.position_neu(aid, dict(pos=20, artikel="B", profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=1500.0,
                              stueck=10, schneidweg=900, einstiche=6))
    s = hf.angebot_oeffnen(aid)
    assert s.optimieren()
    zeilen = s._rechnung()[0]
    r = s.warum_teurer(1, 0)
    assert abs(r["unterschied"] - (zeilen[1]["preis_teil"] - zeilen[0]["preis_teil"])) < 1e-9
    assert abs(sum(g["eur"] for g in r["gruende"]) + r["rest"] - r["unterschied"]) < 1e-9
    assert r["unterschied"] > 0 and r["antwort"].startswith("Pos. 20 kostet je Teil")
    namen = [g["baustein"] for g in r["gruende"]]
    assert "Material" in namen and "Laser" in namen, namen
    assert [abs(g["eur"]) for g in r["gruende"]] == sorted((abs(g["eur"]) for g in r["gruende"]), reverse=True)
    mat = next(g for g in r["gruende"] if g["baustein"] == "Material")
    assert "Länge 1500 statt 500 mm" in mat["text"], mat
    laser = next(g for g in r["gruende"] if g["baustein"] == "Laser")
    assert "Schneidweg 900 statt 200 mm" in laser["text"] and "Einstiche 6 statt 1" in laser["text"], laser
    assert rechnen.zahl(r["preis_a"]) in r["antwort"] and rechnen.zahl(r["preis_b"]) in r["antwort"]
    ok(f"Unterschiede ergeben den Preisunterschied: {r['antwort']}")
    r0 = s.warum_teurer(0, 0)
    assert r0["gruende"] == [] and "gleich viel" in r0["antwort"]
    ok("gleiche Position: gleich viel, keine Gründe")
    d = s.warum_teurer(zeigen=False)
    d.a.setCurrentIndex(1)
    d.b.setCurrentIndex(0)
    assert d.antwort.text() == r["antwort"]
    ok("Dialog Ausgaben → Warum teurer? Positionen vergleichen …")
    print("alle Prüfungen bestanden")


if __name__ == "__main__":
    main()
