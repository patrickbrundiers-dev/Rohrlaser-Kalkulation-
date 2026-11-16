"""Paket 11 (Vorschläge K1–K4, Patrick 08.11.2026 „Alle Empfehlungen“):
K1 Angebots-Check: „Erledigen“ bei Punkten, die das Programm selbst lösen kann, „Alles Automatische erledigen“.
K2 Prüfdialog: Rechtsklick am Teil mit „Passt“, „Nur dieses Teil aufteilen“ und Art.
K3 Hinweis „ungeprüft (gelb)“ öffnet die STEP-Merkmale der Reihe nach („Passt, nächstes“, „Überspringen“).
K4 Preisliste: Lieferant wählbar, vorhandene Preise alt → neu aktualisieren.

Aufruf: python tests/test_paket11.py
"""
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER))
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER.parent / "programm" / "step_messung"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication, QDialog, QMenu  # noqa: E402

import beispiel_angebot  # noqa: E402
from rohrlaser import angebot_check as ac, angebot_check_dialog, step, step_pruefung, zukauf  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402
from rohrlaser.normteil_preise import NormteilPreisSeite, ek_aktuell  # noqa: E402

TMP = Path(tempfile.mkdtemp())
app = QApplication.instance() or QApplication([])


def ok(text):
    print("OK    ", text)


# ------------------------------------------------------------------ K1 Erledigen
db = Datenbank(TMP / "rohrlaser.db")
f = Hauptfenster(db, TMP, stumm=True)
a = beispiel_angebot.anlegen(db)
s = f.angebot_oeffnen(a)
assert s.optimieren()
db.position_aendern(db.positionen(a)[0]["id"], "stueck", 7)
s.neu_laden()
assert s.stand_optimierung() != "aktuell"
p = next(x for x in s.freigabe_punkte() if x.ziel == "optimieren")
assert p.aktion == "optimieren" and ac.erledigbar([p]) == [p]
d = angebot_check_dialog.CheckDialog(None, s.freigabe_punkte(), "Angebot erstellen", erledigen=True)
assert d.erledigen_knoepfe and d.erledigen_knoepfe[0].text() == "Erledigen"
assert not angebot_check_dialog.CheckDialog(None, s.freigabe_punkte(), "x").erledigen_knoepfe, "nur mit erledigen=True"
d.erledigen_knoepfe[0].click()
assert d.aktionen == ["optimieren"] and d.result() == QDialog.Rejected
gezeigt = []


def ausfuehren(self):
    gezeigt.append([x.text for x in self.punkte])
    if len(gezeigt) == 1:
        self.erledigen_knoepfe[0].click()
        return QDialog.Rejected
    return QDialog.Rejected


alt_exec = angebot_check_dialog.CheckDialog.exec
angebot_check_dialog.CheckDialog.exec = ausfuehren
try:
    s.check_zeigen()
finally:
    angebot_check_dialog.CheckDialog.exec = alt_exec
assert len(gezeigt) == 2 and s.stand_optimierung() == "aktuell"
assert any("Schnittplan" in t for t in gezeigt[0]) and not any("Schnittplan" in t for t in gezeigt[1]), gezeigt
ok("K1: „Erledigen“ optimiert den Schnittplan und zeigt den Check neu (ohne den erledigten Punkt)")

# ------------------------------------------------------------------ K3 ungeprüfte STEP-Teile der Reihe nach
gelb = dict(profilform="Quadratrohr", abm_a=40, wandstaerke=3, laenge=500, pruefstatus="prüfen", datei="x.step",
            koerper=1)
ids = [x["id"] for x in db.positionen(a)][:2]
for pid in ids:
    db.position_aendern(pid, "step_merkmale", step_pruefung.speicherwert(gelb))
s.neu_laden()
pk = next(x for x in s.freigabe_punkte() if "ungeprüft (gelb)" in x.text)
assert pk.ziel.startswith("stepgelb:") and len(pk.ziel.split(":")[1].split(",")) == 2, pk.ziel
fenster = []


def bedienen(d):
    fenster.append((d.pruefen_knopf.text(), d.ueberspringen_knopf.text(), d.info.text()))
    (d.pruefen_knopf if len(fenster) == 1 else d.ueberspringen_knopf).click()
    return d.result()


zeilen = [int(x) for x in pk.ziel.split(":")[1].split(",")]
assert s.step_gelb_pruefen(zeilen, dialog=bedienen) == 1
assert [x[0] for x in fenster] == ["Passt, nächstes", "Passt"] and fenster[1][1] == "Offen lassen"
assert "Gelb beim Import" in fenster[0][2] and "noch 1 ungeprüftes Teil" in fenster[0][2], fenster[0][2]
pos = {x["id"]: x for x in db.positionen(a)}
assert not step_pruefung.gelb_ungeprueft(pos[ids[0]]) and step_pruefung.gelb_ungeprueft(pos[ids[1]])
assert "1 Teil aus dem STEP-Import ungeprüft" in " ".join(x.text for x in s.freigabe_punkte())
ok("K3: „Hinspringen“ beim Hinweis zeigt die STEP-Merkmale der Reihe nach: „Passt, nächstes“ bestätigt, "
   "„Überspringen“/„Offen lassen“ lässt offen")

# ------------------------------------------------------------------ K2 Rechtsklick im Prüfdialog
import step_messen  # noqa: E402
from formen_baukasten import ohne, quader, schreibe  # noqa: E402
from rohrlaser.step_dialog import StepPruefDialog  # noqa: E402

