"""Gegenprobe STEP-Import → Editor (Patrick 30.10.2026: „Übergabe in den Editor weiter absichern“; Grundregel: Konturen
und Enden zu 100 % wie in der STEP, Lage und Form).

Beim Übernehmen baut das Programm für jedes Rohr das 3D-Modell des Schneidweg-Rechners (rohr3d, aus denselben
Eingaben wie der Editor) und vergleicht dessen Linien (Konturen K, Enden EA/EB) mit den Linien des gemessenen
STEP-Netzes, in beiden Richtungen: jede Linie der STEP muss im Editor liegen, und der Editor darf keine Linie zeigen,
die es in der STEP nicht gibt. Weicht etwas mehr als GRENZE ab, bekommt die Position einen Hinweis.

Geschlossene Rohre (Quadrat-, Rechteck-, Rundrohr) liegen im Editor wie in der STEP. Offene Profile (L, U, C,
Flachstahl) liegen im Editor anders im Raum (Querschnitt der Skizze): ihr Modell wird zuerst an Ende A auf die STEP
ausgerichtet (Drehung um die Achse in 90°-Schritten, gespiegelt, verschoben), dann gilt GRENZE_OFFEN für die Konturen;
die STEP hat bei offenen Profilen die Konturkanten auf beiden Seiten der Wand, das Modell nur außen, und die Skizze
zeichnet keine Walz-/Biegeradien: STEP → Modell und die Enden dürfen um die Wandstärke weiter weg liegen (Patrick
31.10.2026, „Gegenprobe auch für offene Profile“). Offen gezeichnete Rohre mit Ringen, Knickrahmen und Biegerohre sind bewusst anders als
gezeichnet. Ebene Gehrungen werden wie konstruiert (3D) verglichen, gefertigt werden sie in 2D (lange Seite um
Wand · tan(Winkel) kürzer, Patrick 28.10.2026).
"""
import math

GRENZE = 0.1            # mm: so weit darf eine Linie neben der STEP liegen
SCHRITT = 1.0           # mm: Abtastung der Linien
ZELLE = 2.0             # mm: Raster für die Suche der nächsten Strecke
WEITE = 3.0             # mm: weiter wird nicht gesucht (Abweichung „über 3 mm“)
FORMEN = ("Quadratrohr", "Rechteckrohr", "Rundrohr")
OFFEN = ("L-Profil", "U-Profil", "C-Profil", "Flachstahl")
GRENZE_OFFEN = 0.25     # mm nach dem Ausrichten an Ende A (wie tests/test_step_robust.py)


def _strecken(zuege):
    out = []
    for z in zuege:
        p = [tuple(z[i:i + 3]) for i in range(0, len(z) - 2, 3)]
        out += [(a, b) for a, b in zip(p, p[1:]) if a != b]
    return out


def _abst(p, a, b):
    ab = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
    lg = ab[0] ** 2 + ab[1] ** 2 + ab[2] ** 2
    f = 0.0 if lg < 1e-12 else max(0.0, min(1.0, sum((p[i] - a[i]) * ab[i] for i in range(3)) / lg))
    return math.dist(p, (a[0] + f * ab[0], a[1] + f * ab[1], a[2] + f * ab[2]))


class _Raster:
    """Strecken nach Rasterzellen (je Zelle ihres Hüllquaders): Abstand zur nächsten Strecke nur aus den Zellen in
    der Nähe; weiter als die Suchweite gilt der Abstand als 'weit' (Suchweite selbst)."""

    def __init__(self, strecken, weite):
        self.strecken, self.weite, self.zellen = strecken, weite, {}
        for i, (a, b) in enumerate(strecken):
            lo = [math.floor((min(a[k], b[k]) - weite) / ZELLE) for k in range(3)]
            hi = [math.floor((max(a[k], b[k]) + weite) / ZELLE) for k in range(3)]
            if (hi[0] - lo[0] + 1) * (hi[1] - lo[1] + 1) * (hi[2] - lo[2] + 1) > 200000:
                hi = lo         # ungewöhnlich lange Strecke: nur über die Liste (unten)
                self.lang = getattr(self, "lang", []) + [i]
            for x in range(lo[0], hi[0] + 1):
                for y in range(lo[1], hi[1] + 1):
                    for z in range(lo[2], hi[2] + 1):
                        self.zellen.setdefault((x, y, z), []).append(i)

    def abstand(self, p):
        kand = self.zellen.get(tuple(math.floor(p[k] / ZELLE) for k in range(3)), ())
        kand = list(kand) + getattr(self, "lang", [])
        return min((_abst(p, *self.strecken[i]) for i in kand), default=self.weite)

    def naechster(self, p):
        """Nächster Punkt auf den Strecken in der Nähe oder None."""
        kand = list(self.zellen.get(tuple(math.floor(p[k] / ZELLE) for k in range(3)), ())) + getattr(self, "lang", [])
        best = None
        for i in kand:
            a, b = self.strecken[i]
            ab = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
            lg = ab[0] ** 2 + ab[1] ** 2 + ab[2] ** 2
            f = 0.0 if lg < 1e-12 else max(0.0, min(1.0, sum((p[k] - a[k]) * ab[k] for k in range(3)) / lg))
            q = (a[0] + f * ab[0], a[1] + f * ab[1], a[2] + f * ab[2])
            d = math.dist(p, q)
            if best is None or d < best[0]:
                best = (d, q)
        return best[1] if best else None


