"""Einheitliche Schreibweise von Material- und Profilabmessungen (Patrick 25.11.2026, Master-Auftrag „Einheitliche
Material- und Maßschreibweise“): kompakt ohne Leerzeichen, kleines x, Durchmesserzeichen direkt vor der Zahl.

    50 x 50 x 3   -> 50x50x3        Ø 60 x 3     -> Ø60x3
    50X50X3       -> 50x50x3        ∅60 × 3      -> Ø60x3
    50 x50x 3     -> 50x50x3        40 x 20 x 2,5 -> 40x20x2,5

Die Formatierung passiert nur bei der Ausgabe (Anzeige, PDF, Mail, CSV/Excel): gespeicherte Werte in der Datenbank
bleiben, wie sie sind, es gibt keine Migration. Suche und Zuordnung vergleichen über suchschluessel(), damit alte
Schreibweisen („QR 40 x 40 x 3“) und neue („QR 40x40x3“) dasselbe Material finden.

Drei Stufen:
- abmessung(text): für einen Text, der nur eine Abmessung bzw. Material-/Profilbezeichnung ist (Profil-ID,
  „Rundrohr Ø 42,4 x 2“, „Blech 500 × 300 × 5 mm“). Jedes Maß-Kreuz zwischen zwei Zahlen wird „x“, „Ø 60“ wird „Ø60“.
- text(t): für freie Texte (Positionstext, Artikelbezeichnung, Mailzeile), in denen „Ø“ auch „Durchschnitt“ heißen
  kann („Ø 12,50 €/m“) und „ד auch eine Anzahl („3 × 5 min“): nur Ketten aus Zahlen mit x/X (auch mit Leerzeichen),
  „Ø“ nur direkt vor einer solchen Kette. Ketten mit „ד werden nur mit mindestens drei Zahlen zusammengezogen
  („500 × 300 × 5 mm“), zwei Zahlen mit „ד bleiben (könnte eine Rechnung sein).
- suchschluessel(t): Vergleichsschlüssel für Suche/Filter/Zuordnung (abmessung + klein + Leerzeichen zusammengefasst).

Werkstoffbezeichnungen bleiben unverändert: „1.4301 X5CrNi18-10“ ist keine Abmessung, weil nach dem X ein Buchstabe
folgt; „S235JR“, „EN 10219“, „AlMg3“ enthalten kein Maß-Kreuz. Dezimalzahlen mit Komma oder Punkt bleiben so, wie sie
geschrieben sind (die Zahl selbst wird nie umgerechnet oder gerundet).
"""
import re

__all__ = ["abmessung", "format_material_dimension", "text", "profil", "suchschluessel", "gleich", "finde", "alte_schreibweise"]

_ZAHL = r"\d+(?:[.,]\d+)?"
# hinter der letzten Zahl darf kein Buchstabe folgen (sonst Werkstoff 'X5CrNi', Gewinde 'M6x1' bleibt erlaubt) –
# außer Einheiten mm/m/cm (‚60x3mm')
_ENDE = r"(?!(?!(?:mm|cm|m)(?![^\W\d_]))[^\W\d_])"
_DURCHMESSER = "∅⌀"                       # andere Durchmesserzeichen -> Ø
_KREUZ_ALLE = r"[xX×✕*]"
_KREUZ_TEXT = r"[xX]"

# Kette: Zahl (Kreuz Zahl)+ ; Leerzeichen um das Kreuz egal
_KETTE_ALLE = re.compile(rf"(?<![.,])(?<![^\WØ]){_ZAHL}(?:[ \t ]*{_KREUZ_ALLE}[ \t ]*{_ZAHL})+{_ENDE}")
_KETTE_TEXT = re.compile(rf"(?<![.,])(?<![^\WØ]){_ZAHL}(?:[ \t ]*{_KREUZ_TEXT}[ \t ]*{_ZAHL})+{_ENDE}")
_KETTE_MAL3 = re.compile(rf"(?<![.,])(?<![^\WØ]){_ZAHL}(?:[ \t ]*[×✕][ \t ]*{_ZAHL}){{2,}}{_ENDE}")
_KREUZ = re.compile(rf"[ \t ]*{_KREUZ_ALLE}[ \t ]*")
_D_ZAHL = re.compile(rf"Ø[ \t ]+(?={_ZAHL})")
_D_KETTE = re.compile(rf"Ø[ \t ]+(?={_ZAHL}[ \t ]*[xX×✕*][ \t ]*\d)")


