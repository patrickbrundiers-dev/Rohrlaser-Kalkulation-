"""Online-Preise der Lieferanten (Entwicklungsauftrag Patrick 18.11.2026): Datenmodell, exakte Zuordnung,
Umrechnung €/m · €/kg · €/Stange, Staffel und Konditionen, Preislisten-Import, OCI-Punchout (Formular, lokaler
Empfang, Hintergrundsuche), Schutz vor doppelten Abrufen, nicht erreichbare Lieferanten, Historie und Sprünge,
veraltete Preise, Übernahme ohne Änderung bestehender Angebote, Fenster und Einbindung.

Aufruf: python tests/test_onlinepreise.py
"""
import datetime
import io
import os
import sys
import tempfile
import threading
import urllib.parse
import urllib.request
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402

from rohrlaser import onlinepreise as op, onlinepreise_abruf as ab, onlinepreise_adapter as ad  # noqa: E402
from rohrlaser import funktionen, rechnen, teilen, zugang  # noqa: E402
from rohrlaser.datenbank import ALLE_TABELLEN, Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def ok(t):
    print("OK:", t)


app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
f = Hauptfenster(db, tmp, stumm=True)
k = db.kontext()
RE, RR, QR, S235 = "RE 60x40x3", "RR 42,4x2,0", "QR 40x40x3", "S235-10219"

# ------------------------------------------------------------------ Datenmodell
assert all(t in ALLE_TABELLEN for t in op.TABELLEN) and all(t in teilen.GETEILT for t in op.TABELLEN)
assert op.ABRUFE not in {t.name for t in teilen.GETEILT}          # Protokoll nur dieser Platz
assert "funktion_onlinepreise" in funktionen.FUNKTION
assert op.vorbelegen(db) == 3 and op.vorbelegen(db) == 0
namen = [z["name"] for z in op.lieferanten(db)]
assert any("thyssenkrupp" in n for n in namen) and any("ArcelorMittal" in n for n in namen) and \
    any("Klöckner" in n for n in namen)
assert all(z["weg"] == "Shop-Suche" and not z.get("oci_adresse") for z in op.lieferanten(db))   # nichts erfunden
assert not any("passwort" in fe.name for fe in op.LIEFERANTEN.felder)       # Zugangsdaten nie in der Tabelle
ok("Tabellen geteilt, Protokoll lokal, drei Lieferanten vorbelegt ohne erfundene Zugänge")

# ------------------------------------------------------------------ Zerlegen und exakte Zuordnung
z = op.zerlegen("Rechteckrohr 60 x 40 x 3,0 mm S235JRH EN 10219, 6000 mm")
assert (z["form"], z["a"], z["b"], z["wand"], z["laenge"]) == ("Rechteckrohr", 60, 40, 3, 6000)
assert op.zerlegen("Rundrohr 42,4x2,0 Länge 6 m")["laenge"] == 6000
assert op.zerlegen("Quadratrohr 40x40x3x6000")["laenge"] == 6000


def zu(text, **kw):
    return op.zuordnen(dict(bezeichnung=text, **kw), k)


assert zu("Rechteckrohr 60x40x3 S235JRH EN 10219") == dict(profil_id=RE, werkstoff_id=S235, zuordnung="sicher",
                                                          grund="Profil, Maße und Güte genau gleich")
assert zu("RR 42,4x2,0 S235JRH EN 10219-2")["profil_id"] == RR           # andere Schreibweise der ID
r = zu("Rundrohr 42,4x2,0 S235JRH")                    # Norm fehlt: 10219 (kalt) oder 10210 (warm)?
assert r["zuordnung"] == "prüfen" and "mehrdeutig" in r["grund"]
assert zu("Rechteckrohr 60x40x2,9 S235JRH 10219")["zuordnung"] == "prüfen"     # ähnlich, aber andere Wand
assert zu("Rechteckrohr 60x40x3 S355J2H 10219")["werkstoff_id"] == "S355-10219"
assert zu("QR 40x40x3 S235JRH 10219 feuerverzinkt")["zuordnung"] == "prüfen"    # Oberfläche abweichend
assert zu("Rechteckrohr 60x40x3 S235JR")["zuordnung"] == "prüfen"   # S235JR (Stab) ≠ S235JRH (Hohlprofil)
assert zu("Schraube M8")["zuordnung"] == "keine"
assert op.zuordnen(dict(bezeichnung="Rundrohr 42,4x2 S235JRH"), k, dict(profil_id=RR, werkstoff_id=S235, von="PB"))[
    "zuordnung"] == "bestätigt"
