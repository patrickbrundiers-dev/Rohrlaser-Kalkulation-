"""Teilefamilie im Angebot (CAD-010, teilefamilie.py): aus einem Teil mit einer Wertetabelle mehrere Positionen.

Aufruf aus dem Angebot (Ausgaben → „Teilefamilie aus Position …“, Kontextmenü), aus dem Rohr- und Blech-Editor
(Knopf „Teilefamilie“, die Positionen entstehen mit OK des Editors) und aus Schweißbaugruppe und Satz in 3D (Knopf
an den Einzelteilen: die neuen Teile kommen in dieselbe Baugruppe bzw. denselben Satz). Das Teil selbst bleibt, wie es
ist; jede Zeile der Tabelle wird eine neue Position, gerechnet wie aus dem Editor.
"""
import json

from PySide6.QtWidgets import QDialog

from . import blech, schneidweg, teilefamilie as tf, zukauf
from .angebot import POSITIONEN, ZUKAUFTEIL

# Felder, die ein Familienmitglied nicht vom Teil erbt (neu gerechnet oder gehören nur zum Teil selbst)
OHNE = ("id", "pos", "geometrie", "step_merkmale", "messungen", "messart", "bohrbild", "gewinde_vorschlag",
        "konturen", "kontur_grenzen", "schneidweg", "einstiche", "klein_n", "klein_mm", "mittel_n", "mittel_mm",
        "gross_n", "gross_mm", "a_schnitt", "b_schnitt", "a_gerade", "b_gerade", "innen", "gravur", "bohrungen",
        "bg_haupt", "angebot_id", "offene_frage")
ZUORDNUNG = ("satz", "je_satz", "bg_knoten", "je_knoten", "bg_hilfe", "bg_gravur", "je_umfang")


