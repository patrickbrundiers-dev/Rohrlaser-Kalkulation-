"""Anfragen vorbereiten (Automationen 03.11.2026, Vorschläge 3 und 4, Freigabe „Alle Empfehlungen“).

Vormessen (3a): Sobald eine Anfrage im Anfrage-Ordner liegt, misst das Programm ihre STEP-Dateien im Hintergrund mit
STEP-Import.exe – mit denselben Einstellungen wie beim Öffnen und in denselben Zwischenspeicher (STEP-Cache). Beim
Öffnen ist die Messung dann schon da. STEP-Dateien in Mails und ZIPs werden dafür in einen temporären Ordner
ausgepackt (der Zwischenspeicher erkennt sie am Inhalt wieder). Die Karte zeigt eine Zusammenfassung: Teile, Profile,
fehlende Profile, Wiederholteile des Kunden und einen Richtpreis (Kalkulation wie ein neues Angebot, je Teil ein
Stück). Gespeichert wird nichts.
Für alle Plätze (Patrick 18.11.2026 „nicht erst laden“): die Einträge des Zwischenspeichers, die eine Vormessung
benutzt oder geschrieben hat, kommen zusätzlich in die Akte (Unterordner _messung); jeder Platz übernimmt sie vor
Kalkulieren und 3D-Vorschau in seinen eigenen Zwischenspeicher (messung_uebernehmen). So misst nur ein Platz.

Anfrage-Ampel (4a): Eingang = älteste Mail bzw. Datei der Anfrage; Frist in Arbeitstagen (Einstellung anfrage_frist,
je Kunde Kundenvorgaben → „Anfrage beantworten in“), Feiertage des Bundeslands zählen nicht. Grün bis zum letzten
Tag vor der Frist, gelb am letzten Tag, rot danach. Die Liste sortiert nach Dringlichkeit (rot vor gelb vor grün,
dann nach Fälligkeit). Ohne Qt."""
import datetime
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

GRUEN, GELB, ROT = "grün", "gelb", "rot"
RANG = {ROT: 0, GELB: 1, GRUEN: 2, None: 3}
FARBE = {GRUEN: "#2F7D4F", GELB: "#A66A00", ROT: "#B42318"}
ZEITLIMIT_S = 900           # Vormessung einer Anfrage höchstens so lange
MESSUNG = "_messung"        # Unterordner der Akte: Einträge des STEP-Zwischenspeichers für alle Plätze


# ---------------------------------------------------------------------- Ampel
def eingang(anfrage):
    """Eingang der Anfrage: Sendezeit der ältesten Mail bzw. Änderungszeit der ältesten Datei (datetime oder None)."""
    from . import anfragen
    zeiten = []
    for d in anfrage.dateien:
        try:
            z = anfragen.quell_zeit(d)
        except Exception:
            z = None
        if z and z > datetime.datetime(1971, 1, 1):
            zeiten.append(z.replace(tzinfo=None) if z.tzinfo else z)
    return min(zeiten) if zeiten else anfrage.zeit


def frist_tage(db, kundennr):
    """Arbeitstage bis zur Antwort: Kundenvorgabe, sonst Einstellung anfrage_frist; 0 = keine Ampel."""
    from . import kundenvorgabe
    v = (kundenvorgabe.fuer_kunde(db, kundennr) or {}).get("antwort_frist")
    if v in (None, ""):
        v = db.einstellung("anfrage_frist")
    try:
        return max(0, int(v or 0))
    except (TypeError, ValueError):
        return 0


def ampel(eingang_, tage, jetzt=None, land=None):
    """(Stufe, fällig am als date, Text) oder (None, None, '') ohne Frist bzw. Eingang."""
    from . import feiertage
    if not eingang_ or not tage:
        return None, None, ""
    jetzt = jetzt or datetime.datetime.now()
    faellig = feiertage.arbeitstage_spaeter(eingang_.date(), int(tage), land)
    heute = jetzt.date()
    if heute > faellig:
        n = (heute - faellig).days
        return ROT, faellig, f"überfällig seit {faellig:%d.%m.} ({n} Tag{'e' if n != 1 else ''})"
    if heute == faellig:
        return GELB, faellig, "heute beantworten"
    rest = sum(1 for i in range(1, (faellig - heute).days + 1)
               if feiertage.ist_arbeitstag(heute + datetime.timedelta(days=i), land))
    return GRUEN, faellig, f"bis {faellig:%d.%m.} ({rest} Arbeitstag{'e' if rest != 1 else ''})"


