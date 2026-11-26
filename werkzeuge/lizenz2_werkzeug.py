"""Lizenz 2.0 im Lizenz-Werkzeug (nur bei Patrick): Zertifikate mit Lizenzschlüssel, Aktivierungen, Plätze freigeben.

Register: lizenzen2.json im Lizenzordner (neben lizenzen.csv der bisherigen Lizenzen). Es hält je Lizenznummer das
signierte Zertifikat und alle Aktivierungen (aktiv/frei). Regeln beim Aktivieren:
- gleiches Gerät (gleicher Geräteschlüssel) noch einmal: dieselbe Aktivierung neu ausgeben (kein neuer Platz);
- mindestens 2 von 3 Gerätemerkmalen wie eine aktive Aktivierung (Windows neu installiert, neue Platte): die alte wird
  frei, die neue übernimmt den Platz;
- sonst nur, solange aktive Aktivierungen < aktivierungen_max (Plätze + Reserve).
Gesperrte Lizenzen und deaktivierte Plätze kommen wie bisher über die Sperrliste (Lizenznummer bzw. Aktivierungs-ID).
Die Lizenzdatenbank mit Dashboard folgt in Paket L2-2.
"""
import datetime
import json
import re
from pathlib import Path

import lizenz_werkzeug as W
from rohrlaser import aktivierung as A
from rohrlaser import module as MD
from rohrlaser import lizenz

REGISTER2 = "lizenzen2.json"


def register_lesen(ordner):
    p = Path(ordner) / REGISTER2
    if not p.exists():
        d = {}
    else:                   # unlesbares Register nie still durch ein leeres ersetzen (Schlüssel gingen verloren)
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            raise SystemExit(f"Register {p} ist nicht lesbar ({e}). Bitte aus der Sicherung wiederherstellen; "
                             "es wurde nichts geändert.") from None
        if not isinstance(d, dict):
            raise SystemExit(f"Register {p} ist beschädigt. Bitte aus der Sicherung wiederherstellen.")
    d.setdefault("zertifikate", {})
    d.setdefault("aktivierungen", [])
    return d


def register_schreiben(ordner, d):
    lizenz._schreiben(Path(ordner) / REGISTER2, json.dumps(d, indent=1, ensure_ascii=False))


def naechste_nr(d, heute, praefix="LN"):
    p = f"{praefix}-{heute.year}-"
    werte = [int(k[len(p):]) for k in d["zertifikate"] if k.startswith(p)]
    return f"{p}{max(werte or [0]) + 1:04d}"


def naechste_aktivierung(d, heute):
    p = f"AK-{heute.year}-"
    werte = [int(a["aktivierung_id"][len(p):]) for a in d["aktivierungen"] if a["aktivierung_id"].startswith(p)]
    return f"{p}{max(werte or [0]) + 1:05d}"


def _dateiname(text):
    return re.sub(r"[^\w.-]+", "-", text or "").strip("-")


def zertifikat_ausstellen(ordner, lizenznehmer, typ, plaetze=1, *, firma="", kundennr="", benutzer=0, reserve=1,
                          module=None, bis=None, updates_bis=None, admins=(), hinweis="", heute=None, pw=None,
                          ziel=None, ersetzt=""):
    """Neues Lizenzzertifikat mit Lizenzschlüssel. Ergebnis: (Lizenzschlüssel, Zertifikat-Datei)."""
    ordner = Path(ordner)
    heute = heute or datetime.date.today()
    sid = W.aktueller_schluessel(ordner)
    privat = W.privat_laden(ordner, sid, pw)
    d = register_lesen(ordner)
    nr = naechste_nr(d, heute)
    schluessel = A.schluessel_neu()
    inhalt = A.zertifikat_inhalt(nr, schluessel, lizenznehmer, typ, plaetze, firma=firma, kundennr=kundennr,
                                 benutzer=benutzer, reserve=reserve, module=module, gueltig_bis=bis,
                                 updates_bis=updates_bis, admins=admins, heute=heute, schluessel_id=sid,
                                 hinweis=hinweis, ersetzt=ersetzt)
    zert = dict(format=A.FORMAT, inhalt=inhalt, signatur=lizenz.signieren(inhalt, privat))
    A.zertifikat_pruefen(zert, {sid: lizenz.oeffentlich_text(privat)})    # nur gültige verlassen das Werkzeug
    d["zertifikate"][nr] = dict(zertifikat=zert, lizenzschluessel=schluessel, gesperrt="")
    register_schreiben(ordner, d)
    ziel = Path(ziel) if ziel else ordner / "Zertifikate"
    ziel.mkdir(parents=True, exist_ok=True)
    datei = ziel / f"{nr}_{_dateiname(firma or lizenznehmer)}.zertifikat"
    datei.write_text(json.dumps(zert, indent=1, ensure_ascii=False), encoding="utf-8")
    return schluessel, datei


