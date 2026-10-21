"""Datenbank des Programms: eine SQLite-Datei mit Stammdaten, Einstellungen und Angeboten.

Das Schema entsteht aus stammdaten.TABELLEN und angebot.KOPF/POSITIONEN; die Schemaversion steht in
PRAGMA user_version, damit spätere Versionen alte Dateien erweitern können (1 = nur Stammdaten,
2 = mit Aufträgen, 3 = mit Staffeln und Staffelpreisen, 4 = Maschinengrenzen Hüllkreis/Metergewicht und
Frachtkosten im Kopf, 5 = Zusatzarbeiten, Preis je Gewinde, Schneidzeit manuell, 6 = Aufträge heißen Angebote,
7 = Kunden und Zahlungsbedingungen mit Skonto im Kopf,
8 = Nachkalkulation je Angebot, 9 = 3D-Netze der STEP-Teile je Position, 10 = Kalkulationswerte je Angebot,
11 = Werkstoff-Kategorien, Oberflächen, Schneiddaten je Kategorie und Schneidgas, 14 = Werte je Staffel:
Menge bis, Materialzuschlag, Gewinn, Nebenkosten usw., 15 = Zusatzarbeiten mit Arbeitszeit und Material,
16 = Frachtkosten: Tabellen fracht_* und Historie fracht_kalkulationen; ältere Dateien bekommen sie leer,
17 = Zukaufartikel mit Kategorien, Lieferanten, Einkaufspreisen und Preisänderungen, Zukaufteile je Position).
Vor dem Erweitern einer Datei älterer Version legt das Programm eine Sicherung an (Daten/Sicherung, Zusatz
'vor_Schema_<neu>'); mit ihr und der alten Programmversion lässt sich jede Umstellung rückgängig machen.
Fehlende Spalten älterer Dateien werden beim Öffnen ergänzt; Dateien vor Schema 5 bekommen die
Beispiel-Zusatzarbeiten, Dateien vor Schema 6 werden von Auftrag auf Angebot umbenannt, Dateien vor Schema 11
bekommen Kategorien, die neuen Beispiel-Werkstoffe und -Oberflächen und Schneiddaten je Kategorie.
"""
import contextlib
import datetime
import hashlib
import json
import os
import re
import shutil
import sqlite3
import tempfile
import zipfile
from pathlib import Path

from . import zukauf
from .fracht_daten import FRACHT_TABELLEN, FRACHT_TABELLE, FRACHT_VERWEISE, KURZ, listen_aus
from .fracht_daten import beispieldaten as fracht_beispieldaten
from .fracht_angebot import UMLAGE_NEU
from .angebot import (KALK_PROZENT, KALKULATION, KOPF, KUNDENMATERIAL, POSITIONEN, ZAHLUNG, ZUKAUFTEIL, lieferzeit_wert,
                      naechste_nummer)
from .staffeln import STUFE_FELDER
from .stammdaten import (TABELLEN, TABELLE, EINSTELLUNGEN, EINSTELLUNG, VERWEISE, beispiel_zusatzarbeiten,
                         ALTE_MASCHINEN, MASCHINE_WERTE, alte_beispiel_schneiddaten, alte_richtwerte, ALTE_GRAVUR, GRAVUR,
                         beispiel_arbeitsschritte, beispiel_stundensaetze,
                         beispieldaten, kategorie_raten, kontext_aus, OFFENE_PROFILE)

SCHEMA_VERSION = 31     # 15: Zusatzarbeiten mit Kategorie, Status, Arbeitszeit, Material und Zuschlägen (neue Spalten leer)
                        # 16: Frachtkosten (Tabellen fracht_*, Historie)
                        # 17: Zukaufartikel (neue Tabellen zukauf_*, Spalte positionen.zukauf)
                        # 18: festgeschriebene Materialpreise und Schneiddaten je Angebot (Spalte angebote.preisbasis)
                        # 19: Profilformen I-/H-Träger und T-Profil in der Auswahlliste ergänzt (keine neuen Spalten)
                        # 20: Blechartikel: zukauf_artikel.artikeltyp, Maße, Werkstoff, Herkunft, STEP-Datei, Kennung
                        # 21: Positionsart (positionen.art: Rohrlaserteil/Zukaufteil) und positionen.gewicht_teil
                        # 22: profile.wand_max (größte Wandstärke für die Schneidzeit), Normprofile aus der Tabelle
                        # 23: Lieferlängen (Tabelle lieferlaengen, profile.laengenvergleich, angebote.laengenwahl)
                        # 24: Kundenreferenz, Lieferzeit und Mindestpreis im Angebot (seit 0.6.4 Mindestpreis nur aus den Einstellungen)
                        # 25: Kundenmaterial (positionen.material_herkunft, Kopf material_vorgabe, Handling je kg)
                        # 26: Schneidweg-Rechner (positionen.technik, Eingaben als JSON; ältere Positionen leer)
                        # 27: Zeichnungen je Position (positionen.dokumente; seit 0.6.28 entfernt, beim Start einmalig geleert)
                        # 28: maschinen.min_stange (kürzeste Stange der Stangenladung im Zuschnitt, Vorgabe 2.500 mm)
                        # 29: maschinen.kontur_klein_wand/kontur_mittel_wand (Konturklasse nach Hüllmaß ÷ Wand, 3 und 8)
                        # 30: Schweißnaht (positionen.naht_vorgabe/naht_winkel/naht_quelle/querschnitt_lage, profile.naht_stange; leer = keine Vorgabe)
                        # 31: Gehrung mit Richtung (positionen.a_ende/b_ende als JSON; ältere Positionen leer)
# Schema 6: alte Namen (Schema 2–5) -> neue Namen
UMBENANNT_TABELLEN = (("auftraege", "angebote"),)
UMBENANNT_SPALTEN = (("positionen", "auftrag_id", "angebot_id"), ("step_protokoll", "auftrag_id", "angebot_id"),
                     ("staffeln", "auftrag_id", "angebot_id"))
UMBENANNT_EINSTELLUNGEN = (("letzte_auftragsnummer", "letzte_angebotsnummer"), ("auftragsaufschlag", "angebotsaufschlag"))
ALTE_INDIZES = ("auftraege_nummer", "positionen_auftrag")
SQL_ART = {"zahl": "REAL", "ganz": "INTEGER"}
SICHERUNGEN_BEHALTEN = 30
ALLE_TABELLEN = TABELLEN + FRACHT_TABELLEN + zukauf.TABELLEN
ALLE_TABELLE = {**TABELLE, **FRACHT_TABELLE}
ALLE_VERWEISE = {**VERWEISE, **FRACHT_VERWEISE}
MASCHINEN_STAND = "2026-10-20"     # Maschinen T03/T11/LT7 und Schneiddaten-Richtwerte (Datenbank._maschinen_anpassen)
GRAVUR_STAND = "2026-10-21"        # Vorschub Gravur der Richtwerte 3.000 mm/min (Datenbank._gravur_anpassen)
RICHTWERTE_STAND = "2026-10-21"    # Rohr-Richtwerte Schneiddaten (Datenbank._richtwerte_anpassen)
ZUSCHLAEGE_STAND = "2026-10-21"    # Zuschlag Material und Fertigung einmalig auf 0 (danach in den Einstellungen änderbar)


