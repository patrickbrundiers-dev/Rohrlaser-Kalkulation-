"""Materialanfragen über Outlook (Patrick 13.11.2026, Konzept „Materialanfragen über Outlook“, Freigabe alle a).

Ergänzt die Materialanfrage (materialanfrage.py, Dialog materialanfrage_dialog.py) um:
- E-Mail-Vorlagen (Tabelle mail_vorlagen): Name, Art (Anfrage/Bestellung), Materialgruppe, Betreff, Anrede, Text,
  Gruß, Signatur, PDF anhängen. Ohne eigene Vorlage gilt „Standard“ aus den Einstellungen (anfrage_betreff/_text),
  sie wird nicht als Datensatz angelegt (keine doppelten Daten). Platzhalter wie bisher in geschweiften Klammern.
- Materialgruppen (Tabelle materialgruppen) je Lieferant (zukauf_lieferanten.materialgruppen, „Stahl; Edelstahl“):
  passende Lieferanten werden vorgeschlagen; Standardvorlage und Anrede je Lieferant.
- Blech-, Zukauf- und Dreh-/Frästeile der Kalkulation als Zeilen der Anfrage (F1a), mit Artikelnummer, Bezeichnung,
  Zeichnung, Werkstoff, Abmessung, Stück und Gewicht.
- Verlauf je Angebot (angebote.zusatz['materialanfragen'], wird mit dem Angebot zwischen den Arbeitsplätzen
  abgeglichen): Kennung „MA <Angebot>/<n>“ im Betreff, Status Entwurf → Versendet → Angebot erhalten →
  Abgeschlossen, Datum und Uhrzeit je Schritt, wer. Die Kennung ist ohne gemeinsamen Zähler eindeutig, weil die
  Angebotsnummer es ist und nur der Bearbeiter des Angebots schreibt.
- „Versendet“ aus den Gesendeten Elementen des klassischen Outlook (nur lesen, F4a), sonst per Knopf.
- Schutz vor doppeltem Versand: offene Anfrage an denselben Lieferanten mit gleichem Material wird gemeldet.

Das Programm sendet nie selbst: Versandwege (VERSANDWEGE) öffnen nur eine fertige E-Mail. Ohne Qt."""
import datetime
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

SCHLUESSEL = "materialanfragen"
ENTWURF, VERSENDET, ERHALTEN, ABGESCHLOSSEN = "Entwurf", "Versendet", "Angebot erhalten", "Abgeschlossen"
STATUS = (ENTWURF, VERSENDET, ERHALTEN, ABGESCHLOSSEN)
OFFEN = (ENTWURF, VERSENDET, ERHALTEN)
ANFRAGE, BESTELLUNG = "Materialanfrage", "Materialbestellung"
STANDARD = "Standard"
STANDARD_BESTELLUNG = "Standard Bestellung"
BLECH_GRUPPE, DREH_GRUPPE, ZUKAUF_GRUPPE = "Blechteile", "Dreh-/Frästeile", "Zukaufteile"
TRENNER = "; "
KENNUNG = re.compile(r"\bMA\s+([A-Za-z0-9][\w.-]*)/(\d{1,3})\b")
GRUSS_ZEILE = re.compile(r"^(sehr geehrte|guten tag|hallo|liebe|lieber|moin|servus|grüß gott)\b.*,$", re.I)
SENDEN_TAGE = 30        # Gesendete Elemente so weit zurück durchsuchen


# ---------------------------------------------------------------------- Materialgruppen
def gruppen_liste(text):
    """'Stahl; Edelstahl' -> ['Stahl', 'Edelstahl'] (auch mit Komma getrennt)."""
    return [t.strip() for t in re.split(r"[;,\n]", str(text or "")) if t.strip()]


def gruppen_text(werte):
    out = []
    for w in werte:
        w = str(w).strip()
        if w and w not in out:
            out.append(w)
    return TRENNER.join(out)


def materialgruppe(z, k=None):
    """Materialgruppe einer Zeile der Anfrage: Rohr = Kategorie des Werkstoffs (Stahl, Edelstahl, …), Zukaufteil =
    Blechteile, Dreh-/Frästeile, sonst die Kategorie des Artikels bzw. Zukaufteile."""
    if z.get("materialgruppe"):
        return z["materialgruppe"]
    if z.get("art") == "zukauf":
        typ = z.get("artikeltyp") or ""
        if typ == "Blech" or z.get("kategorie") == BLECH_GRUPPE:
            return BLECH_GRUPPE
        if typ in ("Drehteil", "Frästeil") or z.get("kategorie") in ("Drehteile", "Frästeile"):
            return DREH_GRUPPE
        return z.get("kategorie") or ZUKAUF_GRUPPE
    w = (getattr(k, "werkstoffe", {}) or {}).get(z.get("werkstoff")) or {}
    return w.get("kategorie") or "Stahl"


