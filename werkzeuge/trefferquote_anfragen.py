"""Trefferquote des Anfrage-Lesers auf echten Mails, nur lokal (KI-001, Patrick 12.11.2026: keine Kundendaten
teilen). Läuft auf dem eigenen Rechner über einen Ordner mit .msg/.eml-Dateien (z. B. den Anfrage-Ordner) und
schickt nichts weg: kein Netz, kein Sprachmodell, nichts wird hochgeladen oder eingecheckt.

Schritt 1 – lesen:
    python werkzeuge/trefferquote_anfragen.py lesen  ORDNER  pruefung.csv  [--datenbank PFAD]
  schreibt je Mail und Wert eine Zeile (Datei, Feld, Wert, Fundstelle, Sicherheit) und eine leere Spalte „richtig“.
  In Excel je Zeile j (richtig) oder n (falsch) eintragen; fehlt ein Wert, den die Mail nennt, eine Zeile mit
  Feld, leerem Wert und „fehlt“ in „richtig“ dazuschreiben.
Schritt 2 – auswerten:
    python werkzeuge/trefferquote_anfragen.py auswerten  pruefung.csv
  zeigt Trefferquote gesamt, je Feld und je Sicherheit (nur Zahlen, keine Inhalte).

Die CSV-Datei enthält Auszüge der Mails: sie bleibt auf dem Rechner und gehört nicht in das Repository.
"""
import argparse
import csv
import sys
from pathlib import Path

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent / "programm"))

SPALTEN = ("datei", "feld", "wert", "fundstelle", "sicherheit", "richtig")


def lesen(ordner, ziel, datenbank=None):
    from rohrlaser import mail, mail_fundstellen as mf
    from rohrlaser.stammdaten import beispieldaten
    b = beispieldaten()             # ohne Datenbank: mitgelieferte Werkstoffe und Zusatzarbeiten, keine Kunden
    ws, kunden = b["werkstoffe"], ()
    kat = [z["name"] for z in b.get("zusatzarbeiten") or () if z.get("name")]
    if datenbank:
        import shutil
        import tempfile
        from rohrlaser.datenbank import Datenbank
        kopie = Path(tempfile.mkdtemp()) / "kopie.db"      # nur eine Kopie öffnen: die echte Datei bleibt unberührt
        shutil.copy2(datenbank, kopie)
        db = Datenbank(kopie)
        ws, kunden = db.zeilen("werkstoffe"), db.zeilen("kunden")
        kat = [z["name"] for z in db.zeilen("zusatzarbeiten") if z.get("name")]
    dateien = sorted(p for p in Path(ordner).rglob("*") if p.suffix.lower() in (".msg", ".eml"))
    n = 0
    with open(ziel, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(SPALTEN)
        for p in dateien:
            m = mail.lesen(p)
            if m is None:
                continue
            for x in mf.zusammen([("Mail", m.volltext())], werkstoffe=ws, katalog=kat, kunden=kunden):
                w.writerow((p.name, x["feld"], x["wert"], x["fundstelle"], x["sicherheit"], ""))
                n += 1
    print(f"{len(dateien)} Mails gelesen, {n} Werte in {ziel}. Spalte „richtig“ mit j/n ausfüllen, dann auswerten.")


def auswerten(quelle):
    je_feld, je_sicher = {}, {}
    richtig = falsch = fehlt = offen = 0
    with open(quelle, newline="", encoding="utf-8-sig") as f:
        for z in csv.DictReader(f, delimiter=";"):
            r = (z.get("richtig") or "").strip().lower()
            feld, sicher = z.get("feld") or "?", z.get("sicherheit") or "?"
            if r in ("j", "ja", "1", "x"):
                k = "richtig"
                richtig += 1
            elif r in ("n", "nein", "0"):
                k = "falsch"
                falsch += 1
            elif r == "fehlt":
                k = "fehlt"
                fehlt += 1
            else:
                offen += 1
                continue
            je_feld.setdefault(feld, dict(richtig=0, falsch=0, fehlt=0))[k] += 1
            if k != "fehlt":
                je_sicher.setdefault(sicher, dict(richtig=0, falsch=0, fehlt=0))[k] += 1
    alle = richtig + falsch + fehlt

    def q(d):
        n = d["richtig"] + d["falsch"] + d["fehlt"]
        return f"{d['richtig']} von {n} = {100 * d['richtig'] / n:.1f} %" if n else "–"
    print(f"Trefferquote gesamt: {q(dict(richtig=richtig, falsch=falsch, fehlt=fehlt))} "
          f"(falsch {falsch}, nicht gefunden {fehlt}, ohne Bewertung {offen})" if alle else "Noch nichts bewertet.")
    for name, d in sorted(je_feld.items()):
        print(f"  Feld {name}: {q(d)}")
    for name, d in sorted(je_sicher.items()):
        print(f"  Sicherheit {name}: {q(d)}")


def main(argv=None):
    a = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = a.add_subparsers(dest="schritt", required=True)
    le = sub.add_parser("lesen")
    le.add_argument("ordner")
    le.add_argument("ziel")
    le.add_argument("--datenbank")
    au = sub.add_parser("auswerten")
    au.add_argument("quelle")
    n = a.parse_args(argv)
    if n.schritt == "lesen":
        lesen(n.ordner, n.ziel, n.datenbank)
    else:
        auswerten(n.quelle)


if __name__ == "__main__":
    main()
