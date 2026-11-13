"""Produktion und Rückmeldung je Arbeitsgang (Plan Auftragsworkflow 13.11.2026, Paket 4). Ohne Qt.

Rückmeldungen sind Ereignisse „rueckmeldung“ am Auftrag (Ziel = Position, Feld = Arbeitsgang): begonnen,
unterbrochen, fortgesetzt, Teilmenge, abgeschlossen, Problem (Maschinenstillstand, Material fehlt, Zeichnungsproblem,
Sonstiges), Problem gelöst, Ausschuss, Nacharbeit und Storno (macht eine falsche Rückmeldung unwirksam). Nichts wird
überschrieben; zwei Arbeitsplätze, die gleichzeitig Teilmengen melden, ergeben nach dem Abgleich die Summe.

Daraus gerechnet (nie gespeichert):
  Status je Arbeitsgang  Offen · Eingeplant (geplanter Start) · In Bearbeitung · Unterbrochen · Problem · Fertiggestellt
  Mengen                 gut = Teilmengen + Menge beim Abschluss, Ausschuss, Nacharbeit
  Zeiten                 Ist-Start, Ist-Ende, Istzeit (gemeldete Minuten, sonst die Zeit zwischen Beginnen und
                         Unterbrechen/Abschließen)
  Fortschritt            Arbeitsgang: gut ÷ Sollmenge (höchstens 100 %, abgeschlossen = 100 %); Position: gewichtet
                         mit der Sollzeit ihrer aktiven Arbeitsgänge (ohne Sollzeit zählt ein Schritt wie der
                         Durchschnitt); Auftrag: gewichtet mit der Sollzeit der Positionen. Keine Prozente von Hand.

Die erste Rückmeldung stellt einen produktionsbereiten Auftrag auf „In Produktion“.
"""
import datetime

from . import auftraege as au

BEGONNEN, UNTERBROCHEN, FORTGESETZT, TEILMENGE, ABGESCHLOSSEN = (
    "begonnen", "unterbrochen", "fortgesetzt", "teilmenge", "abgeschlossen")
PROBLEM, GELOEST, AUSSCHUSS, NACHARBEIT, STORNO = "problem", "geloest", "ausschuss", "nacharbeit", "storno"
TYPEN = (BEGONNEN, UNTERBROCHEN, FORTGESETZT, TEILMENGE, ABGESCHLOSSEN, PROBLEM, GELOEST, AUSSCHUSS, NACHARBEIT,
         STORNO)
TYP_TEXT = {BEGONNEN: "Arbeitsgang begonnen", UNTERBROCHEN: "Unterbrochen", FORTGESETZT: "Fortgesetzt",
            TEILMENGE: "Teilmenge fertig", ABGESCHLOSSEN: "Arbeitsgang abgeschlossen", PROBLEM: "Problem gemeldet",
            GELOEST: "Problem gelöst", AUSSCHUSS: "Ausschuss", NACHARBEIT: "Nacharbeit erforderlich",
            STORNO: "Rückmeldung storniert"}
GRUENDE = ("Maschinenstillstand", "Material fehlt", "Zeichnungsproblem", "Sonstiges")

OFFEN, EINGEPLANT, LAEUFT, PAUSE, GESTOERT, FERTIG = (
    "Offen", "Eingeplant", "In Bearbeitung", "Unterbrochen", "Problem / Klärung", "Fertiggestellt")
AG_STATUS = (OFFEN, EINGEPLANT, LAEUFT, PAUSE, GESTOERT, FERTIG)
NICHT_FERTIG = "Nicht fertig"           # Filter: alles außer Fertiggestellt
IN_PRODUKTION = (au.BEREIT, au.PRODUKTION, au.QS, au.TEILWEISE)     # Aufträge auf der Seite Produktion


def _zeit(iso):
    try:
        return datetime.datetime.fromisoformat(str(iso))
    except (TypeError, ValueError):
        return None


def _minuten(von, bis):
    a, b = _zeit(von), _zeit(bis)
    return max(0.0, (b - a).total_seconds() / 60) if a and b else 0.0


