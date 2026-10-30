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

Ohne Qt, damit teilen.py und die Tests es nutzen können.
"""
import datetime
import hashlib
import json
import time
from pathlib import Path

from . import einstellungen_ordnung as ordnung

ADMIN_SEITEN = "admin_seiten"           # Liste der geschützten Bereiche (None = VORGABE); kommt mit dem Paket
STAND = "admin_vorgaben_stand"          # lokal: {stand, von, hash} des zuletzt übernommenen/geschriebenen Pakets
SEITE_ADMIN = "e_admin"                 # die Seite Admin-Schutz selbst: immer geschützt
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
IMMER = (SEITE_ADMIN,)


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
    namen = {"passwort", ADMIN_SEITEN}
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
        self.letzte = uhr()

    def freischalten(self):
        self.freigeschaltet = self.jemals = True
        self.letzte = self.uhr()

    def sperren(self):
        self.freigeschaltet = False

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
    """Darf hier gerade Geschütztes ändern: kein Admin-Passwort gesetzt oder Admin freigeschaltet."""
    s = sitzung if sitzung is not None else SITZUNG
    return not aktiv(db) or bool(s and s.freigeschaltet)


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
    db.einstellung_setzen(STAND, {"stand": p.get("stand"), "von": p.get("von"), "hash": _lokal_hash(db, seiten)})


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
    p = {"format": FORMAT, "stand": stand, "von": wer, "version": VERSION, "schema": schema(db), "hash": h,
         "inhalt": inh}
    abl.schreiben(json.dumps(p, ensure_ascii=False, default=str).encode("utf-8"))
    db.einstellung_setzen(STAND, {"stand": stand, "von": wer, "hash": h})
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
    if p.get("stand") == st.get("stand") and lokal == st.get("hash"):
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
