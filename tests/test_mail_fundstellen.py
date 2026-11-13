"""Anfrage-Mail auslesen mit Fundstelle und Sicherheit (KI-001, Patrick 12.11.2026 „Alle Empfehlungen“; 19:46:
„Kannst du nicht 20 mails erstellen? Ich möchte ungerne Kundendaten hier Preis geben“).

- 20 erfundene Test-Mails (tests/daten/ki001_testmails.json) mit Trefferquote; kein Wert ohne Fundstelle
- jeder Wert mit Sicherheit (sicher / prüfen / unsicher); mehrdeutiger Werkstoff = unsicher, das Programm entscheidet nicht
- im Anfrage-Leser (anfragen.werte): Fundstellen in weitere["fundstellen"] und als Zeile im Prüfdialog

Aufruf: python tests/test_mail_fundstellen.py
"""
import datetime
import json
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
from rohrlaser import anfragen, mail, mail_fundstellen as mf  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402

HEUTE = datetime.date(2026, 11, 12)
MINDEST_QUOTE = 0.85


def ok(t):
    print("OK    ", t)


def main():
    db = Datenbank(Path(tempfile.mkdtemp()) / "r.db")
    ws = db.zeilen("werkstoffe")
    kat = [z["name"] for z in db.zeilen("zusatzarbeiten") if z.get("name")]
    kunden = db.zeilen("kunden")
    daten = json.loads((HIER / "daten" / "ki001_testmails.json").read_text(encoding="utf-8"))["mails"]
    assert len(daten) == 20
    assert all(m["absender"].endswith(".example") for m in daten), "nur erfundene Absender"
    summe = dict(erwartet=0, richtig=0, falsch=0, fehlt=0, zu_viel=0)
    fehler = []
    for i, d in enumerate(daten, 1):
        m = mail.Mail(absender=d["absender"], betreff=d["betreff"], text=d["text"])
        werte = mf.zusammen([("Mail", m.volltext())], werkstoffe=ws, katalog=kat, kunden=kunden, heute=HEUTE)
        assert all(x["fundstelle"] and x["fundstelle"] in " ".join(m.volltext().split()) or
                   x["fundstelle"].strip("…") in " ".join(m.volltext().split()) for x in werte), werte
        assert all(x["sicherheit"] in (mf.SICHER, mf.PRUEFEN, mf.UNSICHER) for x in werte)
        for x in werte:
            if x["feld"] == "werkstoff" and "mehrdeutig" in str(x["wert"]):
                assert x["sicherheit"] == mf.UNSICHER
        v = mf.vergleich(werte, d["erwartet"])
        for n in summe:
            summe[n] += v[n]
        if v["falsch"] or v["fehlt"] or v["zu_viel"]:
            fehler.append((i, d["betreff"], v, [(x["feld"], x["wert"]) for x in werte]))
    quote = summe["richtig"] / summe["erwartet"]
    for f in fehler:
        print("      abweichend:", f)
    print(f"      Trefferquote {summe['richtig']} von {summe['erwartet']} = {100 * quote:.1f} %, falsch "
          f"{summe['falsch']}, nicht gefunden {summe['fehlt']}, zusätzlich gelesen {summe['zu_viel']}")
    assert quote >= MINDEST_QUOTE, quote
    ok(f"20 erfundene Mails: Trefferquote {100 * quote:.1f} % (Mindest {100 * MINDEST_QUOTE:.0f} %), jeder Wert mit "
       "Fundstelle und Sicherheit")
    m = mail.Mail(absender="einkauf@beispiel-metallbau.example", betreff="Anfrage",
                  text="Anfrage-Nr.: AN-1\nWerkstoff 1.4301, entgratet.\nWir benötigen die Teile bis KW 50/2026.")
    _, nr, weitere = anfragen.werte(db, [], [m])
    fs = weitere.get("fundstellen") or []
    assert nr == "AN-1" and {x["feld"] for x in fs} >= {"anfrage_nr", "werkstoff", "zusatz"}, fs
    assert any(h.startswith("Gelesen mit Fundstelle:") and "„Werkstoff 1.4301, entgratet.“" in h
               for h in weitere.get("hinweis") or ()), weitere.get("hinweis")
    ok("Anfrage-Leser: Fundstellen und Zeile „Gelesen mit Fundstelle“ im Prüfdialog")
    # lokale Prüfung (werkzeuge/trefferquote_anfragen.py) mit den erfundenen Mails als .eml
    import contextlib
    import io
    from email.message import EmailMessage
    sys.path.insert(0, str(HIER.parent / "werkzeuge"))
    import trefferquote_anfragen as tq
    o = Path(tempfile.mkdtemp())
    for i, d in enumerate(daten):
        e = EmailMessage()
        e["From"], e["Subject"] = d["absender"], d["betreff"]
        e.set_content(d["text"])
        (o / f"m{i:02d}.eml").write_bytes(bytes(e))
    csv_ = o / "pruefung.csv"
    with contextlib.redirect_stdout(io.StringIO()):
        tq.lesen(o, csv_)
    zeilen = csv_.read_text(encoding="utf-8-sig").splitlines()
    assert zeilen[0].split(";") == list(tq.SPALTEN) and len(zeilen) > 20
    csv_.write_text("\n".join([zeilen[0]] + [z + "j" for z in zeilen[1:2]] + [z + "n" for z in zeilen[2:3]]),
                    encoding="utf-8-sig")
    aus = io.StringIO()
    with contextlib.redirect_stdout(aus):
        tq.auswerten(csv_)
    assert "1 von 2 = 50.0 %" in aus.getvalue(), aus.getvalue()
    ok("lokale Prüfung: lesen schreibt die CSV zum Ankreuzen, auswerten zeigt nur Zahlen")
    print("alle Prüfungen bestanden")


if __name__ == "__main__":
    main()