def sortieren(eintraege):
    """[(Anfrage, Stufe, fällig)] nach Dringlichkeit: rot, gelb, grün, ohne; dann früher fällig, dann älter."""
    return sorted(eintraege, key=lambda e: (RANG.get(e[1], 3), e[2] or datetime.date.max,
                                            e[0].zeit or datetime.datetime.max))


# ---------------------------------------------------------------------- Vormessen
def stempel(anfrage):
    """Kennung des Dateistands einer Anfrage (Name, Größe, Änderungszeit je Datei): ändert sich eine Datei, wird
    neu gemessen."""
    out = []
    for d in anfrage.dateien:
        try:
            st = d.stat()
            out.append((str(d), st.st_size, st.st_mtime_ns))
        except OSError:
            out.append((str(d), None, None))
    return tuple(out)


def step_quellen(anfrage, ordner):
    """STEP-Dateien der Anfrage zum Vormessen: lose Dateien direkt, aus Mails und ZIPs nach ordner ausgepackt.
    Ergebnis: [Pfad] (ältere Versionen '(alt)' nicht)."""
    from . import anfragen, mail
    out = [d for d in anfrage.step]
    namen = {d.name.lower() for d in out}
    ordner = Path(ordner)
    for m in anfrage.mails + anfrage.archive:
        try:
            inhalt = anfragen._zip_dateien(m) if m.suffix.lower() in anfragen.ARCHIV else \
                ((mail.lesen(m) or mail.Mail()).anhaenge)
        except Exception:
            continue
        for name, daten in inhalt:
            if Path(name).suffix.lower() not in anfragen.STEP or name.lower() in namen:
                continue
            namen.add(name.lower())
            ziel = ordner / Path(name).name
            try:
                ziel.write_bytes(daten)
            except OSError:
                continue
            out.append(ziel)
    return out


def auftrag(db, programmordner, anfrage):
    """Was der Hintergrund zum Messen braucht (ohne Datenbank im Thread): dict(befehl, args) oder None (keine
    Messung verfügbar oder ausgeschaltet)."""
    from . import step, step_einstellungen
    if (db.einstellung("anfrage_vormessen") or "ja") != "ja":
        return None
    befehl = step.messprogramm(programmordner)
    if befehl is None:
        return None
    args = step_einstellungen.mess_argumente(db)
    if "--prozesse" in args:            # im Hintergrund nur ein Prozess, damit das Programm flüssig bleibt
        args[args.index("--prozesse") + 1] = "1"
    job = dict(befehl=befehl, args=args + ["--flachstahl-bis", str(step_einstellungen.flach_bis(db, anfrage.kunde))])
    from . import server_rechnen
    z = server_rechnen.zugang(db)       # S4: im Serverbetrieb misst der Rechner am Server einmal für alle Plätze
    if z is not None and z["ort"] != server_rechnen.ORT_WAHL[2]:
        job["server"] = z
    return job


def vorschau_argumente(db, kundennr=None):
    """Messargumente der 3D-Vorschau: dieselben wie Vormessung und Kalkulieren (Zwischenspeicher, Grenzwerte,
    Flachstahl des Kunden), damit eine vorgemessene STEP sofort da ist. Die Zahl der Prozesse bleibt wie eingestellt
    (die Vorschau wartet auf das Ergebnis)."""
    from . import step_einstellungen
    return step_einstellungen.mess_argumente(db) + ["--flachstahl-bis", str(step_einstellungen.flach_bis(db, kundennr))]


def cache_aus(args):
    """Ordner des Zwischenspeichers aus den Messargumenten (oder None)."""
    args = list(args or ())
    return Path(args[args.index("--cache") + 1]) if "--cache" in args[:-1] else None


def _eintraege(ordner):
    try:
        return [e for e in Path(ordner).iterdir() if e.is_dir() and not e.name.endswith(".neu")
                and (e / "ergebnis.json").is_file()]
    except OSError:
        return []


