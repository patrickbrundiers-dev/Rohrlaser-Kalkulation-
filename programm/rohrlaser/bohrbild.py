"""Bohrbild einer Position: Gewinde-Vorschläge, Senkungen und Fließlochbohrungen (Flowdrill) aus dem STEP-Import,
je Zeile im Dialog 'Bohrungen prüfen' bestätigt oder abgelehnt (positionen.bohrbild, JSON-Liste).

Zeile: {art, d, anzahl, status, …}; status offen / bestätigt / abgelehnt.
- art "Bohrung": Kernloch Ø d passt zu einem Gewinde (gewinde = 'M6'). Bestätigt = Gewinde wird geschnitten
  (Spalte Gewinde geprüft), abgelehnt = nur Bohrung.
- art "Senkung": Bohrung Ø d (der Laser schneidet sie, steht schon im Schneidweg), Senk-Ø D ist Nacharbeit.
  gravur = True: der Senk-Ø wird zusätzlich graviert (π × D je Senkung).
- art "Fließloch": Fließlochbohrung mit Kragen, Kernloch Ø d; der Laser schneidet nur eine Markierung, je nach laser
  ein Loch Ø 0,5 mm (Schneidweg, Einstich, Kontur klein) oder eine Gravur Ø 0,5 mm. gewinde = Vorschlag fürs
  Gewindeformen (Kernloch nach FLIESSLOCH_KERN). Abgelehnt = normale Bohrung Ø d, die der Laser schneidet.
- art "Bohren": Bohrung Ø d kleiner als 0,7 × Wandstärke (rechnen.KONTUR_MIN_WAND), die der Laser kaum sauber
  schneidet. Offen und abgelehnt schneidet der Laser sie wie gemessen; bestätigt markiert er nur (Gravur oder Loch
  Ø 0,5 wie beim Flowdrill), danach wird aufgebohrt. 3. Option laser = SCHNEIDEN (Patrick 27.10.2026): der Laser
  schneidet den Ø trotzdem, ohne anschließendes Bohren (Schneidweg wie gemessen, keine Zusatzarbeit, keine Warnung).
  Vorgabe der Wahl: Einstellung bohren_laser.

Arbeitsschritt als Zusatzarbeit (ZUSATZ_ARBEIT): bestätigte Senkungen, Flowdrill und Bohren tragen beim Übernehmen
die Zusatzarbeiten Senken, Flowdrill bzw. Bohren mit der Anzahl je Teil in die Position ein (quelle = QUELLE);
offene und abgelehnte Zeilen nichts. Von Hand eingetragene Zusatzarbeiten gleichen Namens bekommen nur die Anzahl.
Preise (Patrick 22.10.2026: nur € je Stück, keine Zeiten): je Zeile preis = € je Stück der Arbeit und gewinde_preis =
€ je Gewinde; leer = Preis aus den Einstellungen (Zusatzarbeiten bzw. Gewinde), sonst gilt er nur für diese Position.

Was eine Zeile am Schneidweg, an Einstichen, Gravur und Konturliste ändert (zusatz), steht beim Speichern in der
Position; geändert wird um den Unterschied zwischen alter und neuer Wahl (anwenden).

Ausführung nachträglich ändern (Patrick 03.11.2026, Freigabe „alle Empfehlungen“): je Zeile aus = AUSFUEHRUNGEN
(Gewinde schneiden, Flowdrill + Gewinde formen, Einnietmutter, Senkung, Bohren, nur lasern), unabhängig von der
gemessenen Art. Die Art bleibt, was im STEP steht (Grundlage des gemessenen Schneidwegs, _basis); die Ausführung legt
fest, was der Laser schneidet (d_laser = Ø nach Gewindegröße, z. B. M8: Kernloch 6,8 / Einnietmutter 11,0 /
Durchgang 9,0) oder markiert, und welche Arbeit als Zusatzarbeit (€/Stück) dazukommt. Die STEP-Kontur im Export bleibt
unverändert, nur die Kalkulation folgt der Ausführung (Hinweis „weicht von STEP ab“, abweichend). Ohne aus gilt die
Ausführung nach Art und Wahl wie bisher (ausfuehrung), bitgleich zu den Bohrbildern vor 0.9.238. vorschlaege(): je
Bohrung die beste Ausführung (★) und Alternativen mit Grund nach Gewindegröße, Wandstärke und Werkstoff; Grenzen in
den Einstellungen (GRENZEN).
"""
import json
import math

from . import rechnen
from .stammdaten import (BOHREN_LASER, BOHREN_SCHNEIDEN, FLIESSLOCH_LASER, ZUSATZ_BOHREN, ZUSATZ_EINNIETMUTTERN,
                         ZUSATZ_FLOWDRILL, ZUSATZ_SENKEN)

OFFEN, BESTAETIGT, ABGELEHNT = "offen", "bestätigt", "abgelehnt"
LASER = FLIESSLOCH_LASER
GRAVUR, LOCH = LASER
SCHNEIDEN = BOHREN_SCHNEIDEN        # Bohren: Ø trotzdem schneiden, kein Bohren
LASER_BOHREN = BOHREN_LASER         # Auswahl für Zeilen 'Bohren' (Gravur, Loch Ø 0,5, Ø schneiden)
MARKE_D = rechnen.MARKIERLOCH          # Ø der Markierung für Fließlochbohrungen [mm]
# Kernloch fürs Gewindeformen nach Fließlochbohrung (Richtwerte Flowdrill), nicht DIN 336
FLIESSLOCH_KERN = (("M5", 4.5), ("M6", 5.4), ("M8", 7.3), ("M10", 9.2), ("M12", 10.9), ("M16", 14.8))
BOHREN = "Bohren"
ZUSATZ_ARBEIT = {"Senkung": ZUSATZ_SENKEN, "Fließloch": ZUSATZ_FLOWDRILL, BOHREN: ZUSATZ_BOHREN}
QUELLE = "Bohrungen prüfen"         # Zusatzarbeit der Position stammt aus dem Bohrbild

