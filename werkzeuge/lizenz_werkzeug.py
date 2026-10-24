"""Lizenz-Werkzeug (nur bei Patrick): Schlüssel erzeugen, Lizenzen ausstellen und prüfen, Sperrliste, Register.

Enthält keine Geheimnisse und gehört nicht ins Programm (nicht in rohrlaser.spec, nicht in die Update-Pakete).
Der private Schlüssel liegt mit Passwort geschützt im Lizenzordner (Vorgabe %USERPROFILE%\\Rohrlaser-Lizenz, anders
mit --ordner oder der Umgebungsvariable ROHRLASER_LIZENZ_ORDNER), nie im Repository. Zwei Kopien sichern
(USB-Stick im Tresor, Passwortmanager)!

Aufrufe (python werkzeuge/lizenz_werkzeug.py …):
  schluessel-erzeugen [--id K1]          Schlüsselpaar erzeugen, öffentlichen Schlüssel für lizenz_schluessel.py ausgeben
  erstellen --inhaber … --firma … [--art benutzer|test] [--bis JJJJ-MM-TT] [--rechner RL-…]… [--beliebig]
                                         Benutzer- (Vorgabe 3 Monate) oder Testlizenz (30 Tage, Aufdruck TESTVERSION)
  admin --rechner RL-… [--rechner RL-…]  unbefristete Admin-Lizenz (bis 3 Rechner)
  pruefen DATEI [--rechner RL-…]         Inhalt und Prüfergebnis einer Lizenzdatei
  sperren L-JJJJ-NNNN …                  neue Sperrliste Sperrliste.json (Stand + 1) für den Release update-dateien
  liste                                  alle ausgestellten Lizenzen nach Ablaufdatum, mit Status
  faellig [--tage 30]                    Erinnerung: Lizenzen, die bald ablaufen oder abgelaufen sind (ohne Nachfolger)
  kunden                                 Übersicht je Firma: aktive Lizenzen, Rechner, nächster Ablauf, gesperrte
  verlaengern L-JJJJ-NNNN [--bis …]      neue Lizenz mit denselben Angaben im Anschluss (Vorgabe 3 Monate bzw. 30 Tage)
  sperrliste-hochladen                   Sperrliste.json in den Release update-dateien von Rohrlaser-Updates hochladen
                                         und anonym nachprüfen (GitHub-Token: ROHRLASER_GITHUB_TOKEN oder Abfrage;
                                         Fine-grained, nur Rohrlaser-Updates, Contents: Read and write)
  update-schluessel-erzeugen [--id U1]   Schlüsselpaar für die Signatur der Update-Dateiliste (eigener Schlüssel,
                                         nicht der Lizenzschlüssel): öffentlich für update_schluessel.py, privat als
                                         Wert für das GitHub-Secret UPDATE_SIGNATUR
  update-secret [--id U1]                Wert für UPDATE_SIGNATUR noch einmal ausgeben (aus privat_U1.pem)
  (ohne Befehl)                          Fenster mit allem oben (lizenz_werkzeug_fenster.py, Lizenz-Werkzeug.exe)
Passwort: wird abgefragt (oder Umgebungsvariable ROHRLASER_LIZENZ_PASSWORT, z. B. für Tests).
"""
import argparse
import csv
import datetime
import getpass
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "programm"))
from rohrlaser import lizenz  # noqa: E402

REGISTER = "lizenzen.csv"
SPALTEN = ("lizenz_id", "art", "inhaber", "firma", "rechner", "ausgestellt", "gueltig_bis", "gesperrt", "datei")
SPERRLISTE = "Sperrliste.json"
ERINNERUNG_TAGE = 30        # so viele Tage vor Ablauf erinnert das Werkzeug
NACHLAUF_TAGE = 60          # abgelaufene Lizenzen ohne Nachfolger so lange in der Erinnerung
UPDATE_REPO = "patrickbrundiers-dev/Rohrlaser-Updates"     # wie rohrlaser.update.UPDATE_REPO
SPERR_RELEASE = "update-dateien"


def lizenzordner(wert=None):
    return Path(wert or os.environ.get("ROHRLASER_LIZENZ_ORDNER") or Path.home() / "Rohrlaser-Lizenz")


