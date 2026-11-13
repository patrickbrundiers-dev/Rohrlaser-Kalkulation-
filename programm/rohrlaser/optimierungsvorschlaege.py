"""Optimierungsvorschläge eines Angebots an einer Stelle (Plan X1–X8, Paket X6, Patrick 12.11.2026, Freigabe „Alle
Empfehlungen“; Übernehmen nur als neue Fassung).

Sammelt die Vorschläge, die das Programm schon rechnet, einheitlich je Zeile: Beschreibung, Ist, Vorschlag, Zeit-,
Material- und Kostenersparnis, technische Voraussetzung, Nachweis.
  - Lieferlänge je Stangengruppe (varianten.gruppen, gleiche Fertigungsregeln, nur ausführbare mit Preis)
  - Material aus dem Lager (nur mit eingeschaltetem Lager; Buchung bleibt im Fenster Material aus Lager)
  - andere Maschine (maschinen_vergleich: das ganze Angebot neu optimiert und kalkuliert, nur wenn alle Teile passen)
  - Schneiddaten prüfen: Ist-Zeiten der Nachkalkulation (Laufzeit je Teil, CSV der Maschine) weichen bei derselben
    Schneiddaten-Zeile in mindestens SD_MINDESTENS Aufträgen im Mittel um SD_GRENZE oder mehr von der Rechnung ab
Jeder Vorschlag rechnet auf einer Kopie, das Angebot bleibt unverändert. Ein Vorschlag ohne gerechneten Vorteil
erscheint nicht. „Als neue Fassung übernehmen“ legt eine Fassung an (aktuelle Preise wie jede neue Fassung) und
stellt dort Lieferlänge bzw. Maschine um; den Unterschied zeigt der Fassungsvergleich. Geometrie wird nie verändert
(Konturen wie STEP). Ohne Qt."""
from . import rechnen

LIEFERLAENGE, LAGER, MASCHINE, SCHNEIDDATEN = "Lieferlänge", "Lager", "Maschine", "Schneiddaten prüfen"
SD_MINDESTENS = 3          # so viele Aufträge mit Ist-Laufzeit je Schneiddaten-Zeile, bevor ein Vorschlag erscheint
SD_GRENZE = 0.10           # ab 10 % mittlerer Abweichung Ist gegen Soll
EPS = 0.005


def _n(v):
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else 0.0


def _v(art, titel, ist, vorschlag, zeit_s=None, material=None, kosten=None, voraussetzung="", nachweis="",
       aktion=None):
    return dict(art=art, titel=titel, ist=ist, vorschlag=vorschlag, zeit_s=zeit_s, material=material, kosten=kosten,
                voraussetzung=voraussetzung, nachweis=nachweis, aktion=aktion)


def lieferlaengen(gruppen, ergebnis):
    """Vorschläge aus den Varianten je Gruppe (varianten.gruppen): günstigste ausführbare andere Lieferlänge bzw.
    Lager-Variante mit Preis, die weniger kostet als die geplante."""
    out = []
    for g in gruppen or ():
        geplant = next((v for v in g["varianten"] if v.get("geplant")), None)
        if not geplant or geplant.get("kosten") is None:
            continue
        name = f"{g['profil']} · {g['werkstoff']}" + (f" {g['oberflaeche']}" if g.get("oberflaeche") else "")
        besser = [v for v in g["varianten"] if not v.get("geplant") and not v.get("fehler") and v.get("kosten") is not None
                  and geplant["kosten"] - v["kosten"] >= EPS]
        for art in (LIEFERLAENGE, LAGER):
            kand = [v for v in besser if bool(v.get("lager")) == (art == LAGER)]
            if not kand:
                continue
            v = min(kand, key=lambda x: x["kosten"])
            zeit = ((_n(geplant.get("zeit")) - _n(v.get("zeit"))) * 60
                    if geplant.get("zeit") is not None and v.get("zeit") is not None else None)
            aktion = None
            if art == LIEFERLAENGE and g.get("laengen_index") is not None and v.get("laenge"):
                vg = (ergebnis.get("laengen") or [])[g["laengen_index"]]
                aktion = dict(typ="laenge", schluessel=vg["schluessel"],
                              laenge=0 if v["laenge"] == g.get("grundlaenge") else int(v["laenge"]))
            out.append(_v(art, f"{name}: {v['name']}",
                          f"{geplant['name']}: {geplant['stangen']} Stangen, {rechnen.zahl(geplant['kosten'])} €, "
                          f"Verschnitt {rechnen.zahl(geplant['verschnitt'], 1)} %",
                          f"{v['stangen']} Stangen, {rechnen.zahl(v['kosten'])} €, Verschnitt "
                          f"{rechnen.zahl(v['verschnitt'], 1)} %", zeit, geplant["kosten"] - v["kosten"],
                          geplant["kosten"] - v["kosten"],
                          "Lieferlänge beim Händler bestellbar" if art == LIEFERLAENGE else
                          "Lager eingeschaltet, Bestand vorhanden (Buchung im Fenster Material aus Lager)",
                          f"gleiche Optimierung und Fertigungsregeln, Status: {v.get('status') or ''}".strip(),
                          aktion))
    return out


