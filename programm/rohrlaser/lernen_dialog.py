"""Datei → Lernzentrale … (Plan „Programm soll lernen“, Patrick 08.11.2026; Logik in lernen.py).

Alles, was das Programm gelernt hat: Zusatzarbeit-Vorschläge je Kunde (gleich übernehmen bzw. ablehnen), Nacharbeit
nach dem Import, Teileart und Profil aus dem STEP-Prüfdialog, Kennwert-Vorschläge und -Freigaben aus der
Nachkalkulation. „Vergessen“ nimmt einen markierten Eintrag zurück (auch bei den Kollegen im gemeinsamen Ordner),
„Nicht mehr lernen“ sperrt einen Zusatzarbeit-Eintrag, „Kennwerte prüfen …“ öffnet die Vorschläge der
Nachkalkulation zum Freigeben. Vorschläge aus Handeinträgen (muster.py: Erkennungswort, Arbeitsgang-Regel) übernimmt
„Übernehmen“ (mit Rückgängig in der Einblendung); „Vergessen“ lehnt sie ab. Ebenso die Vorschläge aus einsichten.py
(Kundenvorgabe, Programmierzeit; der Schneidzeit-Hinweis lässt sich nur ausblenden)."""
from PySide6.QtGui import QBrush

from . import lernen, stil
from .tabelle_dialog import TabellenDialog


def zeilen(eintraege):
    return [[e["bereich"], e["kunde"], e["was"], e["stand"], e["wann"]] for e in eintraege]


def zeigen(f, dialog=None):
    """Fenster zeigen. dialog(d) bedient es statt exec (Tests). Ergebnis: das Fenster."""
    eintraege = lernen.uebersicht(f.db)

    def ausfuehren(markiert, fn):
        texte, fehler = [], False
        for r in markiert:
            try:
                texte.append(fn(f.db, eintraege[r]))
            except Exception as ex:
                texte.append(f"{eintraege[r]['bereich']}: {ex}")
                fehler = True
        if texte:
            f.meldung(" · ".join(texte), fehler=fehler)
            if hasattr(f, "start"):
                f.start.neu_laden()
            d.accept()

    def uebernehmen(markiert):
        from . import einsichten, muster
        texte, rueck = [], []
        for r in markiert:
            q = eintraege[r]["quelle"]
            if q not in ("muster", "einsicht"):
                continue
            try:
                t, zurueck = (muster if q == "muster" else einsichten).uebernehmen(f.db, eintraege[r]["schluessel"])
                texte.append(t)
                rueck.append(zurueck)
            except Exception as ex:
                texte.append(f"{eintraege[r]['bereich']}: {ex}")
        if texte:
            def alles_zurueck():
                for fn in reversed(rueck):
                    fn()
                f.meldung("Vorschläge zurückgenommen.")
            f.meldung(" · ".join(texte), aktion=("Rückgängig", alles_zurueck) if rueck else None)
            d.accept()

    def kennwerte(_markiert):
        from .kennwerte_dialog import KennwerteDialog
        d.accept()
        k = KennwerteDialog(f, f.db)
        k.exec()
        if k.geaendert and hasattr(f, "alles_neu_laden"):
            f.alles_neu_laden()

    def lst_einlesen(_markiert):
        from . import produktion_lst
        erg = produktion_lst.ordner_einlesen(f.db)
        f.meldung(produktion_lst.ergebnis_text(erg), fehler=bool(erg["fehler"]) and not erg["neu"])
        d.accept()

    grau = {i: QBrush(stil.farbe("#8A94A3")) for i, e in enumerate(eintraege) if not e["gelernt"]}
    n = sum(1 for e in eintraege if e["gelernt"])
    text = (f"{n} Sache{'n' if n != 1 else ''} gelernt; grau = noch beobachtet (gelernt nach {lernen.SCHWELLE} gleichen "
            "Entscheidungen in verschiedenen Angeboten) oder wartet auf Ihre Freigabe. Gelerntes wendet der "
            "STEP-Import selbst an und schreibt es ins Automatik-Protokoll (dort Rückgängig). Markieren und "
            "„Vergessen“ nimmt es zurück, auch bei den Kollegen im gemeinsamen Ordner. Preise lernt das Programm nie."
            if eintraege else "Das Programm hat noch nichts gelernt. Es lernt aus Ihren ✓/✗ bei Zusatzarbeit-"
            "Vorschlägen, aus Änderungen nach dem STEP-Import und aus der Nachkalkulation.")
    try:                        # Lernsystem L1: gesammelte Produktionsdaten aus TRUMPF-LST
        from . import produktion_lst
        u = produktion_lst.uebersicht(f.db)
        if u["dateien"]:
            text += (f" Produktionsdaten: {u['dateien']} LST-Dateien, {u['teile']} Teile ({u['voll']} vollständig, "
                     f"{u['gemessen']} mit gemessener Zeit).")
    except Exception:           # noqa: BLE001 – nur Anzeige
        pass
    d = TabellenDialog(f, "Lernzentrale", text, ("Bereich", "Kunde", "Was gelernt", "Stand", "Geändert"),
                       zeilen(eintraege),
                       [("Vergessen", lambda m: ausfuehren([r for r in m if eintraege[r]["vergessen"]],
                                                           lernen.vergessen)),
                        ("Übernehmen", uebernehmen),
                        ("Nicht mehr lernen", lambda m: ausfuehren(
                            [r for r in m if eintraege[r]["quelle"] == lernen.TABELLE], lernen.sperren)),
                        ("Kennwerte prüfen …", kennwerte),
                        ("LST-Ordner einlesen", lst_einlesen)],
                       farben=grau, breite=1100)
    if dialog:
        dialog(d)
    else:
        d.exec()
    return d