def passwort(neu=False):
    pw = os.environ.get("ROHRLASER_LIZENZ_PASSWORT")
    if pw:
        return pw.encode("utf-8")
    pw = getpass.getpass("Passwort für den privaten Schlüssel: ")
    if neu and getpass.getpass("Passwort wiederholen: ") != pw:
        raise SystemExit("Die Passwörter stimmen nicht überein.")
    if neu and len(pw) < 8:
        raise SystemExit("Bitte ein Passwort mit mindestens 8 Zeichen.")
    return pw.encode("utf-8")


def schluessel_pfad(ordner, sid):
    return Path(ordner) / f"privat_{sid}.pem"


def aktueller_schluessel(ordner):
    """Neueste Schlüssel-ID im Lizenzordner (privat_K2.pem vor privat_K1.pem)."""
    ids = sorted((int(m.group(1)), m.group(0)[7:-4]) for p in Path(ordner).glob("privat_K*.pem")
                 if (m := re.fullmatch(r"privat_K(\d+)\.pem", p.name)))
    if not ids:
        raise SystemExit(f"Kein privater Schlüssel in {ordner}. Zuerst: schluessel-erzeugen")
    return ids[-1][1]


def privat_laden(ordner, sid, pw=None):
    from cryptography.hazmat.primitives import serialization
    try:
        return serialization.load_pem_private_key(schluessel_pfad(ordner, sid).read_bytes(),
                                                  pw or passwort())
    except (ValueError, TypeError):
        raise SystemExit("Passwort falsch oder Schlüsseldatei beschädigt.") from None


def schluessel_erzeugen(ordner, sid, pw=None, ausgabe=True):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    ordner = Path(ordner)
    pfad = schluessel_pfad(ordner, sid)
    if pfad.exists():
        raise SystemExit(f"{pfad} gibt es schon – ein vorhandener Schlüssel wird nie überschrieben.")
    ordner.mkdir(parents=True, exist_ok=True)
    privat = Ed25519PrivateKey.generate()
    pfad.write_bytes(privat.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                          serialization.BestAvailableEncryption(pw or passwort(neu=True))))
    text = lizenz.oeffentlich_text(privat)
    (ordner / f"oeffentlich_{sid}.txt").write_text(text + "\n", encoding="ascii")
    if not ausgabe:
        return text
    print(f"Privater Schlüssel: {pfad}\n  -> jetzt zwei Kopien sichern (USB-Stick im Tresor, Passwortmanager).\n")
    print("Öffentlicher Schlüssel für programm/rohrlaser/lizenz_schluessel.py:\n")
    print(f'    "{sid}": "{text}",')
    return text


def update_schluessel_erzeugen(ordner, sid="U1", pw=None):
    """Schlüsselpaar für die Signatur von Update.json (Audit H3). Der private Schlüssel kommt passwortgeschützt nach
    privat_<sid>.pem (sichern wie den Lizenzschlüssel!). Ergebnis: (öffentlicher Schlüssel für update_schluessel.py,
    Wert für das GitHub-Secret UPDATE_SIGNATUR). Der Secret-Wert wird nirgends gespeichert."""
    if not re.fullmatch(r"U\d+", sid):
        raise SystemExit("Update-Schlüssel heißen U1, U2 …")
    schluessel_erzeugen(ordner, sid, pw, ausgabe=False)
    return update_secret(ordner, sid, pw)


def update_secret(ordner, sid="U1", pw=None):
    """(öffentlicher Schlüssel, Base64 der 32 Byte des privaten Schlüssels für das Secret UPDATE_SIGNATUR)."""
    import base64
    from cryptography.hazmat.primitives import serialization
    privat = privat_laden(ordner, sid, pw)
    roh = privat.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
                               serialization.NoEncryption())
    return lizenz.oeffentlich_text(privat), base64.b64encode(roh).decode("ascii")


def register_lesen(ordner):
    p = Path(ordner) / REGISTER
    if not p.exists():
        return []
    with p.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f, delimiter=";"))


def register_schreiben(ordner, zeilen):
    p = Path(ordner) / REGISTER
    with p.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, SPALTEN, delimiter=";", extrasaction="ignore")
        w.writeheader()
        w.writerows(zeilen)


def naechste_id(zeilen, heute):
    praefix = f"L-{heute.year}-"
    n = max([int(z["lizenz_id"][len(praefix):]) for z in zeilen if z["lizenz_id"].startswith(praefix)] or [0])
    return f"{praefix}{n + 1:04d}"


