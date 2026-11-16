"""Automatik-Protokoll (Vorschlag 14, Patrick 03.11.2026 „Alle Empfehlungen“): was das Programm von sich aus getan
hat, mit Zeit, Bearbeiter und – wo möglich – „Rückgängig“.

Jede Automation des Arbeitsablaufs (Nachtrag einsortiert, Kundendaten aus der Signatur ergänzt, Bestellung zugeordnet,
Nachkalkulation vorbelegt, Lieferantenantwort eingelesen …) schreibt hier eine Zeile. Gespeichert wird in der Tabelle
'automatik' der Datendatei (nur dieser Arbeitsplatz, kein Abgleich mit den Kollegen). Ein Eintrag mit 'rueck' lässt
sich zurücknehmen; danach steht die Zeit im Feld 'zurueck' und der Eintrag bleibt zur Nachverfolgung stehen.

Rückgängig-Arten (rueck = dict(art=…)):
  verschieben   Datei von 'nach' zurück nach 'von' (nur wenn 'von' frei ist)
  kunde         Felder 'alt' des Kunden 'kundennr' zurücksetzen
  zusatz        Zusatzdaten 'schluessel' des Angebots 'angebot_id' auf 'alt' (None = entfernen)
  nachkalk      Nachkalkulation des Angebots 'angebot_id' auf 'alt' (None = keine)
  vorgang       Vorgang des Angebots auf 'alt' und Auftragsnr./Liefertermin auf 'auftragsnr'/'liefertermin'
  positionsfelder  Felder 'alt' = [(Positions-ID, Feld, Wert)] zurücksetzen (Gelerntes angewendet, lernen.py)
Ohne Qt."""
import datetime
import json
import shutil
from pathlib import Path

TABELLE = "automatik"
TABELLEN = (TABELLE,)
TABELLEN_SQL = (
    "CREATE TABLE IF NOT EXISTS automatik (id INTEGER PRIMARY KEY, zeit TEXT, kuerzel TEXT, angebot_id INTEGER, "
    "art TEXT, text TEXT, rueck TEXT, zurueck TEXT)",
    "CREATE INDEX IF NOT EXISTS automatik_angebot ON automatik (angebot_id)",
)
TAGE = 90                   # so lange zeigt das Protokoll Einträge (ältere bleiben gespeichert, bis MAX überschritten)
MAX = 5000                  # danach fallen die ältesten Einträge weg

# Art -> Anzeige
ARTEN = {"vormessen": "Anfrage vorbereitet", "nachtrag": "Nachtrag einsortiert", "kontakt": "Kundendaten ergänzt",
         "bestellung": "Bestellung zugeordnet", "auftrag": "Auftrag gestartet", "materialbestellung": "Material bestellt",
         "lieferantenantwort": "Lieferantenantwort eingelesen", "preiswaechter": "Preiswächter",
         "nachkalk": "Nachkalkulation vorbelegt", "wiederholanfrage": "Wiederholanfrage übernommen",
         "angebot_auto": "Angebot automatisch", "zuweisung": "Anfrage zugewiesen", "nacharbeit": "Importprofil gelernt",
         "gelernt": "Gelerntes angewendet"}


class AutomatikFehler(ValueError):
    """Rückgängig nicht möglich (Text für den Benutzer)."""


def einrichten(con):
    for sql in TABELLEN_SQL:
        con.execute(sql)


def _jetzt():
    return datetime.datetime.now().isoformat(timespec="seconds")


def _kuerzel(db):
    try:
        return str(db.einstellung("benutzer_kuerzel") or "")
    except Exception:
        return ""


def merken(db, art, text, angebot_id=None, rueck=None):
    """Eintrag schreiben. Ergebnis: ID oder None (Lesemodus, Tabelle fehlt). Scheitert nie laut: das Protokoll darf
    keine Automation verhindern."""
    if getattr(db, "nur_lesen", None):
        return None
    try:
        with db.con:
            einrichten(db.con)
            c = db.con.execute("INSERT INTO automatik (zeit, kuerzel, angebot_id, art, text, rueck) VALUES "
                               "(?, ?, ?, ?, ?, ?)", (_jetzt(), _kuerzel(db), angebot_id, art, str(text),
                                                      json.dumps(rueck, ensure_ascii=False) if rueck else None))
            n = db.con.execute("SELECT COUNT(*) FROM automatik").fetchone()[0]
            if n > MAX:
                db.con.execute("DELETE FROM automatik WHERE id IN (SELECT id FROM automatik ORDER BY id LIMIT ?)",
                               (n - MAX,))
            return c.lastrowid
    except Exception:
        return None