def maschinen(liste, maschine, verkauf_jetzt=None):
    """Vorschlag andere Maschine aus maschinen_vergleich.vergleich (nur mögliche, günstiger als die jetzige)."""
    jetzt = next((r for r in liste or () if r["maschine"] == maschine), None)
    if not jetzt or not jetzt.get("verkauf"):
        return []
    andere = [r for r in liste if r["maschine"] != maschine and r["moeglich"] and r.get("verkauf")
              and jetzt["verkauf"] - r["verkauf"] >= EPS]
    if not andere:
        return []
    b = min(andere, key=lambda r: r["verkauf"])
    zeit = (jetzt["laser_h"] - b["laser_h"]) * 3600 if jetzt.get("laser_h") is not None and b.get("laser_h") is not None \
        else None
    return [_v(MASCHINE, f"Angebot auf Maschine {b['maschine']}",
               f"{maschine}: {rechnen.zahl(jetzt['verkauf'])} € netto, Laserzeit {rechnen.zahl(jetzt['laser_h'], 2)} h",
               f"{b['maschine']}: {rechnen.zahl(b['verkauf'])} € netto, Laserzeit {rechnen.zahl(b['laser_h'], 2)} h",
               zeit, None, jetzt["verkauf"] - b["verkauf"],
               "alle Teile auf der Maschine einplanbar (Hüllkreis, Gewicht, Stangenlänge)",
               "ganzes Angebot auf der Maschine neu optimiert und kalkuliert (Verkaufspreis netto)",
               dict(typ="maschine", maschine=b["maschine"]))]


def schneiddaten(teile_soll, faelle, mindestens=SD_MINDESTENS, grenze=SD_GRENZE):
    """Vorschlag „Schneiddaten prüfen“ je Schneiddaten-Zeile dieses Angebots (nachkalkulation.teile_soll), wenn die
    Ist-Laufzeiten früherer Aufträge (nachkalkulation.faelle_laserzeit_teil) dauerhaft abweichen. Ohne Übernehmen:
    die Vorschübe ändert nur der Nutzer (Lernen aus Nachkalkulation)."""
    je = {}
    for f in faelle or ():
        je.setdefault(tuple(f["schluessel"]), []).append(f)
    out, gesehen = [], set()
    for t in teile_soll or ():
        schl = tuple(t["schluessel"])
        if schl in gesehen:
            continue
        gesehen.add(schl)
        ff = je.get(schl) or []
        auftraege = {f["angebot"] for f in ff}
        soll, ist = sum(_n(f["soll"]) for f in ff), sum(_n(f["ist"]) for f in ff)
        if len(auftraege) < mindestens or soll <= 0 or abs(ist / soll - 1) < grenze:
            continue
        faktor = ist / soll
        teile = [x for x in teile_soll if tuple(x["schluessel"]) == schl]
        zeit = sum(_n(x["soll_s"]) * _n(x.get("stueck")) for x in teile) * (faktor - 1)
        m, wer, wand, gas = schl
        out.append(_v(SCHNEIDDATEN, f"Schneiddaten {m} · {wer} · Wand bis {rechnen.zahl(wand, 1)} mm · {gas}",
                      f"gerechnet {rechnen.zahl(soll / len(ff), 1)} s je Teil (Mittel)",
                      f"Maschine {rechnen.zahl(ist / len(ff), 1)} s je Teil: Vorschübe × "
                      f"{rechnen.zahl(1 / faktor, 3)} prüfen", -zeit, None, None,
                      "Ist-Laufzeiten aus der Nachkalkulation (CSV der Maschine oder von Hand)",
                      f"{len(ff)} Teile aus {len(auftraege)} Aufträgen, Ist im Mittel "
                      f"{rechnen.zahl(100 * (faktor - 1), 1)} % {'länger' if faktor > 1 else 'kürzer'}"))
    return out


def alle(kopf, positionen, ergebnis, k, tabellen, einst, einst_db, zeilen, gruppen, maschinen_liste=None,
         faelle=None):
    """Alle Vorschläge, größte Kostenersparnis zuerst (Schneiddaten prüfen am Ende)."""
    from . import nachkalkulation
    out = lieferlaengen(gruppen, ergebnis or {})
    if maschinen_liste:
        out += maschinen(maschinen_liste, kopf.get("maschine"))
    if faelle:
        out += schneiddaten(nachkalkulation.teile_soll(kopf, positionen, zeilen, k, tabellen), faelle)
    return sorted(out, key=lambda v: (v["art"] == SCHNEIDDATEN, -(_n(v["kosten"]))))


def text(v, schl):
    """Zellentext."""
    w = v.get(schl)
    if w is None:
        return ""
    if schl == "zeit_s":
        return f"{rechnen.zahl(w / 60, 1)} min"
    if schl in ("material", "kosten"):
        return f"{rechnen.zahl(w, 2)} €"
    return str(w)


SPALTEN = (("titel", "Vorschlag"), ("ist", "Ist"), ("vorschlag", "Variante"), ("zeit_s", "Zeit gespart"),
           ("material", "Material gespart"), ("kosten", "Kosten gespart"), ("voraussetzung", "Voraussetzung"),
           ("nachweis", "Nachweis"))