# Ausführung einer Bohrung (Patrick 03.11.2026): was am Ende aus ihr wird
GEWINDE_SCHNEIDEN = "Gewinde schneiden"
FLOWDRILL = "Flowdrill + Gewinde formen"
EINNIET = "Einnietmutter"
SENKEN = "Senkung"
AUFBOHREN = "Bohren (markieren, aufbohren)"
NUR_LASER = "nur lasern (Ø schneiden)"
AUSFUEHRUNGEN = (GEWINDE_SCHNEIDEN, FLOWDRILL, EINNIET, SENKEN, AUFBOHREN, NUR_LASER)
MIT_GROESSE = (GEWINDE_SCHNEIDEN, FLOWDRILL, EINNIET)       # brauchen eine Gewindegröße (M6, M8 …)
KURZ = {GEWINDE_SCHNEIDEN: "Gewinde", FLOWDRILL: "Flowdrill", EINNIET: "Einnietmutter", SENKEN: "Senkung",
        AUFBOHREN: "Bohren", NUR_LASER: "nur lasern"}
# Zusatzarbeit (€/Stück) je Ausführung; Gewinde schneiden/formen rechnet über die Gewinde-Stammdaten
ZUSATZ_AUS = {FLOWDRILL: ZUSATZ_FLOWDRILL, SENKEN: ZUSATZ_SENKEN, AUFBOHREN: ZUSATZ_BOHREN, EINNIET: ZUSATZ_EINNIETMUTTERN}
# Richtwerte je Gewindegröße [mm]: Steigung (ISO 261), Durchgangsloch mittel (ISO 273), Senk-Ø für Senkschrauben
# (ISO 15065), Bohrung für Einnietmuttern mit Rundschaft und Klemmbereich (übliche Herstellerwerte)
STEIGUNG = {"M3": 0.5, "M4": 0.7, "M5": 0.8, "M6": 1.0, "M8": 1.25, "M10": 1.5, "M12": 1.75, "M14": 2.0, "M16": 2.0,
            "M20": 2.5, "M24": 3.0}
DURCHGANG = {"M3": 3.4, "M4": 4.5, "M5": 5.5, "M6": 6.6, "M8": 9.0, "M10": 11.0, "M12": 13.5, "M14": 15.5,
             "M16": 17.5, "M20": 22.0, "M24": 26.0}
SENK_D = {"M3": 6.5, "M4": 8.6, "M5": 10.4, "M6": 12.4, "M8": 16.4, "M10": 20.4, "M12": 24.4, "M16": 32.4,
          "M20": 40.4}
NIET_LOCH = {"M3": 5.0, "M4": 6.0, "M5": 7.0, "M6": 9.0, "M8": 11.0, "M10": 13.0, "M12": 16.0}
NIET_KLEMM = {"M3": (0.3, 3.0), "M4": (0.5, 3.0), "M5": (0.5, 3.5), "M6": (0.5, 4.0), "M8": (0.5, 5.5),
              "M10": (1.0, 6.0), "M12": (1.0, 6.0)}
# Grenzen der Vorschläge (Einstellungen › Bohrungen, änderbar): Gewinde schneiden trägt ab so vielen Gängen in der
# Wand (Alu × 1,5), Flowdrill ab Wand min bis Wand ≤ Faktor × Nenn-Ø
GRENZEN = dict(bohr_gewinde_gaenge=3.0, bohr_flowdrill_min=1.0, bohr_flowdrill_faktor=0.5)


def _paare(text, getrennt="/"):
    """'6.6/12.4:2|8:1' -> [((6.6, 12.4), 2), ((8.0,), 1)]"""
    out = []
    for teil in str(text or "").split("|"):
        if ":" not in teil:
            continue
        a, n = teil.rsplit(":", 1)
        try:
            out.append((tuple(float(x) for x in a.split(getrennt)), int(float(n))))
        except ValueError:
            continue
    return out


TOL_KERNLOCH = 0.05     # mm: Bohrung gilt als Kernloch eines Gewindes (Einstellung step_tol_kernloch)


# Kern-Ø D1 des Muttergewindes (ISO 965): so modellieren viele CAD-Systeme (Inventor, Creo, Fusion) die Gewindebohrung
# statt mit dem Kernloch nach DIN 336 (M8: 6,647 statt 6,8, Patrick 28.10.2026 „Gewinde-Erkennung verbessern“)
KERN_D1 = {"M3": 2.459, "M4": 3.242, "M5": 4.134, "M6": 4.917, "M8": 6.647, "M10": 8.376, "M12": 10.106,
           "M14": 11.835, "M16": 13.835, "M20": 17.294, "M24": 20.752}


def _gewinde(d, tabelle, tol=None):
    """Gewinde zur Bohrung Ø d: Kernloch der Tabelle (Stammdaten Gewinde) ± tol, sonst Kern-Ø D1 eines Gewindes der
    Tabelle (CAD-Modell mit dem Kern-Ø); None, wenn nichts passt."""
    tol = TOL_KERNLOCH if tol is None else tol
    g = next((g for g, kern in tabelle if abs(d - kern) <= tol), None)
    if g is None and tabelle is not FLIESSLOCH_KERN:
        g = next((g for g, _ in tabelle if g in KERN_D1 and abs(d - KERN_D1[g]) <= tol), None)
    return g


def zu_klein(d, wand):
    """Bohrung Ø d kleiner als 0,7 × Wandstärke (nicht die Markierung Ø 0,5): Bohren vorschlagen."""
    return isinstance(wand, (int, float)) and wand > 0 and \
        MARKE_D < round(float(d or 0), 2) < round(rechnen.KONTUR_MIN_WAND * wand, 2)


def _bohren_laser(laser):
    return laser if laser in LASER_BOHREN else GRAVUR


