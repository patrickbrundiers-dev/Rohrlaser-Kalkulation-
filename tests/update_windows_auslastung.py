"""Hilfe für den Schritt „Online-Update testen“ im Workflow Auslastung (Windows, fertiges Programm).

vorbereiten ORDNER          Kopie des fertigen Programms zu einem „alten Stand“ machen: Stand 0, eine Datei gelöscht,
                            eine veraltete Datei (steht in der alten Dateiliste) und eigene Dateien (Daten,
                            Auslastung.ini; stehen in keiner Liste, müssen bleiben).
pruefen ORDNER DATEILISTE   Nach dem Update: jede Datei wie in der Dateiliste, veraltete weg, eigene noch da, Stand neu,
                            Dateiliste bytegleich mit gültiger Signatur, Arbeitsordner _update aufgeräumt.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "programm"))
from rl_auslastung import aktualisierung as A  # noqa: E402
from rohrlaser import update  # noqa: E402


def vorbereiten(ordner):
    ordner = Path(ordner)
    liste = json.loads((ordner / update.DATEILISTE).read_text(encoding="utf-8"))
    liste["stand"] = 0
    (ordner / "_internal" / "veraltet.pyd").write_bytes(b"alter Stand")
    liste["dateien"]["_internal/veraltet.pyd"] = dict(sha256=update.pruefsumme(ordner / "_internal" / "veraltet.pyd"),
                                                      groesse=11, paket="p-" + "0" * 40 + ".zip")
    # eine Datei, ohne die das alte Programm noch startet (Übersetzung von Qt), sonst keine
    klein = next(iter(sorted(r for r in liste["dateien"] if r.endswith(".qm"))), None)
    if klein:
        (ordner / klein).unlink()
    (ordner / "Daten").mkdir(exist_ok=True)
    (ordner / "Daten" / "eigene.txt").write_text("bleibt", encoding="utf-8")
    (ordner / "Auslastung.ini").write_text("tafel_zoom = 2 Wochen\n", encoding="utf-8")
    (ordner / update.DATEILISTE).write_text(json.dumps(liste, indent=1), encoding="utf-8")
    print(f"Alter Stand vorbereitet: {klein} gelöscht, veraltet.pyd dazu, Daten und Auslastung.ini angelegt")


def pruefen(ordner, dateiliste):
    ordner = Path(ordner)
    liste = json.loads(Path(dateiliste).read_text(encoding="utf-8"))
    falsch = [rel for rel, d in liste["dateien"].items()
              if not (ordner / rel).is_file() or update.pruefsumme(ordner / rel) != d["sha256"]]
    assert not falsch, f"{len(falsch)} Dateien nicht wie in der Dateiliste: {falsch[:10]}"
    assert not (ordner / "_internal" / "veraltet.pyd").exists(), "veraltete Datei nicht entfernt"
    assert (ordner / "Daten" / "eigene.txt").read_text(encoding="utf-8") == "bleibt", "eigene Datei angefasst"
    assert (ordner / "Auslastung.ini").read_text(encoding="utf-8") == "tafel_zoom = 2 Wochen\n", "Auslastung.ini angefasst"
    assert update.lokale_liste(ordner)["stand"] == liste["stand"]
    assert not (ordner / update.ARBEITSORDNER).exists(), "_update nach dem Neustart nicht aufgeräumt"
    assert (ordner / update.DATEILISTE).read_bytes() == Path(dateiliste).read_bytes(), "Dateiliste nicht bytegleich"
    A.signatur_pruefen((ordner / update.DATEILISTE).read_bytes(), (ordner / update.SIGNATUR).read_bytes())
    print(f"OK: {len(liste['dateien'])} Dateien auf Stand {liste['stand']}, veraltete entfernt, Daten unberührt")


if __name__ == "__main__":
    if sys.argv[1] == "vorbereiten":
        vorbereiten(sys.argv[2])
    else:
        pruefen(sys.argv[2], sys.argv[3])