ok("exakte Zuordnung: nur genaue Abmessung + Güte (mit Norm) ist sicher, ähnliche Profile nie automatisch")

# ------------------------------------------------------------------ Einheiten und Normalisierung
assert op.basis_aus_einheit("MTR") == ("€/m", 1) and op.basis_aus_einheit("€/t") == ("€/kg", 1 / 1000)
assert op.basis_aus_einheit("100 kg") == ("€/kg", 1 / 100) and op.basis_aus_einheit("Stk")[0] == "€/Stange"
assert op.basis_aus_einheit("Paket") is None
kg_m = rechnen.kg_je_m(RE, S235, k)
e = dict(profil_id=RE, werkstoff_id=S235, basis="€/kg", preis=1.40, laenge=6000)
n = op.normalisieren(e, k)
assert abs(n["je_m"] - 1.40 * kg_m) < 1e-9 and abs(n["je_stange"] - 6 * n["je_m"]) < 1e-9 and n["je_kg"] == 1.40
n = op.normalisieren(dict(e, basis="€/Stange", preis=60.0), k)
assert abs(n["je_m"] - 10.0) < 1e-9 and abs(n["je_kg"] - 10.0 / kg_m) < 1e-9
assert op.normalisieren(dict(e, profil_id=None, werkstoff_id=None), k)["je_m"] is None   # ohne Zuordnung kein kg/m
assert op.normalisieren(dict(e, preis=None), k)["hinweise"] == ["kein Preis"]
assert op.normalisieren(dict(e, preis=0), k)["netto"] is None
# brutto, Rabatt nur auf Listenpreis, Staffel, Fracht/Mindermenge/Verpackung/Bearbeitung
lief = dict(mwst=19, rabatt=10, fracht=50, frei_ab=1000, mindermenge_bis=250, mindermenge_zuschlag=25, verpackung=5,
            bearbeitung=10)
n = op.normalisieren(dict(e, basis="€/m", preis=11.9, brutto="ja"), k, lief)
assert abs(n["netto"] - 10.0) < 1e-9 and "aus Bruttopreis gerechnet" in n["hinweise"]
n = op.normalisieren(dict(e, basis="€/m", preis=10, preisart="Listenpreis"), k, lief)
assert abs(n["netto"] - 9.0) < 1e-9
assert abs(op.normalisieren(dict(e, basis="€/m", preis=10, preisart="Kundenpreis"), k, lief)["netto"] - 10) < 1e-9
st = dict(e, basis="€/m", preis=10, staffel="ab 1: 10 | ab 100: 9 | ab 500: 8")
assert op.normalisieren(st, k, {}, menge_m=50)["netto"] == 10
assert op.normalisieren(st, k, {}, menge_m=120)["netto"] == 9 and op.normalisieren(st, k, {}, 600)["netto"] == 8
n = op.normalisieren(dict(e, basis="€/m", preis=10), k, lief, menge_m=20)    # 200 € Warenwert
assert n["zusatz"] == 50 + 25 + 5 + 10 and abs(n["einstand_je_m"] - (10 + 90 / 20)) < 1e-9
n = op.normalisieren(dict(e, basis="€/m", preis=10), k, lief, menge_m=200)   # 2.000 €: frachtfrei, keine Mindermenge
assert n["zusatz"] == 15
n = op.normalisieren(dict(e, mindestmenge=10, mengeneinheit="Stange"), k, {}, menge_m=12)
assert any("Mindestmenge" in h for h in n["hinweise"])
ok("Umrechnung €/m, €/kg, €/Stange; brutto/netto, Rabatt, Mengenstaffel, Fracht und Zuschläge, Mindestmenge")