def nur_schneiden(z):
    """Zeile 'Bohren', die der Laser trotzdem im vollen Ø schneidet (kein Bohren, keine Warnung)."""
    return z.get("art") == BOHREN and z.get("status") != OFFEN and wirkung(z) == NUR_LASER and \
        not (z.get("status") == ABGELEHNT and z.get("laser") != SCHNEIDEN)


def gelasert(liste):
    """Ø (auf 0,1 gerundet) der Bohren-Zeilen, die der Laser bewusst schneidet: abgelehnt, Ø schneiden oder eine
    andere Ausführung mit gelasertem Loch."""
    return {round(float(z.get("d") or 0), 1) for z in liste
            if z.get("art") == BOHREN and z.get("status") != OFFEN and _ziel(z)[0] is not None}


# ------------------------------------------------------------------ Ausführung (Patrick 03.11.2026)
def _natur(z):
    """Ausführung nach Art und Wahl ohne eigene Ausführung (wie vor 0.9.238)."""
    art = z.get("art")
    if art == "Bohrung":
        return GEWINDE_SCHNEIDEN if z.get("gewinde") else NUR_LASER
    if art == "Senkung":
        return SENKEN
    if art == "Fließloch":
        return FLOWDRILL
    if art == BOHREN:
        return NUR_LASER if z.get("laser") == SCHNEIDEN else AUFBOHREN
    return NUR_LASER


def ausfuehrung(z):
    """Gewählte (bzw. nach der Art vorgegebene) Ausführung der Zeile, wie sie die Auswahl zeigt."""
    return z["aus"] if z.get("aus") in AUSFUEHRUNGEN else _natur(z)


def wirkung(z):
    """Ausführung, mit der gerechnet wird: abgelehnt = nur lasern (wie gemessen), offenes 'Bohren' ohne eigene Wahl
    schneidet der Laser wie gemessen (wie bisher)."""
    if z.get("status") == ABGELEHNT:
        return NUR_LASER
    if z.get("status", OFFEN) == OFFEN and z.get("art") == BOHREN and not z.get("aus"):
        return NUR_LASER
    return ausfuehrung(z)


def abweichend(z):
    """True, wenn die gewählte Ausführung nicht der Art im STEP entspricht: die Kalkulation weicht von der STEP-Kontur
    ab (die Kontur im Export bleibt, Freigabe 03.11.2026 1a)."""
    return z.get("status") != ABGELEHNT and z.get("aus") in AUSFUEHRUNGEN and z["aus"] != _natur(z) and \
        not (z.get("art") == BOHREN and z["aus"] in (NUR_LASER, AUFBOHREN))


def _basis(z):
    """Ø, den der gemessene Schneidweg enthält (Fließlochbohrungen misst der STEP-Import ohne Schnitt), oder None."""
    return None if z.get("art") == "Fließloch" else float(z.get("d") or 0)


def _ziel(z):
    """(Ø, den der Laser schneidet, oder None; Markierung GRAVUR/LOCH oder None) nach der Wirkung."""
    w = wirkung(z)
    if w in (FLOWDRILL, AUFBOHREN):
        return None, (LOCH if z.get("laser") == LOCH else GRAVUR)
    d = z.get("d") if w == NUR_LASER else (z.get("d_laser") or z.get("d"))
    return float(d or 0), None


def _gr_zahl(g):
    try:
        return float(str(g).upper().lstrip("M").replace(",", "."))
    except ValueError:
        return None


def groesse(z, gewinde=()):
    """Gewindegröße der Zeile (Spalte Gewinde), sonst aus dem Ø geschätzt (Kernloch, Flowdrill-Kernloch,
    Durchgangsloch, Bohrung für Einnietmutter) oder None."""
    if z.get("gewinde"):
        return z["gewinde"]
    d = float(z.get("d") or 0)
    if d <= 0:
        return None
    if z.get("art") == "Fließloch":
        return _gewinde(d, FLIESSLOCH_KERN, 0.15)
    if z.get("art") != "Senkung":
        g = _gewinde(d, [(n, k) for n, k in gewinde if isinstance(k, (int, float))] or list(step_kernloch()))
        if g:
            return g
    for tab, tol in ((DURCHGANG, 0.3), (NIET_LOCH, 0.2)):
        g = next((n for n, w in tab.items() if abs(w - d) <= tol), None)
        if g:
            return g
    return None


def laser_d(z, aus=None, gewinde=()):
    """Ø, den der Laser für die Ausführung aus schneidet (None = nur markieren): Gewinde = Kernloch der Stammdaten
    (gemessenes Kernloch bleibt, wenn es zum Gewinde passt), Einnietmutter = NIET_LOCH, Senkung = Durchgangsloch
    (gemessene Senkung bleibt), nur lasern = gemessener Ø."""
    aus = aus or ausfuehrung(z)
    d = float(z.get("d") or 0)
    g = z.get("gewinde") if aus in MIT_GROESSE else groesse(z, gewinde)
    if aus in (FLOWDRILL, AUFBOHREN):
        return None
    if aus == GEWINDE_SCHNEIDEN and g:
        tab = [(n, k) for n, k in gewinde if isinstance(k, (int, float))] or list(step_kernloch())
        if z.get("art") == "Bohrung" and _gewinde(d, tab) == g:
            return d                            # gemessenes Kernloch passt zum Gewinde
        kern = dict(tab).get(g)
        return round(float(kern), 2) if isinstance(kern, (int, float)) else d
    if aus == EINNIET and g in NIET_LOCH:
        return NIET_LOCH[g]
    if aus == SENKEN and z.get("art") != "Senkung" and g in DURCHGANG:
        return DURCHGANG[g]
    return d


def step_kernloch():
    """Kernlöcher nach DIN 336, wenn die Stammdaten Gewinde fehlen (wie der STEP-Import)."""
    return (("M3", 2.5), ("M4", 3.3), ("M5", 4.2), ("M6", 5.0), ("M8", 6.8), ("M10", 8.5), ("M12", 10.2),
            ("M14", 12.0), ("M16", 14.0), ("M20", 17.5), ("M24", 21.0))


