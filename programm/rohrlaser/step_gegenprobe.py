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
import hashlib
import json
import math

GRENZE = 0.1            # mm: so weit darf eine Linie neben der STEP liegen
SCHRITT = 1.0           # mm: Abtastung der Linien
ZELLE = 2.0             # mm: Raster für die Suche der nächsten Strecke
WEITE = 3.0             # mm: weiter wird nicht gesucht (Abweichung „über 3 mm“)
FORMEN = ("Quadratrohr", "Rechteckrohr", "Rundrohr")
OFFEN = ("L-Profil", "U-Profil", "C-Profil", "Flachstahl")
MERKEN = 2000           # so viele Ergebnisse höchstens merken
_MERKER = {}
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
    """Strecken nach Rasterzellen (je Zelle ihres Hüllquaders, um die Suchweite erweitert): Abstand zur nächsten
    Strecke nur aus den Strecken, deren erweiterter Hüllquader die Zelle des Punkts enthält; ohne solche gilt der
    Abstand als 'weit' (Suchweite selbst). Die Strecken stehen in groben Zellen (Kantenlänge ≥ 2 × Suchweite, je
    Strecke nur wenige statt bis zu 13³ feinen Zellen); die Liste je feiner Zelle wird beim ersten Abfragen daraus
    gefiltert und gemerkt – dieselben Strecken in derselben Reihenfolge wie vorher je feiner Zelle, also dieselben
    Werte (STEP-Tempo 12.11.2026: Übernehmen stand bis 25 s, Gegenprobe offener Profile baute je Lage neu)."""

    def __init__(self, strecken, weite):
        self.strecken, self.weite, self.lang, self.vor = strecken, weite, [], []
        self.k = max(1, math.ceil(2 * weite / ZELLE) + 1)      # feine Zellen je grober Zelle
        self.grob, self.bereich, self.zellen = {}, [], {}
        k = self.k
        for i, (a, b) in enumerate(strecken):
            lo = [math.floor((min(a[j], b[j]) - weite) / ZELLE) for j in range(3)]
            hi = [math.floor((max(a[j], b[j]) + weite) / ZELLE) for j in range(3)]
            if (hi[0] - lo[0] + 1) * (hi[1] - lo[1] + 1) * (hi[2] - lo[2] + 1) > 200000:
                hi = lo         # ungewöhnlich lange Strecke: nur über die Liste (unten)
                self.lang.append(i)
            self.bereich.append((lo, hi))
            ab = (b[0] - a[0], b[1] - a[1], b[2] - a[2])     # vorbereitet wie in _abst gerechnet
            self.vor.append((a, ab, ab[0] ** 2 + ab[1] ** 2 + ab[2] ** 2))
            for x in range(lo[0] // k, hi[0] // k + 1):
                for y in range(lo[1] // k, hi[1] // k + 1):
                    for z in range(lo[2] // k, hi[2] // k + 1):
                        self.grob.setdefault((x, y, z), []).append(i)

    def _kand(self, p):
        zelle = tuple(math.floor(p[j] / ZELLE) for j in range(3))
        kand = self.zellen.get(zelle)
        if kand is None:
            k, bereich = self.k, self.bereich
            kand = [i for i in self.grob.get((zelle[0] // k, zelle[1] // k, zelle[2] // k), ())
                    if bereich[i][0][0] <= zelle[0] <= bereich[i][1][0] and bereich[i][0][1] <= zelle[1] <= bereich[i][1][1]
                    and bereich[i][0][2] <= zelle[2] <= bereich[i][1][2]] + self.lang
            self.zellen[zelle] = kand
        return kand

    def _naechst(self, p):
        """(Abstand, Punkt) zur nächsten Strecke in der Nähe oder None; dieselbe Rechnung wie _abst, Strecken
        vorbereitet und ohne Erzeuger (Tempo)."""
        best = None
        p0, p1, p2 = p
        vor = self.vor
        for i in self._kand(p):
            a, ab, lg = vor[i]
            # sum() wie in _abst (Python summiert Gleitkommazahlen genauer als a + b + c: gleicher Wert)
            f = 0.0 if lg < 1e-12 else max(0.0, min(1.0, sum(((p0 - a[0]) * ab[0], (p1 - a[1]) * ab[1],
                                                              (p2 - a[2]) * ab[2])) / lg))
            q = (a[0] + f * ab[0], a[1] + f * ab[1], a[2] + f * ab[2])
            d = math.dist(p, q)
            if best is None or d < best[0]:
                best = (d, q)
        return best

    def abstand(self, p):
        best = self._naechst(p)
        return self.weite if best is None else best[0]

    def naechster(self, p):
        """Nächster Punkt auf den Strecken in der Nähe oder None."""
        best = self._naechst(p)
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
    from . import ansicht3d
    if not vergleichbar(m, profil, eingaben):
        return None
    try:
        st = ansicht3d.entpacken(m["_netz"])
    except (ValueError, TypeError, KeyError):
        return None
    if not st or not isinstance(st.get("l"), dict):
        return None
    # gemerkt (12.11.2026): die Gegenprobe läuft schon vor dem Prüfdialog (step.rohre_gegenprobe) und beim Übernehmen
    # noch einmal mit denselben Eingaben; gleiche Körper einer Baugruppe haben dieselben Linien
    try:
        schluessel = (hashlib.sha1(json.dumps(st["l"], sort_keys=True).encode()).hexdigest(),
                      json.dumps(profil, sort_keys=True, default=str),
                      json.dumps(eingaben, sort_keys=True, default=str), laenge)
    except (TypeError, ValueError):
        schluessel = None
    if schluessel in _MERKER:
        return _MERKER[schluessel]
    erg = _abweichung(st, profil, eingaben, laenge)
    if schluessel is not None:
        if len(_MERKER) >= MERKEN:
            _MERKER.clear()
        _MERKER[schluessel] = erg
    return erg


def _abweichung(st, profil, eingaben, laenge):
    from . import rohr3d
    try:
        mod = rohr3d.netz_rechnen(wie_konstruiert(eingaben), profil, laenge)
    except (ValueError, TypeError, KeyError, ZeroDivisionError):
        return None
    if not mod:
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
    if senkung:                                                         # Senkung: Bohrung unter dem Kegel
        hin, wo_h = 0.0, None
    else:
        # Konturlinien des Editors (um ABSTAND über der Wand) dürfen auch auf einer Kante des Endes der STEP liegen:
        # Hinterschnitt am Ende (T-Schlitz, Schlüsselloch-Schlitz) ist im Editor eine Sonderkontur „Teil von Ende“
        # (Patrick 03.11.2026), in der STEP Teil des Endes
        hin, wo_h = max(_weitester(mk, sk_ + se, [], weite, ab), _weitester(me, sk_, se, weite, ab),
                        key=lambda x: x[0])
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


def _mittel(a, raster, weite):
    """Mittlerer Abstand der Punkte der Strecken a (je SCHRITT abgetastet) zu den Strecken des Rasters (höchstens weite)."""
    summe, n_ = 0.0, 0
    for p, q in a:
        n = max(1, int(math.dist(p, q) / SCHRITT))
        for k in range(n + 1):
            summe += min(raster.abstand(tuple(p[i] + (q[i] - p[i]) * k / n for i in range(3))), weite)
            n_ += 1
    return summe / n_ if n_ else weite


def _mitte(punkte):
    """Mitte des Hüllquaders der Punkte."""
    return [(min(q[i] for q in punkte) + max(q[i] for q in punkte)) / 2 for i in range(3)]


def _ausrichten(mod_a, st_a, abstand, mod_rest=(), st_rest=()):
    """Lage des Modells eines offenen Profils (Strecken von Ende A) auf die STEP: Drehung um die Achse (0/90/180/270°),
    gespiegelt, Verschiebung über die Schwerpunkte bzw. die Mitten der Hüllquader und nächste Punkte. Gewählt wird die
    Lage mit dem kleinsten mittleren Abstand: der größte Abstand ist bei WEITE gekappt und unterscheidet falsche Lagen
    nicht, und der Schwerpunkt der Punkte hängt an der Teilung der Linien (gewalzte Radien der STEP sind fein
    geteilt) – Winkel mit Gehrung blieben so in einer falschen Lage hängen und galten als „3 mm neben der STEP“
    (Patrick 10.11.2026, Messreihe an echten Baugruppen). Ergebnis (Abstand, c, s, sp, sh) oder None."""
    sp_ = [p for st in st_a for p in st]
    mp_ = [p for st in mod_a for p in st]
    if not sp_ or not mp_:
        return None
    cs = [sum(q[i] for q in sp_) / len(sp_) for i in range(3)]
    cm = _mitte(sp_)
    weit = WEITE * 4
    raster = _Raster(st_a, weit)
    # Ende B und Konturen entscheiden mit: ein Ende A allein (gerade, Gehrung am gleichschenkligen Winkel) passt oft
    # in zwei Lagen, gespiegelte Teile eines Rahmens bekamen so die Lage ihres Gegenstücks
    mod_rest, st_rest = list(mod_rest), list(st_rest)
    raster_rest = _Raster(st_rest, weit) if mod_rest and st_rest else None
    beste = None
    for sp in (1, -1):
        for w in range(0, 360, 90):
            c, s = round(math.cos(math.radians(w))), round(math.sin(math.radians(w)))
            tp = [p for st in _bewegen(mod_a, c, s, sp, (0, 0, 0)) for p in st]
            tm = _mitte(tp)
            for sh in ([cs[i] - sum(q[i] for q in tp) / len(tp) for i in range(3)], [cm[i] - tm[i] for i in range(3)]):
                for _ in range(8):          # nächste Punkte: Verschiebung nachziehen
                    mp = [p for st in _bewegen(mod_a, c, s, sp, sh) for p in st]
                    paare = [(p, raster.naechster(p)) for p in mp]
                    paare = [(p, q) for p, q in paare if q is not None]
                    if not paare:
                        break
                    sh = [sh[i] + sum(q[i] - p[i] for p, q in paare) / len(paare) for i in range(3)]
                t = _bewegen(mod_a, c, s, sp, sh)
                guete = _mittel(t, raster, weit) + _mittel(st_a, _Raster(t, weit), weit)
                if raster_rest is not None:
                    tr = _bewegen(mod_rest, c, s, sp, sh)
                    guete += _mittel(tr, raster_rest, weit) + _mittel(st_rest, _Raster(tr, weit), weit)
                if beste is None or guete < beste[0]:
                    beste = (guete, c, s, sp, sh)
    _, c, s, sp, sh = beste
    t = _bewegen(mod_a, c, s, sp, sh)
    dd = max(_weitester(t, [], st_a, WEITE, 0)[0], _weitester(st_a, [], t, WEITE, 0)[0])
    return dd, c, s, sp, sh


def _abweichung_offen(st_a, st_k, st_b, mod_a, mod_k, mod_b, wand, abstand):
    """Offenes Profil: Modell an Ende A ausrichten, dann Ende B und Konturen vergleichen. Konturkanten der STEP liegen
    auf beiden Seiten der Wand: STEP → Modell darf um die Wandstärke weiter weg liegen. Ergebnis wie abweichung,
    der Wert über GRENZE_OFFEN auf GRENZE umgerechnet (Hinweis ab GRENZE)."""
    a = _ausrichten(mod_a, st_a, abstand, mod_k + mod_b, st_k + st_b)
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
