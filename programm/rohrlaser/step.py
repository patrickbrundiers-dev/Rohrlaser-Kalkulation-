"""STEP-Import: Messung mit STEP-Import.exe (bzw. step_messung/step_messen.py) und Übernahme in das Angebot.

Die Messung läuft als eigener Prozess: OpenCascade bleibt aus dem Programm heraus, und ein Absturz bei
einer defekten Datei trifft nur die Messung. Die Übernahme der Messwerte: Profilabgleich ±0,15 mm,
Gewinde-Vorschlag, Konturklassen, Protokoll.
"""
import datetime
import json
import math
import importlib.util
import sys
from pathlib import Path

from . import anbau, bohrbild, naht, rechnen, rp_profile

TOL_MASS = 0.15
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


def dez(x):
    return f"{x:g}".replace(".", ",")


def bohrungen_text(text):
    return "; ".join(f"{int(n)}xØ{dez(d)}" for d, n in _paare(text))


def gewinde_vorschlag(text, gewinde):
    out = []
    for d, n in _paare(text):
        for g, kern in gewinde:
            if abs(d - kern) <= 0.05:
                out.append(f"{int(n)}x{g}")
                break
    return "; ".join(out)


def gehrungen(m):
    """Ebene schräge Enden aus der Konturliste der Messung als Felder a_ende/b_ende (JSON {winkel, richtung});
    ohne Richtung (ältere STEP-Import.exe) oder bei geraden und komplexen Enden leer."""
    try:
        liste = json.loads(m.get("konturen_liste") or "[]")
    except (TypeError, ValueError):
        liste = []
    out = {}
    for d in liste if isinstance(liste, list) else ():
        feld = {"Ende A": "a_ende", "Ende B": "b_ende"}.get(d.get("art")) if isinstance(d, dict) else None
        if feld and d.get("form") in ("Gehrung", "Schrägschnitt zweiachsig") and d.get("richtung") is not None \
                and d.get("gehrung"):
            out[feld] = naht.ende_text(d["gehrung"], d["richtung"])
    return out


SEITE_KASTEN = {"0°": "oben", "90°": "vorne", "180°": "unten", "270°": "hinten"}


def _versatz_quer(d, seite, breit, schmal):
    """Versatz einer Kontur quer auf ihrer Seite (Quadrat-/Rechteckrohr) ab Seitenmitte [mm], + in Richtung
    steigender Umfangsposition. Aus dem Umfangswinkel: auf der ebenen Seite ist der Versatz = Abstand der Seite von
    der Rohrmitte × tan(Winkel zur Seitenmitte), unabhängig von den Eckradien (die Umfangsposition u enthält die
    Bögen der Ecken und lag bei gerundeten Rohren um einige mm daneben). Ohne Winkel aus u (scharfkantig)."""
    mitte_w = {"oben": 0, "vorne": 90, "unten": 180, "hinten": 270}[seite]
    if d.get("winkel") is not None:
        dw = (float(d["winkel"]) - mitte_w + 180) % 360 - 180
        if abs(dw) >= 89:
            return None
        abstand = schmal / 2 if seite in ("oben", "unten") else breit / 2
        return abstand * math.tan(math.radians(dw))
    if d.get("u") is None:
        return None
    mitte = {"oben": 0.0, "vorne": (breit + schmal) / 2, "unten": breit + schmal, "hinten": 1.5 * (breit + schmal)}
    umfang = 2 * (breit + schmal)
    return (float(d["u"]) - mitte[seite] + umfang / 2) % umfang - umfang / 2


def kandidaten_3d(m):
    """Was die Messung für die 3D-Schnittbearbeitung anbietet: (Gehrungen an den Enden, schräge Bohrungen ab 0,5°)
    als Anzahl. Fasen zählen nicht (Patrick 22.10.2026: in 3D in der Praxis nicht sauber)."""
    try:
        liste = json.loads(m.get("konturen_liste") or "[]")
    except (TypeError, ValueError):
        return 0, 0
    gehr = bohr = 0
    for d in liste if isinstance(liste, list) else ():
        if not isinstance(d, dict):
            continue
        if d.get("art") in ("Ende A", "Ende B") and d.get("form") in ("Gehrung", "Schrägschnitt zweiachsig") \
                and d.get("gehrung"):
            gehr += 1
        elif d.get("art") == "Bohrung" and d.get("durchgehend") and float(d.get("schraeg") or 0) >= SCHRAEG_3D:
            bohr += 1
    return gehr, bohr


SCHRAEG_3D = 0.5        # Grad, wie step_geometrie.SCHRAEG_3D


OFFEN = ("U-Profil", "C-Profil", "L-Profil", "Flachstahl", "I-/H-Träger", "T-Profil")


def offen_lage(querschnitt, profil):
    """Lage der STEP-Messung im Querschnitt der Skizze für offene Profile und Flachstahl: aus dem gemessenen Umriss
    (Punkte x, y um die Mitte, von Ende A gesehen) die Drehung (0/90/180/270°), mit der er am besten auf den Umriss
    der Skizze passt (skizze.Querschnitt: U/C Steg vorne, L Schenkel a vorne und b unten, Träger/T Flansch oben).
    Ergebnis: Funktion (x, y) -> (Flächenname, Versatz quer ab Flächenmitte) oder None ohne Umriss."""
    from . import skizze as sk
    pts = [(float(x), float(y)) for x, y in querschnitt or () if x is not None and y is not None]
    if len(pts) < 4:
        return None
    try:
        qs = sk.Querschnitt(profil)
    except (ValueError, TypeError, ZeroDivisionError):
        return None
    if not qs.flaechen or not qs.umriss:
        return None
    um = qs.umriss[0]
    us, vs = [p[0] for p in um], [p[1] for p in um]
    mu, mv = (max(us) + min(us)) / 2, (max(vs) + min(vs)) / 2
    kanten = list(zip(um, um[1:] + um[:1]))

    def abst(p, a, b):
        dx, dy = b[0] - a[0], b[1] - a[1]
        lg = dx * dx + dy * dy
        t = 0.0 if lg < 1e-12 else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / lg))
        return math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy)

    def drehen(r, sp):      # Blick von Ende A: u = −x, v = y (wie Umfangswinkel 90° = vorne), dann um r drehen
        c, s_ = round(math.cos(math.radians(r))), round(math.sin(math.radians(r)))
        return lambda x, y: (-sp * x * c - y * s_ + mu, -sp * x * s_ + y * c + mv)
    # gespiegelt nur, wenn es deutlich besser passt: ein L-Profil kann von Ende A gesehen das Spiegelbild der Skizze
    # sein (dasselbe Teil von B aus); Fläche und Abstand von der Ecke bleiben dabei richtig
    beste = min((sum(min(abst(f(x, y), a, b) for a, b in kanten) for x, y in pts) / len(pts) + (0.2 if sp < 0 else 0),
                 r, sp) for r in (0, 90, 180, 270) for sp in (1, -1) for f in (drehen(r, sp),))
    f = drehen(beste[1], beste[2])

    def lage(x, y):
        p = f(float(x), float(y))
        fl = min(qs.flaechen, key=lambda fl_: abst(p, fl_.p0, fl_.p1))
        q = (p[0] - fl.mitte[0]) * fl.dir[0] + (p[1] - fl.mitte[1]) * fl.dir[1]
        return fl.name, max(-fl.breite / 2, min(fl.breite / 2, q))
    return lage


