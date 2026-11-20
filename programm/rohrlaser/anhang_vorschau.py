"""Vorschau für Anhänge im Programm (Patrick 17.11.2026: „Die Dokumente in der Mail in einem eigenen Viewer im
Programm als Vorschau, wenn ich drauf drücke, nicht extern öffnen“, Freigabe „Alle Empfehlungen a“ und „noch eine
Vorschau für Word und Excel“).

Ein eigenes Fenster (F1 a), das offen bleiben kann; ◀ ▶ bzw. Bild auf/ab springen zum vorigen/nächsten Anhang:
  PDF       alle Seiten untereinander (pypdfium2, wie die PDF-Vorschau vor dem Speichern), mit Zoom
  Bilder    JPG, PNG, BMP, GIF, TIF (auch mehrseitig), WEBP, mit Zoom
  Mail      .msg/.eml: Von, Datum, Betreff, Text; ihre Anhänge stehen darunter und öffnen sich in derselben Vorschau
  Word      .docx: Absätze, Überschriften und Tabellen (gelesen aus dem Dokument selbst, ohne Word)
  Excel     .xlsx/.xlsm: jedes Blatt als Tabelle (Werte, wie Excel sie zuletzt gespeichert hat; ohne Excel)
  DXF       Zeichnung mit Linien, Bögen, Kreisen und Texten (dxf_import)
  STEP/IGES 3D-Ansicht; die Messung (STEP-Import) rechnet im Hintergrund, bis dahin steht „3D wird berechnet …“
  Text      TXT, CSV, LOG, XML, JSON
Alles andere (z. B. alte .doc/.xls, ZIP) zeigt „Keine Vorschau“ und den Knopf „Extern öffnen“ (F2 a); den Knopf gibt
es bei jeder Datei (F3 a). Gelesen wird nur, nichts ausgeführt: Makros in Office-Dateien laufen nie.
Die Lese-Teile brauchen kein Fenster und sind einzeln prüfbar: art, docx_html, xlsx_blaetter, dxf_elemente, text_lesen, netz_vereint."""
import html
import json
import re
import subprocess
import tempfile
import time
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtCore import Qt

PDF = {".pdf"}
BILD = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".tif", ".tiff", ".webp"}
MAIL = {".msg", ".eml"}
WORD = {".docx", ".docm"}
EXCEL = {".xlsx", ".xlsm"}
DXF = {".dxf"}
STEP = {".step", ".stp", ".igs", ".iges"}
TEXT = {".txt", ".csv", ".log", ".xml", ".json", ".ini"}
ARTEN = (("pdf", PDF), ("bild", BILD), ("mail", MAIL), ("word", WORD), ("excel", EXCEL), ("dxf", DXF),
         ("step", STEP), ("text", TEXT))
ART_TEXT = dict(pdf="PDF", bild="Bild", mail="E-Mail", word="Word", excel="Excel", dxf="DXF-Zeichnung",
                step="3D-Modell", text="Text", keine="Datei")
TEXT_MAX = 2_000_000            # so viele Zeichen Text höchstens zeigen
ZEILEN_MAX = 2000               # Excel: Zeilen je Blatt höchstens
SPALTEN_MAX = 80
STEP_ZEITLIMIT_S = 300

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
S = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
PR = "{http://schemas.openxmlformats.org/package/2006/relationships}"


def art(pfad):
    """Art der Vorschau für eine Datei: pdf, bild, mail, word, excel, dxf, step, text oder keine."""
    e = Path(str(pfad)).suffix.lower()
    return next((a for a, endungen in ARTEN if e in endungen), "keine")


# ------------------------------------------------------------------ Text
def text_lesen(pfad, hoechstens=TEXT_MAX):
    daten = Path(pfad).read_bytes()[: hoechstens * 2]
    for zs in ("utf-8-sig", "cp1252"):
        try:
            return daten.decode(zs)[:hoechstens]
        except UnicodeDecodeError:
            continue
    return daten.decode("latin-1", errors="replace")[:hoechstens]


# ------------------------------------------------------------------ Word (.docx)
def _xml(z, name):
    try:
        return ET.fromstring(z.read(name))
    except (KeyError, ET.ParseError):
        return None