def _weitester(a, b_k, b_e, weite, abstand):
    """Größter Abstand eines Punkts der Linien a (je SCHRITT abgetastet) zu den Linien b (Konturen b_k, die um
    abstand über der Wand liegen dürfen, und Enden b_e; höchstens weite) und der Punkt dazu."""
    if not a:
        return 0.0, None
    if not b_k and not b_e:
        return weite, a[0][0]
    rk, re_ = _Raster(b_k, weite + abstand), _Raster(b_e, weite)
    weit, wo = 0.0, None
    for p, q in a:
        n = max(1, int(math.dist(p, q) / SCHRITT))
        for k in range(n + 1):
            x = tuple(p[i] + (q[i] - p[i]) * k / n for i in range(3))
            d = min(max(rk.abstand(x) - abstand, 0.0) if b_k else weite, re_.abstand(x) if b_e else weite)
            if d > weit:
                weit, wo = d, x
    return weit, wo


def vergleichbar(m, profil, eingaben):
    """Lässt sich das Teil so vergleichen (geschlossenes Rohr in der gemessenen Lage oder offenes Profil, Netz
    vorhanden)?"""
    from . import step
    if not m.get("_netz") or not eingaben or (profil or {}).get("form") not in FORMEN + OFFEN:
        return False
    if m.get("profilform") != profil.get("form") or m.get("biegerohr") or m.get("_knickrahmen") \
            or m.get("_knick_von") is not None or step.rohr_geschlossen(m):
        return False
    return not eingaben.get("knickrahmen")


def wie_konstruiert(e):
    """Eingaben mit den ebenen STEP-Gehrungen in 3D (wie in der Datei konstruiert)."""
    e = dict(e)
    eben = [s for s in ("a", "b") if (e.get(s) or {}).get("winkel") and not e[s].get("aussen_mass")
            and not e[s].get("d3")]
    if eben:
        e["d3"] = True
        for s in eben:
            e[s] = dict(e[s], d3=True)
    return e


def abweichung(m, profil, eingaben, laenge):
    """Größte Abweichung [mm] zwischen Editor-Modell und STEP-Netz (beide Richtungen, ohne den Abstand der
    Konturlinien über der Wand) und eine kurze Angabe, wo; None, wenn nicht vergleichbar oder nicht berechenbar."""
    from . import ansicht3d, rohr3d
    if not vergleichbar(m, profil, eingaben):
        return None
    try:
        st = ansicht3d.entpacken(m["_netz"])
        mod = rohr3d.netz_rechnen(wie_konstruiert(eingaben), profil, laenge)
    except (ValueError, TypeError, KeyError, ZeroDivisionError):
        return None
    if not st or not mod or not isinstance(st.get("l"), dict):
        return None
    def lin(netz, *arten):
        return _strecken([z for a in arten for z in (netz.get("l") or {}).get(a, [])])
    sk_, se = lin(st, "K"), lin(st, "EA", "EB")
    mk, me = lin(mod, "K"), lin(mod, "EA", "EB")
    if not (sk_ or se) or not (mk or me):
        return None
    if profil.get("form") in OFFEN:
        return _abweichung_offen(lin(st, "EA"), sk_, lin(st, "EB"), lin(mod, "EA"), mk, lin(mod, "EB"),
                                 float(profil.get("wand") or 0), rohr3d.ABSTAND)
    weite, ab = WEITE, rohr3d.ABSTAND
    # Konturlinien liegen in beiden Netzen um ABSTAND über der Wand, Linien der Enden auf der Kante; eine Kante kann
    # in der STEP zur Kontur und im Editor zum Ende gehören (Ausklinkung) – darum gegen beide Arten
    zurueck, wo_z = _weitester(sk_ + se, mk, me, weite, ab)            # Linie der STEP fehlt im Editor
    senkung = any(k.get("art") == "Senkung" for k in eingaben.get("konturen") or ())
    hin, wo_h = (0.0, None) if senkung else _weitester(mk + me, sk_, se, weite, ab)     # Senkung: Bohrung unter dem Kegel
    wo = wo_z if zurueck >= hin else wo_h
    return max(hin, zurueck), (round(wo[2], 1) if wo else None)


