"""TRUMPF-LST wie eine STEP-Datei messen (Patrick 24.11.2026: „So ist der programmierte Schneidweg. Kannst du das
aus der .lst auch so auslesen“).

Der Schneidweg kommt aus dem NC-Teil der LST (rohrlaser/lst_bahn.py). Das Rohr wird wie beim BLM-Programm
(step_blm.bpf_koerper) exakt aus dem Querschnitt gebaut (Prisma außen minus innen), jede Kontur und jeder
Trennschnitt wird lagegenau abgezogen, Kreise werden exakte Bohrungen. Restzerteilung (Schrott zerschneiden) und
Anfahrten bleiben außen vor. Ein Programm mit mehreren verschiedenen Teilen wird nicht gebaut (nur Meldung).

Liegt neben einer TUBX eine gleichnamige LST, misst step_tubx das Teil aus der LST (genauer als das Netz)."""
import math
from pathlib import Path

ENDUNG = ".lst"
HALBSPALT = 0.1         # halbe Schnittfuge, wenn das Programm sie nicht verrät (Faserlaser, Stahl) [mm]


def ist_lst(pfad):
    return Path(str(pfad)).suffix.lower() == ENDUNG


def _topologie(b, h, r, d=0.0):
    """Querschnitt im Format von step_blm (Ebene x = 0): Strecken und Viertelbögen bzw. ein Vollkreis."""
    if d > 0:
        return [dict(art="bogen", c=(0.0, 0.0, 0.0), r=d / 2, w=360.0, n=(1.0, 0.0, 0.0))]
    ay, az = b / 2 - r, h / 2 - r
    out = []
    if ay > 1e-9:
        out += [dict(art="strecke", a=(0.0, -ay, h / 2), b=(0.0, ay, h / 2)),
                dict(art="strecke", a=(0.0, ay, -h / 2), b=(0.0, -ay, -h / 2))]
    if az > 1e-9:
        out += [dict(art="strecke", a=(0.0, b / 2, az), b=(0.0, b / 2, -az)),
                dict(art="strecke", a=(0.0, -b / 2, -az), b=(0.0, -b / 2, az))]
    if r > 1e-9:
        for sy, sz in ((1, 1), (1, -1), (-1, -1), (-1, 1)):
            out.append(dict(art="bogen", c=(0.0, sy * ay, sz * az), r=r, w=90.0, n=(1.0, 0.0, 0.0)))
    return out


STEG_MAX = 2.0          # offene Konturen, deren Enden so nah aneinander liegen, bilden eine Öffnung mit Stegen [mm]


def ketten(prog):
    """Offene Konturen, die zusammen eine Öffnung umschließen (TubeCAM schneidet große Ausschnitte und Kerben als zwei
    offene Schnitte mit kleinen Haltestegen dazwischen, Microjoints): Liste [(kontur_nrn, kontur, stege)]. kontur ist
    die Fläche innerhalb der programmierten Wege (bahn, ohne Versatz; die Schnittfugen der einzelnen Schnitte bleiben
    eigene Werkzeuge), stege = Abstände der Enden [mm]. Jedes Ende eines Glieds liegt höchstens STEG_MAX vom Anfang des
    nächsten entfernt, das letzte schließt zum ersten. Schnittlänge, Einstiche und Konturklassen ändern sich nicht (nur
    die Geometrie: der Abfall zwischen den Schnitten fällt wie in STEP und TUBX heraus; Importengine 2.0, LST 10186133
    P30: Fenster 165 × 75 mm fehlte, 24.114 mm³ zu viel)."""
    from rohrlaser import lst_bahn as lb
    qs = prog["querschnitt"]
    frei = [k for k in prog["konturen"] if k.get("offen") and k["art"] != lb.REST and len(k["bahn"]) >= 2]
    out, benutzt = [], set()
    for start in frei:
        if start["nr"] in benutzt:
            continue
        glieder, pk, ss, stege = [start["nr"]], list(start["bahn"]), list(start["s_bahn"]), []
        rk = list(start["richtung"])  # offene Konturen: richtung gehört zur bahn
        while True:
            if math.dist(pk[-1], pk[0]) <= STEG_MAX and len(glieder) > 1:
                stege.append(math.dist(pk[-1], pk[0]))
                break
            best = None
            for k in frei:
                if k["nr"] in benutzt or k["nr"] in glieder:
                    continue
                for umgedreht in (False, True):
                    b = k["bahn"][::-1] if umgedreht else k["bahn"]
                    d = math.dist(pk[-1], b[0])
                    if d <= STEG_MAX and (best is None or d < best[0]):
                        best = (d, k, umgedreht)
            if best is None or len(glieder) >= 8:
                glieder = None
                break
            d, k, umgedreht = best
            stege.append(d)
            glieder.append(k["nr"])
            bahn, sb = (k["bahn"][::-1], k["s_bahn"][::-1]) if umgedreht else (k["bahn"], k["s_bahn"])
            rich = k["richtung"]
            pk += list(bahn)
            ss += list(sb)
            rk += list(rich[::-1] if umgedreht else rich)
        if not glieder:
            continue
        if not _umfang_ok(pk):
            # weiter als SPANNE_MAX um das Rohr: nur die Schnittfugen der Einzelschnitte (wie bisher), Hinweis
            out.append((glieder, None, stege))
            benutzt.update(glieder)
            continue
        pk.append(pk[0])
        ss.append(ss[0])
        rk.append(rk[0])
        from step_blm import UEBER
        tiefe = innen_tiefe(pk, max(qs.wand, 1.0) * 1.5, qs) - UEBER
        k_neu = dict(nr=glieder[0], block="", art=lb.KONTUR, punkte=pk, richtung=rk, s=ss, offen=False,
                     laenge=lb._laenge(pk), tiefe=tiefe)
        benutzt.update(glieder)
        out.append((glieder, k_neu, stege))
    return out


