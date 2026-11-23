"""Materialdatenbank (Master-Auftrag Patrick 23.11.2026):
- ERP-Stammdaten-Import: Formate (ANSI/Semikolon/Dezimalkomma, UTF-8/Tab/Punkt, Excel), Spaltenvorschlag,
  Importprofile, Preiseinheiten (€/m, €/kg, €/t, €/Stange), Vorschau-Gruppen, nie raten (S355 ohne Norm offen),
  doppelte/fehlerhafte Zeilen, Übernehmen nur mit Vorschau, zweiter Lauf unverändert, Rückgängig, Fehler-CSV,
  Materialnummer-Änderung als Hinweis, große Datei (Tempo),
- Materialstamm: Artikelnummer je Abmessung × Werkstoff, Werkstoffe je Abmessung (Wahl statt Raten), inaktiv,
- Lieferanten: Staffel, Verpackungseinheit, bevorzugter Lieferant, Vergleich,
- Seite Material: 11 Bereiche, Dashboard, ERP-Import ohne Dialog, Importhistorie mit Rückgängig, Preisverlauf mit
  Herkunft, Excel-Export, STEP-Hinweis aus dem Materialstamm.
Alle Preise sind Testwerte.

Aufruf: python tests/test_materialdatenbank.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import os
import sys
import tempfile
import time
import zipfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402

from rohrlaser import admin_schutz  # noqa: E402
from rohrlaser import erp_anlegen as A  # noqa: E402
from rohrlaser import material_bereiche as MB  # noqa: E402
from rohrlaser import material_import as M  # noqa: E402
from rohrlaser import material_stamm as S  # noqa: E402
from rohrlaser import materialplattform as mp  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402

app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())


def ok(text):
    print("OK    ", text)


CSV = ("Artikelnummer;Artikelbezeichnung;Werkstoff;Abmessung;EK-Preis;ME;Lieferant;Gewicht kg/m;Preisdatum\n"
       "100421;Rundrohr 42,4x2,0;S235JRH EN10219;;1,52;kg;Stahlhandel Nord;1,99;01.11.2026\n"
       "100430;Quadratrohr;S235JRH EN 10219;40x40x3;3,40;m;;;\n"
       "100555;Rechteckrohr 80x40x3;S275J0H EN10210 warmgefertigt;;980;t;;;\n"
       "100556;Rundrohr 33,7x2,0;S355;;2,10;m;;;\n"
       "100557;Rundrohr 33,7x2,0;1.4301;;abc;m;;;\n"
       "100421;Rundrohr 42,4x2,0;S235JRH EN10219;;1,52;kg;Stahlhandel Nord;1,99;01.11.2026\n"
       "100600;RR 60,3x2,9 S235 EN10219;;;14,50;Stück;;;\n")

# ------------------------------------------------------------------ ohne Datenbank: Lesen und Spalten
d = M.lesen(CSV.encode("cp1252"))
sp = M.spalten_vorschlag(d["kopf"])
assert {"materialnr", "bezeichnung", "werkstoff", "abmessung", "preis", "einheit", "lieferant", "gewicht",
        "gueltig_ab"} <= set(sp), sp
assert not M.fehlende(sp) and M.fehlende({"materialnr": 0})
tab = ("Item No\tDescription\tGrade\tSize\tPrice\tUnit\tSupplier\n"
       "A-77\tRound tube\tS235JRH EN 10219\t42,4x2,0\t1650\tt\tRohrwerk West\n"
       "A-78\tSquare tube\tS235JRH EN 10219\t50x50x3\t4.25\tm\tRohrwerk West\n")
d_tab = M.lesen(tab.encode("utf-8"))
sp_tab = M.spalten_vorschlag(d_tab["kopf"])
assert {"materialnr", "werkstoff", "abmessung", "preis", "einheit", "lieferant"} <= set(sp_tab), sp_tab
assert M.einheit_lesen("t")[0] == "€/kg" and abs(M.einheit_lesen("t")[1] - 0.001) < 1e-12
assert M.einheit_lesen("Stück")[0] == "€/Stange" and M.einheit_lesen("", "€/m")[0] == "€/m"
ok("Lesen: ANSI/Semikolon/Dezimalkomma und UTF-8/Tab/Punkt mit englischen Köpfen; Spaltenvorschlag; Einheiten €/t, Stück")

# Excel ohne Zusatzpaket: schreiben (Export) und wieder lesen (Import)
px = tmp / "liste.xlsx"
mp.xlsx_export([dict(materialnr="300010", form="Rundrohr", a=48.3, wand=2.6, werkstoff="S235JRH EN 10219",
                     preis="3,80", einheit="€/m")], px, kopf=["Materialnr", "Profilart", "Außendurchmesser",
                                                               "Wandstärke", "Werkstoff", "Einkaufspreis", "Einheit"],
               felder=["materialnr", "form", "a", "wand", "werkstoff", "preis", "einheit"])
assert zipfile.is_zipfile(px)
dx = M.lesen(px.read_bytes(), str(px))
spx = M.spalten_vorschlag(dx["kopf"])
assert dx["kopf"][0] == "Materialnr" and {"materialnr", "form", "a", "wand", "werkstoff", "preis", "einheit"} <= \
    set(spx), (dx["kopf"], spx)
ok("Excel: Export als .xlsx und Import derselben Datei mit getrennten Maßspalten (ohne openpyxl)")

# ------------------------------------------------------------------ Datenbank
db = Datenbank(tmp / "rohrlaser.db")
admin_schutz.ist_admin = lambda db, sitzung=None: True       # Tests: Admin freigeschaltet
assert db.zeilen("materialstamm"), "Materialstamm aus dem Bestand beim Start"
assert db.einstellung("materialstamm_stand") == S.STAND
for n in ("Stahlhandel Nord", "Stahlhandel Süd", "Rohrwerk West"):
    if n not in db.kontext().zukauf_lieferanten:
        db.neu("zukauf_lieferanten", dict(name=n))
ok(f"Migration: Materialstamm aus Preisen/Lieferlängen beim Start ({len(db.zeilen('materialstamm'))} Zeilen), einmalig")

posten = M.analysieren(db, d, sp, "€/m", None)
g = {e["zeile"]: e for e in posten}
z = M.zaehlen(posten)
assert z[M.DOPPELT] == 1 and g[7]["gruppe"] == M.DOPPELT
assert z[M.FEHLER] == 1 and g[6]["gruppe"] == M.FEHLER
assert g[5]["gruppe"] == M.OFFEN, g[5]          # S355 ohne Norm: mehrere Werkstoffe -> nicht raten
assert g[2]["profil_id"] == "RR 42,4x2,0" and g[2]["werkstoff_id"] == "S235-10219" and g[2]["basis"] == "€/kg"
assert g[4]["werkstoff_id"] == "S275-10210" and g[4]["basis"] == "€/kg" and abs(g[4]["preis"] - 0.98) < 1e-9
assert g[4].get("werkstoff_neu"), "S275 EN 10210 wird angelegt"
assert g[8]["basis"] == "€/Stange" and abs(g[8]["preis_m"] - 14.5 / 6) < 0.01
assert all(e["gruppe"] in M.GRUPPEN for e in posten)
assert "materialnr" in M.fehler_csv(posten).lower() or "Zeile" in M.fehler_csv(posten)
ok("Vorschau: doppelt, fehlerhaft (Preis abc), nicht zuordenbar (S355 ohne Norm), €/t → €/kg, €/Stange → €/m")

vorher = {(p["profil_id"], p["werkstoff_id"]): dict(p) for p in db.zeilen("preise")}
erg = M.ausfuehren(db, posten, datei="test.csv", importprofil="", sichern=False)
assert erg["import_id"] and erg["werkstoffe"] == 1
st = S.zeilen_je(db)
assert st[("RR 42,4x2,0", "S235-10219", "")]["materialnr"] == "100421"
assert st[("RE 80x40x3", "S275-10210", "")]["materialnr"] == "100555"
p = next(p for p in db.zeilen("preise") if (p["profil_id"], p["werkstoff_id"]) == ("RR 42,4x2,0", "S235-10219"))
assert p["basis"] == "€/kg" and abs(float(p["preis"]) - 1.52) < 1e-9 and p["lieferant"] == "Stahlhandel Nord"
assert not any(e["materialnr"] == "100556" for e in posten if e["gruppe"] in M.AUSFUEHRBAR)
assert M.laeufe(db)[0]["status"] == "übernommen" and M.letzter_lauf(db)["id"] == erg["import_id"]
ok(f"Übernehmen: {erg['neu']} neu, {erg['preise']} Preise, Werkstoff S275-10210 angelegt, Artikelnummer je "
   "Abmessung × Werkstoff im Materialstamm, Lauf in der Importhistorie")

z2 = M.zaehlen(M.analysieren(db, d, sp, "€/m", None))
assert z2[M.NEU] == 0 and z2[M.PREIS] == 0 and z2[M.GLEICH] >= 3, z2
ok("Zweiter Import derselben Datei: alles unverändert, nichts doppelt")

d3 = M.lesen(CSV.replace("100430;Quadratrohr", "999430;Quadratrohr").encode("cp1252"))
e3 = next(e for e in M.analysieren(db, d3, sp, "€/m", None) if e["materialnr"] == "999430")
assert any("Materialnummer 100430 → 999430" in h for h in e3["hinweis"]), e3["hinweis"]
ok("Geänderte Materialnummer steht als Hinweis in der Vorschau (nie unbemerkt überschreiben)")

# Erkennung vorhandener Werte über Artikel- und Bestellnummer (Patrick 23.11.2026)
db.neu(mp.LIEFERANTEN_TABELLE, dict(profil_id="QR 40x40x3", werkstoff_id="S235-10219", lieferant="Stahlhandel Süd",
                                    basis="€/m", preis=3.5, laenge=6000, artikelnr="SN-4040"))
dn = M.lesen("Artikelnummer;Bestellnummer;Bezeichnung;EK-Preis\n100421;;Rohr unbekannt;3,00\n;SN-4040;Ware;3,60\n"
             "777;;Ware ohne Angaben;1,00\n".encode("utf-8"))
spn = M.spalten_vorschlag(dn["kopf"])
assert spn.get("materialnr") == 0 and spn.get("bestellnr") == 1, spn
pn = M.analysieren(db, dn, spn, "€/m", None)
assert (pn[0]["profil_id"], pn[0]["werkstoff_id"]) == ("RR 42,4x2,0", "S235-10219") and "Artikelnummer" in \
    " ".join(pn[0]["hinweis"]) or "Materialnummer" in " ".join(pn[0]["hinweis"]), pn[0]
assert (pn[1]["profil_id"], pn[1]["werkstoff_id"]) == ("QR 40x40x3", "S235-10219") and "Bestellnummer" in \
    " ".join(pn[1]["hinweis"]), pn[1]
assert pn[2]["gruppe"] in (M.OFFEN, M.FEHLER)
from rohrlaser import erp_preise as E  # noqa: E402
kauf = dict(zeile=1, datum=__import__("datetime").date.today(), menge=12, preis=3.0, artikelnr="100421",
            bezeichnung="Ware 4711", schluessel=E.schluessel("100421", "Ware 4711"))
ea = E.artikel([kauf], {}, db.kontext(), E.nummern_von(db))[0]
assert ea["ampel"] == E.GRUEN and ea["profil_id"] == "RR 42,4x2,0" and "Materialnummer" in ea["hinweis"], ea
assert E.artikel([kauf], {}, db.kontext())[0]["ampel"] != E.GRUEN
ok("Vorhandene Werte über Artikelnummer (Materialstamm) und Bestellnummer (Lieferant) erkannt, im Stammdaten- und "
   "im EK-Import; ohne Nummer nie geraten")

aend = M.preis_aenderungen(db, erg["import_id"])
assert any(a["profil_id"] == "RR 42,4x2,0" for a in aend)
n, meld = M.rueckgaengig(db, erg["import_id"])
assert n > 0 and M.laeufe(db)[0]["status"].startswith("rückgängig")
st = S.zeilen_je(db)
assert ("RE 80x40x3", "S275-10210", "") not in st
nachher = {(p["profil_id"], p["werkstoff_id"]): dict(p) for p in db.zeilen("preise")}
assert nachher.keys() == vorher.keys()
assert all(str(nachher[k].get("preis")) == str(vorher[k].get("preis")) for k in vorher)
ok(f"Rückgängig: {n} Änderungen zurückgenommen, Preise wie vorher, neue Materialien weg")

# Importprofile
M.profil_speichern(db, "ERP Standard", d["kopf"], sp, "€/m", "Stahlhandel Nord")
name, prof = M.profil_fuer(db, d["kopf"])
assert name == "ERP Standard" and prof["spalten"] == sp and prof["lieferant"] == "Stahlhandel Nord"
M.profil_loeschen(db, "ERP Standard")
assert M.profil_fuer(db, d["kopf"])[0] is None
ok("Importprofil: speichern, beim gleichen Spaltenkopf automatisch wählen, löschen")

# Große Datei
gross = ["Artikelnummer;Bezeichnung;Werkstoff;EK-Preis;ME"]
for i in range(4000):
    gross.append(f"{500000 + i};Rundrohr {20 + i % 80},{i % 10}x{1 + i % 4},0;S235JRH EN10219;{2 + i % 50},{i % 100};m")
t0 = time.perf_counter()
dg = M.lesen("\n".join(gross).encode("utf-8"))
pg = M.analysieren(db, dg, M.spalten_vorschlag(dg["kopf"]), "€/m", None)
dt = time.perf_counter() - t0
assert len(pg) == 4000 and dt < 30, dt
ok(f"Große Datei: 4.000 Zeilen gelesen und geprüft in {dt:.1f} s")

# ------------------------------------------------------------------ Materialstamm und Lieferanten
k = db.kontext()
stz = db.zeilen("materialstamm")
def stamm_setzen(pid, wid, aktiv):
    z = S.zeilen_je(db).get((pid, wid, ""))
    if z is None:
        db.neu("materialstamm", dict(profil_id=pid, werkstoff_id=wid, aktiv=aktiv, quelle="Test"))
    else:
        db.aendern("materialstamm", z["id"], "aktiv", aktiv)


stamm_setzen("RR 42,4x2,0", "S355-10219", "ja")
ws = S.werkstoffe_fuer("RR 42,4x2,0", db.zeilen("materialstamm"), k)
assert [w["werkstoff_id"] for w in ws][:2] == ["S235-10219", "S355-10219"] or len(ws) >= 2
stamm_setzen("RR 42,4x2,0", "1.4301", "nein")
assert "1.4301" not in [w["werkstoff_id"] for w in S.werkstoffe_fuer("RR 42,4x2,0", db.zeilen("materialstamm"), k)]
assert not S.aktiv(S.zeilen_je(db), "RR 42,4x2,0", "1.4301") and S.aktiv(S.zeilen_je(db), "RR 42,4x2,0", "S235-10219")
ok("Materialstamm: mehrere Werkstoffe je Abmessung (Wahl statt Raten), inaktive fehlen in der Auswahl")

L = mp.LIEFERANTEN_TABELLE
for preis, lief, bev, ab, ve in ((1.50, "Stahlhandel Süd", "ja", None, None), (1.48, "Rohrwerk West", None, None, None),
                                 (1.30, "Stahlhandel Nord", None, 500, 10)):
    db.neu(L, dict(profil_id="RR 42,4x2,0", werkstoff_id="S235-10219", lieferant=lief, basis="€/kg", preis=preis,
                   laenge=6000, gueltig_bis="2099-12-31", lieferzeit=5, bevorzugt=bev, ab_menge=ab, ve_stangen=ve))
kgm = mp.kg_je_m(k.profile["RR 42,4x2,0"], k.werkstoffe["S235-10219"])
alle = S.angebote_fuer(db.zeilen(L), "RR 42,4x2,0", "S235-10219", kgm, 60)
assert not any(a["lieferant"] == "Stahlhandel Nord" and a["preis_m"] < 1.4 * kgm for a in alle), \
    "Staffel ab 500 m gilt bei 60 m nicht"
v = S.lieferant_vorschlag(db.zeilen(L), "RR 42,4x2,0", "S235-10219", kgm, 60)
assert v["lieferant"] == "Stahlhandel Süd" and "bevorzugt" in v["begruendung"], v
v2 = S.lieferant_vorschlag(db.zeilen(L), "RR 42,4x2,0", "S235-10219", kgm, 60, gleich_pct=0.5)
assert v2["lieferant"] == "Rohrwerk West", v2
ok("Lieferanten: Staffel ab Menge, bevorzugter Lieferant bis 2 % Mehrkosten, sonst der günstigste")

kz = S.kennzahlen(db)
assert kz["werkstoffe"] > 0 and kz["abmessungen"] > 0 and kz["stamm"] >= 2 and kz["inaktiv"] >= 1
ok("Dashboard-Kennzahlen: Werkstoffe, Abmessungen, Varianten, Materialstamm, inaktiv, alte Preise, letzter Import")

# STEP: Hinweis aus dem Materialstamm, nie raten
m1 = dict(profilform="Rundrohr", _profil="RE 80x40x3")
if "RE 80x40x3" not in db.kontext().profile:
    db.neu("profile", dict(profil_id="RE 80x40x3", form="Rechteckrohr", a=80, b=40, wand=3))
stamm_setzen("RE 80x40x3", "S355-10219", "ja")
k = db.kontext()
A.vorauswahl([m1], k.profile, {}, "S235-10219", stamm=db.zeilen("materialstamm"), k=k)
assert "_werkstoff" not in m1 and "S355-10219" in m1.get("_werkstoff_text", ""), m1
ok("STEP-Import: Abmessung im Materialstamm nur in anderem Werkstoff → Hinweis, Werkstoff bleibt (kein Raten)")

# ------------------------------------------------------------------ Seite Material
from rohrlaser.fenster import Hauptfenster  # noqa: E402

f = Hauptfenster(db, tmp, stumm=True)
m = f.material
namen = [m.bereiche.tabText(i) for i in range(m.bereiche.count())]
assert namen == list(MB.BEREICHE), namen
assert m.bereiche.currentWidget() is m.uebersicht
for b in MB.BEREICHE:
    MB.bereich_zeigen(m, b)
assert MB.tabellenseite(m, "Materialkombinationen").t.name == "materialstamm"
assert int(m.dashboard.kacheln["stamm"].wert.text()) >= 2
ok("Seite Material: 11 Bereiche, Tabellenbereiche wie in den Einstellungen, Dashboard mit Kacheln")

pd = tmp / "erp.csv"
pd.write_bytes(CSV.encode("cp1252"))
r = MB.stamm_import(m, str(pd), uebernehmen=M.AUSFUEHRBAR, spalten=sp, profil_name="ERP")
assert r["erg"]["import_id"] and "ERP" in M.profile(db)
hs = MB.bereich_zeigen(m, "Importhistorie")
assert hs.laeufe and hs.laeufe[0]["id"] == r["erg"]["import_id"]
vz = MB.verlauf_zeilen(db)
assert any(z["herkunft"].startswith("ERP-Import") for z in vz)
n, _ = hs.rueckgaengig(r["erg"]["import_id"], frage=False)
assert n > 0 and M.laeufe(db)[0]["status"].startswith("rückgängig")
v = MB.VorschauDialog(m, M.analysieren(db, d, sp, "€/m", None))
assert set(v.gruppen()) <= set(M.AUSFUEHRBAR) and v.reiter.count() == len(M.GRUPPEN)
fp = v.fehler_exportieren(str(tmp / "fehler.csv"))
assert Path(fp).read_text(encoding="utf-8-sig").count("\n") >= 3
ok("ERP-Import über die Seite: Importprofil, Importhistorie, Preisverlauf mit Herkunft, Rückgängig, Fehler-CSV")

res = MB.lieferantenvergleich(m, "RR 42,4x2,0", "S235-10219", 60, frage=False)
assert res and res[1]["lieferant"] == "Stahlhandel Süd"
MB.bereich_zeigen(m, "Materialübersicht")
m.alle_box.setChecked(True)
m.neu_laden(erzwingen=True)
zz = next(z for z in m.alle_zeilen if (z["profil_id"], z["werkstoff_id"]) == ("RR 42,4x2,0", "S235-10219"))
m.stamm_aktiv(zz, False)
assert not S.aktiv(S.zeilen_je(db), "RR 42,4x2,0", "S235-10219")
m.stamm_aktiv(zz, True)
assert S.aktiv(S.zeilen_je(db), "RR 42,4x2,0", "S235-10219")
xp = m.exportieren(m.alle_zeilen[:20], str(tmp / "material.xlsx"))
assert zipfile.is_zipfile(xp) and "RR" in (mp.xlsx_als_csv(xp) or "")
ok("Lieferantenvergleich, Materialstamm aktiv/inaktiv per Kontextmenü, Excel-Export der Materialliste")

# Menü „Material …“ im Angebot
sys.path.insert(0, str(HIER))
import beispiel_angebot  # noqa: E402

an = f.angebot_oeffnen(beispiel_angebot.anlegen(db))
assert an.material_knopf.menu() is None, "Knopf öffnet direkt das Fenster"
assert an.material_bereich("ERP-Import") is m and m.bereiche.tabText(m.bereiche.currentIndex()) == "ERP-Import"
assert f.reiter.currentWidget() is m
f.reiter.setCurrentWidget(an)
an.optimieren()
gesehen = {}


def fenster(d):
    gesehen["kacheln"] = {k: w.text() for k, w in d.kacheln.items()}
    gesehen["knoepfe"] = list(d.aktionen)
    gesehen["bereiche"] = [a.text() for a in d.datenbank_menue.actions()]
    gesehen["menue"] = [t for t, _, _ in d.menue_eintraege(0) if t]
    gesehen["vergleich"] = d.lieferantenvergleich(0, frage=False)
    d.datenbank_menue.actions()[3].trigger()        # Lieferanten: übernimmt und springt in die Materialdatenbank
    return True


an.material_einstellen(fenster)
assert gesehen["knoepfe"] == ["Material suchen und zuweisen …", "Lieferantenvergleich …", "Materialdatenbank"], gesehen
assert gesehen["bereiche"] == ["Dashboard", "Materialübersicht", "Einkaufspreise", "Lieferanten", "Preisverlauf",
                               "ERP-Import …"], gesehen["bereiche"]
assert int(gesehen["kacheln"]["abmessungen"]) >= 1 and gesehen["kacheln"]["stangen"] != "–", gesehen["kacheln"]
assert {"Lieferantenvergleich …", "Material suchen und zuweisen …"} <= set(gesehen["menue"])
assert isinstance(gesehen["vergleich"], tuple)
assert f.reiter.currentWidget() is m and m.bereiche.tabText(m.bereiche.currentIndex()) == "Lieferanten"
ok("Angebot: „Material …“ öffnet direkt das Fenster; dort Kacheln, Material suchen und zuweisen, "
   "Lieferantenvergleich und Sprünge in die Materialdatenbank")

# Lieferzeit je Material aus dem EK (Patrick 23.11.2026): L-Termin minus Datum Erf.; ERP-Vorschlag im Fenster Material
import datetime  # noqa: E402

from rohrlaser import funktionen  # noqa: E402
from rohrlaser.meterpreis_dialog import ERP_VORSCHLAG, LIEFERANT, LIEFERZEIT, SPALTEN  # noqa: E402

heute = datetime.date.today()


def _d(vor, plus=None):
    t = heute - datetime.timedelta(days=vor) + datetime.timedelta(days=plus or 0)
    return t.strftime("%d.%m.%Y")


EK = ("Bestell-Nr.;ArtNr;Bezeichnung;Zusatztext;Bez4;Menge;Preis;L-Termin;Angebotsdatum;Datum Erf.;erfasst;PE;\r\n"
      f"1;EQRS235-40x40x3;Quadratrohr 40x40x3 kaltgefertigt;EN 10219- S235 HL 6m;;60;3,10;{_d(60, 14)};;{_d(60)};M;1;\r\n"
      f"2;EQRS235-40x40x3;Quadratrohr 40x40x3 kaltgefertigt;EN 10219- S235 HL 6m;;120;3,00;{_d(100, 10)};;{_d(100)};M;1;\r\n"
      f"3;EQRS235-40x40x3;Quadratrohr 40x40x3 kaltgefertigt;EN 10219- S235 HL 6m;;90;3,05;{_d(80, -3)};;{_d(80)};M;1;\r\n"
      f"4;EQRS235-40x40x3;Quadratrohr 40x40x3 kaltgefertigt;EN 10219- S235 HL 6m;;30;3,20;;;{_d(70)};M;1;\r\n")
de = E.lesen(EK.encode("cp1252"))
ze = E.spalten_vorschlag(de["kopf"])
assert de["kopf"][ze["liefertermin"]] == "L-Termin" and de["kopf"][ze["datum"]] == "Datum Erf.", ze
alt = {f: i for f, i in ze.items() if f != "liefertermin"}      # gemerkte Zuordnung von vor der Lieferzeit
assert E.zuordnung_fuer(de["kopf"], {E.vorlage_schluessel(de["kopf"]): alt})[0].get("liefertermin") == ze["liefertermin"]
ke, meld = E.kaeufe(de, ze)
assert len(ke) == 4 and not meld and (ke[0]["liefertermin"] - ke[0]["datum"]).days == 14 and ke[3]["liefertermin"] is None
lz = E.lieferzeit(ke, heute)
assert lz == dict(tage=12, min=10, max=14, anzahl=2, letzte=14), lz      # Termin vor dem Kauf und ohne Termin zählen nicht
assert E.lieferzeit_text(lz) == "Ø 12 Tage (10 bis 14, 2 Käufe)" and E.lieferzeit_text(lz, kurz=True) == "12 Tage"
assert E.lieferzeit(ke[2:], heute) is None and E.lieferzeit_text(None) == ""
ohne = [dict(x, liefertermin=None) for x in ke]
E.speichern(db, ohne, "alt.csv")                    # vor dem Update eingelesen: ohne Liefertermin
assert all(x["liefertermin"] is None for x in E.gespeicherte(db) if x["artikelnr"] == "EQRS235-40x40x3")
assert E.speichern(db, ke, "neu.csv") == 0          # neu einlesen: kein Kauf doppelt, Liefertermin nachgetragen
assert sum(1 for x in E.gespeicherte(db) if x["artikelnr"] == "EQRS235-40x40x3" and x["liefertermin"]) == 3
gr = mp.erp_gruppen(db)[("QR 40x40x3", "S235-10219")]
assert gr["lieferzeit"]["tage"] == 12 and gr["lieferzeit"]["anzahl"] == 2, gr["lieferzeit"]
zl = next(z for z in mp.alle_varianten(db) if (z["profil_id"], z["werkstoff_id"]) == ("QR 40x40x3", "S235-10219"))
assert zl["erp_lieferzeit"] == 12 and any(f == "erp_lieferzeit" for f, *_ in mp.EXPORT)
assert MB.lieferzeit_erp(db, "QR 40x40x3", "S235-10219").startswith("Ø 12 Tage")
assert MB.lieferzeit_erp(db, "RE 60x40x3", "S355-10219") == ""
ok("Lieferzeit je Material aus dem EK: L-Termin minus Erfassungsdatum, Ø/kürzeste/längste, Käufe ohne oder mit "
   "früherem Termin zählen nicht; Liefertermin wird beim erneuten Einlesen nachgetragen")

db.einstellung_setzen("funktion_erp_preise", "ja")
funktionen.db_setzen(db)
f.reiter.setCurrentWidget(an)
an.erp_vorschlagen()
an.neu_laden()
gesehen = {}


def fenster2(d):
    r = next(i for i, g in enumerate(d.gruppen) if g["profil"] == "QR 40x40x3")
    gesehen["kopf"] = [d.tabelle.horizontalHeaderItem(c).text() for c in (ERP_VORSCHLAG, LIEFERZEIT)]
    gesehen["lz"] = d.tabelle.item(r, LIEFERZEIT).text()
    gesehen["lz_tipp"] = d.tabelle.item(r, LIEFERZEIT).toolTip()
    gesehen["lieferant"] = d.tabelle.item(r, LIEFERANT).text()
    gesehen["lieferant_tipp"] = d.tabelle.item(r, LIEFERANT).toolTip()
    gesehen["lieferant_leer"] = d.tabelle.item(next(i for i, g in enumerate(d.gruppen) if g["profil"] == "RE 60x40x3"),
                                               LIEFERANT).text()
    gesehen["knopf"] = d.erp_knoepfe[r].text() if d.erp_knoepfe[r] else None
    gesehen["tipp"] = d.erp_knoepfe[r].toolTip() if d.erp_knoepfe[r] else ""
    gesehen["vorher"] = d.felder[r].text()
    if d.erp_knoepfe[r]:
        d.erp_knoepfe[r].click()
    gesehen["nachher"] = d.felder[r].text()
    d.annehmen()
    return True


n = an.material_einstellen(fenster2)
assert gesehen["kopf"] == ["ERP-Vorschlag [€/m]", "Lieferzeit Ø"] == list(SPALTEN[-3:-1]), gesehen
assert SPALTEN[LIEFERANT] == "Lieferant (Vorschlag)" and gesehen["lieferant"].startswith("Stahlhandel"), gesehen
assert gesehen["lieferant_tipp"] and gesehen["lieferant_leer"] == "–", gesehen
assert gesehen["lz"] == "12 Tage" and "10 bis 14" in gesehen["lz_tipp"], gesehen
assert gesehen["knopf"] and gesehen["knopf"].startswith("3,10") and "nur Vorschlag" in gesehen["tipp"], gesehen
assert gesehen["vorher"] == "" and gesehen["nachher"] == "3,10" and n == 1, (gesehen, n)
assert all(p["preis_m"] == 3.1 for p in an.positionen if p["profil_id"] == "QR 40x40x3")
ok("Fenster Material je Abmessung: Spalten ERP-Vorschlag (Datum, Grund; ein Klick trägt ihn als Meterpreis dieses "
   "Angebots ein), Lieferzeit Ø und Lieferant (Vorschlag) zum Bedarf")

# Ausbau 1.3 Zuordnen in der Vorschau, 2.5 Auswirkung auf offene Angebote
pfz = tmp / "zuordnen.csv"
pfz.write_text("Artikelnummer;Bezeichnung;EK-Preis\nX-900;Sonderrohr ohne Angaben;4,00\n"
               "X-901;Quadratrohr 40x40x3 EN 10219 S235;9,90\n", encoding="utf-8")
off = M.analysieren(db, M.lesen(pfz.read_bytes(), str(pfz)), {"materialnr": 0, "bezeichnung": 1, "preis": 2})
assert off[0]["gruppe"] == M.OFFEN and off[1]["gruppe"] == M.PREIS, [(e["gruppe"], e["hinweis"]) for e in off]
gesehen = {}


def vorschau(v):
    gesehen["knopf_vorher"] = v.zuordnen_knopf.isEnabled()
    v.reiter.setCurrentIndex(M.GRUPPEN.index(M.OFFEN))
    v.tabellen[M.OFFEN].selectRow(0)
    gesehen["knopf"] = v.zuordnen_knopf.isEnabled()
    gesehen["offen_vorher"] = v.tabellen[M.OFFEN].rowCount()
    assert v.zuordnen(profil_id="RE 60x40x3", werkstoff_id="S355-10219")
    gesehen["offen"] = v.tabellen[M.OFFEN].rowCount()
    gesehen["gruppe"] = next(e["gruppe"] for e in v.posten if e["materialnr"] == "X-900")
    gesehen["hinweis"] = " ".join(next(e["hinweis"] for e in v.posten if e["materialnr"] == "X-900"))
    gesehen["auswirkung"] = v.auswirkung()
    gesehen["text"] = v.auswirkung_text.text()
    gesehen["haken"] = v.gruppen()
    return True


# Position QR 40x40x3 hat seit dem ERP-Vorschlag einen eigenen Meterpreis: zählt nicht; RE 60x40x3 rechnet neu
vorher_re = next(z for z in db.zeilen("preise") if (z["profil_id"], z["werkstoff_id"]) == ("RE 60x40x3", "S355-10219"))
erg = MB.stamm_import(m, str(pfz), spalten={"materialnr": 0, "bezeichnung": 1, "preis": 2}, vorschau=vorschau)
assert gesehen["knopf"] and gesehen["offen_vorher"] == 1 and gesehen["offen"] == 0, gesehen
assert gesehen["gruppe"] in (M.PREIS, M.NEU) and "von Hand zugeordnet" in gesehen["hinweis"], gesehen
nummern_aw = [a["nummer"] for a in gesehen["auswirkung"]]
assert nummern_aw == [an.kopf["nummer"]] and "1 offenes Angebot" in gesehen["text"], gesehen
mats = {(x[0], x[1]) for x in gesehen["auswirkung"][0]["materialien"]}
assert mats == {("RE 60x40x3", "S355-10219")}, mats           # QR 40x40x3: eigener Meterpreis an der Position
assert erg["erg"] and erg["erg"]["gemerkt"] == 1
zu = [z for z in E.zuordnungen(db).values() if z["artikelnr"] == "X-900"]
assert zu and (zu[0]["profil_id"], zu[0]["werkstoff_id"]) == ("RE 60x40x3", "S355-10219")
nochmal = M.analysieren(db, M.lesen(pfz.read_bytes(), str(pfz)), {"materialnr": 0, "bezeichnung": 1, "preis": 2})
assert nochmal[0]["gruppe"] != M.OFFEN and "gemerkt" in " ".join(nochmal[0]["hinweis"]), nochmal[0]
an.kopf["preisbasis"] = {"x": 1}
db.con.execute("UPDATE angebote SET preisbasis = ? WHERE id = ?", ('{"x": 1}', an.id))
db.con.commit()
pfz.write_text("Artikelnummer;Bezeichnung;EK-Preis\nX-900;Sonderrohr ohne Angaben;4,50\n", encoding="utf-8")
fest = M.analysieren(db, M.lesen(pfz.read_bytes(), str(pfz)), {"materialnr": 0, "bezeichnung": 1, "preis": 2})
assert fest[0]["gruppe"] == M.PREIS and M.auswirkung(db, fest) == [], "festgeschriebene Angebote ändern sich nie"
db.con.execute("UPDATE angebote SET preisbasis = NULL WHERE id = ?", (an.id,))
db.con.commit()
ok("Vorschau: nicht zuordenbare Zeile von Hand zuordnen (Artikelnummer wird gemerkt), Auswirkung auf offene "
   "Angebote (festgeschriebene und Positionen mit eigenem Meterpreis nicht)")

print("Alle Tests Materialdatenbank bestanden")
