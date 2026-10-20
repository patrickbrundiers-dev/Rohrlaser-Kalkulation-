"""Online-Update (programm/rohrlaser/update.py): Pakete bilden, nur Geändertes laden, austauschen, zurückstellen.

Mit einem kleinen nachgebauten Programmordner; der echte Austausch im laufenden Programm unter Windows wird im
Build geprüft (paket.yml, Schritt „Online-Update testen“).
Aufruf: python tests/test_update.py
"""
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "programm"))
from rohrlaser import update  # noqa: E402

tmp = Path(tempfile.mkdtemp(prefix="update_"))


def programm_anlegen(ordner, aenderung=b""):
    """Programmordner wie im ZIP: .exe, große Bibliothek, viele kleine Dateien in Unterordnern, Daten."""
    ordner = Path(ordner)
    dateien = {"Rohrlaser-Angebotskalkulation.exe": b"MZ-exe" + aenderung + os.urandom(0) + bytes(300_000),
               "_internal/gross.dll": bytes(range(256)) * 8000,                       # 2 MB: eigenes Paket
               "_internal/PySide6/Qt6Core.dll": b"qt" * 700_000,                          # 1,4 MB
               "STEP-Import/STEP-Import.exe": b"MZ-step" + bytes(200_000),
               "Bedienungsanleitung.pdf": b"%PDF" + bytes(50_000)}
    for i in range(40):
        dateien[f"_internal/PySide6/translations/qt_{i:02d}.qm"] = f"Übersetzung {i}".encode() * 50
        dateien[f"STEP-Import/_internal/OCP/M{i}/__init__.pyi"] = f"Stub {i}".encode() * 20
    for rel, inhalt in dateien.items():
        p = ordner / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(inhalt)
    (ordner / "Daten").mkdir(exist_ok=True)
    (ordner / "Daten" / "rohrlaser.db").write_bytes(b"DATEN")
    (ordner / "Angebote").mkdir(exist_ok=True)
    (ordner / "Angebote" / "A-1.pdf").write_bytes(b"ANGEBOT")
    return ordner


def stimmt(ordner, liste):
    for rel, d in liste["dateien"].items():
        assert update.pruefsumme(Path(ordner) / rel) == d["sha256"], rel


# Stand 1: installiert (Dateiliste im Programmordner wie im ZIP)
v1 = programm_anlegen(tmp / "v1")
(v1 / "_internal" / "veraltet.pyd").write_bytes(b"alt")
l1 = update.erstellen(v1, tmp / "pakete1", 1, adresse="https://example.invalid/update-dateien/")
shutil.copyfile(tmp / "pakete1" / update.DATEILISTE, v1 / update.DATEILISTE)
assert update.DATEILISTE not in l1["dateien"] and not any(r.startswith(("Daten/", "Angebote/")) for r in l1["dateien"])
assert len(l1["pakete"]) < len(l1["dateien"]) / 5, "kleine Dateien gebündelt"
assert all(n.startswith("d-") for n in {l1["dateien"][r]["paket"] for r in ("_internal/gross.dll",
                                                                                  "_internal/PySide6/Qt6Core.dll")})

# Gleicher Inhalt -> gleiche Paketnamen und gleiche Bytes (unveränderte Pakete werden nicht neu hochgeladen)
l1b = update.erstellen(v1, tmp / "pakete1b", 1)
assert l1b["pakete"].keys() == l1["pakete"].keys()
for p in l1["pakete"]:
    assert (tmp / "pakete1" / p).read_bytes() == (tmp / "pakete1b" / p).read_bytes(), p

# Stand 2: .exe und eine Übersetzung geändert, eine Datei neu, veraltet.pyd entfällt
v2 = programm_anlegen(tmp / "v2", aenderung=b"-v2")
(v2 / "_internal" / "PySide6" / "translations" / "qt_07.qm").write_bytes(b"neu")
(v2 / "_internal" / "neu.pyd").write_bytes(b"neu dazu")
l2 = update.erstellen(v2, tmp / "pakete2", 2, aenderung="Test")
unveraendert = set(l1["pakete"]) & set(l2["pakete"])
assert len(unveraendert) >= len(l2["pakete"]) - 4, "nur Pakete mit Änderungen sind neu"

online = update.online_liste(str(tmp / "pakete2" / update.DATEILISTE))
lokal = update.lokale_liste(v1)
assert update.neuer(online, lokal) and not update.neuer(lokal, online)
assert update.stand_text(lokal).startswith(f"{update.VERSION} (Stand 1 vom ")
plan = update.planen(v1, online, lokal)
assert sorted(plan["neu"]) == ["Rohrlaser-Angebotskalkulation.exe", "_internal/PySide6/translations/qt_07.qm",
                               "_internal/neu.pyd"], plan["neu"]
assert plan["weg"] == ["_internal/veraltet.pyd"]
assert plan["groesse"] < sum(d["groesse"] for d in online["pakete"].values()) / 2, "nur ein Teil wird geladen"

# Geladen wird über die Adresse aus der Dateiliste, bei einem Ordner aus diesem Ordner
assert update.paket_adresse("https://x/aktuell/Update.json", l1, "p-1.zip") == "https://example.invalid/update-dateien/p-1.zip"
assert update.paket_adresse("https://x/aktuell/Update.json", l2, "p-1.zip") == "https://x/aktuell/p-1.zip"

