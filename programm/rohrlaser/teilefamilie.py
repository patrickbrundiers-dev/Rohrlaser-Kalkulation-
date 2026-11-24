"""Teilefamilien mit Variablen (CAD-010, Plan N4 vom 16.11.2026, Patrick „Alle Empfehlungen“).

Aus einem Teil (Rohr-/Profilteil aus dem Rohr-Editor oder Blech aus dem Blech-Editor) werden in einem Schritt mehrere
Positionen: man wählt die Werte, die sich ändern (VARIABLEN), und füllt eine Wertetabelle (auch aus Excel
eingefügt). Jede Zeile wird eine eigene Position, gerechnet wie aus dem Editor.

Variablen: Länge (Blech: Länge und Breite eines Zuschnitts, beim Kantteil die Kantlänge), Stückzahl, Artikel,
Bezeichnung, Profil, Werkstoff und die Anzahl der Konturen einer Lochreihe („n1“, „n2“ … je Konturzeile mit Anzahl > 1).

Konturen bei anderer Länge (F5 a): eine Kontur bzw. Lochreihe, deren Mitte in der hinteren Hälfte liegt, wandert mit
Ende B (Abstand zu Ende B bleibt), die anderen bleiben ab Ende A. Eine Lochreihe mit eigener Anzahl in der Tabelle
wird zwischen ihrer ersten und letzten Kontur gleichmäßig neu verteilt; reicht sie über die Mitte, bleibt die erste
zu Ende A und die letzte zu Ende B (die Reihe streckt sich mit der Länge), sonst bleiben beide an ihrem Ende.
Beim Blech gilt dasselbe für x (Länge) und y (Breite). Konturen ohne Lage bleiben, wie sie sind.

Ohne Qt. Die Positionen legt das Angebot an (familie_mixin.py), das Fenster steht in teilefamilie_dialog.py.
Vorlage: Positionsvorlage (Tabelle positionsvorlagen) mit dem Teil und unter '_familie' den Variablen und Zeilen.
"""
import copy
import json
import re

from . import blech, schneidweg as sw
from .angebot import ist_baugruppe, ist_zukaufteil

ROHR, BLECH = "Rohr", "Blech"
LAENGE, BREITE, STUECK, ARTIKEL, BEZEICHNUNG, PROFIL, WERKSTOFF = (
    "laenge", "breite", "stueck", "artikel", "bezeichnung", "profil_id", "werkstoff_id")
TITEL = {LAENGE: "Länge [mm]", BREITE: "Breite [mm]", STUECK: "Stückzahl", ARTIKEL: "Artikel",
         BEZEICHNUNG: "Bezeichnung", PROFIL: "Profil", WERKSTOFF: "Werkstoff"}
IMMER = (ARTIKEL, BEZEICHNUNG)          # stehen immer in der Tabelle (jedes Teil braucht eigene Nummer/Bezeichnung)
ZAHLEN = (LAENGE, BREITE, STUECK)
REIHE = "n"                             # Variable n1, n2 …: Anzahl der Konturzeile 1, 2 … (Nummer = Zeile + 1)
VORLAGE_SCHLUESSEL = "_familie"
MAX_ZEILEN = 200


def _z(v):
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).strip().replace(".", "").replace(",", ".")) if "," in str(v) else float(str(v).strip())
    except (TypeError, ValueError):
        return None


def _mm(v):
    v = round(float(v), 2)
    return int(v) if v.is_integer() else v


def _text(v):
    v = _z(v)
    if v is None:
        return ""
    return f"{_mm(v):g}".replace(".", ",")


def reihe_name(idx):
    return f"{REIHE}{idx + 1}"


def reihe_index(name):
    m = re.fullmatch(REIHE + r"(\d+)", str(name or ""))
    return int(m.group(1)) - 1 if m else None


# ------------------------------------------------------------------ Teil lesen
def teil_art(p):
    """ROHR (Rohr-/Profilteil mit Profil), BLECH (aus dem Blech-Editor) oder None (Baugruppe, Zukauf, Sonstiges)."""
    if not p or ist_baugruppe(p):
        return None
    if blech.lesen(p.get("technik")) is not None and ist_zukaufteil(p):
        return BLECH
    if ist_zukaufteil(p) or not p.get("profil_id"):
        return None
    return ROHR


def eingaben(p, art=None, profil=None):
    """Editor-Eingaben des Teils (Kopie): Rohr = schneidweg.lesen (+ Werte aus dem STEP-Import, aus_position),
    Blech = blech.lesen."""
    art = art or teil_art(p)
    if art == BLECH:
        return copy.deepcopy(blech.lesen(p.get("technik")) or {})
    e = sw.lesen(p.get("technik"))
    if profil:
        e, _ = sw.aus_position(e, p, profil)
    return copy.deepcopy(e)


