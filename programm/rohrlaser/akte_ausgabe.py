"""Angebotsakte im Angebot (Patrick 18.11.2026): Funktion „Angebotsdokument erstellen“ für die Angebotsseite.

AkteMixin wird von angebot_fenster.AngebotSeite geerbt und nutzt deren Attribute (db, kopf, positionen, ergebnis, k,
tabellen, einst, f). Eine Kalkulation (self._rechnung) für alle Seiten und Dokumente; die 3D-Bilder zeichnet der
Zeichner des 3D-Viewers (ansicht3d.vorschaubild) aus dem gespeicherten Netz der Position, ohne Netz aus dem Rohrmodell
des Editors (rohr3d). Ablage und Versionen: akte_ablage.py."""
import shutil
import tempfile
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, Qt
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

from . import akte_ablage, akte_pdf, angebotsakte, protokoll, rechnen
from .angebot import kein_laserteil
from .klartext import fehler_text

BILD_PX = (512, 352)        # 64 × 44 mm bei rund 200 dpi


def _png(pix):
    daten = QByteArray()
    puffer = QBuffer(daten)
    puffer.open(QIODevice.WriteOnly)
    pix.save(puffer, "PNG")
    puffer.close()
    return bytes(daten)


class AkteMixin:
    # ------------------------------------------------------------------ Daten
    def akte_bilder(self):
        """{Positions-ID: PNG} der 3D-Ansicht je Position (schräg von vorn oben wie die Vorschau im Viewer)."""
        from .ansicht3d import entpacken, vorschaubild
        try:
            netze = self.db.netze(self.id)
        except Exception:       # noqa: BLE001
            netze = {}
        out = {}
        profil_von = None
        for p in self.positionen:
            if not p:
                continue
            netz = None
            roh = netze.get(p.get("id"))
            try:
                netz = entpacken(roh) if roh else None
            except Exception:       # noqa: BLE001
                netz = None
            if netz is None and not kein_laserteil(p) and p.get("profil_id") and rechnen._n(p.get("laenge")) > 0:
                try:        # ohne STEP: Rohrmodell wie im 3D-Editor
                    from . import rohr3d, schneidweg, stangen_abwicklung
                    if profil_von is None:
                        profil_von = stangen_abwicklung.profil_funktion(self.kopf, self.k)
                    netz = rohr3d.netz(schneidweg.lesen(p.get("technik")), profil_von(p), rechnen._n(p.get("laenge")))
                except Exception:       # noqa: BLE001 – dann ohne Bild
                    netz = None
            if not netz:
                continue
            try:
                pix = vorschaubild(netz, BILD_PX[0] // 2, BILD_PX[1] // 2, 2.0)
            except Exception:       # noqa: BLE001
                pix = None
            if pix is not None:
                out[p.get("id")] = _png(pix)
        return out

    def akte_sammeln(self, bilder=True):
        """Akte aus einer Kalkulation des Angebots (dieselbe Kopie für alle Seiten). None = abgebrochen."""
        if not self._vor_ausgabe():
            return None
        zeilen, summen = self._rechnung()
        ang = self.angebot_daten(zeilen=zeilen)
        if ang is None:
            return None
        from . import bearbeitung, teilen
        bearb = []
        for p, z in zip(self.positionen, zeilen):
            try:
                bearb.append((p.get("pos"), bearbeitung.fuer_position(p, z, self.kopf, self.k, self.tabellen)))
            except Exception:       # noqa: BLE001 – nie am PDF scheitern
                protokoll.warnung("Angebotsakte: Bearbeitungsliste einer Position übersprungen")
        name = ""
        try:
            if self.kopf.get("bearbeiter"):
                name = (teilen.mitarbeiter(self.db, self.kopf["bearbeiter"]) or {}).get("name") or ""
        except Exception:       # noqa: BLE001
            name = ""
        name = name or self.db.einstellung("benutzer_name") or ""
        return angebotsakte.sammeln(self.kopf, self.positionen, self.ergebnis, self.k, self.tabellen, self.einst,
                                    zeilen, summen, ang, bilder=self.akte_bilder() if bilder else None,
                                    bearbeitungen=bearb, aktuell=self.stand_optimierung() == "aktuell",
                                    bearbeiter=name)

    def akte_ordner(self):
        return self.f.angebot_ordner(self.kopf)

    # ------------------------------------------------------------------ Erstellen
    def angebotsdokument(self, dialog=None, art=None, seiten=None, vorschau=None, oeffnen=True):
        """Menü „Angebotsdokument erstellen …“: Fenster mit Auswahl, dann erzeugen, Vorschau, ablegen.
        dialog(d) bedient das Fenster statt exec (Tests); art/seiten ohne Fenster. Ergebnis: Bericht von
        akte_ablage.ablegen oder None."""
        if not self.nummer_endgueltig("Angebotsdokument"):
            return None
        akte = self.akte_sammeln()
        if akte is None:
            return None
        if art is None:
            from .akte_dialog import AkteDialog, stand_text
            try:
                o = self.akte_ordner()
                text = stand_text(akte_ablage.letzte(o), akte_ablage.stand(o, akte["fingerabdruck"]))
            except OSError:
                text = ""
            d = AkteDialog(self, akte, text, vorschau=self.db.einstellung("pdf_vorschau") != "nein")
            if dialog:
                if not dialog(d):
                    return None
            elif d.exec() != QDialog.Accepted:
                return None
            art, seiten, vorschau = d.art, d.seiten, d.vorschau.isChecked()
        return self.akte_erzeugen(akte, art, seiten, vorschau=bool(vorschau), oeffnen=oeffnen)

    def akte_erzeugen(self, akte, art="gesamt", seiten=None, vorschau=False, oeffnen=False, still=False,
                      vorschau_dialog=None):
        """Dokument(e) der Akte schreiben und ablegen. art gesamt: zusätzlich Kunde und Intern getrennt.
        vorschau: erst ansehen (Abbrechen = nichts gespeichert). still: nur Meldung, keine Fenster (automatische
        Erneuerung). Ergebnis: Bericht oder None."""
        zwischen = Path(tempfile.mkdtemp())
        try:
            try:
                o = self.akte_ordner()
                version = akte_ablage.naechste_version(akte_ablage.ordner(o))
            except OSError as e:
                if not still:
                    QMessageBox.warning(self, "Angebotsakte", f"Der Ordner des Angebots lässt sich nicht anlegen:\n"
                                                              f"{fehler_text(e)}")
                return None
            QApplication.setOverrideCursor(Qt.WaitCursor)
            try:
                dokumente, gesetzt = {}, {}
                arten = [art] + ([a for a in ("kunde", "intern", "technik") if a != art] if art == "gesamt" else [])
                for a in arten:
                    ziel = zwischen / akte_ablage.dateiname(akte["nummer"], angebotsakte.DATEI_ZUSATZ[a])
                    gesetzt[a] = akte_pdf.schreiben(ziel, akte, self.einst, a, seiten if a == art else None,
                                                    version=version)
                    dokumente[a] = ziel
                schnitt = None
                if (akte.get("schnitt") or {}).get("vorhanden"):
                    schnitt = zwischen / "schnitt.pdf"
                    akte_pdf.schreiben(schnitt, akte, self.einst, "intern", [3], version=version)
            except Exception as e:      # noqa: BLE001
                QApplication.restoreOverrideCursor()
                protokoll.warnung(f"Angebotsakte: PDF nicht erstellt ({type(e).__name__}: {e})")
                if not still:
                    QMessageBox.warning(self, "Angebotsakte", f"Das Dokument konnte nicht erstellt werden:\n"
                                                              f"{fehler_text(e)}")
                return None
            QApplication.restoreOverrideCursor()
            if "kunde" in dokumente:        # Schutztest: keine internen Werte im Kunden-PDF
                funde = akte_pdf.kunde_pruefen(dokumente["kunde"], erlaubt=self._akte_eigene_begriffe(akte))
                if funde:
                    text = ", ".join(sorted({b for _, b in funde}))
                    protokoll.warnung(f"Angebotsakte: interne Begriffe im Kunden-PDF ({text})")
                    if not still:
                        QMessageBox.warning(self, "Angebotsakte", "Das Kundenangebot enthält interne Begriffe "
                                                                  f"({text}) und wird nicht gespeichert.")
                    return None
            zeigen = dokumente[art]
            drucken = False
            if vorschau and not still and not self.f.stumm and QApplication.platformName() != "offscreen" \
                    or vorschau_dialog is not None:
                from . import pdf_vorschau
                d = pdf_vorschau.PdfVorschau(self, zeigen, f"{angebotsakte.ARTEN[art][0]} {akte['nummer']}")
                (vorschau_dialog(d) if vorschau_dialog else d.exec())
                if d.ergebnis == pdf_vorschau.ABBRECHEN:
                    self.f.meldung("Angebotsdokument: Vorschau abgebrochen, nichts gespeichert.")
                    return None
                drucken = d.ergebnis == pdf_vorschau.DRUCKEN
            bilder = {}
            for t in akte.get("technik") or ():
                if t.get("bild"):
                    from .teilebilder import dateiname as bildname
                    bilder[bildname(dict(pos=t["pos"], artikel=t["artikel"], bezeichnung=t["bezeichnung"]))] = t["bild"]
            eintrag = dict(erstellt=akte.get("erstellt"), bearbeiter=akte.get("bearbeiter"),
                           fingerabdruck=akte.get("fingerabdruck"), netto=(akte.get("kunde") or {}).get("netto"),
                           verkauf=(akte.get("gesamt") or {}).get("verkauf"), art=art,
                           seiten={a: s for a, s in gesetzt.items()},
                           pruefung=angebotsakte.schlimmste(akte.get("pruefung")))
            try:
                bericht = akte_ablage.ablegen(o, akte["nummer"], dokumente, angebotsakte.als_json(akte), bilder,
                                              schnitt, eintrag)
            except PermissionError:
                if not still:
                    QMessageBox.warning(self, "Angebotsakte", "Eine Datei der Akte ist noch in einem anderen Programm "
                                                              "geöffnet. Bitte schließen und erneut versuchen.")
                return None
            except OSError as e:
                if not still:
                    QMessageBox.warning(self, "Angebotsakte", f"Die Akte lässt sich nicht speichern:\n{fehler_text(e)}")
                return None
            pfad = bericht["dateien"][art]
            self.f.meldung(f"Angebotsakte Version {bericht['version']} gespeichert: {pfad}")
            if drucken:
                from . import pdf_vorschau
                pdf_vorschau.drucken(self, pfad, Path(pfad).stem)
            elif oeffnen and not still:
                self.f.datei_oeffnen(pfad)
            return bericht
        finally:
            shutil.rmtree(zwischen, ignore_errors=True)

    def _akte_eigene_begriffe(self, akte):
        """Begriffe des Schutztests, die schon in Texten des Benutzers stehen (Angebotstexte, Bezeichnungen): die
        dürfen im Kunden-PDF stehen, weil der Benutzer sie selbst geschrieben hat."""
        import json
        roh = json.dumps(dict(kunde=akte.get("kunde"), technik=[{k: v for k, v in t.items() if k != "bild"}
                                                                for t in akte.get("technik") or ()]),
                         ensure_ascii=False, default=str)
        roh += " ".join(" ".join(z for z in sp) for sp in akte_pdf.firmen_spalten(self.einst))
        return tuple(b for b in akte_pdf.INTERNE_BEGRIFFE if b in roh)

    def akte_automatisch(self):
        """Nach dem Angebots-PDF: Akte still erneuern, wenn sich die Kalkulation seit der letzten Akte geändert hat
        (Einstellung akte_automatisch, Vorgabe an). Nie am Angebots-PDF scheitern."""
        if self.db.einstellung("akte_automatisch") == "nein" or self.fremd():
            return None
        try:
            if not akte_ablage.letzte(self.akte_ordner()):
                return None             # nur eine vorhandene Akte erneuern, nie still eine neue anlegen
            akte = self.akte_sammeln()
            if akte is None:
                return None
            if akte_ablage.stand(self.akte_ordner(), akte["fingerabdruck"]) == akte_ablage.AKTUELL:
                return None
            return self.akte_erzeugen(akte, "gesamt", still=True)
        except Exception as e:      # noqa: BLE001
            protokoll.warnung(f"Angebotsakte automatisch: übersprungen ({type(e).__name__}: {e})")
            return None


# ------------------------------------------------------------------ Angebotsübersicht
def menue_fuellen(menue, f, kopf):
    """Untermenü „Angebotsakte“ der Angebotsübersicht für ein Angebot (kopf): öffnen, getrennt öffnen, drucken,
    neu erzeugen, Ordner. f = Hauptfenster."""
    try:
        o = akte_ablage._akte(f.angebot_ordner(kopf))
    except OSError:
        o = None
    e = akte_ablage.letzte(o) if o else None
    titel = "Angebotsakte"
    if e:
        zeit = str(e.get("gespeichert") or "")
        titel += f" (Version {e.get('version')} vom {akte_pdf.datum(zeit)})"
        if str(kopf.get("geaendert") or "") > zeit[:19]:
            titel += " – veraltet?"
    unter = menue.addMenu(titel)
    nummer = kopf.get("nummer") or ""
    for text, art in (("Komplettes Dokument öffnen", "gesamt"), ("Kundenangebot öffnen", "kunde"),
                      ("Interne Kalkulation öffnen", "intern"),
                      ("Technisches Kalkulationsblatt öffnen", "technik")):
        p = akte_ablage.datei(o, nummer, art) if o else None
        a = unter.addAction(text, lambda p=p: f.datei_oeffnen(p))
        a.setEnabled(p is not None)
    p = (akte_ablage.datei(o, nummer, "gesamt") or akte_ablage.datei(o, nummer, "kunde")) if o else None
    a = unter.addAction("Drucken …", lambda p=p: _drucken(f, p))
    a.setEnabled(p is not None)
    unter.addSeparator()
    unter.addAction("Erstellen / neu erzeugen …", lambda: _neu(f, kopf))
    a = unter.addAction("Ordner der Akte öffnen", lambda: f.datei_oeffnen(o))
    a.setEnabled(bool(o and o.exists()))
    return unter


def _drucken(f, pfad):
    from . import pdf_vorschau
    return pdf_vorschau.drucken(f, pfad, Path(pfad).stem) if pfad else False


def _neu(f, kopf):
    seite = f.angebot_oeffnen(kopf["id"])
    return seite.angebotsdokument() if seite is not None else None