def _w_text(el):
    teile = []
    for t in el.iter():
        if t.tag == W + "t" and t.text:
            teile.append(t.text)
        elif t.tag == W + "tab":
            teile.append("\t")
        elif t.tag in (W + "br", W + "cr"):
            teile.append("\n")
    return "".join(teile)


def _w_absatz(p):
    stil = p.find(f"{W}pPr/{W}pStyle")
    s = (stil.get(W + "val") if stil is not None else "") or ""
    text = html.escape(_w_text(p)).replace("\n", "<br>")
    m = re.match(r"(?i)(heading|berschrift|titel|title)\s*(\d)?", s.replace("Ü", "").replace("ü", ""))
    if m and text:
        n = min(int(m.group(2) or 1) + 1, 4)
        return f"<h{n}>{text}</h{n}>"
    fett = p.find(f".//{W}b") is not None and len(text) < 120
    return f"<p>{'<b>' if fett else ''}{text or '&nbsp;'}{'</b>' if fett else ''}</p>"


def docx_html(pfad):
    """Inhalt eines Word-Dokuments (.docx) als einfaches HTML: Überschriften, Absätze, Tabellen, Kopf-/Fußzeilen
    unten. Ohne Word, Makros laufen nie."""
    with zipfile.ZipFile(pfad) as z:
        doc = _xml(z, "word/document.xml")
        if doc is None:
            raise ValueError("kein Word-Dokument (.docx)")
        body = doc.find(W + "body")
        teile = []
        for el in list(body) if body is not None else []:
            if el.tag == W + "p":
                teile.append(_w_absatz(el))
            elif el.tag == W + "tbl":
                zeilen = []
                for tr in el.iter(W + "tr"):
                    zellen = "".join("<td>" + "<br>".join(html.escape(_w_text(p)) for p in tc.iter(W + "p"))
                                     + "</td>" for tc in tr.findall(W + "tc"))
                    zeilen.append(f"<tr>{zellen}</tr>")
                teile.append("<table border='1' cellspacing='0' cellpadding='4'>" + "".join(zeilen) + "</table>")
        rand = []
        for name in sorted(n for n in z.namelist() if re.match(r"word/(header|footer)\d*\.xml$", n)):
            x = _xml(z, name)
            t = " ".join(_w_text(p) for p in x.iter(W + "p")).strip() if x is not None else ""
            if t:
                rand.append(html.escape(t))
        if rand:
            teile.append("<hr><p style='color:#666'>Kopf-/Fußzeile: " + " · ".join(dict.fromkeys(rand)) + "</p>")
    return "".join(teile)


def docx_text(pfad):
    """Reiner Text eines Word-Dokuments (.docx) für Auswertungen: Absätze je Zeile, Tabellenzeilen mit Tabulator
    zwischen den Zellen, dann Kopf-/Fußzeilen."""
    with zipfile.ZipFile(pfad) as z:
        doc = _xml(z, "word/document.xml")
        if doc is None:
            raise ValueError("kein Word-Dokument (.docx)")
        body = doc.find(W + "body")
        zeilen = []
        for el in list(body) if body is not None else []:
            if el.tag == W + "p":
                zeilen.append(_w_text(el))
            elif el.tag == W + "tbl":
                for tr in el.iter(W + "tr"):
                    zeilen.append("\t".join(" ".join(_w_text(p) for p in tc.iter(W + "p")).strip()
                                             for tc in tr.findall(W + "tc")))
        for name in sorted(n for n in z.namelist() if re.match(r"word/(header|footer)\d*\.xml$", n)):
            x = _xml(z, name)
            zeilen += [_w_text(p) for p in x.iter(W + "p")] if x is not None else []
    return "\n".join(zeilen).strip()


# ------------------------------------------------------------------ Excel (.xlsx)
def _spalte(ref):
    n = 0
    for c in re.match(r"[A-Z]+", ref or "A").group(0):
        n = n * 26 + ord(c) - 64
    return n - 1