def _reihen(e):
    """[(Index, Text, Anzahl)] der Konturzeilen mit Anzahl > 1 (Lochreihen, Lochfelder)."""
    out = []
    for i, k in enumerate(e.get("konturen") or ()):
        n = int(_z(k.get("anzahl")) or 1)
        if n > 1 and k.get("art") not in sw.GRAVUREN:
            s = next((s for s in ("d", "l", "b", "laenge") if _z(k.get(s))), None)
            mass = (" Ø" if s == "d" else " ") + _text(k[s]) if s else ""
            out.append((i, f"{k.get('art') or 'Kontur'}{mass} ({n}×)", n))
    return out


def basis(p, e=None, profil=None):
    """Was sich an diesem Teil ändern lässt: dict(art, werte {Variable: Wert}, variablen [(Name, Titel)], reihen,
    hinweise) oder dict(art=None, fehler) für Teile ohne Teilefamilie."""
    art = teil_art(p)
    if art is None:
        return dict(art=None, fehler="Teilefamilie gibt es für Rohr-/Profilteile und Bleche aus dem Blech-Editor.")
    e = copy.deepcopy(e) if e is not None else eingaben(p, art, profil)
    hinweise, variablen = [], []
    werte = {STUECK: p.get("stueck") or e.get("stueck") or 1, ARTIKEL: p.get("artikel") or "",
             BEZEICHNUNG: p.get("bezeichnung") or ""}
    if art == ROHR:
        werte.update({LAENGE: p.get("laenge"), PROFIL: p.get("profil_id"), WERKSTOFF: p.get("werkstoff_id")})
        if e.get("knickrahmen"):
            hinweise.append("Knickrahmen: die Länge ergibt sich aus den Schenkeln und ist keine Variable.")
        else:
            variablen.append(LAENGE)
        variablen += [STUECK, PROFIL, WERKSTOFF]
    else:
        werte[WERKSTOFF] = e.get("werkstoff")
        if e.get("art") == blech.KANTTEIL:
            werte[LAENGE] = e.get("kantlaenge")
            variablen.append(LAENGE)
        elif e.get("form") == blech.POLYGON:
            hinweise.append("Freie Außenkontur (Polygon): Länge und Breite sind keine Variablen.")
        else:
            werte.update({LAENGE: e.get("laenge"), BREITE: e.get("breite")})
            variablen += [LAENGE, BREITE]
        variablen += [STUECK, WERKSTOFF]
    reihen = _reihen(e)
    for i, text, n in reihen:
        werte[reihe_name(i)] = n
    titel = [(v, TITEL[v]) for v in variablen] + [(reihe_name(i), f"Anzahl {text}") for i, text, _ in reihen]
    return dict(art=art, werte=werte, variablen=titel, reihen=reihen, hinweise=hinweise, eingaben=e)


# ------------------------------------------------------------------ Konturen mitziehen
def _reihe_anpassen(k, l_alt, l_neu, n_neu, achse="x"):
    """Kontur k (Kopie) an die neue Länge bzw. Anzahl anpassen (Regel F5 a, Moduldoku). Ergebnis: Fehlertext oder
    None."""
    x = _z(k.get(achse))
    n = int(_z(k.get("anzahl")) or 1)
    a = (_z(k.get("abstand")) or 0.0) if achse == "x" else 0.0
    if n_neu is not None:
        n_neu = int(n_neu)
        if n_neu < 1:
            return "Anzahl mindestens 1"
    if x is None:                       # Lage unbekannt: nur die Anzahl
        if n_neu is not None:
            k["anzahl"] = n_neu
        return None
    d = (l_neu - l_alt) if l_alt is not None and l_neu is not None else 0.0
    erste, letzte = x, x + (n - 1) * a
    if n_neu is not None and n_neu != n and n > 1 and a > 0:
        haelfte = l_alt / 2 if l_alt is not None else None
        if haelfte is None or erste < haelfte - 1e-9 < letzte:
            erste_neu, letzte_neu = erste, letzte + d       # über die Mitte: erste zu Ende A, letzte zu Ende B
        elif erste >= haelfte - 1e-9:
            erste_neu, letzte_neu = erste + d, letzte + d   # hintere Hälfte: beide zu Ende B
        else:
            erste_neu, letzte_neu = erste, letzte           # vordere Hälfte: beide zu Ende A
        if letzte_neu < erste_neu - 1e-9:
            return "Lochreihe passt nicht mehr in die Länge"
        k["anzahl"] = n_neu
        if n_neu > 1:
            k[achse] = _mm(erste_neu)
            k["abstand"] = _mm((letzte_neu - erste_neu) / (n_neu - 1))
        else:
            k[achse] = _mm((erste_neu + letzte_neu) / 2)
            k.pop("abstand", None)
        return None
    if n_neu is not None:
        k["anzahl"] = n_neu
    if l_alt is not None and (erste + letzte) / 2 > l_alt / 2 + 1e-9:
        k[achse] = _mm(x + d)
    return None


