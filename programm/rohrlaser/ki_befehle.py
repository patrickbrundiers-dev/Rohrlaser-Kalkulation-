"""KI 3, Paket D: Befehle in Worten für die Bohrungen eines Angebots (Plan 20.11.2026).

Beispiele: „alle Bohrungen Ø 8,5 als M10“, „Ø 6,8 als Einnietmutter M8“, „Pos. 20 Ø 9 Flowdrill M10“,
„alle Senkungen bestätigen“, „Ø 5 nur lasern“, „Bohrungen Ø 4,2 ablehnen“.

befehl(text, positionen, gewinde, wand_fn) liest den Befehl regelbasiert (kein Sprachmodell nötig) und liefert für
jede betroffene Position das neue Bohrbild als Vorschlag mit Vorher/Nachher. Übernommen wird erst mit dem Knopf
„Übernehmen“ im KI-Assistenten (angebot_fenster.bohrungen_alle_pruefen, mit Rückgängig wie dort). Die STEP-Kontur
bleibt unverändert: die Ausführung ändert nur Kalkulation und Laser-Ø (Grundregel Patrick 25.10.2026). Ohne Qt."""
import re

from . import bohrbild

TOL = 0.15              # mm: Ø im Befehl gegen gemessenen Ø
ARTEN_BOHRUNG = ("Bohrung", "Fließloch", "Senkung", bohrbild.BOHREN)

AUSFUEHRUNG_WORTE = (
    (r"flow\s*drill|fließloch|fliessloch|fließbohr", bohrbild.FLOWDRILL),
    (r"einniet|nietmutter|einpress", bohrbild.EINNIET),
    (r"senk", bohrbild.SENKEN),
    (r"aufbohr|\bbohren\b|nachbohr", bohrbild.AUFBOHREN),
    (r"nur\s+lasern|nur\s+schneiden|\blasern\b", bohrbild.NUR_LASER),
    (r"gewinde|\bschneiden\b|\bals\s+m\s?\d", bohrbild.GEWINDE_SCHNEIDEN),
)


def _zahl(t):
    try:
        return float(str(t).replace(",", "."))
    except ValueError:
        return None


def lesen(text):
    """dict(d, gewinde, aus, status, pos, nur_art) aus dem Befehl oder None, wenn es kein Bohrungsbefehl ist."""
    t = str(text or "").strip()
    tl = t.casefold()
    if t.endswith("?"):         # Frage, kein Befehl
        return None
    if not re.search(r"bohrung|ø|durchmesser|senkung|gewinde|flowdrill|fließloch|einniet|\bm\s?\d{1,2}\b", tl):
        return None
    d = None
    m = re.search(r"(?:ø|⌀|durchmesser|\bd\s*=?)\s*(\d{1,2}(?:[.,]\d{1,2})?)", tl)
    if m:
        d = _zahl(m.group(1))
    else:
        m = re.search(r"bohrungen?\s+(\d{1,2}(?:[.,]\d{1,2})?)\s*(?:mm)?\b(?!\s*(?:stück|stk|x))", tl)
        if m:
            d = _zahl(m.group(1))
    g = re.search(r"\bm\s?(\d{1,2})\b", tl)
    gewinde = f"M{int(g.group(1))}" if g else None
    status = bohrbild.ABGELEHNT if re.search(r"ablehn|verwerf|keine?\s+gewinde", tl) else bohrbild.BESTAETIGT
    aus = None
    if status != bohrbild.ABGELEHNT:
        for muster, a in AUSFUEHRUNG_WORTE:
            if re.search(muster, tl):
                aus = a
                break
    pos = None
    p = re.search(r"\bpos(?:ition)?\.?\s*(\d{1,4})\b", tl)
    if p:
        pos = int(p.group(1))
    nur_art = None
    if re.search(r"alle\s+senkungen|senkungen\s+(?:bestätig|übernehm|ablehn)", tl) and d is None:
        nur_art = "Senkung"
    elif re.search(r"alle\s+(?:fließl|flowdrill)", tl) and d is None:
        nur_art = "Fließloch"
    if d is None and nur_art is None and not re.search(r"\balle\b", tl):
        return None
    if aus is None and status == bohrbild.BESTAETIGT and not re.search(r"bestätig|übernehm|ok\b", tl):
        return None
    return dict(d=d, gewinde=gewinde, aus=aus, status=status, pos=pos, nur_art=nur_art)


def _beschreibung(z):
    aus = z.get("aus") or bohrbild.ausfuehrung(z)
    teile = [bohrbild.KURZ.get(aus, aus)]
    if z.get("gewinde") and aus in bohrbild.MIT_GROESSE:
        teile.append(z["gewinde"])
    teile.append(z.get("status") or bohrbild.OFFEN)
    return " ".join(str(x) for x in teile if x)


def befehl(text, positionen, gewinde, wand_fn=None):
    """dict(befehl, werte {Zeile: neues Bohrbild}, aenderungen [Text], text) oder None (kein Bohrungsbefehl).
    positionen: Liste der Positionen (Zeile = Index), gewinde: [(Name, Kernloch)], wand_fn(p) → Wandstärke."""
    b = lesen(text)
    if b is None:
        return None
    werte, aenderungen = {}, []
    for r, p in enumerate(positionen):
        if b["pos"] is not None and str(p.get("pos")) != str(b["pos"]):
            continue
        liste = bohrbild.aus_position(p, gewinde, wand_fn(p) if wand_fn else None) or []
        neu, n = [], 0
        for z in liste:
            passt = z.get("art") in ARTEN_BOHRUNG and (b["nur_art"] is None or z.get("art") == b["nur_art"])
            if passt and b["d"] is not None:
                passt = abs(float(z.get("d") or 0) - b["d"]) <= TOL
            if not passt:
                neu.append(z)
                continue
            vorher = _beschreibung(z)
            y = dict(z)
            if b["aus"]:
                y = bohrbild.ausfuehrung_setzen(y, b["aus"], gewinde, groesse_=b["gewinde"])
            elif b["gewinde"] and z.get("art") in ("Bohrung", "Fließloch"):
                y["gewinde"] = b["gewinde"]
            y["status"] = b["status"]
            nachher = _beschreibung(y)
            if y != z:
                n += 1
                aenderungen.append(f"Pos. {p.get('pos') or r + 1}: {z.get('anzahl') or 1}× Ø "
                                   f"{str(z.get('d')).replace('.', ',')} {z.get('art')}: {vorher} → {nachher}")
            neu.append(y)
        if n:
            werte[r] = neu
    if not werte:
        txt = "Keine passende Bohrung gefunden" + (f" (Ø {str(b['d']).replace('.', ',')} mm ± {TOL})"
                                                  if b["d"] is not None else "") + "."
    else:
        txt = (f"Vorschlag für {len(werte)} Position(en) – „Übernehmen“ speichert ihn (die STEP-Kontur bleibt "
               "unverändert):\n" + "\n".join("• " + a for a in aenderungen))
    return dict(befehl=b, werte=werte, aenderungen=aenderungen, text=txt)
