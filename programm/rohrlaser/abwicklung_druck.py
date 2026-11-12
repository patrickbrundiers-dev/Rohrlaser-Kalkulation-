"""Abwicklung 1:1 drucken (Plan PROfirst-/LogiTRACE-Handbücher 12.11.2026, I4).

LogiTRACE druckt Abwicklungen im Maßstab 1:1 auf mehrere Blätter, um sie auszuschneiden, um das Rohr zu wickeln und
anzureißen. Hier: die Abwicklung einer Rohrposition (Mantel mit Schnittkanten der Enden, Innenkonturen und Gravuren,
wie stangen_abwicklung.teil) als PDF im Maßstab 1:1 auf A4-Blättern hochkant. Jedes Blatt hat Passmarken (Kreuze in
den Ecken des Druckbereichs mit gemeinsamen Koordinaten), seine Lage „Blatt Zeile/Spalte“ und einen 100-mm-Prüfbalken
(Drucker auf „Tatsächliche Größe“ stellen, nicht „An Seite anpassen“). Danach eine Koordinatenliste: je 10 mm des
Umfangs der Abstand der Schnittkante A und B vom Teilende, zum Anreißen von Hand. Nur Ausgabe, ändert nichts."""
import math

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from . import schneidweg as sw, skizze as sk, stangen_abwicklung as sa

RAND = 12 * mm                   # Druckrand je Seite
SCHRITT_LISTE = 10.0             # mm am Umfang je Zeile der Koordinatenliste


def daten(p, profil):
    """Abwicklung der Position: dict(laenge, umfang, umriss=[(x, s)] mm, konturen=[[(x, s)]], la, lb (Schnittlinien
    [(s, Abstand vom Ende)])). ValueError ohne Querschnitt oder Länge."""
    if not profil:
        raise ValueError("Abwicklung: Profil fehlt.")
    L = float(p.get("laenge") or 0)
    if L <= 0:
        raise ValueError("Abwicklung: Länge fehlt.")
    qs = sk.Querschnitt(profil)
    if qs.umfang <= 0:
        raise ValueError("Abwicklung: Querschnitt ohne Umfang.")
    e = sw.aus_position(sw.lesen(p.get("technik")), p, profil)[0]
    form = sa.grundform(qs, e, L)
    t = sa.teil(qs, dict(ref=None, pos=p.get("pos"), artikel=p.get("artikel"), laenge=L, von=0.0, bis=L), e, form)
    return dict(laenge=L, umfang=qs.umfang, umriss=t["umriss"], konturen=[k["punkte"] for k in t["konturen"]],
                la=form[0], lb=form[1])


def koordinaten(d, schritt=SCHRITT_LISTE):
    """[(s, Abstand Kante A vom Ende A, Abstand Kante B vom Ende B)] je schritt mm am Umfang."""
    n = max(int(math.ceil(d["umfang"] / schritt)), 1)
    out = []
    for i in range(n + 1):
        s = min(i * schritt, d["umfang"])
        out.append((s, sa._linie_bei(d["la"], s), sa._linie_bei(d["lb"], s)))
    return out


def blaetter(breite_mm, hoehe_mm, seite=A4):
    """Anzahl Blätter (Spalten, Zeilen) für eine Fläche breite × höhe in mm."""
    bw, bh = (seite[0] - 2 * RAND) / mm, (seite[1] - 2 * RAND) / mm
    return max(int(math.ceil(breite_mm / bw - 1e-9)), 1), max(int(math.ceil(hoehe_mm / bh - 1e-9)), 1)


def _kreuz(c, x, y, r=4 * mm):
    c.line(x - r, y, x + r, y)
    c.line(x, y - r, x, y + r)
    c.circle(x, y, r / 2)