def passende_lieferanten(zeilen, lieferanten, k=None):
    """Lieferanten für die Zeilen, beste zuerst: [(Name, Grund)]. Erst die Lieferanten der Zeilen (Lieferlängen,
    Preise, Bezug des Artikels), dann die mit passender Materialgruppe (mehr Treffer zuerst), dann der Rest nicht."""
    out, gesehen = [], set()
    for z in zeilen:
        n = z.get("lieferant")
        if n and n not in gesehen:
            out.append((n, "Lieferant des Materials"))
            gesehen.add(n)
    gruppen = [materialgruppe(z, k) for z in zeilen]
    treffer = []
    for l in lieferanten:
        n = l.get("name")
        if not n or n in gesehen:
            continue
        g = set(gruppen_liste(l.get("materialgruppen")))
        t = [x for x in dict.fromkeys(gruppen) if x in g]
        if t:
            treffer.append((-len(t), n, "Materialgruppe " + ", ".join(t)))
    for _, n, grund in sorted(treffer):
        out.append((n, grund))
    return out


# ---------------------------------------------------------------------- Vorlagen
def standard_vorlage(einst, bestellung=False):
    """Vorlage „Standard“ aus den Einstellungen (wie bis 0.9.312): Anrede und Gruß stehen im Text."""
    from .materialanfrage import _einst
    return dict(name=STANDARD_BESTELLUNG if bestellung else STANDARD, art=BESTELLUNG if bestellung else ANFRAGE,
                materialgruppe=None, betreff=_einst(einst, "bestellung_betreff" if bestellung else "anfrage_betreff"),
                anrede="", text=_einst(einst, "bestellung_text" if bestellung else "anfrage_text"), gruss="",
                signatur="", pdf="nein", standard=True)


def vorlagen(db_zeilen, einst, bestellung=False):
    """Vorlagen einer Art: eigene (Tabelle mail_vorlagen) und, falls keine „Standard“ heißt, die Standardvorlage aus
    den Einstellungen vorn."""
    art = BESTELLUNG if bestellung else ANFRAGE
    eigene = [dict(z) for z in db_zeilen if z.get("name") and (z.get("art") or ANFRAGE) == art]
    std = standard_vorlage(einst, bestellung)
    if not any(v["name"] == std["name"] for v in eigene):
        eigene.insert(0, std)
    return eigene


def vorlage_waehlen(alle, lieferant=None, gruppen=()):
    """Vorlage für einen Lieferanten: seine Standardvorlage, sonst die der Materialgruppe, sonst „Standard“."""
    namen = {v["name"]: v for v in alle}
    if lieferant and (lieferant.get("vorlage") or "") in namen:
        return namen[lieferant["vorlage"]]
    for g in gruppen:
        v = next((v for v in alle if v.get("materialgruppe") == g), None)
        if v:
            return v
    return namen.get(STANDARD) or namen.get(STANDARD_BESTELLUNG) or (alle[0] if alle else None)


def anrede(vorlage, lieferant=None):
    """Anrede: die des Lieferanten (z. B. „Sehr geehrter Herr Maier,“), sonst die der Vorlage."""
    a = ((lieferant or {}).get("anrede") or "").strip() or (vorlage.get("anrede") or "").strip()
    return a + ("," if a and not a.endswith((",", "!", ":")) else "")


def text_aus(vorlage, werte, lieferant=None):
    """E-Mail-Text aus Vorlage und Platzhaltern. Steht {anrede} bzw. {gruss} nicht im Text, kommen Anrede vorn und
    Grußformel hinten dazu; Signatur der Vorlage zuletzt (leer = Signatur aus Outlook bzw. den Einstellungen)."""
    from .materialanfrage import _vorlage
    t = vorlage.get("text") or ""
    a, g = anrede(vorlage, lieferant), (vorlage.get("gruss") or "").strip()
    werte = dict(werte, anrede=a, gruss=g, ansprechpartner=(lieferant or {}).get("ansprechpartner") or "",
                 lieferant=(lieferant or {}).get("name") or "")
    if a and "{anrede}" not in t:
        erste = t.split("\n", 1)
        if GRUSS_ZEILE.match(erste[0].strip()):     # Text beginnt schon mit einer Anrede (z. B. Standard): ersetzen
            t = "{anrede}" + ("\n" + erste[1] if len(erste) > 1 else "")
        else:
            t = "{anrede}\n\n" + t
    if g and "{gruss}" not in t:
        t = t.rstrip() + "\n\n{gruss}"
    if "{materialdaten}" not in t and "{positionen}" not in t:
        t = t.rstrip() + "\n\n{materialdaten}"
    t = _vorlage(t, dict(werte, materialdaten=werte.get("positionen", "")))
    return t