# ------------------------------------------------------------------ Preisliste
CSV = ("Artikelnr;Bezeichnung;Güte;Länge;Nettopreis;Einheit;Mindestmenge;Lieferzeit;Gültig bis;Staffel\n"
       "4711;Rechteckrohr 60x40x3;S235JRH EN 10219;6000;138,00;100 kg;2;3;31.12.2026;\n"
       "4712;Rundrohr 42,4x2,0;S235JRH EN 10219;6;4,10;m;;2;;ab 1: 4,10 | ab 300: 3,90\n"
       "4713;Quadratrohr 40x40x3;S235JRH EN 10219;6000;29,90;St;;;;\n"
       "4714;Rundrohr 42,4x2,0;S235JRH;6000;4,05;m;;;;\n"
       "4715;Rechteckrohr 80x40x3;S235JRH EN 10219;6000;;kg;;;;\n"
       "4716;Rechteckrohr 60x40x3;S235JRH EN 10219;6000;1,20;Paket;;;;\n").encode("cp1252")
eintraege, meldungen = ad.preisliste_lesen(CSV, "liste.csv", {})
assert len(eintraege) == 4 and len(meldungen) == 2          # ohne Preis und mit unbekannter Einheit: gemeldet
e1 = eintraege[0]
assert e1["basis"] == "€/kg" and abs(e1["preis"] - 1.38) < 1e-9 and e1["gueltig_bis"] == "2026-12-31"
assert eintraege[1]["laenge"] == 6000 and eintraege[1]["staffel"].startswith("ab 1")
assert any("kein Preis" in m for m in meldungen) and any("Paket" in m for m in meldungen)
# Excel (.xlsx) mit Kopf nicht in Zeile 1 und Preis €/m im Spaltenkopf
import zipfile  # noqa: E402
puffer = io.BytesIO()
with zipfile.ZipFile(puffer, "w") as zf:
    zf.writestr("xl/worksheets/sheet1.xml", (
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
        '<row r="1"><c r="A1" t="inlineStr"><is><t>Preisliste Klöckner November</t></is></c></row>'
        '<row r="2"><c r="A2" t="inlineStr"><is><t>Artikelnummer</t></is></c><c r="B2" t="inlineStr"><is>'
        '<t>Bezeichnung</t></is></c><c r="C2" t="inlineStr"><is><t>Preis €/m</t></is></c></row>'
        '<row r="3"><c r="A3" t="inlineStr"><is><t>K-1</t></is></c><c r="B3" t="inlineStr"><is>'
        '<t>Rechteckrohr 60x40x3 S235JRH EN 10219 6000 mm</t></is></c><c r="C3"><v>6.05</v></c></row>'
        '</sheetData></worksheet>'))
x, m = ad.preisliste_lesen(puffer.getvalue(), "k.xlsx", {})
assert len(x) == 1 and x[0]["basis"] == "€/m" and x[0]["preis"] == 6.05 and x[0]["laenge"] == 6000
ok("Preislisten CSV und Excel: Spalten erkannt, Einheiten umgerechnet, fehlerhafte Zeilen gemeldet statt geraten")

# ------------------------------------------------------------------ Abruf aus dem Ordner, doppelt, nicht erreichbar
ordner = tmp / "preislisten_tk"
ordner.mkdir()
(ordner / "november.csv").write_bytes(CSV)
tk = next(z for z in op.lieferanten(db) if "thyssenkrupp" in z["name"])
db.aendern(op.LIEFERANTEN.name, tk["id"], "weg", "Preisliste")
db.aendern(op.LIEFERANTEN.name, tk["id"], "preisliste_ordner", str(ordner))
tk = op.lieferant(db, tk["name"])
erg = ab.preislisten(db, tk, k, "manuell")
assert erg["anzahl"] == 4 and erg["neu"] == 4 and erg["ergebnis"] == "ok", erg
assert len(op.aktuelle(db, tk["name"])) == 4
erg = ab.preislisten(db, tk, k, "manuell")              # dieselbe Datei: nicht noch einmal
assert erg["anzahl"] == 0 and "Keine neue Preisliste." in erg["meldungen"]
assert len(op.aktuelle(db, tk["name"])) == 4
rr = next(z for z in op.aktuelle(db, tk["name"]) if z["artikelnr"] == "4714")
assert rr["zuordnung"] == "prüfen"                     # ohne Norm nicht übernehmbar
# nicht erreichbar: Ordner weg -> Fehler im Protokoll, Preise bleiben
db.aendern(op.LIEFERANTEN.name, tk["id"], "preisliste_ordner", str(tmp / "gibt_es_nicht"))
erg = ab.preislisten(db, op.lieferant(db, tk["name"]), k, "start")
assert erg["ergebnis"] == "fehler" and len(op.aktuelle(db, tk["name"])) == 4
assert op.protokoll(db, tk["name"], 1)[0]["ergebnis"] == "fehler"
db.aendern(op.LIEFERANTEN.name, tk["id"], "preisliste_ordner", str(ordner))
tk = op.lieferant(db, tk["name"])
# gleichzeitige Abrufe: derselbe Lieferant nur einmal, die Sperre hält
sp = ab._sperre(tk["name"])
sp.acquire()
try:
    assert ab.laeuft(tk["name"]) and ab.preislisten(db, tk, k, "manuell")["ergebnis"] == "läuft"
