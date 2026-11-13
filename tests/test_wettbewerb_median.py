"""Wettbewerbsabstand je Kategorie (OFFER-022, Patrick 12.11.2026 „Alle Empfehlungen“).

- ab 3 Absagen mit Wettbewerbspreis (gleiche Werkstoff-Kategorie und Preisklasse) Median, Anzahl und Streuung
- unter 3 Werten kein Hinweis; Median stimmt (Ausreißer verschiebt ihn nicht); Gewinn bleibt

Aufruf: python tests/test_wettbewerb_median.py
"""
import datetime
import sys
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
from rohrlaser import kalk_hinweise as kh  # noqa: E402


def ok(t):
    print("OK    ", t)


def main():
    heute = datetime.date(2026, 11, 12)

    def absage(i, netto, preis, w="S235"):
        return dict(id=i, nummer=f"A{i}", kunde="K", datum="2026-10-01", vk_netto=netto, vorgang="Abgelehnt",
                    versand=[dict(art="absage", datum="2026-10-05", grund="Preis zu hoch", preis=preis)]), w
    daten = [absage(1, 1100.0, 1000.0), absage(2, 1200.0, 1000.0), absage(3, 1990.0, 1000.0),
             absage(4, 1500.0, 1000.0, "1.4301")]
    zeilen = [z for z, _ in daten]
    werkstoffe = {z["id"]: [w] for z, w in daten}
    kat = {"S235": "Stahl", "1.4301": "Edelstahl"}
    m = kh.marktpreis(zeilen, werkstoffe, kat, "Stahl", 1500.0, heute=heute)
    assert m and m["n"] == 3, m
    assert abs(m["abstand"] - 0.2) < 1e-9 and abs(m["min"] - 0.1) < 1e-9 and abs(m["max"] - 0.99) < 1e-9, m
    assert abs(m["mittel"] - (0.1 + 0.2 + 0.99) / 3) < 1e-9
    t = kh.markt_text(m)
    assert "Median 20 % unter uns" in t and "3 Absagen" in t and "Streuung 10 % unter bis 99 % unter" in t, t
    assert "Gewinn ändert sich dadurch nicht" in t
    ok(f"Median 20 % trotz Ausreißer 99 %, mit Anzahl und Streuung: {t}")
    assert kh.marktpreis(zeilen, werkstoffe, kat, "Edelstahl", 1500.0, heute=heute) is None
    assert kh.marktpreis(zeilen[:2], werkstoffe, kat, "Stahl", 1500.0, heute=heute) is None
    assert kh.markt_text(None) == ""
    ok("unter 3 Werten kein Hinweis")
    print("alle Prüfungen bestanden")


if __name__ == "__main__":
    main()
