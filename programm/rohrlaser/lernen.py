"""Das Programm lernt (Plan „Programm soll lernen“, Patrick 08.11.2026, Freigabe „Alle Empfehlungen“ = F1a F2a F3a F4a).

Lernzentrale: alles, was das Programm gelernt hat, an einem Ort (uebersicht), jeder Eintrag lässt sich einzeln
vergessen (vergessen). Quellen:
- Zusatzarbeit-Vorschläge (neu, Tabelle 'gelernt', Art ZUSATZ): ✓ (übernommen) oder ✗ (abgelehnt) je Kunde und
  Zusatzarbeit. Gezählt wird je Angebot (20 Positionen auf einmal ablehnen zählt einmal). Nach SCHWELLE gleichen
  Entscheidungen in verschiedenen Angeboten hintereinander gilt sie als gelernt (F2a); eine andere Entscheidung fängt
  wieder bei 1 an. Gelerntes wendet der STEP-Import selbst an (F3a, angebot_automatik.nach_import): Vorschlag gleich
  übernehmen bzw. gleich ablehnen, mit Einblendung und Rückgängig im Automatik-Protokoll.
- Aus Nacharbeit (nacharbeit.py, Einstellung 'nacharbeit_gelernt'), Teileart und Profilzuordnung aus dem
  STEP-Prüfdialog (step.ART_GELERNT, step.PROFIL_GELERNT), Kennwert-Vorschläge und -Freigaben (kennwerte.py).
Teilen (F1a): die Tabelle 'gelernt' geht wie Stammdaten über den gemeinsamen Ordner (teilen.GETEILT, je Zeile die
neueste Änderung); die Einstellungen EINSTELLUNGEN_GETEILT ebenso, beim Lesen je Eintrag gemischt (mischen), damit
Gelerntes der Kollegen das eigene nicht verdrängt. Vergessen schreibt bei diesen Einstellungen einen leeren Eintrag
(Grabstein), damit es auch bei den Kollegen weg ist.
trefferquote: beauftragte und abgelehnte Angebote eines Kunden als Hinweis neben dem Gewinn (F4: nur Hinweis, der
Gewinn ändert sich nie von allein). Ohne Qt."""
import datetime
import json

from .stammdaten import Feld, Tabelle

SCHWELLE = 3                    # F2a: nach 3 gleichen Entscheidungen (in verschiedenen Angeboten) gilt es als gelernt
ZUSATZ = "zusatz"
JA, NEIN = "ja", "nein"
AUS = "aus"                     # Status: nicht mehr lernen (gesperrt)
ARTEN = {ZUSATZ: "Zusatzarbeit-Vorschlag"}
TABELLE = "gelernt"
GELERNT = Tabelle(
    TABELLE, "Gelerntes",
    (Feld("art", "Art", breite=110),
     Feld("kundennr", "Kunde", breite=80),
     Feld("schluessel", "Schlüssel", breite=160),
     Feld("titel", "Titel", breite=200),
     Feld("wert", "Entscheidung", breite=70),             # ja | nein
     Feld("angebote", "Angebote", breite=120),            # JSON-Liste der Angebote der laufenden Folge
     Feld("ja", "Übernommen", "ganz", breite=60),
     Feld("nein", "Abgelehnt", "ganz", breite=60),
     Feld("status", "Status", breite=60),                 # leer | aus
     Feld("kuerzel", "Wer", breite=50),
     Feld("geaendert", "Geändert", breite=130)),
    ("art", "kundennr", "schluessel"),
    "Was das Programm aus Entscheidungen gelernt hat (Lernzentrale, lernen.py).")
# gelernte Einstellungen, die über den gemeinsamen Ordner gehen (teilen.EINSTELLUNGEN_GETEILT, je Eintrag gemischt)
NACHARBEIT, STEP_ART, STEP_PROFIL = "nacharbeit_gelernt", "step_art_gelernt", "step_profil_gelernt"
EINSTELLUNGEN_GETEILT = (NACHARBEIT, STEP_ART, STEP_PROFIL)
KENNWERT_AB = 0.05              # Startseite: Kennwert-Vorschlag erst ab 5 % Abweichung Ist ÷ Soll
TREFFER_AB = 3                  # Trefferquote erst ab 3 entschiedenen Angeboten des Kunden