def gueltige(rms):
    """Rückmeldungen ohne stornierte (und ohne die Storno-Einträge selbst), nach Zeit."""
    weg = {(r.get("daten") or {}).get("bezug") for r in rms if r.get("typ") == STORNO}
    return sorted((r for r in rms if r.get("typ") != STORNO and r.get("uid") not in weg),
                  key=lambda r: r.get("am") or "")         # stabil: in derselben Sekunde gilt die Reihenfolge der Sicht


def zustand(ag, rms, jetzt=None):
    """Gerechneter Stand eines Arbeitsgangs aus seinen Rückmeldungen: dict(status, gut, ausschuss, nacharbeit,
    ist_start, ist_ende, istzeit, laeuft_seit, problem, fortschritt)."""
    gut = ausschuss = nacharbeit = gemeldet = 0.0
    start = ende = seit = None
    lauf_min = 0.0
    problem = ""
    fertig = False
    for r in gueltige(rms):
        t, d = r["typ"], r.get("daten") or {}
        gut += au._n(d.get("menge")) if t in (TEILMENGE, ABGESCHLOSSEN) else 0.0
        ausschuss += au._n(d.get("ausschuss"))
        nacharbeit += au._n(d.get("menge")) if t == NACHARBEIT else 0.0
        gemeldet += au._n(d.get("minuten"))
        if t in (BEGONNEN, FORTGESETZT):
            start = start or r["am"]
            seit = seit or r["am"]
            fertig = False
            problem = ""                # weiterarbeiten heißt: Problem erledigt
        elif t in (UNTERBROCHEN, PROBLEM, ABGESCHLOSSEN):
            if seit:
                lauf_min += _minuten(seit, r["am"])
                seit = None
            if t == PROBLEM:
                problem = " ".join(x for x in (d.get("grund") or "", r.get("bemerkung") or "") if x).strip() or "?"
            if t == ABGESCHLOSSEN:
                fertig, ende = True, r["am"]
                start = start or r["am"]
                problem = ""
        elif t == GELOEST:
            problem = ""
        elif t == TEILMENGE:
            start = start or r["am"]
    soll = au._n(ag.get("sollmenge"))
    if soll > 0 and gut >= soll:
        fertig = True
        ende = ende or max((r["am"] for r in gueltige(rms) if r["typ"] in (TEILMENGE, ABGESCHLOSSEN)), default=None)
    if fertig:
        status = FERTIG
    elif problem:
        status = GESTOERT
    elif seit:
        status = LAEUFT
    elif start:
        status = PAUSE
    elif ag.get("start"):
        status = EINGEPLANT
    else:
        status = OFFEN
    offen_min = _minuten(seit, (jetzt or datetime.datetime.now()).isoformat(timespec="seconds")) if seit else 0.0
    istzeit = gemeldet if gemeldet > 0 else lauf_min + offen_min
    fortschritt = 1.0 if fertig else (min(1.0, gut / soll) if soll > 0 else 0.0)
    return dict(status=status, gut=gut, ausschuss=ausschuss, nacharbeit=nacharbeit, ist_start=start or "",
                ist_ende=ende or "", istzeit=round(istzeit, 1), laeuft_seit=seit or "", problem=problem,
                fortschritt=fortschritt, soll=soll, sollzeit=au._n(ag.get("sollzeit")))


def rueckmeldungen(p, ag_uid=None):
    """Rückmeldungen einer Position (aus der Sicht), optional nur eines Arbeitsgangs."""
    return [r for r in p.get("_rm") or () if ag_uid is None or r.get("ag") == ag_uid]


def _gewichtet(teile):
    """[(gewicht, wert)] -> gewichteter Mittelwert; Gewicht 0 zählt wie der Durchschnitt der übrigen."""
    if not teile:
        return None
    pos = [g for g, _ in teile if g > 0]
    mittel = sum(pos) / len(pos) if pos else 1.0
    gew = [(g if g > 0 else mittel, w) for g, w in teile]
    summe = sum(g for g, _ in gew)
    return sum(g * w for g, w in gew) / summe if summe else None


