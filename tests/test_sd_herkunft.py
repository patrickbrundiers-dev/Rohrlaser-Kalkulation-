"""Herkunft und Sicherheit der Schneiddaten (MACH-014, Patrick 12.11.2026 „Alle Empfehlungen“).

- Schneiddaten haben Quelle und Stand; die Beispieldaten sind „Richtwert“
- je Teil: aus Werkstoff oder Kategorie, interpoliert, außerhalb der gemessenen Wand, Quelle, Stand, Sicherheit
- keine Zahl ändert sich (nur Anzeige)

Aufruf: python tests/test_sd_herkunft.py
"""
import sys
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
from rohrlaser import rechnen  # noqa: E402
from rohrlaser.stammdaten import SCHNEIDDATEN, beispieldaten  # noqa: E402


def ok(t):
    print("OK    ", t)


def z(w, v, q=None, wid="S235", kat=None, datum=None):
    return dict(maschinen_id="L1", werkstoff_id=wid, kategorie=kat, gas=None, wand_bis=w, vorschub_gross=v,
                einstechzeit=1.0, quelle=q, datum=datum)


def main():
    assert {"quelle", "datum"} <= {f.name for f in SCHNEIDDATEN.felder}
    assert all(x["quelle"] == "Richtwert" for x in beispieldaten()["schneiddaten"])
    ok("Felder Quelle und Stand, Beispieldaten = Richtwert")
    tab = dict(schneiddaten=[z(2, 4000, "eigene Messung", datum="2026-11-01"), z(4, 2000, "eigene Messung")], einstellungen={})
    sd = rechnen._schneiddaten("L1", "S235", 2, tab)
    h = rechnen.sd_herkunft(sd, 2)
    assert h["sicherheit"] == "hoch" and "Quelle eigene Messung" in h["text"] and "Stand 2026-11-01" in h["text"], h
    sd = rechnen._schneiddaten("L1", "S235", 3, tab)
    h = rechnen.sd_herkunft(sd, 3)
    assert h["sicherheit"] == "mittel" and "interpoliert 2–4 mm" in h["text"], h
    assert sd["vorschub_gross"] == 3000
    sd = rechnen._schneiddaten("L1", "S235", 1, tab)
    h = rechnen.sd_herkunft(sd, 1)
    assert h["sicherheit"] == "niedrig" and "außerhalb der gemessenen Wand" in h["text"], h
    assert sd["vorschub_gross"] == 4000
    ok("hoch auf der Stufe, mittel interpoliert, niedrig unter der kleinsten Stufe (Werte unverändert)")
    tab = dict(schneiddaten=[z(2, 4000, None, wid=None, kat="Stahl")], einstellungen={})
    h = rechnen.sd_herkunft(rechnen._schneiddaten("L1", "S235", 2, tab, kategorie="Stahl"), 2)
    assert h["sicherheit"] == "mittel" and "aus Kategorie Stahl" in h["text"] and "unbekannt" in h["text"], h
    tab = dict(schneiddaten=[z(2, 4000, "geschätzt")], einstellungen={})
    assert rechnen.sd_herkunft(rechnen._schneiddaten("L1", "S235", 2, tab), 2)["sicherheit"] == "niedrig"
    assert rechnen.sd_herkunft(None) is None
    ok("Kategorie und ohne Quelle = mittel, geschätzt = niedrig")
    print("alle Prüfungen bestanden")


if __name__ == "__main__":
    main()
