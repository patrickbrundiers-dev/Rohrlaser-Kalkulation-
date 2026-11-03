"""Admin-Schutz der Einstellungen (Plan „Admin-Schutz für Einstellungen“, Patrick 30.10.2026, Freigabe
„1c 2a 3a 4b 5a 6a 7a 8a“).

Statt eines Passworts für den ganzen Reiter Einstellungen hat jede Einstellungsseite und jede Stammdatentabelle die
Stufe „frei“ oder „nur Admin“ (Bereiche). Welche Bereiche geschützt sind, legt der Admin auf der Seite Admin-Schutz
fest (Einstellung ADMIN_SEITEN, leer = VORGABE). Admin ist, wer in dieser Sitzung das Admin-Passwort (oder einen
Notfallcode) eingegeben hat – am Platz mit Admin-Lizenz beim Start, an jedem anderen Platz über „Als Admin
freischalten …“. Nach MINUTEN ohne Eingabe sperrt der Schutz wieder (Sitzung.ablauf_pruefen). Ohne Admin-Passwort
(Einstellung 'passwort' leer) ist nichts gesperrt.

Admin-Vorgaben für alle Arbeitsplätze: Die Werte der geschützten Bereiche gehen nicht über den normalen Abgleich
(jüngste Änderung gewinnt), sondern als ein Paket (Admin-Vorgaben) in die Ablage. Nur ein freigeschalteter Admin
schreibt es (paket_schreiben), jeder Platz übernimmt es beim Lesen (paket_lesen + paket_anwenden) und stellt
abweichende Werte wieder her – ein Nicht-Admin kann sie also nicht dauerhaft überschreiben. Die Ablage ist heute der
gemeinsame Ordner (OrdnerAblage, Datei Admin/admin_vorgaben.json); für einen späteren Server-Abgleich genügt eine
zweite Ablage mit lesen()/schreiben(). Der Schutz liegt im Programm: die Prüfsumme erkennt beschädigte Dateien, ist
aber keine Verschlüsselung.

Hauptadmin und weitere Admins (Patrick 30.10.2026, Freigabe „1a 2a 3a 4a 5a“ + Seite „Arbeitsplätze und Rechte“):
Hauptadmin ist, wer das Admin-Passwort der Admin-Lizenz (oder einen Notfallcode) eingibt. Er vergibt auf der Seite
Arbeitsplätze und Rechte je Mitarbeiter (Kürzel) das Recht Mitarbeiter, Admin oder gesperrt (Liste ADMINS, kommt mit
den Admin-Vorgaben an alle Plätze). Ein Admin schaltet sich mit seinem eigenen Passwort frei – an jedem Arbeitsplatz
mit gültiger Lizenz –, ändert alle geschützten Seiten, aber nicht Admin-Schutz und Rechte (HAUPT_SEITEN). Das
Startpasswort vom Hauptadmin ändert er beim ersten Freischalten. Wer gesperrt wird, verliert die Freischaltung beim
nächsten Abgleich. Jedes Paket trägt im Verlauf, welcher Admin was geändert hat.

Ohne Qt, damit teilen.py und die Tests es nutzen können.
"""
import datetime
import hashlib
import json
import time
from pathlib import Path

from . import einstellungen_ordnung as ordnung
from . import passwort as pw