def position_stand(p, jetzt=None):
    """[(arbeitsgang, zustand)] der aktiven, festgelegten Arbeitsgänge und Fortschritt der Position (oder None)."""
    gaenge = [x for x in p.get("arbeitsgaenge") or () if x.get("aktiv")]
    zeilen = [(x, zustand(x, rueckmeldungen(p, x["uid"]), jetzt)) for x in gaenge]
    return zeilen, _gewichtet([(au._n(x.get("sollzeit")), z["fortschritt"]) for x, z in zeilen])


def fortschritt(a, jetzt=None):
    """Fortschritt des Auftrags 0–1 aus den Mengen der Arbeitsgänge oder None (noch keine Arbeitsgänge)."""
    teile = []
    for p in a["positionen"]:
        zeilen, f = position_stand(p, jetzt)
        if f is not None:
            teile.append((sum(au._n(x.get("sollzeit")) for x, _ in zeilen), f))
    return _gewichtet(teile)


def _ag(a, position, ag_uid):
    p = next((x for x in a["positionen"] if x["uid"] == position), None)
    if p is None:
        raise au.AuftragFehler("Die Position gibt es im Auftrag nicht.")
    ag = next((x for x in p.get("arbeitsgaenge") or () if x.get("uid") == ag_uid), None)
    if ag is None:
        raise au.AuftragFehler("Den Arbeitsgang gibt es an dieser Position nicht (Arbeitsvorbereitung).")
    return p, ag


def rueckmelden(db, uid, position, ag_uid, typ, menge=0, ausschuss=0, minuten=None, grund="", bemerkung="",
                bezug=None):
    """Rückmeldung zu einem Arbeitsgang schreiben. Ergebnis: True (geschrieben) oder False (nichts zu tun, z. B.
    Beginnen eines laufenden Arbeitsgangs)."""
    if db.nur_lesen:
        raise au.AuftragFehler(f"Lesemodus – {db.nur_lesen}.")
    if typ not in TYPEN:
        raise au.AuftragFehler(f"Rückmeldung „{typ}“ gibt es nicht.")
    a = au.auftrag(db, uid)
    if a is None:
        raise au.AuftragFehler("Den Auftrag gibt es nicht mehr.")
    if a["status"] not in IN_PRODUKTION:
        raise au.AuftragFehler(f"Auftrag {a['nummer']} steht auf „{a['status']}“. Rückmelden geht erst, wenn er "
                               "produktionsbereit gemeldet ist (Arbeitsvorbereitung).")
    p, ag = _ag(a, position, ag_uid)
    if not ag.get("aktiv"):
        raise au.AuftragFehler(f"{ag['name']} ist für diese Position abgewählt.")
    m, aus = au._wert("menge", menge or 0), au._wert("menge", ausschuss or 0)
    minu = None if minuten in (None, "") else au._wert("menge", minuten)
    if m is None or aus is None or m < 0 or aus < 0 or (minu is not None and minu < 0):
        raise au.AuftragFehler("Mengen und Minuten müssen Zahlen ab 0 sein.")
    z = zustand(ag, rueckmeldungen(p, ag_uid))
    if typ == BEGONNEN and z["status"] == LAEUFT:
        return False
    if typ in (UNTERBROCHEN,) and z["status"] != LAEUFT:
        return False
    if typ == FORTGESETZT and z["status"] not in (PAUSE, GESTOERT):
        return False
    if typ == GELOEST and z["status"] != GESTOERT:
        return False
    if typ == ABGESCHLOSSEN and z["status"] == FERTIG and not m and not aus:
        return False
    if typ == TEILMENGE and not m and not aus:
        raise au.AuftragFehler("Bitte die fertige Menge (oder den Ausschuss) angeben.")
    if typ in (AUSSCHUSS, NACHARBEIT) and not (m or aus):
        raise au.AuftragFehler("Bitte die Menge angeben.")
    if typ == PROBLEM and not (str(grund or "").strip() or str(bemerkung or "").strip()):
        raise au.AuftragFehler("Bitte angeben, was das Problem ist.")
    if typ == STORNO:
        if not any(r.get("uid") == bezug for r in rueckmeldungen(p, ag_uid)):
            raise au.AuftragFehler("Die Rückmeldung gibt es nicht.")
        if not str(bemerkung or "").strip():
            raise au.AuftragFehler("Storno nur mit Grund (steht in der Historie).")
    if typ == AUSSCHUSS and m and not aus:
        m, aus = 0.0, m                 # „Ausschuss 3“: die Menge ist der Ausschuss
    daten = {k: v for k, v in dict(menge=m or None, ausschuss=aus or None, minuten=minu, grund=grund or None,
                                    bezug=bezug).items() if v not in (None, "")}
    with db.con:
        if a["status"] == au.BEREIT and typ in (BEGONNEN, TEILMENGE, ABGESCHLOSSEN, FORTGESETZT):
            au._ereignis(db, uid, au.STATUS, feld="status", alt=au.BEREIT, neu=au.PRODUKTION,
                         bemerkung="automatisch (erste Rückmeldung)")
        au._ereignis(db, uid, au.RUECKMELDUNG, ziel=position, feld=ag_uid, neu=typ, daten=daten,
                     alt=ag["name"], bemerkung=bemerkung)
    return True


