"""Rückmeldungen füllen die Nachkalkulation (Plan Angebotskalkulation 16.11.2026, Paket K1, F2a). Ohne Qt.

Wird ein Auftrag fertiggestellt oder abgeschlossen, übernimmt das Programm die Ist-Zeiten je Arbeitsgang und den
Ausschuss aus den Rückmeldungen (auftrag_produktion) in die Nachkalkulation der zugehörigen Angebote:

- Faktor je Arbeitsgang einer Position = Ist-Zeit je Teil ÷ Soll-Zeit je Teil (Soll = Sollzeit ÷ Sollmenge der
  Arbeitsvorbereitung, Ist = Ist-Zeit ÷ (gut + Ausschuss)). Nur fertige Arbeitsgänge mit Ist-Zeit zählen.
- Laserzeit und Rüsten + Stangenwechsel = Soll der Nachkalkulation × Faktor des Arbeitsgangs Rohrlaser (der
  Arbeitsgang enthält beides, deshalb gilt der Faktor für beide Teile), Laufzeit je Teil = Soll je Teil × Faktor
  der Position (für die Kalibrierung der Schneiddaten).
- Schweißbaugruppen: Schweißen und Arbeitsgänge = Soll × Faktor des Arbeitsgangs Schweißen der Position.
- Ausschuss [Stück] aus Werkstatt und Qualitätsprüfung.
- Zeit je Arbeitsgang (Soll/Ist je Teil, Teile) für die Zeitvorschläge (Paket K2).

Von Hand eingetragene Werte bleiben und gehen vor; überschrieben werden nur leere Felder und Felder, die schon
aus Rückmeldungen stammen (ist['quelle'][Feld] = 'rueckmeldung'). Dazu wird wie beim Speichern im Angebot der
Soll-Stand festgehalten, damit Auswertung und Kalibrierung den Fall zählen. Geht die Rechnung nicht (kein
Schnittplan), werden nur Ausschuss und die Zeiten je Arbeitsgang übernommen.
"""
import datetime

from . import auftraege as au, auftrag_produktion as ap

QUELLE = "rueckmeldung"


def _art(x):
    from .auftrag_av import _schluessel
    return _schluessel(x.get("name"))


def faktor(x, z):
    """Ist ÷ Soll je Teil eines fertigen Arbeitsgangs oder None."""
    if z.get("status") != ap.FERTIG or z.get("istzeit", 0) <= 0:
        return None
    soll, menge = au._n(x.get("sollzeit")), au._n(x.get("sollmenge"))
    teile = au._n(z.get("gut")) + au._n(z.get("ausschuss"))
    if soll <= 0 or menge <= 0 or teile <= 0:
        return None
    return (z["istzeit"] / teile) / (soll / menge)


def _position_id(db, angebot_id, uid):
    r = db.con.execute("SELECT id FROM positionen WHERE angebot_id=? AND uid=?", (angebot_id, uid)).fetchone()
    if r:
        return r[0]
    t = str(uid or "").rsplit("-", 1)
    return int(t[1]) if len(t) == 2 and t[0] == str(angebot_id) and t[1].isdigit() else None


def werte(db, a):
    """{Angebots-uid: dict(positionen={Positions-ID: {Art: Faktor}}, laser=[(soll_min, ist_min)], ausschuss,
    arbeitsgaenge={Art: dict(name, soll_s, ist_s, teile, faelle)})} aus den Rückmeldungen des Auftrags."""
    out = {}
    for p in a["positionen"]:
        ang = p.get("angebot")
        if not ang:
            continue
        aid = au.angebot_id(db, ang)
        d = out.setdefault(ang, dict(angebot_id=aid, positionen={}, laser=[], ausschuss=0.0, arbeitsgaenge={}))
        zeilen, _ = ap.position_stand(p)
        pid = _position_id(db, aid, p.get("uid")) if aid else None
        from .auftrag_qs import qs_stand
        d["ausschuss"] += qs_stand(p)["ausschuss"] + sum(z["ausschuss"] for x, z in zeilen if _art(x) != "qualität")
        for x, z in zeilen:
            f = faktor(x, z)
            if f is None:
                continue
            art = _art(x)
            if pid is not None:
                d["positionen"].setdefault(pid, {})[art] = f
            if art == "laser":
                d["laser"].append((au._n(x["sollzeit"]) * (z["gut"] + z["ausschuss"]) / au._n(x["sollmenge"]),
                                   z["istzeit"]))
            teile = z["gut"] + z["ausschuss"]
            g = d["arbeitsgaenge"].setdefault(art, dict(name=x["name"], soll_s=0.0, ist_s=0.0, teile=0.0, faelle=0))
            g["soll_s"] += au._n(x["sollzeit"]) / au._n(x["sollmenge"]) * teile * 60
            g["ist_s"] += z["istzeit"] * 60
            g["teile"] += teile
            g["faelle"] += 1
    return out