SPANNE_MAX = 180.0      # Öffnung aus offenen Schnitten: größter Umfangswinkel für das Werkzeug [Grad]


def _umfang_ok(punkte):
    """True, wenn die Öffnung höchstens SPANNE_MAX um das Rohr reicht. Der Deckel des Werkzeugs liegt eben über der
    Kontur (über die Bogenhöhe angehoben, werkzeug_dreiecke); reicht sie weiter (Kerben zum Abkanten über drei Seiten,
    LST 10186133 P10: 305°), läge der Deckel im Rohr und das Werkzeug zerschnitte das Teil."""
    from step_blm import _winkel_lauf
    w = _winkel_lauf(punkte)
    return math.degrees(max(w) - min(w)) <= SPANNE_MAX


def teil(prog, dazu=()):
    """Programm aus lst_bahn.programme() → Teil im Format von step_blm.bpf_teil. dazu: weitere geschlossene Konturen
    (Öffnungen aus ketten())."""
    from rohrlaser import lst_bahn as lb
    qs = prog["querschnitt"]
    if qs.rund:
        aussen, innen = _topologie(0, 0, 0, qs.d), (_topologie(0, 0, 0, qs.d - 2 * qs.wand)
                                                    if qs.d > 2 * qs.wand > 0 else [])
        name = f"Ø{qs.d:g}×{qs.wand:g}"
    else:
        aussen = _topologie(qs.b, qs.h, qs.r)
        ri = max(qs.r - qs.wand, 0.0)
        innen = _topologie(qs.b - 2 * qs.wand, qs.h - 2 * qs.wand, ri) if qs.wand > 0 else []
        name = f"{qs.b:g}×{qs.h:g}×{qs.wand:g}"
    konturen = [dict(nr=k["nr"], art=k["art"], punkte=k["punkte"], richtung=k["richtung"], laenge=k["laenge"])
                for k in prog["konturen"] if k["art"] in (lb.KONTUR, lb.TRENN) and not k.get("offen")]
    konturen += [dict(nr=k["nr"], art=k["art"], punkte=k["punkte"], richtung=k["richtung"], laenge=k["laenge"],
                      tiefe=k.get("tiefe")) for k in dazu]
    return dict(name=prog["programm"], laenge=prog["laenge"] or max(p[0] for k in konturen for p in k["punkte"]),
                volumen=0.0, querschnitt=dict(form_nr=0, name=name, a=qs.b or qs.d, b=qs.h or qs.d, wand=qs.wand,
                                              r=qs.r, aussen=aussen, innen=innen),
                werkstoff=prog.get("werkstoff") or "", maschine=prog.get("maschine") or "", konturen=konturen)