finally:
    sp.release()
ergebnisse = []
faeden = [threading.Thread(target=lambda: ergebnisse.append(ab._sperre("X").acquire(blocking=False))) for _ in range(8)]
[t.start() for t in faeden]
[t.join() for t in faeden]
assert ergebnisse.count(True) == 1
ok("Abruf aus dem Ordner, jede Datei nur einmal, nicht erreichbarer Ordner lässt Preise stehen, Sperre je Lieferant")

# ------------------------------------------------------------------ Historie, Änderung, Sprung, veraltet
neu = CSV.replace(b"138,00;100 kg", b"155,00;100 kg")    # +12,3 %
(ordner / "dezember.csv").write_bytes(neu)
erg = ab.preislisten(db, tk, k, "manuell")
assert erg["geaendert"] == 1 and erg["gleich"] == 3, erg
staende = [z for z in db.zeilen(op.PREISE.name) if z["kennung"] == "4711"]
assert len(staende) == 2 and {z["status"] for z in staende} == {"aktuell", "abgelöst"}
akt = next(z for z in staende if z["status"] == "aktuell")
assert abs(akt["aenderung"] - 100 * (1.55 - 1.38) / 1.38) < 0.01
assert [z["kennung"] for z in op.auffaellige(db)] == ["4711"] and op.auffaellige(db, schwelle=20) == []
v = op.verlauf(db, k, RE, S235)
assert len(v) == 2 and v[0]["je_m"] < v[1]["je_m"]
kz = op.kennzahlen(db, k, RE, S235)
assert abs(kz["tiefst"] - 1.38 * kg_m) < 1e-6 and abs(kz["aktuell"] - 1.55 * kg_m) < 1e-6
alt = dict(akt, abruf=(datetime.datetime.now() - datetime.timedelta(days=9)).isoformat(timespec="seconds"))
assert op.veraltet(alt) and not op.veraltet(akt) and op.veraltet(dict(akt, gueltig_bis="2020-01-01"))
ok("Preishistorie: alter Stand abgelöst, Änderung in %, Sprung erkannt, Tiefstpreis, veraltete Stände")

# ------------------------------------------------------------------ Vergleich mehrerer Lieferanten
kl = next(z for z in op.lieferanten(db) if "Klöckner" in z["name"])
op.eintragen(db, kl["name"], dict(artikelnr="K-1", bezeichnung="Rechteckrohr 60x40x3 S235JRH EN 10219",
                                  basis="€/m", preis=6.05, laenge=6000), "Preisliste k.xlsx", k)
am = next(z for z in op.lieferanten(db) if "ArcelorMittal" in z["name"])
op.eintragen(db, am["name"], dict(artikelnr="A-9", bezeichnung="Rechteckrohr 60x40x3", werkstoff="S235JRH EN 10219",
                                  basis="€/Stange", preis=39.0, laenge=6000, brutto="ja"), "Shop (von Hand)", k)