def rechner_eingaben(m, form, a=None, b=None, d3=False):
    """Konturen und Enden der Messung als Eingaben des Schneidweg-Rechners (positionen.technik, Quelle
    'STEP-Import'): Art und Maße wie gemessen, Lage (z ab Ende A, Winkel bzw. Seite und Versatz), gemessene
    Schnittlänge und Hüllmaß ('gemessen', 'huelle_gemessen'), Gravur als Länge. Solange die Maße einer Zeile
    unverändert bleiben, rechnet der Rechner mit der gemessenen Länge. Nur innen liegende Merkmale fehlen;
    ohne Konturliste (ältere STEP-Import.exe) None.
    d3 (Häkchen 3D-Schnittbearbeitung im Prüfdialog): Gehrungen an den Enden werden Gehrungen in 3D, schräge
    Bohrungen (ab 0,5°) Bohrungen in 3D mit Neigung längs/quer (STEP-JSON 1.5; ältere Messungen nur mit dem Betrag
    als Neigung längs und dem Text „3D prüfen“). Ohne d3 bleibt alles 2D."""
    from .schneidweg import ACHSE_ZWEI, ACHSEN, QUELLE_STEP, messprofil_text
    try:
        liste = json.loads(m.get("konturen_liste") or "[]")
    except (TypeError, ValueError):
        return None
    if not isinstance(liste, list) or not liste:
        return None
    a_, b_ = float(a or 0), float(b or a or 0)
    breit, schmal = max(a_, b_), min(a_, b_)
    kasten = form in ("Quadratrohr", "Rechteckrohr")
    offen = None
    if form in OFFEN:
        kopf = next((d for d in liste if isinstance(d, dict) and d.get("art") == "Ende A"), {})
        offen = offen_lage(kopf.get("querschnitt"), dict(
            form=form, a=a_, b=b_ if b else None, wand=_z(m, "wandstaerke") or _wand(m),
            profil_id=m.get("normprofil") or m.get("profil_id_vorschlag")))
    eing = dict(quelle=QUELLE_STEP, a={}, b={}, konturen=[])
    if d3:
        eing["d3"] = True
    for d in liste:
        if not isinstance(d, dict):
            continue
        art = d.get("art")
        if art in ("Ende A", "Ende B"):
            e = dict(gemessen=round(float(d.get("schnittlaenge") or 0), 2), form=d.get("form"))
            if m.get("profilform") and _z(m, "abm_a") > 0:      # gemessener Querschnitt (Profilwechsel)
                e["messprofil"] = messprofil_text(m["profilform"], m.get("abm_a"), m.get("abm_b"), _wand(m))
            if d.get("huellmass"):
                e["huelle_gemessen"] = round(float(d["huellmass"]), 2)
            if d.get("form") in ("Gehrung", "Schrägschnitt zweiachsig") and d.get("gehrung"):
                e["winkel"] = round(float(d["gehrung"]), 2)
                r = d.get("richtung")
                if r is not None:
                    e["richtung"] = float(r) % 360
                    # Achse passend zur Richtung (Breitseite oben: 0°/180° kippt über die kürzere Seite)
                    quer = schmal if e["richtung"] % 180 == 0 else breit
                    e["achse"] = ACHSEN[0] if abs(quer - a_) < 1e-6 else ACHSEN[1]
                if d.get("form") == "Schrägschnitt zweiachsig" and d.get("um_x") is not None \
                        and d.get("um_y") is not None:
                    # um_x kippt über die senkrechte Ausdehnung (Breitseite oben: die schmale Seite), um_y über
                    # die waagrechte; über Höhe = über Maß a
                    senk, waag = float(d["um_x"]), float(d["um_y"])
                    a_senk = abs(schmal - a_) < 1e-6
                    e.update(achse=ACHSE_ZWEI, winkel_h=round(senk if a_senk else waag, 2),
                             winkel_b=round(waag if a_senk else senk, 2))
                if d3:
                    e["d3"] = True
            if d.get("flaechen") and d.get("huelle"):        # 3D-Ende (STEP-JSON 1.8): Flächen der Messung
                e.update(flaechen=d["flaechen"], huelle=d["huelle"])
            if e["gemessen"] > 0:
                eing["a" if art == "Ende A" else "b"] = e
            continue
        if not d.get("durchgehend") or d.get("z") is None or not d.get("schnittlaenge"):
            continue
        k = dict(anzahl=1, x=round(float(d["z"]), 1), gemessen=round(float(d["schnittlaenge"]), 2))
        if d.get("huellmass"):
            k["huelle_gemessen"] = round(float(d["huellmass"]), 2)
        lage = float(d.get("richtung") or 0)
        laengs = 45 < lage % 180 < 135          # Längsrichtung der Kontur entlang der Rohrachse
        if art == "Bohrung" and d.get("durchmesser"):
            k.update(art="Bohrung", d=float(d["durchmesser"]))
            schraeg = float(d.get("schraeg") or 0)
            if d3 and schraeg >= SCHRAEG_3D:
                if d.get("neigung_l") is not None:
                    k.update(d3=True, neigung_l=round(float(d["neigung_l"]), 1),
                             neigung_q=round(float(d.get("neigung_q") or 0), 1))
                else:                       # Messung vor STEP-JSON 1.5: Richtung unbekannt
                    k.update(d3=True, neigung_l=round(schraeg, 1), text=f"schräg {schraeg:g}°, 3D prüfen")
        elif art == "Senkung" and d.get("durchmesser") and d.get("senk_durchmesser"):
            k.update(art="Senkung", d=float(d["durchmesser"]), D=float(d["senk_durchmesser"]))
        elif art == "Langloch" and d.get("laenge") and d.get("breite"):
            k.update(art="Langloch", l=float(d["laenge"]), b=float(d["breite"]))
            if not laengs:
                k["quer"] = True
        elif art == "Rechteckausschnitt" and d.get("laenge") and d.get("breite"):
            lg, br = float(d["laenge"]), float(d["breite"])
            k.update(art="Rechteck", b=lg if laengs else br, h=br if laengs else lg, r=0)
        else:
            k.update(art="sonstige Kontur", laenge=k["gemessen"], huelle=k.get("huelle_gemessen"))
        if form == "Rundrohr" and d.get("winkel") is not None:
            k["seite"] = round(float(d["winkel"]) % 360, 1)
        elif kasten and d.get("seite") in SEITE_KASTEN:
            seite = SEITE_KASTEN[d["seite"]]
            breite_f = breit if seite in ("oben", "unten") else schmal
            q = _versatz_quer(d, seite, breit, schmal)
            if q is not None and abs(q) <= breite_f / 2 + 1e-6 and abs(q) > 0.05:
                k["q"] = round(q, 1)
            if seite != "oben":
                k["seite"] = seite
        elif offen and isinstance(d.get("querlage"), dict) and d["querlage"].get("x") is not None:
            k["seite"], q = offen(d["querlage"]["x"], d["querlage"].get("y"))
            if abs(q) > 0.05:
                k["q"] = round(q, 1)
        eing["konturen"].append(k)
    if _z(m, "gravur") > 0:                     # Gravur nur als Länge (nicht im Schneidweg)
        eing["gravur"] = round(_z(m, "gravur"), 1)
    return eing if (eing["konturen"] or eing["a"] or eing["b"]) else None


