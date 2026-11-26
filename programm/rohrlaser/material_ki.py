"""Lokale Prüfvorschläge der Materialplattform (Phase 6 des Auftrags „Materialfenster Next Level“, 23.11.2026).

Alles läuft auf diesem PC aus den eigenen Stammdaten, ohne Internet (Dauerregel KI Patrick 20.11.2026). Jeder Befund
sagt, was auffällt, warum (Begründung mit Zahlen) und was man tun kann. Die Prüfung ändert nie selbst etwas; ein
Vorschlag mit Aktion wird erst mit „Übernehmen“ ausgeführt und im KI-Protokoll (ki_protokoll) vermerkt.
Materialgüte und technische Werte (Werkstoff, Dichte, Maße) ändert keine Aktion: dazu gibt es nur Hinweise.

Prüfungen:
- fehlende Stammdaten: Werkstoff ohne Dichte/Kategorie, Material in Angeboten nur mit Tonnenpreis oder ganz ohne
  Preis, Preis ohne Lieferant, Preisstand älter als die Einstellung preisalter_tage
- ungewöhnliche Preise: €/kg weit weg vom Median derselben Werkstoff- und Profilart (Faktor AUSREISSER), Preissprung
  zum vorigen Stand im Preisverlauf
- Dichte unplausibel für die Materialgruppe (häufiger Kalkulationsfehler)
- Dubletten: zwei Profil-IDs mit gleicher Form und gleichen Maßen
- günstigerer gültiger Lieferant bzw. Handelslänge (materialplattform.alternativen)
"""
import statistics

from . import materialplattform as mp
from .zahlen import float_oder_none as _n  # Audit 26.11.2026 R-01: gemeinsame Hilfsfunktion

HINWEIS, WARNUNG, VORSCHLAG = "HINWEIS", "WARNUNG", "VORSCHLAG"
AGENT = "Materialprüfung"
AUSREISSER = 1.6            # €/kg mehr als 1,6-mal bzw. weniger als 1/1,6 des Medians der Nachbarn
SPRUNG = 0.25               # Preisänderung über 25 % zum vorigen Stand
MIN_ERSPARNIS = 2.0         # günstigerer Lieferant ab 2 % Ersparnis
# Edelstahl ab 7,6: ferritische Sorten (1.4003, 1.4016, 1.4509) haben 7,7 kg/dm³
DICHTE = {"Stahl": (7.7, 8.0), "Edelstahl": (7.6, 8.1), "Aluminium": (2.6, 2.85), "Buntmetall": (7.3, 9.0)}


def _zahl(v, stellen=2):
    return f"{v:.{stellen}f}".replace(".", ",") if v is not None else "–"


def befund(stufe, art, material, text, begruendung, aktion=None, daten=None):
    return dict(art=stufe, typ=art, material=material, text=text, begruendung=begruendung, aktion=aktion,
                daten=daten or {}, agent=AGENT, schluessel=f"{AGENT}|{art}|{material}|{text}"[:500])


