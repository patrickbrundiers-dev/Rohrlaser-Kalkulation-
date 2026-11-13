"""Kostentreiber über alle Aufträge (CALC-030, Patrick 12.11.2026 „Alle Empfehlungen“).

- je Bearbeitungsart und Abmessung Zeit, Kosten, Teile und Anzahl der Aufträge, Top 10 nach Kosten
- Summe = Summe der Aufträge (Laser + Gas je Teil × Stück); nur beauftragte Angebote
- leere Datenbank läuft ohne Fehler; Dialog Datei → Kostentreiber …

Aufruf: python tests/test_kostentreiber.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from rohrlaser import kostentreiber as kt, rechnen  # noqa: E402
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
    leer = kt.auswertung(db)
    assert leer["auftraege"] == 0 and leer["arten"] == [] and leer["summe_eur"] == 0
    ok("leere Datenbank ohne Fehler")
    erwartet = 0.0
    for n, (profil, stueck, vorgang) in enumerate((("QR 40x40x3", 20, "Beauftragt"), ("RR 42,4x2,0", 50, "Beauftragt"),
                                                   ("QR 40x40x3", 7, "Abgelehnt"))):
        aid = db.angebot_neu(dict(kunde=f"K{n}", maschine="T11", stange=6000))
        db.position_neu(aid, dict(pos=10, artikel="A", profil_id=profil, werkstoff_id="S235-10219", laenge=900.0,
                                  stueck=stueck, schneidweg=400, einstiche=2,
                                  konturen="A:40x40; B:40x40; 10x31,4; 10x31,4"))
        s = hf.angebot_oeffnen(aid)
        assert s.optimieren()
        if vorgang == "Beauftragt":
            zeilen = s._rechnung()[0]
            erwartet += sum((z["laser_schneiden_teil"] + z["schneidgas_teil"]) * z["stueck"] for z in zeilen if z)
        db.vorgang_setzen(aid, vorgang)
    r = kt.auswertung(db)
    assert r["auftraege"] == 2 and r["gerechnet"] == 2, r
    assert abs(r["summe_eur"] - erwartet) < 1e-6, (r["summe_eur"], erwartet)
    assert abs(r["summe_abm_eur"] - r["summe_eur"]) < 1e-6
    assert abs(r["summe_arten_eur"] - r["summe_eur"]) < 0.01 * r["summe_eur"], (r["summe_arten_eur"], r["summe_eur"])
    assert {x["name"] for x in r["abmessungen"]} == {"QR 40x40x3", "RR 42,4x2,0"}
    assert all(x["auftraege"] == 1 for x in r["abmessungen"])
    assert [x["eur"] for x in r["arten"]] == sorted((x["eur"] for x in r["arten"]), reverse=True)
    assert len(r["arten"]) <= kt.TOP and any(x["name"] == "Anfangs-/Endschnitt" for x in r["arten"]), r["arten"]
    ok(f"Summe = Summe der Aufträge ({rechnen.zahl(r['summe_eur'])} €), je Abmessung und Bearbeitungsart, "
       "abgelehnte zählen nicht")
    d = hf.kostentreiber_zeigen(zeigen=False)
    assert d.arten.rowCount() == len(r["arten"]) and d.abmessungen.rowCount() == 2
    ok("Dialog Datei → Kostentreiber …")
    print("alle Prüfungen bestanden")


if __name__ == "__main__":
    main()
