"""Ergebnisprüfung der Kalkulation (Master-Prompt Rechenkerne und Systemstabilität, Patrick 21.11.2026: „Eine
fehlerhafte Berechnung darf niemals unbemerkt als korrektes Ergebnis übernommen werden.“).

Nach jeder Kalkulation prüft pruefen() das Ergebnis unabhängig von der Rechnung: Jede Zahl in den Zeilen und Summen
muss endlich sein (kein NaN, kein ±∞). Ein solcher Wert entsteht nur durch einen Rechenfehler (Division durch 0,
beschädigte Stammdaten, Überlauf) und würde sonst still als Preis 0, „nan €“ oder als falsche Summe weitergereicht.

Findet die Prüfung etwas, steht in summen["rechenfehler"] eine Liste lesbarer Befunde. Der Angebots-Check zeigt dann
einen FEHLER (blockiert das Angebots-PDF, übergehen nur mit Begründung), das Protokoll bekommt eine Warnung und die
Diagnose zählt die fehlgeschlagene Kalkulation. Ein fehlerfreies Ergebnis bleibt unverändert (kein neuer Schlüssel,
die Rechenergebnisse sind bitgleich). An den Formeln ändert die Prüfung nichts.
"""
import math

MAX_BEFUNDE = 12            # so viele Befunde werden genannt (der Rest nur gezählt)
_TIEFE = 6                  # Verschachtelung der Ergebnisse (Zeilen → Bausteine → Listen); tiefer wird nicht geprüft


def _ungueltig(w):
    return isinstance(w, float) and not math.isfinite(w)


def _suchen(w, pfad, out, tiefe):
    if _ungueltig(w):
        out.append((pfad, w))
    elif tiefe < _TIEFE:
        if isinstance(w, dict):
            for k, v in w.items():
                if isinstance(v, (float, dict, list, tuple)):
                    _suchen(v, f"{pfad}.{k}" if pfad else str(k), out, tiefe + 1)
        elif isinstance(w, (list, tuple)):
            for i, v in enumerate(w):
                if isinstance(v, (float, dict, list, tuple)):
                    _suchen(v, f"{pfad}[{i}]", out, tiefe + 1)


def _alle_endlich(wurzel):
    """True, wenn keine Zahl in der Struktur NaN/∞ ist (ohne Rekursion, nur Typprüfungen und isfinite)."""
    stapel = [wurzel]
    endlich, fl, dc, ls, tp = math.isfinite, float, dict, list, tuple
    while stapel:
        w = stapel.pop()
        for v in (w.values() if type(w) is dc else w):
            t = type(v)
            if t is fl:
                if not endlich(v):
                    return False
            elif t is dc or t is ls or t is tp:
                stapel.append(v)
    return True


def befunde(zeilen, summen):
    """[(Ort, Wert)] aller ungültigen Zahlen. Ort: „Pos. 20: material“ bzw. „Summe: verkauf“."""
    if _alle_endlich((zeilen, summen)):      # schneller Vorab-Test ohne Pfade (der Normalfall)
        return []
    out = []
    for z in zeilen or ():
        if isinstance(z, dict):
            roh = []
            _suchen(z, "", roh, 0)
            out += [(f"Pos. {z.get('pos', '?')}: {o}", w) for o, w in roh]
    if isinstance(summen, dict):
        roh = []
        _suchen({k: v for k, v in summen.items() if k != "rechenfehler"}, "", roh, 0)
        out += [(f"Summe: {o}", w) for o, w in roh]
    return out


def texte(gefunden):
    """Lesbare Liste für summen["rechenfehler"] (höchstens MAX_BEFUNDE, dann „… und n weitere“)."""
    t = [f"{o} = {w!r}" for o, w in gefunden[:MAX_BEFUNDE]]
    if len(gefunden) > MAX_BEFUNDE:
        t.append(f"… und {len(gefunden) - MAX_BEFUNDE} weitere")
    return t


def pruefen(zeilen, summen, name="Kalkulation"):
    """Ergebnis prüfen; bei Befunden summen["rechenfehler"] setzen, protokollieren und zählen. Ergebnis: Befunde
    als Texte (leer = in Ordnung)."""
    try:
        gefunden = befunde(zeilen, summen)
    except Exception as ex:     # noqa: BLE001 – Prüfung darf die Kalkulation nicht abbrechen; Fehler wird gemeldet
        gefunden = [("Prüfung", f"nicht möglich: {type(ex).__name__}: {ex}")]
    if not gefunden:
        return []
    t = texte(gefunden)
    if isinstance(summen, dict):
        summen["rechenfehler"] = t
    from . import diagnose
    diagnose.fehlgeschlagen(name, "; ".join(t[:3]))
    from . import protokoll
    protokoll.warnung(f"{name}: ungültiges Ergebnis (Rechenfehler) – " + "; ".join(t[:5]))
    return t


def check_text(summen):
    """Text für den Angebots-Check oder None."""
    t = (summen or {}).get("rechenfehler") if isinstance(summen, dict) else None
    if not t:
        return None
    return ("Rechenfehler in der Kalkulation: ungültige Zahl im Ergebnis (" + "; ".join(t[:3])
            + (" …" if len(t) > 3 else "") + "). Eingaben und Stammdaten der Position prüfen; das Ergebnis ist so "
            "nicht verwendbar.")
