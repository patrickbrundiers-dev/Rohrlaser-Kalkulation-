"""Anfragen sammeln und zusammenführen (Patrick 20.11.2026, Entwicklungsauftrag „Outlook-E-Mail-Verwaltung und
intelligente Anfragezusammenführung“, Pakete Z2/Z3).

Grundprinzip: eine Anfrage = ein Vorgang mit beliebig vielen Mails, Anhängen und Dokumenten. Gebaut auf der Akte
(anfragen_akten): Dateien liegen einmal im Ordner Dateien der Akte (gleicher Inhalt nur einmal, Dokumenten-ID aus der
SHA-256), jede Änderung ist ein Ereignis im Verlauf (= Änderungsprotokoll), gelöscht oder überschrieben wird nichts.

  hinzufuegen        Mails (.msg/.eml, Anhänge werden ausgepackt) und Dokumente zu einer Anfrage, viele auf einmal
  verschieben        Mail/Datei einer anderen Anfrage zuweisen (bleibt in der alten ausgeblendet liegen)
  zusammenfuehren    weitere Anfragen in eine Hauptanfrage (vorher vorschau() zeigen und bestätigen lassen)
  rueckgaengig       Zusammenführung trennen: Hauptanfrage blendet die übernommenen Inhalte aus, die weiteren
                     Anfragen bekommen ihren Stand zurück
  wiederherstellen   beim Start: abgebrochene Zusammenführungen (Absturz, Netz) zu Ende führen
  vorschlaege        „Gehört vielleicht zu …“ – nie automatisch zusammenführen

Zusammenführen ist absturzsicher: zuerst steht ein Journal (_zusammenfuehren/<id>.json im Akten-Ordner), dann folgen
Schritte, die sich gefahrlos wiederholen lassen (Dateien kopieren mit Prüfsumme, Ereignisse nur einmal je Journal-ID).
Eine Sperrdatei je beteiligter Akte verhindert, dass zwei Plätze gleichzeitig dieselben Anfragen zusammenführen.
Ohne Qt."""
import datetime
import json
import os
import re
import uuid
from pathlib import Path

from . import anfragen_akten as ak

JOURNAL = "_zusammenfuehren"
PROTOKOLL = "import_protokoll.jsonl"    # im Ordner _outlook der Akten
SPERRE = "zusammenfuehren.sperre"
SPERRE_ALT_MIN = 15                     # ältere Sperre (Absturz) gilt als frei

# Kategorien der Dokumente (Patrick 20.11.2026, Punkt 4); weitere legt der Benutzer an (KATEGORIEN_DATEI)
KUNDENANFRAGE, VERLAUF, ZEICHNUNG, STUECKLISTE = "Kundenanfrage", "E-Mail-Verlauf", "Technische Zeichnungen", \
    "Stücklisten"
MATERIAL, ANGEBOT, NACHTRAG, SONSTIGE = "Materialanfragen", "Angebote", "Nachträge", "Sonstige Dokumente"
KATEGORIEN = (KUNDENANFRAGE, VERLAUF, ZEICHNUNG, STUECKLISTE, MATERIAL, ANGEBOT, NACHTRAG, SONSTIGE)
KATEGORIEN_DATEI = "dokument_kategorien.json"
QUELLE_TEXT = {"eingang": "Eingang", "outlook": "Outlook", "hand": "von Hand hinzugefügt", "drag": "Drag & Drop",
               "zusammen": "zusammengeführt", "verschoben": "verschoben", "antwort": "Antwort des Kunden"}

STUECKLISTE_WORT = re.compile(r"st(ü|ue)ckliste|\bbom\b|teileliste|materialliste|bauteilliste", re.I)
MATERIAL_WORT = re.compile(r"materialanfrage|werkstoffanfrage|preisanfrage[_\s-]*material", re.I)
ANGEBOT_WORT = re.compile(r"angebot|offer|quotation|\bag[-_ ]?\d", re.I)
ZEICHNUNG_WORT = re.compile(r"zeichnung|drawing|\bzng\b|\bzchn", re.I)


