"""Prüft Lieferzeit, Kundenreferenz und Mindestpreis je Angebot (Schema 24):
- Lieferzeit: Vorgabe aus den Einstellungen beim Anlegen, je Angebot änderbar, Prüfung der Eingaben (Arbeitstage,
  Wochen, Kalenderwoche, Lieferdatum, Freitext), Text in Angebot und PDF ohne Widerspruch zu den Bedingungen,
  keine Preisänderung, ältere Angebote unverändert.
- Mindestpreis netto: unter, genau bei und über 200 €, mehrere Positionen, Skonto, Rundung (Summe nie unter dem
  Mindestpreis), einmal je Angebot, Staffelpreise je Stufe, Kostenart in der Kalkulation, Hinweis im Angebot,
  ältere Angebote ohne Mindestpreis, neue Einstellung gilt nur für neue Angebote.

Aufruf: python tests/test_angebot_vorgaben.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import os
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402
from rohrlaser import ausgabe, pdf, rechnen, staffeln  # noqa: E402
from rohrlaser.angebot import bedingungen_text, lieferzeit_text, lieferzeit_wert  # noqa: E402
from rohrlaser.datenbank import SCHEMA_VERSION, Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def ok(t):
    print("OK    ", t)


def nah(a, b, tol=1e-6):
    return a is not None and abs(a - b) <= tol


def fehler(f, *args):
    try:
        f(*args)
    except ValueError as e:
        return str(e)
    raise AssertionError(f"kein Fehler für {args}")


tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")

# ------------------------------------------------------------------ L1 Eingaben prüfen
assert lieferzeit_wert("Arbeitstage", " 10 ") == "10" and lieferzeit_wert("Wochen", "3") == "3"
assert lieferzeit_wert("Kalenderwoche", "KW 46", "2026-10-21") == "46/2026"
assert lieferzeit_wert("Kalenderwoche", "2/2027") == "2/2027"
assert lieferzeit_wert("Kalenderwoche", "53/2026") == "53/2026"     # 2026 hat 53 Kalenderwochen
assert "gibt es 2027 nicht" in fehler(lieferzeit_wert, "Kalenderwoche", "53/2027")
assert lieferzeit_wert("Lieferdatum", "15.11.2026") == "2026-11-15" and lieferzeit_wert("Lieferdatum", "15.11.26")
assert "kein gültiges Datum" in fehler(lieferzeit_wert, "Lieferdatum", "31.02.2026")
assert "kein gültiges Datum" in fehler(lieferzeit_wert, "Lieferdatum", "nächste Woche")
assert "ganze Zahl" in fehler(lieferzeit_wert, "Arbeitstage", "10,5")
assert "ganze Zahl" in fehler(lieferzeit_wert, "Arbeitstage", "0")
assert "ganze Zahl" in fehler(lieferzeit_wert, "Wochen", "15.11.2026")       # Datum ist keine Wochenzahl
assert lieferzeit_wert("nur Text", "15.11.2026") is None                     # Freitext wird nie Datum
assert lieferzeit_wert("Arbeitstage", "") is None and lieferzeit_wert(None, "10") is None
ok("L1 Eingaben: Arbeitstage/Wochen ganze Zahl, KW 1–52/53 je Jahr, gültiges Datum, Freitext nie als Datum")

# ------------------------------------------------------------------ L2 Text im Angebot
assert lieferzeit_text(dict(lieferzeit_art="Arbeitstage", lieferzeit_wert="10")) == \
    "Lieferzeit: ca. 10 Arbeitstage nach Auftragseingang."
assert lieferzeit_text(dict(lieferzeit_art="Arbeitstage", lieferzeit_wert="1")) == \
    "Lieferzeit: ca. 1 Arbeitstag nach Auftragseingang."
assert lieferzeit_text(dict(lieferzeit_art="Wochen", lieferzeit_wert="3", lieferzeit_zusatz="Teillieferung möglich")) \
    == "Lieferzeit: ca. 3 Wochen nach Auftragseingang, Teillieferung möglich."
assert lieferzeit_text(dict(lieferzeit_art="Kalenderwoche", lieferzeit_wert="46/2026")) == "Lieferzeit: KW 46/2026."
assert lieferzeit_text(dict(lieferzeit_art="Lieferdatum", lieferzeit_wert="2026-11-15")) == "Lieferzeit: bis 15.11.2026."
assert lieferzeit_text(dict(lieferzeit_art="nur Text", lieferzeit_zusatz="nach Absprache")) == "Lieferzeit: nach Absprache."
assert lieferzeit_text({}) == "" and lieferzeit_text(dict(lieferzeit_art="Arbeitstage")) == ""
bed = "Lieferzeit nach Absprache. Preise in Euro zuzüglich Mehrwertsteuer."
assert bedingungen_text({}, bed) == bed                                       # ältere Angebote: wie bisher
assert bedingungen_text(dict(lieferzeit_art="Arbeitstage", lieferzeit_wert="5"), bed) == \
    "Preise in Euro zuzüglich Mehrwertsteuer."
ok("L2 Text: Arbeitstage, Wochen, KW, Datum, Freitext; Satz 'Lieferzeit …' der Bedingungen entfällt nur bei eigener Lieferzeit")

# ------------------------------------------------------------------ L3 Vorgabe beim Anlegen, je Angebot speichern
a = db.angebot_neu(dict(kunde="Kunde A", skonto=0))
kopf = db.angebot(a)
assert (kopf["lieferzeit_art"], kopf["lieferzeit_wert"], kopf["lieferzeit_zusatz"]) == ("nur Text", None, "nach Absprache")
assert "mindestpreis" not in kopf            # Mindestpreis gilt aus den Einstellungen, nicht je Angebot
db.einstellung_setzen("lieferzeit_art", "Arbeitstage")
db.einstellung_setzen("lieferzeit_wert", "12")
db.einstellung_setzen("lieferzeit_zusatz", "")
b = db.angebot_neu(dict(kunde="Kunde B"))
assert (db.angebot(b)["lieferzeit_art"], db.angebot(b)["lieferzeit_wert"], db.angebot(b)["lieferzeit_zusatz"]) == \
    ("Arbeitstage", "12", None)
assert db.angebot(a)["lieferzeit_art"] == "nur Text"                        # bestehendes Angebot unverändert
db.einstellung_setzen("lieferzeit_wert", "zwölf")                             # ungültige Vorgabe: Wert bleibt leer
assert db.angebot(db.angebot_neu())["lieferzeit_wert"] is None
db.angebot_aendern(a, "lieferzeit_art", "Lieferdatum")
db.angebot_aendern(a, "lieferzeit_wert", "15.11.2026")
assert db.angebot(a)["lieferzeit_wert"] == "2026-11-15"
assert "kein gültiges Datum" in fehler(db.angebot_aendern, a, "lieferzeit_wert", "morgen")
assert db.angebot(a)["lieferzeit_wert"] == "2026-11-15"
db.angebot_aendern(a, "lieferzeit_art", "Arbeitstage")                       # Datum passt nicht zu Arbeitstagen
assert db.angebot(a)["lieferzeit_wert"] is None
db.angebot_aendern(a, "lieferzeit_wert", "8")
db.angebot_aendern(a, "lieferzeit_art", "Wochen")                            # 8 passt weiter
assert db.angebot(a)["lieferzeit_wert"] == "8"
db.angebot_aendern(a, "lieferzeit_art", "Arbeitstage")
db.angebot_aendern(a, "kundenreferenz", "Anfrage 4711 vom 20.10.2026")
kopie = db.angebot_kopieren(a)
assert db.angebot(kopie)["lieferzeit_wert"] == "8" and db.angebot(kopie)["kundenreferenz"] == "Anfrage 4711 vom 20.10.2026"
ok("L3 Vorgabe aus den Einstellungen beim Anlegen, Änderung nur im Angebot, Prüfung beim Speichern, Kopie übernimmt sie")

# ------------------------------------------------------------------ M1 Mindestpreis in der Kalkulation
for nr, laenge, st in ((10, 500, 2), (20, 300, 1)):
    db.position_neu(a, dict(pos=nr, artikel=f"T{nr}", profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=laenge,
                            stueck=st, schneidweg=320, einstiche=2))
k, tab = db.kontext(), db.tabellen()
kopf, pos = db.angebot(a), db.positionen(a)
erg = rechnen.optimieren(kopf, pos, k, tab)
einst = rechnen.einstellungen_angebot(kopf, db.einstellungen())
z0, s0 = rechnen.kalkulation(kopf, pos, erg, k, tab, dict(einst, mindestpreis=0))
kalk = s0["verkauf"]
assert 0 < kalk < 200, kalk
z1, s1 = rechnen.kalkulation(kopf, pos, erg, k, tab, einst)
assert nah(s1["verkauf"], 200) and s1["mindestpreis_gilt"] and nah(s1["verkauf_kalkuliert"], kalk)
assert nah(s1["mindestpreis_anhebung"], 200 - kalk) and nah(s1["herstell"], s0["herstell"])
f = 200 / kalk
for a0, a1 in zip(z0, z1):                       # alle Stückpreise im gleichen Verhältnis, Kosten unverändert
    assert nah(a1["preis_teil"], a0["preis_teil"] * f) and nah(a1["mindestpreis_teil"], a0["preis_teil"] * (f - 1))
    assert nah(a1["laser_teil"], a0["laser_teil"]) and nah(a1["material_teil"], a0["material_teil"])
kosten = dict((t.split(" (")[0], w) for t, w, _ in rechnen.kostenarten(s1, einst))
assert nah(kosten["Anhebung auf Mindestpreis"], 200 - kalk) and nah(kosten["Verkaufspreis"], 200)
text = next(t for t, _, _ in rechnen.kostenarten(s1, einst) if t.startswith("Anhebung"))
assert "kalkuliert" in text and "Mindestpreis 200" in text and "netto" in text, text
# Herstellkosten + Gewinn + … + Anhebung = Verkaufspreis (keine Kostenart doppelt, keine fehlt)
teile = [w for (t, w, fett), (_, n, _) in zip(rechnen.kostenarten(s1, einst), rechnen.KOSTENARTEN)
         if n in ("herstell", "gewinn", "pauschalen", "programmierung", "angebotsaufschlag", "fracht", "zukauf_einstand",
                  "zukauf_aufschlag", "skonto", "mindestpreis_anhebung")]
assert nah(sum(teile), s1["verkauf"], 1e-6)
ok(f"M1 kalkuliert {kalk:.2f} € < 200 €: alle Stückpreise × {f:.4f}, Kosten unverändert, Kostenart 'Anhebung auf Mindestpreis'")

# genau 200 und darüber: keine Anhebung
for mind in (kalk, kalk - 0.01, 50.0, 0.0):
    _, s = rechnen.kalkulation(kopf, pos, erg, k, tab, dict(einst, mindestpreis=mind))
    assert nah(s["verkauf"], kalk) and not s["mindestpreis_gilt"] and nah(s["mindestpreis_anhebung"], 0), mind
# ohne Stückzahl (Preis 0): kein Mindestpreis
_, s = rechnen.kalkulation(kopf, [dict(p, stueck=None) for p in pos], erg, k, tab, einst)
assert s["verkauf"] == 0 and not s["mindestpreis_gilt"]
ok("M2 genau beim Mindestpreis, darüber, Mindestpreis 0 und Angebot ohne Preis: keine Anhebung")

# Skonto: Mindestpreis gilt netto nach Skonto-Einrechnung
_, s = rechnen.kalkulation(dict(kopf, skonto=3), pos, erg, k, tab, einst)
assert nah(s["verkauf"], 200) and s["skonto"] > 0
ok("M3 mit 3 % Skonto: Angebotssumme netto genau 200 € (Skonto eingerechnet, keine zweite Anhebung)")

# Angebot: Stückpreise aufgerundet, Summe nie unter 200 €; Hinweis für den Kunden, keine zusätzliche Zeile
ang = ausgabe.angebot(kopf, pos, z1, k, einst)
assert len(ang["zeilen"]) == 2 and 200 <= ang["netto"] < 200.05, ang["netto"]
for z, zz in zip(ang["zeilen"], z1):
    assert z["preis"] >= zz["preis_teil"] - 1e-9 and z["preis"] - zz["preis_teil"] < 0.01
assert ang["mindestpreis"] == "Mindestauftragswert 200,00 € netto."
ang0 = ausgabe.angebot(kopf, pos, z0, k, dict(einst, mindestpreis=0))
assert ang0["mindestpreis"] == "" and nah(ang0["netto"], ausgabe.kaufm_runden(sum(z["gesamt"] for z in ang0["zeilen"])))
ok(f"M4 Angebot: Stückpreise auf den Cent aufgerundet, netto {ang['netto']:.2f} €, MwSt auf netto, Hinweis 'Mindestauftragswert'")

# Rundung: 7 Teile zu je 200/7 € -> 28,58 € × 7 = 200,06 € (nicht 199,99 €)
p7 = [dict(pos[0], stueck=7)]
erg7 = rechnen.optimieren(kopf, p7, k, tab)
z7, s7 = rechnen.kalkulation(kopf, p7, erg7, k, tab, einst)
if s7["mindestpreis_gilt"]:
    a7 = ausgabe.angebot(kopf, p7, z7, k, einst)
    assert a7["zeilen"][0]["preis"] == ausgabe.aufrunden(200 / 7) == 28.58 and a7["netto"] == 200.06, a7["netto"]
assert ausgabe.aufrunden(28.570000000001) == 28.57 and ausgabe.aufrunden(28.5701) == 28.58
ok("M5 Rundung: 200 € / 7 Stück = 28,58 € je Stück, Summe 200,06 € (aufgerundet, nie unter dem Mindestpreis)")

# ------------------------------------------------------------------ M6 Staffelpreise je Stufe
st_klein = staffeln.stufe_rechnen(kopf, pos, "10", 2, k, tab, einst)
assert st_klein["preis"]["mindest_anhebung"] > 0 and st_klein["preis_gesamt"] >= 200 > st_klein["preis"]["netto"] - \
    st_klein["preis"]["mindest_anhebung"]
assert st_klein["preis_gesamt"] - 200 < 0.02 * st_klein["menge"]
st_gross = staffeln.stufe_rechnen(kopf, pos, "10", 400, k, tab, einst)
assert st_gross["preis"]["mindest_anhebung"] == 0 and st_gross["preis_gesamt"] > 200
st_ohne = staffeln.stufe_rechnen(kopf, pos, "10", 2, k, tab, dict(einst, mindestpreis=0))
assert st_ohne["preis"]["mindest_anhebung"] == 0 and st_ohne["preis_gesamt"] < 200
sp = [dict(st_klein, schluessel="10", einheit="Stück", bezeichnung="T10")]
assert ausgabe.angebot(kopf, pos, z0, k, einst, sp)["mindestpreis"] == "Mindestauftragswert 200,00 € netto."
ok(f"M6 Staffelpreise: kleine Stufe auf 200 € angehoben ({st_klein['preis_gesamt']:.2f} €), große Stufe unverändert")

# ------------------------------------------------------------------ L4 Lieferzeit ändert keine Preise
db.angebot_aendern(a, "lieferzeit_wert", "20")
db.angebot_aendern(a, "lieferzeit_zusatz", None)
kopf2 = db.angebot(a)
_, s2 = rechnen.kalkulation(kopf2, pos, erg, k, tab, rechnen.einstellungen_angebot(kopf2, db.einstellungen()))
assert nah(s2["verkauf"], s1["verkauf"]) and rechnen.eingabe_kennung(kopf2, pos, k, tab, einst) == \
    rechnen.eingabe_kennung(kopf, pos, k, tab, einst)
ok("L4 Lieferzeit geändert: Preise und Prüfsumme der Optimierung unverändert (keine Neuberechnung nötig)")

# ------------------------------------------------------------------ L5 Angebots-PDF
texte = []
p_alt = pdf._p
pdf._p = lambda t, *a, **kw: (texte.append(str(t)), p_alt(t, *a, **kw))[1]
try:
    ang = ausgabe.angebot(kopf2, pos, z1, k, einst)
    ziel = tmp / "angebot.pdf"
    pdf.angebot_pdf(ziel, kopf2, ang, db.einstellungen())
finally:
    pdf._p = p_alt
alles = "\n".join(texte)
assert ziel.stat().st_size > 1000
assert "Lieferzeit: ca. 20 Arbeitstage nach Auftragseingang." in alles and "Lieferzeit nach Absprache" not in alles
assert "Mindestauftragswert 200,00 € netto." in alles and "Ihre Anfrage" in alles and "Anfrage 4711" in alles
assert alles.count("Lieferzeit") == 1
# älteres Angebot ohne Lieferzeit: wie bisher nur der Satz aus den Bedingungen
texte.clear()
pdf._p = lambda t, *a, **kw: (texte.append(str(t)), p_alt(t, *a, **kw))[1]
try:
    alt_kopf = dict(kopf2, lieferzeit_art=None, lieferzeit_wert=None, lieferzeit_zusatz=None, kundenreferenz=None)
    pdf.angebot_pdf(tmp / "alt.pdf", alt_kopf, ausgabe.angebot(alt_kopf, pos, z0, k, dict(einst, mindestpreis=0)),
                    db.einstellungen())
finally:
    pdf._p = p_alt
alles = "\n".join(texte)
assert "Lieferzeit nach Absprache." in alles and "Lieferzeit:" not in alles and "Ihre Anfrage" not in alles
assert "Mindestauftragswert" not in alles
ok("L5 Angebots-PDF: Lieferzeit einmal und ohne Widerspruch, Kundenreferenz, Hinweis Mindestauftragswert; ältere Angebote wie bisher")

# ------------------------------------------------------------------ L6 Oberfläche
app = QApplication.instance() or QApplication([])
fenster = Hauptfenster(db, stumm=True)
s = fenster.angebot_oeffnen(a)
kb = s.kopf_bereich
assert kb.lz_art.currentText() == "Arbeitstage" and kb.lz_wert.text() == "20" and kb.lz_wert.isEnabled()
assert "ca. 20 Arbeitstage" in kb.lz_vorschau.text()
kb.lz_art.setCurrentText("Lieferdatum")
assert s.kopf["lieferzeit_art"] == "Lieferdatum" and s.kopf["lieferzeit_wert"] is None
kb.lz_wert.setText("01.01.2020")
kb.lz_wert.editingFinished.emit()
assert s.kopf["lieferzeit_wert"] == "2020-01-01" and kb.lz_wert.text() == "01.01.2020"
kb.lz_wert.setText("30.02.2026")
kb.lz_wert.editingFinished.emit()
assert s.kopf["lieferzeit_wert"] == "2020-01-01" and kb.lz_wert.text() == "01.01.2020"   # abgelehnt, alter Wert
kb.lz_art.setCurrentText("nur Text")
assert not kb.lz_wert.isEnabled()
kb.lz_zusatz.setText("ab Lager")
kb.lz_zusatz.editingFinished.emit()
assert db.angebot(a)["lieferzeit_zusatz"] == "ab Lager" and kb.lz_vorschau.text() == "Im Angebot: Lieferzeit: ab Lager."
assert kb.felder["kundenreferenz"].text() == "Anfrage 4711 vom 20.10.2026"
assert "mindestpreis" not in kb.felder           # nicht je Angebot änderbar (nur Einstellungen)
ok("L6 Angebotsseite: Lieferzeit (Art, Wert, Freitext, Vorschau), ungültiges Datum abgelehnt, Kundenreferenz, kein Mindestpreisfeld")

# ------------------------------------------------------------------ S1 ältere Datei (Schema 23)
db.schliessen()
alt = tmp / "alt.db"
shutil.copy(tmp / "rohrlaser.db", alt)
con = sqlite3.connect(alt)
for spalte in ("lieferzeit_art", "lieferzeit_wert", "lieferzeit_zusatz", "kundenreferenz"):
    con.execute(f"ALTER TABLE angebote DROP COLUMN {spalte}")
con.execute("PRAGMA user_version=23")
con.commit()
con.close()
db2 = Datenbank(alt)
assert db2.con.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
alt_a = db2.angebot(a)
assert alt_a["lieferzeit_art"] is None and alt_a["kundenreferenz"] is None
# Mindestpreis aus den Einstellungen gilt auch für ältere Angebote, auch wenn dort noch 0 gespeichert ist
e2 = rechnen.einstellungen_angebot(dict(alt_a, mindestpreis=0), db2.einstellungen())
assert e2["mindestpreis"] == 200
_, s_alt = rechnen.kalkulation(alt_a, pos, erg, k, tab, e2)
assert nah(s_alt["verkauf"], 200) and s_alt["mindestpreis_gilt"]
assert db2.sicherungen(zusatz=f"vor_Schema_{SCHEMA_VERSION}")
db2.schliessen()
ok("S1 Datei Schema 23: Spalten ergänzt, alte Angebote ohne Lieferzeit, Mindestpreis aus den Einstellungen gilt, Sicherung")
print("OK: Lieferzeit, Kundenreferenz und Mindestpreis je Angebot")
