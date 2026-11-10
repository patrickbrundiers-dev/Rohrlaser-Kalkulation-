"""Zentrale Art-Entscheidung beim STEP-Import (Patrick 04.11.2026: „Kantteile werden als Frästeile erkannt … eine
Auswahl, dass ich immer manuell noch umentscheiden kann, ob Blech, Rohr oder Dreh-/Frästeil“; Entscheidung „Zentrale
Art-Entscheidung“, Umstellung gemerkt für alle Kunden; dazu „Richtpreis Dreh-/Frästeil überschreiben wie bei Blech“).
Alle Teile werden hier gebaut:
- A1 Fehlerkennung belegt und behoben: kurze dicke Kant-Winkel (40×40×8 × 100, 50×50×10 × 80, Biegeradius außen =
  innen + Dicke) waren Frästeile („dicke Wand, aus dem Vollen?“, Biegeradien als „Bohrungen“) – jetzt Kantteil mit
  Grund aus der Regelliste; Frästeil bleibt als Auswahl. Echte Frästeile/Drehteile bleiben es.
- A2 Jedes Teil hat alle drei Arten (Blech, Rohr/Profil, Dreh-/Frästeil): gemessen oder mit Grund nicht messbar.
- A3 Umstellen über alle drei Arten und zurück (step.art_setzen): Messwerte der Art gelten, nichts geht verloren.
- A4 Gemerkte Wahl: gleiches Teil beim nächsten Import gleich die gewählte Art, Hinweis nennt es.
- A5 Prüfdialog: Spalte Art zeigt alle drei Arten, Umstellen rechnet neu, Hinweis nennt den Grund, 3D goldgelb.
- A6 Richtpreis Dreh-/Frästeil: eigene Werte je Teil (wie Blech), „Richtpreis je Stück“ ersetzt den Preis.
- A7 Kalkulation: Rechtsklick „Art ändern …“ ersetzt die Position (Pos.-Nr., Stückzahl bleiben).

Aufruf: python tests/test_art_auswahl.py   (ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import json
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(HIER))
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER.parent / "programm" / "step_messung"))
import erzeuge_testteile as et  # noqa: E402
from formen_baukasten import ohne, quader, schreibe, zyl  # noqa: E402
from rohrlaser import drehfraes_preis as dp, step  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
import step_messen  # noqa: E402

fehler = 0


def fall(name):
    def deko(fn):
        global fehler
        try:
            fn()
            print(f"OK     {name}")
        except AssertionError as e:
            fehler += 1
            print(f"FEHLER {name}: {e}")
        return fn
    return deko


def L(a, b, t, R=None, lg=500):
    R = t if R is None else R
    return et.profil([(0, 0), (a, 0), (a, t), (t, t), (t, b), (0, b)], lg, {(0, 0): R + t, (t, t): R} if R else None)


TEILE = {   # Name: (Form, erwartete Art)
    "A01_KantL_40x40x8_kurz": (L(40, 40, 8, lg=100), "Blech gekantet"),
    "A02_KantL_50x50x10_kurz": (L(50, 50, 10, lg=80), "Blech gekantet"),
    "A03_KantL_50x50x10_R2": (L(50, 50, 10, 2, lg=80), "Blech gekantet"),
    "A04_KantL_60x40x8_lang": (L(60, 40, 8, lg=300), "Blech gekantet"),
    "A05_Fraesblock_Tasche": (ohne(quader(60, 40, 30), quader(40, 20, 10, 10, 10, 20), zyl(4, 30, 0, 8, 8)),
                              "Frästeil"),
    "A06_Platte": (quader(200, 100, 3), "Blech"),
    "A07_Rundrohr": (ohne(zyl(21.2, 400), zyl(18.6, 400)), "Rundrohr"),
}
TMP = Path(tempfile.mkdtemp())
schreibe({n: f for n, (f, _) in TEILE.items()}, TMP)


def messen(*namen):
    aus, js = TMP / "m.txt", TMP / "m.json"
    step_messen.main(["--ausgabe", str(aus), "--json", str(js), "--flachstahl-bis", "0"]
                     + [str(TMP / f"{n}.step") for n in namen])
    return step.lies_messwerte(aus), json.loads(js.read_text(encoding="utf-8"))


MW, JS = messen(*TEILE)
JE = {Path(m["datei"]).stem: m for m in MW}


@fall("A1 kurze dicke Kant-Winkel sind Kantteile (nicht Frästeil), Grund aus der Regelliste; Frästeil bleibt Auswahl")
def _():
    for n, (_, art) in TEILE.items():
        assert JE[n]["profilform"] == art, (n, JE[n]["profilform"], art)
    for n in ("A01_KantL_40x40x8_kurz", "A02_KantL_50x50x10_kurz", "A03_KantL_50x50x10_R2"):
        m = JE[n]
        assert "nie Dreh-/Frästeil" in m["art_grund"], (n, m["art_grund"])
        df = step.arten(m)[step.ART_DREHFRAES]["messung"]
        assert df and df["profilform"] == "Frästeil", (n, df and df["profilform"])
        assert "Bohrungen" not in json.loads(df["drehfraes"])["zusatz"], "Biegeradien sind keine Bohrungen"
    assert "Frästeil" in JE["A05_Fraesblock_Tasche"]["art_grund"], JE["A05_Fraesblock_Tasche"]["art_grund"]
    k = next(k for d in JS["dateien"] for k in d["koerper"] if d["datei"].startswith("A01"))
    assert k["art_grund"] and set(k["arten"]) == {"Dreh-/Frästeil"}, k.get("arten")


@fall("A2 jedes Teil hat alle drei Arten (gemessen oder mit Grund)")
def _():
    for n, m in JE.items():
        a = step.arten(m)
        assert set(a) == set(step.ART_GRUPPEN), (n, set(a))
        for gr, x in a.items():
            assert x["messung"] is not None or x["grund"], (n, gr)
    rr = step.arten(JE["A07_Rundrohr"])
    assert rr[step.ART_BLECH]["messung"] is None and "Blech" in rr[step.ART_BLECH]["grund"], rr[step.ART_BLECH]
    assert rr[step.ART_DREHFRAES]["messung"]["profilform"] == "Drehteil", rr[step.ART_DREHFRAES]


@fall("A3 Umstellen über alle drei Arten und zurück: Messwerte der Art gelten, nichts geht verloren")
def _():
    m = dict(JE["A02_KantL_50x50x10_kurz"])
    vorher = dict(m)
    assert step.art_setzen(m, step.ART_DREHFRAES) and m["profilform"] == "Frästeil" and m["drehfraes"]
    assert step.art_grund(m) == "Art von Hand: Dreh-/Frästeil statt Blech", step.art_grund(m)
    assert step.art_setzen(m, step.ART_PROFIL) and m["profilform"] == "L-Profil", m["profilform"]
    assert step.art_setzen(m, step.ART_BLECH) and m["profilform"] == "Blech gekantet"
    assert not step.art_grund(m).startswith("Art von Hand"), step.art_grund(m)
    for k in ("profilform", "abm_a", "abm_b", "laenge", "blech"):
        assert m[k] == vorher[k], k
    assert set(step.arten(m)) == set(step.ART_GRUPPEN)
    assert not step.art_setzen(dict(JE["A07_Rundrohr"]), step.ART_BLECH), "nicht messbare Art bleibt aus"


@fall("A4 gemerkte Wahl: gleiches Teil beim nächsten Import gleich die gewählte Art (für alle Kunden)")
def _():
    m = dict(JE["A01_KantL_40x40x8_kurz"])
    s = step.art_schluessel(m)
    assert s and s == step.art_schluessel(dict(JE["A01_KantL_40x40x8_kurz"])), s
    gelernt = step.arten_gelernt_merken({}, {s: step.ART_DREHFRAES})
    neu = [dict(JE[n]) for n in TEILE]
    assert step.arten_gelernt_anwenden(neu, gelernt) == 1
    x = next(x for x in neu if x["datei"].startswith("A01"))
    assert x["profilform"] == "Frästeil" and "von Hand gewählt" in step.art_grund(x), step.art_grund(x)
    import datetime
    alt = {s: step.ART_DREHFRAES}                       # Eintrag von vor 0.9.275: nur die Gruppe, ohne Datum
    y = [dict(JE["A01_KantL_40x40x8_kurz"])]
    assert step.arten_gelernt_anwenden(y, alt) == 1 and "wie beim letzten Mal" in step.art_grund(y[0])
    g2 = step.arten_gelernt_merken({}, {s: step.ART_DREHFRAES}, heute=datetime.date(2026, 11, 7))
    assert g2[s] == [step.ART_DREHFRAES, "07.11.2026"], g2
    y = [dict(JE["A01_KantL_40x40x8_kurz"])]
    step.arten_gelernt_anwenden(y, g2)
    assert step.art_grund(y[0]).startswith("Art wie am 07.11.2026 von Hand gewählt"), step.art_grund(y[0])
    with tempfile.TemporaryDirectory() as tmp:
        db = Datenbank(Path(tmp) / "r.db")
        db.einstellung_setzen(step.ART_GELERNT, gelernt)
        assert db.einstellung(step.ART_GELERNT) == gelernt
        db.con.close()


@fall("A5 Prüfdialog: Spalte Art mit allen drei Arten, Umstellen rechnet neu, Grund im Hinweis, 3D goldgelb")
def _():
    from PySide6.QtWidgets import QApplication
    from rohrlaser.step_dialog import StepPruefDialog
    app = QApplication.instance() or QApplication([])
    with tempfile.TemporaryDirectory() as tmp:
        db = Datenbank(Path(tmp) / "r.db")
        mw = [dict(JE["A01_KantL_40x40x8_kurz"])]
        d = StepPruefDialog(None, mw, db.kontext(), "S235-10219", 1, db.zukauf_artikel_liste())
        z = d.zeilen[0]
        art = d.baum.itemWidget(z.it, d.SP_ART)
        texte = [art.itemText(i) for i in range(art.count())]
        assert art.currentText().startswith("Kantteil"), texte
        assert "nie Dreh-/Frästeil" in z.it.text(d.SP_HINWEIS), z.it.text(d.SP_HINWEIS)
        i = next(i for i in range(art.count()) if art.itemData(i) == "gruppe:" + step.ART_DREHFRAES)
        assert texte[i].startswith("Dreh-/Frästeil: Frästeil"), texte
        assert any(art.itemData(i) == "alt" and texte[i] == "L-Profil" for i in range(art.count())), texte
        art.setCurrentIndex(i)
        z = d.zeilen[0]
        assert mw[0]["profilform"] == "Frästeil" and z.it.parent().data(0, 0x0100) == d.DREHGRUPPE
        assert "Art von Hand: Dreh-/Frästeil statt Blech" in z.it.text(d.SP_HINWEIS), z.it.text(d.SP_HINWEIS)
        assert d.art_merken == {step.art_schluessel(mw[0]): step.ART_DREHFRAES}, d.art_merken
        netz = {"p": [0, 0, 0, 1, 0, 0, 0, 1, 0], "t": {"A": [0, 1, 2]}, "l": {"EA": [[0, 0, 0, 1, 0, 0]]}}
        n = step.netz_der_art(dict(mw[0], _netz=netz))
        assert set(n["t"]) == {"KD"} and not n["l"], n
        d.close()
        app.processEvents()
        db.con.close()
    # Rundrohr: Blech ausgegraut mit Grund
    with tempfile.TemporaryDirectory() as tmp:
        db = Datenbank(Path(tmp) / "r.db")
        d = StepPruefDialog(None, [dict(JE["A07_Rundrohr"])], db.kontext(), "S235-10219", 1, db.zukauf_artikel_liste())
        art = d.baum.itemWidget(d.zeilen[0].it, d.SP_ART)
        i = next(i for i in range(art.count()) if art.itemText(i).startswith(step.ART_BLECH))
        assert not art.model().item(i).isEnabled() and "Blech" in art.itemText(i), art.itemText(i)
        d.close()
        app.processEvents()
        db.con.close()


@fall("A6 Richtpreis Dreh-/Frästeil: eigene Werte je Teil wie beim Blech, Richtpreis je Stück ersetzt den Preis")
def _():
    from rohrlaser import drehfraes
    d = drehfraes.daten(JE["A05_Fraesblock_Tasche"])
    e = dp.aus_step(d, "S235", 10)
    erg = dp.rechnen(e)
    assert not erg["fehler"] and erg["richtpreis"] > 0 and not erg["eigene"], erg["fehler"]
    rw = erg["richtwerte"]
    assert set(rw) == set(dp.RICHTWERT_NAMEN), set(rw)
    e2 = dict(e, eigene={"maschine": rw["maschine"] * 2})
    erg2 = dp.rechnen(e2)
    assert erg2["richtpreis"] > erg["richtpreis"] and erg2["richtwerte"]["maschine"] == rw["maschine"]
    erg3 = dp.rechnen(dict(e, eigene={"richtpreis": 99.5}))
    assert erg3["richtpreis"] == 99.5 and erg3["richtpreis_berechnet"] == erg["richtpreis"]
    assert any("von Hand" in h for h in erg3["hinweise"]) and any("Eigene Werte" in z for z in dp.bericht(erg3))
    erg4 = dp.rechnen(dict(e, eigene={"aufschlag": 0.0}))
    assert erg4["aufschlag"] == 0 and erg4["richtpreis"] < erg["richtpreis"]
    assert dp.eigene_werte({"eigene": {"richtpreis": -1, "x": 3, "zusatz": True}}) == {}
    from PySide6.QtWidgets import QApplication
    from rohrlaser.drehfraes_dialog import DrehfraesDialog
    app = QApplication.instance() or QApplication([])
    dlg = DrehfraesDialog(None, dict(e, eigene={"richtpreis": 99.5}), None)
    assert dlg.ergebnis["richtpreis"] == 99.5 and dlg.richtwerte.eigene() == {"richtpreis": 99.5}
    dlg.richtwerte.zuruecksetzen(dlg.richtwerte.rw.index(next(r for r in dp.RICHTWERTE if r[0] == "richtpreis")))
    assert dlg.ergebnis["richtpreis"] == erg["richtpreis"] and dlg.eingaben()["eigene"] == {}
    dlg.close()
    app.processEvents()


@fall("A7 Kalkulation: Rechtsklick „Art ändern …“ ersetzt die Position (Pos.-Nr., Stückzahl bleiben)")
def _():
    from PySide6.QtWidgets import QApplication
    from rohrlaser import angebot_fenster
    app = QApplication.instance() or QApplication([])
    assert "Art ändern (Blech / Rohr / Dreh-/Frästeil) …" in angebot_fenster.AngebotSeite.MENUE_ARTEN
    p = dict(technik=json.dumps({"quelle": "x"}), artikel="A01_KantL_40x40x8_kurz")
    m = dict(JE["A01_KantL_40x40x8_kurz"], _pfad=str(TMP / "A01_KantL_40x40x8_kurz.step"))
    step.herkunft_merken(p, m)
    h = step.herkunft(p)
    assert h["name"] == "A01_KantL_40x40x8_kurz.step" and h["koerper"] == 1 and h["art"] == step.ART_BLECH, h
    assert step.nur_koerper(MW, h) == [JE["A01_KantL_40x40x8_kurz"]]
    assert step.nur_koerper(MW, None, {"artikel": "gibt es nicht"}) == MW
    app.processEvents()


if fehler:
    print(f"{fehler} Fall/Fälle rot")
    sys.exit(1)
print("Alle Fälle der Art-Auswahl bestanden.")
