"""Winkel bzw. U aus einem größeren Profil gleicher Form als virtuelles Bauteil messen (Patrick 26.10.2026: „ein
virtuelles Rohrbauteil anlegen, um den Schnittweg zu ermitteln“, Beispiel Winkel 33x30x6 nur als 60x40x6 vorrätig).

Gefertigt wird das Teil aus dem größeren Profil: an Ende A und Ende B bleibt je ein Steg STEG (2 mm) des ganzen
größeren Querschnitts stehen, dazwischen werden die Schenkel auf das gezeichnete Maß gekürzt. Das virtuelle Bauteil
ist das gezeichnete Teil ∪ die zwei Stege; es wird wie jedes Profil gemessen (Lage und Querschnitt aus dem größeren
Profil über die ganze Länge, Konturen und Enden aus dem virtuellen Bauteil). So stimmen Längsschnitte, Querschnitte
um die Stege, Gehrungen, Bohrungen und Ausschnitte genau wie in der Zeichnung; Bohrungen im weggeschnittenen
Bereich fallen weg. Die Stege folgen den Endflächen (eben: gerade, Gehrung, Schrägschnitt); sind die Enden nicht
eben, gibt es kein virtuelles Bauteil (das Programm rechnet dann mit der Formel, schneidweg.schenkel_kuerzen).

Das Ziel-Profil kommt aus dem Programm (STEP-Import.exe --stege „Form|A|B|Wand“, step_geometrie.einstellen); die
Datei bleibt unverändert."""
import step_geometrie as g
from step_offenes_rohr import STEG, _bool, _halbraum, _netz_koerper, _vereinen

FORMEN = ("L-Profil", "U-Profil")
HINWEIS = "Aus größerem Profil"
TOL = 0.3           # mm, Maße gleich


def ziel_lesen(text):
    """'L-Profil|60|40|6' -> dict(form, a, b, wand) oder None."""
    try:
        form, a, b, wand = str(text or "").split("|")
        return dict(form=form, a=float(a), b=float(b), wand=float(wand))
    except ValueError:
        return None


def _enden_eben(lok, zmin, zmax, tol=0.05):
    """Ebene je Ende (gp_Pln): die ebenen Flächen quer zur Achse, die bis an zmin bzw. zmax reichen (Ausklinkungen
    und Ausschnitte dazwischen zählen nicht); None, wenn ein Ende nicht in einer Ebene liegt."""
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.BRepBndLib import BRepBndLib
    from OCP.Bnd import Bnd_Box
    from OCP.GeomAbs import GeomAbs_Plane
    from OCP.TopAbs import TopAbs_FACE
    from OCP.TopoDS import TopoDS
    enden = {0: [], 1: []}
    for f in g._liste(lok, TopAbs_FACE):
        s = BRepAdaptor_Surface(TopoDS.Face(f))
        if s.GetType() != GeomAbs_Plane or abs(s.Plane().Axis().Direction().Z()) < 0.2:
            continue
        bb = Bnd_Box()
        BRepBndLib.Add_s(f, bb, False)
        if bb.CornerMin().Z() <= zmin + tol:
            enden[0].append(s.Plane())
        elif bb.CornerMax().Z() >= zmax - tol:
            enden[1].append(s.Plane())
    out = []
    for k in (0, 1):
        if not enden[k]:
            return None
        p0 = enden[k][0]
        for p in enden[k][1:]:
            if not p.Axis().Direction().IsParallel(p0.Axis().Direction(), 1e-4) or p0.Distance(p.Location()) > 0.01:
                return None
        out.append(p0)
    return out


def _querschnitt(lok, zmin, zmax):
    """Regelquerschnitt in der Mitte: (Draht, x0, y0, x1, y1) oder None."""
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib
    for anteil in (0.5037, 0.4137, 0.5937, 0.3137, 0.6937):
        ws = g._schnitt(lok, zmin + anteil * (zmax - zmin))
        if len(ws) == 1:
            bb = Bnd_Box()
            BRepBndLib.AddOptimal_s(ws[0][1], bb, False, False)
            return ws[0][1], bb.CornerMin().X(), bb.CornerMin().Y(), bb.CornerMax().X(), bb.CornerMax().Y()
    return None