ADMIN_SEITEN = "admin_seiten"           # Liste der geschützten Bereiche (None = VORGABE); kommt mit dem Paket
STAND = "admin_vorgaben_stand"          # lokal: {stand, von, hash} des zuletzt übernommenen/geschriebenen Pakets
SEITE_ADMIN = "e_admin"                 # die Seite Admin-Schutz selbst: immer geschützt
SEITE_PLAETZE = "e_plaetze"             # Seite Arbeitsplätze und Rechte: nur der Hauptadmin
HAUPT_SEITEN = (SEITE_ADMIN, SEITE_PLAETZE)
ADMINS = "admin_liste"                  # {Kürzel: {name, recht, hash, neu, stand}}; kommt mit dem Paket
VERLAUF = "admin_verlauf"               # lokal: [{zeit, wer, was}] aus dem Paket (wer hat was geändert)
VERLAUF_MAX = 300
LIZENZ_INFO = "lizenz_info"             # lokal: Lizenz dieses Platzes für die Übersicht (Hauptfenster)
MITARBEITER, ADMIN, GESPERRT = "mitarbeiter", "admin", "gesperrt"
RECHTE = ((MITARBEITER, "Mitarbeiter"), (ADMIN, "Admin"), (GESPERRT, "Admin gesperrt"))
HAUPTADMIN = "Hauptadmin"
FRACHT = "fracht"                       # Pflege der Frachtdaten (alle Tabellen aus fracht_daten)
ZEITVORGABEN = "zeitvorgaben"           # Stundensätze und Arbeitsschritte
MINUTEN = 15                            # ohne Eingabe so lange freigeschaltet (Frage 4b)
FORMAT = 1
DATEI = "admin_vorgaben.json"
ORDNER = "Admin"

# Vorschlag nach Risiko (Plan): Geld, Stammdaten mit Preis- oder Zeitwirkung, Firma und Steuerung
VORGABE = ("e_funktionen", "e_firma", "e_ablage", "e_zuschlaege", "e_gewinn_gestaffelt", "e_kosten",
           "e_neue_angebote", "e_automatik", "e_lieferlaengen", "e_blech",
           "preise", "werkstoffe", "maschinen", "schneiddaten", ZEITVORGABEN, "zusatzarbeiten",
           "arbeitsgang_regeln", FRACHT)
# immer frei: eigener Arbeitsplatz; Profile, damit „Unbekannte Abmessung anlegen“ im Popup weiter geht
NIE = ("e_arbeitsplatz", "kunden")
IMMER = HAUPT_SEITEN


def bereiche():
    """Alle Bereiche, die geschützt werden können: [(Schlüssel, Titel, Art)], Art 'einstellungen' oder 'stammdaten'."""
    from .stammdaten import TABELLEN
    aus = [(s.schluessel, s.titel, "einstellungen") for s in ordnung.SEITEN if s.schluessel not in NIE]
    zeit = False
    for t in TABELLEN:
        if t.name in NIE:
            continue
        if t.name in ("stundensaetze", "arbeitsschritte"):
            if not zeit:
                aus.append((ZEITVORGABEN, "Stundensätze und Zeitvorgaben", "stammdaten"))
                zeit = True
            continue
        aus.append((t.name, t.titel, "stammdaten"))
    aus.append((FRACHT, "Frachtkosten (Zonen, Tarife, Zuschläge …)", "stammdaten"))
    return aus


def tabellen_von(schluessel):
    """Stammdatentabellen eines Bereichs (leer bei Einstellungsseiten)."""
    if schluessel == ZEITVORGABEN:
        return ("stundensaetze", "arbeitsschritte")
    if schluessel == FRACHT:
        from .fracht_daten import FRACHT_TABELLEN
        return tuple(t.name for t in FRACHT_TABELLEN)
    from .stammdaten import TABELLE
    return (schluessel,) if schluessel in TABELLE else ()


def geschuetzt_liste(db, seiten=None):
    """Geschützte Bereiche (Menge der Schlüssel); seiten: Liste aus einem Paket statt der Einstellung."""
    wert = seiten if seiten is not None else (db.einstellung(ADMIN_SEITEN) if db is not None else None)
    liste = VORGABE if wert is None else wert
    return (set(liste) | set(IMMER)) - set(NIE)


def aktiv(db):
    """Schutz eingeschaltet: es gibt ein Admin-Passwort (Einstellung 'passwort', bei Admin-Lizenz von dort kopiert)."""
    return db is not None and bool(db.einstellung("passwort"))


