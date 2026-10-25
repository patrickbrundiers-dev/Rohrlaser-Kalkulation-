"""Schnellzeile über der Positionsliste (Plan Bedienung B6): eine Position in einer Zeile tippen, z. B.
„QR 40x3 S235 1250 20“ = Profil, Werkstoff, Länge [mm], Stückzahl. Mehrere Zeilen (z. B. aus einer E-Mail) legen
mehrere Positionen an.

Erkannt wird je Zeile:
- Werkstoff: ein Wort, das eine Werkstoff-ID ist (Groß-/Kleinschreibung egal) oder in genau einer vorkommt (S235 →
  S235JR, 4301 → 1.4301); passt es zu mehreren (S235 → S235-10219, S235-10210), gilt der erste aus bevorzugt
  (letzte Position, Vorgabe, zuletzt benutzt), sonst Hinweis „mehrdeutig“ (Fehlersuche 25.10.2026);
- Länge und Stückzahl: die erste Zahl ist die Länge, die zweite die Stückzahl; eindeutig mit „L=1250“, „1250mm“,
  „20 Stk“, „20St“, „x20“, „20x“ oder „1250 x 20“ nach dem Profil (Komma oder Punkt als Dezimalzeichen);
- Profilmaße mit Leerzeichen („RR 42,4 x 2“, „QR 40 x 40 x 3“) gehören zum Profil, wenn sie am Zeilenanfang oder
  direkt nach dem Profilkürzel stehen;
- Artikelnummer: ein Wort mit „#“ davor (#4711-01);
- Profil: der Rest, gesucht wie in der Profilspalte (tabellen_eingabe.profil_treffer: „40x3“ findet QR 40x40x3).
"""
import re

from . import tabellen_eingabe

ZAHL = r"\d+(?:[.,]\d+)?"


def _zahl(text):
    return float(text.replace(",", "."))


def werkstoff_kandidaten(wort, werkstoffe):
    """Werkstoff-IDs zu einem Wort: [gleiche] (ohne Groß-/Kleinschreibung), sonst alle, die es enthalten."""
    w = wort.lower()
    if len(w) < 3:
        return []
    gleich = [x for x in werkstoffe if x.lower() == w]
    return gleich[:1] or [x for x in werkstoffe if w in x.lower()]


def werkstoff_finden(wort, werkstoffe, bevorzugt=()):
    """Werkstoff-ID zu einem Wort: gleich, sonst eindeutig enthalten, sonst der erste passende aus bevorzugt, sonst
    None."""
    teil = werkstoff_kandidaten(wort, werkstoffe)
    if len(teil) == 1:
        return teil[0]
    return next((b for b in bevorzugt or () if b in teil), None)


# Profilmaße mit Leerzeichen („42,4 x 2“, „40 x 40 x 3“) am Zeilenanfang oder nach einem Kürzel aus Buchstaben
PROFIL_MASS = re.compile(rf"(^\s*|\s[A-Za-zÄÖÜäöü]+\.?\s*)({ZAHL}(?:\s*[x×*]\s*{ZAHL})+)(?=\s)")