def _jetzt(jetzt=None):
    return (jetzt or datetime.datetime.now()).replace(microsecond=0)


# ------------------------------------------------------------------ Kategorien
_KAT_CACHE = {}


def kategorien(wurzel):
    """Alle Kategorien: die festen und die selbst angelegten (gelesen nur, wenn sich die Datei geändert hat)."""
    p = Path(wurzel) / "_outlook" / KATEGORIEN_DATEI
    try:
        st = p.stat()
        merkmal = (st.st_size, st.st_mtime_ns)
    except OSError:
        return list(KATEGORIEN)
    if _KAT_CACHE.get(str(p), (None,))[0] != merkmal:
        try:
            eigene = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            eigene = []
        _KAT_CACHE[str(p)] = (merkmal, [str(k) for k in eigene if str(k).strip() and str(k) not in KATEGORIEN])
    return list(KATEGORIEN) + list(_KAT_CACHE[str(p)][1])


def kategorie_anlegen(wurzel, name):
    name = " ".join(str(name or "").split())[:40]
    if not name:
        raise ak.AblageFehler("Bitte einen Namen für die Kategorie eingeben.")
    alle = kategorien(wurzel)
    if name in alle:
        return alle
    p = Path(wurzel) / "_outlook" / KATEGORIEN_DATEI
    p.parent.mkdir(parents=True, exist_ok=True)
    eigene = [k for k in alle if k not in KATEGORIEN] + [name]
    tmp = p.with_suffix(f".{uuid.uuid4().hex[:6]}.tmp")
    tmp.write_text(json.dumps(eigene, ensure_ascii=False), encoding="utf-8")
    tmp.replace(p)
    return alle + [name]


def kategorie_vorschlag(e, erste_mail=False):
    """Kategorie aus Art, Name und Herkunft eines Dokuments (Eintrag wie Akte.dateien())."""
    name = str(e.get("name") or "")
    h = e.get("herkunft") or {}
    if e.get("art") == "mail":
        return KUNDENANFRAGE if erste_mail else VERLAUF
    if MATERIAL_WORT.search(name):
        return MATERIAL
    if STUECKLISTE_WORT.search(name):
        return STUECKLISTE
    if ANGEBOT_WORT.search(name) and e.get("art") == "pdf":
        return ANGEBOT
    if e.get("art") in ("step", "dxf") or ZEICHNUNG_WORT.search(name) or e.get("art") == "pdf":
        return ZEICHNUNG
    if e.get("art") == "excel":
        return STUECKLISTE
    if h.get("quelle") in ("antwort", "hand", "drag") or h.get("nachtrag"):
        return NACHTRAG
    return SONSTIGE


def dokumente(akte, mit_weg=False):
    """Dokumente der Akte mit Kategorie (von Hand gesetzt, sonst vorgeschlagen), Dokumenten-ID und Herkunft."""
    liste = akte.dateien(mit_weg=mit_weg)
    mails = [d for d in liste if d["art"] == "mail" and not d.get("aus_mail") and not d.get("weg")]
    erste = min(mails, key=lambda d: (d.get("herkunft") or {}).get("datum") or "~", default=None)
    for d in liste:
        d["kategorie"] = d.get("kategorie") or kategorie_vorschlag(d, d is erste)
        d.setdefault("herkunft", {})
    return liste


def nach_kategorie(akte, wurzel=None):
    """{Kategorie: [Dokumente]} in der Reihenfolge der Kategorien (leere fehlen)."""
    out = {}
    for d in dokumente(akte):
        out.setdefault(d["kategorie"], []).append(d)
    reihe = kategorien(wurzel) if wurzel else list(KATEGORIEN)
    return {k: out[k] for k in reihe + [k for k in out if k not in reihe] if k in out}