def betreff_aus(vorlage, werte, kennung=None):
    from .materialanfrage import _vorlage
    b = _vorlage(vorlage.get("betreff") or "", werte).strip()
    if kennung and kennung not in b and "{kennung}" not in (vorlage.get("betreff") or ""):
        b = f"{b} ({kennung})" if b else kennung
    return b


def zusatz_block(liefertermin="", gueltig="", info=""):
    """Zeilen nach der Materialliste: gewünschter Liefertermin, Angebotsgültigkeit, zusätzliche Informationen."""
    teile = []
    if (liefertermin or "").strip():
        teile.append(f"Gewünschter Liefertermin: {liefertermin.strip()}")
    if (gueltig or "").strip():
        teile.append(f"Bitte Angebot gültig bis: {gueltig.strip()}")
    if (info or "").strip():
        teile.append(info.strip())
    return "\n".join(teile)


def projekt(kopf):
    """Projekt- bzw. Auftragsnummer: Auftragsnummer (beim Beauftragen), sonst Angebotsnummer."""
    return str(kopf.get("auftragsnr") or kopf.get("nummer") or "").strip()


# ---------------------------------------------------------------------- Zukaufteile als Zeilen
def _zahl(w):
    return w if isinstance(w, (int, float)) and not isinstance(w, bool) else None


def zukauf_bedarf(positionen, artikel=None):
    """Blech-, Zukauf- und Dreh-/Frästeile der Kalkulation als Zeilen der Anfrage (ohne Mengenstufen): je Artikel
    (Stamm-ID bzw. Bezeichnung + Artikelnummer) eine Zeile mit der Summe der Mengen. artikel = {id: Artikelzeile}
    für Typ, Maße, Werkstoff, Gewicht, STEP-Datei."""
    from . import blech, zukauf
    artikel = artikel or {}
    zeilen = {}
    for p in positionen:
        for e in zukauf.eintraege(p):
            st = e.get("stand") or {}
            a = artikel.get(e.get("artikel_id")) or {}
            schl = (e.get("artikel_id"), st.get("bezeichnung"), st.get("artikelnr"))
            menge = (_zahl(e.get("menge")) or 0) * zukauf.bezugsmenge(e, p)
            if menge <= 0:
                continue
            z = zeilen.get(schl)
            if z is None:
                laenge, breite, dicke = (_zahl(a.get(n)) for n in ("laenge", "breite", "dicke"))
                masse = " x ".join(f"{x:g}".replace(".", ",") for x in (laenge, breite, dicke) if x)
                z = zeilen[schl] = dict(
                    art="zukauf", profil=None, werkstoff=a.get("werkstoff") or "", oberflaeche="", laenge=laenge,
                    stangen=0, gewicht=0.0 if _zahl(a.get("gewicht")) else None, pos=[], artikel=[],
                    lieferant=(st.get("bezug") or {}).get("lieferant"), zuschnitte=[], anforderungen="",
                    naht_noetig=False, naht=None, artikelnr=st.get("artikelnr") or a.get("artikelnr") or "",
                    bezeichnung=st.get("bezeichnung") or a.get("bezeichnung") or "", masse=masse,
                    einheit=st.get("einheit") or a.get("einheit") or "Stück", kategorie=st.get("kategorie")
                    or a.get("kategorie"), artikeltyp=a.get("artikeltyp"), artikel_id=e.get("artikel_id"),
                    zeichnung=Path(a["step_datei"]).stem if a.get("step_datei") else "",
                    dateien=[a["step_datei"]] if a.get("step_datei") else [])
            z["stangen"] += menge
            if blech.lesen(p.get("technik")) and all(q is not p for q in z.setdefault("blech_pos", [])):
                z["blech_pos"].append(p)        # Blechteil: Zeichnung, DXF und STEP als Anhang (13.11.2026)
            if z["gewicht"] is not None:
                z["gewicht"] += menge * a["gewicht"]
            nr = str(p.get("pos") or p.get("artikel") or "")
            if nr and nr not in z["pos"]:
                z["pos"].append(nr)
            if (p.get("artikel") or "") and p["artikel"] not in z["artikel"]:
                z["artikel"].append(p["artikel"])
    out = list(zeilen.values())
    for z in out:
        z["stangen"] = int(z["stangen"]) if float(z["stangen"]).is_integer() else z["stangen"]
        z["materialgruppe"] = materialgruppe(z)
        z["text"] = zukauf_text(z)
    return out