def monate_spaeter(d, monate):
    """Gleicher Tag n Monate später, minus 1 Tag (1.11. + 6 Monate = 30.4.)."""
    j, m = divmod(d.month - 1 + monate, 12)
    ziel = datetime.date(d.year + j, m + 1, 1)
    tag = min(d.day, (datetime.date(ziel.year + (ziel.month == 12), ziel.month % 12 + 1, 1)
                      - datetime.timedelta(days=1)).day)
    return ziel.replace(day=tag) - datetime.timedelta(days=1)


def dateiname(inhalt):
    teile = [inhalt.get("firma") or "", inhalt.get("inhaber") or "", inhalt.get("gueltig_bis") or "unbefristet"]
    name = "_".join(re.sub(r"[^\w.-]+", "-", t).strip("-") for t in teile if t)
    return f"{inhalt['lizenz_id']}_{name}.lizenz"


def ausstellen(ordner, art, inhaber, firma, bis, rechner, hinweis="", heute=None, ziel=None, pw=None):
    ordner = Path(ordner)
    heute = heute or datetime.date.today()
    sid = aktueller_schluessel(ordner)
    privat = privat_laden(ordner, sid, pw)
    zeilen = register_lesen(ordner)
    inhalt = dict(lizenz_id=naechste_id(zeilen, heute), art=art, inhaber=inhaber or "", firma=firma or "",
                  ausgestellt=heute.isoformat(), gueltig_ab=heute.isoformat(),
                  gueltig_bis=bis.isoformat() if bis else None, rechner=[lizenz.id_normal(r) for r in rechner],
                  funktionen=["alle"], test=art == "test", schluessel_id=sid, hinweis=hinweis or "")
    daten = dict(format=lizenz.FORMAT, inhalt=inhalt, signatur=lizenz.signieren(inhalt, privat))
    lizenz.pruefen(daten, {sid: lizenz.oeffentlich_text(privat)})      # nur gültige Lizenzen verlassen das Werkzeug
    ziel = Path(ziel) if ziel else ordner / "Lizenzen"
    ziel.mkdir(parents=True, exist_ok=True)
    datei = ziel / dateiname(inhalt)
    datei.write_text(json.dumps(daten, indent=1, ensure_ascii=False), encoding="utf-8")
    zeilen.append(dict(lizenz_id=inhalt["lizenz_id"], art=art, inhaber=inhalt["inhaber"], firma=inhalt["firma"],
                       rechner=" ".join(inhalt["rechner"]) or "beliebig", ausgestellt=inhalt["ausgestellt"],
                       gueltig_bis=inhalt["gueltig_bis"] or "unbefristet", gesperrt="", datei=datei.name))
    register_schreiben(ordner, zeilen)
    print(f"Lizenz {inhalt['lizenz_id']} ({art}) für {inhalt['inhaber'] or inhalt['firma']}, gültig bis "
          f"{inhalt['gueltig_bis'] or 'unbefristet'}, Rechner {' '.join(inhalt['rechner']) or 'beliebig'}:\n  {datei}")
    return datei


def schluessel_bekannt(ordner):
    """Öffentliche Schlüssel des Programms und die im Lizenzordner (solange lizenz_schluessel.py noch leer ist)."""
    s = dict(lizenz.standard_schluessel())
    for p in Path(ordner).glob("oeffentlich_K*.txt"):
        s.setdefault(p.stem[len("oeffentlich_"):], p.read_text(encoding="ascii").strip())
    return s


def pruefen(datei, rechner=None, ordner=None):
    schluessel = schluessel_bekannt(ordner) if ordner else None
    try:
        daten = lizenz.lesen(Path(datei))
        print(json.dumps(daten.get("inhalt"), indent=1, ensure_ascii=False))
        lizenz.pruefen(daten, schluessel)
    except lizenz.LizenzFehler as e:
        print(f"UNGÜLTIG: {e}")
        return 1
    z = lizenz.ermitteln(daten, rechner=rechner or (daten["inhalt"]["rechner"] or [""])[0],
                         schluessel=schluessel, durchsetzung=True)
    print(f"Signatur gültig. Zustand heute: {z.stufe}" + (f" – {z.grund or z.hinweis}" if (z.grund or z.hinweis)
                                                          else ""))
    return 0


