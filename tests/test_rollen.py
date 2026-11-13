"""Benutzer, Rollen und Rechte (Plan Auftragsworkflow 13.11.2026, Paket 6, rollen.py): ohne Rollen alles wie bisher,
Benutzer mit Rollen, Passwort und PIN, Anmeldung mit Sperre nach Fehlversuchen, Rechtetabelle (Vorgabe und
geändert), Seiten und Reiter je Recht, Rechteprüfung in Aufträgen, AV, QS und Auslieferung, Angebote nur sehen,
freigeschalteter Admin darf alles, Rollen gehen mit den Admin-Vorgaben an alle Plätze.

Aufruf: python tests/test_rollen.py
"""
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication, QPushButton  # noqa: E402

from rohrlaser import admin_schutz, auftraege as au, auftrag_av as av, auftrag_qs as qs, rollen  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402
from rohrlaser.lizenz_dialog import LESEMODUS_TIPP  # noqa: E402


def ok(t):
    print("OK:", t)


def fehler(f, text):
    try:
        f()
    except (au.AuftragFehler, rollen.RechteFehler) as ex:
        assert text in str(ex), ex
        return
    raise AssertionError(f"kein Fehler: {text}")


app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
db.einstellung_setzen("benutzer_kuerzel", "PB")
db.einstellung_setzen("benutzer_name", "Patrick")
db.einstellung_setzen("auftrag_nach_beauftragt", "nein")
f = Hauptfenster(db, tmp, stumm=True)
R = f.reiter


def sichtbar(w):
    return R.isTabVisible(R.indexOf(w))


def admin(an):
    """Hauptadmin freischalten (Seite Arbeitsplätze und Rechte) bzw. wieder sperren."""
    s = f.bereich.sitzung
    s.freischalten() if an else s.sperren()
    f.bereich.schutz_anwenden()
    f.rechte_anwenden()


# ------------------------------------------------------------------ R1 ohne Rollen: alles wie bisher
assert not rollen.aktiv(db) and not rollen.pflicht(db)
assert all(rollen.darf(db, b) for b, _ in rollen.BEREICHE)
assert sichtbar(f.angebote) and sichtbar(f.auftraege) and sichtbar(f.produktion) and not (not f.benutzer_info.isHidden())
assert not f.benutzer_anmelden("PB", "x")                    # Benutzerverwaltung aus: Hinweis
a = db.angebot_neu(dict(kunde="Becker GmbH (erfunden)", kundennr="10023", stange=6000, maschine="T03"))
db.position_neu(a, dict(pos=1, artikel="BG-100", bezeichnung="Holm", profil_id="RR 42,4x2,0",
                        werkstoff_id="S235-10219", laenge=1250, stueck=10, schneidweg=300, einstiche=2))
f.angebote.vorgang_setzen("Beauftragt", angebot_id=a, auftrag=("PO-1", "2026-11-27"))
uid = au.uebernehmen(db, [a])
ok("R1 ohne Rollen: jeder darf alles, keine Anmeldung, alle Seiten")

# ------------------------------------------------------------------ R2 Benutzer anlegen (Seite Arbeitsplätze und Rechte)
rt = f.plaetze_seite.rollen
assert admin_schutz.aktiv(db) and rt.gesperrt and not rt.anlegen(dict(kuerzel="PB", name="", rollen=[], passwort=None,
                                                                     pin=None))   # nur der Hauptadmin
admin(True)
assert rt.anlegen(dict(kuerzel="pb", name="Patrick", rollen=[rollen.KALKULATION, rollen.LEITUNG], passwort="geheim1",
                       pin=None))
assert rt.anlegen(dict(kuerzel="ws", name="Werner (Säge)", rollen=[rollen.WERKSTATT], passwort=None, pin="1234"))
assert rt.anlegen(dict(kuerzel="AV", name="Anna", rollen=[rollen.AV], passwort="planung1", pin=None))
assert not rt.anlegen(dict(kuerzel="XX", name="", rollen=[], passwort="kurz", pin=None))       # Passwort zu kurz
assert not rt.anlegen(dict(kuerzel="YY", name="", rollen=[], passwort=None, pin="12a4"))        # PIN nur Ziffern
b = rollen.benutzer(db)
assert b["PB"]["rollen"] == [rollen.KALKULATION, rollen.LEITUNG] and b["PB"]["hash"] and "geheim1" not in str(b)
assert b["WS"]["pin"] and not b["WS"].get("hash")
assert rollen.aktiv(db) and rollen.pflicht(db)
assert rt.waehlen("WS") and rt.tabelle.item(rt.tabelle.currentRow(), 3).text() == "PIN"
admin(False)
assert (not f.benutzer_info.isHidden()) and "Patrick" in f.benutzer_info.text() and "Kalkulation" in f.benutzer_info.text()
assert {"benutzer_rollen", "rollen_rechte", "anmeldung_pflicht"} <= admin_schutz.einstellungen_geschuetzt(db)
ok("R2 Benutzer mit Rollen, Passwort (Hash) und PIN; Regeln; gehen mit den Admin-Vorgaben an alle Plätze")

# ------------------------------------------------------------------ R3 Anmeldung und Sperre
f.rollen_sitzung.fehl = 0
assert not f.benutzer_anmelden("WS", "0000")
for _ in range(rollen.FEHL_FREI - 1):
    assert rollen.anmelden(db, "WS", "9999")
