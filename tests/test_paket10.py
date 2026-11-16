"""Paket 10 (Vorschläge L1, L5, L7, Patrick 08.11.2026 „Alle Empfehlungen“):
L1 Rohr mit angeschweißtem Blech (Kopfplatte, Lasche): Rohr statt Drehteil, gelb, „Aufteilen“ trennt Rohr und Blech.
L5 „Preise aus CSV …“ bei den Normteilen ohne Preis: Preisliste lesen, zuordnen, vor dem Speichern prüfen.
L7 Windows-Bau: Tesseract und Sprachdaten zuerst aus Rohrlaser-Updates (Release „werkzeuge“), feste Prüfsumme.

Aufruf: python tests/test_paket10.py
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
from PySide6.QtWidgets import QApplication  # noqa: E402

from rohrlaser import step, zukauf  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.normteil_preise import (NormteilPreisSeite, normteil_schluessel, preisliste_lesen,  # noqa: E402
                                       zuordnen)

TMP = Path(tempfile.mkdtemp())
app = QApplication.instance() or QApplication([])


def ok(text):
    print("OK    ", text)


# ------------------------------------------------------------------ L5 Preisliste
assert normteil_schluessel("Sechskantschraube DIN 933 M8 x 20 8.8") == ("DIN", "933", "M8", "20")
assert normteil_schluessel("ISO 4032 M12") == ("ISO", "4032", "M12", "")
assert normteil_schluessel("DIN EN ISO 4762 M6×16") == ("DIN", "4762", "M6", "16")
assert normteil_schluessel("Kugel Ø20") is None
liste = preisliste_lesen("Art.-Nr.;Bezeichnung;Preis netto €\n"
                         "4711;Sechskantmutter ISO 4032 M12 verzinkt;0,12\n"
                         "4712;6kt-Mutter ISO 4032 M16;0,25 €\n"
                         ";Zylinderschraube DIN 912 M6x16;1.234,50\n"
                         "9;Ohne Preis;\n".encode("cp1252"))
assert [z["preis"] for z in liste] == [0.12, 0.25, 1234.5], liste
assert liste[0]["artikelnr"] == "4711" and liste[2]["bezeichnung"].startswith("Zylinder")
assert preisliste_lesen("Bezeichnung,EK\nKugel Ø20,0.35\n") == [dict(bezeichnung="Kugel Ø20", artikelnr="",
                                                                      preis=0.35)]
try:
    preisliste_lesen("Name;Menge\nx;1\n")
    raise AssertionError("ohne Preis-Spalte muss ein Fehler kommen")
except ValueError as e:
    assert "Kopfzeile" in str(e)
ok("L5: Preisliste mit Semikolon/Komma, cp1252/UTF-8, deutsche Zahlen; ohne Preis-Spalte klare Meldung")

db = Datenbank(TMP / "n.db")


def normteil(name, artnr=None):
    werte = dict(bezeichnung=name, kategorie=step.NORMTEIL_KATEGORIE, einheit="Stück", status="aktiv",
                 aufschlag_quelle="Kategorie", angebotstext="nein", rest_lager="nein", kombiniert="nein",
                 artikeltyp=step.NORMTEIL_TYP, herkunft="STEP-Import", artikelnr=artnr)
    return db.zukauf_speichern(None, werte, [dict(lieferant=None, bevorzugt="ja", preiseinheit=1, preise=[])])


m12 = normteil("ISO 4032 M12")
m16 = normteil("ISO 4032 M16", "4712")
zyl = normteil("DIN 912 M6x16")
m20 = normteil("ISO 4032 M20")
treffer, rest = zuordnen([db.zukauf_artikel(i) for i in (m12, m16, zyl, m20)], liste)
assert {i: w for i, (_, w) in treffer.items()} == {m12: "Norm und Größe", m16: "Artikelnummer",
                                                   zyl: "Norm und Größe"}, treffer
assert not rest and m20 not in treffer
ok("L5: Zuordnung über Artikelnummer, sonst Norm + Gewinde + Länge; ohne Treffer bleibt die Zeile leer")

meldungen = []
s = NormteilPreisSeite(db, lambda t, f=False: meldungen.append((t, f)))
assert s.csv_knopf.isEnabled() and s.tabelle.rowCount() == 4
n, rest = s.csv_uebernehmen("Bezeichnung;Preis\nISO 4032 M12;0,12\nISO 4032 M16;0,25\nUnbekannt M99;3\n")
assert n == 2 and len(rest) == 1 and "2 von 3 Zeilen zugeordnet" in s.info.text() and "Unbekannt" in s.info.text()
assert all(zukauf.ek_fehlt(db.zukauf_artikel(i)) for i in (m12, m16)), "erst „Preise speichern“ speichert"
werte = {a["bezeichnung"]: s.tabelle.cellWidget(r, 3).value() for r, a in enumerate(s.artikel)}
assert werte["ISO 4032 M12"] == 0.12 and werte["ISO 4032 M16"] == 0.25 and werte["ISO 4032 M20"] == 0
assert s.speichern() == 2 and not zukauf.ek_fehlt(db.zukauf_artikel(m12)) and s.tabelle.rowCount() == 2
assert s.csv_uebernehmen(b"Name;Menge\n") == (0, []) and meldungen[-1][1]
ok("L5: „Preise aus CSV …“ trägt die Preise zum Prüfen in die Zeilen, gespeichert wird erst mit „Preise speichern“")

# ------------------------------------------------------------------ L7 Tesseract aus dem eigenen Repository
import re  # noqa: E402

yml = (HIER.parent / ".github" / "workflows" / "paket.yml").read_text(encoding="utf-8")
schritt = yml[yml.index("- name: Tesseract mitliefern"):]
schritt = schritt[:schritt.index("\n      - name:")]
for name in ("tesseract-ocr-w64-setup-5.4.0.20240606.exe", "deu.traineddata", "eng.traineddata"):
    block = schritt[schritt.index(f'name = "{name}"'):][:400]
    assert re.search(r'sha = "[0-9a-f]{64}"', block), name
assert "releases/download/werkzeuge" in schritt and "Get-FileHash" in schritt and "--clobber" in schritt
assert schritt.index("releases/download/werkzeuge") < schritt.index("Invoke-WebRequest $w.url"), "eigenes Repo zuerst"
assert "Prüfsumme stimmt nicht" in schritt and "secrets.UPDATES_TOKEN" in schritt
ok("L7: Tesseract-Setup und Sprachdaten zuerst aus Rohrlaser-Updates, Prüfsumme fest, sonst Originalquelle und ablegen")

# ------------------------------------------------------------------ L1 Rohr mit Blech
import json  # noqa: E402

import step_messen  # noqa: E402
from formen_baukasten import ohne, plus, quader, schreibe, zyl  # noqa: E402

rr = ohne(zyl(21.3, 600, d=(1, 0, 0)), zyl(18.3, 600, d=(1, 0, 0)))
qr = ohne(quader(500, 40, 40), quader(500, 34, 34, 0, 3, 3))
dreh = ohne(plus(zyl(30, 20, d=(1, 0, 0)), zyl(15, 60, d=(1, 0, 0))), zyl(8, 60, d=(1, 0, 0)))  # Buchse mit Bund
teile = {"RR_Kopf": plus(rr, quader(5, 80, 80, 600, -40, -40)), "QR_Lasche": plus(qr, quader(300, 6, 60, 100, 40, -10)),
         "Rohr": qr, "Buchse": dreh}
schreibe(teile, TMP)
aus = TMP / "l1.txt"
step_messen.main(["--ausgabe", str(aus)] + [str(TMP / f"{n}.step") for n in teile])
mw = {m["datei"].split(".")[0]: m for m in step.lies_messwerte(aus)}
for n in ("RR_Kopf", "QR_Lasche"):
    m = dict(mw[n], _pfad=str(TMP / f"{n}.step"))
    assert m["bauteiltyp"] == "Profil" and m["profilform"] in ("Rundrohr", "Quadratrohr"), (n, m["bauteiltyp"])
    assert step.ROHR_BLECH_HINWEIS in m["hinweise"] and step.mehrteilig_koerper(m), (n, m["hinweise"])
    farbe, gruende = step.ampel(m)
    assert farbe == "gelb" and any("Aufteilen" in g for g in gruende), (n, farbe, gruende)
    assert step.gewaehlt(m) or "anbauteile" in step.unsicher(m), "sicher erkannt: als Rohr mit Anbauteil angehakt"
assert "Kopfplatte" in mw["RR_Kopf"]["hinweise"] and "kein Dreh-/Frästeil" in mw["RR_Kopf"]["art_grund"]
assert step.ROHR_BLECH_HINWEIS not in (mw["Rohr"]["hinweise"] or "") and step.ampel(mw["Rohr"])[0] == "gruen"
assert mw["Buchse"]["bauteiltyp"] == "Drehteil", mw["Buchse"]["bauteiltyp"]
ok("L1: Rundrohr mit Kopfplatte ist ein Rohr (nicht mehr Drehteil), Rohr mit Lasche gelb mit „Aufteilen“; "
   "Rohr ohne Blech grün, Buchse mit Bund bleibt Drehteil")

for n in ("RR_Kopf", "QR_Lasche"):
    a = TMP / f"auf_{n}.txt"
    step_messen.main([str(TMP / f"{n}.step"), "--ausgabe", str(a), "--aufteilen", "1"])
    namen = [x[1] for x in json.loads(Path(str(a) + ".teile.json").read_text(encoding="utf-8"))]
    neu = step.lies_messwerte(a)
    assert namen[-1] == "Rohr" and namen[0] == "Blech", namen
    rohr_m = neu[-1]
    assert rohr_m["profilform"] == mw[n]["profilform"] and abs(float(rohr_m["laenge"]) - float(mw[n]["laenge"])) < 0.1
    assert step.ROHR_BLECH_HINWEIS not in (rohr_m.get("hinweise") or "")
    blech_m = neu[0]
    assert blech_m["bauteiltyp"] in ("Blech", "Profil") and blech_m["profilform"] in ("Blech", "Flachstahl"), blech_m
    erg = step.aufgeteilt(dict(mw[n], artikel="A-7", koerper=1), neu, namen)
    assert erg[-1]["artikel"] == "A-7" and erg[0]["artikel"] == "A-7-1" and not erg[0].get("_normteil")
ok("L1: „Aufteilen“ trennt Rohr (gleiche Form und Länge, Artikelnummer bleibt) und Blech (als Blech/Flachstahl, kein "
   "Normteil)")

print("Paket 10: alle Tests bestanden.")