def _zertifikat_zum_schluessel(d, schluessel):
    pruef = A.schluessel_pruefwert(schluessel)
    for nr, e in d["zertifikate"].items():
        if e["zertifikat"]["inhalt"]["schluessel_pruef"] == pruef and not e.get("ersetzt_durch"):
            return nr, e
    raise SystemExit("Zu diesem Lizenzschlüssel gibt es kein Zertifikat im Register.")


def aktive(d, nr):
    return [a for a in d["aktivierungen"] if a["lizenz_nr"] == nr and a["status"] == "aktiv"]


def aktivieren(ordner, anfrage_quelle, heute=None, pw=None, ziel=None):
    """Aktivierungsanfrage prüfen und beantworten. Ergebnis: (Antwort-dict, Datei, Text zum Ergebnis)."""
    ordner = Path(ordner)
    heute = heute or datetime.date.today()
    try:
        anfrage = A.anfrage_pruefen(anfrage_quelle)
    except lizenz.LizenzFehler as e:
        raise SystemExit(f"Anfrage abgelehnt: {e}") from None
    d = register_lesen(ordner)
    nr, e = _zertifikat_zum_schluessel(d, anfrage["lizenzschluessel"])
    if e.get("gesperrt"):
        raise SystemExit(f"Lizenz {nr} ist gesperrt ({e['gesperrt']}).")
    z = e["zertifikat"]["inhalt"]
    bis = z.get("gueltig_bis")
    if bis and datetime.date.fromisoformat(bis) < heute:
        raise SystemExit(f"Lizenz {nr} ist am {bis} abgelaufen – zuerst verlängern.")
    liste = aktive(d, nr)
    gleich = next((a for a in liste if a["geraet"] == anfrage["geraet"]), None)
    text = ""
    if gleich:
        aid = gleich["aktivierung_id"]
        text = f"Gerät ist schon aktiviert ({aid}), Antwort neu ausgestellt."
    else:
        alt = next((a for a in liste if A.merkmale_treffer(a["merkmale"], anfrage["merkmale"]) >= A.MERKMALE_MIN),
                   None)
        if alt:
            alt.update(status="frei", frei_am=heute.isoformat(), frei_grund="gleicher Rechner neu aktiviert")
            text = f"Gleicher Rechner wie {alt['aktivierung_id']} (neu installiert): alter Platz freigegeben."
        elif len(liste) >= z["aktivierungen_max"]:
            namen = ", ".join(f"{a['aktivierung_id']} {a.get('name') or ''}".strip() for a in liste)
            raise SystemExit(f"Alle {z['aktivierungen_max']} Aktivierungen von {nr} sind belegt ({namen}). Erst einen "
                             "Platz freigeben (Freigabebeleg) oder deaktivieren.")
        aid = naechste_aktivierung(d, heute)
        d["aktivierungen"].append(dict(aktivierung_id=aid, lizenz_nr=nr, geraet=anfrage["geraet"],
                                       merkmale=anfrage["merkmale"], rechner_id=anfrage.get("rechner_id", ""),
                                       name=anfrage.get("name", ""), aktiviert_am=heute.isoformat(), status="aktiv"))
        text = (text + " " if text else "") + f"Neue Aktivierung {aid} ({len(liste) + (0 if alt else 1)} von " \
                                              f"{z['aktivierungen_max']} belegt)."
    sid = W.aktueller_schluessel(ordner)
    privat = W.privat_laden(ordner, sid, pw)
    antwort = A.antwort_erstellen(anfrage, e["zertifikat"], aid, privat, sid, heute)
    schl = dict(W.schluessel_bekannt(ordner), **{sid: lizenz.oeffentlich_text(privat)})
    A.antwort_pruefen(antwort, schl)        # nur gültige Antworten verlassen das Werkzeug
    register_schreiben(ordner, d)
    ziel = Path(ziel) if ziel else ordner / "Aktivierungen"
    ziel.mkdir(parents=True, exist_ok=True)
    datei = ziel / f"{aid}_{_dateiname(anfrage.get('name') or nr)}.lizenz"
    datei.write_text(json.dumps(antwort, indent=1, ensure_ascii=False), encoding="utf-8")
    return antwort, datei, text.strip()


