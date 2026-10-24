"""Versioniertes Ergebnisformat der STEP-Messung (JSON).

Je STEP-Datei: Dateiname, Importstatus, Einheit, Meldungen des STEP-Lesers und je Körper Profiltyp, Außen- und
Innenmaße, Wandstärke mit Einzelmessungen, Länge, Längsachse, Konturen mit Lage, Schnittwinkel der Enden, Prüfstatus,
Warnungen und Erkennungssicherheit je Merkmal. Alle Längen in mm, Winkel in Grad.

Regeln: Was nicht gemessen wurde, ist null (nie 0 oder ein Ersatzwert); der Grund steht in "warnungen".
"pruefstatus" = "plausibel" heißt nur, dass die Messung in sich stimmig ist. Es ist keine Fertigungsfreigabe.

Versionen von SCHEMA_VERSION:
- 1.0 (19.10.2026): erste Fassung.
- 1.1 (20.10.2026): "bauteiltyp" (Profil, Blech, Blech gekantet) und je Blech der Block "blech" (Länge, Breite, Dicke,
  Flächen, Volumen, Kontur, Innenkonturen, Bohrungen, Fingerabdruck). Bei Blechen sind Profilwerte (Querschnitt,
  Wandstärke, Innenmaße) null. Je Profil "normprofil" (z. B. IPE 200, nur bei passenden Maßen) und bei I-/H-Trägern
  und T-Profilen der Block "traeger" (Steg-, Flanschdicke, symmetrisch, Ausrundung). Felder aus 1.0 unverändert.
- 1.2 (20.10.2026): Grenzfälle Flachstahl/Blech und Profil/Kantteil: "alternative" = derselbe Körper in der anderen
  Art (gleicher Aufbau wie ein Körper, ohne "nr"), sonst null. "ersatzwerte" = true, wenn die Werte nicht gemessen,
  sondern aus der anderen Messung abgeleitet sind (Prüfstatus dann "prüfen"). Felder aus 1.1 unverändert.
- 1.3 (22.10.2026): Konturarten "Senkung" (durchmesser = gelaserte Bohrung, senk_durchmesser) und "Fließloch"
  (Flowdrill mit Kragen: durchmesser = Kernloch, kragen_durchmesser, schnittlaenge 0, nicht im Schneidweg); je Körper
  "senkungen" und "fliessloecher" als Liste mit Anzahl. Felder aus 1.2 unverändert.
- 1.4 (22.10.2026): Anbauteile (aufgeschweißte Bolzen, Laschen, Bleche, Muttern, Kopfplatten). Alle Maße, Konturen und
  der Schneidweg gelten für die Rohrlaser-Geometrie OHNE Anbauteile. Je Körper "anbauteile" (Liste: nr, art, quelle
  "verschmolzen" oder "Körper n", z ab Ende A, winkel, u, seite, aufstand {form, umfang, flaeche, durchmesser bzw.
  laenge/breite}, hoehe, volumen, bearbeitung Umriss/Positionsmarke/keine, gravur_laenge, vertrauen sicher/prüfen,
  hinweis), "trennung" (regelanteil, laengsanbau, ohne_trennung {profil_id, laenge, schneidweg, pruefstatus}) oder
  null, im Block "schneidweg" zusätzlich "gravur_anbau" (in "gravur" enthalten); "alternative" ist bei abgetrennten
  Anbauteilen die Messung ohne Trennung. Felder aus 1.3 unverändert.
- 1.5 (22.10.2026): 3D-Schnittbearbeitung: schräge Bohrungen (ab 0,5° gegen die Wandnormale) tragen "neigung_l"
  (längs, + Richtung Ende B) und "neigung_q" (quer, + Richtung steigender Umfangswinkel) in Grad. Felder aus 1.4
  unverändert.
- 1.6 (22.10.2026): im Block "blech" (ebene Bleche) "konturen_lage": je Innenkontur art (Bohrung, Langloch, Rechteck,
  Polygon), x/y = Mitte im Zuschnitt (x längs ab der linken, y quer ab der unteren Kante des Hüllrechtecks),
  durchmesser bzw. laenge/breite und quer (Längsrichtung quer zum Zuschnitt), bei Polygon punkte um die Mitte,
  schnittlaenge; "aussen_punkte" = Eckpunkte der freien Außenkontur im Zuschnitt, sonst null. Offene Profile (U, C,
  L, Flachstahl, I-/H-Träger, T): je Kontur "querlage" {x, y} = Mitte im Querschnitt um die Mitte des Hüllrechtecks
  (von Ende A gesehen), beim Ende A "querschnitt" = Umriss als Punkte [x, y] im selben System. Felder aus 1.5
  unverändert.
- 1.7 (22.10.2026): RP-Profile (Rohre mit Anschlag aus doppeltem Blech) und Mehrkammerprofile: Profilform "RP-Profil"
  mit "normprofil" = Profil-ID der RP-Bibliothek (z. B. RP 0106-35); je Hohlprofil "kammern" (Zahl der
  Innenkonturen) und "kontur_umfang" (Länge der Außenkontur), "verbund" = Text, wenn ein Körper als Kern in der
  Kammer eines anderen liegt (Verbundprofil, nur gemeldet; der Kern hat die Profilform "Verbundkern"), sonst null.
  Felder aus 1.6 unverändert.
- 1.8 (22.10.2026): Fasen an den Enden: das Ende trägt "fase": true und "hinweis"; die Fase wird nicht gelasert,
  Schnittlänge = Außenkontur an der längsten Stelle (bei gerader Außenkante "form" = "gerade"), Länge = längste Länge.
  Felder aus 1.7 unverändert.
- 1.9 (22.10.2026): 3D-Enden (Form "komplex" aus Ebenen und Zylindern quer zur Rohrachse) bekommen in der
  Konturliste "flaechen" und "huelle": Ebene ["E", gx, gy, c] mit z = c + gx·x + gy·y, Zylinder ["Z", ux, uy, ax, ay,
  az, r, vz]; x, y im Querschnitt um die Mitte, gedreht wie die Schnittwinkel (y = 0°-Richtung), z ab dem Ende;
  "huelle" = "min" oder "max" (Schnittfläche über einem Punkt). Damit rechnet das Programm das Ende für ein anderes
  Profil neu. Andere komplexe Enden ohne diese Felder. Felder aus 1.8 unverändert.
- 1.10 (23.10.2026): "schwenk" je Ende (außer Fasen) und je Innenkontur außer Bohrungen: größter Winkel [Grad]
  zwischen Schnittfläche und Senkrechter zur Rohroberfläche entlang der Schnittkante. Ab 0,5° ist der Schnitt eine
  3D-Bearbeitung (Kopf geschwenkt), darunter 2D, auch bei einer Gehrung. Felder aus 1.9 unverändert.
- 1.11 (23.10.2026): Bohrungen und Senkungen im Rundrohr, die senkrecht zur Oberfläche stehen (schraeg < 0,5°):
  "schnittlaenge" ist die Kontur beim 2D-Schnitt (Strahl zur Rohrmitte, innen Ø der Konstruktion, außen breiter;
  dreid.bohrung_2d_rundrohr) statt der Außenkante der Konstruktion; "innen"/"schneidweg" entsprechend. Hüllmaß
  bleibt der Ø. Felder sonst unverändert.
- 1.12 (23.10.2026): Konturen von Hohlprofilen (Innenkonturen, Gravuren, komplexe Enden) tragen "umriss" = Punkte
  [u, z] der abgewickelten Kontur (u = Umfangsposition wie "u", über die 0°-Naht fortlaufend, z ab Ende A); bei
  Quadrat-/Rechteckrohren "waende" = berührte Seiten. Neue Konturart "Sonderkontur" (über mehrere Wände oder keine
  Grundform; laenge/breite = Hüllrechteck der Abwicklung) statt "Ausschnitt" bei Hohlprofilen; Gravuren und
  Sackbohrungen mit "tiefe" [mm], flache runde Vertiefungen bis 0,5 mm sind Gravur (mit durchmesser), keine
  Sackbohrung. Gekantete Bleche: im Block "blech" Schneidweg (umfang_aussen/innen), Innenkonturen, konturen_lage,
  aussen_punkte der Abwicklung und "abwicklung" {laenge, breite (Zuschnitt), kantlaenge, schenkel [{laenge
  (Außenmaß), winkel (+ zur Außenseite), radius (Innenradius, null = scharfkantig, Blechdicke angenommen)}] bei
  einer Kette paralleler Kanten, sonst null, biegelinien [{punkte, winkel, radius, scharf, ba, von, bis}], kantungen,
  mehrachsig, scharf, k_faktor}; scharfkantig gezeichnete Kantteile werden erkannt (Grenzfall Profil/Kantteil).
  Felder aus 1.11 unverändert.
- 1.13 (23.10.2026): Baugruppenstruktur aus der STEP-Datei (Produktstruktur, Namen). Je Datei "struktur" = null
  (keine Baugruppe) oder {"knoten": [{id, name, eltern (id|null), menge (Instanzen je übergeordnetem Knoten)}],
  "teile": [{teil_index (= Körper "nr", erster Körper des Bauteils), knoten, anzahl (je Knoten)}]}; weitere
  Instanzen einer Unterbaugruppe stehen nicht noch einmal in "teile". Je Körper "bauteil" (Produktname, null =
  keiner), "pfad" ("Gestell/Rahmenseite[2]/Strebe", Instanznummer ab 2) und "knoten" (id oder null). Felder aus
  1.12 unverändert.
- 1.14 (23.10.2026): Je Datei "nahtkandidaten" = Liste möglicher Schweißnähte zwischen sich berührenden Körpern
  {teile [a, b] (Körper "nr"), knoten (gemeinsamer Knoten der Struktur oder null), laenge_mm (Umfang der
  Berührung), stossart (Kehlnaht/Stumpfnaht/Ecknaht), dicke_mm (dünnere Wand bzw. Blechdicke), status "prüfen"};
  nur ein Vorschlag, erst nach Bestätigung übernehmen. Leer bei Einzelteilen. Felder aus 1.13 unverändert.
- 1.15 (23.10.2026): Biegerohre (Rundrohr bzw. Rundstahl aus Geraden und Bögen): "laenge" = Länge der Mittellinie
  (gestreckte Länge mit neutraler Faser in Rohrmitte), Konturen mit "z" = Lage auf der Mittellinie ab Ende A, "winkel"
  um die Rohrachse (0° = Innenseite der ersten Biegung, ohne Verdrehung mitgeführt), "s_von"/"s_bis" (Bereich auf der
  Mittellinie) und "biegezone": true, wenn die Kontur in einem Bogen liegt. Je Körper "biegerohr" = null oder
  {mittellinie, aussen_d, elemente [{art gerade/bogen, s0, s1, laenge, radius, winkel}], lra [{gerade (vor der
  Biegung), drehung (Biegeebene gegen die vorige, Grad), winkel, radius}; letzte Zeile = Gerade nach der letzten
  Biegung], xyz [[x, y, z] Eckpunkte des Tangentenzugs ab Ende A, z = Richtung der ersten Geraden]}. Prüfstatus
  immer "prüfen". Felder aus 1.14 unverändert.
- 1.16 (24.10.2026): Je Nahtkandidat "linien" = Nahtverlauf für die 3D-Ansicht der Baugruppe: Liste von Linienzügen
  [x, y, z, x, y, z, …] in Dateilage (mm, 0,1 mm gerundet), je Kante des längsten Berührungszugs einer, Stützpunkte
  etwa alle 5 mm. Felder aus 1.15 unverändert.
"""
from datetime import datetime