def ausfuehrung_setzen(z, aus, gewinde=(), laser=None, groesse_=None):
    """Zeile z mit neuer Ausführung aus (neues dict): Gewindegröße (groesse_ oder geschätzt), Ø am Laser, Senk-Ø und
    Markierung nach Vorgabe laser. Die Art (Messung) bleibt."""
    z = dict(z, aus=aus)
    if aus in MIT_GROESSE:
        g = groesse_ or groesse(z, gewinde)
        if g:
            z["gewinde"] = g
    elif groesse_:
        z["gewinde"] = groesse_
    if aus in (FLOWDRILL, AUFBOHREN) and z.get("laser") not in LASER:
        z["laser"] = laser if laser in LASER else GRAVUR
    if aus == NUR_LASER and z.get("art") == BOHREN:
        z["laser"] = SCHNEIDEN
    if aus == SENKEN and not z.get("D"):
        g = groesse(z, gewinde)
        z["D"] = SENK_D.get(g) or round(2 * float(z.get("d") or 0), 1)
        z.setdefault("gravur", False)
    dl = laser_d(z, aus, gewinde)
    if dl is None or abs(dl - float(z.get("d") or 0)) < 0.005:
        z.pop("d_laser", None)
    else:
        z["d_laser"] = dl
    return z


def grenzen_aus(einst):
    """Grenzen der Vorschläge aus den Einstellungen (dict oder Funktion name -> Wert); fehlend = GRENZEN."""
    out = dict(GRENZEN)
    for k in GRENZEN:
        try:
            v = einst(k) if callable(einst) else (einst or {}).get(k)
        except Exception:  # noqa: BLE001 – Einstellung fehlt (ältere Datenbank)
            v = None
        if isinstance(v, (int, float)) and v > 0:
            out[k] = float(v)
    return out


def ist_alu(werkstoff):
    w = str(werkstoff or "").upper().replace(" ", "")
    return "ALU" in w or w.startswith(("ALMG", "ALSI", "ENAW", "AW-", "ALZN", "ALCU", "3.3", "3.2"))


def vorschlaege(z, wand=None, werkstoff=None, gewinde=(), grenzen=None):
    """Je Ausführung: dict(aus, rang, grund) – rang 0 = ★ beste (eine), 1 = passt auch, 2 = nicht empfohlen; sortiert
    nach Rang. Nach Gewindegröße (Spalte Gewinde oder aus dem Ø), Wandstärke und Werkstoff (Alu: mehr Gänge):
    Gewinde schneiden trägt ab bohr_gewinde_gaenge Gängen in der Wand, Flowdrill von bohr_flowdrill_min bis
    bohr_flowdrill_faktor × Nenn-Ø, Einnietmutter im Klemmbereich (NIET_KLEMM). ★ = die Ausführung nach der Art im
    STEP, wenn sie passt, sonst die erste passende aus Gewinde, Flowdrill, Einnietmutter, nur lasern."""
    gr = dict(GRENZEN, **(grenzen or {}))
    g = groesse(z, gewinde)
    d = float(z.get("d") or 0)
    s = float(wand) if isinstance(wand, (int, float)) and wand > 0 else None
    alu = ist_alu(werkstoff)
    out = {}
    if g:
        st, nenn = STEIGUNG.get(g), _gr_zahl(g)
        min_g = gr["bohr_gewinde_gaenge"] * (1.5 if alu else 1)
        if s and st:
            gaenge = s / st
            ok = gaenge >= min_g - 1e-9
            out[GEWINDE_SCHNEIDEN] = (ok, f"Wand {dez(s)} mm = {dez(round(gaenge, 1))} Gänge {g}" + (
                " – trägt" if ok else f" – zu wenig (ab {dez(min_g)} Gängen{' in Alu' if alu else ''})"))
        else:
            out[GEWINDE_SCHNEIDEN] = (True, f"Kernloch lasern, Gewinde {g} schneiden")
        fmax = gr["bohr_flowdrill_faktor"] * nenn if nenn else None
        if s and fmax:
            ok = gr["bohr_flowdrill_min"] - 1e-9 <= s <= fmax + 1e-9
            out[FLOWDRILL] = (ok, "Laser markiert, Kragen gibt ca. 3 × Wand Gewindelänge" if ok else
                              f"Wand {dez(s)} mm " + (f"zu dünn (ab {dez(gr['bohr_flowdrill_min'])} mm)"
                                                      if s < gr["bohr_flowdrill_min"] else
                                                      f"zu dick (bis {dez(round(fmax, 1))} mm)"))
        else:
            out[FLOWDRILL] = (True, "Laser markiert, Gewinde wird geformt")
        klemm = NIET_KLEMM.get(g)
        if not klemm:
            out[EINNIET] = (False, f"keine Einnietmutter {g} in der Tabelle")
        else:
            ok = s is None or klemm[0] - 1e-9 <= s <= klemm[1] + 1e-9
            out[EINNIET] = (ok, f"Loch Ø{dez(NIET_LOCH[g])}, Klemmbereich {dez(klemm[0])}–{dez(klemm[1])} mm"
                            + ("" if ok else f" – Wand {dez(s)} mm passt nicht"))
        senk = SENK_D.get(g)
        out[SENKEN] = (z.get("art") == "Senkung" or bool(senk),
                       f"für Senkschraube {g}: Ø{dez(DURCHGANG.get(g, d))} / Senk-Ø {dez(z.get('D') or senk)}"
                       if z.get("art") != "Senkung" else f"Senk-Ø {dez(z.get('D'))} wie im STEP")
    else:
        for aus in MIT_GROESSE:
            out[aus] = (False, "erst die Gewindegröße wählen")
        if z.get("art") == "Senkung":
            out[SENKEN] = (True, f"Senk-Ø {dez(z.get('D'))} wie im STEP")
    klein = zu_klein(d, s)
    out[NUR_LASER] = (not klein, f"Ø{dez(d)} schneiden, ohne Gewinde" + (
        " – kleiner als 0,7 × Wand, schneidet unsauber" if klein else ""))
    if klein:
        out[AUFBOHREN] = (True, f"Ø{dez(d)} kleiner als 0,7 × Wand: markieren und aufbohren")
    natur = _natur(z)
    reihe = [natur] + [a for a in ((SENKEN,) if z.get("art") == "Senkung" else ()) +
                       (GEWINDE_SCHNEIDEN, FLOWDRILL, EINNIET, AUFBOHREN, NUR_LASER) if a != natur]
    stern = next((a for a in reihe if a in out and out[a][0]), None)
    liste = [dict(aus=a, rang=0 if a == stern else 1 if ok else 2, grund=grund)
             for a, (ok, grund) in out.items()]
    return sorted(liste, key=lambda v: (v["rang"], AUSFUEHRUNGEN.index(v["aus"])))


