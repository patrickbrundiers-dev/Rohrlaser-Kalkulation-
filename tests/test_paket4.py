"""Optimierungsplan 04.11.2026, Paket 4:
- E3 Speicher messen: Arbeitsspeicher im Zeitwächter (jeder Eintrag, neue Höchststände, Zusammenfassung),
- C3 aus Korrekturen lernen: anderes Profil als gemessen wird Regel des Kunden und beim nächsten Import automatisch
  angewendet (gelb in der Ampel, zurückstellbar; andere Form = Profilform umgestellt, Messwerte und Konturen bleiben).
Aufruf: python tests/test_paket4.py
"""
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm" / "step_messung"))
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import step_messen  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication([])
from rohrlaser import step, stil, tempo  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402

stil.anwenden(app, "hell")
tmp = Path(tempfile.mkdtemp())


def ok(text):
    print("OK    ", text)


# ------------------------------------------------------------------ E3 Speicher
mb = tempo.speicher_mb()
assert mb and 10 < mb < 100000, mb
geschrieben = []
w = tempo.Waechter(None, kontext=lambda: "Angebot › Editor", schreiben=geschrieben.append)
assert w.speicher_pruefen(400) == "Speicher 400 MB | Ort: Angebot › Editor"
assert w.speicher_pruefen(450) is None                      # weniger als 100 MB mehr: nichts
assert w.speicher_pruefen(520).startswith("Speicher 520 MB")
assert "Speicher: " in w.eintragen(0.8)
ok(f"E3 Arbeitsspeicher {mb:.0f} MB; neue Höchststände ab +100 MB mit Ort, jeder langsame Schritt mit Speicher")
ordner = tmp / "Protokoll"
ordner.mkdir()
(ordner / tempo.DATEI).write_text(
    "2026-11-05 08:00:00,000 Speicher 410 MB | Ort: Start\n"
    "2026-11-05 09:00:00,000 0.8 s | Ort: Angebot › Positionen | Speicher: 600 MB\n"
    "2026-11-05 10:00:00,000 Speicher 720 MB | Ort: Angebot 2026-00002 › Rohr-Editor\n", encoding="utf-8")
assert tempo.speicher_hoechststand(ordner) == (720, "2026-11-05 10:00:00,000", "Angebot 2026-00002 › Rohr-Editor")
text = tempo.auswerten(ordner)
assert text.startswith("1 langsame Schritte") and "Arbeitsspeicher höchstens 720 MB" in text, text
assert tempo.lesen(ordner)[0]["speicher"] == "600 MB"
ok("E3 Support-Paket (tempo.txt) nennt den höchsten Arbeitsspeicher mit Ort")

# ------------------------------------------------------------------ C3 Regeln aus Korrekturen
db = Datenbank(tmp / "rohrlaser.db")
k = db.kontext()
netze = Path(tempfile.mkdtemp(dir=tmp))
roh = [dict(zip(step_messen.SPALTEN, z)) for z in step_messen.zeilen(HIER / "step_anbau" / "A01_RE60x40x3_ohne_Anbau.step",
                                                                      netze)]
gemessen = step.profil_vorschlag(roh[0], k.profile)
assert gemessen == "RE 60x40x3", gemessen
anders = next(p for p, z in k.profile.items() if z.get("form") == "Rechteckrohr" and p != gemessen)
quadrat = next(p for p, z in k.profile.items() if z.get("form") == "Quadratrohr")


def neu():
    return [dict(m) for m in roh]