def _pruefen_lage(k, laenge, achse="x"):
    x = _z(k.get(achse))
    if x is None or laenge is None:
        return None
    n = int(_z(k.get("anzahl")) or 1)
    a = (_z(k.get("abstand")) or 0.0) if achse == "x" else 0.0
    if x < -1e-6 or x + (n - 1) * a > laenge + 1e-6:
        return "liegt außerhalb des Teils"
    return None


def konturen_anpassen(konturen, l_alt, l_neu, anzahl=None, achse="x", pruefen=True):
    """Konturen (Kopie) an Länge l_neu und Anzahlen {Konturindex: n} anpassen. Ergebnis: (Konturen, [Fehler])."""
    out, fehler = [], []
    anzahl = anzahl or {}
    for i, k in enumerate(konturen or ()):
        k = dict(k)
        f = _reihe_anpassen(k, l_alt, l_neu, anzahl.get(i), achse)
        if f is None and pruefen:
            f = _pruefen_lage(k, l_neu, achse)
        if f:
            fehler.append(f"Kontur {i + 1} ({k.get('art') or 'Kontur'}): {f}")
        out.append(k)
    return out, fehler


def rohr_eingaben(e, l_alt, werte):
    """Rohr-Editor-Eingaben für ein Familienmitglied: Konturen mitziehen. Ergebnis (Eingaben, [Fehler])."""
    e = copy.deepcopy(e)
    l_neu = _z(werte.get(LAENGE)) if werte.get(LAENGE) not in (None, "") else _z(l_alt)
    anz = {reihe_index(n): _z(w) for n, w in werte.items() if reihe_index(n) is not None and _z(w) is not None}
    e["konturen"], fehler = konturen_anpassen(e.get("konturen"), _z(l_alt), l_neu, anz)
    return e, fehler


def blech_eingaben(e, werte):
    """Blech-Editor-Eingaben für ein Familienmitglied (Länge/Breite bzw. Kantlänge, Werkstoff, Konturen).
    Ergebnis (Eingaben, [Fehler])."""
    e = copy.deepcopy(e)
    fehler = []
    anz = {reihe_index(n): _z(w) for n, w in werte.items() if reihe_index(n) is not None and _z(w) is not None}
    kant = e.get("art") == blech.KANTTEIL
    l_feld = "kantlaenge" if kant else "laenge"
    l_alt, b_alt = _z(e.get(l_feld)), (None if kant else _z(e.get("breite")))
    l_neu = _z(werte.get(LAENGE)) if werte.get(LAENGE) not in (None, "") else l_alt
    b_neu = _z(werte.get(BREITE)) if werte.get(BREITE) not in (None, "") and not kant else b_alt
    if l_neu is not None and l_neu <= 0 or b_neu is not None and b_neu <= 0:
        return e, ["Länge und Breite größer 0"]
    konturen, f1 = konturen_anpassen(e.get("konturen"), l_alt, l_neu, anz, "x",
                                     pruefen=e.get("form") != blech.POLYGON)
    if not kant and e.get("form") != blech.POLYGON:
        konturen, f2 = konturen_anpassen(konturen, b_alt, b_neu, {}, "y")
    else:
        f2 = []
    fehler += f1 + f2
    e["konturen"] = konturen
    if l_neu is not None and e.get("form") != blech.POLYGON or kant:
        e[l_feld] = _mm(l_neu)
    if b_neu is not None and not kant and e.get("form") != blech.POLYGON:
        e["breite"] = _mm(b_neu)
    if werte.get(WERKSTOFF):
        e["werkstoff"] = werte[WERKSTOFF]
    if werte.get(STUECK) not in (None, ""):
        e["stueck"] = int(_z(werte[STUECK]) or 1)
    for s in ("step", "ursprung", "angebotspreis", "richtpreise"):      # neues Teil: nicht mehr wie aus STEP
        e.pop(s, None)
    return e, fehler