def einstellungen_geschuetzt(db, seiten=None):
    """Namen der Einstellungen, die nur der Admin ändert: alles auf einer geschützten Seite (steht eine Einstellung
    auf zwei Seiten, reicht eine geschützte), dazu Passwort und Schutzliste. Nie die Werte nur dieses Arbeitsplatzes."""
    from .teilen import LOKAL
    schutz = geschuetzt_liste(db, seiten)
    namen = {"passwort", ADMIN_SEITEN, ADMINS}
    for s in ordnung.SEITEN:
        if s.schluessel in schutz:
            for a in s.abschnitte:
                namen.update(a.namen)
    if FRACHT in schutz:                # Einstellungen im Reiter Frachtkosten (Historie und Einstellungen)
        from .stammdaten import EINSTELLUNGEN
        namen.update(e.name for e in EINSTELLUNGEN if e.gruppe == ordnung.EIGENER_REITER)
    return namen - set(LOKAL)


def tabellen_geschuetzt(db, seiten=None):
    """Namen der Stammdatentabellen, die nur der Admin ändert."""
    aus = set()
    for b in geschuetzt_liste(db, seiten):
        aus.update(tabellen_von(b))
    return aus


# ------------------------------------------------------------------ Sitzung: wer ist gerade Admin
class Sitzung:
    """Admin-Freischaltung dieses Arbeitsplatzes. freigeschaltet: Admin-Passwort in dieser Sitzung eingegeben (Admin-
    Lizenz beim Start oder „Als Admin freischalten …“). Nach MINUTEN ohne Eingabe (eingabe() vom Fenster) gesperrt.
    jemals: in dieser Sitzung schon einmal Admin (dann schreibt der Platz die Admin-Vorgaben, auch nach dem Sperren)."""

    def __init__(self, uhr=time.monotonic):
        self.uhr = uhr
        self.freigeschaltet = False
        self.jemals = False
        self.wer = ""               # HAUPTADMIN (Lizenz-Passwort, Notfallcode) oder das Kürzel des Admins
        self.letzte = uhr()

    def freischalten(self, wer=HAUPTADMIN):
        self.freigeschaltet = self.jemals = True
        self.wer = wer
        self.letzte = self.uhr()

    def sperren(self):
        self.freigeschaltet = False

    @property
    def haupt(self):
        """Gerade als Hauptadmin freigeschaltet."""
        return self.freigeschaltet and self.wer == HAUPTADMIN

    def eingabe(self):
        self.letzte = self.uhr()

    def ablauf_pruefen(self):
        """True, wenn die Freischaltung gerade abgelaufen ist (dann gesperrt)."""
        if self.freigeschaltet and self.uhr() - self.letzte >= MINUTEN * 60:
            self.freigeschaltet = False
            return True
        return False


SITZUNG = None          # Sitzung des Hauptfensters (ohne Fenster, z. B. Tests von teilen: kein Admin)


def ist_admin(db, sitzung=None):
    """Darf hier gerade Geschütztes ändern: kein Admin-Passwort gesetzt oder Admin freigeschaltet. Ein Admin, den der
    Hauptadmin inzwischen gesperrt oder entfernt hat, verliert die Freischaltung hier."""
    s = sitzung if sitzung is not None else SITZUNG
    if not aktiv(db):
        return True
    if s and s.freigeschaltet and not s.haupt and recht(db, s.wer) != ADMIN:
        s.sperren()
    return bool(s and s.freigeschaltet)


def ist_haupt(db, sitzung=None):
    """Darf Admin-Schutz und Rechte ändern: kein Admin-Passwort gesetzt oder als Hauptadmin freigeschaltet."""
    s = sitzung if sitzung is not None else SITZUNG
    return not aktiv(db) or bool(s and s.haupt)


# ------------------------------------------------------------------ Hauptadmin und weitere Admins
def admins(db):
    """{Kürzel: {name, recht, hash, neu, stand}} – nur Admins und gesperrte Admins, Mitarbeiter fehlen."""
    return {k: dict(v) for k, v in (db.einstellung(ADMINS) or {}).items() if isinstance(v, dict)}


def recht(db, kuerzel):
    """Recht eines Mitarbeiters: ADMIN, GESPERRT oder MITARBEITER."""
    return (admins(db).get(kuerzel) or {}).get("recht") or MITARBEITER


def _jetzt():
    return datetime.datetime.now().isoformat(timespec="seconds")


