"""Plausibilitätsprüfung beim STEP-Import (Auftrag Patrick 21.11.2026 „KI-gestützten STEP-Import analysieren,
optimieren und erweitern“, 3C; „Alles einbauen nach Empfehlungen“).

- P1 Gemessene Testteile: P09 exzentrisch (Wand 1,61–2,39 mm, Innenmaß), P10 Wand 2 und 3 mm, I03 Flächenmodell
  (nicht geschlossen); T01 RR 42,4 × 2 ohne Befund
- P2 Regeln an Messwerten: Normwand, Stammdatenwand, Wandverhältnis, Länge, Sonderkontur; Fehlerzeile ohne Befund
- P3 Jeder Befund nennt seine Datenbasis; Messwerte bleiben unverändert (keine Maße geändert/geschätzt)
- P4 Ampel: gelb mit Grund „Plausibilität: …“ (nie rot); „Passt“ macht grün; Prüfdialog-Zeile
- P5 markieren übersteht kaputte Werte; zusammenfassung zählt je Regel
- P6 Name gegen Messung: „QR40x40x2“ gemessen 3 mm meldet, Messung gilt; keine Fehlalarme bei RR42-4x2, C-Profil
- P7 Übernehmen speichert die Befunde (step_merkmale), die Qualitäts-KI meldet sie je Position mit Zahlen für den
  Faktencheck; „Passt“ (geprüft) meldet nichts

Aufruf: python tests/test_step_plausibel.py
"""
import copy
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent / "programm"))
from rohrlaser import step_plausibel as pl  # noqa: E402
from rohrlaser import step  # noqa: E402

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


TMP = Path(tempfile.mkdtemp())


def messen(dateien):
    """Messung als eigener Prozess wie im Programm (STEP-Import.exe)."""
    aus = TMP / f"m{len(list(TMP.iterdir()))}.txt"
    subprocess.run([sys.executable, str(HIER.parent / "programm" / "step_messung" / "step_messen.py"), "--ausgabe",
                    str(aus), "--json", str(aus.with_suffix(".json"))] + [str(p) for p in dateien],
                   check=True, capture_output=True, timeout=900)
    return step.lies_messwerte(aus)


DATEIEN = [HIER / "step_profile" / "P09_RR42-4_exzentrisch_L800.step",
           HIER / "step_profile" / "P10_RE60x40_Wand2und3_L600.step",
           HIER / "step_import" / "I03_QR40x2_L800_Flaechenmodell.step",
           HIER / "step" / "T01_RR42-4x2_L1250.step"]
GEMESSEN = {Path(m["datei"]).name[:3]: m for m in messen(DATEIEN)}


def regeln(m, profile=None):
    return sorted(b["regel"] for b in pl.pruefen(m, profile))


ROHR = dict(datei="x.step", bauteiltyp="Profil", profilform="Quadratrohr", abm_a="40", abm_b="40", wandstaerke="2",
            laenge="800", koerperart="Volumenkörper", gueltig="1")


@fall("P1 Testteile: P09/P10 Wand ungleich + Innenmaß, I03 nicht geschlossen, T01 ohne Befund")
def _():
    assert set(GEMESSEN) == {"P09", "P10", "I03", "T01"}, list(GEMESSEN)
    assert regeln(GEMESSEN["P09"]) == [pl.W_INNEN, pl.W_STREU], pl.pruefen(GEMESSEN["P09"])
    assert regeln(GEMESSEN["P10"]) == [pl.W_INNEN, pl.W_STREU], pl.pruefen(GEMESSEN["P10"])
    assert regeln(GEMESSEN["I03"]) == [pl.OFFEN], pl.pruefen(GEMESSEN["I03"])
    assert regeln(GEMESSEN["T01"]) == [], pl.pruefen(GEMESSEN["T01"])
    streu = next(b for b in pl.pruefen(GEMESSEN["P10"]) if b["regel"] == pl.W_STREU)
    assert streu["basis"]["minimum"] < 2.1 and streu["basis"]["maximum"] > 2.9, streu


@fall("P2 Regeln: Normwand, Stammdaten, Verhältnis, Länge, Sonderkontur; Fehlerzeile ohne Befund")
def _():
    assert regeln(ROHR) == []
    assert regeln(dict(ROHR, wandstaerke="2.2")) == [pl.W_NORM]
    profile = [dict(form="Quadratrohr", a=40, b=40, wand=3), dict(form="Quadratrohr", a=40, b=40, wand=4)]
    assert regeln(ROHR, profile) == [pl.W_STAMM]                      # Stammdaten gehen vor der Normreihe
    assert regeln(dict(ROHR, wandstaerke="3"), profile) == []
    assert regeln(dict(ROHR, wandstaerke="12")) == [pl.W_VERH]
    assert regeln(dict(ROHR, abm_a="400", abm_b="400", wandstaerke="2")) == [pl.W_VERH]
    assert regeln(dict(ROHR, laenge="13000")) == [pl.LANG]
    kontur = json.dumps([dict(art="Sonderkontur", z=120, schnittlaenge=88.5), dict(art="Bohrung", z=300)])
    b = pl.pruefen(dict(ROHR, konturen_liste=kontur))
    assert [x["regel"] for x in b] == [pl.KONTUR] and b[0]["basis"]["z"] == 120, b
    assert regeln(dict(ROHR, fehler="nicht lesbar", wandstaerke="2.2")) == []
    assert regeln(dict(ROHR, bauteiltyp="Blech", wandstaerke="2.2")) == []     # nur Profile


