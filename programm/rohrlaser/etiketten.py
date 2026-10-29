"""Etiketten mit QR-Code und Rückmeldung per Scan (Plan 29.10.2026 Schritt 2a).

Je Position eines beauftragten Angebots ein oder mehrere Etiketten (PDF) mit QR-Code, Kunde, Auftrag, Position,
Artikel, Profil, Werkstoff, Länge und Stückzahl. Der QR-Code enthält nur Großbuchstaben und Ziffern, damit jeder
Handscanner (meldet sich als Tastatur, auch mit deutscher Belegung) ihn richtig eintippt:
    RL + Angebotsnummer ohne Sonderzeichen + P + Positionsnummer, z. B. RL202600042P20 (2026-00042, Pos. 20).
Neue Fassungen behalten ihren Zusatz (2026-00042-2 -> RL2026000422P20); gesucht wird über dieselbe Kurzform.

Rückmeldung: Im Reiter Fertigung „Scannen …“ den Arbeitsschritt wählen (Einstellung 'rueckmeldung_schritte',
Vorgabe Geschnitten, Entgratet, Verpackt) und Etiketten scannen. Jeder Scan steht in der Tabelle rueckmeldungen
(Angebot, Position, Schritt, Menge, Zeitpunkt, Kürzel); ohne Menge zählt die ganze Stückzahl der Position. Der erste
Scan eines freigegebenen Auftrags setzt den Fertigungsstatus auf „In Fertigung“, wenn er davor steht. Sind alle
Positionen im letzten Schritt vollständig, meldet der Scan das (Fertigmeldung bleibt ein eigener Schritt)."""
import datetime
import re

from reportlab.lib.units import mm

from . import fertigung
from .angebot import aktiv as position_aktiv

TABELLEN = ("rueckmeldungen",)
TABELLEN_SQL = (
    "CREATE TABLE IF NOT EXISTS rueckmeldungen (id INTEGER PRIMARY KEY, angebot_id INTEGER NOT NULL, position_id "
    "INTEGER, pos TEXT, schritt TEXT NOT NULL, menge REAL, am TEXT, wer TEXT, code TEXT)",
    "CREATE INDEX IF NOT EXISTS rueckmeldungen_angebot ON rueckmeldungen (angebot_id, id)",
)
SCHRITTE = ("Geschnitten", "Entgratet", "Verpackt")
IN_FERTIGUNG = "In Fertigung"

# Formate: Name -> (Seite (Breite, Höhe) oder None = Seite so groß wie das Etikett, Spalten, Zeilen, Etikett
# (Breite, Höhe), Rand links, Rand oben) in mm
FORMATE = {
    "A4, 3 × 8 Etiketten (70 × 37 mm)": ((210, 297), 3, 8, (70, 37), 0, 0.5),
    "A4, 2 × 7 Etiketten (105 × 42,3 mm)": ((210, 297), 2, 7, (105, 42.3), 0, 0.4),
    "Etikettendrucker 100 × 50 mm": (None, 1, 1, (100, 50), 0, 0),
    "Etikettendrucker 62 × 29 mm": (None, 1, 1, (62, 29), 0, 0),
}
FORMAT_VORGABE = "A4, 3 × 8 Etiketten (70 × 37 mm)"


class ScanFehler(ValueError):
    """Code nicht lesbar oder kein passender Auftrag (Text für den Benutzer)."""


def einrichten(con):
    for sql in TABELLEN_SQL:
        con.execute(sql)


def angebot_geloescht(db, angebot_id):
    db.con.execute("DELETE FROM rueckmeldungen WHERE angebot_id=?", (angebot_id,))


def kurz(nummer):
    """Angebotsnummer ohne Sonderzeichen in Großbuchstaben: '2026-00042' -> '202600042'."""
    return re.sub(r"[^0-9A-Za-z]", "", str(nummer or "")).upper()


def _pos_text(pos):
    try:
        f = float(pos)
        return str(int(f)) if f.is_integer() else str(pos)
    except (TypeError, ValueError):
        return str(pos or "")