EINHEIT = {"Stück": "Stück", "kg": "kg", "m": "m"}


def zukauf_text(z, menge=None):
    """'12 Stück Blechteil Lasche (Art.-Nr. B-17, Zeichnung L-17), 200 x 100 x 3, S235JR (ca. 5 kg)'."""
    from .rechnen import zahl
    n = z["stangen"] if menge is None else menge
    e = z.get("einheit") or "Stück"
    angaben = ", ".join(t for t in (f"Art.-Nr. {z['artikelnr']}" if z.get("artikelnr") else "",
                                    f"Zeichnung {z['zeichnung']}" if z.get("zeichnung") and z["zeichnung"]
                                    != z.get("artikelnr") else "") if t)
    g = z.get("gewicht")
    gew = f" (ca. {zahl(g * n / z['stangen'], 0)} kg)" if g and z.get("stangen") else ""
    return (f"{zahl(n, 0) if float(n).is_integer() else zahl(n, 2)} {e} {z.get('bezeichnung') or 'Artikel'}"
            + (f" ({angaben})" if angaben else "") + (f", {z['masse']} mm" if z.get("masse") else "")
            + (f", {z['werkstoff']}" if z.get("werkstoff") else "") + gew)


def artikel_text(z):
    """'für Artikel T-100, T-200 (Pos. 10, 20)' zu einer Rohrzeile, '' ohne Artikelnummern."""
    a = [x for x in z.get("artikel") or () if x]
    return f"für Artikel {', '.join(a)}" if a else ""


# ---------------------------------------------------------------------- Verlauf je Angebot
def _jetzt():
    return datetime.datetime.now().isoformat(timespec="seconds")


def liste(db, angebot_id):
    return [dict(e) for e in (db.zusatz(angebot_id, SCHLUESSEL) or [])]


def kennung(nummer, n):
    return f"MA {nummer or 'ohne-Nr'}/{n}"


def naechste_kennung(db, angebot_id, nummer):
    vorhanden = {e.get("kennung") for e in liste(db, angebot_id)}
    n = len(vorhanden) + 1
    while kennung(nummer, n) in vorhanden:
        n += 1
    return kennung(nummer, n)


def material_schluessel(z):
    """Schlüssel einer Zeile für den Doppelversand-Schutz."""
    if z.get("art") == "zukauf":
        return f"zukauf|{z.get('artikel_id') or ''}|{z.get('bezeichnung') or ''}|{z.get('artikelnr') or ''}"
    return f"rohr|{z.get('profil')}|{z.get('werkstoff')}|{z.get('oberflaeche') or ''}|{z.get('laenge')}"


def doppelt(db, angebot_id, lieferant, schluessel):
    """Offene Anfrage an diesen Lieferanten mit (teilweise) gleichem Material oder None."""
    s = set(schluessel)
    for e in reversed(liste(db, angebot_id)):
        if e.get("lieferant") == lieferant and e.get("status") in OFFEN and s & set(e.get("schluessel") or ()):
            return e
    return None


def doppelt_text(e):
    z = _zeit_text(e.get("versendet") or e.get("erstellt"))
    return (f"An {e.get('lieferant')} gibt es schon die Anfrage {e.get('kennung')} ({e.get('status')}, {z}"
            + (f", {e['wer']}" if e.get("wer") else "") + ") mit gleichem Material.")


def _zeit_text(iso):
    try:
        return datetime.datetime.fromisoformat(str(iso)).strftime("%d.%m.%Y %H:%M")
    except (TypeError, ValueError):
        return str(iso or "")


def anlegen(db, angebot_id, eintrag, wer=""):
    """Anfrage in den Verlauf schreiben (Status Entwurf: in Outlook geöffnet bzw. als Datei gespeichert). eintrag:
    kennung, lieferant, an, vorlage, betreff, text, zeilen (Texte), schluessel, anhaenge (Dateinamen), liefertermin,
    gueltig, info, intern, weg, bezug (Kennung der ersten Anfrage beim erneuten Senden). Ergebnis: Eintrag."""
    alle = liste(db, angebot_id)
    jetzt = _jetzt()
    e = dict(eintrag, status=ENTWURF, erstellt=jetzt, wer=wer or "",
             verlauf=[dict(zeit=jetzt, status=ENTWURF, wer=wer or "", text=eintrag.get("weg_text") or "")])
    e.pop("weg_text", None)
    alle.append(e)
    db.zusatz_setzen(angebot_id, SCHLUESSEL, alle)
    return e


