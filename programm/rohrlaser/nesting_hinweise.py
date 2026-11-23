"""Lokale Hinweise zur Verschachtelung (Patrick 23.11.2026, Punkt 12 „KI-Unterstützung“; Dauerregel: KI nur lokal,
nur Hinweise). Ohne Qt, ohne Netz, ohne Modell: feste, nachvollziehbare Prüfregeln auf den gerechneten Kennzahlen
des Strategievergleichs (nesting_vergleich). Die Hinweise rechnen nichts neu und ändern nichts; übernommen wird
nur, was der Benutzer im Nesting-Arbeitsplatz wählt. Die mathematische Optimierung bleibt deterministisch.

Regeln:
  - Einsparung: eine Strategie kauft mindestens HINWEIS_EUR € bzw. HINWEIS_ANTEIL günstiger ein als bisher.
  - Schwache Stange: die am schwächsten belegte Stange des bisherigen Plans ist zu weniger als SCHWACH belegt
    (Kandidat für eine kürzere Länge oder ein Reststück).
  - Hoher Verschnitt: nicht verwertbarer Verschnitt über VERSCHNITT_HOCH der eingekauften Länge.
  - Reststücke: passende Reste im Lager, aber Strategie C ist nicht gewählt.
  - Preis fehlt: eine Lieferlänge hat keinen Preis (Vergleich nach Kosten nur eingeschränkt möglich).
"""
from . import nesting as ne, rechnen

HINWEIS_EUR = 10.0
HINWEIS_ANTEIL = 0.02
SCHWACH = 0.30
VERSCHNITT_HOCH = 0.12


def hinweise(v):
    """Hinweistexte für eine Gruppe aus nesting_vergleich.vergleich."""
    out = []
    z = rechnen.zahl
    bisher = v["plaene"].get("bisher")
    zeilen = {x["strategie"]: x for x in v["zeilen"]}
    b = zeilen.get("bisher")
    if b and b.get("einkauf"):
        beste = max((x for x in v["zeilen"] if x["strategie"] != "bisher" and x.get("ersparnis") is not None),
                    key=lambda x: x["ersparnis"], default=None)
        if beste and beste["ersparnis"] >= max(HINWEIS_EUR, HINWEIS_ANTEIL * b["einkauf"]):
            out.append(f"{beste['name']} kauft {z(beste['ersparnis'])} € günstiger ein als bisher "
                       f"({beste['laengen']}).")
    if bisher and bisher.stangen:
        g = v["gruppe"]
        schwach = min(bisher.stangen, key=lambda s: sum(t.laenge for t, _ in s[1]) / s[0])
        anteil = sum(t.laenge for t, _ in schwach[1]) / schwach[0]
        if anteil < SCHWACH and len(bisher.stangen) > 1:
            out.append(f"Eine Stange ist bisher nur zu {z(100 * anteil, 0)} % belegt – eine kürzere Lieferlänge "
                       f"oder ein Reststück lohnt sich (Strategie B oder C).")
        w = bisher.werte
        if w["gesamt_mm"] and w["verschnitt_mm"] / w["gesamt_mm"] > VERSCHNITT_HOCH:
            out.append(f"Hoher Verschnitt: {z(100 * w['verschnitt_mm'] / w['gesamt_mm'], 1)} % der Stangenlänge "
                       f"ist nicht verwertbar ({g.profil}).")
    if v["daten"]["reste"] and v.get("gewaehlt") not in (ne.C, ne.E):
        out.append(f"{len(v['daten']['reste'])} passende Reststücke im Lager – Strategie C setzt sie zuerst ein.")
    if any(x.preis is None for x in v["daten"]["laengen"]):
        out.append("Für mindestens eine Lieferlänge fehlt der Preis: Strategien nach Kosten vergleichen diese Länge "
                   "nicht (Preise in der Materialdatenbank pflegen).")
    return out