def code(nummer, pos):
    """Inhalt des QR-Codes: 'RL202600042P20'."""
    return f"RL{kurz(nummer)}P{kurz(_pos_text(pos))}"


def lesen(text):
    """Scan -> (Kurzform der Angebotsnummer, Positionsnummer als Text). Verträgt Leerzeichen, Kleinbuchstaben und
    Zeichen, die ein Scanner mit falscher Tastaturbelegung einstreut. ScanFehler, wenn es kein Etikett ist."""
    t = re.sub(r"[^0-9A-Za-z]", "", str(text or "")).upper()      # erst filtern: 'ß'.upper() wäre 'SS'
    if not t.startswith("RL") or "P" not in t[2:]:
        raise ScanFehler(f"„{str(text or '').strip()}“ ist kein Etikett dieses Programms (erwartet RL…P…).")
    nr, _, pos = t[2:].rpartition("P")
    if not nr or not pos:
        raise ScanFehler(f"„{str(text or '').strip()}“: Angebot oder Position fehlt im Code.")
    return nr, pos


def schritte(db):
    out = []
    for z in str(db.einstellung("rueckmeldung_schritte") or "").splitlines():
        z = z.strip()
        if z and z not in out:
            out.append(z)
    return out or list(SCHRITTE)


def _jetzt():
    return datetime.datetime.now().isoformat(timespec="seconds")


def finden(db, text):
    """Scan -> (Angebot, Position). Gesucht werden eigene beauftragte Angebote (neueste zuerst)."""
    nr, pos = lesen(text)
    treffer = [a for a in db.angebote() if kurz(a.get("nummer")) == nr]
    if not treffer:
        raise ScanFehler(f"Kein Angebot mit der Nummer aus „{text.strip()}“.")
    eigene = [a for a in treffer if not a.get("fremd")] or treffer
    a = next((x for x in eigene if x.get("vorgang") == "Beauftragt"), eigene[0])
    if a.get("vorgang") != "Beauftragt":
        raise ScanFehler(f"Angebot {a.get('nummer')} ist nicht beauftragt (Vorgang {a.get('vorgang') or 'Entwurf'}).")
    p = next((x for x in db.positionen(a["id"]) if kurz(_pos_text(x.get("pos"))) == pos and position_aktiv(x)), None)
    if p is None:
        raise ScanFehler(f"Angebot {a.get('nummer')} hat keine Position {pos}.")
    return a, p


def rueckmelden(db, text, schritt, menge=None, wer=None):
    """Scan eines Etiketts für einen Arbeitsschritt merken. Ergebnis: dict(angebot, position, schritt, menge, summe
    (Menge des Schritts für die Position), stueck, status (neu gesetzter Fertigungsstatus oder None), fertig (alle
    Positionen im letzten Schritt vollständig), text). ScanFehler/Lesemodus sonst."""
    from .datenbank import Lesemodus
    if db.nur_lesen:
        raise Lesemodus(f"Lesemodus – {db.nur_lesen}.")
    liste = schritte(db)
    if schritt not in liste:
        raise ScanFehler(f"Arbeitsschritt „{schritt}“ steht nicht in der Liste (Einstellungen → Rückmeldung).")
    a, p = finden(db, text)
    stueck = p.get("stueck") or 0
    menge = stueck if not menge else menge
    wer = wer if wer is not None else (db.einstellung("benutzer_kuerzel") or "")
    with db.con:
        db.con.execute("INSERT INTO rueckmeldungen (angebot_id, position_id, pos, schritt, menge, am, wer, code) "
                       "VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (a["id"], p["id"], _pos_text(p.get("pos")), schritt, menge,
                                                          _jetzt(), wer, str(text).strip()))
    status = None
    if fertigung.aktiv(db) and fertigung.freigabe(db, a["id"]):
        st = fertigung.status_liste(db)
        jetzt = (fertigung.aktuell(db, a["id"]) or {}).get("status")
        if IN_FERTIGUNG in st and jetzt in st and st.index(jetzt) < st.index(IN_FERTIGUNG):
            fertigung.setzen(db, a["id"], IN_FERTIGUNG, "per Scan", wer)
            status = IN_FERTIGUNG
    stand = stand_je_position(db, a["id"])
    summe = next((z["schritte"].get(schritt, 0) for z in stand if z["id"] == p["id"]), menge)
    fertig = bool(stand) and all(z["schritte"].get(liste[-1], 0) >= (z["stueck"] or 0) for z in stand)
    t = f"{a.get('nummer')} Pos. {_pos_text(p.get('pos'))} {p.get('artikel') or ''}".strip()
    t += f": {schritt} {_z(menge)} Stk (gesamt {_z(summe)} von {_z(stueck)})"
    if summe > stueck:
        t += " – mehr als bestellt"
    if status:
        t += f"; Auftrag jetzt „{status}“"
    if fertig:
        t += f"; alle Positionen „{liste[-1]}“ – Auftrag fertig melden?"
    return dict(angebot=a, position=p, schritt=schritt, menge=menge, summe=summe, stueck=stueck, status=status,
                fertig=fertig, text=t)


