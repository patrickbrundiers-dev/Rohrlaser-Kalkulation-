"""Dashboard und Auswertungen der Aufträge (Plan Auftragsworkflow 13.11.2026, Paket 7).

Nur lesen: alles kommt aus der Sicht der Aufträge (auftraege.py) und ihren Ereignissen, nichts wird gespeichert.

- dashboard(): Zahlen für die Kacheln der Startseite (offen, in Produktion, verzögert, in der Qualitätskontrolle,
  fertig zum Ausliefern, diese Woche fällig).
- auswertung(): Kennzahlen für einen Zeitraum (Aufträge, deren Ende im Zeitraum liegt, bzw. Rückmeldungen im
  Zeitraum): Durchlaufzeit, Termintreue, verspätete Aufträge, Zeit je Arbeitsgang (Soll/Ist), Ausschussquote,
  Produktivität (Soll ÷ Ist) und kalkulierte gegen tatsächliche Kosten je Auftrag.

Tatsächliche Kosten: Material wie kalkuliert (Einkaufspreise sind im Auftrag nicht erfasst), Fertigung mit dem
Verhältnis Ist-Zeit ÷ Soll-Zeit der Arbeitsgänge hochgerechnet, dazu der Ausschuss mit den Selbstkosten je Teil.
Positionen ohne gemeldete Zeiten zählen wie kalkuliert.
"""
import datetime

from . import auftraege as au, auftrag_produktion as ap

ENDE = (au.FERTIG, au.AUSGELIEFERT, au.ABGESCHLOSSEN)
ZEITRAEUME = (("30", "Letzte 30 Tage"), ("90", "Letzte 90 Tage"), ("365", "Letzte 12 Monate"), ("jahr", "Dieses Jahr"),
              ("alle", "Alle"))


def _datum(iso):
    try:
        return datetime.date.fromisoformat(str(iso or "")[:10])
    except ValueError:
        return None


def zeitraum(schluessel, heute=None):
    """(von, bis) als ISO-Datum für einen Schlüssel aus ZEITRAEUME; 'alle' = ('', '')."""
    h = _datum(heute) or datetime.date.today()
    if schluessel == "alle":
        return "", ""
    if schluessel == "jahr":
        return f"{h.year}-01-01", h.isoformat()
    return (h - datetime.timedelta(days=int(schluessel))).isoformat(), h.isoformat()


def _im(iso, von, bis):
    d = str(iso or "")[:10]
    return bool(d) and (not von or d >= von) and (not bis or d <= bis)


def _alle(db):
    return [a for a in (au.auftrag(db, uid) for (uid,) in db.con.execute("SELECT uid FROM auftrag_kopf")) if a]


# ------------------------------------------------------------------ Dashboard (Startseite)
def dashboard(db, heute=None):
    """dict(offen, wert_offen, produktion, verzoegert, qs, lieferbar, woche) für die Kacheln der Startseite."""
    h = _datum(heute) or datetime.date.today()
    woche_bis = (h + datetime.timedelta(days=6 - h.weekday())).isoformat()
    out = dict(offen=0, wert_offen=0.0, produktion=0, verzoegert=0, qs=0, lieferbar=0, woche=0)
    for a in _alle(db):
        s = a.get("status") or au.NEU
        if s not in au.OFFEN:
            continue
        out["offen"] += 1
        out["wert_offen"] += a["wert"]
        out["produktion"] += s in (au.BEREIT, au.PRODUKTION)
        out["qs"] += s == au.QS
        out["lieferbar"] += s == au.FERTIG
        out["verzoegert"] += au.verzoegert(a, h.isoformat())
        t = str(a["kopf"].get("liefertermin") or "")[:10]
        out["woche"] += bool(t) and h.isoformat() <= t <= woche_bis
    out["wert_offen"] = round(out["wert_offen"], 2)
    return out


# ------------------------------------------------------------------ Auswertung
def zeiten(db, a, ereignisse_=None):
    """dict(start, ende, ende_status, geliefert_am): Anlage des Auftrags, erstes Erreichen von Fertiggestellt/
    Ausgeliefert/Abgeschlossen (aus den Ereignissen) und letzter Liefertag."""
    ev = ereignisse_ if ereignisse_ is not None else au.ereignisse(db, a["uid"])
    start = a.get("angelegt") or (ev[0]["am"] if ev else "")
    ende = ende_status = ""
    for e in ev:
        if e["art"] == au.STATUS and e.get("neu") in ENDE:
            ende, ende_status = e["am"], e["neu"]
            break
    from .auftrag_qs import lieferungen
    lief = [str(x.get("datum") or x.get("am") or "")[:10] for x in lieferungen(a)]
    if not ende and a.get("status") in ENDE:
        ende, ende_status = a.get("geaendert") or "", a.get("status")
    return dict(start=start or "", ende=ende, ende_status=ende_status, geliefert_am=max(lief) if lief else "")


def _tage(von, bis):
    a, b = _datum(von), _datum(bis)
    return (b - a).days if a and b else None