def recht_setzen(db, kuerzel, neu, name="", startpasswort=None):
    """Hauptadmin: Recht vergeben. Admin braucht ein Passwort (beim ersten Mal das Startpasswort, das der Admin beim
    Freischalten ändert); gesperrt behält das Passwort, Mitarbeiter entfernt den Eintrag. Ergebnis: Fehlertext oder ''."""
    liste = admins(db)
    e = dict(liste.get(kuerzel) or {})
    if neu == MITARBEITER:
        liste.pop(kuerzel, None)
    else:
        if startpasswort:
            if len(startpasswort) < 6:
                return "Das Startpasswort braucht mindestens 6 Zeichen."
            e.update(hash=pw.hash_bilden(startpasswort), neu=True)
        if neu == ADMIN and not e.get("hash"):
            return "Für einen Admin bitte ein Startpasswort vergeben."
        e.update(recht=neu, name=name or e.get("name") or "", stand=_jetzt())
        liste[kuerzel] = e
    db.einstellung_setzen(ADMINS, liste)
    return ""


def admin_finden(db, passwort):
    """Weiterer Admin zum Passwort: (Kürzel, Eintrag) oder (None, Grund), Grund '' = kein Admin mit diesem Passwort."""
    if not passwort:
        return None, ""
    gesperrt = False
    for k, e in sorted(admins(db).items()):
        if e.get("hash") and pw.pruefen(passwort, e["hash"]):
            if e.get("recht") == ADMIN:
                return k, e
            gesperrt = True
    return None, ("Dieser Admin ist gesperrt (Hauptadmin)." if gesperrt else "")


def passwort_aendern(db, kuerzel, neu):
    """Admin ändert sein Passwort (Startpasswort beim ersten Freischalten). Ergebnis: Fehlertext oder ''."""
    liste = admins(db)
    if kuerzel not in liste:
        return "Kein Admin."
    if not neu or len(neu) < 6:
        return "Das Passwort braucht mindestens 6 Zeichen."
    liste[kuerzel].update(hash=pw.hash_bilden(neu), neu=False, stand=_jetzt())
    db.einstellung_setzen(ADMINS, liste)
    return ""


def plaetze(db):
    """Übersicht für die Seite Arbeitsplätze und Rechte: je Mitarbeiter (Kürzel aus dem gemeinsamen Ordner und dieser
    Platz) Name, Rechner, Lizenz, Version, zuletzt gesehen und Recht. Sortiert nach Name."""
    from . import teilen
    liste = admins(db)
    aus = []
    import socket
    from . import VERSION
    ich = teilen.kuerzel(db)
    for k, m in teilen.mitarbeiter(db).items():
        m = dict(m or {})
        if k == ich:                    # dieser Platz: aktuell statt aus der eigenen Datei
            m.update(rechner=socket.gethostname(), version=VERSION, stand=_jetzt(),
                     lizenz=db.einstellung(LIZENZ_INFO) or {})
        aus.append(dict(kuerzel=k, name=m.get("name") or (liste.get(k) or {}).get("name") or "",
                        rechner=m.get("rechner") or "", version=m.get("version") or "", stand=m.get("stand") or "",
                        lizenz=dict(m.get("lizenz") or {}), recht=recht(db, k), ich=k == ich))
    bekannt = {p["kuerzel"] for p in aus}
    for k, e in liste.items():          # Admin ohne Datei im Ordner (z. B. noch nie abgeglichen)
        if k not in bekannt:
            aus.append(dict(kuerzel=k, name=e.get("name") or "", rechner="", version="", stand="", lizenz={},
                            recht=e.get("recht") or MITARBEITER, ich=False))
    return sorted(aus, key=lambda p: ((p["name"] or p["kuerzel"]).lower(), p["kuerzel"]))


def lizenz_info(zustand):
    """Lizenz eines Platzes für die Übersicht (Einstellung LIZENZ_INFO, geht mit der Datei im Ordner an alle)."""
    if zustand is None:
        return {}
    i = zustand.inhalt or {}
    return {"art": i.get("art") or "", "lizenz_id": i.get("lizenz_id") or "", "inhaber": i.get("inhaber") or "",
            "gueltig_bis": i.get("gueltig_bis") or "", "stufe": zustand.stufe, "rechner_id": zustand.rechner_id or ""}


