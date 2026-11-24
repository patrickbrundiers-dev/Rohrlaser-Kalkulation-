"""Materialstamm: die Zuordnung Werkstoff × Abmessung (viele zu viele) mit Materialnummer, Aktiv und bevorzugtem
Lieferanten (Master-Auftrag Materialdatenbank, Patrick 23.11.2026). Ohne Qt.

- ergaenzen(): einmalige Übernahme aller Kombinationen, die es schon gibt (Preise, Lieferlängen,
  Material-Lieferanten, ERP-Zuordnungen mit Artikelnummer), damit nach dem Update nichts fehlt (Migration).
- werkstoffe_fuer(): Werkstoffe einer Abmessung für die Auswahl in der Kalkulation (aktive zuerst, nie geraten).
- lieferant_vorschlag(): wirtschaftlichster Lieferant für einen Bedarf mit Staffel, Mindestabnahme,
  Verpackungseinheit, Preisbasis und Lieferzeit.
- kennzahlen(): Zahlen für das Dashboard der Seite Material.
"""
import datetime
import math

from . import materialplattform as mp

STAMM = "materialstamm"
STAND = "2026-11-23"        # Einstellung materialstamm_stand: Übernahme aus dem Bestand gelaufen


def _heute():
    return datetime.date.today().isoformat()


def _t(x, st=2):
    from .stammdaten import zahl_als_text
    return zahl_als_text(x, st)


def _n(v):
    return mp._n(v)


def schluessel(z):
    return (z.get("profil_id"), z.get("werkstoff_id"), z.get("oberflaeche") or "")


def _ek_artikel(db, k):
    """{(profil, werkstoff, oberfläche): [dict(artikelnr, bezeichnung, kaeufe)]} aus dem EK-Import: gemerkte und sicher
    erkannte (grüne) Artikel mit Artikelnummer, meistgekaufte zuerst."""
    from . import erp_preise
    out = {}
    try:
        kaeufe = erp_preise.gespeicherte(db)
        artikel = erp_preise.artikel(kaeufe, erp_preise.zuordnungen(db), k) if kaeufe else []
        for z in erp_preise.zuordnungen(db).values():      # gemerkt ohne Käufe (z. B. aus dem Stammdaten-Import)
            if z.get("artikelnr") and not z.get("ignorieren") and not any(a["schluessel"] == z["schluessel"]
                                                                         for a in artikel):
                artikel.append(dict(z, ampel=erp_preise.GRUEN, kaeufe=0, meter=0.0))
    except Exception:           # noqa: BLE001  (Datei ohne ERP-Tabellen)
        from . import protokoll
        protokoll.warnung("Materialstamm: EK-Artikel nicht lesbar")
        return out
    for a in artikel:
        if a.get("ampel") != erp_preise.GRUEN or a.get("ignorieren") or not a.get("artikelnr"):
            continue
        s = (a.get("profil_id"), a.get("werkstoff_id"), a.get("oberflaeche") or "")
        if s[0] in k.profile and s[1] in k.werkstoffe:
            out.setdefault(s, []).append(dict(artikelnr=a["artikelnr"], bezeichnung=a.get("bezeichnung") or "",
                                              meter=a.get("meter") or 0.0))
    for v in out.values():
        v.sort(key=lambda x: -x["meter"])
    return out


def ergaenzen(db, quelle="Bestand (Update)"):
    """Materialstamm aus dem Bestand ergänzen (Patrick 23.11.2026: „Artikelnummer je Abmessung × Werkstoff aus dem
    Import übernehmen“): fehlende Kombinationen aus Preisen, Lieferlängen, Material-Lieferanten und EK-Import
    anlegen (aktiv, Herkunft quelle); bei vorhandenen Zeilen eine leere Materialnummer bzw. Bezeichnung aus dem
    EK-Import nachtragen (die meistgekaufte Artikelnummer). Ausgefüllte Werte bleiben. Ergebnis: dict(neu, nummern)."""
    k = db.kontext()
    vorhanden = {schluessel(z): z for z in db.zeilen(STAMM)}
    ek = _ek_artikel(db, k)
    neu = {}
    for t in ("preise", "lieferlaengen", mp.LIEFERANTEN_TABELLE):
        for z in db.zeilen(t):
            s = (z.get("profil_id"), z.get("werkstoff_id"), "")
            if s[0] in k.profile and s[1] in k.werkstoffe and s not in vorhanden:
                neu.setdefault(s, dict(lieferant=z.get("lieferant") if z.get("lieferant") in k.zukauf_lieferanten
                                       else None))
    for s in ek:
        if s not in vorhanden:
            neu.setdefault(s, {})
    heute = _heute()
    for s, e in neu.items():
        a = (ek.get(s) or [{}])[0]
        db.neu(STAMM, {kk: v for kk, v in dict(profil_id=s[0], werkstoff_id=s[1], oberflaeche=s[2] or None,
                                                 materialnr=a.get("artikelnr") or None,
                                                 bezeichnung=a.get("bezeichnung") or None, aktiv="ja",
                                                 angelegt=heute, geaendert=heute, quelle=quelle, **e).items()
                       if v is not None})
    nummern = 0
    for s, z in vorhanden.items():
        a = (ek.get(s) or [None])[0]
        if a is None:
            continue
        geaendert = False
        if not z.get("materialnr"):
            db.aendern(STAMM, z["id"], "materialnr", a["artikelnr"])
            geaendert = True
        if not z.get("bezeichnung") and a.get("bezeichnung"):
            db.aendern(STAMM, z["id"], "bezeichnung", a["bezeichnung"])
            geaendert = True
        if geaendert:
            db.aendern(STAMM, z["id"], "geaendert", heute)
            nummern += 1
    return dict(neu=len(neu), nummern=nummern)