def vorschlag_bester(z, wand=None, werkstoff=None, gewinde=(), grenzen=None):
    v = vorschlaege(z, wand, werkstoff, gewinde, grenzen)
    return next((x for x in v if x["rang"] == 0), None)


def bohren_zeilen(bohrungen, wand, laser=GRAVUR, vorhanden=()):
    """Zeilen 'Bohren' für die Bohrungen [(Ø, Anzahl)] kleiner als 0,7 × Wandstärke, ohne die Ø in vorhanden;
    laser = Vorgabe (Gravur/Loch Ø 0,5 und aufbohren oder SCHNEIDEN)."""
    summe = {}
    for d, n in bohrungen:
        if zu_klein(d, wand) and round(d, 2) not in vorhanden:
            summe[round(d, 2)] = summe.get(round(d, 2), 0) + int(n)
    return [dict(art=BOHREN, d=d, anzahl=n, laser=_bohren_laser(laser), status=OFFEN)
            for d, n in sorted(summe.items()) if n > 0]


def aus_messung(m, gewinde, laser=GRAVUR, wand=None, bohren_laser=None):
    """Zeilen aus den Messwerten eines Teils (Spalten bohrungen, senkungen, fliessloecher); gewinde = [(Gewinde,
    Kernloch)] der Stammdaten. Alle Zeilen offen; laser = Vorgabe für Fließlochbohrungen und (ohne bohren_laser)
    Bohren; mit wand (Wandstärke) zusätzlich Bohren für Bohrungen kleiner als 0,7 × Wand."""
    out = []
    bohrungen = [(d, n) for (d,), n in _paare(m.get("bohrungen"))]
    for d, n in bohrungen:
        g = _gewinde(d, gewinde)
        if g:
            out.append(dict(art="Bohrung", d=d, anzahl=n, gewinde=g, status=OFFEN))
    for (d, dd), n in _paare(m.get("senkungen")):
        out.append(dict(art="Senkung", d=d, D=dd, anzahl=n, gravur=False, status=OFFEN))
    for (d,), n in _paare(m.get("fliessloecher")):
        out.append(dict(art="Fließloch", d=d, anzahl=n, gewinde=_gewinde(d, FLIESSLOCH_KERN, 0.15),
                        laser=laser if laser in LASER else GRAVUR, status=OFFEN))
    return out + bohren_zeilen(bohrungen, wand, bohren_laser or laser)


def aus_rechner(erg, alt, gewinde, wand=None, laser=GRAVUR, bohren_laser=None):
    """Bohrbild nach dem Schneidweg-Rechner (Ergebnis schneidweg.rechnen): Gewinde der Bohrungen (Spalte Gewinde der
    Konturzeile, sonst Vorschlag nach dem Kernloch), Senkungen, Flowdrill und Bohren (< 0,7 × Wand) aus den
    Eingaben. Was im Rechner eingegeben ist, gilt als bestätigt (Patrick 23.10.2026); Zeilen gleicher Art und
    gleichen Ø aus dem bisherigen Bohrbild (alt, z. B. vom STEP-Import) behalten Prüfstatus und Wahl, ein im Rechner
    gewähltes Gewinde geht vor. Eigenschaft Ausführung der Konturzeile (Eingabe aus, alle Editoren) setzt die
    Ausführung der Zeile (ausfuehrung_setzen)."""
    bohr, senk, fluss = {}, {}, {}       # (Ø, Gewinde oder None, Gewinde von Hand?, Ausführung) -> Anzahl
    for s_ in erg.get("schritte", [])[2:]:
        e = s_.get("eingabe") or {}
        try:
            d = round(float(e.get("d")), 2)
        except (TypeError, ValueError):
            continue
        hand = "gewinde" in e
        aus = e.get("aus") if e.get("aus") in AUSFUEHRUNGEN else None
        if s_.get("art") == "Bohrung":
            schl = (d, (e.get("gewinde") or None) if hand else (_gewinde(d, gewinde) or e.get("groesse")), hand,
                    aus)
            bohr[schl] = bohr.get(schl, 0) + int(s_["anzahl"])
        elif s_.get("art") == "Flowdrill":
            schl = (d, (e.get("gewinde") or None) if hand else _gewinde(d, FLIESSLOCH_KERN, 0.15), hand, aus)
            fluss[schl] = fluss.get(schl, 0) + int(s_["anzahl"])
        elif s_.get("art") == "Senkung" and isinstance(e.get("D"), (int, float)):
            schl = (d, round(float(e["D"]), 2), e.get("groesse") or None, aus)
            senk[schl] = senk.get(schl, 0) + int(s_["anzahl"])
    laser = laser if laser in LASER else GRAVUR
    neu = [(dict(art="Bohrung", d=d, anzahl=n, gewinde=g, status=BESTAETIGT), hand, aus)
           for (d, g, hand, aus), n in sorted(bohr.items(), key=str) if g or aus]
    neu += [(dict(art="Senkung", d=d, D=dd, anzahl=n, gravur=False, status=BESTAETIGT,
                  **({"gewinde": g} if g else {})), False, aus)
            for (d, dd, g, aus), n in sorted(senk.items(), key=str)]
    neu += [(dict(art="Fließloch", d=d, anzahl=n, gewinde=g, laser=laser, status=BESTAETIGT), hand, aus)
            for (d, g, hand, aus), n in sorted(fluss.items(), key=str)]
    summe = {}
    for (d, _, _, aus), n in bohr.items():
        if not aus:
            summe[d] = summe.get(d, 0) + n
    neu += [(dict(z, status=BESTAETIGT), False, None)
            for z in bohren_zeilen(sorted(summe.items()), wand, bohren_laser or laser)]
    vorher = {(z.get("art"), round(float(z.get("d") or 0), 2)): z for z in alt or ()}
    out = []
    for z, hand, aus in neu:
        v = vorher.get((z["art"], z["d"]))
        if v:
            z.update({k: v[k] for k in ("status", "gewinde", "laser", "gravur", "preis", "gewinde_preis", "aus",
                                        "d_laser")
                      if k in v and not (k == "gewinde" and hand) and not (k in ("aus", "d_laser") and aus)})
        if aus:
            z = ausfuehrung_setzen(dict(z, status=BESTAETIGT), aus, gewinde, laser)
        out.append(z)
    return out