def _frei(ist, feld):
    """Feld leer oder schon aus Rückmeldungen (darf neu geschrieben werden)."""
    return ist.get(feld) in (None, "") or (ist.get("quelle") or {}).get(feld) == QUELLE


def _setzen(ist, feld, wert, n):
    if wert is None or not _frei(ist, feld):
        return n
    ist[feld] = wert
    ist.setdefault("quelle", {})[feld] = QUELLE
    return n + 1


def _rechnung(db, kopf):
    """(Positionen, Kalkulationszeilen, Kontext, Tabellen, Einstellungen) oder None."""
    if not kopf.get("ergebnis") or not (kopf["ergebnis"] or {}).get("stangen"):
        return None
    from . import preis_simulator, rechnen
    try:
        pos = db.positionen(kopf["id"])
        k, tab, e = preis_simulator.grundlage(db, kopf)
        zeilen, summen = rechnen.kalkulation(kopf, pos, kopf["ergebnis"], k, tab, e)
        return pos, (zeilen, summen), k, tab, e
    except (ValueError, KeyError, TypeError, ZeroDivisionError, AttributeError):
        return None


def _gesamtfaktor(laser):
    soll = sum(s for s, _ in laser)
    return sum(i for _, i in laser) / soll if soll > 0 else None


def uebernehmen(db, uid):
    """Ist-Werte aus den Rückmeldungen in die Nachkalkulation der Angebote des Auftrags. Ergebnis: Anzahl
    geschriebener Felder."""
    from . import nachkalkulation as nk
    a = au.auftrag(db, uid)
    if a is None or db.nur_lesen:
        return 0
    n_ges = 0
    for ang_uid, w in werte(db, a).items():
        aid = w["angebot_id"]
        kopf = db.angebot(aid) if aid else None
        if not kopf or kopf.get("fremd"):
            continue
        ist = dict(kopf.get("nachkalkulation") or {})
        ist["quelle"] = dict(ist.get("quelle") or {})
        n = 0
        if w["ausschuss"] > 0:
            n = _setzen(ist, "ausschuss_stk", w["ausschuss"], n)
        if w["arbeitsgaenge"]:
            ist["arbeitsgaenge"] = {k: {f: round(v, 3) if isinstance(v, float) else v for f, v in g.items()}
                                    for k, g in w["arbeitsgaenge"].items()}
        r = _rechnung(db, kopf)
        f_laser = _gesamtfaktor(w["laser"])
        if r is not None:
            pos, kalk, k, tab, e = r
            zeilen = kalk[0]
            from . import bestellpreis        # K3: Bestellpreis als EK-Meterpreis Ist
            n += bestellpreis.in_nachkalkulation(ist, nk.gruppen(kopf["ergebnis"], kopf, pos, k, tab),
                                                 bestellpreis.eigene(db, aid, k))
            v = nk.vergleich(kopf, pos, kopf["ergebnis"], k, tab, e, {}, kalk=kalk)
            z = {x["text"]: x for x in v["zeilen"]}
            if f_laser is not None:
                n = _setzen(ist, "laser_h", round(z["Laserzeit"]["soll_menge"] * f_laser, 3), n)
                n = _setzen(ist, "ruest_min", round(z["Rüsten + Stangenwechsel"]["soll_menge"] * f_laser, 1), n)
            teile = nk.teile_soll(kopf, pos, zeilen, k, tab)
            lz = dict(ist.get("laufzeit") or {})
            lq = dict(ist["quelle"].get("laufzeit") or {})
            for t in teile:
                fp = (w["positionen"].get(t["id"]) or {}).get("laser")
                key = str(t["id"])
                if fp is None or (lz.get(key) not in (None, "") and lq.get(key) != QUELLE):
                    continue
                lz[key] = round(t["soll_s"] * fp, 2)
                lq[key] = QUELLE
                n += 1
            if lz:
                ist["laufzeit"] = lz
            if lq:
                ist["quelle"]["laufzeit"] = lq
            bg_ist = {b: dict(x) for b, x in (ist.get("baugruppen") or {}).items()}
            bq = dict(ist["quelle"].get("baugruppen") or {})
            for p, zk in zip(pos, zeilen):
                fs = (w["positionen"].get(p.get("id")) or {}).get("schweiß")
                if fs is None or not zk or not zk.get("baugruppe"):
                    continue
                b = (nk.baugruppen_soll([p], [zk]) or [{}])[0]
                if not b.get("id"):
                    continue
                e_ = bg_ist.setdefault(b["id"], {})
                for feld in ("schweiss_h", "arbeit_h"):
                    menge = b["werte"][feld][0]
                    schl = f"{b['id']}|{feld}"
                    if not menge or (e_.get(feld) not in (None, "") and bq.get(schl) != QUELLE):
                        continue
                    e_[feld] = round(menge * fs, 3)
                    bq[schl] = QUELLE
                    n += 1
            if bg_ist:
                ist["baugruppen"] = bg_ist
            if bq:
                ist["quelle"]["baugruppen"] = bq
        elif f_laser is not None and _frei(ist, "laser_h"):
            # ohne Schnittplan: gemeldete Minuten des Rohrlasers (enthalten Rüsten) wie bisher
            n = _setzen(ist, "laser_h", round(sum(i for _, i in w["laser"]) / 60, 2), n)
        if not n and not w["arbeitsgaenge"]:
            continue
        ist["aus_auftrag"] = a["nummer"]
        ist["am"] = ist.get("am") or datetime.datetime.now().isoformat(timespec="seconds")
        if not ist.get("bemerkung"):
            ist["bemerkung"] = f"aus den Rückmeldungen von Auftrag {a['nummer']} (von Hand Eingetragenes geht vor)"
        if r is not None:
            pos, kalk, k, tab, e = r
            zeilen = kalk[0]
            try:
                ist.pop("soll", None)
                v = nk.vergleich(kopf, pos, kopf["ergebnis"], k, tab, e, ist, kalk=kalk)
                ist["soll"] = nk.soll_stand(v, kopf, pos, kopf["ergebnis"], k,
                                            teile=nk.teile_soll(kopf, pos, zeilen, k, tab))
            except (ValueError, KeyError, TypeError, ZeroDivisionError, AttributeError):
                pass
        db.nachkalkulation_speichern(aid, ist)
        n_ges += n
    return n_ges


