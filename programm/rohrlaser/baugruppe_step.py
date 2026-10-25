"""Baugruppe und Satz als STEP-Baugruppe (Plan 3D-Editor 3E-14, Patrick 25.10.2026 „Alle a“).

Im Editor der Schweißbaugruppe und im Fenster „Satz in 3D“ schreibt STEP speichern alle Teile als eine STEP-Datei
mit echter Baugruppenstruktur (F5 a): jedes Teil einmal definiert und so oft eingesetzt, wie es in der STEP-Datei
vorkommt, Unterbaugruppen wie im Strukturbaum, Namen = Artikelnummer bzw. Pos.

- Rohre aus den Eingaben des Rohr-Editors (step_export.rohr_teil) mit den Schlitzen und Nasen der
  Steckverbindungen, in der Einbaulage der STEP-Messung (lage: Ende A, Rohrachse, X-Richtung).
- Bleche aus dem Blech-Editor (step_export.blech_teil, eben oder gekantet); ihre Lage bestimmt der Export durch
  Ausrichten am Netz der STEP-Messung (Hauptachsen und Abgleich der Oberfläche).
- Teile, die nur als Netz der STEP-Messung vorliegen (Biegerohr, Knickrahmen, Anbauteile, Zukaufteile ohne
  Editor): das Netz als Körper, mit Hinweis (facettiert).
- Teile ohne Lage (von Hand angelegt): neben die Baugruppe gelegt, mit Hinweis (F4 a). Schweißnähte nicht (F3 a).
"""
from . import blech, schneidweg as sw, step_export, steckverbindung as stv


def lage_matrix(lage, versatz_z=0.0):
    """Einbaulage [Ende A, Rohrachse, X-Richtung] als 3 × 4 Matrix (zeilenweise); versatz_z verschiebt das Teil
    entlang seiner Achse (Nasen an Ende A ragen über 0 hinaus)."""
    o, z, x = lage[0:3], lage[3:6], lage[6:9]
    y = (z[1] * x[2] - z[2] * x[1], z[2] * x[0] - z[0] * x[2], z[0] * x[1] - z[1] * x[0])
    o = [o[i] + z[i] * versatz_z for i in range(3)]
    return [round(float(c), 9) for i in range(3) for c in (x[i], y[i], z[i], o[i])]


def _lagen(netz):
    lagen = (netz or {}).get("lagen") or ([netz["lage"]] if (netz or {}).get("lage") else [])
    return [lg for lg in lagen if lg and len(lg) == 9]


def _dreiecke(netz):
    return [i for idx in ((netz or {}).get("t") or {}).values() for i in idx]


def netz_in_lage(netz, lage):
    """Punkte des Netzes in der Datei (flach) für das Ausrichten."""
    o, z, x = lage[0:3], lage[3:6], lage[6:9]
    y = (z[1] * x[2] - z[2] * x[1], z[2] * x[0] - z[0] * x[2], z[0] * x[1] - z[1] * x[0])
    p, out = netz["p"], []
    for i in range(0, len(p) - 2, 3):
        a, b, c = p[i], p[i + 1], p[i + 2]
        out += [round(o[k] + a * x[k] + b * y[k] + c * z[k], 4) for k in range(3)]
    return out


def bauplan(name, eintraege, knoten=()):
    """Bauplan der STEP-Baugruppe. eintraege: je Position dict(pid, q (Position), netz (entpackt), knoten (Knoten-ID
    oder ''), rohr (Eingaben, Länge, Profil, Nasenwinkel) oder None, gravur_h); knoten: Unterbaugruppen [dict(id,
    name, parent)]. Ergebnis (Bauplan, Hinweise)."""
    teile, hinweise, einsatz = [], [], {}
    for x in eintraege:
        q, netz = x["q"], x.get("netz") or {}
        name_t = step_export.teilname(q)
        lagen, plan, art = _lagen(netz), None, None
        if x.get("rohr"):
            e, laenge, profil, nasen_w = x["rohr"]
            try:
                plan = step_export.rohr_teil(e, profil, laenge, name_t, nasen_winkel=nasen_w, artikel=q.get("artikel"),
                                             gravur_h=x.get("gravur_h") or 0)
                nb = stv.nasen((e or {}).get("a"))
                art = ("lage", -float(nb.get("laenge_plus") or 0) if nb else 0.0)
            except (ValueError, TypeError, ZeroDivisionError, KeyError) as f:
                hinweise.append(f"{name_t}: Rohr nicht aus den Eingaben ({f})")
        e_blech = blech.lesen(q.get("technik"))
        if plan is None and e_blech:
            try:
                plan = step_export.blech_teil(e_blech, blech.zuschnitt(e_blech), name_t)
                art = ("ausrichten", None)
            except ValueError as f:
                hinweise.append(f"{name_t}: Blech nicht aus den Eingaben ({f})")
        if plan is None and netz.get("p") and _dreiecke(netz):
            plan = dict(name=name_t, koerper=dict(art="netz", p=netz["p"], t=_dreiecke(netz)), werkzeuge=[],
                        rillen=[], meldungen=[])
            art = ("lage", 0.0)
            hinweise.append(f"{name_t}: als Netz aus der STEP-Messung (facettiert)")
        if plan is None:
            hinweise.append(f"{name_t}: kein 3D-Modell, nicht in der STEP-Datei")
            continue
        nr = len(teile)
        teile.append(plan)
        liste = einsatz.setdefault(x.get("knoten") or "", [])
        if not lagen:
            liste.append(dict(teil=nr, daneben=True))
        for lage in lagen:
            if art[0] == "lage":
                liste.append(dict(teil=nr, lage=lage_matrix(lage, art[1])))
            elif netz.get("p") and _dreiecke(netz):
                liste.append(dict(teil=nr, ausrichten=dict(p=netz_in_lage(netz, lage), t=_dreiecke(netz))))
            else:
                liste.append(dict(teil=nr, daneben=True))
    ids = {k.get("id") for k in knoten}

    def baum(kid, text, tiefe=0):
        kinder = [baum(k["id"], k.get("name") or "Unterbaugruppe", tiefe + 1) for k in knoten
                  if (k.get("parent") or "") == kid and k.get("id") and tiefe < 20]
        return dict(name=text, einsatz=einsatz.get(kid, []), kinder=[k for k in kinder if k["einsatz"] or k["kinder"]])
    wurzel = baum("", name)
    for kid, liste in einsatz.items():          # Knoten, den es nicht mehr gibt: direkt in die Baugruppe
        if kid and kid not in ids:
            wurzel["einsatz"] += liste
    return dict(name=name, teile=teile, baugruppe=wurzel), hinweise