def _jetzt():
    return datetime.datetime.now().isoformat(timespec="seconds")


def _kuerzel(db):
    try:
        return str(db.einstellung("benutzer_kuerzel") or "")
    except Exception:
        return ""


def _liste(text):
    try:
        w = json.loads(text) if text else []
    except (TypeError, ValueError):
        w = []
    return w if isinstance(w, list) else []


def _zeile(db, art, kundennr, schluessel):
    r = db.con.execute("SELECT * FROM gelernt WHERE art=? AND COALESCE(kundennr, '')=? AND COALESCE(schluessel, '')=?",
                       (art, str(kundennr or ""), str(schluessel or ""))).fetchone()
    return dict(r) if r is not None else None


def gelernt(z):
    """Entscheidung der Zeile (JA/NEIN), wenn sie gelernt ist, sonst None."""
    if not z or z.get("status") == AUS or z.get("wert") not in (JA, NEIN):
        return None
    return z["wert"] if len(_liste(z.get("angebote"))) >= SCHWELLE else None


def entscheiden(db, art, kundennr, schluessel, ja, angebot_id=None, titel=None):
    """Eine Entscheidung (✓ = ja, ✗ = nein) zählen. Je Angebot zählt sie einmal; eine andere Entscheidung fängt die
    Folge neu an. Ergebnis: JA/NEIN, wenn die Sache gerade (mit dieser Entscheidung) gelernt ist, sonst None.
    Scheitert nie laut: Lernen darf keine Bedienung verhindern."""
    if not kundennr or not schluessel or getattr(db, "nur_lesen", None):
        return None
    wert = JA if ja else NEIN
    try:
        z = _zeile(db, art, kundennr, schluessel)
        if z and z.get("status") == AUS:
            return None
        vorher = gelernt(z)
        angebote = _liste(z.get("angebote")) if z else []
        if z and z.get("wert") == wert:
            if angebot_id in angebote:
                return None             # dieses Angebot zählt schon
            angebote = (angebote + [angebot_id])[-20:]
        else:
            angebote = [angebot_id]
        werte = dict(art=art, kundennr=str(kundennr), schluessel=str(schluessel), titel=titel or str(schluessel),
                     wert=wert, angebote=json.dumps(angebote), ja=((z or {}).get("ja") or 0) + (1 if ja else 0),
                     nein=((z or {}).get("nein") or 0) + (0 if ja else 1), kuerzel=_kuerzel(db), geaendert=_jetzt())
        with db.con:
            if z is None:
                namen = ", ".join(werte)
                db.con.execute(f"INSERT INTO gelernt ({namen}) VALUES ({', '.join('?' * len(werte))})",
                               list(werte.values()))
            else:
                db.con.execute("UPDATE gelernt SET " + ", ".join(f'"{k}"=?' for k in werte) + " WHERE id=?",
                               [*werte.values(), z["id"]])
        neu = gelernt(dict(werte, status=""))
        return neu if neu and neu != vorher else None
    except Exception:
        return None


def wirksam(db, art, kundennr):
    """Gelernte Entscheidungen eines Kunden: {Schlüssel: JA/NEIN}."""
    if not kundennr:
        return {}
    try:
        zeilen = db.con.execute("SELECT * FROM gelernt WHERE art=? AND kundennr=?", (art, str(kundennr))).fetchall()
    except Exception:
        return {}
    out = {}
    for r in zeilen:
        w = gelernt(dict(r))
        if w:
            out[r["schluessel"]] = w
    return out


def text_gelernt(name, wert, kundennr):
    if wert == JA:
        return (f"Gelernt: „{name}“ haben Sie bei Kunde {kundennr} {SCHWELLE}-mal übernommen – beim nächsten "
                "STEP-Import übernimmt das Programm den Vorschlag gleich (Datei → Lernzentrale …).")
    return (f"Gelernt: „{name}“ haben Sie bei Kunde {kundennr} {SCHWELLE}-mal abgelehnt – beim nächsten STEP-Import "
            "lehnt das Programm den Vorschlag gleich ab (Datei → Lernzentrale …).")


