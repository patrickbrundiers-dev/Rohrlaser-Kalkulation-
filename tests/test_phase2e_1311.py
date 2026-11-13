"""Roadmap Kalkulation, Phase 2 Paket 2e (Freigabe Patrick 13.11.2026 „Ganze Phase 2 nach Empfehlung“).

OFFER-015  Angebot und Auftragsbestätigung auf Englisch.
PART-004   Normteilbibliothek mit DIN/ISO-Merkmalen (STEP-Import und Preisliste finden gleichwertige Normen).
PART-009   Sammel-Preisanfrage je Lieferant für Normteile ohne Preis.
ERP-003    Rollen AV/Vertrieb sperren die Bereiche der anderen Rolle.
Neue Einstellungen und Felder leer = aus.

Aufruf: python tests/test_phase2e_1311.py
"""
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402

import beispiel_angebot as B  # noqa: E402
from rohrlaser import admin_schutz, englisch, normteil, normteil_preise as np_, pdf, step, zukauf  # noqa: E402
from rohrlaser.angebot_oben import KOPF_FELD  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402

app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
fenster = Hauptfenster(db, tmp, stumm=True)
KOPF = {k: v for k, v in B.KOPF.items() if k not in ("nummer", "kundennr", "kunde")}
ROHR = dict(B.POSITIONEN[1])
K1 = db.zeilen("kunden")[0]["kundennr"]


def ok(text):
    print("OK  ", text)


def angebot(*positionen, kopf=None):
    i = db.angebot_neu(dict(KOPF, kundennr=K1, **(kopf or {})))
    for p in positionen:
        db.position_neu(i, p)
    s = fenster.angebot_oeffnen(i)
    s.optimieren()
    return s


def pdf_text(pfad):
    from pypdf import PdfReader
    return "\n".join(seite.extract_text() for seite in PdfReader(str(pfad)).pages)


# ------------------------------------------------------------------ OFFER-015 Englisch
assert "englisch" in KOPF_FELD
for n in ("bedingungen_en", "ab_text_en", "englisch_woerter"):
    assert not db.einstellung(n), n
assert englisch.zahlen("1.234,56 € und 42,4 mm am 15.11.2026") == "1,234.56 € und 42.4 mm am 15.11.2026"
assert englisch.text("Rundrohr Ø 42,4 x 2\nL = 860 mm\ninkl. Material S235\nfeuerverzinkt\ninkl. Gewinde 4xM6") == \
    "Round tube Ø 42.4 x 2\nL = 860 mm\nincl. material S235\nhot-dip galvanised\nincl. thread 4xM6"
assert englisch.text("Lieferzeit: ca. 10 Arbeitstage nach Auftragseingang.") == \
    "Delivery time: approx. 10 working days after receipt of order."
assert englisch.text("Zahlung innerhalb 10 Tagen mit 2 % Skonto oder innerhalb 30 Tagen netto.") == \
    "Payment within 10 days less 2 % cash discount or within 30 days net."
assert englisch.text("Bügel vom Kunden", englisch.woerter("Bügel = bracket; Kunden = customer")) == \
    "bracket vom customer"

s = angebot(dict(ROHR, stueck=20), kopf=dict(lieferzeit_art="Arbeitstage", lieferzeit_wert="10", zahlungsziel=30))
p_de = s.angebot_pdf(oeffnen=False)
t_de = pdf_text(p_de)
assert "Summe netto" in t_de and "Quotation" not in t_de
assert englisch.check_punkt(s.kopf, s.einst) is None
s.kopf_bereich.englisch_an.setChecked(True)
assert db.angebot(s.id)["englisch"] == "ja"
assert any("Angebot auf Englisch: die Bedingungen" in p.text for p in s._angebot_mehr_punkte(*s._rechnung()))
db.einstellung_setzen("bedingungen_en", "Prices in euros plus VAT.")
s.neu_laden()
assert not any("Angebot auf Englisch" in p.text for p in s._angebot_mehr_punkte(*s._rechnung()))
p_en = s.angebot_pdf(oeffnen=False)
t_en = pdf_text(p_en)
for w in ("Page 1 of 1", "Quotation", "Subtotal (net)", "plus VAT", "Total amount", "Terms", "Unit price", "Round tube",
          "Delivery time: approx. 10 working days", "or within 30 days net.", "Prices in euros plus VAT."):
    assert w in t_en, (w, t_en)
