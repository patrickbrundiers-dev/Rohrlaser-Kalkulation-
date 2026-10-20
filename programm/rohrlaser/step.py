"""STEP-Import: Messung mit STEP-Import.exe (bzw. step_messung/step_messen.py) und Übernahme in das Angebot.

Die Messung läuft als eigener Prozess: OpenCascade bleibt aus dem Programm heraus, und ein Absturz bei
einer defekten Datei trifft nur die Messung. Die Übernahme der Messwerte: Profilabgleich ±0,15 mm,
Gewinde-Vorschlag, Konturklassen, Protokoll.
"""
import datetime
import importlib.util
import sys
from pathlib import Path

TOL_MASS = 0.15
KLEIN_BIS, MITTEL_BIS = 10.0, 50.0
KERNLOCH = [("M3", 2.5), ("M4", 3.3), ("M5", 4.2), ("M6", 5.0), ("M8", 6.8), ("M10", 8.5),
            ("M12", 10.2), ("M14", 12.0), ("M16", 14.0), ("M20", 17.5)]
PROTOKOLL = ["Zeitpunkt", "Datei", "Körper", "Profilform", "Abm. A [mm]", "Abm. B [mm]", "Wandstärke [mm]",
             "Querschnitt [mm²]", "Länge [mm]", "Schneidweg ohne Gravur [mm]", "Einstiche",
             "Anfangsschnitt gerade", "Anfangsschnitt [mm]", "Endschnitt gerade", "Endschnitt [mm]",
             "Innenkonturen [mm]", "Innenkonturen [Stk]", "Gravur [mm]", "Gravur [Stk]", "Bohrungen",
             "Gewinde-Vorschlag", "Kontur klein [Stk]", "Kontur klein [mm]", "Kontur mittel [Stk]",
             "Kontur mittel [mm]", "Kontur groß [Stk]", "Kontur groß [mm]", "Profil-ID", "Pos.", "Hinweise"]


def messprogramm(programmordner):
    """Befehl für die Messung (Liste für subprocess) oder None, wenn keine Messung verfügbar ist."""
    exe = Path(programmordner) / "STEP-Import" / "STEP-Import.exe"
    if exe.is_file():
        return [str(exe)]
    if not getattr(sys, "frozen", False):
        skript = Path(__file__).resolve().parents[1] / "step_messung" / "step_messen.py"
        if skript.is_file() and importlib.util.find_spec("OCP") is not None:
            return [sys.executable, str(skript)]
    return None


def step_dateien(pfade):
    """STEP-Dateien aus Dateien und Ordnern (Ordner samt Unterordnern), sortiert und ohne doppelte."""
    out = []
    for p in map(Path, pfade):
        kandidaten = sorted(x for x in p.rglob("*") if x.is_file()) if p.is_dir() else [p]
        out += [x for x in kandidaten if x.suffix.lower() in (".step", ".stp") and x not in out]
    return out


def lies_messwerte(pfad):
    """Textdatei der Messung (UTF-8, Tabulator, Kopfzeile) als Liste von dicts."""
    zeilen = Path(pfad).read_text(encoding="utf-8").splitlines()
    if not zeilen:
        return []
    kopf = zeilen[0].split("\t")
    return [dict(zip(kopf, z.split("\t") + [""] * (len(kopf) - len(z.split("\t"))))) for z in zeilen[1:] if z]


def lade_netze(messwerte, ordner):
    """Dreiecksnetze der Messung (Spalte 'netz' = JSON-Datei im Ordner) als komprimierte Bytes an die Messwerte
    hängen (Schlüssel '_netz'); fehlt die Datei (ältere STEP-Import.exe), bleibt das Teil ohne 3D-Ansicht."""
    import zlib
    for m in messwerte:
        datei = Path(ordner) / m["netz"] if m.get("netz") else None
        if datei and datei.is_file():
            m["_netz"] = zlib.compress(datei.read_bytes(), 6)
    return messwerte


def _z(m, name):
    try:
        return float(m.get(name) or 0)
    except ValueError:
        return 0.0