db.aendern(op.LIEFERANTEN.name, kl["id"], "fracht", 80.0)
vg = op.vergleich(db, k, dict(profil_id=RE, werkstoff_id=S235), menge_m=60)
assert len(vg) == 3 and sum(r["bester"] for r in vg) == 1
je = {r["zeile"]["lieferant"]: r["norm"] for r in vg}
assert abs(je[am["name"]]["je_m"] - 39.0 / 1.19 / 6) < 1e-6           # brutto -> netto, Stange -> m
assert abs(je[kl["name"]]["einstand_je_m"] - (6.05 + 80 / 60)) < 1e-9   # Fracht auf die Menge
bester = next(r for r in vg if r["bester"])
assert bester["zeile"]["lieferant"] == am["name"]
# Suche nach Maßen findet auch „prüfen“-Zeilen (ohne Übernahme)
s = op.vergleich(db, k, dict(form="Rundrohr", a=42.4, wand=2.0))
assert any(r["zeile"]["zuordnung"] == "prüfen" and not r["uebernehmbar"] for r in s)
ok("Preisvergleich auf einheitlicher Basis über drei Lieferanten, günstigster übernehmbarer markiert")

# ------------------------------------------------------------------ Übernahme, bestehende Angebote bleiben
a = db.angebot_neu(dict(kunde="Becker GmbH", kundennr="10023", stange=6000, maschine="T03"))
db.position_neu(a, dict(pos=1, artikel="R-1", bezeichnung="Teil", profil_id=RE, werkstoff_id=S235, laenge=1000,
                        stueck=10, schneidweg=300, einstiche=2))
seite = f.angebot_oeffnen(a)
seite.optimieren()
seite.neu_laden()
db.preisbasis_speichern(a, rechnen.preisbasis_aus(seite.kopf, seite.positionen, seite.k, seite.tabellen))
vorher_basis = db.con.execute("SELECT preisbasis FROM angebote WHERE id=?", (a,)).fetchone()[0]
f.angebot_schliessen(a)
try:
    op.uebernehmen(db, k, rr["id"])
    raise AssertionError("prüfen-Zeile darf nicht übernommen werden")
except ValueError:
    pass
ordner_s = db.pfad.parent / "Sicherung"
vorher_s = set(Path(ordner_s).glob("*Onlinepreis*"))
i = op.uebernehmen(db, k, bester["zeile"]["id"])
p = next(z for z in db.zeilen("preise") if z["id"] == i)
assert p["profil_id"] == RE and p["werkstoff_id"] == S235 and p["basis"] == "€/Stange" and p["lieferlaenge"] == 6000
assert abs(p["preis"] - 39.0 / 1.19) < 1e-3 and p["lieferant"] == am["name"] and "Online-Preis" in p["bemerkung"]
assert p["gueltig_ab"] == datetime.date.today().isoformat()
assert db.con.execute("SELECT preisbasis FROM angebote WHERE id=?", (a,)).fetchone()[0] == vorher_basis
assert len(set(Path(ordner_s).glob("*Onlinepreis*")) - vorher_s) >= 1        # Sicherung vor der Änderung
i2 = op.uebernehmen(db, k, next(r for r in vg if r["zeile"]["lieferant"] == kl["name"])["zeile"]["id"], menge_m=60,
                    einstand=True, sichern=False)
p2 = next(z for z in db.zeilen("preise") if z["id"] == i2)
assert i2 == i and p2["basis"] == "€/m" and abs(p2["preis"] - (6.05 + 80 / 60)) < 1e-3
assert any(e["art"] == "Preise" and e["profil_id"] == RE for e in db.preisverlauf(RE, S235))
ok("Übernahme in die Stammdaten Preise mit Sicherung, Quelle und Datum; festgeschriebenes Angebot unverändert")

# ------------------------------------------------------------------ Zuordnung bestätigen
op.zuordnung_bestaetigen(db, rr["id"], RR, S235, "PB", k)
rr2 = next(z for z in db.zeilen(op.PREISE.name) if z["id"] == rr["id"])
assert rr2["zuordnung"] == "bestätigt" and rr2["werkstoff_id"] == S235
art, _ = op.eintragen(db, tk["name"], dict(artikelnr="4714", bezeichnung="Rundrohr 42,4x2,0", werkstoff="S235JRH",
                                           basis="€/m", preis=4.05, laenge=6000), "Preisliste x", k)
assert art == "gleich"
ok("bestätigte Zuordnung gilt für den Artikel und künftige Abrufe")

