"""Schnellpreis für Telefonanfragen (Vorschlag V5, Patrick 31.10.2026).

Profil, Werkstoff, Teilelänge, Stückzahl und grob die Konturen (Anzahl Bohrungen mit Ø, weitere Konturen mit
Schnittlänge, Enden gerade oder Gehrung) eingeben, nach wenigen Sekunden steht ein Richtpreis je Stück. Gerechnet wird
genau wie ein Angebot: Kopf mit den Vorgaben eines neuen Angebots (Kundenvorgaben, Maschine, Gewinn …), eine Position,
Optimierung der Stangen und Kalkulation; gespeichert wird nichts. Zusätzlich die Preise für weitere Stückzahlen
(Staffel am Telefon).

„Als Angebot übernehmen“ legt ein neues Angebot mit genau dieser Position an.

Schneidweg je Teil = zwei gerade Trennschnitte (Anfang und Ende, wie optimierung.schnittlaenge; Gehrung 45° länger)
+ Bohrungen π × Ø + weitere Konturen; Einstiche = Enden + Bohrungen + Konturen."""
import math

from . import rechnen
from . import optimierung as opt
from .stammdaten import flaeche_wirksam

GEHRUNG_45 = math.sqrt(2)         # schräger Schnitt 45°: Schnittlänge × √2 (Näherung wie schneidweg.schraeg)
MENGEN = (1, 10, 50, 100, 500)


def _z(v):
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def schneidweg(profil, bohrungen=0, bohr_d=0.0, konturen=0, kontur_mm=0.0, gehrung=0):
    """(Schneidweg je Teil [mm], Einstiche je Teil). gehrung = Anzahl Enden mit 45°-Gehrung (0-2)."""
    gerade = opt.schnittlaenge(profil.get("form"), _z(profil.get("a")), profil.get("b"), profil.get("wand"),
                               flaeche_wirksam(profil), profil.get("profil_id"), profil.get("r_aussen"))
    g = max(0, min(2, int(gehrung or 0)))
    enden = gerade * (2 - g) + gerade * GEHRUNG_45 * g
    weg = enden + max(0, int(bohrungen or 0)) * math.pi * _z(bohr_d) + max(0.0, _z(kontur_mm))
    return round(weg, 1), 2 + max(0, int(bohrungen or 0)) + max(0, int(konturen or 0))


def position(k, profil_id, werkstoff_id, laenge, stueck, bohrungen=0, bohr_d=0.0, konturen=0, kontur_mm=0.0,
             gehrung=0):
    """Position (dict) für die Rechnung bzw. für „Als Angebot übernehmen“."""
    pr = dict(k.profile.get(profil_id) or {}, profil_id=profil_id)
    weg, einst = schneidweg(pr, bohrungen, bohr_d, konturen, kontur_mm, gehrung)
    p = dict(pos=10, profil_id=profil_id, werkstoff_id=werkstoff_id, laenge=float(laenge), stueck=int(stueck),
             schneidweg=weg, einstiche=einst, bezeichnung="Schnellpreis")
    if gehrung:
        p["a_gerade"] = "nein"
        if int(gehrung) > 1:
            p["b_gerade"] = "nein"
    return p


def rechnen_(db, kopf, p):
    """Ein Preis: dict(stueck, preis_stueck, verkauf, selbst, material, laser, stangen, fehler) oder dict(fehler=…)."""
    k, tab = db.kontext(), db.tabellen()
    e = rechnen.einstellungen_angebot(kopf, rechnen.einstellungen_fest(tab, db.einstellungen()))
    pos = [dict(p)]
    try:
        erg = rechnen.optimieren(kopf, pos, k, tab, e)
    except (ValueError, AssertionError) as fehler:
        return dict(stueck=p["stueck"], fehler=str(fehler))
    if erg.get("fehler"):
        return dict(stueck=p["stueck"], fehler="; ".join(f.get("grund") or "nicht eingeplant" for f in erg["fehler"]))
    zeilen, s = rechnen.kalkulation(kopf, pos, erg, k, tab, e)
    if not zeilen or zeilen[0] is None:
        return dict(stueck=p["stueck"], fehler="nicht kalkulierbar (Profil oder Werkstoff fehlt)")
    hinweise = [h for h in (zeilen[0].get("hinweise") or ()) if isinstance(h, str)][:3]
    n = max(1, int(p["stueck"]))
    return dict(stueck=n, preis_stueck=rechnen._n(s.get("verkauf")) / n, verkauf=rechnen._n(s.get("verkauf")),
                selbst=rechnen._n(s.get("selbst")), material=rechnen._n(s.get("material")),
                laser=rechnen._n(s.get("laser")), stangen=len(erg.get("stangen") or ()), hinweise=hinweise,
                fehler=None)


def berechnen(db, eingabe, mengen=MENGEN, kundennr=None):
    """Richtpreise. eingabe = dict(profil_id, werkstoff_id, laenge, stueck, bohrungen, bohr_d, konturen, kontur_mm,
    gehrung). Ergebnis: dict(kopf, position, haupt=Preis der Stückzahl, staffel=[Preis je weitere Menge]) oder
    dict(fehler=Text)."""
    k = db.kontext()
    if eingabe.get("profil_id") not in k.profile:
        return dict(fehler="Profil unbekannt")
    if eingabe.get("werkstoff_id") not in k.werkstoffe:
        return dict(fehler="Werkstoff unbekannt")
    if _z(eingabe.get("laenge")) <= 0 or int(_z(eingabe.get("stueck"))) <= 0:
        return dict(fehler="Länge und Stückzahl angeben")
    kopf = db.neuer_kopf(dict(kundennr=kundennr) if kundennr else {})
    kopf["zeitbasis"] = db.zeitbasis_vorgabe(kopf.get("maschine"))
    p = position(k, eingabe["profil_id"], eingabe["werkstoff_id"], eingabe["laenge"], int(_z(eingabe["stueck"])),
                 eingabe.get("bohrungen"), eingabe.get("bohr_d"), eingabe.get("konturen"), eingabe.get("kontur_mm"),
                 eingabe.get("gehrung"))
    haupt = rechnen_(db, kopf, p)
    staffel = [rechnen_(db, kopf, dict(p, stueck=m)) for m in mengen if m != p["stueck"]]
    return dict(kopf=kopf, position=p, haupt=haupt, staffel=staffel)