def zeilen_je(db_oder_zeilen):
    """{(profil, werkstoff, oberfläche): Zeile} des Materialstamms."""
    zeilen = db_oder_zeilen.zeilen(STAMM) if hasattr(db_oder_zeilen, "zeilen") else db_oder_zeilen
    return {schluessel(z): z for z in zeilen}


def nummern(db):
    """{Nummer: dict(profil_id, werkstoff_id, oberflaeche, quelle)} vorhandener Materialien: Materialnummer (ERP) im
    Materialstamm und Artikel-/Bestellnummer der Lieferantenpreise. Eine Nummer, die auf mehrere Materialien zeigt,
    fehlt (nie raten)."""
    k = db.kontext()
    je = {}
    for z in db.zeilen(STAMM):
        if z.get("materialnr"):
            je.setdefault(str(z["materialnr"]).strip(), []).append(
                (z.get("profil_id"), z.get("werkstoff_id"), z.get("oberflaeche") or "", "Materialnummer (Materialstamm)"))
    for z in db.zeilen("material_lieferanten"):
        if z.get("artikelnr"):
            je.setdefault(str(z["artikelnr"]).strip(), []).append(
                (z.get("profil_id"), z.get("werkstoff_id"), "", f"Bestellnummer {z.get('lieferant') or 'Lieferant'}"))
    out = {}
    for nr, treffer in je.items():
        mat = {t[:3] for t in treffer}
        if len(mat) == 1 and nr:
            pid, wid, ober = next(iter(mat))
            if pid in k.profile and wid in k.werkstoffe:
                out[nr] = dict(profil_id=pid, werkstoff_id=wid, oberflaeche=ober, quelle=treffer[0][3])
    return out


def werkstoffe_fuer(profil_id, stamm_zeilen, k, nur_aktiv=True):
    """Werkstoffe, die es in dieser Abmessung laut Materialstamm gibt: [dict(werkstoff_id, aktiv, materialnr,
    bezeichnung)], aktive zuerst, dann nach Werkstoff-ID. Inaktive nur mit nur_aktiv=False. Eine Liste mit mehr als
    einem Eintrag heißt: in der Kalkulation wählen lassen, nicht raten."""
    out = {}
    for z in stamm_zeilen:
        if z.get("profil_id") != profil_id or z.get("werkstoff_id") not in k.werkstoffe:
            continue
        aktiv = z.get("aktiv") != "nein"
        if not aktiv and nur_aktiv:
            continue
        w = out.setdefault(z["werkstoff_id"], dict(werkstoff_id=z["werkstoff_id"], aktiv=aktiv,
                                                   materialnr=z.get("materialnr") or "",
                                                   bezeichnung=z.get("bezeichnung") or ""))
        w["aktiv"] = w["aktiv"] or aktiv
    return sorted(out.values(), key=lambda w: (not w["aktiv"], w["werkstoff_id"]))


def aktiv(stamm_je, profil_id, werkstoff_id):
    """False nur, wenn der Materialstamm die Kombination ausdrücklich als inaktiv führt (ohne Zeile: aktiv)."""
    zeilen = [z for s, z in stamm_je.items() if s[0] == profil_id and s[1] == werkstoff_id]
    return not zeilen or any(z.get("aktiv") != "nein" for z in zeilen)


