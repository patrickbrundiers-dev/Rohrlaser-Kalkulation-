"""Zeichnung eines Teils aus dem Schneidweg-Rechner als PDF (A4 quer, Design wie die übrigen PDFs in pdf.py):
Seite 1 Draufsicht, Seitenansicht und Ansicht von A maßstäblich mit Bemaßung und Schweißnaht, Seite 2 Abwicklung,
Enden und Konturliste mit Lage, Seite, Maßen und Schnittlängen. Die Skizze zeichnet skizze_widget.Skizze (ohne
Bedienhinweise); der Maßstab auf dem Papier steht unter dem Bild. Die Zeichnung zeigt nur, was im Rechner steht:
Konturen ohne Lage sind gleichmäßig verteilt und als solche gekennzeichnet.
blech_pdf: Zeichnung eines Blechteils aus dem Blech-Editor (Abwicklung bzw. Zuschnitt mit Biegelinien, Kantteil mit
Seitenansicht, Biegungen und Innenkonturen mit Lage), S7.
"""
import io

from PySide6.QtCore import QBuffer, QIODevice
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import CondPageBreak, Image, Spacer

from . import naht as naht_, rechnen, schneidweg as sw, skizze as sk
from .pdf import GRAU, S_H2, S_KLEIN, _dok_kopf, _dokument, _erstellt, _fuss, _kacheln, _kopfzeile, _p, _tabelle
from .skizze_widget import ABWICKLUNG, ANSICHTEN, Skizze

BREITE = 273 * mm
S_GRAU = ParagraphStyle("zg", parent=S_KLEIN, textColor=GRAU)


def _png(img):
    puffer = QBuffer()
    puffer.open(QIODevice.WriteOnly)
    img.save(puffer, "PNG")
    return io.BytesIO(bytes(puffer.data()))


def _bild(skizze, modus, hoehe_max_mm):
    """Skizze als Bild über die volle Breite, so hoch wie nötig (höchstens hoehe_max_mm); Ergebnis (Image,
    Maßstab-Text)."""
    breite_px = 1150
    hoehe_px = min(round(breite_px * hoehe_max_mm / (BREITE / mm)), round(skizze.hoehe_fuer(breite_px, modus)) + 4)
    hoehe_mm = hoehe_px * (BREITE / mm) / breite_px
    img, px_mm = skizze.bild(breite_px, hoehe_px, modus)
    papier = px_mm * (BREITE / mm) / breite_px            # mm Papier je mm Teil
    n = 1 / papier if papier > 0 else 0
    text = f"Maßstab 1 : {rechnen.zahl(n, 1 if n < 10 else 0)} (A4 quer, alle Maße in mm)"
    return Image(_png(img), width=BREITE, height=hoehe_mm * mm), text


def ende_text(e, profil):
    """Ausführung eines Endes: gerade, Gehrung 45° über Höhe, länger rechts (90°), Ausklinkung auf Rundrohr Ø …"""
    if sw._z(e.get("sattel")):
        return f"Ausklinkung auf Rundrohr Ø {rechnen.zahl(e['sattel'], 1)}"
    w = sw._z(e.get("winkel"))
    if not w:
        return "gerade" if e.get("form") in (None, "gerade") else str(e.get("form"))
    if e.get("achse") == sw.ACHSE_ZWEI:
        return (f"Schrägschnitt zweiachsig {rechnen.zahl(sw._z(e.get('winkel_h')), 1)}° über Höhe, "
                f"{rechnen.zahl(sw._z(e.get('winkel_b')), 1)}° über Breite")
    t = f"Gehrung {rechnen.zahl(w, 1)}°"
    if profil.get("form") != "Rundrohr":
        t += f" {e.get('achse') or sw.ACHSEN[0]}"
    r = next((k for k, v in sw.RICHTUNGEN.items() if v is not None and v == e.get("richtung")), None)
    return t + (f", {r}" if r else "") + (" (automatisch)" if r and e.get("richtung_auto") else "")


def _lage_text(e, n):
    x, ab = e.get("x"), sw._z(e.get("abstand"))
    if x is None:
        return "verteilt (nicht angegeben)"
    if n > 1 and ab:
        return f"{rechnen.zahl(x, 1)} + {n - 1} × {rechnen.zahl(ab, 1)}"
    return rechnen.zahl(x, 1)


def _seite_text(qs, e):
    if qs.r:
        return sk.winkel_text(sk.winkel_aus_text(e.get("seite")) or 0.0)
    return sk.seite_anzeige(qs, e.get("seite") if e.get("seite") in qs.seiten() else (qs.seiten() or [""])[0])