def kategorie_setzen(abl, akte, datei, kategorie, jetzt=None):
    """Kategorie eines Dokuments ändern (datei = Schlüssel wie d.get('datei', d['name']))."""
    if kategorie not in kategorien(abl.wurzel):
        raise ak.AblageFehler(f"Unbekannte Kategorie: {kategorie}")
    akte = abl.neu_lesen(akte)
    d = next((x for x in dokumente(akte) if x.get("datei", x["name"]) == datei), None)
    if d is None:
        raise ak.AblageFehler(f"{datei}: nicht in der Anfrage {akte.nr}")
    if d["kategorie"] != kategorie:
        abl.ereignis(akte, ak.KATEGORIE, alt=d["kategorie"], neu=kategorie, datei=datei, jetzt=jetzt)
    return abl.neu_lesen(akte)


# ------------------------------------------------------------------ Protokoll der Importe
def protokollieren(abl, **eintrag):
    p = Path(abl.wurzel) / "_outlook" / PROTOKOLL
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        e = dict(zeit=_jetzt().isoformat(), kuerzel=abl.kuerzel, platz=abl.platz)
        e.update(eintrag)
        with open(p, "a", encoding="utf-8") as f:
            f.write(json.dumps(e, ensure_ascii=False, default=str) + "\n")
    except OSError:
        pass


def protokoll(abl, n=200):
    try:
        zeilen = (Path(abl.wurzel) / "_outlook" / PROTOKOLL).read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out = []
    for z in zeilen[-n:]:
        try:
            out.append(json.loads(z))
        except ValueError:
            continue
    return out


# ------------------------------------------------------------------ Hinzufügen
def hinzufuegen(abl, akte, pfade, quelle="hand", jetzt=None):
    """Mails und Dokumente zur Anfrage hinzufügen (viele auf einmal). Gleiche Inhalte nur einmal, Mails mit Von, An,
    Datum und Betreff als Herkunft, ihre Anhänge ausgepackt. Ein Netzabbruch bricht kontrolliert ab: was vorher kopiert
    war, steht vollständig in der Akte, der Rest wird gemeldet. Ergebnis: dict(neu=[Name], doppelt=[Name],
    fehler=[Text], akte)."""
    akte = abl.neu_lesen(akte)
    pfade = [Path(p) for p in pfade]
    bekannt = {d.get("sha256"): d["name"] for d in akte.dateien() if d.get("sha256")}
    neu, doppelt, fehler = [], [], []
    herkunft = dict(quelle=quelle, kuerzel=abl.kuerzel, zeit=_jetzt(jetzt).isoformat(), nachtrag=True)
    for p in pfade:
        if not p.is_file():
            fehler.append(f"{p.name}: nicht gefunden")
            continue
        try:
            h = ak.pruefsumme(p)
        except OSError as e:
            fehler.append(f"{p.name}: nicht lesbar ({e})")
            continue
        if h in bekannt:
            doppelt.append(f"{p.name} (schon da als {bekannt[h]})")
            continue
        try:
            e = abl.kopieren(akte, [p], herkunft=herkunft)
        except OSError as x:          # z. B. Netzabbruch: was schon da ist, bleibt; Rest kontrolliert abbrechen
            fehler.append(f"{p.name}: nicht kopiert ({x})")
            break
        if e:
            iid = next((x["herkunft"].get("internet_id") for x in e if x.get("herkunft", {}).get("internet_id")), "")
            abl.ereignis(akte, ak.DATEI_DAZU, dateien=e, jetzt=jetzt, quelle=quelle,
                         **({"internet_id": iid} if iid else {}))
            akte = abl.neu_lesen(akte)
            bekannt.update({x.get("sha256"): x["name"] for x in e})
            neu += [x["name"] for x in e]
    protokollieren(abl, art="hinzufuegen", akte=akte.nr, quelle=quelle, neu=neu, doppelt=doppelt, fehler=fehler)
    return dict(neu=neu, doppelt=doppelt, fehler=fehler, akte=abl.neu_lesen(akte))