assert "warten" in rollen.anmelden(db, "WS", "1234")             # Sperre auch für das richtige Passwort
f.rollen_sitzung.gesperrt_bis = 0
assert f.benutzer_anmelden("ws", "1234") and rollen.angemeldet(db) == "WS"
assert f.anmeldung_beim_start()                                   # stumm: keine Abfrage
ok("R3 Anmeldung mit Kürzel und PIN, Sperre nach Fehlversuchen")

# ------------------------------------------------------------------ R4 Werkstatt: Seiten und Rechte
assert not sichtbar(f.angebote) and sichtbar(f.auftraege) and sichtbar(f.produktion) and not sichtbar(f.versand)
assert not sichtbar(f.kunden) and not sichtbar(f.anfragen_seite) and not sichtbar(f.materialanfragen)
f.fertigung_anwenden()                                            # Seiten-Schalter heben die Rechte nicht auf
assert not sichtbar(f.kunden) and sichtbar(f.fertigung) == f.fertigung_an()
f.auftrag_zeigen(uid)
S = f.auftraege
assert not S.reiter.isTabVisible(S.reiter.indexOf(S.av)) and not S.reiter.isTabVisible(S.reiter.indexOf(S.qs))
assert not S.knopf["bearbeiten"].isEnabled() and not S.knopf["status"].isEnabled()
assert not S.knopf["uebernehmen"].isEnabled() and not S.knopf["angebot"].isEnabled()   # Angebote nicht sehen
fehler(lambda: au.aendern(db, uid, "projekt", "Halle 4"), "Keine Berechtigung: Aufträge")
fehler(lambda: av.bestaetigen(db, uid, "zeichnungen", av.OK, "da"), "Keine Berechtigung: Arbeitsvorbereitung")
fehler(lambda: qs.fertigmelden(db, uid, "x"), "Keine Berechtigung: Qualitätskontrolle")
fehler(lambda: qs.liefern(db, uid, {}), "Keine Berechtigung: Auslieferung")
assert rollen.darf(db, rollen.B_PRODUKTION) and not rollen.darf(db, rollen.B_ANGEBOTE, rollen.SEHEN)
assert "Werner" in f.benutzer_info.text() and "Mitarbeiter Produktion" in f.benutzer_info.text()
# Rechtetabelle: Werkstatt darf die AV sehen -> Reiter da, ändern weiter nicht
admin(True)
assert rt.recht(rollen.WERKSTATT, rollen.B_AV, rollen.SEHEN)
assert not rt.recht(rollen.ADMIN, rollen.B_AV, rollen.SEHEN)    # Administrator darf immer alles
admin(False)
assert S.reiter.isTabVisible(S.reiter.indexOf(S.av))
fehler(lambda: av.bestaetigen(db, uid, "zeichnungen", av.OK, "da"), "Keine Berechtigung")
ok("R4 Mitarbeiter Produktion: nur Aufträge sehen und Produktion; Rechte im Kern geprüft; Rechtetabelle wirkt sofort")

# ------------------------------------------------------------------ R5 AV: Angebote nur sehen, AV bearbeiten
assert f.benutzer_anmelden("AV", "planung1")
assert sichtbar(f.angebote) and S.reiter.isTabVisible(S.reiter.indexOf(S.av))
f.auftrag_zeigen(uid)
assert sichtbar(f.kunden) and S.knopf["angebot"].isEnabled() and not S.knopf["uebernehmen"].isEnabled()
assert av.bestaetigen(db, uid, "zeichnungen", av.OK, "Zeichnung per Mail")
seite = f.angebot_oeffnen(a)
gesperrt = [k for k in seite.findChildren(QPushButton) if not k.isEnabled() and k.toolTip() == LESEMODUS_TIPP]
assert gesperrt, "Angebot nicht im Lesemodus"
f.angebot_schliessen(a)
fehler(lambda: qs.fertigmelden(db, uid, "x"), "Keine Berechtigung: Qualitätskontrolle")
ok("R5 Arbeitsvorbereitung: AV bearbeiten, Angebote nur sehen (Lesemodus)")

# ------------------------------------------------------------------ R6 gesperrt, ohne Rolle, Admin, Vorgabe
admin(True)
assert rt.waehlen("AV") and rt.sperren_umschalten()
admin(False)
assert "gesperrt" in rollen.anmelden(db, "AV", "planung1") and rollen.stufe(db, rollen.B_AV) == rollen.SEHEN
rollen.abmelden()
db.einstellung_setzen("benutzer_kuerzel", "NEU")                 # Platz ohne Rolle: nur sehen
assert rollen.stufe(db, rollen.B_AUFTRAEGE) == rollen.SEHEN
admin(True)                                                      # freigeschalteter Admin: alles
assert all(rollen.darf(db, b_) for b_, _ in rollen.BEREICHE)
admin(False)
assert not rollen.darf(db, rollen.B_AUFTRAEGE)
rollen.vorgabe_wiederherstellen(db)
assert rollen.rechte(db)[rollen.WERKSTATT][rollen.B_AV] == rollen.KEIN
db.einstellung_setzen("benutzer_kuerzel", "PB")
for k in ("PB", "WS", "AV"):
    assert rollen.entfernen(db, k) == ""
f.rechte_anwenden()
assert not rollen.aktiv(db) and sichtbar(f.angebote) and sichtbar(f.versand) and not (not f.benutzer_info.isHidden())
ok("R6 gesperrter Benutzer, Platz ohne Rolle nur sehen, freigeschalteter Admin darf alles, Vorgabe, alles entfernt "
   "= wie bisher")
print("test_rollen OK")