def konturen_enden(m):
    """Anfangs- und Endschnitt als [('A' bzw. 'E', Hüllmaß, Schnittweg)] für die Konturklassen; fehlt das Hüllmaß
    (Messung einer älteren STEP-Import.exe), bleiben die Enden ohne Klasse und laufen mit Vorschub groß."""
    out = []
    for art, laenge, huelle in (("A", "ende_a", "ende_a_huelle"), ("E", "ende_b", "ende_b_huelle")):
        if _z(m, laenge) > 0 and _z(m, huelle) > 0:
            out.append((art, _z(m, huelle), _z(m, laenge)))
    return out


def _wand(m):
    """Wand- bzw. Blechdicke eines gemessenen Teils (Flachstahl: Dicke = Abmessung B der Messung)."""
    return _z(m, "abm_b") if m.get("profilform") == "Flachstahl" else _z(m, "wandstaerke")


def wand_max(m):
    """Größte gemessene Wandstärke für die Schneidzeit (Profil neu aus dem STEP-Import): Flanschdicke bei Trägern
    und T-Profilen, sonst die dickste Einzelmessung der Wand; None, wenn sie nicht dicker als die Wandstärke ist."""
    werte = [_z(m, "flanschdicke")]
    for teil in (m.get("wand_messungen") or "").split("|"):
        f = teil.split(":")
        if len(f) >= 4:
            try:
                werte.append(float(f[3]))
            except ValueError:
                pass
    w = max(werte)
    return round(w, 2) if w > _wand(m) + 0.05 else None


def profil_abweichung(m, pr):
    """Weicht der gemessene Querschnitt vom gewählten Profil ab (Patrick 22.10.2026)? Maße ±0,3 mm, Wand ±0,15 mm,
    Fläche ±1,5 %: 'WARNUNG: STEP … ↔ Profil …' mit beiden Werten, sonst None."""
    if not pr:
        return None
    from .schneidweg import _masse
    from .stammdaten import flaeche_wirksam
    form = m.get("profilform")
    ist, soll = _masse(form, _z(m, "abm_a"), _z(m, "abm_b")), _masse(form, pr.get("a"), pr.get("b"))
    fl_ist, fl_soll = _z(m, "flaeche"), flaeche_wirksam(pr) or 0
    wand_ist, wand_soll = _wand(m), float(pr.get("wand") or 0)
    abweichend = any(abs(x - y) > TOL_MASS for x, y in zip(ist, soll)) or \
        (form != "Flachstahl" and abs(wand_ist - wand_soll) > 0.15) or \
        (fl_ist > 0 and fl_soll > 0 and abs(fl_ist - fl_soll) > 0.015 * fl_soll)
    if not abweichend:
        return None
    t = lambda masse, w, fl: (" × ".join(dez(round(x, 1)) for x in masse) + (f" × {dez(round(w, 2))}" if w else "")
                              + f" mm, Fläche {dez(round(fl, 1))} mm²")
    return f"WARNUNG: STEP weicht vom gewählten Profil ab: STEP {t(ist, wand_ist, fl_ist)} ↔ Profil " \
           f"{pr.get('profil_id') or ''} {t(soll, wand_soll, fl_soll)}".replace("  ", " ")


def enden_neu(m, pr, rechner):
    """Anfangs- und Endschnitt für das Profil der Position neu (Patrick 22.10.2026): gilt die gemessene Länge nicht
    für das Profil (anderes Profil als gemessen, RP-Profil mit doppelt gezähltem Anschlag; schneidweg.anderes_profil),
    rechnet schneidweg.ende_neu mit der gemessenen Form (gerade, Gehrung, Schrägschnitt zweiachsig, 3D-Ende).
    Ergebnis dict(laengen {a/b: mm}, differenz (neu − gemessen, für den Schneidweg), hinweise) oder None."""
    from .schneidweg import anderes_profil, ende_neu
    if not pr or not rechner:
        return None
    pr = dict(pr, profil_id=pr.get("profil_id"))
    laengen, hinweise, diff = {}, [], 0.0
    for x, titel in (("a", "Anfangsschnitt"), ("b", "Endschnitt")):
        e = rechner.get(x) or {}
        if not _z(e, "gemessen") or not anderes_profil(e, pr):
            continue
        neu = ende_neu(pr, e)
        if neu is None:
            hinweise.append(f"{titel} ({e.get('form') or '?'}) nicht für das Profil rechenbar: gemessene Länge "
                            f"{dez(round(_z(e, 'gemessen'), 1))} mm übernommen, bitte prüfen")
            continue
        laengen[x] = neu[0]
        diff += neu[0] - _z(e, "gemessen")
    if laengen:
        rp = pr.get("form") == rp_profile.FORM
        hinweise.insert(0, ("RP-Profil " + str(pr.get("profil_id")) + ": Anschlag (Doppellage) einmal geschnitten, "
                            if rp else f"Enden für Profil {pr.get('profil_id')} neu gerechnet, ")
                        + f"Schneidweg {dez(round(abs(diff), 1))} mm {'kürzer' if diff < 0 else 'länger'} als gemessen")
    return dict(laengen=laengen, differenz=diff, hinweise=hinweise) if laengen or hinweise else None