def zeilen(db, jetzt=None):
    """Alle aktiven Arbeitsgänge der Aufträge in Produktion (für die Seite Produktion): [dict(...)]."""
    out = []
    for (uid,) in db.con.execute("SELECT uid FROM auftrag_kopf WHERE status IN (%s) ORDER BY nummer"
                                 % ",".join("?" * len(IN_PRODUKTION)), IN_PRODUKTION).fetchall():
        a = au.auftrag(db, uid)
        k = a["kopf"]
        for p in a["positionen"]:
            for x, z in position_stand(p, jetzt)[0]:
                out.append(dict(z, auftrag=uid, nummer=a["nummer"], kunde=k.get("kunde") or "",
                                liefertermin=k.get("liefertermin") or "", position=p["uid"], pos=p["nr"],
                                artikel=p.get("artikel") or "", bezeichnung=p.get("bezeichnung") or "",
                                ag=x["uid"], name=x["name"], maschine=x.get("maschine") or "",
                                mitarbeiter=x.get("mitarbeiter") or "", start=x.get("start") or "",
                                ende=x.get("ende") or "", auftrag_status=a["status"]))
    return out


def arbeitsplatz(z):
    """Arbeitsplatz einer Zeile: Maschine, sonst der Arbeitsgang."""
    return z["maschine"] or z["name"]


def filtern(zeilen_, platz="", status="", suche=""):
    s = str(suche or "").strip().lower()
    out = []
    for z in zeilen_:
        if platz and arbeitsplatz(z) != platz:
            continue
        if status == NICHT_FERTIG and z["status"] == FERTIG:
            continue
        if status not in ("", "Alle", NICHT_FERTIG) and z["status"] != status:
            continue
        if s and s not in " ".join((z["nummer"] or "", z["kunde"], z["artikel"], z["bezeichnung"], z["name"],
                                    z["mitarbeiter"])).lower():
            continue
        out.append(z)
    return out


def verlauf(p, ag_uid):
    """Rückmeldungen eines Arbeitsgangs zum Anzeigen (neueste zuerst), stornierte markiert."""
    weg = {(r.get("daten") or {}).get("bezug") for r in rueckmeldungen(p, ag_uid) if r.get("typ") == STORNO}
    neueste = list(reversed(rueckmeldungen(p, ag_uid)))      # gleiche Sekunde: zuletzt eingegangen zuerst
    return [dict(r, storniert=r.get("uid") in weg) for r in sorted(neueste, key=lambda r: r.get("am") or "",
                                                                    reverse=True)]
