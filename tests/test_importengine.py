"""Importengine nach Laserhub-Vergleich (Patrick 20.11.2026 „CAD-Import, Bauteilerkennung und automatische
Geometrieanalyse“, Konzept docs/system-audit/IMPORTENGINE_LASERHUB_2011.md, Abschnitt 11 Testkatalog).

Testkatalog mit Referenzmaßen (Teile aus tests/step, step_regression, step_struktur, step_satz und den neuen
tests/step_importengine, erzeugt mit tests/importengine_teile.py):
- E1 Referenzmaße: Profilform, Abmessungen, Wand, Länge, Bohrungen und Kategorie je Teil (Tabelle REFERENZ);
  Abweichungen werden je Teil ausgegeben
- E2 Ovalrohre: Flachoval, Halbflachoval, Elliptisch erkannt (vorher „Sonderprofil, Profil nicht erkannt“) und dem
  Profil der Stammdaten zugeordnet
- E3 Import vorbereiten: ZIP (auch ZIP in ZIP), Zip Slip, SolidWorks/CATIA/Inventor gemeldet, leere/keine/
  unvollständige STEP, doppelter Inhalt, andere Dateien, Ordner; step_dateien entpackt ZIP
- E4 fehlerhafte Dateien durch die Messung: unvollständige STEP stürzt nicht ab, nicht lesbare Dateien werden rote
  Zeilen (fehler_zeilen) und stehen im Importbericht
- E5 Bauteilanalyse: elf Kategorien, Konfidenz passt zur Ampel, Merkmale mit Lage/Abmessung/Bearbeitung
  (Bohrung, Gewinde-Vorschlag, Gravur, Stirnausschnitt, Gehrung, Langloch, Senkung), Kennzahlen
- E6 Baugruppen: gleiche Teile mit Stückzahl, Struktur (Knoten), Varianten, Verbindungen, Materialbedarf, CSV;
  große Baugruppe (48 Körper) in 3 Positionen
- E7 Datenübergabe: Analyse wird mit der Position gespeichert (step_pruefung.speicherwert) und dort gelesen
- E8 Oberfläche: Schrittleiste und Fenster Importanalyse (Bauteile, Merkmale, Baugruppen, Dateien)

Aufruf: python tests/test_importengine.py
"""
import json
import os
import shutil
import sys
import tempfile
import time
import zipfile
from pathlib import Path

HIER = Path(__file__).parent
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER.parent / "programm" / "step_messung"))
import step_messen  # noqa: E402
from rohrlaser import baugruppe_analyse as bga  # noqa: E402
from rohrlaser import bauteil_analyse as ba  # noqa: E402
from rohrlaser import cad_import, step, step_pruefung  # noqa: E402

fehler = 0
ABWEICHUNGEN = []


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


# Referenzmaße: Datei-Anfang -> (Profilform, A, B, Wand, Länge, Bohrungen gesamt, Kategorie)
REFERENZ = {
    "T01": ("Rundrohr", 42.4, 0, 2.0, 1250, 0, ba.RUNDROHR),
    "T02": ("Rundrohr", 42.4, 0, 2.0, 860, 2, ba.RUNDROHR),
    "T03": ("Quadratrohr", 40, 0, 3.0, 2150, 1, ba.VIERKANT),
    "T04": ("Rechteckrohr", 60, 40, 3.0, 1825.5, 0, ba.RECHTECK),
    "T05": ("Rundrohr", 33.7, 0, 2.6, 500, 0, ba.RUNDROHR),
    "T06": ("Quadratrohr", 40, 0, 3.0, 1000, 0, ba.VIERKANT),
    "T07": ("Quadratrohr", 40, 0, 3.0, 1000, 4, ba.VIERKANT),
    "R04": ("Quadratrohr", 40, 0, 2.0, 800, 0, ba.VIERKANT),
    "R06": ("Rechteckrohr", 40, 30, 3.0, 920, 6, ba.RECHTECK),
    "I01": ("Flachoval", 60, 30, 2.0, 800, 2, ba.OVAL),
    "I02": ("Elliptisch", 60, 30, 2.0, 800, 0, ba.OVAL),
    "I03": ("Halbflachoval", 80, 30, 2.0, 600, 0, ba.OVAL),
    "I04": ("L-Profil", 50, 30, 4.0, 700, 0, ba.OFFEN),
}
ORDNER = [HIER / "step", HIER / "step_regression", HIER / "step_struktur", HIER / "step_satz",
          HIER / "step_importengine"]