@fall("P3 Datenbasis je Befund; Messwerte bleiben unverändert")
def _():
    for m in GEMESSEN.values():
        vorher = copy.deepcopy(m)
        pl.markieren([m])
        for b in m["_plausibel"]:
            assert b["basis"] and b["titel"] and b["text"] and b["stufe"] in ("Hinweis", "prüfen"), b
        m.pop("_plausibel")
        assert m == vorher, [k for k in m if m[k] != vorher.get(k)]


@fall("P4 Ampel gelb mit Grund „Plausibilität“, nie rot; „Passt“ macht grün; Prüfdialog-Zeile")
def _():
    m = dict(GEMESSEN["P10"])
    gruen = dict(GEMESSEN["T01"])
    pl.markieren([m, gruen])
    farbe, gruende = step.ampel(m)
    assert farbe == "gelb" and any(g.startswith("Plausibilität: ") for g in gruende), (farbe, gruende)
    assert step.ampel(gruen)[0] == "gruen", step.ampel(gruen)
    m["_geprueft"] = True
    assert step.ampel(m)[0] == "gruen", step.ampel(m)
    i03 = dict(GEMESSEN["I03"])
    pl.markieren([i03])
    assert step.ampel(i03)[0] != "rot", step.ampel(i03)
    from rohrlaser import step_dialog
    assert "Plausibilität:" in step_dialog._analyse_zeile(m)
    assert "Plausibilität" not in step_dialog._analyse_zeile(gruen)


@fall("P5 markieren übersteht kaputte Werte; Gründe gekürzt; zusammenfassung je Regel")
def _():
    kaputt = dict(ROHR, wandstaerke="abc", abm_a=None, wand_messungen="1:2:x|::", konturen_liste="{kein json")
    liste = pl.markieren([kaputt, dict(ROHR, wandstaerke="2.2"), dict(ROHR, wandstaerke="2.2", laenge="20000")])
    assert all(isinstance(m["_plausibel"], list) for m in liste)
    assert pl.zusammenfassung(liste) == {pl.W_NORM: 2, pl.LANG: 1}, pl.zusammenfassung(liste)
    viele = {"_plausibel": [dict(text=f"t{i}") for i in range(5)]}
    assert pl.gruende(viele) == ["Plausibilität: t0; t1; t2; 2 weitere"], pl.gruende(viele)
    assert pl.gruende({}) == []


@fall("P6 Name gegen Messung: Wand aus dem Namen nur als Hinweis, keine Fehlalarme")
def _():
    m = dict(ROHR, datei="Kunde_QR40x40x2_L800.step", wandstaerke="3")
    b = [x for x in pl.pruefen(m) if x["regel"] == pl.NAME]
    assert len(b) == 1 and b[0]["basis"]["wand_name"] == 2 and b[0]["basis"]["wand"] == 3, b
    assert m["wandstaerke"] == "3"                                   # die Messung gilt, nichts übernommen
    assert not pl.name_vergleich(dict(ROHR, datei="QR40x40x3.step", wandstaerke="3"))
    rr = dict(ROHR, profilform="Rundrohr", abm_a="42.4", abm_b="0", wandstaerke="2")
    assert not pl.name_vergleich(dict(rr, datei="T01_RR42-4x2_L1250.step"))
    assert pl.name_vergleich(dict(rr, datei="RR33-7x2-6.step", abm_a="33.7"))[0]["basis"]["wand_name"] == 2.6
    assert not pl.name_vergleich(dict(ROHR, datei="C100x50x20x3.step", abm_a="100", abm_b="50"))
    assert not pl.name_vergleich(dict(ROHR, datei="QR50x50x2.step"))            # anderes Profil: kein Vergleich
    assert regeln(GEMESSEN["T01"]) == []


@fall("P7 Übernehmen speichert Befunde; Qualitäts-KI meldet sie mit Zahlen; „Passt“ meldet nichts")
def _():
    from rohrlaser import ki_agenten, ki_orchestrator, step_pruefung
    m = dict(GEMESSEN["P10"])
    pl.markieren([m])
    d = json.loads(step_pruefung.speicherwert(m))
    assert [b["regel"] for b in d["plausibel"]] == [b["regel"] for b in m["_plausibel"]], d.get("plausibel")

    class Seite:
        kopf, ergebnis, k = {"nummer": "T"}, None, None
        positionen = [dict(pos=1, step_merkmale=json.dumps(d)),
                      dict(pos=2, step_merkmale=json.dumps(dict(d, geprueft=dict(am="x"))))]
    ctx = ki_agenten.Kontext(None, seite=Seite())
    out = ki_agenten.AGENT["qualitaet"]._import(ctx)
    pl_out = [b for b in out if b["quelle"].startswith("STEP-Plausibilität")]
    assert len(pl_out) == len(m["_plausibel"]) and all(b["ziel"] == "pos:0" for b in out), out
    for b in pl_out:
        ok, fremd = ki_orchestrator.faktencheck(b["text"], " ".join(str(v) for v in b["zahlen"].values()))
        assert ok, (b["text"], fremd)


print("ALLE OK" if not fehler else f"{fehler} FEHLER")
sys.exit(1 if fehler else 0)