rohr = ohne(quader(500, 40, 40), quader(500, 34, 34, 0, 3, 3))
schreibe({"A_Rohr": rohr, "B_Rohr": rohr, "Lasche": quader(146, 40, 9.5)}, TMP)
aus = TMP / "m.txt"
step_messen.main(["--ausgabe", str(aus)] + [str(TMP / f"{n}.step") for n in ("A_Rohr", "B_Rohr", "Lasche")])
werte = [dict(m) for m in step.lies_messwerte(aus)]
for m in werte:
    if "Rohr" in m["datei"]:
        m["pruefstatus"] = "prüfen"
pd = StepPruefDialog(None, werte, db.kontext(), "S235-10219", 1, zukauf_liste=[], aufteilen=lambda m: None)
pd.show()
app.processEvents()
za = next(z for z in pd.zeilen if "A_Rohr" in pd.messwerte[z.liste[0]]["datei"])
menue = QMenu()
pd._kontext_teil(menue, za)
texte = [x.text() for x in menue.actions()]
assert "Passt (1 gleiche)\tLeertaste" in texte, texte
art_menue = next(x.menu() for x in menue.actions() if x.text() == "Art")
arten = {x.text(): (x.isChecked(), x.isEnabled()) for x in art_menue.actions()}
assert arten[step.ART_PROFIL] == (True, False) and set(arten) == set(step.ART_GRUPPEN), arten
la = next(z for z in pd.zeilen if "Lasche" in pd.messwerte[z.liste[0]]["datei"])
ziel = step.ART_BLECH if step.art_gruppe(pd.messwerte[la.liste[0]]) != step.ART_BLECH else step.ART_PROFIL
pd.baum.clearSelection()
assert pd.art_kontext(la, ziel) == 1
la = next(z for z in pd.zeilen if "Lasche" in pd.messwerte[z.liste[0]]["datei"])
assert step.art_gruppe(pd.messwerte[la.liste[0]]) == ziel
assert all(step.art_gruppe(pd.messwerte[z.liste[0]]) == step.ART_PROFIL for z in pd.zeilen if "Rohr" in z.datei)
za = next(z for z in pd.zeilen if "A_Rohr" in pd.messwerte[z.liste[0]]["datei"])      # Liste neu aufgebaut
pd.passt(za)
assert za.ampel == "gruen"
werte[0]["hinweise"] = step.MEHRTEILIG_HINWEIS + " Bolzen"
werte[0]["_pfad"] = str(TMP / "A_Rohr.step")
menue = QMenu()
pd._kontext_teil(menue, next(z for z in pd.zeilen if 0 in z.liste))
assert "Nur dieses Teil aufteilen" in [x.text() for x in menue.actions()]
ok(f"K2: Rechtsklick am Teil: „Passt (1 gleiche)“, Art-Menü (aktuelle Art angehakt), Lasche → {ziel}, "
   "„Nur dieses Teil aufteilen“ bei mehreren Teilen in einem Körper")

# ------------------------------------------------------------------ K4 Lieferant und vorhandene Preise
db2 = Datenbank(TMP / "n.db")


def normteil(name, preis=None):
    werte = dict(bezeichnung=name, kategorie=step.NORMTEIL_KATEGORIE, einheit="Stück", status="aktiv",
                 aufschlag_quelle="Kategorie", angebotstext="nein", rest_lager="nein", kombiniert="nein",
                 artikeltyp=step.NORMTEIL_TYP, herkunft="STEP-Import")
    return db2.zukauf_speichern(None, werte, [dict(lieferant=None, bevorzugt="ja", preiseinheit=1,
                                                   preise=[dict(ab=1, preis=preis)] if preis else [])])


m12 = normteil("ISO 4032 M12")
m16 = normteil("ISO 4032 M16", 0.30)
m20 = normteil("ISO 4032 M20", 0.50)
meldungen = []
seite = NormteilPreisSeite(db2, lambda t, fehler=False: meldungen.append((t, fehler)))
seite.lieferant.setCurrentText("Schrauben Müller")
n, rest = seite.csv_uebernehmen("Bezeichnung;Preis\nISO 4032 M12;0,12\nISO 4032 M16;0,25\nISO 4032 M20;0,50\n")
assert n == 1 and not rest, (n, rest)
assert [x["artikel"]["id"] for x in seite.abweichend] == [m16], "M20 hat schon denselben Preis"
assert seite.aktualisieren_knopf.isVisibleTo(seite) and "(1)" in seite.aktualisieren_knopf.text()
assert "1 vorhandene Preis weicht ab" in seite.info.text(), seite.info.text()
gesehen = []


def annehmen(d):
    gesehen.append([d.tabelle.item(0, c).text() for c in range(5)])
    return QDialog.Accepted


assert seite.vorhandene_aktualisieren(dialog=annehmen) == 1
assert gesehen[0][0] == "ISO 4032 M16" and gesehen[0][2] == "0,3000" and gesehen[0][3] == "0,2500", gesehen
assert gesehen[0][4] == "-16,7 %", gesehen
assert abs(ek_aktuell(db2.zukauf_artikel(m16), "Schrauben Müller") - 0.25) < 1e-9
assert seite.speichern() == 1 and not zukauf.ek_fehlt(db2.zukauf_artikel(m12))
assert any(b.get("lieferant") == "Schrauben Müller" for b in db2.zukauf_artikel(m12)["bezuege"])
assert not seite.aktualisieren_knopf.isVisibleTo(seite)
ok("K4: Lieferant der Preisliste wird beim Speichern eingetragen; abweichender vorhandener Preis alt → neu "
   "(−16,7 %) zum Prüfen und Übernehmen, gleicher Preis bleibt")

print("Paket 11: alle Tests bestanden.")
