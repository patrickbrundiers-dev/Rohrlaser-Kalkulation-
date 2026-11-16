"""Schachtelvergleich in einer Tabelle (Plan X1–X8, Paket X3, Patrick 12.11.2026, Freigabe „Alle Empfehlungen“).

Je Stangengruppe (Profil, Werkstoff, Oberfläche) die Einteilungen nebeneinander, gerechnet mit denselben
Fertigungsregeln wie der Schnittplan:
  1 einfache Einteilung    Eingabereihenfolge, Stange voll, dann die nächste (optimierung.manuell)
  2 optimiert              der Schnittplan des Angebots
  3 ohne gemeinsamen Schnitt  dieselbe Optimierung, als hätte kein Teil ein gerades Ende für einen gemeinsamen
                           Schnitt; nur um den Nutzen des gemeinsamen Schnitts auszuweisen (wird nie geplant)
  4 andere Lieferlängen    wie „Varianten vergleichen“ (varianten.gruppen), übernehmen nur dort per Klick
  5 aus dem Lager          nur mit eingeschaltetem Lager (Patrick 12.11.: Zeile erscheint dann), nie automatisch
Spalten: Stangen, Teile eingeplant / nicht eingeplant, Material kg und €, Nutzlänge m, Verschnitt mm und %, Material
€ je Teil, Schnitte und Laserzeit gespart (gemeinsamer Schnitt), Einsparung € gegenüber 1.

Die Regel für den gemeinsamen Schnitt bleibt: nur zwei gerade Enden, gegenläufige Gehrungen nie. Fehlt ein Preis, steht
„fehlt“ statt 0 €. Ohne Qt."""
from dataclasses import replace

from . import optimierung as opt, rechnen

EINFACH, OPTIMIERT, OHNE_GEM, LIEFER, LAGER = "einfach", "optimiert", "ohne gemeinsamen Schnitt", "Lieferlänge", "Lager"
SPALTEN = (("name", "Einteilung"), ("stangen", "Stangen"), ("eingeplant", "Teile eingeplant"),
           ("nicht", "nicht eingeplant"), ("kg", "Material [kg]"), ("eur", "Material [€]"),
           ("nutz_m", "Stangenlänge gesamt [m]"), ("verschnitt_mm", "Verschnitt [mm]"),
           ("verschnitt", "Verschnitt [%]"), ("eur_teil", "Material [€/Teil]"), ("schnitte", "Schnitte gespart"),
           ("laser_s", "Laserzeit gespart [s]"), ("laser_eur", "Laser gespart [€]"),
           ("ersparnis", "Einsparung ggü. einfach [€]"))


def _n(v):
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else 0.0


def _zeile(art, name, stangen, stange_mm, teile_mm, n_teile, preis_stange, kgm, nicht=0, **w):
    lang = stangen * stange_mm if stange_mm else 0.0
    eur = stangen * preis_stange if preis_stange is not None else None
    return dict(dict(art=art, name=name, stangen=stangen, eingeplant=n_teile, nicht=nicht,
                     kg=lang / 1000 * kgm if kgm else None, eur=eur, nutz_m=lang / 1000,
                     verschnitt_mm=max(0.0, lang - teile_mm), verschnitt=100 * (lang - teile_mm) / lang if lang else None,
                     eur_teil=eur / n_teile if eur is not None and n_teile else None, schnitte=None, laser_s=None,
                     laser_eur=None, ersparnis=None, hinweis=""), **w)


def ohne_gemeinsamen_schnitt(g):
    """Gruppe, als hätte kein Teil ein gerades Ende (kein gemeinsamer Schnitt möglich); Gehrungen bleiben."""
    return replace(g, teile=[replace(t, a_gerade=False, b_gerade=False) for t in g.teile], bewiesen=False, schranke=0)