def _kopieren(e, ziel):
    """Einen Eintrag des Zwischenspeichers nach ziel kopieren (erst unter .neu, dann umbenennen). Ergebnis: bool."""
    tmp = Path(ziel) / (e.name + ".neu")
    try:
        shutil.rmtree(tmp, ignore_errors=True)
        shutil.copytree(e, tmp)
        if (Path(ziel) / e.name).exists():
            shutil.rmtree(tmp, ignore_errors=True)
            return False
        tmp.rename(Path(ziel) / e.name)
        return True
    except OSError:
        shutil.rmtree(tmp, ignore_errors=True)
        return False


def messung_ablegen(cache, ziel, seit):
    """Einträge des Zwischenspeichers, die seit `seit` (time.time) benutzt oder geschrieben wurden, in den Ordner der
    Akte legen (ziel = Akte/_messung). Ergebnis: Anzahl kopierter Einträge."""
    if cache is None or ziel is None:
        return 0
    n = 0
    for e in _eintraege(cache):
        try:
            neu = e.stat().st_mtime >= seit - 1
        except OSError:
            continue
        if neu and not (Path(ziel) / e.name).exists():
            try:
                Path(ziel).mkdir(parents=True, exist_ok=True)
            except OSError:
                return n
            n += _kopieren(e, ziel)
    return n


def messung_uebernehmen(quelle, cache):
    """Vormessung eines anderen Platzes (Akte/_messung) in den eigenen Zwischenspeicher übernehmen, nur fehlende
    Einträge. Ergebnis: Anzahl übernommener Einträge."""
    if cache is None or not Path(quelle).is_dir():
        return 0
    try:
        Path(cache).mkdir(parents=True, exist_ok=True)
    except OSError:
        return 0
    return sum(_kopieren(e, cache) for e in _eintraege(quelle) if not (Path(cache) / e.name).exists())


