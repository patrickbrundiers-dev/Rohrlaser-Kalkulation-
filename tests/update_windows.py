"""Hilfe für den Build-Schritt „Online-Update testen“ (paket.yml, Windows).

vorbereiten ORDNER          Kopie des fertigen Programms zu einem „alten Stand“ machen: Stand 0, eine Datei
                            beschädigt, eine gelöschte, eine veraltete Datei (steht in der alten Dateiliste) und eine
                            eigene Datei (steht in keiner Liste, muss bleiben).
pruefen ORDNER DATEILISTE   Nach dem Update: jede Datei wie in der Dateiliste, veraltete weg, eigene noch da, Stand neu.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "programm"))
from rohrlaser import update  # noqa: E402


def vorbereiten(ordner):
    ordner = Path(ordner)
    liste = json.loads((ordner / update.DATEILISTE).read_text(encoding="utf-8"))
    liste["stand"] = 0
    (ordner / "_internal" / "veraltet.pyd").write_bytes(b"alter Stand")
    liste["dateien"]["_internal/veraltet.pyd"] = dict(sha256=update.pruefsumme(ordner / "_internal" / "veraltet.pyd"),
                                                      groesse=11, paket="p-alt.zip")
    (ordner / "Bedienungsanleitung.pdf").write_bytes(b"beschaedigt")
    klein = sorted(r for r, d in liste["dateien"].items() if r.startswith("_internal/PySide6/translations/"))[0]
    (ordner / klein).unlink()
    (ordner / "Daten").mkdir(exist_ok=True)
    (ordner / "Daten" / "eigene.txt").write_text("bleibt", encoding="utf-8")
    (ordner / update.DATEILISTE).write_text(json.dumps(liste, indent=1), encoding="utf-8")
    print(f"Alter Stand vorbereitet: {klein} gelöscht, Bedienungsanleitung beschädigt, veraltet.pyd dazu")


def pruefen(ordner, dateiliste):
    ordner = Path(ordner)
    liste = json.loads(Path(dateiliste).read_text(encoding="utf-8"))
    falsch = [rel for rel, d in liste["dateien"].items()
              if not (ordner / rel).is_file() or update.pruefsumme(ordner / rel) != d["sha256"]]
    assert not falsch, f"{len(falsch)} Dateien nicht wie in der Dateiliste: {falsch[:10]}"
    assert not (ordner / "_internal" / "veraltet.pyd").exists(), "veraltete Datei nicht entfernt"
    assert (ordner / "Daten" / "eigene.txt").read_text(encoding="utf-8") == "bleibt", "eigene Datei angefasst"
    assert update.lokale_liste(ordner)["stand"] == liste["stand"]
    assert not (ordner / update.ARBEITSORDNER).exists(), "_update nach dem Neustart nicht aufgeräumt"
    print(f"OK: {len(liste['dateien'])} Dateien auf Stand {liste['stand']}, veraltete entfernt, Daten unberührt")


if __name__ == "__main__":
    if sys.argv[1] == "vorbereiten":
        vorbereiten(sys.argv[2])
    else:
        pruefen(sys.argv[2], sys.argv[3])
