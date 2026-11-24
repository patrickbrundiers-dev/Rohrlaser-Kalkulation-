"""Produktionsdaten-Intelligenz, Phase 3 (Patrick 24.11.2026): je zugeordnetem Teil die Kalkulation den Maschinendaten
gegenüberstellen und erklären, woher eine Abweichung kommt. Ohne Qt; baut auf lst_vergleich.vergleich auf (Zuordnung,
unsere Laserzeit ohne Nebenzeit, Zeit je Baustein) und auf den ausgelesenen Werten (produktion_lst, Spalte merkmale).

Werte (je Zeile: Kalkulation, Art, Maschinendaten, Art, Abweichung):
- Materialverbrauch je Teil: Teillänge + Schnittverlust der Maschine ↔ Bearbeitungslänge + Teileabstand (LST)
- Einstiche, Konturen, Schnittlänge, Konturklassen groß/mittel/klein (mm): Position (STEP-Messung) ↔ Programm
- Bearbeitungszeit: unsere Laserzeit ohne Nebenzeit ↔ gemessen bzw. vom CAM berechnet
- reine Laserzeit: Schneiden + Einstechen + Ecken ↔ Laser an (LST Verbrauchsgruppe 2, Leistung > 0)
- Positionierzeit: Verfahren und Drehen ↔ Laser aus (LST Verbrauchsgruppe 2, 0 W)
- Vorschub: Schnittlänge ÷ reine Laserzeit auf beiden Seiten (gleiche Rechnung, daher vergleichbar)
- Materialausnutzung bei nur diesem Teil: (Stange − Endbeschnitt − Greiferrest) ÷ Verbrauch ↔ dieselbe Rechnung mit
  den Werten des Programms
Fehlt ein Wert auf einer Seite, steht „fehlt“ (nichts wird ergänzt).

Ursachen: die Zeitabweichung wird in Anteile zerlegt (Schnittlänge, Einstiche, Positionieren, Vorschub/Laser, Rest),
jeder Anteil mit der Rechnung, aus der er folgt. Anteile unter UNWICHTIG_S zählen nicht."""
import statistics

from . import maschinendaten as md

UNWICHTIG_S = 0.3           # Anteile darunter werden nicht als Ursache genannt [s]
GEOMETRIE_PCT = 5.0         # Schnittlänge weicht mehr als 5 % ab: Geometrie, nicht Zeit

BERECHNET, GESCHAETZT, ERMITTELT, MASCHINE, FEHLT = "berechnet", "geschätzt", "ermittelt", "Maschinenwert", "fehlt"
PARAMETER = (
    ("material", "Materialverbrauch je Teil", "mm"),
    ("einstiche", "Schnittanzahl (Einstiche)", ""),
    ("konturen", "Konturen", ""),
    ("schnittlaenge", "Schnittlänge", "mm"),
    ("mm_gross", "Schnittlänge große Konturen", "mm"),
    ("mm_mittel", "Schnittlänge mittlere Konturen", "mm"),
    ("mm_klein", "Schnittlänge kleine Konturen", "mm"),
    ("zeit", "Bearbeitungszeit je Teil", "s"),
    ("laserzeit", "reine Laserzeit (Laser an)", "s"),
    ("positionierzeit", "Positionierzeit (Verfahren, Laser aus)", "s"),
    ("vorschub", "Vorschub (Schnittlänge ÷ Laserzeit)", "m/min"),
    ("ausnutzung", "Materialausnutzung (nur dieses Teil)", "%"),
)
TITEL = {s: t for s, t, _ in PARAMETER}


def _n(x):
    return x if isinstance(x, (int, float)) and not isinstance(x, bool) else None


def position(db, position_id, cache=None):
    """Position als dict (alle Spalten) oder {}."""
    if cache is not None and position_id in cache:
        return cache[position_id]
    cur = db.con.execute("SELECT * FROM positionen WHERE id=?", (position_id,))
    r = cur.fetchone()
    p = dict(zip([d[0] for d in cur.description], r)) if r else {}
    if cache is not None:
        cache[position_id] = p
    return p


def _zeile(schl, kalk, kalk_art, masch, masch_art, quelle=""):
    d = dict(schluessel=schl, titel=TITEL[schl], einheit=next(e for s, _, e in PARAMETER if s == schl),
             kalk=kalk, kalk_art=kalk_art if kalk is not None else FEHLT, maschine=masch,
             maschine_art=masch_art if masch is not None else FEHLT, quelle=quelle, diff=None, diff_pct=None)
    if kalk is not None and masch is not None:
        d["diff"] = round(masch - kalk, 3)
        d["diff_pct"] = round(100.0 * (masch / kalk - 1.0), 1) if kalk else None
    return d


