"""Knickverbindung aus Einzelrohren (Plan K1-2): Rohre einer STEP-Datei, die an den Ecken mit Gehrung aneinander
stoßen, werden ein Knickrahmen (knickrahmen.py) = eine Position mit dem gestreckten Rohr und den V-Ausschnitten.

Erkennung (Fall B): gleiches Quadrat- oder Rechteckrohr (± TOL_PROFIL), je zwei Enden mit Gehrung liegen beieinander
(Achsenden höchstens NAH × größte Seite auseinander), der Winkel zwischen den Achsen ist die Summe der beiden
Gehrungen (± TOL_WINKEL), alle Rohre liegen in einer Ebene und die Kette ist eindeutig (offen oder geschlossen).
Die Lage kommt aus dem Netz der Messung (lage = Ende A, Rohrachse, X-Richtung in der Datei), die Stegwand aus der
Richtung der Gehrung (längste Seite = Außenseite der Ecke).

Im Prüfdialog trägt der erste Schenkel (Leitteil) den Block _knickrahmen und _knick_teile = [{i, umgekehrt}] in
Reihenfolge; die übrigen Rohre tragen _knick_von = Index des Leitteils und werden nicht einzeln übernommen. Beim
Übernehmen (step.uebernehmen) kommen die Konturen aller Schenkel auf das gestreckte Rohr (eingaben)."""
import json
import math
import zlib

from . import knickrahmen as kn

TOL_PROFIL = 0.15       # mm
TOL_WINKEL = 1.5        # Grad: Achsenwinkel gegen Summe der Gehrungen
NAH = 1.5               # Achsenden einer Ecke liegen höchstens 1,5 × größte Seite auseinander
HERKUNFT = "STEP-Einzelrohre"
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


def erstellen(messwerte, k, freistich=None, z=None, kf=None, schraeg=False):
    """Knickverbindung k (kette) in die Messwerte schreiben (Leitteil = erster Schenkel). Ergebnis: Index des
    Leitteils. ValueError, wenn der Rahmen nicht geht (knickrahmen.rahmen)."""
    leit = k["teile"][0]["i"]
    m = messwerte[leit]
    block = dict(schenkel=k["schenkel"], beta=k["beta"], geschlossen=k["geschlossen"], steg=k["steg"],
                 freistich=freistich or None, z=z or None, k=kf or kn.K_FAKTOR, schraeg=bool(schraeg) or None,
                 herkunft=HERKUNFT)
    profil = dict(form=m.get("profilform"), a=_z(m.get("abm_a")), b=_z(m.get("abm_b")) or _z(m.get("abm_a")),
                  wand=_z(m.get("wandstaerke")))
    r = kn.rahmen(block, profil)
    for t in k["teile"]:
        loesen(messwerte, t["i"])
    m["_knickrahmen"] = block
    m["_knick_teile"] = [dict(i=t["i"], umgekehrt=t["umgekehrt"], steg_winkel=t["steg_winkel"]) for t in k["teile"]]
    m["_knick_laenge"] = round(r["laenge"], 1)
    for t in k["teile"][1:]:
        messwerte[t["i"]]["_knick_von"] = leit
    return leit


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
    neu, r = kn.anwenden(out, dict(k, herkunft=HERKUNFT), profil)
    return v_ergaenzen(neu, profil), r


def netz_gefaltet(messwerte, m_leit):
    """Netz des gefalteten Rahmens im System des Leitteils (alle Schenkel in ihrer Lage), gepackt wie die Netze der
    Messung; None ohne Netze."""
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
        if m.get("datei") != datei or not m.get("_knickrahmen"):
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
    for t in m_leit.get("_knick_teile") or ():
        for teil in str(messwerte[t["i"]].get(spalte) or "").split("|"):
            if ":" in teil:
                a, z = teil.rsplit(":", 1)
                try:
                    n[a] = n.get(a, 0) + int(float(z))
                except ValueError:
                    continue
    return "|".join(f"{a}:{z}" for a, z in n.items())