# ------------------------------------------------------------------ Verschieben
def verschieben(abl, von, nach, dateien, jetzt=None):
    """Mails/Dateien (Schlüssel) von einer Anfrage in eine andere. In der alten bleiben sie ausgeblendet liegen
    („verschoben nach …“); Anhänge einer verschobenen Mail gehen mit. Ist es die Outlook-Mail der alten Anfrage, folgt
    ihr die Outlook-Zuordnung. Ergebnis: (alte Akte, neue Akte)."""
    von, nach = abl.neu_lesen(von), abl.neu_lesen(nach)
    if von.nr == nach.nr:
        raise ak.AblageFehler("Quelle und Ziel sind dieselbe Anfrage.")
    alle = von.dateien()
    wahl = [d for d in alle if d.get("datei", d["name"]) in set(dateien)]
    namen = {d["name"] for d in wahl if d["art"] == "mail"}
    wahl += [d for d in alle if d.get("aus_mail") in namen and d not in wahl]
    if not wahl:
        raise ak.AblageFehler("Keine Datei gewählt.")
    herkunft = dict(quelle="verschoben", akte=von.nr, kuerzel=abl.kuerzel, zeit=_jetzt(jetzt).isoformat())
    pfade = [d["pfad"] for d in wahl if not d.get("aus_mail") and d["pfad"].is_file()]
    neu = abl.kopieren(nach, pfade, herkunft=herkunft)
    mids = []
    if von.kopf.get("nachrichten_id") and any(d["name"] == (von.kopf.get("dateien") or [{}])[0].get("name")
                                              and d["art"] == "mail" for d in wahl):
        mids.append(von.kopf["nachrichten_id"])
    iids = [d.get("herkunft", {}).get("internet_id") for d in wahl if d.get("herkunft", {}).get("internet_id")]
    abl.ereignis(nach, ak.DATEI_DAZU, dateien=neu, jetzt=jetzt, quelle="verschoben", von_akte=von.nr,
                 **({"nachrichten_id": mids[0]} if mids else {}),
                 **({"internet_id": iids[0]} if iids else {}))
    abl.ereignis(von, ak.DATEI_WEG, neu=nach.nr, dateien=[d.get("datei", d["name"]) for d in wahl], mids=mids,
                 jetzt=jetzt)
    protokollieren(abl, art="verschieben", von=von.nr, nach=nach.nr, dateien=[d["name"] for d in wahl])
    return abl.neu_lesen(von), abl.neu_lesen(nach)


# ------------------------------------------------------------------ Zusammenführen
def vorschau(haupt, weitere):
    """Übersicht vor dem Zusammenführen: dict(mails=[(Anfrage, Von, Datum, Betreff)], dateien=[(Anfrage, Name,
    Kategorie)], doppelt=[(Anfrage, Name, schon da als)], kunden={Kundennummer: [Anfrage]}, angebote=[…],
    warnungen=[Text]). Die doppelten Dateien werden beim Zusammenführen nicht noch einmal gespeichert."""
    bekannt = {d.get("sha256"): d["name"] for d in haupt.dateien() if d.get("sha256")}
    out = dict(mails=[], dateien=[], doppelt=[], kunden={}, angebote=list(haupt.stand["angebote"]), warnungen=[])
    if haupt.kunde:
        out["kunden"].setdefault(haupt.kunde, []).append(haupt.nr)
    for a in weitere:
        if a.nr == haupt.nr:
            continue
        if a.stand.get("zusammengefuehrt_in"):
            out["warnungen"].append(f"{a.nr} ist schon in {a.stand['zusammengefuehrt_in']} zusammengeführt.")
        if a.kunde:
            out["kunden"].setdefault(a.kunde, []).append(a.nr)
        out["angebote"] += [n for n in a.stand["angebote"] if n not in out["angebote"]]
        for d in dokumente(a):
            if d.get("sha256") in bekannt:
                out["doppelt"].append((a.nr, d["name"], bekannt[d["sha256"]]))
                continue
            bekannt[d.get("sha256")] = d["name"]
            if d["art"] == "mail" and not d.get("aus_mail"):
                h = d.get("herkunft") or {}
                out["mails"].append((a.nr, h.get("von") or a.absender_adresse, h.get("datum") or "",
                                     h.get("betreff") or a.betreff))
            out["dateien"].append((a.nr, d["name"], d["kategorie"]))
    if len(out["kunden"]) > 1:
        out["warnungen"].append("Verschiedene Kunden: " + ", ".join(f"{k} ({', '.join(v)})"
                                                                     for k, v in out["kunden"].items())
                                + f" – die Hauptanfrage behält {haupt.kunde or 'keinen Kunden'}.")
    return out