SCHEMA = "rohrlaser-step-messung"
SCHEMA_VERSION = "1.16"
HOHL = ("Rundrohr", "Quadratrohr", "Rechteckrohr", "Sonderprofil")
VOLL = ("Flachstahl", "Vierkantstahl", "Rundstahl")
BLECH = ("Blech", "Blech gekantet")


def _blech(b):
    """Blechblock fürs JSON (nur Bleche)."""
    if not b:
        return None
    out = {k: _r(b.get(k), 2) for k in ("laenge", "breite", "hoehe", "dicke", "flaeche_aussen", "flaeche_netto",
                                         "abwicklung_flaeche", "volumen", "umfang_aussen", "umfang_innen")
           if b.get(k) is not None}
    out.update(kontur=b.get("kontur"), innenkonturen=b.get("innen", 0),
               bohrungen=[dict(durchmesser=_r(d), anzahl=n) for d, n in (b.get("bohrungen") or {}).items()],
               fingerabdruck=b.get("fingerabdruck"), konturen_lage=b.get("konturen_lage") or [],
               aussen_punkte=b.get("aussen_punkte"), abwicklung=b.get("abwicklung"))
    return out


def _r(x, n=3):
    return None if x is None else round(float(x), n) + 0.0     # + 0.0: keine -0.0


