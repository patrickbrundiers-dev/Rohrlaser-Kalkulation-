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


def teil(prog):
    """Programm aus lst_bahn.programme() → Teil im Format von step_blm.bpf_teil."""
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
    return dict(name=prog["programm"], laenge=prog["laenge"] or max(p[0] for k in konturen for p in k["punkte"]),
                volumen=0.0, querschnitt=dict(form_nr=0, name=name, a=qs.b or qs.d, b=qs.h or qs.d, wand=qs.wand,
                                              r=qs.r, aussen=aussen, innen=innen),
                werkstoff=prog.get("werkstoff") or "", maschine=prog.get("maschine") or "", konturen=konturen)


def streifen_dreiecke(links, rechts, tiefe):
    """Dreiecke eines Fugenstreifens entlang einer offenen Kontur (zwischen den beiden Fugenrändern, durch die Wand)."""
    from step_blm import UEBER, _add, _norm
    (pl, rl), (pr, rr) = links, rechts
    ol = [_add(p, _norm(v), UEBER) for p, v in zip(pl, rl)]
    ul = [_add(p, _norm(v), -(tiefe + UEBER)) for p, v in zip(pl, rl)]
    orr = [_add(p, _norm(v), UEBER) for p, v in zip(pr, rr)]
    ur = [_add(p, _norm(v), -(tiefe + UEBER)) for p, v in zip(pr, rr)]
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
    form, meld = bpf_koerper(teil(prog))
    qs = prog["querschnitt"]
    halb = prog.get("halbspalt") or HALBSPALT
    werkzeuge = []
    for k in prog["konturen"]:
        if not k.get("offen") or k["art"] == lb.REST:
            continue
        s = _occ_dreiecke_koerper(streifen_dreiecke(*lb.streifen(k, qs, halb), max(qs.wand, 1.0) * 1.5))
        if s is None:
            meld.append(f"Kontur {k['nr']} (offen) ließ sich nicht als Werkzeug bauen (übersprungen)")
        else:
            werkzeuge.append(s)
    if werkzeuge:
        form = _vereinheitlicht(_bool("cut", form, werkzeuge))
        meld.append(f"{len(werkzeuge)} offene Kontur(en) als Schnittfuge {2 * halb:.2f} mm")
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
    return koerper_, dict(einheit="mm", meldungen=meld[:20], baugruppe=len(koerper_) > 1, struktur=None,
                          bauteile={})


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
