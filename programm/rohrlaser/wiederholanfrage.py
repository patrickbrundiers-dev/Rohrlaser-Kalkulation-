"""Wiederholanfrage ohne STEP (Automationen 03.11.2026, Vorschlag 6a).

Schreibt ein bekannter Kunde nur Artikelnummern und Mengen („wie letztes Mal, 200 Stück 4711-02“), sucht das
Programm die Artikel in seinem Teilekatalog (alle seine Angebote, teilekatalog.katalog). Die Anfrage-Karte zeigt
„Wiederholanfrage … N bekannte Artikel“; im Fenster wählt man die Artikel, „Neues Angebot aus Auswahl“ kopiert die
Positionen des neuesten Angebots (mit den gespeicherten STEP-Konturen, ohne Staffeln) und setzt die angefragten
Stückzahlen. Die Preise rechnet das neue Angebot mit den aktuellen Stammdaten. Aus Zeichnungen entsteht weiter nichts
automatisch (Patrick 28.10.2026). Ohne Qt."""
import re

MIN_LAENGE = 3          # kürzere Artikelnummern werden nicht gesucht (zu viele Zufallstreffer)


def _form(t):
    return re.sub(r"[\s\-_./]", "", str(t or "")).casefold()


def treffer(db, kundennr, text):
    """Bekannte Artikel des Kunden im Text: [dict(Katalogzeile, menge=angefragte Stückzahl oder None, sicher)]."""
    from . import formular, mail, teilekatalog
    if not kundennr or not (text or "").strip():
        return []
    katalog = [r for r in teilekatalog.katalog(db, kundennr) if len(_form(r["artikel"])) >= MIN_LAENGE]
    if not katalog:
        return []
    neu = mail.neuester_teil(text)
    form = _form(neu)
    gefunden = [r for r in katalog if _form(r["artikel"]) in form]
    if not gefunden:
        return []
    mengen = formular.stueckzahlen(neu, [r["artikel"] for r in gefunden])
    return [dict(r, menge=(mengen.get(r["artikel"]) or (None, False))[0],
                 sicher=bool((mengen.get(r["artikel"]) or (None, False))[1])) for r in gefunden]


def stueck_setzen(db, angebot_id, liste):
    """Stückzahlen der Anfrage in die kopierten Positionen des neuen Angebots (gleiche Artikelnummer). Ergebnis:
    Anzahl gesetzter Positionen."""
    mengen = {_form(r["artikel"]): int(r["menge"]) for r in liste if r.get("menge")}
    n = 0
    for p in db.positionen(angebot_id):
        m = mengen.get(_form(p.get("artikel")))
        if m and m != p.get("stueck"):
            db.position_aendern(p["id"], "stueck", m)
            n += 1
    return n
