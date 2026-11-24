"""Hilfe für den Build-Schritt „Installationsprogramm und portable Version testen“ (paket.yml, Windows).

dateien ORDNER DATEILISTE       Jede Programmdatei im Ordner wie in der Dateiliste (gleiche Prüfsumme wie das ZIP),
                                keine Portabel.ini (installiert)
info DATEI portabel|installiert DATENORDNER [ANGEBOTE]
                                Ergebnis von --info: Art, Datenordner, Datendatei vorhanden, ggf. Anzahl Angebote
angebot DATENDATEI              Ein Angebot anlegen und sichern (Daten, die eine Deinstallation überleben müssen)
deinstalliert PROGRAMMORDNER DATENORDNER
                                Nach der Deinstallation: Programm weg, Datendatei und Sicherungen noch da
vergleichen PROTOKOLL PROTOKOLL Selbsttest beider Varianten: gleiche Rechenergebnisse
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "programm"))
from rohrlaser import orte, update  # noqa: E402


def dateien(ordner, dateiliste):
    ordner = Path(ordner)
    liste = json.loads(Path(dateiliste).read_text(encoding="utf-8"))
    falsch = [rel for rel, d in liste["dateien"].items()
              if not (ordner / rel).is_file() or update.pruefsumme(ordner / rel) != d["sha256"]]
    assert not falsch, f"{len(falsch)} Dateien anders als im ZIP: {falsch[:10]}"
    assert not (ordner / orte.PORTABEL).exists(), "Portabel.ini gehört nicht in die Installation"
    print(f"OK: {len(liste['dateien'])} Programmdateien identisch mit dem ZIP")


def info(datei, art, daten, angebote=None):
    w = json.loads(Path(datei).read_text(encoding="utf-8"))
    assert not w.get("fehler"), w.get("fehler")
    assert w["portabel"] == (art == "portabel"), f"{art} erwartet: {w}"
    assert Path(w["daten"]).resolve() == Path(daten).resolve(), f"Datenordner {w['daten']} statt {daten}"
    assert Path(w["datei"]).is_file(), "Datendatei nicht angelegt"
    if angebote is not None:
        assert w["anzahl"]["angebote"] == int(angebote), f"{w['anzahl']} statt {angebote} Angebote"
    print(f"OK: {art}, Daten in {w['daten']} ({w['grund']}), {w['anzahl']}")
    return w


def angebot(datei):
    from rohrlaser.datenbank import Datenbank
    db = Datenbank(datei)
    db.angebot_neu(dict(kunde="Installationstest"))
    db.sicherung()
    db.schliessen()
    print(f"OK: Angebot in {datei} angelegt und gesichert")


def deinstalliert(programm, daten):
    programm, daten = Path(programm), Path(daten)
    assert not (programm / "Rohrlaser-Angebotskalkulation.exe").exists(), "Programm nach Deinstallation noch da"
    assert not (programm / "_internal").exists(), "_internal nach Deinstallation noch da"
    assert (daten / orte.DATENDATEI).is_file(), "Datendatei bei der Deinstallation gelöscht"
    assert any((daten / "Sicherung").glob("*.db")), "Sicherungen bei der Deinstallation gelöscht"
    print(f"OK: Programm entfernt, Daten in {daten} erhalten")


def vergleichen(a, b):
    def werte(p):
        return [z for z in Path(p).read_text(encoding="utf-8").splitlines()
                if z.startswith(("Staffelpreise:", "Angebot ", "Stammdaten:", "SELBSTTEST"))]
    wa, wb = werte(a), werte(b)
    assert wa and wa == wb, f"Ergebnisse verschieden:\n{wa}\n{wb}"
    print("OK: gleiche Rechenergebnisse\n  " + "\n  ".join(wa))


if __name__ == "__main__":
    befehl, *rest = sys.argv[1:]
    dict(dateien=dateien, info=info, angebot=angebot, deinstalliert=deinstalliert, vergleichen=vergleichen)[befehl](*rest)