ECKE_REST = 0.05        # Werkzeug endet an einer Rohrecke so weit vor dem Mittelpunkt des Eckenradius [mm]


def innen_tiefe(punkte, tiefe, qs=None):
    """Wie tief ein Werkzeug unter die Oberfläche reicht: tiefe + UEBER. Berührt der Streifen eine Rohrecke (ein Punkt
    auf dem Eckenradius r oder an seinem Anfang) und reicht diese Tiefe bis an den Mittelpunkt des Radius
    (≥ r − ECKE_REST), dann für den ganzen Streifen nur bis zur Mitte zwischen Innenwand und Mittelpunkt
    (Wand + (r − Wand) / 2). Sonst träfen sich die inneren Werkzeugpunkte über die Ecke im Mittelpunkt bzw. liefen
    über ihn hinaus: Dreiecke ohne Fläche, das Werkzeug schneidet sich selbst (Importengine 2.0, LST 10186133 P10:
    60×40×2 R 4, Tiefe 3 + 1 = 4 = R; Nähen über 20 min). Das Werkzeug reicht weiter sicher durch die Wand, die
    Schnittfuge (Seitenwände des Werkzeugs) bleibt gleich. Nur wenn der Radius größer als die Wand ist."""
    from step_blm import UEBER
    t = tiefe + UEBER
    if qs is None or qs.rund or qs.r <= 0 or t < qs.r - ECKE_REST or qs.r - qs.wand <= 2 * ECKE_REST:
        return t
    ay, az = qs.b / 2 - qs.r, qs.h / 2 - qs.r
    if any(abs(p[1]) >= ay - 1e-6 and abs(p[2]) >= az - 1e-6 for p in punkte):
        return qs.wand + (qs.r - qs.wand) / 2
    return t


def streifen_dreiecke(links, rechts, tiefe, qs=None):
    """Dreiecke eines Fugenstreifens entlang einer offenen Kontur (zwischen den beiden Fugenrändern, durch die Wand).
    qs (lst_bahn.Querschnitt): Tiefe an Rohrecken begrenzen (innen_tiefe)."""
    from step_blm import UEBER, _add, _norm
    (pl, rl), (pr, rr) = links, rechts
    t = innen_tiefe(pl + pr, tiefe, qs)
    ol = [_add(p, _norm(v), UEBER) for p, v in zip(pl, rl)]
    ul = [_add(p, _norm(v), -t) for p, v in zip(pl, rl)]
    orr = [_add(p, _norm(v), UEBER) for p, v in zip(pr, rr)]
    ur = [_add(p, _norm(v), -t) for p, v in zip(pr, rr)]
    tri = []
    for i in range(len(pl) - 1):
        j = i + 1
        for a, b, c, d in ((ol[i], ol[j], orr[j], orr[i]), (ul[i], ur[i], ur[j], ul[j]),
                           (ol[i], ul[i], ul[j], ol[j]), (orr[i], orr[j], ur[j], ur[i])):
            tri += [(a, b, c), (a, c, d)]
    for i in (0, len(pl) - 1):
        tri += [(ol[i], orr[i], ur[i]), (ol[i], ur[i], ul[i])]
    return tri