def bohrungen_lesen(text):
    """Spalte Bohrungen der Position ('4xØ5; 1xØ10; 2x Senkung Ø6,6/12,4') -> [(5.0, 4), (10.0, 1)], nur einfache
    Bohrungen."""
    out = []
    for teil in str(text or "").split(";"):
        n, _, d = teil.strip().partition("xØ")
        try:
            out.append((float(d.replace(",", ".")), int(n)))
        except ValueError:
            continue
    return out


def ergaenzen(liste, p, wand, laser=GRAVUR):
    """Bohrbild um Zeilen 'Bohren' ergänzen, die es noch nicht gibt (Importe vor 0.8.12, Schneidweg-Rechner,
    andere Wandstärke): aus der Spalte Bohrungen der Position."""
    da = {round(float(z.get("d") or 0), 2) for z in liste if z.get("art") == BOHREN}
    return list(liste) + bohren_zeilen(bohrungen_lesen(p.get("bohrungen")), wand, laser, da)


def aus_position(p, gewinde, wand=None, laser=GRAVUR):
    """Zeilen einer Position: gespeichertes Bohrbild, sonst aus der Spalte Gewinde-Vorschlag (ältere Importe und
    Schneidweg-Rechner); bereits eingetragenes Gewinde gilt als bestätigt. Mit wand ergänzt um Bohren (ergaenzen)."""
    liste = lesen(p.get("bohrbild"))
    if liste:
        return ergaenzen(liste, p, wand, laser)
    out = []
    kern = dict(gewinde)
    fertig = rechnen.gewinde_anzahl(p.get("gewinde"), [dict(gewinde=g) for g, _ in gewinde]) if p.get("gewinde") \
        else {}
    for teil in str(p.get("gewinde_vorschlag") or "").split(";"):
        n, _, g = teil.strip().partition("x")
        if g and n.strip().isdigit():
            out.append(dict(art="Bohrung", d=kern.get(g.strip()), anzahl=int(n), gewinde=g.strip(),
                            status=BESTAETIGT if fertig.get(g.strip()) else OFFEN))
    return ergaenzen(out, p, wand, laser)


def lesen(text):
    try:
        liste = json.loads(text) if text else []
    except (TypeError, ValueError):
        return []
    return [z for z in liste if isinstance(z, dict) and z.get("art")] if isinstance(liste, list) else []


def schreiben(liste):
    return json.dumps(liste, ensure_ascii=False, separators=(",", ":")) if liste else None


def zusatz(liste):
    """Was die Wahl am Schneidweg ändert: dict(schneidweg, einstiche, gravur [mm], konturen [(Hüllmaß, Länge)]
    zusätzlich, weg [(Hüllmaß, Länge)] aus der gemessenen Konturliste entfernt). Grundlage ist der gemessene Ø der
    Art (_basis), Ziel der Ø bzw. die Markierung der Ausführung (_ziel)."""
    out = dict(schneidweg=0.0, einstiche=0, gravur=0.0, konturen=[], weg=[])
    for z in liste:
        n = int(z.get("anzahl") or 0)
        w = wirkung(z)
        if w == SENKEN and z.get("gravur") and z.get("D"):
            out["gravur"] += n * math.pi * float(z["D"])
        basis = _basis(z)
        d, marke = _ziel(z)
        gleich = basis is not None and d is not None and abs(d - basis) < 0.005
        if basis is not None and not gleich:        # gemessene Bohrung fällt weg
            out["schneidweg"] -= n * math.pi * basis
            out["weg"] += [(basis, math.pi * basis)] * n
            out["einstiche"] -= n
        if d is not None and not gleich:            # anderer Ø am Laser
            out["schneidweg"] += n * math.pi * d
            out["konturen"] += [(d, math.pi * d)] * n
            out["einstiche"] += n
        if marke == LOCH:
            out["schneidweg"] += n * math.pi * MARKE_D
            out["konturen"] += [(MARKE_D, math.pi * MARKE_D)] * n
            out["einstiche"] += n
        elif marke == GRAVUR:
            out["gravur"] += n * math.pi * MARKE_D
    return out


def gewinde_text(liste):
    """Bestätigte Gewinde als Text der Spalte Gewinde geprüft ('4xM6; 2xM8'), sonst None."""
    summe = {}
    for z in liste:
        if _gewinde_zeile(z):
            summe[z["gewinde"]] = summe.get(z["gewinde"], 0) + int(z.get("anzahl") or 0)
    return "; ".join(f"{n}x{g}" for g, n in summe.items()) or None