def sperren(ordner, ids, pw=None):
    ordner = Path(ordner)
    sid = aktueller_schluessel(ordner)
    privat = privat_laden(ordner, sid, pw)
    p = ordner / SPERRLISTE
    alt = json.loads(p.read_text(encoding="utf-8")) if p.exists() else dict(stand=0, gesperrt=[])
    daten = lizenz.sperrliste_signieren(alt["stand"] + 1, list(alt["gesperrt"]) + list(ids), privat, sid)
    p.write_text(json.dumps(daten, indent=1, ensure_ascii=False), encoding="utf-8")
    zeilen = register_lesen(ordner)
    for z in zeilen:
        if z["lizenz_id"] in daten["gesperrt"] and not z.get("gesperrt"):
            z["gesperrt"] = datetime.date.today().isoformat()
    register_schreiben(ordner, zeilen)
    print(f"Sperrliste Stand {daten['stand']}: {', '.join(daten['gesperrt'])}\n  {p}\n"
          "Jetzt als Sperrliste.json in den Release update-dateien von Rohrlaser-Updates hochladen.")
    return p


def _bis(z):
    try:
        return datetime.date.fromisoformat(z.get("gueltig_bis") or "")
    except ValueError:
        return None         # unbefristet (Admin)


def status(z, heute=None):
    """(Status, Tage bis Ablauf bzw. seit Ablauf) einer Registerzeile: gesperrt, unbefristet, abgelaufen,
    laeuft_ab (höchstens ERINNERUNG_TAGE), gueltig."""
    heute = heute or datetime.date.today()
    if z.get("gesperrt"):
        return "gesperrt", None
    bis = _bis(z)
    if bis is None:
        return "unbefristet", None
    tage = (bis - heute).days
    if tage < 0:
        return "abgelaufen", -tage
    return ("laeuft_ab" if tage <= ERINNERUNG_TAGE else "gueltig"), tage


STATUS_TEXT = dict(gesperrt="gesperrt", unbefristet="unbefristet", abgelaufen="abgelaufen", laeuft_ab="läuft ab",
                   gueltig="gültig")


def status_text(z, heute=None):
    st, tage = status(z, heute)
    if st == "abgelaufen":
        return f"abgelaufen seit {tage} Tag{'en' if tage != 1 else ''}"
    if st == "laeuft_ab":
        return "läuft heute ab" if tage == 0 else f"läuft in {tage} Tag{'en' if tage != 1 else ''} ab"
    return STATUS_TEXT[st]


def _kunde(z):
    return (z.get("firma") or "").strip() or (z.get("inhaber") or "").strip() or "(ohne Namen)"


def hat_nachfolger(z, zeilen):
    """Gibt es für denselben Inhaber und dieselbe Firma (gleiche Art) eine nicht gesperrte Lizenz, die länger gilt?"""
    bis = _bis(z)
    for andere in zeilen:
        if andere is z or andere.get("gesperrt") or andere.get("art") != z.get("art"):
            continue
        if (andere.get("inhaber"), andere.get("firma")) != (z.get("inhaber"), z.get("firma")):
            continue
        if bis is not None and (_bis(andere) is None or _bis(andere) > bis):
            return True
    return False


def faellig(zeilen, heute=None, tage=ERINNERUNG_TAGE):
    """Erinnerung: [(Zeile, Status, Tage)] für Lizenzen, die in höchstens `tage` Tagen ablaufen oder seit höchstens
    NACHLAUF_TAGE abgelaufen sind – ohne gesperrte, unbefristete und solche mit Nachfolger. Dringendste zuerst."""
    heute = heute or datetime.date.today()
    treffer = []
    for z in zeilen:
        bis = _bis(z)
        if z.get("gesperrt") or bis is None or hat_nachfolger(z, zeilen):
            continue
        rest = (bis - heute).days
        if -NACHLAUF_TAGE <= rest <= tage:
            treffer.append((z, "abgelaufen" if rest < 0 else "laeuft_ab", abs(rest)))
    return sorted(treffer, key=lambda t: t[0]["gueltig_bis"])