# ---------------------------------------------------------------------- gelernte Einstellungen teilen (F1a)
def mischen(name, hier, dort):
    """Gelernte Einstellung name beim Abgleich: dort (neuer, von einem Kollegen) gewinnt je Eintrag, eigene Einträge,
    die er nicht hat, bleiben. hier/dort als JSON-Text. Ergebnis: JSON-Text."""
    try:
        a = json.loads(hier) if hier else {}
        b = json.loads(dort) if dort else {}
    except (TypeError, ValueError):
        return dort
    if not isinstance(a, dict) or not isinstance(b, dict):
        return dort
    out = dict(a)
    for k, v in b.items():
        if name == STEP_PROFIL and isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = {**out[k], **v}
        else:
            out.pop(k, None)
            out[k] = v
    if name == STEP_ART:
        out = dict(list(out.items())[-5000:])
    return json.dumps(out, ensure_ascii=False)


# ---------------------------------------------------------------------- Lernzentrale
def _datum(text):
    return str(text or "")[:16].replace("T", " ")


def _kunden(db):
    try:
        return {str(z.get("kundennr")): z.get("name") or "" for z in db.zeilen("kunden")}
    except Exception:
        return {}


def _kunde(namen, nr):
    if not nr:
        return "alle Kunden"
    return f"{nr} {namen.get(str(nr), '')}".strip()


def uebersicht(db, mit_kennwerten=True):
    """Alles Gelernte: [dict(quelle, schluessel, bereich, kunde, was, stand, wann, vergessen (bool))], Gelerntes
    zuerst, darin nach Bereich."""
    namen = _kunden(db)
    out = []
    try:
        zeilen = [dict(r) for r in db.con.execute("SELECT * FROM gelernt ORDER BY id")]
    except Exception:
        zeilen = []
    for z in zeilen:
        w = gelernt(z)
        n = len(_liste(z.get("angebote")))
        tat = "übernehmen" if z.get("wert") == JA else "ablehnen"
        if z.get("status") == AUS:
            stand, was = "gesperrt (lernt nicht mehr)", f"„{z.get('titel')}“"
        elif w:
            stand, was = "gelernt", f"„{z.get('titel')}“ gleich {tat}"
        else:
            stand, was = f"beobachtet ({n} von {SCHWELLE})", f"„{z.get('titel')}“ {tat}?"
        out.append(dict(quelle=TABELLE, schluessel=z["id"], bereich=ARTEN.get(z.get("art"), z.get("art")),
                        kunde=_kunde(namen, z.get("kundennr")),
                        was=was + f" (bisher {z.get('ja') or 0}× übernommen, {z.get('nein') or 0}× abgelehnt)",
                        stand=stand, wann=_datum(z.get("geaendert")) + (f" ({z['kuerzel']})" if z.get("kuerzel") else ""),
                        gelernt=bool(w), vergessen=True))
    from . import nacharbeit
    for k, e in (_einstellung(db, NACHARBEIT) or {}).items():
        if not isinstance(e, dict) or e.get("status") == "vergessen" or k.count("|") < 2:
            continue
        kundennr, art, wert = k.split("|", 2)
        n = len(e.get("angebote") or ())
        st = e.get("status") or ""
        stand = {"gelernt": "gelernt (im Importprofil bzw. in den Kundenvorgaben)", "abgelehnt": "nicht übernehmen",
                 "gefragt": "gefragt"}.get(st, f"beobachtet ({n} von {nacharbeit.SCHWELLE})")
        w = f"{wert} mm" if art == "stange" else wert
        out.append(dict(quelle=NACHARBEIT, schluessel=k, bereich="Nacharbeit nach dem Import",
                        kunde=_kunde(namen, kundennr), was=f"{nacharbeit.ARTEN.get(art, art)} {w}", stand=stand,
                        wann="", gelernt=st == "gelernt", vergessen=True))
    gruppen = {}
    for k, g in (_einstellung(db, STEP_ART) or {}).items():
        if g:
            gruppen[g] = gruppen.get(g, 0) + 1
    for g, n in sorted(gruppen.items()):
        out.append(dict(quelle=STEP_ART, schluessel=g, bereich="STEP: Teileart", kunde="alle Kunden",
                        was=f"{n} Teil{'e' if n != 1 else ''} beim nächsten Import gleich als „{g}“", stand="gelernt",
                        wann="", gelernt=True, vergessen=True))
    for kundennr, regeln in (_einstellung(db, STEP_PROFIL) or {}).items():
        for gemessen, ziel in (regeln or {}).items() if isinstance(regeln, dict) else ():
            if ziel and ziel != gemessen:
                out.append(dict(quelle=STEP_PROFIL, schluessel=[kundennr, gemessen], bereich="STEP: Profil",
                                kunde=_kunde(namen, kundennr), was=f"gemessen {gemessen} → {ziel}", stand="gelernt",
                                wann="", gelernt=True, vergessen=True))
    if mit_kennwerten:
        for v in kennwerte_reif(db):
            out.append(dict(quelle="kennwerte", schluessel=None, bereich="Kennwert-Vorschlag", kunde="alle Kunden",
                            was=f"{v['titel']} {_schluessel_text(v['schluessel'])}: Ist ÷ Soll "
                                f"{v['faktor']:.2f} aus {v['n']} Aufträgen",
                            stand="wartet auf Freigabe", wann="", gelernt=False, vergessen=False))
        for h in _freigaben(db):
            out.append(dict(quelle="kennwerte_historie", schluessel=h["id"], bereich="Kennwert freigegeben",
                            kunde="alle Kunden", was=f"{h.get('quelle')} {_schluessel_text(h.get('schluessel'))}: "
                                                     f"Faktor {h.get('faktor') or 0:.3f}",
                            stand="gelernt", wann=_datum(h.get("datum")), gelernt=True, vergessen=True))
    out.sort(key=lambda e: (not e["gelernt"], e["bereich"], e["kunde"]))
    return out


