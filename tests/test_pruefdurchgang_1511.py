"""Prüfdurchgang vor dem Rollout am 20.11.2026 (Patrick 15.11.2026, Vorschlag N1).

Prüft die gefundenen Fehler und den ganzen Ablauf über zwei Arbeitsplätze:
- Knöpfe „CSV exportieren“ / „CSV importieren …“ (Kunden) und „RP-Profile aus MegaCAD laden …“ (Profile) öffnen die
  Dateiauswahl; vorher kam vom Knopf ein False als Pfad an (Absturz bzw. RP-Knopf tat nichts);
- im Lesemodus (ab 20.11. ohne gültige Lizenz) gilt ein abgewiesener Schreibversuch der Datenschicht (NurLesen, auch
  PostgreSQL) als Lesemodus-Hinweis statt als Programmfehler;
- Benutzerverwaltung: wer Angebote nicht bearbeiten darf (z. B. Mitarbeiter Produktion), legt weder über die
  Startseite noch über das Menü (Neue Fassung) ein Angebot an; ohne „Angebote sehen“ zeigt die Startseite keine
  Angebote und Vertriebszahlen;
- Ablauf Angebot → Auftrag → AV → Produktion → QS → Auslieferung → Abschluss über zwei Arbeitsplätze mit gemeinsamem
  Ordner, danach Nummern, die zwei Plätze ohne Ordner gleichzeitig vergeben haben, eindeutig.

Aufruf: python tests/test_pruefdurchgang_1511.py
"""
import os
import shutil
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path[:0] = [str(HIER.parent / "programm"), str(HIER)]
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox, QPushButton, QWidget  # noqa: E402

from rohrlaser import (auftraege as au, auftrag_av as av, auftrag_produktion as pr, auftrag_qs as qs,  # noqa: E402
                       db_verbindung, protokoll, rollen, teilen)
from rohrlaser.datenbank import Datenbank, Lesemodus  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def ok(t):
    print("OK    ", t)


app = QApplication.instance() or QApplication([])
for _n in ("information", "warning", "critical", "question"):
    setattr(QMessageBox, _n, staticmethod(lambda *a, **k: QMessageBox.No))
tmp = Path(tempfile.mkdtemp())


def knopf(f, text, tabelle):
    seiten = [w for w in f.findChildren(QWidget) if getattr(getattr(w, "t", None), "name", None) == tabelle]
    treffer = [b for s in seiten for b in s.findChildren(QPushButton) if b.text() == text]
    assert treffer, text
    return treffer[0]


# ------------------------------------------------------------------ 0 Knopf-Signal an Methode mit Vorgabe-Argument
# clicked/triggered/toggled übergeben checked (True/False) als erstes Argument: eine Methode mit Vorgabe wie
# pfad=None bekäme False. Solche Methoden nur über lambda verbinden (Fund im Prüfdurchgang: Kunden-CSV, RP-Profile).
import ast  # noqa: E402

FREI = ("checked", "an", "_", "ein", "geprueft", "_checked", "haken", "_c", "zustand", "sichtbar", "offen", "wert")
klassen, baeume = {}, {}
for datei in (HIER.parent / "programm").rglob("*.py"):
    baeume[datei] = ast.parse(datei.read_text(encoding="utf-8"))
    for c in ast.walk(baeume[datei]):
        if isinstance(c, ast.ClassDef):
            klassen.setdefault(c.name, []).append(c)


def methoden(c, tiefe=0):
    m = {n.name: n for n in c.body if isinstance(n, ast.FunctionDef)}
    for b_ in c.bases if tiefe < 4 else ():
        for bc in klassen.get(getattr(b_, "id", getattr(b_, "attr", None)), []):
            for k, v in methoden(bc, tiefe + 1).items():
                m.setdefault(k, v)
    return m


funde = []
for datei, baum in baeume.items():
    for c in (x for x in ast.walk(baum) if isinstance(x, ast.ClassDef)):
        m = methoden(c)
        for n in ast.walk(c):
            if not (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "connect"
                    and n.args and isinstance(n.func.value, ast.Attribute)
                    and n.func.value.attr in ("clicked", "triggered", "toggled")):
                continue
            arg = n.args[0]
            if not (isinstance(arg, ast.Attribute) and isinstance(arg.value, ast.Name) and arg.value.id == "self"):
                continue
            d = m.get(arg.attr)
            namen = [x.arg for x in d.args.args][1:] if d else []
            if namen and not d.args.vararg and len(namen) <= len(d.args.defaults) and namen[0] not in FREI:
                funde.append(f"{datei.relative_to(HIER.parent)}:{n.lineno} self.{arg.attr}({namen[0]}=…)")
assert not funde, "Signal übergibt checked an ein Vorgabe-Argument:\n" + "\n".join(funde)
ok(f"kein Knopf-Signal übergibt checked an ein Vorgabe-Argument ({len(baeume)} Dateien geprüft)")