def aus_rueckmeldung(ist, feld, bg_id=None, position_id=None):
    """True, wenn der Wert aus Rückmeldungen stammt (Anzeige in der Nachkalkulation)."""
    q = (ist or {}).get("quelle") or {}
    if feld == "meterpreis" and bg_id is not None:      # K3: EK-Meterpreis Ist aus der Bestellung (bg_id = Gruppe)
        return (q.get("meterpreis") or {}).get(bg_id) == "bestellung"
    if position_id is not None:
        return (q.get("laufzeit") or {}).get(str(position_id)) == QUELLE
    if bg_id is not None:
        return (q.get("baugruppen") or {}).get(f"{bg_id}|{feld}") == QUELLE
    return q.get(feld) == QUELLE


def von_hand(ist, feld, bg_id=None, position_id=None):
    """Wert wurde von Hand geändert: Quelle entfernen (geht danach vor)."""
    q = (ist or {}).get("quelle")
    if not isinstance(q, dict):
        return
    if position_id is not None:
        (q.get("laufzeit") or {}).pop(str(position_id), None)
    elif feld == "meterpreis" and bg_id is not None:
        (q.get("meterpreis") or {}).pop(bg_id, None)
    elif bg_id is not None:
        (q.get("baugruppen") or {}).pop(f"{bg_id}|{feld}", None)
    else:
        q.pop(feld, None)