class FamilieMixin:
    """Methoden der Angebotsseite (AngebotSeite) für Teilefamilien."""

    def _familie_basis(self, p, e=None):
        profil = self.k.profile.get(p.get("profil_id")) if p.get("profil_id") else None
        return tf.basis(p, e, profil)

    def teilefamilie(self, zeile=None, dialog=None, zeilen=None, variablen=None):
        """Teilefamilie aus der markierten Position: Fenster mit Wertetabelle (dialog(d) bedient es statt exec,
        Tests), dann je Zeile eine neue Position. zeilen = [dict] legt ohne Fenster an. Ergebnis: [IDs] oder None."""
        if self.fremd() or self.db.nur_lesen:
            self.f.meldung("Dieses Angebot lässt sich nur ansehen.", fehler=True)
            return None
        if zeile is None:
            i = self.pos_ansicht.currentIndex()
            zeile = i.row() if i.isValid() else None
        if zeile is None or not 0 <= zeile < len(self.positionen):
            self.f.meldung("Bitte zuerst eine Position wählen.", fehler=True)
            return None
        p = self.positionen[zeile]
        b = self._familie_basis(p)
        if b["art"] is None:
            self.f.meldung(b["fehler"], fehler=True)
            return None
        b["_p"] = p
        if zeilen is None:
            wahl = self.familie_fenster(b, dialog)
            if wahl is None:
                return None
            variablen, zeilen = wahl
        return self.familie_anlegen(p, zeilen, zuordnung=False)

    def familie_fenster(self, b, dialog=None, vorlage_p=None):
        """Fenster Teilefamilie für Basis b; Ergebnis (variablen, zeilen) oder None (abgebrochen)."""
        from .teilefamilie_dialog import TeilefamilieDialog
        werkstoffe = sorted(self.k.werkstoffe) if b["art"] == tf.ROHR else \
            sorted((self.db.blech_daten() or {}).get("werkstoffe") or ())
        d = TeilefamilieDialog(self, b, sorted(self.k.profile, key=str.lower), werkstoffe,
                               speichern=lambda v, z, name: self.familie_als_vorlage(vorlage_p or b.get("_p"), v, z,
                                                                                      name))
        if (dialog(d) if dialog else d.exec()) != QDialog.Accepted:
            return None
        return d.variablen(), d.zeilen()

    def familie_als_vorlage(self, p, variablen, zeilen, name):
        """Teil p mit Variablen und Zeilen als Positionsvorlage (Neue Position aus Vorlage legt die ganze Familie
        an). Ergebnis: ID der Vorlage oder None."""
        from . import positionsvorlagen
        if not p:
            return None
        try:
            i = positionsvorlagen.speichern(self.db, p, name)
        except ValueError as x:
            self.f.meldung(str(x), fehler=True)
            return None
        v = next((z for z in self.db.zeilen(positionsvorlagen.TABELLE) if z["id"] == i), None)
        d = json.loads((v or {}).get("daten") or "{}")
        d.update(tf.vorlage_daten(variablen, zeilen))
        self.db.aendern(positionsvorlagen.TABELLE, i, "daten", json.dumps(d, ensure_ascii=False))
        self.db.aendern(positionsvorlagen.TABELLE, i, "inhalt",
                        f"Teilefamilie mit {len(zeilen)} Teilen: " + ((v or {}).get("inhalt") or ""))
        self.f.meldung(f"Teilefamilie „{name}“ als Vorlage gespeichert ({len(zeilen)} Teile).")
        return i

    def familie_aus_editor(self, d, p):
        """Nach OK im Rohr- oder Blech-Editor: hat man dort eine Teilefamilie gefüllt (d.familie), die Positionen
        zum gespeicherten Teil p anlegen. Ergebnis: Meldungstext (leer ohne Familie)."""
        fam = getattr(d, "familie", None)
        if not fam or not fam.get("zeilen") or p is None:
            return ""
        ids = self.familie_anlegen(p, fam["zeilen"], zuordnung=False, melden=False)
        return f" Teilefamilie: {len(ids)} weitere Position(en) angelegt." if ids else ""

    def familien_aus_baugruppe(self, liste):
        """Nach OK in Schweißbaugruppe oder Satz in 3D: [(Positions-ID des Teils, zeilen)] als neue Einzelteile in
        derselben Baugruppe bzw. demselben Satz. Ergebnis: Hinweistexte."""
        out = []
        aktuell = self.db.positionen(self.id) if liste else []      # Zuordnung wie eben gespeichert
        for pid, zeilen in liste or ():
            p = next((x for x in aktuell if x.get("id") == pid), None)
            if p is None:
                continue
            ids = self.familie_anlegen(p, zeilen, zuordnung=True, melden=False)
            if ids:
                out.append(f"Teilefamilie aus Pos. {p.get('pos') or ''}: {len(ids)} weitere Teile.")
        return out

    def familie_anlegen(self, p, zeilen, zuordnung=False, melden=True, e=None, lieferant=None):
        """Je Zeile eine neue Position aus Teil p (Rohr: Felder wie aus dem Rohr-Editor, Blech: neuer Zukaufartikel
        mit Richtpreis). zuordnung: Satz/Baugruppe des Teils übernehmen. e: Editor-Eingaben (sonst aus p).
        Ergebnis: [IDs der neuen Positionen]."""
        b = self._familie_basis(p, e)
        if b["art"] is None:
            self.f.meldung(b["fehler"], fehler=True)
            return []
        ids, fehler = [], []
        pos = int(max((x["pos"] for x in self.db.positionen(self.id) if isinstance(x.get("pos"), (int, float))),
                      default=0)) + 10
        if b["art"] == tf.BLECH:
            daten = self.db.blech_daten()
            liste = zukauf.json_liste(p.get("zukauf"))
            if not lieferant and liste:
                lieferant = ((liste[0].get("stand") or {}).get("bezug") or {}).get("lieferant")
            lieferant = lieferant or zukauf.lieferant_vorgabe("Blechteile")
        for nr, z in enumerate(zeilen, 1):
            z = {k_: v for k_, v in z.items() if v not in (None, "")}
            f = tf.zeile_pruefen(b, z, self.k.profile, None)
            if f:
                fehler.append(f"Zeile {nr}: " + "; ".join(f))
                continue
            werte = dict(b["werte"], **z)
            if b["art"] == tf.ROHR:
                pid = self._familie_rohr(p, b, werte, pos, zuordnung, fehler, nr)
            else:
                pid = self._familie_blech(p, b, werte, pos, zuordnung, fehler, nr, daten, lieferant)
            if pid:
                ids.append(pid)
                pos += 10
        self.neu_laden()
        if fehler:
            self.f.meldung(f"Teilefamilie: {len(ids)} Position(en) angelegt, {len(fehler)} Zeile(n) nicht: "
                           + " | ".join(fehler), fehler=True)
        elif melden:
            self.f.meldung(f"Teilefamilie aus Pos. {p.get('pos') or ''}: {len(ids)} Position(en) angelegt.")
        return ids

    def _familie_rohr(self, p, b, werte, pos, zuordnung, fehler, nr):
        pid_profil = werte.get(tf.PROFIL) or p.get("profil_id")
        profil = self.k.profile.get(pid_profil)
        if profil is None:
            fehler.append(f"Zeile {nr}: Profil {pid_profil} fehlt")
            return None
        e, f = tf.rohr_eingaben(b["eingaben"], b["werte"].get(tf.LAENGE), werte)
        if pid_profil != p.get("profil_id"):
            e = schneidweg.konturen_umstellen(e, profil)[0]
        namen = {x.name for x in POSITIONEN.felder}
        neu = {k_: v for k_, v in p.items() if k_ in namen and k_ not in OHNE and (zuordnung or k_ not in ZUORDNUNG)
               and v not in (None, "")}
        for s in (tf.LAENGE, tf.STUECK, tf.ARTIKEL, tf.BEZEICHNUNG, tf.PROFIL, tf.WERKSTOFF):
            if werte.get(s) not in (None, ""):
                neu[s] = werte[s]
        neu["laenge"] = tf._z(neu.get("laenge"))
        neu["stueck"] = int(tf._z(neu.get("stueck")) or 1)
        felder, erg = self._rechner_felder(neu, e, profil)
        if erg["fehler"]:
            fehler.append(f"Zeile {nr}: " + " ".join(erg["fehler"]))
            return None
        neu.update(felder, pos=pos)
        return self.db.position_neu(self.id, {k_: v for k_, v in neu.items() if v is not None})

    def _familie_blech(self, p, b, werte, pos, zuordnung, fehler, nr, daten, lieferant):
        e, f = tf.blech_eingaben(b["eingaben"], werte)
        stueck = int(tf._z(werte.get(tf.STUECK)) or 1)
        erg = blech.rechnen(dict(e, stueck=stueck), daten["werkstoffe"], daten["laser"], daten["einst"])
        if erg["fehler"] or not erg.get("richtpreis"):
            fehler.append(f"Zeile {nr}: " + "; ".join(erg["fehler"] or ["kein Richtpreis"]))
            return None
        extra = {k_: p.get(k_) for k_ in ZUORDNUNG if zuordnung and p.get(k_) not in (None, "")}
        extra["pos"] = pos
        bez = werte.get(tf.BEZEICHNUNG) or blech.bezeichnung_vorschlag(e, erg["zuschnitt"])
        kopf = dict(bezeichnung=bez, artikelnr=werte.get(tf.ARTIKEL) or None, stueck=stueck, lieferant=lieferant)
        kopf["muster"] = p.get("muster")
        pid = self._blech_anlegen(e, erg, kopf, extra=extra, leise=True)
        return pid or None

    def familie_aus_vorlage(self, v, dialog=None):
        """Positionsvorlage mit Teilefamilie: Fenster mit den gespeicherten Zeilen, dann alle Positionen. Ergebnis:
        [IDs] oder None."""
        from . import positionsvorlagen
        fam = tf.aus_vorlage(v)
        werte = positionsvorlagen.werte(v)
        if not fam or werte is None:
            return None
        p = dict(werte)
        if blech.lesen(p.get("technik")) is not None and p.get("zukauf"):
            p["art"] = ZUKAUFTEIL
        b = self._familie_basis(p)
        if b["art"] is None:
            self.f.meldung(b["fehler"], fehler=True)
            return None
        b["start"] = fam
        wahl = self.familie_fenster(b, dialog, vorlage_p=p) if dialog is not False else fam
        if wahl is None:
            return None
        return self.familie_anlegen(p, wahl[1], zuordnung=False)