def _z(x):
    return str(int(x)) if float(x).is_integer() else f"{x:.1f}".replace(".", ",")


def stand_je_position(db, angebot_id):
    """[dict(id, pos, artikel, stueck, schritte={Schritt: Menge}, zuletzt)] für die aktiven Positionen."""
    summen, zuletzt = {}, {}
    for pid, schritt, menge, am in db.con.execute(
            "SELECT position_id, schritt, menge, am FROM rueckmeldungen WHERE angebot_id=? ORDER BY id", (angebot_id,)):
        summen.setdefault(pid, {})
        summen[pid][schritt] = summen[pid].get(schritt, 0) + (menge or 0)
        zuletzt[pid] = am
    return [dict(id=p["id"], pos=_pos_text(p.get("pos")), artikel=p.get("artikel"), stueck=p.get("stueck"),
                 schritte=summen.get(p["id"], {}), zuletzt=zuletzt.get(p["id"]))
            for p in db.positionen(angebot_id) if position_aktiv(p)]


def letzte(db, anzahl=50):
    """Letzte Rückmeldungen aller Aufträge, neueste zuerst."""
    return [dict(r) for r in db.con.execute(
        "SELECT r.*, a.nummer FROM rueckmeldungen r LEFT JOIN angebote a ON a.id = r.angebot_id ORDER BY r.id DESC "
        "LIMIT ?", (anzahl,))]


# ------------------------------------------------------------------ Etiketten als PDF
def etiketten(kopf, positionen, anzahl=1, je_stueck=False):
    """Inhalt der Etiketten: [dict(code, zeilen)] je Position anzahl-mal (je_stueck: so oft wie Stück)."""
    out = []
    for p in positionen:
        if not position_aktiv(p):
            continue
        n = int(p.get("stueck") or 1) if je_stueck else max(1, int(anzahl or 1))
        laenge = p.get("laenge")
        zeilen = [kopf.get("kunde") or "", f"Auftrag {kopf.get('nummer') or ''}",
                  f"Best. {kopf['auftragsnr']}" if kopf.get("auftragsnr") else "",
                  f"Pos. {_pos_text(p.get('pos'))}  {p.get('artikel') or ''}".strip(),
                  " · ".join(str(t) for t in (p.get("profil_id"), p.get("werkstoff_id")) if t),
                  " · ".join(t for t in (f"L = {_z(laenge)} mm" if laenge else "",
                                         f"{_z(p.get('stueck') or 0)} Stk") if t)]
        if kopf.get("liefertermin"):
            try:
                zeilen.append("Termin " + datetime.date.fromisoformat(kopf["liefertermin"]).strftime("%d.%m.%Y"))
            except ValueError:
                pass
        for _ in range(n):
            out.append(dict(code=code(kopf.get("nummer"), p.get("pos")), zeilen=zeilen))
    return out