def kunden(zeilen, heute=None):
    """Übersicht je Kunde (Firma, sonst Inhaber): aktive Lizenzen, Rechner, nächster Ablauf, gesperrte, alle."""
    heute = heute or datetime.date.today()
    uebersicht = {}
    for z in zeilen:
        k = uebersicht.setdefault(_kunde(z), dict(kunde=_kunde(z), aktiv=0, rechner=set(), naechster_ablauf="",
                                                  gesperrt=0, gesamt=0))
        k["gesamt"] += 1
        st, _ = status(z, heute)
        if st == "gesperrt":
            k["gesperrt"] += 1
            continue
        if st in ("abgelaufen",):
            continue
        k["aktiv"] += 1
        k["rechner"].update(r for r in (z.get("rechner") or "").split() if r != "beliebig")
        bis = z.get("gueltig_bis") or ""
        if st != "unbefristet" and (not k["naechster_ablauf"] or bis < k["naechster_ablauf"]):
            k["naechster_ablauf"] = bis
    for k in uebersicht.values():
        k["rechner"] = len(k["rechner"])
    return sorted(uebersicht.values(), key=lambda k: k["kunde"].casefold())


def verlaengerung_bis(z, heute=None):
    """Vorgabe für die Verlängerung: im Anschluss an das alte Ablaufdatum (bzw. ab heute, wenn schon abgelaufen),
    Benutzer STANDARD_MONATE, Test TEST_TAGE."""
    heute = heute or datetime.date.today()
    start = max(heute, (_bis(z) or heute) + datetime.timedelta(days=1))
    if z.get("art") == "test":
        return start + datetime.timedelta(days=lizenz.TEST_TAGE - 1)
    return monate_spaeter(start, lizenz.STANDARD_MONATE)


def verlaengern(ordner, lizenz_id, bis=None, pw=None, heute=None, ziel=None):
    """Neue Lizenz mit Art, Inhaber, Firma und Rechnern der Lizenz lizenz_id (Hinweis „Verlängerung von …“). Die alte
    bleibt bis zu ihrem Ablauf gültig. Ergebnis: Pfad der neuen Lizenzdatei."""
    zeilen = register_lesen(ordner)
    z = next((z for z in zeilen if z["lizenz_id"] == lizenz_id), None)
    if z is None:
        raise SystemExit(f"Lizenz {lizenz_id} steht nicht im Register.")
    if z.get("gesperrt"):
        raise SystemExit(f"Lizenz {lizenz_id} ist gesperrt und wird nicht verlängert.")
    if z["art"] == "admin":
        raise SystemExit("Admin-Lizenzen sind unbefristet, eine Verlängerung ist nicht nötig.")
    rechner = [r for r in (z.get("rechner") or "").split() if r != "beliebig"]
    return ausstellen(ordner, z["art"], z["inhaber"], z["firma"], bis or verlaengerung_bis(z, heute), rechner,
                      f"Verlängerung von {lizenz_id}", heute=heute, ziel=ziel, pw=pw)


def _github(methode, url, token, daten=None, art="application/json", oeffnen=None):
    """Ein Aufruf der GitHub-API (nur https). Ergebnis: (Status, Bytes). oeffnen: Ersatz für urlopen (Tests)."""
    import urllib.error
    import urllib.request
    if not url.startswith("https://"):
        raise SystemExit("Nur https.")
    kopf = {"Accept": "application/vnd.github+json", "User-Agent": "Rohrlaser-Lizenz-Werkzeug",
            "X-GitHub-Api-Version": "2022-11-28"}
    if token:
        kopf["Authorization"] = f"Bearer {token}"
    if daten is not None:
        kopf["Content-Type"] = art
    anfrage = urllib.request.Request(url, data=daten, headers=kopf, method=methode)
    try:
        with (oeffnen or urllib.request.urlopen)(anfrage, timeout=30) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read() if hasattr(e, "read") else b""
    except OSError as e:
        raise SystemExit(f"GitHub nicht erreichbar: {e}") from None