TMP = Path(tempfile.mkdtemp())
DATEIEN = [p for o in ORDNER for p in sorted(o.glob("*.step"))]
aus, js = TMP / "m.txt", TMP / "m.json"
t0 = time.perf_counter()
step_messen.main(["--ausgabe", str(aus), "--json", str(js)] + [str(p) for p in DATEIEN])
MESSZEIT = time.perf_counter() - t0
MW = step.struktur_anhaengen(step.lies_messwerte(aus), js)
JE = {}
for m in MW:
    JE.setdefault(m["datei"][:3], []).append(m)
print(f"Messung: {len(DATEIEN)} Dateien, {len(MW)} Körper in {MESSZEIT:.1f} s")


def z(m, n):
    return float(m.get(n) or 0)


@fall("E1 Referenzmaße des Testkatalogs (Profil, Maße, Wand, Länge, Bohrungen, Kategorie)")
def _():
    falsch = []
    for k, (form, a, b, wand, lg, bohr, kat) in REFERENZ.items():
        m = JE[k][0]
        ist = (m.get("profilform"), round(max(z(m, "abm_a"), z(m, "abm_b")), 2),
               round(min(z(m, "abm_a"), z(m, "abm_b")), 2) if b else 0, round(z(m, "wandstaerke"), 2),
               round(z(m, "laenge"), 1), sum(n for _, n in step._paare(m.get("bohrungen"))), ba.von(m)["kategorie"])
        soll = (form, a, b, wand, lg, bohr, kat)
        abw = [f"{n}: {i} statt {s}" for n, i, s in zip(("Profil", "A", "B", "Wand", "Länge", "Bohrungen", "Kategorie"),
                                                         ist, soll)
               if (abs(i - s) > 0.15 if isinstance(s, (int, float)) and not isinstance(s, bool) else i != s)]
        print(f"       {k} {m['datei'][:34]:34} {ist[0]:14} {ist[1]:g}×{ist[2]:g}×{ist[3]:g} L{ist[4]:g} "
              f"Bohr {ist[5]} {ist[6]:13} {'OK' if not abw else 'ABWEICHUNG ' + '; '.join(abw)}")
        if abw:
            falsch.append(f"{k}: {'; '.join(abw)}")
            ABWEICHUNGEN.append((k, abw))
    assert not falsch, falsch


@fall("E2 Ovalrohre erkannt und dem Stammdaten-Profil zugeordnet")
def _():
    for k, form in (("I01", "Flachoval"), ("I02", "Elliptisch"), ("I03", "Halbflachoval")):
        m = JE[k][0]
        assert m["profilform"] == form, (k, m["profilform"], m.get("hinweise"))
        assert "Profil nicht erkannt" not in (m.get("hinweise") or ""), m.get("hinweise")
        profile = {f"{form} 60x30x2": dict(form=form, a=60, b=30, wand=2.0),
                   f"{form} 80x30x2": dict(form=form, a=80, b=30, wand=2.0),
                   "RE 60x30x2": dict(form="Rechteckrohr", a=60, b=30, wand=2.0)}
        pid = step.finde_profil(m, profile)
        assert pid and pid.startswith(form), (k, pid)
    assert "Flachoval" in step.MIT_B and "Elliptisch" in step.MIT_B
    # Flachoval mit zwei Bohrungen: die Bohrungen gehören zur Messung (Konturen auf dem Oval)
    assert step._paare(JE["I01"][0].get("bohrungen")) == [(8.0, 2)], JE["I01"][0].get("bohrungen")


VORBEREITUNG = None


def _zip(pfad, eintraege):
    with zipfile.ZipFile(pfad, "w") as zf:
        for name, daten in eintraege.items():
            zf.writestr(name, daten)
    return pfad