def _passend(text, schrift, groesse, breite, kleinste):
    """(Text, Schriftgröße): erst kleiner schreiben bis kleinste, dann kürzen."""
    from reportlab.pdfbase.pdfmetrics import stringWidth
    while groesse > kleinste and stringWidth(text, schrift, groesse) > breite:
        groesse = max(kleinste, groesse - 0.25)
    while len(text) > 1 and stringWidth(text, schrift, groesse) > breite:
        text = text[:-2] + "…"
    return text, groesse


def _etikett(c, x, y, b, h, e):
    """Ein Etikett mit linker unterer Ecke (x, y), Größe b × h [pt]: QR links, Text rechts, Code klein darunter.
    Die Position (Zeile 'Pos. …') steht fett und größer."""
    from reportlab.graphics import renderPDF
    from reportlab.graphics.barcode.qr import QrCodeWidget
    from reportlab.graphics.shapes import Drawing
    rand = 2.2 * mm
    q = min(h - 2 * rand, b * 0.36)
    w = QrCodeWidget(e["code"], barLevel="M", barBorder=1)
    x0, y0, x1, y1 = w.getBounds()
    d = Drawing(q, q, transform=[q / (x1 - x0), 0, 0, q / (y1 - y0), 0, 0])
    d.add(w)
    renderPDF.draw(d, c, x + rand * 0.6, y + (h - q) / 2)
    tx = x + rand * 0.6 + q + 1.2 * mm
    tb = x + b - rand - tx
    zeilen = [z for z in e["zeilen"] if z]
    code_g = 5.5
    groesse = max(5.5, min(9, (h - 2 * rand - code_g * 1.2) / (len(zeilen) + 0.3) / 1.17))
    ty = y + h - rand - groesse
    for z in zeilen:
        fett = z.startswith("Pos. ")
        schrift = "Helvetica-Bold" if fett else "Helvetica"
        text, g = _passend(z, schrift, groesse * (1.3 if fett else 1), tb, 5)
        c.setFont(schrift, g)
        c.drawString(tx, ty, text)
        ty -= groesse * (1.3 if fett else 1) * 1.17
    c.setFont("Helvetica", code_g)
    c.setFillGray(0.35)
    c.drawString(tx, y + rand * 0.7, e["code"])
    c.setFillGray(0)


def etiketten_pdf(pfad, liste, format_name=FORMAT_VORGABE, rahmen=False, start=0):
    """Etiketten als PDF. start: so viele Felder des ersten A4-Bogens frei lassen (angebrochener Bogen).
    rahmen: dünne Linie um jedes Etikett (zum Ausschneiden auf Normalpapier)."""
    from reportlab.pdfgen import canvas as rl_canvas
    seite, spalten, zeilen, (eb, eh), rl, ro = FORMATE.get(format_name) or FORMATE[FORMAT_VORGABE]
    eb, eh = eb * mm, eh * mm
    groesse = (seite[0] * mm, seite[1] * mm) if seite else (eb, eh)
    c = rl_canvas.Canvas(str(pfad), pagesize=groesse)
    c.setTitle("Etiketten")
    c.setAuthor("Rohrlaser-Angebotskalkulation")
    je_seite = spalten * zeilen
    felder = [None] * (start % je_seite if seite else 0) + list(liste)
    for i, e in enumerate(felder):
        if i and i % je_seite == 0:
            c.showPage()
        if e is None:
            continue
        k = i % je_seite
        x = rl * mm + (k % spalten) * eb
        y = groesse[1] - ro * mm - (k // spalten + 1) * eh
        if rahmen:
            c.setStrokeGray(0.75)
            c.setLineWidth(0.3)
            c.rect(x, y, eb, eh)
        _etikett(c, x, y, eb, eh, e)
    c.showPage()
    c.save()
    return len(liste)