def _rechteck(u0, v0, u1, v1, abb):
    """Rechteck im Querschnitt (u, v im Bezug des Profils, abb -> x, y) als Fläche bei z = 0."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakePolygon
    from OCP.gp import gp_Pnt
    poly = BRepBuilderAPI_MakePolygon()
    for u, v in ((u0, v0), (u1, v0), (u1, v1), (u0, v1)):
        poly.Add(gp_Pnt(*abb(u, v), 0.0))
    poly.Close()
    return BRepBuilderAPI_MakeFace(poly.Wire()).Face()


def verlaengerungen(draht, x0, y0, x1, y1, form, ziel, d):
    """Rechtecke (Flächen bei z = 0, lokales System), um die die Schenkel des gezeichneten Querschnitts länger sind
    als im größeren Profil; [] wenn nichts fehlt, None wenn der Querschnitt nicht passt."""
    seiten = g._seiten_belegung(g._strecken(draht), x0, y0, x1, y1)
    lang = {"links": y1 - y0, "rechts": y1 - y0, "unten": x1 - x0, "oben": x1 - x0}
    voll = {n for n, ab in seiten.items() if len(ab) == 1 and ab[0][1] - ab[0][0] >= 0.6 * lang[n]}
    w, h = x1 - x0, y1 - y0
    if form == "L-Profil":
        if len(voll) != 2 or ("links" in voll) == ("rechts" in voll):
            return None
        sx = 1.0 if "links" in voll else -1.0         # Ecke (Ferse) des Winkels
        sy = 1.0 if "unten" in voll else -1.0
        hx, hy = (x0 if sx > 0 else x1), (y0 if sy > 0 else y1)

        def abb(u, v):
            return hx + sx * u, hy + sy * v
        lang_z, kurz_z = max(ziel["a"], ziel["b"]), min(ziel["a"], ziel["b"])
        lx, ly = (lang_z, kurz_z) if w >= h else (kurz_z, lang_z)
        if lx < w - TOL or ly < h - TOL:
            return None
        out = []
        if lx > w + TOL:
            out.append(_rechteck(w / 2, 0.0, lx, d, abb))
        if ly > h + TOL:
            out.append(_rechteck(0.0, h / 2, d, ly, abb))
        return out
    # U: drei Seiten voll, die offene Seite liegt dem Steg gegenüber; die Flansche werden zur offenen Seite länger
    if len(voll) != 3:
        return None
    offen = next(n for n in seiten if n not in voll)
    steg = lang[offen]
    breite = w if offen in ("links", "rechts") else h
    if abs(steg - ziel["a"]) > TOL or ziel["b"] < breite - TOL:
        return None
    mehr = ziel["b"] - breite
    if mehr <= TOL:
        return []
    # u längs der Flansche ab der Stegseite, v quer (0 … Steghöhe)
    if offen == "rechts":
        def abb(u, v):
            return x0 + u, y0 + v
    elif offen == "links":
        def abb(u, v):
            return x1 - u, y0 + v
    elif offen == "oben":
        def abb(u, v):
            return x0 + v, y0 + u
    else:
        def abb(u, v):
            return x0 + v, y1 - u
    return [_rechteck(breite / 2, 0.0, ziel["b"], d, abb), _rechteck(breite / 2, steg - d, ziel["b"], steg, abb)]


def mit_stegen(solid, t, ziel, datei="", koerper=1, netz=False):
    """Messung des virtuellen Bauteils (Teil ∪ Stege des größeren Profils ziel) oder None (andere Form, nicht
    größer, Enden nicht eben, Messung passt nicht). Das Netz von t bekommt die Stege als Art EO."""
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse
    from OCP.BRepPrimAPI import BRepPrimAPI_MakePrism
    from OCP.gp import gp_Trsf, gp_Vec
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
    form = t.profilform if t is not None else None
    if not ziel or form not in FORMEN or ziel["form"] != form or t.laenge < 4 * STEG:
        return None
    d = t.wandstaerke or ziel["wand"]
    if abs(d - ziel["wand"]) > 0.15:
        return None
    ax3, _ = g._lage(solid)
    lok = g._transformiere(solid, ax3)
    zmin, zmax = g._z_bereich(lok)
    qs = _querschnitt(lok, zmin, zmax)
    if qs is None:
        return None
    flaechen = verlaengerungen(*qs, form, ziel, d)
    if not flaechen:
        return None
    ebenen = _enden_eben(lok, zmin, zmax)
    if ebenen is None:
        return None
    laenge = zmax - zmin
    z0, h = zmin - laenge - 10.0, 3 * laenge + 20.0
    verschieben = gp_Trsf()
    verschieben.SetTranslation(gp_Vec(0, 0, z0))
    zusatz = None
    for f in flaechen:
        p = BRepPrimAPI_MakePrism(BRepBuilderAPI_Transform(f, verschieben, True).Shape(), gp_Vec(0, 0, h)).Shape()
        if zusatz is None:
            zusatz = p
        else:
            fu = BRepAlgoAPI_Fuse(zusatz, p)
            fu.SetFuzzyValue(g.FUZZY)
            fu.Build()
            zusatz = fu.Shape()
    innen = (0.0, 0.0, (zmin + zmax) / 2)
    for pl in ebenen:           # nur zwischen den Endflächen
        zusatz = zusatz and _bool("und", zusatz, _halbraum(pl, 0.0, innen))
    if zusatz is None:
        return None
    stege = []
    for pl, d_, ref in ((ebenen[0], STEG, (0, 0, z0)), (ebenen[1], -STEG, (0, 0, z0 + h))):
        s = _bool("und", zusatz, _halbraum(pl, d_, ref))
        if s is None:
            return None
        stege.append(s)
    stege = _bool("plus", stege[0], stege[1])
    zu = _vereinen(solid, [stege], ax3, False) if stege is not None else None
    quer = _vereinen(solid, [zusatz], ax3, False)
    if zu is None or quer is None:
        return None
    m = g._profil_messen(zu, datei, koerper, False, quer=quer)
    lang_z, kurz_z = max(ziel["a"], ziel["b"]), min(ziel["a"], ziel["b"])
    soll = (lang_z, kurz_z) if form == "L-Profil" else (ziel["a"], ziel["b"])
    if m.profilform != form or abs(m.abm_a - soll[0]) > TOL or abs(m.abm_b - soll[1]) > TOL:
        return None
    for name in ("bauteil", "pfad", "knoten", "verbund", "anbauteile", "trennung", "gravur_anbau"):
        if hasattr(t, name):
            setattr(m, name, getattr(t, name))
    m.netz = t.netz
    m.hinweise.append(f"{HINWEIS}: {form} {t.abm_a:g}x{t.abm_b:g}x{d:g} aus {soll[0]:g}x{soll[1]:g}x{d:g}, "
                      f"Schenkel gekürzt, je ein Steg {STEG:g} mm an Ende A und B (virtuelles Bauteil gemessen)")
    m.sicherheit["stege"] = "virtuell"
    # Volumen mit Stegen (Gewicht, so gelasert); die Spalte volumen bleibt das gezeichnete Teil
    m.sicherheit["volumen_virtuell"] = f"{g._volumen(zu):.1f}"
    g.virtuell_ablegen(zu, koerper)
    if netz:
        try:
            _netz_koerper(t, stege, ax3, 0.05, art="ES")
            m.netz = t.netz
        except Exception:  # noqa: BLE001, S110 – ohne Anzeige der Stege bleibt die Messung gültig
            pass
    if m.netz:
        # das Netz steht im System des gezeichneten Teils (Ende A auf seiner Schwerlinie), Lage und Konturen der
        # Messung im System des größeren Profils: Netz umrechnen, sonst lag das Teil in Satz und Baugruppe um den
        # Unterschied der Schwerlinien verschoben (Grundregel: Teile nie verschieben)
        _netz_umrechnen(m.netz, t, m)
    return m


def _netz_umrechnen(netz, von, nach):
    """Punkte und Kantenzüge des Netzes vom Rohr-System der Messung von in das der Messung nach umrechnen."""
    from OCP.gp import gp_Pnt, gp_Trsf
    a, b = gp_Trsf(), gp_Trsf()
    a.SetTransformation(g._rohr_ax3(von))
    b.SetTransformation(g._rohr_ax3(nach))
    tr = b.Multiplied(a.Inverted())

    def neu(pk):
        out = []
        for i in range(0, len(pk) - 2, 3):
            q = gp_Pnt(pk[i], pk[i + 1], pk[i + 2]).Transformed(tr)
            out += [round(q.X(), 4), round(q.Y(), 4), round(q.Z(), 4)]
        return out
    if netz.get("p"):
        netz["p"] = neu(netz["p"])
    for art, zuege in (netz.get("l") or {}).items():
        netz["l"][art] = [neu(z) for z in zuege]