def schreiben(pfad, p, profil, titel=""):
    """PDF schreiben. Ergebnis: dict(blaetter=(Spalten, Zeilen), seiten, koordinaten)."""
    d = daten(p, profil)
    # Lage auf dem Papier: x = Länge (waagerecht), y = Umfang (senkrecht), Ursprung unten links
    spalten, zeilen = blaetter(d["laenge"], d["umfang"])
    bw, bh = A4[0] - 2 * RAND, A4[1] - 2 * RAND
    c = canvas.Canvas(str(pfad), pagesize=A4)
    c.setTitle(f"Abwicklung 1:1 {titel}".strip())
    seiten = 0
    for zr in range(zeilen):
        for sp in range(spalten):
            x0, y0 = sp * bw, zr * bh            # Ausschnitt in pt der Abwicklung

            def punkt(x_mm, s_mm):
                return RAND + x_mm * mm - x0, RAND + s_mm * mm - y0
            c.saveState()
            pfad_clip = c.beginPath()
            pfad_clip.rect(RAND, RAND, bw, bh)
            c.clipPath(pfad_clip, stroke=0, fill=0)
            c.setStrokeColor(colors.HexColor("#9AA3AD"))
            c.setLineWidth(0.3)
            c.rect(*punkt(0, 0), d["laenge"] * mm, d["umfang"] * mm)          # Mantel
            c.setStrokeColor(colors.black)
            c.setLineWidth(0.6)
            for linie in [d["umriss"]] + d["konturen"]:
                for teil in sa.kontur_teile(linie, d["umfang"]) if linie is not d["umriss"] else [linie]:
                    pts = [punkt(x, s) for x, s in teil]
                    if len(pts) >= 2:
                        pa = c.beginPath()
                        pa.moveTo(*pts[0])
                        for q in pts[1:]:
                            pa.lineTo(*q)
                        pa.close()
                        c.drawPath(pa, stroke=1, fill=0)
            c.restoreState()
            c.setLineWidth(0.4)
            for x, y in ((RAND, RAND), (RAND + bw, RAND), (RAND, RAND + bh), (RAND + bw, RAND + bh)):
                _kreuz(c, x, y)
            c.setFont("Helvetica", 7)
            c.drawString(RAND, A4[1] - RAND + 3 * mm,
                         f"Abwicklung 1:1 {titel} – Blatt {zr + 1}/{sp + 1} (Zeile/Spalte) von {zeilen}×{spalten} – "
                         f"Passmarken: x {x0 / mm:.0f}…{(x0 + bw) / mm:.0f} mm, Umfang {y0 / mm:.0f}…"
                         f"{(y0 + bh) / mm:.0f} mm")
            c.line(RAND, RAND - 6 * mm, RAND + 100 * mm, RAND - 6 * mm)       # Prüfbalken 100 mm
            c.drawString(RAND + 102 * mm, RAND - 7 * mm, "100 mm (Druck auf tatsächliche Größe prüfen)")
            c.showPage()
            seiten += 1
    # Koordinatenliste
    liste = koordinaten(d)
    y = A4[1] - RAND
    c.setFont("Helvetica-Bold", 11)
    c.drawString(RAND, y, f"Koordinatenliste {titel}".strip())
    y -= 6 * mm
    c.setFont("Helvetica", 8)
    c.drawString(RAND, y, f"Länge {d['laenge']:.1f} mm, Umfang {d['umfang']:.1f} mm; Abstand der Schnittkante vom "
                          "jeweiligen Teilende je Stelle am Umfang")
    y -= 7 * mm
    for i, (s, a, b) in enumerate([("Umfang [mm]", "Kante A [mm]", "Kante B [mm]")] + liste):
        if y < RAND:
            c.showPage()
            seiten += 1
            y = A4[1] - RAND
            c.setFont("Helvetica", 8)
        f = (lambda w: w if isinstance(w, str) else f"{w:.1f}".replace(".", ","))
        c.setFont("Helvetica-Bold" if i == 0 else "Helvetica", 8)
        for spalte, w in enumerate((s, a, b)):
            c.drawRightString(RAND + (35 + 35 * spalte) * mm, y, f(w))
        y -= 4.2 * mm
    c.showPage()
    seiten += 1
    c.save()
    return dict(blaetter=(spalten, zeilen), seiten=seiten, koordinaten=liste)
