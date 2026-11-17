"""Nachgebautes klassisches Outlook für die Tests der Anfragenverwaltung (Pakete 2 und 3): bekommt dieselben Daten
wie das PowerShell-Skript outlook_anfragen.ABRUF_PS und antwortet genauso. Nur erfundene Testmails."""
import datetime
import json
import sys
from pathlib import Path
from types import SimpleNamespace

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER))
import mail_testdateien  # noqa: E402
from rohrlaser import outlook_anfragen as ol  # noqa: E402


class Outlook:
    """Nachbau: Ordner „Anfragen“ mit Unterordnern; jede Mail {mid, daten, eingang}. Verhält sich wie ABRUF_PS."""

    def __init__(self, ordner="Anfragen", pfade=None, kategorien=()):
        self.name = ordner
        self.ordner = {"": [], "Neu": [], "In Bearbeitung": [], "Erledigt": []}
        self.pfade = dict(pfade or {})      # {"Neu": "\\\\Postfach\\…"}: dieser Ordner liegt woanders (16.11.2026)
        self.kategorien = list(kategorien)  # Kategorien des Postfachs
        self.gewaehlt = ""                  # Ergebnis der Ordnerauswahl (PickFolder)
        self.kennung = {}                   # {Pfad: EntryID}: Kennung der Ordner (für PickFolder und GetFolderFromID)
        self.nur_kennung = set()            # Pfade, die nur über die Kennung zu finden sind (freigegebene Ordner)
        self.andere = 0                     # Einträge im Eingang, die keine Mail sind (Termin, Lesebestätigung)
        self.nicht_sicherbar = set()        # Mails, deren Kopie (SaveAs) leer bleibt: dürfen nicht verschoben werden
        self.aufrufe = []
        self.fehler = None

    def mail(self, mid, betreff, text, absender, anhaenge=(), wo="", eingang=None, konversation="", kat=()):
        eingang = eingang or datetime.datetime(2026, 11, 13, 7, 30)
        self.ordner[wo].append(dict(mid=mid, eingang=eingang, konversation=konversation, kat=list(kat),
                                    daten=mail_testdateien.msg(
            betreff, text, absender.split("@")[0].title(), absender, eingang, list(anhaenge))))

    def wo(self, mid):
        return next((o for o, l in self.ordner.items() for m in l if m["mid"] == mid), None)

    def schieben(self, mid, nach):
        von = self.wo(mid)
        m = next(m for m in self.ordner[von] if m["mid"] == mid)
        self.ordner[von].remove(m)
        self.ordner[nach].append(m)

    def kat(self, mid):
        return next(m["kat"] for l in self.ordner.values() for m in l if m["mid"] == mid)

    def __call__(self, befehl):
        skript = Path(befehl[-3]).read_text(encoding="utf-8-sig")
        assert befehl[0] == "powershell" and skript in (ol.ABRUF_PS, ol.WAEHLEN_PS, ol.KATEGORIEN_PS)
        d = json.loads(Path(befehl[-2]).read_text(encoding="utf-8"))
        self.aufrufe.append(d)
        if self.fehler:
            return SimpleNamespace(returncode=1, stdout="", stderr=self.fehler)
        if skript != ol.ABRUF_PS:
            pf = self.gewaehlt if skript == ol.WAEHLEN_PS else ""
            aus = dict(pfad=pf, id=self.kennung.get(pf, ""), store="store-1" if pf in self.kennung else "",
                       kategorien=self.kategorien)
            Path(befehl[-1]).write_text(json.dumps(aus), encoding="utf-8-sig")
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if d["ordner"] != self.name:
            return SimpleNamespace(returncode=1, stdout="", stderr=f"Outlook-Ordner '{d['ordner']}' nicht gefunden")
        ids = d.get("ids") or {}
        for pf in [d["ordner"], *(d.get("unter_pfade") or [])]:
            if pf in self.nur_kennung and (ids.get(pf) or {}).get("e") != self.kennung.get(pf):
                return SimpleNamespace(returncode=1, stdout="", stderr=f"Outlook-Ordner '{pf}' nicht gefunden")
        for n, pf in zip(d["unter"], d.get("unter_pfade") or ["", "", ""]):
            if (pf or "") != self.pfade.get(n, ""):
                return SimpleNamespace(returncode=1, stdout="", stderr=f"Outlook-Ordner '{pf or n}' nicht gefunden")
        aus = dict(neu=[], liste=[], verschoben=[], fehler=[], kat_gesetzt=[], kategorien=list(self.kategorien))
        andere = self.andere
        katw = {v["mid"]: v for v in d.get("kategorien") or []}
        nr = [0]

        def sichern(m):
            nr[0] += 1
            p = Path(d["ziel"]) / f"mail_{nr[0]}.msg"
            p.write_bytes(m["daten"])
            aus["neu"].append(dict(mid=m["mid"], datei=str(p), eingang=m["eingang"].isoformat(),
                                   konversation=m["konversation"]))
        wunsch = {v["mid"]: v["nach"] for v in d["verschieben"]}
        for n in d["unter"]:
            for m in list(self.ordner[n]):
                if m["mid"] in katw:
                    w = katw[m["mid"]]
                    m["kat"] = [k for k in m["kat"] if k not in w["weg"]]
                    if w["setzen"] and w["setzen"] not in m["kat"]:
                        m["kat"].append(w["setzen"])
                    aus["kat_gesetzt"].append(m["mid"])
                if m["mid"] in wunsch and wunsch[m["mid"]] != n:
                    self.schieben(m["mid"], wunsch[m["mid"]])
                    aus["verschoben"].append(m["mid"])
        for m in list(self.ordner[""])[:d["max"]]:
            if m["mid"] in self.nicht_sicherbar:          # wie ABRUF_PS: leere Kopie = Fehler, Mail bleibt
                aus["fehler"].append(m["mid"] + ": Kopie der Mail nicht gesichert, Mail bleibt, wo sie ist")
                continue
            sichern(m)
            self.schieben(m["mid"], d["unter"][0])
        grenze = datetime.datetime.now() - datetime.timedelta(days=d["tage"])
        for n in d["unter"]:
            for m in self.ordner[n]:
                if n == d["unter"][2] and m["eingang"] < grenze:
                    continue
                aus["liste"].append(dict(mid=m["mid"], ordner=n, kat=list(m["kat"])))
                if m["mid"] in d["nachholen"]:
                    sichern(m)
        # PowerShell: eine Liste mit nur einem Eintrag kommt als Objekt an
        aus = {k: (v[0] if len(v) == 1 else v) for k, v in aus.items()}
        aus["andere"] = andere
        Path(befehl[-1]).write_text(json.dumps(aus), encoding="utf-8-sig")
        return SimpleNamespace(returncode=0, stdout="", stderr="")