def zeile_lesen(text, profile, werkstoffe, bevorzugt=()):
    """Eine Zeile lesen. Ergebnis: dict(profil_id, werkstoff_id, laenge, stueck, artikel, rest, fehler) – nur
    erkannte Werte; fehler = Liste der Hinweise (fehlt Profil/Länge …). bevorzugt: Werkstoff-IDs für ein mehrdeutiges
    Wort (z. B. S235), in dieser Reihenfolge."""
    erg = dict(fehler=[])
    t = " " + (text or "").strip() + " "
    # Artikelnummer
    m = re.search(r"\s#(\S+)", t)
    if m:
        erg["artikel"] = m.group(1)
        t = t[:m.start()] + " " + t[m.end():]
    # Profilmaße mit Leerzeichen zusammenziehen, damit „x“ darin keine Stückzahl wird
    t = PROFIL_MASS.sub(lambda m: m.group(1) + re.sub(r"\s+", "", m.group(2)), t, count=1)
    # eindeutige Länge und Stückzahl
    for muster, feld in ((rf"\sL\s*=\s*({ZAHL})\s*(?:mm)?(?=\s)", "laenge"), (rf"\s({ZAHL})\s*mm(?=\s)", "laenge"),
                         (rf"\s({ZAHL})\s*(?:stk\.?|st\.?|stück)(?=\s)", "stueck"),
                         (rf"\s({ZAHL})\s+[x×]\s*({ZAHL})(?=\s)", "paar"),       # „1250 x 20“ = Länge × Stück
                         (rf"\s[x×]\s*({ZAHL})(?=\s)", "stueck"),
                         (rf"\s({ZAHL})\s*[x×](?=\s)", "stueck")):
        m = re.search(muster, t, re.IGNORECASE)
        if m and feld == "paar":
            if "laenge" not in erg and "stueck" not in erg:
                erg["laenge"], erg["stueck"] = _zahl(m.group(1)), _zahl(m.group(2))
                t = t[:m.start()] + " " + t[m.end():]
        elif m and feld not in erg:
            erg[feld] = _zahl(m.group(1))
            t = t[:m.start()] + " " + t[m.end():]
    rest = []
    zahlen = []
    for wort in t.split():
        if "werkstoff_id" not in erg and wort.lower() in {x.lower() for x in werkstoffe}:
            erg["werkstoff_id"] = werkstoff_finden(wort, werkstoffe)    # auch Zahlen wie 1.4301
            continue
        kurz = [x for x in werkstoffe if x.endswith("." + wort)] if re.fullmatch(r"\d{4}", wort) else []
        if "werkstoff_id" not in erg and len(kurz) == 1:                # 4301 = 1.4301
            erg["werkstoff_id"] = kurz[0]
            continue
        if re.fullmatch(ZAHL, wort):
            zahlen.append(_zahl(wort))
            continue
        kand = werkstoff_kandidaten(wort, werkstoffe) if "werkstoff_id" not in erg and \
            not re.search(r"\d+[x×*]\d", wort) else []
        ws = werkstoff_finden(wort, werkstoffe, bevorzugt) if kand else None
        if ws:
            erg["werkstoff_id"] = ws
        elif len(kand) > 1 and re.search(r"\d", wort):     # mehrdeutig (S235): nicht ins Profil, Hinweis
            erg["fehler"].append(f"Werkstoff „{wort}“ mehrdeutig ({', '.join(kand[:3])}"
                                 + (" …" if len(kand) > 3 else "") + ")")
        else:
            rest.append(wort)
    for feld in ("laenge", "stueck"):
        if feld not in erg and zahlen:
            erg[feld] = zahlen.pop(0)
    if zahlen:          # weitere lose Zahlen gehören zum Profil (z. B. „RR 42,4 x 2“)
        rest += [str(z).rstrip("0").rstrip(".") for z in zahlen]
    if "stueck" in erg:
        erg["stueck"] = max(1, int(round(erg["stueck"])))
    profil_text = " ".join(rest).strip()
    if profil_text:
        treffer = tabellen_eingabe.profil_treffer(profil_text, list(profile))
        if treffer:
            erg["profil_id"] = treffer[0]
        else:
            erg["fehler"].append(f"Profil „{profil_text}“ nicht gefunden")
    erg["rest"] = profil_text
    if "profil_id" not in erg and not profil_text:
        erg["fehler"].append("Profil fehlt")
    if not erg.get("laenge"):
        erg["fehler"].append("Länge fehlt")
    return erg


def lesen(text, profile, werkstoffe, bevorzugt=()):
    """Alle nicht leeren Zeilen (auch mit Tabulator oder ; getrennt wie aus Excel). Ergebnis: Liste von zeile_lesen."""
    out = []
    for z in re.split(r"[\r\n]+", text or ""):
        z = re.sub(r"[\t;]+", " ", z).strip()
        if z:
            out.append(dict(zeile_lesen(z, profile, werkstoffe, bevorzugt), text=z))
    return out


def vorschau(erg, zahl_text=str):
    """Kurzer Text, was die Zeile ergibt (für die Anzeige unter der Schnellzeile)."""
    teile = [erg.get("profil_id") or "Profil ?", erg.get("werkstoff_id") or "Werkstoff (Vorgabe)",
             f"L = {zahl_text(erg['laenge'])} mm" if erg.get("laenge") else "L = ?",
             f"{erg.get('stueck') or 1} Stk"]
    if erg.get("artikel"):
        teile.insert(0, f"Art. {erg['artikel']}")
    return " · ".join(teile) + ("  –  " + "; ".join(erg["fehler"]) if erg.get("fehler") else "")