def naht_text(werte, profil):
    v = (werte or {}).get("naht_vorgabe")
    if not v:
        return "keine Vorgabe (frei drehbar)"
    if v != naht_.FEST:
        return "unbekannt (nicht drehen)"
    return naht_.seite(profil, werte["naht_winkel"])["text"]


def zeichnung_pdf(pfad, kopf, p, profil, eingaben, ergebnis, naht=None, einst=None, schneidzeit=None):
    """Zeichnung als PDF schreiben. eingaben/ergebnis aus dem Schneidweg-Rechner, naht = Nahtfelder der Position."""
    titel = f"Zeichnung Pos. {p.get('pos') or ''} {p.get('artikel') or ''}".strip()
    doc, leinwand = _dokument(pfad, titel, _fuss(einst, titel), quer=True)
    angaben = [("Angebot", kopf.get("nummer")), ("Kunde", kopf.get("kunde")), ("Pos.", rechnen.zahl(p.get("pos"), 0)
               if isinstance(p.get("pos"), (int, float)) else p.get("pos")), ("Artikel", p.get("artikel")),
               ("Bezeichnung", p.get("bezeichnung")), ("erstellt", _erstellt())]
    inhalt = _dok_kopf("Zeichnung", kopf, einst, BREITE, angaben=angaben)
    f = (ergebnis or {}).get("felder") or {}
    laenge = p.get("laenge")
    inhalt += [_kacheln([("Profil", p.get("profil_id") or "–"), ("Werkstoff", p.get("werkstoff_id") or "–"),
                         ("Teilelänge", f"{rechnen.zahl(laenge, 1)} mm" if isinstance(laenge, (int, float)) else "–"),
                         ("Stückzahl", rechnen.zahl(p.get("stueck"), 0) if isinstance(p.get("stueck"), (int, float))
                          else "–"),
                         ("Schneidweg je Teil", f"{rechnen.zahl(f.get('schneidweg') or 0, 1)} mm"),
                         ("Einstiche", str(f.get("einstiche") or 0)),
                         ("Schweißnaht (SN)", naht_text(naht, profil) if naht_.form_von(profil) else "–")], BREITE),
               Spacer(1, 4 * mm)]
    skizze = Skizze(profil, laenge)
    werte = naht or {}
    skizze.naht = werte.get("naht_winkel") if werte.get("naht_vorgabe") == naht_.FEST else None
    skizze.zeigen(eingaben, ergebnis)
    bild, massstab = _bild(skizze, ANSICHTEN, 110)
    hinweis = ("Draufsicht = Blick von oben, Seitenansicht = Blick auf vorne (rechts von Ende A gesehen); Rechteckrohr "
               "mit der Breitseite oben. Verdeckte Kanten und Konturen gestrichelt, SN = Schweißnaht.")
    inhalt += [bild, _p(f"{massstab}. {hinweis}", S_GRAU)]
    if not isinstance(laenge, (int, float)) or laenge <= 0:
        inhalt.append(_p("Teilelänge fehlt: gezeichnet mit 1000 mm.", S_GRAU))
    bild, massstab = _bild(skizze, ABWICKLUNG, 80)
    inhalt += [CondPageBreak(bild.drawHeight + 12 * mm), _p("Abwicklung", S_H2), bild, _p(f"{massstab}. Jede Fläche ein Streifen, von oben nach unten.", S_GRAU),
               Spacer(1, 3 * mm)]
    # Enden
    daten = [_kopfzeile(["Ende", "Ausführung", "Schnittlänge [mm]", "Einstiche", "Herkunft"])]
    for i, (s, name) in enumerate((("a", "Anfangsschnitt (Ende A)"), ("b", "Endschnitt (Ende B)"))):
        e = eingaben.get(s) or {}
        schritt = (ergebnis or {}).get("schritte", [{}, {}])[i] if ergebnis else {}
        daten.append([_p(name), _p(ende_text(e, profil)), rechnen.zahl(schritt.get("laenge") or 0, 1),
                      str(schritt.get("einstiche") or ""), _p("STEP gemessen" if sw._z(e.get("gemessen")) else
                                                              "Formel")])
    inhalt += [CondPageBreak(25 * mm), _p("Enden", S_H2),
               _tabelle(daten, [w * mm for w in (50, 110, 35, 25, 53)], rechts=(2, 3)), Spacer(1, 3 * mm)]
    # Konturen
    qs = sk.Querschnitt(profil)
    schritte = {id(s_.get("eingabe")): s_ for s_ in ((ergebnis or {}).get("schritte") or ())[2:]}
    daten = [_kopfzeile(["Nr.", "Art", "Anzahl", "Maße [mm]", "Lage ab Ende A [mm]", "Seite", "Versatz quer [mm]",
                         "Schnitt je Stück [mm]", "Klasse", "Bemerkung"])]
    for nr, e in enumerate(eingaben.get("konturen") or (), start=1):
        n = int(sw._z(e.get("anzahl")) or 1)
        s_ = schritte.get(id(e)) or {}
        quer = "" if qs.r or not sw._z(e.get("q")) else rechnen.zahl(e["q"], 1)
        daten.append([str(nr), _p(e.get("art")), str(n), _p(sk.kurz(e)), _p(_lage_text(e, n)),
                      _p(_seite_text(qs, e)), quer, rechnen.zahl(s_.get("laenge_stueck") or 0, 1),
                      s_.get("klasse") or "", _p(e.get("text") or "", S_KLEIN)])
    if len(daten) > 1:
        inhalt += [CondPageBreak(30 * mm), _p("Innenkonturen", S_H2),
                   _tabelle(daten, [w * mm for w in (10, 26, 15, 45, 37, 27, 24, 28, 17, 44)], rechts=(2, 6, 7))]
    else:
        inhalt.append(_p("Keine Innenkonturen.", S_GRAU))
    zeilen = [f"Schneidweg je Teil {rechnen.zahl(f.get('schneidweg') or 0, 1)} mm (Enden "
              f"{rechnen.zahl(f.get('a_schnitt') or 0, 1)} + {rechnen.zahl(f.get('b_schnitt') or 0, 1)} mm, "
              f"Innenkonturen {rechnen.zahl(f.get('innen') or 0, 1)} mm), {f.get('einstiche') or 0} Einstiche"]
    if sw._z(f.get("gravur") or eingaben.get("gravur")):
        zeilen.append(f"Gravur {rechnen.zahl(sw._z(f.get('gravur') or eingaben.get('gravur')), 1)} mm (grün, nicht "
                      "im Schneidweg)")
    if schneidzeit is not None:
        zeilen.append(f"Schneidzeit je Teil {rechnen.zahl(schneidzeit, 1)} s")
    inhalt += [Spacer(1, 3 * mm), _p(" · ".join(zeilen)),
               _p("Lage, Seite und Versatz der Konturen kommen aus dem Schneidweg-Rechner bzw. dem STEP-Import; "
                  "„verteilt“ heißt, die Lage ist nicht angegeben. Seite von Ende A gesehen: 0° oben, 90° vorne "
                  "(rechts), 180° unten, 270° hinten (links).", S_GRAU)]
    doc.build(inhalt, canvasmaker=leinwand)
    return pfad