for w in ("Summe netto", "Gesamtbetrag", "Lieferzeit", "Konditionen"):
    assert w not in t_en, (w, t_en)
assert not pdf._EN
ok("OFFER-015: PDF englisch (Bezeichnungen, Sätze, Positionstext, Zahlen), deutsch ohne Haken")

db.neu("kundenvorgaben", dict(kundennr=K1, englisch="ja"))
s2 = angebot(dict(ROHR, stueck=5))
assert s2.kopf.get("englisch") == "ja" and s2.kopf_bereich.englisch_an.isChecked()
ok("OFFER-015: Kundenvorgabe „Angebote auf Englisch“ setzt den Haken bei neuen Angeboten")

# AB auf Englisch mit eigenem Text
db.einstellung_setzen("ab_text_en", "Thank you for your order.")
s.neu_laden()
import datetime  # noqa: E402
fenster.angebote.vorgang_setzen("Beauftragt", angebot_id=s.id,
                                auftrag=("PO-77", (datetime.date.today() + datetime.timedelta(days=20)).isoformat()))
ab_pfad = s.auftragsbestaetigung_pdf(abweichung_ok=True)
t_ab = pdf_text(ab_pfad)
assert "Order confirmation" in t_ab and "Thank you for your order." in t_ab and "Delivery date" in t_ab, t_ab
ok("OFFER-015: Auftragsbestätigung englisch mit eigenem Text")

# ------------------------------------------------------------------ PART-004 Normteilbibliothek
m = normteil.merkmale("Sechskantschraube DIN 933 M8 x 20 8.8 verzinkt")
assert m == dict(norm="DIN 933", groesse="M8", laenge=20.0, festigkeit="8.8", norm_oberflaeche="verzinkt"), m
assert normteil.gleich(m, normteil.merkmale("ISO 4017 M8x20"))
assert not normteil.gleich(m, normteil.merkmale("ISO 4017 M8x20 10.9"))
assert not normteil.gleich(m, normteil.merkmale("ISO 4017 M8x25"))
assert normteil.merkmale("Mutter ISO 4032 M12")["laenge"] is None
for f in ("norm", "groesse", "festigkeit", "norm_oberflaeche"):
    assert f in {x.name for x in zukauf.ARTIKEL.felder}, f
aid = db.zukauf_speichern(None, dict(bezeichnung="Sechskantschraube DIN 933 M8 x 20 8.8", kategorie="Normteile",
                                     artikeltyp="Normteil", einheit="Stück", aufschlag_quelle=zukauf.KATEGORIE),
                          [dict(lieferant="Würfel Schrauben", preiseinheit=1, preise=[dict(ab=1, preis=0.12)])])
liste = db.zukauf_artikel_liste()
verweis, name, txt = step._normteil_position(dict(bauteil="ISO 4017 M8x20"), liste, {})
assert verweis == dict(artikel_id=aid) and "gleiche Norm und Größe" in txt, (verweis, txt)
neu = {}
verweis, name, txt = step._normteil_position(dict(bauteil="ISO 4032 M12"), liste, neu)
w = neu[verweis["neu"]][0]
assert w["norm"] == "ISO 4032" and w["groesse"] == "M12", w
# Preisliste: DIN-Schreibweise des Lieferanten passt zum ISO-Artikel ohne Preis
aid2 = db.zukauf_speichern(None, dict(bezeichnung="Mutter", norm="ISO 4032", groesse="M10", kategorie="Normteile",
                                      artikeltyp="Normteil", einheit="Stück", aufschlag_quelle=zukauf.KATEGORIE), [])
