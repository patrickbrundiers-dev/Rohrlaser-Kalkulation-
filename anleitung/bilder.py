"""Bildschirmfotos für die Bedienungsanleitung, aus dem echten Programm mit Beispieldaten.

Das Programm läuft unsichtbar (QT_QPA_PLATFORM=offscreen), startet mit den Beispiel-Stammdaten,
bekommt
ein realistisches Angebot (Maschinengestell aus der Abnahme), wird bedient wie von Hand und
fotografiert Fenster, Reiter und Dialoge. Wichtige Bedienelemente bekommen rote Nummern, die der Text
der Anleitung aufgreift. Die PDF-Ausgaben des Programms werden als Seitenbilder eingebunden.

Aufruf: python anleitung/bilder.py ZIELORDNER   (schreibt PNG-Dateien und bilder.json)
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_SCALE_FACTOR", "2")      # doppelte Auflösung, damit der Druck scharf wird

HIER = Path(__file__).resolve().parent
WURZEL = HIER.parent
sys.path.insert(0, str(WURZEL / "programm"))
sys.path.insert(0, str(WURZEL / "tools"))
sys.path.insert(0, str(WURZEL / "tests"))

from PySide6.QtCore import QLocale, QPoint, QRect, QRectF, Qt, QTimer  # noqa: E402
from PySide6.QtGui import QColor, QFont, QPainter, QPen  # noqa: E402
from PySide6.QtWidgets import QApplication, QComboBox, QMessageBox, QPushButton, QSpinBox  # noqa: E402

from abnahme_angebote import ANGEBOTE  # noqa: E402

STEP = sorted((WURZEL / "tests" / "step").glob("*.step"))
BAUGRUPPE = WURZEL / "tests" / "step_satz" / "T08_Gestell_Baugruppe.step"
ROT = QColor("#D0021B")

FIRMA = ("Muster Rohrlaser GmbH", "Industriestraße 12", "12345 Musterstadt", "Tel. 01234 5678-0 · info@muster-rohrlaser.example")


class Fotograf:
    def __init__(self, ziel):
        self.ziel = Path(ziel)
        self.ziel.mkdir(parents=True, exist_ok=True)
        self.bilder = {}

    def foto(self, name, wurzel, marken=(), ausschnitt=None):
        """wurzel fotografieren; marken = [(Widget oder (Widget, QRect im Widget), Nummer)];
        ausschnitt = QRect in Koordinaten von wurzel (nur diesen Teil speichern)."""
        QApplication.processEvents()
        bild = wurzel.grab()
        dpr = bild.devicePixelRatio()
        p = QPainter(bild)
        p.setRenderHint(QPainter.Antialiasing)
        for ziel, nr in marken:
            w, r = ziel if isinstance(ziel, tuple) else (ziel, None)
            r = QRect(r) if r is not None else w.rect()
            r.moveTopLeft(w.mapTo(wurzel, r.topLeft()))
            r = r.adjusted(-2, -2, 2, 2)
            p.setPen(QPen(ROT, 2.2))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(QRectF(r), 4, 4)
            d = 20
            mitte = QPoint(r.left() + 2, r.top() + 2)
            kreis = QRectF(mitte.x() - d / 2, mitte.y() - d / 2, d, d)
            p.setPen(QPen(QColor("white"), 1.5))
            p.setBrush(ROT)
            p.drawEllipse(kreis)
            f = QFont(QApplication.font())
            f.setBold(True)
            f.setPointSizeF(8.5)
            p.setFont(f)
            p.setPen(QColor("white"))
            p.drawText(kreis, Qt.AlignCenter, str(nr))
        p.end()
        if ausschnitt is not None:
            bild = bild.copy(QRect(int(ausschnitt.x() * dpr), int(ausschnitt.y() * dpr),
                                   int(ausschnitt.width() * dpr), int(ausschnitt.height() * dpr)))
        datei = self.ziel / f"{name}.png"
        bild.save(str(datei))
        self.bilder[name] = dict(datei=datei.name, breite=bild.width(), hoehe=bild.height())
        return datei


def tab_rect(reiter, text):
    leiste = reiter.tabBar()
    for i in range(reiter.count()):
        if reiter.tabText(i) == text:
            return (leiste, leiste.tabRect(i))
    raise KeyError(text)


def knopf(wurzel, text):
    for b in wurzel.findChildren(QPushButton):
        if b.text() == text:
            return b
    raise KeyError(text)


def angebot_anlegen(db, vorlage, nummer, kunde, kundennr, bemerkung, saetze=None):
    """Angebot aus einer Vorlage der Abnahme anlegen; saetze = Anzahl Gestelle (Spalte Satz, Stück je Satz)."""
    a = db.angebot_neu(dict(nummer=nummer, kunde=kunde, kundennr=kundennr, maschine=vorlage["maschine"],
                            stange=vorlage["stange"], bemerkung=bemerkung, datum="2026-10-19"))
    for p in vorlage["positionen"]:
        werte = dict(pos=p["pos"], artikel=p["artikel"], bezeichnung=p["bezeichnung"], profil_id=p["profil"],
                     werkstoff_id=p["werkstoff"], laenge=p["laenge"], stueck=p["stueck"])
        for f in ("schneidweg", "einstiche", "a_gerade", "b_gerade", "stange"):
            if p.get(f) is not None:
                werte[f] = p[f]
        if saetze:
            werte.update(satz="MG 2000", je_satz=p["stueck"] // saetze)
        db.position_neu(a, werte)
    return a


def mit_dialog(aktion, foto, name, antwort):
    """aktion() öffnet einen modalen Dialog; der wird fotografiert und mit antwort(dialog) geschlossen."""
    def knipsen():
        d = QApplication.activeModalWidget()
        if d is None:
            QTimer.singleShot(50, knipsen)
            return
        foto.foto(name, d)
        antwort(d)
    QTimer.singleShot(100, knipsen)
    return aktion()


def ja(d):
    for b in d.findChildren(QPushButton):
        if b.text().replace("&", "") in ("Yes", "Ja", "OK"):
            b.click()
            return
    d.accept()


def reiter_waehlen(s, text):
    for i in range(s.reiter.count()):
        if s.reiter.tabText(i) == text:
            s.reiter.setCurrentIndex(i)
            QApplication.processEvents()
            return
    raise KeyError(text)


def main(ziel):
    from rohrlaser.datenbank import Datenbank
    from rohrlaser.fenster import Hauptfenster
    from rohrlaser.__main__ import deutsch

    QLocale.setDefault(QLocale(QLocale.German, QLocale.Germany))
    app = QApplication(sys.argv[:1])
    app.setStyle("Fusion")
    deutsch(app)
    app.setFont(QFont("Liberation Sans", 9))
    foto = Fotograf(ziel)
    tmp = Path(tempfile.mkdtemp(prefix="anleitung_"))
    programmordner = tmp / "Rohrlaser-Angebotskalkulation"
    (programmordner / "Daten").mkdir(parents=True)
    db = Datenbank(programmordner / "Daten" / "rohrlaser.db")
    f = Hauptfenster(db, programmordner, stumm=True)
    f.resize(1280, 760)
    f.show()
    QApplication.processEvents()

    def start_zeigen():
        # Pfad so zeigen, wie er unter Windows aussieht
        f.start.neu_laden()
        f.start.info.setText(f.start.info.text().replace(str(db.pfad), r"C:\Rohrlaser\Daten\rohrlaser.db"))
        f.reiter.setCurrentWidget(f.start)
        f.statusBar().showMessage("Bereit")

    def reiterflaeche(seite):
        """Nur die Reiter des Angebots (Kopf und Knöpfe stehen schon auf dem ersten Bild)."""
        y = seite.reiter.mapTo(f, QPoint(0, 0)).y() - 4
        return QRect(0, y, f.width(), f.height() - y)

    def bereit():
        f.statusBar().setStyleSheet("")
        f.statusBar().showMessage("Bereit")

    # 1) Start mit Beispieldaten
    start_zeigen()
    foto.foto("start_beispiel", f, [(knopf(f.start, "Datensicherung erstellen"), 1),
                                    (knopf(f.start, "Datenordner öffnen"), 2)])

    # 2) Eigener Briefkopf und Nummernkreis
    for i, text in enumerate(FIRMA, 1):
        db.einstellung_setzen(f"briefkopf_{i}", text)
    db.einstellung_setzen("letzte_angebotsnummer", "A-2026-0038")
    for kd in (("10417", "Metallbau Krüger", "Werkstraße 3", "34117 Kassel", "Herr Krüger", "0561 12345",
                "info@krueger-metallbau.example", 2, 10, 30, "Stammkunde"),
               ("10233", "Anlagenbau Hessler", "Am Hafen 8", "60314 Frankfurt", "Frau Hessler", "069 987654",
                "einkauf@hessler-anlagenbau.example", 3, 14, 45, "Rahmenvertrag")):
        db.neu("kunden", dict(zip(("kundennr", "name", "strasse", "plz_ort", "ansprechpartner", "telefon", "email",
                                   "skonto", "skonto_tage", "zahlungsziel", "bemerkung"), kd)))
    f.alles_neu_laden()

    # 3) Stammdaten-Reiter
    for seite in f.seiten:
        f.reiter.setCurrentWidget(seite)
        QApplication.processEvents()
        marken = []
        if seite.t.name == "profile":
            marken = [(tab_rect(f.reiter, seite.t.titel), 1), (knopf(seite, "Neue Zeile"), 2),
                      (knopf(seite, "Zeilen löschen"), 3), (seite.suche, 4)]
            kopf = seite.ansicht.horizontalHeader()
            spalte = len(seite.modell.spalten) - 1
            x = kopf.sectionViewportPosition(spalte)
            marken.append(((kopf, QRect(x, 0, min(kopf.sectionSize(spalte), kopf.width() - x), kopf.height())), 5))
        foto.foto("stamm_" + seite.t.name, f, marken)

    # 4) Einstellungen
    f.reiter.setCurrentWidget(f.einstellungen)
    foto.foto("einstellungen", f)
    leiste = f.einstellungen.verticalScrollBar()
    leiste.setValue(leiste.maximum())
    foto.foto("einstellungen_unten", f)
    leiste.setValue(0)

    # 5) Angebote: Beispielangebot Maschinengestell (2 Gestelle), dazu zwei ältere Angebote für die Liste
    vorlagen = {a["nummer"]: a for a in ANGEBOTE}
    a1 = angebot_anlegen(db, vorlagen["ABN-01"], "A-2026-0039", "Metallbau Krüger", "10417", "Geländer Treppenhaus")
    a2 = angebot_anlegen(db, vorlagen["ABN-08"], "A-2026-0040", "Metallbau Krüger", "10417", "Nachbestellung")
    haupt = angebot_anlegen(db, vorlagen["ABN-02"], "A-2026-0041", "Anlagenbau Hessler", "10233",
                            "Maschinengestell MG 2000", saetze=2)
    db.einstellung_setzen("letzte_angebotsnummer", "A-2026-0041")
    for a in (a1, a2):
        f.angebot_oeffnen(a).optimieren()
        f.angebot_schliessen(a)
    f.reiter.setCurrentWidget(f.angebote)
    f.angebote.neu_laden()
    bereit()
    au = f.angebote
    foto.foto("angebote", f, [(tab_rect(f.reiter, "Angebote"), 1), (knopf(au, "Neues Angebot"), 2),
                               (knopf(au, "Kopieren"), 3), (au.suche, 4)])
    mit_dialog(lambda: au._kunde_fuer_kopie(db.angebot(a2)), foto, "kopieren_dialog", lambda d: d.reject())

    # 6) Angebot öffnen: Positionen vor der Optimierung
    s = f.angebot_oeffnen(haupt)
    bereit()
    kopf_box = s.felder["nummer"].parentWidget()
    foto.foto("angebot_positionen", f, [(kopf_box, 1), (s.stand.parentWidget(), 2), (s.pos_ansicht, 3),
                                        (knopf(s, "Neue Position"), 4), (knopf(s, "Zusatzarbeiten …"), 5),
                                        (knopf(s, "STEP importieren …"), 6), (knopf(s, "Optimieren"), 7),
                                        (s.zeige_berechnet, 8)])
    s.zeige_berechnet.setChecked(True)
    foto.foto("angebot_berechnet", f)
    s.zeige_berechnet.setChecked(False)

    # 7) Optimieren und Ergebnisse
    s.optimieren()
    foto.foto("angebot_optimiert", f, [(s.stand, 1)])
    for text, name in (("Kalkulation", "erg_kalkulation"), ("Schnittplan", "erg_schnittplan"),
                       ("Stangenbild", "erg_stangenbild"), ("Auswertung", "erg_auswertung")):
        reiter_waehlen(s, text)
        if text == "Schnittplan":
            s.stangen_ansicht.selectRow(2)
        foto.foto(name, f, ausschnitt=reiterflaeche(s))
    # veraltet nach einer Änderung
    pos = db.positionen(haupt)
    db.position_aendern(pos[0]["id"], "stueck", 10)
    s.neu_laden()
    reiter_waehlen(s, "Positionen")
    foto.foto("angebot_veraltet", f, [(s.stand, 1)])
    db.position_aendern(pos[0]["id"], "stueck", 8)
    s.neu_laden()
    s.optimieren()

    # 7a) Zusatzarbeiten: alle Teile feuerverzinkt; Pos. 1 zusätzlich Gewinde und Gravur extra (Dialog);
    #     Pos. 2 mit manueller Schneidzeit
    s.zusatzarbeiten(list(range(len(s.positionen))), (None, json.dumps([dict(name="Feuerverzinken")])))

    def zusatz_ausfuellen(d):
        d.gewinde.setText("2xM8")
        r = d.zeile_neu()
        d.tabelle.cellWidget(r, 0).setCurrentText("Gravur extra")
        d.tabelle.cellWidget(r, 4).setText("Logo")
        QApplication.processEvents()
        foto.foto("zusatz_dialog", d, [(d.gewinde, 1), (d.tabelle.cellWidget(r, 0), 2),
                                       (d.tabelle.cellWidget(0, 2), 3), (d.tabelle.cellWidget(r, 4), 4),
                                       (knopf(d, "Zusatzarbeit hinzufügen"), 5)])
        d._ok()
    QTimer.singleShot(100, lambda: _warte_modal(zusatz_ausfuellen))
    s.zusatzarbeiten([0])
    db.position_aendern(s.positionen[1]["id"], "zeit_manuell", 45.0)
    s.neu_laden()
    bereit()
    m = s.pos_modell
    versteckt = [i for i, (art, x) in enumerate(m.spalten) if art == "feld" and x.name in
                 ("einstiche", "stange", "satz", "je_satz", "preis_m")]
    for c in versteckt:
        s.pos_ansicht.setColumnHidden(c, True)
    spalte = {x.name if art != "status" else "status": i for i, (art, x) in enumerate(m.spalten) if art != "berechnet"}
    kopf = s.pos_ansicht.horizontalHeader()

    def kopf_marke(c):
        x = kopf.sectionViewportPosition(c)
        return (kopf, QRect(x, 0, kopf.sectionSize(c), kopf.height()))
    QApplication.processEvents()
    status = s.pos_ansicht.visualRect(m.index(1, spalte["status"]))
    foto.foto("angebot_zusatz", f, [(kopf_marke(spalte["zeit_manuell"]), 1), (kopf_marke(spalte["zusatz"]), 2),
                                    ((s.pos_ansicht.viewport(), status), 3)], ausschnitt=reiterflaeche(s))
    for c in versteckt:
        s.pos_ansicht.setColumnHidden(c, False)

    # 8) Staffeln: Gestelle als Satz
    for menge, bem in ((1, "Einzelgestell"), (2, "Anfrage"), (5, "kleine Serie"), (10, "Rahmenauftrag")):
        db.staffel_neu(haupt, dict(schluessel="MG 2000", menge=menge, bemerkung=bem))
    s.neu_laden()
    reiter_waehlen(s, "Staffeln")
    bereit()
    foto.foto("staffeln_vorher", f, [(knopf(s, "Neue Stufe"), 1), (s.staffel_ansicht, 2),
                                     (knopf(s, "Staffelpreise rechnen"), 3)], ausschnitt=reiterflaeche(s))
    s.staffelpreise_rechnen()
    foto.foto("staffeln", f, ausschnitt=reiterflaeche(s))

    # 9) Ausgabe
    reiter_waehlen(s, "Positionen")
    bereit()
    unterkante = knopf(s, "Angebot (PDF)").mapTo(f, QPoint(0, 0)).y() + 34
    foto.foto("ausgabe_leiste", f, [(knopf(s, "Angebot (PDF)"), 1), (knopf(s, "Werkstattpapiere (PDF)"), 2),
                                    (knopf(s, "Kalkulation (PDF)"), 3), (knopf(s, "CSV-Export"), 4),
                                    (knopf(s, "Ablage öffnen"), 5)],
              ausschnitt=QRect(0, 0, f.width(), unterkante))
    pdfs = dict(angebot=s.angebot_pdf(), werkstatt=s.werkstatt_pdf(), kalkulation=s.kalkulation_pdf())
    s.csv_export()
    seiten = {}
    for art, pfad in pdfs.items():
        info = subprocess.run(["pdfinfo", str(pfad)], capture_output=True, text=True, check=True).stdout
        n = int(next(z.split()[-1] for z in info.splitlines() if z.startswith("Pages:")))
        seiten[art] = n
        for nr in range(1, n + 1):
            pdf_seite(pfad, foto, f"pdf_{art}_{nr}", nr)
    ablage = sorted(p.name for p in (programmordner / "Angebote").iterdir())

    # 10) STEP-Import in ein neues Angebot (Testteile aus tests/step)
    neu = db.angebot_neu(dict(kunde="Stahlbau Ostermann", kundennr="10588", bemerkung="Teile laut Zeichnung (STEP)"))
    s2 = f.angebot_oeffnen(neu)
    s2.f.stumm = False
    def step_dialog_ausfuellen(d):
        d.findChild(QComboBox).setCurrentText("S235-10219")
        d.findChild(QSpinBox).setValue(10)
        foto.foto("step_dialog", d)
        d.accept()
    QTimer.singleShot(100, lambda: _warte_modal(step_dialog_ausfuellen))
    auswahl = s2._step_dialog()
    f.stumm = True
    s2.step_importieren([str(p) for p in STEP], werkstoff=auswahl[0], stueck=auswahl[1])
    bereit()
    s2.zeige_step.setChecked(True)
    foto.foto("step_positionen", f, [(s2.zeige_step, 1)])
    reiter_waehlen(s2, "STEP-Protokoll")
    foto.foto("step_protokoll", f, ausschnitt=reiterflaeche(s2))
    s2.optimieren()
    reiter_waehlen(s2, "Positionen")
    s2.zeige_step.setChecked(False)
    bereit()
    foto.foto("step_optimiert", f)

    # 11) Baugruppe (mehrere Teile in einer STEP) als Satz, mit der echten Rückfrage
    gestell = db.angebot_neu(dict(kunde="Stahlbau Ostermann", kundennr="10588", bemerkung="Gestell als Baugruppe (STEP)"))
    s3 = f.angebot_oeffnen(gestell)
    f.stumm = False

    def abschluss_schliessen():
        d = QApplication.activeModalWidget()
        if not isinstance(d, QMessageBox) or "übernommen" not in d.text():
            QTimer.singleShot(50, abschluss_schliessen)
            return
        d.accept()

    def satz_ja(d):
        ja(d)
        QTimer.singleShot(50, abschluss_schliessen)      # Abschlussmeldung „… übernommen“ schließen
    def frage_knipsen():                                 # erst nach der Messung (Fortschrittsanzeige) kommt die Frage
        d = QApplication.activeModalWidget()
        if not isinstance(d, QMessageBox) or "Satz" not in d.text():
            QTimer.singleShot(50, frage_knipsen)
            return
        foto.foto("step_satz_frage", d)
        satz_ja(d)
    QTimer.singleShot(100, frage_knipsen)
    s3.step_importieren([str(BAUGRUPPE)], werkstoff="S235-10219", stueck=4)
    f.stumm = True
    bereit()
    spalten = [i for i, (art, x) in enumerate(s3.pos_modell.spalten) if art == "feld" and x.name in ("satz", "je_satz", "stueck")]
    s3.pos_ansicht.scrollTo(s3.pos_modell.index(0, max(spalten)))
    QApplication.processEvents()
    foto.foto("step_satz_positionen", f, [(s3.pos_ansicht, 1)])

    # Menü Hilfe
    f.reiter.setCurrentWidget(f.start)
    start_zeigen()
    (Path(ziel) / "bilder.json").write_text(json.dumps(dict(bilder=foto.bilder, seiten=seiten, ablage=ablage),
                                                       indent=1, ensure_ascii=False), encoding="utf-8")
    f.close()
    db.schliessen()


def _warte_modal(aufruf):
    d = QApplication.activeModalWidget()
    if d is None:
        QTimer.singleShot(50, lambda: _warte_modal(aufruf))
        return
    aufruf(d)


def pdf_seite(pdf, foto, name, seite, dpi=110):
    """Eine PDF-Seite als PNG (pdftoppm aus Poppler)."""
    basis = foto.ziel / name
    subprocess.run(["pdftoppm", "-png", "-r", str(dpi), "-f", str(seite), "-l", str(seite), "-singlefile",
                    str(pdf), str(basis)], check=True)
    foto.bilder[name] = dict(datei=basis.with_suffix(".png").name)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "anleitung_bilder")