# erster Import: keine Regel, nur das gemessene Profil wird gemerkt
mw = neu()
assert step.profile_gelernt_anwenden(mw, {}, k.profile) == 0 and mw[0]["_profil_gemessen"] == gemessen
mw[0]["_profil"], mw[0]["_uebernehmen"] = anders, True       # im Prüfdialog anderes Profil gewählt
regeln = step.profile_gelernt_merken({}, mw, k.profile)
assert regeln == {gemessen: anders}, regeln
# nächster Import beim selben Kunden: automatisch, gelb mit Grund
mw = neu()
assert step.profile_gelernt_anwenden(mw, regeln, k.profile) == 1
assert mw[0]["_profil"] == anders and mw[0]["profilform"] == "Rechteckrohr"
st, gr = step.ampel(mw[0])
assert st == "gelb" and gr == [f"Regel des Kunden: {anders} statt gemessen {gemessen}"], (st, gr)
# zurückgestellt (wieder das gemessene gewählt): Regel weg
mw[0]["_profil"], mw[0]["_uebernehmen"] = gemessen, True
assert step.profile_gelernt_merken(regeln, mw, k.profile) == {}
# von Hand gewählt bleibt, auch wenn eine Regel passt
mw = neu()
mw[0]["_profil_gemessen"], mw[0]["_profil"] = gemessen, "RE 80x40x3"
assert step.profile_gelernt_anwenden(mw, regeln, k.profile) == 0 and mw[0]["_profil"] == "RE 80x40x3"
# andere Form: Profilform umgestellt, Messwerte bleiben; Rücknahme (anderer Kunde) stellt alles wieder her
mw = neu()
vorher = {f: mw[0][f] for f in ("abm_a", "abm_b", "wandstaerke", "laenge", "schneidweg", "konturen_liste")}
assert step.profile_gelernt_anwenden(mw, {gemessen: quadrat}, k.profile) == 1
assert mw[0]["profilform"] == "Quadratrohr" and mw[0]["_form_gemessen"] == "Rechteckrohr"
assert {f: mw[0][f] for f in vorher} == vorher
assert "Art von Hand geändert" not in " ".join(step.ampel(mw[0])[1])
step.profile_gelernt_zuruecknehmen(mw)
assert mw[0]["profilform"] == "Rechteckrohr" and mw[0]["_profil"] == gemessen and "_profil_regel" not in mw[0]
# Regel auf ein Profil, das es nicht mehr gibt: nichts
mw = neu()
assert step.profile_gelernt_anwenden(mw, {gemessen: "RE 999x9x9"}, k.profile) == 0
ok(f"C3 Regel {gemessen} → {anders}: gemerkt, beim nächsten Import automatisch (gelb), zurückstellbar, "
   "Handwahl bleibt, andere Form ohne neue Messwerte")

# ------------------------------------------------------------------ C3 im Prüfdialog
from rohrlaser.step_dialog import StepPruefDialog  # noqa: E402

mw = neu()
step.profile_gelernt_anwenden(mw, regeln, k.profile)
d = StepPruefDialog(None, mw, k, "S235-10219", 1)
z = d.zeilen[0]
assert z.pr.currentText() == anders, z.pr.currentText()
assert z.ampel == "gelb" and "Regel des Kunden" in z.it.text(d.SP_HINWEIS), z.it.text(d.SP_HINWEIS)
z.pr.setCurrentText(gemessen)                    # zurückstellen im Fenster
d.werte_schreiben()
assert step.profile_gelernt_merken(regeln, mw, k.profile) == {}
d.close()
ok("C3 Prüffenster: Profil der Regel vorbelegt, Hinweis „Regel des Kunden …“, Zurückstellen löscht die Regel")

# ------------------------------------------------------------------ C3 im Angebot (ganzer Ablauf, stumm)
from rohrlaser.fenster import Hauptfenster  # noqa: E402

f = Hauptfenster(db, stumm=True)
a = db.angebot_neu(dict(kunde="Kunde Regel", kundennr="K-10045", maschine="T11", stange=6000))
db.einstellung_setzen(step.PROFIL_GELERNT, {"K-10045": {gemessen: anders}, "K-99999": {gemessen: quadrat}})
s = f.angebot_oeffnen(a)
s.step_importieren([str(HIER / "step_anbau" / "A01_RE60x40x3_ohne_Anbau.step")], None, 1)
pos = [p for p in db.positionen(a) if p.get("profil_id")]
assert [p["profil_id"] for p in pos] == [anders], [p.get("profil_id") for p in pos]
f.close()
ok("C3 Angebot: STEP-Import beim Kunden K-10045 nimmt die Regel (Position mit dem Profil der Regel)")
print("Alle Prüfungen Paket 4 bestanden.")