class Datenbank:
    def __init__(self, pfad):
        self.pfad = Path(pfad)
        self.pfad.parent.mkdir(parents=True, exist_ok=True)
        neu = not self.pfad.exists()
        self.con = sqlite3.connect(self.pfad)
        self.con.row_factory = sqlite3.Row
        self.con.execute("PRAGMA journal_mode=DELETE")
        self._anlegen()
        if neu:
            self.stammdaten_ersetzen(beispieldaten(), {}, "Beispieldaten")
            self.fracht_beispiele_laden()
            self.einstellung_setzen("maschinen_stand", MASCHINEN_STAND)
            self.einstellung_setzen("gravur_stand", GRAVUR_STAND)
            self.einstellung_setzen("richtwerte_stand", RICHTWERTE_STAND)
            self.einstellung_setzen("zuschlaege_stand", ZUSCHLAEGE_STAND)

    def schliessen(self):
        self.con.close()

    # -------------------------------------------------------------- Schema
    def _anlegen(self):
        version = self.con.execute("PRAGMA user_version").fetchone()[0]
        if version > SCHEMA_VERSION:
            raise RuntimeError(f"Die Datendatei {self.pfad} stammt von einer neueren Programmversion "
                               f"(Schema {version}). Bitte das Programm aktualisieren.")
        if 0 < version < SCHEMA_VERSION:    # Rückfall: Stand vor der Umstellung sichern
            self.sicherung(zusatz=f"vor_Schema_{SCHEMA_VERSION}")
        elif version > 0 and self.einstellung("maschinen_stand") != MASCHINEN_STAND:
            self.sicherung(zusatz="vor_Maschinen_T03_T11_LT7")
        elif version > 0 and self.einstellung("richtwerte_stand") != RICHTWERTE_STAND:
            self.sicherung(zusatz="vor_Richtwerte_Rohr")
        with self.con:
            if 0 < version < 6:
                self._umbenennen()
            if 0 < version < 11:          # Schlüssel der Schneiddaten mit Kategorie und Schneidgas
                self.con.execute('DROP INDEX IF EXISTS "schneiddaten_schluessel"')
            for t in ALLE_TABELLEN:
                spalten = ", ".join(f'"{f.name}" {SQL_ART.get(f.art, "TEXT")}' for f in t.felder)
                self.con.execute(f'CREATE TABLE IF NOT EXISTS "{t.name}" (id INTEGER PRIMARY KEY, {spalten})')
            self.con.execute("CREATE TABLE IF NOT EXISTS einstellungen (name TEXT PRIMARY KEY, wert TEXT)")
            kopf = ", ".join(f'"{f.name}" {SQL_ART.get(f.art, "TEXT")}' for f in KOPF)
            self.con.execute(f"CREATE TABLE IF NOT EXISTS angebote (id INTEGER PRIMARY KEY, {kopf}, angelegt TEXT, "
                             "geaendert TEXT, ergebnis TEXT, optimiert_am TEXT)")
            self.con.execute("CREATE UNIQUE INDEX IF NOT EXISTS angebote_nummer ON angebote (nummer)")
            spalten = ", ".join(f'"{f.name}" {SQL_ART.get(f.art, "TEXT")}' for f in POSITIONEN.felder)
            self.con.execute("CREATE TABLE IF NOT EXISTS positionen (id INTEGER PRIMARY KEY, angebot_id INTEGER "
                             f"NOT NULL REFERENCES angebote(id) ON DELETE CASCADE, nr INTEGER, {spalten})")
            self.con.execute("CREATE INDEX IF NOT EXISTS positionen_angebot ON positionen (angebot_id, nr)")
            self.con.execute("CREATE TABLE IF NOT EXISTS step_protokoll (id INTEGER PRIMARY KEY, angebot_id INTEGER "
                             "NOT NULL REFERENCES angebote(id) ON DELETE CASCADE, zeile TEXT)")
            self.con.execute("CREATE TABLE IF NOT EXISTS netze (position_id INTEGER PRIMARY KEY REFERENCES "
                             "positionen(id) ON DELETE CASCADE, daten BLOB)")
            self.con.execute("CREATE TABLE IF NOT EXISTS fracht_kalkulationen (id INTEGER PRIMARY KEY, datum TEXT, "
                             "angebot_id INTEGER, bezeichnung TEXT, eingaben TEXT, ergebnis TEXT, gesamt REAL, "
                             "programm TEXT)")
            self.con.execute("CREATE TABLE IF NOT EXISTS staffeln (id INTEGER PRIMARY KEY, angebot_id INTEGER "
                             "NOT NULL REFERENCES angebote(id) ON DELETE CASCADE, nr INTEGER, schluessel TEXT, "
                             "menge INTEGER, bemerkung TEXT)")
            spalten_a = {r[1] for r in self.con.execute("PRAGMA table_info(angebote)")}
            if "staffelpreise" not in spalten_a:      # Datei aus Schema 2
                self.con.execute("ALTER TABLE angebote ADD COLUMN staffelpreise TEXT")
            if "nachkalkulation" not in spalten_a:    # Datei vor Schema 8
                self.con.execute("ALTER TABLE angebote ADD COLUMN nachkalkulation TEXT")
            if "zeitbasis" not in spalten_a:          # Datei vor Schema 13 (alte Angebote: ohne Snapshot)
                self.con.execute("ALTER TABLE angebote ADD COLUMN zeitbasis TEXT")
            if "preisbasis" not in spalten_a:         # Datei vor Schema 18 (alte Angebote: aktuelle Preise)
                self.con.execute("ALTER TABLE angebote ADD COLUMN preisbasis TEXT")
            if "laengenwahl" not in spalten_a:        # Datei vor Schema 23 (alle Gruppen mit der Angebotslänge)
                self.con.execute("ALTER TABLE angebote ADD COLUMN laengenwahl TEXT")
            for tabelle, felder in [(t.name, t.felder) for t in ALLE_TABELLEN] + [("angebote", KOPF),
                                                                            ("positionen", POSITIONEN.felder),
                                                                            ("staffeln", STUFE_FELDER)]:
                vorhanden = {r[1] for r in self.con.execute(f'PRAGMA table_info("{tabelle}")')}
                for f in felder:                       # neue Felder späterer Versionen
                    if f.name not in vorhanden:
                        self.con.execute(f'ALTER TABLE "{tabelle}" ADD COLUMN "{f.name}" {SQL_ART.get(f.art, "TEXT")}')
            for t in ALLE_TABELLEN:                    # nach den neuen Spalten: Schlüssel können sie enthalten
                if not t.schluessel:
                    continue
                # leere Felder im Schlüssel (Schneiddaten: Werkstoff-ID oder Kategorie) zählen als gleich
                schl = ", ".join(f'"{s}"' if t.feld(s).pflicht else f"""COALESCE("{s}", '')""" for s in t.schluessel)
                self.con.execute(f'CREATE UNIQUE INDEX IF NOT EXISTS "{t.name}_schluessel" ON "{t.name}" ({schl})')
            if 0 < version < 5 and not self.anzahl("zusatzarbeiten"):
                namen = [f.name for f in TABELLE["zusatzarbeiten"].felder]
                self.con.executemany(f'INSERT INTO zusatzarbeiten ({", ".join(namen)}) VALUES ({", ".join("?" * len(namen))})',
                                     [[z[n] for n in namen] for z in beispiel_zusatzarbeiten()])
            if 0 < version < 11:
                self._werkstoffe_ergaenzen()
            if 0 < version < 19:
                self._profilformen_ergaenzen()      # Schema 12: U, C, L, Flachstahl; Schema 19: I-/H-Träger, T-Profil
            if 0 < version < 22:
                self._wand_max_ergaenzen()
            if 0 < version < 28:
                self.con.execute("UPDATE maschinen SET min_stange=2500 WHERE min_stange IS NULL")
            if 0 < version < 29:
                self.con.execute("UPDATE maschinen SET kontur_klein_wand=3, kontur_mittel_wand=8 "
                                 "WHERE kontur_klein_wand IS NULL AND kontur_mittel_wand IS NULL")
            if 0 < version < 13:
                if not self.anzahl("stundensaetze"):
                    self._einfuegen("stundensaetze", beispiel_stundensaetze())
                if not self.anzahl("arbeitsschritte"):
                    self._einfuegen("arbeitsschritte", beispiel_arbeitsschritte())
            self.con.execute("CREATE INDEX IF NOT EXISTS zukauf_bezug_artikel ON zukauf_bezug (artikel_id)")
            if version < 17 and not self.anzahl("zukauf_kategorien"):    # neue Datei oder vor Schema 17
                self.con.executemany("INSERT INTO zukauf_kategorien (name, aktiv) VALUES (?, 'ja')",
                                     [(n,) for n in zukauf.KATEGORIEN_START])
            if version > 0 and self.einstellung("maschinen_stand") != MASCHINEN_STAND:
                self._maschinen_anpassen()
            if version > 0 and self.einstellung("gravur_stand") != GRAVUR_STAND:
                self._gravur_anpassen()
            if version > 0 and self.einstellung("richtwerte_stand") != RICHTWERTE_STAND:
                self._richtwerte_anpassen()
            if version > 0 and self.einstellung("zuschlaege_stand") != ZUSCHLAEGE_STAND:
                for n in ("zuschlag_material", "zuschlag_fertigung"):
                    self._einstellung_schreiben(n, 0)
                self._einstellung_schreiben("zuschlaege_stand", ZUSCHLAEGE_STAND)
            self.con.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
        self.con.execute("PRAGMA foreign_keys=ON")

    def _einfuegen(self, tabelle, zeilen, ergaenzen=False):
        """Zeilen einfügen; ergaenzen=True überspringt Zeilen, deren Schlüssel es schon gibt."""
        namen = [f.name for f in ALLE_TABELLE[tabelle].felder]
        self.con.executemany(f'INSERT {"OR IGNORE " if ergaenzen else ""}INTO "{tabelle}" ({", ".join(chr(34) + n + chr(34) for n in namen)}) '
                             f'VALUES ({", ".join("?" * len(namen))})', [[z.get(n) for n in namen] for z in zeilen])

    def _maschinen_anpassen(self):
        """Dateien bis 0.5.8 (einmalig, ohne neues Schema): Beispielmaschinen RL-1/RL-2 werden T03/T11, LT7 kommt
        dazu. Unverändertes RL-1/RL-2 wird mit Schneiddaten, Angeboten und Standard-Maschine umbenannt; wurde es von
        Hand umbenannt, ziehen die Angebote nach. Neue Werte nur, wo noch die alten Beispielwerte stehen, eigene
        Maschinen bleiben. Schneiddaten: unveränderte alte Beispielzeilen gehen, die neuen Richtwerte kommen für
        T03, T11 und LT7 dazu, wo es die Zeile (Maschine, Kategorie, Gas, Wandstärke) noch nicht gibt."""
        neu = {z["maschinen_id"]: z for z in beispieldaten()["maschinen"]}
        da = {z["maschinen_id"]: z for z in self.zeilen("maschinen") if z.get("maschinen_id")}
        beispiel = lambda z, werte: all(z.get(n) == w for n, w in zip(MASCHINE_WERTE, werte))
        for alt, (ziel, werte) in ALTE_MASCHINEN.items():
            z = da.get(alt)
            if z is not None and ziel not in da and beispiel(z, werte):
                for tabelle, feld in (("maschinen", "maschinen_id"),) + VERWEISE[("maschinen", "maschinen_id")]:
                    self.con.execute(f'UPDATE "{tabelle}" SET "{feld}"=? WHERE "{feld}"=?', (ziel, alt))
                self._maschine_umbenannt(alt, ziel)
                da[ziel] = da.pop(alt)
            elif z is None and ziel in da:
                self.con.execute("UPDATE angebote SET maschine=? WHERE maschine=?", (ziel, alt))
                self._maschine_umbenannt(alt, ziel)
            z = da.get(ziel)
            if z is not None and beispiel(z, werte):
                felder = [n for n in neu[ziel] if n != "maschinen_id"]
                self.con.execute(f'UPDATE maschinen SET {", ".join(chr(34) + n + chr(34) + "=?" for n in felder)} '
                                 "WHERE id=?", [neu[ziel][n] for n in felder] + [z["id"]])
        self._einfuegen("maschinen", [z for m, z in neu.items() if m not in da])
        alte = alte_beispiel_schneiddaten()
        werte = lambda z: (z.get("kategorie"), z.get("gas")) + tuple(
            float(z[n]) if isinstance(z.get(n), (int, float)) else z.get(n)
            for n in ("wand_bis", "vorschub_gross", "vorschub_mittel", "vorschub_klein", "einstechzeit", "vorschub_gravur"))
        for z in self.zeilen("schneiddaten"):
            if not z.get("werkstoff_id") and z.get("bemerkung") == "Beispiel" and werte(z) in alte:
                self.con.execute("DELETE FROM schneiddaten WHERE id=?", (z["id"],))
        self._einfuegen("schneiddaten", beispieldaten()["schneiddaten"], ergaenzen=True)
        self._einstellung_schreiben("maschinen_stand", MASCHINEN_STAND)

    def _gravur_anpassen(self):
        """Einmalig: Vorschub Gravur der Richtwert-Zeilen (Bemerkung 'Beispiel: Richtwert …') mit dem alten Wert
        (Faser 15.000, CO₂ 10.000 mm/min) auf 3.000 mm/min; von Hand geänderte Werte bleiben."""
        self.con.execute(f"UPDATE schneiddaten SET vorschub_gravur=? WHERE bemerkung LIKE 'Beispiel: Richtwert%' "
                         f"AND vorschub_gravur IN ({', '.join('?' * len(ALTE_GRAVUR))})",
                         (GRAVUR["Faser"],) + ALTE_GRAVUR)
        self._einstellung_schreiben("gravur_stand", GRAVUR_STAND)

    def _richtwerte_anpassen(self):
        """Einmalig: Richtwert-Zeilen (Werkstoff-ID leer, Bemerkung 'Beispiel: Richtwert …') mit den Werten 0.5.13 bis
        0.6.18 bekommen die Rohr-Richtwerte vom 21.10.2026 (Vorschub groß, mittel, klein, Einstechzeit); von Hand
        geänderte Zeilen und eigene Maschinen bleiben."""
        alte = alte_richtwerte()
        neu = {(z["maschinen_id"], z["kategorie"], z["gas"], float(z["wand_bis"])): z
               for z in beispieldaten()["schneiddaten"]}
        zahl = lambda w: float(w) if isinstance(w, (int, float)) else w
        for z in self.zeilen("schneiddaten"):
            k = (z.get("maschinen_id"), z.get("kategorie"), z.get("gas"), zahl(z.get("wand_bis")))
            if (z.get("werkstoff_id") or not str(z.get("bemerkung") or "").startswith("Beispiel: Richtwert")
                    or k not in neu or alte.get(k) != tuple(zahl(z.get(n)) for n in (
                        "vorschub_gross", "vorschub_mittel", "vorschub_klein", "einstechzeit"))):
                continue
            n = neu[k]
            self.con.execute("UPDATE schneiddaten SET vorschub_gross=?, vorschub_mittel=?, vorschub_klein=?, "
                             "einstechzeit=? WHERE id=?", (n["vorschub_gross"], n["vorschub_mittel"],
                                                          n["vorschub_klein"], n["einstechzeit"], z["id"]))
        self._einstellung_schreiben("richtwerte_stand", RICHTWERTE_STAND)

    def _maschine_umbenannt(self, alt, neu):
        """Nach dem Umbenennen einer Maschine (Spalte angebote.maschine ist schon umbenannt): Maschinen-ID in den
        festgeschriebenen Zeitvorgaben und Schneiddaten der Angebote und in der Standard-Maschine mitziehen, damit
        alte Angebote unverändert weiterrechnen."""
        for r in self.con.execute("SELECT id, zeitbasis, preisbasis FROM angebote WHERE maschine=?", (neu,)).fetchall():
            zb = json.loads(r["zeitbasis"]) if r["zeitbasis"] else None
            pb = json.loads(r["preisbasis"]) if r["preisbasis"] else None
            if isinstance(zb, dict) and (zb.get("maschine") or {}).get("maschinen_id") == alt:
                zb["maschine"]["maschinen_id"] = neu
            if isinstance(pb, dict) and pb.get("maschine") == alt:
                pb["maschine"] = neu
                for z in pb.get("schneiddaten") or []:
                    if z.get("maschinen_id") == alt:
                        z["maschinen_id"] = neu
            self.con.execute("UPDATE angebote SET zeitbasis=?, preisbasis=? WHERE id=?",
                             (json.dumps(zb, ensure_ascii=False) if zb is not None else None,
                              json.dumps(pb, ensure_ascii=False) if pb is not None else None, r["id"]))
        r = self.con.execute("SELECT wert FROM einstellungen WHERE name='standard_maschine'").fetchone()
        if r is not None and json.loads(r[0]) == alt:
            self._einstellung_schreiben("standard_maschine", neu)

    def _profilformen_ergaenzen(self):
        """Dateien vor Schema 12: U-, C-, L-Profil und Flachstahl, seit 20.10.2026 auch I-/H-Träger und T-Profil, in
        die Auswahlliste Profilformen (vor 'Sonderprofil'), sofern sie dort fehlen; eigene Einträge bleiben."""
        formen = [s.strip() for s in (self.einstellung("profilformen") or "").splitlines() if s.strip()]
        neu = [f for f in OFFENE_PROFILE if f not in formen]
        if neu:
            i = formen.index("Sonderprofil") if "Sonderprofil" in formen else len(formen)
            self._einstellung_schreiben("profilformen", "\n".join(formen[:i] + neu + formen[i:]))

    def _wand_max_ergaenzen(self):
        """Dateien vor Schema 22: Wandstärke max. der Normprofile (Träger, T, UPN) aus der Flanschdicke der
        Normtabelle, wo sie dicker als die eingetragene Wandstärke ist; andere Profile bleiben leer."""
        from . import normprofile
        for pid, form, wand in self.con.execute("SELECT profil_id, form, wand FROM profile WHERE wand_max IS NULL")\
                .fetchall():
            n = normprofile.daten(pid)
            if n and n["form"] == form and n.get("tf") and (wand is None or n["tf"] > wand):
                self.con.execute("UPDATE profile SET wand_max=? WHERE profil_id=?", (n["tf"], pid))

    def _werkstoffe_ergaenzen(self):
        """Dateien vor Schema 11: Kategorie der vorhandenen Werkstoffe raten, fehlende Beispiel-Werkstoffe und
        Oberflächen ergänzen (vorhandene bleiben unverändert). Schneiddaten: unveränderte Beispieldaten werden
        ersetzt; eigene Werte bleiben und gehen vor, dazu kommen die Beispielwerte je Kategorie."""
        neu = beispieldaten()
        for z in self.zeilen("werkstoffe"):
            if not z.get("kategorie"):
                self.con.execute("UPDATE werkstoffe SET kategorie=? WHERE id=?", (kategorie_raten(z), z["id"]))
        da = {z["werkstoff_id"] for z in self.zeilen("werkstoffe")}
        self._einfuegen("werkstoffe", [z for z in neu["werkstoffe"] if z["werkstoff_id"] not in da])
        if not self.anzahl("oberflaechen"):
            self._einfuegen("oberflaechen", neu["oberflaechen"])
        if self.einstellung("stammdaten_herkunft") == "Beispieldaten":
            self.con.execute("DELETE FROM schneiddaten")
        self._einfuegen("schneiddaten", neu["schneiddaten"])

    def _umbenennen(self):
        """Dateien vor Schema 6: Tabellen, Spalten und Einstellungen von Auftrag auf Angebot umbenennen."""
        tabellen = {r[0] for r in self.con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for alt, neu in UMBENANNT_TABELLEN:
            if alt in tabellen and neu not in tabellen:
                self.con.execute(f'ALTER TABLE "{alt}" RENAME TO "{neu}"')
        for tabelle, alt, neu in UMBENANNT_SPALTEN:
            if tabelle in tabellen and alt in {r[1] for r in self.con.execute(f'PRAGMA table_info("{tabelle}")')}:
                self.con.execute(f'ALTER TABLE "{tabelle}" RENAME COLUMN "{alt}" TO "{neu}"')
        for name in ALTE_INDIZES:
            self.con.execute(f'DROP INDEX IF EXISTS "{name}"')
        for alt, neu in UMBENANNT_EINSTELLUNGEN:
            self.con.execute("UPDATE OR IGNORE einstellungen SET name=? WHERE name=?", (neu, alt))

    # -------------------------------------------------------------- Stammdaten
    def zeilen(self, tabelle):
        return [dict(r) for r in self.con.execute(f'SELECT * FROM "{tabelle}" ORDER BY id')]

    def anzahl(self, tabelle):
        return self.con.execute(f'SELECT COUNT(*) FROM "{tabelle}"').fetchone()[0]

    def _stammdaten_geaendert(self, tabelle):
        """Nach einer Änderung von Hand gelten die Stammdaten nicht mehr als Beispielwerte (Startseite).
        Kunden zählen dabei nicht: sie ändern keine Rechenwerte."""
        if tabelle in TABELLE and tabelle != "kunden" and not tabelle.startswith("zukauf_"):
            self._einstellung_schreiben("stammdaten_herkunft", "eigene Werte")
            self._einstellung_schreiben("stammdaten_stand", self._jetzt())

    def neu(self, tabelle, werte=None):
        werte = {k: v for k, v in (werte or {}).items() if k != "id"}
        with self.con:
            self._stammdaten_geaendert(tabelle)
            if not werte:
                return self.con.execute(f'INSERT INTO "{tabelle}" DEFAULT VALUES').lastrowid
            namen = ", ".join(f'"{k}"' for k in werte)
            return self.con.execute(f'INSERT INTO "{tabelle}" ({namen}) VALUES ({", ".join("?" * len(werte))})',
                                    list(werte.values())).lastrowid

    def aendern(self, tabelle, zeilen_id, feld, wert):
        """Ein Feld ändern. Ist es ein Schlüssel, auf den andere Tabellen verweisen (Profil-ID,
        Werkstoff-ID, Maschinen-ID), werden die Verweise mit umbenannt. Doppelte Schlüssel lösen
        ValueError aus."""
        ALLE_TABELLE[tabelle].feld(feld)   # unbekanntes Feld -> StopIteration
        alt = self.con.execute(f'SELECT "{feld}" FROM "{tabelle}" WHERE id=?', (zeilen_id,)).fetchone()
        try:
            with self.con:
                self._stammdaten_geaendert(tabelle)
                self.con.execute(f'UPDATE "{tabelle}" SET "{feld}"=? WHERE id=?', (wert, zeilen_id))
                if alt is not None and alt[0] not in (None, "") and wert not in (None, ""):
                    for ziel, zfeld in ALLE_VERWEISE.get((tabelle, feld), ()):
                        self.con.execute(f'UPDATE "{ziel}" SET "{zfeld}"=? WHERE "{zfeld}"=?', (wert, alt[0]))
                    if (tabelle, feld) == ("maschinen", "maschinen_id"):
                        self._maschine_umbenannt(alt[0], wert)
        except sqlite3.IntegrityError:
            t = ALLE_TABELLE[tabelle]
            namen = " + ".join(t.feld(s).titel for s in t.schluessel)
            raise ValueError(f"Diese Kombination ({namen}) gibt es schon." if len(t.schluessel) > 1
                             else f"{namen} '{wert}' gibt es schon.")

    def verweise(self, tabelle, zeilen_id):
        """Anzahl der Zeilen anderer Tabellen, die auf diese Zeile verweisen (Hinweis vor dem Löschen)."""
        n = 0
        for (quelle, feld), ziele in ALLE_VERWEISE.items():
            if quelle != tabelle:
                continue
            r = self.con.execute(f'SELECT "{feld}" FROM "{tabelle}" WHERE id=?', (zeilen_id,)).fetchone()
            if r and r[0] not in (None, ""):
                for ziel, zfeld in ziele:
                    n += self.con.execute(f'SELECT COUNT(*) FROM "{ziel}" WHERE "{zfeld}"=?', (r[0],)).fetchone()[0]
        return n

    def loeschen(self, tabelle, ids):
        with self.con:
            self._stammdaten_geaendert(tabelle)
            self.con.executemany(f'DELETE FROM "{tabelle}" WHERE id=?', [(i,) for i in ids])

    def schneiddaten_zuruecksetzen(self, maschinen=None):
        """Schneiddaten der Maschinen (None = alle mit mitgelieferten Richtwerten, stammdaten.LASER) auf die
        Standardwerte zurücksetzen: alle Zeilen dieser Maschinen (auch eigene und werkstoffgenaue) löschen, die
        Richtwerte neu einfügen. Andere Maschinen und festgeschriebene Angebote bleiben unverändert.
        Ergebnis: (gelöscht, eingefügt)."""
        standard = [z for z in beispieldaten()["schneiddaten"]
                    if maschinen is None or z["maschinen_id"] in maschinen]
        ids = sorted({z["maschinen_id"] for z in standard})
        if not ids:
            return 0, 0
        with self.con:
            self._stammdaten_geaendert("schneiddaten")
            weg = self.con.execute(f'DELETE FROM schneiddaten WHERE maschinen_id IN ({", ".join("?" * len(ids))})',
                                   ids).rowcount
            self._einfuegen("schneiddaten", standard)
        return weg, len(standard)

    # -------------------------------------------------------------- Zusatzarbeiten
    def _zusatz_positionen(self, name=None):
        """[(Positions-ID, Angebots-ID, Angebotsnummer, Liste)] aller Positionen mit Zusatzarbeiten (nur mit
        diesem Namen, falls angegeben)."""
        out = []
        for pid, aid, nummer, roh in self.con.execute(
                "SELECT p.id, p.angebot_id, a.nummer, p.zusatz FROM positionen p JOIN angebote a ON a.id = p.angebot_id "
                "WHERE p.zusatz IS NOT NULL AND p.zusatz <> ''"):
            try:
                liste = json.loads(roh)
            except ValueError:
                continue
            if not isinstance(liste, list):
                continue
            if name is None or any(isinstance(e, dict) and e.get("name") == name for e in liste):
                out.append((pid, aid, nummer, liste))
        return out

    def zusatz_verwendung(self, name):
        """Wo eine Zusatzarbeit verwendet wird: {angebote: [Nummer], positionen: Anzahl, ohne_stand: Anzahl
        Positionen ohne gespeicherten Preisstand (rechnen nach dem Löschen nicht mehr)}."""
        treffer = self._zusatz_positionen(name)
        ohne = sum(1 for *_, liste in treffer if any(isinstance(e, dict) and e.get("name") == name
                                                     and not isinstance(e.get("stand"), dict) for e in liste))
        return dict(angebote=sorted({n or "" for _, _, n, _ in treffer}), positionen=len(treffer), ohne_stand=ohne)

    def zusatz_haeufigkeit(self):
        """{Name: Anzahl Positionen} über alle Angebote (häufig verwendete Zusatzarbeiten zuerst anbieten)."""
        n = {}
        for *_, liste in self._zusatz_positionen():
            for name in {e.get("name") for e in liste if isinstance(e, dict) and e.get("name")}:
                n[name] = n.get(name, 0) + 1
        return n

    def zusatz_speichern(self, zeilen_id, werte):
        """Zusatzarbeit anlegen (zeilen_id None) oder alle Felder ersetzen. Wird der Name geändert, ändern sich die
        Namen in den Positionen mit (Preise bleiben). Ergebnis: ID. Doppelter Name -> ValueError."""
        felder = [f.name for f in TABELLE["zusatzarbeiten"].felder]
        werte = {n: werte.get(n) for n in felder}
        try:
            with self.con:
                self._stammdaten_geaendert("zusatzarbeiten")
                if zeilen_id is None:
                    return self.con.execute(
                        f'INSERT INTO zusatzarbeiten ({", ".join(chr(34) + n + chr(34) for n in felder)}) '
                        f'VALUES ({", ".join("?" * len(felder))})', [werte[n] for n in felder]).lastrowid
                alt = self.con.execute("SELECT name FROM zusatzarbeiten WHERE id=?", (zeilen_id,)).fetchone()
                self.con.execute(f'UPDATE zusatzarbeiten SET {", ".join(chr(34) + n + chr(34) + "=?" for n in felder)} '
                                 "WHERE id=?", [werte[n] for n in felder] + [zeilen_id])
                if alt and alt[0] and werte["name"] and alt[0] != werte["name"]:
                    for pid, _, _, liste in self._zusatz_positionen(alt[0]):
                        for e in liste:
                            if isinstance(e, dict) and e.get("name") == alt[0]:
                                e["name"] = werte["name"]
                        self.con.execute("UPDATE positionen SET zusatz=? WHERE id=?",
                                         (json.dumps(liste, ensure_ascii=False), pid))
                return zeilen_id
        except sqlite3.IntegrityError:
            raise ValueError(f"Eine Zusatzarbeit '{werte['name']}' gibt es schon.")

    # -------------------------------------------------------------- Zukaufartikel
    def zukauf_kategorien(self):
        """{Name: Zeile} der Kategorien der Zukaufartikel."""
        return {z["name"]: z for z in self.zeilen("zukauf_kategorien") if z.get("name")}

    def zukauf_artikel_liste(self):
        """Alle Zukaufartikel, je mit 'bezuege' (Einkauf je Lieferant, bevorzugter zuerst)."""
        bezuege = {}
        for b in self.zeilen("zukauf_bezug"):
            bezuege.setdefault(b["artikel_id"], []).append(b)
        out = []
        for a in self.zeilen("zukauf_artikel"):
            a["bezuege"] = sorted(bezuege.get(a["id"], []), key=lambda b: b.get("bevorzugt") != "ja")
            out.append(a)
        return out

    def zukauf_artikel(self, artikel_id):
        """Zukaufartikel mit 'bezuege' oder None."""
        r = self.con.execute("SELECT * FROM zukauf_artikel WHERE id=?", (artikel_id,)).fetchone()
        if r is None:
            return None
        a = dict(r)
        a["bezuege"] = sorted((dict(b) for b in self.con.execute(
            "SELECT * FROM zukauf_bezug WHERE artikel_id=? ORDER BY id", (artikel_id,))),
            key=lambda b: b.get("bevorzugt") != "ja")
        return a

    def zukauf_speichern(self, artikel_id, werte, bezuege, bemerkung=None):
        """Zukaufartikel anlegen (artikel_id None) oder ersetzen, mit allen Einkaufsbedingungen. Prüft Eingaben
        (zukauf.artikel_fehler) und eindeutige Artikelnummer (ValueError). Änderungen an Einkaufspreisen und
        Aufschlag kommen ins Protokoll der Preisänderungen. Ergebnis: ID."""
        felder = [f.name for f in zukauf.ARTIKEL.felder if f.name not in ("angelegt", "geaendert")]
        alt = self.zukauf_artikel(artikel_id) if artikel_id is not None else None
        # Blechdaten (Maße, STEP-Datei, Kennung) bleiben erhalten, wenn der Aufrufer sie nicht mitgibt
        werte = {n: alt.get(n) if alt is not None and n in zukauf.BLECH_FELDER and n not in werte else werte.get(n)
                 for n in felder}
        for n in ("artikelnr", "bezeichnung"):
            if isinstance(werte[n], str):
                werte[n] = werte[n].strip() or None
        bezuege = [dict(b) for b in bezuege or () if any(b.get(f.name) not in (None, "", [])
                                                         for f in zukauf.BEZUG.felder if f.name != "artikel_id")]
        for b in bezuege:
            if isinstance(b.get("lieferant"), str):
                b["lieferant"] = b["lieferant"].strip() or None
        fehler = zukauf.artikel_fehler(werte, bezuege)
        if fehler:
            raise ValueError("; ".join(fehler))
        if werte["artikelnr"]:
            r = self.con.execute("SELECT id FROM zukauf_artikel WHERE artikelnr=? AND id IS NOT ?",
                                 (werte["artikelnr"], artikel_id)).fetchone()
            if r:
                raise ValueError(f"Artikelnummer '{werte['artikelnr']}' gibt es schon.")
        if bezuege and not any(b.get("bevorzugt") == "ja" for b in bezuege):
            bezuege[0]["bevorzugt"] = "ja"
        for b in bezuege:
            if isinstance(b.get("preise"), list):
                b["preise"] = json.dumps(b["preise"], ensure_ascii=False)
        jetzt = self._jetzt()
        bekannt = {z["name"] for z in self.zeilen("zukauf_lieferanten")}
        neue_lieferanten = sorted({b["lieferant"].strip() for b in bezuege if (b.get("lieferant") or "").strip()} - bekannt)
        bfelder = [f.name for f in zukauf.BEZUG.felder if f.name != "artikel_id"]
        with self.con:
            if alt is None:
                namen = felder + ["angelegt", "geaendert"]
                artikel_id = self.con.execute(
                    f'INSERT INTO zukauf_artikel ({", ".join(chr(34) + n + chr(34) for n in namen)}) '
                    f'VALUES ({", ".join("?" * len(namen))})', [werte[n] for n in felder] + [jetzt, jetzt]).lastrowid
            else:
                self.con.execute(f'UPDATE zukauf_artikel SET {", ".join(chr(34) + n + chr(34) + "=?" for n in felder)}, '
                                 "geaendert=? WHERE id=?", [werte[n] for n in felder] + [jetzt, artikel_id])
                self.con.execute("DELETE FROM zukauf_bezug WHERE artikel_id=?", (artikel_id,))
            # Lieferanten, die es noch nicht gibt, werden mit Namen angelegt
            self.con.executemany("INSERT INTO zukauf_lieferanten (name) VALUES (?)", [(n,) for n in neue_lieferanten])
            for b in bezuege:
                self.con.execute(f'INSERT INTO zukauf_bezug (artikel_id, {", ".join(chr(34) + n + chr(34) for n in bfelder)}) '
                                 f'VALUES (?, {", ".join("?" * len(bfelder))})', [artikel_id] + [b.get(n) for n in bfelder])
            self._zukauf_protokoll(artikel_id, alt, dict(werte, bezuege=bezuege), jetzt, bemerkung)
        return artikel_id

    def zukauf_ek_eintragen(self, artikel_id, preis, lieferant=None, ab=None, bemerkung=None):
        """Einkaufspreis je Einheit (ab Menge 1) beim Lieferanten eintragen (fehlt er, beim bevorzugten bzw. einem neuen
        Eintrag); weitere Staffelzeilen dieses Lieferanten werden ersetzt. Mit ab (Stückzahl, z. B. aus dem Angebot)
        wird der Preis als Staffelzeile 'ab Stückzahl' eingetragen und die übrigen Zeilen über 0 € bleiben (kleinere
        Mengen nehmen die erste Zeile). Preis muss über 0 € liegen (ValueError)."""
        p = zukauf.dez(preis)
        if p is None or p <= 0:
            raise ValueError("Bitte einen Einkaufspreis über 0 € eingeben.")
        a = self.zukauf_artikel(artikel_id)
        if a is None:
            raise ValueError("Artikel nicht gefunden.")
        bezuege = [dict(b) for b in a["bezuege"]]
        for b in bezuege:
            b.pop("id", None)
            b.pop("artikel_id", None)
        b = zukauf.bezug_waehlen(bezuege, lieferant)
        if b is None or (lieferant and b.get("lieferant") != lieferant and b.get("lieferant")):
            b = dict(lieferant=lieferant or None, bevorzugt="nein" if bezuege else "ja", preiseinheit=1)
            bezuege.append(b)
        elif lieferant:
            b["lieferant"] = lieferant
        if ab is None:
            b["preise"] = [dict(ab=1, preis=float(p))]
        else:
            ab = max(1, float(ab))
            ab = int(ab) if ab.is_integer() else ab
            bleiben = [e for e in zukauf.staffel_sortiert(b.get("preise")) if e["preis"] > 0 and float(e["ab"]) != ab]
            b["preise"] = sorted([dict(ab=float(e["ab"]), preis=float(e["preis"])) for e in bleiben]
                                 + [dict(ab=ab, preis=float(p))], key=lambda e: e["ab"])
        b["preiseinheit"] = b.get("preiseinheit") or 1
        a.pop("bezuege")
        return self.zukauf_speichern(artikel_id, a, bezuege, bemerkung=bemerkung or "EK eingetragen")

    PROTOKOLL_ARTIKEL = ("aufschlag_quelle", "aufschlag_methode", "aufschlag_wert", "aufschlag_staffel")
    PROTOKOLL_BEZUG = ("preise", "preiseinheit", "rabatt", "verpackung", "mindermenge", "mindermenge_bis", "fracht",
                       "fracht_einheit", "weitere", "mindestmenge", "vpe", "gueltig_von", "gueltig_bis")

    def _zukauf_protokoll(self, artikel_id, alt, neu, jetzt, bemerkung):
        """Preisänderungen protokollieren (alt None = neuer Artikel: Einkaufspreise als 'neu')."""
        name = " ".join(x for x in (neu.get("artikelnr"), neu.get("bezeichnung")) if x)
        zeilen = []
        leer = lambda w: None if w in (None, "", "[]") else w
        text = lambda w: "" if w in (None, "") else (zukauf.staffel_text(w) if isinstance(w, str) and w.startswith("[")
                                                    else zukauf.zahl_text(w) if isinstance(w, (int, float)) else str(w))
        if alt is not None:
            for f in self.PROTOKOLL_ARTIKEL:
                if leer(alt.get(f)) != leer(neu.get(f)):
                    zeilen.append(("", zukauf.ARTIKEL.feld(f).titel, text(alt.get(f)), text(neu.get(f))))
        alt_b = {b.get("lieferant") or "": b for b in (alt or {}).get("bezuege", ())}
        neu_b = {b.get("lieferant") or "": b for b in neu.get("bezuege", ())}
        for lief in list(alt_b) + [n for n in neu_b if n not in alt_b]:
            a, b = alt_b.get(lief), neu_b.get(lief)
            if a is None:
                zeilen.append((lief, "Lieferant neu", "", text(b.get("preise"))))
            elif b is None:
                zeilen.append((lief, "Lieferant entfernt", text(a.get("preise")), ""))
            else:
                for f in self.PROTOKOLL_BEZUG:
                    if leer(a.get(f)) != leer(b.get(f)):
                        zeilen.append((lief, zukauf.BEZUG.feld(f).titel, text(a.get(f)), text(b.get(f))))
        self.con.executemany("INSERT INTO zukauf_historie (datum, artikel_id, artikel, lieferant, feld, alt, neu, "
                             "bemerkung) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                             [(jetzt, artikel_id, name, l, f, a, n, bemerkung) for l, f, a, n in zeilen])

    def zukauf_status(self, artikel_id, status):
        """Artikel archivieren oder wieder aktivieren (Positionen mit dem Artikel rechnen mit ihrem Preisstand weiter)."""
        with self.con:
            self.con.execute("UPDATE zukauf_artikel SET status=?, geaendert=? WHERE id=?",
                             (status, self._jetzt(), artikel_id))

    def zukauf_historie(self, artikel_id=None):
        """Preisänderungen, neueste zuerst."""
        sql = "SELECT * FROM zukauf_historie" + (" WHERE artikel_id=?" if artikel_id is not None else "")
        return [dict(r) for r in self.con.execute(sql + " ORDER BY datum DESC, id DESC",
                                                  (artikel_id,) if artikel_id is not None else ())]

    def zukauf_stand(self, artikel_id, lieferant=None):
        """Aktueller Preisstand eines Artikels für eine Position (zukauf.stand) oder None."""
        a = self.zukauf_artikel(artikel_id)
        if a is None:
            return None
        return zukauf.stand(a, zukauf.bezug_waehlen(a["bezuege"], lieferant), self.zukauf_kategorien(),
                            self.einstellung("zukauf_aufschlag"))

    def zukauf_positionen(self, artikel_id=None):
        """[(Positions-ID, Angebots-ID, Angebotsnummer, Liste)] aller Positionen mit Zukaufteilen (nur mit diesem
        Artikel, falls angegeben)."""
        out = []
        for pid, aid, nummer, roh in self.con.execute(
                "SELECT p.id, p.angebot_id, a.nummer, p.zukauf FROM positionen p JOIN angebote a ON a.id = p.angebot_id "
                "WHERE p.zukauf IS NOT NULL AND p.zukauf <> ''"):
            liste = zukauf.json_liste(roh)
            if artikel_id is None or any(e.get("artikel_id") == artikel_id for e in liste):
                out.append((pid, aid, nummer, liste))
        return out

    def zukauf_verwendung(self, artikel_id):
        """Wo ein Artikel verwendet wird: {angebote: [Nummer], positionen: Anzahl, veraltet: [Nummer] (Angebote,
        deren gespeicherter Preisstand vom aktuellen abweicht)}."""
        aktuell = {}
        treffer = self.zukauf_positionen(artikel_id)
        veraltet = set()
        for _, _, nummer, liste in treffer:
            for e in liste:
                if e.get("artikel_id") != artikel_id:
                    continue
                lief = ((e.get("stand") or {}).get("bezug") or {}).get("lieferant")
                if lief not in aktuell:
                    aktuell[lief] = zukauf.stand_kennung(self.zukauf_stand(artikel_id, lief))
                if zukauf.stand_kennung(e.get("stand")) != aktuell[lief]:
                    veraltet.add(nummer or "")
        return dict(angebote=sorted({n or "" for _, _, n, _ in treffer}), positionen=len(treffer),
                    veraltet=sorted(veraltet))

    def zukauf_betroffen(self, artikel_id):
        """Angebote mit dem Artikel in einem älteren Preisstand: [{angebot_id, nummer, kunde, positionen, stand
        (Datum), verbrauch, vk_alt, vk_neu}] (VK netto für den ganzen Verbrauch im Angebot, ohne Skonto)."""
        aktuell, out = {}, {}
        for pid, aid, nummer, liste in self.zukauf_positionen(artikel_id):
            stueck, je_satz = self.con.execute("SELECT stueck, je_satz FROM positionen WHERE id=?", (pid,)).fetchone()
            pos = dict(stueck=stueck or 0, je_satz=je_satz)
            for n, e in enumerate(liste):
                if e.get("artikel_id") != artikel_id:
                    continue
                lief = ((e.get("stand") or {}).get("bezug") or {}).get("lieferant")
                if lief not in aktuell:
                    aktuell[lief] = self.zukauf_stand(artikel_id, lief)
                if zukauf.stand_kennung(e.get("stand")) == zukauf.stand_kennung(aktuell[lief]):
                    continue
                x = out.setdefault(aid, dict(angebot_id=aid, nummer=nummer, positionen=set(), alt=[], neu=[],
                                             stand=set()))
                x["positionen"].add(pid)
                x["stand"].add((e.get("stand") or {}).get("datum") or "")
                x["alt"].append(((pid, n), e, zukauf.bezugsmenge(e, pos)))
                x["neu"].append(((pid, n), dict(e, stand=aktuell[lief]), zukauf.bezugsmenge(e, pos)))
        ergebnis = []
        for x in out.values():
            alt, _ = zukauf.rechnen(x["alt"])
            neu, _ = zukauf.rechnen(x["neu"])
            kopf = self.con.execute("SELECT kunde FROM angebote WHERE id=?", (x["angebot_id"],)).fetchone()
            fehlt = any(g["fehler"] for g in alt + neu)
            ergebnis.append(dict(angebot_id=x["angebot_id"], nummer=x["nummer"], kunde=kopf[0] if kopf else None,
                                 positionen=len(x["positionen"]), stand=", ".join(sorted(d[:10] for d in x["stand"])),
                                 verbrauch=float(sum((g["bestellung"]["verbrauch"] for g in alt), zukauf.NULL)),
                                 vk_alt=None if fehlt else float(sum((g["vk"] for g in alt), zukauf.NULL)),
                                 vk_neu=None if fehlt else float(sum((g["vk"] for g in neu), zukauf.NULL))))
        return sorted(ergebnis, key=lambda x: x["nummer"] or "")

    def zukauf_angebot_aktualisieren(self, angebot_id, artikel_id):
        """Preisstand eines Artikels in allen Positionen eines Angebots auf den aktuellen Stand setzen (gleicher
        Lieferant). Ergebnis: Anzahl geänderter Einträge."""
        n = 0
        for pid, aid, _, liste in self.zukauf_positionen(artikel_id):
            if aid != angebot_id:
                continue
            geaendert = False
            for e in liste:
                if e.get("artikel_id") != artikel_id:
                    continue
                neu = self.zukauf_stand(artikel_id, ((e.get("stand") or {}).get("bezug") or {}).get("lieferant"))
                if neu is not None and zukauf.stand_kennung(neu) != zukauf.stand_kennung(e.get("stand")):
                    e["stand"] = neu
                    geaendert = True
                    n += 1
            if geaendert:
                self.position_aendern(pid, "zukauf", json.dumps(liste, ensure_ascii=False))
        return n

    def zukauf_importieren(self, zeilen, bemerkung="CSV-Import"):
        """Geprüfte Zeilen aus zukauf_csv.vorschau übernehmen (nur 'neu' und 'ändern'). Unbekannte Kategorien werden
        angelegt. Ergebnis: (neu, geändert)."""
        from .zukauf_csv import AENDERN, NEU
        je = {}
        for z in zeilen:
            if z.get("aktion") in (NEU, AENDERN):
                je[z["artikelnr"]] = z            # mehrere Lieferanten: Zeilen tragen denselben zusammengeführten Artikel
        kategorien = set(self.zukauf_kategorien())
        neu = geaendert = 0
        for z in je.values():
            kat = z["artikel"].get("kategorie")
            if kat and kat not in kategorien:
                self.neu("zukauf_kategorien", dict(name=kat, aktiv="ja"))
                kategorien.add(kat)
            vorhanden = self.con.execute("SELECT id FROM zukauf_artikel WHERE artikelnr=?",
                                         (z["artikelnr"],)).fetchone()
            self.zukauf_speichern(vorhanden[0] if vorhanden else None, z["artikel"], z["bezuege"], bemerkung)
            if vorhanden:
                geaendert += 1
            else:
                neu += 1
        return neu, geaendert

    def stammdaten_ersetzen(self, daten, einstellungen, herkunft):
        """Alle Stammdatentabellen in einem Schritt ersetzen (z. B. Beispieldaten einer neuen Datei).
        daten: {Tabelle: [Zeile, …]}; einstellungen: {Name: Wert}, nur die genannten werden gesetzt."""
        with self.con:
            for t in TABELLEN:
                if t.name not in daten:
                    continue
                self.con.execute(f'DELETE FROM "{t.name}"')
                namen = [f.name for f in t.felder]
                self.con.executemany(
                    f'INSERT INTO "{t.name}" ({", ".join(chr(34) + n + chr(34) for n in namen)}) '
                    f'VALUES ({", ".join("?" * len(namen))})',
                    [[z.get(n) for n in namen] for z in daten[t.name]])
            for name, wert in einstellungen.items():
                self._einstellung_schreiben(name, wert)
            self._einstellung_schreiben("stammdaten_herkunft", herkunft)
            self._einstellung_schreiben("stammdaten_stand", datetime.datetime.now().isoformat(timespec="seconds"))

    def kontext(self):
        formen = [s.strip() for s in self.einstellung("profilformen").splitlines() if s.strip()]
        kategorien = [s.strip() for s in (self.einstellung("kategorien") or "").splitlines() if s.strip()]
        k = kontext_aus({t: self.zeilen(t) for t in ("profile", "werkstoffe", "maschinen", "oberflaechen",
                                                     "stundensaetze", "schneiddaten", "zukauf_kategorien",
                                                     "zukauf_lieferanten")},
                        formen, kategorien)
        k.listen = listen_aus(self.fracht_daten(), self.zeilen("kunden"))
        return k

    def tabellen(self):
        """Stammdaten, die die Rechnung braucht (Preise, Lieferlängen, Schneiddaten, Gewinde, Zusatzarbeiten, Stundensätze,
        Arbeitsschritte)."""
        tab = {t: self.zeilen(t) for t in ("preise", "lieferlaengen", "schneiddaten", "gewinde", "zusatzarbeiten",
                                           "stundensaetze", "arbeitsschritte")}
        tab["einstellungen"] = self.einstellungen()     # Händler-Mehrlänge im Materialpreis (rechnen.lieferstange_preis)
        return tab

    def zeitbasis_vorgabe(self, maschinen_id):
        """Snapshot der Stundensätze und Zeitvorgaben für ein Angebot (rechnen.zeitbasis_aus)."""
        from .rechnen import zeitbasis_aus
        return zeitbasis_aus(maschinen_id, self.kontext(), self.tabellen())

    def zeitbasis_speichern(self, angebot_id, zeitbasis):
        """Stundensätze und Zeitvorgaben eines Angebots setzen (None = wieder die aktuellen Stammdaten)."""
        with self.con:
            self.con.execute("UPDATE angebote SET zeitbasis=?, geaendert=? WHERE id=?",
                             (json.dumps(zeitbasis, ensure_ascii=False) if zeitbasis is not None else None,
                              self._jetzt(), angebot_id))

    def preisbasis_speichern(self, angebot_id, preisbasis):
        """Festgeschriebene Materialpreise und Schneiddaten eines Angebots setzen (rechnen.preisbasis_aus;
        None = wieder die aktuellen Stammdaten)."""
        with self.con:
            self.con.execute("UPDATE angebote SET preisbasis=?, geaendert=? WHERE id=?",
                             (json.dumps(preisbasis, ensure_ascii=False) if preisbasis is not None else None,
                              self._jetzt(), angebot_id))

    def laengenwahl_speichern(self, angebot_id, wahl):
        """Übernommene Lieferlängen eines Angebots {Gruppenschlüssel: Länge} (rechnen.laengen_schluessel;
        leer = alle Gruppen mit der Stangenlänge des Angebots)."""
        with self.con:
            self.con.execute("UPDATE angebote SET laengenwahl=?, geaendert=? WHERE id=?",
                             (json.dumps(wahl, ensure_ascii=False) if wahl else None, self._jetzt(), angebot_id))

    # -------------------------------------------------------------- Frachtkosten
    def fracht_daten(self):
        """Fracht-Stammdaten für den Rechenkern {Kurzname: [Zeilen]} (fracht_daten.KURZ)."""
        return {kurz: self.zeilen(t) for t, kurz in KURZ.items()}

    def fracht_beispiele_laden(self):
        """Beispiel-Frachtdaten (BEISPIEL) einfügen; vorhandene Zeilen mit gleichem Schlüssel bleiben.
        Ergebnis: Anzahl eingefügter Zeilen."""
        n = 0
        with self.con:
            for tabelle, zeilen in fracht_beispieldaten().items():
                namen = [f.name for f in ALLE_TABELLE[tabelle].felder]
                for z in zeilen:
                    c = self.con.execute(f'INSERT OR IGNORE INTO "{tabelle}" ({", ".join(chr(34) + x + chr(34) for x in namen)}) '
                                         f'VALUES ({", ".join("?" * len(namen))})', [z.get(x) for x in namen])
                    n += c.rowcount
        return n

    def fracht_richtwerte_laden(self, absender_plz=None):
        """Richtwerte Palettenversand (fracht_richtwerte.py) übernehmen: alle Zeilen mit BEISPIEL oder RICHTWERT in
        der Bemerkung werden ersetzt, eigene Einträge bleiben (gleicher Schlüssel: der eigene gilt). Absender-PLZ
        (leer = Einstellung) muss eine deutsche PLZ sein; leere Absender-PLZ und Versandart werden gesetzt.
        Ergebnis: (entfernt, eingefügt)."""
        from .fracht_richtwerte import TARIF, VERSANDART, richtwerte
        absender_plz = (absender_plz or self.einstellung("absender_plz") or "").strip()
        daten = richtwerte(absender_plz)              # ValueError bei unbekannter PLZ, vor jeder Änderung
        weg = neu = 0
        with self.con:
            for tabelle in KURZ:
                if "bemerkung" in [f.name for f in ALLE_TABELLE[tabelle].felder]:
                    weg += self.con.execute(f'DELETE FROM "{tabelle}" WHERE bemerkung LIKE \'BEISPIEL%\' '
                                            "OR bemerkung LIKE 'RICHTWERT%'").rowcount
            weg += self.con.execute("DELETE FROM fracht_preise WHERE tarif_id=?", (TARIF,)).rowcount
            for tabelle, zeilen in daten.items():
                namen = [f.name for f in ALLE_TABELLE[tabelle].felder]
                for z in zeilen:
                    neu += self.con.execute(
                        f'INSERT OR IGNORE INTO "{tabelle}" ({", ".join(chr(34) + x + chr(34) for x in namen)}) '
                        f'VALUES ({", ".join("?" * len(namen))})', [z.get(x) for x in namen]).rowcount
        if not self.einstellung("absender_plz"):
            self.einstellung_setzen("absender_plz", absender_plz)
        if (self.einstellung("fracht_versandart") or "Stückgut") == "Stückgut":
            self.einstellung_setzen("fracht_versandart", VERSANDART)
        return weg, neu

    def fracht_zonen_zuruecksetzen(self, absender_plz=None):
        """Frachtzonen und PLZ-Zuordnungen auf Standard (Richtwert-Zonen RW1–4 und Inseln ab der Absender-PLZ,
        fracht_richtwerte.py) zurücksetzen: vorher geschützte Sicherung 'vor_Frachtzonen_Standard', dann alle Zonen
        und PLZ-Zuordnungen löschen (auch eigene) und die Standardzeilen einfügen. Die Preise des Richtwert-Tarifs
        werden passend neu geschrieben (Land DE, Dienstleister und Tarif angelegt, falls sie fehlen); andere Tarife,
        Zuschläge, Ladehilfsmittel und Angebote mit gespeicherter Tarifkopie bleiben unverändert.
        Ergebnis: (entfernt, eingefügt, Pfad der Sicherung)."""
        from .fracht_richtwerte import TARIF, richtwerte
        absender_plz = (absender_plz or self.einstellung("absender_plz") or "").strip()
        daten = richtwerte(absender_plz)              # ValueError bei unbekannter PLZ, vor jeder Änderung
        pfad = self.sicherung(zusatz="vor_Frachtzonen_Standard")
        weg = neu = 0

        def einfuegen(tabelle, zeilen):
            namen = [f.name for f in ALLE_TABELLE[tabelle].felder]
            return sum(self.con.execute(
                f'INSERT OR IGNORE INTO "{tabelle}" ({", ".join(chr(34) + x + chr(34) for x in namen)}) '
                f'VALUES ({", ".join("?" * len(namen))})', [z.get(x) for x in namen]).rowcount for z in zeilen)
        with self.con:
            for tabelle in ("fracht_plz", "fracht_zonen"):
                weg += self.con.execute(f'DELETE FROM "{tabelle}"').rowcount
            weg += self.con.execute("DELETE FROM fracht_preise WHERE tarif_id=?", (TARIF,)).rowcount
            for tabelle in ("fracht_laender", "fracht_dienstleister", "fracht_tarife"):
                einfuegen(tabelle, daten[tabelle])
            for tabelle in ("fracht_zonen", "fracht_plz", "fracht_preise"):
                neu += einfuegen(tabelle, daten[tabelle])
        if not self.einstellung("absender_plz"):
            self.einstellung_setzen("absender_plz", absender_plz)
        return weg, neu, pfad

    def fracht_zonen_fremd(self):
        """Preiszeilen anderer Tarife (nicht Richtwert), deren Zone es nach dem Zurücksetzen nicht mehr gäbe: Anzahl
        (für die Sicherheitsabfrage)."""
        from .fracht_richtwerte import RINGE, TARIF
        standard = [z for z, *_ in RINGE] + ["RW-INSEL"]
        return self.con.execute(
            f'SELECT COUNT(*) FROM fracht_preise WHERE tarif_id<>? AND COALESCE(zone_id,\'\')<>\'\' AND zone_id NOT IN '
            f'({", ".join("?" * len(standard))})', [TARIF] + standard).fetchone()[0]

    def plz_importieren(self, zeilen):
        """PLZ-Zuordnungen übernehmen (fracht_daten.plz_csv_lesen); gleicher Schlüssel (Land, PLZ von, PLZ bis,
        Richtung, Dienstleister, Kunde) wird ersetzt. Ergebnis: (neu, ersetzt)."""
        namen = [f.name for f in ALLE_TABELLE["fracht_plz"].felder]
        neu = ersetzt = 0
        with self.con:
            for z in zeilen:
                alt = self.con.execute(
                    "SELECT id FROM fracht_plz WHERE land=? AND plz_von=? AND COALESCE(plz_bis,'')=? AND "
                    "COALESCE(richtung,'')=? AND COALESCE(dienstleister,'')=? AND COALESCE(kundennr,'')=?",
                    [z.get("land"), z.get("plz_von")] + [z.get(x) or "" for x in ("plz_bis", "richtung", "dienstleister",
                                                                                    "kundennr")]).fetchone()
                if alt:
                    self.con.execute(f'UPDATE fracht_plz SET {", ".join(chr(34) + x + chr(34) + "=?" for x in namen)} '
                                     "WHERE id=?", [z.get(x) for x in namen] + [alt[0]])
                    ersetzt += 1
                else:
                    self.con.execute(f'INSERT INTO fracht_plz ({", ".join(chr(34) + x + chr(34) for x in namen)}) '
                                     f'VALUES ({", ".join("?" * len(namen))})', [z.get(x) for x in namen])
                    neu += 1
        return neu, ersetzt

    def fracht_tarif_neue_version(self, tarif_id, ab):
        """Tarif mit Preisstaffeln kopieren: neue Tarif-ID '<alt>/<ab>', gültig ab `ab` (ISO); der alte Tarif
        bekommt 'gültig bis' am Vortag. Ergebnis: neue Tarif-ID."""
        alt = self.con.execute("SELECT * FROM fracht_tarife WHERE tarif_id=?", (tarif_id,)).fetchone()
        if alt is None:
            raise ValueError(f"Tarif {tarif_id} unbekannt.")
        alt = dict(alt)
        if alt.get("gueltig_ab") and ab <= alt["gueltig_ab"]:
            raise ValueError("Die neue Version muss nach dem Beginn der alten gelten.")
        basis = tarif_id.split("/")[0]
        neu_id, i = f"{basis}/{ab}", 2
        while self.con.execute("SELECT 1 FROM fracht_tarife WHERE tarif_id=?", (neu_id,)).fetchone():
            neu_id, i = f"{basis}/{ab}-{i}", i + 1
        vortag = (datetime.date.fromisoformat(ab) - datetime.timedelta(days=1)).isoformat()
        with self.con:
            werte = {k: v for k, v in alt.items() if k != "id"}
            werte.update(tarif_id=neu_id, gueltig_ab=ab, gueltig_bis=alt.get("gueltig_bis") if (
                alt.get("gueltig_bis") or "") > ab else None, version=ab[:7])
            self.con.execute(f'INSERT INTO fracht_tarife ({", ".join(chr(34) + k + chr(34) for k in werte)}) '
                             f'VALUES ({", ".join("?" * len(werte))})', list(werte.values()))
            self.con.execute("UPDATE fracht_tarife SET gueltig_bis=? WHERE id=?", (vortag, alt["id"]))
            for p in self.con.execute("SELECT * FROM fracht_preise WHERE tarif_id=?", (tarif_id,)).fetchall():
                w = {k: v for k, v in dict(p).items() if k != "id"}
                w["tarif_id"] = neu_id
                self.con.execute(f'INSERT INTO fracht_preise ({", ".join(chr(34) + k + chr(34) for k in w)}) '
                                 f'VALUES ({", ".join("?" * len(w))})', list(w.values()))
        return neu_id

    def _fracht_auto(self, angebot_id):
        """Angebot, Positionen, Positionswerte und neue automatische Frachtberechnung (ohne zu speichern)."""
        from . import fracht_angebot
        from .angebot import aktiv
        from .rechnen import position_werte
        a = self.angebot(angebot_id)
        pos = self.positionen(angebot_id)
        k, tab = self.kontext(), self.tabellen()
        werte = [position_werte(p, a, k, tab) if aktiv(p) else None for p in pos]
        einst = {n: self.einstellung(n) for n in ("absender_plz", "absender_land", "fracht_versandart",
                                                  "fracht_lht_standard", "fracht_lht_langgut")}
        return a, pos, werte, lambda: fracht_angebot.auto_rechnen(self.fracht_daten(), a, pos, werte,
                                                                  self.kunde(a.get("kundennr")), einst)

    def _fracht_auto_speichern(self, angebot_id, d):
        from . import fracht_angebot
        self.angebot_aendern(angebot_id, "fracht_sendung", json.dumps(d, ensure_ascii=False, default=str))
        self.angebot_aendern(angebot_id, "fracht_modus", fracht_angebot.BERECHNET)
        self.angebot_aendern(angebot_id, "fracht", d.get("gesamt"))

    def fracht_auto_aktualisieren(self, angebot_id):
        """'Fracht automatisch berechnen': Zone, Tarif und Tarifkopie mit den aktuellen Frachtdaten neu festhalten
        (beim Setzen des Hakens, Ändern der Ziel-PLZ oder des Kunden). Ergebnis: Frachtberechnung (dict)."""
        d = self._fracht_auto(angebot_id)[3]()
        self._fracht_auto_speichern(angebot_id, d)
        return d

    def fracht_auto_nachfuehren(self, angebot_id):
        """Nach jeder Änderung am Angebot (Haken gesetzt): Fracht mit der Tarifkopie neu rechnen und ins Feld
        Frachtkosten schreiben (leer, solange sie nicht berechnet werden kann). Ohne Tarifkopie (noch nicht
        berechnet, Fehler) wird ganz neu gerechnet, z. B. sobald Gewicht oder Versandart da sind.
        Gespeichert wird nur, was sich ändert. Ergebnis: True = geändert."""
        from . import fracht_angebot
        a = self.angebot(angebot_id)
        if not a or not fracht_angebot.auto(a) or fracht_angebot.modus(a) != fracht_angebot.BERECHNET:
            return False
        a, pos, werte, neu = self._fracht_auto(angebot_id)
        d = fracht_angebot.daten(a)
        if not d or not d.get("snapshot"):
            d2 = json.loads(json.dumps(neu(), ensure_ascii=False, default=str))
            if d2 == d and d2.get("gesamt") == a.get("fracht"):
                return False
            self._fracht_auto_speichern(angebot_id, d2)
            return True
        b, _, _ = fracht_angebot.stufe(a, pos, werte)
        b = round(b, 2) if b is not None else None
        if b == a.get("fracht"):
            return False
        self.angebot_aendern(angebot_id, "fracht", b)
        return True

    def fracht_kalkulation_speichern(self, ergebnis, bezeichnung="", angebot_id=None):
        """Abgeschlossene Frachtkalkulation mit allen verwendeten Tarifwerten (Snapshot) in die Historie."""
        from . import VERSION
        with self.con:
            return self.con.execute(
                "INSERT INTO fracht_kalkulationen (datum, angebot_id, bezeichnung, eingaben, ergebnis, gesamt, programm) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (self._jetzt(), angebot_id, bezeichnung, json.dumps(ergebnis.get("eingaben"), ensure_ascii=False),
                 json.dumps(ergebnis, ensure_ascii=False, default=str), ergebnis.get("gesamt"), VERSION)).lastrowid

    def fracht_kalkulationen(self):
        """Historie, neueste zuerst: id, datum, bezeichnung, angebot_id, gesamt und das gespeicherte Ergebnis."""
        out = []
        for r in self.con.execute("SELECT * FROM fracht_kalkulationen ORDER BY datum DESC, id DESC"):
            z = dict(r)
            z["ergebnis"] = json.loads(z["ergebnis"]) if z.get("ergebnis") else {}
            z["eingaben"] = json.loads(z["eingaben"]) if z.get("eingaben") else {}
            out.append(z)
        return out

    # -------------------------------------------------------------- Kunden
    def kunde(self, kundennr):
        """Kundenzeile zur Kundennummer oder None."""
        if kundennr in (None, ""):
            return None
        r = self.con.execute("SELECT * FROM kunden WHERE kundennr=?", (kundennr,)).fetchone()
        return dict(r) if r else None

    def zahlungsbedingungen(self, kundennr=None):
        """Skonto [%], Skontofrist und Zahlungsziel für ein neues Angebot: Werte des Kunden, fehlende aus den
        Einstellungen."""
        k = self.kunde(kundennr) or {}
        return {n: k[n] if k.get(n) is not None else self.einstellung(n) for n in ZAHLUNG}

    def kalkulation_vorgaben(self):
        """Kalkulationswerte für ein Angebot aus den Einstellungen (Prozentwerte in %)."""
        out = {}
        for f in KALKULATION:
            w = self.einstellung(f.name)
            if isinstance(w, (int, float)):
                out[f.name] = round(w * 100, 4) if f.name in KALK_PROZENT else w
        return out

    def lieferzeit_vorgabe(self, datum=None):
        """Lieferzeit für ein neues Angebot aus den Einstellungen; ein ungültiger Wert dort bleibt leer."""
        art = self.einstellung("lieferzeit_art") or None
        try:
            wert = lieferzeit_wert(art, self.einstellung("lieferzeit_wert"), datum)
        except ValueError:
            wert = None
        return dict(lieferzeit_art=art, lieferzeit_wert=wert,
                    lieferzeit_zusatz=(self.einstellung("lieferzeit_zusatz") or "").strip() or None)

    def kalkulation_zuruecksetzen(self, angebot_id):
        """Kalkulationswerte, Stundensätze und Zeitvorgaben des Angebots wieder auf die Einstellungen setzen."""
        for n, w in self.kalkulation_vorgaben().items():
            self.angebot_aendern(angebot_id, n, w)
        self.zeitbasis_speichern(angebot_id, self.zeitbasis_vorgabe(self.angebot(angebot_id).get("maschine")))

    def kunde_uebernehmen(self, angebot_id, kundennr):
        """Kundennummer ins Angebot; steht sie im Kundenstamm, auch Name und Zahlungsbedingungen.
        Ergebnis: Kundenzeile oder None."""
        k = self.kunde(kundennr)
        self.angebot_aendern(angebot_id, "kundennr", kundennr)
        if k:
            self.angebot_aendern(angebot_id, "kunde", k["name"])
            for n, w in self.zahlungsbedingungen(kundennr).items():
                self.angebot_aendern(angebot_id, n, w)
        return k

    # -------------------------------------------------------------- Angebote
    def angebote(self, suche=""):
        """Übersicht: Kopf, Anzahl Positionen und Teile, Zeitpunkt der Optimierung."""
        sql = ("SELECT a.id, a.nummer, a.kundennr, a.kunde, a.datum, a.maschine, a.geaendert, a.optimiert_am, "
               "a.nachkalkulation IS NOT NULL AS nachkalkuliert, "
               "COUNT(p.id) AS positionen, COALESCE(SUM(p.stueck), 0) AS teile FROM angebote a "
               "LEFT JOIN positionen p ON p.angebot_id = a.id")
        werte = []
        if suche:
            sql += (" WHERE a.nummer LIKE ? OR a.kunde LIKE ? OR a.kundennr LIKE ? OR a.bemerkung LIKE ? "
                    "OR a.id IN (SELECT angebot_id FROM positionen WHERE artikel LIKE ? OR bezeichnung LIKE ?)")
            werte = [f"%{suche}%"] * 6
        sql += " GROUP BY a.id ORDER BY a.datum DESC, a.id DESC"
        return [dict(r) for r in self.con.execute(sql, werte)]

    def angebot(self, angebot_id):
        r = self.con.execute("SELECT * FROM angebote WHERE id=?", (angebot_id,)).fetchone()
        if r is None:
            return None
        a = dict(r)
        a["ergebnis"] = json.loads(a["ergebnis"]) if a["ergebnis"] else None
        a["staffelpreise"] = json.loads(a["staffelpreise"]) if a.get("staffelpreise") else None
        a["nachkalkulation"] = json.loads(a["nachkalkulation"]) if a.get("nachkalkulation") else None
        a["zeitbasis"] = json.loads(a["zeitbasis"]) if a.get("zeitbasis") else None
        a["preisbasis"] = json.loads(a["preisbasis"]) if a.get("preisbasis") else None
        a["laengenwahl"] = json.loads(a["laengenwahl"]) if a.get("laengenwahl") else None
        return a

    def _jetzt(self):
        return datetime.datetime.now().isoformat(timespec="seconds")

    def angebot_neu(self, kopf=None):
        """Neues Angebot mit Vorgaben aus den Einstellungen; die Nummer zählt die letzte hoch."""
        kopf = dict(kopf or {})
        if not kopf.get("nummer"):
            nr = naechste_nummer(self.einstellung("letzte_angebotsnummer"))
            while self.con.execute("SELECT 1 FROM angebote WHERE nummer=?", (nr,)).fetchone():
                nr = naechste_nummer(nr)
            kopf["nummer"] = nr
        kopf.setdefault("datum", datetime.date.today().isoformat())
        kopf.setdefault("maschine", self.einstellung("standard_maschine"))
        kopf.setdefault("stange", self.einstellung("standard_stange"))
        k = self.kunde(kopf.get("kundennr"))
        if k and not kopf.get("kunde"):
            kopf["kunde"] = k["name"]
        for n, w in self.zahlungsbedingungen(kopf.get("kundennr")).items():
            kopf.setdefault(n, w)
        for n, w in self.kalkulation_vorgaben().items():
            kopf.setdefault(n, w)
        for n, w in self.lieferzeit_vorgabe(kopf.get("datum")).items():
            kopf.setdefault(n, w)
        kopf.setdefault("fracht_umlage", UMLAGE_NEU)     # neue Angebote: nach Gewicht; Kopien behalten ihren Wert
        namen = [f.name for f in KOPF if f.name in kopf]
        zb = kopf.get("zeitbasis") or self.zeitbasis_vorgabe(kopf.get("maschine"))     # Snapshot beim Anlegen
        try:
            with self.con:
                i = self.con.execute(
                    f'INSERT INTO angebote ({", ".join(namen)}, zeitbasis, angelegt, geaendert) VALUES '
                    f'({", ".join("?" * len(namen))}, ?, ?, ?)',
                    [kopf[n] for n in namen] + [json.dumps(zb, ensure_ascii=False)] + [self._jetzt()] * 2).lastrowid
                self._einstellung_schreiben("letzte_angebotsnummer", kopf["nummer"])
        except sqlite3.IntegrityError:
            raise ValueError(f"Angebotsnummer '{kopf['nummer']}' gibt es schon.")
        return i

    def angebot_aendern(self, angebot_id, feld, wert):
        if feld not in {f.name for f in KOPF}:
            raise KeyError(feld)
        if feld == "nummer" and not wert:
            raise ValueError("Die Angebotsnummer darf nicht leer sein.")
        if feld in ("lieferzeit_art", "lieferzeit_wert"):     # Wert passend zur Art prüfen (ValueError mit Meldung)
            a = self.con.execute("SELECT lieferzeit_art, lieferzeit_wert, datum FROM angebote WHERE id=?",
                                 (angebot_id,)).fetchone()
            if feld == "lieferzeit_wert":
                wert = lieferzeit_wert(a["lieferzeit_art"], wert, a["datum"])
            else:
                try:                                       # andere Art: alter Wert nur, wenn er weiter passt
                    neu = lieferzeit_wert(wert, a["lieferzeit_wert"], a["datum"])
                except ValueError:
                    neu = None
                with self.con:
                    self.con.execute("UPDATE angebote SET lieferzeit_wert=? WHERE id=?", (neu, angebot_id))
        try:
            with self.con:
                self.con.execute(f'UPDATE angebote SET "{feld}"=?, geaendert=? WHERE id=?',
                                 (wert, self._jetzt(), angebot_id))
                if feld == "maschine":          # andere Maschine: deren Stundensatz, Rüstzeit, Stangenwechsel
                    zb = self.con.execute("SELECT zeitbasis FROM angebote WHERE id=?", (angebot_id,)).fetchone()[0]
                    if zb:
                        zb = json.loads(zb)
                        zb["maschine"] = self.zeitbasis_vorgabe(wert)["maschine"]
                        self.con.execute("UPDATE angebote SET zeitbasis=? WHERE id=?",
                                         (json.dumps(zb, ensure_ascii=False), angebot_id))
        except sqlite3.IntegrityError:
            raise ValueError(f"Angebotsnummer '{wert}' gibt es schon.")

    def angebot_kopieren(self, angebot_id, kundennr=None):
        """Kopie mit neuer Nummer und heutigem Datum. kundennr: anderer Kunde (Name und Zahlungsbedingungen
        aus dem Kundenstamm, sonst bleibt nur die Nummer); None = gleicher Kunde."""
        a = self.angebot(angebot_id)
        kopf = {f.name: a[f.name] for f in KOPF if f.name != "nummer"}
        kopf["datum"] = datetime.date.today().isoformat()
        kopf["zeitbasis"] = a.get("zeitbasis")      # gleiche Stundensätze; ältere Angebote: aktuelle Vorgaben
        if kundennr is not None and kundennr != a.get("kundennr"):
            k = self.kunde(kundennr)
            kopf["kundennr"] = kundennr or None
            kopf["kunde"] = k["name"] if k else None
            kopf.update(self.zahlungsbedingungen(kundennr))
        neu = self.angebot_neu(kopf)
        if a.get("laengenwahl"):                    # übernommene Lieferlängen gelten auch für die Kopie
            self.laengenwahl_speichern(neu, a["laengenwahl"])
        netze = self.netze(angebot_id)
        for p in self.positionen(angebot_id):
            i = self.position_neu(neu, p)
            if p["id"] in netze:
                self.netz_speichern(i, netze[p["id"]])
        for st in self.staffeln(angebot_id):
            self.staffel_neu(neu, st)
        return neu

    def angebot_loeschen(self, angebot_id):
        with self.con:
            self.con.execute("DELETE FROM angebote WHERE id=?", (angebot_id,))

    def ergebnis_speichern(self, angebot_id, ergebnis):
        with self.con:
            self.con.execute("UPDATE angebote SET ergebnis=?, optimiert_am=? WHERE id=?",
                             (json.dumps(ergebnis, ensure_ascii=False) if ergebnis else None,
                              self._jetzt() if ergebnis else None, angebot_id))

    def staffelpreise_speichern(self, angebot_id, staffelpreise):
        """staffelpreise: {'zeilen': [...], 'kennung': str, 'am': Zeitpunkt} oder None"""
        with self.con:
            self.con.execute("UPDATE angebote SET staffelpreise=? WHERE id=?",
                             (json.dumps(staffelpreise, ensure_ascii=False) if staffelpreise else None, angebot_id))

    def nachkalkulation_speichern(self, angebot_id, ist):
        """Ist-Werte der Nachkalkulation (siehe nachkalkulation.py) oder None."""
        with self.con:
            self.con.execute("UPDATE angebote SET nachkalkulation=? WHERE id=?",
                             (json.dumps(ist, ensure_ascii=False) if ist else None, angebot_id))

    # -------------------------------------------------------------- Staffeln (Mengenstufen)
    def staffeln(self, angebot_id):
        return [dict(r) for r in self.con.execute("SELECT * FROM staffeln WHERE angebot_id=? ORDER BY nr, id",
                                                  (angebot_id,))]

    def staffel_neu(self, angebot_id, werte=None):
        werte = werte or {}
        nr = self.con.execute("SELECT COALESCE(MAX(nr), 0) + 1 FROM staffeln WHERE angebot_id=?",
                              (angebot_id,)).fetchone()[0]
        namen = [f.name for f in STUFE_FELDER]
        with self.con:
            return self.con.execute(f'INSERT INTO staffeln (angebot_id, nr, {", ".join(chr(34) + n + chr(34) for n in namen)}) '
                                    f'VALUES (?, ?, {", ".join("?" * len(namen))})',
                                    [angebot_id, nr] + [werte.get(n) for n in namen]).lastrowid

    def staffel_aendern(self, staffel_id, feld, wert):
        if feld not in {f.name for f in STUFE_FELDER}:
            raise KeyError(feld)
        with self.con:
            self.con.execute(f'UPDATE staffeln SET "{feld}"=? WHERE id=?', (wert, staffel_id))

    def staffeln_loeschen(self, ids):
        with self.con:
            self.con.executemany("DELETE FROM staffeln WHERE id=?", [(i,) for i in ids])

    def positionen(self, angebot_id):
        return [dict(r) for r in self.con.execute("SELECT * FROM positionen WHERE angebot_id=? ORDER BY nr, id",
                                                  (angebot_id,))]

    def position_neu(self, angebot_id, werte=None):
        werte = {f.name: (werte or {}).get(f.name) for f in POSITIONEN.felder if (werte or {}).get(f.name) is not None}
        if "material_herkunft" not in werte:      # Vorgabe des Angebots (Material neuer Positionen)
            r = self.con.execute("SELECT material_vorgabe FROM angebote WHERE id=?", (angebot_id,)).fetchone()
            if r and r[0] == KUNDENMATERIAL and werte.get("art") != ZUKAUFTEIL:
                werte["material_herkunft"] = KUNDENMATERIAL
        nr = self.con.execute("SELECT COALESCE(MAX(nr), 0) + 1 FROM positionen WHERE angebot_id=?",
                              (angebot_id,)).fetchone()[0]
        namen = ["angebot_id", "nr"] + list(werte)
        with self.con:
            i = self.con.execute(f'INSERT INTO positionen ({", ".join(chr(34) + n + chr(34) for n in namen)}) '
                                 f'VALUES ({", ".join("?" * len(namen))})', [angebot_id, nr] + list(werte.values())).lastrowid
            self.con.execute("UPDATE angebote SET geaendert=? WHERE id=?", (self._jetzt(), angebot_id))
        return i

    def position_aendern(self, position_id, feld, wert):
        POSITIONEN.feld(feld)
        with self.con:
            self.con.execute(f'UPDATE positionen SET "{feld}"=? WHERE id=?', (wert, position_id))
            self.con.execute("UPDATE angebote SET geaendert=? WHERE id=(SELECT angebot_id FROM positionen WHERE id=?)",
                             (self._jetzt(), position_id))

    def positionen_loeschen(self, ids):
        with self.con:
            self.con.executemany("DELETE FROM positionen WHERE id=?", [(i,) for i in ids])

    # -------------------------------------------------------------- 3D-Netze (STEP-Import)
    def netz_speichern(self, position_id, daten):
        """Dreiecksnetz einer Position (zlib-komprimiertes JSON, siehe ansicht3d.packen)."""
        with self.con:
            self.con.execute("INSERT OR REPLACE INTO netze (position_id, daten) VALUES (?, ?)", (position_id, daten))

    def netz(self, position_id):
        r = self.con.execute("SELECT daten FROM netze WHERE position_id=?", (position_id,)).fetchone()
        return bytes(r[0]) if r else None

    def netz_ids(self, angebot_id):
        """Positions-IDs eines Angebots, für die es ein 3D-Netz gibt."""
        return {r[0] for r in self.con.execute("SELECT n.position_id FROM netze n JOIN positionen p ON "
                                                "p.id = n.position_id WHERE p.angebot_id=?", (angebot_id,))}

    def netze(self, angebot_id):
        """{Positions-ID: Netz-Bytes} aller Positionen eines Angebots mit 3D-Daten."""
        return {r[0]: bytes(r[1]) for r in self.con.execute(
            "SELECT n.position_id, n.daten FROM netze n JOIN positionen p ON p.id = n.position_id "
            "WHERE p.angebot_id=?", (angebot_id,))}

    def protokoll(self, angebot_id):
        return [json.loads(r[0]) for r in self.con.execute(
            "SELECT zeile FROM step_protokoll WHERE angebot_id=? ORDER BY id", (angebot_id,))]

    def protokoll_anhaengen(self, angebot_id, zeilen):
        with self.con:
            self.con.executemany("INSERT INTO step_protokoll (angebot_id, zeile) VALUES (?, ?)",
                                 [(angebot_id, json.dumps(z, default=str, ensure_ascii=False)) for z in zeilen])

    # -------------------------------------------------------------- Zeichnungsablage (0.6.10 bis 0.6.23) entfernen
    def zeichnungen_entfernen(self, ablage):
        """Einmalig (Marke 'zeichnungen_entfernt'): die mit der früheren Zeichnungsablage in den Ordner des Angebots
        (<Ablage>/<Angebotsnummer>) kopierten Dateien löschen und positionen.dokumente leeren. Gelöscht werden nur
        die dort eingetragenen Dateinamen, der Ordner nur, wenn er danach leer ist. Ergebnis: Anzahl gelöschter Dateien."""
        from .ausgabe import dateiname
        if self.einstellung("zeichnungen_entfernt"):
            return 0
        spalten = {r[1] for r in self.con.execute("PRAGMA table_info(positionen)")}
        geloescht = 0
        if "dokumente" in spalten:
            treffer = self.con.execute(
                "SELECT p.id, p.dokumente, a.nummer FROM positionen p JOIN angebote a ON a.id = p.angebot_id "
                "WHERE p.dokumente IS NOT NULL AND p.dokumente <> ''").fetchall()
            ordner = set()
            for _, text, nummer in treffer:
                try:
                    namen = json.loads(text)
                except (TypeError, ValueError):
                    namen = []
                o = Path(ablage) / dateiname(dict(nummer=nummer))
                for n in namen if isinstance(namen, list) else []:
                    if not n or Path(str(n)).name != str(n):        # nur einfache Dateinamen im Ordner des Angebots
                        continue
                    datei = o / str(n)
                    try:
                        if datei.is_file():
                            datei.unlink()
                            geloescht += 1
                    except OSError:
                        pass
                ordner.add(o)
            for o in ordner:
                with contextlib.suppress(OSError):
                    if o.is_dir() and not any(o.iterdir()):
                        o.rmdir()
            with self.con:
                self.con.execute("UPDATE positionen SET dokumente = NULL")
        self.einstellung_setzen("zeichnungen_entfernt", datetime.date.today().isoformat())
        return geloescht

    # -------------------------------------------------------------- Stand eines Angebots (Rückgängig/Wiederholen)
    def angebot_stand(self, angebot_id):
        """Alles, was zu einem Angebot gehört, als Werte (Kopf, Positionen, Staffeln, STEP-Protokoll) plus
        {Positions-ID: Länge} der 3D-Netze. Die Netze selbst holt verlauf.Verlauf nur bei Bedarf. None = gelöscht."""
        a = self.con.execute("SELECT * FROM angebote WHERE id=?", (angebot_id,)).fetchone()
        if a is None:
            return None
        def zeilen(sql):
            return tuple(tuple(r) for r in self.con.execute(sql, (angebot_id,)))
        return dict(
            angebot=tuple((k, a[k]) for k in a.keys() if k not in ("id", "geaendert")),
            positionen=zeilen("SELECT * FROM positionen WHERE angebot_id=? ORDER BY id"),
            staffeln=zeilen("SELECT * FROM staffeln WHERE angebot_id=? ORDER BY id"),
            protokoll=zeilen("SELECT * FROM step_protokoll WHERE angebot_id=? ORDER BY id"),
            netze=dict(zeilen("SELECT n.position_id, length(n.daten) FROM netze n JOIN positionen p ON "
                              "p.id = n.position_id WHERE p.angebot_id=?")))

    def angebot_stand_setzen(self, angebot_id, stand, netze):
        """Angebot auf einen mit angebot_stand gelesenen Stand zurücksetzen (eine Transaktion). netze:
        {Positions-ID: Netz-Bytes} für alle Netze des Stands."""
        spalten = {t: [r[1] for r in self.con.execute(f"PRAGMA table_info({t})")]
                   for t in ("positionen", "staffeln", "step_protokoll")}
        def einsetzen(tabelle, zeilen):
            namen = ", ".join(f'"{n}"' for n in spalten[tabelle])
            self.con.executemany(f'INSERT INTO {tabelle} ({namen}) VALUES ({", ".join("?" * len(spalten[tabelle]))})',
                                 zeilen)
        with self.con:
            werte = dict(stand["angebot"])
            self.con.execute(f'UPDATE angebote SET {", ".join(chr(34) + n + chr(34) + "=?" for n in werte)}, '
                             'geaendert=? WHERE id=?', list(werte.values()) + [self._jetzt(), angebot_id])
            ids = {z[0] for z in stand["positionen"]}
            weg = [r[0] for r in self.con.execute("SELECT id FROM positionen WHERE angebot_id=?", (angebot_id,))
                   if r[0] not in ids]
            self.con.executemany("DELETE FROM positionen WHERE id=?", [(i,) for i in weg])
            namen = spalten["positionen"]
            for z in stand["positionen"]:          # vorhandene ändern (ihre 3D-Netze bleiben), fehlende anlegen
                if self.con.execute("SELECT 1 FROM positionen WHERE id=?", (z[0],)).fetchone():
                    self.con.execute(f'UPDATE positionen SET {", ".join(chr(34) + n + chr(34) + "=?" for n in namen[1:])} '
                                     'WHERE id=?', list(z[1:]) + [z[0]])
                else:
                    einsetzen("positionen", [z])
            for pid in ids:
                if pid in netze:
                    alt = self.con.execute("SELECT length(daten) FROM netze WHERE position_id=?", (pid,)).fetchone()
                    if alt is None or alt[0] != len(netze[pid]):
                        self.con.execute("INSERT OR REPLACE INTO netze (position_id, daten) VALUES (?, ?)",
                                         (pid, netze[pid]))
                else:
                    self.con.execute("DELETE FROM netze WHERE position_id=?", (pid,))
            for tabelle, schl in (("staffeln", "staffeln"), ("step_protokoll", "protokoll")):
                self.con.execute(f"DELETE FROM {tabelle} WHERE angebot_id=?", (angebot_id,))
                einsetzen(tabelle, stand[schl])

    def profile_anlegen(self, profile):
        """Profile aus Optimierung (Name) oder STEP-Import anlegen, vorhandene IDs bleiben unverändert."""
        for p in profile:
            if not self.con.execute("SELECT 1 FROM profile WHERE profil_id=?", (p["profil_id"],)).fetchone():
                self.neu("profile", {k: v for k, v in p.items() if k in {f.name for f in TABELLE["profile"].felder}})

    # -------------------------------------------------------------- Einstellungen
    def einstellung(self, name):
        r = self.con.execute("SELECT wert FROM einstellungen WHERE name=?", (name,)).fetchone()
        if r is None:
            e = EINSTELLUNG.get(name)
            return e.vorgabe if e else None
        return json.loads(r[0])

    def einstellung_setzen(self, name, wert):
        with self.con:
            self._einstellung_schreiben(name, wert)

    def _einstellung_schreiben(self, name, wert):
        self.con.execute("INSERT OR REPLACE INTO einstellungen (name, wert) VALUES (?, ?)",
                         (name, json.dumps(wert, ensure_ascii=False)))

    def einstellungen(self):
        return {e.name: self.einstellung(e.name) for e in EINSTELLUNGEN}

    # -------------------------------------------------------------- Sicherung
    def sicherung(self, ordner=None, behalten=SICHERUNGEN_BEHALTEN, zusatz=None):
        """Kopie der Datendatei nach Daten/Sicherung (sqlite-Backup, auch bei offener Datei sicher), danach geprüft
        (Integrität, gleiche Anzahl Angebote und Positionen wie das Original) und mit einer Beschreibung
        <name>.json daneben (Version, Schema, Zeit, Anzahlen, Prüfsumme). Scheitert die Prüfung, wird die Kopie
        gelöscht und SicherungFehler (ein OSError) ausgelöst.
        zusatz: 'beenden' u. ä. = eine Datei je Tag, die überschrieben wird; 'vor_…' (vor_update, vor_Schema_N,
        vor_Wiederherstellung) = geschützte Sicherung mit Uhrzeit, wird nie überschrieben.
        Aufräumen: von den laufenden Sicherungen bleiben `behalten`, von jeder Art geschützter Sicherungen
        GESCHUETZT_BEHALTEN; die Datendatei selbst wird nie gelöscht. Ergebnis: Pfad der Sicherung."""
        ordner = Path(ordner) if ordner else self.pfad.parent / "Sicherung"
        ordner.mkdir(parents=True, exist_ok=True)
        jetzt = datetime.datetime.now()
        if zusatz and not zusatz.startswith("vor_"):
            ziel = ordner / f"{self.pfad.stem}_{jetzt:%Y-%m-%d}_{zusatz}.db"
            _sicherung_loeschen(ziel)
        else:
            name = f"{self.pfad.stem}_{jetzt:%Y-%m-%d_%H%M%S}" + (f"_{zusatz}" if zusatz else "")
            ziel, n = ordner / f"{name}.db", 1
            while ziel.exists():
                ziel = ordner / f"{name}_{n}.db"
                n += 1
        kopie = sqlite3.connect(ziel)
        try:
            with kopie:
                self.con.backup(kopie)
        finally:
            kopie.close()
        soll = _anzahlen(self.con)
        try:
            info = datei_pruefen(ziel)
            if info["anzahl"] != soll:
                raise SicherungFehler(f"Die Sicherung {ziel} ist unvollständig: {info['anzahl']} statt {soll}")
        except SicherungFehler:
            _sicherung_loeschen(ziel)
            raise
        info.update(art=zusatz or "", erstellt=jetzt.isoformat(timespec="seconds"), quelle=str(self.pfad))
        ziel.with_suffix(".json").write_text(json.dumps(info, indent=1, ensure_ascii=False), encoding="utf-8")
        # nach Zeit (mehrere Sicherungen in einer Sekunde heißen _1, _2 … _10 und sortieren nach Namen falsch)
        alle = sorted(ordner.glob(f"{self.pfad.stem}_*.db"), key=lambda p: (p.stat().st_mtime_ns, p.name))
        laufend = [p for p in alle if _geschuetzt(p) is None]
        weg = laufend[:max(0, len(laufend) - behalten)]
        for art in {_geschuetzt(p) for p in alle} - {None}:
            gleich = [p for p in alle if _geschuetzt(p) == art]
            weg += gleich[:max(0, len(gleich) - GESCHUETZT_BEHALTEN)]
        for p in weg:
            if p != ziel:
                _sicherung_loeschen(p)
        return ziel

    def sicherung_heute(self, ordner=None):
        """Beim Start: eine Sicherung je Tag."""
        ordner = Path(ordner) if ordner else self.pfad.parent / "Sicherung"
        if any(ordner.glob(f"{self.pfad.stem}_{datetime.date.today():%Y-%m-%d}_*.db")):
            return None
        return self.sicherung(ordner)

    def sicherungen(self, zusatz=None):
        """Sicherung nach Daten/Sicherung und, falls eingestellt, in den zweiten Sicherungsordner.
        Ergebnis: (Pfade, Fehlertext oder None) – ein nicht erreichbarer zweiter Ordner (Netzlaufwerk,
        USB-Stick fehlt) verhindert die erste Sicherung nicht."""
        pfade = [self.sicherung(zusatz=zusatz)]
        ordner2 = (self.einstellung("sicherung_ordner2") or "").strip()
        if not ordner2:
            return pfade, None
        try:
            pfade.append(self.sicherung(ordner2, zusatz=zusatz))
        except OSError as e:
            return pfade, f"Zweiter Sicherungsordner nicht erreichbar ({ordner2}): {e}"
        return pfade, None

    def sicherungsordner(self):
        """Ordner mit Sicherungen: Daten/Sicherung und, falls eingestellt und vorhanden, der zweite Ordner."""
        ordner = [self.pfad.parent / "Sicherung"]
        ordner2 = (self.einstellung("sicherung_ordner2") or "").strip()
        if ordner2 and Path(ordner2).is_dir():
            ordner.append(Path(ordner2))
        return ordner

    def wiederherstellen(self, quelle, zusatz="vor_Wiederherstellung"):
        """Datendatei durch eine Sicherung, eine Datendatei oder eine Export-Datei (.zip) ersetzen. Vorher wird die
        Quelle geprüft (Integrität, nicht von einer neueren Programmversion) und der jetzige Stand gesichert
        (Sicherung mit `zusatz`, geschützt). Der Inhalt wird in die offene Datei kopiert, danach werden ältere
        Schemas wie beim Öffnen erweitert. Ergebnis: (Beschreibung der Quelle, Pfad der Sicherung des alten Stands)."""
        with _quelle_entpacken(quelle) as datei:
            info = datei_pruefen(datei)
            if info["schema"] > SCHEMA_VERSION:
                raise SicherungFehler(f"{Path(quelle).name} stammt von einer neueren Programmversion (Schema "
                                      f"{info['schema']}, dieses Programm kennt {SCHEMA_VERSION}). Bitte zuerst das "
                                      "Programm aktualisieren.")
            vorher = self.sicherung(zusatz=zusatz)
            quelle_con = _nur_lesen(datei)
            try:
                quelle_con.backup(self.con)
            finally:
                quelle_con.close()
        self._anlegen()
        return info, vorher

    def exportieren(self, ziel):
        """Alle Daten in eine Export-Datei (ZIP mit rohrlaser.db und info.json: Version, Schema, Anzahlen, Prüfsumme)
        zum Umziehen zwischen portabler und installierter Version oder auf einen anderen Rechner. Ergebnis: info."""
        ziel = Path(ziel)
        ziel.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory() as tmp:
            kopie_pfad = Path(tmp) / "rohrlaser.db"
            kopie = sqlite3.connect(kopie_pfad)
            try:
                with kopie:
                    self.con.backup(kopie)
            finally:
                kopie.close()
            info = datei_pruefen(kopie_pfad)
            info.update(art="Export", erstellt=datetime.datetime.now().isoformat(timespec="seconds"),
                        quelle=str(self.pfad))
            neu = ziel.with_name(ziel.name + ".neu")
            with zipfile.ZipFile(neu, "w", zipfile.ZIP_DEFLATED) as z:
                z.write(kopie_pfad, EXPORT_DATEI)
                z.writestr(EXPORT_INFO, json.dumps(info, indent=1, ensure_ascii=False))
            os.replace(neu, ziel)
        return info


GESCHUETZT_BEHALTEN = 10       # je Art geschützter Sicherungen (vor_update, vor_Schema, vor_Wiederherstellung …)
EXPORT_DATEI = "rohrlaser.db"
EXPORT_INFO = "info.json"


class SicherungFehler(OSError):
    pass


def _geschuetzt(pfad):
    """Art einer geschützten Sicherung ('update', 'Schema', 'Wiederherstellung', 'Import') oder None."""
    name = Path(pfad).stem
    if "_vor_" not in name:
        return None
    art = name.split("_vor_", 1)[1]
    return re.sub(r"(_\d+)+$", "", art)


def _nur_lesen(pfad):
    """Datei zum Lesen öffnen (nur SELECT/PRAGMA). Ohne URI-Modus, damit auch UNC-Pfade und Sonderzeichen gehen;
    eine fehlende Datei wird nicht angelegt."""
    if not Path(pfad).is_file():
        raise SicherungFehler(f"{pfad} gibt es nicht.")
    return sqlite3.connect(Path(pfad))


def _sicherung_loeschen(pfad):
    Path(pfad).unlink(missing_ok=True)
    Path(pfad).with_suffix(".json").unlink(missing_ok=True)


def _anzahlen(con):
    """Anzahl Zeilen der wichtigsten Tabellen (Angebote heißen in Dateien vor Schema 6 noch 'auftraege')."""
    tabellen = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    anzahl = {}
    for t in ("angebote", "auftraege", "positionen", "kunden", "preise"):
        if t in tabellen:
            anzahl["angebote" if t == "auftraege" else t] = con.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
    return anzahl


def datei_info(pfad):
    """Version und Inhalt einer Datendatei oder Sicherung, ohne sie zu verändern (für Listen; ohne Prüfung)."""
    con = _nur_lesen(pfad)
    try:
        schema = con.execute("PRAGMA user_version").fetchone()[0]
        tabellen = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        anzahl = _anzahlen(con)
        letzte = None
        if "angebote" in tabellen:
            letzte = con.execute("SELECT MAX(geaendert) FROM angebote").fetchone()[0]
    finally:
        con.close()
    return dict(schema=schema, anzahl=anzahl, letzte_aenderung=letzte, groesse=Path(pfad).stat().st_size)


def datei_pruefen(pfad):
    """Prüft eine Datendatei oder Sicherung (lesbar, Integrität, Tabellen des Programms). Ergebnis: info wie
    datei_info, dazu Programmversion und Prüfsumme; sonst SicherungFehler."""
    from . import VERSION
    pfad = Path(pfad)
    try:
        con = _nur_lesen(pfad)
        try:
            ergebnis = con.execute("PRAGMA integrity_check").fetchone()[0]
        finally:
            con.close()
        if ergebnis != "ok":
            raise SicherungFehler(f"{pfad.name} ist beschädigt: {ergebnis}")
        info = datei_info(pfad)
    except sqlite3.DatabaseError as e:
        raise SicherungFehler(f"{pfad.name} ist keine lesbare Datendatei: {e}") from e
    if "angebote" not in info["anzahl"] or "preise" not in info["anzahl"]:
        raise SicherungFehler(f"{pfad.name} ist keine Datendatei dieses Programms.")
    h = hashlib.sha256()
    with open(pfad, "rb") as f:
        for teil in iter(lambda: f.read(1 << 20), b""):
            h.update(teil)
    info.update(version=VERSION, sha256=h.hexdigest())
    return info


@contextlib.contextmanager
def _quelle_entpacken(quelle):
    """Pfad einer .db direkt; aus einer Export-Datei (.zip) die Datendatei in einen temporären Ordner, mit
    Vergleich der Prüfsumme aus info.json."""
    quelle = Path(quelle)
    if not zipfile.is_zipfile(quelle):
        yield quelle
        return
    with tempfile.TemporaryDirectory() as tmp:
        try:
            with zipfile.ZipFile(quelle) as z:
                info = json.loads(z.read(EXPORT_INFO).decode("utf-8"))
                z.extract(EXPORT_DATEI, tmp)
        except (KeyError, ValueError, zipfile.BadZipFile) as e:
            raise SicherungFehler(f"{quelle.name} ist keine Export-Datei dieses Programms: {e}") from e
        datei = Path(tmp) / EXPORT_DATEI
        if datei_pruefen(datei)["sha256"] != info.get("sha256"):
            raise SicherungFehler(f"{quelle.name}: Prüfsumme stimmt nicht, die Datei ist beschädigt.")
        yield datei


def datei_uebernehmen(quelle, ziel):
    """Ohne offene Datenbank (erster Start, Datendatei lässt sich nicht öffnen): Quelle (.db oder Export .zip)
    prüfen und als `ziel` ablegen. Eine vorhandene Zieldatei wird nicht gelöscht, sondern nach Sicherung/
    <name>_<Zeit>_vor_Uebernahme.db verschoben. Ergebnis: info der Quelle."""
    ziel = Path(ziel)
    with _quelle_entpacken(quelle) as datei:
        info = datei_pruefen(datei)
        if info["schema"] > SCHEMA_VERSION:
            raise SicherungFehler(f"{Path(quelle).name} stammt von einer neueren Programmversion (Schema "
                                  f"{info['schema']}). Bitte zuerst das Programm aktualisieren.")
        ziel.parent.mkdir(parents=True, exist_ok=True)
        neu = ziel.with_name(ziel.name + ".neu")
        shutil.copyfile(datei, neu)
        if ziel.exists():
            alt = ziel.parent / "Sicherung" / f"{ziel.stem}_{datetime.datetime.now():%Y-%m-%d_%H%M%S}_vor_Uebernahme.db"
            alt.parent.mkdir(parents=True, exist_ok=True)
            os.replace(ziel, alt)
        os.replace(neu, ziel)
    return info
