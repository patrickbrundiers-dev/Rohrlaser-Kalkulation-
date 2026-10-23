"""Lizenz-Werkzeug (nur bei Patrick): Schlüssel erzeugen, Lizenzen ausstellen und prüfen, Sperrliste, Register.

Enthält keine Geheimnisse und gehört nicht ins Programm (nicht in rohrlaser.spec, nicht in die Update-Pakete).
Der private Schlüssel liegt mit Passwort geschützt im Lizenzordner (Vorgabe %USERPROFILE%\\Rohrlaser-Lizenz, anders
mit --ordner oder der Umgebungsvariable ROHRLASER_LIZENZ_ORDNER), nie im Repository. Zwei Kopien sichern
(USB-Stick im Tresor, Passwortmanager)!

Aufrufe (python werkzeuge/lizenz_werkzeug.py …):
  schluessel-erzeugen [--id K1]          Schlüsselpaar erzeugen, öffentlichen Schlüssel für lizenz_schluessel.py ausgeben
  erstellen --inhaber … --firma … [--art benutzer|test] [--bis JJJJ-MM-TT] [--rechner RL-…]… [--beliebig]
                                         Benutzer- (Vorgabe 6 Monate) oder Testlizenz (30 Tage, Aufdruck TESTVERSION)
  admin --rechner RL-… [--rechner RL-…]  unbefristete Admin-Lizenz (bis 3 Rechner)
  pruefen DATEI [--rechner RL-…]         Inhalt und Prüfergebnis einer Lizenzdatei
  sperren L-JJJJ-NNNN …                  neue Sperrliste Sperrliste.json (Stand + 1) für den Release update-dateien
  liste                                  alle ausgestellten Lizenzen nach Ablaufdatum
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


def privat_laden(ordner, sid):
    from cryptography.hazmat.primitives import serialization
    try:
        return serialization.load_pem_private_key(schluessel_pfad(ordner, sid).read_bytes(), passwort())
    except (ValueError, TypeError):
        raise SystemExit("Passwort falsch oder Schlüsseldatei beschädigt.") from None


def schluessel_erzeugen(ordner, sid):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    ordner = Path(ordner)
    pfad = schluessel_pfad(ordner, sid)
    if pfad.exists():
        raise SystemExit(f"{pfad} gibt es schon – ein vorhandener Schlüssel wird nie überschrieben.")
    ordner.mkdir(parents=True, exist_ok=True)
    privat = Ed25519PrivateKey.generate()
    pfad.write_bytes(privat.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                          serialization.BestAvailableEncryption(passwort(neu=True))))
    text = lizenz.oeffentlich_text(privat)
    (ordner / f"oeffentlich_{sid}.txt").write_text(text + "\n", encoding="ascii")
    print(f"Privater Schlüssel: {pfad}\n  -> jetzt zwei Kopien sichern (USB-Stick im Tresor, Passwortmanager).\n")
    print("Öffentlicher Schlüssel für programm/rohrlaser/lizenz_schluessel.py:\n")
    print(f'    "{sid}": "{text}",')
    return text


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


def ausstellen(ordner, art, inhaber, firma, bis, rechner, hinweis="", heute=None, ziel=None):
    ordner = Path(ordner)
    heute = heute or datetime.date.today()
    sid = aktueller_schluessel(ordner)
    privat = privat_laden(ordner, sid)
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


def sperren(ordner, ids):
    ordner = Path(ordner)
    sid = aktueller_schluessel(ordner)
    privat = privat_laden(ordner, sid)
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


def liste(ordner):
    zeilen = sorted(register_lesen(ordner), key=lambda z: z["gueltig_bis"])
    if not zeilen:
        print("Noch keine Lizenzen ausgestellt.")
    for z in zeilen:
        print(f"{z['lizenz_id']}  {z['art']:8}  bis {z['gueltig_bis']:11}  {z['inhaber']} / {z['firma']}  "
              f"Rechner {z['rechner']}" + (f"  GESPERRT {z['gesperrt']}" if z.get("gesperrt") else ""))
    return zeilen


def main(argv=None):
    ap = argparse.ArgumentParser(prog="lizenz_werkzeug", description=__doc__.split("\n")[0])
    ap.add_argument("--ordner", help="Lizenzordner mit privatem Schlüssel und Register")
    sub = ap.add_subparsers(dest="befehl", required=True)
    s = sub.add_parser("schluessel-erzeugen")
    s.add_argument("--id", default="K1")
    e = sub.add_parser("erstellen")
    e.add_argument("--art", choices=("benutzer", "test"), default="benutzer")
    e.add_argument("--inhaber", required=True)
    e.add_argument("--firma", default="")
    e.add_argument("--bis", help="gültig bis JJJJ-MM-TT (Vorgabe: Benutzer 6 Monate, Test 30 Tage)")
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
    a = ap.parse_args(argv)
    ordner = lizenzordner(a.ordner)
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
    return 0


if __name__ == "__main__":
    sys.exit(main())