def sperrliste_hochladen(ordner, token, repo=UPDATE_REPO, tag=SPERR_RELEASE, oeffnen=None, schluessel=None):
    """Sperrliste.json des Lizenzordners in den Release `tag` von `repo` hochladen (vorhandene ersetzen) und danach
    ohne Anmeldung laden und prüfen, wie es die Programme tun. Ergebnis: Stand der veröffentlichten Liste. Der Token
    wird nirgends gespeichert und nie ausgegeben."""
    p = Path(ordner) / SPERRLISTE
    if not p.exists():
        raise SystemExit("Noch keine Sperrliste – zuerst Lizenzen sperren.")
    daten = p.read_bytes()
    schluessel = schluessel_bekannt(ordner) if schluessel is None else schluessel
    lokal = lizenz.sperrliste_pruefen(daten.decode("utf-8", "replace"), schluessel)
    if lokal is None:
        raise SystemExit("Die Sperrliste im Lizenzordner ist nicht gültig signiert – nichts hochgeladen.")
    if not token:
        raise SystemExit("Kein GitHub-Token angegeben.")
    api = f"https://api.github.com/repos/{repo}"
    st, antwort = _github("GET", f"{api}/releases/tags/{tag}", token, oeffnen=oeffnen)
    if st == 401:
        raise SystemExit("GitHub lehnt den Token ab (abgelaufen oder falsch).")
    if st != 200:
        raise SystemExit(f"Release {tag} in {repo} nicht gefunden (HTTP {st}).")
    release = json.loads(antwort)
    for asset in release.get("assets") or []:
        if asset.get("name") == SPERRLISTE:
            st, _ = _github("DELETE", f"{api}/releases/assets/{asset['id']}", token, oeffnen=oeffnen)
            if st not in (204, 404):
                raise SystemExit(f"Alte Sperrliste lässt sich nicht ersetzen (HTTP {st}). Token-Rechte prüfen "
                                 "(Contents: Read and write für Rohrlaser-Updates).")
    hoch = f"https://uploads.github.com/repos/{repo}/releases/{release['id']}/assets?name={SPERRLISTE}"
    st, _ = _github("POST", hoch, token, daten, art="application/json", oeffnen=oeffnen)
    if st not in (200, 201):
        raise SystemExit(f"Hochladen fehlgeschlagen (HTTP {st}). Token-Rechte prüfen.")
    # wie das Programm: ohne Anmeldung laden und prüfen
    st, online = _github("GET", f"https://github.com/{repo}/releases/download/{tag}/{SPERRLISTE}", None,
                         oeffnen=oeffnen)
    geprueft = lizenz.sperrliste_pruefen(online.decode("utf-8", "replace"), schluessel) if st == 200 else None
    if geprueft is None or geprueft["stand"] != lokal["stand"]:
        raise SystemExit(f"Hochgeladen, aber die Prüfung ohne Anmeldung passt nicht (HTTP {st}). In ein paar Minuten "
                         "noch einmal hochladen.")
    print(f"Sperrliste Stand {lokal['stand']} veröffentlicht ({', '.join(lokal['gesperrt']) or 'leer'}). "
          "Die Programme übernehmen sie beim nächsten Update-Check.")
    return lokal["stand"]


def liste(ordner, heute=None):
    zeilen = sorted(register_lesen(ordner), key=lambda z: z["gueltig_bis"])
    if not zeilen:
        print("Noch keine Lizenzen ausgestellt.")
    for z in zeilen:
        print(f"{z['lizenz_id']}  {z['art']:8}  bis {z['gueltig_bis']:11}  {z['inhaber']} / {z['firma']}  "
              f"Rechner {z['rechner']}  "
              + (f"GESPERRT {z['gesperrt']}" if z.get("gesperrt") else status_text(z, heute)))
    return zeilen