# ------------------------------------------------------------------ OCI
felder = [("NEW_ITEM-DESCRIPTION[1]", "Rechteckrohr 60x40x3 S235JRH EN 10219"), ("NEW_ITEM-PRICE[1]", "605,00"),
          ("NEW_ITEM-PRICEUNIT[1]", "100"), ("NEW_ITEM-UNIT[1]", "MTR"), ("NEW_ITEM-CURRENCY[1]", "EUR"),
          ("NEW_ITEM-VENDORMAT[1]", "KL-77"), ("NEW_ITEM-LEADTIME[1]", "2"),
          ("NEW_ITEM-LONGTEXT_1:132[]", "Lagerlänge 6000 mm"),
          ("NEW_ITEM-DESCRIPTION[2]", "Rundrohr 42,4x2"), ("NEW_ITEM-PRICE[2]", ""), ("NEW_ITEM-UNIT[2]", "MTR"),
          ("NEW_ITEM-DESCRIPTION[3]", "Flach 40x5"), ("NEW_ITEM-PRICE[3]", "1500"), ("NEW_ITEM-UNIT[3]", "TNE")]
x, m = ad.oci_artikel(felder)
assert len(x) == 2 and len(m) == 1
assert x[0]["artikelnr"] == "KL-77" and x[0]["basis"] == "€/m" and abs(x[0]["preis"] - 6.05) < 1e-9
assert x[0]["laenge"] == 6000 and x[0]["lieferzeit"] == 2 and x[1]["basis"] == "€/kg" and x[1]["preis"] == 1.5
html_antwort = ("<html><form action='http://127.0.0.1/' method='post'>" + "".join(
    f"<input type='hidden' name='{n}' value='{v}'>" for n, v in felder[:8]) + "</form></html>")
assert ad.oci_felder_aus_html(html_antwort)[1] == ("NEW_ITEM-PRICE[1]", "605,00")


class Antwort(io.BytesIO):
    headers = type("H", (), {"get_content_charset": staticmethod(lambda: "utf-8")})()
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


gesendet = []


def oeffnen(req, timeout=None):
    gesendet.append(urllib.parse.parse_qs(req.data.decode()))
    return Antwort(html_antwort.encode())


x, m = ad.oci_hintergrund("https://shop.example/oci", "OCI-U", "geheim", "Rechteckrohr 60x40x3", oeffnen)
assert len(x) == 1 and gesendet[0]["FUNCTION"] == ["BACKGROUND_SEARCH"] and gesendet[0]["USERNAME"] == ["OCI-U"]
try:
    ad.oci_hintergrund("http://shop.example/oci", "u", "p", "x", oeffnen)
    raise AssertionError("OCI ohne https")
except ValueError:
    pass
# Hintergrundsuche mit Cache: dieselbe Suche geht nicht zweimal raus
ab.cache_leeren()
gesendet.clear()
kl = op.lieferant(db, kl["name"])
kl_oci = dict(kl, weg="OCI-Punchout", oci_adresse="https://shop.example/oci", oci_hintergrund="ja")
geholt = ab.holen_oci(kl_oci, ("OCI-U", "geheim"), ["Rechteckrohr 60x40x3", "Rechteckrohr 60x40x3"], oeffnen)
geholt2 = ab.holen_oci(kl_oci, ("OCI-U", "geheim"), ["Rechteckrohr 60x40x3"], oeffnen)
assert len(gesendet) == 1 and len(geholt[0]) == 1 and len(geholt2[0]) == 1
erg = ab.oci_speichern(db, kl_oci, k, geholt, "manuell")
assert erg["anzahl"] == 1 and erg["ergebnis"] == "ok"


def kaputt(req, timeout=None):
    raise OSError("Verbindung abgelehnt")