def _paare(text):
    out = []
    for teil in (text or "").split("|"):
        if ":" in teil:
            a, b = teil.split(":", 1)
            out.append((float(a), float(b)))
    return out


def _dez(x):
    return f"{x:g}".replace(".", ",")


def bohrungen_text(text):
    return "; ".join(f"{int(n)}xØ{_dez(d)}" for d, n in _paare(text))


def gewinde_vorschlag(text, gewinde):
    out = []
    for d, n in _paare(text):
        for g, kern in gewinde:
            if abs(d - kern) <= 0.05:
                out.append(f"{int(n)}x{g}")
                break
    return "; ".join(out)


def konturklassen(text, klein, mittel):
    """[(Anzahl, Länge) klein, mittel, groß] nach größtem Hüllmaß."""
    kl = [[0, 0.0], [0, 0.0], [0, 0.0]]
    for groesse, laenge in _paare(text):
        g = round(groesse, 2)   # Ø10 genau auf der Grenze zählt als klein
        c = 0 if g <= klein else 1 if g <= mittel else 2
        kl[c][0] += 1
        kl[c][1] += laenge
    return kl


def _wand(m):
    """Wand- bzw. Blechdicke eines gemessenen Teils (Flachstahl: Dicke = Abmessung B der Messung)."""
    return _z(m, "abm_b") if m.get("profilform") == "Flachstahl" else _z(m, "wandstaerke")


def finde_profil(m, profile):
    form, a, b, t = m.get("profilform"), _z(m, "abm_a"), _z(m, "abm_b"), _wand(m)
    for pid, p in profile.items():
        if p.get("form") != form or abs((p.get("wand") or 0) - t) > TOL_MASS:
            continue
        pa, pb = p.get("a") or 0, p.get("b") or 0
        if form in ("Rundrohr", "Quadratrohr"):
            if abs(pa - a) <= TOL_MASS:
                return pid
        elif form in ("Rechteckrohr", "L-Profil"):
            gr, kl = max(pa, pb), min(pa, pb)
            if abs(gr - a) <= TOL_MASS and abs(kl - b) <= TOL_MASS:
                return pid
        elif form in ("U-Profil", "C-Profil"):
            if abs(pa - a) <= TOL_MASS and abs(pb - b) <= TOL_MASS:
                return pid
        elif form == "Flachstahl":
            if abs(pa - a) <= TOL_MASS:
                return pid
    return None


def profil_vorschlag(m, profile):
    """Profil-ID für ein gemessenes Teil: passendes Profil der Stammdaten, sonst der Vorschlag der Messung."""
    return finde_profil(m, profile) or m.get("profil_id_vorschlag") or None


# Profilformen, die die Messung erkennt, das Programm aber nicht kalkuliert. U-, C-, L-Profile und Flachstahl
# werden seit 20.10.2026 kalkuliert (Patrick: Plan Frage 2 b); Vollmaterial und nicht erkannte offene Profile nicht.
NICHT_KALKULIERT = ("Vierkantstahl", "Rundstahl", "offenes Sonderprofil")
MIT_B = ("Rechteckrohr", "U-Profil", "C-Profil", "L-Profil")     # Profilformen mit Abmessung B


def unsicher(m):
    """Merkmale, die die Messung als unsicher bewertet (Spalte 'sicherheit', z. B. 'wandstaerke=unsicher')."""
    return [k for k, _, v in (x.partition("=") for x in (m.get("sicherheit") or "").split(";")) if v == "unsicher"]


def gewaehlt(m):
    """False, wenn das Teil im Prüfdialog abgewählt wurde (Schlüssel '_uebernehmen'). Ohne Entscheidung im Dialog
    werden Teile mit unsicherer Erkennung nicht übernommen (erst nach Bestätigung durch Anhaken)."""
    return m.get("_uebernehmen", not unsicher(m)) is not False


TOL_GLEICH = 0.2     # mm: Körper einer Baugruppe gelten als gleiches Teil, wenn alle Maße so nah beieinander liegen


def _rohrteil(m):
    return (not m.get("fehler") and bool(m.get("profilform")) and m.get("profilform") not in NICHT_KALKULIERT
            and _z(m, "laenge") > 0)


