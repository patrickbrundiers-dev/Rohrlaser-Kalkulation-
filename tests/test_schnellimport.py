"""Schnellimport STEP (Patrick 24.11.2026, Master-Prompt „Schnellimport und Schneidweg-Kalkulation ohne editierbare
3D-Geometrie“): Importmodus A (vollständig) und B (Schneidweg & Zusatzarbeiten) im ganzen Ablauf mit Datenbank und
Fenster.

- Logik (schnellimport.py): Modus aus der Einstellung, Messargument, Merkmale, 4 Genauigkeitsstufen, Status,
  Speichern/Lesen der Importdaten in technik, „3D nachgeladen“
- Messung: --netze-linien liefert dieselben Messwerte (bitgleich), das Netz hat nur die Linienzüge
- Programm: dieselben Dateien voll und schnell importiert ergeben dieselben Positionen (alle Felder ungerundet) und
  dieselbe Kalkulation; schnell ohne gespeichertes Dreiecksnetz, mit Importmodus/Version/Status in der Position
- Übersicht statt Prüfdialog (Haken abwählen übernimmt das Teil nicht), „Vollständig importieren“ aus der Übersicht,
  Moduswahl mit „als Vorgabe merken“
- 3D nachladen: Netz kommt, Werte und Kalkulation bleiben gleich
- fehlerhafte Datei: Meldung, keine Position, kein Absturz

Aufruf: python tests/test_schnellimport.py
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER.parent / "programm" / "step_messung"))
sys.path.insert(0, str(HIER.parent / "werkzeuge"))
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox  # noqa: E402
from rohrlaser import rechnen, schnellimport as si  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402
from rohrlaser.schnellimport_dialog import ModusDialog, UebersichtDialog  # noqa: E402
from rohrlaser.step_dialog import StepPruefDialog  # noqa: E402
import schnellimport_vergleich as sv  # noqa: E402

fehler = 0


def fall(name):
    def deko(fn):
        global fehler
        try:
            fn()
            print(f"OK     {name}")
        except AssertionError as e:
            import traceback
            fehler += 1
            print(f"FEHLER {name}: {e} ({traceback.extract_tb(e.__traceback__)[-1].line})")
        return fn
    return deko


app = QApplication.instance() or QApplication([])
TMP = Path(tempfile.mkdtemp())
DATEIEN = [HIER / "step" / "T03_QR40x3_L2150_Bohrung.step",
           HIER / "step_regression" / "R06_RE40x30x3_L920_Langloecher.step",
           HIER / "step_bleche" / "B02_Blech_400x200x4_Bohrungen.step"]


class _Db:
    def __init__(self, **w):
        self.w = w

    def einstellung(self, n):
        return self.w.get(n)


@fall("Logik: Modus aus Einstellung, Frage, Messargument, Stufen, Merken/Lesen/Nachladen")
def _logik():
    an = {"funktion_schnellimport": "ja"}
    assert si.vorgabe(_Db(**an)) == si.MODUS_VOLL
    assert si.vorgabe(_Db(step_importmodus="Schnellkalkulation", **an)) == si.MODUS_SCHNELL
    assert si.fragen(_Db(**an)) and not si.fragen(_Db(step_importmodus_fragen="nein", **an))
    # Funktion aus (Vorgabe, Patrick 24.11.2026): immer vollständig, keine Frage
    assert not si.an(_Db()) and not si.an(None) and not si.fragen(_Db())
    assert si.vorgabe(_Db(step_importmodus="Schnellkalkulation")) == si.MODUS_VOLL
    assert si.mess_argumente(si.MODUS_SCHNELL) == ["--netze-linien"] and si.mess_argumente(si.MODUS_VOLL) == []
    assert si.nur_linien({"nur_linien": True, "l": {}}) and not si.nur_linien({"p": [1], "t": {}})
    assert len(si.STUFEN) == 4 and si.stufe_text(9) == si.STUFEN[3]
    m = dict(profilform="Quadratrohr", schneidweg=812.5, konturen=3, laenge=1000.0, wandstaerke=3.0, koerper=2,
             konturen_liste=json.dumps([{"art": "Bohrung"}, {"art": "Bohrung"}, {"art": "Langloch"}]), datei="x.step")
    mm = si.merkmale(m)
    assert mm["einstiche"] == mm["anfahrten"] == 3 and mm["schneidweg"] == 812.5, mm
    assert sum(mm["bearbeitungen"].values()) == 3, mm
    stufe, gruende = si.genauigkeit(dict(m, fehler="nicht messbar"))
    assert stufe == 3, (stufe, gruende)
    p = si.merken({"technik": json.dumps({"a": 1})}, m, "0.9.999", jetzt=__import__("datetime").datetime(2026, 11, 24, 18, 0))
    info = si.lesen(p)
    assert info["modus"] == si.MODUS_SCHNELL and info["version"] == "0.9.999" and info["koerper"] == 2, info
    assert info["name"] == "x.step" and info["status"] in (si.VOLLSTAENDIG, si.TEILWEISE, si.ERGAENZEN), info
    assert json.loads(p["technik"])["a"] == 1 and si.ist_schnell(p)
    q = si.nachgeladen(dict(p))
    assert not si.ist_schnell(q) and si.lesen(q)["modus"] == si.NACHGELADEN, si.lesen(q)
    assert si.koerper_finden([dict(koerper=1, datei="x.step"), dict(koerper=2, datei="x.step")], info) == 1
    assert si.gleiche_messung(m, dict(m)) == [] and si.gleiche_messung(m, dict(m, schneidweg=1)) == ["schneidweg"]


@fall("Messung: --netze-linien bitgleich, Netz nur Linienzüge (Rohr), Blech mit Dreiecken (Kantteil-Gegenprobe)")
def _messung():
    import step_benchmark as sb
    voll, schnell = TMP / "m_voll", TMP / "m_schnell"
    for d in DATEIEN:
        for ziel, s in ((voll, False), (schnell, True)):
            e = sb.lauf(HIER.parent, ziel, [d], schnell=s)
            assert e and all(w["rc"] == 0 for w in e.values()), e
    for d in DATEIEN:
        a = json.loads((voll / f"{d.name}.json").read_text(encoding="utf-8"))
        b = json.loads((schnell / f"{d.name}.json").read_text(encoding="utf-8"))
        u = sb.unterschiede(a, b)
        assert not u, (d.name, u[:5])
    for name, linien in (("T03", True), ("R06", True), ("B02", False)):
        for ziel, nur in ((schnell, linien), (voll, False)):
            netze = [json.loads(n.read_text(encoding="utf-8")) for d in ziel.glob(f"{name}*_netze")
                     for n in d.glob("*.json")]
            assert netze, (name, ziel)
            for n in netze:
                assert bool(n.get("nur_linien")) == nur and bool(n.get("t")) != nur, (name, list(n))
                assert n.get("l") or name == "B02", (name, list(n))     # Blech: Kantteil-Gegenprobe braucht Dreiecke


def _fenster(db, tmp):
    for n, w in (("step_vorschau", "nein"), ("angebot_automatik", "nein")):
        db.einstellung_setzen(n, w)
    f = Hauptfenster(db, tmp, stumm=True)
    return f


db = Datenbank(TMP / "rohrlaser.db")
fenster = _fenster(db, TMP)
db.einstellung_setzen("funktion_schnellimport", "ja")      # Vorgabe aus (Patrick 24.11.2026)
db.einstellung_setzen("step_importmodus_fragen", "nein")
GESEHEN = {"pruef": 0, "ueber": 0}
UEBER_AKTION = {"abwaehlen": None, "voll": False}


def _pruef_exec(self):
    GESEHEN["pruef"] += 1
    self.accept()
    return QDialog.Accepted


def _ueber_exec(self):
    GESEHEN["ueber"] += 1
    if UEBER_AKTION["voll"]:
        UEBER_AKTION["voll"] = False
        self._voll()
        return QDialog.Accepted
    if UEBER_AKTION["abwaehlen"] is not None:
        from PySide6.QtCore import Qt
        self.tabelle.item(UEBER_AKTION["abwaehlen"], 0).setCheckState(Qt.Unchecked)
    self._uebernehmen()
    return QDialog.Accepted


StepPruefDialog.exec = _pruef_exec
UebersichtDialog.exec = _ueber_exec
QMessageBox.exec = lambda self: QMessageBox.Ok


def _import(modus, dateien=DATEIEN):
    aid = db.angebot_neu()
    seite = fenster.angebot_oeffnen(aid)
    fenster.stumm = False
    try:
        seite.step_importieren([str(d) for d in dateien], modus=modus)
    finally:
        fenster.stumm = True
    seite.neu_laden()
    return aid, seite


def _kalk(seite):
    zeilen, summen = rechnen.kalkulation(seite.kopf, seite.positionen, seite.ergebnis, seite.k, seite.tabellen,
                                         seite.einst)
    zeilen = [{k: v for k, v in z.items() if not k.startswith("_") and k not in sv.OHNE_FELDER} for z in zeilen]
    summen = {k: v for k, v in summen.items() if not k.startswith("_")} if isinstance(summen, dict) else summen
    return json.loads(json.dumps(dict(z=zeilen, s=summen), default=str))


ERG = {}
N = [0]


@fall("Programm: voll und schnell -> gleiche Positionen und Kalkulation, schnell ohne Dreiecksnetz, mit Importdaten")
def _gleich():
    GESEHEN.update(pruef=0, ueber=0)
    a_voll, s_voll = _import(si.MODUS_VOLL)
    assert GESEHEN == {"pruef": 1, "ueber": 0}, GESEHEN
    a_schnell, s_schnell = _import(si.MODUS_SCHNELL)
    assert GESEHEN == {"pruef": 1, "ueber": 1}, GESEHEN       # Übersicht statt Prüfdialog
    pv = [sv._ohne_import(p) for p in s_voll.positionen]
    ps = [sv._ohne_import(p) for p in s_schnell.positionen]
    assert len(pv) == len(ps) >= 2, (len(pv), len(ps))
    N[0] = len(pv)
    u = sv.unterschiede(pv, ps)
    assert not u, u[:5]
    assert s_voll.optimieren() and s_schnell.optimieren()      # gleicher Stand (Optimierung F9) für beide
    u = sv.unterschiede(_kalk(s_voll), _kalk(s_schnell))
    assert _kalk(s_schnell)["s"].get("material"), _kalk(s_schnell)["s"]
    assert not u, u[:6]
    nv = {pid: len(db.netz(pid) or b"") for pid in db.netz_ids(a_voll)}
    ns = {pid: len(db.netz(pid) or b"") for pid in db.netz_ids(a_schnell)}
    assert len(nv) == N[0] and all(nv.values()), nv
    assert not any(ns.values()), ns
    for p in s_schnell.positionen:
        info = si.lesen(p)
        assert info and info["modus"] == si.MODUS_SCHNELL and info["version"] and info["datei"], info
        assert info["status"] in (si.VOLLSTAENDIG, si.TEILWEISE, si.ERGAENZEN) and "erkennung" in info, info
    assert all(si.lesen(p) is None for p in s_voll.positionen)
    ERG.update(schnell=(a_schnell, s_schnell), voll=s_voll)


@fall("3D nachladen: Netz gespeichert, Werte und Kalkulation unverändert, Modus „voll (3D nachgeladen)“")
def _nachladen():
    aid, seite = ERG["schnell"]
    vorher = ([sv._ohne_import(p) for p in seite.positionen], _kalk(seite))
    n = seite.step_3d_nachladen(list(range(len(seite.positionen))))
    assert n == N[0], n
    seite.neu_laden()
    assert ([sv._ohne_import(p) for p in seite.positionen], _kalk(seite)) == vorher
    netze = {pid: len(db.netz(pid) or b"") for pid in db.netz_ids(aid)}
    assert len(netze) == N[0] and all(netze.values()), netze
    assert all(si.lesen(p)["modus"] == si.NACHGELADEN for p in seite.positionen)
    assert seite.step_3d_nachladen([0]) is None              # schon nachgeladen


@fall("Übersicht: abgewähltes Teil wird nicht übernommen; „Vollständig importieren“ öffnet den Prüfdialog")
def _uebersicht():
    UEBER_AKTION["abwaehlen"] = 0
    try:
        _, seite = _import(si.MODUS_SCHNELL)
    finally:
        UEBER_AKTION["abwaehlen"] = None
    assert len(seite.positionen) == N[0] - 1, len(seite.positionen)
    GESEHEN.update(pruef=0, ueber=0)
    UEBER_AKTION["voll"] = True
    aid, seite = _import(si.MODUS_SCHNELL)
    assert GESEHEN == {"pruef": 1, "ueber": 1}, GESEHEN
    assert len(seite.positionen) == N[0] and all(si.lesen(p) is None for p in seite.positionen)
    assert all(len(db.netz(pid) or b"") for pid in db.netz_ids(aid))


@fall("Moduswahl: Vorgabe aus Einstellung, Dialog mit „als Vorgabe merken“, Abbrechen")
def _moduswahl():
    aid = db.angebot_neu()
    seite = fenster.angebot_oeffnen(aid)
    fenster.stumm = False
    db.einstellung_setzen("step_importmodus_fragen", "ja")
    alt = ModusDialog.exec
    try:
        def waehlen(self):
            self.knoepfe[si.MODUS_SCHNELL].setChecked(True)
            self.vorgabe_haken.setChecked(True)
            return QDialog.Accepted
        ModusDialog.exec = waehlen
        assert seite._importmodus_waehlen([str(DATEIEN[0])]) == si.MODUS_SCHNELL
        assert db.einstellung("step_importmodus") == "Schnellkalkulation" and si.vorgabe(db) == si.MODUS_SCHNELL
        ModusDialog.exec = lambda self: QDialog.Rejected
        assert seite._importmodus_waehlen([str(DATEIEN[0])]) is None
        db.einstellung_setzen("step_importmodus_fragen", "nein")
        assert seite._importmodus_waehlen([str(DATEIEN[0])]) == si.MODUS_SCHNELL
        # Funktion aus: ohne Frage vollständig, auch wenn die Vorgabe Schnellkalkulation ist
        db.einstellung_setzen("step_importmodus_fragen", "ja")
        db.einstellung_setzen("funktion_schnellimport", "nein")
        ModusDialog.exec = lambda self: (_ for _ in ()).throw(AssertionError("keine Frage bei Funktion aus"))
        assert seite._importmodus_waehlen([str(DATEIEN[0])]) == si.MODUS_VOLL
    finally:
        db.einstellung_setzen("funktion_schnellimport", "ja")
        ModusDialog.exec = alt
        fenster.stumm = True
        db.einstellung_setzen("step_importmodus", "vollständig")
        db.einstellung_setzen("step_importmodus_fragen", "nein")
    d = ModusDialog(None, 3, si.MODUS_VOLL)
    assert d.modus == si.MODUS_VOLL and d.knoepfe[si.MODUS_VOLL].isChecked()


@fall("Fehlerhafte Datei: Meldung, keine Position, kein Absturz (beide Modi)")
def _kaputt():
    schlecht = TMP / "kaputt.step"
    schlecht.write_text("ISO-10303-21;\nHEADER;\nDAS IST KEINE GEOMETRIE\n", encoding="utf-8")
    for modus in (si.MODUS_VOLL, si.MODUS_SCHNELL):
        _, seite = _import(modus, [schlecht])
        assert not seite.positionen, (modus, len(seite.positionen))


@fall("Einstellungen: Funktion Schnellimport (Vorgabe aus), Seite „STEP-Import: Schnellimport“ nur wenn an")
def _einstellungen():
    from rohrlaser import einstellungen_ordnung as eo, funktionen, stammdaten
    assert funktionen.FUNKTION[funktionen.SCHNELLIMPORT].vorgabe == "nein"
    assert stammdaten.EINSTELLUNG[funktionen.SCHNELLIMPORT].vorgabe == "nein"
    assert funktionen.seite_an("e_step_ablauf", db)
    db.einstellung_setzen(funktionen.SCHNELLIMPORT, "nein")
    try:
        assert not funktionen.seite_an("e_step_ablauf", db) and funktionen.seite_an("e_step", db)
    finally:
        db.einstellung_setzen(funktionen.SCHNELLIMPORT, "ja")
    assert eo.seiten_von("step_importmodus") == ["e_step_ablauf"] == eo.seiten_von("step_importmodus_fragen")
    namen = {e.name for e in stammdaten.EINSTELLUNGEN}
    assert {"step_importmodus", "step_importmodus_fragen"} <= namen
    assert [si.modus_aus_text(t) for t in ("vollständig", "Schnellkalkulation")] == [si.MODUS_VOLL, si.MODUS_SCHNELL]


@fall("Werkzeug schnellimport_vergleich: Befehlszeile läuft (Hilfe)")
def _werkzeug():
    r = subprocess.run([sys.executable, str(HIER.parent / "werkzeuge" / "schnellimport_vergleich.py"), "--help"],
                       capture_output=True, text=True)
    assert r.returncode == 0 and "--bericht" in r.stdout, r.stderr[-500:]


print(f"{'Alle Tests bestanden.' if not fehler else f'{fehler} Fehler'}")
sys.exit(1 if fehler else 0)
