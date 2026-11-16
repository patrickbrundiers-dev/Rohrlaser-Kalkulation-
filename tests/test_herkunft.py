"""Herkunft und Sicherheit je Rechenwert (CALC-028, Patrick 12.11.2026 „Alle Empfehlungen“).

- Summe der Anteile = Preis (je Position und im Angebot)
- Wert von Hand ergibt Quelle „von Hand“; Dynamik-Richtwert ergibt „unsicher“
- Schneiddaten unter der kleinsten Stufe = unsicher, interpoliert/Kategorie = prüfen
- keine Zahl der Kalkulation ändert sich

Aufruf: python tests/test_herkunft.py
"""
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
from rohrlaser import herkunft as hk, rechnen  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402


def ok(t):
    print("OK    ", t)


def main():
    db = Datenbank(Path(tempfile.mkdtemp()) / "rohrlaser.db")
    k, tab = db.kontext(), db.tabellen()
    m = next(iter(k.maschinen))
    pid = next(p for p, w in k.profile.items() if w.get("form") == "Rundrohr")
    wst = next(w for w in k.werkstoffe if rechnen.schneiddaten(m, w, 2.0, tab, rechnen.kategorie(w, k)))
    a = db.angebot_neu(dict(kunde="Test", maschine=m))
    kopf = db.angebot(a)
    pos = [dict(id=1, pos=10, profil_id=pid, werkstoff_id=wst, laenge=800, stueck=30, schneidweg=400, einstiche=2),
           dict(id=2, pos=20, profil_id=pid, werkstoff_id=wst, laenge=500, stueck=10, schneidweg=300, zeit_manuell=12.0)]

    def kalk(pos, tab=tab):
        erg = rechnen.optimieren(kopf, pos, k, tab, db.einstellungen())
        einst = rechnen.einstellungen_angebot(kopf, db.einstellungen())
        return rechnen.kalkulation(kopf, pos, erg, k, tab, einst)

    zeilen, summen = kalk(pos)
    u = hk.uebersicht(kopf, pos, zeilen, k, tab)
    for p, z in zip(u["positionen"], zeilen):
        assert abs(sum(b["eur_position"] for b in p["bausteine"]) - p["preis"]) < 1e-6, p
        assert abs(p["preis"] - z["preis_teil"] * z["stueck"]) < 1e-6
    assert abs(sum(u["je_sicherheit"].values()) - u["gesamt"]) < 1e-6
    assert abs(sum(u["je_quelle"].values()) - u["gesamt"]) < 1e-6
    assert u["pruefen_eur"] > 0, "Richtwert-Schneiddaten aus der Kategorie = prüfen"
    ok(f"Summe der Anteile = Preis ({rechnen.zahl(u['gesamt'])} €): {hk.text(u)}")
    laser2 = next(b for b in u["positionen"][1]["bausteine"] if b["baustein"] == "Laser")
    assert laser2["quelle"] == hk.HAND and laser2["sicherheit"] == hk.SICHER
    ok("Schneidzeit von Hand = Quelle „von Hand“")
    z = dict(zeilen[0], zeit_dynamik="ja", zeit_anfahren=5.0, zeit_drehen=5.0, laser_brutto=40.0)
    bs = hk.bausteine(z, pos[0], kopf, k, tab)
    dyn = next(b for b in bs if "Dynamik" in b["baustein"])
    assert dyn["sicherheit"] == hk.UNSICHER and dyn["quelle"] == hk.RICHTWERT
    assert abs(sum(b["eur"] for b in bs) - z["preis_teil"]) < 1e-9
    ok("Bewegungszeit aus der Dynamik = Richtwert, unsicher")
    bs = hk.bausteine(dict(zeilen[0], sd_sicherheit="niedrig"), pos[0], kopf, k, tab)
    assert next(b for b in bs if b["baustein"] == "Laser")["sicherheit"] == hk.UNSICHER
    bs = hk.bausteine(dict(zeilen[0], sd_sicherheit="mittel"), pos[0], kopf, k, tab)
    assert next(b for b in bs if b["baustein"] == "Laser")["sicherheit"] == hk.PRUEFEN
    ok("Schneiddaten niedrig = unsicher, mittel = prüfen")
    bs = hk.bausteine(zeilen[0], dict(pos[0], preis_m=9.5), kopf, k, tab)
    assert next(b for b in bs if b["baustein"] == "Material")["quelle"] == hk.HAND
    ok("Materialpreis von Hand = Quelle „von Hand“")
    z2, s2 = kalk(pos)
    assert [x["preis_teil"] for x in z2] == [x["preis_teil"] for x in zeilen] and s2["verkauf"] == summen["verkauf"]
    ok("Kalkulation unverändert")
    assert hk.uebersicht(kopf, [], [], k, tab)["gesamt"] == 0
    ok("leeres Angebot")
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from rohrlaser.fenster import Hauptfenster
    app = QApplication.instance() or QApplication([])  # noqa: F841
    tmp = Path(tempfile.mkdtemp())
    db = Datenbank(tmp / "rohrlaser.db")
    fenster = Hauptfenster(db, tmp, stumm=True)
    aid = db.angebot_neu(dict(kunde="Test", maschine="T11", stange=6000))
    db.position_neu(aid, dict(pos=10, artikel="A", profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=3100.0,
                              stueck=30, schneidweg=200, einstiche=1))
    s = fenster.angebot_oeffnen(aid)
    assert s.optimieren()
    s.freigabe_punkte()
    w = s.uebersicht_bereich.kennzahl["unsicher"]
    assert w.text().endswith("%)") and "unsicher" in w.toolTip(), (w.text(), w.toolTip())
    u = s.herkunft_uebersicht()
    assert abs(sum(u["je_sicherheit"].values()) - u["gesamt"]) < 1e-6
    ok(f"Übersicht im Angebot: Kennzahl Unsicher {w.text()}")
    print("alle Prüfungen bestanden")


if __name__ == "__main__":
    main()