def _ausnutzung(stange, laenge, verbrauch, rest):
    if not (_n(stange) and _n(laenge) and _n(verbrauch)) or verbrauch <= 0:
        return None
    n = int((stange - (rest or 0.0)) // verbrauch)
    return round(100.0 * n * laenge / stange, 1) if n > 0 else None


def werte(z, p, m_stamm=None, profil=None):
    """Vergleich einer Zeile von lst_vergleich.vergleich mit ihrer Position p und der Maschine der Kalkulation
    m_stamm (Stammdaten-Zeile): [dict(schluessel, titel, einheit, kalk, kalk_art, maschine, maschine_art, quelle,
    diff, diff_pct)] in der Reihenfolge von PARAMETER."""
    t = z["teil"]
    mk = t.get("merkmale") or {}
    bst = z.get("bausteine") or {}
    f = z.get("f_laser") or 1.0
    ms = m_stamm or {}
    out = []
    # Material
    lg = _n(p.get("laenge"))
    sv = _n(ms.get("schnittverlust")) or 0.0
    out.append(_zeile("material", round(lg + sv, 2) if lg else None, BERECHNET, _n(md.w(mk, "verbrauch_mm")),
                      ERMITTELT, "LST Bearbeitungslänge + Teileabstand; Kalkulation Länge + Schnittverlust"))
    # Geometrie
    out.append(_zeile("einstiche", _n(p.get("einstiche")), BERECHNET, _n(md.w(mk, "einstiche", t.get("einstiche"))),
                      ERMITTELT))
    n_k = sum(int(_n(p.get(f"{c}_n")) or 0) for c in ("gross", "mittel", "klein"))
    out.append(_zeile("konturen", n_k or None, BERECHNET, _n(md.w(mk, "konturen")), ERMITTELT,
                      "Maschine zählt Anschnitt und Abschnitt mit"))
    sw_m = _n(md.w(mk, "schneidweg", t.get("schneidweg")))
    out.append(_zeile("schnittlaenge", _n(p.get("schneidweg")), BERECHNET, sw_m, ERMITTELT,
                      (mk.get("schneidweg") or [None, "", ""])[2] if mk.get("schneidweg") else ""))
    for c in ("gross", "mittel", "klein"):
        out.append(_zeile(f"mm_{c}", _n(p.get(f"{c}_mm")), BERECHNET, _n(md.w(mk, f"mm_{c}")), ERMITTELT))
    # Zeiten
    ist = z.get("ist_s") if z.get("ist_s") is not None else z.get("lst_s")
    out.append(_zeile("zeit", z.get("soll_s"), GESCHAETZT, ist, MASCHINE if z.get("ist_s") is not None else BERECHNET,
                      "gemessen an der Maschine" if z.get("ist_s") is not None else "vom CAM berechnet"))
    laser_k = f * sum(bst.get(b) or 0.0 for b in ("schneiden", "einstechen", "ecken")) if bst else None
    laser_m = _n(md.w(mk, "laser_an_s"))
    out.append(_zeile("laserzeit", round(laser_k, 2) if laser_k else None, GESCHAETZT, laser_m, BERECHNET,
                      "LST Laser an (Verbrauchsgruppe 2)"))
    pos_k = f * (bst.get("bewegen") or 0.0) if bst else None
    out.append(_zeile("positionierzeit", round(pos_k, 2) if pos_k is not None else None, GESCHAETZT,
                      _n(md.w(mk, "verfahren_s")), BERECHNET, "LST Laser aus (Verbrauchsgruppe 2, 0 W)"))
    sw_k = _n(p.get("schneidweg"))
    v_k = round(sw_k / 1000.0 / (laser_k / 60.0), 2) if sw_k and laser_k else None
    v_m = round(sw_m / 1000.0 / (laser_m / 60.0), 2) if sw_m and laser_m else None
    out.append(_zeile("vorschub", v_k, BERECHNET, v_m, ERMITTELT, "Schnittlänge ÷ reine Laserzeit"))
    st = _n(md.w(mk, "stangenlaenge"))
    pr = profil or {}      # Endbeschnitt/Greiferrest des Profils gehen vor (wie in der Kalkulation)
    rest_k = (_n(pr.get("endbeschnitt")) or _n(ms.get("endbeschnitt")) or 0.0) + \
        (_n(pr.get("greiferrest")) or _n(ms.get("greiferrest")) or 0.0)
    out.append(_zeile("ausnutzung", _ausnutzung(st, lg, (lg or 0) + sv, rest_k), BERECHNET,
                      _n(md.w(mk, "ausnutzung_pct")), ERMITTELT, "gleiche Stangenlänge (aus dem Programm)"))
    return out


def ursachen(z, ws):
    """Zeitabweichung in Anteile zerlegen: [dict(ursache, anteil_s, rechnung)], größter Anteil zuerst; Anteile unter
    UNWICHTIG_S fallen weg. Leer, wenn es keine Zeitabweichung gibt."""
    v = {w["schluessel"]: w for w in ws}
    zt = v.get("zeit") or {}
    if zt.get("diff") is None:
        return []
    out = []
    lk, lm = (v.get("laserzeit") or {}).get("kalk"), (v.get("laserzeit") or {}).get("maschine")
    sk, sm = (v.get("schnittlaenge") or {}).get("kalk"), (v.get("schnittlaenge") or {}).get("maschine")
    bst = z.get("bausteine") or {}
    f = z.get("f_laser") or 1.0
    anteil_weg = 0.0
    if sk and sm and lk:
        schneiden = f * (bst.get("schneiden") or 0.0)
        anteil_weg = schneiden * (sm / sk - 1.0)
        out.append(dict(ursache="Schnittlänge" + (" (Geometrie prüfen)" if abs(100 * (sm / sk - 1)) > GEOMETRIE_PCT
                                                   else ""),
                        anteil_s=round(anteil_weg, 2),
                        rechnung=f"Schneidzeit {schneiden:.1f} s × (Programm {sm:.0f} mm ÷ Kalkulation {sk:.0f} mm − 1)"))
    ek, em = (v.get("einstiche") or {}).get("kalk"), (v.get("einstiche") or {}).get("maschine")
    anteil_stich = 0.0
    if ek and em is not None and bst.get("einstechen"):
        je = f * bst["einstechen"] / ek
        anteil_stich = (em - ek) * je
        out.append(dict(ursache="Einstiche", anteil_s=round(anteil_stich, 2),
                        rechnung=f"({em:.0f} − {ek:.0f}) Einstiche × {je:.2f} s"))
    pk, pm = (v.get("positionierzeit") or {}).get("kalk"), (v.get("positionierzeit") or {}).get("maschine")
    if pk is not None and pm is not None:
        out.append(dict(ursache="Positionieren und Verfahren", anteil_s=round(pm - pk, 2),
                        rechnung=f"Programm {pm:.1f} s − Kalkulation {pk:.1f} s"))
    if lk and lm:
        rest = lm - lk - anteil_weg - anteil_stich
        out.append(dict(ursache="Vorschub / Laserleistung", anteil_s=round(rest, 2),
                        rechnung=f"Laser an {lm:.1f} s − Kalkulation {lk:.1f} s − Anteile Schnittlänge und Einstiche"))
    erklaert = sum(u["anteil_s"] for u in out)
    rest = zt["diff"] - erklaert
    if abs(rest) >= UNWICHTIG_S:
        out.append(dict(ursache="übrige Zeit (Ecken, Anschnitt/Abschnitt, Nebenwege)" if lm else
                        "nicht weiter zerlegbar (Datei ohne Laser-an-/Verfahrzeit)", anteil_s=round(rest, 2),
                        rechnung="Zeitabweichung − erklärte Anteile"))
    out = [u for u in out if abs(u["anteil_s"]) >= UNWICHTIG_S]
    out.sort(key=lambda u: -abs(u["anteil_s"]))
    return out


def ursache_text(us, n=2):
    """'Vorschub / Laserleistung +3,2 s; Einstiche −0,8 s'."""
    return "; ".join(f"{u['ursache']} {u['anteil_s']:+.1f} s".replace(".", ",").replace("-", "−") for u in us[:n])


def auswerten(db, zeilen):
    """Je zugeordneter Zeile (mit Position) Werte und Ursachen: [dict(zeile, werte, ursachen)] (ohne Position fehlt die
    Zeile). Die Maschine der Kalkulation kommt aus den Stammdaten."""
    k = db.kontext()
    cache, out = {}, []
    for z in zeilen:
        pid = (z.get("zuordnung") or {}).get("position_id")
        if not pid:
            continue
        p = position(db, pid, cache)
        z["position"] = p
        ms = k.maschinen.get(z.get("maschine")) or {}
        ws = werte(z, p, ms, k.profile.get(p.get("profil_id")))
        out.append(dict(zeile=z, werte=ws, ursachen=ursachen(z, ws)))
    return out


def zusammenfassung(ergebnisse):
    """Über alle Teile je Wert: dict(schluessel: dict(n, median_pct, mittel_abs_pct)) und je Ursache der Median-Anteil
    {ursache: dict(n, median_s)}."""
    je, urs = {}, {}
    for e in ergebnisse:
        for w in e["werte"]:
            if w["diff_pct"] is not None:
                je.setdefault(w["schluessel"], []).append(w["diff_pct"])
        for u in e["ursachen"]:
            urs.setdefault(u["ursache"], []).append(u["anteil_s"])
    werte_ = {s: dict(n=len(x), median_pct=round(statistics.median(x), 1),
                      mittel_abs_pct=round(statistics.mean(abs(y) for y in x), 1)) for s, x in je.items()}
    return werte_, {u: dict(n=len(x), median_s=round(statistics.median(x), 2)) for u, x in urs.items()}
