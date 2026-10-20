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
from PySide6.QtWidgets import QAbstractItemView, QApplication, QComboBox, QMessageBox, QPushButton, QSpinBox  # noqa: E402

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
    from rohrlaser import staffeln
    from rohrlaser.datenbank import Datenbank
    from rohrlaser.step_dialog import StepPruefDialog
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

    # 3) Einstellungen gesperrt, dann mit Passwort geöffnet; Stammdaten als Unterreiter (Kunden eigener Reiter)
    f.bereich.sperren()
    f.reiter.setCurrentWidget(f.bereich)
    QApplication.processEvents()
    foto.foto("einstellungen_gesperrt", f, [(tab_rect(f.reiter, "Einstellungen"), 1), (f.bereich.passwort, 2),
                                            (knopf(f.bereich, "Einstellungen öffnen"), 3)],
              ausschnitt=QRect(0, 0, 760, f.bereich.passwort.mapTo(f, QPoint(0, 0)).y() + 70))
    f.bereich.oeffnen(db.einstellung("passwort"))
    for seite in f.seiten:
        f.zeigen(seite)
        QApplication.processEvents()
        marken = []
        if seite.t.name == "profile":
            marken = [(tab_rect(f.bereich.unter, seite.t.titel), 1), (knopf(seite, "Neue Zeile"), 2),
                      (knopf(seite, "Zeilen löschen"), 3), (seite.suche, 4)]
            kopf = seite.ansicht.horizontalHeader()
            spalte = len(seite.modell.spalten) - 1
            x = kopf.sectionViewportPosition(spalte)
            marken.append(((kopf, QRect(x, 0, min(kopf.sectionSize(spalte), kopf.width() - x), kopf.height())), 5))
        foto.foto("stamm_" + seite.t.name, f, marken)

    # 4) Einstellungen: Unterreiter Vorgaben
    f.zeigen(f.einstellungen)
    QApplication.processEvents()
    foto.foto("einstellungen", f, [(tab_rect(f.bereich.unter, "Vorgaben"), 1),
                                   (knopf(f.bereich, "Einstellungen sperren"), 2)])
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

    # 6) Angebot öffnen: Positionen vor der Optimierung (breiteres Fenster: Kalkulationsgruppen nebeneinander)
    f.resize(1680, 980)
    s = f.angebot_oeffnen(haupt)
    bereit()
    kopf_box = s.felder["nummer"].parentWidget()
    foto.foto("angebot_positionen", f, [(kopf_box, 1), (s.stand.parentWidget(), 2), (s.pos_ansicht, 3),
                                        (knopf(s, "Neue Position"), 4), (knopf(s, "Zusatzarbeiten …"), 5),
                                        (knopf(s, "STEP importieren …"), 6), (knopf(s, "Optimieren"), 7),
                                        ((s.pos_seite, QRect(0, 0, s.pos_seite.width(), s.pos_ansicht.y() - 2)), 8)])
    kb = s.kopf_bereich
    s.kopf_bereich.erweitert_bereich.aufklappen(True)
    s.kopf_bereich.maschinen_bereich.aufklappen(True)
    QApplication.processEvents()
    foto.foto("angebot_erweitert", s.teiler.widget(0).widget())     # ganzer oberer Teil, auch was gerollt wäre
    kb.erweitert_bereich.aufklappen(False)
    kb.maschinen_bereich.aufklappen(False)
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
    # Zeiten & Arbeitskosten mit Beispielzeiten, danach wieder die Vorgaben (Preise der übrigen Bilder unverändert)
    zb = db.zeitbasis_vorgabe(s.kopf.get("maschine"))
    beispiel = {"Materialbereitstellung": dict(ruestzeit=10), "Entgraten / Nachbearbeitung": dict(zeit=20),
                "Qualitätskontrolle": dict(ruestzeit=5, zeit=10), "Verpackung": dict(zeit=120, bezug="Stange")}
    for x in zb["schritte"]:
        x.update(beispiel.get(x["schritt"], {}))
    db.zeitbasis_speichern(haupt, zb)
    s.neu_laden()
    reiter_waehlen(s, "Zeiten && Arbeitskosten")
    zs = s.zeiten_seite
    foto.foto("erg_zeiten", f, [(zs.alle, 1), (zs.uebernehmen, 2), (zs.summen, 3)], ausschnitt=reiterflaeche(s))
    db.zeitbasis_speichern(haupt, db.zeitbasis_vorgabe(s.kopf.get("maschine")))
    s.neu_laden()
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
    spalte = {m.name(i): i for i in range(m.columnCount())}
    kopf = s.pos_ansicht.horizontalHeader()

    def kopf_marke(c):
        x = kopf.sectionViewportPosition(c)
        return (kopf, QRect(x, 0, kopf.sectionSize(c), kopf.height()))
    QApplication.processEvents()
    status = s.pos_ansicht.visualRect(m.index(1, spalte["status"]))
    foto.foto("angebot_zusatz", f, [(kopf_marke(spalte["zeit_manuell"]), 1), (kopf_marke(spalte["zusatz"]), 2),
                                    ((s.pos_ansicht.viewport(), status), 3)], ausschnitt=reiterflaeche(s))
    s._spalten_zeigen()

    # 8) Staffeln: Gestelle als Satz
    for menge, bem in ((1, "Einzelgestell"), (2, "Anfrage"), (5, "kleine Serie"), (10, "Rahmenauftrag")):
        db.staffel_neu(haupt, dict(schluessel="MG 2000", menge=menge, bemerkung=bem))
    s.neu_laden()
    reiter_waehlen(s, "Staffeln")
    bereit()
    st = s.st_seite
    foto.foto("staffeln_vorher", f, [(knopf(s, "Neue Stufe"), 1), (knopf(s, "Stufen aus Angebot"), 2),
                                     (s.staffel_ansicht, 3), (knopf(s, "Staffelpreise rechnen"), 4),
                                     (st.erweitert, 5)],
              ausschnitt=reiterflaeche(s))
    s.staffelpreise_rechnen()
    spalte_st = [x.name for x in staffeln.STUFE_FELDER].index
    for zeile, zuschlag in enumerate((20, 15, 10, 5)):      # Materialzuschlag je Stufe (Beispiel)
        st.modell.setData(st.modell.index(zeile, spalte_st("mat_zuschlag")), str(zuschlag))
    st.vorher = {}
    st.stand()
    oben_vorher = s.teiler.sizes()
    s.teiler.setSizes([0, sum(oben_vorher)])          # Kopf des Angebots zuklappen: mehr Platz fürs Ergebnis
    st.teiler.setSizes([140, 2000])
    baum = st.baum
    baum.collapseAll()
    baum.zeile("material").setExpanded(True)
    QApplication.processEvents()
    def rect(schl):
        r = baum.visualItemRect(baum.zeile(schl))
        r.setWidth(baum.columnWidth(0))
        return (baum.viewport(), r)
    foto.foto("staffeln", f, [((st.ansicht.viewport(), st.ansicht.visualRect(
        st.modell.index(0, spalte_st("mat_zuschlag")))), 1), (rect("material"), 2), (rect("selbst"), 3),
        (rect("vk"), 4), (rect("brutto"), 5), (st.vergleich, 6), (st.info, 7)], ausschnitt=reiterflaeche(s))
    st.modell.setData(st.modell.index(3, spalte_st("ruesten")), staffeln.SEPARAT)
    st.modell.setData(st.modell.index(3, spalte_st("neben_einheit")), "12")
    st.erweitert.setChecked(True)
    for schl in ("fertigung", "ruesten", "gemeinkosten"):
        baum.zeile(schl).setExpanded(True)
    baum.zeile("material").setExpanded(False)
    QApplication.processEvents()
    baum.scrollToItem(baum.zeile("fertigung"), QAbstractItemView.PositionAtTop)
    QApplication.processEvents()
    foto.foto("staffeln_details", f, [(rect("fertigung"), 1), (rect("ruesten"), 2), (rect("gemeinkosten"), 3),
                                      (rect("einmalig"), 4), (rect("aenderung"), 5)], ausschnitt=reiterflaeche(s))
    st.erweitert.setChecked(False)
    s.teiler.setSizes(oben_vorher)

    # 8a) Nachkalkulation nach dem Auftrag: eine Stange QR 40x40x3 mehr, Laser etwas länger, Rechnung Verzinkerei
    reiter_waehlen(s, "Nachkalkulation")
    nk = s.nachkalk
    gr = {g["profil"]: g for g in __import__("rohrlaser.nachkalkulation", fromlist=["x"]).gruppen(
        s.ergebnis, s.kopf, s.positionen, s.k, s.tabellen)}
    soll = {z["text"]: z for z in nk.vergleich.zeilen}
    nk.setzen(dict(laser_h=round(soll["Laserzeit"]["soll_menge"] * 1.15, 2), ruest_min=75,
                   zusatz=round(soll["Gewinde und Zusatzarbeiten"]["soll"] + 38, 2), sonstiges=24.0,
                   bemerkung="Stiele nachgeschnitten, Verzinkerei-Rechnung 4711"),
              {g["schluessel"]: g["soll"] + (1 if p == "QR 40x40x3" else 0) for p, g in gr.items()},
              {g["schluessel"]: round(g["meterpreis"] * 1.06, 2) for p, g in gr.items() if p == "QR 40x40x3"})
    bereit()
    foto.foto("nachkalkulation", f, [(nk.gruppen, 1), (nk.felder["laser_h"].parentWidget(), 2),
                                     (nk.vergleich_ansicht, 3), (knopf(nk, "Nachkalkulation (PDF)"), 4)],
              ausschnitt=reiterflaeche(s))

    # 9) Ausgabe
    reiter_waehlen(s, "Positionen")
    bereit()
    unterkante = knopf(s, "Angebot (PDF)").mapTo(f, QPoint(0, 0)).y() + 34
    oberkante = knopf(s, "Angebot (PDF)").mapTo(f, QPoint(0, 0)).y() - 10
    foto.foto("ausgabe_leiste", f, [(knopf(s, "Angebot (PDF)"), 1), (knopf(s, "Werkstattpapiere (PDF)"), 2),
                                    (knopf(s, "Kalkulation (PDF)"), 3), (knopf(s, "Weitere Aktionen"), 4)],
              ausschnitt=QRect(0, oberkante, f.width(), unterkante - oberkante))
    pdfs = dict(angebot=s.angebot_pdf(), werkstatt=s.werkstatt_pdf(), kalkulation=s.kalkulation_pdf(),
                nachkalkulation=s.nachkalk.pdf())
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
    f.stumm = False

    def pruefen_ausfuellen():                            # nach der Messung: Prüfdialog mit der Rohrliste
        d = QApplication.activeModalWidget()
        if not isinstance(d, StepPruefDialog):
            QTimer.singleShot(50, pruefen_ausfuellen)
            return
        d.resize(1300, 620)
        d.alle_setzen("S235-10219", 10)                  # „Für alle“
        d.zeile_setzen("T05_RR33-7x2-6_L500", stueck=25)
        d.zeile_setzen("T04_RE60x40x3_Gehrung", werkstoff="S355-10219")
        d.datei_waehlen(1)                               # mit ▶ zur zweiten Datei (T02 mit Bohrung)
        d.baum.setCurrentItem(next(z.it for z in d.zeilen if z.datei == d.datei))
        bereit()
        foto.foto("step_pruefen", d, [(d.kopf, 1), (d.baum, 2), (d.leiste, 3)])
        f.stumm = True                                   # danach keine Rückfragen mehr
        d.accept()
    QTimer.singleShot(100, pruefen_ausfuellen)
    s2.step_importieren([str(p) for p in STEP])
    f.stumm = True
    bereit()
    s2.zeige_step.setChecked(True)
    foto.foto("step_positionen", f, [(s2.zeige_step, 1)])
    d3 = s2.ansicht_3d(6)                                # 3D-Ansicht: T07 mit Innenkontur und Gravur
    d3.resize(1150, 560)
    d3.show()
    bereit()
    foto.foto("step_3d", d3, [(d3.ansicht.knoepfe, 1)])
    d3.close()
    reiter_waehlen(s2, "STEP-Protokoll")
    foto.foto("step_protokoll", f, ausschnitt=reiterflaeche(s2))
    s2.optimieren()
    reiter_waehlen(s2, "Positionen")
    s2.zeige_step.setChecked(False)
    bereit()
    foto.foto("step_optimiert", f)

    # 11) Baugruppe (mehrere Teile in einer STEP) als Satz: oben im Prüfdialog 4 Sätze eintragen
    gestell = db.angebot_neu(dict(kunde="Stahlbau Ostermann", kundennr="10588", bemerkung="Gestell als Baugruppe (STEP)"))
    s3 = f.angebot_oeffnen(gestell)
    f.stumm = False

    def satz_ausfuellen():                               # nach der Messung: Prüfdialog mit Feld „Sätze“
        d = QApplication.activeModalWidget()
        if not isinstance(d, StepPruefDialog):
            QTimer.singleShot(50, satz_ausfuellen)
            return
        d.resize(1300, 520)
        d.satz_spin.setValue(4)
        d.baum.setCurrentItem(d.zeilen[0].it)
        bereit()
        foto.foto("step_satz_pruefen", d, [(d.satz_feld, 1), (d.baum, 2)])
        f.stumm = True
        d.accept()
    QTimer.singleShot(100, satz_ausfuellen)
    s3.step_importieren([str(BAUGRUPPE)], werkstoff="S235-10219")
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