def _gewinde_zeile(z):
    """Bestätigte Zeile, deren Gewinde gerechnet wird (geschnitten oder nach Flowdrill geformt)."""
    return z.get("status") == BESTAETIGT and bool(z.get("gewinde")) and wirkung(z) in (GEWINDE_SCHNEIDEN, FLOWDRILL)


def vorschlag_text(liste):
    """Alle Gewinde-Vorschläge (auch abgelehnte) als Text der Spalte Gewinde-Vorschlag; ohne Zeilen, die bewusst
    eine Ausführung ohne Gewinde haben (Einnietmutter, Senkung, nur lasern, Bohren)."""
    summe = {}
    for z in liste:
        if z.get("gewinde") and ausfuehrung(z) in (GEWINDE_SCHNEIDEN, FLOWDRILL):
            summe[z["gewinde"]] = summe.get(z["gewinde"], 0) + int(z.get("anzahl") or 0)
    return "; ".join(f"{n}x{g}" for g, n in summe.items()) or None


def arbeiten(liste):
    """Anzahl je Teil der Arbeitsschritte aus bestätigten Zeilen: {Zusatzarbeit: Anzahl} (Senken, Flowdrill, Bohren)."""
    out = {}
    for z in liste:
        name = ZUSATZ_AUS.get(wirkung(z))
        if name and z.get("status") == BESTAETIGT and int(z.get("anzahl") or 0) > 0:
            out[name] = out.get(name, 0) + int(z["anzahl"])
    return out


def arbeit_groessen(liste):
    """{Zusatzarbeit: '4× M8, 2× M6'} der bestätigten Einnietmuttern und Flowdrill mit Gewindegröße (Text im Angebot)."""
    summe = {}
    for z in liste:
        name = ZUSATZ_AUS.get(wirkung(z))
        if name in (ZUSATZ_EINNIETMUTTERN, ZUSATZ_FLOWDRILL) and z.get("status") == BESTAETIGT and z.get("gewinde"):
            d = summe.setdefault(name, {})
            d[z["gewinde"]] = d.get(z["gewinde"], 0) + int(z.get("anzahl") or 0)
    return {name: ", ".join(f"{n}× {g}" for g, n in d.items()) for name, d in summe.items()}


def arbeit_preise(liste):
    """{Zusatzarbeit: € je Stück} aus den bestätigten Zeilen mit eigenem Preis (letzter gilt)."""
    out = {}
    for z in liste:
        name = ZUSATZ_AUS.get(wirkung(z))
        if name and z.get("status") == BESTAETIGT and isinstance(z.get("preis"), (int, float)):
            out[name] = float(z["preis"])
    return out


def gewinde_preise(liste):
    """{Gewinde: € je Stück} der bestätigten Zeilen mit eigenem Gewindepreis; liste oder JSON-Text."""
    if isinstance(liste, str):
        liste = lesen(liste)
    return {z["gewinde"]: float(z["gewinde_preis"]) for z in liste
            if _gewinde_zeile(z) and isinstance(z.get("gewinde_preis"), (int, float))}


def arbeiten_text(liste):
    return ", ".join(f"{n}× {name}" for name, n in arbeiten(liste).items())


def zusatz_eintragen(p, liste, katalog, saetze=None):
    """Spalte Zusatzarbeiten (JSON) der Position mit den Arbeitsschritten des Bohrbilds: vorhandener Eintrag gleichen
    Namens bekommt die Anzahl als Menge, neuer Eintrag mit Preisstand der Stammdaten (katalog = Zeilen der
    Zusatzarbeiten); Einträge aus dem Bohrbild ohne bestätigte Zeile fallen weg. Ergebnis: (JSON oder None, Namen,
    die in den Stammdaten fehlen)."""
    soll, preise, groessen = arbeiten(liste), arbeit_preise(liste), arbeit_groessen(liste)
    kat = {z.get("name"): z for z in katalog or ()}
    out, fehlt = [], []
    for e in rechnen.zusatz_liste(p):
        name = e["name"]
        if name in soll:
            e = dict(e, menge=soll.pop(name), quelle=e.get("quelle") or QUELLE)
            if name in preise or e["quelle"] == QUELLE:
                e["preis"] = preise.get(name)
            if e["quelle"] == QUELLE and (name in groessen or e.get("text")):
                e["text"] = groessen.get(name)        # Größen im Angebotstext, z. B. „4× M8“
            out.append(e)
        elif e.get("quelle") != QUELLE:
            out.append(e)
    for name, n in soll.items():
        if name not in kat:
            fehlt.append(name)
            continue
        out.append(dict(name=name, menge=n, preis=preise.get(name), text=groessen.get(name), quelle=QUELLE,
                        stand=rechnen.zusatz_stand(kat[name], saetze)))
    return (json.dumps(out, ensure_ascii=False) if out else None), fehlt


def offen(liste):
    return sum(1 for z in liste if z.get("status", OFFEN) == OFFEN)


def dez(x):
    return f"{float(x):g}".replace(".", ",") if x not in (None, "") else ""


def text(liste):
    """Kurztext für die Spalte Bohrungen, z. B. '2x Senkung Ø6,6/12,4; 2x Flowdrill Ø7,3 (M8)'."""
    out = []
    for z in liste:
        if abweichend(z):
            out.append(aus_text(z) + " (weicht von STEP ab)")
        elif z["art"] == "Senkung":
            out.append(f"{z['anzahl']}x Senkung Ø{dez(z['d'])}/{dez(z.get('D'))}")
        elif z["art"] == "Fließloch":
            out.append(f"{z['anzahl']}x Flowdrill Ø{dez(z['d'])}"
                       + (f" ({z['gewinde']})" if z.get("gewinde") else ""))
        elif nur_schneiden(z):
            out.append(f"{z['anzahl']}x Ø{dez(z['d'])} geschnitten (ohne Bohren)")
        elif z["art"] == BOHREN:
            out.append(f"{z['anzahl']}x Bohren Ø{dez(z['d'])}")
    return "; ".join(out)