def _sperre_nehmen(akte, kuerzel, jetzt):
    p = akte.pfad / SPERRE
    if ak._exklusiv(p, f"{kuerzel}|{jetzt.isoformat()}"):
        return True
    try:
        wer, _, zeit = p.read_text(encoding="utf-8").partition("|")
        alt = jetzt - datetime.datetime.fromisoformat(zeit) > datetime.timedelta(minutes=SPERRE_ALT_MIN)
    except (OSError, ValueError):
        wer, alt = "?", True
    if alt or wer == kuerzel:
        p.unlink(missing_ok=True)
        return ak._exklusiv(p, f"{kuerzel}|{jetzt.isoformat()}")
    return False


def _sperre_geben(akten):
    for a in akten:
        (a.pfad / SPERRE).unlink(missing_ok=True)


def _journal(abl, jid):
    return Path(abl.wurzel) / JOURNAL / f"{jid}.json"


def _journal_schreiben(abl, j):
    p = _journal(abl, j["id"])
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(j, ensure_ascii=False, default=str), encoding="utf-8")
    tmp.replace(p)


def darf(akte, ich, admin=False):
    """Zusammenführen/Rückgängig: Bearbeiter der Anfrage, Admin, oder die Anfrage ist neu (noch niemandes)."""
    return admin or akte.status == ak.NEU or (bool(ich) and akte.bearbeiter == ich)


def zusammenfuehren(abl, haupt, weitere, jetzt=None, ich=None, admin=False, _abbruch_nach=None):
    """Weitere Anfragen in die Hauptanfrage zusammenführen (nach Bestätigung der vorschau). Alle Mails, Anhänge und
    Dokumente kommen in die Hauptanfrage (gleiche Inhalte einmal), mit Herkunft (alte Anfrage, Absender, Zeit); die
    alten Nummern stehen im Verlauf; die weiteren Anfragen werden „Zusammengeführt in …“ (bleiben lesbar).
    Ergebnis: Journal-ID (für rueckgaengig). _abbruch_nach: Test für einen Absturz nach Schritt n."""
    jetzt = _jetzt(jetzt)
    ich = abl.kuerzel if ich is None else ich
    haupt = abl.neu_lesen(haupt)
    weitere = [abl.neu_lesen(a) for a in weitere if a.nr != haupt.nr]
    if not weitere:
        raise ak.AblageFehler("Bitte mindestens eine weitere Anfrage wählen.")
    for a in [haupt] + weitere:
        if a.stand.get("zusammengefuehrt_in"):
            raise ak.AblageFehler(f"{a.nr} ist schon in {a.stand['zusammengefuehrt_in']} zusammengeführt.")
        if not darf(a, ich, admin):
            raise ak.AblageFehler(f"{a.nr} bearbeitet {a.bearbeiter}: nur er oder der Admin darf zusammenführen.")
    gesperrt = []
    for a in [haupt] + weitere:
        if not _sperre_nehmen(a, abl.kuerzel, jetzt):
            _sperre_geben(gesperrt)
            raise ak.AblageFehler(f"{a.nr} wird gerade an einem anderen Platz zusammengeführt.")
        gesperrt.append(a)
    j = dict(id=uuid.uuid4().hex[:12], art="zusammen", haupt=haupt.nr, weitere=[a.nr for a in weitere],
             kuerzel=abl.kuerzel, zeit=jetzt.isoformat(), fertig=[], stand="begonnen")
    _journal_schreiben(abl, j)
    try:
        _ausfuehren(abl, j, jetzt, _abbruch_nach)
    finally:
        _sperre_geben(gesperrt)
    return j["id"]