@fall("E3 Import vorbereiten: ZIP, ZIP in ZIP, Herstellerformate, leere/defekte/doppelte Dateien, Ordner")
def _():
    q = TMP / "quelle"
    q.mkdir()
    t01 = (HIER / "step" / "T01_RR42-4x2_L1250.step").read_bytes()
    t03 = (HIER / "step" / "T03_QR40x3_L2150_Bohrung.step").read_bytes()
    innen = _zip(TMP / "innen.zip", {"Rohr_T03.step": t03})
    _zip(q / "Paket.zip", {"teile/T01.step": t01, "teile/Kopie_T01.stp": t01, "Unterpaket.zip": innen.read_bytes(),
                           "Halter.SLDPRT": b"\x00" * 64, "Lies mich.txt": b"Hallo",
                           "../../ausbruch.step": t01, "Zeichnung.pdf": b"%PDF-1.4"})
    (q / "Rahmen.CATPart").write_bytes(b"V5_CFV2")
    (q / "Teil.ipt").write_bytes(b"x")
    (q / "leer.step").write_bytes(b"")
    (q / "kein_step.stp").write_text("Das ist keine STEP-Datei", encoding="utf-8")
    (q / "abgeschnitten.step").write_bytes(t03[: len(t03) // 2])
    (q / "T01_nochmal.step").write_bytes(t01)
    basis = TMP / "entpackt"
    v = cad_import.vorbereiten([q], basis)
    namen = sorted(p.name for p in v.dateien)
    # T01 nur einmal (Inhalt gleich: ZIP, Kopie, nochmal, ausbruch), T03 aus dem inneren ZIP, abgeschnitten (Hinweis)
    assert namen == ["Rohr_T03.step", "T01.step", "abgeschnitten.step"] or \
        sorted(namen) == sorted(["Rohr_T03.step", "T01_nochmal.step", "abgeschnitten.step"]), namen
    texte = {b["datei"]: (b["stufe"], b["text"]) for b in v.befunde}
    alle = " | ".join(f"{d}: {s} {t}" for d, (s, t) in texte.items())
    assert any("SolidWorks-Teil" in t and s == cad_import.FEHLER for s, t in texte.values()), alle
    assert any("CATIA-Teil" in t for _, t in texte.values()) and any("Inventor-Teil" in t for _, t in texte.values())
    assert any("leere Datei" in t for _, t in texte.values()), alle
    assert any("keine STEP-Datei" in t for _, t in texte.values()), alle
    assert any("unvollständig" in t and s == cad_import.HINWEIS for s, t in texte.values()), alle
    assert sum("gleicher Inhalt" in t for _, t in texte.values()) >= 2, alle
    assert any("übersprungen" in t and ".txt" in t and ".pdf" in t for _, t in texte.values()), alle
    # Zip Slip: nichts außerhalb des Zielordners
    for p in v.dateien:
        assert str(p.resolve()).startswith(str(q.resolve())) or str(p.resolve()).startswith(str(basis.resolve())), p
    assert not (TMP / "ausbruch.step").exists() and not (basis.parent / "ausbruch.step").exists()
    # step_dateien (Ablegen, Neu einlesen) entpackt ZIPs ebenso; kandidat nimmt ZIP und Herstellerformate an
    assert any(p.name == "Rohr_T03.step" for p in step.step_dateien([q / "Paket.zip"]))
    assert step.step_kandidaten([q / "Paket.zip"]) and step.step_kandidaten([q / "Rahmen.CATPart"])
    # nur Herstellerformate: nichts zu messen, aber klare Befunde
    v2 = cad_import.vorbereiten([q / "Rahmen.CATPart"])
    assert not v2.dateien and v2.fehler() and "STEP (AP214 oder AP242)" in v2.fehler()[0]["text"]
    # defektes ZIP
    (TMP / "kaputt.zip").write_bytes(b"PK\x03\x04kaputt")
    v3 = cad_import.vorbereiten([TMP / "kaputt.zip"], basis)
    assert not v3.dateien and "ZIP defekt" in v3.fehler()[0]["text"], v3.befunde
    global VORBEREITUNG
    VORBEREITUNG = v


@fall("E4 Fehlerhafte Dateien: Messung stürzt nicht ab, rote Zeilen, Importbericht")
def _():
    v = VORBEREITUNG
    a2, j2 = TMP / "f.txt", TMP / "f.json"
    rc = step_messen.main(["--ausgabe", str(a2), "--json", str(j2)] + [str(p) for p in v.dateien])
    mw = step.lies_messwerte(a2)
    namen = {m["datei"] for m in mw}
    assert {"T01.step", "Rohr_T03.step"} <= namen or {"T01_nochmal.step", "Rohr_T03.step"} <= namen, (rc, namen)
    ab = [m for m in mw if m["datei"] == "abgeschnitten.step"]
    assert ab and (ab[0].get("fehler") or ab[0].get("profilform")), ab     # gemeldet oder gemessen, kein Absturz
    rot = cad_import.fehler_zeilen(v, mw[0])
    assert len(rot) == len([b for b in v.fehler()]) and all(r["fehler"] and r["pruefstatus"] == "nicht messbar"
                                                             for r in rot), rot
    assert all(ba.analyse(r)["stufe"] == "unsicher" and ba.analyse(r)["konfidenz"] == 0 for r in rot)
    alle = mw + rot
    alle[0]["_import_befunde"] = v.befunde
    bericht = step.importbericht(alle)
    assert any("Halter.SLDPRT" in z_ and "nicht messbar" in z_ for z_ in bericht), bericht
    assert any(z_.startswith("Import ") and "gleicher Inhalt" in z_ for z_ in bericht), bericht


@fall("E5 Bauteilanalyse: Kategorien, Konfidenz zur Ampel, Merkmale, Kennzahlen")
def _():
    # Kategorien aus echten Messungen
    kat = {ba.von(m)["kategorie"] for m in MW}
    for k in (ba.RUNDROHR, ba.VIERKANT, ba.RECHTECK, ba.OVAL, ba.OFFEN, ba.BLECH, ba.FRAES, ba.SONSTIGE):
        assert k in kat, (k, kat)
    # übrige Kategorien aus Messwerten wie von STEP-Import.exe
    assert ba.kategorie(dict(profilform="Drehteil", bauteiltyp="Drehteil"))[0] == ba.DREH
    assert ba.kategorie(dict(profilform="Sonderprofil", bauteiltyp="Profil"))[0] == ba.SONDER
    assert ba.kategorie(dict(profilform="Rundstahl", bauteiltyp="Profil"))[0] == ba.SONSTIGE
    assert ba.kategorie(dict(profilform="Rundrohr", _normteil=True))[0] == ba.SONSTIGE
    assert ba.kategorie(dict(profilform="Quadratrohr", biegerohr='{"bogen": 1}')) == (ba.VIERKANT, "gebogen")
    assert len(ba.KATEGORIEN) == 11 and ba.BAUGRUPPE in ba.KATEGORIEN
    # Konfidenz-Band passt zur Ampel (eine Entscheidung, die Zahl erklärt sie)
    for m in MW:
        a = ba.von(m)
        farbe = step.ampel(m)[0]
        band = {"gruen": (90, 100), "gelb": (50, 89), "rot": (0, 49)}[farbe]
        assert band[0] <= a["konfidenz"] <= band[1], (m["datei"], farbe, a["konfidenz"])
        assert a["stufe"] == {"gruen": "sicher", "gelb": "prüfen", "rot": "unsicher"}[farbe]
    sonder = dict(JE["I02"][0], profilform="Sonderprofil", sicherheit="profil=unsicher;wandstaerke=unsicher",
                  hinweise="Profil nicht erkannt, Fläche manuell prüfen", pruefstatus="prüfen")
    a = ba.analyse(sonder)
    assert a["kategorie"] == ba.SONDER and a["konfidenz"] < 90 and any("Profil" in u for u in a["unsicherheiten"]), a
    # Merkmale T07: Bohrungen, Gewinde-Vorschlag (Annahme), Gravur, Stirnausschnitt
    a = ba.von(JE["T07"][0])
    namen = [x["merkmal"] for x in a["merkmale"]]
    for n in (ba.M_BOHRUNG, ba.M_GEWINDE, ba.M_GRAVUR, ba.M_STIRN):
        assert n in namen, (n, namen)
    g = next(x for x in a["merkmale"] if x["merkmal"] == ba.M_GEWINDE)
    assert g["konfidenz"] < 90 and g["bearbeitung"] == ba.GEWINDE and "M6" in g["abmessung"], g
    b = next(x for x in a["merkmale"] if x["merkmal"] == ba.M_BOHRUNG)
    assert "x" in b and ("seite" in b or "winkel" in b) and b["abmessung"].startswith("Ø") and b["schnittlaenge"] > 0
    gr = next(x for x in a["merkmale"] if x["merkmal"] == ba.M_GRAVUR)
    assert gr["bearbeitung"] == ba.GRAVUR_LASER and not gr["durchgehend"]
    # Gehrung T04, Langlöcher R06, Senkungen R07, Schlitz T06
    assert any(x["merkmal"] == ba.M_GEHRUNG and abs(x["gehrung"] - 45) < 0.1 for x in ba.von(JE["T04"][0])["merkmale"])
    assert sum(x["merkmal"] == ba.M_LANGLOCH for x in ba.von(JE["R06"][0])["merkmale"]) == 4
    assert any(x["merkmal"] == ba.M_SENKUNG for x in ba.von(JE["R07"][0])["merkmale"])
    assert any(x["merkmal"] in (ba.M_SCHLITZ, ba.M_LANGLOCH) for x in ba.von(JE["T06"][0])["merkmale"])
    # Kennzahlen
    k = ba.von(JE["R06"][0])["kennzahlen"]
    assert k["bohrungen"] == 6 and k["ausschnitte"] == 4 and k["komplexitaet"] in ("mittel", "komplex"), k
    assert ba.von(JE["T01"][0])["kennzahlen"]["komplexitaet"] == "einfach"
    gew = ba.von(JE["T03"][0])["kennzahlen"]["gewicht_stahl_kg"]
    assert 6.8 < gew < 7.4, gew      # QR 40×3 (Querschnitt ca. 422 mm²), 2150 mm: ca. 3,3 kg/m × 2,15 m
    assert ba.kurztext(ba.von(JE["T07"][0])).startswith("Vierkantrohr")


@fall("E6 Baugruppen zerlegen: gleiche Teile, Struktur, Varianten, Verbindungen, Materialbedarf, CSV")
def _():
    dd = {d["datei"][:3]: d for d in bga.alle(MW)}
    s4 = dd["S04"]
    anz = sorted(p["anzahl"] for p in s4["positionen"])
    assert s4["koerper"] == 11 and anz == [2, 4, 5], anz
    assert s4["rohrlaser_baugruppe"] and len(s4["verbindungen"]) >= 10 and s4["naht_laenge"] > 1000, \
        (len(s4["verbindungen"]), s4["naht_laenge"])
    quer = next(p for p in s4["positionen"] if p["anzahl"] == 5)
    assert quer["knoten"] == {"Gestell › Seitenrahmen": 4, "Gestell": 1}, quer["knoten"]
    assert len(s4["varianten"]) == 2 and all("Länge" in v["text"] for v in s4["varianten"]), s4["varianten"]
    assert abs(s4["materialbedarf_mm"]["Quadratrohr 40 × 3"] - 8420) < 1, s4["materialbedarf_mm"]
    s1 = dd["S01"]
    assert any(p["kategorie"] == ba.SONSTIGE and p["anzahl"] == 4 for p in s1["positionen"])    # Schrauben
    i5 = dd["I05"]
    assert i5["koerper"] == 48 and sorted(p["anzahl"] for p in i5["positionen"]) == [8, 16, 24]
    assert not i5["rohrlaser_baugruppe"]       # lose Rohre ohne Berührung: mehrteilig, keine Schweißbaugruppe
    i6 = dd["I06"]
    assert sorted(p["kategorie"] for p in i6["positionen"]) == sorted(
        [ba.VIERKANT, ba.RUNDROHR, ba.BLECH, ba.FRAES]), [p["kategorie"] for p in i6["positionen"]]
    csv = TMP / "bauteile.csv"
    bga.csv_schreiben(list(dd.values()), csv)
    text = csv.read_text(encoding="utf-8-sig")
    assert text.splitlines()[0].startswith("Datei;Pos.;Bezeichnung") and "Querrohr QR40x3 L500" in text
    zus = bga.zusammenfassung(list(dd.values()))
    assert zus["koerper"] == len(MW) and zus["baugruppen"] >= 3, zus


@fall("E7 Datenübergabe: Analyse einmal ermittelt, mit der Position gespeichert und gelesen")
def _():
    m = dict(JE["R06"][0])
    text = step_pruefung.speicherwert(m)
    p = dict(step_merkmale=text)
    a = ba.aus_position(p)
    assert a and a["kategorie"] == ba.RECHTECK and a["kennzahlen"]["bohrungen"] == 6, a
    assert json.loads(text)["ampel"] in ("gruen", "gelb")
    # Merkmalliste begrenzt (große Teile)
    viele = dict(m, konturen_liste=json.dumps([dict(art="Bohrung", z=i, winkel=0, durchmesser=5, schnittlaenge=15.7)
                                               for i in range(ba.MERKMALE_MAX + 50)]))
    a2 = ba.speicherform(viele)
    assert len(a2["merkmale"]) == ba.MERKMALE_MAX and a2["merkmale_gekuerzt"]


@fall("E8 Oberfläche: Schrittleiste und Fenster Importanalyse")
def _():
    from PySide6.QtWidgets import QApplication
    from rohrlaser import importanalyse_dialog as iad
    QApplication.instance() or QApplication([])
    mw = [dict(m) for m in MW] + cad_import.fehler_zeilen(VORBEREITUNG, MW[0])
    mw[0]["_import_befunde"] = VORBEREITUNG.befunde
    zahlen = iad.schritt_zahlen(mw)
    assert zahlen["teile"] == len(MW) and zahlen["nicht_lesbar"] >= 5, zahlen
    html_ = iad.schritt_html(zahlen)
    for n in iad.SCHRITTE:
        assert n in html_, n
    d = iad.ImportanalyseDialog(None, mw)
    assert d.reiter.count() == 4 and d.bauteile.rowCount() == sum(len(x["positionen"]) for x in d.dateien)  # + Geometrieprüfung (24.11.)
    r = next(i for i, (_, p) in enumerate(d.zeilen) if p["bezeichnung"].startswith("T07"))
    d.bauteile.selectRow(r)
    assert d.merkmale.rowCount() >= 8 and "Vierkantrohr" in d.merkmal_titel.text(), (
        d.merkmale.rowCount(), d.merkmal_titel.text(), r, d.bauteile.currentRow())
    assert d.baugruppen.topLevelItemCount() >= 5 and d.befunde.rowCount() == len(VORBEREITUNG.befunde)
    assert Path(d.csv_speichern(str(TMP / "d.csv"))).is_file()
    if os.environ.get("IMPORTENGINE_BILDER"):      # Ordner für Bilder (Vergleichsseite), sonst keine Bilder
        p_ = Path(os.environ["IMPORTENGINE_BILDER"])
        if True:
            p_.mkdir(parents=True, exist_ok=True)
            d.resize(1300, 700)
            d.show()
            QApplication.processEvents()
            d.grab().save(str(p_ / "importanalyse_bauteile.png"))
            d.reiter.setCurrentIndex(1)
            QApplication.processEvents()
            d.grab().save(str(p_ / "importanalyse_baugruppen.png"))
            d.reiter.setCurrentIndex(2)
            QApplication.processEvents()
            d.grab().save(str(p_ / "importanalyse_dateien.png"))


shutil.rmtree(TMP, ignore_errors=True)
if ABWEICHUNGEN:
    print("Abweichungen:", ABWEICHUNGEN)
print(f"{'ALLE OK' if not fehler else f'{fehler} FEHLER'} (Messung {MESSZEIT:.1f} s)")
sys.exit(1 if fehler else 0)