def finde_rp(m, profile):
    """RP-Profil der Stammdaten zu einer Messung: die erkannte Profil-ID (Spalte normprofil), sonst per Fingerabdruck
    (Maße, Fläche, Außenkontur, Kammern) unter den RP-Profilen der Stammdaten mit bekannter Kontur (Bibliothek oder
    selbst geladen). Damit findet auch ein als Sonderprofil gemessenes Teil sein selbst geladenes RP-Profil."""
    if m.get("normprofil") in profile and (profile[m["normprofil"]].get("form") == rp_profile.FORM):
        return m["normprofil"]
    if not _z(m, "kontur_umfang"):
        return None
    eintraege = {pid: rp_profile.daten(pid) for pid, p in profile.items() if p.get("form") == rp_profile.FORM}
    treffer = rp_profile.erkennen(_z(m, "abm_a"), _z(m, "abm_b"), _z(m, "flaeche"), _z(m, "kontur_umfang"),
                                  int(_z(m, "kammern") or 1), _wand(m), {k: v for k, v in eintraege.items() if v})
    return treffer[0] if treffer else None


def finde_profil(m, profile):
    form, a, b, t = m.get("profilform"), _z(m, "abm_a"), _z(m, "abm_b"), _wand(m)
    if form in (rp_profile.FORM, "Sonderprofil"):
        pid = finde_rp(m, profile)
        if pid or form == rp_profile.FORM:
            return pid
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
        elif form in ("U-Profil", "C-Profil", "I-/H-Träger", "T-Profil"):
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
# werden seit 20.10.2026 kalkuliert (Patrick: Plan Frage 2 b), I-/H-Träger und T-Profile ebenfalls (Plan "Profile
# und Bleche", Frage 2 a); Vollmaterial und nicht erkannte offene Profile nicht.
# Bleche (STEP-Messung seit 20.10.2026) sind keine Rohrlaserteile: sie werden nie als Profil übernommen.
BLECHE = ("Blech", "Blech gekantet")
NICHT_KALKULIERT = ("Vierkantstahl", "Rundstahl", "offenes Sonderprofil", "Verbundkern") + BLECHE
MIT_B = ("Rechteckrohr", "U-Profil", "C-Profil", "L-Profil", "I-/H-Träger", "T-Profil", rp_profile.FORM)    # Formen mit Abmessung B


def blech(m):
    """Blechdaten eines gemessenen Teils (Spalte 'blech' der Messung, JSON) oder None."""
    import json
    if m.get("profilform") not in BLECHE or not m.get("blech"):
        return None
    try:
        return json.loads(m["blech"])
    except ValueError:
        return None


def alternative(m):
    """Grenzfall Flachstahl/Blech bzw. Profil/Kantteil: Messwerte des Teils in der anderen Art (Spalte
    'alternative', JSON {Spalte: Wert}) oder None."""
    import json
    try:
        return json.loads(m["alternative"]) if m.get("alternative") else None
    except ValueError:
        return None


def anbauteile(m):
    """Anbauteile der Messung (Spalte 'anbauteile', JSON-Liste, ab STEP-Import 0.8.5) oder []."""
    try:
        return json.loads(m.get("anbauteile") or "[]")
    except ValueError:
        return []


def anbau_text(m):
    """Kurztext der Anbauteile für den Prüfdialog, z. B. 'Anbauteile (nicht gelasert): Bolzen bei z 300 mm 0°,
    Gravur 20 mm …' oder ''."""
    liste = anbauteile(m)
    if not liste:
        return ""
    teile = []
    for a in liste:
        lage = a.get("seite") or (f"{dez(a['winkel'])}°" if a.get("winkel") is not None else "")
        z = f"z {dez(a['z'])} mm" if a.get("z") is not None else ""
        teile.append(" ".join(x for x in (a.get("art") or "", z, lage, "(prüfen)" if a.get("vertrauen") == "prüfen"
                                          else "") if x)
                     + (f" ({a['quelle']})" if str(a.get("quelle", "")).startswith("Körper") else ""))
    try:
        tr = json.loads(m.get("trennung") or "null") or {}
    except ValueError:
        tr = {}
    ohne = tr.get("ohne_trennung") or {}
    return (f"Anbauteile (nicht gelasert, abgetrennt): {'; '.join(teile)} – Gravur {dez(_z(m, 'gravur_anbau'))} mm"
            + (f" · ohne Trennung gemessen: {ohne.get('profil_id') or 'nicht messbar'}, Länge {dez(ohne.get('laenge'))}"
               f" mm, Schneidweg {dez(ohne.get('schneidweg'))} mm" if ohne else ""))


def art_text(m, gegen=None):
    """Bauteilart für die Auswahl im Prüfdialog, z. B. 'Flachstahl', 'Blech', 'L-Profil', 'Kantteil (Blech gekantet)'.
    Bei Anbauteilen mit dem Zusatz 'Anbauteile abgetrennt' bzw. (gegen = die andere Messung hat sie abgetrennt)
    'ohne Trennung'."""
    form = m.get("profilform") or ""
    zusatz = " – Anbauteile abgetrennt" if m.get("trennung") else \
        " – ohne Trennung" if gegen is not None and gegen.get("trennung") else ""
    return (("Kantteil (Blech gekantet)" if form == "Blech gekantet" else form) + zusatz
            + (" – Ersatzwerte" if m.get("ersatz") == "1" else ""))


