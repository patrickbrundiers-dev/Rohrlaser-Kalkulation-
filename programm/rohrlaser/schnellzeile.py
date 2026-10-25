"""Schnellzeile über der Positionsliste (Plan Bedienung B6): eine Position in einer Zeile tippen, z. B.
„QR 40x3 S235 1250 20“ = Profil, Werkstoff, Länge [mm], Stückzahl. Mehrere Zeilen (z. B. aus einer E-Mail) legen
mehrere Positionen an.

Erkannt wird je Zeile:
- Werkstoff: ein Wort, das eine Werkstoff-ID ist (Groß-/Kleinschreibung egal) oder in genau einer vorkommt (S235 →
  S235JR, 4301 → 1.4301);
- Länge und Stückzahl: die erste Zahl ist die Länge, die zweite die Stückzahl; eindeutig mit „L=1250“, „1250mm“,
  „20 Stk“, „20St“, „x20“ oder „20x“ (Komma oder Punkt als Dezimalzeichen);
- Artikelnummer: ein Wort mit „#“ davor (#4711-01);
- Profil: der Rest, gesucht wie in der Profilspalte (tabellen_eingabe.profil_treffer: „40x3“ findet QR 40x40x3).
"""
import re

from . import tabellen_eingabe

ZAHL = r"\d+(?:[.,]\d+)?"


def _zahl(text):
    return float(text.replace(",", "."))


def werkstoff_finden(wort, werkstoffe):
    """Werkstoff-ID zu einem Wort: gleich (ohne Groß-/Kleinschreibung), sonst eindeutig enthalten, sonst None."""
    w = wort.lower()
    if len(w) < 3:
        return None
    gleich = [x for x in werkstoffe if x.lower() == w]
    if gleich:
        return gleich[0]
    teil = [x for x in werkstoffe if w in x.lower()]
    return teil[0] if len(teil) == 1 else None


def zeile_lesen(text, profile, werkstoffe):
    """Eine Zeile lesen. Ergebnis: dict(profil_id, werkstoff_id, laenge, stueck, artikel, rest, fehler) – nur
    erkannte Werte; fehler = Liste der Hinweise (fehlt Profil/Länge …)."""
    erg = dict(fehler=[])
    t = " " + (text or "").strip() + " "
    # Artikelnummer
    m = re.search(r"\s#(\S+)", t)
    if m:
        erg["artikel"] = m.group(1)
        t = t[:m.start()] + " " + t[m.end():]
    # eindeutige Länge und Stückzahl
    for muster, feld in ((rf"\sL\s*=\s*({ZAHL})\s*(?:mm)?(?=\s)", "laenge"), (rf"\s({ZAHL})\s*mm(?=\s)", "laenge"),
                         (rf"\s({ZAHL})\s*(?:stk\.?|st\.?|stück|x)(?=\s)", "stueck"),
                         (rf"\s[x×]\s*({ZAHL})(?=\s)", "stueck")):
        m = re.search(muster, t, re.IGNORECASE)
        if m and feld not in erg:
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
        ws = werkstoff_finden(wort, werkstoffe) if "werkstoff_id" not in erg and not re.search(r"\d+[x×*]\d", wort) \
            else None
        if ws:
            erg["werkstoff_id"] = ws
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


def lesen(text, profile, werkstoffe):
    """Alle nicht leeren Zeilen (auch mit Tabulator oder ; getrennt wie aus Excel). Ergebnis: Liste von zeile_lesen."""
    out = []
    for z in re.split(r"[\r\n]+", text or ""):
        z = re.sub(r"[\t;]+", " ", z).strip()
        if z:
            out.append(dict(zeile_lesen(z, profile, werkstoffe), text=z))
    return out


def vorschau(erg, zahl_text=str):
    """Kurzer Text, was die Zeile ergibt (für die Anzeige unter der Schnellzeile)."""
    teile = [erg.get("profil_id") or "Profil ?", erg.get("werkstoff_id") or "Werkstoff (Vorgabe)",
             f"L = {zahl_text(erg['laenge'])} mm" if erg.get("laenge") else "L = ?",
             f"{erg.get('stueck') or 1} Stk"]
    if erg.get("artikel"):
        teile.insert(0, f"Art. {erg['artikel']}")
    return " · ".join(teile) + ("  –  " + "; ".join(erg["fehler"]) if erg.get("fehler") else "")