# ------------------------------------------------------------------ 1 Knöpfe mit Dateiauswahl
db = Datenbank(tmp / "eins" / "rohrlaser.db")
f = Hauptfenster(db, tmp / "eins", stumm=True)
db.neu("kunden", dict(kundennr="10023", name="Becker GmbH"))
ziel = tmp / "Kunden.csv"
gefragt = []


def speichern(*a, **k):
    gefragt.append("speichern")
    return str(ziel), ""


def oeffnen_csv(*a, **k):
    gefragt.append("öffnen")
    return "", ""                         # abgebrochen: nichts passiert, kein Fehler


rp_dateien = sorted(str(p) for p in (HIER / "rp").glob("*.mac"))[:2]


def oeffnen_mac(*a, **k):
    gefragt.append("mac")
    return rp_dateien, ""


QFileDialog.getSaveFileName = staticmethod(speichern)
QFileDialog.getOpenFileName = staticmethod(oeffnen_csv)
QFileDialog.getOpenFileNames = staticmethod(oeffnen_mac)
fehler_vorher = []
alt_haken = sys.excepthook
sys.excepthook = lambda *a: fehler_vorher.append(a)
knopf(f, "CSV exportieren", "kunden").click()
knopf(f, "CSV importieren …", "kunden").click()
db.con.execute("DELETE FROM profile WHERE profil_id LIKE 'RP %'")
db.con.commit()
knopf(f, "RP-Profile aus MegaCAD laden …", "profile").click()
app.processEvents()
sys.excepthook = alt_haken
assert not fehler_vorher, fehler_vorher
assert gefragt == ["speichern", "öffnen", "mac"], gefragt
assert "Becker GmbH" in ziel.read_text(encoding="utf-8")
assert db.con.execute("SELECT COUNT(*) FROM profile WHERE profil_id LIKE 'RP %'").fetchone()[0] == len(rp_dateien)
ok("Kunden-CSV und RP-Profile: Knöpfe öffnen die Dateiauswahl, Export geschrieben, RP-Profile eingelesen")

# ------------------------------------------------------------------ 2 Lesemodus: Datenschicht = Hinweis
db.lesemodus("Lizenz abgelaufen (Test)")
try:
    db.con.execute("INSERT INTO einstellungen (name, wert) VALUES ('x', 'y')")
    raise AssertionError("im Lesemodus geschrieben")
except db_verbindung.NurLesen as e:
    assert protokoll.ist_lesemodus(e), e
assert protokoll.ist_lesemodus(Lesemodus("Lesemodus – Test"))
assert not protokoll.ist_lesemodus(ValueError("anderer Fehler"))
f.lesemodus_anwenden()
assert not f.datei_aktionen["Neue Fassung des Angebots"].isEnabled()
db.lesemodus("")
ok("Lesemodus: NurLesen der Datenschicht gilt als Lesemodus (kein Fehlerfenster), Neue Fassung im Menü aus")
f.close()

# ------------------------------------------------------------------ 3 Rollen: Mitarbeiter Produktion
po = tmp / "rollen"
db3 = Datenbank(po / "rohrlaser.db")
db3.einstellung_setzen("benutzer_kuerzel", "PB")
f3 = Hauptfenster(db3, po, stumm=True)
a0 = db3.angebot_neu(dict(kunde="Becker GmbH", kundennr="10023"))
anzahl = lambda: db3.con.execute("SELECT COUNT(*) FROM angebote").fetchone()[0]  # noqa: E731
rollen.benutzer_setzen(db3, "PB", "Patrick", [rollen.ADMIN])
rollen.benutzer_setzen(db3, "WS", "Werkstatt", [rollen.WERKSTATT])
rollen.zugang_setzen(db3, "WS", pin="1234")
assert f3.benutzer_anmelden("WS", "1234")
vorher = anzahl()
assert not any(b.isEnabled() for b in f3.start.angebote_knoepfe)
assert f3.start.angebote_karte.isHidden() and f3.start.kacheln.isHidden() and f3.start.pipeline.isHidden()
assert f3.angebote.neu() is None and f3.angebote.neu_aus_step([]) is None and f3.angebote.kopieren() is None
assert f3.angebote.neue_fassung(a0) is None
assert not f3.datei_aktionen["Neue Fassung des Angebots"].isEnabled()
f3.datei_aktionen["Neue Fassung des Angebots"].trigger()
assert not f3.kuerzel_aktionen["optimieren"].isEnabled()
assert anzahl() == vorher, (anzahl(), vorher)
# Kalkulation darf wieder alles
rollen.benutzer_setzen(db3, "KA", "Kalkulation", [rollen.KALKULATION])
rollen.zugang_setzen(db3, "KA", pin="5678")
assert f3.benutzer_anmelden("KA", "5678")
assert all(b.isEnabled() for b in f3.start.angebote_knoepfe) and not f3.start.angebote_karte.isHidden()
assert f3.datei_aktionen["Neue Fassung des Angebots"].isEnabled() and f3.kuerzel_aktionen["optimieren"].isEnabled()
f3.angebote.neu()
assert anzahl() == vorher + 1
f3.close()
ok("Rollen: Mitarbeiter Produktion legt kein Angebot an und sieht keine Angebote/Zahlen auf der Startseite; "
   "Kalkulation wieder frei")

