"""Scans lesen (Plan W6c, Patrick 25.10.2026: Tesseract, mitgeliefert): Anfrageformulare ohne Text (gescanntes PDF,
Foto als JPG/PNG/TIFF) werden Seite für Seite als Bild an Tesseract gegeben (Deutsch + Englisch); der Text geht danach
durch dieselbe Auswertung wie ein PDF mit Text (formular.py). Wörter, die Tesseract nur unsicher erkennt, kommen in
eine eigene Menge: eine Stückzahl daraus gilt als unsicher (gelb im Prüfdialog).

Tesseract liegt im Windows-Paket im Ordner TESSERACT_ORDNER neben der .exe (Build: .github/workflows/paket.yml), beim
Entwickeln reicht ein installiertes tesseract im Suchpfad. Fehlt es, liefert lesen() None (Formular bleibt ungelesen).
Bilder gehen über stdin an Tesseract (keine Probleme mit Umlauten im Pfad). Ohne Qt."""
import io
import os
import shutil
import subprocess
from pathlib import Path

TESSERACT_ORDNER = "Tesseract-OCR"
SPRACHEN = "deu+eng"
DPI = 300                   # PDF-Seiten werden so gerendert
MAX_PIXEL = 4200            # längste Seite höchstens (A4 mit 300 dpi: 3508)
MIN_BREITE = 2000           # kleinere Bilder (Handyfoto, Fax) werden vergrößert
UNSICHER_UNTER = 70         # Erkennungssicherheit (0–100) darunter: Wort unsicher
ZEIT_S = 60                 # je Seite
BILD = {".jpg", ".jpeg", ".png", ".tif", ".tiff"}


def programm(programmordner=None):
    """Pfad zu tesseract(.exe): mitgeliefert im Programmordner, sonst aus dem Suchpfad; None = nicht vorhanden."""
    if programmordner:
        for name in ("tesseract.exe", "tesseract"):
            exe = Path(programmordner) / TESSERACT_ORDNER / name
            if exe.is_file():
                return str(exe)
    return shutil.which("tesseract")


def seiten(pfad):
    """Seiten als Graustufenbilder (PIL): PDF mit DPI gerendert, Bilddatei je Seite (mehrseitiges TIFF)."""
    from PIL import Image, ImageFilter, ImageSequence
    pfad = Path(pfad)
    out = []
    if pfad.suffix.lower() == ".pdf":
        import pypdfium2 as pdfium
        pdf = pdfium.PdfDocument(str(pfad))
        try:
            for i in range(len(pdf)):
                seite = pdf[i]
                gross = max(seite.get_size()) or 1          # Punkte (1/72 Zoll); Plan A0 nicht riesig rendern
                out.append(seite.render(scale=min(DPI / 72, MAX_PIXEL / gross)).to_pil().convert("L"))
        finally:
            pdf.close()
    else:
        with Image.open(pfad) as bild:
            for s in ImageSequence.Iterator(bild):
                out.append(s.convert("L"))
    for i, b in enumerate(out):
        if b.width < MIN_BREITE:
            f = MIN_BREITE / b.width
            b = b.resize((MIN_BREITE, round(b.height * f)), Image.LANCZOS)
        out[i] = b.filter(ImageFilter.MedianFilter(3))      # Punkte von Fax und Scanner weg, Schrift bleibt
    return out


def _tsv_text(tsv):
    """Tesseract-TSV in (Text mit einer Zeile je erkannter Zeile, unsichere Wörter)."""
    zeilen, unsicher = {}, set()
    for z in tsv.splitlines()[1:]:
        t = z.split("\t")
        if len(t) < 12 or not t[11].strip():
            continue
        try:
            conf = float(t[10])
        except ValueError:
            continue
        zeilen.setdefault((int(t[1]), int(t[2]), int(t[3]), int(t[4])), []).append(t[11])
        if 0 <= conf < UNSICHER_UNTER:
            unsicher.add(t[11].strip())
    return "\n".join(" ".join(w) for _, w in sorted(zeilen.items())), unsicher


def bild_lesen(bild, exe, zeit=ZEIT_S):
    """Ein Bild (PIL) mit Tesseract lesen: (Text, unsichere Wörter). OSError/subprocess-Fehler gehen durch."""
    puffer = io.BytesIO()
    bild.save(puffer, format="PNG")
    umgebung = dict(os.environ)
    if Path(exe).parent.name == TESSERACT_ORDNER:   # mitgeliefert: Sprachdaten in tessdata daneben (Vorgabe von
        umgebung.pop("TESSDATA_PREFIX", None)        # Tesseract), nie die einer anderen Installation
    erg = subprocess.run([exe, "stdin", "stdout", "-l", SPRACHEN, "--psm", "6", "tsv"], input=puffer.getvalue(),
                         capture_output=True, timeout=zeit, check=True, env=umgebung,
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return _tsv_text(erg.stdout.decode("utf-8", errors="replace"))


def lesen(pfad, programmordner=None):
    """Formular (Scan-PDF oder Bild) lesen: dict(text, unsicher) oder None (kein Tesseract, Datei nicht lesbar)."""
    exe = programm(programmordner)
    if not exe:
        return None
    try:
        texte, unsicher = [], set()
        for b in seiten(pfad):
            t, u = bild_lesen(b, exe)
            texte.append(t)
            unsicher |= u
    except Exception:           # kaputtes Bild, Tesseract abgestürzt oder zu langsam: wie ohne Formular
        return None
    return dict(text="\n".join(texte), unsicher=unsicher)
