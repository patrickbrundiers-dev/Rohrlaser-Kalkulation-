"""Empfindlichkeit je Annahme (CALC-029, Patrick 12.11.2026 „Alle Empfehlungen“).

- ±10 % auf Vorschub, Materialpreis, Stundensatz, Rüstzeit, Zeit Zusatzarbeiten; die drei größten Hebel je Position
- lineare Größe ergibt die erwartete Änderung (Stundensatz +10 % = −(−10 %)); Stangensprung wird erkannt
- das Angebot bleibt unverändert

Aufruf: python tests/test_empfindlichkeit.py
"""
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
from rohrlaser import empfindlichkeit as ef, rechnen  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402


def ok(t):
    print("OK    ", t)


def main():
    db = Datenbank(Path(tempfile.mkdtemp()) / "r.db")
    k, tab = db.kontext(), db.tabellen()
    a = db.angebot_neu(dict(kunde="T", maschine="T11", stange=6000))
    kopf = db.angebot(a)
    pos = [dict(id=1, pos=10, profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=1000.0, stueck=13,
                schneidweg=800, einstiche=4),
           dict(id=2, pos=20, profil_id="RR 42,4x2,0", werkstoff_id="S235-10219", laenge=400.0, stueck=30,
                schneidweg=300, einstiche=2)]
    erg = rechnen.optimieren(kopf, pos, k, tab, db.einstellungen())
    einst = rechnen.einstellungen_angebot(kopf, db.einstellungen())
    vorher = rechnen.kalkulation(kopf, pos, erg, k, tab, einst)[1]["verkauf"]
    r = ef.rechnen_alle(kopf, pos, erg, k, tab, db.einstellungen())
    assert abs(r["basis"] - vorher) < 1e-9
    je = {x["hebel"]: x for x in r["angebot"]}
    assert set(je) == set(ef.HEBEL)
    s = je[ef.SATZ]
    assert s["plus"] > 0 and s["minus"] < 0 and s["linear"] and abs(s["plus"] + s["minus"]) < 0.02 * s["plus"], s
    m = je[ef.MATERIAL]
    assert m["plus"] > 0 and m["minus"] < 0, m
    v = je[ef.VORSCHUB]
    assert v["plus"] < 0 < v["minus"] and v["linear"], v       # schneller = billiger, Zeit mit 1/Vorschub
    assert [abs(x["plus"]) for x in r["angebot"]][0] >= max(abs(x["plus"]) for x in r["angebot"]) - 1e-9
    for p in r["positionen"]:
        assert len(p["hebel"]) <= 3
    ok("Stundensatz linear (+10 % = −(−10 %)), Material teurer, Vorschub schneller = billiger, Top 3 je Position: "
       + "; ".join(f"{x['hebel']} {ef.text(x)}" for x in r["angebot"][:3]))
    assert rechnen.kalkulation(kopf, pos, erg, k, tab, einst)[1]["verkauf"] == vorher
    ok("Angebot unverändert")
    # Stangensprung: Optimierung mit anderer Stangenzahl bei +10 % Material (künstlich)
    alt = rechnen.optimieren
    zaehler = []

    def opt(kp, positionen, k2, t2, e):
        zaehler.append(1)
        out = alt(kp, positionen, k2, t2, e)
        if len(zaehler) == 1:
            out = dict(out, stangen=list(out["stangen"]) + [out["stangen"][0]])
        return out
    rechnen.optimieren = opt
    try:
        r2 = ef.rechnen_alle(kopf, pos, erg, k, tab, db.einstellungen(), hebel=(ef.MATERIAL,))
    finally:
        rechnen.optimieren = alt
    x = r2["angebot"][0]
    assert x["stangen"] and x["stangen"][2] == x["stangen"][1] + 1 and "Stangen" in ef.text(x), x
    assert not ef._linear(10.0, -2.0) and ef._linear(10.0, -10.1)
    ok("Stangensprung gemeldet, nicht lineare Änderung erkannt")
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from rohrlaser.fenster import Hauptfenster
    app = QApplication.instance() or QApplication([])  # noqa: F841
    tmp = Path(tempfile.mkdtemp())
    db = Datenbank(tmp / "rohrlaser.db")
    hf = Hauptfenster(db, tmp, stumm=True)
    aid = db.angebot_neu(dict(kunde="Test", maschine="T11", stange=6000))
    db.position_neu(aid, dict(pos=10, artikel="A", profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=1000.0,
                              stueck=13, schneidweg=800, einstiche=4))
    s = hf.angebot_oeffnen(aid)
    seite = s.optimierung_seite
    assert seite.empfindlichkeit_laden() is None and "Erst optimieren" in seite.ef_info.text()
    assert s.optimieren()
    r = seite.empfindlichkeit_laden()
    assert r and seite.ef_tabelle.rowCount() >= len(ef.HEBEL) and "Größte Hebel" in seite.ef_info.text()
    ok("Reiter Optimierung: Knopf „Empfindlichkeit rechnen (±10 %)“ mit Tabelle")
    print("alle Prüfungen bestanden")


if __name__ == "__main__":
    main()