def status_setzen(db, angebot_id, kenn, status, wer="", text="", zeit=None):
    """Status einer Anfrage ändern (mit Datum, Uhrzeit, wer); True = geändert."""
    if status not in STATUS:
        raise ValueError(f"Unbekannter Status: {status}")
    alle = liste(db, angebot_id)
    for e in alle:
        if e.get("kennung") == kenn:
            if e.get("status") == status:
                return False
            zeit = zeit or _jetzt()
            e["status"] = status
            if status == VERSENDET and not e.get("versendet"):
                e["versendet"] = zeit
            e.setdefault("verlauf", []).append(dict(zeit=zeit, status=status, wer=wer or "", text=text or ""))
            db.zusatz_setzen(angebot_id, SCHLUESSEL, alle)
            return True
    return False


def erneut_vermerken(db, angebot_id, kenn, wer=""):
    """Erneut gesendet (Erinnerung, F5a): Zähler + Verlauf, Status wieder Entwurf bis zum Versand."""
    alle = liste(db, angebot_id)
    for e in alle:
        if e.get("kennung") == kenn:
            e["erneut"] = int(e.get("erneut") or 0) + 1
            e["status"] = ENTWURF
            e.setdefault("verlauf", []).append(dict(zeit=_jetzt(), status=ENTWURF, wer=wer or "",
                                                    text=f"Erinnerung {e['erneut']} geöffnet"))
            db.zusatz_setzen(angebot_id, SCHLUESSEL, alle)
            return e
    return None


def erinnerung_betreff(e):
    b = e.get("betreff") or e.get("kennung") or ""
    return b if b.lower().startswith("erinnerung") else f"Erinnerung: {b}"


def erinnerung_text(e):
    d = _zeit_text(e.get("versendet") or e.get("erstellt"))[:10]
    return (f"wir kommen auf unsere Anfrage {e.get('kennung')} vom {d} zurück und bitten um Ihr Angebot.\n\n"
            "--- Unsere Anfrage ---\n" + (e.get("text") or ""))


def alle(db):
    """Alle Anfragen aller Angebote (auch der Kollegen): [Eintrag + angebot_id, nummer, kunde, fremd]."""
    out = []
    for aid, nummer, kunde, fremd, zusatz in db.con.execute(
            "SELECT id, nummer, kunde, fremd, zusatz FROM angebote WHERE zusatz LIKE ?", (f'%"{SCHLUESSEL}"%',)):
        try:
            d = json.loads(zusatz) if zusatz else {}
        except ValueError:
            continue
        for e in d.get(SCHLUESSEL) or ():
            out.append(dict(e, angebot_id=aid, nummer=nummer, kunde=kunde, fremd=fremd))
    return sorted(out, key=lambda e: e.get("erstellt") or "", reverse=True)


def filtern(eintraege, status=None, lieferant=None, suche=""):
    s = (suche or "").lower().strip()
    return [e for e in eintraege if (not status or e.get("status") == status)
            and (not lieferant or e.get("lieferant") == lieferant)
            and (not s or s in " ".join(str(e.get(n) or "") for n in ("kennung", "nummer", "kunde", "lieferant",
                                                                        "betreff", "intern")).lower())]


# ---------------------------------------------------------------------- Status automatisch
def gesendet_abgleichen(db, gesendet, wer=""):
    """Gesendete Elemente [(Betreff, Zeit ISO)] mit den Entwürfen abgleichen: Kennung im Betreff = Versendet (nur
    eigene Angebote). Ergebnis: Anzahl."""
    zeiten = {}
    for betreff, zeit in gesendet:
        for m in KENNUNG.finditer(betreff or ""):
            k = f"MA {m.group(1)}/{m.group(2)}"
            zeiten[k] = max(zeiten.get(k, ""), zeit or "")
    n = 0
    for e in alle(db):
        if e.get("fremd") or e.get("status") != ENTWURF or e.get("kennung") not in zeiten:
            continue
        if status_setzen(db, e["angebot_id"], e["kennung"], VERSENDET, wer, "in Outlook gesendet",
                         zeiten[e["kennung"]] or None):
            n += 1
    return n