def pruefen(zeilen, k, tabellen, lieferanten=(), verlauf=None, einst=None, heute=None):
    """Alle Prüfungen über die Varianten (materialplattform.varianten). verlauf = {(profil, werkstoff): [Stände
    (preis €/m) alt → neu]} oder None. Ergebnis: Liste von Befunden, Warnungen und Vorschläge zuerst."""
    out = []
    alt_tage = _n((einst or {}).get("preisalter_tage"))
    alt_tage = 30 if alt_tage is None else alt_tage
    out += _werkstoffe(k)
    out += _dubletten(k)
    nachbarn = {}
    for z in zeilen:
        if z.get("preis_kg") is not None and z.get("quelle") in (mp.QUELLE_PREISE, mp.QUELLE_LIEFERLAENGE):
            nachbarn.setdefault((z["werkstoff_id"], z["form"]), []).append((z["profil_id"], z["preis_kg"]))
    for z in zeilen:
        name = f"{z['profil_id']} · {z['werkstoff_id']}"
        if z.get("nutzung") and z.get("quelle") == mp.QUELLE_FEHLT:
            out.append(befund(WARNUNG, "fehlt", name, "Material wird in Angeboten benutzt, hat aber keinen Preis",
                              f"In {z['nutzung']} Angeboten verwendet; weder Preise, Lieferlängen noch Tonnenpreis "
                              "des Werkstoffs liefern einen Preis."))
        elif z.get("nutzung", 0) >= 3 and z.get("quelle") == mp.QUELLE_TONNE:
            out.append(befund(HINWEIS, "tonnenpreis", name, "Häufig benutzt, aber nur mit dem Tonnenpreis gerechnet",
                              f"In {z['nutzung']} Angeboten verwendet; ein echter Lieferantenpreis (Preise oder "
                              "Preisliste) macht die Kalkulation genauer."))
        if z.get("quelle") == mp.QUELLE_PREISE and not z.get("lieferant"):
            out.append(befund(HINWEIS, "lieferant", name, "Preis ohne Lieferant",
                              "Die Zeile in 'Preise' nennt keinen Lieferanten; Materialanfrage und Preisvergleich "
                              "finden dann keinen Ansprechpartner."))
        if alt_tage and z.get("alter_tage") is not None and z["alter_tage"] > alt_tage and z.get("nutzung"):
            out.append(befund(HINWEIS, "alt", name, f"Preis {z['alter_tage']} Tage alt",
                              f"Gültig ab {z['stand']}, Grenze {int(alt_tage)} Tage (Einstellung Preisalter); "
                              "Materialanfrage oder Preisliste aktualisieren."))
        if z.get("erp_abw") is not None and abs(z["erp_abw"]) > mp.ERP_ABW_PCT:
            out.append(befund(HINWEIS, "erp", name, f"ERP-Einkauf {_zahl(z['erp_abw'], 1)} % "
                              + ("über" if z["erp_abw"] > 0 else "unter") + " dem Stammdatenpreis",
                              f"Eingekauft im Schnitt {_zahl(z['erp_schnitt'])} €/m ({z['erp_anzahl']} Käufe, "
                              f"zuletzt {_zahl(z['erp_letzter'])} €/m), Stammdaten {_zahl(z['preis_m'])} €/m. "
                              "ERP-Preise ändern die Stammdaten nie selbst; Preis bei Bedarf in 'Preise' anpassen."))
        ref = [p for pid, p in nachbarn.get((z["werkstoff_id"], z["form"]), []) if pid != z["profil_id"]]
        if z.get("preis_kg") is not None and len(ref) >= 3 and z.get("quelle") != mp.QUELLE_TONNE:
            med = statistics.median(ref)
            if med > 0 and (z["preis_kg"] > med * AUSREISSER or z["preis_kg"] < med / AUSREISSER):
                out.append(befund(WARNUNG, "ausreisser", name,
                                  f"Ungewöhnlicher Preis {_zahl(z['preis_kg'])} €/kg",
                                  f"Median der {len(ref)} anderen {z['form']} in {z['werkstoff_id']}: "
                                  f"{_zahl(med)} €/kg (Faktor {_zahl(z['preis_kg'] / med, 1)}). Preisbasis "
                                  "(€/kg, €/m, €/Stange) und Lieferlänge prüfen."))
        stande = (verlauf or {}).get((z["profil_id"], z["werkstoff_id"])) or []
        if len(stande) >= 2 and stande[-2] and abs(stande[-1] / stande[-2] - 1) > SPRUNG:
            out.append(befund(HINWEIS, "sprung", name,
                              f"Preissprung {_zahl((stande[-1] / stande[-2] - 1) * 100, 0)} %",
                              f"Voriger Stand {_zahl(stande[-2])} €/m, jetzt {_zahl(stande[-1])} €/m."))
        for a in mp.alternativen(z, lieferanten, k, tabellen, heute=heute):
            if a["art"] == "Lieferant" and a["ersparnis_pct"] is not None and a["ersparnis_pct"] >= MIN_ERSPARNIS:
                out.append(befund(VORSCHLAG, "guenstiger", name,
                                  f"{a['quelle'].get('lieferant')} ist {_zahl(a['ersparnis_pct'], 1)} % günstiger",
                                  f"{_zahl(a['preis_m'])} €/m statt {_zahl(z.get('preis_m'))} €/m ({a['text']}). "
                                  "Übernehmen setzt diesen Preis als aktiven Preis; gleicher Werkstoff, gleiche Güte.",
                                  aktion="preis_uebernehmen", daten=dict(lieferant_id=a["quelle"].get("id"))))
                break
    reihe = {WARNUNG: 0, VORSCHLAG: 1, HINWEIS: 2}
    return sorted(out, key=lambda b: reihe.get(b["art"], 3))