def liste(db, angebot_id=None, tage=TAGE, heute=None):
    """Einträge der letzten tage Tage, neueste zuerst: [dict(id, zeit, kuerzel, angebot_id, art, titel, text, rueck,
    zurueck, rueckgaengig)] (rueckgaengig = lässt sich noch zurücknehmen)."""
    heute = heute or datetime.datetime.now()
    ab = (heute - datetime.timedelta(days=tage)).isoformat(timespec="seconds")
    try:
        einrichten(db.con)
        sql = "SELECT id, zeit, kuerzel, angebot_id, art, text, rueck, zurueck FROM automatik WHERE zeit >= ?"
        werte = [ab]
        if angebot_id is not None:
            sql += " AND angebot_id = ?"
            werte.append(angebot_id)
        zeilen = db.con.execute(sql + " ORDER BY id DESC", werte).fetchall()
    except Exception:
        return []
    out = []
    for i, zeit, kuerzel, aid, art, text, rueck, zurueck in zeilen:
        try:
            r = json.loads(rueck) if rueck else None
        except ValueError:
            r = None
        out.append(dict(id=i, zeit=zeit, kuerzel=kuerzel or "", angebot_id=aid, art=art, titel=ARTEN.get(art, art),
                        text=text or "", rueck=r, zurueck=zurueck, rueckgaengig=bool(r) and not zurueck))
    return out


def eintrag(db, eintrag_id):
    return next((e for e in liste(db, tage=36500) if e["id"] == eintrag_id), None)


def rueckgaengig(db, eintrag_id):
    """Eintrag zurücknehmen. Ergebnis: Text für die Meldung; AutomatikFehler, wenn es nicht (mehr) geht."""
    from .datenbank import Lesemodus
    if db.nur_lesen:
        raise Lesemodus(f"Lesemodus – {db.nur_lesen}.")
    e = eintrag(db, eintrag_id)
    if e is None:
        raise AutomatikFehler("Eintrag nicht gefunden.")
    if e["zurueck"]:
        raise AutomatikFehler("Dieser Schritt wurde schon zurückgenommen.")
    r = e["rueck"]
    if not r:
        raise AutomatikFehler("Dieser Schritt lässt sich nicht zurücknehmen (nur Hinweis).")
    art = r.get("art")
    if art == "verschieben":
        text = _verschieben_zurueck(r)
    elif art == "kunde":
        text = _kunde_zurueck(db, r)
    elif art == "zusatz":
        db.zusatz_setzen(r["angebot_id"], r["schluessel"], r.get("alt"))
        text = "Zusatzdaten zurückgesetzt"
    elif art == "nachkalk":
        db.nachkalkulation_speichern(r["angebot_id"], r.get("alt"))
        alt_zusatz = r.get("zusatz_alt")
        db.zusatz_setzen(r["angebot_id"], "nachkalk_vorbelegt", alt_zusatz)
        text = "Nachkalkulation zurückgesetzt"
    elif art == "kopf":             # Kopffelder des Angebots (Maschine, Lieferzeit; Paket D)
        for feld, wert in (r.get("alt") or {}).items():
            db.angebot_aendern(r["angebot_id"], feld, wert)
        text = ", ".join(r.get("alt") or {}) + " wie vorher"
    elif art == "positionen":       # ein Feld an mehreren Positionen (Material, Oberfläche; Paket D)
        vorhanden = {p["id"] for p in db.positionen(r["angebot_id"])}
        for pid, wert in r.get("alt") or ():
            if pid in vorhanden:
                db.position_aendern(pid, r["feld"], wert)
        text = f"{r['feld']} wie vorher"
    elif art == "positionsfelder":  # mehrere Felder an mehreren Positionen (Gelerntes, 08.11.2026)
        vorhanden = {p["id"] for p in db.positionen(r["angebot_id"])}
        for pid, feld, wert in r.get("alt") or ():
            if pid in vorhanden:
                db.position_aendern(pid, feld, wert)
        text = "Positionen wie vorher"
        g = r.get("gelernt")            # I10 Selbstkorrektur: zweimal zurückgenommen = verlernt
        if isinstance(g, dict):
            from . import lernen
            weg = lernen.zurueckgenommen(db, g.get("art"), g.get("kundennr"), g.get("schluessel") or ())
            if weg:
                text += "; verlernt: " + ", ".join(f"„{t}“" for t in weg) + " (wird wieder nur beobachtet)"
    elif art == "vorgang":
        db.vorgang_setzen(r["angebot_id"], r.get("alt") or "Entwurf")
        db.auftrag_setzen(r["angebot_id"], r.get("auftragsnr"), r.get("liefertermin"))
        text = f"Vorgang wieder {r.get('alt') or 'Entwurf'}"
    else:
        raise AutomatikFehler(f"Unbekannte Art {art!r}.")
    with db.con:
        db.con.execute("UPDATE automatik SET zurueck=? WHERE id=?", (_jetzt(), eintrag_id))
    return f"Rückgängig: {e['titel']} – {text}."