def ohne_trennung_text(m):
    """Kurztext der Messung ohne Trennung (Teil mit abgetrennten Anbauteilen), z. B. 'Sonderprofil, Länge 1008 mm,
    Schneidweg 2280 mm', oder None (keine Trennung oder ohne Trennung nicht messbar)."""
    alt = alternative(m)
    if not m.get("trennung") or not alt or alt.get("trennung"):
        return None
    return (f"{alt.get('profilform') or ''} {alt.get('profil_id_vorschlag') or ''}".strip()
            + f", Länge {dez(_z(alt, 'laenge'))} mm, Schneidweg {dez(_z(alt, 'schneidweg'))} mm")


def anbau_setzen(m, neu):
    """Ergebnis des Dialogs 'Anbauteile prüfen' in die Messwerte schreiben: Liste, Gravur um den Unterschied.
    Sind danach alle unsicher erkannten Anbauteile entschieden, gilt die Anbauteil-Erkennung als geprüft."""
    alt = anbau.lesen(m.get("anbauteile"))
    for k, v in anbau.anwenden({k: m.get(k) for k in ("gravur", "gravur_anbau", "gravur_konturen")}, alt,
                               neu).items():
        m[k] = str(v)
    m["anbauteile"] = anbau.schreiben(neu) or ""
    if not anbau.offen(neu) and any(anbau.unsicher(a) for a in neu):
        m["sicherheit"] = ";".join(f"{k}=geprüft" if k == "anbauteile" else x for x in
                                   (m.get("sicherheit") or "").split(";") for k in [x.partition("=")[0]])


def art_wechseln(m):
    """Teil auf die andere Art umstellen (Flachstahl ↔ Blech, Profil ↔ Kantteil): die Messwerte der Spalte
    'alternative' gelten, die bisherigen werden die Alternative. Eingaben aus dem Prüfdialog, die zur Art gehören
    (Häkchen, Profil, Werkstoff, Zukaufartikel), fallen weg und werden für die neue Art neu vorbelegt."""
    import json
    alt = alternative(m)
    if alt is None:
        return False
    bisher = {k: m.get(k, "") for k in alt}
    m.update(alt)
    m["alternative"] = json.dumps(bisher, ensure_ascii=False, separators=(",", ":"))
    for k in ("_uebernehmen", "_profil", "_werkstoff", "_blech_artikel"):
        m.pop(k, None)
    return True


VON_HAND = "von Hand nachgetragen"


def von_hand(m, form, profil_id, profile):
    """Nicht erkanntes Teil von Hand als Rohr/Profil nachtragen (Patrick 22.10.2026): Profilform und Profil-ID aus dem
    Prüfdialog, Maße aus den Stammdaten bzw. der Profil-ID ('QR 40x40x3'), sonst aus dem Hüllmaß; Länge = größtes
    Hüllmaß, zwei gerade Enden, keine Konturen (im Schneidweg-Rechner ergänzen). Prüfstatus 'prüfen', angehakt.
    Die Messung bleibt unter '_original' (zurück mit von_hand_zuruecknehmen). False, wenn kein Hüllmaß bekannt ist."""
    from .optimierung import profil_aus_name, schnittlaenge
    try:
        h = sorted((float(x) for x in (m.get("huelle") or "").split("|") if x), reverse=True)
    except ValueError:
        h = []
    if len(h) != 3 or h[0] <= 0 or not form:
        return False
    original = m.get("_original") or {k: v for k, v in m.items() if not k.startswith("_")}
    pr = profile.get(profil_id) or (profil_aus_name(profil_id) if profil_id else None) or {}
    a = float(pr.get("a") or h[1])
    b = float(pr.get("b") or (h[2] if form in MIT_B else 0) or 0)
    wand = float(pr.get("wand") or 0)
    ende = schnittlaenge(form, a, b, wand, pr.get("flaeche_manuell")) or 2 * (a + b)
    netz = m.get("_netz")
    m.clear()
    m.update(original)
    m.update(profilform=form, abm_a=str(a), abm_b=str(b), wandstaerke=str(wand), laenge=str(h[0]),
             ende_a=str(ende), ende_b=str(ende), ende_a_gerade="1", ende_b_gerade="1", schneidweg=str(2 * ende),
             konturen="2", innen="0", innen_konturen="0", gravur="0", gravur_konturen="0", bohrungen="",
             innen_liste="", konturen_liste="", profil_id_vorschlag=profil_id or "", pruefstatus="prüfen",
             sicherheit="profil=von Hand", alternative="", anbauteile="", trennung="", bauteiltyp="Profil",
             hinweise=f"{VON_HAND} ({original.get('hinweise') or 'nicht messbar'}): Länge aus Hüllmaß, gerade "
                      "Enden, Konturen im Schneidweg-Rechner ergänzen")
    m["_original"], m["_uebernehmen"], m["_profil"] = original, True, profil_id or None
    if netz:        # Rohnetz der Messung (Art N = nicht übernehmbar) jetzt als Außenwand
        import zlib
        try:
            n = json.loads(zlib.decompress(netz).decode("utf-8"))
            if "N" in (n.get("t") or {}):
                n["t"]["A"] = n["t"].pop("N")
                netz = zlib.compress(json.dumps(n, separators=(",", ":")).encode("utf-8"), 6)
        except (zlib.error, ValueError):
            pass
        m["_netz"] = netz
    return True


def von_hand_zuruecknehmen(m):
    """Nachtrag zurücknehmen: wieder die Messung (nicht übernehmbar)."""
    original = m.get("_original")
    if not original:
        return False
    netz = m.get("_netz")
    m.clear()
    m.update(original)
    if netz:        # wieder als nicht übernehmbar zeigen
        import zlib
        try:
            n = json.loads(zlib.decompress(netz).decode("utf-8"))
            if "A" in (n.get("t") or {}) and len(n["t"]) == 1:
                n["t"]["N"] = n["t"].pop("A")
                netz = zlib.compress(json.dumps(n, separators=(",", ":")).encode("utf-8"), 6)
        except (zlib.error, ValueError):
            pass
        m["_netz"] = netz
    return True


def blech_text(m):
    """Kurztext eines Blechs, z. B. 'Blech 500 × 300 × 5 mm'."""
    b = blech(m) or {}
    f = lambda x: dez(round(float(x or 0), 1))
    return f"{m.get('profilform')} {f(b.get('laenge'))} × {f(b.get('breite'))} × {f(b.get('dicke'))} mm"


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