def koerper(t):
    """Ergebnis eines Körpers (step_geometrie.Teil) als dict."""
    gemessen = bool(t.profilform) and t.laenge > 0
    hohl = t.profilform in HOHL and t.innen_a > 0
    konturen = [k for k in t.konturen_liste if not k["art"].startswith("Ende ")]
    enden = {k["art"]: k for k in t.konturen_liste if k["art"].startswith("Ende ")}
    blech = t.profilform in BLECH
    if blech:
        aussen = dict(laenge=_r(t.blech.get("laenge")), breite=_r(t.blech.get("breite")),
                      dicke=_r(t.blech.get("dicke")))
    elif t.profilform in ("Rundrohr", "Rundstahl"):
        aussen = dict(durchmesser=_r(t.abm_a))
    elif t.profilform in ("Quadratrohr", "Vierkantstahl"):
        aussen = dict(a=_r(t.abm_a), b=_r(t.abm_a))
    else:
        aussen = dict(a=_r(t.abm_a), b=_r(t.abm_b))
    if gemessen and hohl:
        innen = dict(durchmesser=_r(t.innen_a)) if t.profilform == "Rundrohr" else dict(a=_r(t.innen_a),
                                                                                         b=_r(t.innen_b))
    else:
        innen = None
    if gemessen and t.profilform not in VOLL and not blech:
        wand = dict(wert=_r(t.wandstaerke), minimum=_r(min([m[3] for m in t.wand_messungen] + [t.wandstaerke])),
                    maximum=_r(max([m[3] for m in t.wand_messungen] + [t.wandstaerke])),
                    einzelmessungen=[dict(z=_r(z), x=_r(x), y=_r(y), wert=_r(w), seite=s)
                                     for z, x, y, w, s in t.wand_messungen])
    else:
        wand = None
    konturen_ausgewertet = gemessen and t.sicherheit.get("konturen") not in (None, "nicht ausgewertet")
    return {
        "nr": t.koerper,
        "artikel_vorschlag": t.datei,
        "koerperart": t.koerperart or None,
        "geometrie_gueltig": t.gueltig,
        "volumen_mm3": _r(t.volumen, 1) if t.koerperart != "Flächenmodell offen" else None,
        "oberflaeche_mm2": _r(t.oberflaeche, 1),
        "anzahl_flaechen": t.n_flaechen,
        "anzahl_kanten": t.n_kanten,
        "huellquader_datei": list(map(_r, t.huelle)) if t.huelle else None,
        "bauteiltyp": t.bauteiltyp or None,
        "profiltyp": t.profilform or None,
        "profil_id_vorschlag": t.profil_id_vorschlag or None,
        "aussenmasse": aussen if gemessen else None,
        "innenmasse": innen,
        "querschnittsflaeche_mm2": _r(t.flaeche, 2) if gemessen and not blech else None,
        "wandstaerke": wand,
        "laenge": _r(t.laenge) if gemessen else None,
        "laengsachse": dict(richtung=list(map(lambda x: _r(x, 6), t.achse_global)),
                            ende_a=list(map(_r, t.ende_a_global))) if gemessen and t.achse_global else None,
        "schnittwinkel": {name: dict(form=e.get("form"), gesamt=e.get("gehrung"), um_x=e.get("um_x"),
                                     um_y=e.get("um_y"), richtung=e.get("richtung")) for name, e in enden.items()} if konturen_ausgewertet else None,
        "schneidweg": dict(gesamt=_r(t.schneidweg, 2), ende_a=_r(t.ende_a, 2), ende_b=_r(t.ende_b, 2),
                           innen=_r(t.innen, 2), gravur=_r(t.gravur, 2), gravur_anbau=_r(t.gravur_anbau, 2),
                           einstiche=t.konturen)
        if konturen_ausgewertet else None,
        "konturen": [dict(d) for d in konturen] if konturen_ausgewertet else None,
        "senkungen": [dict(durchmesser=_r(d), senk_durchmesser=_r(s_), anzahl=n)
                      for (d, s_), n in sorted(t.senkungen.items())] if konturen_ausgewertet else None,
        "fliessloecher": [dict(durchmesser=_r(d), anzahl=n) for d, n in sorted(t.fliessloecher.items())]
        if konturen_ausgewertet else None,
        "enden": list(enden.values()) if konturen_ausgewertet else None,
        "blech": _blech(t.blech) if blech else None,
        "normprofil": t.normprofil or None,
        "kammern": t.kammern or None,
        "kontur_umfang": _r(t.kontur_umfang, 2) if t.kontur_umfang else None,
        "verbund": t.verbund or None,
        "biegerohr": t.biegerohr if gemessen and t.biegerohr else None,
        "bauteil": t.bauteil or None,
        "pfad": t.pfad or None,
        "knoten": t.knoten or None,
        "traeger": dict(stegdicke=_r(t.stegdicke), flanschdicke=_r(t.flanschdicke), symmetrisch=t.symmetrisch,
                        ausrundung=_r(t.radius, 1) if t.radius else None)
        if gemessen and t.profilform in ("I-/H-Träger", "T-Profil") else None,
        "pruefstatus": t.pruefstatus,
        "warnungen": list(t.hinweise),
        "erkennungssicherheit": dict(t.sicherheit),
        "ersatzwerte": bool(t.ersatz),
        "anbauteile": [dict(a) for a in t.anbauteile],
        "trennung": dict(t.trennung) if t.trennung else None,
        "alternative": {k: v for k, v in koerper(t.alternative).items() if k != "nr"} if t.alternative else None,
    }