ab.cache_leeren()
vorher = len(db.zeilen(op.PREISE.name))
geholt = ab.holen_oci(kl_oci, ("u", "p"), ["Rundrohr 42,4x2"], kaputt)
assert geholt[0] == [] and "abgelehnt" in geholt[1][0]
erg = ab.oci_speichern(db, kl_oci, k, geholt, "uhr")
assert erg["ergebnis"] == "fehler" and len(db.zeilen(op.PREISE.name)) == vorher
assert ab.holen_oci(kl_oci, None, ["x"])[1] == ["Kein OCI-Zugang hinterlegt."]
# Interaktiver Punchout: lokale Startseite (einmal, Passwort nur per POST) und Rückgabe an die HOOK_URL
emp = ad.OciEmpfang("https://shop.example/oci", "OCI-U", "geheim", "Rechteckrohr 60x40x3")
try:
    seite_html = urllib.request.urlopen(emp.start_adresse, timeout=5).read().decode()
    assert "geheim" in seite_html and "method='post'" in seite_html and "BACKGROUND" not in seite_html
    assert "geheim" not in emp.start_adresse
    try:
        urllib.request.urlopen(emp.start_adresse, timeout=5)        # zweites Mal: nicht mehr
        raise AssertionError("Startseite zweimal")
    except urllib.error.HTTPError as fehler:
        assert fehler.code == 404
    hook = [v for n, v in ad.oci_felder_aus_html(seite_html) if n == "HOOK_URL"][0]
    assert hook == emp.hook and hook.startswith("http://127.0.0.1:")
    try:
        urllib.request.urlopen(urllib.request.Request(hook.split("?")[0] + "?t=falsch",
                                                      data=urllib.parse.urlencode(felder).encode()), timeout=5)
        raise AssertionError("fremder Hook")
    except urllib.error.HTTPError as fehler:
        assert fehler.code == 404
    urllib.request.urlopen(urllib.request.Request(hook, data=urllib.parse.urlencode(felder).encode()), timeout=5)
    assert emp.fertig.wait(5) and len(emp.ergebnis[0]) == 2
finally:
    emp.stoppen()
ok("OCI: Formularfelder, Preiseinheit, Hintergrundsuche mit Cache, Fehler ohne Preisverlust, lokaler Empfang")

# ------------------------------------------------------------------ Verbindung testen, Zugangsdaten, fällig
assert ad.testen(dict(weg="Preisliste", preisliste_ordner=str(ordner)))[0]
assert not ad.testen(dict(weg="Preisliste", preisliste_ordner=str(tmp / "nein")))[0]
assert not ad.testen(dict(weg="OCI-Punchout", oci_adresse="https://shop.example/oci"))[0]      # ohne Zugang
assert ad.testen(dict(weg="OCI-Punchout", oci_adresse="https://shop.example/oci", oci_hintergrund="ja"),
                 ("u", "p"), oeffnen)[0]
assert not ad.testen(dict(weg="Shop-Suche", shop_adresse="https://shop.example"), None, kaputt)[0]
assert ad.shop_adresse(dict(such_adresse="https://s.example/suche?q={suche}"), "RE 60x40x3") == \
    "https://s.example/suche?q=RE%2060x40x3"
assert ad.shop_adresse(dict(shop_adresse="https://s.example"), "x") == "https://s.example"
assert zugang.speichern("Test-Lieferant", "u1", "p1") is (sys.platform == "win32")
assert zugang.lesen("Test-Lieferant") == ("u1", "p1") and zugang.loeschen("Test-Lieferant")
assert zugang.lesen("Test-Lieferant") is None
jetzt = datetime.datetime.now()
tk = op.lieferant(db, tk["name"])
db.aendern(op.LIEFERANTEN.name, tk["id"], "aktualisierung", "täglich")
tk = op.lieferant(db, tk["name"])
assert not op.faellig(db, tk, "start")                 # gerade erst abgerufen
assert op.faellig(db, tk, "start", jetzt + datetime.timedelta(days=1, minutes=5))
assert not op.faellig(db, tk, "oeffnen", jetzt + datetime.timedelta(days=2))
assert not op.faellig(db, dict(tk, weg="Shop-Suche"), "start", jetzt + datetime.timedelta(days=9))  # nie automatisch
assert not op.faellig(db, dict(tk, aktiv="nein"), "start", jetzt + datetime.timedelta(days=9))
ok("Verbindung testen, Zugangsdaten außerhalb der Datenbank, Aktualisierung täglich/wöchentlich/beim Öffnen")