def freigeben(ordner, beleg_quelle, heute=None):
    """Freigabebeleg eines Rechners verbuchen: Platz wieder frei. Ergebnis: Aktivierungs-ID."""
    heute = heute or datetime.date.today()
    d = register_lesen(ordner)
    try:
        roh = A.lesen(beleg_quelle)
        aid = (roh.get("inhalt") or {}).get("aktivierung_id")
        a = next((x for x in d["aktivierungen"] if x["aktivierung_id"] == aid), None)
        if a is None:
            raise SystemExit(f"Aktivierung {aid} ist nicht im Register.")
        A.freigabe_pruefen(roh, a["geraet"])
    except lizenz.LizenzFehler as e:
        raise SystemExit(f"Freigabe abgelehnt: {e}") from None
    a.update(status="frei", frei_am=heute.isoformat(), frei_grund="Freigabebeleg vom Rechner")
    register_schreiben(ordner, d)
    return aid


def deaktivieren(ordner, aktivierung_id, heute=None, pw=None):
    """Platz ohne Beleg deaktivieren (Rechner defekt oder verloren): im Register frei und auf die Sperrliste, damit
    eine Kopie nicht weiterläuft. Ergebnis: Pfad der neuen Sperrliste."""
    heute = heute or datetime.date.today()
    d = register_lesen(ordner)
    a = next((x for x in d["aktivierungen"] if x["aktivierung_id"] == aktivierung_id), None)
    if a is None:
        raise SystemExit(f"Aktivierung {aktivierung_id} ist nicht im Register.")
    a.update(status="frei", frei_am=heute.isoformat(), frei_grund="deaktiviert (Sperrliste)")
    register_schreiben(ordner, d)
    return W.sperren(ordner, [aktivierung_id], pw)


def lizenz_sperren(ordner, nr, heute=None, pw=None):
    """Ganze Lizenz (alle Plätze) sperren: Register + Sperrliste mit der Lizenznummer UND allen Vor- und Nachfolgern
    (ersetzt/ersetzt_durch), denn Rechner, die eine Verlängerung noch nicht geholt haben, laufen mit der alten Nummer."""
    heute = heute or datetime.date.today()
    d = register_lesen(ordner)
    if nr not in d["zertifikate"]:
        raise SystemExit(f"Lizenz {nr} ist nicht im Register.")
    nrs = kette(d, nr)
    for n in nrs:
        d["zertifikate"][n]["gesperrt"] = heute.isoformat()
    register_schreiben(ordner, d)
    return W.sperren(ordner, nrs, pw)


def kette(d, nr):
    """Alle Lizenznummern derselben Lizenz (Vorgänger und Nachfolger über ersetzt/ersetzt_durch), sortiert."""
    z = d["zertifikate"]
    gefunden, offen = set(), [nr]
    while offen:
        n = offen.pop()
        if n in gefunden or n not in z:
            continue
        gefunden.add(n)
        offen += [x for x in (z[n].get("ersetzt"), z[n].get("ersetzt_durch")) if x]
    return sorted(gefunden)