def blech_pdf(pfad, kopf, teil, e, erg, einst=None):
    """Zeichnung eines Blechteils als PDF. kopf = Angebotskopf (oder leer), teil = Kopfwerte des Blech-Editors
    (bezeichnung, artikelnr, stueck), e = Eingaben, erg = blech.rechnen."""
    from . import blech
    from .blech_dialog import BlechSkizze
    zs = erg["zuschnitt"]
    titel = f"Zeichnung {teil.get('artikelnr') or ''} {teil.get('bezeichnung') or ''}".strip()
    doc, leinwand = _dokument(pfad, titel, _fuss(einst, titel), quer=True)
    angaben = [("Angebot", kopf.get("nummer")), ("Kunde", kopf.get("kunde")), ("Artikel", teil.get("artikelnr")),
               ("Bezeichnung", teil.get("bezeichnung")), ("erstellt", _erstellt())]
    inhalt = _dok_kopf("Zeichnung Blech", kopf, einst, BREITE, angaben=[(n, w) for n, w in angaben if w])
    kant = e.get("art") == blech.KANTTEIL
    inhalt += [_kacheln([("Werkstoff", e.get("werkstoff") or "–"),
                         ("Dicke", f"{rechnen.zahl(sw._z(e.get('dicke')), 1)} mm"),
                         ("Zuschnitt", f"{rechnen.zahl(zs['laenge'], 1)} × {rechnen.zahl(zs['breite'], 1)} mm"),
                         ("Stückzahl", rechnen.zahl(teil.get("stueck"), 0) if teil.get("stueck") else "–"),
                         ("Kantungen", str(erg.get("kantungen") or 0)),
                         ("Schneidweg je Teil", f"{rechnen.zahl(erg.get('schneidweg') or 0, 1)} mm"),
                         ("Einstiche", str(erg.get("einstiche") or 0)),
                         ("Gewicht je Teil", f"{rechnen.zahl(erg.get('gewicht') or 0, 2)} kg")], BREITE),
               Spacer(1, 4 * mm)]
    # Skizze wie im Editor, breit und so hoch wie das Teil es braucht
    breite_px = 1000            # Schrift der Skizze (8 pt) noch lesbar
    verhaeltnis = zs["breite"] / max(zs["laenge"], 1)
    hoehe_px = int(min(max(breite_px * (0.62 if kant else 1.0) * verhaeltnis + 120, 380),
                       breite_px * 105 / (BREITE / mm)))          # höchstens 105 mm hoch: Kopf und Bild auf Seite 1
    skizze = BlechSkizze()
    skizze.resize(breite_px, hoehe_px)
    skizze.setzen(e, zs)
    img = skizze.grab().toImage()
    hoehe_mm = hoehe_px * (BREITE / mm) / breite_px
    papier = getattr(skizze, "m", 0) * (BREITE / mm) / breite_px
    n = 1 / papier if papier > 0 else 0
    inhalt += [Image(_png(img), width=BREITE, height=hoehe_mm * mm),
               _p(f"Maßstab 1 : {rechnen.zahl(n, 1 if n < 10 else 0)} (A4 quer, alle Maße in mm). "
                  + ("Abwicklung mit Biegelinien (grün gestrichelt, ↑ = zur Außenseite), rechts die Seitenansicht "
                     "mit Außenmaßen." if kant or zs.get("biegungen") else "Zuschnitt von oben.")
                  + " Innenkonturen rot, Lage = Mitte ab der linken unteren Ecke.", S_GRAU), Spacer(1, 3 * mm)]
    # Biegungen
    bg = zs.get("biegungen") or []
    if bg:
        daten = [_kopfzeile(["Nr.", "Lage ab Anfang der Abwicklung [mm]", "Winkel [°]", "Richtung",
                             "Innenradius [mm]", "Ausgleich [mm]"])]
        for i, (lage, w, r, v) in enumerate(bg, 1):
            daten.append([f"B{i}", rechnen.zahl(lage, 1), rechnen.zahl(abs(w), 1), "zur Außenseite" if w > 0 else
                          "zur Innenseite", rechnen.zahl(r, 1), rechnen.zahl(v, 2)])
        inhalt += [CondPageBreak(25 * mm), _p("Biegungen", S_H2),
                   _tabelle(daten, [w * mm for w in (15, 70, 30, 50, 40, 40)], rechts=(1, 2, 4, 5)),
                   Spacer(1, 3 * mm)]
    # Innenkonturen
    daten = [_kopfzeile(["Nr.", "Art", "Anzahl", "Maße [mm]", "Lage x [mm]", "Lage y [mm]", "Bemerkung"])]
    for nr, z in enumerate([z for z in e.get("konturen") or () if z.get("art")], 1):
        lage = z.get("x") is not None and z.get("y") is not None
        daten.append([str(nr), _p(z.get("art")), str(int(sw._z(z.get("anzahl")) or 1)), _p(sk.kurz(z)),
                      rechnen.zahl(z["x"], 1) if lage else "verteilt", rechnen.zahl(z["y"], 1) if lage else "",
                      _p(z.get("text") or "", S_KLEIN)])
    if len(daten) > 1:
        inhalt += [CondPageBreak(30 * mm), _p("Innenkonturen", S_H2),
                   _tabelle(daten, [w * mm for w in (12, 35, 18, 70, 30, 30, 78)], rechts=(2, 4, 5))]
    else:
        inhalt.append(_p("Keine Innenkonturen.", S_GRAU))
    zeilen = [f"Schneidweg je Teil {rechnen.zahl(erg.get('schneidweg') or 0, 1)} mm (außen "
              f"{rechnen.zahl(erg.get('aussen') or 0, 1)} mm, innen {rechnen.zahl(erg.get('innen') or 0, 1)} mm), "
              f"{erg.get('einstiche') or 0} Einstiche"]
    if erg.get("gravur"):
        zeilen.append(f"Gravur {rechnen.zahl(erg['gravur'], 1)} mm (nicht im Schneidweg)")
    if erg.get("zeit"):
        gas = str(erg.get("gas") or "").translate(str.maketrans("₂₃", "23"))     # Schrift der PDFs ohne Tiefzahlen
        zeilen.append(f"Laserzeit je Teil {rechnen.zahl(erg['zeit'], 1)} s" + (f" ({gas})" if gas else ""))
    inhalt += [Spacer(1, 3 * mm), _p(" · ".join(zeilen))]
    doc.build(inhalt, canvasmaker=leinwand)
    return pfad
