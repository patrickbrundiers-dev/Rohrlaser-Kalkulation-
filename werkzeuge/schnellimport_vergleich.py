"""Vergleich vollständiger CAD-Import gegen Schnellimport „Schneidweg & Zusatzarbeiten“ im ganzen Ablauf (Master-Prompt
Patrick 24.11.2026, Abschnitte 7, 8 und 12).

Je Modus läuft ein eigener Prozess mit eigener Datenbank und dem echten Fenster (Qt offscreen): STEP importieren
mit Messung, Prüfdialog (Vollimport, unverändert übernommen) bzw. Ergebnisübersicht (Schnellimport, unverändert
übernommen), Positionen speichern, Angebot neu laden und die Kalkulation (rechnen.kalkulation) rechnen. Gemessen
werden die Zeit vom Start des Imports bis zur fertigen Kalkulation, die Zeit je Schritt (tempo-Abschnitte), die
Messung selbst, CPU-Zeit, RAM-Spitze (Programm und Messprozess) und die Größe der gespeicherten 3D-Netze.

Verglichen werden ungerundet: alle Felder der neuen Positionen (ohne Datenbank-IDs und den Schlüssel step_import in
technik, den nur der Schnellimport schreibt), Schneidweg, Einstiche, Konturklassen, Zusatzarbeiten, Arbeitsgänge und
jede Zahl der Kalkulationszeilen und -summen (Maschinenzeit, Herstellkosten, Preis).

Aufruf:
    python werkzeuge/schnellimport_vergleich.py ERGEBNIS_ORDNER DATEI_ODER_ORDNER … [--bericht bericht.md]
"""
import argparse
import json
import os
import resource
import subprocess
import sys
import time
from pathlib import Path

HIER = Path(__file__).resolve().parent
PROGRAMM = HIER.parent / "programm"
ENDUNGEN = (".step", ".stp")
OHNE_FELDER = {"id", "angebot_id", "geaendert", "erstellt", "angelegt", "zeitpunkt"}


def _dateien(pfade):
    out = []
    for p in map(Path, pfade):
        out += sorted(q for q in p.rglob("*") if q.suffix.lower() in ENDUNGEN) if p.is_dir() else [p]
    return out


def _ohne_import(p):
    """Position ohne Datenbank-IDs und ohne technik.step_import (gibt es nur im Schnellimport)."""
    from rohrlaser import schnellimport
    q = {k: v for k, v in p.items() if k not in OHNE_FELDER and not k.startswith("_")}
    try:
        t = json.loads(q.get("technik") or "")
    except (TypeError, ValueError):
        t = None
    if isinstance(t, dict) and schnellimport.SCHLUESSEL in t:
        t.pop(schnellimport.SCHLUESSEL)
        q["technik"] = json.dumps(t, ensure_ascii=False, sort_keys=True)
    elif isinstance(t, dict):
        q["technik"] = json.dumps(t, ensure_ascii=False, sort_keys=True)
    try:        # Zeitpunkt der Merkmalsprüfung („am“) ist kein Messwert
        sm = json.loads(q.get("step_merkmale") or "")
    except (TypeError, ValueError):
        sm = None
    if isinstance(sm, dict):
        sm.pop("am", None)
        q["step_merkmale"] = json.dumps(sm, ensure_ascii=False, sort_keys=True)
    return q