def _hat(akte, aktion, jid):
    return any(e.get("aktion") == aktion and e.get("id") == jid and not e.get("ungueltig") for e in akte.verlauf)


def _ausfuehren(abl, j, jetzt, _abbruch_nach=None):
    """Schritte des Journals (wiederholbar): 1 Dateien kopieren + Ereignis in der Hauptanfrage, 2 je weitere Anfrage
    „aufgegangen“, 3 fertig."""
    haupt = abl.lesen(j["haupt"])
    if haupt is None:
        raise ak.AblageFehler(f"Hauptanfrage {j['haupt']} nicht gefunden.")
    if not _hat(haupt, ak.ZUSAMMEN, j["id"]):
        neu, mids, iids = [], [], []
        vorhanden = {d.get("sha256") for d in haupt.dateien() if d.get("sha256")}
        for nr in j["weitere"]:
            a = abl.lesen(nr)
            if a is None:
                continue
            for d in a.dateien():
                if d.get("aus_mail") or d.get("gesperrt") or not d["pfad"].is_file():
                    continue
                h = dict(d.get("herkunft") or {})
                h.update(quelle="zusammen", akte=nr, zusammen=j["id"], kuerzel=abl.kuerzel, zeit=jetzt.isoformat())
                e = abl.kopieren(haupt, [d["pfad"]], herkunft=h, vorhanden=vorhanden)
                for x in e:             # Herkunft der Mail (Von, Datum) bleibt die aus der alten Anfrage
                    x["herkunft"] = {**(d.get("herkunft") or {}), **x.get("herkunft", {}), **h}
                neu += e
            mids += [m for m in [a.kopf.get("nachrichten_id"), *a.stand.get("mids", [])] if m and m not in mids]
            iids += [x for x in sorted(a.internet_ids()) if x not in iids]
        if _abbruch_nach == 1:
            raise RuntimeError("Test: Absturz nach dem Kopieren")
        abl.ereignis(haupt, ak.ZUSAMMEN, id=j["id"], von=j["weitere"], dateien=neu, mids=mids, internet_ids=iids,
                     jetzt=jetzt)
        j["fertig"].append("haupt")
        _journal_schreiben(abl, j)
    for nr in j["weitere"]:
        a = abl.lesen(nr)
        if a is None or _hat(a, ak.AUFGEGANGEN, j["id"]):
            continue
        if _abbruch_nach == 2:
            raise RuntimeError("Test: Absturz vor dem Abschluss der weiteren Anfragen")
        abl.ereignis(a, ak.AUFGEGANGEN, neu=j["haupt"], id=j["id"], jetzt=jetzt)
        j["fertig"].append(nr)
        _journal_schreiben(abl, j)
    j["stand"] = "fertig"
    _journal_schreiben(abl, j)
    protokollieren(abl, art="zusammenfuehren", haupt=j["haupt"], weitere=j["weitere"], id=j["id"])