treffer, rest = np_.zuordnen(np_.ohne_preis(db), [dict(bezeichnung="Sechskantmutter DIN 934 M10", artikelnr="",
                                                       preis=0.03)])
assert aid2 in treffer and treffer[aid2][1] == "Norm und Größe", (treffer, rest)
ok("PART-004: Merkmale aus der Bezeichnung, DIN 933 = ISO 4017, STEP-Import und Preisliste finden das Normteil")

# ------------------------------------------------------------------ PART-009 Sammel-Preisanfrage
db.con.execute("UPDATE zukauf_lieferanten SET email=? WHERE name=?", ("einkauf@example.com", "Würfel Schrauben"))
db.zukauf_speichern(None, dict(bezeichnung="Scheibe ISO 7089 M10", kategorie="Normteile", artikeltyp="Normteil",
                               einheit="Stück", aufschlag_quelle=zukauf.KATEGORIE),
                    [dict(lieferant="Würfel Schrauben", bevorzugt="ja", preiseinheit=1, preise=[])])
seite = np_.NormteilPreisSeite(db, lambda *a: None)
anfragen = np_.preisanfragen(seite.artikel, {"Würfel Schrauben": "einkauf@example.com"}, None, {})
namen = [x["lieferant"] for x in anfragen]
assert "Würfel Schrauben" in namen and np_.OHNE_LIEFERANT in namen, namen
w_ = next(x for x in anfragen if x["lieferant"] == "Würfel Schrauben")
assert w_["an"] == "einkauf@example.com" and "Scheibe ISO 7089 M10" in w_["text"], w_
ordner = tmp / "anfragen"
ordner.mkdir()
x = seite.preise_anfragen(ordner=ordner)
assert len(list(ordner.glob("*.eml"))) == len(x) >= 2
ok(f"PART-009: {len(x)} Preisanfragen je Lieferant (E-Mail-Dateien), ohne E-Mail-Adresse gemeldet")

# ------------------------------------------------------------------ ERP-003 Rollen
db.einstellung_setzen("passwort", "geheim")
db.einstellung_setzen("benutzer_kuerzel", "VK")
sz = admin_schutz.Sitzung()
assert admin_schutz.rolle_gesperrt(db, sz) == set(), "ohne Rolle wie bisher"
admin_schutz.rolle_setzen(db, "VK", admin_schutz.VERTRIEB)
gesp = admin_schutz.rolle_gesperrt(db, sz)
assert "maschinen" in gesp and "e_fertigung" in gesp and "e_neue_angebote" not in gesp, gesp
admin_schutz.rolle_setzen(db, "VK", admin_schutz.AV)
assert "e_neue_angebote" in admin_schutz.rolle_gesperrt(db, sz) and "maschinen" not in admin_schutz.rolle_gesperrt(db, sz)
sz.freischalten()
assert admin_schutz.rolle_gesperrt(db, sz) == set(), "Admin: Rolle sperrt nichts"
assert admin_schutz.ROLLEN in admin_schutz.einstellungen_geschuetzt(db), "Rollen kommen mit den Admin-Vorgaben"
f3 = Hauptfenster(db, tmp, stumm=True)
assert f3.bereich.bereich_gesperrt("e_neue_angebote") and f3.bereich.bereich_gesperrt("e_pdf_texte")
s3 = {x.schluessel: x for x in f3.einstellungen.seiten}
assert not s3["e_pdf_texte"].felder["bedingungen_en"].isEnabled(), "AV: Verkaufstexte grau"
assert s3["e_step"].felder["step_kopieren"].isEnabled()
assert "Rolle" in f3.plaetze_seite.SPALTEN
admin_schutz.rolle_setzen(db, "VK", "")
f3.bereich.schutz_anwenden()
assert s3["e_pdf_texte"].felder["bedingungen_en"].isEnabled()
f3.close()
ok("ERP-003: Rolle Vertrieb sperrt Fertigungsdaten, AV die Verkaufsvorgaben; Admin und ohne Rolle wie bisher")

fenster.close()
db.schliessen()
print("Alle Prüfungen Paket 2e bestanden.")
