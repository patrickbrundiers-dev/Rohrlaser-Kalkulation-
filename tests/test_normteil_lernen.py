"""Normteile von Hand korrigieren und lernen (Master-Prompt Patrick 21.11.2026 „Intelligente Normteil- und
Zukaufteil-Erkennung“, Punkte manuelle Korrektur und Lernen, N6).

- L1 „Doch Fertigungsteil“ auch für voll gemessene Normteile (Begriff im Namen): Fertigungsteil, Vorschlag mit Grund;
  wieder annehmen geht; nur als Zukaufteil gemessenes Normteil (Norm im Bauteilnamen, 0.9.447) bleibt Zukaufteil
- L2 Entscheidungen merken je Bauteilname + Geometrie (Instanz-Zusatz :3 egal, Datum), Unverändertes nicht neu
- L3 nächster Import (importprofil.anwenden): gleiche Teile wie entschieden, mit Datum im Grund; andere Geometrie oder
  anderer Name unverändert; gemerktes Fertigungsteil bleibt Fertigungsteil
- L4 Lernzentrale: Eintrag sichtbar, vergessen; Abgleich über den gemeinsamen Ordner (EINSTELLUNGEN_GETEILT)
- L5 Aufteilung für die Kalkulation (N7): Rohrlaser-Teile, Bleche, Dreh-/Frästeile, Normteile, ungeklärt (Vorschlag)

Aufruf: python tests/test_normteil_lernen.py
"""
import copy
import datetime
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "programm"))

from rohrlaser import importprofil, lernen, zukaufteile as zk  # noqa: E402

E = {"step_normteile": "ISO; DIN; Schraube; Mutter; Scheibe; Stift; Niet; Normteil", "step_zukauf_begriffe": "ja"}


def teil(name, huelle="8|8|20", volumen="900", **w):
    return dict(datei="a.step", koerper="1", bauteil=name, artikel=name, profilform="Rundstahl", abm_a="8", abm_b="8",
                laenge="20", huelle=huelle, volumen=volumen, n_flaechen="3", n_kanten="3", **w)


def importieren(ms, gelernt=None):
    importprofil.anwenden(ms, None, dict(E, step_zukauf_gelernt=gelernt or {}))
    return ms


# L1
m = importieren([teil("Schraube M8x20")])[0]
assert m.get("_normteil") and zk.kann_fertigung(m), m
zk.ablehnen(m)
assert m.get("_fertigung_hand") and not m.get("_normteil"), m
assert m["_zukaufteil"]["vertrauen"] == zk.VORSCHLAG and "von Hand als Fertigungsteil" in m["_zukaufteil"]["grund"]
importieren([m])                                            # Kundenwechsel: bleibt Fertigungsteil
assert not m.get("_normteil"), m
zk.annehmen(m)
assert m.get("_normteil") and not m.get("_fertigung_hand") and m["_zukaufteil"]["vertrauen"] == zk.SICHER, m
n1 = importieren([teil("Nýt DIN 7337 4x8", art_grund="Norm DIN 7337 im Bauteilnamen")])[0]
assert n1.get("_normteil") and zk.nur_als_zukauf_gemessen(n1) and not zk.kann_fertigung(n1), n1
zk.ablehnen(n1)
assert n1.get("_normteil") and not n1.get("_fertigung_hand"), n1
print("OK: L1 Doch Fertigungsteil auch für voll gemessene Normteile; nur als Zukaufteil gemessene bleiben")

# L2
a = importieren([teil("Schraube M8x20:1"), teil("Hülse 12x30", huelle="12|12|30", volumen="2000"),
                 teil("Halter", huelle="40|5|60", volumen="9000")])
zk.ablehnen(a[0])                                           # Schraube: Fertigungsteil
zk.annehmen(a[2], dict(kategorie=zk.SONST, grund="von Hand"))   # Halter: Zukaufteil
neu = zk.entscheidungen(a)
assert neu == {zk.lern_schluessel(a[0]): (zk.FERTIGUNG, ""), zk.lern_schluessel(a[2]): (zk.ZUKAUF, zk.SONST)}, neu
assert zk.lern_schluessel(a[0]) == zk.lern_schluessel(teil("schraube  M8x20:7")), "Instanz und Schreibweise egal"
gelernt = zk.merken({}, neu, datetime.date(2026, 11, 21))
assert all(v[2] == "21.11.2026" for v in gelernt.values()), gelernt
assert zk.entscheidungen(a, gelernt) == {}, "unverändert: nicht neu merken (Datum bleibt)"
print("OK: L2 Entscheidungen je Name + Geometrie gemerkt, mit Datum")