def _verschieben_zurueck(r):
    von, nach = Path(r["von"]), Path(r["nach"])
    if not nach.exists():
        raise AutomatikFehler(f"{nach.name} liegt nicht mehr in {nach.parent}.")
    if von.exists():
        raise AutomatikFehler(f"An der alten Stelle liegt schon eine Datei {von.name}.")
    try:
        von.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(nach), str(von))
    except OSError as e:
        raise AutomatikFehler(f"{nach.name} lässt sich nicht zurücklegen: {e}") from e
    return f"{von.name} wieder in {von.parent}"


def _kunde_zurueck(db, r):
    z = next((k for k in db.zeilen("kunden") if str(k.get("kundennr")) == str(r["kundennr"])), None)
    if z is None:
        raise AutomatikFehler(f"Kunde {r['kundennr']} gibt es nicht mehr.")
    for feld, wert in (r.get("alt") or {}).items():
        db.aendern("kunden", z["id"], feld, wert)
    return f"Kunde {r['kundennr']}: {', '.join(r.get('alt') or {})} wie vorher"


def verschieben(db, quelle, ziel_ordner, art, text, angebot_id=None):
    """Datei in ziel_ordner verschieben (Name frei machen: 'Name (2)') und mit Rückgängig protokollieren. Ergebnis:
    neuer Pfad. OSError, wenn es nicht geht."""
    quelle, ziel_ordner = Path(quelle), Path(ziel_ordner)
    ziel_ordner.mkdir(parents=True, exist_ok=True)
    ziel = ziel_ordner / quelle.name
    i = 1
    while ziel.exists():
        i += 1
        ziel = ziel_ordner / f"{quelle.stem} ({i}){quelle.suffix}"
    shutil.move(str(quelle), str(ziel))
    merken(db, art, text, angebot_id, dict(art="verschieben", von=str(quelle), nach=str(ziel)))
    return ziel


# ---------------------------------------------------------------------- Startseite: was die Automatik meldet
def aufgaben(db, heute=None):
    """Hinweise der Automationen für die Startseite: [dict(art, text, angebot_id)]: Wareneingang fällig (Vorschlag 8),
    Nachkalkulation mit großer Abweichung (10), Preiswächter (9)."""
    heute = heute or datetime.date.today()
    out = []
    try:
        from . import lieferantenangebote
        out += [dict(art="wareneingang", angebot_id=a["angebot_id"],
                     text=f"Wareneingang prüfen: {a['nummer']} – {a['lieferant']} ({a['profil_id']}), erwartet "
                          f"{datetime.date.fromisoformat(a['erwartet']):%d.%m.%Y}")
                for a in lieferantenangebote.wareneingang_faellig(db, heute)]
    except Exception:
        pass
    try:
        from . import nachkalk_vorbelegen
        out += [dict(art="nachkalk", angebot_id=n["angebot_id"],
                     text=f"Nachkalkulation prüfen: {n['nummer']} – {n['text']}")
                for n in nachkalk_vorbelegen.zu_pruefen(db)]
    except Exception:
        pass
    try:
        from . import lernen
        t = lernen.kennwerte_text(db)
        if t:
            out.append(dict(art="kennwerte", angebot_id=None, text=t))
        t = lernen.muster_text(db)
        if t:
            out.append(dict(art="muster", angebot_id=None, text=t))
        from . import einsichten
        t = einsichten.text(db)                         # I7, I11
        if t:
            out.append(dict(art="muster", angebot_id=None, text=t))
        out += [dict(art="verlust", angebot_id=None, text="Auffällig oft verloren – " + t)      # I12
                for t in einsichten.verlustmuster(db)]
    except Exception:
        pass
    try:                # V3 (Vorschläge 11.11.2026): still gewordene Stammkunden
        from . import vertrieb
        if (db.einstellung("stille_kunden") or "ja") != "nein":
            aus = vertrieb.ausgeblendet(db.einstellung(vertrieb.STILL_AUS), heute)
            out += [dict(art="still", angebot_id=None, kundennr=s["kundennr"],
                         text="Lange nichts bestellt – " + vertrieb.still_text(s) + " (Doppelklick: Nachfass-Mail)")
                    for s in vertrieb.stille_kunden(db.angebote(), heute, aus)[:5]]
    except Exception:
        pass
    try:                # Plan Schweißbaugruppe Teil 2, A5: neue Regeln der Schweiß-Vorkalkulation nach einem Update
        from . import schweiss_neu
        t = schweiss_neu.text(db)
        if t:
            out.append(dict(art="schweiss_richtwerte", angebot_id=None, text=t))
    except Exception:
        pass
    try:
        from . import preiswaechter
        t = preiswaechter.text(db)
        if t:
            out.append(dict(art="preiswaechter", angebot_id=None, text=t))
    except Exception:
        pass
    return out