def aendern(ordner, nr, heute=None, pw=None, ziel=None, **neu):
    """Lizenz ändern (verlängern, Plätze/Benutzer ändern, übertragen): neues Zertifikat mit DEMSELBEN Lizenzschlüssel
    und Feld ersetzt=nr; die aktiven Plätze ziehen mit. Die Rechner holen sich das neue Zertifikat mit einer neuen
    Anfrage (gleicher Geräteschlüssel → gleiche Aktivierung, kein neuer Platz). neu: lizenznehmer, firma, kundennr,
    typ, plaetze, benutzer, reserve, module, bis (date oder None = unbefristet), updates_bis, admins, hinweis.
    Ergebnis: (neue Lizenznummer, Zertifikat-Datei)."""
    heute = heute or datetime.date.today()
    ordner = Path(ordner)
    d = register_lesen(ordner)
    e = d["zertifikate"].get(nr)
    if e is None:
        raise SystemExit(f"Lizenz {nr} ist nicht im Register.")
    if e.get("ersetzt_durch"):
        raise SystemExit(f"Lizenz {nr} wurde schon durch {e['ersetzt_durch']} ersetzt.")
    if e.get("gesperrt"):
        raise SystemExit(f"Lizenz {nr} ist gesperrt.")
    alt = e["zertifikat"]["inhalt"]
    werte = dict(lizenznehmer=alt["lizenznehmer"], firma=alt.get("firma", ""), kundennr=alt.get("kundennr", ""),
                 typ=alt["typ"], plaetze=alt["plaetze"], benutzer=alt.get("benutzer", 0),
                 reserve=alt["aktivierungen_max"] - alt["plaetze"], module=alt.get("module"),
                 bis=datetime.date.fromisoformat(alt["gueltig_bis"]) if alt.get("gueltig_bis") else None,
                 updates_bis=datetime.date.fromisoformat(alt["updates_bis"]) if alt.get("updates_bis") else None,
                 admins=alt.get("admins") or [], hinweis=alt.get("hinweis", ""))
    unbekannt = set(neu) - set(werte)
    if unbekannt:
        raise SystemExit(f"Unbekannte Felder: {', '.join(sorted(unbekannt))}")
    werte.update(neu)
    belegt = len(aktive(d, nr))
    maximal = (1 if werte["typ"] == "einzelplatz" else int(werte["plaetze"])) + max(0, int(werte["reserve"]))
    if belegt > maximal:
        raise SystemExit(f"{belegt} Plätze sind belegt, die neue Lizenz erlaubt nur {maximal}. Erst Plätze "
                         "freigeben oder deaktivieren.")
    sid = W.aktueller_schluessel(ordner)
    privat = W.privat_laden(ordner, sid, pw)
    neu_nr = naechste_nr(d, heute)
    schluessel = e["lizenzschluessel"]
    inhalt = A.zertifikat_inhalt(neu_nr, schluessel, werte["lizenznehmer"], werte["typ"], werte["plaetze"],
                                 firma=werte["firma"], kundennr=werte["kundennr"], benutzer=werte["benutzer"],
                                 reserve=werte["reserve"], module=werte["module"], gueltig_bis=werte["bis"],
                                 updates_bis=werte["updates_bis"], admins=werte["admins"], heute=heute,
                                 schluessel_id=sid, hinweis=werte["hinweis"], ersetzt=nr)
    zert = dict(format=A.FORMAT, inhalt=inhalt, signatur=lizenz.signieren(inhalt, privat))
    A.zertifikat_pruefen(zert, {sid: lizenz.oeffentlich_text(privat)})
    e["ersetzt_durch"] = neu_nr
    d["zertifikate"][neu_nr] = dict(zertifikat=zert, lizenzschluessel=schluessel, gesperrt="", ersetzt=nr)
    for a in aktive(d, nr):
        a["lizenz_nr"] = neu_nr
    register_schreiben(ordner, d)
    ziel = Path(ziel) if ziel else ordner / "Zertifikate"
    ziel.mkdir(parents=True, exist_ok=True)
    datei = ziel / f"{neu_nr}_{_dateiname(werte['firma'] or werte['lizenznehmer'])}.zertifikat"
    datei.write_text(json.dumps(zert, indent=1, ensure_ascii=False), encoding="utf-8")
    return neu_nr, datei


def status(eintrag, heute=None):
    """(Kurzwort, Text) einer Lizenz im Register: gesperrt, ersetzt, abgelaufen, laeuft_ab, gueltig, unbefristet."""
    heute = heute or datetime.date.today()
    z = eintrag["zertifikat"]["inhalt"]
    if eintrag.get("gesperrt"):
        return "gesperrt", f"gesperrt seit {eintrag['gesperrt']}"
    if eintrag.get("ersetzt_durch"):
        return "ersetzt", f"ersetzt durch {eintrag['ersetzt_durch']}"
    if not z.get("gueltig_bis"):
        return "unbefristet", "unbefristet"
    rest = (datetime.date.fromisoformat(z["gueltig_bis"]) - heute).days
    if rest < 0:
        return "abgelaufen", f"abgelaufen seit {-rest} Tagen"
    if rest <= W.ERINNERUNG_TAGE:
        return "laeuft_ab", f"läuft in {rest} Tagen ab"
    return "gueltig", "gültig"


def aktivierungen_von(ordner, nr):
    """Alle Aktivierungen einer Lizenz (auch über ersetzte Vorgänger), neueste zuerst."""
    d = register_lesen(ordner)
    nrs = set(kette(d, nr))
    return sorted((a for a in d["aktivierungen"] if a["lizenz_nr"] in nrs), key=lambda a: a["aktivierung_id"],
                  reverse=True)


def uebersicht(ordner, heute=None):
    """Zeilen je Zertifikat: Nummer, Lizenznehmer, Typ, belegt/max, Ablauf, gesperrt (für liste2 und Dashboard)."""
    d = register_lesen(ordner)
    zeilen = []
    for nr, e in sorted(d["zertifikate"].items()):
        z = e["zertifikat"]["inhalt"]
        st, st_text = status(e, heute)
        zeilen.append(dict(lizenz_nr=nr, lizenznehmer=z["lizenznehmer"], firma=z.get("firma", ""), typ=z["typ"],
                           plaetze=z["plaetze"], benutzer=z.get("benutzer", 0), belegt=len(aktive(d, nr)),
                           max=z["aktivierungen_max"], gueltig_bis=z.get("gueltig_bis") or "unbefristet",
                           gesperrt=e.get("gesperrt", ""), lizenzschluessel=e["lizenzschluessel"], status=st,
                           status_text=st_text, ersetzt_durch=e.get("ersetzt_durch", ""),
                           module=z.get("module") or ["alle"], module_text=MD.text(z.get("module"))))
    return zeilen