# ------------------------------------------------------------------ Lieferantenvorschlag
def angebote_fuer(lieferanten_zeilen, profil_id, werkstoff_id, kgm, bedarf_m, stange_mm=6000, heute=None):
    """Alle gültigen Lieferantenpreise des Materials, gerechnet für den Bedarf [m]: je Lieferant und Lieferlänge die
    passende Staffel (größtes „ab“ ≤ Bedarf), dann Stangen = Bedarf ÷ Lieferlänge aufgerundet, mindestens die
    Mindestabnahme, aufgerundet auf die Verpackungseinheit. Ergebnis [dict(lieferant, laenge, preis_m, stangen, meter,
    kosten, lieferzeit, bevorzugt, staffel_ab, grund, zeile)], günstigste Kosten zuerst."""
    heute = heute or datetime.date.today()
    gruppen = {}
    for z in lieferanten_zeilen:
        if z.get("profil_id") != profil_id or z.get("werkstoff_id") != werkstoff_id or not mp.gueltig(z, heute):
            continue
        lg = _n(z.get("laenge")) or float(stange_mm)
        ab = _n(z.get("ab_menge")) or 0.0
        if ab > bedarf_m:
            continue
        g = gruppen.get((z.get("lieferant"), lg))
        if g is None or ab > (_n(g.get("ab_menge")) or 0.0):
            gruppen[(z.get("lieferant"), lg)] = z
    out = []
    for (lief, lg), z in gruppen.items():
        pm = mp.je_meter(z.get("basis"), z.get("preis"), kgm, lg)
        if pm is None:
            continue
        stangen = max(1, math.ceil(bedarf_m * 1000 / lg - 1e-9))
        gruende = []
        mindest = int(_n(z.get("mindest_stangen")) or 0)
        if mindest > stangen:
            gruende.append(f"Mindestabnahme {mindest} Stangen")
            stangen = mindest
        ve = int(_n(z.get("ve_stangen")) or 0)
        if ve > 1 and stangen % ve:
            stangen = math.ceil(stangen / ve) * ve
            gruende.append(f"Verpackungseinheit {ve} Stangen")
        meter = stangen * lg / 1000
        out.append(dict(lieferant=lief, laenge=lg, preis_m=pm, stangen=stangen, meter=meter, kosten=pm * meter,
                        lieferzeit=_n(z.get("lieferzeit")), bevorzugt=z.get("bevorzugt") == "ja",
                        staffel_ab=_n(z.get("ab_menge")), grund=", ".join(gruende), zeile=z))
    out.sort(key=lambda a: (round(a["kosten"], 2), a["lieferzeit"] if a["lieferzeit"] is not None else 9999,
                            not a["bevorzugt"]))
    return out


def lieferant_vorschlag(lieferanten_zeilen, profil_id, werkstoff_id, kgm, bedarf_m, stange_mm=6000, heute=None,
                        bis_tage=None, gleich_pct=2.0):
    """Wirtschaftlich sinnvollster Lieferant für den Bedarf oder None: der mit den geringsten Kosten für die
    tatsächlich zu kaufenden Stangen; liegt der bevorzugte Lieferant höchstens gleich_pct % darüber, wird er
    genommen. Mit bis_tage zählen nur Lieferanten mit Lieferzeit ≤ bis_tage (ohne Angabe: zählt). Ergebnis
    dict wie angebote_fuer mit begruendung."""
    alle = angebote_fuer(lieferanten_zeilen, profil_id, werkstoff_id, kgm, bedarf_m, stange_mm, heute)
    if bis_tage is not None:
        alle = [a for a in alle if a["lieferzeit"] is None or a["lieferzeit"] <= bis_tage]
    if not alle:
        return None
    best = alle[0]
    bev = next((a for a in alle if a["bevorzugt"]), None)
    if bev is not None and bev is not best and bev["kosten"] <= best["kosten"] * (1 + gleich_pct / 100):
        best = dict(bev, begruendung=f"bevorzugter Lieferant, nur {_t(bev['kosten'] - alle[0]['kosten'])} € "
                                     f"teurer als {alle[0]['lieferant']}")
        return best
    teile = [f"{best['stangen']} Stangen à {_t(best['laenge'] / 1000, 1)} m für {_t(bedarf_m, 1)} m Bedarf",
             f"{_t(best['kosten'])} €"]
    if best["grund"]:
        teile.append(best["grund"])
    if len(alle) > 1:
        d = alle[1]["kosten"] - best["kosten"]
        teile.append(f"{alle[1]['lieferant']} {'+' if d >= 0 else '−'}{_t(abs(d))} €")
    return dict(best, begruendung="; ".join(teile))


# ------------------------------------------------------------------ Dashboard
def kennzahlen(db, zeilen=None, heute=None):
    """Zahlen für das Dashboard: werkstoffe, abmessungen, varianten, lieferanten, stamm, inaktiv, ohne_preis,
    preis_alt, letzter_import (dict oder None), aenderungen_seit_import."""
    k = db.kontext()
    zeilen = mp.alle_varianten(db) if zeilen is None else zeilen
    lief = {z.get("lieferant") for z in db.zeilen(mp.LIEFERANTEN_TABELLE) if z.get("lieferant")}
    lief |= {z.get("lieferant") for z in db.zeilen("preise") if z.get("lieferant")}
    stamm = db.zeilen(STAMM)
    from . import material_import
    letzter = material_import.letzter_lauf(db)
    return dict(werkstoffe=sum(1 for w in k.werkstoffe.values() if not mp.archiviert(w)),
                abmessungen=sum(1 for p in k.profile.values() if not mp.archiviert(p)),
                varianten=len(zeilen), lieferanten=len(lief), stamm=len(stamm),
                inaktiv=sum(1 for z in stamm if z.get("aktiv") == "nein"),
                ohne_preis=sum(1 for z in zeilen if z.get("quelle") == mp.QUELLE_FEHLT),
                nur_tonne=sum(1 for z in zeilen if z.get("quelle") == mp.QUELLE_TONNE),
                preis_alt=sum(1 for z in zeilen if (z.get("alter_tage") or 0) > mp.STAND_ALT_TAGE),
                letzter_import=letzter,
                aenderungen_seit_import=(letzter or {}).get("preise", 0))