# ------------------------------------------------------------------ 4 Ablauf über zwei Arbeitsplätze
gem = tmp / "Gemeinsam"
gem.mkdir()


def platz(name, k):
    d = Datenbank(tmp / name / "rohrlaser.db")
    d.einstellung_setzen("benutzer_name", name)
    d.einstellung_setzen("benutzer_kuerzel", k)
    d.einstellung_setzen("teilen_ordner", str(gem))
    return d


pb, mk = platz("Patrick", "PB"), platz("Martin", "MK")
teilen.abgleichen(pb, modus=teilen.UEBERNEHMEN)
teilen.abgleichen(mk, modus=teilen.UEBERNEHMEN)
a = pb.angebot_neu(dict(kunde="Becker GmbH", kundennr="10023", stange=6000, maschine="T03"))
for n, art in enumerate(("BG-100", "BG-101")):
    pb.position_neu(a, dict(pos=n + 1, artikel=art, bezeichnung="Teil", profil_id="RR 42,4x2,0",
                            werkstoff_id="S235-10219", laenge=1250 - 300 * n, stueck=50, schneidweg=300, einstiche=2))
pb.vorgang_setzen(a, "Beauftragt")
uid = au.uebernehmen(pb, [a])
teilen.abgleichen(pb)
teilen.abgleichen(mk)
assert au.auftrag(mk, uid)["nummer"] == au.nummer(pb, uid) and au.MUSTER.match(au.nummer(pb, uid))
assert av.alle_uebernehmen(mk, uid) == 2
av.freigeben(mk, uid, grund="Prüfdurchgang")
for p in au.auftrag(mk, uid)["positionen"]:
    for ag in p["arbeitsgaenge"]:
        if ag.get("aktiv", True):
            pr.rueckmelden(mk, uid, p["uid"], ag["uid"], pr.ABGESCHLOSSEN, menge=p["menge"])
    qs.pruefung_erfassen(mk, uid, p["uid"], p["menge"], p["menge"], pruefer="MK")
qs.status_nachziehen(mk, uid)
assert au.auftrag(mk, uid)["status"] == au.FERTIG
teilen.abgleichen(mk)
teilen.abgleichen(pb)
ap = au.auftrag(pb, uid)
assert ap["status"] == au.FERTIG, ap["status"]
qs.liefern(pb, uid, {p["uid"]: p["menge"] for p in ap["positionen"]})
qs.abschliessen(pb, uid)
teilen.abgleichen(pb)
teilen.abgleichen(mk)
assert au.auftrag(mk, uid)["status"] == au.auftrag(pb, uid)["status"] == au.ABGESCHLOSSEN
assert au.pruefen(pb) == [] and au.pruefen(mk) == []
ok("Ablauf Angebot → Auftrag → AV → Produktion → QS → Auslieferung → Abschluss über zwei Arbeitsplätze")

# beide ohne gemeinsamen Ordner: vorläufige Nummern, danach eindeutig
shutil.move(str(gem), str(tmp / "weg"))
neu = {}
for d, k in ((pb, "PB"), (mk, "MK")):
    x = d.angebot_neu(dict(kunde="Offline", kundennr="1"))
    d.position_neu(x, dict(pos=1, artikel="Z", profil_id="RR 42,4x2,0", werkstoff_id="S235-10219", laenge=500,
                           stueck=5))
    d.vorgang_setzen(x, "Beauftragt")
    neu[k] = (x, au.uebernehmen(d, [x]))
    assert d.angebot(x)["nummer"].startswith(f"V-{k}-") and au.nummer(d, neu[k][1]).startswith(f"AU-V-{k}-")
shutil.move(str(tmp / "weg"), str(gem))
for _ in range(2):
    teilen.abgleichen(pb)
    teilen.abgleichen(mk)
for d in (pb, mk):
    nummern = [r[0] for r in d.con.execute("SELECT nummer FROM angebote")]
    assert len(nummern) == len(set(nummern)) == 3 and not any(n.startswith("V-") for n in nummern), nummern
    au_nr = [r[0] for r in d.con.execute("SELECT nummer FROM auftrag_kopf")]
    assert len(au_nr) == len(set(au_nr)) == 3 and all(au.MUSTER.match(n) for n in au_nr), au_nr
ok("ohne gemeinsamen Ordner vergebene Angebots- und Auftragsnummern sind nach dem Abgleich endgültig und eindeutig")
pb.schliessen()
mk.schliessen()
print("Alle Prüfungen bestanden.")
