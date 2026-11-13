"""Neue Schweiß-Richtwerte melden (Plan Schweißbaugruppe Teil 2, 13.11.2026, A5): kennt das Programm Regeln der
Schweiß-Vorkalkulation, die in den Stammdaten noch fehlen (z. B. nach einem Update: Ansatzzeit, Schweißlage,
Nahtvorbereitung, Vorwärmen, Prüfumfang), erscheint auf der Startseite eine Aufgabe. Geladen wird erst auf Klick;
vorhandene Zeilen werden nie geändert. Wer die neuen Regeln nicht will, blendet die Aufgabe aus (gilt, bis das
Programm wieder andere neue Regeln kennt)."""
from . import baugruppe

TABELLE = "schweiss_regeln"
AUS = "schweiss_richtwerte_aus"         # Einstellung: Liste der Schlüssel, die nicht mehr gemeldet werden


def fehlend(db):
    """Fehlende Regelzeilen [dict]; leer, solange die Tabelle noch ganz leer ist (dann lädt das Programm die
    Richtwerte beim ersten Vorkalkulieren selbst, A2)."""
    tab = db.tabellen()
    if not tab.get(TABELLE):
        return []
    return list(baugruppe.richtwerte_fehlend(tab).get(TABELLE) or ())


def _schluessel(zeilen):
    return sorted(f"{z.get('art')}|{z.get('wert')}" for z in zeilen)


def offen(db):
    """Fehlende Zeilen, die noch nicht ausgeblendet wurden."""
    aus = db.einstellung(AUS)
    aus = set(aus) if isinstance(aus, list) else set()
    return [z for z in fehlend(db) if f"{z.get('art')}|{z.get('wert')}" not in aus]


def arten(zeilen):
    out = []
    for z in zeilen:
        if z.get("art") not in out:
            out.append(z.get("art"))
    return out


def text(db):
    """Text der Aufgabe auf der Startseite oder ''."""
    z = offen(db)
    if not z:
        return ""
    return (f"Neue Schweiß-Richtwerte verfügbar: {len(z)} Regel(n) ({', '.join(arten(z))}) – Doppelklick lädt sie, "
            "vorhandene Werte bleiben unverändert")


def laden(db):
    """Fehlende Regeln eintragen. Ergebnis: [(Tabelle, id)] der neuen Zeilen (für Rückgängig)."""
    return [(TABELLE, db.neu(TABELLE, z)) for z in offen(db)]


def zurueck(db, neue):
    for name, i in reversed(neue):
        db.loeschen(name, [i])


def ausblenden(db):
    """Die jetzt fehlenden Regeln nicht mehr melden."""
    alt = db.einstellung(AUS)
    db.einstellung_setzen(AUS, sorted(set(alt if isinstance(alt, list) else ()) | set(_schluessel(fehlend(db)))))
