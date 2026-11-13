"""Anfragenverwaltung, Paket 2 (Patrick 13.11.2026): Anfragen aus dem klassischen Outlook am PC.

Geprüft mit einem nachgebauten Outlook (dieselben Daten und Antworten wie das PowerShell-Skript): Mails im Ordner
„Anfragen“ werden Akten und wandern nach „Neu“, keine Doppel; Übernehmen/Erledigen im Programm verschiebt die Mail,
Verschieben in Outlook ändert die Akte; fehlende Akten werden nachgeholt; nur ein Rechner ruft ab (Abruf-Marke);
ohne klassisches Outlook eine klare Meldung; Seite „Anfragen“ mit Knopf „Outlook …“ und Windows-Meldung.
Nur erfundene Testmails, nichts geht an ein echtes Postfach.

Aufruf: python tests/test_outlook_anfragen.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import datetime
import json
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402

import mail_testdateien  # noqa: E402
from rohrlaser import anfragen_akten as ak  # noqa: E402
from rohrlaser import outlook_anfragen as ol  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def ok(text):
    print("OK    ", text)


class Outlook:
    """Nachbau: Ordner „Anfragen“ mit Unterordnern; jede Mail {mid, daten, eingang}. Verhält sich wie ABRUF_PS."""

    def __init__(self, ordner="Anfragen"):
        self.name = ordner
        self.ordner = {"": [], "Neu": [], "In Bearbeitung": [], "Erledigt": []}
        self.aufrufe = []
        self.fehler = None

    def mail(self, mid, betreff, text, absender, anhaenge=(), wo="", eingang=None):
        eingang = eingang or datetime.datetime(2026, 11, 13, 7, 30)
        self.ordner[wo].append(dict(mid=mid, eingang=eingang, daten=mail_testdateien.msg(
            betreff, text, absender.split("@")[0].title(), absender, eingang, list(anhaenge))))

    def wo(self, mid):
        return next((o for o, l in self.ordner.items() for m in l if m["mid"] == mid), None)

    def schieben(self, mid, nach):
        von = self.wo(mid)
        m = next(m for m in self.ordner[von] if m["mid"] == mid)
        self.ordner[von].remove(m)
        self.ordner[nach].append(m)

    def __call__(self, befehl):
        assert befehl[0] == "powershell" and Path(befehl[-3]).read_text(encoding="utf-8-sig") == ol.ABRUF_PS
        d = json.loads(Path(befehl[-2]).read_text(encoding="utf-8"))
        self.aufrufe.append(d)
        if self.fehler:
            return SimpleNamespace(returncode=1, stdout="", stderr=self.fehler)
        if d["ordner"] != self.name:
            return SimpleNamespace(returncode=1, stdout="", stderr=f"Outlook-Ordner '{d['ordner']}' nicht gefunden")
        aus = dict(neu=[], liste=[], verschoben=[], fehler=[])
        nr = [0]

        def sichern(m):
            nr[0] += 1
            p = Path(d["ziel"]) / f"mail_{nr[0]}.msg"
            p.write_bytes(m["daten"])
            aus["neu"].append(dict(mid=m["mid"], datei=str(p), eingang=m["eingang"].isoformat()))
        wunsch = {v["mid"]: v["nach"] for v in d["verschieben"]}
        for n in d["unter"]:
            for m in list(self.ordner[n]):
                if m["mid"] in wunsch and wunsch[m["mid"]] != n:
                    self.schieben(m["mid"], wunsch[m["mid"]])
                    aus["verschoben"].append(m["mid"])
        for m in list(self.ordner[""])[:d["max"]]:
            sichern(m)
            self.schieben(m["mid"], d["unter"][0])
        grenze = datetime.datetime.now() - datetime.timedelta(days=d["tage"])
        for n in d["unter"]:
            for m in self.ordner[n]:
                if n == d["unter"][2] and m["eingang"] < grenze:
                    continue
                aus["liste"].append(dict(mid=m["mid"], ordner=n))
                if m["mid"] in d["nachholen"]:
                    sichern(m)
        # PowerShell: eine Liste mit nur einem Eintrag kommt als Objekt an
        aus = {k: (v[0] if len(v) == 1 else v) for k, v in aus.items()}
        Path(befehl[-1]).write_text(json.dumps(aus), encoding="utf-8-sig")
        return SimpleNamespace(returncode=0, stdout="", stderr="")


tmp = Path(tempfile.mkdtemp())
JETZT = datetime.datetime.now().replace(microsecond=0)

# ------------------------------------------------------------------ Abruf-Marke
abl = ak.OrdnerAblage(tmp / "akten", "PB", platz="BUERO1")
abl2 = ak.OrdnerAblage(tmp / "akten", "MK", platz="WERKSTATT")
assert ol.marke_nehmen(abl, jetzt=JETZT)[0]
erfolg, m = ol.marke_nehmen(abl2, jetzt=JETZT + datetime.timedelta(seconds=30))
assert not erfolg and m["platz"] == "BUERO1"
assert ol.marke_nehmen(abl, jetzt=JETZT + datetime.timedelta(seconds=60))[0]        # erneuert
assert ol.marke_nehmen(abl2, jetzt=JETZT + datetime.timedelta(seconds=60 + ol.LEASE_S + 1))[0]   # verwaist
assert ol.abrufen(abl, ausfuehren=Outlook(), jetzt=JETZT + datetime.timedelta(seconds=400))["anderer"]["platz"] \
    == "WERKSTATT"
ol.marke_abgeben(abl2)
assert ol.marke_lesen(abl) is None
ok("Nur ein Rechner ruft ab: Abruf-Marke, verwaiste Marke nach 5 Minuten übernommen, Abgeben beim Ausschalten")

# ------------------------------------------------------------------ neue Mails werden Akten, keine Doppel
ou = Outlook()
ou.mail("<a1@muster-metall.example>", "Anfrage Halter 2026-77", "Bitte 20 Stück anbieten.\nGruß",
        "max@muster-metall.example", [("halter.step", b"ISO-10303-21; Halter")])
ou.mail("<b2@beispiel-bau.example>", "Anfrage Winkel", "Bitte 5 Winkel.", "erika@beispiel-bau.example")
kunden = [dict(kundennr="10417", name="Muster Metall GmbH", email="einkauf@muster-metall.example")]
erg = ol.abrufen(abl, "Anfragen", kunden, ausfuehren=ou, jetzt=JETZT)
assert not erg["fehler"] and len(erg["neu"]) == 2, erg
assert not ou.ordner[""] and len(ou.ordner["Neu"]) == 2
a1 = next(a for a in abl.alle() if a.kopf["nachrichten_id"] == "<a1@muster-metall.example>")
assert a1.status == ak.NEU and a1.kopf["quelle"] == "outlook" and a1.kopf["absender"] == "max@muster-metall.example"
assert a1.betreff == "Anfrage Halter 2026-77" and a1.kopf.get("kundennr") == "10417"
namen = sorted(d["name"] for d in a1.dateien())
assert namen == ["Anfrage_Halter_2026-77.msg", "halter.step"], namen
assert ol.stand_lesen(abl) == {"<a1@muster-metall.example>": "Neu", "<b2@beispiel-bau.example>": "Neu"}
erg = ol.abrufen(abl, "Anfragen", kunden, ausfuehren=ou, jetzt=JETZT)
assert not erg["neu"] and len(abl.alle()) == 2
# dieselbe Mail noch einmal im Ordner (z. B. in Outlook zurückkopiert): keine zweite Akte
ou.mail("<a1@muster-metall.example>", "Anfrage Halter 2026-77", "Bitte 20 Stück anbieten.",
        "max@muster-metall.example")
erg = ol.abrufen(abl, "Anfragen", kunden, ausfuehren=ou, jetzt=JETZT)
assert not erg["neu"] and len(abl.alle()) == 2
ok("Mails im Outlook-Ordner Anfragen: je eine Akte (Absender, Betreff, Kunde, Mail + Anhang), Mail nach Neu, "
   "dieselbe Mail nie zweimal")

# ------------------------------------------------------------------ Programm -> Outlook
abl.uebernehmen(a1, jetzt=JETZT)
erg = ol.abrufen(abl, "Anfragen", kunden, ausfuehren=ou, jetzt=JETZT)
assert erg["verschoben"] == 1 and ou.wo("<a1@muster-metall.example>") == "In Bearbeitung", ou.ordner
abl.erledigen(abl.neu_lesen(a1), jetzt=JETZT)
ol.abrufen(abl, "Anfragen", kunden, ausfuehren=ou, jetzt=JETZT)
assert ou.wo("<a1@muster-metall.example>") == "Erledigt"
assert abl.neu_lesen(a1).status == ak.ERLEDIGT          # bleibt, Outlook folgt dem Programm
ok("Übernehmen und Erledigen im Programm verschieben die Mail in Outlook (In Bearbeitung, Erledigt)")

# ------------------------------------------------------------------ Outlook -> Programm
b2 = next(a for a in abl.alle() if a.kopf["nachrichten_id"] == "<b2@beispiel-bau.example>")
ou.schieben("<b2@beispiel-bau.example>", "In Bearbeitung")
erg = ol.abrufen(abl, "Anfragen", kunden, ausfuehren=ou, jetzt=JETZT)
b2 = abl.neu_lesen(b2)
assert b2.status == ak.BEARBEITUNG and b2.bearbeiter == "PB" and erg["gefolgt"], erg
ou.schieben("<b2@beispiel-bau.example>", "Erledigt")
ol.abrufen(abl, "Anfragen", kunden, ausfuehren=ou, jetzt=JETZT)
assert abl.neu_lesen(b2).status == ak.ERLEDIGT
ou.schieben("<b2@beispiel-bau.example>", "Neu")
ol.abrufen(abl, "Anfragen", kunden, ausfuehren=ou, jetzt=JETZT)
b2 = abl.neu_lesen(b2)
assert b2.status == ak.NEU and any("in Outlook" in n["text"].lower() or "Outlook" in n["text"]
                                   for n in b2.stand["notizen"])
assert not [e for e in b2.verlauf if e.get("ungueltig")]
# Erledigt direkt aus Neu (in Outlook verschoben): übernommen und erledigt
ou.schieben("<b2@beispiel-bau.example>", "Erledigt")
ol.abrufen(abl, "Anfragen", kunden, ausfuehren=ou, jetzt=JETZT)
assert abl.neu_lesen(b2).status == ak.ERLEDIGT
ok("Verschieben in Outlook ändert die Anfrage: In Bearbeitung = übernommen, Erledigt = erledigt, Neu = "
   "zurückgegeben, mit Notiz im Verlauf")

# ------------------------------------------------------------------ fehlende Akte nachholen, Mail verschwunden
ou.mail("<c3@neu.example>", "Altanfrage", "schon vorher einsortiert", "info@neu.example", wo="In Bearbeitung")
erg = ol.abrufen(abl, "Anfragen", kunden, ausfuehren=ou, jetzt=JETZT)
assert not erg["neu"] and ol.stand_lesen(abl)["<c3@neu.example>"] == "In Bearbeitung"
erg = ol.abrufen(abl, "Anfragen", kunden, ausfuehren=ou, jetzt=JETZT)
c3 = next(a for a in abl.alle() if a.kopf.get("nachrichten_id") == "<c3@neu.example>")
assert len(erg["neu"]) == 1 and c3.status == ak.BEARBEITUNG          # folgt dem Ordner, in dem die Mail liegt
ol.abrufen(abl, "Anfragen", kunden, ausfuehren=ou, jetzt=JETZT)
assert ou.wo("<c3@neu.example>") == "In Bearbeitung"
ou.ordner["In Bearbeitung"] = [m for m in ou.ordner["In Bearbeitung"] if m["mid"] != "<c3@neu.example>"]   # gelöscht
ol.abrufen(abl, "Anfragen", kunden, ausfuehren=ou, jetzt=JETZT)
assert "<c3@neu.example>" not in ol.stand_lesen(abl) and abl.neu_lesen(c3).status == ak.BEARBEITUNG
ok("Mail ohne Akte (schon vorher einsortiert) wird nachgeholt; in Outlook gelöschte Mail: Akte bleibt")

# ------------------------------------------------------------------ Fehler
ou.fehler = "New-Object : Die COM-Klassenfabrik ... 80040154 Klasse nicht registriert"
erg = ol.abrufen(abl, "Anfragen", ausfuehren=ou, jetzt=JETZT)
assert erg["fehler"] == ["Kein klassisches Outlook auf diesem Rechner (das neue Outlook hat keine Schnittstelle)."]
ou.fehler = None
erg = ol.abrufen(abl, "Posteingang\\Kunden", ausfuehren=ou, jetzt=JETZT)
assert "nicht gefunden" in erg["fehler"][0]
if sys.platform != "win32":
    assert ol.outlook_lauf(ol.ps_daten("Anfragen", tmp))[1] == "Outlook gibt es nur unter Windows."
assert len(abl.alle()) == 3
ok("Ohne klassisches Outlook oder ohne Ordner: klare Meldung, nichts geändert")

# ------------------------------------------------------------------ Seite „Anfragen“
app = QApplication.instance() or QApplication([])
db = Datenbank(tmp / "prog" / "rohrlaser.db")
db.einstellung_setzen("benutzer_kuerzel", "PB")
fenster = Hauptfenster(db, tmp / "prog", stumm=True)
seite = fenster.anfragen_seite
ou2 = Outlook()
seite.outlook_ausfuehren = ou2
assert not ol.an(db) and not seite.outlook_abrufen()                 # Vorgabe: aus
d = seite.outlook_zeigen()
assert d.windowTitle() == "Anfragen aus Outlook" and "kein Rechner" in d.stand.text()
d.ein.setChecked(True)                                               # startet den ersten Abruf
assert ol.an(db)
if seite._ol_lauf is not None:
    seite._ol_lauf.result()
    seite._outlook_pruefen()
ou2.mail("<d4@kunde.example>", "Anfrage Rahmen", "Bitte 3 Rahmen anbieten.", "kauf@kunde.example")
d.abrufen()
assert [a.betreff for a in seite.akten] == ["Anfrage Rahmen"] and seite.zaehler["neu"].text().endswith("1")
assert "Letzter Abruf" in d.stand.text() and "1 neue Anfrage" in d.stand.text(), d.stand.text()
assert "PB am Rechner" in d.stand.text()
meldungen = getattr(fenster, "windows_meldungen", [])
assert meldungen and meldungen[-1][0] == "Neue Anfrage" and "Anfrage Rahmen" in meldungen[-1][1], meldungen
seite.waehlen(seite.akten[0].nr)
seite.uebernehmen()
seite.outlook_abrufen(warten=True)
assert ou2.wo("<d4@kunde.example>") == "In Bearbeitung"
d.ein.setChecked(False)
assert not ol.an(db) and ol.marke_lesen(seite.ablage()) is None
ok("Seite Anfragen: Knopf Outlook … (je Rechner ein/aus, Ordner, wer abruft, Jetzt abrufen), neue Anfrage mit "
   "Windows-Meldung, Übernehmen verschiebt die Mail")
fenster.close()
db.schliessen()
print("Alle Tests bestanden.")