def _blechteil(m):
    return not m.get("fehler") and blech(m) is not None


def _gleiches_blech(a, b):
    """Zwei gemessene Bleche sind dasselbe Teil: gleiche Art, Geometrie-Kennung und Maße (± TOL_GLEICH)."""
    ba, bb = blech(a), blech(b)
    return (a.get("profilform") == b.get("profilform") and ba.get("fingerabdruck") == bb.get("fingerabdruck")
            and all(abs(float(ba.get(n) or 0) - float(bb.get(n) or 0)) <= TOL_GLEICH
                    for n in ("laenge", "breite", "dicke")))


def gleiche_bleche(messwerte):
    """Gruppen gleicher Bleche je Datei: {Index des ersten Körpers: [Indizes aller gleichen Körper]}."""
    gruppen = {}
    for i, m in enumerate(messwerte):
        if not _blechteil(m):
            continue
        for erster, liste in gruppen.items():
            if messwerte[erster].get("datei") == m.get("datei") and _gleiches_blech(messwerte[erster], m):
                liste.append(i)
                break
        else:
            gruppen[i] = [i]
    return gruppen


def teile_gruppen(messwerte, mit_blechen=True):
    """Rohrteile (gleiche_teile) und, mit_blechen, Bleche (gleiche_bleche) zusammen, nach erstem Index sortiert."""
    g = dict(gleiche_teile(messwerte))
    if mit_blechen:
        g.update(gleiche_bleche(messwerte))
    return dict(sorted(g.items()))


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


def mehrteilig(messwerte, mit_blechen=False):
    """STEP-Dateien mit mehreren Rohrteilen (mit_blechen: auch Blechen): {Datei: (Anzahl Körper, Anzahl verschiedene
    Teile)}."""
    out = {}
    for erster, liste in teile_gruppen(messwerte, mit_blechen).items():
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


def blech_gewicht(b, werkstoff_id, k, blech_werkstoffe=None):
    """Gewicht je Blech [kg] aus Volumen × Dichte des Werkstoffs (Blech-Werkstoffe, sonst Stammdaten der Rohre);
    None ohne bekannten Werkstoff."""
    w = (blech_werkstoffe or {}).get(werkstoff_id) or k.werkstoffe.get(werkstoff_id) if werkstoff_id else None
    dichte = (w or {}).get("dichte")
    vol = b.get("volumen") or (b.get("flaeche_netto") or 0) * (b.get("dicke") or 0)
    if not isinstance(dichte, (int, float)) or dichte <= 0 or not vol:
        return None
    return round(vol * dichte / 1e6, 3)          # mm³ × g/cm³ / 10⁶ = kg


def blech_richtpreis(b, wst, blech_daten, stueck=None):
    """Richtpreis je Stück [€] eines gemessenen Blechs wie im Blech-Editor (blech.aus_step) oder None (ohne
    Blech-Werkstoff, Daten oder Richtwerte)."""
    from . import blech as bl
    if not blech_daten or not wst or wst not in blech_daten.get("werkstoffe", {}):
        return None
    erg = bl.rechnen(bl.aus_step(b, wst, stueck), blech_daten["werkstoffe"], blech_daten.get("laserdaten") or [],
                     blech_daten.get("einst"))
    return erg["richtpreis"] if not erg["fehler"] else None


def _blech_position(m, b, wst, zukauf_liste, neue_artikel, k, blech_daten=None, stueck=None):
    """Zukaufartikel für ein Blech: im Prüfdialog gewählter Artikel (_blech_artikel), sonst eine Dublette (gleich)
    aus den vorhandenen bzw. in diesem Import neu angelegten Artikeln, sonst ein neuer Artikel; mit Blech-Werkstoff
    und blech_daten (Blech-Editor: werkstoffe, laserdaten, einst) bekommt er den Richtpreis als EK, sonst keinen.
    Ergebnis: (Verweis {artikel_id} bzw. {neu: Schlüssel}, Hinweistext)."""
    from . import zukauf
    gewaehlt_id = m.get("_blech_artikel")
    if isinstance(gewaehlt_id, int):
        a = next((x for x in zukauf_liste if x.get("id") == gewaehlt_id), None)
        if a is not None:
            return dict(artikel_id=gewaehlt_id), f"Zukaufartikel {a.get('bezeichnung')} (im Prüfdialog gewählt)" + (
                ", EK fehlt" if zukauf.ek_fehlt(a) else "")
    vorhandene = [x for x in zukauf_liste if x.get("id") is not None]
    gleich, aehnlich = zukauf.blech_dubletten(b, wst, vorhandene)
    if gleich:
        a = gleich[0]
        return dict(artikel_id=a["id"]), f"vorhandener Zukaufartikel {a.get('bezeichnung')}" + (
            ", EK fehlt" if zukauf.ek_fehlt(a) else "")
    neu_gleich, _ = zukauf.blech_dubletten(b, wst, [dict(x[0], status="aktiv", _schl=s_) for s_, x in neue_artikel.items()])
    if neu_gleich:
        schl = neu_gleich[0]["_schl"]
        return dict(neu=schl), f"Zukaufartikel {neu_gleich[0].get('bezeichnung')} (neu" + (
            ", EK = Richtpreis)" if neue_artikel[schl][1][0].get("preise") else ", EK fehlt)")
    werte, bezuege = zukauf.blech_artikel(b, wst, m.get("datei"))
    schl = f"neu{len(neue_artikel) + 1}"
    neue_artikel[schl] = (werte, bezuege)
    preis = blech_richtpreis(b, wst, blech_daten, stueck)
    if preis:
        bezuege[0]["preise"] = [dict(ab=1, preis=preis)]
    text = f"neuer Zukaufartikel {werte['bezeichnung']}, " + (
        f"EK = Richtpreis {preis:.2f} €".replace(".", ",") if preis else "EK fehlt")
    if aehnlich:
        text += f" (ähnlich: {', '.join(a.get('bezeichnung') or '' for a in aehnlich[:3])})"
    return dict(neu=schl), text