def lizenz_text(info):
    """(Text, Ampel 'gruen' | 'gelb' | 'rot' | '') für eine Lizenz aus lizenz_info()."""
    if not info:
        return "unbekannt", ""
    st = info.get("stufe")
    if st == "admin":
        return "Admin-Lizenz (unbefristet)", "gruen"
    bis = info.get("gueltig_bis") or ""
    datum = ".".join(reversed(bis.split("-"))) if bis else ""
    art = "Testlizenz" if info.get("art") == "test" else "Lizenz"
    if st == "gueltig":
        return f"{art} bis {datum}", "gruen"
    if st in ("bald", "kulanz"):
        return f"{art} bis {datum}" + (" (abgelaufen, Kulanz)" if st == "kulanz" else " (läuft bald ab)"), "gelb"
    return ("abgelaufen" + (f" am {datum}" if datum else "")) if bis else "keine Lizenz", "rot"


def lizenz_gueltig(info):
    """Admin-Recht nur an einem Platz mit gültiger Lizenz (Admin-, Benutzer- oder Testlizenz, auch Kulanz)."""
    return bool(info) and info.get("stufe") in ("admin", "gueltig", "bald", "kulanz")


def verlauf(db):
    return list(db.einstellung(VERLAUF) or [])


def _was(alt, neu):
    """Was sich zwischen zwei Paket-Inhalten geändert hat (Text für den Verlauf)."""
    from .stammdaten import EINSTELLUNG, TABELLE
    alt = alt or {}
    teile = []
    ea, en = alt.get("einstellungen") or {}, neu.get("einstellungen") or {}
    namen = sorted(n for n in set(ea) | set(en) if ea.get(n) != en.get(n) and n != "passwort")
    if namen:
        titel = [(EINSTELLUNG[n].titel if n in EINSTELLUNG else {ADMINS: "Rechte"}.get(n, n)) for n in namen]
        teile.append("Einstellungen: " + ", ".join(titel[:6]) + (f" und {len(titel) - 6} weitere" if len(titel) > 6
                                                                    else ""))
    ta, tn = alt.get("tabellen") or {}, neu.get("tabellen") or {}
    tab = sorted(t for t in set(ta) | set(tn) if ta.get(t) != tn.get(t))
    if tab:
        teile.append("Tabellen: " + ", ".join(TABELLE[t].titel if t in TABELLE else t for t in tab))
    if sorted(alt.get("seiten") or ()) != sorted(neu.get("seiten") or ()) and alt:
        teile.append("Admin-Schutz (Häkchen)")
    return "; ".join(teile) or ("erste Admin-Vorgaben" if not alt else "")


# ------------------------------------------------------------------ Admin-Vorgaben für alle Arbeitsplätze
class OrdnerAblage:
    """Admin-Vorgaben über den Austauschweg (austausch.py): heute Datei Admin/admin_vorgaben.json im gemeinsamen
    Ordner, atomar ersetzt; ein späterer Server-Weg liefert dieselben Dateien."""

    def __init__(self, weg):
        from . import austausch
        self.weg = weg if hasattr(weg, "datei_lesen") else austausch.OrdnerWeg(weg)
        self.pfad = Path(str(self.weg)) / ORDNER / DATEI

    def lesen(self):
        return self.weg.datei_lesen(ORDNER, DATEI)

    def schreiben(self, daten):
        self.weg.datei_schreiben(daten, ORDNER, DATEI)


def ablage(db):
    """Ablage der Admin-Vorgaben oder None (kein gemeinsamer Ordner)."""
    from . import teilen
    w = teilen.weg(db)
    return OrdnerAblage(w) if w is not None else None


def _hash(inhalt):
    return hashlib.sha256(json.dumps(inhalt, sort_keys=True, ensure_ascii=False, default=str)
                          .encode("utf-8")).hexdigest()