def vergleich(kopf, positionen, ergebnis, k, tabellen, einst, zeilen=None, lagerplan=None, lager_an=False):
    """[dict(profil, werkstoff, oberflaeche, stange, zeilen=[…])] je Stangengruppe des Schnittplans (ohne
    Kundenmaterial). zeilen = rechnen.kalkulation(...)[0] für die gesparte Laserzeit (sonst ohne). lagerplan =
    lager.planen(...) nur bei eingeschaltetem Lager (lager_an)."""
    from . import varianten
    if not ergebnis or not ergebnis.get("stangen"):
        return []
    gruppen = {rechnen.gruppe_schluessel(g)[:4]: g
               for g in rechnen.gruppen_bilden(kopf, positionen, k, tabellen, einst)[0] if not g.beistellung
               and not g.muster}
    werte = rechnen.stangen_werte(ergebnis, kopf, positionen, k, tabellen)
    var = {(v["profil"], v["werkstoff"], v["oberflaeche"] or ""): v
           for v in varianten.gruppen(kopf, positionen, ergebnis, k, tabellen, einst,
                                      lagerplan if lager_an else None)}
    nicht_je = {}
    for f in ergebnis.get("fehler") or ():
        p = positionen[f["index"]] if 0 <= f.get("index", -1) < len(positionen) else {}
        schl = (p.get("profil_id"), p.get("werkstoff_id"), rechnen.oberflaeche_von(p) or "")
        nicht_je[schl] = nicht_je.get(schl, 0) + _n(f.get("anzahl"))
    out = []
    for a in ergebnis.get("auswertung") or ():
        if a.get("beistellung"):
            continue
        schl = (a["profil"], a["werkstoff"], a["oberflaeche"] or "")
        grund = a.get("grundlaenge", a["stange"])
        st = [(s, w) for s, w in zip(ergebnis["stangen"], werte)
              if (s["profil"], s["werkstoff"], s.get("oberflaeche") or "") == schl and not s.get("beistellung")
              and not s.get("muster") and (s["stange"] == a["stange"] or a.get("vorgegeben"))]
        if not st:
            continue
        kosten = [w.get("kosten") for _, w in st]
        preis = sum(kosten) / len(kosten) if None not in kosten else None
        kgm = rechnen.kg_je_m(a["profil"], a["werkstoff"], k)
        teile = [t for s, _ in st for t in s["teile"]]
        teile_mm = sum(_n(t.get("laenge")) for t in teile)
        n = len(teile)
        z = []
        if a.get("manuell"):
            z.append(_zeile(EINFACH, "1 einfache Einteilung", a["manuell"], a["stange"], teile_mm, n, preis, kgm))
        opt_z = _zeile(OPTIMIERT, "2 optimiert (Schnittplan)", len(st), a["stange"], teile_mm, n, preis, kgm,
                       nicht=int(nicht_je.get(schl, 0)))
        opt_z["eur"] = sum(kosten) if None not in kosten else None
        opt_z["eur_teil"] = opt_z["eur"] / n if opt_z["eur"] is not None and n else None
        gem = sum(_n(s.get("gemeinsam")) for s, _ in st)
        idx = {t.get("index") for t in teile}
        laser_s = laser_eur = None
        if zeilen:
            laser_s = sum(_n((zeilen[i] or {}).get("einsparung")) * _n((zeilen[i] or {}).get("stueck")) for i in idx
                          if isinstance(i, int) and i < len(zeilen))
            laser_eur = sum(_n((zeilen[i] or {}).get("einsparung")) * _n((zeilen[i] or {}).get("stueck"))
                            * (_n(zeilen[i].get("laser_schneiden_teil")) / _n(zeilen[i].get("laser_netto"))
                               if _n((zeilen[i] or {}).get("laser_netto")) else 0.0)
                            for i in idx if isinstance(i, int) and i < len(zeilen) and zeilen[i])
        opt_z.update(schnitte=gem, laser_s=laser_s, laser_eur=laser_eur)
        z.append(opt_z)
        g = gruppen.get(schl + (grund,))
        if gem and g is not None and grund == a["stange"]:
            try:
                n3 = len(opt.optimiere(ohne_gemeinsamen_schnitt(g)))
            except Exception:       # noqa: BLE001 – Vergleich ist nur Anzeige
                n3 = None
            if n3 is not None:
                z3 = _zeile(OHNE_GEM, "3 optimiert ohne gemeinsamen Schnitt (nur Vergleich)", n3, a["stange"],
                            teile_mm, n, preis, kgm, schnitte=0, laser_s=0.0, laser_eur=0.0,
                            hinweis=f"gemeinsamer Schnitt spart {gem:g} Schnitte"
                                    + (f" und {rechnen.zahl(n3 - len(st), 0)} Stange(n)" if n3 > len(st) else ""))
                z.append(z3)
        v = var.get(schl)
        for x in (v or {}).get("varianten") or ():
            if x.get("geplant"):
                continue
            art = LAGER if x.get("lager") else LIEFER
            if art == LAGER and not lager_an:
                continue
            lang = _n(x.get("laenge")) * _n(x.get("stangen"))
            zz = dict(art=art, name=("5 " if art == LAGER else "4 ") + x["name"], stangen=x.get("stangen"),
                      eingeplant=n, nicht=0, kg=lang / 1000 * kgm if kgm and lang else None, eur=x.get("kosten"),
                      nutz_m=lang / 1000 if lang else None, verschnitt_mm=None, verschnitt=x.get("verschnitt"),
                      eur_teil=x["kosten"] / n if x.get("kosten") is not None and n else None, schnitte=None,
                      laser_s=None, laser_eur=None, ersparnis=None,
                      hinweis=("nicht ausführbar: " + x["fehler"]) if x.get("fehler") else "; ".join(x.get("fehlt") or ()))
            z.append(zz)
        basis = z[0]["eur"] if z and z[0]["art"] == EINFACH else None
        for x in z:
            if x["art"] != EINFACH and basis is not None and x["eur"] is not None:
                x["ersparnis"] = basis - x["eur"]
            if x["eur"] is None and not x["hinweis"]:
                x["hinweis"] = "Preis der Stange fehlt"
        out.append(dict(profil=a["profil"], werkstoff=a["werkstoff"], oberflaeche=a["oberflaeche"],
                        stange=a["stange"], teile=n, zeilen=z))
    return out


def text(w, schl):
    """Zellentext einer Spalte."""
    v = w.get(schl)
    if schl == "name":
        return v or ""
    if v is None:
        return "fehlt" if schl in ("eur", "eur_teil") else ""
    stellen = {"kg": 1, "eur": 2, "nutz_m": 2, "verschnitt_mm": 0, "verschnitt": 1, "eur_teil": 2, "laser_s": 0,
               "laser_eur": 2, "ersparnis": 2}.get(schl, 0)
    return rechnen.zahl(v, stellen)