def antwort_erhalten(db, angebot_id, lieferant, text="", wer=""):
    """Antwort eines Lieferanten eingelesen (lieferantenantwort.einlesen): die Anfrage mit der Kennung im Text, sonst
    die neueste offene an diesen Lieferanten bekommt „Angebot erhalten“. Ergebnis: Kennung oder None."""
    eintraege = liste(db, angebot_id)
    kenn = next((f"MA {m.group(1)}/{m.group(2)}" for m in KENNUNG.finditer(text or "")), None)
    ziel = next((e for e in eintraege if e.get("kennung") == kenn), None) if kenn else None
    if ziel is None:
        ziel = next((e for e in reversed(eintraege) if e.get("lieferant") == lieferant
                     and e.get("status") in (ENTWURF, VERSENDET)), None)
    if ziel is None or ziel.get("status") in (ERHALTEN, ABGESCHLOSSEN):
        return None
    status_setzen(db, angebot_id, ziel["kennung"], ERHALTEN, wer, "Antwort eingelesen")
    return ziel["kennung"]


def abschliessen(db, angebot_id, lieferant=None, wer="", text="bestellt"):
    """Bestellung beim Lieferanten: seine offenen Anfragen dieses Angebots abschließen. Ergebnis: Anzahl."""
    n = 0
    for e in liste(db, angebot_id):
        if e.get("status") in OFFEN and (not lieferant or e.get("lieferant") == lieferant):
            n += status_setzen(db, angebot_id, e["kennung"], ABGESCHLOSSEN, wer, text)
    return n


# PowerShell: klassisches Outlook per COM, Gesendete Elemente nur lesen (Betreff und Sendezeit der letzten Tage)
GESENDET_PS = r"""
$ErrorActionPreference = 'Stop'
$tage = [int]$args[1]
$o = New-Object -ComObject Outlook.Application
$f = $o.Session.GetDefaultFolder(5)
$ab = (Get-Date).AddDays(-$tage).ToString('g')
$items = $f.Items.Restrict("[SentOn] >= '" + $ab + "'")
$out = @()
foreach ($i in $items) {
    if ($i.Subject -match 'MA ') { $out += @{ betreff = [string]$i.Subject; zeit = $i.SentOn.ToString('s') } }
}
$out | ConvertTo-Json -Compress | Set-Content -Encoding UTF8 -LiteralPath $args[0]
"""