def uebernehmen(messwerte, positionen, k, gewinde_zeilen, maschine, werkstoff=None, stueck=None,
                neue_profile=False, erneut=False, jetzt=None, saetze=(), zukauf_liste=None, fliessloch_laser=None,
                blech_daten=None, d3=False):
    """Messwerte in Positionen umsetzen. Ergebnis: dict(positionen=[neue Positionen], profile=[neue Profile],
    protokoll=[Zeilen wie PROTOKOLL], bericht=[Text je Teil]).
    saetze = Dateinamen, deren Körper als Satz übernommen werden: Satz = Dateiname, gleiche Körper werden eine
    Position mit 'Stück je Satz' = Anzahl, stueck zählt dann Sätze (Stückzahl = Sätze × Stück je Satz).
    Werte aus dem Prüfdialog je Teil (vor werkstoff/stueck): _uebernehmen (False = nicht übernehmen), _stueck,
    _werkstoff, _profil (Profil-ID statt des Abgleichs mit den Stammdaten). Bei gleichen Körpern eines Satzes
    gelten die Werte des ersten. Aus dem Prüfdialog (Feld 'Sätze'): _saetze > 0 macht die Datei zum Satz (zusätzlich
    zu saetze), _stueck = Sätze, _je_satz = Stück je Satz (leer = Anzahl gleicher Körper).

    Bleche (Plan 4 b): mit zukauf_liste (Zukaufartikel der Datenbank, z. B. db.zukauf_artikel_liste()) wird jedes
    gewählte Blech eine Position der Art Zukaufteil mit einem Zukaufartikel (vorhandene Dublette oder neu, ohne EK).
    Der Werkstoff kommt nur aus dem Prüfdialog (_werkstoff, ein Blech-Werkstoff), nie aus der Vorgabe für die
    Rohre; mit blech_daten (werkstoffe, laserdaten, einst des Blech-Editors) bekommt ein neuer Artikel den Richtpreis
    als EK. Bleche mit
    Prüfstatus 'prüfen' (z. B. gekantet) werden erst nach Bestätigung im Prüfdialog übernommen. Die Positionen tragen
    _zukauf = {artikel_id} bzw. {neu: Schlüssel}; neue Artikel stehen im Ergebnis unter zukauf_neu {Schlüssel:
    (Werte, Einkaufsbedingungen)}, der Aufrufer legt sie an und trägt die Zukaufteile ein (Menge 1 je Teil).
    Ohne zukauf_liste werden Bleche wie bisher nicht übernommen.
    d3 bzw. je Teil _d3 (Häkchen 3D-Schnittbearbeitung im Prüfdialog): Gehrungen und schräge Bohrungen in 3D
    (rechner_eingaben); ohne Häkchen bekommen Teile mit schrägen Bohrungen den Hinweis „3D prüfen“."""
    jetzt = jetzt or datetime.datetime.now().replace(microsecond=0)
    gewinde = [(g["gewinde"], g["kernloch"]) for g in gewinde_zeilen
               if g.get("gewinde") and isinstance(g.get("kernloch"), (int, float))] or KERNLOCH
    (klein, mittel), vorgabe = rechnen.kontur_grenzen(maschine)
    grenz_hinweis = f"Konturgrenzen Vorgabe {klein:g}/{mittel:g} mm (Maschine ohne Werte)" if vorgabe else ""
    profile = dict(k.profile)
    vorhanden = {str(p.get("artikel")) for p in positionen if p.get("artikel") not in (None, "")}
    pos_max = max((p["pos"] for p in positionen if isinstance(p.get("pos"), (int, float))), default=0)
    naechste = int(pos_max) + 10
    neu, neue_prof, protokoll, bericht = [], [], [], []
    saetze = set(saetze or ()) | {m.get("datei") for m in messwerte if m.get("_saetze")}
    mit_blechen = zukauf_liste is not None
    neue_artikel = {}
    gruppe_von = {}         # Index -> Index des ersten gleichen Körpers (nur in Sätzen)
    for erster, liste in teile_gruppen(messwerte, mit_blechen).items():
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
        enden = konturen_enden(m)
        # Wandstärke für die Konturklassen wie später im Angebot: Profil der Stammdaten, sonst die Messung
        pr = profile.get(m.get("_profil") or finde_profil(m, profile))
        regel = rechnen.kontur_regel(maschine, rechnen.wand_schneiden(pr) if pr else
                                     max(_wand(m), wand_max(m) or 0) or None)
        kl = rechnen.konturklassen([(g, lg) for _, g, lg in enden] + _paare(m.get("innen_liste")), regel)
        kl = [[kl[f"{n}_n"], kl[f"{n}_mm"]] for n in ("klein", "mittel", "gross")]
        if grenz_hinweis and (m.get("innen_liste") or enden):
            hinweise.append(grenz_hinweis)
        ziel, pid = None, None
        if m.get("profilform") and m.get("profilform") not in NICHT_KALKULIERT:
            gemessen = profil_vorschlag(m, profile)
            pid = m.get("_profil") or finde_profil(m, profile)
            if m.get("_profil") and pid != gemessen:
                hinweise.append(f"Profil im Prüfdialog geändert (gemessen {gemessen or m['profilform']})")
                abw = profil_abweichung(m, profile.get(pid))
                if abw:
                    hinweise.append(abw)
            if pid is None or pid not in profile:
                pid = pid or m.get("profil_id_vorschlag") or None
                if neue_profile and pid and rp_profile.daten(pid):
                    p = rp_profile.stammdaten_zeile(rp_profile.daten(pid))
                    neue_prof.append(p)
                    profile[pid] = p
                    hinweise.append("RP-Profil aus der Bibliothek in Stammdaten angelegt")
                elif neue_profile and pid:
                    p = dict(profil_id=pid, form=m["profilform"], a=round(_z(m, "abm_a"), 2),
                             b=round(_z(m, "abm_b"), 2) if m["profilform"] in MIT_B else None,
                             wand=round(_wand(m), 2), wand_max=wand_max(m), flaeche_manuell=round(_z(m, "flaeche"), 1),
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
        elif m.get("profilform") in BLECHE and not (mit_blechen and blech(m)):
            hinweise.append(f"nicht übernommen: {blech_text(m)} ist kein Rohrlaserteil")
        elif m.get("profilform") in BLECHE and (m.get("_uebernehmen") is False or (
                m.get("pruefstatus") == "prüfen" and m.get("_uebernehmen") is not True)):
            hinweise.append(f"nicht übernommen: {blech_text(m)}" + (" im Prüfdialog abgewählt" if "_uebernehmen" in m
                                                                     else " ungeprüft (Prüfstatus prüfen), im Prüfdialog bestätigen"))
        elif m.get("profilform") in BLECHE and art in vorhanden and not erneut:
            hinweise.append("übersprungen: Artikel steht schon im Angebot")
        elif m.get("profilform") in BLECHE:
            from .angebot import ZUKAUFTEIL
            b = blech(m)
            wst = m.get("_werkstoff") or None       # nur, wenn im Prüfdialog gewählt
            stk = m.get("_stueck", stueck)
            verweis, text = _blech_position(m, b, wst, zukauf_liste, neue_artikel, k, blech_daten, stk)
            # Eingaben des Blech-Editors (Doppelklick öffnet ihn); ein Richtpreis als EK wird gemerkt, damit die
            # Staffeln ihn vom EK des Einkaufs unterscheiden
            preise = neue_artikel[verweis["neu"]][1][0].get("preise") if "neu" in verweis else None
            from . import blech as bl
            technik = bl.speichern(dict(bl.aus_step(b, wst, stk), richtpreise=[dict(ab=1, preis=preise[0]["preis"])]
                                        if preise else []))
            from .zukauf import blech_bezeichnung
            p = dict(pos=naechste, art=ZUKAUFTEIL, artikel=art,
                     bezeichnung=blech_bezeichnung(b.get("laenge"), b.get("breite"), b.get("dicke"), wst),
                     werkstoff_id=wst if wst in k.werkstoffe else None, laenge=round(float(b.get("laenge") or 0), 1),
                     stueck=stk or None, gewicht_teil=blech_gewicht(b, wst, k, (blech_daten or {}).get("werkstoffe")),
                     technik=technik, _zukauf=verweis)
            if m.get("_netz"):
                p["_netz"] = m["_netz"]
            hinweise.append(f"Zukaufteil: {text}")
            if not wst:
                hinweise.append("Werkstoff offen")
            if satz:
                anzahl = int(m.get("_je_satz") or len(gruppen[i]))
                p["satz"], p["je_satz"] = satz, anzahl
                p["stueck"] = stk * anzahl if stk else None
                hinweise.append(f"Satz {satz}, {anzahl} Stück je Satz")
            neu.append(p)
            ziel = naechste
            vorhanden.add(art)
            naechste += 10
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
            form = (profile.get(pid) or {}).get("form") or m.get("profilform")
            enden_n = sum(1 for n in ("ende_a", "ende_b") if _z(m, n) > 0)
            p = dict(pos=naechste, artikel=art, profil_id=pid, werkstoff_id=wst or None,
                     laenge=round(_z(m, "laenge"), 1), stueck=stk or None,
                     schneidweg=round(_z(m, "schneidweg"), 1),
                     einstiche=int(_z(m, "konturen")) + (rechnen.einstiche_ende(form) - 1) * enden_n,
                     innen=round(_z(m, "innen"), 1), gravur=round(_z(m, "gravur"), 1),
                     bohrungen=bohrungen_text(m.get("bohrungen")) or None, gewinde_vorschlag=vorschlag or None)
            if m.get("_netz"):
                p["_netz"] = m["_netz"]         # 3D-Ansicht; speichert der Aufrufer nach position_neu
            p.update(gehrungen(m))
            mit_3d = bool(m.get("_d3", d3))
            rechner = rechner_eingaben(m, form, (profile.get(pid) or {}).get("a") or m.get("abm_a"),
                                       (profile.get(pid) or {}).get("b") or m.get("abm_b"), mit_3d)
            gehr_3d, bohr_3d = kandidaten_3d(m)
            if bohr_3d and not mit_3d:
                hinweise.append(f"3D prüfen: {bohr_3d} schräge Bohrung{'en' if bohr_3d > 1 else ''}, ohne "
                                "3D-Schnittbearbeitung als 2D gerechnet")
            elif mit_3d and not (gehr_3d or bohr_3d):
                hinweise.append("3D-Schnittbearbeitung gewählt, aber keine Gehrung und keine schräge Bohrung")
            if rechner:
                p["technik"] = json.dumps(rechner, ensure_ascii=False)     # Konturen für Skizze und Rechner
            if _z(m, "ende_a"):
                p["a_gerade"] = "ja" if m.get("ende_a_gerade") == "1" else "nein"
                p["a_schnitt"] = round(_z(m, "ende_a"), 1)
            if _z(m, "ende_b"):
                p["b_gerade"] = "ja" if m.get("ende_b_gerade") == "1" else "nein"
                p["b_schnitt"] = round(_z(m, "ende_b"), 1)
            neu_enden = enden_neu(m, profile.get(pid), rechner)
            if neu_enden:   # anderes Profil als gemessen bzw. RP-Profil: Enden mit der gemessenen Form neu gerechnet
                for x, lg in neu_enden["laengen"].items():
                    p[f"{x}_schnitt"] = round(lg, 1)
                p["schneidweg"] = round(p["schneidweg"] + neu_enden["differenz"], 1)
                hinweise += neu_enden["hinweise"]
            for name, (n, l) in zip(("klein", "mittel", "gross"), kl):
                p[f"{name}_n"], p[f"{name}_mm"] = n, round(l, 1)
            if m.get("innen_liste") or enden:
                p["konturen"] = rechnen.konturen_text(_paare(m.get("innen_liste")), enden)
                p["kontur_grenzen"] = rechnen.grenzen_text(regel)
            # Gewinde-Vorschläge, Senkungen, Fließlochbohrungen, Bohren (< 0,7 × Wand): offen bis 'Bohrungen prüfen'
            # (bohrbild.py), erst dann die Zusatzarbeiten Senken, Flowdrill, Bohren
            bild = bohrbild.aus_messung(m, gewinde, fliessloch_laser or bohrbild.GRAVUR,
                                        regel[4] if len(regel) >= 5 else None)
            if bild:
                p.update(bohrbild.anwenden(p, bild))
                p["bohrungen"] = "; ".join(filter(None, [p.get("bohrungen"), bohrbild.text(bild)])) or None
                if any(z["art"] != "Bohrung" for z in bild):
                    hinweise.append(bohrbild.text(bild) + ": im Angebot mit 'Bohrungen prüfen' bestätigen")
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
    return dict(positionen=neu, profile=neue_prof, protokoll=protokoll, bericht=bericht, zukauf_neu=neue_artikel)
