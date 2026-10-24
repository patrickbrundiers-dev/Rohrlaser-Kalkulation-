"""Knickverbindung aus Einzelrohren (Plan K1-2): Rohre einer STEP-Datei, die an den Ecken mit Gehrung aneinander
stoßen, werden ein Knickrahmen (knickrahmen.py) = eine Position mit dem gestreckten Rohr und den V-Ausschnitten.

Erkennung (Fall B): gleiches Quadrat- oder Rechteckrohr (± TOL_PROFIL), je zwei Enden mit Gehrung liegen beieinander
(Achsenden höchstens NAH × größte Seite auseinander), der Winkel zwischen den Achsen ist die Summe der beiden
Gehrungen (± TOL_WINKEL), alle Rohre liegen in einer Ebene und die Kette ist eindeutig (offen oder geschlossen).
Die Lage kommt aus dem Netz der Messung (lage = Ende A, Rohrachse, X-Richtung in der Datei), die Stegwand aus der
Richtung der Gehrung (längste Seite = Außenseite der Ecke).

Im Prüfdialog trägt der erste Schenkel (Leitteil) den Block _knickrahmen und _knick_teile = [{i, umgekehrt}] in
Reihenfolge; die übrigen Rohre tragen _knick_von = Index des Leitteils und werden nicht einzeln übernommen. Beim
Übernehmen (step.uebernehmen) kommen die Konturen aller Schenkel auf das gestreckte Rohr (eingaben).

Knickrahmen aus einem Körper (Plan K1-3, Fall A): Die Messung (step_messung/step_knickrahmen.py) teilt den Körper an
den Ecken in gerade Rohrstücke mit Gehrung (Spalte knick_schenkel). koerper_vorbereiten verbindet sie wie Einzelrohre;
der Körper selbst trägt dann den Block, _knick_teile zählt in _knick_schenkel (die Stücke), nicht in den Messwerten.
Ist der Rahmen gestreckt gezeichnet (gerades Rohr mit V-Ausschnitten, „vor dem Knicken“), kommen Knickwinkel und
Schenkel aus den V-Ausschnitten der Messung (v_rahmen); der Block steht dann mit _knick_v (Lage der V) am Rohr."""
import json
import math
import zlib

from . import knickrahmen as kn

TOL_PROFIL = 0.15       # mm
TOL_WINKEL = 1.5        # Grad: Achsenwinkel gegen Summe der Gehrungen
NAH = 1.5               # Achsenden einer Ecke liegen höchstens 1,5 × größte Seite auseinander
HERKUNFT = "STEP-Einzelrohre"
HERKUNFT_KOERPER = "STEP-Körper"
SEITEN = {0: "oben", 90: "vorne", 180: "unten", 270: "hinten"}
WINKEL = {s: w for w, s in SEITEN.items()}


def _z(x):
    try:
        return float(x) if x not in (None, "") else 0.0
    except (TypeError, ValueError):
        return 0.0


def _netz(m):
    d = m.get("_netz")
    if isinstance(d, dict):
        return d
    if not d:
        return None
    try:
        return json.loads(zlib.decompress(bytes(d)).decode("utf-8"))
    except (zlib.error, ValueError, TypeError):
        return None


def _sub(a, b):
    return tuple(x - y for x, y in zip(a, b))


