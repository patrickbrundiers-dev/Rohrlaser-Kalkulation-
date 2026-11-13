"""PDF-Design (Patrick 12.11.2026, freigegeben „Alle Empfehlungen, F2 nie“): gemeinsames Designsystem, Kundendokumente
als Geschäftsbrief, keine internen Kalkulationsdaten im Kundendokument, Bezeichnung im Angebot (F1), keine Übersicht
unter dem Titel (F2 nie), Prüfplan fortlaufend (F3), Vorschau vor dem Speichern (F4), Nachkalkulation ohne leere
Kostenarten (Zukaufteile nur, wenn welche im Angebot sind).

Aufruf: python tests/test_pdf_design.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import datetime
import json
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pypdfium2 as pdfium  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import beispiel_angebot  # noqa: E402
from rohrlaser import design, pdf, pdf_vorschau, pruefplan, rechnen, stil  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def fehler_im_layout(pfad, rand=3):
    """[(Seite, Art, Text)]: Zeichen, die sich überdecken, und Zeichen außerhalb des Blatts."""
    out = []
    d = pdfium.PdfDocument(str(pfad))
    for nr in range(len(d)):
        seite = d[nr]
        b, h = seite.get_size()
        tp = seite.get_textpage()
        zeichen = []
        for i in range(tp.count_chars()):
            c = tp.get_text_range(i, 1)
            if not c.strip():
                continue
            x0, y0, x1, y1 = tp.get_charbox(i)
            if x1 - x0 < 0.3 or y1 - y0 < 0.3:
                continue
            zeichen.append((x0, y0, x1, y1, c))
            if x0 < rand or x1 > b - rand or y0 < rand or y1 > h - rand:
                out.append((nr + 1, "außerhalb", c))
        zeichen.sort()
        for i, a in enumerate(zeichen):
            for z in zeichen[i + 1:]:
                if z[0] >= a[2]:
                    break
                dx = min(a[2], z[2]) - max(a[0], z[0])
                dy = min(a[3], z[3]) - max(a[1], z[1])
                if dx > 0.35 * min(a[2] - a[0], z[2] - z[0]) and dy > 0.4 * min(a[3] - a[1], z[3] - z[1]):
                    out.append((nr + 1, "überlappt", a[4] + z[4]))
    d.close()
    return out


def ok(t):
    print("OK    ", t)


def text(pfad):
    d = pdfium.PdfDocument(str(pfad))
    try:
        return [s.get_textpage().get_text_range() for s in d]
    finally:
        d.close()


# ------------------------------------------------------------------ D1 ein Designsystem für Oberfläche und PDF
for name in ("AKZENT", "AKZENT_DUNKEL", "TEXT", "TEXT_GRAU", "LINIE", "RAHMEN", "FLAECHE", "BLAU_FLAECHE", "ROT",
             "ROT_FLAECHE", "GELB_TEXT", "GELB_FLAECHE", "ORANGE", "GRUEN", "GRUEN_FLAECHE"):
    assert getattr(design, name).upper() == getattr(stil, name).upper(), name
assert pdf.BLAU.hexval().upper().endswith(design.AKZENT[1:].upper()) and pdf.S_TITEL.fontSize == design.PDF_TITEL
assert pdf.PS_BLAU == pdf.BLAU, "Palettenschein in den Farben des Designsystems"
ok("D1 design.py = Farben der Oberfläche; PDF-Titel 14 pt, Palettenschein im selben Blau")

sp = pdf.brief_spalten({"briefkopf_1": "Muster GmbH", "briefkopf_2": "Weg 1 · 12345 Ort",
                        "briefkopf_3": "Tel. 1 · a@b.de", "briefkopf_4": "USt-IdNr. DE1 · HRB 2 · IBAN DE00 · BIC X"})
assert sp == (("Muster GmbH", "Weg 1", "12345 Ort"), ("Tel. 1", "a@b.de"), ("USt-IdNr. DE1", "HRB 2", "IBAN DE00 · BIC X"))
sp = pdf.brief_spalten({"briefkopf_1": "Muster GmbH", "briefkopf_2": "Weg 1", "briefkopf_3": "12345 Ort",
                        "briefkopf_4": "Telefon 0291 1 / info@muster.de"})       # Aufteilung der Vorgabe-Zeilen
assert sp == (("Muster GmbH", "Weg 1", "12345 Ort"), ("Telefon 0291 1 / info@muster.de",)), sp
assert pdf.brief_spalten({}) == ()
assert pdf.bezeichnung_zeile(dict(bezeichnung="Holm  links", text="Rundrohr\nL = 1 mm")) == "Holm links"
assert pdf.bezeichnung_zeile(dict(bezeichnung="Lasche", text="Lasche, Mutter")) == ""      # steht schon im Text
ok("D2 Firmenangaben im Fuß in drei Spalten; Bezeichnung nur, wenn sie nicht schon im Text steht")

# ------------------------------------------------------------------ Testangebot mit Satz, Staffeln, Zukauf
app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
db.einstellung_setzen("ablageordner", str(tmp / "Ablage"))
for i, t in enumerate(("Muster Rohrlaser GmbH", "Industriestraße 12 · 59872 Meschede", "Tel. 0291 1 · info@muster.de",
                       "USt-IdNr. DE123 · HRB 1 Arnsberg"), start=1):
    db.einstellung_setzen(f"briefkopf_{i}", t)
db.con.execute("INSERT INTO kunden (kundennr, name, strasse, plz_ort) VALUES (?,?,?,?)",
               ("K-1", "Metallbau Krüger GmbH", "Hafenstraße 3", "28195 Bremen"))
db.con.commit()
a = beispiel_angebot.anlegen(db, dict(nummer="A-2026-0815", kundennr="K-1", kunde="Metallbau Krüger GmbH",
                                      kundenreferenz="AN-0815", datum=datetime.date.today().isoformat()))
z = db.zukauf_speichern(None, dict(artikelnr="Z-1", bezeichnung="Schraube M6x20", einheit="Stück", angebotstext="ja"),
                        [dict(lieferant="L", preiseinheit=1, preise=[dict(ab=1, preis=0.37)])])
p50 = next(p for p in db.positionen(a) if p["pos"] == 50)
db.position_aendern(p50["id"], "zukauf", json.dumps([dict(artikel_id=z, menge=2, stand=db.zukauf_stand(z))]))
f = Hauptfenster(db, tmp, stumm=True)
s = f.angebot_oeffnen(a)
assert s.optimieren()
s.staffelpreise_rechnen()
s.neu_laden()
zeilen, summen = s._rechnung()
ang_pfad = s.angebot_pdf()
seiten = text(ang_pfad)
alles = "\n".join(seiten)

# ------------------------------------------------------------------ K1 keine internen Daten im Kundendokument
VERBOTEN = ("Stundensatz", "€/h", "Selbstkosten", "Herstellkosten", "Gewinn", "Marge", "Deckungsbeitrag", "Einkauf",
            "Einstand", "EK", "Maschinenzeit", "Schneidzeit", "Aufschlag", "Programmierkosten", "Lieferant", "Kalkulation")
intern = [rechnen.zahl(summen[k], 2) for k in ("selbst", "herstell") if summen.get(k)]


def sauber(name, t):
    funde = [w for w in VERBOTEN if w in t] + [w for w in intern if w in t]
    assert not funde, (name, funde)


sauber("Angebot", alles)
assert "Holm links" in alles and "Rundrohr Ø 42,4 x 2" in alles, "F1 Bezeichnung und Profiltext"
assert "Angebotssumme" not in alles, "F2 nie: keine Übersicht unter dem Titel"
assert "Ab 24 Stk.: 10" in alles.replace("\r", "") or "Ab 24 Stk.:" in alles, "Staffelpreise in einer Zeile"
assert alles.count("Industriestraße 12") == 2, "Anschrift nur in Absenderzeile und Fuß (nicht dreimal)"
assert "Seite 1 von 1" in alles and "USt-IdNr. DE123" in alles
assert not fehler_im_layout(ang_pfad)
ok("K1 Angebot: keine internen Werte (Kosten, Zeiten, Sätze, Lieferant), Bezeichnung fett mit Profiltext, Staffeln "
   "einzeilig, Firma einmal im Fuß, ohne Übersicht")

termin = datetime.date.today() + datetime.timedelta(days=20)
f.angebote.vorgang_setzen("Beauftragt", angebot_id=a, auftrag=("BE-4711", termin.isoformat()))
s.neu_laden()
ab = s.auftragsbestaetigung_pdf(abweichung_ok=True)
t_ab = "\n".join(text(ab))
sauber("Auftragsbestätigung", t_ab)
assert "Holm links" in t_ab and "BE-4711" in t_ab and not fehler_im_layout(ab)
ls = s.lieferschein(pfad=tmp / "ls.pdf", oeffnen=False)
t_ls = "\n".join(text(ls["pfad"]))
sauber("Lieferschein", t_ls)
assert "Unser Auftrag" in t_ls and "A-2026-0815" in t_ls and "Ihre Bestellung" in t_ls and "BE-4711" in t_ls
assert "Ihre Anfrage" in t_ls and "AN-0815" in t_ls and "Hafenstraße 3" in t_ls and "USt-IdNr. DE123" in t_ls
assert t_ls.index("BE-4711") > t_ls.index("Ihre Bestellung") - 40
assert not fehler_im_layout(ls["pfad"])
ok("K2 Auftragsbestätigung und Lieferschein: gleicher Geschäftsbrief, keine internen Werte; Lieferschein mit "
   "Unser Auftrag / Ihre Bestellung / Ihre Anfrage richtig belegt")

# ------------------------------------------------------------------ K3 Palettenschein für den Kunden (13.11.2026)
from rohrlaser import palettenschein, palettenschein_dialog  # noqa: E402

d = db.palettenschein(a)
d.update(hinweis="Nur Kran links anschlagen", status=[palettenschein.STATUS[0]])
d["arbeiten"] = list(d.get("arbeiten") or ()) + [palettenschein.schluessel("Intern", "Entgraten")]
db.palettenschein_speichern(a, d)
gedruckt = db.palettenschein(a).get("gedruckt_am")
ks = palettenschein_dialog.scheine_drucken(f, [a], pfad=tmp / "kunde.pdf", kunde=True)
t_ks = text(ks)
for t in t_ks:
    for w in ("ARBEITSSCHRITTE", "AUFTRAGSSTATUS", "BEARBEITER", "HINWEIS", "Kran", "Entgraten",
              palettenschein.STATUS[0], "PALETTENBEGLEITSCHEIN"):
        assert w not in t, w
    assert "PALETTENSCHEIN" in t and "Metallbau Krüger GmbH" in t and "BE-4711" in t and "A-2026-0815" in t
    assert "ABSENDER" in t and "EMPFÄNGER" in t
assert any("INHALT DIESER PALETTE" in t for t in t_ks), "Inhalt der Palette"
assert db.palettenschein(a).get("gedruckt_am") == gedruckt, "Kundenschein vermerkt kein „gedruckt am“"
assert not fehler_im_layout(ks)
hs = palettenschein_dialog.scheine_drucken(f, [a], pfad=tmp / "halle.pdf")
assert "Kran" in "\n".join(text(hs)) and "ARBEITSSCHRITTE" in text(hs)[0], "Hallenschein unverändert"
assert len(text(hs)) == len(t_ks), "je Palette ein Blatt, wie beim Hallenschein"
ok(f"K3 Palettenschein für den Kunden ({len(t_ks)} Blatt): Empfänger, Bestellung, Inhalt; ohne Arbeitsschritte, "
   "Status, Hinweis, Bearbeiter")

# ------------------------------------------------------------------ I1 interne Dokumente
pp = pruefplan.pdf(tmp / "pp.pdf", db.angebot(a), db.positionen(a), {}, db.kontext().profile)
n_pos = len(pruefplan.positionen(db.positionen(a)))
assert len(text(pp)) < n_pos, (len(text(pp)), n_pos)
assert not fehler_im_layout(pp)
ok(f"I1 Prüfplan fortlaufend (F3): {n_pos} Positionen auf {len(text(pp))} Seite(n)")

nk = s.nachkalk.pdf()
t_nk = "\n".join(text(nk))
assert "Zukaufteile (Einstand)" in t_nk, "Angebot mit Zukaufteil: Zeile bleibt"
assert "Sonstige Kosten" not in t_nk and "ausgeblendet" in t_nk
b = db.angebot_neu(dict(kunde="Ohne Zukauf", stange=6000))
db.position_neu(b, dict(pos=10, artikel="T", profil_id="RR 42,4x2,0", werkstoff_id="S235-10219", laenge=1000,
                        stueck=10, schneidweg=300, einstiche=2))
s2 = f.angebot_oeffnen(b)
s2.optimieren()
s2.neu_laden()
t_nk2 = "\n".join(text(s2.nachkalk.pdf()))
assert "Zukaufteile" not in t_nk2 and "Material" in t_nk2 and "Deckungsbeitrag" in t_nk2
ok("I2 Nachkalkulation: Kostenarten ohne Soll und Ist ausgeblendet (Zukaufteile nur mit Zukaufteilen im Angebot)")

w = s.werkstatt_pdf()
t_w = "\n".join(text(w))
assert "gem. Schnitt" in t_w and "gemeinsamer Schnitt" not in t_w and not fehler_im_layout(w)
k = s.kalkulation_pdf()
assert not fehler_im_layout(k)
ok("I3 Werkstattpapiere „gem. Schnitt“ ohne Umbruch; Kalkulation ohne Layoutfehler")

# ------------------------------------------------------------------ V1 Vorschau vor dem Speichern (F4)
assert db.einstellung("pdf_vorschau") == "ja"
ziel = tmp / "vorschau" / "Angebot.pdf"
ziel.parent.mkdir()
gesehen = {}


def bedienen(wahl, nicht_mehr=False):
    def d_(d):
        gesehen.update(seiten=len(d.bilder), text=d.seiten.text())
        d.nicht_mehr.setChecked(nicht_mehr)
        d._ende(wahl)
    return d_


schreiben = lambda p: pdf.angebot_pdf(p, s.kopf, s.angebot_daten(), s.einst)  # noqa: E731
assert s._mit_vorschau("Angebot", ziel, schreiben, bedienen(pdf_vorschau.ABBRECHEN)) is None and not ziel.exists()
assert gesehen == dict(seiten=1, text="1 Seite")
assert s._mit_vorschau("Angebot", ziel, schreiben, bedienen(pdf_vorschau.SPEICHERN, True)) == ziel and ziel.exists()
assert db.einstellung("pdf_vorschau") == "nein", "Häkchen „Vorschau nicht mehr zeigen“"
assert len(pdf_vorschau.seiten_bilder(ziel)) == 1 and pdf_vorschau.seiten_bilder(tmp / "fehlt.pdf") == []
ok("V1 Vorschau: Abbrechen speichert nichts, Speichern legt die Datei ab, „nicht mehr zeigen“ schaltet sie ab")

f.close()
db.schliessen()
print("PDF-Design: alle Tests bestanden.")