# L3
b = importieren([teil("Schraube M8x20:4"), teil("Halter", huelle="40|5|60", volumen="9000"),
                 teil("Halter", huelle="40|5|80", volumen="12000"), teil("Halter-2", huelle="40|5|60", volumen="9000"),
                 teil("Hülse 12x30", huelle="12|12|30", volumen="2000")], copy.deepcopy(gelernt))
assert not b[0].get("_normteil") and "am 21.11.2026 von Hand als Fertigungsteil" in b[0]["_zukaufteil"]["grund"], b[0]
assert b[1].get("_normteil") == zk.SONST and "wie am 21.11.2026 von Hand bestätigt" in b[1]["_zukaufteil"]["grund"]
assert not b[2].get("_normteil") and not b[3].get("_normteil"), "andere Geometrie bzw. anderer Name: wie gemessen"
assert b[4] == importieren([teil("Hülse 12x30", huelle="12|12|30", volumen="2000")])[0], "nicht entschieden: gleich"
assert zk.entscheidungen(b, gelernt) == {}, "angewendetes Gelerntes ist keine neue Entscheidung"
zk.ablehnen(b[1])                                           # diesmal anders entschieden: gilt ab jetzt
assert zk.entscheidungen(b, gelernt) == {zk.lern_schluessel(b[1]): (zk.FERTIGUNG, "")}
print("OK: L3 nächster Import wie entschieden (Datum im Grund), andere Geometrie/Name unverändert")


# L4
class DB:
    nur_lesen = None

    def __init__(self, w):
        self.w = w

    def einstellung(self, n):
        return json.loads(json.dumps(self.w.get(n)))

    def einstellung_setzen(self, n, v):
        self.w[n] = v


db = DB({zk.GELERNT: gelernt})
zeilen = [e for e in lernen.uebersicht(db, mit_kennwerten=False) if e["quelle"] == lernen.STEP_ZUKAUF]
assert len(zeilen) == 2 and all(e["gelernt"] and e["vergessen"] for e in zeilen), zeilen
assert any("als Fertigungsteil" in e["was"] for e in zeilen) and any("Zukaufteil (Normteil)" in e["was"] for e in zeilen)
lernen.vergessen(db, next(e for e in zeilen if zk.FERTIGUNG in e["was"]))
rest = [k for k, v in db.w[zk.GELERNT].items() if v]
assert rest == [zk.lern_schluessel(a[2])], db.w
assert lernen.STEP_ZUKAUF == zk.GELERNT and zk.GELERNT in lernen.EINSTELLUNGEN_GETEILT
gemischt = json.loads(lernen.mischen(zk.GELERNT, json.dumps({"x": [zk.ZUKAUF, "", "1.1.2026"]}),
                                     json.dumps({"y": [zk.FERTIGUNG, "", "2.1.2026"]})))
assert set(gemischt) == {"x", "y"}, gemischt
print("OK: L4 Lernzentrale zeigt und vergisst, Abgleich mischt je Eintrag")

# L5
auf = zk.aufteilung([dict(profilform="Rundrohr"), dict(profilform="Rundrohr"), dict(profilform="Blech"),
                     dict(bauteiltyp="Drehteil", profilform="Drehteil"), dict(_normteil="Schraube"),
                     dict(profilform="Rundstahl", _zukaufteil=dict(vertrauen=zk.VORSCHLAG)), dict(fehler="x")])
assert list(auf.items()) == [("Rohrlaser-Teile", 2), ("Bleche/Kantteile (Zukauf)", 1), ("Dreh-/Frästeile (Zukauf)", 1),
                             ("Normteile/Zukaufteile", 1), ("ungeklärt (Vorschlag)", 1)], auf
print("OK: L5 Aufteilung Rohrlaser-Teile / Bleche / Dreh-Frästeile / Normteile / ungeklärt")
print("Alle Tests bestanden.")