def _zahl_text(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return v
    if f == int(f) and abs(f) < 1e15:
        return str(int(f))
    return f"{f:.6g}".replace(".", ",")


def xlsx_blaetter(pfad, zeilen_max=ZEILEN_MAX, spalten_max=SPALTEN_MAX):
    """Blätter einer Excel-Datei: [(Name, [[Zelltext, …], …])] mit den zuletzt gespeicherten Werten (Formeln nicht
    neu gerechnet). Ohne Excel, Makros laufen nie."""
    with zipfile.ZipFile(pfad) as z:
        mappe = _xml(z, "xl/workbook.xml")
        if mappe is None:
            raise ValueError("keine Excel-Datei (.xlsx)")
        rel = _xml(z, "xl/_rels/workbook.xml.rels")
        ziel = {r.get("Id"): r.get("Target") for r in (rel if rel is not None else [])}
        texte = []
        sst = _xml(z, "xl/sharedStrings.xml")
        for si in (sst if sst is not None else []):
            texte.append("".join(t.text or "" for t in si.iter(S + "t")))
        out = []
        for blatt in mappe.iter(S + "sheet"):
            t = ziel.get(blatt.get(R + "id"), "")
            name = t.lstrip("/") if t.startswith("/") else "xl/" + t.replace("../", "")
            x = _xml(z, name)
            zeilen = []
            for row in (x.iter(S + "row") if x is not None else []):
                if len(zeilen) >= zeilen_max:
                    break
                r = int(row.get("r") or len(zeilen) + 1) - 1
                while len(zeilen) < r and len(zeilen) < zeilen_max:
                    zeilen.append([])
                werte = []
                for c in row.findall(S + "c"):
                    i = _spalte(c.get("r"))
                    if i >= spalten_max:
                        continue
                    typ, v = c.get("t"), c.find(S + "v")
                    if typ == "s" and v is not None:
                        w = texte[int(v.text)] if v.text and int(v.text) < len(texte) else ""
                    elif typ == "inlineStr":
                        w = "".join(t.text or "" for t in c.iter(S + "t"))
                    elif typ in ("str", "e"):
                        w = v.text if v is not None else ""
                    elif typ == "b":
                        w = "WAHR" if v is not None and v.text == "1" else "FALSCH"
                    else:
                        w = _zahl_text(v.text) if v is not None and v.text is not None else ""
                    werte += [""] * (i - len(werte))
                    werte.append(w or "")
                zeilen.append(werte)
            while zeilen and not any(zeilen[-1]):
                zeilen.pop()
            out.append((blatt.get("name") or f"Blatt {len(out) + 1}", zeilen))
    return out


# ------------------------------------------------------------------ DXF
def dxf_elemente(pfad):
    """Linien, Kreise und Texte einer DXF in mm: dict(strecken=[(p, q, bulge)], kreise=[(c, r)],
    texte=[(p, h, winkel, text)], box=(x0, y0, x1, y1) oder None)."""
    from . import dxf_import as di
    roh = di.roh_lesen(text_lesen(pfad, 200_000_000))
    st, kr, tx = [], [], []
    for el in di.elemente(roh):
        if el[0] == "S":
            st.append((el[2], el[3], el[4] or 0.0))
        elif el[0] == "K":
            kr.append((el[2], el[3]))
        elif el[0] == "T":
            tx.append((el[2], el[3] or 2.5, el[4] or 0.0, di.text_klar(str(el[5]))))
    xs = [p[0] for a, b, _ in st for p in (a, b)] + [c[0] + s * r for c, r in kr for s in (-1, 1)] \
        + [p[0] for p, *_ in tx]
    ys = [p[1] for a, b, _ in st for p in (a, b)] + [c[1] + s * r for c, r in kr for s in (-1, 1)] \
        + [p[1] for p, *_ in tx]
    box = (min(xs), min(ys), max(xs), max(ys)) if xs else None
    return dict(strecken=st, kreise=kr, texte=tx, box=box)


# ------------------------------------------------------------------ STEP
def netz_vereint(netze):
    """Mehrere Körper-Netze (dict mit p, t, lage) zu einem Netz in der Lage der Datei (für die 3D-Vorschau)."""
    from .baugruppe_step import netz_in_lage
    p, t = [], {}
    for n in netze:
        if not n or not n.get("p"):
            continue
        lage = n.get("lage")
        pts = netz_in_lage(n, lage) if lage and len(lage) == 9 else list(n["p"])
        basis = len(p) // 3
        p += pts
        for a, idx in (n.get("t") or {}).items():
            t.setdefault(a, []).extend(i + basis for i in idx)
    return dict(p=p, t=t) if p else None


def step_messen(befehl, pfad, zeitlimit=STEP_ZEITLIMIT_S, args=None):
    """Im Hintergrund: STEP-Datei messen und ihre Körper als ein Netz. args: Messargumente wie beim Kalkulieren
    (anfrage_vorab.vorschau_argumente, mit Zwischenspeicher: vorgemessen = sofort da); ohne: ein Prozess, ohne
    Zwischenspeicher. Ergebnis: (Netz oder None, Text)."""
    if not befehl:
        return None, "Für die 3D-Vorschau fehlt der STEP-Import."
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        liste, ausgabe, netze = tmp / "liste.txt", tmp / "messwerte.txt", tmp / "netze"
        liste.write_text(str(pfad), encoding="utf-8")
        try:
            subprocess.run(list(befehl) + ["--liste", str(liste), "--ausgabe", str(ausgabe), "--netze", str(netze)]
                           + (list(args) if args else ["--prozesse", "1"]),
                           capture_output=True, timeout=zeitlimit,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except (OSError, subprocess.SubprocessError) as e:
            return None, f"3D-Vorschau nicht möglich: {e}"
        teile = []
        for f in sorted(netze.glob("*.json")) if netze.is_dir() else []:
            try:
                teile.append(json.loads(f.read_text(encoding="utf-8")))
            except (OSError, ValueError):
                continue
        netz = netz_vereint(teile)
        if netz is None:
            return None, "3D-Vorschau nicht möglich: die Datei enthält keine lesbaren Körper."
        return netz, f"{len(teile)} Körper"


# ------------------------------------------------------------------ Fenster
class Zeichenflaeche(QtWidgets.QWidget):
    """DXF: Linien, Bögen, Kreise, Texte; Mausrad zoomt, Ziehen verschiebt, Doppelklick = alles zeigen."""

    def __init__(self, daten):
        super().__init__()
        self.d, self.zoom, self.ver, self._von = daten, 1.0, QtCore.QPointF(0, 0), None
        self.setMinimumSize(300, 200)
        self.setStyleSheet("background: white;")

    def _trafo(self):
        x0, y0, x1, y1 = self.d["box"]
        b, h = max(x1 - x0, 1e-6), max(y1 - y0, 1e-6)
        s = min((self.width() - 20) / b, (self.height() - 20) / h) * self.zoom
        ox = self.width() / 2 - (x0 + b / 2) * s + self.ver.x()
        oy = self.height() / 2 + (y0 + h / 2) * s + self.ver.y()
        return s, ox, oy

    def paintEvent(self, _e):
        from . import schneidweg as sw
        g = QtGui.QPainter(self)
        g.fillRect(self.rect(), QtGui.QColor("white"))  # fest: Zeichnung wie Papier (wie die PDF-Seiten)
        if not self.d.get("box"):
            g.drawText(self.rect(), Qt.AlignCenter, "Die Zeichnung ist leer.")
            return
        g.setRenderHint(QtGui.QPainter.Antialiasing)
        s, ox, oy = self._trafo()

        def pt(p):
            return QtCore.QPointF(ox + p[0] * s, oy - p[1] * s)
        g.setPen(QtGui.QPen(QtGui.QColor("#1F2937"), 1.0))  # fest: Papier
        for p, q, b in self.d["strecken"]:
            zug = [p] + sw.bogen_punkte(p, q, b) if b else [p, q]
            g.drawPolyline(QtGui.QPolygonF([pt(a) for a in zug]))
        for c, r in self.d["kreise"]:
            g.drawEllipse(pt(c), r * s, r * s)
        g.setPen(QtGui.QColor("#2B5DA8"))  # fest: Papier
        for p, h, w, t in self.d["texte"]:
            if h * s < 3:
                continue
            f = g.font()
            f.setPixelSize(max(3, int(h * s)))
            g.setFont(f)
            g.save()
            g.translate(pt(p))
            g.rotate(-w)
            for i, zeile in enumerate(str(t).split("\n")):
                g.drawText(QtCore.QPointF(0, i * h * s * 1.4), zeile)
            g.restore()

    def wheelEvent(self, e):
        f = 1.25 if e.angleDelta().y() > 0 else 0.8
        self.zoom = min(max(self.zoom * f, 0.05), 200.0)
        self.update()

    def mousePressEvent(self, e):
        self._von = e.position()

    def mouseMoveEvent(self, e):
        if self._von is not None:
            self.ver += e.position() - self._von
            self._von = e.position()
            self.update()

    def mouseReleaseEvent(self, _e):
        self._von = None

    def mouseDoubleClickEvent(self, _e):
        self.zoom, self.ver = 1.0, QtCore.QPointF(0, 0)
        self.update()

class AnhangVorschau(QtWidgets.QDialog):
    """Vorschau-Fenster. eintraege: [dict(name, pfad, hinweis="")]; extern(pfad): Datei mit ihrem Programm
    öffnen; mess_befehl: Befehl der STEP-Messung (step.messprogramm) oder None; mess_args: Messargumente
    (anfrage_vorab.vorschau_argumente)."""

    def __init__(self, parent, eintraege, index=0, extern=None, mess_befehl=None, mess_args=None):
        super().__init__(parent)
        self.setWindowFlag(Qt.WindowMaximizeButtonHint, True)
        self.setAttribute(Qt.WA_DeleteOnClose, False)
        self.eintraege, self.extern, self.mess_befehl = list(eintraege), extern, mess_befehl
        self.mess_args = list(mess_args) if mess_args else None
        self.i, self.zoom, self._tmp, self._pool, self._lauf = 0, 1.0, None, None, None
        self.inhalt_art = ""
        lay = QtWidgets.QVBoxLayout(self)
        oben = QtWidgets.QHBoxLayout()
        self.zurueck = QtWidgets.QPushButton("◀")
        self.vor = QtWidgets.QPushButton("▶")
        for k, tipp in ((self.zurueck, "Voriger Anhang (Bild auf, Alt+←)"),
                        (self.vor, "Nächster Anhang (Bild ab, Alt+→)")):
            k.setToolTip(tipp)
            k.setFixedWidth(36)
        self.zurueck.clicked.connect(lambda: self.zeigen(self.i - 1))
        self.vor.clicked.connect(lambda: self.zeigen(self.i + 1))
        self.titel = QtWidgets.QLabel()
        self.titel.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.k_klein = QtWidgets.QPushButton("−")
        self.k_gross = QtWidgets.QPushButton("+")
        for k, f, tipp in ((self.k_klein, 0.8, "Verkleinern (Strg+−)"), (self.k_gross, 1.25, "Vergrößern (Strg++)")):
            k.setFixedWidth(32)
            k.setToolTip(tipp)
            k.clicked.connect(lambda _=False, f=f: self.zoomen(f))
        self.k_extern = QtWidgets.QPushButton("Extern öffnen")
        self.k_extern.setToolTip("Datei mit dem Programm öffnen, das Windows dafür vorsieht")
        self.k_extern.clicked.connect(self.extern_oeffnen)
        for w in (self.zurueck, self.vor):
            oben.addWidget(w)
        oben.addWidget(self.titel, 1)
        for w in (self.k_klein, self.k_gross, self.k_extern):
            oben.addWidget(w)
        lay.addLayout(oben)
        self.hinweis = QtWidgets.QLabel()
        self.hinweis.setWordWrap(True)
        self.hinweis.setStyleSheet("color: #8A5A00;")
        lay.addWidget(self.hinweis)
        self.flaeche = QtWidgets.QStackedLayout()
        halter = QtWidgets.QWidget()
        halter.setLayout(self.flaeche)
        lay.addWidget(halter, 1)
        for taste, d in ((QtGui.QKeySequence.MoveToPreviousPage, -1), (QtGui.QKeySequence.MoveToNextPage, 1),
                         ("Alt+Left", -1), ("Alt+Right", 1)):
            QtGui.QShortcut(QtGui.QKeySequence(taste), self, activated=lambda d=d: self.zeigen(self.i + d))
        QtGui.QShortcut(QtGui.QKeySequence.ZoomIn, self, activated=lambda: self.zoomen(1.25))
        QtGui.QShortcut(QtGui.QKeySequence.ZoomOut, self, activated=lambda: self.zoomen(0.8))
        self._warten = QtCore.QTimer(self)
        self._warten.setInterval(300)
        self._warten.timeout.connect(self._step_pruefen)
        self.resize(1000, 900)
        self.zeigen(index)

    # ---------------------------------------------------------- Anzeige
    @property
    def eintrag(self):
        return self.eintraege[self.i] if self.eintraege else None

    def zeigen(self, i):
        if not self.eintraege:
            return
        self.i = max(0, min(i, len(self.eintraege) - 1))
        self.zoom = 1.0
        self._aufbauen()

    def zoomen(self, f):
        if self.inhalt_art in ("pdf", "bild", "word", "excel", "mail", "text"):
            self.zoom = min(max(self.zoom * f, 0.25), 6.0)
            self._aufbauen()
        elif self.inhalt_art == "dxf":
            w = self.flaeche.currentWidget()
            w.zoom *= f
            w.update()

    def _setzen(self, w):
        while self.flaeche.count():
            alt = self.flaeche.widget(0)
            self.flaeche.removeWidget(alt)
            alt.deleteLater()
        self.flaeche.addWidget(w)
        self.flaeche.setCurrentWidget(w)

    def _aufbauen(self):
        e = self.eintrag
        pfad = Path(e["pfad"])
        a = art(pfad)
        self.inhalt_art = a
        n = len(self.eintraege)
        self.setWindowTitle(f"Vorschau: {e['name']}")
        self.titel.setText(f"<b>{html.escape(e['name'])}</b> · {ART_TEXT[a]}"
                           + (f" · {self.i + 1} von {n}" if n > 1 else ""))
        self.zurueck.setEnabled(self.i > 0)
        self.vor.setEnabled(self.i < n - 1)
        self.k_klein.setEnabled(a in ("pdf", "bild", "word", "excel", "mail", "text", "dxf"))
        self.k_gross.setEnabled(self.k_klein.isEnabled())
        self.hinweis.setText(e.get("hinweis") or "")
        self.hinweis.setVisible(bool(e.get("hinweis")))
        self._warten.stop()
        try:
            w = getattr(self, "_w_" + a)(pfad)
        except Exception as x:          # noqa: BLE001 – kaputte Datei: Hinweis statt Absturz
            w = self._meldung(f"Keine Vorschau möglich: {x}")
        self._setzen(w)

    def _meldung(self, text):
        w = QtWidgets.QWidget()
        v = QtWidgets.QVBoxLayout(w)
        v.addStretch(1)
        lab = QtWidgets.QLabel(text)
        lab.setAlignment(Qt.AlignCenter)
        lab.setWordWrap(True)
        v.addWidget(lab)
        w.text_feld = lab
        k = QtWidgets.QPushButton("Extern öffnen")
        k.clicked.connect(self.extern_oeffnen)
        v.addWidget(k, 0, Qt.AlignCenter)
        v.addStretch(1)
        w.meldung = text
        return w

    def _rollen(self, inneres):
        r = QtWidgets.QScrollArea()
        r.setWidget(inneres)
        r.setWidgetResizable(True)
        r.setStyleSheet("QScrollArea { background: #E3E7EC; }")
        return r

    def _bilder(self, bilder):
        flaeche = QtWidgets.QWidget()
        spalte = QtWidgets.QVBoxLayout(flaeche)
        spalte.setSpacing(14)
        for k, bild in enumerate(bilder, start=1):
            lab = QtWidgets.QLabel()
            lab.setPixmap(QtGui.QPixmap.fromImage(bild))
            lab.setStyleSheet("border: 1px solid #C5CCD6; background: white;")
            lab.setToolTip(f"Seite {k} von {len(bilder)}")
            spalte.addWidget(lab, 0, Qt.AlignHCenter)
        w = self._rollen(flaeche)
        w.seiten = len(bilder)
        return w

    def _w_pdf(self, pfad):
        from .pdf_vorschau import seiten_bilder
        bilder = seiten_bilder(pfad, int(860 * self.zoom))
        if not bilder:
            return self._meldung("Das PDF lässt sich nicht lesen.")
        return self._bilder(bilder)

    def _w_bild(self, pfad):
        leser = QtGui.QImageReader(str(pfad))
        leser.setAutoTransform(True)
        bilder = []
        for _k in range(max(1, leser.imageCount())):
            b = leser.read()
            if b.isNull():
                break
            if self.zoom != 1.0 or b.width() > 1600:
                breite = int(min(b.width(), 1600) * self.zoom)
                b = b.scaledToWidth(max(50, breite), Qt.SmoothTransformation)
            bilder.append(b)
            if not leser.jumpToNextImage():
                break
        if not bilder:
            return self._meldung(f"Das Bild lässt sich nicht lesen ({leser.errorString()}).")
        return self._bilder(bilder)

    def _browser(self, inhalt, html_=True):
        b = QtWidgets.QTextBrowser()
        b.setOpenLinks(False)
        b.setOpenExternalLinks(False)
        if html_:
            b.setHtml(inhalt)
        else:
            b.setPlainText(inhalt)
        if self.zoom != 1.0:
            b.zoomIn(round((self.zoom - 1) * 8))
        return b

    def _w_text(self, pfad):
        b = self._browser(text_lesen(pfad), html_=False)
        b.setLineWrapMode(QtWidgets.QTextEdit.NoWrap)
        return b

    def _w_word(self, pfad):
        return self._browser("<div style='font-family:Calibri,Arial;'>" + docx_html(pfad) + "</div>")

    def _w_excel(self, pfad):
        reiter = QtWidgets.QTabWidget()
        for name, zeilen in xlsx_blaetter(pfad):
            t = QtWidgets.QTableWidget(len(zeilen), max([len(z) for z in zeilen] + [1]))
            t.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
            t.setHorizontalHeaderLabels([_spaltenname(k) for k in range(t.columnCount())])
            for r, z in enumerate(zeilen):
                for c, wert in enumerate(z):
                    if wert:
                        t.setItem(r, c, QtWidgets.QTableWidgetItem(str(wert)))
            if self.zoom != 1.0:
                f = t.font()
                f.setPointSizeF(max(5.0, f.pointSizeF() * self.zoom))
                t.setFont(f)
            t.resizeColumnsToContents()
            reiter.addTab(t, name)
        return reiter if reiter.count() else self._meldung("Die Excel-Datei ist leer.")

    def _w_mail(self, pfad):
        from . import mail
        m = mail.lesen(pfad)
        if m is None:
            return self._meldung("Die Mail lässt sich nicht lesen.")
        kopf = [f"<b>Von:</b> {html.escape(m.absender_name)} &lt;{html.escape(m.absender)}&gt;",
                f"<b>Datum:</b> {m.datum:%d.%m.%Y %H:%M}" if m.datum else "",
                f"<b>Betreff:</b> {html.escape(m.betreff)}"]
        from . import anfragen_akten as ak
        links = "".join(f"<li>{html.escape(n)} ({len(d) // 1024 + 1} KB, ausführbar, wird nicht geöffnet)</li>"
                        if Path(str(n)).suffix.lower() in ak.GEFAEHRLICH else
                        f"<li><a href='anhang:{k}'>{html.escape(n)}</a> ({len(d) // 1024 + 1} KB)</li>"
                        for k, (n, d) in enumerate(m.anhaenge))
        text = html.escape(m.text).replace("\n", "<br>")
        b = self._browser("<br>".join(x for x in kopf if x)
                          + (f"<p><b>Anhänge</b> (anklicken für die Vorschau):</p><ul>{links}</ul>" if links else "")
                          + f"<hr><div>{text}</div>")
        b.anhaenge = m.anhaenge
        b.anchorClicked.connect(lambda url, m=m: self.mail_anhang(m, int(url.toString().split(":")[1])))
        return b

    def mail_anhang(self, m, k):
        """Anhang einer Mail in der Vorschau zeigen (ausführbare Dateien nie)."""
        from . import anfragen_akten as ak
        name, daten = m.anhaenge[k]
        name = Path(str(name)).name or f"Anhang_{k + 1}"
        if Path(name).suffix.lower() in ak.GEFAEHRLICH:
            self.hinweis.setText(f"{name}: ausführbare Datei, wird aus Sicherheitsgründen nicht geöffnet.")
            self.hinweis.setVisible(True)
            return None
        if self._tmp is None:
            self._tmp = tempfile.TemporaryDirectory(prefix="vorschau_")
        ziel = Path(self._tmp.name) / f"{k}_{name}"
        ziel.write_bytes(daten)
        neu = dict(name=f"{name} (aus {self.eintrag['name']})", pfad=ziel)
        self.eintraege.insert(self.i + 1, neu)
        self.zeigen(self.i + 1)
        return ziel

    def _w_dxf(self, pfad):
        d = dxf_elemente(pfad)
        w = Zeichenflaeche(d)
        w.setToolTip("Mausrad: Zoom · Ziehen: verschieben · Doppelklick: ganze Zeichnung")
        w.zoom = self.zoom
        return w

    def _w_step(self, pfad):
        from concurrent.futures import ThreadPoolExecutor
        w = self._meldung("3D wird berechnet …")
        # V3 3D-Visualisierung: Fortschritt statt stillem Warten (Laufbalken, verstrichene Zeit); das Fenster bleibt
        # bedienbar, die Messung läuft in einem eigenen Prozess
        balken = QtWidgets.QProgressBar()
        balken.setRange(0, 0)
        balken.setMaximumWidth(320)
        balken.setTextVisible(False)
        w.layout().insertWidget(2, balken, 0, Qt.AlignCenter)
        w.balken, self._start = balken, time.monotonic()
        self._pool = self._pool or ThreadPoolExecutor(max_workers=1)
        self._lauf = (self._pool.submit(step_messen, self.mess_befehl, pfad, STEP_ZEITLIMIT_S, self.mess_args), self.i)
        self._warten.start()
        return w

    def _step_pruefen(self):
        if self._lauf is not None and not self._lauf[0].done():
            feld = getattr(self.flaeche.currentWidget(), "text_feld", None)
            if feld is not None:
                s = int(time.monotonic() - getattr(self, "_start", time.monotonic()))
                feld.setText(f"3D wird berechnet … {s} s\n(STEP wird gemessen: Flächen, Konturen, Netz; höchstens "
                             f"{STEP_ZEITLIMIT_S // 60} min. Das Fenster bleibt bedienbar.)")
            return
        if self._lauf is None:
            return
        f, i = self._lauf
        self._lauf = None
        self._warten.stop()
        if i != self.i:                 # inzwischen anderer Anhang gewählt
            return
        try:
            netz, text = f.result()
        except Exception as x:          # noqa: BLE001
            netz, text = None, str(x)
        if netz is None:
            self._setzen(self._meldung(text))
            return
        from .ansicht3d import Ansicht3D
        a = Ansicht3D()
        a.setzen(netz, self.eintrag["name"])
        a.koerper_text = text
        self._setzen(a)

    def step_warten(self, s=STEP_ZEITLIMIT_S):
        """Tests: bis die 3D-Vorschau fertig ist."""
        if self._lauf is not None:
            self._lauf[0].result(timeout=s)
            self._step_pruefen()

    def _w_keine(self, pfad):
        e = pfad.suffix.lower()
        alt = {".doc": "Word (altes Format .doc)", ".xls": "Excel (altes Format .xls)"}.get(e)
        return self._meldung(f"Für {alt or 'diese Datei'} gibt es keine Vorschau im Programm."
                             + (" Speichert der Kunde als .docx/.xlsx, klappt sie." if alt else ""))

    def extern_oeffnen(self):
        if self.extern and self.eintrag:
            self.extern(self.eintrag["pfad"])

    def closeEvent(self, e):
        self._warten.stop()
        super().closeEvent(e)

def _spaltenname(k):
    s = ""
    k += 1
    while k:
        k, r = divmod(k - 1, 26)
        s = chr(65 + r) + s
    return s


def fenster(parent, eintraege, index=0, extern=None, mess_befehl=None, mess_args=None):
    """Vorschau-Fenster anlegen (nicht modal, bleibt offen). Ergebnis: das Fenster."""
    return AnhangVorschau(parent, eintraege, index, extern, mess_befehl, mess_args)