def kind(modus, ziel, dateien):
    """Ein Import in einem Modus (eigener Prozess)."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    sys.path.insert(0, str(PROGRAMM))
    import tempfile
    from PySide6.QtWidgets import QApplication, QDialog, QMessageBox
    from rohrlaser import rechnen, schnellimport, tempo
    from rohrlaser.datenbank import Datenbank
    from rohrlaser.fenster import Hauptfenster
    from rohrlaser.schnellimport_dialog import UebersichtDialog
    from rohrlaser.step_dialog import StepPruefDialog

    _app = QApplication.instance() or QApplication([])  # noqa: F841 – Qt braucht die Anwendung
    abschnitte = []
    alt = tempo.abschnitt

    import contextlib

    @contextlib.contextmanager
    def merken(name, min_s=None):
        t0 = time.perf_counter()
        try:
            with alt(name, min_s):
                yield
        finally:
            abschnitte.append((name, time.perf_counter() - t0))
    tempo.abschnitt = merken

    def pruef_exec(self):
        self.accept()
        return QDialog.Accepted

    def ueber_exec(self):
        self._uebernehmen()
        return QDialog.Accepted
    StepPruefDialog.exec = pruef_exec
    UebersichtDialog.exec = ueber_exec
    QMessageBox.exec = lambda self: QMessageBox.Ok
    tmp = Path(tempfile.mkdtemp())
    db = Datenbank(tmp / "rohrlaser.db")
    for n, w in (("step_vorschau", "nein"), ("step_cache", "nein"), ("angebot_automatik", "nein"),
                 ("step_importmodus_fragen", "nein")):
        db.einstellung_setzen(n, w)
    f = Hauptfenster(db, tmp, stumm=True)
    aid = db.angebot_neu()
    seite = f.angebot_oeffnen(aid)
    f.stumm = False
    ru0, kind0 = resource.getrusage(resource.RUSAGE_SELF), resource.getrusage(resource.RUSAGE_CHILDREN)
    t0 = time.perf_counter()
    erg = seite.step_importieren([str(d) for d in dateien], modus=modus)
    seite.neu_laden()
    zeilen, summen = rechnen.kalkulation(seite.kopf, seite.positionen, seite.ergebnis, seite.k, seite.tabellen,
                                         seite.einst)
    gesamt = time.perf_counter() - t0
    ru1, kind1 = resource.getrusage(resource.RUSAGE_SELF), resource.getrusage(resource.RUSAGE_CHILDREN)
    netze = {pid: len(db.netz(pid) or b"") for pid in db.netz_ids(aid)}
    schritte = {}
    for name, d in abschnitte:
        schritte[name] = round(schritte.get(name, 0) + d, 3)
    out = dict(modus=modus, dateien=[str(d) for d in dateien], uebernommen=bool(erg),
               gesamt_s=round(gesamt, 3), messung_s=round(getattr(seite, "_step_mess_s", 0) or 0, 3),
               cpu_programm_s=round((ru1.ru_utime + ru1.ru_stime) - (ru0.ru_utime + ru0.ru_stime), 3),
               cpu_messung_s=round((kind1.ru_utime + kind1.ru_stime) - (kind0.ru_utime + kind0.ru_stime), 3),
               ram_programm_mb=round(ru1.ru_maxrss / 1024, 1), ram_messung_mb=round(kind1.ru_maxrss / 1024, 1),
               netze_n=len(netze), netze_kb=round(sum(netze.values()) / 1024, 1), schritte=schritte,
               positionen=[_ohne_import(p) for p in seite.positionen],
               importdaten=[schnellimport.lesen(p) for p in seite.positionen],
               zeilen=[{k: v for k, v in z.items() if not k.startswith("_") and k not in OHNE_FELDER}
                       for z in zeilen],
               summen={k: v for k, v in summen.items() if not k.startswith("_")} if isinstance(summen, dict) else summen)
    Path(ziel).write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return 0


def unterschiede(a, b, pfad=""):
    if isinstance(a, dict) and isinstance(b, dict):
        out = []
        for k in sorted(set(a) | set(b), key=str):
            out += unterschiede(a.get(k), b.get(k), f"{pfad}.{k}")
        return out
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return [(pfad, f"{len(a)} Einträge", f"{len(b)} Einträge")]
        out = []
        for i, (x, y) in enumerate(zip(a, b)):
            out += unterschiede(x, y, f"{pfad}[{i}]")
        return out
    return [] if a == b else [(pfad, a, b)]


def _starten(modus, ziel, dateien):
    t0 = time.perf_counter()
    p = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--kind", modus, str(ziel)]
                       + [str(d) for d in dateien], capture_output=True, text=True)
    if p.returncode:
        raise SystemExit(f"{modus}: Fehler\n{p.stdout[-3000:]}\n{p.stderr[-3000:]}")
    erg = json.loads(Path(ziel).read_text(encoding="utf-8"))
    erg["prozess_s"] = round(time.perf_counter() - t0, 3)
    return erg


def vergleich(ordner, dateien, bericht=None, je_datei=True):
    ordner = Path(ordner)
    ordner.mkdir(parents=True, exist_ok=True)
    gruppen = [[d] for d in dateien] if je_datei else [dateien]
    zeilen, alle = [], {}
    for g in gruppen:
        name = g[0].name if len(g) == 1 else f"{len(g)} Dateien"
        v = _starten("voll", ordner / f"{name}.voll.json", g)
        s = _starten("schnell", ordner / f"{name}.schnell.json", g)
        u = unterschiede(dict(p=v["positionen"], z=v["zeilen"], s=v["summen"]),
                         dict(p=s["positionen"], z=s["zeilen"], s=s["summen"]))
        alle[name] = dict(voll=v, schnell=s, unterschiede=u)
        zeilen.append((name, v, s, u))
        print(f"{name}: voll {v['gesamt_s']:.1f} s, schnell {s['gesamt_s']:.1f} s, Positionen {len(v['positionen'])}"
              f"/{len(s['positionen'])}, Unterschiede {len(u)}", flush=True)
    (ordner / "vergleich.json").write_text(json.dumps(alle, ensure_ascii=False, indent=1, default=str),
                                           encoding="utf-8")
    text = markdown(zeilen)
    if bericht:
        Path(bericht).write_text(text, encoding="utf-8")
    return alle, text


def _f(x, st=1):
    return f"{x:.{st}f}".replace(".", ",") if isinstance(x, (int, float)) else "–"


def markdown(zeilen):
    out = ["| Datei | Pos. | Import bis Kalkulation voll / schnell [s] | Faktor | Messung voll / schnell [s] | "
           "Prüfdialog bzw. Übersicht [s] | RAM Programm voll / schnell [MB] | RAM Messung [MB] | 3D-Netze [KB] | "
           "Werte gleich |", "|---|---:|---:|---:|---:|---:|---:|---:|---:|---|"]
    sv = ss = 0.0
    for name, v, s, u in zeilen:
        sv, ss = sv + v["gesamt_s"], ss + s["gesamt_s"]
        dlg_v = v["schritte"].get("STEP: Prüfdialog aufbauen", 0)
        dlg_s = s["schritte"].get("STEP: Prüfdialog aufbauen", 0) + s["schritte"].get(
            "STEP: Schnellübersicht vorbereiten", 0)
        out.append(f"| {name} | {len(s['positionen'])} | {_f(v['gesamt_s'])} / {_f(s['gesamt_s'])} | "
                   f"{_f(v['gesamt_s'] / s['gesamt_s'], 2) if s['gesamt_s'] else '–'} | {_f(v['messung_s'])} / "
                   f"{_f(s['messung_s'])} | {_f(dlg_v)} / {_f(dlg_s)} | {_f(v['ram_programm_mb'], 0)} / "
                   f"{_f(s['ram_programm_mb'], 0)} | {_f(v['ram_messung_mb'], 0)} / {_f(s['ram_messung_mb'], 0)} | "
                   f"{_f(v['netze_kb'], 0)} / {_f(s['netze_kb'], 0)} | "
                   f"{'ja' if not u else f'nein ({len(u)})'} |")
    out.append(f"| **Summe** | | **{_f(sv)} / {_f(ss)}** | **{_f(sv / ss, 2) if ss else '–'}** | | | | | | |")
    return "\n".join(out) + "\n"


def main(argv=None):
    rest = list(sys.argv[1:] if argv is None else argv)
    if rest[:1] == ["--kind"]:
        return kind(rest[1], rest[2], [Path(x) for x in rest[3:]])
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("ergebnis")
    ap.add_argument("pfade", nargs="+")
    ap.add_argument("--bericht")
    ap.add_argument("--zusammen", action="store_true", help="alle Dateien in einem Import (statt je Datei)")
    a = ap.parse_args(rest)
    alle, text = vergleich(a.ergebnis, _dateien(a.pfade), a.bericht, not a.zusammen)
    print(text)
    return 1 if any(x["unterschiede"] for x in alle.values()) else 0


if __name__ == "__main__":
    sys.exit(main())