# Austausch schlägt fehl (Ziel ist ein Ordner, nicht ersetzbar) -> alles wieder wie vorher
vorher = {p.relative_to(v1).as_posix(): p.read_bytes() for p in v1.rglob("*") if p.is_file()}
kaputt = dict(plan, neu=plan["neu"] + ["Bedienungsanleitung.pdf/x"])
online_kaputt = json.loads(json.dumps(online))
online_kaputt["dateien"]["Bedienungsanleitung.pdf/x"] = dict(online["dateien"]["Bedienungsanleitung.pdf"])
neu_ordner = update.laden(v1, str(tmp / "pakete2" / update.DATEILISTE), online_kaputt, kaputt)
try:
    update.einspielen(v1, online_kaputt, kaputt, neu_ordner)
    raise AssertionError("Fehler erwartet")
except update.UpdateFehler as e:
    assert "lässt sich nicht austauschen" in str(e), e
nachher = {p.relative_to(v1).as_posix(): p.read_bytes() for p in v1.rglob("*")
           if p.is_file() and not p.relative_to(v1).as_posix().startswith(update.ARBEITSORDNER + "/")}
assert nachher == vorher, set(nachher) ^ set(vorher)
update.aufraeumen(v1)

# Update im Ganzen: danach entspricht der Ordner Stand 2, Daten und Angebote unberührt, alte Dateien unter _update
geladen = []
online, plan = update.aktualisieren(v1, str(tmp / "pakete2" / update.DATEILISTE), fortschritt=geladen.append)
assert sum(geladen) == plan["groesse"], (sum(geladen), plan["groesse"])
stimmt(v1, l2)
assert not (v1 / "_internal" / "veraltet.pyd").exists()
assert (v1 / "Daten" / "rohrlaser.db").read_bytes() == b"DATEN" and (v1 / "Angebote" / "A-1.pdf").exists()
assert update.lokale_liste(v1)["stand"] == 2
alt = list((v1 / update.ARBEITSORDNER).glob("alt-*"))
assert len(alt) == 1 and (alt[0] / "_internal" / "veraltet.pyd").read_bytes() == b"alt"
assert not (v1 / update.ARBEITSORDNER / "neu").exists()

# Nochmal: nichts zu tun; beim nächsten Start wird aufgeräumt
assert update.aktualisieren(v1, str(tmp / "pakete2" / update.DATEILISTE))[1] is None
update.aufraeumen(v1)
assert not (v1 / update.ARBEITSORDNER).exists()

# Beschädigte Datei wird erkannt und neu geladen, auch ohne neuen Stand (alle=True tauscht jede Datei)
(v1 / "_internal" / "PySide6" / "translations" / "qt_03.qm").write_bytes(b"kaputt")
assert update.planen(v1, online, update.lokale_liste(v1))["neu"] == ["_internal/PySide6/translations/qt_03.qm"]
assert len(update.planen(v1, online, alle=True)["neu"]) == len(online["dateien"])

# Nicht erreichbar / beschädigt -> verständlicher Fehler
for quelle in (str(tmp / "fehlt" / update.DATEILISTE), str(tmp / "pakete2" / "Rohrlaser-Angebotskalkulation.exe")):
    try:
        update.online_liste(quelle)
        raise AssertionError("Fehler erwartet")
    except update.UpdateFehler:
        pass

# Oberfläche: Hinweis beim neuen Stand, „Jetzt aktualisieren“ sichert die Datendatei, tauscht aus, startet neu
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from rohrlaser import update_fenster  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402

app = QApplication.instance() or QApplication([])
v3 = programm_anlegen(tmp / "v3")
shutil.copyfile(tmp / "pakete1" / update.DATEILISTE, v3 / update.DATEILISTE)
(v3 / "Daten" / "rohrlaser.db").unlink()
db = Datenbank(v3 / "Daten" / "rohrlaser.db")
os.environ["RL_UPDATE_QUELLE"] = str(tmp / "pakete2" / update.DATEILISTE)
f = Hauptfenster(db, v3, stumm=True)
assert "Stand 1" in f.windowTitle(), f.windowTitle()
meldungen, neustart = [], []
QMessageBox.information = staticmethod(lambda *a, **k: meldungen.append(a[2]))
QMessageBox.warning = staticmethod(lambda *a, **k: meldungen.append("WARNUNG " + a[2]))
f.updater.neu_starten = lambda: neustart.append(True)
m = update_fenster.frage(f, online, f.updater.lokal)
assert "Stand 2" in m.text() and "Stand 1" in m.text() and "Test" in m.text()
assert [b.text() for b in m.buttons()] == ["Jetzt aktualisieren", "Später"], [b.text() for b in m.buttons()]
update_fenster.frage = lambda *a: type("Frage", (), dict(exec=lambda s: 0, clickedButton=lambda s: s.jetzt,
                                                         jetzt=object()))()
f.updater._gefunden(online, None, still=True)
assert neustart and "Stand 2" in meldungen[-1], meldungen
stimmt(v3, l2)
assert any((v3 / "Daten" / "Sicherung").glob("rohrlaser_*_vor_update.db")), "Datendatei vor dem Update gesichert"
assert f.updater.lokal["stand"] == 2
f.updater._gefunden(online, None, still=False)              # jetzt aktuell
assert "aktuell" in meldungen[-1], meldungen
f.updater._gefunden(None, "keine Verbindung", still=True)   # still: keine Meldung
f.updater._gefunden(None, "keine Verbindung", still=False)
assert meldungen[-1].startswith("WARNUNG"), meldungen
f.close()
db.schliessen()

shutil.rmtree(tmp, ignore_errors=True)
print("OK: Online-Update (Pakete, nur Geändertes laden, Austausch, Zurückstellen, Aufräumen)")