def _schluessel_text(s):
    if isinstance(s, str):
        try:
            s = json.loads(s)
        except ValueError:
            return s
    return "(" + ", ".join(str(x) for x in s if x not in (None, "")) + ")" if isinstance(s, (list, tuple)) else ""


def _einstellung(db, name):
    try:
        w = db.einstellung(name)
    except Exception:
        return {}
    return w if isinstance(w, dict) else {}


def _freigaben(db):
    try:
        return [z for z in db.zeilen("kennwerte_historie") if not z.get("zurueck")]
    except Exception:
        return []


def vergessen(db, eintrag):
    """Eintrag der Übersicht vergessen. Ergebnis: Text für die Meldung."""
    from .datenbank import Lesemodus
    if db.nur_lesen:
        raise Lesemodus(f"Lesemodus – {db.nur_lesen}.")
    q, s = eintrag["quelle"], eintrag["schluessel"]
    if q == TABELLE:
        with db.con:
            db.con.execute("DELETE FROM gelernt WHERE id=?", (s,))
    elif q == NACHARBEIT:
        d = _einstellung(db, NACHARBEIT)
        d[s] = dict(angebote=[], status="vergessen")        # Grabstein für die Kollegen; merken fängt neu an
        db.einstellung_setzen(NACHARBEIT, d)
    elif q == STEP_ART:
        d = _einstellung(db, STEP_ART)
        db.einstellung_setzen(STEP_ART, {k: (None if v == s else v) for k, v in d.items()})
    elif q == STEP_PROFIL:
        d = _einstellung(db, STEP_PROFIL)
        kundennr, gemessen = s
        regeln = dict(d.get(kundennr) or {})
        regeln[gemessen] = None
        d[kundennr] = regeln
        db.einstellung_setzen(STEP_PROFIL, d)
    elif q == "kennwerte_historie":
        from . import kennwerte
        kennwerte.zuruecknehmen(db, s)
    else:
        raise ValueError("Dieser Eintrag lässt sich hier nicht vergessen.")
    return f"Vergessen: {eintrag['bereich']} – {eintrag['was']}"


def sperren(db, eintrag):
    """Zusatzarbeit-Eintrag sperren: das Programm lernt dafür nichts mehr (bis Vergessen). Ergebnis: Text."""
    if eintrag["quelle"] != TABELLE:
        raise ValueError("Sperren geht nur für Zusatzarbeit-Vorschläge.")
    with db.con:
        db.con.execute("UPDATE gelernt SET status=?, angebote='[]', geaendert=? WHERE id=?",
                       (AUS, _jetzt(), eintrag["schluessel"]))
    return f"Gesperrt: {eintrag['was']}"


# ---------------------------------------------------------------------- Kennwerte melden sich selbst
_REIF = {}


