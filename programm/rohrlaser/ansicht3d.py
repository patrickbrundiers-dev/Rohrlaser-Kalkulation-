"""3D-Ansicht eines Rohrteils aus dem STEP-Import (Dreiecksnetz der STEP-Messung).

Gezeichnet wird ohne OpenGL mit QPainter, damit die Ansicht auf jedem Rechner läuft, auch über Remote-Desktop.
Rückseiten fallen weg; dann genügen zwei Schichten: zuerst die Innenwand, darüber alle anderen Flächen, von hinten
nach vorn sortiert (so überdecken sich auch bei offenen Profilen wie U oder L die Schenkel richtig). Bei Rohren ist
die Innenwand nur durch Öffnungen zu sehen, die in der Außenhaut ausgespart sind. Zuletzt die Schnittkonturen auf
der Außenhaut als kräftige Linien. Farben nach Art der Fläche.

Netz: {p: [x, y, z, …], t: {Art: [i, j, k, …]}, l: {Art: [[x, y, z, …], …]}} mit Rohrachse = Z ab 0 (siehe
step_messung/step_geometrie.py). Gespeichert wird es zlib-komprimiert je Position. Neuere Messungen haben dazu
lage = [Ende A, Rohrachse, X-Richtung] in der STEP-Datei; damit setzt baugruppe() die Teile einer Datei zusammen.
"""
import itertools
import json
import math
import sys
import threading
import time
import weakref
import zlib

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QLinearGradient, QPainter, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import (QButtonGroup, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QToolTip, QVBoxLayout,
                               QWidget)

from . import explosion as explo_mod, mess_kern, mess_protokoll, navigation3d, schnitt_explosion, stil, visualisierung
from .mess_kern import winkel_bei  # noqa: F401 – auch ansicht3d.winkel_bei (Messkern, M1/M2)

ARTEN = (  # (Art, Bezeichnung, Farbe Fläche, Farbe Linie)
    ("A", "Außenwand", "#B9C3CD", None),
    ("I", "Innenwand", "#8A96A3", None),
    ("EA", "Anfangsschnitt", "#F28E2B", "#D9660A"),
    ("EB", "Endschnitt", "#B07AA1", "#8E4F80"),
    ("K", "Innenkonturen", "#E15759", "#C00000"),
    ("G", "Gravur", "#59A14F", "#2E7D32"),
    ("AN", "Anbauteile", "#E8C77A", None),            # aufgeschweißte Teile (nicht gelasert)
    ("GA", "Gravur Anbauteile", "#59A14F", "#00897B"),
    ("S", "gewählte Teile", "#2E75B6", None),       # nur in der Baugruppen-Ansicht
    ("N", "nicht übernehmbar", "#FF00FF", None),    # nicht messbare Teile (Rohnetz in Dateilage), magenta
    ("BL", "Blech", "#C9D6E3", None),               # Blech-Editor (blech3d)
    ("KB", "Blech/Kantteil (Zukauf, nicht gelasert)", "#6F9FD8", None),   # STEP-Prüfdialog: Art Blech
    ("KD", "Dreh-/Frästeil (Zukauf, nicht gelasert)", "#C9A227", None),  # STEP-Prüfdialog: Art Dreh-/Frästeil
    ("NT", "Normteil/Zukaufteil", "#3F4650", None),   # Baugruppe im STEP-Prüfdialog: Schrauben, Muttern … (21.11.2026)
    ("RS", "Stange: Endbeschnitt, Rest, Greiferrest", "#C5CCD6", None),  # Nesting-Arbeitsplatz 3D (24.11.2026)
    ("VS", "Verschnitt zwischen den Teilen", "#E15759", None),  # Nesting 3D: Flächen zwischen den Schnittkanten
    ("B", "Biegelinien", "#2E7D32", "#2E7D32"),
    ("SN", "Schweißnähte", "#1A1A1A", "#1A1A1A"),        # Baugruppen-Ansicht: Nahtgruppen (schwarz: auf allen
    ("SV", "Nahtvorschläge (STEP)", "#D000D0", "#D000D0"),  # Teilfarben sichtbar), offene Nahtkandidaten magenta
    ("SH", "gewählte Naht", "#FF0000", "#FF0000"),
    ("SX", "Naht nicht erreichbar (STEP)", "#FF8C00", "#FF8C00"),   # Brenner kommt nicht hin (Erreichbarkeit)
    ("NL", "Schweißnaht (Längsnaht)", "#E00000", "#E00000"),     # Rohr-Editor: Lage der Naht im Rohr
    ("GB", "3D über Grenze (begrenzt)", "#F2C200", "#C79A00"),  # Schnitt braucht mehr als die Schwenkgrenze
    ("HK", "Hilfskörper (Gegenrohr, Tiefe)", "#E377C2", "#E377C2"),   # Rohr-Editor: Gegenrohr am Ende / Durchbruch
    ("EW", "Ringe bzw. Spalt (aus dem Rohr)", "#E00000", None),   # STEP: Rohr mit Spalt gezeichnet, Spalt geschlossen
    ("EO", "Ringe bzw. Spalt (nicht gefertigt)", "#E89A9A", None),  # derselbe Spalt, wenn das Teil offen bleibt
    ("ES", "Stege 2 mm (aus größerem Profil)", "#E00000", None),  # Winkel/U aus größerem Profil (step_schenkel)
    ("UW", "über dem Rohr (fällt weg)", "#F28E2B", None),     # offenes Rohr: ragt über den Rohrquerschnitt
    ("UO", "über dem Rohr (bleibt, Teil offen)", "#AEB8C4", None),  # dasselbe, wenn das Teil offen bleibt
    # Schnittkörper je Kontur (schnittkoerper.py): halb durchsichtig, Farbe je Konturart
    ("WB", "Schnittkörper Bohrung", "#2F80ED", "#1F5FBF"),
    ("WL", "Schnittkörper Langloch/Schlitz", "#00A3A3", "#007A7A"),
    ("WR", "Schnittkörper Rechteck/Kontur", "#9B51E0", "#7330B0"),
    ("WA", "Schnittkörper Ausklinkung", "#F2994A", "#C46A1C"),
    ("WG", "Schnittkörper Gravur", "#27AE60", "#1E8449"),
    ("WU", "Schnittkörper Sonderkontur", "#FF1493", "#C2006E"),       # unbekannte Kontur, Form wie STEP
    ("WV", "Schnittkörper V-Ausschnitt", "#8D6E63", "#5D4037"),
    # Kostentreiber (CAD-005, kostenfarben.py): Teile einer Baugruppe/eines Satzes nach ihrem €-Anteil
    ("KO0", "Kosten ab 50 %", "#C62828", None),
    ("KO1", "Kosten 25 bis 50 %", "#EF6C00", None),
    ("KO2", "Kosten 10 bis 25 %", "#F9A825", None),
    ("KO3", "Kosten unter 10 %", "#2E7D32", None),
    # Geometrieprüfung des Imports (step_qualitaet, STEP-Viewer „Farben nach Prüfung“, 24.11.2026)
    ("QK", "Geometrie korrekt", "#2E7D32", None),
    ("QU", "Geometrie unsicher", "#F2A900", None),
    ("QR", "Geometrie reparierbar", "#2B6CB0", None),
    ("QF", "Geometrie fehlerhaft", "#C62828", None),
    ("SC", "Schnittkante (nur Anzeige)", "#D81B60", "#D81B60"),     # V6: Kante an der Schnittebene
)
FARBE = {a: QColor(f) for a, _, f, _ in ARTEN}
REIHE = [a for a, *_ in ARTEN]          # Reihenfolge der Legende
# Darstellung (Einstellung 'ansicht_3d', je Arbeitsplatz): Automatisch = OpenGL, wenn möglich und nicht über
# Remote-Desktop; Software = immer QPainter; OpenGL = OpenGL, wenn möglich (Rückfall auf QPainter)
RENDERER = ("Automatisch", "Software", "OpenGL")
_renderer = RENDERER[0]
_gl_fehler = None       # OpenGL ist in diesem Programmlauf schon einmal gescheitert: Grund
GROB_DREIECKE = 10000   # beim Drehen/Zoomen höchstens so viele Dreiecke zeichnen (grobe Stufe, Modell.grob)
GROB_ZEIT, GROB_MIN = 0.06, 3000   # V3: grobe Stufe so groß, dass ein Bild etwa 60 ms braucht, mindestens 3000
DREHPUNKT_FEIN = 80000  # Drehpunkt bis zu so vielen Dreiecken im vollen Modell suchen, darüber in der groben Stufe
# Baugruppen-Ansicht: je Teil (Zeile gleicher Teile) eine Farbe, ohne Eintrag in der Legende
TEILFARBEN = ("#4E79A7", "#F28E2B", "#59A14F", "#E15759", "#76B7B2", "#EDC948", "#B07AA1", "#FF9DA7", "#9C755F",
              "#BAB0AC", "#2F4B7C", "#A05195")
FARBE.update({f"F{n}": QColor(f) for n, f in enumerate(TEILFARBEN)})
FARBE["X"] = stil.farbe_fest("#D9DDE2")
FARBE["RS"].setAlpha(110)    # Nesting: Endbeschnitt, Rest, Greiferrest halb durchsichtig (Teile davor bleiben klar)     # nicht gewählte Teile, wenn andere hervorgehoben sind
LINIE = {a: QColor(l or f) for a, _, f, l in ARTEN}
NAEHTE, NAHT_BREITE = ("SN", "SV", "SH", "SX"), 4.5     # Schweißnähte dicker und immer sichtbar (Normale 0)
HINTERGRUND = stil.farbe_fest("#FFFFFF")     # unten; oben HINTERGRUND_OBEN, dazwischen Verlauf (hintergrund_bei)
HINTERGRUND_OBEN = stil.farbe_fest("#DCE3EA")
# Licht (QPainter je Dreieck, OpenGL je Ecke, gleiche Formel): seit V2 (19.11.2026) aus visualisierung (Lichtprofil
# und Material); diese Werte = Profil „Werkstatt“ mit Material „Standard“ (Hauptlicht links oben vorn, Fülllicht
# rechts unten; LICHT_WERTE = Grundlicht, Neigung oben heller, Fülllicht, Glanz, Glanz-Exponent)
LICHT = (-0.35, 0.45, 0.82)
LICHT2 = (0.55, -0.35, 0.76)
LICHT_WERTE = (0.38, 0.06, 0.16, 0.22, 36.0)
MARKIERT = stil.farbe_fest("#00A040")       # Teile-Editor: gewähltes Merkmal (grün umrandet wie im CAM, Plan G3)
KANTE = stil.farbe_fest("#3C4650")          # Darstellung „Mit Kanten“: Körperkanten
# Darstellungsarten (Plan 3D-Editor A4): Schattiert = Flächen und Schnittkonturen (wie bisher), Mit Kanten = dazu die
# Körperkanten dunkel, Durchsichtig = Röntgen (Rückseiten und verdeckte Konturen sichtbar)
SCHATTIERT, MIT_KANTEN, DURCHSICHTIG = "Schattiert", "Mit Kanten", "Durchsichtig"
# Plan 3D-Ansicht 3E-11 (M3): Drahtgitter = nur Körperkanten und Konturen (auch die hinteren), Verdeckt gestrichelt =
# helle Flächen, sichtbare Kanten durchgezogen, verdeckte gestrichelt (wie eine technische Zeichnung)
DRAHTGITTER, VERDECKT = "Drahtgitter", "Verdeckt gestrichelt"
# 3D-Visualisierungsupdate V5 (19.11.2026): fünf weitere Darstellungen. Verdeckt ausgeblendet = Linienbild ohne
# verdeckte Kanten (weiße Flächen), Durchsichtig mit Kanten = Röntgen mit Körperkanten, Flächentypen = jede Fläche
# nach ihrer Art aus der STEP (Ebene, Zylinder, …; Flächenkatalog M3), Konturen betont = Teil hell, Konturen,
# Gravuren und Schnitte kräftig, Nur Konturen = nur die Schnittlinien (prüft, was gelasert wird)
VERDECKT_AUS, DURCHSICHTIG_KANTEN, FLAECHENTYPEN = "Verdeckt ausgeblendet", "Durchsichtig mit Kanten", "Flächentypen"
KONTUREN_BETONT, NUR_KONTUREN = "Konturen betont", "Nur Konturen"
# Kanten und Prüfbarkeit (Patrick 20.11.2026): Realistisch = Material, nur dezente Außenkanten; Technisch (CAD) = weiße
# Flächen, einheitliche dunkle Kanten, verdeckte gestrichelt, Innenkanten blau; Prüfmodus Rohrlaser = Außenwand
# durchsichtig (Deckkraft einstellbar), Innenwand, Innenkanten, Lochränder und Konturen klar sichtbar
REALISTISCH, TECHNISCH, PRUEFMODUS = "Realistisch", "Technisch (CAD)", "Prüfmodus Rohrlaser"
DARSTELLUNGEN = (SCHATTIERT, MIT_KANTEN, DURCHSICHTIG, DRAHTGITTER, VERDECKT, VERDECKT_AUS, DURCHSICHTIG_KANTEN,
                 FLAECHENTYPEN, KONTUREN_BETONT, NUR_KONTUREN, REALISTISCH, TECHNISCH, PRUEFMODUS)
# Modi A–E des Auftrags (Kurzwahl im Menü Darstellung): Realistisch, Kanten, Technisch, Durchsicht, Drahtgitter
MODI_AE = (("A", REALISTISCH), ("B", MIT_KANTEN), ("C", TECHNISCH), ("D", DURCHSICHTIG_KANTEN), ("E", DRAHTGITTER))
MIT_KOERPERKANTEN = (MIT_KANTEN, DRAHTGITTER, VERDECKT, VERDECKT_AUS, DURCHSICHTIG_KANTEN, FLAECHENTYPEN,
                     KONTUREN_BETONT, REALISTISCH, TECHNISCH, PRUEFMODUS)
# immer mit verdeckten Kanten (gestrichelt); die übrigen Kanten-Darstellungen nur mit der Einstellung „verdeckte Kanten“
IMMER_VERDECKT = (VERDECKT, TECHNISCH, PRUEFMODUS)
OHNE_VERDECKT = (DRAHTGITTER, VERDECKT_AUS, REALISTISCH)       # nie gestrichelt (Drahtgitter zeigt alles durchgezogen)
DARSTELLUNG_TIPP = ("Schattiert = Flächen und Schnittkonturen, Mit Kanten = dazu die Körperkanten (Vorgabe), "
                    "Durchsichtig = Röntgen (Rückseite und verdeckte Konturen sichtbar), Drahtgitter = nur Kanten, "
                    "Verdeckt gestrichelt = verdeckte Kanten gestrichelt, Verdeckt ausgeblendet = Linienbild ohne "
                    "verdeckte Kanten, Durchsichtig mit Kanten, Flächentypen = Ebene/Zylinder/… aus der STEP, "
                    "Konturen betont = Teil hell, Konturen kräftig, Nur Konturen = nur die Schnittlinien, "
                    "Realistisch = Material mit dezenten Außenkanten, Technisch (CAD) = weiße Flächen, verdeckte "
                    "Kanten gestrichelt, Innenkanten blau, Prüfmodus Rohrlaser = Außenwand durchsichtig, innen alles "
                    "sichtbar")
ROENTGEN_ARTEN = (DURCHSICHTIG, DURCHSICHTIG_KANTEN)          # Flächen halb durchsichtig
DRAHT_ARTEN = (DRAHTGITTER, NUR_KONTUREN)                     # ohne Flächen
UMRISS_ARTEN = (DRAHTGITTER, VERDECKT, VERDECKT_AUS, TECHNISCH)   # Umriss der Rundungen je Blickrichtung
WEISS_ANTEIL = {VERDECKT_AUS: 0.94, TECHNISCH: 0.93}          # Flächen so weit zu Weiß gemischt (dazu VERDECKT)
PRUEF_DURCH = frozenset(("A", "BL", "UO", "AN", "KB", "KD"))  # Prüfmodus: diese Flächen (außen) durchsichtig
TECHNISCH_KANTE = "#141A20"     # Technisch (CAD): einheitlich fast schwarz
VERDECKT_PIXEL = 9.0            # Kanten in Stücke dieser Länge [px] teilen und je Stück die Verdeckung prüfen
NEUTRAL_ARTEN = ("A", "I", "BL", "AN", "UO", "KB", "KD", "NT", "RS", "S", "X")    # Körperflächen (Konturen betont: hell)
BETONT_HELL, BETONT_BREITE = 0.62, 3.4
HAUCH_FARBE = stil.farbe_fest("#B6C0CA")      # Nur Konturen: Körperkanten ganz hell
# Flächentypen: Farbe je Art des Flächenkatalogs (FT_ + Art); Flächen ohne Katalog (ältere Messung) FT_Netz
FLAECHENTYP_FARBE = {"Ebene": "#7FA7D6", "Zylinder": "#E9A25B", "Kegel": "#B48FD9", "Kugel": "#5FBF9A",
                     "Torus": "#E07B91", "Freiform": "#C9BD4E", "Netz": "#B9C3CD"}
FARBE.update({f"FT_{n}": QColor(f) for n, f in FLAECHENTYP_FARBE.items()})
VERDECKT_HELL = 0.6     # „Verdeckt gestrichelt“: Flächen so weit zu Weiß gemischt
VERDECKT_FARBE = stil.farbe_fest("#7A8794")      # verdeckte Kanten (gestrichelt)
# Perspektive (M2): Kamera so viele Modellgrößen vor der Bildmitte; Vorgabe orthogonal, je Benutzer gemerkt
PERSPEKTIVE_ABSTAND = 2.4
PERSPEKTIVE_EINSTELLUNG = "ansicht_perspektive"
ALPHA = 0.32            # Deckkraft der Flächen bei „Durchsichtig“
# Schnittkörper (schnittkoerper.py): Deckkraft, gewählte Kontur kräftiger; Vorgabe an, je Benutzer gemerkt
WK_ALPHA, WK_ALPHA_GEWAEHLT = 0.26, 0.6
WK_ARTEN = ("WB", "WL", "WR", "WA", "WG", "WU", "WV")
KOERPER_EINSTELLUNG = "ansicht_schnittkoerper"
BLASS = 0.72            # „nur Gewähltes hervorheben“: Rest so weit zu Weiß gemischt
KANTEN_MAX = 300000     # Körperkanten bis zu so vielen Dreiecken (20.11.2026: auch große Baugruppen, vorher 60.000)
TANGENTE_BREITE = 4.0   # mm: ohne Flächenkatalog ist eine schmalere „ebene Fläche“ ein Streifen einer Rundung
KANTEN_WINKEL = 0.9     # cos des Knickwinkels: darüber gilt ein Übergang als glatt (keine Kante), etwa 25°
# Kantenklassen (20.11.2026): Innenkanten = nur an der Innenwand (Innenecken, Lochränder innen) – eigene Farbe, einzeln
# ausblendbar; alles mit einer Außenfläche ist außen
KANTE_AUSSEN, KANTE_INNEN = "a", "i"
AUSSEN_ARTEN = frozenset(("A", "BL", "AN", "UO", "KB", "KD", "NT", "RS", "N", "S", "EW", "EO", "ES", "UW"))
GLATT_MAX = 150000      # Rundungen glatt schattieren (Normale je Ecke) nur bis zu so vielen Dreiecken
MESSEN = stil.farbe_fest("#B42318")
FANG = stil.farbe_fest("#0070C0")            # Messen: gefangenes Element unter der Maus
VORHER = stil.farbe_fest("#E07000")          # Vorher-Nachher: Stand beim Öffnen gestrichelt
SCHNITT = stil.farbe_fest("#1F4E78")        # Querschnitt-Stelle (editor_schnitt)
PRUEFEN = stil.farbe_fest("#F2C200")        # P3.1: unsicher erkanntes Merkmal (STEP-Import)
PRUEFEN_TEXT = stil.farbe_fest("#1F3864")
HOVER = stil.farbe_fest("#0070C0")         # P5.2: Kontur, über der die Maus in Skizze/Abwicklung steht
FOLGE_AKTUELL = stil.farbe_fest("#E07000")  # Schneidvorschau: aktueller Schritt
FOLGE_FERTIG = stil.farbe_fest("#9AA3AD")   # bereits geschnitten
FOLGE_OFFEN = stil.farbe_fest("#2F6FB0")    # noch offen bzw. Übersicht
FOLGE_START = stil.farbe_fest("#00A040")    # Einstich (Anschnitt)
FOLGE_LEER = stil.farbe_fest("#5A6470")     # Leerweg des Kopfs
FOLGE_HUB = stil.farbe_fest("#8E44AD")      # Leerweg mit Kopf heben (Sprung bzw. Drehen über die Kante)
FOLGE_STEG = stil.farbe_fest("#F2C200")     # Mikrosteg
FOLGE_ZERTEILT = stil.farbe_fest("#C0392B")  # Schnitte, die den Abfall zerteilen
# Vorschau bei Anbauteilen: Original = Rohr mit Anbauteilen, Rohrgeometrie = nur was der Laser bearbeitet,
# Gravurkonturen = Rohr mit allen Gravurlinien (ohne Schnittlinien)
MODI = ("Original", "Rohrgeometrie", "Gravurkonturen")


MAUS_RUHE_MS = 60       # A5: Koordinaten unter der Maus erst nach so viel Ruhe rechnen
KOORD_MAX = 1e6         # |Koordinate| darüber (1 km) gilt als fehlerhaft (Einheit falsch oder Datenmüll)


def _zahl_ok(v):
    return type(v) in (int, float) and math.isfinite(v) and -KOORD_MAX <= v <= KOORD_MAX


def _zahlen_ok(werte):
    """Schnellprüfung einer Zahlenliste (Plan 3D-Editor 19.11.2026, A2): nur int/float, alle endlich, alle innerhalb
    ±KOORD_MAX. True heißt sicher in Ordnung; False heißt „genau prüfen“ (dann zählt _zahl_ok je Wert). Die Summe ist
    genau dann endlich, wenn kein Wert NaN oder unendlich ist (NaN und ±∞ setzen sich in der Summe durch); läuft sie
    bei riesigen Werten über, ist sie ∞ und die genaue Prüfung entscheidet."""
    if not werte:
        return True
    try:
        return (set(map(type, werte)) <= _ZAHL_TYPEN and math.isfinite(sum(werte))
                and -KOORD_MAX <= min(werte) and max(werte) <= KOORD_MAX)
    except (TypeError, OverflowError):
        return False


def _nummern_ok(idx, n):
    """Schnellprüfung einer Liste von Punktnummern: nur int (kein bool), alle in 0 … n − 1."""
    return not idx or (set(map(type, idx)) <= _NUMMER_TYPEN and min(idx) >= 0 and max(idx) < n)


_ZAHL_TYPEN, _NUMMER_TYPEN = frozenset((int, float)), frozenset((int,))


def _anzahl(n, eins, mehr):
    return f"{n} {eins if n == 1 else mehr}"