def koerper(prog):
    """(Shape, Meldungen) eines Programms: geschlossene Konturen und Trennschnitte wie beim BPF, offene Konturen als
    Fugenstreifen; abgetrennte Abfallstücke fallen weg (größter Körper bleibt)."""
    from rohrlaser import lst_bahn as lb
    from step_blm import _bool, _occ_dreiecke_koerper, _vereinheitlicht, bpf_koerper
    kt = ketten(prog)
    form, meld = bpf_koerper(teil(prog, [k for _, k, _ in kt if k is not None]))
    prog["abfall_offen"] = sum(1 for _, k, _ in kt if k is None)
    for glieder, k, stege in kt:
        t = (f"Konturen {', '.join(map(str, glieder))} (offen) umschließen zusammen eine Öffnung mit {len(stege)} "
             f"Steg(en) {', '.join(f'{s:.1f}' for s in stege)} mm")
        meld.append(t + (": Abfall entfernt wie in STEP" if k is not None else
                         f" über mehr als {SPANNE_MAX:.0f}° des Umfangs: nur die Schnittfugen abgezogen, Abfall "
                         "bleibt im Körper (Volumen und Gewicht zu hoch, bitte mit STEP/TUBX prüfen)"))
    qs = prog["querschnitt"]
    halb = prog.get("halbspalt") or HALBSPALT
    werkzeuge, offene = [], 0
    for k in prog["konturen"]:
        if not k.get("offen") or k["art"] == lb.REST:
            continue
        offene += 1
        # je Stück ein Werkzeug: an Knicken mit Bahnstücken kürzer als die Fuge geteilt (lb.streifen_stuecke)
        for links, rechts in lb.streifen_stuecke(k, qs, halb):
            s = _occ_dreiecke_koerper(streifen_dreiecke(links, rechts, max(qs.wand, 1.0) * 1.5, qs))
            if s is None:
                meld.append(f"Kontur {k['nr']} (offen) ließ sich nicht als Werkzeug bauen (übersprungen)")
            else:
                werkzeuge.append(s)
    if werkzeuge:
        form = _vereinheitlicht(_bool("cut", form, werkzeuge))
        meld.append(f"{offene} offene Kontur(en) als Schnittfuge {2 * halb:.2f} mm")
    if not prog.get("halbspalt"):
        meld.append(f"Schnittfuge nicht aus dem Programm bestimmbar: {2 * HALBSPALT:.1f} mm angenommen")
    return form, meld


def text(prog):
    qs = prog["querschnitt"]
    prof = f"Ø{qs.d:g}×{qs.wand:g}" if qs.rund else f"{qs.b:g}×{qs.h:g}×{qs.wand:g} R {qs.r:g}"
    t = (f"aus TRUMPF-LST{', ' + prog['maschine'] if prog.get('maschine') else ''}: Profil {prof} exakt, "
         f"{prog['einstiche']} Schneidwege, Schnittlänge am Material {prog['schnittlaenge']:.0f} mm")
    if prog.get("maschinenweg"):
        t += f" (Maschinenweg laut LST {prog['maschinenweg']:.0f} mm mit Anfahrten und Ecken)"
    return t


def lies_lst_info(pfad):
    """LST lesen: (Körper, Info) wie step_geometrie.lies_step_info. Je Programm ein Körper."""
    from rohrlaser import lst_bahn as lb
    progs = lb.lesen(pfad)
    if not progs:
        raise ValueError("LST ohne lesbaren Schneidweg (kein NC-Teil mit Konturen)")
    koerper_, meld = [], []
    for p in progs:
        if p["teile_im_programm"] > 1:
            meld.append(f"{p['programm']}: {p['teile_im_programm']} verschiedene Teile in einem Programm – nicht "
                        "gebaut (bitte STEP oder TUBX je Teil)")
            continue
        form, m = koerper(p)
        koerper_.append(("Volumenkörper", form))
        meld += m
        meld.append(f"{p['programm']}: " + text(p))
    if not koerper_:
        raise ValueError("; ".join(meld) or "LST ohne messbares Teil")
    # abfall_offen: Öffnungen, deren Abfall im Körper blieb (ketten, über mehr als SPANNE_MAX): für die Gegenprobe
    return koerper_, dict(einheit="mm", meldungen=meld[:20], baugruppe=len(koerper_) > 1, struktur=None,
                          bauteile={}, abfall_offen=sum(p.get("abfall_offen") or 0 for p in progs), aus_programm=True)


def lst_daneben(pfad, programm=""):
    """Gleichnamige LST neben einer Datei (TUBX), deren Programm passt, oder None."""
    pfad = Path(str(pfad))
    for q in pfad.parent.glob("*"):
        if q.suffix.lower() == ENDUNG and q.stem.lower() == pfad.stem.lower():
            return q
    return None


def volumen(form):
    from step_blm import volumen as v
    return v(form)


if __name__ == "__main__":       # Prüfen: python step_lst.py DATEI.lst
    import sys
    for a in sys.argv[1:]:
        k, info = lies_lst_info(a)
        for (_, f) in k:
            print(a, f"Volumen {volumen(f):.1f} mm³")
        print("\n".join(info["meldungen"]))
        _ = math