def kosten(a):
    """Kalkulierte und tatsächliche (hochgerechnete) Kosten eines Auftrags: dict(kalk, ist, material, fertigung_kalk,
    fertigung_ist, ausschuss, abweichung, mit_zeiten)."""
    from .auftrag_qs import _art, qs_stand
    mat = fk = fi = aus = 0.0
    mit = False
    for p in a["positionen"]:
        m, f = au._n(p.get("material")), au._n(p.get("fertigung"))
        zeilen, _ = ap.position_stand(p)
        soll = sum(au._n(x.get("sollzeit")) for x, z in zeilen if z["istzeit"] > 0)
        ist = sum(z["istzeit"] for _, z in zeilen if z["istzeit"] > 0)
        faktor = ist / soll if soll > 0 and ist > 0 else 1.0
        mit = mit or (soll > 0 and ist > 0)
        menge = au._n(p.get("menge"))
        selbst_teil = au._n(p.get("selbstkosten")) / menge if menge > 0 else 0.0
        ausschuss = qs_stand(p)["ausschuss"] + sum(z["ausschuss"] for x, z in zeilen if _art(x) != "qualität")
        mat += m
        fk += f
        fi += f * faktor
        aus += ausschuss * selbst_teil
    kalk = mat + fk
    tats = mat + fi + aus
    return dict(kalk=round(kalk, 2), ist=round(tats, 2), material=round(mat, 2), fertigung_kalk=round(fk, 2),
                fertigung_ist=round(fi, 2), ausschuss=round(aus, 2),
                abweichung=(tats - kalk) / kalk if kalk > 0 else None, mit_zeiten=mit)


def auswertung(db, von="", bis="", heute=None):
    """Kennzahlen im Zeitraum (ISO-Datum, leer = offen):
    dict(abgeschlossen, durchlauf_tage, termintreue, verspaetet[...], arbeitsgaenge[...], gut, ausschuss,
    ausschussquote, soll_min, ist_min, produktivitaet, kosten[...], kalk_summe, ist_summe)."""
    h = (_datum(heute) or datetime.date.today()).isoformat()
    durchlauf, puenktlich, mit_termin = [], 0, 0
    verspaetet, kosten_ = [], []
    gaenge = {}
    gut = ausschuss = soll_min = ist_min = 0.0
    for a in _alle(db):
        k = a["kopf"]
        termin = str(k.get("liefertermin") or "")[:10]
        z = zeiten(db, a)
        fertig_am = z["geliefert_am"] or z["ende"][:10]
        if z["ende"] and _im(fertig_am, von, bis):
            t = _tage(z["start"], fertig_am)
            if t is not None:
                durchlauf.append(max(0, t))
            if termin:
                mit_termin += 1
                if fertig_am <= termin:
                    puenktlich += 1
            c = kosten(a)
            kosten_.append(dict(uid=a["uid"], nummer=a["nummer"], kunde=k.get("kunde") or "", **c))
        # verspätet: offen und Termin vorbei, oder im Zeitraum fertig nach dem Termin
        spaet_tage = None
        if au.verzoegert(a, h):
            spaet_tage = _tage(termin, h)
        elif z["ende"] and termin and _im(fertig_am, von, bis) and fertig_am > termin:
            spaet_tage = _tage(termin, fertig_am)
        if spaet_tage:
            verspaetet.append(dict(uid=a["uid"], nummer=a["nummer"], kunde=k.get("kunde") or "", liefertermin=termin,
                                   tage=spaet_tage, status=a.get("status") or au.NEU,
                                   offen=(a.get("status") or au.NEU) in au.OFFEN))
        # Arbeitsgänge, Ausschuss, Produktivität: Rückmeldungen im Zeitraum
        for p in a["positionen"]:
            for x in p.get("arbeitsgaenge") or ():
                if not x.get("aktiv"):
                    continue
                rms = [r for r in ap.rueckmeldungen(p, x["uid"]) if _im(r.get("am"), von, bis)]
                if not rms:
                    continue
                st = ap.zustand(x, rms)
                g = gaenge.setdefault(x["name"], dict(name=x["name"], soll=0.0, ist=0.0, gut=0.0, ausschuss=0.0,
                                                      anzahl=0))
                g["gut"] += st["gut"]
                g["ausschuss"] += st["ausschuss"]
                g["anzahl"] += 1
                if st["status"] == ap.FERTIG and st["istzeit"] > 0:
                    g["soll"] += st["sollzeit"]
                    g["ist"] += st["istzeit"]
    for g in gaenge.values():
        g["abweichung"] = (g["ist"] - g["soll"]) / g["soll"] if g["soll"] > 0 else None
        gut += g["gut"]
        ausschuss += g["ausschuss"]
        soll_min += g["soll"]
        ist_min += g["ist"]
    kosten_.sort(key=lambda c: -(abs(c["abweichung"]) if c["abweichung"] is not None else -1))
    verspaetet.sort(key=lambda v: (not v["offen"], -v["tage"]))
    return dict(
        abgeschlossen=len(kosten_), durchlauf_tage=sum(durchlauf) / len(durchlauf) if durchlauf else None,
        termintreue=puenktlich / mit_termin if mit_termin else None, verspaetet=verspaetet,
        arbeitsgaenge=sorted(gaenge.values(), key=lambda g: g["name"].lower()), gut=gut, ausschuss=ausschuss,
        ausschussquote=ausschuss / (gut + ausschuss) if gut + ausschuss > 0 else None, soll_min=soll_min,
        ist_min=ist_min, produktivitaet=soll_min / ist_min if ist_min > 0 else None, kosten=kosten_,
        kalk_summe=round(sum(c["kalk"] for c in kosten_), 2), ist_summe=round(sum(c["ist"] for c in kosten_), 2))