def main(argv=None):
    ap = argparse.ArgumentParser(prog="lizenz_werkzeug", description=__doc__.split("\n")[0])
    ap.add_argument("--ordner", help="Lizenzordner mit privatem Schlüssel und Register")
    sub = ap.add_subparsers(dest="befehl")
    s = sub.add_parser("schluessel-erzeugen")
    s.add_argument("--id", default="K1")
    e = sub.add_parser("erstellen")
    e.add_argument("--art", choices=("benutzer", "test"), default="benutzer")
    e.add_argument("--inhaber", required=True)
    e.add_argument("--firma", default="")
    e.add_argument("--bis", help="gültig bis JJJJ-MM-TT (Vorgabe: Benutzer 3 Monate, Test 30 Tage)")
    e.add_argument("--rechner", action="append", default=[])
    e.add_argument("--beliebig", action="store_true", help="ohne Rechnerbindung (portabel an mehreren PCs)")
    e.add_argument("--hinweis", default="")
    e.add_argument("--ziel")
    a_ = sub.add_parser("admin")
    a_.add_argument("--rechner", action="append", required=True)
    a_.add_argument("--inhaber", default="Patrick")
    a_.add_argument("--ziel")
    p = sub.add_parser("pruefen")
    p.add_argument("datei")
    p.add_argument("--rechner")
    sp = sub.add_parser("sperren")
    sp.add_argument("ids", nargs="+")
    sub.add_parser("liste")
    f_ = sub.add_parser("faellig")
    f_.add_argument("--tage", type=int, default=ERINNERUNG_TAGE)
    sub.add_parser("kunden")
    v = sub.add_parser("verlaengern")
    v.add_argument("lizenz_id")
    v.add_argument("--bis", help="gültig bis JJJJ-MM-TT (Vorgabe: im Anschluss 3 Monate bzw. 30 Tage)")
    v.add_argument("--ziel")
    sub.add_parser("sperrliste-hochladen")
    for name in ("update-schluessel-erzeugen", "update-secret"):
        u = sub.add_parser(name)
        u.add_argument("--id", default="U1")
    a = ap.parse_args(argv)
    ordner = lizenzordner(a.ordner)
    if a.befehl is None:            # ohne Befehl (Doppelklick auf Lizenz-Werkzeug.exe): Fenster
        from lizenz_werkzeug_fenster import starten
        return starten(ordner)
    if a.befehl == "schluessel-erzeugen":
        schluessel_erzeugen(ordner, a.id)
    elif a.befehl == "erstellen":
        if not a.rechner and not a.beliebig:
            raise SystemExit("Bitte --rechner RL-… angeben (oder --beliebig für portable Nutzung an mehreren PCs).")
        heute = datetime.date.today()
        bis = (datetime.date.fromisoformat(a.bis) if a.bis else
               monate_spaeter(heute, lizenz.STANDARD_MONATE) if a.art == "benutzer" else
               heute + datetime.timedelta(days=lizenz.TEST_TAGE - 1))
        ausstellen(ordner, a.art, a.inhaber, a.firma, bis, [] if a.beliebig else a.rechner, a.hinweis, ziel=a.ziel)
    elif a.befehl == "admin":
        if len(a.rechner) > lizenz.ADMIN_RECHNER_MAX:
            raise SystemExit(f"Höchstens {lizenz.ADMIN_RECHNER_MAX} Rechner.")
        ausstellen(ordner, "admin", a.inhaber, "", None, a.rechner, ziel=a.ziel)
    elif a.befehl == "pruefen":
        return pruefen(a.datei, a.rechner, ordner)
    elif a.befehl == "sperren":
        sperren(ordner, a.ids)
    elif a.befehl == "liste":
        liste(ordner)
    elif a.befehl == "faellig":
        treffer = faellig(register_lesen(ordner), tage=a.tage)
        if not treffer:
            print(f"Keine Lizenz läuft in den nächsten {a.tage} Tagen ab.")
        for z, _, _ in treffer:
            print(f"{z['lizenz_id']}  {_kunde(z)} ({z['inhaber']})  bis {z['gueltig_bis']}  {status_text(z)}")
    elif a.befehl == "kunden":
        for k in kunden(register_lesen(ordner)):
            print(f"{k['kunde']}: {k['aktiv']} aktiv, {k['rechner']} Rechner, nächster Ablauf "
                  f"{k['naechster_ablauf'] or '–'}, {k['gesperrt']} gesperrt, {k['gesamt']} insgesamt")
    elif a.befehl == "verlaengern":
        verlaengern(ordner, a.lizenz_id, datetime.date.fromisoformat(a.bis) if a.bis else None, ziel=a.ziel)
    elif a.befehl == "sperrliste-hochladen":
        token = os.environ.get("ROHRLASER_GITHUB_TOKEN") or getpass.getpass("GitHub-Token (Rohrlaser-Updates): ")
        sperrliste_hochladen(ordner, token.strip())
    elif a.befehl in ("update-schluessel-erzeugen", "update-secret"):
        if a.befehl == "update-schluessel-erzeugen":
            oeffentlich, geheim = update_schluessel_erzeugen(ordner, a.id, passwort(neu=True))
        else:
            oeffentlich, geheim = update_secret(ordner, a.id)
        print(f"Öffentlicher Schlüssel für programm/rohrlaser/update_schluessel.py:\n\n    \"{a.id}\": \"{oeffentlich}\",\n")
        print("Wert für das GitHub-Secret UPDATE_SIGNATUR (Settings → Secrets and variables → Actions), GEHEIM, nicht "
              f"in den Chat oder eine Datei:\n\n    {geheim}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