def _kompakt(m):
    return _KREUZ.sub("x", m.group(0))


def _durchmesser(t):
    for z in _DURCHMESSER:
        t = t.replace(z, "Ø")
    return t


def abmessung(wert):
    """Abmessung bzw. Material-/Profilbezeichnung in der einheitlichen kompakten Schreibweise (formatMaterialDimension):
    'Rundrohr Ø 42,4 x 2' -> 'Rundrohr Ø42,4x2', '50X50X3' -> '50x50x3', 'Blech 500 × 300 × 5 mm' ->
    'Blech 500x300x5 mm'. None -> '', Zahlen werden als Text zurückgegeben."""
    if wert is None:
        return ""
    t = str(wert)
    if not t:
        return t
    t = _durchmesser(t)
    t = _KETTE_ALLE.sub(_kompakt, t)
    return _D_ZAHL.sub("Ø", t)


format_material_dimension = abmessung      # Name aus dem Auftrag (formatMaterialDimension)


def text(wert):
    """Freier Text (Positionstext, Bezeichnung, Mail, CSV-Feld) mit Abmessungen in kompakter Schreibweise; sonst
    unverändert. 'Ø 12,50 €/m' (Durchschnitt) und '3 × 5 min' (Rechnung) bleiben stehen."""
    if wert is None:
        return ""
    if not isinstance(wert, str):
        return wert
    if not wert or not any(c in wert for c in "xX×✕Ø∅⌀"):
        return wert
    t = wert
    if any(z in t for z in _DURCHMESSER):
        t = re.sub(rf"[{_DURCHMESSER}](?=[ \t ]*\d)", "Ø", t)
    t = _KETTE_TEXT.sub(_kompakt, t)
    t = _KETTE_MAL3.sub(_kompakt, t)
    return _D_KETTE.sub("Ø", t)


def profil(pid):
    """Profil-ID für die Anzeige: 'QR 40 x 40 x 3' (alte Schreibweise in der Datenbank) -> 'QR 40x40x3'. Die ID in der
    Datenbank bleibt unverändert (Schlüssel für Preise, Lieferlängen, Angebote)."""
    return abmessung(pid) if pid else ("" if pid is None else pid)


def suchschluessel(wert):
    """Vergleichsschlüssel für Suche, Filter und Zuordnung: Schreibweise und Groß-/Kleinschreibung egal,
    'QR 40 x 40 x 3' == 'qr 40x40x3' == 'QR 40X40X3'."""
    return " ".join(abmessung(wert).casefold().split())


def finde(wert, schluessel):
    """Vorhandener Schlüssel (z. B. Profil-ID aus k.profile) mit derselben Abmessung wie wert, nur anders geschrieben
    ('qr 40 x 40 x 3' -> 'QR 40x40x3'); genau gleich geht vor; None, wenn keiner oder mehrere passen."""
    if wert is None or wert == "":
        return None
    if wert in schluessel:
        return wert
    such = suchschluessel(wert)
    treffer = [s for s in schluessel if isinstance(s, str) and suchschluessel(s) == such]
    return treffer[0] if len(treffer) == 1 else None


def gleich(a, b):
    """True, wenn beide Texte dieselbe Abmessung meinen (nur Schreibweise verschieden)."""
    return suchschluessel(a) == suchschluessel(b)


def alte_schreibweise(wert):
    """True, wenn der Text noch eine Abmessung in alter Schreibweise enthält (für Tests und Prüfungen)."""
    if not isinstance(wert, str) or not wert:
        return False
    return text(wert) != wert