def ergebnis_text(erg, ziel=None, hinweise=()):
    from pathlib import Path
    if erg.get("fehler") or not erg.get("teile"):
        return f"STEP nicht geschrieben: {erg.get('fehler') or 'keine Teile'}"
    text = (f"STEP-Baugruppe gespeichert{f': {Path(ziel).name}' if ziel else ''} ({len(erg['teile'])} Teile, "
            f"{erg.get('einsaetze', 0)} Körper)")
    if not erg.get("ok"):
        text += "\nAchtung: Die Prüfung meldet Fehler an einem Teil, bitte im CAD kontrollieren."
    alles = list(hinweise) + list(erg.get("hinweise") or ()) + list(erg.get("meldungen") or ())
    if alles:
        text += "\n" + "\n".join(f"• {m}" for m in dict.fromkeys(alles))
    return text


class StepBaugruppe:
    """STEP speichern für den Editor der Schweißbaugruppe und das Fenster „Satz in 3D“ (gemeinsam, Regel „alle
    Editoren“). Erwartet self.teile, self._netz, self._steck_profil, self._rohr_eingaben() und step_name()."""

    def step_knopf(self):
        from PySide6.QtWidgets import QPushButton
        k = QPushButton("STEP speichern …")
        k.setToolTip("Alle Teile als STEP-Baugruppe mit echten Volumenkörpern in der Einbaulage der STEP-Datei, "
                     "Unterbaugruppen wie im Strukturbaum (ohne Schweißnähte)")
        k.clicked.connect(lambda: self.step_speichern())
        return k

    def step_eintraege(self):
        eing, winkel = self._rohr_eingaben()
        out = []
        from .baugruppe_ansicht import eigenes_modell
        for t in self.teile:
            if not t.get("drin"):
                continue
            pid, q = t["_id"], t["_q"]
            netz = self._netz(pid)
            rohr = None
            if pid in eing and not blech.lesen(q.get("technik")):
                e, laenge = eing[pid]
                profil = self._steck_profil(pid)
                if laenge and profil and eigenes_modell(e, netz) and not sw.lesen(q.get("technik")).get("knickrahmen"):
                    rohr = (e, laenge, profil, winkel.get(pid))
            out.append(dict(pid=pid, q=q, netz=netz, knoten=t.get("knoten") or "", rohr=rohr,
                            gravur_h=t.get("gravur_h") if t.get("gravur") else 0))
        return out

    def step_speichern(self, pfad=None):
        """Dateidialog (Ordner des Angebots), Bauplan, Schreiben, Meldung. Ergebnis: Pfad oder None;
        self.step_ergebnis = Ergebnis des Exports (für Tests)."""
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox
        name = self.step_name()
        plan, hinweise = bauplan(name, self.step_eintraege(), getattr(self, "bg", {}).get("knoten") or ())
        if not plan["teile"]:
            QMessageBox.information(self, "STEP speichern", "Keine Teile mit 3D-Modell.")
            return None
        if pfad is None:
            pfad, _ = QFileDialog.getSaveFileName(self, "STEP speichern", step_export.vorschlag(self, name),
                                                  "STEP-Datei (*.step *.stp)")
            if not pfad:
                return None
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            erg = step_export.schreiben(plan, pfad, step_export.programmordner_von(self), name=name,
                                        zeitlimit=step_export.ZEITLIMIT * 3)
        finally:
            QApplication.restoreOverrideCursor()
        erg["hinweise"] = list(hinweise) + list(erg.get("hinweise") or ())
        self.step_ergebnis = erg
        gut = bool(erg.get("teile")) and not erg.get("fehler")
        if not getattr(self, "stumm", False):
            (QMessageBox.information if gut else QMessageBox.warning)(self, "STEP speichern",
                                                                      ergebnis_text(erg, pfad))
        return pfad if gut else None