def _dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def _kreuz(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _norm(a):
    return math.sqrt(_dot(a, a))


def lage(m):
    """(Ende A, Rohrachse, X-Richtung) in der Datei aus dem Netz der Messung oder None."""
    lg = (_netz(m) or {}).get("lage")
    if not isinstance(lg, list) or len(lg) != 9:
        return None
    return tuple(map(float, lg[0:3])), tuple(map(float, lg[3:6])), tuple(map(float, lg[6:9]))


def enden(m):
    """{'A': (Gehrung, Richtung) oder None, 'B': …} aus der Konturliste der Messung (nur ebene Gehrungen mit
    Richtung)."""
    try:
        liste = json.loads(m.get("konturen_liste") or "[]")
    except (TypeError, ValueError):
        liste = []
    out = {"A": None, "B": None}
    for d in liste if isinstance(liste, list) else ():
        if isinstance(d, dict) and d.get("art") in ("Ende A", "Ende B") and d.get("form") == "Gehrung" \
                and d.get("gehrung") and d.get("richtung") is not None:
            out[d["art"][-1]] = (float(d["gehrung"]), float(d["richtung"]) % 360)
    return out


def _teil(messwerte, i):
    """Daten eines Rohrs für die Erkennung oder Text, warum es nicht passt."""
    m = messwerte[i]
    name = m.get("artikel") or f"Körper {m.get('koerper')}"
    if m.get("profilform") not in kn.FORMEN:
        return f"{name}: Knickrahmen nur aus Quadrat- und Rechteckrohr"
    lg = lage(m)
    if not lg or _z(m.get("laenge")) <= 0:
        return f"{name}: Lage in der Datei unbekannt (ältere Messung, STEP neu einlesen)"
    o, z, x = lg
    a, b = _z(m.get("abm_a")), _z(m.get("abm_b")) or _z(m.get("abm_a"))
    L = _z(m.get("laenge"))
    return dict(i=i, name=name, o=o, z=z, x=x, L=L, enden=enden(m), a=a, b=b,
                wand=_z(m.get("wandstaerke")), form=m.get("profilform"),
                punkt={"A": o, "B": tuple(o[k] + z[k] * L for k in range(3))})


def _gleiches_profil(t, u):
    return t["form"] == u["form"] and all(abs(t[n] - u[n]) <= TOL_PROFIL for n in ("wand",)) and \
        abs(max(t["a"], t["b"]) - max(u["a"], u["b"])) <= TOL_PROFIL and \
        abs(min(t["a"], t["b"]) - min(u["a"], u["b"])) <= TOL_PROFIL


def _ecken(teile):
    """Ecken zwischen den Rohren: {(i, Ende): (j, Ende, Knickwinkel β)}; je Ende der nächste passende Partner."""
    beste = {}
    for t in teile:
        for u in teile:
            if u["i"] <= t["i"] or not _gleiches_profil(t, u):
                continue
            grenze = NAH * max(t["a"], t["b"])
            for e in "AB":
                for f in "AB":
                    gt, gu = t["enden"][e], u["enden"][f]
                    if not gt or not gu:
                        continue
                    d = _norm(_sub(t["punkt"][e], u["punkt"][f]))
                    if d > grenze:
                        continue
                    aus = t["z"] if e == "B" else tuple(-c for c in t["z"])       # aus t heraus zur Ecke
                    ein = u["z"] if f == "A" else tuple(-c for c in u["z"])      # von der Ecke in u hinein
                    beta = math.degrees(math.acos(max(-1.0, min(1.0, _dot(aus, ein)))))
                    if abs(beta - (gt[0] + gu[0])) > TOL_WINKEL:
                        continue
                    for schl, partner in (((t["i"], e), (u["i"], f)), ((u["i"], f), (t["i"], e))):
                        if schl not in beste or d < beste[schl][1]:
                            beste[schl] = (partner, d, round(gt[0] + gu[0], 1))
    out = {}
    for schl, (partner, _, beta) in beste.items():     # nur gegenseitige Paare
        if beste.get(partner, (None,))[0] == schl:
            out[schl] = (partner[0], partner[1], beta)
    return out


def _komponenten(teile, ecken):
    nach = {t["i"]: set() for t in teile}
    for (i, _), (j, _, _) in ecken.items():
        nach[i].add(j)
    out, gesehen = [], set()
    for t in teile:
        if t["i"] in gesehen:
            continue
        stapel, comp = [t["i"]], []
        while stapel:
            i = stapel.pop()
            if i in gesehen:
                continue
            gesehen.add(i)
            comp.append(i)
            stapel += list(nach[i])
        out.append(sorted(comp))
    return out


def _seite(w):
    return SEITEN[int(round((w % 360) / 90.0)) % 4 * 90]


def kette(messwerte, indizes, start=None, umkehren=False):
    """Knickrahmen aus den Rohren indizes: dict(teile=[dict(i, umgekehrt, steg_winkel)], schenkel, beta,
    geschlossen, steg). start = Index des ersten Schenkels (offen: ein Endstück, Vorgabe das kleinere; geschlossen:
    jedes, Vorgabe der kleinste Index, Stoß an seinem Anfang), umkehren = andere Laufrichtung. ValueError mit Grund,
    wenn die Rohre keinen Knickrahmen ergeben."""
    teile = []
    for i in indizes:
        t = _teil(messwerte, i)
        if isinstance(t, str):
            raise ValueError(t)
        teile.append(t)
    if len(teile) < 2:
        raise ValueError("Knickverbindung: mindestens zwei Rohre markieren.")
    if any(not _gleiches_profil(teile[0], t) for t in teile[1:]):
        raise ValueError("Knickverbindung: alle Rohre müssen dasselbe Profil haben.")
    ecken = _ecken(teile)
    comps = _komponenten(teile, ecken)
    if len(comps) != 1:
        allein = [messwerte[c[0]].get("artikel") for c in comps if len(c) == 1]
        raise ValueError("Knickverbindung: Die Rohre stoßen nicht alle mit passenden Gehrungen aneinander"
                         + (f" (ohne Ecke: {', '.join(map(str, allein))})" if allein else "") + ".")
    # Ebene: alle Achsen senkrecht zur Normalen, alle Rohre auf einer Ebene
    n = None
    for t in teile[1:]:
        c = _kreuz(teile[0]["z"], t["z"])
        if _norm(c) > 0.1:
            n = tuple(x / _norm(c) for x in c)
            break
    if n is None:
        raise ValueError("Knickverbindung: Die Rohre liegen parallel, das ist kein Rahmen.")
    tol = 0.5 * min(teile[0]["a"], teile[0]["b"])
    for t in teile:
        if abs(_dot(t["z"], n)) > 0.02 or abs(_dot(_sub(t["o"], teile[0]["o"]), n)) > tol:
            raise ValueError(f"Knickverbindung: {t['name']} liegt nicht in der Ebene des Rahmens (räumlicher Rahmen).")
    nach = {t["i"]: {} for t in teile}
    for (i, e), (j, f, beta) in ecken.items():
        nach[i][e] = (j, f, beta)
    geschlossen = all(len(v) == 2 for v in nach.values())
    erste = [i for i, v in nach.items() if len(v) == 1]
    if not geschlossen and len(erste) != 2:
        raise ValueError("Knickverbindung: Die Kette ist nicht eindeutig.")
    if geschlossen:
        s = start if start in nach else min(nach)
        frei = "A" if not umkehren else "B"         # Stoß am Anfang des ersten Schenkels
    else:
        s = start if start in erste else min(erste)
        if umkehren and start is None:
            s = max(erste)
        frei = "A" if "A" not in nach[s] else "B"
    reihe, i, e_frei = [], s, frei
    while True:
        e_ecke = "B" if e_frei == "A" else "A"
        reihe.append((i, e_frei == "B"))
        if e_ecke not in nach[i]:
            break
        j, f, _ = nach[i][e_ecke]
        if j == s:
            break
        if any(j == r for r, _ in reihe):
            raise ValueError("Knickverbindung: Die Kette ist nicht eindeutig.")
        i, e_frei = j, f
    if len(reihe) != len(teile):
        raise ValueError("Knickverbindung: Die Kette ist nicht eindeutig.")
    t_von = {t["i"]: t for t in teile}
    out, schenkel, betas = [], [], []
    for nr, (i, umg) in enumerate(reihe):
        t = t_von[i]
        e_ecke = "A" if umg else "B"
        e_anf = "B" if umg else "A"
        g = t["enden"][e_ecke] if nr < len(reihe) - 1 or geschlossen else t["enden"][e_anf]
        if g is None:
            g = t["enden"][e_anf]
        out.append(dict(i=i, umgekehrt=umg, steg_winkel=g[1] if g else 0.0, laenge=t["L"]))
        schenkel.append(round(t["L"], 2))
        if nr < len(reihe) - 1:
            betas.append(nach[i][e_ecke][2])
    steg_tube = (-out[0]["steg_winkel"] if out[0]["umgekehrt"] else out[0]["steg_winkel"]) % 360
    return dict(teile=out, schenkel=schenkel, beta=betas[0] if len(set(betas)) == 1 else betas,
                geschlossen=geschlossen, steg=_seite(steg_tube))


def vorschlaege(messwerte, belegt=()):
    """Mögliche Knickrahmen aus Einzelrohren je Datei: [Liste der Indizes]; Rohre in belegt (schon verbunden) und
    Mitglieder vorhandener Knickverbindungen bleiben außen vor."""
    out = []
    dateien = {}
    for i, m in enumerate(messwerte):
        if i in belegt or m.get("_knick_von") is not None or m.get("_knickrahmen") or m.get("fehler"):
            continue
        t = _teil(messwerte, i)
        if not isinstance(t, str) and any(t["enden"].values()):
            dateien.setdefault(m.get("datei"), []).append(t)
    for teile in dateien.values():
        ecken = _ecken(teile)
        for comp in _komponenten(teile, ecken):
            if len(comp) < 2:
                continue
            try:
                kette(messwerte, comp)
            except ValueError:
                continue
            out.append(comp)
    return out


def erstellen(messwerte, k, freistich=None, z=None, kf=None, schraeg=False, ziel=None):
    """Knickverbindung k (kette) in die Messwerte schreiben (Leitteil = erster Schenkel). Ergebnis: Index des
    Leitteils. ValueError, wenn der Rahmen nicht geht (knickrahmen.rahmen). ziel: Körper, der den Block trägt
    (Knickrahmen aus einem Körper, messwerte = seine Rohrstücke)."""
    leit = k["teile"][0]["i"]
    m = messwerte[leit] if ziel is None else ziel
    block = dict(schenkel=k["schenkel"], beta=k["beta"], geschlossen=k["geschlossen"], steg=k["steg"],
                 freistich=_z(freistich) or None, z=_z(z) or None, k=_z(kf) or kn.K_FAKTOR,
                 schraeg=bool(schraeg) or None, herkunft=HERKUNFT if ziel is None else HERKUNFT_KOERPER)
    profil = dict(form=m.get("profilform"), a=_z(m.get("abm_a")), b=_z(m.get("abm_b")) or _z(m.get("abm_a")),
                  wand=_z(m.get("wandstaerke")))
    r = kn.rahmen(block, profil)
    for t in k["teile"]:
        loesen(messwerte, t["i"])
    m["_knickrahmen"] = block
    m["_knick_teile"] = [dict(i=t["i"], umgekehrt=t["umgekehrt"], steg_winkel=t["steg_winkel"]) for t in k["teile"]]
    m["_knick_laenge"] = round(r["laenge"], 1)
    if ziel is None:
        for t in k["teile"][1:]:
            messwerte[t["i"]]["_knick_von"] = leit
    return leit


def stuecke(m):
    """Rohrstücke eines Knickrahmens aus einem Körper (Spalte knick_schenkel der Messung) als Messwerte mit Lage im
    Netz, Artikel „… Schenkel n“; [] bei anderen Teilen."""
    if m.get("_knick_schenkel") is not None:
        return m["_knick_schenkel"]
    try:
        liste = json.loads(m.get("knick_schenkel") or "[]")
    except (TypeError, ValueError):
        return []
    if not isinstance(liste, list) or not all(isinstance(d, dict) for d in liste):
        return []
    out = []
    for nr, d in enumerate(liste, 1):
        x = dict(d, datei=m.get("datei"), koerper=m.get("koerper"), artikel=f"{m.get('artikel')} Schenkel {nr}")
        lg = x.pop("lage", None)
        x["_netz"] = {"lage": lg} if isinstance(lg, list) and len(lg) == 9 else None
        out.append(x)
    return out


def ist_koerper(m):
    """Knickrahmen aus einem Körper (geknickt oder gestreckt gezeichnet), nicht aus Einzelrohren?"""
    return m.get("_knick_schenkel") is not None or m.get("_knick_v") is not None


TOL_V = 0.03            # Anteil: Schnittlänge eines V-Ausschnitts gegen die Formel


def v_ausschnitte(m):
    """Gestreckt gezeichneter Knickrahmen: V-Ausschnitte eines geraden Quadrat- oder Rechteckrohrs = durchgehende
    Sonderkonturen durch drei Wände (die vierte, die Stegwand, bleibt). Ergebnis [dict(x, breite, steg,
    schnittlaenge)] nach x."""
    if m.get("profilform") not in kn.FORMEN or m.get("biegerohr") or m.get("knick_schenkel"):
        return []
    try:
        liste = json.loads(m.get("konturen_liste") or "[]")
    except (TypeError, ValueError):
        return []
    out = []
    for d in liste if isinstance(liste, list) else ():
        if not isinstance(d, dict) or d.get("art") != "Sonderkontur" or not d.get("durchgehend") \
                or d.get("z") is None or not d.get("breite"):
            continue
        try:
            waende = {int(round(float(str(w).rstrip("°")))) % 360 for w in d.get("waende") or ()}
        except ValueError:
            continue
        if len(waende) != 3 or not waende <= set(SEITEN):
            continue
        out.append(dict(x=float(d["z"]), breite=float(d["breite"]), steg=SEITEN[(set(SEITEN) - waende).pop()],
                        schnittlaenge=_z(d.get("schnittlaenge"))))
    return sorted(out, key=lambda v: v["x"])


def v_rahmen(m, vorgaben=None):
    """Block eines gestreckt gezeichneten Knickrahmens aus den V-Ausschnitten (v_ausschnitte) oder None: Knickwinkel
    aus der Breite an der Innenwand (w = 2 · (h − s) · tan(β/2)), die Schnittlänge muss zur Formel passen; Schenkel so,
    dass die Knicke an den gemessenen Stellen liegen (gestreckte Länge = gemessene Länge). Geschlossen, wenn beide
    Enden die halbe Gehrung des Stoßes haben. Ergebnis (Block, Lage der V)."""
    vs = v_ausschnitte(m)
    if not vs or len({v["steg"] for v in vs}) != 1:
        return None
    profil = dict(form=m.get("profilform"), a=_z(m.get("abm_a")), b=_z(m.get("abm_b")) or _z(m.get("abm_a")),
                  wand=_z(m.get("wandstaerke")))
    steg = vs[0]["steg"]
    b, h, s = kn.querschnitt(profil, steg)
    if h <= s:
        return None
    betas = [2 * math.degrees(math.atan(v["breite"] / 2 / (h - s))) for v in vs]
    if max(betas) - min(betas) > TOL_WINKEL:
        return None
    beta = round(sum(betas) / len(betas), 1)
    if abs(beta - round(beta)) <= 0.6:
        beta = float(round(beta))
    soll = kn.v_masse(b, h, s, beta)["laenge"]
    if any(v["schnittlaenge"] and abs(v["schnittlaenge"] - soll) > TOL_V * soll for v in vs):
        return None
    v = vorgaben or {}
    kf, zug = _z(v.get("k")) or kn.K_FAKTOR, _z(v.get("z"))
    netto = kn.ausgleich(beta, s, kf) - zug
    xs = [x["x"] for x in vs]
    L = _z(m.get("laenge"))
    schenkel = [xs[0] + netto / 2] + [xs[i] - xs[i - 1] + netto for i in range(1, len(xs))] + [L - xs[-1] + netto / 2]
    e = enden(m)
    stoss = 360.0 - len(xs) * beta
    geschlossen = 0 < stoss < 180 and all(e[x_] and abs(e[x_][0] - stoss / 2) <= TOL_WINKEL for x_ in "AB")
    block = dict(schenkel=[round(x, 2) for x in schenkel], beta=beta, geschlossen=geschlossen, steg=steg,
                 freistich=_z(v.get("freistich")) or None, z=zug or None, k=kf, herkunft=HERKUNFT_KOERPER)
    try:
        kn.rahmen(block, profil)
    except ValueError:
        return None
    return block, xs


def koerper_vorbereiten(m, vorgaben=None):
    """Knickrahmen aus einem Körper: die Rohrstücke wie Einzelrohre verbinden und den Block in m schreiben (nur
    einmal, Änderungen aus dem Prüfdialog bleiben). vorgaben = Einstellungen {z, freistich, k}. Ergebnis: True, wenn m
    ein Knickrahmen ist; geht die Kette nicht, steht der Grund in m['_knick_fehler']."""
    if m.get("_knickrahmen"):
        return True
    teile = stuecke(m)
    if len(teile) < 2:
        gestreckt = v_rahmen(m, vorgaben)
        if not gestreckt:
            return False
        block, xs = gestreckt
        m.update(_knickrahmen=block, _knick_v=xs, pruefstatus="prüfen",
                 _knick_laenge=round(kn.rahmen(block, dict(form=m.get("profilform"), a=_z(m.get("abm_a")),
                                                           b=_z(m.get("abm_b")) or _z(m.get("abm_a")),
                                                           wand=_z(m.get("wandstaerke"))))["laenge"], 1))
        return True
    m["_knick_schenkel"] = teile
    v = vorgaben or {}
    try:
        erstellen(teile, kette(teile, range(len(teile))), v.get("freistich"), v.get("z"), v.get("k"), ziel=m)
    except ValueError as f:
        m["_knick_fehler"] = str(f)
        return False
    return True


def _quelle(messwerte, m):
    """Messwerte, in die _knick_teile von m zählen: die Rohrstücke eines Körpers oder die Messwerte selbst."""
    return m["_knick_schenkel"] if m.get("_knick_schenkel") is not None else messwerte


def loesen(messwerte, i):
    """Knickverbindung, zu der Rohr i gehört, wieder lösen (alle Rohre wieder einzeln)."""
    m = messwerte[i]
    leit = m.get("_knick_von") if m.get("_knick_von") is not None else i
    for t in messwerte[leit].get("_knick_teile") or ():
        messwerte[t["i"]].pop("_knick_von", None)
    for n in ("_knickrahmen", "_knick_teile", "_knick_laenge"):
        messwerte[leit].pop(n, None)


def text(m):
    """Kurztext für die Rohrliste des Prüfdialogs."""
    k = m.get("_knickrahmen")
    if not k:
        return ""
    n = len(k["schenkel"]) - 1
    if ist_koerper(m):
        return (f"Knickrahmen ({n} Knick{'e' if n != 1 else ''}) aus einem Körper"
                + (" (gestreckt gezeichnet)" if m.get("_knick_v") is not None else "")
                + (", geschlossen" if k.get("geschlossen") else ", offen")
                + f", gestreckt {kn._zahl(m.get('_knick_laenge') or 0)} mm")
    return (f"Knickrahmen aus {len(k['schenkel'])} Rohren, {n} Knick{'e' if n != 1 else ''}"
            + (", geschlossen" if k.get("geschlossen") else ", offen")
            + f", gestreckt {kn._zahl(m.get('_knick_laenge') or 0)} mm")


def _drehen(seite, von, nach, s):
    """Seite eines Schenkels (Stegwinkel von) auf das gestreckte Rohr (Stegwinkel nach, s = −1 umgekehrt)."""
    w = WINKEL.get(seite or "oben", 0)
    return _seite(nach + s * (w - von))


def zeile_umsetzen(z, start, laenge, umgekehrt, von, nach):
    """Konturzeile eines Schenkels (step.rechner_eingaben) auf das gestreckte Rohr: Lage um start verschoben (bei
    umgekehrter Laufrichtung gespiegelt), Seite gedreht, Querversatz, Umriss und Neigungen gespiegelt."""
    s = -1 if umgekehrt else 1
    neu = dict(z)
    x = _z(z.get("x"))
    neu["x"] = round(start + (laenge - x if umgekehrt else x), 1)
    seite = _drehen(z.get("seite"), von, nach, s)
    neu.pop("seite", None)
    if seite != "oben":
        neu["seite"] = seite
    if umgekehrt:
        if z.get("q"):
            neu["q"] = -z["q"]
        if z.get("umriss"):
            neu["umriss"] = [[-p[0], -p[1]] for p in z["umriss"]]
        for n in ("neigung_l", "neigung_q"):
            if z.get(n):
                neu[n] = -z[n]
    return neu


def _ende(e, von, nach, umgekehrt, profil):
    if not e or not e.get("winkel"):
        return {}
    from . import schneidweg as sw
    out = dict(e)
    if e.get("richtung") is not None:
        s = -1 if umgekehrt else 1
        r = (nach + s * (float(e["richtung"]) - von)) % 360
        out["richtung"] = r
        out["achse"] = sw.achse_zu_richtung(profil, r)
    return out


def eingaben(m_leit, rechner_je_teil, profil):
    """Eingaben des Rechners für das gestreckte Rohr: Konturen aller Schenkel (rechner_je_teil = {Index: Eingaben aus
    step.rechner_eingaben oder None}) an ihrer Stelle, offene Enden vom ersten und letzten Schenkel, dazu Block und
    V-Ausschnitte (knickrahmen.anwenden). Ergebnis (Eingaben, rahmen)."""
    from .schneidweg import QUELLE_STEP
    k = m_leit["_knickrahmen"]
    r = kn.rahmen(k, profil)
    nach = kn.STEG_RICHTUNG.get(r["steg"], 180)
    teile = m_leit["_knick_teile"]
    erste = rechner_je_teil.get(teile[0]["i"]) or {}
    out = dict(quelle=QUELLE_STEP, a={}, b={}, konturen=[])
    if erste.get("d3"):
        out["d3"] = True
    start, gravur = 0.0, 0.0
    for nr, t in enumerate(teile):
        e = rechner_je_teil.get(t["i"]) or {}
        L = r["schenkel"][nr]
        for z in e.get("konturen") or ():
            out["konturen"].append(zeile_umsetzen(z, start, L, t["umgekehrt"], t["steg_winkel"], nach))
        gravur += _z(e.get("gravur"))
        if not k.get("geschlossen"):
            if nr == 0:
                out["a"] = _ende(e.get("b" if t["umgekehrt"] else "a"), t["steg_winkel"], nach, t["umgekehrt"], profil)
            if nr == len(teile) - 1:
                out["b"] = _ende(e.get("a" if t["umgekehrt"] else "b"), t["steg_winkel"], nach, t["umgekehrt"], profil)
        if nr < len(teile) - 1:
            start += L - (r["vs"][nr] - r["z"])
    if gravur:
        out["gravur"] = round(gravur, 1)
    from .schneidweg import v_ergaenzen
    neu, r = kn.anwenden(out, dict(k, herkunft=k.get("herkunft") or HERKUNFT), profil)
    return v_ergaenzen(neu, profil), r


def netz_gefaltet(messwerte, m_leit):
    """Netz des gefalteten Rahmens im System des Leitteils (alle Schenkel in ihrer Lage), gepackt wie die Netze der
    Messung; None ohne Netze. Knickrahmen aus einem Körper: das Netz des Körpers."""
    if ist_koerper(m_leit):
        return m_leit.get("_netz")
    basis = lage(m_leit)
    if not basis:
        return None
    o, zl, xl = basis
    yl = _kreuz(zl, xl)
    p_out, t_out, l_out = [], {}, {}
    for t in m_leit.get("_knick_teile") or ():
        m = messwerte[t["i"]]
        netz, lg = _netz(m), lage(m)
        if not netz or not lg or not netz.get("p"):
            continue
        o2, z2, x2 = lg
        y2 = _kreuz(z2, x2)

        def umrechnen(a, b, c, o2=o2, x2=x2, y2=y2, z2=z2):
            g = tuple(o2[k] + a * x2[k] + b * y2[k] + c * z2[k] - o[k] for k in range(3))
            return [round(_dot(g, xl), 2), round(_dot(g, yl), 2), round(_dot(g, zl), 2)]
        basis_i = len(p_out) // 3
        p = netz["p"]
        for i in range(0, len(p) - 2, 3):
            p_out += umrechnen(p[i], p[i + 1], p[i + 2])
        for art, idx in (netz.get("t") or {}).items():
            t_out.setdefault(art, []).extend(basis_i + i for i in idx)
        for art, linien in (netz.get("l") or {}).items():
            for li in linien:
                neu = []
                for i in range(0, len(li) - 2, 3):
                    neu += umrechnen(li[i], li[i + 1], li[i + 2])
                l_out.setdefault(art, []).append(neu)
    if not p_out:
        return None
    netz = dict(p=p_out, t=t_out, l=l_out, lage=[*o, *zl, *xl])
    return zlib.compress(json.dumps(netz, separators=(",", ":")).encode("utf-8"), 6)


def kandidaten_filtern(kandidaten, messwerte, datei):
    """Nahtkandidaten einer Datei ohne die Ecken der Knickrahmen (dort wird geknickt, nicht geschweißt); der Stoß
    eines geschlossenen Rahmens bleibt."""
    weg = set()
    for m in messwerte:
        if m.get("datei") != datei or not m.get("_knickrahmen") or ist_koerper(m):
            continue
        nrs = [str(messwerte[t["i"]].get("koerper")) for t in m["_knick_teile"]]
        for a, b in zip(nrs, nrs[1:]):
            weg.add(frozenset((a, b)))
    if not weg:
        return list(kandidaten or ())
    return [k for k in kandidaten or () if not (isinstance(k, dict) and isinstance(k.get("teile"), list)
                                                 and frozenset(map(str, k["teile"])) in weg)]


def summe(messwerte, m_leit, spalte):
    """Spalte mit Paaren 'Ø:Anzahl|…' (bohrungen, senkungen, fliessloecher) über alle Schenkel zusammengezählt."""
    n = {}
    messwerte = _quelle(messwerte, m_leit)
    for t in m_leit.get("_knick_teile") or ():
        for teil in str(messwerte[t["i"]].get(spalte) or "").split("|"):
            if ":" in teil:
                a, z = teil.rsplit(":", 1)
                try:
                    n[a] = n.get(a, 0) + int(float(z))
                except ValueError:
                    continue
    return "|".join(f"{a}:{z}" for a, z in n.items())
