"""Datei → Automatik-Protokoll … (Automationen 03.11.2026, Vorschlag 14a; Logik in automatik.py).

Alles, was das Programm von selbst erledigt hat (Anfrage vorbereitet, Nachtrag einsortiert, Kundendaten ergänzt,
Bestellung zugeordnet, Auftrag gestartet, Lieferantenantwort eingelesen, Nachkalkulation vorbelegt …) der letzten 90
Tage, neueste oben. „Rückgängig“ nimmt einen markierten Schritt zurück, wo das geht (Datei zurücklegen, Kundendaten
und Zusatzdaten wie vorher); „Angebot öffnen“ springt ins Angebot."""
from PySide6.QtGui import QBrush

from . import automatik, stil
from .tabelle_dialog import TabellenDialog


def zeilen(eintraege):
    out = []
    for e in eintraege:
        out.append([e["zeit"][:16].replace("T", " "), e["kuerzel"] or "", e["titel"], e.get("nummer") or "",
                    e["text"], "zurückgenommen" if e["zurueck"] else ("Rückgängig möglich" if e["rueckgaengig"]
                                                                      else "")])
    return out


def zeigen(f, dialog=None):
    """Fenster zeigen. dialog(d) bedient es statt exec (Tests). Ergebnis: das Fenster."""
    eintraege = automatik.liste(f.db)
    for e in eintraege:
        if e.get("angebot_id"):
            e["nummer"] = (f.db.angebot(e["angebot_id"]) or {}).get("nummer") or ""

    def rueck(markiert):
        texte, fehler = [], False
        for r in markiert:
            try:
                texte.append(automatik.rueckgaengig(f.db, eintraege[r]["id"]))
            except Exception as ex:
                texte.append(f"{eintraege[r]['titel']}: {ex}")
                fehler = True
        if texte:
            f.meldung(" ".join(texte), fehler=fehler)
            if hasattr(f, "start"):
                f.start.neu_laden()
            d.accept()

    def oeffnen(markiert):
        for r in markiert[:1]:
            if eintraege[r].get("angebot_id"):
                d.accept()
                f.angebot_oeffnen(eintraege[r]["angebot_id"])

    grau = {i: QBrush(stil.farbe("#8A94A3")) for i, e in enumerate(eintraege) if e["zurueck"]}
    d = TabellenDialog(f, "Automatik-Protokoll", "Was das Programm in den letzten 90 Tagen von selbst erledigt hat. "
                       "Einen Schritt markieren und „Rückgängig“ nimmt ihn zurück, wo das geht."
                       if eintraege else "Das Programm hat in den letzten 90 Tagen nichts von selbst erledigt.",
                       ("Zeit", "Wer", "Was", "Angebot", "Einzelheiten", ""), zeilen(eintraege),
                       [("Rückgängig", rueck), ("Angebot öffnen", oeffnen)], farben=grau, breite=1100)
    if dialog:
        dialog(d)
    else:
        d.exec()
    return d