def netz_pruefen(netz):
    """Zentrale Prüfung eines Netzes vor dem Anzeigen (Plan 3D-Viewer 18.11.2026, V1): Punkte mit NaN, unendlich,
    falschem Typ oder außerhalb ±KOORD_MAX, Dreiecke mit ungültigen Punktnummern, Linienzüge mit solchen Punkten und
    unlesbare Schnittkörper fallen heraus, statt das Zeichnen abstürzen zu lassen. Ergebnis (Netz, Meldung): ein
    fehlerfreies Netz kommt unverändert (dasselbe Objekt) mit Meldung "" zurück; sonst eine bereinigte Kopie und ein
    Satz, was ausgelassen wurde (wird in der Ansicht angezeigt, nie still). Kein dict -> (None, Meldung)."""
    if netz is None:
        return None, ""
    if not isinstance(netz, dict):
        return None, "Modell fehlerhaft: keine lesbaren 3D-Daten."
    p = netz.get("p")
    if not isinstance(p, list):
        return (None, "Modell fehlerhaft: Punktliste fehlt.") if p is not None else (netz, "")
    teile = []
    n = len(p) // 3
    rest = len(p) % 3
    # A2 (Plan 3D-Editor 19.11.2026): erst die Schnellprüfung über die ganze Liste, nur bei Verdacht je Punkt
    schlecht = [] if _zahlen_ok(p) else [i for i in range(n) if not (_zahl_ok(p[3 * i]) and _zahl_ok(p[3 * i + 1])
                                                                     and _zahl_ok(p[3 * i + 2]))]
    t, li_, ti, l_ = netz.get("t"), netz.get("li"), netz.get("ti"), netz.get("l")
    t_ok = t is None or (isinstance(t, dict) and all(isinstance(v, list) for v in t.values()))
    l_ok = l_ is None or (isinstance(l_, dict) and all(isinstance(v, list) and all(isinstance(z, list) for z in v)
                                                      for v in l_.values()))
    wk = netz.get("wk")
    wk_ok = wk is None or (isinstance(wk, list) and all(isinstance(k, dict) for k in wk))
    idx_ok = t_ok and all(_nummern_ok(v, n) for v in (t or {}).values()) and \
        all(len(v) % 3 == 0 for v in (t or {}).values())
    tf_ok = _katalog_ok(netz, t if t_ok else None)
    zug_ok = l_ok and all(len(z) % 3 == 0 and _zahlen_ok(z) for v in (l_ or {}).values() for z in v)
    if not schlecht and not rest and idx_ok and zug_ok and wk_ok and tf_ok:
        return netz, ""
    out = dict(netz)
    if not tf_ok:                # Flächenkatalog passt nicht (älteres/geändertes Netz): ohne, Messung am Netz
        out.pop("tf", None)
        out.pop("fk", None)
    tf = out.get("tf")
    bad = set(schlecht)
    if bad:
        gut = next((i for i in range(n) if i not in bad), None)
        if gut is None:
            return None, f"Modell fehlerhaft: alle {n} Punkte ungültig (keine Zahl, unendlich oder zu groß)."
        q = p[:3 * n]
        ersatz = q[3 * gut:3 * gut + 3]
        for i in bad:
            q[3 * i:3 * i + 3] = ersatz          # Platz behalten (Nummern bleiben), Lage eines gültigen Punkts
        out["p"] = q
        teile.append(_anzahl(len(bad), "ungültiger Punkt", "ungültige Punkte"))
    elif rest:
        out["p"] = p[:3 * n]
    weg = 0
    if not t_ok:
        out["t"], weg = {}, -1
        out.pop("ti", None)
    elif t:
        neu_t, neu_ti, neu_tf = {}, {}, {}
        for art, idx in t.items():
            kn = (ti or {}).get(art) if isinstance(ti, dict) else None
            kf = (tf or {}).get(art) if isinstance(tf, dict) else None
            behalten, kennung, katalog = [], [], []
            for m in range(0, len(idx) - 2, 3):
                a, b, c = idx[m], idx[m + 1], idx[m + 2]
                if all(type(x) is int and 0 <= x < n and x not in bad for x in (a, b, c)):
                    behalten += [a, b, c]
                    if isinstance(kn, list):
                        kennung.append(kn[m // 3] if m // 3 < len(kn) else None)
                    if isinstance(kf, list):
                        katalog.append(kf[m // 3])
                else:
                    weg += 1
            weg += (len(idx) % 3 != 0)
            neu_t[art] = behalten
            if isinstance(kn, list):
                neu_ti[art] = kennung
            if isinstance(kf, list):
                neu_tf[art] = katalog
        out["t"] = neu_t
        if isinstance(ti, dict):
            out["ti"] = neu_ti
        if isinstance(tf, dict):
            out["tf"] = neu_tf
    if weg:
        teile.append("Dreiecksliste unlesbar" if weg < 0 else _anzahl(weg, "Dreieck", "Dreiecke") + " mit ungültigen Punkten")
    zuege_weg = 0
    if not l_ok:
        out["l"], zuege_weg = {}, -1
        out.pop("li", None)
        out.pop("ln", None)
    elif l_:
        neu_l, neu_li = {}, {}
        for art, zuege in l_.items():
            kn = (li_ or {}).get(art) if isinstance(li_, dict) else None
            ok_z, ok_k = [], []
            for nr, z in enumerate(zuege):
                if len(z) % 3 == 0 and all(_zahl_ok(c) for c in z):
                    ok_z.append(z)
                    ok_k.append(kn[nr] if isinstance(kn, list) and nr < len(kn) else None)
                else:
                    zuege_weg += 1
            neu_l[art] = ok_z
            if isinstance(kn, list):
                neu_li[art] = ok_k
        out["l"] = neu_l
        if isinstance(li_, dict):
            out["li"] = neu_li
        if zuege_weg:
            out.pop("ln", None)
    if zuege_weg:
        teile.append("Linienliste unlesbar" if zuege_weg < 0 else _anzahl(zuege_weg, "Linienzug", "Linienzüge") + " mit ungültigen Punkten")
    if not wk_ok:
        out.pop("wk", None)
        teile.append("Schnittkörper unlesbar")
    if not teile:            # nur der Flächenkatalog fiel weg: kein Fehler am Modell
        return out, ""
    return out, "Modell fehlerhaft: " + ", ".join(teile) + " ausgelassen – Anzeige und Messung ohne diese Stellen."


def _katalog_ok(netz, t):
    """Flächenkatalog (Messplan M3: 'fk' je STEP-Fläche, 'tf' je Art und Dreieck die Nummer darin) passt zum Netz:
    gleich viele Einträge wie Dreiecke, Nummern im Katalog. Ohne Katalog: True."""
    tf, fk = netz.get("tf"), netz.get("fk")
    if tf is None and fk is None:
        return True
    if not isinstance(tf, dict) or not isinstance(fk, list) or not all(isinstance(e, dict) for e in fk):
        return False
    n = len(fk)
    for art, nrn in tf.items():
        idx = (t or {}).get(art)
        if not isinstance(nrn, list) or idx is None or len(nrn) != len(idx) // 3 or \
                not all(type(x) is int and 0 <= x < n for x in nrn):
            return False
    return True


def gefiltert(netz, modus):
    """Netz für eine Vorschau (MODI); Original gibt das Netz unverändert zurück."""
    if not netz or modus not in MODI[1:]:
        return netz
    out = dict(netz)
    out["t"] = {a: i for a, i in (netz.get("t") or {}).items() if a != "AN"}
    out["l"] = {a: z for a, z in (netz.get("l") or {}).items()
                if (a in ("G", "GA") if modus == "Gravurkonturen" else a != "GA")}
    return out


def ohne_arten(netz, aus):
    """Netz ohne die Flächen- und Linienarten aus (Ebenen ausblenden, Plan 3D-Editor 19.11.2026 A6). Kennungen ('ti',
    'li', 'ln') bleiben den richtigen Dreiecken bzw. Linien zugeordnet; ohne aus kommt das Netz unverändert zurück."""
    if not netz or not aus:
        return netz
    out = dict(netz)
    for schl in ("t", "ti", "tf", "l", "li", "ln"):
        teil = netz.get(schl)
        if isinstance(teil, dict):
            out[schl] = {a: v for a, v in teil.items() if a not in aus}
    if "WK" in aus or any(a in aus for a in WK_ARTEN):
        out.pop("wk", None)
    return out


def mit_anbau(netz):
    return bool(netz) and ("AN" in (netz.get("t") or {}) or "GA" in (netz.get("l") or {}))


def packen(netz):
    """Netz (dict) -> Bytes für die Datenbank."""
    return zlib.compress(json.dumps(netz, separators=(",", ":")).encode("utf-8"), 6)


def entpacken(daten):
    if not daten:
        return None
    try:
        return json.loads(zlib.decompress(daten).decode("utf-8"))
    except (zlib.error, ValueError):
        return None


_lage_merker = {}        # (id(p), Lage) -> (p, Punkte in Einbaulage): Klicks im Satz/Baugruppe ohne Neurechnen
LAGE_MERKEN = 4_000_000  # so viele Zahlen höchstens merken


def _in_lage(p, lage):
    """Punkte p (x, y, z flach) in die Einbaulage (Ursprung, z-Achse, x-Achse), auf 0,01 mm gerundet."""
    schl = (id(p), tuple(lage))
    alt = _lage_merker.get(schl)
    if alt is not None and alt[0] is p:
        return alt[1]
    o, z, x = lage[0:3], lage[3:6], lage[6:9]
    y = (z[1] * x[2] - z[2] * x[1], z[2] * x[0] - z[0] * x[2], z[0] * x[1] - z[1] * x[0])
    o0, o1, o2 = o
    x0, x1, x2 = x
    y0, y1, y2 = y
    z0, z1, z2 = z
    aus = []
    neu = aus.extend
    for i in range(0, len(p) - 2, 3):
        a, b, c = p[i], p[i + 1], p[i + 2]
        neu((round(o0 + a * x0 + b * y0 + c * z0, 2), round(o1 + a * x1 + b * y1 + c * z1, 2),
             round(o2 + a * x2 + b * y2 + c * z2, 2)))
    if sum(len(v[1]) for v in _lage_merker.values()) + len(aus) > LAGE_MERKEN:
        _lage_merker.clear()
    _lage_merker[schl] = (p, aus)
    return aus


def baugruppe(netze, hervor=(), farben=None, fehlend=(), bereiche=None, kosten=None, normteile=(), pruefung=None):
    """Teile einer Baugruppe in ihrer Einbaulage zu einem Netz zusammensetzen. netze: Liste von Netzen (dict oder
    gepackt); farben: je Netz eine Nummer, gleiche Nummer = gleiche Farbe (z. B. gleiche Teile), sonst je Netz eine;
    hervor: Nummern in netze, die als 'gewählte Teile' (Art S) blau, alle anderen hellgrau gefärbt werden;
    fehlend: Nummern der nicht übernehmbaren Teile, immer magenta (Art N), außer sie sind gewählt. Ohne Innenwände und
    Schnittlinien (bei vielen Teilen verdeckt bzw. zu unruhig). Ergebnis: (Netz oder None, Anzahl Teile ohne
    Einbaulage, z. B. aus einer älteren Messung). bereiche: Liste, bekommt je Netz (Nummer, erster Punkt, Ende,
    Dreiecke als Punktnummern) für die Zuordnung eines Modellpunkts zu seinem Teil. kosten: {Nummer in netze: Stufe
    0 … 3} färbt die Teile nach ihrem €-Anteil (kostenfarben.py, Arten KO0 … KO3, mit Legende); gewählte Teile bleiben
    blau. normteile: Nummern der Normteile/Zukaufteile, eigene Farbe (Art NT, mit Legende), außer gewählt.
    pruefung: {Nummer in netze: Art QK/QU/QR/QF} färbt nach der Geometrieprüfung (korrekt, unsicher, reparierbar,
    fehlerhaft); Normteile bleiben NT (ausgeschlossen), gewählte Teile blau."""
    punkte, dreiecke, ohne, wk = [], {}, 0, []
    fk, tf, mit_fk = [], {}, True            # Flächenkatalog der Teile (Messplan M3), nur wenn alle Teile einen haben
    for nr, netz in enumerate(netze):
        if isinstance(netz, (bytes, bytearray, memoryview)):
            netz = entpacken(bytes(netz))
        lage = (netz or {}).get("lage")
        if not netz or not netz.get("p") or not lage or len(lage) != 9:
            ohne += 1
            continue
        p = netz["p"]
        basis = len(punkte) // 3
        punkte += _in_lage(p, lage)
        if netz.get("wk"):              # Schnittkörper der Rohre aus den Eingaben mit in die Einbaulage
            from .schnittkoerper import in_lage
            wk += in_lage(netz["wk"], lage)
        if bereiche is not None:
            bereiche.append((nr, basis, len(punkte) // 3, [basis + i for a, idx in (netz.get("t") or {}).items()
                                                            if a != "I" for i in idx]))
        kat_ok = mit_fk and _katalog_ok(netz, netz.get("t")) and bool(netz.get("tf"))
        mit_fk = kat_ok
        k0 = len(fk)
        if kat_ok:
            fk += netz["fk"]
        for art_teil, idx in (netz.get("t") or {}).items():
            if art_teil == "I":
                continue
            art = "S" if nr in hervor else "N" if nr in fehlend else f"KO{kosten[nr]}" if kosten and nr in kosten \
                else "NT" if pruefung and nr in normteile else pruefung[nr] if pruefung and nr in pruefung \
                else "X" if hervor else "NT" if nr in normteile else \
                f"F{(farben[nr] if farben else nr) % len(TEILFARBEN)}"
            dreiecke.setdefault(art, []).extend(basis + i for i in idx)
            if kat_ok:
                tf.setdefault(art, []).extend(k0 + k for k in netz["tf"][art_teil])
    out = dict(p=punkte, t=dreiecke, l={}, **{"global": True})
    if mit_fk and fk:
        out["fk"], out["tf"] = fk, tf
    if wk:
        out["wk"] = wk
    return (out if punkte else None), ohne


MESS_ABSTAND, MESS_WINKEL = "Abstand", "Winkel"
# Feste Blickrichtungen (3E-11): Name -> Richtung im Modell, die zum Betrachter zeigt (wie der Ansichtswürfel: Rohrachse
# z, Ende A bei z = 0, oben = +y, vorne = −x)
ISOMETRIE = "Isometrie"
BLICKE = (("Vorn", (-1, 0, 0)), ("Hinten", (1, 0, 0)), ("Oben", (0, 1, 0)), ("Unten", (0, -1, 0)),
          ("Ende A", (0, 0, -1)), ("Ende B", (0, 0, 1)))
TASTEN_BLICK = {Qt.Key_1: "Vorn", Qt.Key_2: "Hinten", Qt.Key_3: "Oben", Qt.Key_4: "Unten", Qt.Key_5: "Ende A",
                Qt.Key_6: "Ende B", Qt.Key_0: ISOMETRIE, Qt.Key_F: "einpassen", Qt.Key_V: "vorher"}
NICK_MAX = math.pi / 2  # Blick genau von oben/unten (19.11.2026: die Lage ist eine Matrix, nichts bleibt unbestimmt)


def blick_auf(normale):
    """(gier, nick), damit die Modellrichtung normale zum Betrachter zeigt (_drehung dreht sie auf +z)."""
    nx, ny, nz = normale
    betrag = math.sqrt(nx * nx + ny * ny + nz * nz) or 1.0
    nx, ny, nz = nx / betrag, ny / betrag, nz / betrag
    a, b = nz, -nx                 # Grundstellung (x, y, z) -> (z, y, -x)
    r = math.hypot(a, b)
    gier = math.atan2(-a, b) if r > 1e-9 else 0.0
    nick = max(-NICK_MAX, min(NICK_MAX, math.atan2(ny, r)))
    return gier, nick


def _zahl(w):
    return f"{w:.1f}".replace(".", ",")


_speicher = None        # Datenbank des Benutzers für gemerkte Ansicht-Einstellungen (Perspektive)


def speicher_setzen(db):
    """Datenbank, in der die 3D-Ansichten die Perspektive je Benutzer merken (fenster.py beim Start)."""
    global _speicher
    _speicher = db


def perspektive_vorgabe():
    try:
        return _speicher is not None and _speicher.einstellung(PERSPEKTIVE_EINSTELLUNG) is True
    except Exception:           # Lesemodus, alte Datei
        return False


def koerper_vorgabe():
    """Schnittkörper zeigen (Vorgabe an, je Benutzer gemerkt)."""
    try:
        return _speicher is None or _speicher.einstellung(KOERPER_EINSTELLUNG) is not False
    except Exception:           # Lesemodus, alte Datei
        return True


RASTER_EINSTELLUNG = "ansicht_raster"     # A7: Raster unter dem Modell (Vorgabe aus, je Benutzer gemerkt)
ACHSEN_EINSTELLUNG = "ansicht_achsen"     # A7: Achsenkreuz unten links (Vorgabe an)


def _merker_lesen(name, vorgabe):
    try:
        if _speicher is None:
            return vorgabe
        w = _speicher.einstellung(name)
        return vorgabe if w is None else w is True
    except Exception:           # Lesemodus, alte Datei
        return vorgabe


def _merker_setzen(name, an):
    try:
        if _speicher is not None:
            _speicher.einstellung_setzen(name, bool(an))
    except Exception:           # noqa: BLE001 – Lesemodus: dann eben nicht merken, aber im Protokoll
        from . import protokoll
        protokoll.warnung(f"Ansicht-Einstellung {name} nicht gespeichert")


def aussehen_setzen(werte, merken=False):
    """Aussehen (visualisierung: Material, Licht, Hintergrund, Schatten) ändern und alle offenen 3D-Ansichten neu
    zeichnen; merken: auch in den Einstellungen dieses Arbeitsplatzes speichern (Schnellwahl in der Leiste)."""
    neu = visualisierung.aktuell()
    neu.update({k: v for k, v in (werte or {}).items() if k in visualisierung.NAMEN})
    neu = visualisierung.setzen(neu)
    if merken and _speicher is not None:
        for k in (werte or {}):
            if k in visualisierung.NAMEN:
                try:
                    _speicher.einstellung_setzen(k, neu[k])
                except Exception:       # noqa: BLE001 – Lesemodus: gilt bis zum Programmende
                    from . import protokoll
                    protokoll.warnung(f"Ansicht-Einstellung {k} nicht gespeichert")
    from PySide6.QtWidgets import QApplication
    for w in QApplication.allWidgets() if QApplication.instance() else ():
        if isinstance(w, Ansicht3D):
            w._bild = None
            w.update()
    return neu


def raster_schritt(laenge):
    """Rasterweite [mm] für eine Fläche der Größe laenge: 1-2-5-Reihe, etwa 10 bis 25 Linien."""
    laenge = max(1e-6, float(laenge))
    roh = laenge / 20
    basis = 10 ** math.floor(math.log10(roh))
    for f in (1, 2, 5, 10):
        if basis * f >= roh:
            return basis * f
    return basis * 10


def achsen_bild(gier, nick, roll=0.0):
    """Richtung der Modellachsen X, Y, Z auf dem Bildschirm (x rechts, y nach unten) und Tiefe (z zum Betrachter):
    [(Name, dx, dy, tiefe)] für das Achsenkreuz (A7)."""
    m = _drehung(gier, nick, roll)
    return [(name, m[0][k], -m[1][k], m[2][k]) for k, name in enumerate("XYZ")]


def _koerper_merken(an):
    try:
        if _speicher is not None:
            _speicher.einstellung_setzen(KOERPER_EINSTELLUNG, bool(an))
    except Exception:           # Lesemodus: dann eben nicht merken
        pass


def _perspektive_merken(an):
    try:
        if _speicher is not None:
            _speicher.einstellung_setzen(PERSPEKTIVE_EINSTELLUNG, bool(an))
    except Exception:           # Lesemodus: dann eben nicht merken
        pass


def renderer_setzen(wert):
    """Darstellung für neu geöffnete 3D-Ansichten (RENDERER; Unbekanntes = Automatisch)."""
    global _renderer
    _renderer = wert if wert in RENDERER else RENDERER[0]


def _remote_desktop():
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        return bool(ctypes.windll.user32.GetSystemMetrics(0x1000))       # SM_REMOTESESSION
    except (OSError, AttributeError):
        return False


def renderer_waehlen():
    """("OpenGL" | "Software", Grund) für eine neue Ansicht nach Einstellung, Rechner und bisherigen Fehlern."""
    if _renderer == "Software":
        return "Software", "Einstellung Software"
    if _gl_fehler:
        return "Software", f"OpenGL gescheitert: {_gl_fehler}"
    if _renderer == "Automatisch" and _remote_desktop():
        return "Software", "Remote-Desktop"
    try:
        from .ansicht3d_gl import gl_moeglich
    except ImportError as e:            # PySide6 ohne OpenGL-Module
        return "Software", f"OpenGL fehlt: {e}"
    ok, grund = gl_moeglich()
    return ("OpenGL", grund) if ok else ("Software", grund)


def koerper_lesen(wk):
    """Schnittkörper aus netz['wk'] (schnittkoerper.py): [dict(id, art, text, dreiecke [(a, b, c, Normale)],
    ringe (außen, innen), punkte)]. Seitenflächen zwischen den Ringen, dazu die beiden Deckel."""
    out = []
    for k in wk or ():
        try:
            koerper = _koerper_lesen(k)
        except (TypeError, ValueError, IndexError, AttributeError):
            koerper = None                  # unlesbarer Schnittkörper: weglassen statt abstürzen (V1)
        if koerper is not None:
            out.append(koerper)
    return out


def _koerper_lesen(k):
    """Ein Schnittkörper aus netz['wk'] oder None (zu wenig Punkte bzw. keine Fläche)."""
    o, u = k.get("o") or [], k.get("u") or []
    if not all(_zahl_ok(c) for c in list(o) + list(u) + list(k.get("dr") or ())):
        return None
    ro = [tuple(o[i:i + 3]) for i in range(0, len(o) - 2, 3)]
    ri = [tuple(u[i:i + 3]) for i in range(0, len(u) - 2, 3)]
    dr = k.get("dr") or []          # Körper aus der STEP-Datei: Dreiecke direkt, Linien li
    if (len(ro) < 3 or len(ro) != len(ri)) and not dr:
        return None
    tris = []

    def drei(a, b, c):
        v1 = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
        v2 = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
        n = (v1[1] * v2[2] - v1[2] * v2[1], v1[2] * v2[0] - v1[0] * v2[2], v1[0] * v2[1] - v1[1] * v2[0])
        betrag = math.sqrt(n[0] ** 2 + n[1] ** 2 + n[2] ** 2)
        if betrag > 1e-12:
            tris.append((a, b, c, (n[0] / betrag, n[1] / betrag, n[2] / betrag)))
    n = len(ro)
    for i in range(n):
        j = (i + 1) % n
        drei(ro[i], ro[j], ri[j])
        drei(ro[i], ri[j], ri[i])
    d = k.get("d") or []
    for q in range(0, len(d) - 2, 3):
        i, j, m = d[q], d[q + 1], d[q + 2]
        if max(i, j, m) < n:
            drei(ro[i], ro[j], ro[m])
            drei(ri[i], ri[m], ri[j])
    for q in range(0, len(dr) - 8, 9):
        drei(tuple(dr[q:q + 3]), tuple(dr[q + 3:q + 6]), tuple(dr[q + 6:q + 9]))
    # Linienzüge (geschlossen: erster Punkt am Ende wiederholt)
    zuege = [ro + ro[:1], ri + ri[:1]] if ro else []
    zuege += [[tuple(z[i:i + 3]) for i in range(0, len(z) - 2, 3)] for z in k.get("li") or ()]
    if not tris:
        return None
    if not all(_zahl_ok(c) for z in zuege for q in z for c in q):
        return None                         # Punkte mit NaN/unendlich: weglassen (V1)
    return dict(id=k.get("id"), art=k.get("art") if k.get("art") in WK_ARTEN else "WR",
                text=k.get("t") or "", dreiecke=tris, ringe=[z for z in zuege if len(z) >= 2],
                punkte=[q for t in tris for q in t[:3]], auf=bool(k.get("auf")))


class Modell:
    """Aufbereitetes Netz: Punkte, Dreiecke (i, j, k, Art, Normale), Liniensegmente (a, b, Art, Normale)."""

    def __init__(self, netz, geprueft=False):
        """geprueft: das Netz kam schon durch netz_pruefen (Ansicht3D.setzen) – nicht ein zweites Mal prüfen (A2)."""
        if geprueft:
            self.pruef_meldung = ""
        else:
            netz, self.pruef_meldung = netz_pruefen(netz)    # V1: nie mit NaN/falschen Nummern zeichnen
        netz = netz or {}
        p = netz.get("p") or []
        self.punkte = [(p[i], p[i + 1], p[i + 2]) for i in range(0, len(p) - 2, 3)]
        xs, ys, zs = ([q[k] for q in self.punkte] or [0] for k in range(3))
        self.min = (min(xs), min(ys), min(zs))
        self.max = (max(xs), max(ys), max(zs))
        self.mitte = tuple((a + b) / 2 for a, b in zip(self.min, self.max))
        self.groesse = max(1e-6, math.dist(self.min, self.max))
        laenge = self.max[2] - self.min[2]
        self.dreiecke = []
        self.dreiecke_id = []                   # je Dreieck: Merkmal (netz 'ti', Teile-Editor) – leer ohne 'ti'
        # Flächenkatalog der STEP-Messung (Messplan M3): je Dreieck die STEP-Fläche (Nummer in self.katalog) – leer
        # ohne 'tf'/'fk' (Editor-Teile, ältere Messungen)
        self.katalog = list(netz.get("fk") or []) if netz.get("tf") else []
        self.dreiecke_f = []
        kennung = netz.get("ti") or {}
        katalog = netz.get("tf") or {} if self.katalog else {}
        for art, idx in (netz.get("t") or {}).items():
            kn = kennung.get(art) or []
            kf = katalog.get(art) or []
            for n in range(0, len(idx) - 2, 3):
                if self._dreieck(idx[n], idx[n + 1], idx[n + 2], art):
                    if kennung:
                        self.dreiecke_id.append(kn[n // 3] if n // 3 < len(kn) else None)
                    if self.katalog:
                        self.dreiecke_f.append(kf[n // 3] if n // 3 < len(kf) else None)
        self.linien = []
        self.linien_id = []                     # je Liniensegment: Merkmal (netz 'li', Teile-Editor) oder None
        self.mitten = []                        # Mitte je Konturlinie (Messen fängt Kreismitten)
        normalen = netz.get("ln") or {}         # Normale je Linienzug (Blech), sonst radial zur Rohrachse
        kennung = netz.get("li") or {}
        for art, zuege in (netz.get("l") or {}).items():
            for nr, zug in enumerate(zuege):
                pk = [(zug[i], zug[i + 1], zug[i + 2]) for i in range(0, len(zug) - 2, 3)]
                n = (normalen.get(art) or [])[nr] if nr < len(normalen.get(art) or []) else None
                kn = (kennung.get(art) or [])[nr] if nr < len(kennung.get(art) or []) else None
                self.linien_id += [kn] * max(len(pk) - 1, 0)
                if art in ("K", "G") and len(pk) >= 4:
                    ring = pk[:-1] if pk[0] == pk[-1] else pk
                    self.mitten.append(tuple(sum(q[i] for q in ring) / len(ring) for i in range(3)))
                for a, b in zip(pk, pk[1:]):
                    if n is None:
                        m = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
                        r = math.hypot(m[0], m[1]) or 1.0
                        self.linien.append((a, b, art, (m[0] / r, m[1] / r, 0.0)))
                    else:
                        self.linien.append((a, b, art, tuple(n)))
        self.koerper = koerper_lesen(netz.get("wk"))
        self.arten = sorted({d[3] for d in self.dreiecke} | {l[2] for l in self.linien} |
                            {k["art"] for k in self.koerper}, key=lambda a: REIHE.index(a) if a in REIHE else 99)
        self.laenge = laenge
        self._grob = None

    def grob(self, anzahl=None):
        """Grobe Stufe für große Netze (Baugruppen) beim Drehen und Zoomen: nur die anzahl (Vorgabe GROB_DREIECKE)
        größten Dreiecke (lange Rohrwände, Blechflächen; kleine Rundungen, Bohrungen und Fasen fallen weg), ohne
        Linien. Punkte, Mitte und Größe bleiben, damit das Bild beim Umschalten nicht springt. Kleine Netze: das
        Modell. Gemerkt je anzahl (die Ansicht passt sie an die gemessene Zeichenzeit an, V3)."""
        anzahl = anzahl or GROB_DREIECKE
        if len(self.dreiecke) <= anzahl:
            return self
        merker = self.__dict__.setdefault("_grob_je", {})
        if anzahl in merker:
            return merker[anzahl]
        if self._grob is None or len(self._grob.dreiecke) != anzahl:
            p = self.punkte

            def flaeche(d):
                a, b, c = p[d[0]], p[d[1]], p[d[2]]
                u = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
                v = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
                return ((u[1] * v[2] - u[2] * v[1]) ** 2 + (u[2] * v[0] - u[0] * v[2]) ** 2
                        + (u[0] * v[1] - u[1] * v[0]) ** 2)
            g = Modell.__new__(Modell)
            g.__dict__.update(self.__dict__)
            neu, g.punkte, g.dreiecke = {}, [], []
            ff = self.dreiecke_f if len(getattr(self, "dreiecke_f", ())) == len(self.dreiecke) else None
            g.dreiecke_f = []
            reihe = sorted(range(len(self.dreiecke)), key=lambda nr: flaeche(self.dreiecke[nr]), reverse=True)
            for nr in reihe[:anzahl]:
                i, j, k, art, n = self.dreiecke[nr]
                for x in (i, j, k):
                    if x not in neu:
                        neu[x] = len(g.punkte)
                        g.punkte.append(p[x])
                g.dreiecke.append((neu[i], neu[j], neu[k], art, n))
                if ff is not None:
                    g.dreiecke_f.append(ff[nr])     # Flächenkatalog bleibt passend (Darstellung Flächentypen)
            g.__dict__.pop("_typen", None)
            g.linien, g.linien_id, g.dreiecke_id, g.koerper = [], [], [], []
            g._glatt = None
            g._grob = g
            g._grob_je = {}
            self._grob = g
        merker[anzahl] = self._grob
        return self._grob

    def glatte_normalen(self):
        """Normale je Ecke für glatte Rundungen (OpenGL schattiert zwischen den Ecken): Mittel der Flächennormalen
        aller Dreiecke an derselben Stelle, gewichtet mit der Fläche, nur über glatte Übergänge (Knick flacher als
        KANTEN_WINKEL) – Kanten wie Rohrwand/Stirnfläche oder scharfe Profilecken bleiben scharf. [(n_i, n_j, n_k)]
        je Dreieck; große Netze: None (flach)."""
        if getattr(self, "_glatt", 0) != 0:
            return self._glatt
        self._glatt = None
        if not self.dreiecke or len(self.dreiecke) > GLATT_MAX:
            return None
        p = self.punkte
        orte = {}
        gewicht = []
        for nr, (i, j, k, _, n) in enumerate(self.dreiecke):
            a, b, c = p[i], p[j], p[k]
            u = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
            v = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
            f = math.sqrt((u[1] * v[2] - u[2] * v[1]) ** 2 + (u[2] * v[0] - u[0] * v[2]) ** 2
                          + (u[0] * v[1] - u[1] * v[0]) ** 2)
            gewicht.append(f)
            for x in (i, j, k):
                orte.setdefault((round(p[x][0], 2), round(p[x][1], 2), round(p[x][2], 2)), []).append(nr)
        out = []
        for i, j, k, _, n in self.dreiecke:
            ecken = []
            for x in (i, j, k):
                s = [0.0, 0.0, 0.0]
                for m in orte[(round(p[x][0], 2), round(p[x][1], 2), round(p[x][2], 2))]:
                    q = self.dreiecke[m][4]
                    if q[0] * n[0] + q[1] * n[1] + q[2] * n[2] > KANTEN_WINKEL:
                        w = gewicht[m]
                        s[0] += q[0] * w
                        s[1] += q[1] * w
                        s[2] += q[2] * w
                betrag = math.sqrt(s[0] ** 2 + s[1] ** 2 + s[2] ** 2)
                ecken.append((s[0] / betrag, s[1] / betrag, s[2] / betrag) if betrag > 1e-12 else n)
            out.append(ecken)
        self._glatt = out
        return out

    def ebenen(self):
        """Ebene Flächen (3E-11, Messen und Tangentenkanten): (je Dreieck Nummer der Ebene, je Ebene dict(n, d,
        flaeche, dreiecke)) – Dreiecke gleicher Normale und gleichen Abstands vom Ursprung (n·p = d) gehören zu einer
        Ebene. Einmal je Modell gerechnet; große Netze: keine."""
        if getattr(self, "_ebenen", None) is not None:
            return self._ebenen
        nummer, liste, schl = [], [], {}
        if len(self.dreiecke) <= KANTEN_MAX:
            p = self.punkte
            for i, j, k, _, n in self.dreiecke:
                a, b, c = p[i], p[j], p[k]
                u = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
                v = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
                f = math.sqrt((u[1] * v[2] - u[2] * v[1]) ** 2 + (u[2] * v[0] - u[0] * v[2]) ** 2
                              + (u[0] * v[1] - u[1] * v[0]) ** 2) / 2
                d = sum(n[q] * (a[q] + b[q] + c[q]) / 3 for q in range(3))
                key = (round(n[0], 3), round(n[1], 3), round(n[2], 3), round(d, 1))
                nr = schl.get(key)
                if nr is None:
                    nr = schl[key] = len(liste)
                    liste.append(dict(n=n, d=d, flaeche=0.0, dreiecke=[]))
                liste[nr]["flaeche"] += f
                liste[nr]["dreiecke"].append(len(nummer))
                nummer.append(nr)
        self._ebenen = (nummer, liste)
        return self._ebenen

    def _kanten_rechnen(self, grenze=KANTEN_WINKEL):
        from . import tempo           # Supportpaket 24.11.2026: Abschnitt im Zeitwächter (nur Oberfläche)
        with tempo.abschnitt("3D: Kanten rechnen"):
            return self._kanten_rechnen_roh(grenze)

    def _kanten_rechnen_roh(self, grenze=KANTEN_WINKEL):
        """Körperkanten und glatte Übergänge (für Umrisslinien) suchen: (kanten, glatte, klassen). grenze: cos des
        Erkennungswinkels (Einstellung Kantenwinkel): flachere Übergänge sind keine Kante, Netzdreiecke in einer
        Fläche nie. klassen je Kante: KANTE_AUSSEN oder KANTE_INNEN (nur Innenwand: Innenecken, Lochränder innen,
        Innenkante der Stirnfläche)."""
        kanten, glatte, klassen = [], [], []
        if len(self.dreiecke) > KANTEN_MAX:
            return kanten, glatte, klassen
        p = self.punkte
        nummer, ebenen = self.ebenen()
        gross = 0.1 * max((e["flaeche"] for e in ebenen), default=0.0)     # „große“ ebene Fläche

        def schl(i):
            return (round(p[i][0], 2), round(p[i][1], 2), round(p[i][2], 2))
        seiten = {}
        for nr, (i, j, k, _, n) in enumerate(self.dreiecke):
            a, b, c = schl(i), schl(j), schl(k)
            for x, y in ((a, b), (b, c), (c, a)):
                if x != y:
                    seiten.setdefault((x, y) if x < y else (y, x), []).append(nr)
        flaeche_nr = self.dreiecke_f if len(self.dreiecke_f) == len(self.dreiecke) else None
        breiten = {}

        def breite(e, a, b):
            """Breite der ebenen Fläche e quer zur Kante a-b: Fläche / Ausdehnung längs der Kante."""
            r = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
            lg = math.sqrt(sum(c * c for c in r)) or 1.0
            r = tuple(c / lg for c in r)
            key = (id(e), round(r[0], 2), round(r[1], 2), round(r[2], 2))
            if key not in breiten:
                t = [sum(p[x][q] * r[q] for q in range(3)) for d in e["dreiecke"] for x in self.dreiecke[d][:3]]
                breiten[key] = e["flaeche"] / max(max(t) - min(t), 1e-6)
            return breiten[key]
        for (a, b), drei in seiten.items():
            ns = [self.dreiecke[d][4] for d in drei]
            if len(ns) == 2 and flaeche_nr is not None and flaeche_nr[drei[0]] is not None \
                    and flaeche_nr[drei[0]] == flaeche_nr[drei[1]]:
                # 20.11.2026 (Patrick: Linien mitten im Rohr): zwei Dreiecke derselben STEP-Fläche (Flächenkatalog
                # der Messung) – nie eine Kante, auch wenn die Vernetzung um ein Loch schmale Dreiecke mit
                # abweichender Normale oder kleine „Ebenen“ neben langen Streifen erzeugt
                glatte.append((a, b, ns[0], ns[1]))
                continue
            if len(ns) == 2:
                cos = sum(ns[0][q] * ns[1][q] for q in range(3))
                e0, e1 = ebenen[nummer[drei[0]]], ebenen[nummer[drei[1]]]
                # Tangentenkante: Übergang einer großen ebenen Fläche in eine Rundung (z. B. Eckradius eines
                # Quadratrohrs), wie die Kanten im CAD
                f0, f1 = sorted((e0["flaeche"], e1["flaeche"]))
                tangente = e0 is not e1 and cos < 0.99995 and f1 >= gross and f1 > 3 * f0
                if tangente and flaeche_nr is None:
                    # ohne Flächenkatalog (ältere Messung, Editor): nur wenn die ebene Fläche quer zur Kante
                    # deutlich breiter ist als die Facette daneben – sonst ist es ein Streifen derselben Rundung
                    # (Rundrohr: lange Facetten neben den kleinen um ein Loch)
                    gr, kl = (e1, e0) if e1["flaeche"] >= e0["flaeche"] else (e0, e1)
                    w = breite(gr, a, b)
                    tangente = w >= TANGENTE_BREITE and w >= 3 * breite(kl, a, b)
                if cos > grenze and not tangente:
                    glatte.append((a, b, ns[0], ns[1]))
                    continue
            n = tuple(sum(x[q] for x in ns[:2]) for q in range(3))
            betrag = math.sqrt(sum(c * c for c in n)) or 1.0
            kanten.append((a, b, tuple(c / betrag for c in n)))
            arten = {self.dreiecke[d][3] for d in drei}
            klassen.append(KANTE_INNEN if "I" in arten and not arten & AUSSEN_ARTEN else KANTE_AUSSEN)
        return kanten, glatte, klassen

    def kanten(self):
        """Körperkanten für „Mit Kanten“, Drahtgitter und Verdeckt: [(a, b, Normale)] – Ränder des Netzes, Knicke
        zwischen zwei Dreiecken (stumpfer als KANTEN_WINKEL) und Tangentenkanten (ebene Fläche → Rundung). Punkte
        gleicher Lage gelten als derselbe Punkt (das Netz hat je Dreieck eigene Punkte). Einmal je Modell gerechnet
        (V3: meist schon im Hintergrund vorgerechnet, vorrechnen); große Netze: keine. Erkennungswinkel aus der
        Einstellung (visualisierung.kanten_stil), je Winkel einmal gerechnet."""
        self._kanten_sicher()
        return self._kanten

    def kanten_klassen(self):
        """Je Körperkante (gleiche Reihenfolge wie kanten()) KANTE_AUSSEN oder KANTE_INNEN."""
        self._kanten_sicher()
        return self._kanten_klassen

    def glatte_kanten(self):
        """Glatte Übergänge [(a, b, Normale 1, Normale 2)]: wo eine Seite zum Betrachter zeigt und die andere nicht,
        liegt der Umriss (Rundrohr im Drahtgitter)."""
        self._kanten_sicher()
        return self._glatt_kanten

    def _kanten_sicher(self, grenze=None):
        grenze = visualisierung.kanten_stil()["cos"] if grenze is None else grenze
        if getattr(self, "_glatt_kanten", None) is not None and getattr(self, "_kanten", None) is not None \
                and getattr(self, "_kanten_grenze", None) == grenze:
            return
        with _KANTEN_SPERRE:            # V3: Hintergrund und Oberfläche rechnen nie dasselbe doppelt
            if getattr(self, "_glatt_kanten", None) is None or getattr(self, "_kanten", None) is None \
                    or getattr(self, "_kanten_grenze", None) != grenze:
                kanten, glatt, klassen = self._kanten_rechnen(grenze)
                self._glatt_kanten, self._kanten_klassen = glatt, klassen
                self._kanten, self._kanten_grenze = kanten, grenze

    def _dreieck(self, i, j, k, art):
        a, b, c = self.punkte[i], self.punkte[j], self.punkte[k]
        u = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
        v = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
        n = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
        betrag = math.sqrt(n[0] ** 2 + n[1] ** 2 + n[2] ** 2)
        if betrag < 1e-12:
            return False
        self.dreiecke.append((i, j, k, art, (n[0] / betrag, n[1] / betrag, n[2] / betrag)))
        return True


_TASTE = {Qt.LeftButton: "links", Qt.MiddleButton: "mitte", Qt.RightButton: "rechts"}


def _zusatz(mods):
    """Zusatztasten für navigation3d.aktion."""
    return {n for n, m in (("umschalt", Qt.ShiftModifier), ("strg", Qt.ControlModifier)) if mods & m}


_KANTEN_SPERRE = threading.RLock()
VORRECHNEN_AB = 4000        # V3: ab so vielen Dreiecken Körperkanten nach dem Laden im Hintergrund vorrechnen
_vorrechnen = {"naechstes": None, "lauf": None}


def vorrechnen(modell):
    """Körperkanten und Umrisskanten eines großen Modells im Hintergrund rechnen (V3, 3D-Visualisierung): der erste
    Klick auf „Mit Kanten“, Drahtgitter oder eine Fläche wartet dann nicht mehr. Nur das neueste Modell wird gerechnet
    (der Editor setzt bei jeder Eingabe ein neues); rechnet nichts am Netz, nur Anzeigedaten."""
    if modell is None or not VORRECHNEN_AB <= len(modell.dreiecke) <= KANTEN_MAX:
        return False
    _vorrechnen["naechstes"] = weakref.ref(modell)
    lauf = _vorrechnen["lauf"]
    if lauf is None or not lauf.is_alive():
        lauf = threading.Thread(target=_vorrechnen_lauf, name="3D-Vorrechnen", daemon=True)
        _vorrechnen["lauf"] = lauf
        lauf.start()
    return True


def _vorrechnen_lauf():
    while True:
        ref, _vorrechnen["naechstes"] = _vorrechnen["naechstes"], None
        modell = ref() if ref is not None else None
        if modell is None:
            return
        try:
            modell.glatte_kanten()
        except Exception:       # noqa: BLE001 – nur Vorarbeit: die Ansicht rechnet sonst beim ersten Gebrauch
            from . import protokoll
            protokoll.warnung("3D: Körperkanten im Hintergrund nicht vorgerechnet")


def vorrechnen_warten(s=30.0):
    """Tests: bis das Vorrechnen fertig ist."""
    lauf = _vorrechnen["lauf"]
    if lauf is not None:
        lauf.join(s)


def _drehung(gier, nick, roll=0.0):
    """Drehmatrix: erst um die Hochachse (gier), dann kippen (nick), dann um die Blickachse (roll; 19.11.2026 freie
    360°-Drehung, navigation3d). Bildschirm: x rechts, y oben, z zum Betrachter. Rohrachse Z liegt in der
    Grundstellung waagerecht (nach rechts): Modell (x, y, z) -> (z, y, -x)."""
    return navigation3d.matrix(gier, nick, roll)


def persp_faktor(modell, perspektive):
    """1 / Kameraabstand für die Perspektive (0 = orthogonal)."""
    return 1.0 / (PERSPEKTIVE_ABSTAND * modell.groesse) if perspektive else 0.0


_letzte_projektion = [None, None]      # (Schlüssel, Ergebnis) der letzten Projektion: Drehen um den Mauszeiger
#                                        rechnet sie vor dem Zeichnen, das Zeichnen nimmt sie dann aus dem Speicher


def _projektion_roh(modell, breite, hoehe, gier, nick, zoom=1.0, verschiebung=(0.0, 0.0), perspektive=False, roll=0.0):
    schluessel = (modell, breite, hoehe, gier, nick, zoom, bool(perspektive), roll)
    if _letzte_projektion[0] is not None and _letzte_projektion[0][0] is modell and \
            _letzte_projektion[0][1:] == schluessel[1:]:
        m, proj, roh, massstab = _letzte_projektion[1]
        return m, proj, roh, massstab, breite / 2 + verschiebung[0], hoehe / 2 + verschiebung[1]
    m = _drehung(gier, nick, roll)
    cx, cy, cz = modell.mitte
    pz = persp_faktor(modell, perspektive)
    proj, roh = [], []
    for x, y, z in modell.punkte:
        x, y, z = x - cx, y - cy, z - cz
        q = (m[0][0] * x + m[0][1] * y + m[0][2] * z, m[1][0] * x + m[1][1] * y + m[1][2] * z,
             m[2][0] * x + m[2][1] * y + m[2][2] * z)
        roh.append(q)
        if pz:
            f = 1.0 / (1.0 - q[2] * pz)
            q = (q[0] * f, q[1] * f, q[2])
        proj.append(q)
    massstab = zoom * 0.92 * min(breite, hoehe * 3) / modell.groesse
    if proj:
        bx = max(abs(q[0]) for q in proj) * 2 or 1
        by = max(abs(q[1]) for q in proj) * 2 or 1
        massstab = zoom * 0.9 * min(breite / bx, hoehe / by)
    fest = getattr(modell, "rahmen_fest", None)     # Explosion: beim Ziehen bleibt der Maßstab stehen
    if fest is not None and fest[0] == (breite, hoehe, gier, nick, bool(perspektive), roll):
        massstab = zoom * fest[1]
    _letzte_projektion[:] = [schluessel, (m, proj, roh, massstab)]
    return m, proj, roh, massstab, breite / 2 + verschiebung[0], hoehe / 2 + verschiebung[1]


def projektion(modell, breite, hoehe, gier, nick, zoom=1.0, verschiebung=(0.0, 0.0), perspektive=False, roll=0.0):
    """Gedrehte Punkte (x, y, Tiefe) um die Mitte, Maßstab und Bildmitte wie beim Zeichnen mit QPainter.
    perspektive: x, y schon mit dem Faktor der Perspektive (näher = größer)."""
    m, proj, _, massstab, ox, oy = _projektion_roh(modell, breite, hoehe, gier, nick, zoom, verschiebung, perspektive,
                                                   roll)
    return m, proj, massstab, ox, oy


def sicht(n, q, pz):
    """Anteil der gedrehten Normale n zum Betrachter am gedrehten Ort q (> 0 = Vorderseite); orthogonal n.z."""
    if not pz:
        return n[2]
    return -n[0] * q[0] * pz - n[1] * q[1] * pz + n[2] * (1.0 - q[2] * pz)


def _blass(c, an):
    """Farbe für „nur Gewähltes hervorheben“: zu Weiß gemischt."""
    if not an:
        return c
    return QColor(*(int(x + (255 - x) * BLASS) for x in (c.red(), c.green(), c.blue())))


def hintergrund_bei(y, hoehe):
    """Farbe des Hintergrundverlaufs in Bildzeile y (0 = oben)."""
    f = max(0.0, min(1.0, y / max(1, hoehe - 1)))
    o, u = hintergrund_farben()
    return QColor(round(o.red() + (u.red() - o.red()) * f), round(o.green() + (u.green() - o.green()) * f),
                  round(o.blue() + (u.blue() - o.blue()) * f))


def hintergrund_farben():
    """(oben, unten) des Hintergrunds nach dem Aussehen (visualisierung, V2). „Verlauf“ und das dunkle Theme nehmen
    die Theme-Farben HINTERGRUND_OBEN/HINTERGRUND (bleiben im Dunkelmodus dunkel); sonst die gewählten Farben."""
    o, u = visualisierung.hintergrund()
    if visualisierung.aktuell()["ansicht3d_hintergrund"] == visualisierung.VERLAUF or HINTERGRUND.lightness() < 128:
        return HINTERGRUND_OBEN, HINTERGRUND
    return QColor(o), QColor(u)


def hintergrund_malen(p, rechteck):
    oben, unten = hintergrund_farben()
    verlauf = QLinearGradient(0, rechteck.top(), 0, rechteck.bottom())
    verlauf.setColorAt(0.0, oben)
    verlauf.setColorAt(1.0, unten)
    p.fillRect(rechteck, QBrush(verlauf))


def licht_wert(nx, ny, nz, werte=None):
    """(Faktor für die Farbe, Glanz-Zugabe 0..1) zur Normalen in Bildkoordinaten (zum Betrachter gedreht). Licht und
    Glanz nach Lichtprofil und Material (visualisierung.beleuchten, dieselbe Formel wie im OpenGL-Shader)."""
    return visualisierung.beleuchten((nx, ny, nz), werte)


SORTIER_TEIL = 0.045    # Software-Zeichnen: längere Dreiecke (Anteil der Modellgröße) fürs Sortieren teilen
SORTIER_PIXEL = 16.0    # … aber keine Stücke unter so vielen Bildpunkten


def _sortier_teile(a, b, c, grenze2, tiefe=0):
    """Ein gedrehtes Dreieck (Bildpunkte mit Tiefe) für das Sortieren von hinten nach vorn in Stücke teilen, deren
    längste Seite höchstens √grenze2 ist (immer die längste Seite halbieren, höchstens 9 Stufen). Lange, schmale
    Dreiecke (Profilwände) lagen sonst nach ihrer Mitte falsch vor- bzw. hintereinander, z. B. schien der Schenkel
    eines L-Profils durch die vordere Wand. Gezeichnet wird dieselbe Fläche, nur in Stücken; das Netz bleibt."""
    ab = (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2
    bc = (b[0] - c[0]) ** 2 + (b[1] - c[1]) ** 2 + (b[2] - c[2]) ** 2
    ca = (c[0] - a[0]) ** 2 + (c[1] - a[1]) ** 2 + (c[2] - a[2]) ** 2
    laengste = max(ab, bc, ca)
    if laengste <= grenze2 or tiefe >= 9:
        return ((a, b, c),)
    if laengste == bc:
        a, b, c = b, c, a
    elif laengste == ca:
        a, b, c = c, a, b
    m = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2, (a[2] + b[2]) / 2)        # Mitte der längsten Seite a-b
    return _sortier_teile(a, m, c, grenze2, tiefe + 1) + _sortier_teile(m, b, c, grenze2, tiefe + 1)


def flaechentyp_arten(modell):
    """Je Dreieck die Farbart „FT_<Flächenart>“ aus dem Flächenkatalog der STEP (Darstellung Flächentypen); ohne
    passenden Katalog (ältere Messung) überall FT_Netz. Nur Anzeige: das Netz bleibt."""
    merk = getattr(modell, "_typen", None)
    if merk is not None:
        return merk
    n = len(modell.dreiecke)
    kat = getattr(modell, "katalog", None) or []
    nummern = getattr(modell, "dreiecke_f", None) or []
    namen = [f"FT_{e.get('a')}" if f"FT_{e.get('a')}" in FARBE else "FT_Netz" for e in kat]
    if kat and len(nummern) == n:
        typen = [namen[x] if 0 <= x < len(namen) else "FT_Netz" for x in nummern]
    else:
        typen = ["FT_Netz"] * n
    modell._typen = typen
    return typen


def flaechen_farben():
    """Farbe je Flächenart fürs Zeichnen: FARBE, die neutralen Flächen (Außen-, Innenwand, Blech) in der Farbe des
    gewählten Materials (V2); Signalfarben (Konturen, Gravur, Nähte, Teilfarben …) bleiben."""
    farben = dict(FARBE)
    for art in (*visualisierung.MATERIAL_ARTEN, "I"):
        hexwert = visualisierung.flaechenfarbe(art)
        if hexwert:
            farben[art] = QColor(hexwert)
    return farben


def umriss(modell, m, pz=0.0):
    """Umrisslinien glatter Rundungen für die aktuelle Drehung m: [(a, b, True)] – Übergänge, an denen eine Seite
    zum Betrachter zeigt und die andere nicht."""
    cx, cy, cz = modell.mitte
    out = []
    for a, b, n1, n2 in modell.glatte_kanten():
        if pz:
            q = tuple(sum(m[r][c] * ((a[c] + b[c]) / 2 - (cx, cy, cz)[c]) for c in range(3)) for r in range(3))
        else:
            q = (0.0, 0.0, 0.0)
        s1 = sicht(tuple(m[r][0] * n1[0] + m[r][1] * n1[1] + m[r][2] * n1[2] for r in range(3)), q, pz)
        s2 = sicht(tuple(m[r][0] * n2[0] + m[r][1] * n2[1] + m[r][2] * n2[2] for r in range(3)), q, pz)
        if (s1 > 0) != (s2 > 0):
            out.append((a, b, True))
    return out


class _Verdeckung:
    """Software-Weg (20.11.2026): Verdeckung je Punkt über ein Raster der gezeichneten, deckenden Dreiecke im Bild
    (gedrehte Koordinaten, z zum Betrachter). Kanten und Konturen werden in kurze Stücke geteilt und je Stück geprüft:
    sichtbare durchgezogen, verdeckte gestrichelt oder gar nicht – keine Linien mehr durch fremde Teile oder durch die
    Rohrwand (vorher lag jede zum Betrachter zeigende Kante obenauf)."""

    def __init__(self, zelle, eps):
        self.zelle, self.eps, self.raster, self.sortiert = zelle, eps, {}, set()

    def dazu(self, a, b, c):
        z = self.zelle
        x0, x1 = int(math.floor(min(a[0], b[0], c[0]) / z)), int(math.floor(max(a[0], b[0], c[0]) / z))
        y0, y1 = int(math.floor(min(a[1], b[1], c[1]) / z)), int(math.floor(max(a[1], b[1], c[1]) / z))
        if (x1 - x0 + 1) * (y1 - y0 + 1) > 40000:
            return
        d = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
        if abs(d) < 1e-12:
            return
        zmax = max(a[2], b[2], c[2])
        r = self.raster
        if x0 == x1 and y0 == y1:
            r.setdefault((x0, y0), []).append((a, b, c, d, zmax))
            return
        # Ebene z = ex·x + ey·y + e0: je Zelle höchstens das Maximum an ihren Ecken (lange Rohrwände ragen sonst in
        # jeder Zelle mit ihrem nächsten Ende nach vorn und jede Abfrage prüfte sie)
        ex = ((b[1] - c[1]) * (a[2] - c[2]) + (c[1] - a[1]) * (b[2] - c[2])) / d
        ey = ((c[0] - b[0]) * (a[2] - c[2]) + (a[0] - c[0]) * (b[2] - c[2])) / d
        e0 = c[2] - ex * c[0] - ey * c[1]
        for gx in range(x0, x1 + 1):
            xa, xb = gx * z, (gx + 1) * z
            zx = max(ex * xa, ex * xb)
            for gy in range(y0, y1 + 1):
                zc = min(zmax, zx + max(ey * gy * z, ey * (gy + 1) * z) + e0)
                r.setdefault((gx, gy), []).append((a, b, c, d, zc))

    def verdeckt(self, q):
        z = self.zelle
        schl = (int(math.floor(q[0] / z)), int(math.floor(q[1] / z)))
        liste = self.raster.get(schl)
        if not liste:
            return False
        if schl not in self.sortiert:            # nächste zuerst: verdeckte Punkte treffen früh, der Rest bricht ab
            liste.sort(key=lambda e: -e[4])
            self.sortiert.add(schl)
        qx, qy, grenze = q[0], q[1], q[2] + self.eps
        for a, b, c, d, zmax in liste:
            if zmax <= grenze:
                break
            l1 = ((b[1] - c[1]) * (qx - c[0]) + (c[0] - b[0]) * (qy - c[1])) / d
            if l1 < -1e-9 or l1 > 1 + 1e-9:
                continue
            l2 = ((c[1] - a[1]) * (qx - c[0]) + (a[0] - c[0]) * (qy - c[1])) / d
            l3 = 1 - l1 - l2
            if l2 < -1e-9 or l3 < -1e-9:
                continue
            if l1 * a[2] + l2 * b[2] + l3 * c[2] > grenze:
                return True
        return False

    def stuecke(self, ra, rb, stueck):
        """Strecke ra–rb (gedreht) in Abschnitte gleicher Sichtbarkeit: [(von, bis, sichtbar)]."""
        lg = math.hypot(rb[0] - ra[0], rb[1] - ra[1])
        n = max(1, min(48, int(lg / stueck)))
        out = []
        for i in range(n):
            t0, t1 = i / n, (i + 1) / n
            tm = (t0 + t1) / 2
            q = tuple(ra[k] + (rb[k] - ra[k]) * tm for k in range(3))
            vis = not self.verdeckt(q)
            if out and out[-1][2] == vis:
                out[-1][1] = t1
            else:
                out.append([t0, t1, vis])
        return [(tuple(ra[k] + (rb[k] - ra[k]) * t0 for k in range(3)),
                 tuple(ra[k] + (rb[k] - ra[k]) * t1 for k in range(3)), vis) for t0, t1, vis in out]


def zeichnen(p, modell, breite, hoehe, gier, nick, zoom=1.0, verschiebung=(0.0, 0.0), linien=True, glatt=True,
             darstellung=SCHATTIERT, blass=False, perspektive=False, koerper=False, gewaehlt=(), roll=0.0):
    """Modell in ein Rechteck (0, 0, breite, hoehe) zeichnen. glatt: Kantenglättung (aus = schneller). darstellung:
    DARSTELLUNGEN; blass: alles blass (der Teile-Editor zeichnet das Gewählte kräftig darüber); perspektive: Tiefe
    perspektivisch (sonst orthogonal); koerper: Schnittkörper der Konturen halb durchsichtig dazu, die Merkmale in
    gewaehlt kräftiger. Kanten und Konturen mit echter Verdeckung (_Verdeckung); Dreiecke in modell.durch
    (durchsichtig geschaltete Teile) halb durchsichtig."""
    m, proj, roh, massstab, ox, oy = _projektion_roh(modell, breite, hoehe, gier, nick, zoom, verschiebung,
                                                     perspektive, roll)
    cx, cy, cz = modell.mitte
    pz = persp_faktor(modell, perspektive)
    stil_k = visualisierung.kanten_stil()
    roentgen = darstellung in ROENTGEN_ARTEN
    draht = darstellung in DRAHT_ARTEN
    pruef = darstellung == PRUEFMODUS
    zeige_verdeckt = darstellung in IMMER_VERDECKT or (stil_k["verdeckt"] and darstellung not in OHNE_VERDECKT) \
        or roentgen
    verdeckt_strich = darstellung == VERDECKT
    weiss = VERDECKT_HELL if verdeckt_strich else WEISS_ANTEIL.get(darstellung, 0.0)
    betont = darstellung in (KONTUREN_BETONT, PRUEFMODUS)
    typen = flaechentyp_arten(modell) if darstellung == FLAECHENTYPEN else None
    lw = visualisierung.licht_werte()                       # V2: Lichtprofil und Material einmal je Bild
    farben = flaechen_farben()
    durch = getattr(modell, "durch", None) or ()
    alpha_durch = stil_k["alpha"]
    # Teilen nur, wo es sichtbar ist: Stücke unter SORTIER_PIXEL Bildpunkten nicht weiter (kleine Vorschaubilder der
    # Positionsliste zeichnen sonst 100.000 Stücke)
    grenze2 = max(SORTIER_TEIL * modell.groesse, SORTIER_PIXEL / max(massstab, 1e-9)) ** 2
    # Verdeckung nur fürs volle Bild mit Linien (beim Drehen grob ohne Linien); Röntgen: deckend gilt trotzdem, damit
    # verdeckte Kanten heller gestrichelt erscheinen
    ver = _Verdeckung(max(14.0, VERDECKT_PIXEL * 2) / max(massstab, 1e-9), 0.0005 * modell.groesse + 0.02) \
        if linien and not draht else None
    # Einträge (Schicht, Tiefe, Punkte, Art, Licht bzw. sichtbar, Linie?): Schicht 0 Innenwand, 1 Flächen,
    # 2 Linien und Kanten obenauf (ihre Verdeckung ist schon geprüft), 2.5 durchsichtige Flächen darüber
    liste = []
    if not draht:
        for nr, (i, j, k, art, n) in enumerate(modell.dreiecke):
            nx = m[0][0] * n[0] + m[0][1] * n[1] + m[0][2] * n[2]
            ny = m[1][0] * n[0] + m[1][1] * n[1] + m[1][2] * n[2]
            nz = m[2][0] * n[0] + m[2][1] * n[1] + m[2][2] * n[2]
            if pz:
                ra, rb, rc = roh[i], roh[j], roh[k]
                sz = sicht((nx, ny, nz), ((ra[0] + rb[0] + rc[0]) / 3, (ra[1] + rb[1] + rc[1]) / 3,
                                          (ra[2] + rb[2] + rc[2]) / 3), pz)
            else:
                sz = nz
            klar = (pruef and art in PRUEF_DURCH) or nr in durch      # durchsichtig (Prüfmodus, Teil geschaltet)
            if sz <= 0 and not (roentgen or klar):
                continue                     # Rückseite
            if sz <= 0:
                nx, ny, nz = -nx, -ny, -nz
            a, b, c = proj[i], proj[j], proj[k]
            if ver is not None and not roentgen and not klar:
                ver.dazu(a, b, c)
            # Schicht: Innenwand zuerst, dann die Lochwände der Konturen, dann Flächen, Schweißnaht-Raupen darüber
            # (immer sichtbar wie ihre Linien). Lochwände (K) liegen in der Wand und sind nur durchs Loch zu sehen:
            # nach der Mitte sortiert lagen sie sonst vor den langen Wanddreiecken, und Konturen auf der Rückseite
            # schienen als rote Striche durch die Wand (Patrick 16.11.2026: „Konturen werden komisch dargestellt“)
            schicht = 1.5 if art in NAEHTE else 1 if roentgen else 0 if art == "I" else 0.5 if art == "K" else 1
            farbart, licht = typen[nr] if typen is not None else art, licht_wert(nx, ny, nz, lw)
            if klar:
                schicht, farbart = (1 if roentgen else 1.8), farbart + "~"
            for d in _sortier_teile(a, b, c, grenze2):
                liste.append((schicht, (d[0][2] + d[1][2] + d[2][2]) / 3, d, farbart, licht, False))

    def gedreht(a):
        q = (m[0][0] * (a[0] - cx) + m[0][1] * (a[1] - cy) + m[0][2] * (a[2] - cz),
             m[1][0] * (a[0] - cx) + m[1][1] * (a[1] - cy) + m[1][2] * (a[2] - cz),
             m[2][0] * (a[0] - cx) + m[2][1] * (a[1] - cy) + m[2][2] * (a[2] - cz))
        if not pz:
            return q, q
        f = 1.0 / (1.0 - q[2] * pz)
        return (q[0] * f, q[1] * f, q[2]), q

    def nach_vorn(n, qa, qb):
        nr = tuple(m[r][0] * n[0] + m[r][1] * n[1] + m[r][2] * n[2] for r in range(3))
        return sicht(nr, tuple((qa[r] + qb[r]) / 2 for r in range(3)), pz)
    # große Baugruppen (Software): Stücke länger, damit die Prüfung je Stück das Bild nicht bremst
    stueck = VERDECKT_PIXEL * max(1.0, len(modell.dreiecke) / 40000.0) / max(massstab, 1e-9)

    def strecke(ra, rb, art, verdeckt_art, tiefe_plus=0.0):
        """Linie mit Verdeckung: sichtbare Stücke als art, verdeckte als verdeckt_art (None = weglassen)."""
        if ver is None:
            liste.append((2, (ra[2] + rb[2]) / 2 + tiefe_plus, (ra, rb), art, 1.0, True))
            return
        for a, b, vis in ver.stuecke(ra, rb, stueck):
            if vis:
                liste.append((2, (a[2] + b[2]) / 2 + tiefe_plus, (a, b), art, 1.0, True))
            elif verdeckt_art is not None:
                liste.append((1.9, (a[2] + b[2]) / 2, (a, b), verdeckt_art, 0.0, True))
    if linien:
        for a, b, art, n in modell.linien:
            (ra, qa), (rb, qb) = gedreht(a), gedreht(b)
            if art in NAEHTE or draht:          # Nähte immer sichtbar, Drahtgitter alles
                liste.append((2, (ra[2] + rb[2]) / 2, (ra, rb), art, 1.0, True))
                continue
            if ver is None and not nach_vorn(n, qa, qb) >= 0.0 and not (roentgen or verdeckt_strich):
                continue
            strecke(ra, rb, art, art if zeige_verdeckt else None)
    for k in (modell.koerper if koerper else ()):
        art = k["art"] + ("!" if k["id"] in gewaehlt else "")       # ! = gewählt (kräftiger)
        # Schicht: zwischen Innenwand und Flächen, damit die Außenwand den Körper verdeckt und er nur im Loch zu
        # sehen ist (große Wanddreiecke sortieren sich nach ihrer Mitte sonst falsch); auf einer geschlossenen
        # Fläche (Gravur, Blech) obenauf; Röntgen: mit den Flächen
        schicht = 1 if roentgen else 1.4 if k["auf"] else 0.5
        if not draht:
            for a, b, c, n in k["dreiecke"]:
                (pa, qa), (pb, qb), (pc, qc) = gedreht(a), gedreht(b), gedreht(c)
                nr = tuple(m[r][0] * n[0] + m[r][1] * n[1] + m[r][2] * n[2] for r in range(3))
                if sicht(nr, tuple((qa[r] + qb[r] + qc[r]) / 3 for r in range(3)), pz) < 0:
                    nr = (-nr[0], -nr[1], -nr[2])           # durchsichtig: beide Seiten, Licht von vorn
                liste.append((schicht, (pa[2] + pb[2] + pc[2]) / 3, (pa, pb, pc), art, licht_wert(*nr, lw), False))
        if linien:
            for ring in k["ringe"]:
                for a, b in zip(ring, ring[1:]):
                    (ra, _), (rb, _) = gedreht(a), gedreht(b)
                    liste.append((schicht, (ra[2] + rb[2]) / 2 + 1e-6, (ra, rb), art, 1.0, True))
    kanten_an = stil_k["an"] or draht or darstellung in (TECHNISCH, PRUEFMODUS)
    if linien and kanten_an and (darstellung in MIT_KOERPERKANTEN or darstellung == NUR_KONTUREN):
        hauch = darstellung == NUR_KONTUREN         # Nur Konturen: Körperkanten ganz hell zur Orientierung
        innen_an = stil_k["innen"] or pruef
        nur_aussen = darstellung == REALISTISCH
        klassen = modell.kanten_klassen()
        for nr_k, (a, b, n) in enumerate(modell.kanten()):
            innen = klassen[nr_k] == KANTE_INNEN if nr_k < len(klassen) else False
            if innen and (not innen_an or nur_aussen):
                continue
            (ra, qa), (rb, qb) = gedreht(a), gedreht(b)
            if hauch:
                strecke(ra, rb, "_hauch", None, -1e-6)
                continue
            if draht:
                liste.append((2, (ra[2] + rb[2]) / 2, (ra, rb), "_innen" if innen else "_kante", 1.0, True))
                continue
            if ver is None:         # ohne Verdeckungsraster: wie bisher nach der Richtung der Kante
                vorn = nach_vorn(n, qa, qb) >= -0.05
                if vorn or zeige_verdeckt:
                    liste.append((2 if vorn else 1.9, (ra[2] + rb[2]) / 2 - 1e-6, (ra, rb),
                                  ("_innen" if innen else "_kante") if vorn else
                                  ("_innen_v" if innen else "_verdeckt"), 1.0, True))
                continue
            strecke(ra, rb, "_dezent" if nur_aussen else "_innen" if innen else "_kante",
                    ("_innen_v" if innen else "_verdeckt") if zeige_verdeckt else None, -1e-6)
    if linien and darstellung in UMRISS_ARTEN:
        for a, b, rand in umriss(modell, m, pz):
            (ra, _), (rb, _) = gedreht(a), gedreht(b)
            if ver is None:
                liste.append((2, (ra[2] + rb[2]) / 2 - 1e-6, (ra, rb), "_kante", 1.0, True))
            else:
                strecke(ra, rb, "_kante", "_verdeckt" if zeige_verdeckt else None, -1e-6)
    liste.sort(key=lambda e: (e[0], e[1]))
    p.setRenderHint(QPainter.Antialiasing, glatt)
    kfarbe = QColor(TECHNISCH_KANTE if darstellung == TECHNISCH else stil_k["farbe"])
    kbreite = stil_k["breite"]
    stift_linie = {a: QPen(_blass(LINIE.get(a, stil.farbe("#C00000")), blass),
                           NAHT_BREITE if a in NAEHTE else BETONT_BREITE if betont else 2.2,
                           Qt.SolidLine, Qt.RoundCap) for a in LINIE}
    stift_linie["_kante"] = QPen(_blass(kfarbe, blass), kbreite, Qt.SolidLine, Qt.RoundCap)
    dezent = QColor(kfarbe)
    dezent.setAlpha(120)
    stift_linie["_dezent"] = QPen(_blass(dezent, blass), max(0.7, kbreite * 0.75), Qt.SolidLine, Qt.RoundCap)
    stift_linie["_innen"] = QPen(_blass(QColor(stil_k["innen_farbe"]), blass), max(0.8, kbreite * 0.9),
                                 Qt.SolidLine, Qt.RoundCap)
    stift_linie["_verdeckt"] = QPen(_blass(VERDECKT_FARBE, blass), max(0.8, kbreite * 0.8), Qt.DashLine)
    innen_v = QColor(stil_k["innen_farbe"])
    innen_v.setAlpha(150)
    stift_linie["_innen_v"] = QPen(_blass(innen_v, blass), max(0.8, kbreite * 0.75), Qt.DashLine)
    stift_linie["_hauch"] = QPen(_blass(HAUCH_FARBE, blass), 0.9)
    verdeckt = {a: QPen(QColor(s.color().red(), s.color().green(), s.color().blue(), 110), 1.4, Qt.DashLine)
                for a, s in stift_linie.items()}
    for a in ("_verdeckt", "_innen_v"):
        verdeckt[a] = stift_linie[a]
    grundfarbe, farb_cache = {}, {}
    for schicht, _, punkte, art, hell, ist_linie in liste:
        poly = [QPointF(ox + q[0] * massstab, oy - q[1] * massstab) for q in punkte]
        if art[:2] in WK_ARTEN:             # Schnittkörper: halb durchsichtig, gewählter kräftiger
            gew = art.endswith("!")
            if ist_linie:
                c = _blass(LINIE[art[:2]], blass and not gew)
                c.setAlpha(230 if gew else 140)
                p.setPen(QPen(c, 2.0 if gew else 1.0))
                p.drawLine(poly[0], poly[1])
                continue
            f = _blass(FARBE[art[:2]], blass and not gew)
            faktor, glanz = hell
            farbe = QColor(*(min(255, int(c * faktor + 255 * glanz)) for c in (f.red(), f.green(), f.blue())))
            farbe.setAlphaF(WK_ALPHA_GEWAEHLT if gew else WK_ALPHA)
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(farbe))
            p.drawPolygon(QPolygonF(poly))
            continue
        if ist_linie:
            p.setPen((stift_linie if hell else verdeckt).get(art, stift_linie["K"]))
            p.drawLine(poly[0], poly[1])
            continue
        klar = art.endswith("~")
        if klar:
            art = art[:-1]
        grund = grundfarbe.get(art)
        if grund is None:
            f = _blass(farben.get(art, FARBE["K"]), blass)
            grund = grundfarbe[art] = (f.red(), f.green(), f.blue())
        faktor, glanz = hell
        g255 = 255 * glanz
        rgb = (min(255, int(grund[0] * faktor + g255)), min(255, int(grund[1] * faktor + g255)),
               min(255, int(grund[2] * faktor + g255)))
        # V3: Stift und Pinsel je Farbe einmal anlegen (gleiche Farbe = gleiches Bild, nur schneller)
        anteil = BETONT_HELL if betont and art in NEUTRAL_ARTEN else weiss
        stift_pinsel = farb_cache.get((rgb, anteil, klar))
        if stift_pinsel is None:
            farbe = QColor(*rgb)
            if anteil:
                farbe = QColor(*(int(c + (255 - c) * anteil) for c in rgb))
            if roentgen or klar:
                farbe.setAlphaF(alpha_durch)
            stift_pinsel = farb_cache[(rgb, anteil, klar)] = (Qt.NoPen if roentgen or klar else QPen(farbe, 0.8),
                                                              QBrush(farbe))
        p.setPen(stift_pinsel[0])
        p.setBrush(stift_pinsel[1])
        p.drawPolygon(QPolygonF(poly))


def vorschaubild(netz, breite=96, hoehe=30, dpr=1.0):
    """Kleines Bild des Teils (schräg von vorn oben) für die Positionsliste, oder None."""
    if not netz or not netz.get("p"):
        return None
    bild = QPixmap(int(breite * dpr), int(hoehe * dpr))
    bild.setDevicePixelRatio(dpr)
    bild.fill(Qt.transparent)
    p = QPainter(bild)
    try:
        zeichnen(p, netz if isinstance(netz, Modell) else Modell(netz), breite, hoehe, -0.45, 0.45, linien=True)
    except Exception:       # noqa: BLE001 – V1: Vorschaubild ist nur Anzeige, nie die Liste stören
        return None
    finally:
        p.end()
    return bild


class Ansicht3D(QWidget):
    """Drehbare Ansicht: linke Maustaste drehen (um den Punkt des Modells unter dem Mauszeiger, daneben um die
    Modellmitte), rechte oder mittlere verschieben, Mausrad zoomen (zur Mausposition), Doppelklick = Ausgangsansicht."""
    GRUND = (-0.45, 0.45)
    gedreht = Signal()
    angeklickt = Signal(object)     # Klick ohne Ziehen auf eine Linie: dict(id=Merkmal oder None, punkt=(x, y, z))
    # nur mit flaeche_vor_kante (Baugruppe/Satz): Doppelklick bzw. Rechtsklick auf eine Fläche, dict(id, punkt)
    doppelt = Signal(object)
    kontext = Signal(object, object)    # (Treffer, globale Position fürs Menü)
    gemessen = Signal(object)       # Messen: Abstand [mm] nach dem zweiten Punkt
    messen_geaendert = Signal()     # Messen ein/aus bzw. Art gewechselt (gemeinsame Leiste stellt ihre Knöpfe)
    maus_punkt = Signal(object)     # A5: Modellpunkt (x, y, z) unter der Maus oder None (nur mit maus_koordinaten)
    # P5.2 (20.11.2026): Linie unter der Maus (Hover) dict(id, punkt) bzw. None, nur mit maus_koordinaten und bei
    # Wechsel; der Editor hebt dieselbe Kontur in Skizze und Abwicklung hervor
    ueber = Signal(object)
    voll = None             # Modell mit allen Körpern (modell = das gezeigte, ohne die ausgeblendeten)
    _gl = None              # OpenGL-Fläche (ansicht3d_gl.GLFlaeche) oder None = QPainter

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(360, 220)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setFocusPolicy(Qt.StrongFocus)
        self.modell, self.titel, self.netz, self.modus = None, "", None, MODI[0]
        self.pruef_meldung, self._fehler = "", None      # V1: Meldung der Netzprüfung, Fehler beim Zeichnen
        self.schnitt_laengen = {}                # V2: Schnittlänge je Merkmal aus der Rechnung (Editor)
        # V3 Vorher-Nachher: Stand beim Öffnen (Editor: vorher_auto) gestrichelt über dem jetzigen Modell
        self.vorher_auto, self.vorher_netz, self.vorher_an, self._vorher_modell = False, None, False, None
        # Teile-Editor: hervorgehobene Linien (Merkmale bzw. Bereich längs der Rohrachse), Messen Punkt–Punkt
        self.markiert, self.markiert_z, self.messen, self.messpunkte = set(), None, False, []
        self.hover_id, self._ueber_alt = None, None     # P5.2: Kennung, die von außen (Skizze) hervorgehoben ist
        self.pruef_punkte = []      # P3.1: [(Punkt xyz, Text)] unsichere Merkmale der Importanalyse, gelb markiert
        self.kosten_linien, self.kosten_z, self.kosten_legende = {}, [], []    # CAD-005 Kostentreiber
        self.folge, self.folge_akt, self.folge_text = [], None, ""      # Schneidvorschau (schneidfolge.schritte)
        self.mess_treffer = []                  # Fangpunkte zu den Messpunkten (messen3d: Art, Punkt, Element)
        self._schwebe = None                    # Fangpunkt unter der Maus (hervorgehoben)
        self._geo = None                        # messen3d.Geometrie des Modells (beim ersten Messen)
        self.mess_max = 2                       # Messen: 2 Punkte, Winkel 3; Naht zeichnen (Baugruppe): beliebig viele
        self.mess_art = MESS_ABSTAND
        self.masse_fest = []                    # fertige Messungen [(Punkte, Text)]: bleiben stehen bis gelöscht
        self.schnitt_linie = []                 # Querschnitt (editor_schnitt): Ring an der Stelle x
        # V6 (19.11.2026): Schnittebenen [dict(achse, anteil, neigung, umkehren)] und Explosion (Faktor) – nur Anzeige
        self.schnittebenen, self.explosion, self.schnitt_kanten, self.wand_schnitt = [], 0.0, [], None
        # Explosionsansicht (Auftrag 20.11.2026, explosion.py): Zustand mit Versatz von Hand, Fixierung, Ebenen;
        # explo_t 0 … 1 (Animation), explosion_gruppe(Kennung) -> Unterbaugruppe, explo_pfeile für Linien/Nummern
        self.explo, self.explo_t, self.explosion_gruppe, self.explo_pfeile = explo_mod.Stand(), 1.0, None, []
        self.explo_ziehen, self.explo_achse, self._explo_zug = False, "frei", None
        self._explo_rahmen = None       # Bildausschnitt (min, max, mitte, groesse), solange Teile gezogen werden
        self.explosion_nummer = None            # Funktion Kennung -> Positionsnummer (Text) für die Beschriftung
        self.explosion_text = None              # Funktion Kennung -> [Zeilen] (Artikel, Bezeichnung, Werkstoff …)
        self.explosion_teil = None              # Funktion Kennung -> Position (dict) für die Stückliste
        self.explosion_ablage = None            # (lesen, schreiben) der gespeicherten Explosionsansichten
        self.explosion_akte = None              # Funktion -> (Angebotsordner, Nummer) für die Angebotsakte
        self._explo_uhr = QTimer(self)          # Animation (auseinander, zusammen, schrittweise)
        self._explo_uhr.setInterval(40)
        self._explo_uhr.timeout.connect(self._explo_schritt)
        self._explo_anim = None
        self._druck = self._rechts = None
        self._drehpunkt = None                  # (Modellpunkt, Pixel) beim Drücken: dreht um diesen Punkt
        # Darstellungsarten (A4); Vorgabe seit 19.11.2026 „Mit Kanten“ (wie im CAD: Körperkanten dunkel, plastischer)
        self.darstellung, self.nur_gewaehlt = MIT_KANTEN, False
        self.perspektive = perspektive_vorgabe()                        # 3E-11 M2: Vorgabe orthogonal
        self.koerper_an = koerper_vorgabe()                             # Schnittkörper der Konturen (Vorgabe an)
        self._tipp = None                                               # (Ansicht, Körper je Pixel) fürs Überfahren
        # Werkzeug des Teile-Editors (editor_griffe): zeichnet Griffe/Maße über das Bild und bekommt Maus und Tasten
        # zuerst (druck/ziehen/loslassen/schweben/doppelklick/kontext/taste/zeichnen/hinweis)
        self.werkzeug, self._werkzeug_zieht = None, False
        self._bild, self._eilig = None, False      # gezeichnetes Bild (solange sich die Ansicht nicht ändert)
        self._ruhe = QTimer(self)                   # nach dem Zoomen wieder fein zeichnen
        self._ruhe.setSingleShot(True)
        self._ruhe.setInterval(250)
        self._ruhe.timeout.connect(self._fein)
        self.renderer, self.renderer_grund = renderer_waehlen()
        self._gl = None
        if self.renderer == "OpenGL":
            from .ansicht3d_gl import GLFlaeche
            self._gl = GLFlaeche(self)
            self._gl.setGeometry(self.rect())
        from .messen3d import MessTafel
        self.tafel = MessTafel(self)            # Ergebnis des Messens mit Kernwerten (kopierbar)
        from .auswahl3d import Auswahl
        self.wahl = Auswahl(self)               # Auswahl Körper/Fläche/Kante/Punkt, Ausblenden, Isolieren (Paket 3)
        # Plan 3D-Editor 19.11.2026: Ebenen (ausgeblendete Arten, A6), Legende ein/aus (A9), Mauskoordinaten (A5,
        # gerechnet erst, wenn die Maus kurz ruht: auch bei großen Modellen kein Ruckeln)
        self.arten_aus, self.legende_an, self.maus_koordinaten = set(), True, False
        self.raster_an = _merker_lesen(RASTER_EINSTELLUNG, False)       # A7 Raster unter dem Modell
        self.achsen_an = _merker_lesen(ACHSEN_EINSTELLUNG, True)        # A7 Achsenkreuz unten links
        self._maus_pos = None
        self._maus_uhr = QTimer(self)
        self._maus_uhr.setSingleShot(True)
        self._maus_uhr.setInterval(MAUS_RUHE_MS)
        self._maus_uhr.timeout.connect(self._maus_punkt_melden)
        # freie 360°-Drehung (navigation3d, 19.11.2026): Einstellungen beim Drücken gelesen, Nachlauf optional
        self.nav = dict(navigation3d.VORGABEN)
        self._nachlauf = QTimer(self)
        self._nachlauf.setInterval(16)
        self._nachlauf.timeout.connect(self._nachlaufen)
        self._tempo = (0.0, 0.0)
        self.zuruecksetzen()

    def _gl_aus(self, grund):
        """OpenGL gescheitert: diese und alle weiteren Ansichten zeichnen mit QPainter."""
        global _gl_fehler
        _gl_fehler = grund
        self.renderer, self.renderer_grund = "Software", f"OpenGL gescheitert: {grund}"
        if self._gl is not None:
            gl, self._gl = self._gl, None
            gl.hide()
            gl.deleteLater()
        QTimer.singleShot(0, self, self.update)

    def update(self, *args):
        super().update(*args)
        if self._gl is not None:
            self._gl.update()

    def resizeEvent(self, e):
        if self._gl is not None:
            self._gl.setGeometry(self.rect())
        self.tafel.anordnen()
        super().resizeEvent(e)

    def _fein(self):
        self._eilig = False
        self.update()

    def setzen(self, netz, titel=""):
        """netz: dict, Bytes aus der Datenbank oder None (= keine 3D-Daten)."""
        if isinstance(netz, (bytes, bytearray, memoryview)):
            netz = entpacken(bytes(netz))
        netz, self.pruef_meldung = netz_pruefen(netz)     # V1: fehlerhafte Stellen weglassen und melden
        self.netz = netz if netz and netz.get("p") else None
        if self.vorher_auto and self.vorher_netz is None and self.netz is not None:
            self.vorher_netz = self.netz            # erster Stand im Editor = „vorher“
        self._fehler = None
        try:
            self._modell_setzen(Modell(self._gezeigt(), geprueft=True) if self.netz else None)
        except Exception as e:      # noqa: BLE001 – nie das Fenster sterben lassen: leer zeigen und melden
            self.netz, self.voll = None, None
            self._fehler = f"3D-Modell nicht darstellbar ({type(e).__name__}: {e})"
            self._modell_setzen(None)
        self.titel = titel
        vorrechnen(self.voll)           # V3: Körperkanten großer Modelle im Hintergrund
        self.messpunkte, self.mess_treffer, self._schwebe, self._geo = [], [], None, None
        weg = self._masse_pruefen()
        self._tipp = None
        self.tafel.zeigen([f"{weg} {'Maß' if weg == 1 else 'Maße'} entfernt: das Modell hat sich an dieser Stelle "
                           "geändert (alte Werte wären falsch)."] if weg else [])
        self._maus_verfolgen()
        self.zuruecksetzen()

    def _masse_pruefen(self):
        """Feste Maße nach einem neuen Modell: bleiben nur, wenn alle ihre Punkte im neuen Modell noch genau so
        liegen (dann stimmt der Wert weiter), sonst fallen sie weg. Ergebnis: Anzahl entfernter Maße."""
        if not self.masse_fest:
            return 0
        if self.modell is None:
            n, self.masse_fest = len(self.masse_fest), []
            return n
        try:
            geo = self.geometrie()
            arten = getattr(self, "_mass_arten", {})

            def gilt(m):
                aa = arten.get(tuple(tuple(q) for q in m[0])) or getattr(m, "arten", None) or [None] * len(m[0])
                return all(geo.hat_punkt(q, art) for q, art in zip(m[0], aa))
            behalten = [m for m in self.masse_fest if gilt(m)]
        except Exception:       # noqa: BLE001 – im Zweifel lieber kein Maß als ein falsches
            behalten = []
        n = len(self.masse_fest) - len(behalten)
        self.masse_fest = behalten
        return n

    def _gezeigt(self):
        """Netz, wie es gezeigt wird: Vorschau-Modus (Anbauteile, Gravurkonturen) und ausgeblendete Ebenen."""
        return ohne_arten(gefiltert(self.netz, self.modus), self.arten_aus)

    def ebenen_setzen(self, aus):
        """Ebenen (Arten wie 'A', 'I', 'K') aus- bzw. wieder einblenden (A6). Blick, Auswahl der Körper und Maße bleiben;
        die Rechnung sieht davon nichts (nur die Anzeige)."""
        aus = set(aus or ())
        if aus == self.arten_aus:
            return
        self.arten_aus = aus
        if self.netz:
            self._modell_setzen(Modell(self._gezeigt(), geprueft=True))

    def raster_setzen(self, an, merken=True):
        """Raster unter dem Modell ein/aus (A7); merken: je Benutzer speichern (gilt in allen 3D-Fenstern)."""
        self.raster_an = bool(an)
        if merken:
            _merker_setzen(RASTER_EINSTELLUNG, self.raster_an)
        self._bild = None
        self.update()

    def achsen_setzen(self, an, merken=True):
        """Achsenkreuz X/Y/Z unten links ein/aus (A7)."""
        self.achsen_an = bool(an)
        if merken:
            _merker_setzen(ACHSEN_EINSTELLUNG, self.achsen_an)
        self.update()

    def raster_linien(self):
        """Linien des Rasters in Modellkoordinaten [(a, b, kraeftig)]: Ebene unter dem Modell (Rohr/Blech: y = min,
        Baugruppe in Dateilage: z = min), etwas größer als das Modell, Weite nach raster_schritt; jede 5. Linie
        kräftiger. Leer ohne Modell."""
        mo = self.modell
        if mo is None:
            return []
        hoch = 2 if (self.netz or {}).get("global") else 1          # Achse nach oben
        a_, b_ = [k for k in range(3) if k != hoch]
        rand = 0.1 * max(mo.max[a_] - mo.min[a_], mo.max[b_] - mo.min[b_], 1.0)
        lo = [mo.min[a_] - rand, mo.min[b_] - rand]
        hi = [mo.max[a_] + rand, mo.max[b_] + rand]
        schritt = raster_schritt(max(hi[0] - lo[0], hi[1] - lo[1]))
        ebene = mo.min[hoch]
        linien = []
        for achse in (0, 1):
            anf = math.floor(lo[achse] / schritt)
            ende = math.ceil(hi[achse] / schritt)
            if ende - anf > 400:            # Schutz: nie Tausende Linien
                return []
            for i in range(anf, ende + 1):
                w = i * schritt
                p, q = [0.0] * 3, [0.0] * 3
                p[hoch] = q[hoch] = ebene
                if achse == 0:
                    p[a_], q[a_], p[b_], q[b_] = w, w, lo[1], hi[1]
                else:
                    p[b_], q[b_], p[a_], q[a_] = w, w, lo[0], hi[0]
                linien.append((tuple(p), tuple(q), i % 5 == 0))
        return linien

    def schatten_lage(self):
        """Kontaktschatten: Umriss (Bildpunkte) des Modells, auf seinen Boden projiziert, oder None (aus, ohne
        Modell, Drahtgitter/Durchsichtig). Boden = die Ebene quer zur Modellachse, die im Bild am meisten senkrecht
        steht, an ihrer unteren Seite; so liegt der Schatten auch unter schrägen und langen Teilen direkt darunter."""
        if self.modell is None or not visualisierung.schatten_an() or self.darstellung in (*ROENTGEN_ARTEN,
                                                                                            *DRAHT_ARTEN):
            return None
        mo = self.modell
        m = _drehung(self.gier, self.nick, self.roll)
        achse = max(range(3), key=lambda c: abs(m[1][c]))
        if abs(m[1][achse]) < 0.35:         # von oben/unten gesehen: kein Boden im Bild
            return None
        unten = mo.min[achse] if m[1][achse] > 0 else mo.max[achse]
        abstand = 0.02 * mo.groesse * (-1 if m[1][achse] > 0 else 1)
        bild = self.bildpunkt()
        pkt = mo.punkte
        schritt = max(1, len(pkt) // 600)          # Stichprobe der Eckpunkte (schnell, je Bild)
        boden = []
        for q in pkt[::schritt]:
            q = list(q)
            q[achse] = unten + abstand
            boden.append(bild(tuple(q))[:2])
        grenzen = getattr(mo, "sicht_grenzen", None) or (mo.min, mo.max)     # V6: geschnitten = nur der Rest
        for c0 in (0, 1):                           # Ecken der Grundfläche dazu (Stichprobe kann sie verfehlen)
            for c1 in (0, 1):
                q = [0.0, 0.0, 0.0]
                andere = [c for c in range(3) if c != achse]
                q[andere[0]] = grenzen[c0][andere[0]]
                q[andere[1]] = grenzen[c1][andere[1]]
                q[achse] = unten + abstand
                boden.append(bild(tuple(q))[:2])
        return visualisierung.huelle(boden)

    def _schatten_malen(self, p):
        """Weicher Kontaktschatten hinter dem Modell (nur Anzeige, ohne Tiefe; Modell und Netz bleiben, wie sie sind)."""
        huelle = self.schatten_lage()
        if not huelle or len(huelle) < 3:
            return
        from PySide6.QtGui import QPainterPath
        weg = QPainterPath()
        weg.moveTo(*huelle[0])
        for x, y in huelle[1:]:
            weg.lineTo(x, y)
        weg.closeSubpath()
        d = visualisierung.SCHATTEN_DECKKRAFT
        p.save()
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setBrush(Qt.NoBrush)
        for breite in (40, 30, 22, 15, 9, 4):      # weicher Rand: jeder Ring legt etwas Schatten dazu (nach innen dunkler)
            p.setPen(QPen(QColor(20, 28, 36, int(255 * d * 0.045)), breite, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            p.drawPath(weg)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(20, 28, 36, int(255 * d * 0.22)))
        p.drawPath(weg)
        p.restore()

    def _raster_malen(self, p):
        """Raster hinter dem Modell (vor dem Modell gezeichnet, das Modell deckt es zu)."""
        if not getattr(self, "raster_an", False) or self.modell is None:
            return
        bild = self.bildpunkt()
        p.save()
        p.setRenderHint(QPainter.Antialiasing, True)
        fein, kraeftig = QPen(stil.farbe("#C9D0D8"), 1), QPen(stil.farbe("#8FA6C1"), 1)
        for a, b, kr in self.raster_linien():
            pa, pb = bild(a), bild(b)
            p.setPen(kraeftig if kr else fein)
            p.drawLine(QPointF(pa[0], pa[1]), QPointF(pb[0], pb[1]))
        p.restore()

    def _achsen_malen(self, p):
        """Achsenkreuz X (rot), Y (grün), Z (blau) unten links, dreht sich mit dem Modell (A7)."""
        if not getattr(self, "achsen_an", True) or self.modell is None:
            return
        laenge, mx, my = 26.0, 38.0, self.height() - 62.0
        p.save()
        p.setRenderHint(QPainter.Antialiasing, True)
        farben = {"X": "#D62728", "Y": "#2CA02C", "Z": "#1F77B4"}
        for name, dx, dy, _ in sorted(achsen_bild(self.gier, self.nick, self.roll), key=lambda a: a[3]):     # hinten zuerst
            ende = QPointF(mx + dx * laenge, my + dy * laenge)
            p.setPen(QPen(stil.farbe(farben[name]), 2.2))
            p.drawLine(QPointF(mx, my), ende)
            p.drawText(QRectF(ende.x() + dx * 6 - 6, ende.y() + dy * 6 - 8, 12, 16), Qt.AlignCenter, name)
        p.setPen(QPen(stil.farbe("#606060"), 1))
        p.setBrush(stil.farbe("#FFFFFF"))
        p.drawEllipse(QPointF(mx, my), 2.5, 2.5)
        p.restore()

    def legende_setzen(self, an):
        """Legende der Flächenarten oben links ein/aus (A9: sie verdeckte bei schmaler Ansicht das Modell)."""
        self.legende_an = bool(an)
        self._bild = None
        self.update()

    def _maus_punkt_melden(self):
        if self._maus_pos is None or self.modell is None or self._maus is not None:
            self.maus_punkt.emit(None)
            return
        try:
            self.maus_punkt.emit(self.punkt_unter(*self._maus_pos))
        except Exception:   # noqa: BLE001 – Anzeige der Koordinaten darf nie stören
            self.maus_punkt.emit(None)
        try:
            t = self.linie_unter(*self._maus_pos)
        except Exception:   # noqa: BLE001 – Hover darf nie stören
            t = None
        schl = (t or {}).get("id") if t and t.get("id") else (t or {}).get("punkt")
        if schl != self._ueber_alt:
            self._ueber_alt = schl
            self.ueber.emit(t)

    def linie_unter(self, x, y, fang=8):
        """Linie unter dem Bildpunkt (x, y) ohne Klick: dict(id = Kennung oder None, punkt) oder None."""
        if self.modell is None or not self.modell.linien:
            return None
        bild = self.bildpunkt()
        beste = None
        for nr, (a, b, _, _) in enumerate(self.modell.linien):
            pa, pb = bild(a), bild(b)
            dx, dy = pb[0] - pa[0], pb[1] - pa[1]
            lg = dx * dx + dy * dy
            t = 0.0 if lg < 1e-9 else max(0.0, min(1.0, ((x - pa[0]) * dx + (y - pa[1]) * dy) / lg))
            d = math.hypot(pa[0] + t * dx - x, pa[1] + t * dy - y)
            if d <= fang and (beste is None or d < beste[0]):
                beste = (d, nr, tuple(a[k] + t * (b[k] - a[k]) for k in range(3)))
        if beste is None:
            return None
        ids = self.modell.linien_id
        return dict(id=ids[beste[1]] if beste[1] < len(ids) else None, punkt=beste[2])

    def hover_setzen(self, kennung):
        """Kennung (z. B. 'kontur:3') von außen hervorheben (Hover in Skizze/Abwicklung) oder None."""
        if kennung != self.hover_id:
            self.hover_id = kennung
            self.update()

    def _pruef_zeichnen(self, p):
        """P3.1: unsichere Merkmale (Konfidenz unter 90 %) als gelbe Marke mit Fragezeichen."""
        if not self.pruef_punkte or self.modell is None:
            return
        bild = self.bildpunkt()
        p.save()
        p.setRenderHint(QPainter.Antialiasing, True)
        for pt, _ in self.pruef_punkte:
            x, y, _t = bild(pt)
            p.setPen(QPen(PRUEFEN.darker(140), 1.2))
            p.setBrush(PRUEFEN)
            p.drawEllipse(QPointF(x, y), 8, 8)
            p.setPen(QPen(PRUEFEN_TEXT, 1))
            p.drawText(QRectF(x - 8, y - 8, 16, 16), Qt.AlignCenter, "?")
        p.restore()

    def _hover_zeichnen(self, p):
        if not self.hover_id or self.modell is None:
            return
        ids = self.modell.linien_id
        bild = None
        p.save()
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setPen(QPen(HOVER, 3.2))
        for nr, (a, b, _, _) in enumerate(self.modell.linien):
            if nr < len(ids) and ids[nr] == self.hover_id:
                bild = bild or self.bildpunkt()
                pa, pb = bild(a), bild(b)
                p.drawLine(QPointF(pa[0], pa[1]), QPointF(pb[0], pb[1]))
        p.restore()

    def leaveEvent(self, e):
        if self.maus_koordinaten:
            self._maus_pos = None
            self._maus_uhr.stop()
            self.maus_punkt.emit(None)
        super().leaveEvent(e)

    def _modell_setzen(self, modell):
        """Neues Modell: voll = alle Körper, modell = das gezeigte (ohne die ausgeblendeten Körper der Auswahl)."""
        self.voll = self.modell = modell
        self.wahl.modell_neu()
        self.sichtbarkeit_anwenden()

    def sichtbarkeit_anwenden(self):
        """Ausgeblendete Körper der Auswahl (wahl.versteckt) aus dem gezeigten Modell nehmen; danach Explosion und
        Schnittebenen (V6) auf eine Kopie – das volle Modell, das Netz und die Rechnung bleiben unberührt."""
        m = self.voll
        self.schnitt_kanten, self.wand_schnitt = [], None
        if m is not None:
            kv = None
            durch = getattr(self.wahl, "durchsichtig", None) or set()
            self.explo_pfeile = []
            if self.wahl.versteckt or self.explo.aktiv() or durch:
                kv = self.wahl.elemente().koerper_von
            if self.explo.aktiv() and kv is not None:
                m, self.explo_pfeile = explo_mod.anwenden(m, kv, self.explo, self.explosion_gruppe, self.explo_t)
                r = self._explo_rahmen
                if r is not None and self.explo_ziehen:     # beim Ziehen bleibt der Bildausschnitt stehen
                    if m is self.voll:
                        m = schnitt_explosion._kopie(m)
                    m.min, m.max, m.mitte, m.groesse, m.rahmen_fest = r
            if self.wahl.versteckt:
                from .auswahl3d import sichtbar
                m = sichtbar(m, kv, self.wahl.versteckt)
            if self.schnittebenen:
                ebenen = [schnitt_explosion.ebene(self.voll, e.get("achse", "Z"), e.get("anteil", 0.5),
                                                  e.get("neigung", 0.0), e.get("umkehren", False))
                          for e in self.schnittebenen[:schnitt_explosion.MAX_EBENEN]]
                m, self.schnitt_kanten = schnitt_explosion.schneiden(m, ebenen)
                try:
                    self.wand_schnitt = schnitt_explosion.wandstaerke(self.schnitt_kanten)
                except Exception:       # noqa: BLE001 – nur Anzeige: ohne Wert weiter
                    self.wand_schnitt = None
            if durch and kv is not None:      # durchsichtig geschaltete Teile (20.11.2026): je Dreieck markieren
                voll_nr = {nr for nr, k in enumerate(kv) if k in durch}
                herk = getattr(m, "herkunft", None) if m is not self.voll else None
                if m is self.voll:
                    m = schnitt_explosion._kopie(m)
                m.durch = frozenset(nr for nr in range(len(m.dreiecke))
                                    if (herk[nr] if herk and nr < len(herk) else nr) in voll_nr)
        self.modell = m
        self._geo, self._tipp, self._bild = None, None, None
        self.update()

    def schnittebenen_setzen(self, ebenen):
        """V6: bis zu drei Schnittebenen [dict(achse 'X'/'Y'/'Z', anteil 0…1, neigung Grad, umkehren)] ([] = aus).
        Nur Anzeige: geschnitten wird eine Kopie; Wandstärke an der Schnittstelle in wand_schnitt."""
        self.schnittebenen = [dict(e) for e in (ebenen or ())][:schnitt_explosion.MAX_EBENEN]
        self.sichtbarkeit_anwenden()
        self.gedreht.emit()

    def explosion_setzen(self, faktor):
        """V6: Explosionsansicht (Baugruppe/Satz): jeder Körper rückt um faktor × Abstand zur Mitte nach außen
        (0 = aus). Nur Anzeige; Messen ist dabei gesperrt (Abstände zwischen Teilen wären falsch)."""
        self.explosion = max(0.0, min(explo_mod.FAKTOR_MAX, float(faktor or 0.0)))
        self.explo.faktor = self.explosion
        if self.explo.aktiv() and self.messen:
            self.messen_setzen(False)
        self.sichtbarkeit_anwenden()
        if self.explosion and self.modell is self.voll and self.voll is not None:
            self.tafel.zeigen(["Explosion: das Modell hat nur einen Körper, es bewegt sich nichts."])
        self.gedreht.emit()

    # ------------------------------------------------------------ Explosionsansicht (Auftrag 20.11.2026)
    def explosion_anwenden(self):
        """Nach jeder Änderung an self.explo: Anzeige neu (nur Anzeige, Netz und volles Modell bleiben)."""
        if not self.explo_ziehen:
            self._explo_rahmen = None
        self.explosion = float(self.explo.faktor or 0.0)
        if self.explo.aktiv() and self.messen:
            self.messen_setzen(False)
        self.sichtbarkeit_anwenden()
        self.gedreht.emit()

    def explosion_stand_laden(self, daten, kamera=None):
        """Gespeicherte Explosionsansicht (explosion.Stand.als_dict, Kamera) zeigen."""
        self._explo_uhr.stop()
        self._explo_anim, self.explo_t = None, 1.0
        self.explo.merken()
        self.explo.aus_dict(daten)
        for n, v in (kamera or {}).items():
            if n in ("gier", "nick", "roll", "zoom") and isinstance(v, (int, float)):
                setattr(self, n, float(v))
            elif n == "versatz" and isinstance(v, (list, tuple)) and len(v) == 2:
                self.versatz = (float(v[0]), float(v[1]))
            elif n == "perspektive" and isinstance(v, bool):
                self.perspektive = v
        self.explosion_anwenden()

    def kamera(self):
        return dict(gier=self.gier, nick=self.nick, roll=self.roll, zoom=self.zoom, versatz=list(self.versatz))

    def explosion_koerper_bei(self, x, y):
        """Kennung des Körpers unter dem Pixel (gezeigtes Modell) oder None."""
        try:
            r = self.wahl.dreieck_unter(x, y)
            el = self.wahl.elemente()
        except Exception:       # noqa: BLE001 – nur Anzeige
            return None
        if r is None or el is None or r[0] >= len(el.koerper_von):
            return None
        return el.koerper_von[r[0]]

    def _modell_weg(self, dx, dy):
        """Pixelweg (dx, dy) im Bild -> Weg im Modell (mm) in der Bildebene, nach explo_achse eingeschränkt."""
        mo = self.modell
        bild = self.bildpunkt()
        c = mo.mitte
        p0 = bild(c)
        spalten = []
        for k in range(3):
            q = list(c)
            q[k] += 1.0
            pk = bild(q)
            spalten.append((pk[0] - p0[0], pk[1] - p0[1]))
        a = self.explo_achse
        if a in ("x", "y", "z"):            # nur entlang einer Achse: Weg = Anteil der Maus in Richtung der Achse
            k = "xyz".index(a)
            ux, uy = spalten[k]
            n2 = ux * ux + uy * uy
            if n2 < 1e-12:
                return (0.0, 0.0, 0.0)
            t = (dx * ux + dy * uy) / n2
            return tuple(t if i == k else 0.0 for i in range(3))
        # kleinster Weg in 3D, der im Bild genau (dx, dy) ergibt: J^T (J J^T)^-1 d
        j00 = sum(s[0] * s[0] for s in spalten)
        j01 = sum(s[0] * s[1] for s in spalten)
        j11 = sum(s[1] * s[1] for s in spalten)
        det = j00 * j11 - j01 * j01
        if abs(det) < 1e-12:
            return (0.0, 0.0, 0.0)
        u = (j11 * dx - j01 * dy) / det
        v = (-j01 * dx + j00 * dy) / det
        return tuple(spalten[k][0] * u + spalten[k][1] * v for k in range(3))

    def _explo_druck(self, e):
        if not (self.explo_ziehen and e.button() == Qt.LeftButton and not self.messen and self.modell is not None):
            return False
        kid = self.explosion_koerper_bei(e.position().x(), e.position().y())
        if kid is None:
            return False
        gewaehlt = self.wahl.koerper_ids() if self.wahl.an else []
        ids = [k for k in (gewaehlt if kid in gewaehlt else [kid]) if k not in self.explo.fix]
        if not ids:
            self.tafel.zeigen(["Das Teil ist fixiert und bleibt stehen (Lösen im Explosionsfenster)."])
            return True
        self.explo.merken()
        self._explo_zug = (e.position(), ids)
        if self._explo_rahmen is None:
            mo = self.modell
            w, h = max(1, self.width()), max(1, self.height())
            s = projektion(mo, w, h, self.gier, self.nick, self.zoom, self.versatz, self.perspektive, self.roll)[2]
            self._explo_rahmen = (mo.min, mo.max, mo.mitte, mo.groesse,
                                  ((w, h, self.gier, self.nick, bool(self.perspektive), self.roll), s / (self.zoom or 1)))
        return True

    def _explo_ziehen_zu(self, pos):
        alt, ids = self._explo_zug
        d = pos - alt
        w = self._modell_weg(d.x(), d.y())
        if any(abs(c) > 1e-9 for c in w):
            for k in ids:
                v = self.explo.versatz.get(k, [0.0, 0.0, 0.0])
                self.explo.versatz[k] = [v[c] + w[c] for c in range(3)]
            self._explo_zug = (pos, ids)
            self.explosion_anwenden()

    def explosion_animieren(self, art, sekunden=1.5):
        """art: 'auseinander' (Faktor 0 → Ziel), 'zusammen', 'schrittweise' (Teil für Teil, außen zuerst), 'montage'
        (schrittweise umgekehrt: Montagereihenfolge). sekunden: Dauer (schrittweise je Teil)."""
        el = self.wahl.elemente() if self.voll is not None else None
        if el is None or len(set(el.koerper_von)) < 2:
            self.tafel.zeigen(["Animation: das Modell hat nur einen Körper."])
            return False
        if not self.explo.faktor:
            self.explo.faktor = 1.0
        n = len(set(el.koerper_von))
        if art in ("schrittweise", "montage"):
            mitten, _ = explo_mod.koerper_daten(self.voll, el.koerper_von)
            self.explo.reihenfolge = explo_mod.reihenfolge(mitten, self.voll.mitte)
            start, ende = (0.0, float(n)) if art == "schrittweise" else (float(n), 0.0)
            self.explo.schritt, self.explo_t = start, 1.0
            dauer = max(0.2, float(sekunden)) * n
        else:
            start, ende = (0.0, 1.0) if art == "auseinander" else (1.0, 0.0)
            self.explo.schritt, self.explo_t = None, start
            dauer = max(0.2, float(sekunden))
        self._explo_anim = dict(art=art, start=start, ende=ende, schritte=max(2, int(dauer * 25)), nr=0)
        self.explosion_anwenden()
        self._explo_uhr.start()
        return True

    def explosion_pause(self):
        """Animation anhalten bzw. weiterlaufen lassen. Ergebnis: läuft sie jetzt?"""
        if self._explo_anim is None:
            return False
        if self._explo_uhr.isActive():
            self._explo_uhr.stop()
            return False
        self._explo_uhr.start()
        return True

    def explosion_laeuft(self):
        return self._explo_anim is not None

    def _explo_schritt(self):
        an = self._explo_anim
        if an is None:
            self._explo_uhr.stop()
            return
        an["nr"] += 1
        f = min(1.0, an["nr"] / an["schritte"])
        wert = an["start"] + (an["ende"] - an["start"]) * f
        if an["art"] in ("schrittweise", "montage"):
            self.explo.schritt = wert
        else:
            self.explo_t = wert
        if f >= 1.0:
            self._explo_uhr.stop()
            self._explo_anim = None
            self.explo.schritt, self.explo_t = None, 1.0
            if an["art"] in ("zusammen", "montage"):
                self.explo.faktor = 0.0
        self.explosion_anwenden()

    def _explo_nummer(self, kid, ids):
        if self.explosion_nummer is not None:
            try:
                n = self.explosion_nummer(kid)
            except Exception:       # noqa: BLE001 – nur Beschriftung
                n = None
            if n:
                return str(n)
        name = self.wahl.koerper_name(kid) if self.wahl.koerper_name else None
        if name and name.startswith("Pos. "):
            return name[5:].split(" ")[0]
        return str(ids.index(kid) + 1) if kid in ids else "?"

    def _explosion_malen(self, p):
        """Verbindungslinien von der Einbaulage zur Explosionslage und Positionsnummern (Ballons) über dem Bild."""
        if not self.explo_pfeile or self.modell is None or self.modell is self.voll:
            return
        bild = self.bildpunkt()
        versteckt = self.wahl.versteckt
        pfeile = [x for x in self.explo_pfeile if x[0] not in versteckt]
        ids = [x[0] for x in pfeile]
        p.save()
        p.setRenderHint(QPainter.Antialiasing, True)
        if self.explo.linien:
            stift = QPen(stil.farbe("#5B6B7C"), 1.1, Qt.DashLine)
            p.setPen(stift)
            for kid, alt, neu in pfeile:
                a, b = bild(alt), bild(neu)
                if math.hypot(a[0] - b[0], a[1] - b[1]) > 3:
                    p.drawLine(QPointF(a[0], a[1]), QPointF(b[0], b[1]))
                    p.drawEllipse(QPointF(a[0], a[1]), 2.0, 2.0)
        art = self.explo.beschriftung
        if art != "Aus":
            fm = p.fontMetrics()
            belegt = []
            for kid, _, neu in sorted(pfeile, key=lambda x: str(x[0])):
                b = bild(neu)
                nr = self._explo_nummer(kid, ids)
                zeilen = [nr]
                if art != "Positionsnummer" and self.explosion_text is not None:
                    try:
                        mehr = [z for z in (self.explosion_text(kid) or []) if z]
                    except Exception:       # noqa: BLE001
                        mehr = []
                    zeilen += mehr[:1] if art == "Nummer und Artikel" else mehr[:5]
                r_k = 10 + 2 * max(0, len(nr) - 2)
                x, y = b[0] + 22, b[1] - 22
                breite = max([fm.horizontalAdvance(z) for z in zeilen[1:]] or [0])
                for r in belegt:            # Ballons nicht übereinander
                    if abs(r[0] - x) < max(40, breite) and abs(r[1] - y) < 2 * r_k + 4:
                        y = r[1] + 2 * r_k + 6
                belegt.append((x, y))
                p.setPen(QPen(stil.farbe("#1F3F73"), 1.0))
                p.drawLine(QPointF(b[0], b[1]), QPointF(x, y))
                p.setBrush(stil.farbe("#FFFFFF"))
                fix = kid in self.explo.fix
                p.setPen(QPen(stil.farbe("#B45309" if fix else "#1F3F73"), 1.6))
                p.drawEllipse(QPointF(x, y), r_k, r_k)
                p.setPen(stil.farbe("#1F3F73"))
                p.drawText(QRectF(x - r_k, y - r_k, 2 * r_k, 2 * r_k), Qt.AlignCenter, nr)
                if len(zeilen) > 1:
                    feld = QColor(HINTERGRUND_OBEN)
                    feld.setAlpha(210)
                    h = 16 * (len(zeilen) - 1)
                    p.fillRect(QRectF(x + r_k + 3, y - 8, breite + 8, h), feld)
                    p.setPen(stil.farbe("#202020"))
                    for i, z in enumerate(zeilen[1:]):
                        p.drawText(QRectF(x + r_k + 7, y - 8 + 16 * i, breite + 4, 16), Qt.AlignLeft | Qt.AlignVCenter,
                                   z)
        p.restore()

    def anzeige_hinweis(self):
        """Hinweis oben rechts, solange die Anzeige nicht das echte Teil zeigt (Schnitt, Explosion) oder ''."""
        teile = []
        if self.explo.aktiv():
            teile.append(f"Explosion {self.explosion:.1f}×" + (" mit eigenem Versatz" if self.explo.versatz else "")
                         + " – nur Anzeige, Messen gesperrt")
        if self.schnittebenen:
            t = f"Schnitt ({len(self.schnittebenen)} {'Ebene' if len(self.schnittebenen) == 1 else 'Ebenen'})"
            if self.wand_schnitt:
                typ, lo, hi = self.wand_schnitt
                t += (f" · Wand an der Schnittstelle ≈ {typ:.2f} mm" if hi - lo < 0.05 else
                      f" · Wand an der Schnittstelle ≈ {typ:.2f} mm ({lo:.2f}–{hi:.2f})")
            teile.append(t + " – nur Anzeige")
        return " · ".join(teile)

    def koerper_setzen(self, an, merken=True):
        """Schnittkörper der Konturen zeigen (an) oder nicht; merken: Wahl je Benutzer speichern."""
        self.koerper_an = bool(an)
        if merken:
            _koerper_merken(self.koerper_an)
        self._maus_verfolgen()
        self.update()
        self.gedreht.emit()

    def koerper(self):
        """Gezeigte Schnittkörper (leer, wenn aus oder keine da)."""
        return self.modell.koerper if self.koerper_an and self.modell is not None else []

    def _maus_verfolgen(self):
        """Mausbewegung ohne Taste nur, wenn sie gebraucht wird (Werkzeug, Messen, Tooltip der Schnittkörper)."""
        self.setMouseTracking(self.werkzeug is not None or self.messen or bool(self.koerper()) or self.wahl.an)

    def koerper_unter(self, x, y):
        """Vorderster Schnittkörper unter dem Pixel (x, y): (Tiefe, Körper) oder None."""
        ks = self.koerper()
        if not ks:
            return None
        schl = (self.width(), self.height(), self.gier, self.nick, self.roll, self.zoom, self.versatz,
                self.perspektive, self.modell)
        if self._tipp is None or self._tipp[0] != schl:
            bild = self.bildpunkt()
            liste = []
            for k in ks:
                tris = [tuple(bild(q) for q in d[:3]) for d in k["dreiecke"]]
                xs = [q[0] for t in tris for q in t]
                ys = [q[1] for t in tris for q in t]
                liste.append(((min(xs), max(xs), min(ys), max(ys)), tris, k))
            self._tipp = (schl, liste)
        beste = None
        for (x0, x1, y0, y1), tris, k in self._tipp[1]:
            if not (x0 <= x <= x1 and y0 <= y <= y1):
                continue
            for a, b, c in tris:
                det = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
                if abs(det) < 1e-9:
                    continue
                l1 = ((b[1] - c[1]) * (x - c[0]) + (c[0] - b[0]) * (y - c[1])) / det
                l2 = ((c[1] - a[1]) * (x - c[0]) + (a[0] - c[0]) * (y - c[1])) / det
                if min(l1, l2, 1 - l1 - l2) < -1e-6:
                    continue
                t = l1 * a[2] + l2 * b[2] + (1 - l1 - l2) * c[2]
                if beste is None or t > beste[0]:
                    beste = (t, k)
        return beste

    def _koerper_tipp(self, e):
        """Tooltip mit der Tiefe des Schnittkörpers unter der Maus."""
        t = self.koerper_unter(e.position().x(), e.position().y())
        if t is None:
            QToolTip.hideText()
            return
        QToolTip.showText(e.globalPosition().toPoint(), t[1]["text"], self)

    def darstellung_setzen(self, darstellung=None, nur_gewaehlt=None):
        """Darstellungsart (DARSTELLUNGEN) und „nur Gewähltes hervorheben“ (Rest blass)."""
        if darstellung in DARSTELLUNGEN:
            self.darstellung = darstellung
        if nur_gewaehlt is not None:
            self.nur_gewaehlt = bool(nur_gewaehlt)
        self.update()

    def blass(self):
        """Rest blass zeichnen: nur Gewähltes hervorheben und etwas ist gewählt."""
        return self.nur_gewaehlt and bool(self.markiert or self.markiert_z)

    def werkzeug_setzen(self, werkzeug):
        self.werkzeug = werkzeug
        self._maus_verfolgen()
        self.update()

    def geometrie(self):
        """Fangbare Geometrie des Modells mit exakten Kernwerten (messen3d.Geometrie), einmal je Modell."""
        if self._geo is None or self._geo.modell is not self.modell:
            from .messen3d import Geometrie
            self._geo = Geometrie(self.modell, gefiltert(self.netz, self.modus))
        self._geo.schnitt = self.schnitt_laengen
        return self._geo

    def schnitt_laengen_setzen(self, werte):
        """Schnittlänge je Merkmal {id: (je Stück, gesamt)} [mm] aus der Rechnung des Editors (V2): die Mess-Tafel
        nennt sie zur angeklickten Kontur."""
        self.schnitt_laengen = dict(werte or {})

    def markieren(self, ids=(), z_bereich=None):
        """Linien der Merkmale ids (netz 'li') bzw. alle Linien mit z im Bereich (z0, z1) hervorheben."""
        self.markiert, self.markiert_z = set(ids or ()), z_bereich
        self.update()

    def kosten_setzen(self, linien=None, z_bereiche=None, legende=None):
        """Kostentreiber einfärben (CAD-005): linien = {Merkmal-ID der Linie (netz 'li'): Farbe}, z_bereiche =
        [(z0, z1, Farbe)] für Netze ohne Kennung (STEP-Netz des Rohrs), legende = [(Text, Farbe)] zusätzlich zur
        Legende der Flächenarten. Ohne Argumente: aus."""
        self.kosten_linien = {k: QColor(f) for k, f in (linien or {}).items()}
        self.kosten_z = [(z0, z1, QColor(f)) for z0, z1, f in (z_bereiche or ())]
        self.kosten_legende = list(legende or ()) if (self.kosten_linien or self.kosten_z) else []
        self.update()

    def folge_setzen(self, schritte=None, aktuell=None, text=""):
        """Schneidvorschau (Recherche 16.11.2026 V1/V2): schritte = schneidfolge.schritte (Linienzüge, Einstich,
        Mikrostege, Nummer je Schritt), aktuell = Index des gezeigten Schritts (None = alle mit Nummern), text =
        Zeile über dem Bedienhinweis. Ohne Argumente: aus."""
        self.folge, self.folge_akt, self.folge_text = list(schritte or ()), aktuell, text if schritte else ""
        self.update()

    @staticmethod
    def _pfeil(p, q, farbe):
        """Pfeilspitzen auf dem Linienzug q (QPointF): in der Mitte und am Ende, in Fahrtrichtung."""
        if len(q) < 2:
            return
        laengen = [math.hypot(b.x() - a.x(), b.y() - a.y()) for a, b in zip(q, q[1:])]
        ges = sum(laengen)
        if ges < 12:
            return
        p.setPen(QPen(farbe, 1.5))
        for ziel in (ges / 2, ges - 0.5):
            s_ = 0.0
            for (a, b), lg in zip(zip(q, q[1:]), laengen):
                if s_ + lg >= ziel and lg > 1e-6:
                    t = (ziel - s_) / lg
                    sp = QPointF(a.x() + (b.x() - a.x()) * t, a.y() + (b.y() - a.y()) * t)
                    ux, uy = (b.x() - a.x()) / lg, (b.y() - a.y()) / lg
                    for dreh in (0.45, -0.45):
                        c, s2 = math.cos(math.pi + dreh), math.sin(math.pi + dreh)
                        p.drawLine(sp, QPointF(sp.x() + 9 * (ux * c - uy * s2), sp.y() + 9 * (ux * s2 + uy * c)))
                    break
                s_ += lg

    def _folge_zeichnen(self, p, bild):
        """Schneidfolge über dem Bild: geschnittene Schritte grau, der aktuelle dick orange, die übrigen dünn blau;
        Einstich grüner Punkt, Mikrostege gelbe Balken, Leerweg des Kopfs mit Pfeilen (schneidfolge.kopf_weg: hoch, um
        das Rohr, runter; violett mit Punkten oben und Höhe, wenn der Kopf hebt, sonst gestrichelt), Nummern im Kreis."""
        akt = self.folge_akt
        fm = p.fontMetrics()
        for i, x in enumerate(self.folge):
            if akt is None:
                f, w = FOLGE_OFFEN, 2.5
            elif i < akt:
                f, w = FOLGE_FERTIG, 2.5
            elif i == akt:
                f, w = FOLGE_AKTUELL, 4.5
            else:
                f, w = FOLGE_OFFEN, 1.5
            p.setPen(QPen(f, w, Qt.SolidLine, Qt.RoundCap))
            for pk in x["punkte"]:
                q = [bild(v) for v in pk]
                for a, b in zip(q, q[1:]):
                    p.drawLine(QPointF(a[0], a[1]), QPointF(b[0], b[1]))
        bis = len(self.folge) if akt is None else akt + 1
        for a, b in zip(self.folge[:bis], self.folge[1:bis]):      # Leerweg des Kopfs von Einstich zu Einstich
            hub = b.get("hub") in ("sprung", "drehen")
            farbe = FOLGE_HUB if hub else FOLGE_LEER
            kw = b.get("kopf") or {}
            q = [bild(v) for v in (kw.get("punkte") or [a["start"], b["start"]])]
            q = [QPointF(v[0], v[1]) for v in q]
            p.setPen(QPen(farbe, 2.0 if hub else 1.5, Qt.SolidLine if kw.get("oben") else Qt.DashLine))
            p.drawPolyline(q)
            self._pfeil(p, q, farbe)
            p.setPen(QPen(farbe, 1.0))
            p.setBrush(QBrush(farbe))
            for v in kw.get("oben") or ():     # Kopf oben: Punkt wie in ArTube
                w = bild(v)
                p.drawEllipse(QPointF(w[0], w[1]), 3.5, 3.5)
            p.setBrush(Qt.NoBrush)
            ist_akt = akt is not None and b is self.folge[akt]
            if hub and (ist_akt or (akt is None and b.get("hub") == "drehen")):     # Höhe am höchsten Punkt
                ob = kw.get("oben") or ()
                if len(ob) == 2 and len(q) <= 4:        # Sprung: Mitte der oberen Strecke
                    m_ = bild(tuple((ob[0][k] + ob[1][k]) / 2 for k in range(3)))
                    m_ = QPointF(m_[0], m_[1])
                else:                                   # Drehen: Mitte des Bogens
                    m_ = q[len(q) // 2]
                p.setPen(QPen(farbe, 1.0))
                p.drawText(QPointF(m_.x() + 4, m_.y() - 8), f"{b.get('hub_mm') or 0:.0f} mm".replace(".", ","))
        for i, x in enumerate(self.folge):
            if akt is not None and i > akt:
                continue
            for st in x["stege"]:           # Steg: gelber Balken auf der Kontur, Raute in der Mitte (sichtbar klein)
                q = [bild(v) for v in st]
                p.setPen(QPen(FOLGE_STEG, 6.0, Qt.SolidLine, Qt.FlatCap))
                for a, b in zip(q, q[1:]):
                    p.drawLine(QPointF(a[0], a[1]), QPointF(b[0], b[1]))
                m = q[len(q) // 2]
                p.setPen(QPen(stil.farbe("#5A4A00"), 1.0))
                p.setBrush(QBrush(FOLGE_STEG))
                p.drawPolygon([QPointF(m[0], m[1] - 5), QPointF(m[0] + 5, m[1]), QPointF(m[0], m[1] + 5),
                               QPointF(m[0] - 5, m[1])])
            for zug in x.get("schnitte") or ():      # Abfall zerschneiden bzw. Abfallschnitte (Linienzüge)
                q = [bild(v) for v in zug]
                p.setPen(QPen(FOLGE_ZERTEILT, 3.0, Qt.DashLine))
                p.drawPolyline([QPointF(v[0], v[1]) for v in q])
            s0 = bild(x["start"])
            if x.get("anfahrt"):        # Anfahrweg: Einstich auf dem Abfall (Ring), Linie zur Kontur
                pa = bild(x["anfahrt"][0])
                p.setPen(QPen(FOLGE_START, 2.0))
                p.drawLine(QPointF(pa[0], pa[1]), QPointF(s0[0], s0[1]))
                p.setBrush(Qt.NoBrush)
                p.drawEllipse(QPointF(pa[0], pa[1]), 3.5, 3.5)
            p.setPen(QPen(stil.farbe("#FFFFFF"), 1.5))
            p.setBrush(QBrush(FOLGE_START))
            p.drawEllipse(QPointF(s0[0], s0[1]), 4.5, 4.5)
            if akt is None or i == akt or len(self.folge) <= 30:
                t = str(x["nr"])
                r = max(8.0, fm.horizontalAdvance(t) / 2 + 4)
                m = QPointF(s0[0] + 10 + r, s0[1] - 10 - r)
                p.setPen(QPen(FOLGE_AKTUELL if i == akt else FOLGE_OFFEN, 1.2))
                p.setBrush(QBrush(stil.farbe("#FFFFFF")))
                p.drawEllipse(m, r, r)
                p.drawText(QRectF(m.x() - r, m.y() - r, 2 * r, 2 * r), Qt.AlignCenter, t)
        p.setBrush(Qt.NoBrush)
        if self.folge_text:
            breite = min(self.width() - 20, fm.horizontalAdvance(self.folge_text) + 12)
            feld = QColor(HINTERGRUND_OBEN)
            feld.setAlpha(220)
            p.fillRect(QRectF(6, self.height() - 44, breite, 20), feld)
            p.setPen(stil.farbe("#202020"))
            p.drawText(QRectF(12, self.height() - 44, self.width() - 24, 20), Qt.AlignLeft | Qt.AlignVCenter,
                       fm.elidedText(self.folge_text, Qt.ElideRight, int(self.width() - 24)))

    def messen_setzen(self, an, punkte=2, art=None):
        """Messen: zwei Punkte des Modells anklicken (fängt die nächste Ecke oder Konturmitte), Abstand in mm;
        art MESS_WINKEL: drei Punkte, Winkel am mittleren. punkte = 0: Linienzug mit beliebig vielen Punkten (Naht
        zeichnen), Signal gemessen nach jedem Punkt mit der Länge des Zugs. Fertige Messungen bleiben als Maß
        stehen (masse_loeschen)."""
        if an and self.explo.aktiv():       # V6: in der Explosion stimmen Abstände zwischen Teilen nicht
            self.tafel.zeigen(["Messen ist in der Explosionsansicht gesperrt (die Teile sind nur für die Anzeige "
                               "auseinandergezogen). Explosion auf 0 stellen, dann messen."])
            self.messen_geaendert.emit()
            return
        self.mess_art = art or MESS_ABSTAND
        if self.mess_art == MESS_WINKEL and punkte:
            punkte = 3
        if an and self.wahl.an:             # Messen und Auswahl schließen sich aus
            self.wahl.an = False
            self.wahl.schwebe = None
            self.wahl.geaendert.emit()
        self.messen, self.messpunkte, self.mess_max = bool(an), [], punkte or 0
        self.mess_treffer, self._schwebe = [], None
        self.setCursor(Qt.CrossCursor if an else Qt.ArrowCursor)
        self._maus_verfolgen()
        if not an:
            self.tafel.zeigen([])
        self.update()
        self.messen_geaendert.emit()

    def schnitt_setzen(self, punkte):
        """Stelle des Querschnitts als Linienzug [(x, y, z)] hervorheben ([] = aus)."""
        self.schnitt_linie = list(punkte or ())
        self.update()

    def masse_loeschen(self):
        self.masse_fest, self.messpunkte, self.mess_treffer = [], [], []
        self.tafel.zeigen([])
        self.update()

    # ------------------------------------------------------------ Stehende Maße verwalten (Messplan M2)
    def masse_liste(self):
        """Stehende Maße als mess_protokoll.Mass (alte (Punkte, Text)-Einträge werden umgewandelt)."""
        self.masse_fest = [mess_protokoll.als_mass(m) for m in self.masse_fest]
        return list(self.masse_fest)

    def mass_aendern(self, nr, **aenderung):
        """Maß nr ändern (name, sichtbar). Am Teil ändert sich nichts."""
        liste = self.masse_liste()
        if 0 <= nr < len(liste):
            self.masse_fest[nr] = liste[nr].kopie(**aenderung)
            self.update()

    def mass_entfernen(self, nummern):
        weg = set(nummern)
        self.masse_fest = [m for i, m in enumerate(self.masse_liste()) if i not in weg]
        self.update()

    def _mass_lage(self):
        try:
            return self.geometrie().lage if self.modell is not None else None
        except Exception:       # noqa: BLE001 – ohne Modell: Zahlen ohne Achsnamen
            return None

    def masse_klartext(self):
        return mess_protokoll.klartext(self.masse_liste(), self._mass_lage())

    def masse_kopieren(self):
        from PySide6.QtGui import QGuiApplication
        QGuiApplication.clipboard().setText(self.masse_klartext())

    def masse_csv(self, pfad, kopf=()):
        with open(pfad, "w", encoding="utf-8-sig", newline="") as f:
            f.write(mess_protokoll.csv_text(self.masse_liste(), self._mass_lage(), kopf))
        return pfad

    def bild_png(self):
        """Bild der Ansicht, wie gerade zu sehen (PNG-Bytes) oder None."""
        from PySide6.QtCore import QBuffer, QIODevice
        try:
            puffer = QBuffer()
            puffer.open(QIODevice.WriteOnly)
            self.grab().save(puffer, "PNG")
            return bytes(puffer.data())
        except Exception:       # noqa: BLE001 – ohne Bild weiter
            return None

    def masse_pdf(self, pfad, titel="Messprotokoll", angaben=(), einst=None):
        """Messprotokoll mit Bild der Ansicht (wie gerade zu sehen, mit den sichtbaren Maßen)."""
        return mess_protokoll.pdf_schreiben(pfad, self.masse_liste(), titel, angaben, self.bild_png(),
                                            self._mass_lage(), einst)

    def teil_messung(self):
        """Rohr-, Kontur- und Fertigungsmessung des gezeigten Teils (Messplan M3) als Gruppen [(Titel, [Zeilen])].
        Dichte und Prüfregeln: mess_kontext (dichte kg/dm³, werkstoff), sonst Stahl angenommen bzw. die Prüfregeln
        der Datenbank. Ändert nichts am Teil."""
        from . import dfm, mess_teil
        if self.modell is None:
            return []
        kontext = dict(getattr(self, "mess_kontext", None) or {})
        tris = mess_teil.material_dreiecke(self.modell)
        volumen = None
        if 0 < len(tris) <= mess_kern.KOERPER_MAX:
            w = mess_kern.werte(dict(typ="koerper", dreiecke=tris))
            if w.get("geschlossen"):
                volumen = w.get("volumen")
        try:
            regeln = dfm.regeln(_speicher.zeilen("pruefregeln")) if _speicher is not None else dfm.regeln()
        except Exception:       # noqa: BLE001 – Prüfregeln sind Zusatz: Vorgaben
            regeln = dfm.regeln()
        m = mess_teil.messen(self.modell, gefiltert(self.netz, self.modus), self.geometrie().kreise, volumen,
                             kontext.get("dichte"), regeln)
        gr = mess_teil.gruppen(m)
        if kontext.get("werkstoff"):
            gr[0][1].insert(1, f"Werkstoff: {kontext['werkstoff']}")
        return gr

    def teil_messen(self):
        from . import mess_teil_dialog
        mess_teil_dialog.TeilMessung(self).exec()

    def mass_aktionen(self):
        """Knöpfe der Mess-Tafel nach einer fertigen Messung."""
        return [("Maße …", lambda: self.masse_verwalten(), "Alle stehenden Maße: umbenennen, ein-/ausblenden, löschen, "
                 "kopieren, CSV, Messprotokoll (PDF)")]

    def masse_verwalten(self):
        from . import mess_liste
        mess_liste.MessListe(self).exec()

    def masse_menue(self, m):
        """Untermenü „Maße“ (Rechtsklick und Leisten)."""
        m.setToolTipsVisible(True)
        n = len(self.masse_fest)
        m.addAction(f"Maße verwalten … ({n})", self.masse_verwalten)
        for text, fn in (("Alle kopieren", self.masse_kopieren), ("Alle löschen", self.masse_loeschen)):
            x = m.addAction(text, fn)
            x.setEnabled(bool(n))
        return m

    def abstand(self):
        """Gemessener Abstand [mm] (Linienzug: Länge des Zugs) oder None (auch beim Winkel)."""
        if self.mess_art == MESS_WINKEL:
            return None
        if len(self.messpunkte) == 2 or (not self.mess_max and len(self.messpunkte) > 1):
            return sum(math.dist(a, b) for a, b in zip(self.messpunkte, self.messpunkte[1:]))
        return None

    def winkel(self):
        """Gemessener Winkel [°] am mittleren von drei Punkten oder None."""
        if self.mess_art != MESS_WINKEL or len(self.messpunkte) != 3:
            return None
        return winkel_bei(*self.messpunkte)

    def mess_text(self, punkte=None):
        """Ergebnis als Text: Abstand mit Δx/Δy/Δz bzw. Winkel; None solange unvollständig."""
        pk = self.messpunkte if punkte is None else punkte
        tr = self.mess_treffer
        if punkte is None and self.mess_art == MESS_ABSTAND and len(pk) == 2 and len(tr) == 2 and \
                [tuple(t["punkt"]) for t in tr] == [tuple(q) for q in pk]:
            return self.geometrie().vergleich(*tr)[0]          # exakter Wert (Fläche, Kante, Achse …)
        if len(pk) == 3:
            return f"Winkel {_zahl(winkel_bei(*pk))}°"
        if len(pk) == 2:
            a, b = pk
            return (f"Abstand {_zahl(math.dist(a, b))} mm (Δx {_zahl(abs(b[0] - a[0]))}, "
                    f"Δy {_zahl(abs(b[1] - a[1]))}, Δz {_zahl(abs(b[2] - a[2]))})")
        return None

    def punkt_zurueck(self):
        """Letzten Punkt des Linienzugs entfernen."""
        self.messpunkte = self.messpunkte[:-1]
        self.mess_treffer = self.mess_treffer[:len(self.messpunkte)]
        self.update()
        self.gemessen.emit(self.abstand())

    def bildpunkt(self, modell=None):
        """Funktion Modellpunkt (x, y, z) -> (Pixel x, Pixel y, Tiefe) für die aktuelle Ansicht (wie gezeichnet).
        modell: Stufe, deren Maßstab gilt (beim Drehen die grobe), sonst das Modell."""
        modell = modell or self.modell
        if self._gl is not None:
            from .ansicht3d_gl import abbildung
            m = _drehung(self.gier, self.nick, self.roll)
            s, ox, oy = abbildung(modell, max(1, self.width()), max(1, self.height()), m, self.zoom, self.versatz,
                                  persp_faktor(modell, self.perspektive))
        else:
            m, _, s, ox, oy = projektion(modell, self.width(), self.height(), self.gier, self.nick, self.zoom,
                                         self.versatz, self.perspektive, self.roll)
        cx, cy, cz = modell.mitte
        pz = persp_faktor(modell, self.perspektive)

        def bild(v):
            x, y, z = v[0] - cx, v[1] - cy, v[2] - cz
            t = m[2][0] * x + m[2][1] * y + m[2][2] * z
            f = s / (1.0 - t * pz) if pz else s
            return (ox + (m[0][0] * x + m[0][1] * y + m[0][2] * z) * f,
                    oy - (m[1][0] * x + m[1][1] * y + m[1][2] * z) * f, t)
        return bild

    def klicken(self, x, y):
        """Klick an Pixel (x, y): Messpunkt setzen bzw. nächste Linie wählen (Signal angeklickt)."""
        if self.modell is None:
            return None
        bild = self.bildpunkt()
        if self.messen and self.mess_max:
            return self._messen_klick(bild, x, y)
        if self.messen:             # Naht zeichnen (Linienzug): Ecken des Netzes und Punkte der Konturen
            beste = None
            # Ecken des Netzes und Punkte der Schnittkonturen (Mitte zwischen zwei Konturen messen)
            for v in itertools.chain(self.modell.punkte, (li[0] for li in self.modell.linien), self.modell.mitten):
                px, py, t = bild(v)
                d = math.hypot(px - x, py - y)
                if d <= 14 and (beste is None or (d - t * 1e-3) < beste[0]):
                    beste = (d - t * 1e-3, v)
            if beste is None:
                return None
            if not self.mess_max and self.messpunkte and self.messpunkte[-1] == tuple(beste[1]):
                return beste[1]                             # Linienzug: derselbe Punkt nochmal zählt nicht
            voll = self.mess_max and len(self.messpunkte) >= self.mess_max
            self.messpunkte = ([] if voll else self.messpunkte) + [tuple(beste[1])]
            fertig = self.mess_max and len(self.messpunkte) == self.mess_max
            if fertig:
                self.masse_fest.append(mess_protokoll.Mass(self.messpunkte, self.mess_text(),
                                                           mess_protokoll.WINKEL if self.mess_art == MESS_WINKEL
                                                           else None))
            self.update()
            if fertig or not self.mess_max:
                self.gemessen.emit(self.winkel() if self.mess_art == MESS_WINKEL else self.abstand())
            return beste[1]
        beste = None
        for nr, (a, b, _, _) in enumerate(self.modell.linien):
            pa, pb = bild(a), bild(b)
            dx, dy = pb[0] - pa[0], pb[1] - pa[1]
            lg = dx * dx + dy * dy
            t = 0.0 if lg < 1e-9 else max(0.0, min(1.0, ((x - pa[0]) * dx + (y - pa[1]) * dy) / lg))
            d = math.hypot(pa[0] + t * dx - x, pa[1] + t * dy - y)
            if d <= 8 and (beste is None or d < beste[0]):
                beste = (d, nr, tuple(a[k] + t * (b[k] - a[k]) for k in range(3)))
        if beste is None:
            treffer = self._flaeche_treffer(bild, x, y)
            kt = self.koerper_unter(x, y)        # Klick in einen Schnittkörper (z. B. ins Loch) wählt seine Kontur
            if kt is not None and (treffer is None or kt[0] >= treffer["tiefe"]):
                pk = kt[1]["punkte"]
                treffer = dict(id=kt[1]["id"], punkt=tuple(sum(q[i] for q in pk) / len(pk) for i in range(3)))
            if treffer is None:
                return None
            treffer.pop("tiefe", None)
            self.angeklickt.emit(treffer)
            return treffer
        kn = self.modell.linien_id[beste[1]] if beste[1] < len(self.modell.linien_id) else None
        if kn is None and getattr(self, "flaeche_vor_kante", False):
            # Baugruppe/Satz: Klick nahe einer Körperkante (ohne Merkmal) wählt die Fläche darunter, also ihr Teil
            treffer = self._flaeche_treffer(bild, x, y)
            if treffer is not None:
                treffer.pop("tiefe", None)
                self.angeklickt.emit(treffer)
                return treffer
        treffer = dict(id=kn, punkt=beste[2])
        self.angeklickt.emit(treffer)
        return treffer

    def flaeche_unter(self, x, y):
        """Fläche mit Merkmal unter dem Pixel (x, y): dict(id, punkt) oder None."""
        if self.modell is None:
            return None
        treffer = self._flaeche_treffer(self.bildpunkt(), x, y)
        if treffer is not None:
            treffer.pop("tiefe", None)
        return treffer

    def _flaeche_treffer(self, bild, x, y):
        """Vorderstes Dreieck mit Merkmal (netz 'ti') unter dem Pixel (x, y): dict(id, punkt) oder None."""
        mo = self.modell
        if not mo.dreiecke_id:
            return None
        beste = None
        for (i, j, k, _, _), kn in zip(mo.dreiecke, mo.dreiecke_id):
            if kn is None:
                continue
            a, b, c = bild(mo.punkte[i]), bild(mo.punkte[j]), bild(mo.punkte[k])
            det = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
            if abs(det) < 1e-9:
                continue
            l1 = ((b[1] - c[1]) * (x - c[0]) + (c[0] - b[0]) * (y - c[1])) / det
            l2 = ((c[1] - a[1]) * (x - c[0]) + (a[0] - c[0]) * (y - c[1])) / det
            l3 = 1 - l1 - l2
            if min(l1, l2, l3) < -1e-6:
                continue
            tiefe = l1 * a[2] + l2 * b[2] + l3 * c[2]           # größer = näher am Betrachter
            if beste is None or tiefe > beste[0]:
                pa, pb, pc = mo.punkte[i], mo.punkte[j], mo.punkte[k]
                beste = (tiefe, kn, tuple(l1 * pa[m] + l2 * pb[m] + l3 * pc[m] for m in range(3)))
        return None if beste is None else dict(id=beste[1], punkt=beste[2], tiefe=beste[0])

    def modus_setzen(self, modus):
        """Vorschau Original / Rohrgeometrie / Gravurkonturen (MODI); Blickrichtung bleibt."""
        self.modus = modus
        if self.netz:
            self._modell_setzen(Modell(self._gezeigt(), geprueft=True))
            self._geo, self._tipp = None, None
        self.update()

    def zuruecksetzen(self):
        self.gier, self.nick = self.GRUND
        self.roll = 0.0
        self.zoom, self.versatz, self._maus = 1.0, (0.0, 0.0), None
        self.update()

    def ansicht(self, gier, nick, roll=0.0):
        self.gier, self.nick, self.zoom, self.versatz = gier, nick, 1.0, (0.0, 0.0)
        self.roll = roll
        self.update()
        self.gedreht.emit()

    def blick(self, name):
        """Feste Blickrichtung nach Namen (BLICKE: Isometrie, Vorn, Hinten, Oben, Unten, Ende A, Ende B)."""
        if name == ISOMETRIE:
            self.ansicht(*self.GRUND)
            return
        n = dict(BLICKE).get(name)
        if n is not None:
            self.ansicht(*blick_auf(n))

    def drehen(self, schritte_gier=0, schritte_nick=0, schritte_roll=0, winkel=math.pi / 2):
        """Schrittweise drehen (Strg + Pfeiltasten 90°, Alt + Pfeiltasten 15°, Strg/Alt + Bild auf/ab um die
        Blickachse): waagrecht um die Hochachse des Bildschirms, senkrecht ohne Grenze auch über Kopf (19.11.2026)."""
        g, n, r = self.gier, self.nick, self.roll
        for achse, k in (("y", schritte_gier), ("x", schritte_nick), ("z", schritte_roll)):
            if k:
                g, n, r = navigation3d.um_achse(g, n, r, achse, k * winkel)
        self.gier, self.nick, self.roll = (round(w, 12) for w in (g, n, r))
        self.update()
        self.gedreht.emit()

    def drehen_um(self, achse, grad):
        """Um eine Achse um grad Grad drehen: 'x', 'y', 'z' = Bildschirm (quer, hoch, Blickachse), 'X', 'Y', 'Z' =
        Achse des Modells (exakte Winkeleingabe)."""
        w = math.radians(float(grad))
        f = navigation3d.um_achse if achse in "xyz" else navigation3d.um_modellachse
        self.gier, self.nick, self.roll = f(self.gier, self.nick, self.roll, achse, w)
        self.update()
        self.gedreht.emit()

    def _nachlaufen(self):
        dx, dy = self._tempo
        if abs(dx) + abs(dy) < 0.05 or self.modell is None:
            self._nachlauf.stop()
            self._eilig = False
            self.update()
            return
        self.gier, self.nick, self.roll = navigation3d.ziehen(self.gier, self.nick, self.roll, dx, dy, self.nav)
        k = float(self.nav.get("nav_nachlauf") or 0.9)     # V4: Stärke des Nachlaufs (0,5 kurz … 0,97 lang)
        self._tempo = (dx * k, dy * k)
        self._eilig = True
        self.update()
        self.gedreht.emit()

    def perspektive_setzen(self, an, merken=True):
        """Perspektivisch (an) oder orthogonal zeichnen; merken: Wahl je Benutzer speichern."""
        self.perspektive = bool(an)
        if merken:
            _perspektive_merken(self.perspektive)
        self.update()
        self.gedreht.emit()

    def auswahl_punkte(self):
        """Punkte des Gewählten: markierte Merkmale (Linien) bzw. der markierte Bereich, sonst die Messpunkte."""
        mo = self.modell
        if mo is None:
            return [], None
        pk, normalen = [], []
        z = self.markiert_z
        for nr, (a, b, _, n) in enumerate(mo.linien):
            kn = mo.linien_id[nr] if nr < len(mo.linien_id) else None
            if (kn is not None and kn in self.markiert) or \
                    (z is not None and z[0] - 1e-6 <= a[2] <= z[1] + 1e-6 and z[0] - 1e-6 <= b[2] <= z[1] + 1e-6):
                pk += [a, b]
                normalen.append(n)
        if not pk and self.markiert:        # Merkmal nur als Fläche (netz 'ti')
            for (i, j, k, _, n), kn in zip(mo.dreiecke, mo.dreiecke_id):
                if kn in self.markiert:
                    pk += [mo.punkte[i], mo.punkte[j], mo.punkte[k]]
                    normalen.append(n)
        if not pk:
            pk = list(self.messpunkte) or [q for punkte, _ in self.masse_fest[-1:] for q in punkte]
        if not normalen:
            return pk, None
        s = [sum(n[i] for n in normalen) for i in range(3)]
        betrag = math.sqrt(sum(c * c for c in s))
        return pk, (tuple(c / betrag for c in s) if betrag > 1e-6 else None)

    def auf_auswahl(self):
        """„Auf Auswahl“: senkrecht auf das gewählte Merkmal schauen (mittlere Normale) und es groß in die Mitte
        holen. False, wenn nichts gewählt ist. Mit der Auswahl (wahl): auf das dort Gewählte zoomen."""
        if self.wahl.an and self.wahl.gewaehlt:
            return self.wahl.auf_auswahl()
        pk, n = self.auswahl_punkte()
        if not pk:
            return False
        if n is not None:
            self.gier, self.nick = blick_auf(n)
        self.zoom, self.versatz = 1.0, (0.0, 0.0)
        bild = self.bildpunkt()
        px = [bild(v) for v in pk]
        x0, x1 = min(q[0] for q in px), max(q[0] for q in px)
        y0, y1 = min(q[1] for q in px), max(q[1] for q in px)
        w, h = max(1, self.width()), max(1, self.height())
        k = max(1.0, min(40.0, 0.45 * min(w / max(x1 - x0, 4.0), h / max(y1 - y0, 4.0))))
        self.zoom = k
        self.versatz = (-((x0 + x1) / 2 - w / 2) * k, -((y0 + y1) / 2 - h / 2) * k)
        self.update()
        self.gedreht.emit()
        return True

    def vorher_zeigen(self, an):
        """Vorher-Nachher (V3): den Stand beim Öffnen gestrichelt über das jetzige Modell legen. False ohne
        gemerkten Stand."""
        self.vorher_an = bool(an) and self.vorher_netz is not None
        if self.vorher_an and (self._vorher_modell is None or self._vorher_modell[0] is not self.vorher_netz):
            self._vorher_modell = (self.vorher_netz, Modell(self.vorher_netz))
        self.update()
        self.messen_geaendert.emit()        # Leiste stellt ihren Knopf
        return self.vorher_an

    def _vorher_zeichnen(self, p):
        mo = self._vorher_modell[1] if self.vorher_an and self._vorher_modell else None
        if mo is None or self.modell is None:
            return
        bild = self.bildpunkt()
        p.save()
        p.setRenderHint(QPainter.Antialiasing, True)
        farbe = QColor(VORHER)
        farbe.setAlpha(170)
        p.setPen(QPen(farbe, 1.4, Qt.DashLine))
        striche = [(a, b) for a, b, _, _ in mo.linien]
        if len(mo.dreiecke) <= KANTEN_MAX:
            striche += [(a, b) for a, b, _ in mo.kanten()]
        for a, b in striche:
            pa, pb = bild(a), bild(b)
            p.drawLine(QPointF(pa[0], pa[1]), QPointF(pb[0], pb[1]))
        p.restore()

    def grob_modell(self):
        """Die grobe Stufe, die beim Drehen gezeichnet wird (Größe nach _grob_anzahl); Drehpunkt und Treffer nehmen
        dieselbe, sonst springt der Punkt unter der Maus."""
        return self.modell.grob(self._grob_anzahl()) if self.modell is not None else None

    def _grob_anzahl(self):
        """Dreiecke der groben Stufe (V3): so viele, wie in GROB_ZEIT gezeichnet werden (gemessen am letzten feinen
        Bild), zwischen GROB_MIN und GROB_DREIECKE, auf 1000 gerundet (damit die Stufe gemerkt bleibt)."""
        t = getattr(self, "_zeit_je_dreieck", None)
        if not t:
            return GROB_DREIECKE
        n = int(GROB_ZEIT / t) // 1000 * 1000
        return max(GROB_MIN, min(GROB_DREIECKE, n))

    def einpassen(self):
        """Einpassen (Taste F, V3): Blickrichtung bleibt, Zoom und Versatz so, dass das ganze Modell (bzw. die Auswahl
        der Auswahl-Werkzeuge) das Bild füllt. False ohne Modell."""
        if self.modell is None:
            return False
        if self.wahl.an and self.wahl.gewaehlt:
            pk = self.wahl.punkte() or []
        else:
            pk = self.modell.punkte
        if not pk:
            return False
        schritt = max(1, len(pk) // 20000)          # große Netze: jeder n-te Punkt genügt für den Rahmen
        self.zoom, self.versatz = 1.0, (0.0, 0.0)
        bild = self.bildpunkt()
        px = [bild(v) for v in pk[::schritt]]
        x0, x1 = min(q[0] for q in px), max(q[0] for q in px)
        y0, y1 = min(q[1] for q in px), max(q[1] for q in px)
        w, h = max(1, self.width()), max(1, self.height())
        k = max(0.2, min(40.0, 0.9 * min(w / max(x1 - x0, 4.0), (h - 60) / max(y1 - y0, 4.0))))
        self.zoom = k
        self.versatz = (-((x0 + x1) / 2 - w / 2) * k, -((y0 + y1) / 2 - h / 2) * k)
        self.update()
        self.gedreht.emit()
        return True

    def paintEvent(self, _):
        if self._gl is not None:        # zeichnet die OpenGL-Fläche (mit _beschriften)
            return
        p = QPainter(self)
        from . import tempo
        try:
            with tempo.abschnitt("3D: Bild zeichnen (ohne OpenGL)"):
                self._malen(p)
        except Exception as e:      # noqa: BLE001 – V1: ein Fehler beim Zeichnen beendet nie das Programm
            self._bild, self._fehler = None, f"Zeichnen gescheitert ({type(e).__name__}: {e})"
            hintergrund_malen(p, self.rect())
            self._fehler_zeigen(p)
        finally:
            p.end()

    def _fehler_zeigen(self, p):
        p.setPen(stil.farbe("#B42318"))
        p.drawText(self.rect().adjusted(20, 20, -20, -20), Qt.AlignCenter | Qt.TextWordWrap,
                   f"{self._fehler}\n\nDie Ansicht lässt sich mit einem neuen Modell (z. B. Editor neu öffnen) "
                   "wiederherstellen; die Kalkulation ist davon nicht betroffen.")

    def _malen(self, p):
        hintergrund_malen(p, self.rect())
        if self.modell is None and getattr(self, "_fehler", None):
            self._fehler_zeigen(p)
            return
        if self.modell is None:
            p.setPen(stil.farbe("#7F7F7F"))
            p.drawText(self.rect(), Qt.AlignCenter | Qt.TextWordWrap,
                       "Keine 3D-Daten.\nDie 3D-Ansicht gibt es für Teile, die per STEP-Import übernommen wurden.")
            return
        grob = self._eilig or self._maus is not None
        modell = self.grob_modell() if grob else self.modell
        schluessel = (modell, self.width(), self.height(), self.devicePixelRatioF(), self.gier, self.nick, self.roll,
                      self.zoom, self.versatz, self.darstellung, self.blass(), self.perspektive, self.koerper_an,
                      tuple(sorted(self.markiert)) if modell.koerper else (), visualisierung.schluessel())
        if self._bild is None or self._bild[0] != schluessel:
            dpr = self.devicePixelRatioF()
            bild = QPixmap(int(self.width() * dpr), int(self.height() * dpr))
            bild.setDevicePixelRatio(dpr)
            bild.fill(Qt.transparent)
            q = QPainter(bild)
            t0 = time.perf_counter()
            try:
                zeichnen(q, modell, self.width(), self.height(), self.gier, self.nick, self.zoom, self.versatz, roll=self.roll,
                         linien=modell is self.modell, glatt=not grob, darstellung=self.darstellung,
                         blass=self.blass(), perspektive=self.perspektive, koerper=self.koerper_an,
                         gewaehlt=self.markiert)
            finally:
                q.end()     # nie ein offenes QPainter am Bild lassen (sonst Absturz beim Aufräumen)
            if not grob:    # V3: Zeit je Dreieck merken, daraus die grobe Stufe fürs flüssige Drehen
                self._zeit_je_dreieck = (time.perf_counter() - t0) / max(1, len(modell.dreiecke))
            self._bild = (schluessel, bild)
        self._schatten_malen(p)         # V2: weicher Kontaktschatten unter dem Modell
        self._raster_malen(p)           # A7: hinter dem Modell (das Bild des Modells ist außen durchsichtig)
        p.drawPixmap(0, 0, self._bild[1])
        self._beschriften(p)

    def _beschriften(self, p):
        """Titel, Legende der Flächenarten und Bedienhinweis über dem Bild (QPainter und OpenGL)."""
        if self.modell is None:
            p.setPen(stil.farbe("#7F7F7F"))
            p.drawText(self.rect(), Qt.AlignCenter | Qt.TextWordWrap,
                       "Keine 3D-Daten.\nDie 3D-Ansicht gibt es für Teile, die per STEP-Import übernommen wurden.")
            return
        p.setRenderHint(QPainter.Antialiasing, False)
        y = 8
        p.setPen(stil.farbe("#202020"))
        if self.titel:
            p.drawText(QRectF(10, y, self.width() - 20, 18), Qt.AlignLeft | Qt.AlignVCenter, self.titel)
            y += 20
        if getattr(self, "pruef_meldung", ""):      # V1: ausgelassene Stellen nie still
            p.setPen(stil.farbe("#B45309"))
            p.drawText(QRectF(10, y, self.width() - 20, 18), Qt.AlignLeft | Qt.AlignVCenter,
                       p.fontMetrics().elidedText(self.pruef_meldung, Qt.ElideRight, int(self.width() - 20)))
            y += 20
            p.setPen(stil.farbe("#202020"))
        legende = [(text, linie or visualisierung.flaechenfarbe(art) or farbe) for art, text, farbe, linie in ARTEN
                   if art in self.modell.arten and not (art in WK_ARTEN and not self.koerper_an)] \
            if getattr(self, "legende_an", True) else []
        if legende and self.darstellung == FLAECHENTYPEN:     # V5: Legende der Flächentypen statt der Flächenarten
            da = set(flaechentyp_arten(self.modell))
            legende = [(f"Fläche: {n}" if n != "Netz" else "Fläche ohne STEP-Art (ältere Messung)", f)
                       for n, f in FLAECHENTYP_FARBE.items() if f"FT_{n}" in da] + \
                [(text, linie) for art, text, _, linie in ARTEN if art in self.modell.arten and linie]
        legende += [(t, f) for t, f in getattr(self, "kosten_legende", ())]
        if self.vorher_an:
            legende.append(("Vorher (beim Öffnen, gestrichelt)", VORHER))
        if getattr(self, "folge", None):
            legende += [("Schneidfolge (aktuell)", FOLGE_AKTUELL), ("geschnitten", FOLGE_FERTIG),
                        ("Einstich, Anfahrweg", FOLGE_START), ("Leerweg Kopf", FOLGE_LEER)]
            if any(x.get("hub") in ("sprung", "drehen") for x in self.folge):
                legende.append(("Leerweg mit Kopf heben", FOLGE_HUB))
            if any(x["stege"] for x in self.folge):
                legende.append(("Mikrosteg", FOLGE_STEG))
            if any(x.get("schnitte") for x in self.folge):
                legende.append(("Abfall zerschneiden", FOLGE_ZERTEILT))
        # Legende in Spalten, wenn sie sonst in den Bedienhinweis unten liefe (kleine 3D-Ansicht im Editor: der
        # Hinweis lag über „Schweißnaht“, Plan 06.11.2026 E1)
        fm = p.fontMetrics()
        je_spalte = max(1, int((self.height() - 26 - y) // 18))
        x = 10
        if legende:     # Legende auf hellem Feld, damit sie über dem Modell lesbar bleibt (Layout-Prüfung 11.11.2026)
            spalten = [legende[i0:i0 + je_spalte] for i0 in range(0, len(legende), je_spalte)]
            b_ges = sum(min(220, max(fm.horizontalAdvance(t) for t, _ in sp)) + 34 for sp in spalten) - 10
            feld = QColor(HINTERGRUND_OBEN)
            feld.setAlpha(200)
            p.fillRect(QRectF(x - 4, y, b_ges + 4, 18 * min(je_spalte, len(legende)) + 2), feld)
        for i0 in range(0, len(legende), je_spalte):
            breite = 0
            for k, (text, farbe) in enumerate(legende[i0:i0 + je_spalte]):
                p.fillRect(QRectF(x, y + 18 * k + 3, 12, 12), QColor(farbe))
                p.setPen(stil.farbe("#202020"))
                p.drawText(QRectF(x + 18, y + 18 * k, 220, 18), Qt.AlignLeft | Qt.AlignVCenter, text)
                breite = max(breite, fm.horizontalAdvance(text))
            x += min(220, breite) + 34
        self._markierung_zeichnen(p)
        self._explosion_malen(p)
        self._achsen_malen(p)
        hw = self.anzeige_hinweis()
        if hw:                              # V6: Schnitt/Explosion deutlich als Anzeige kennzeichnen
            p.save()
            text = fm.elidedText(hw, Qt.ElideRight, int(self.width() - 40))
            br = fm.horizontalAdvance(text) + 16
            r = QRectF(self.width() - br - 10, 10, br, 22)
            p.setRenderHint(QPainter.Antialiasing, True)
            p.setPen(Qt.NoPen)
            p.setBrush(stil.farbe("#FFF4D6"))
            p.drawRoundedRect(r, 5, 5)
            p.setPen(stil.farbe("#7A4B00"))
            p.drawText(r, Qt.AlignCenter, text)
            p.restore()
        p.setPen(stil.farbe("#7F7F7F"))
        hinweis = self.werkzeug.hinweis() if self.werkzeug is not None and not self.messen else None
        if self.wahl.an and not self.messen:
            hinweis = ("Auswahl: Klick wählt, Strg+Klick dazu/weg, Umschalt+Ziehen = Fenster, Esc hebt auf · "
                       "H ausblenden, I isolieren, Umschalt+H alle einblenden, Strg+A alle, Strg+I umkehren · "
                       "rechte Maustaste: Menü")
        p.drawText(QRectF(10, self.height() - 22, self.width() - 20, 18), Qt.AlignLeft | Qt.AlignVCenter, fm.elidedText(
                   ("Winkel: drei Punkte anklicken, der mittlere ist der Scheitel" if self.mess_art == MESS_WINKEL
                    else "Messen: zwei Punkte anklicken (fängt Kreismitte, Kantenmitte, Ecke oder Fläche)"
                    if self.mess_max else
                    "Naht zeichnen: Punkte entlang der Naht anklicken (fängt die nächste Ecke)") if self.messen else
                   hinweis or
                   navigation3d.hinweis(navigation3d.werte_lesen(_speicher)) +     # nach der Mausbelegung (25.11.)
                   " · Doppelklick Ausgangsansicht · Tasten 1–6/0 Ansichten, F einpassen", Qt.ElideRight,
                   int(self.width() - 20)))
        if self._drehpunkt is not None and self._maus is not None and self._maus[2] == "drehen":
            x, y = self._drehpunkt[1]           # Drehpunkt beim Drehen zeigen
            p.setRenderHint(QPainter.Antialiasing, True)
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(stil.farbe("#FFFFFF"), 3))
            p.drawEllipse(QPointF(x, y), 5, 5)
            p.setPen(QPen(stil.farbe("#E07000"), 1.5))
            p.drawEllipse(QPointF(x, y), 5, 5)
            p.drawPoint(QPointF(x, y))
        self._schilder_zeichnen(p)

    def _schilder_zeichnen(self, p):
        """Schilder [(Punkt 3D, Text, Farbe)] über dem Modell (Nesting-Arbeitsplatz: Positionsnummer je Teil);
        sich überdeckende Schilder werden weggelassen (beim Zoomen erscheinen sie)."""
        schilder = getattr(self, "schilder", None)
        if not schilder or self.modell is None:
            return
        bild = self.bildpunkt()
        fm = p.fontMetrics()
        belegt = []
        p.save()
        p.setRenderHint(QPainter.Antialiasing, True)
        for punkt, text, farbe in schilder:
            x, y = bild(punkt)[:2]
            w = fm.horizontalAdvance(text) + 10
            r = QRectF(x - w / 2, y - 24, w, 17)
            if not QRectF(self.rect()).contains(r) or any(r.intersects(b) for b in belegt):
                continue
            belegt.append(r)
            p.setPen(QPen(QColor(farbe).darker(130), 1))
            p.setBrush(stil.farbe("#FFFFFF"))
            p.drawRoundedRect(r, 4, 4)
            p.drawLine(QPointF(x, r.bottom()), QPointF(x, y))
            p.setPen(stil.farbe("#202020"))
            p.drawText(r, Qt.AlignCenter, text)
        p.restore()

    def einpassen_auf(self, punkte, anteil=0.8):
        """Wie einpassen, aber auf die Punkte [(x, y, z)] (z. B. ein Teil auf der Stange). False ohne Punkte."""
        if self.modell is None or not punkte:
            return False
        self.zoom, self.versatz = 1.0, (0.0, 0.0)
        bild = self.bildpunkt()
        px = [bild(v) for v in punkte]
        x0, x1 = min(q[0] for q in px), max(q[0] for q in px)
        y0, y1 = min(q[1] for q in px), max(q[1] for q in px)
        w, h = max(1, self.width()), max(1, self.height())
        k = max(0.2, min(200.0, anteil * min(w / max(x1 - x0, 4.0), (h - 60) / max(y1 - y0, 4.0))))
        self.zoom = k
        self.versatz = (-((x0 + x1) / 2 - w / 2) * k, -((y0 + y1) / 2 - h / 2) * k)
        self.update()
        self.gedreht.emit()
        return True

    def _markierung_zeichnen(self, p):
        """Hervorgehobene Linien (Teile-Editor), Messung und Werkzeug (Griffe, Maße) über dem Bild."""
        if self.werkzeug is not None:
            p.save()
            self.werkzeug.zeichnen(p, self.bildpunkt())
            p.restore()
        self.wahl.zeichnen(p)
        self._vorher_zeichnen(p)
        self._hover_zeichnen(p)
        self._pruef_zeichnen(p)
        if not (self.markiert or self.markiert_z or self.messpunkte or self.masse_fest or self.schnitt_linie or
                self._schwebe or self.kosten_linien or self.kosten_z or self.folge):
            return
        bild = self.bildpunkt()
        if self.messen and self.mess_max:
            from .messen3d import fang_zeichnen
            for t in self.mess_treffer:
                fang_zeichnen(p, bild, t, MESSEN)
            if self._schwebe is not None:
                fang_zeichnen(p, bild, self._schwebe, FANG, beschriften=True)
        p.setRenderHint(QPainter.Antialiasing, True)
        if self.schnitt_linie:
            p.setPen(QPen(SCHNITT, 2.5, Qt.DashLine))
            pk = [bild(v) for v in self.schnitt_linie]
            for a, b in zip(pk, pk[1:]):
                p.drawLine(QPointF(a[0], a[1]), QPointF(b[0], b[1]))
        if self.kosten_linien or self.kosten_z:      # Kostentreiber (CAD-005) unter der grünen Markierung
            for nr, (a, b, _, _) in enumerate(self.modell.linien):
                kn = self.modell.linien_id[nr] if nr < len(self.modell.linien_id) else None
                f = self.kosten_linien.get(kn) if kn is not None else None
                if f is None:
                    f = next((f_ for z0, z1, f_ in self.kosten_z if z0 - 1e-6 <= a[2] <= z1 + 1e-6 and
                              z0 - 1e-6 <= b[2] <= z1 + 1e-6), None)
                if f is not None:
                    p.setPen(QPen(f, 3.5, Qt.SolidLine, Qt.RoundCap))
                    pa, pb = bild(a), bild(b)
                    p.drawLine(QPointF(pa[0], pa[1]), QPointF(pb[0], pb[1]))
        p.setPen(QPen(MARKIERT, 4.0, Qt.SolidLine, Qt.RoundCap))
        z = self.markiert_z
        for nr, (a, b, _, _) in enumerate(self.modell.linien):
            kn = self.modell.linien_id[nr] if nr < len(self.modell.linien_id) else None
            if (kn is not None and kn in self.markiert) or \
                    (z is not None and z[0] - 1e-6 <= a[2] <= z[1] + 1e-6 and z[0] - 1e-6 <= b[2] <= z[1] + 1e-6):
                pa, pb = bild(a), bild(b)
                p.drawLine(QPointF(pa[0], pa[1]), QPointF(pb[0], pb[1]))
        if self.folge:
            self._folge_zeichnen(p, bild)
        offen = [] if self.mess_max and len(self.messpunkte) == self.mess_max else [(self.messpunkte, None)]
        for m_ in self.masse_fest + offen:
            punkte, text = m_
            if not punkte or not getattr(m_, "sichtbar", True):
                continue
            if text and getattr(m_, "name", ""):
                text = f"{m_.name}: {text}"
            pk = [bild(v) for v in punkte]
            p.setPen(QPen(MESSEN, 2.0))
            for a, b in zip(pk, pk[1:]):
                p.drawLine(QPointF(a[0], a[1]), QPointF(b[0], b[1]))
            p.setBrush(QBrush(MESSEN))
            for q in pk:
                p.drawEllipse(QPointF(q[0], q[1]), 4, 4)
            p.setBrush(Qt.NoBrush)
            if text:
                m = pk[1] if len(pk) == 3 else ((pk[0][0] + pk[1][0]) / 2, (pk[0][1] + pk[1][1]) / 2)
                p.drawText(QRectF(m[0] + 8, m[1] - 20, 360, 18), Qt.AlignLeft | Qt.AlignVCenter, text)

    def punkt_unter(self, x, y):
        """Vorderster Punkt des Modells unter dem Pixel (x, y) oder None (daneben). Projiziert jeden Punkt nur einmal,
        prüft dann die Dreiecke über ihr Rechteck (schnell auch bei großen Baugruppen)."""
        mo = self.modell
        if mo is None:
            return None
        if len(mo.dreiecke) > DREHPUNKT_FEIN:
            mo = self.grob_modell()             # sehr große Netze: die Stufe, die beim Drehen zu sehen ist
        bild = self.bildpunkt(mo)
        px = list(map(bild, mo.punkte))
        pz = persp_faktor(mo, self.perspektive)     # perspektivisch: Gewichte je Ecke mit ihrem Faktor (exakt)
        beste = None
        for i, j, k, _, _ in mo.dreiecke:
            a, b, c = px[i], px[j], px[k]
            if (a[0] > x and b[0] > x and c[0] > x) or (a[0] < x and b[0] < x and c[0] < x) or \
                    (a[1] > y and b[1] > y and c[1] > y) or (a[1] < y and b[1] < y and c[1] < y):
                continue
            det = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
            if abs(det) < 1e-9:
                continue
            l1 = ((b[1] - c[1]) * (x - c[0]) + (c[0] - b[0]) * (y - c[1])) / det
            l2 = ((c[1] - a[1]) * (x - c[0]) + (a[0] - c[0]) * (y - c[1])) / det
            l3 = 1 - l1 - l2
            if min(l1, l2, l3) < -1e-6:
                continue
            if pz:
                l1, l2, l3 = l1 / (1.0 - a[2] * pz), l2 / (1.0 - b[2] * pz), l3 / (1.0 - c[2] * pz)
                summe = (l1 + l2 + l3) or 1.0
                l1, l2, l3 = l1 / summe, l2 / summe, l3 / summe
            tiefe = l1 * a[2] + l2 * b[2] + l3 * c[2]           # größer = näher am Betrachter
            if beste is None or tiefe > beste[0]:
                beste = (tiefe, (i, j, k, l1, l2, l3))
        if beste is None:
            return None
        i, j, k, l1, l2, l3 = beste[1]
        pa, pb, pc = mo.punkte[i], mo.punkte[j], mo.punkte[k]
        return tuple(l1 * pa[m] + l2 * pb[m] + l3 * pc[m] for m in range(3))

    def _um_drehpunkt(self, modell=None):
        """Nach dem Drehen verschieben, sodass der Drehpunkt an seinem Pixel bleibt (Bild dreht um ihn). modell:
        Stufe, die als Nächstes gezeichnet wird (beim Drehen die grobe, nach dem Loslassen das volle Modell)."""
        if self._drehpunkt is None or self.modell is None:
            return
        punkt, (x0, y0) = self._drehpunkt
        x, y, _ = self.bildpunkt(modell or self.grob_modell())(punkt)
        self.versatz = (self.versatz[0] + x0 - x, self.versatz[1] + y0 - y)

    def mousePressEvent(self, e):
        if self._explo_druck(e):        # Explosion: Teil von Hand ziehen
            return
        w = self.werkzeug
        wahl = self.wahl.an and not self.messen and self.modell is not None
        if wahl and e.button() == Qt.LeftButton and e.modifiers() & Qt.ShiftModifier:
            self.wahl.fenster = (e.position(), e.position())        # Fensterauswahl aufziehen
            self.setFocus()
            return
        if w is not None and self.modell is not None and not self.messen and not wahl \
                and w.druck(e.position(), e.button()):
            self._werkzeug_zieht = True
            return
        if wahl:
            self.setFocus()
        self._drehpunkt = None
        self._nachlauf.stop()
        self._tempo = (0.0, 0.0)
        self.nav = navigation3d.werte_lesen(_speicher)
        was = navigation3d.aktion(_TASTE.get(e.button()), _zusatz(e.modifiers()), self.nav)     # V4 Mausbelegung
        if was == "drehen" and self.modell is not None:
            x, y = e.position().x(), e.position().y()
            zentrum = self.nav.get("nav_drehzentrum")
            punkt = None
            if zentrum == navigation3d.AUSWAHL:     # Drehzentrum = Mitte des Gewählten
                try:
                    pk, _ = self.auswahl_punkte()
                except (TypeError, ValueError, AttributeError):
                    pk = None
                if pk:
                    punkt = tuple(sum(p[i] for p in pk) / len(pk) for i in range(3))
            elif zentrum != navigation3d.MITTE:
                punkt = self.punkt_unter(x, y)
            if punkt is not None:
                px, py, _ = self.bildpunkt(self.grob_modell())(punkt)
                self._drehpunkt = (punkt, (px, py))
        self._maus = (e.position(), e.button(), was)
        self._druck = e.position() if e.button() == Qt.LeftButton else None
        self._rechts = e.position() if e.button() == Qt.RightButton else None

    def mouseMoveEvent(self, e):
        if self.maus_koordinaten and not self._maus:
            self._maus_pos = (e.position().x(), e.position().y())
            self._maus_uhr.start()
        if self._werkzeug_zieht:
            self.werkzeug.ziehen(e.position(), e.modifiers())
            return
        if self._explo_zug is not None:
            self._explo_ziehen_zu(e.position())
            return
        if self.wahl.fenster is not None:
            self.wahl.fenster = (self.wahl.fenster[0], e.position())
            self.update()
            return
        if not self._maus:
            if self.koerper() and not self.messen:
                self._koerper_tipp(e)
            if self.wahl.an and not self.messen and self.modell is not None:
                self.wahl.schweben(e.position().x(), e.position().y())
            elif self.werkzeug is not None and self.modell is not None and not self.messen:
                self.werkzeug.schweben(e.position())
            elif self.messen and self.mess_max and self.modell is not None:
                t = self._fang_wahl(self.bildpunkt(), e.position().x(), e.position().y(), mit_flaeche=False,
                                    neu=True)
                if (t and (t["art"], tuple(t["punkt"]))) != (self._schwebe and (self._schwebe["art"],
                                                                               tuple(self._schwebe["punkt"]))):
                    self._schwebe = t
                    self.update()
            return
        alt, knopf, was = self._maus
        d = e.position() - alt
        if was == "drehen":     # freie Drehung ohne Grenze (navigation3d, 19.11.2026); Taste nach Mausbelegung (V4)
            self.gier, self.nick, self.roll = navigation3d.ziehen(self.gier, self.nick, self.roll, d.x(), d.y(),
                                                                  self.nav)
            self._tempo = (d.x(), d.y())
            self._um_drehpunkt()
        elif was == "schieben":
            t = float(self.nav.get("nav_schiebe_tempo") or 1.0)
            self.versatz = (self.versatz[0] + d.x() * t, self.versatz[1] + d.y() * t)
        self._maus = (e.position(), knopf, was)
        self.update()
        self.gedreht.emit()

    def mouseReleaseEvent(self, e):
        if self._explo_zug is not None:
            self._explo_zug = None
            if not any(self.explo.versatz.values()):
                self.explo.versatz = {}
            self.gedreht.emit()
            return
        if self._werkzeug_zieht:
            self._werkzeug_zieht = False
            self.werkzeug.loslassen(e.position() if e is not None else None)
            self.update()
            return
        if self.wahl.fenster is not None:
            strg = bool(e is not None and e.modifiers() & Qt.ControlModifier)
            start, ende = self.wahl.fenster
            if (ende - start).manhattanLength() < 4:        # Umschalt+Klick ohne Ziehen: dazu wie Strg+Klick
                self.wahl.fenster = None
                self.wahl.klick(ende.x(), ende.y(), dazu=True)
            else:
                self.wahl.fenster_fertig(dazu=strg)
            self.update()
            return
        if self._maus is not None and self._maus[2] == "drehen" and self._maus[0] != (self._druck or self._rechts):
            self._um_drehpunkt(self.modell)     # volles Modell kann einen anderen Maßstab haben: Punkt bleibt stehen
            if self.nav.get("nav_traegheit") == "ja" and abs(self._tempo[0]) + abs(self._tempo[1]) > 2:
                self._nachlauf.start()          # optionaler Nachlauf (Vorgabe aus: Drehung endet beim Loslassen)
        self._maus, self._drehpunkt = None, None
        druck, self._druck = self._druck, None
        rechts, self._rechts = self._rechts, None
        if druck is not None and e is not None and (e.position() - druck).manhattanLength() < 4:
            if self.wahl.an and not self.messen:
                self.wahl.klick(e.position().x(), e.position().y(), dazu=bool(e.modifiers() & Qt.ControlModifier))
            else:
                self.klicken(e.position().x(), e.position().y())
        elif (rechts is not None and e is not None and self.werkzeug is not None
              and (e.position() - rechts).manhattanLength() < 4):
            self.werkzeug.kontext(e.position(), e.globalPosition().toPoint())      # Rechtsklick ohne Ziehen: Menü
        elif (rechts is not None and e is not None and getattr(self, "flaeche_vor_kante", False) and not self.messen
              and (e.position() - rechts).manhattanLength() < 4):
            treffer = self.flaeche_unter(e.position().x(), e.position().y())
            if treffer is not None:
                self.kontext.emit(treffer, e.globalPosition().toPoint())
            else:
                self.standard_menue(e.globalPosition().toPoint())
        elif (rechts is not None and e is not None and not self.messen
              and (e.position() - rechts).manhattanLength() < 4):
            self.standard_menue(e.globalPosition().toPoint())       # Rechtsklick ohne Ziehen: Menü (19.11.2026)
        self.update()

    def standard_menue(self, pos=None, zeigen=True):
        """Rechtsklick-Menü der 3D-Fenster ohne eigenes Menü (19.11.2026): Blick, Einpassen, Darstellung, Auswahl
        und Messen – dieselben Einträge wie in den Leisten (ansicht3d_leiste). Ergebnis: das QMenu."""
        from PySide6.QtWidgets import QMenu

        from . import ansicht3d_leiste as leiste
        m = QMenu(self)
        m.setToolTipsVisible(True)
        m.addAction("Einpassen\tF", self.einpassen)
        leiste.blick_menue(m.addMenu("Blick"), self)
        dm = m.addMenu("Darstellung")
        for name in DARSTELLUNGEN:
            x = dm.addAction(name, lambda n=name: self.darstellung_setzen(n))
            x.setCheckable(True)
            x.setChecked(self.darstellung == name)
        leiste.auswahl_menue(m.addMenu("Auswahl"), self)
        if hasattr(self, "messen_setzen"):
            x = m.addAction("Messen", lambda: self.messen_setzen(not self.messen))
            x.setCheckable(True)
            x.setChecked(bool(self.messen))
            self.masse_menue(m.addMenu("Maße"))
            x = m.addAction("Teil messen (Rohr, Konturen, Fertigung) …", self.teil_messen)
            x.setToolTip("Profilform, Maße, Wand, Querschnitt, Masse, Konturen, Lochabstände und Reststege gegen die "
                         "Prüfregeln – nur Prüfung, die Kalkulation bleibt")
        if zeigen and pos is not None and not getattr(self, "stumm", False):
            m.exec(pos)
        return m

    def _fang_wahl(self, bild, x, y, flaeche_treffer=None, mit_flaeche=True, neu=False):
        """Fangpunkt nach den Einstellungen fang_* (Messplan M2); Tab schaltet unter dem Mauszeiger zum nächsten
        Kandidaten weiter („Andere wählen“). neu: Mausbewegung – an einer anderen Stelle beginnt die Wahl von vorn."""
        from .messen3d import fang_erlaubt
        if neu and getattr(self, "_fang_ort", None) is not None and \
                math.hypot(x - self._fang_ort[0], y - self._fang_ort[1]) > 3:
            self._fang_nr = 0
        self._fang_ort = (x, y)
        kand = self.geometrie().fangen(bild, x, y, flaeche_treffer, mit_flaeche, fang_erlaubt(_speicher), alle=True)
        self._fang_kand = kand
        if not kand:
            return None
        return kand[getattr(self, "_fang_nr", 0) % len(kand)]

    def focusNextPrevChild(self, weiter):
        if self.messen and self.mess_max:       # Tab beim Messen: anderer Fangpunkt statt nächstes Feld
            return False
        return super().focusNextPrevChild(weiter)

    def andere_waehlen(self):
        """Tab beim Messen: nächster Fangpunkt unter dem Mauszeiger (Kreismitte, Kante, Ecke, Fläche …)."""
        ort = getattr(self, "_fang_ort", None)
        if not self.messen or ort is None or self.modell is None:
            return False
        self._fang_nr = getattr(self, "_fang_nr", 0) + 1
        self._schwebe = self._fang_wahl(self.bildpunkt(), ort[0], ort[1], mit_flaeche=False)
        kand = getattr(self, "_fang_kand", None) or []
        if self._schwebe is not None and len(kand) > 1:
            self.tafel.zeigen([f"Fängt: {self._schwebe['art']} ({self._fang_nr % len(kand) + 1} von {len(kand)}, "
                               "Tab = andere)"])
        self.update()
        return True

    def _messen_klick(self, bild, x, y):
        """Messen (2 Punkte) bzw. Winkel (3): fängt Kreismitte, Kantenmitte, Ecke, Punkt auf einer Linie oder Fläche
        mit exakter Geometrie (messen3d); Kernwerte und Ergebnis in der Mess-Tafel."""
        geo = self.geometrie()
        ort = getattr(self, "_fang_ort", None)
        if getattr(self, "_fang_nr", 0) and self._schwebe is not None and ort is not None and \
                math.hypot(x - ort[0], y - ort[1]) <= 3:
            t = self._schwebe               # mit Tab gewählt: genau das Gezeigte nehmen
        else:
            t = self._fang_wahl(bild, x, y, self._dreieck_unter, neu=True)
        if t is None:
            return None
        if len(self.messpunkte) >= self.mess_max:
            self.messpunkte, self.mess_treffer = [], []
        self.messpunkte.append(tuple(t["punkt"]))
        self.mess_treffer.append(t)
        fertig = len(self.messpunkte) == self.mess_max
        zeilen = []
        if fertig and self.mess_art == MESS_WINKEL:
            zeilen = [self.mess_text()] + [f"{n + 1}: {geo.kernwerte(q)[0]}" for n, q in enumerate(self.mess_treffer)]
        elif fertig:
            _, zeilen = geo.vergleich(*self.mess_treffer)
            zeilen += [f"{n + 1}: {geo.kernwerte(q)[0]}" for n, q in enumerate(self.mess_treffer)]
        else:
            zeilen = geo.kernwerte(t)
            if self.mess_max:
                zeilen.append(f"Punkt {len(self.messpunkte) + 1} von {self.mess_max} anklicken")
        if fertig:
            arten = [x.get("art") for x in self.mess_treffer]
            haupt = self.mess_text()
            exakt = self.mess_art != MESS_WINKEL and len(self.mess_treffer) == 2
            m = mess_protokoll.Mass(self.messpunkte, haupt, mess_protokoll.WINKEL if self.mess_art == MESS_WINKEL
                                    else None, arten=arten)
            if exakt:                   # Hauptwert der exakten Messung (Fläche–Fläche, Kante–Kante …) als Wert
                w = mess_protokoll.wert_aus_text(haupt)
                if w is not None:
                    m = m.kopie(wert=w[0], einheit=w[1])
            self.masse_fest.append(m)
            self._mass_arten = getattr(self, "_mass_arten", {})     # Fangart je Punkt (für _masse_pruefen)
            self._mass_arten[tuple(tuple(q) for q in self.messpunkte)] = arten
        self.tafel.zeigen(zeilen, self.mass_aktionen() if fertig else ())
        self.update()
        if fertig:
            self.gemessen.emit(self.winkel() if self.mess_art == MESS_WINKEL else self.abstand())
        return t["punkt"]

    def _dreieck_unter(self, bild, x, y):
        """Vorderstes Dreieck unter dem Pixel (x, y): (Nummer, Punkt im Modell) oder None."""
        mo = self.modell
        beste = None
        for nr, (i, j, k, _, _) in enumerate(mo.dreiecke):
            a, b, c = bild(mo.punkte[i]), bild(mo.punkte[j]), bild(mo.punkte[k])
            if min(a[0], b[0], c[0]) > x or max(a[0], b[0], c[0]) < x or min(a[1], b[1], c[1]) > y or \
                    max(a[1], b[1], c[1]) < y:
                continue
            det = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
            if abs(det) < 1e-9:
                continue
            l1 = ((b[1] - c[1]) * (x - c[0]) + (c[0] - b[0]) * (y - c[1])) / det
            l2 = ((c[1] - a[1]) * (x - c[0]) + (a[0] - c[0]) * (y - c[1])) / det
            l3 = 1 - l1 - l2
            if min(l1, l2, l3) < -1e-6:
                continue
            tiefe = l1 * a[2] + l2 * b[2] + l3 * c[2]
            if beste is None or tiefe > beste[0]:
                pa, pb, pc = mo.punkte[i], mo.punkte[j], mo.punkte[k]
                beste = (tiefe, nr, tuple(l1 * pa[m] + l2 * pb[m] + l3 * pc[m] for m in range(3)))
        return None if beste is None else (beste[1], beste[2])

    def mouseDoubleClickEvent(self, e):
        if self.werkzeug is not None and e is not None and self.werkzeug.doppelklick(e.position()):
            return
        if getattr(self, "flaeche_vor_kante", False) and e is not None and not self.messen:
            treffer = self.flaeche_unter(e.position().x(), e.position().y())
            if treffer is not None:
                self.doppelt.emit(treffer)          # z. B. ganze Gehrungskette wählen
                return
        ziel = getattr(self, "doppelklick_ziel", None)
        if ziel is not None and e is not None and self.auf_modell(e.position().x(), e.position().y()):
            ziel()                      # z. B. 3D-Ansicht der Positionen: Teil im Editor öffnen (Plan 3D-Editor F1)
            return
        self.zuruecksetzen()

    def auf_modell(self, x, y):
        """Liegt das Pixel (x, y) auf dem Modell (irgendeinem Dreieck)?"""
        mo = self.modell
        if mo is None:
            return False
        bild = self.bildpunkt()
        for i, j, k, _, _ in mo.dreiecke:
            a, b, c = bild(mo.punkte[i]), bild(mo.punkte[j]), bild(mo.punkte[k])
            det = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
            if abs(det) < 1e-9:
                continue
            l1 = ((b[1] - c[1]) * (x - c[0]) + (c[0] - b[0]) * (y - c[1])) / det
            l2 = ((c[1] - a[1]) * (x - c[0]) + (a[0] - c[0]) * (y - c[1])) / det
            if min(l1, l2, 1 - l1 - l2) >= -1e-6:
                return True
        return False

    def keyPressEvent(self, e):
        k = e.key()
        mods = e.modifiers()
        if k == Qt.Key_Tab and self.messen and self.mess_max and self.andere_waehlen():
            e.accept()
            return
        if mods & (Qt.ControlModifier | Qt.AltModifier) and k in (Qt.Key_Left, Qt.Key_Right, Qt.Key_Up, Qt.Key_Down,
                                                                  Qt.Key_PageUp, Qt.Key_PageDown):
            schritt = math.pi / 2 if mods & Qt.ControlModifier else math.radians(15)
            self.drehen(-1 if k == Qt.Key_Left else 1 if k == Qt.Key_Right else 0,
                        1 if k == Qt.Key_Up else -1 if k == Qt.Key_Down else 0,
                        1 if k == Qt.Key_PageUp else -1 if k == Qt.Key_PageDown else 0, schritt)
            e.accept()
            return
        if self.wahl.an and not self.messen and e.modifiers() & Qt.ControlModifier and k in (Qt.Key_A, Qt.Key_I):
            if k == Qt.Key_A:       # 19.11.2026: alle sichtbaren Körper wählen
                self.wahl.alle_waehlen()
            else:                   # Auswahl umkehren
                self.wahl.umkehren()
            e.accept()
            return
        if self.wahl.an and not self.messen and k in (Qt.Key_Escape, Qt.Key_H, Qt.Key_I, Qt.Key_T):
            if k == Qt.Key_T:       # 20.11.2026: Gewähltes durchsichtig (Umschalt: alle wieder deckend)
                if e.modifiers() & Qt.ShiftModifier:
                    self.wahl.alle_deckend()
                else:
                    self.wahl.durchsichtig_schalten()
            elif k == Qt.Key_Escape:
                self.wahl.aufheben()
            elif k == Qt.Key_I:
                self.wahl.isolieren()
            elif e.modifiers() & Qt.ShiftModifier:
                self.wahl.alle_einblenden()
            else:
                self.wahl.ausblenden()
            e.accept()
            return
        if self.werkzeug is not None and self.werkzeug.taste(e):
            e.accept()
            return
        # V3 (Plan 3D-Viewer 18.11.2026): Standardansichten und Einpassen per Taste (ohne Strg/Alt)
        if not e.modifiers() & (Qt.ControlModifier | Qt.AltModifier | Qt.MetaModifier) and k in TASTEN_BLICK:
            ziel = TASTEN_BLICK[k]
            if ziel == "vorher":
                self.vorher_zeigen(not self.vorher_an)
            elif ziel == "einpassen":
                self.einpassen()
            else:
                self.blick(ziel)
            e.accept()
            return
        super().keyPressEvent(e)

    def wheelEvent(self, e):
        schritte = navigation3d.rad_schritte(e.angleDelta().y(), e.angleDelta().x(), e.pixelDelta().y())
        e.accept()                      # das Rad gehört dem 3D (rollt nie die Seite darunter)
        if schritte:
            self.zoomen(navigation3d.zoom_faktor(schritte, navigation3d.werte_lesen(_speicher)),
                        e.position().x(), e.position().y())

    def zoomen(self, faktor, x=None, y=None):
        """Zoom um faktor; mit Pixel (x, y) bleibt der Punkt unter der Maus stehen (Zoom zur Mausposition)."""
        alt = self.zoom
        self.zoom = max(0.2, min(40.0, alt * faktor))
        if x is not None:
            k = self.zoom / alt                 # Maßstab wächst mit dem Zoom, die Bildmitte liegt bei Mitte + Versatz
            vx, vy = self.versatz
            self.versatz = (vx + (1 - k) * (x - self.width() / 2 - vx), vy + (1 - k) * (y - self.height() / 2 - vy))
        self._eilig = True
        self._ruhe.start()
        self.update()


class Ansicht3DMitKnoepfen(QWidget):
    """Ansicht mit der gemeinsamen Leiste der 3D-Fenster (Blick, Darstellung, Perspektive, Messen) und dem
    Ansichtswürfel oben rechts."""

    def __init__(self, parent=None):
        super().__init__(parent)
        from .ansicht3d_leiste import Leiste3D
        from .ansichtswuerfel import Ansichtswuerfel, an_ecke
        self.ansicht = Ansicht3D()
        self.info = QLabel()
        self.info.setWordWrap(True)
        self.knoepfe = QWidget()
        leiste = QHBoxLayout(self.knoepfe)
        leiste.setContentsMargins(0, 0, 0, 0)
        self.leiste = Leiste3D(self.ansicht)
        leiste.addWidget(self.leiste, 1)
        self.wuerfel = Ansichtswuerfel(self.ansicht)
        an_ecke(self.wuerfel)
        # Vorschau bei Anbauteilen (nur sichtbar, wenn das Teil welche hat)
        self.modi = QWidget()
        ml = QHBoxLayout(self.modi)
        ml.setContentsMargins(0, 0, 0, 0)
        ml.setSpacing(0)
        self.modus_knoepfe = QButtonGroup(self.modi)
        for text, tipp in zip(MODI, ("Rohr mit Anbauteilen (sandfarben)", "Nur die Rohrlaser-Geometrie ohne Anbauteile",
                                     "Rohr mit allen Gravurlinien, ohne Schnittlinien")):
            b = QPushButton(text)
            b.setCheckable(True)
            b.setChecked(text == MODI[0])
            b.setToolTip(tipp)
            b.clicked.connect(lambda _=False, t=text: self.ansicht.modus_setzen(t))
            self.modus_knoepfe.addButton(b)
            ml.addWidget(b)
        self.modi.setVisible(False)
        leiste.addWidget(self.modi)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.ansicht, 1)
        lay.addWidget(self.knoepfe)
        # langer Hinweis (STEP-Prüfung): im Rollbereich statt abgeschnitten (Layout-Prüfung 11.11.2026, L5)
        from PySide6.QtWidgets import QFrame, QScrollArea
        self.info_rollen = QScrollArea()
        self.info_rollen.setWidgetResizable(True)
        self.info_rollen.setFrameShape(QFrame.NoFrame)
        self.info_rollen.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.info_rollen.setWidget(self.info)
        self.info_rollen.setFixedHeight(0)
        lay.addWidget(self.info_rollen)

    def setzen(self, netz, titel="", info=""):
        self.ansicht.setzen(netz, titel)
        self.modi.setVisible(mit_anbau(self.ansicht.netz))
        self.info.setText(info)
        self._info_hoehe()

    def resizeEvent(self, ereignis):
        super().resizeEvent(ereignis)
        self._info_hoehe()

    def _info_hoehe(self):
        """Hinweis so hoch wie sein Text, höchstens 45 % der Ansicht; der Rest ist im Rollbereich."""
        if not self.info.text():
            self.info_rollen.setFixedHeight(0)
            return
        breite = max(50, self.width() - 4)
        hoch = self.info.heightForWidth(breite)
        frei = self.height() - self.knoepfe.sizeHint().height() - 140 - 2 * self.layout().spacing()  # 3D bleibt sichtbar
        zeile = self.fontMetrics().height() + 4
        self.info_rollen.setFixedHeight(max(0, min(max(zeile, min(hoch + 2, int(self.height() * 0.45))), frei)))

    def modus_setzen(self, modus):
        """Vorschau wählen wie mit den Knöpfen (Tests, Bildschirmfotos)."""
        for b in self.modus_knoepfe.buttons():
            b.setChecked(b.text() == modus)
        self.ansicht.modus_setzen(modus)