def _gleich(a, b):
    """Zwei gemessene Körper sind dasselbe Teil (Lage im Raum und vertauschte Enden egal)."""
    if a.get("profilform") != b.get("profilform") or bohrungen_text(a.get("bohrungen")) != bohrungen_text(b.get("bohrungen")):
        return False
    if any(int(_z(a, n)) != int(_z(b, n)) for n in ("konturen", "innen_konturen", "gravur_konturen")):
        return False
    if any(abs(_z(a, n) - _z(b, n)) > TOL_GLEICH
           for n in ("abm_a", "abm_b", "wandstaerke", "laenge", "schneidweg", "innen", "gravur")):
        return False
    enden = [sorted([(x.get("ende_a_gerade") == "1", _z(x, "ende_a")), (x.get("ende_b_gerade") == "1", _z(x, "ende_b"))])
             for x in (a, b)]
    return all(ga == gb and abs(la - lb) <= TOL_GLEICH for (ga, la), (gb, lb) in zip(*enden))


def gleiche_teile(messwerte):
    """Gruppen gleicher Rohrteile je Datei: {Index des ersten Körpers: [Indizes aller gleichen Körper]}."""
    gruppen = {}
    for i, m in enumerate(messwerte):
        if not _rohrteil(m):
            continue
        for erster, liste in gruppen.items():
            if messwerte[erster].get("datei") == m.get("datei") and _gleich(messwerte[erster], m):
                liste.append(i)
                break
        else:
            gruppen[i] = [i]
    return gruppen


def mehrteilig(messwerte):
    """STEP-Dateien mit mehreren Rohrteilen: {Datei: (Anzahl Körper, Anzahl verschiedene Teile)}."""
    out = {}
    for erster, liste in gleiche_teile(messwerte).items():
        d = messwerte[erster].get("datei")
        n, v = out.get(d, (0, 0))
        out[d] = (n + len(liste), v + 1)
    return {d: nv for d, nv in out.items() if nv[0] > 1}


def satzname(datei):
    """Satzbezeichnung aus dem Dateinamen (ohne Endung)."""
    return Path(str(datei)).stem


def vorpruefung(messwerte, positionen, k):
    """(fehlende Profil-IDs, Anzahl Artikel, die schon im Angebot stehen) für die Rückfragen."""
    vorhanden = {str(p.get("artikel")) for p in positionen if p.get("artikel") not in (None, "")}
    fehlend, doppelt = [], 0
    for m in messwerte:
        if m.get("fehler") or not m.get("profilform") or not gewaehlt(m) or m.get("profilform") in NICHT_KALKULIERT:
            continue
        pid = m.get("_profil") or m.get("profil_id_vorschlag")
        fehlt = pid not in k.profile if m.get("_profil") else finde_profil(m, k.profile) is None
        if fehlt and pid and pid not in fehlend:
            fehlend.append(pid)
        if m.get("artikel") in vorhanden:
            doppelt += 1
    return fehlend, doppelt