def rueckgaengig(abl, haupt, jid=None, jetzt=None, ich=None, admin=False):
    """Zusammenführung trennen (jid: welche; ohne = die letzte aktive). Die übernommenen Inhalte werden in der
    Hauptanfrage ausgeblendet, die weiteren Anfragen bekommen ihren Stand zurück; Dateien bleiben liegen.
    Ergebnis: [wieder eigenständige Anfragen]."""
    jetzt = _jetzt(jetzt)
    ich = abl.kuerzel if ich is None else ich
    haupt = abl.neu_lesen(haupt)
    aktiv = [z for z in haupt.stand.get("zusammen", []) if z["aktiv"]]
    z = next((x for x in aktiv if x["id"] == jid), None) if jid else (aktiv[-1] if aktiv else None)
    if z is None:
        raise ak.AblageFehler("Keine Zusammenführung zum Rückgängigmachen.")
    if not darf(haupt, ich, admin) and z["kuerzel"] != abl.kuerzel:
        raise ak.AblageFehler(f"{haupt.nr} bearbeitet {haupt.bearbeiter}: nur er oder der Admin darf trennen.")
    if not _sperre_nehmen(haupt, abl.kuerzel, jetzt):
        raise ak.AblageFehler(f"{haupt.nr} wird gerade an einem anderen Platz bearbeitet.")
    j = dict(id=z["id"], art="trennen", haupt=haupt.nr, weitere=list(z["von"]), kuerzel=abl.kuerzel,
             zeit=jetzt.isoformat(), stand="trennen")
    try:
        _journal_schreiben(abl, j)
        _trennen(abl, j, jetzt)
    finally:
        _sperre_geben([haupt])
    return [abl.lesen(nr) for nr in z["von"] if abl.lesen(nr) is not None]


def _trennen(abl, j, jetzt):
    haupt = abl.lesen(j["haupt"])
    if not _hat(haupt, ak.TRENNEN, j["id"]):
        abl.ereignis(haupt, ak.TRENNEN, id=j["id"], neu=", ".join(j["weitere"]), jetzt=jetzt)
    for nr in j["weitere"]:
        a = abl.lesen(nr)
        if a is not None and a.stand.get("zusammengefuehrt_in") == j["haupt"] and not _hat(a, ak.GETRENNT, j["id"]):
            abl.ereignis(a, ak.GETRENNT, id=j["id"], alt=j["haupt"], jetzt=jetzt)
    j["stand"] = "getrennt"
    _journal_schreiben(abl, j)
    protokollieren(abl, art="trennen", haupt=j["haupt"], weitere=j["weitere"], id=j["id"])


def wiederherstellen(abl, jetzt=None):
    """Beim Start: abgebrochene Zusammenführungen bzw. Trennungen (Absturz, Netzabbruch) zu Ende führen. Ergebnis:
    [Text] für die Meldung."""
    o = Path(abl.wurzel) / JOURNAL
    out = []
    try:
        dateien = sorted(o.glob("*.json"))
    except OSError:
        return out
    for p in dateien:
        try:
            j = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if j.get("stand") in ("fertig", "getrennt"):
            continue
        try:
            if j.get("art") == "trennen":
                _trennen(abl, j, _jetzt(jetzt))
                out.append(f"Trennung von {j['haupt']} nach Abbruch fertiggestellt.")
            else:
                _ausfuehren(abl, j, _jetzt(jetzt))
                out.append(f"Zusammenführung {', '.join(j['weitere'])} → {j['haupt']} nach Abbruch fertiggestellt.")
        except (OSError, ak.AblageFehler) as e:
            out.append(f"Zusammenführung {j.get('id')}: noch nicht möglich ({e}), nächster Versuch beim nächsten Start.")
    return out


def ziel(akten, akte):
    """Zusammengeführte Anfrage: die Hauptanfrage (auch über mehrere Stufen), sonst die Akte selbst."""
    nach = {a.nr: a for a in akten}
    gesehen = set()
    while akte is not None and akte.stand.get("zusammengefuehrt_in") and akte.nr not in gesehen:
        gesehen.add(akte.nr)
        akte = nach.get(akte.stand["zusammengefuehrt_in"], akte)
    return akte