def messen(job, anfrage):
    """Im Hintergrund-Thread: Anfrage vormessen. Ergebnis: Liste der Messwerte (dicts) oder None. job["ablage"]:
    Ordner der Akte für die Einträge des Zwischenspeichers (messung_ablegen)."""
    from . import step
    seit = time.time()
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / "step").mkdir()
        dateien = step_quellen(anfrage, tmp / "step")
        if not dateien:
            return None
        if job.get("server"):           # erst am Server (gleiche Anfrage an allen Plätzen: ein Auftrag), dann hier
            from . import server_rechnen    # aus dem gemeinsamen Zwischenspeicher
            server_rechnen.am_server_rechnen(job["server"], dateien, job["args"], True, entscheiden_=False,
                                             warten_start_s=ZEITLIMIT_S, zeitlimit_s=ZEITLIMIT_S)
        liste, ausgabe = tmp / "liste.txt", tmp / "messwerte.txt"
        liste.write_text("\n".join(map(str, dateien)), encoding="utf-8")
        befehl = job["befehl"] + ["--liste", str(liste), "--ausgabe", str(ausgabe), "--netze", str(tmp / "netze")] \
            + job["args"]
        try:
            subprocess.run(befehl, capture_output=True, timeout=ZEITLIMIT_S,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except (OSError, subprocess.SubprocessError):
            return None
        if job.get("ablage"):
            try:
                messung_ablegen(cache_aus(job["args"]), Path(job["ablage"]), seit)
            except OSError:
                pass
        if not ausgabe.exists():
            return None
        return step.lies_messwerte(ausgabe)


def zusammenfassung(messwerte, profile):
    """dict(teile, profile=[IDs], fehlend=[Vorschläge ohne Stammdaten], bleche, fehler, artikel=[…]) aus den
    Messwerten."""
    from . import step
    teile, ids, fehlend, bleche, fehler, artikel = 0, [], [], 0, 0, []
    for m in messwerte or ():
        if m.get("fehler"):
            fehler += 1
            continue
        if m.get("profilform") in step.BLECHE:
            bleche += 1
            continue
        if m.get("profilform") in step.NICHT_KALKULIERT:
            continue
        teile += 1
        if m.get("artikel"):
            artikel.append(m["artikel"])
        pid = step.finde_profil(m, profile)
        if pid:
            if pid not in ids:
                ids.append(pid)
        else:
            v = m.get("profil_id_vorschlag") or m.get("profilform") or "?"
            if v not in fehlend:
                fehlend.append(v)
    return dict(teile=teile, profile=ids, fehlend=fehlend, bleche=bleche, fehler=fehler, artikel=artikel)


def _z(w):
    try:
        return float(str(w).replace(",", ".") or 0)
    except (TypeError, ValueError):
        return 0.0


def richtpreis(db, kundennr, messwerte):
    """Richtpreis netto (je Teil 1 Stück) wie ein neues Angebot: Vorgaben des Kunden, Werkstoff aus Importprofil bzw.
    Einstellung, Länge und Schneidweg aus der Messung. Ergebnis: Betrag oder None (nichts kalkulierbar)."""
    from . import importprofil, rechnen, step
    k = db.kontext()
    vorgaben = importprofil.vorgaben(importprofil.fuer_kunde(db, kundennr))
    ws = vorgaben.get("werkstoff") or db.einstellung("step_werkstoff")
    if ws not in k.werkstoffe:
        ws = next(iter(k.werkstoffe), None)
    if not ws:
        return None
    pos = []
    for m in messwerte or ():
        if m.get("fehler") or m.get("profilform") in step.NICHT_KALKULIERT:
            continue
        pid = step.finde_profil(m, k.profile)
        laenge = _z(m.get("laenge"))
        if not pid or laenge <= 0:
            continue
        pos.append(dict(pos=10 * (len(pos) + 1), profil_id=pid, werkstoff_id=ws, laenge=laenge, stueck=1,
                        schneidweg=_z(m.get("schneidweg")), einstiche=int(_z(m.get("konturen"))) + 2,
                        artikel=m.get("artikel") or "", bezeichnung="Vormessung"))
    if not pos:
        return None
    tab = db.tabellen()
    kopf = db.neuer_kopf(dict(kundennr=kundennr) if kundennr else {})
    kopf["zeitbasis"] = db.zeitbasis_vorgabe(kopf.get("maschine"))
    e = rechnen.einstellungen_angebot(kopf, rechnen.einstellungen_fest(tab, db.einstellungen()))
    try:
        erg = rechnen.optimieren(kopf, pos, k, tab, e)
        if erg.get("fehler") and len(erg["fehler"]) >= len(pos):
            return None
        _, s = rechnen.kalkulation(kopf, pos, erg, k, tab, e)
    except (ValueError, AssertionError, KeyError, ZeroDivisionError, TypeError):
        return None
    return rechnen._n(s.get("verkauf")) or None


def wiederholt(db, kundennr, artikel):
    """Anzahl Artikel, die der Kunde schon angefragt hat (Teilekatalog)."""
    from . import teilekatalog
    if not kundennr or not artikel:
        return 0
    bekannt = {r["artikel"].casefold() for r in teilekatalog.katalog(db, kundennr) if r["artikel"]}
    return sum(1 for a in set(artikel) if str(a).strip().casefold() in bekannt)


def text(z, preis=None, wiederholt_=0):
    """Eine Zeile für die Karte: '12 Teile · 4 Profile (1 fehlt) · ca. 3.400 € · 2 Wiederholteile'."""
    from .ausgabe import euro_text
    if not z:
        return ""
    teile = [f"{z['teile']} Teil{'e' if z['teile'] != 1 else ''}"]
    if z["profile"] or z["fehlend"]:
        teile.append(f"{len(z['profile']) + len(z['fehlend'])} Profil{'e' if len(z['profile']) + len(z['fehlend']) != 1 else ''}"
                     + (f" ({len(z['fehlend'])} fehlt in den Stammdaten)" if z["fehlend"] else ""))
    if z["bleche"]:
        teile.append(f"{z['bleche']} Blech{'e' if z['bleche'] != 1 else ''}")
    if preis:
        teile.append(f"Richtpreis ca. {euro_text(round(preis, -1) if preis >= 100 else preis)} € (je Teil 1 Stk)")
    if wiederholt_:
        teile.append(f"{wiederholt_} Wiederholteil{'e' if wiederholt_ != 1 else ''}")
    if z["fehler"]:
        teile.append(f"{z['fehler']} nicht lesbar")
    return " · ".join(teile)