def datei(name, teile=None, fehler=None):
    """Ergebnis einer STEP-Datei. teile: Liste step_geometrie.Teil; fehler: Text, wenn die Datei nicht lesbar war."""
    if fehler is not None or not teile:
        return {"datei": name, "importstatus": "nicht lesbar", "fehler": fehler, "einheit_datei": None,
                "einheit_ausgabe": "mm", "meldungen": [], "warnungen": [], "baugruppe": None, "struktur": None, "nahtkandidaten": [],
                "anzahl_koerper": 0, "koerper": []}
    meldungen = teile[0].meldungen
    leer = [h for t in teile if not t.koerper for h in t.hinweise]     # z. B. "Kein Körper … in der Datei"
    return {
        "datei": name,
        "importstatus": "gelesen mit Meldungen" if meldungen else "gelesen",
        "fehler": None,
        "einheit_datei": teile[0].einheit or None,
        "einheit_ausgabe": "mm",
        "meldungen": list(meldungen),
        "warnungen": leer,
        "baugruppe": len(teile) > 1,
        "struktur": teile[0].struktur,
        "nahtkandidaten": list(teile[0].naehte or []),
        "anzahl_koerper": len([t for t in teile if t.koerper]),
        "koerper": [koerper(t) for t in teile if t.koerper],
    }


def gesamt(dateien):
    """Gesamtergebnis einer Messung mehrerer Dateien."""
    return {"schema": SCHEMA, "schema_version": SCHEMA_VERSION, "erzeugt": datetime.now().isoformat(timespec="seconds"),
            "hinweis": "Messergebnis aus der Geometrie, keine Fertigungsfreigabe.", "dateien": dateien}