def inhalt(db, seiten=None):
    """Werte der geschützten Bereiche dieses Platzes: Schutzliste, Einstellungen, Tabellenzeilen (Form wie im
    Abgleich: je Zeile die Kennung uid, Verweise als Kennung)."""
    from . import teilen
    if seiten is None:
        seiten = sorted(geschuetzt_liste(db))
    namen = einstellungen_geschuetzt(db, seiten)
    tabellen = tabellen_geschuetzt(db, seiten)
    from .stammdaten import EINSTELLUNG
    roh = dict(db.con.execute("SELECT name, wert FROM einstellungen"))
    einst = {}
    for name in sorted(namen - {ADMIN_SEITEN}):     # auch Vorgabewerte: sonst bliebe ein abweichender Wert stehen
        if name in roh:
            einst[name] = roh[name]
        elif name in EINSTELLUNG:
            einst[name] = json.dumps(EINSTELLUNG[name].vorgabe, ensure_ascii=False)
    zeilen = {t: {} for t in sorted(tabellen) if t in teilen.GETEILT_NAME}
    for (t, u), daten in teilen.lokale_zeilen(db.con).items():
        if t in zeilen:
            zeilen[t][u] = daten
    return {"seiten": list(seiten), "einstellungen": einst, "tabellen": zeilen}


def schema(db):
    return db.con.execute("PRAGMA user_version").fetchone()[0]


def paket_lesen(db, abl=None):
    """Admin-Vorgaben aus der Ablage: dict (format, stand, von, schema, hash, inhalt) oder None (keine, beschädigt,
    neuere Programmversion: dann mit 'hinweis')."""
    abl = abl if abl is not None else ablage(db)
    if abl is None:
        return None
    try:
        roh = abl.lesen()
    except OSError:
        return None
    if not roh:
        return None
    try:
        p = json.loads(roh.decode("utf-8"))
        if not isinstance(p, dict) or not isinstance(p.get("inhalt"), dict):
            raise ValueError("kein Paket")
    except (ValueError, UnicodeDecodeError):
        return {"hinweis": "Admin-Vorgaben im gemeinsamen Ordner sind nicht lesbar und werden übergangen."}
    if p.get("hash") != _hash(p["inhalt"]):
        return {"hinweis": "Admin-Vorgaben im gemeinsamen Ordner sind beschädigt (Prüfsumme) und werden übergangen."}
    if int(p.get("format") or 0) > FORMAT or int(p.get("schema") or 0) > schema(db):
        return {"hinweis": f"Admin-Vorgaben stammen von einer neueren Programmversion ({p.get('version')}); sie "
                           "gelten hier erst nach dem Update."}
    return p


def gueltig(p):
    return bool(p) and "inhalt" in p


def _stand(db):
    return dict(db.einstellung(STAND) or {})


def _lokal_hash(db, seiten):
    return _hash(inhalt(db, seiten))


def paket_anwenden(db, p):
    """Werte des Pakets hier eintragen (Schutzliste, Einstellungen, Tabellen). Zeilen, die das Paket nicht kennt,
    entfallen – außer das Paket stammt von einer älteren Programmversion (dann fehlen dort neue Richtwerte)."""
    from . import teilen
    con = db.con
    inh = p["inhalt"]
    seiten = list(inh.get("seiten") or VORGABE)
    with con:
        db._einstellung_schreiben(ADMIN_SEITEN, seiten)
        for name, wert in (inh.get("einstellungen") or {}).items():
            con.execute("INSERT OR REPLACE INTO einstellungen (name, wert) VALUES (?, ?)", (name, wert))
        loeschen = int(p.get("schema") or 0) >= schema(db)
        for t, zeilen in (inh.get("tabellen") or {}).items():
            tab = teilen.GETEILT_NAME.get(t)
            if tab is None:
                continue
            hier = teilen._uid_karte(con, t)            # id -> uid
            if loeschen:
                for i, u in hier.items():
                    if u not in zeilen:
                        con.execute(f'DELETE FROM "{t}" WHERE id=?', (i,))
            for u, daten in zeilen.items():
                werte = dict(daten)
                ids = {uu: i for i, uu in teilen._uid_karte(con, t).items()}
                andere = None if u in ids else teilen._schluessel_treffer(con, tab, werte, u)
                if andere is not None:          # gleicher Schlüssel unter anderer Kennung: Zeile übernimmt sie
                    con.execute(f'UPDATE "{t}" SET uid=? WHERE id=?', (u, andere[0]))
                try:
                    teilen._zeile_setzen(db, t, u, werte)
                except Exception:       # noqa: BLE001 – eine Zeile passt nicht (Schlüssel doppelt): nächstes Mal
                    continue
    db.einstellung_setzen(STAND, {"stand": p.get("stand"), "von": p.get("von"), "hash": _lokal_hash(db, seiten),
                                  "paket": p.get("hash")})
    if isinstance(p.get("verlauf"), list):
        db.einstellung_setzen(VERLAUF, p["verlauf"][-VERLAUF_MAX:])