# ------------------------------------------------------------------ Fenster
from rohrlaser.onlinepreise_dialog import OnlinePreiseDialog  # noqa: E402
d = OnlinePreiseDialog(db, f, dict(profil_id=RE, werkstoff_id=S235, menge_m=60))
assert d.e_abmessung.text() == RE and d.e_form.currentText() == "Rechteckrohr" and d.tabelle.rowCount() == 4  # mit OCI-Artikel KL-77
assert "Materialstamm" in d.info.text() and "Tiefstpreis" in d.info.text()
d.reiter.setCurrentIndex(1)
assert d.v_tabelle.rowCount() >= 3 and d.kurve.punkte
d.reiter.setCurrentIndex(0)
d.e_abmessung.setText("RE 60x40x2,9")
d._abmessung_zerlegen()
d.suchen()
assert d.tabelle.rowCount() == 0 and "Keine Online-Preise" in d.leer.text()
d.e_abmessung.setText(RE)
d._abmessung_zerlegen()
d.suchen()
offen = []
d.browser = offen.append
assert d.shop_suche(kl["name"]) == "https://shop.kloeckner.de" and offen
assert QApplication.clipboard().text().startswith("Rechteckrohr 60x40x3")
i = d.erfassen(dict(lieferant=am["name"], artikelnr="A-9", bezeichnung="Rechteckrohr 60x40x3",
                    werkstoff="S235JRH EN 10219", basis="€/Stange", preis=36.0, laenge=6000, brutto="nein",
                    quelle="Shop (von Hand)"))
assert i and d.tabelle.rowCount() == 4
d.tabelle.selectRow(0)
assert d.markiert()["bester"]
pid_ = d.uebernehmen(frage=False)
assert pid_ and abs(next(z for z in db.zeilen("preise") if z["id"] == pid_)["preis"] - 36.0) < 1e-9
assert d.uebernehmen(frage=False) == pid_ and d.gesichert          # zweite Übernahme ohne neue Sicherung
# Lieferanten: neue Zeile, Werte ändern, Zugang, Verbindung testen, Preisliste wählen
d.reiter.setCurrentIndex(2)
neu_id = d.lieferant_neu("Eigener Händler")
d.lieferanten_neu()
r = next(r for r in range(d.l_tabelle.rowCount()) if d.l_tabelle.item(r, 0).text() == "Eigener Händler")
d.l_tabelle.setCurrentCell(r, 0)
spalte = [x for x, _ in __import__("rohrlaser.onlinepreise_dialog", fromlist=["x"]).LIEF_SPALTEN].index("rabatt")
d.l_tabelle.item(r, spalte).setText("12,5")
assert op.lieferant(db, "Eigener Händler")["rabatt"] == 12.5
assert d.zugang_bearbeiten("u", "p") and zugang.lesen("Eigener Händler") == ("u", "p")
d.l_tabelle.setCurrentCell(r, 0)
assert d.verbindung_testen()[0] is False                  # Preisliste ohne Ordner
d.l_tabelle.setCurrentCell(r, 0)
erg = d.preisliste_waehlen([str(ordner / "november.csv")])
assert erg["anzahl"] == 4
d.reiter.setCurrentIndex(3)
assert d.p_tabelle.rowCount() >= 5
d.l_tabelle.setCurrentCell(r, 0)
d.lieferant_weg(frage=False)
assert op.lieferant(db, "Eigener Händler") is None and zugang.lesen("Eigener Händler") is None
d.reject()
ok("Fenster: Vorwahl, Vergleich, Verlauf mit Kurve, Shop-Suche, Preis erfassen, Übernehmen, Lieferanten, Protokoll")

# ------------------------------------------------------------------ Einbindung
assert "Online-Preise …" in f.datei_aktionen
d2 = f.onlinepreise(dict(profil_id=RE, werkstoff_id=S235), zeigen=False)
assert d2.tabelle.rowCount() >= 3
d2.reject()
assert f.onlinepreise_auto("start") == [] or True                   # nie ein Fehler
seite = f.angebot_oeffnen(a)
geprueft = {}


def im_material(md):
    texte = [t for t, _, _ in md.menue_eintraege(0) if t]
    assert "Online-Preise vergleichen …" in texte
    d3 = md.onlinepreise(0, zeigen=False)
    geprueft.update(abmessung=d3.e_abmessung.text(), menge=d3.e_menge.text())
    d3.reject()
    return False


seite.material_einstellen(dialog=im_material)
assert geprueft["abmessung"] == RE and geprueft["menge"], geprueft
f.angebot_schliessen(a)
ok("Einbindung: Datei → Online-Preise, Material-Fenster (Kontextmenü), automatischer Abruf ohne Fehler")
print("Alle Tests Online-Preise bestanden.")