# ------------------------------------------------------------------ Tabelle
def standard_zeilen(b, n=1):
    """Erste Zeile(n) der Wertetabelle: Zeile 1 = das Teil selbst mit Artikel-Endung -1, weitere mit -2 …"""
    out = []
    for i in range(n):
        z = dict(b["werte"])
        art = str(z.get(ARTIKEL) or "").strip()
        z[ARTIKEL] = f"{art}-{i + 1}" if art else ""
        out.append(z)
    return out


def bezeichnung_vorschlag(bez, werte, art=ROHR):
    """Bezeichnung mit dem Maß der Zeile, z. B. 'Sprosse L=850' (vorhandenes L=… wird ersetzt)."""
    bez = re.sub(r"\s*L=\S+(\s*×\s*\S+)?", "", str(bez or "")).strip()
    lg, br = _text(werte.get(LAENGE)), _text(werte.get(BREITE))
    mass = (f"L={lg}" + (f" × {br}" if br and art == BLECH else "")) if lg else ""
    return (bez + " " + mass).strip()


def zeilen_aus_text(text, spalten):
    """Zeilen aus der Zwischenablage (Excel: Tabulator, sonst Semikolon) in der Reihenfolge spalten (Namen). Eine
    Kopfzeile wird erkannt, wenn ihre Zahlen-Spalten keine Zahlen sind. Ergebnis: [dict]."""
    zeilen = [z for z in str(text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n") if z.strip()]
    out = []
    for nr, z in enumerate(zeilen):
        teile = z.split("\t") if "\t" in z else z.split(";") if ";" in z else [z]
        teile = [t.strip() for t in teile]
        werte = dict(zip(spalten, teile))
        if nr == 0 and any(s in werte and werte[s] and _z(werte[s]) is None for s in spalten
                           if s in ZAHLEN or reihe_index(s) is not None):
            continue                    # Kopfzeile
        for s in list(werte):
            if s in ZAHLEN or reihe_index(s) is not None:
                v = _z(werte[s])
                werte[s] = (_mm(v) if s != STUECK and reihe_index(s) is None else int(v)) if v is not None else None
        out.append(werte)
        if len(out) >= MAX_ZEILEN:
            break
    return out


def zeile_pruefen(b, werte, profile=None, werkstoffe=None):
    """Fehlertexte einer Tabellenzeile (Eingaben, ohne zu rechnen)."""
    fehler = []
    for s in ZAHLEN:
        if s in werte and werte[s] not in (None, "") and (_z(werte[s]) is None or _z(werte[s]) <= 0):
            fehler.append(f"{TITEL[s]} größer 0 eintragen")
    if not str(werte.get(ARTIKEL) or "").strip() and not str(werte.get(BEZEICHNUNG) or "").strip():
        fehler.append("Artikel oder Bezeichnung eintragen")
    if profile is not None and b["art"] == ROHR and werte.get(PROFIL) and werte[PROFIL] not in profile:
        fehler.append(f"Profil {werte[PROFIL]} fehlt in den Stammdaten")
    if werkstoffe is not None and werte.get(WERKSTOFF) and werte[WERKSTOFF] not in werkstoffe:
        fehler.append(f"Werkstoff {werte[WERKSTOFF]} fehlt in den Stammdaten")
    e = b["eingaben"]
    if b["art"] == ROHR:
        _, f = rohr_eingaben(e, b["werte"].get(LAENGE), werte)
    else:
        _, f = blech_eingaben(e, werte)
    return fehler + f


def doppelte_artikel(zeilen):
    """Artikelnummern, die in der Tabelle mehrfach vorkommen."""
    gesehen, doppelt = set(), []
    for z in zeilen:
        a = str(z.get(ARTIKEL) or "").strip().casefold()
        if a and a in gesehen and a not in doppelt:
            doppelt.append(a)
        gesehen.add(a)
    return doppelt


# ------------------------------------------------------------------ Vorlage
def vorlage_daten(variablen, zeilen):
    """'_familie' einer Positionsvorlage: gewählte Variablen und Zeilen."""
    return {VORLAGE_SCHLUESSEL: dict(variablen=list(variablen), zeilen=[dict(z) for z in zeilen])}


def aus_vorlage(vorlage):
    """(variablen, zeilen) einer Familien-Vorlage oder None (normale Positionsvorlage)."""
    try:
        d = json.loads((vorlage or {}).get("daten") or "")
    except (TypeError, ValueError):
        return None
    f = d.get(VORLAGE_SCHLUESSEL) if isinstance(d, dict) else None
    if not isinstance(f, dict) or not f.get("zeilen"):
        return None
    return list(f.get("variablen") or ()), [dict(z) for z in f["zeilen"] if isinstance(z, dict)]