# ------------------------------------------------------------------ Vorschläge (nie automatisch)
NUMMER = re.compile(r"\b(?:Projekt|Proj\.?|Bestell|Auftrags?|Anfrage|Zeichnungs?|Order|PO)[\s.-]*(?:Nr\.?|Nummer|No\.?)?"
                    r"\s*[:#]?\s*([A-Z0-9][A-Z0-9/._-]{3,20})", re.I)


def nummern(text):
    """Projekt-, Bestell-, Auftrags- und Zeichnungsnummern im Text."""
    return {n.strip("._-/").upper() for n in NUMMER.findall(str(text or "")) if any(c.isdigit() for c in n)}


def vorschlaege(akten, akte, text="", tage=60):
    """Anfragen, zu denen akte vielleicht gehört: [(Akte, Grund)] – gleicher Kunde mit ähnlichem Betreff, gleiche
    Projekt-/Bestellnummer, gleiche Datei (SHA-256). Nur offene bzw. junge Anfragen; nie automatisch."""
    out = []
    kern = ak.betreff_kern(akte.betreff)
    worte = {w for w in re.findall(r"[a-zäöüß0-9]{4,}", kern)}
    eigene_nr = nummern(f"{akte.betreff}\n{text}\n{akte.kopf.get('kurz', '')}")
    shas = {d.get("sha256") for d in akte.dateien() if d.get("sha256") and d["art"] != "mail"}
    grenze = (akte.eingang or datetime.datetime.now()) - datetime.timedelta(days=tage)
    for a in akten:
        if a.nr == akte.nr or a.stand.get("zusammengefuehrt_in") or (a.eingang and a.eingang < grenze):
            continue
        gruende = []
        if shas & {d.get("sha256") for d in a.dateien()}:
            gruende.append("gleiche Datei")
        n = eigene_nr & nummern(f"{a.betreff}\n{a.kopf.get('kurz', '')}")
        if n:
            gruende.append(f"gleiche Nummer {', '.join(sorted(n))}")
        if akte.kunde and a.kunde == akte.kunde:
            andere = {w for w in re.findall(r"[a-zäöüß0-9]{4,}", ak.betreff_kern(a.betreff))}
            if kern and (ak.betreff_kern(a.betreff) == kern or len(worte & andere) >= max(2, len(worte) // 2)):
                gruende.append("gleicher Kunde, ähnlicher Betreff")
        elif not akte.kunde and akte.absender_adresse and a.absender_adresse == akte.absender_adresse \
                and ak.betreff_kern(a.betreff) == kern:
            gruende.append("gleicher Absender und Betreff")
        if gruende:
            out.append((a, ", ".join(gruende)))
    return sorted(out, key=lambda x: (-len(x[1].split(",")), x[0].nr))[:5]


# ------------------------------------------------------------------ Chronik
def chronik(akte):
    """Alle Mails und Ereignisse nach Zeit: [dict(zeit, art 'mail'|'ereignis', text, datei?)]. Mails mit ihrem
    Sendedatum (sonst Eingang), Antworten des Kunden als „Antwort“."""
    out = []
    for d in dokumente(akte):
        if d["art"] != "mail" or d.get("aus_mail"):
            continue
        h = d.get("herkunft") or {}
        out.append(dict(zeit=h.get("datum") or akte.kopf.get("eingang") or "", art="mail", datei=d.get("datei",
                        d["name"]), text=f"Mail von {h.get('von_name') or h.get('von') or akte.absender or '?'}: "
                        f"{h.get('betreff') or d['name']}" + (f" (aus {h['akte']})" if h.get("akte") else "")))
    for e in akte.verlauf:
        if e.get("aktion") == ak.VIREN:
            continue
        out.append(dict(zeit=e.get("zeit", ""), art="ereignis", text=ak.verlauf_text(e).split("  ", 2)[-1],
                        kuerzel=e.get("kuerzel", "")))
    return sorted(out, key=lambda x: str(x["zeit"]))