def gesendete(ausfuehren=None, tage=SENDEN_TAGE):
    """Betreff und Sendezeit der Gesendeten Elemente mit einer Kennung (nur lesen). Ergebnis: (True, [(Betreff,
    Zeit)]) oder (False, Fehlertext). ausfuehren(befehl) ersetzt subprocess.run (Tests)."""
    if ausfuehren is None and sys.platform != "win32":
        return False, "Outlook gibt es nur unter Windows."
    with tempfile.TemporaryDirectory() as tmp:
        skript, aus = Path(tmp) / "gesendet.ps1", Path(tmp) / "gesendet.json"
        skript.write_text(GESENDET_PS, encoding="utf-8-sig")
        befehl = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(skript), str(aus), str(tage)]
        try:
            if ausfuehren:
                r = ausfuehren(befehl)
            else:
                r = subprocess.run(befehl, capture_output=True, text=True, timeout=60,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except (OSError, subprocess.TimeoutExpired) as e:
            return False, str(e)
        if r.returncode != 0:
            return False, (r.stderr or r.stdout or "").strip()[:400] or f"Rückgabewert {r.returncode}"
        try:
            roh = aus.read_text(encoding="utf-8-sig").strip() if aus.exists() else ""
            d = json.loads(roh) if roh else []
        except ValueError:
            return False, "Antwort von Outlook nicht lesbar."
    d = [d] if isinstance(d, dict) else d
    return True, [(x.get("betreff") or "", x.get("zeit") or "") for x in d if isinstance(x, dict)]


# ---------------------------------------------------------------------- Versandwege (austauschbar)
def outlook_weg(an, betreff_, text_, anhaenge=(), ausfuehren=None, signatur_=False):
    """Klassisches Outlook am PC (COM): E-Mail anzeigen, nie senden."""
    from .materialanfrage import outlook_oeffnen
    return outlook_oeffnen(an, betreff_, text_, anhaenge, ausfuehren=ausfuehren, signatur_=signatur_)


# Name -> Funktion(an, betreff, text, anhaenge, ausfuehren, signatur_) -> (ok, Fehler). Ein späterer Weg (z. B.
# Microsoft-Graph-Entwurf, sobald eine App-Registrierung da ist) kommt hier dazu; der Dialog bleibt gleich.
VERSANDWEGE = {"outlook": outlook_weg}


# ---------------------------------------------------------------------- Zeichnungen im Angebotsordner
ZEICHNUNG_ENDUNGEN = (".pdf", ".dxf", ".dwg", ".step", ".stp", ".igs", ".iges")


# ---------------------------------------------------------------------- Interner Einkauf (Patrick 13.11.2026)
# Der interne Einkauf bekommt die Anfrage wie ein Lieferant und verteilt sie weiter. Er steht in den Einstellungen
# (Materialanfrage → Interner Einkauf); ohne E-Mail-Adresse wird er nicht angeboten.
EINKAUF_NAME, EINKAUF_ANREDE = "Interner Einkauf", "Hallo zusammen"


def einkauf(einst):
    """Interner Einkauf als Empfänger: dict(name, email, anrede, intern=True) oder None (keine Adresse)."""
    einst = einst or {}
    mail = str(einst.get("einkauf_email") or "").strip()
    if not mail:
        return None
    return dict(name=str(einst.get("einkauf_name") or "").strip() or EINKAUF_NAME, email=mail,
                anrede=str(einst.get("einkauf_anrede") or "").strip() or EINKAUF_ANREDE, intern=True,
                blech_email=str(einst.get("einkauf_blech_email") or "").strip())


def einkauf_aufteilen(e, zeilen, auswahl, k=None):
    """E-Mails an den Einkauf: [(Name im Verlauf, E-Mail, Zeilen-Indizes)]. Mit eigener Adresse für Blech (Patrick
    13.11.2026: Rohr und Blech zwei verschiedene Adressen) gehen Blechteile an die Blech-Adresse, alles andere an die
    Hauptadresse; leere Teile entfallen."""
    if not e.get("blech_email"):
        return [(e["name"], e["email"], list(auswahl))]
    blech = [r for r in auswahl if materialgruppe(zeilen[r], k) == BLECH_GRUPPE]
    rest = [r for r in auswahl if r not in blech]
    return [(f"{e['name']} ({n})", m, rows) for n, m, rows in (("Rohr", e["email"], rest),
                                                                ("Blech", e["blech_email"], blech)) if rows]


# ---------------------------------------------------------------------- Blechteile: Zeichnung, DXF, STEP
BLECH_ANHAENGE = (("pdf", "Zeichnung (PDF)", (".pdf",)), ("dxf", "Abwicklung (DXF)", (".dxf",)),
                  ("step", "3D (STEP)", (".step", ".stp")))


def blech_name(p):
    """Name der Dateien eines Blechteils: Artikel- bzw. Zeichnungsnummer, sonst Bezeichnung oder Pos."""
    n = str(p.get("artikel") or p.get("bezeichnung") or f"Pos {p.get('pos') or ''}").strip()
    return re.sub(r'[\\/:*?"<>|]+', "_", n)[:60] or "Blech"


def blech_vorhanden(dateien, p):
    """Vorhandene Dateien eines Blechteils (Zeichnung, DXF, STEP im Ordner des Angebots, Name enthält die
    Artikelnummer): {art: Pfad}."""
    nr = str(p.get("artikel") or "").lower()
    out = {}
    if len(nr) < 3:
        return out
    for d in dateien:
        d = Path(d)
        for art, _, endungen in BLECH_ANHAENGE:
            if art not in out and d.suffix.lower() in endungen and nr in d.stem.lower():
                out[art] = d
    return out


def blech_dxf(pfad, p, einst=None, werkstoffe=None, laserdaten=None, blech_einst=None):
    """Abwicklung eines Blechteils (Eingaben des Blech-Editors in positionen.technik) als DXF schreiben, wie
    „Abwicklung als DXF“ im Blech-Editor. Ergebnis: Pfad; ValueError, wenn die Eingaben nicht reichen."""
    from . import blech, dxf
    e = blech.lesen(p.get("technik"))
    if not e:
        raise ValueError("keine Eingaben des Blech-Editors")
    erg = blech.rechnen(e, werkstoffe or {}, laserdaten or [], blech_einst)
    if not erg.get("zuschnitt"):
        raise ValueError("; ".join(erg.get("fehler") or ["keine Abwicklung"]))
    text = " ".join(str(x) for x in (p.get("artikel"), p.get("bezeichnung")) if x)
    elem, _ = dxf.elemente(e, erg["zuschnitt"], beschriftung=text,
                           biegelinien=(einst or {}).get("blech_dxf_biegelinien") != "nein")
    dxf.speichern(pfad, elem, dxf.layer_namen((einst or {}).get("blech_dxf_layer")))
    return Path(pfad)


def blech_datei(art, ziel, p, kopf, einst, db, widget=None):
    """Datei eines Blechteils erzeugen (art pdf/dxf/step, wie im Blech-Editor: Zeichnung, Abwicklung, STEP mit
    Prüfung gegen die Mutter-STEP). Ergebnis: Pfad; ValueError/OSError mit Grund, wenn es nicht geht (z. B. STEP
    ohne STEP-Import.exe)."""
    from . import blech
    bd = db.blech_daten()
    werkstoffe, laser, b_einst = bd["werkstoffe"], bd["laser"], bd["einst"]
    if art == "dxf":
        return blech_dxf(ziel, p, einst, werkstoffe, laser, b_einst)
    e = blech.lesen(p.get("technik"))
    if not e:
        raise ValueError("keine Eingaben des Blech-Editors")
    erg = blech.rechnen(e, werkstoffe, laser, b_einst)
    if not erg.get("zuschnitt"):
        raise ValueError("; ".join(erg.get("fehler") or ["keine Abwicklung"]))
    teil = dict(bezeichnung=p.get("bezeichnung"), artikelnr=p.get("artikel"), stueck=p.get("stueck"))
    if art == "pdf":
        from . import zeichnung
        zeichnung.blech_pdf(ziel, kopf or {}, teil, e, erg, einst)
        return Path(ziel)
    from . import step_export
    plan = step_export.blech_teil(e, erg["zuschnitt"], blech_name(p))
    netz = None
    if p.get("id") and hasattr(db, "netz"):             # Konturen wie in der STEP des Kunden (Grundregel 25.10.)
        from .ansicht3d import entpacken
        netz = entpacken(db.netz(p["id"])) or None
    plan = step_export.mutter_einzelteil(plan, netz) if netz else [plan]
    r = step_export.mit_anzeige(widget, plan, str(ziel), name=blech_name(p)) if widget is not None else \
        step_export.schreiben(plan, str(ziel), name=blech_name(p))
    if not r.get("teile") or r.get("fehler"):
        raise ValueError(r.get("fehler") or "STEP nicht geschrieben")
    return Path(ziel)


def zeichnungen(ordner, zeilen=(), eigene_praefix=""):
    """Zeichnungen im Ordner des Angebots (eine Ebene tief): [(Pfad, vorbelegt)]. Vorbelegt (F6a): PDF, deren Name
    eine Artikel- bzw. Zeichnungsnummer der Zeilen enthält. Eigene Ausgaben (Name beginnt mit der Angebotsnummer)
    zählen nicht."""
    try:
        o = Path(ordner)
        dateien = [p for p in sorted(o.glob("*")) + sorted(o.glob("*/*"))
                   if p.is_file() and p.suffix.lower() in ZEICHNUNG_ENDUNGEN]
    except (OSError, TypeError):
        return []
    nummern = {str(x).lower() for z in zeilen for x in [z.get("artikelnr"), z.get("zeichnung")] + list(
        z.get("artikel") or ()) if x and len(str(x)) >= 3}
    out = []
    for p in dateien:
        if eigene_praefix and p.name.startswith(eigene_praefix):
            continue
        name = p.stem.lower()
        out.append((p, p.suffix.lower() == ".pdf" and any(n in name for n in nummern)))
    for z in zeilen:                # STEP-Datei des Zukaufartikels (nicht vorbelegt)
        for d in z.get("dateien") or ():
            p = Path(d)
            if p.is_file() and all(p != x for x, _ in out):
                out.append((p, False))
    return out


# ---------------------------------------------------------------------- E-Mail zusammensetzen
def mail_bauen(vorlage, kopf, zeilen, einst, k, mengen=None, zuschnitt=None, preise=None, lieferant=None,
               kennung_=None, liefertermin="", gueltig="", info="", artikel=True):
    """(Betreff, Text) einer Anfrage aus Vorlage und Zeilen. mengen/zuschnitt/preise wie materialanfrage.anschreiben;
    lieferant = Zeile der Lieferanten (Anrede, Ansprechpartner). Liefertermin, Gültigkeit und Information stehen an
    ihrem Platzhalter, sonst unter der Materialliste."""
    from .materialanfrage import _werte, zeile_block
    mengen = mengen or {}
    liste_ = "\n".join(zeile_block(z, k, mengen.get(i), zuschnitt is None or i in zuschnitt,
                                   (preise or {}).get((z.get("profil"), z.get("werkstoff"))), artikel)
                       for i, z in enumerate(zeilen))
    t = (vorlage.get("text") or "") + (vorlage.get("betreff") or "")
    extra = zusatz_block("" if "{liefertermin}" in t else liefertermin, "" if "{gueltigkeit}" in t else gueltig,
                         "" if "{info}" in t else info)
    werte = _werte(kopf, einst, liste_ + (f"\n\n{extra}" if extra else ""))
    werte.update(projekt=projekt(kopf), kennung=kennung_ or "", liefertermin=liefertermin or "",
                 gueltigkeit=gueltig or "", info=info or "")
    return betreff_aus(vorlage, werte, kennung_), text_aus(vorlage, werte, lieferant)