def _werkstoffe(k):
    out = []
    for wid, w in sorted(k.werkstoffe.items()):
        if mp.archiviert(w):
            continue
        d = _n(w.get("dichte"))
        if d is None:
            out.append(befund(WARNUNG, "dichte_fehlt", wid, "Werkstoff ohne Dichte",
                              "Ohne Dichte gibt es kein Gewicht und keinen Preis je kg."))
            continue
        if not w.get("kategorie"):
            out.append(befund(HINWEIS, "kategorie", wid, "Werkstoff ohne Materialgruppe",
                              "Ohne Kategorie fehlen Schneiddaten und Oberflächen der Gruppe."))
            continue
        bereich = DICHTE.get(w["kategorie"])
        if bereich and not bereich[0] <= d <= bereich[1]:
            out.append(befund(WARNUNG, "dichte", wid, f"Dichte {_zahl(d)} kg/dm³ unüblich für {w['kategorie']}",
                              f"Üblich {_zahl(bereich[0])} bis {_zahl(bereich[1])} kg/dm³. Nur prüfen: das Programm "
                              "ändert technische Werte nie selbst."))
    return out


OHNE_DUBLETTE = ("RP-Profil", "Sonderprofil")


def _dubletten(k):
    out, gesehen = [], {}
    for pid, p in sorted(k.profile.items()):
        if mp.archiviert(p) or _n(p.get("a")) is None or _n(p.get("wand")) is None or p.get("form") in OHNE_DUBLETTE:
            continue        # RP- und Sonderprofile: gleiche Hüllmaße, aber eigene Kontur
        b = _n(p.get("b"))
        schl = (p.get("form"), round(p["a"], 1), round(b, 1) if b is not None and p.get("form") != "Quadratrohr" else None,
                round(p["wand"], 2), _n(p.get("flaeche_manuell")))
        if schl in gesehen:
            out.append(befund(HINWEIS, "dublette", pid, f"Gleiche Abmessung wie {gesehen[schl]}",
                              f"{p.get('form')} mit gleichen Maßen und Wandstärke unter zwei Profil-IDs. Preise und "
                              "Lieferlängen gelten je ID; eine davon archivieren, wenn sie doppelt ist.",
                              aktion="archivieren", daten=dict(profil_id=pid)))
        else:
            gesehen[schl] = pid
    return out


def anwenden(db, b):
    """Vorschlag nach Freigabe ausführen und protokollieren. Ergebnis: Text für die Meldung."""
    from . import ki_protokoll
    if b.get("aktion") == "preis_uebernehmen":
        lz = next((z for z in db.zeilen(mp.LIEFERANTEN_TABELLE) if z.get("id") == b["daten"].get("lieferant_id")), None)
        if lz is None:
            raise ValueError("Die Lieferantenzeile gibt es nicht mehr.")
        ziel = mp.lieferant_uebernehmen(db, lz)
        text = f"Preis von {lz.get('lieferant')} für {b['material']} in '{ziel}' übernommen"
    elif b.get("aktion") == "preis_aus_historie":
        from . import material_historie
        d = b["daten"]
        text = material_historie.uebernehmen(db, d["profil_id"], d["werkstoff_id"], d["preis_m"], d.get("quelle", ""))
    elif b.get("aktion") == "archivieren":
        mp.archivieren(db, "profile", b["daten"]["profil_id"])
        text = f"Profil {b['daten']['profil_id']} archiviert"
    else:
        raise ValueError("Dieser Befund hat keine Aktion.")
    ki_protokoll.schreiben(db, AGENT, "Vorschlag übernommen", frage=b.get("text"), ergebnis=text,
                           quellen=[b.get("begruendung")])
    return text