def paket_schreiben(db, sitzung=None, abl=None, wer=""):
    """Als Admin die Werte der geschützten Bereiche in die Ablage legen, wenn sie sich hier seit dem letzten Paket
    geändert haben. Ergebnis: True = geschrieben."""
    s = sitzung if sitzung is not None else SITZUNG
    if not aktiv(db) or not (s and s.jemals):
        return False
    abl = abl if abl is not None else ablage(db)
    if abl is None:
        return False
    inh = inhalt(db)
    h = _hash(inh)
    st = _stand(db)
    if st.get("hash") == h and gueltig(paket_lesen(db, abl)):
        return False
    from . import VERSION
    stand = datetime.datetime.now().isoformat(timespec="seconds")
    alt = paket_lesen(db, abl)
    alt = alt if gueltig(alt) else None
    liste = list((alt or {}).get("verlauf") or verlauf(db))
    was = _was((alt or {}).get("inhalt"), inh)
    haupt = s.wer in (HAUPTADMIN, "")
    wer_text = (f"{HAUPTADMIN} ({wer})" if haupt and wer else HAUPTADMIN if haupt
                else f"{(admins(db).get(s.wer) or {}).get('name') or s.wer} ({s.wer})" if s.wer else wer)
    if was:
        liste = (liste + [{"zeit": stand, "wer": wer_text, "was": was}])[-VERLAUF_MAX:]
    p = {"format": FORMAT, "stand": stand, "von": wer_text, "version": VERSION, "schema": schema(db), "hash": h,
         "inhalt": inh, "verlauf": liste}
    abl.schreiben(json.dumps(p, ensure_ascii=False, default=str).encode("utf-8"))
    db.einstellung_setzen(STAND, {"stand": stand, "von": wer_text, "hash": h, "paket": h})
    db.einstellung_setzen(VERLAUF, liste)
    return True


def nach_lesen(db, p, sitzung=None):
    """Beim Lesen: Paket übernehmen, wenn es neuer ist oder die Werte hier abweichen (Nicht-Admin hat geändert).
    Ein Admin mit eigenen, noch nicht geschriebenen Änderungen behält sie (sie gehen beim Schreiben hinaus).
    Ergebnis: True = übernommen."""
    if not gueltig(p):
        return False
    s = sitzung if sitzung is not None else SITZUNG
    st = _stand(db)
    seiten = list(p["inhalt"].get("seiten") or VORGABE)
    lokal = _lokal_hash(db, seiten)
    if s is not None and s.jemals and st.get("hash") and lokal != st.get("hash"):
        return False                    # eigene Admin-Änderungen: nicht überschreiben
    if p.get("stand") == st.get("stand") and p.get("hash") == st.get("paket", p.get("hash")) and lokal == st.get("hash"):
        return False                    # schon übernommen, hier unverändert
    paket_anwenden(db, p)
    return True


def ausfiltern(entfernt, p):
    """Abgleich (teilen.lesen): Änderungen der Kollegen an geschützten Werten übergehen, wenn es Admin-Vorgaben gibt –
    dafür gilt das Paket."""
    if not gueltig(p):
        return entfernt
    from .teilen import EINST
    seiten = list(p["inhalt"].get("seiten") or VORGABE)
    namen = einstellungen_geschuetzt(None, seiten)
    tabellen = tabellen_geschuetzt(None, seiten)
    return {(t, u): w for (t, u), w in entfernt.items()
            if not ((t == EINST and u in namen) or t in tabellen)}