def aus_text(z):
    """'4x Flowdrill M8 statt Gewinde', '2x Einnietmutter M8 Ø11 statt Gewinde'."""
    aus = ausfuehrung(z)
    teile = [f"{z.get('anzahl')}x {KURZ[aus]}"]
    if aus in MIT_GROESSE and z.get("gewinde"):
        teile.append(z["gewinde"])
    d, _ = _ziel(dict(z, status=BESTAETIGT))
    if d is not None and aus != GEWINDE_SCHNEIDEN:
        teile.append(f"Ø{dez(d)}")
    if aus == SENKEN and z.get("D"):
        teile[-1] += f"/{dez(z['D'])}"
    return " ".join(teile) + f" statt {KURZ[_natur(z)]}"


def step_hinweis(liste):
    """Zeilen, deren Ausführung von der STEP-Kontur abweicht, als Hinweis oder ''."""
    t = "; ".join(aus_text(z) for z in liste if abweichend(z))
    return f"Weicht von STEP ab (Kontur im Export bleibt): {t}" if t else ""


def _ohne(liste, weg, tol=0.06, gtol=0.006):
    """Konturliste ohne die Einträge in weg (je Eintrag ein Vorkommen, gerundet wie im Text; tol/gtol = Abweichung
    von Länge und Hüllmaß, gemessene Bohrungen weichen von π × d etwas ab)."""
    rest = list(liste)
    for g, lg in weg:
        for i, (a, g2, l2) in enumerate(rest):
            if not a and abs(round(g2, 2) - round(g, 2)) < gtol and abs(l2 - round(lg, 1)) < tol:
                del rest[i]
                break
    return rest


def hand_gewinde(p, liste):
    """Teile von 'Gewinde geprüft', die zu keiner Zeile des Bohrbilds gehören (von Hand eingetragen), als Text."""
    namen = {z.get("gewinde") for z in liste if z.get("gewinde")}
    return "; ".join(t.strip() for t in str(p.get("gewinde") or "").split(";")
                     if t.strip() and t.strip().upper().partition("X")[2].strip() not in {n.upper() for n in namen})


def anwenden(p, neu, hand=None, katalog=None, saetze=None):
    """Feldänderungen der Position für das neue Bohrbild: Schneidweg, Einstiche, Innenkonturen, Gravur, Konturliste
    und Konturklassen um den Unterschied alt → neu, dazu Gewinde geprüft (bestätigte Gewinde + hand, None = die von
    Hand eingetragenen bleiben), Gewinde-Vorschlag und bohrbild. Mit katalog (Zeilen der Zusatzarbeiten) auch die
    Zusatzarbeiten Senken, Flowdrill, Bohren (zusatz_eintragen); fehlende Namen unter '_fehlt' (nicht speichern)."""
    alt_z, neu_z = zusatz(lesen(p.get("bohrbild"))), zusatz(neu)
    out = {}
    d_weg = neu_z["schneidweg"] - alt_z["schneidweg"]
    if abs(d_weg) > 1e-9:
        out["schneidweg"] = round(max(0.0, rechnen._n(p.get("schneidweg")) + d_weg), 1)
        out["innen"] = round(max(0.0, rechnen._n(p.get("innen")) + d_weg), 1)
    if neu_z["einstiche"] != alt_z["einstiche"]:
        out["einstiche"] = max(0, int(rechnen._n(p.get("einstiche"))) + neu_z["einstiche"] - alt_z["einstiche"])
    d_grav = neu_z["gravur"] - alt_z["gravur"]
    if abs(d_grav) > 1e-9:
        out["gravur"] = round(max(0.0, rechnen._n(p.get("gravur")) + d_grav), 1) or None
    if alt_z["konturen"] != neu_z["konturen"] or alt_z["weg"] != neu_z["weg"]:
        liste = _ohne(rechnen.konturen_lesen(p.get("konturen"), True), alt_z["konturen"])
        liste += [("", g, lg) for g, lg in alt_z["weg"]]
        liste = _ohne(liste, neu_z["weg"], tol=1.0, gtol=0.06)
        liste += [("", g, lg) for g, lg in neu_z["konturen"]]
        out["konturen"] = rechnen.konturen_text([(g, lg) for a, g, lg in liste if not a],
                                                [(a, g, lg) for a, g, lg in liste if a]) or None
        grenzen = rechnen.grenzen_lesen(p.get("kontur_grenzen"))
        if grenzen:
            out.update(rechnen.konturklassen([(g, lg) for _, g, lg in liste], grenzen))     # Enden mit (wie STEP)
    hand = hand_gewinde(p, neu) if hand is None else str(hand).strip()
    out["gewinde"] = "; ".join(filter(None, [gewinde_text(neu), hand])) or None
    out["gewinde_vorschlag"] = vorschlag_text(neu)
    t_alt, t_neu = text(lesen(p.get("bohrbild"))), text(neu)
    if t_alt != t_neu:          # Spalte Bohrungen: Text des Bohrbilds (STEP-Import) mit der neuen Ausführung
        b = str(p.get("bohrungen") or "")
        if t_alt and b.endswith(t_alt):
            b = b[:len(b) - len(t_alt)].rstrip("; ")
        if t_alt and b == t_alt:
            b = ""
        b = "; ".join(filter(None, [b, t_neu])) or None
        if b != (p.get("bohrungen") or None) and (t_alt and t_alt in str(p.get("bohrungen") or "")
                                                   or any(abweichend(z) for z in neu)):
            out["bohrungen"] = b
    out["bohrbild"] = schreiben(neu)
    if katalog is not None:
        zu, fehlt = zusatz_eintragen(p, neu, katalog, saetze)
        if zu != (p.get("zusatz") or None):
            out["zusatz"] = zu
        if fehlt:
            out["_fehlt"] = fehlt
    return out