def ablehnen(db, b):
    """Befund ablehnen: kommt als offene Empfehlung nicht wieder (ki_protokoll)."""
    from . import ki_protokoll
    i = ki_protokoll.empfehlung_merken(db, dict(b, art=VORSCHLAG if b.get("art") == HINWEIS else b.get("art")))
    if i:
        ki_protokoll.empfehlung_setzen(db, i, ki_protokoll.ABGELEHNT)
    ki_protokoll.schreiben(db, AGENT, "Vorschlag abgelehnt", frage=b.get("text"))


def abgelehnt(db):
    """Schlüssel der abgelehnten Befunde (werden in der Liste ausgeblendet)."""
    from . import ki_protokoll
    try:
        return {e.get("schluessel") for e in ki_protokoll.empfehlungen(db, status=ki_protokoll.ABGELEHNT)
                if e.get("agent") == AGENT}
    except Exception:           # noqa: BLE001
        return set()


def verlauf_je_material(db):
    """{(profil, werkstoff): [€/m-Stände alt → neu]} aus dem Preisverlauf (nur Preise mit Preisbasis €/m oder €/kg
    umrechenbar über das Gewicht)."""
    from . import preisverlauf
    k = db.kontext()
    out = {}
    try:
        for e in preisverlauf.eintraege(db.con, art=preisverlauf.ART_PREIS):
            pid, wid = e.get("profil_id"), e.get("werkstoff_id")
            kgm = mp.kg_je_m(k.profile.get(pid), k.werkstoffe.get(wid))
            pm = mp.je_meter(e.get("basis"), e.get("preis"), kgm, e.get("laenge") or 6000)
            if pm is not None:
                out.setdefault((pid, wid), []).append(pm)
    except Exception:           # noqa: BLE001
        from . import protokoll
        protokoll.warnung("Materialprüfung: abgefangen, ohne diese Angabe weiter")
    return out


def historie_befunde(db, zeilen, erp_gruppen=None, heute=None):
    """Preisvorschläge aus der Preishistorie (material_historie) als Befunde mit Aktion „preis_aus_historie“."""
    from . import material_historie as mh
    out = []
    for (pid, wid), v in mh.alle_vorschlaege(db, zeilen, erp_gruppen, heute).items():
        name = f"{pid} · {wid}"
        richtung = "" if v["abw"] is None else f" ({'+' if v['abw'] > 0 else ''}{_zahl(v['abw'], 1)} %)"
        b = befund(VORSCHLAG, "historie", name, f"Preisvorschlag {_zahl(v['preis_m'])} €/m{richtung}, Sicherheit "
                   f"{v['sicherheit']}", v["begruendung"] + ". Übernehmen schreibt den Preis nach 'Preise' "
                   "(Gültig ab heute); festgeschriebene Angebote bleiben.", aktion="preis_aus_historie",
                   daten=dict(profil_id=pid, werkstoff_id=wid, preis_m=v["preis_m"], quelle=v["quelle"],
                              sicherheit=v["sicherheit"]))
        b["schluessel"] = f"{AGENT}|historie|{name}|{round(v['preis_m'], 1)}"     # neuer Preis: neuer Vorschlag
        out.append(b)
    rang = {mh.HOCH: 0, mh.MITTEL: 1, mh.NIEDRIG: 2}
    return sorted(out, key=lambda b: (rang.get(b["daten"]["sicherheit"], 3), b["material"]))


def alle(db, zeilen=None):
    """Prüfung mit den Daten der Datenbank; abgelehnte Befunde fehlen."""
    zeilen = zeilen if zeilen is not None else mp.alle_varianten(db)
    weg = abgelehnt(db)
    erg = pruefen(zeilen, db.kontext(), db.tabellen(), db.zeilen(mp.LIEFERANTEN_TABELLE), verlauf_je_material(db),
                  db.einstellungen())
    vs = historie_befunde(db, zeilen)
    mit = {b["material"] for b in vs}
    erg = vs + [b for b in erg if not (b["typ"] == "erp" and b["material"] in mit)]
    from . import ki_protokoll
    ki_protokoll.schreiben(db, AGENT, "Prüfung", ergebnis=f"{len(erg)} Befunde")
    return [b for b in erg if b["schluessel"] not in weg]