def kennwerte_reif(db, mindest_n=5):
    """Kennwert-Vorschläge mit genug Daten (status ok) und mindestens KENNWERT_AB Abweichung; gemerkt, bis sich die
    Datendatei ändert."""
    from . import funktionen, kennwerte
    try:
        if not funktionen.an("funktion_nachkalkulation", db):
            return []
        stand = (db.con.total_changes, db.con.execute("PRAGMA data_version").fetchone()[0])
    except Exception:
        return []
    alt = _REIF.get(id(db))
    if alt and alt[0] == stand:
        return alt[1]
    try:
        v = [x for x in kennwerte.vorschlaege(db, mindest_n) if x.get("status") == "ok"
             and isinstance(x.get("faktor"), (int, float)) and abs(x["faktor"] - 1) >= KENNWERT_AB]
    except Exception:
        v = []
    _REIF[id(db)] = (stand, v)
    return v


def kennwerte_text(db):
    v = kennwerte_reif(db)
    if not v:
        return None
    return (f"{len(v)} Kennwert-Vorschlag{'e' if len(v) > 1 else ''} aus der Nachkalkulation mit genug Daten "
            "(Doppelklick: Lernzentrale)")


# ---------------------------------------------------------------------- Trefferquote (Hinweis beim Gewinn)
def trefferquote(db, kundennr, ohne_id=None):
    """Beauftragte und abgelehnte Angebote des Kunden (auch die der Kollegen, ohne ersetzte Fassungen): dict(
    beauftragt, abgelehnt, quote, gewinn_ja, gewinn_nein (Ø Gewinn in %), preis_zu_hoch) oder None (unter
    TREFFER_AB entschiedenen Angeboten)."""
    from .absage import letzte
    if not kundennr:
        return None
    try:
        zeilen = db.con.execute("SELECT id, vorgang, gewinn, vk_gewinn, versand FROM angebote WHERE kundennr=? AND "
                                "COALESCE(ersetzt_durch, '') = '' AND id IS NOT ?", (str(kundennr), ohne_id)).fetchall()
    except Exception:
        return None
    ja, nein, zu_teuer = [], [], 0
    for r in zeilen:
        v = r["vorgang"] or "Entwurf"
        g = r["gewinn"] if isinstance(r["gewinn"], (int, float)) else r["vk_gewinn"]
        if v == "Beauftragt":
            ja.append(g)
        elif v == "Abgelehnt":
            nein.append(g)
            try:
                versand = json.loads(r["versand"]) if r["versand"] else []
            except ValueError:
                versand = []
            a = letzte(dict(versand=versand if isinstance(versand, list) else []))
            zu_teuer += bool(a and a.get("grund") == "Preis zu hoch")
    n = len(ja) + len(nein)
    if n < TREFFER_AB:
        return None

    def mittel(werte):
        w = [x for x in werte if isinstance(x, (int, float))]
        return sum(w) / len(w) if w else None
    return dict(beauftragt=len(ja), abgelehnt=len(nein), quote=len(ja) / n, gewinn_ja=mittel(ja),
                gewinn_nein=mittel(nein), preis_zu_hoch=zu_teuer)


def treffer_text(t):
    """Eine Zeile für die Angebotsseite (nur Hinweis)."""
    if not t:
        return ""
    n = t["beauftragt"] + t["abgelehnt"]
    teile = [f"Dieser Kunde: {t['beauftragt']} von {n} entschiedenen Angeboten beauftragt "
             f"({100 * t['quote']:.0f} %)"]
    g = []
    if t["gewinn_ja"] is not None:
        g.append(f"beauftragt {t['gewinn_ja']:.1f} %".replace(".", ","))
    if t["gewinn_nein"] is not None:
        g.append(f"abgelehnt {t['gewinn_nein']:.1f} %".replace(".", ","))
    if g:
        teile.append("Ø Gewinn " + ", ".join(g))
    if t["preis_zu_hoch"]:
        teile.append(f"{t['preis_zu_hoch']}× Absage „Preis zu hoch“")
    if t["quote"] >= 0.8 and n >= 5:
        teile.append("sehr hohe Trefferquote – der Gewinn könnte höher sein")
    elif t["quote"] <= 0.3 and t["preis_zu_hoch"] >= 2:
        teile.append("oft zu teuer – Gewinn prüfen")
    return " · ".join(teile)