def hinweis(d, x):
    """Text für die Position, wenn die Abweichung d über GRENZE liegt, sonst None."""
    if d is None or d <= GRENZE:
        return None
    lage = f" (bei {_zahl(x)} mm ab Ende A)" if x is not None else ""
    wie = f"über {_zahl(WEITE)}" if d >= WEITE - 1e-6 else f"bis {_zahl(d)}"
    return f"Editor weicht {wie} mm von der STEP ab{lage} – Konturen und Enden im Schneidweg-Rechner prüfen"


def _zahl(x):
    return f"{x:.1f}".replace(".", ",")


def _bewegen(strecken, c, s, sp, sh):
    def b(p):
        return (c * p[0] * sp - s * p[1] + sh[0], s * p[0] * sp + c * p[1] + sh[1], p[2] + sh[2])
    return [(b(p), b(q)) for p, q in strecken]


def _ausrichten(mod_a, st_a, abstand):
    """Lage des Modells eines offenen Profils (Strecken von Ende A) auf die STEP: Drehung um die Achse (0/90/180/270°),
    gespiegelt, Verschiebung über die Schwerpunkte und nächste Punkte. Ergebnis (Abstand, c, s, sp, sh) oder None."""
    sp_ = [p for st in st_a for p in st]
    mp_ = [p for st in mod_a for p in st]
    if not sp_ or not mp_:
        return None
    cs = [sum(q[i] for q in sp_) / len(sp_) for i in range(3)]
    raster = _Raster(st_a, WEITE * 4)
    beste = None
    for sp in (1, -1):
        for w in range(0, 360, 90):
            c, s = round(math.cos(math.radians(w))), round(math.sin(math.radians(w)))
            tp = [p for st in _bewegen(mod_a, c, s, sp, (0, 0, 0)) for p in st]
            sh = [cs[i] - sum(q[i] for q in tp) / len(tp) for i in range(3)]
            for _ in range(4):          # nächste Punkte: Verschiebung nachziehen
                mp = [p for st in _bewegen(mod_a, c, s, sp, sh) for p in st]
                paare = [(p, raster.naechster(p)) for p in mp]
                paare = [(p, q) for p, q in paare if q is not None]
                if not paare:
                    break
                sh = [sh[i] + sum(q[i] - p[i] for p, q in paare) / len(paare) for i in range(3)]
            t = _bewegen(mod_a, c, s, sp, sh)
            dd = max(_weitester(t, [], st_a, WEITE, 0)[0], _weitester(st_a, [], t, WEITE, 0)[0])
            if beste is None or dd < beste[0]:
                beste = (dd, c, s, sp, sh)
    return beste


def _abweichung_offen(st_a, st_k, st_b, mod_a, mod_k, mod_b, wand, abstand):
    """Offenes Profil: Modell an Ende A ausrichten, dann Ende B und Konturen vergleichen. Konturkanten der STEP liegen
    auf beiden Seiten der Wand: STEP → Modell darf um die Wandstärke weiter weg liegen. Ergebnis wie abweichung,
    der Wert über GRENZE_OFFEN auf GRENZE umgerechnet (Hinweis ab GRENZE)."""
    a = _ausrichten(mod_a, st_a, abstand)
    if a is None:
        return None
    dd, c, s, sp, sh = a
    # Enden: die Skizze zeichnet offene Profile ohne Walz-/Biegeradien (bewusst, 2-3 mm an der Rundung) – an den
    # Enden zählt nur, was weiter als die Wandstärke daneben liegt (falsche Gehrung, fehlende Ausklinkung)
    werte = [(max(dd - abstand - wand, 0.0), None)]
    for mod, st, ist_k in ((mod_b, st_b, False), (mod_k, st_k, True)):
        if not st and not mod:
            continue
        mod = _bewegen(mod, c, s, sp, sh)
        hin, wo_h = _weitester(mod, st if ist_k else [], [] if ist_k else st, WEITE + wand, abstand)
        zurueck, wo_z = _weitester(st, mod if ist_k else [], [] if ist_k else mod, WEITE + wand, abstand)
        zurueck = max(zurueck - wand, 0.0)
        if not ist_k:
            hin = max(hin - wand, 0.0)
        werte += [(hin, wo_h), (zurueck, wo_z)]
    d, wo = max(werte, key=lambda x: x[0])
    d = max(d, 0.0)
    # Toleranz der Ausrichtung: bis GRENZE_OFFEN gilt das Teil als wie STEP (Wert dann höchstens GRENZE)
    return (d if d > GRENZE_OFFEN else min(d, GRENZE)), (round(wo[2], 1) if wo else None)