def uebernehmen(messwerte, positionen, k, gewinde_zeilen, maschine, werkstoff=None, stueck=None,
                neue_profile=False, erneut=False, jetzt=None, saetze=()):
    """Messwerte in Positionen umsetzen. Ergebnis: dict(positionen=[neue Positionen], profile=[neue Profile],
    protokoll=[Zeilen wie PROTOKOLL], bericht=[Text je Teil]).
    saetze = Dateinamen, deren Körper als Satz übernommen werden: Satz = Dateiname, gleiche Körper werden eine
    Position mit 'Stück je Satz' = Anzahl, stueck zählt dann Sätze (Stückzahl = Sätze × Stück je Satz).
    Werte aus dem Prüfdialog je Teil (vor werkstoff/stueck): _uebernehmen (False = nicht übernehmen), _stueck,
    _werkstoff, _profil (Profil-ID statt des Abgleichs mit den Stammdaten). Bei gleichen Körpern eines Satzes
    gelten die Werte des ersten. Aus dem Prüfdialog (Feld 'Sätze'): _saetze > 0 macht die Datei zum Satz (zusätzlich
    zu saetze), _stueck = Sätze, _je_satz = Stück je Satz (leer = Anzahl gleicher Körper)."""
    jetzt = jetzt or datetime.datetime.now().replace(microsecond=0)
    gewinde = [(g["gewinde"], g["kernloch"]) for g in gewinde_zeilen
               if g.get("gewinde") and isinstance(g.get("kernloch"), (int, float))] or KERNLOCH
    klein, mittel, grenz_hinweis = KLEIN_BIS, MITTEL_BIS, \
        f"Konturgrenzen Vorgabe {KLEIN_BIS:g}/{MITTEL_BIS:g} mm (Maschine ohne Werte)"
    if maschine and isinstance(maschine.get("kontur_klein"), (int, float)) and \
            isinstance(maschine.get("kontur_mittel"), (int, float)) and 0 < maschine["kontur_klein"] < maschine["kontur_mittel"]:
        klein, mittel, grenz_hinweis = maschine["kontur_klein"], maschine["kontur_mittel"], ""
    profile = dict(k.profile)
    vorhanden = {str(p.get("artikel")) for p in positionen if p.get("artikel") not in (None, "")}
    pos_max = max((p["pos"] for p in positionen if isinstance(p.get("pos"), (int, float))), default=0)
    naechste = int(pos_max) + 10
    neu, neue_prof, protokoll, bericht = [], [], [], []
    saetze = set(saetze or ()) | {m.get("datei") for m in messwerte if m.get("_saetze")}
    gruppe_von = {}         # Index -> Index des ersten gleichen Körpers (nur in Sätzen)
    for erster, liste in gleiche_teile(messwerte).items():
        if messwerte[erster].get("datei") in saetze:
            for i in liste:
                gruppe_von[i] = erster
    gruppen = {e: [i for i, g in gruppe_von.items() if g == e] for e in set(gruppe_von.values())}
    ergebnis = {}           # Index des ersten Körpers -> Ziel-Pos. (None = nicht übernommen)
    for i, m in enumerate(messwerte):
        if m.get("fehler"):
            protokoll.append([jetzt, m.get("datei")] + [None] * 27 + ["FEHLER: " + m["fehler"]])
            bericht.append(f"{m.get('datei')}: FEHLER: {m['fehler']}")
            continue
        art = m.get("artikel")
        hinweise = [h for h in [m.get("hinweise")] if h]
        vorschlag = gewinde_vorschlag(m.get("bohrungen"), gewinde)
        kl = konturklassen(m.get("innen_liste"), klein, mittel)
        if grenz_hinweis and m.get("innen_liste"):
            hinweise.append(grenz_hinweis)
        ziel, pid = None, None
        if m.get("profilform") and m.get("profilform") not in NICHT_KALKULIERT:
            gemessen = profil_vorschlag(m, profile)
            pid = m.get("_profil") or finde_profil(m, profile)
            if m.get("_profil") and pid != gemessen:
                hinweise.append(f"Profil im Prüfdialog geändert (gemessen {gemessen or m['profilform']})")
            if pid is None or pid not in profile:
                pid = pid or m.get("profil_id_vorschlag") or None
                if neue_profile and pid:
                    p = dict(profil_id=pid, form=m["profilform"], a=round(_z(m, "abm_a"), 2),
                             b=round(_z(m, "abm_b"), 2) if m["profilform"] in MIT_B else None,
                             wand=round(_wand(m), 2), flaeche_manuell=round(_z(m, "flaeche"), 1),
                             bemerkung="aus STEP-Import angelegt, bitte prüfen")
                    neue_prof.append(p)
                    profile[pid] = p
                    hinweise.append("Profil neu in Stammdaten angelegt")
                else:
                    hinweise.append("Profil fehlt in Stammdaten")
        erster = gruppe_von.get(i)
        satz = satzname(m.get("datei")) if erster is not None else None
        if erster is not None and erster != i:
            ziel = ergebnis[erster]
            hinweise.append(f"gleich wie {messwerte[erster].get('artikel')}" + (f" (Satz {satz})" if ziel else ""))
        elif m.get("profilform") in NICHT_KALKULIERT:
            hinweise.append(f"nicht übernommen: {m['profilform']} wird noch nicht kalkuliert")
        elif not gewaehlt(m):
            hinweise.append(f"nicht übernommen: Erkennung unsicher ({', '.join(unsicher(m))}), im Prüfdialog "
                            "bestätigen" if "_uebernehmen" not in m else "nicht übernommen: im Prüfdialog abgewählt")
        elif art in vorhanden and not erneut:
            hinweise.append("übersprungen: Artikel steht schon im Angebot")
        elif _z(m, "laenge") <= 0 or not m.get("profilform"):
            hinweise.append("nicht übernommen: kein Rohrteil erkannt")
        else:
            wst = m.get("_werkstoff", werkstoff)
            stk = m.get("_stueck", stueck)
            p = dict(pos=naechste, artikel=art, profil_id=pid, werkstoff_id=wst or None,
                     laenge=round(_z(m, "laenge"), 1), stueck=stk or None,
                     schneidweg=round(_z(m, "schneidweg"), 1), einstiche=int(_z(m, "konturen")),
                     innen=round(_z(m, "innen"), 1), gravur=round(_z(m, "gravur"), 1),
                     bohrungen=bohrungen_text(m.get("bohrungen")) or None, gewinde_vorschlag=vorschlag or None)
            if m.get("_netz"):
                p["_netz"] = m["_netz"]         # 3D-Ansicht; speichert der Aufrufer nach position_neu
            if _z(m, "ende_a"):
                p["a_gerade"] = "ja" if m.get("ende_a_gerade") == "1" else "nein"
                p["a_schnitt"] = round(_z(m, "ende_a"), 1)
            if _z(m, "ende_b"):
                p["b_gerade"] = "ja" if m.get("ende_b_gerade") == "1" else "nein"
                p["b_schnitt"] = round(_z(m, "ende_b"), 1)
            for name, (n, l) in zip(("klein", "mittel", "gross"), kl):
                p[f"{name}_n"], p[f"{name}_mm"] = n, round(l, 1)
            if satz:
                anzahl = int(m.get("_je_satz") or len(gruppen[i]))
                p["satz"], p["je_satz"] = satz, anzahl
                p["stueck"] = stk * anzahl if stk else None
                hinweise.append(f"Satz {satz}, {anzahl} Stück je Satz"
                                + (f" (Körper {', '.join(messwerte[j].get('koerper') for j in gruppen[i])})" if anzahl > 1 else ""))
            neu.append(p)
            ziel = naechste
            vorhanden.add(art)
            naechste += 10
        if erster == i:
            ergebnis[i] = ziel
        abm_b = round(_z(m, "abm_b"), 2)
        protokoll.append([jetzt, m.get("datei"), int(_z(m, "koerper")), m.get("profilform"), round(_z(m, "abm_a"), 2),
                          abm_b or None, round(_z(m, "wandstaerke"), 2), round(_z(m, "flaeche"), 1),
                          round(_z(m, "laenge"), 1), round(_z(m, "schneidweg"), 1), int(_z(m, "konturen")),
                          "ja" if m.get("ende_a_gerade") == "1" else "nein", round(_z(m, "ende_a"), 1),
                          "ja" if m.get("ende_b_gerade") == "1" else "nein", round(_z(m, "ende_b"), 1),
                          round(_z(m, "innen"), 1), int(_z(m, "innen_konturen")), round(_z(m, "gravur"), 1),
                          int(_z(m, "gravur_konturen")), bohrungen_text(m.get("bohrungen")) or None, vorschlag or None,
                          kl[0][0], round(kl[0][1], 1), kl[1][0], round(kl[1][1], 1), kl[2][0], round(kl[2][1], 1),
                          pid, ziel, "; ".join(hinweise) or None])
        bericht.append(f"{art}: " + (f"Pos. {ziel}" if ziel else "nicht übernommen") +
                       (", " + "; ".join(hinweise) if hinweise else ", OK"))
    return dict(positionen=neu, profile=neue_prof, protokoll=protokoll, bericht=bericht)
