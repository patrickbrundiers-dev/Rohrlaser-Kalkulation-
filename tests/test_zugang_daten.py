"""Zugangssystem Paket B (programm/rohrlaser/zugang_daten.py): Tabellen zg_*, Konten im neuen Format, Umrechnung
der alten Rollen, Sperre je Kürzel, Protokoll/Sitzungen in der Datenbank, Migration mit Sicherung. Fälle D1–D16.

Deckt aus dem Auftrag (Abschnitt 10) Test 1 (Migration: Benutzer übernommen, keine Rechte verloren oder dazu,
Sicherung, Bericht) und die Datenbankteile von Test 6/7 (Fehlversuche über Neustart, keine Geheimnisse in Tabellen).
Aufruf: python tests/test_zugang_daten.py (mit PostgreSQL wie die übrigen Datenbanktests)
"""
import itertools
import os
import sys
import tempfile
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WURZEL / "programm"))
sys.path.insert(0, str(WURZEL / "tests"))
os.environ["ROHRLASER_ARBEITSPLATZ"] = "PRUEFPLATZ"

import db_roh  # noqa: E402

from rohrlaser import admin_schutz, db_verbindung, rollen as R  # noqa: E402
from rohrlaser import zugang_authentifizierung as A  # noqa: E402
from rohrlaser import zugang_berechtigung as B  # noqa: E402
from rohrlaser import zugang_daten as D  # noqa: E402
from rohrlaser import zugang_protokoll as P  # noqa: E402
from rohrlaser.datenbank import SCHEMA_VERSION, Datenbank, datei_pruefen  # noqa: E402
from rohrlaser.zugang_sitzungen import Sitzungen  # noqa: E402

tmp = Path(tempfile.mkdtemp(prefix="zugang_daten_"))
fehler = []
PW = "Geheim-Passwort-4711"


def ok(name):
    print("ok", name)


def fall(name, f):
    try:
        f()
        ok(name)
    except Exception as e:          # noqa: BLE001
        import traceback
        traceback.print_exc()
        fehler.append(f"{name}: {e!r}")


db = Datenbank(tmp / "rohrlaser.db")


def d1():
    t = set(db_roh.tabellen(db.con))
    assert set(D.TABELLEN) <= t, set(D.TABELLEN) - t
    assert SCHEMA_VERSION >= D.SCHEMA
    m = D.migrationen(db)
    assert len(m) == 1 and m[0]["nach"] == D.SCHEMA and m[0]["von"] == 0 and m[0]["status"] == "fertig", m


fall("D1 neue Datei: Tabellen zg_* angelegt, Migration einmal eingetragen", d1)


def d2():
    tab = R.rechte(db)
    for n in range(0, 3):
        for kombi in itertools.combinations([r for r, _ in R.ROLLEN if r != R.ADMIN], n):
            neu = D.umrechnen(kombi, tab)
            stufen = {}
            for r in kombi:
                for b, st in tab[r].items():
                    if R._RANG[st] > R._RANG.get(stufen.get(b, ""), 0):
                        stufen[b] = st
            if not kombi:
                stufen = {b: R.SEHEN for b, _ in R.BEREICHE}
            soll = D.alte_rechte(stufen)
            ist = B.wirksame_rechte(neu["rollen"], neu["plus"], neu["minus"])
            assert ist == soll, (kombi, ist ^ soll)
            assert not set(neu["plus"]) & set(neu["minus"])
    assert D.umrechnen([R.KALKULATION], tab)["rollen"] == [B.KALK_PRO]
    assert D.umrechnen([R.WERKSTATT], tab)["rollen"] == [B.MITARBEITER]
    assert "produktion.bearbeiten" in D.umrechnen([R.WERKSTATT], tab)["plus"]
    assert "angebot.sehen" not in B.wirksame_rechte(**{k: v for k, v in D.umrechnen([R.WERKSTATT], tab).items()})
    assert D.umrechnen([], tab)["rollen"] == [B.NUR_LESEN]
    assert D.umrechnen([R.ADMIN], tab)["rollen"] == [B.ADMIN]


fall("D2 Umrechnung alt -> neu: jede Rollenkombination behält genau ihre Rechte (nichts weg, nichts dazu)", d2)


def d3():
    R.recht_setzen(db, R.WERKSTATT, R.B_ANGEBOTE, R.SEHEN)          # angepasste alte Rechtetabelle
    try:
        neu = D.umrechnen([R.WERKSTATT], R.rechte(db))
        r = B.wirksame_rechte(neu["rollen"], neu["plus"], neu["minus"])
        assert "angebot.sehen" in r and "angebot.bearbeiten" not in r
    finally:
        R.vorgabe_wiederherstellen(db)


fall("D3 angepasste alte Rechtetabelle wird mit übernommen", d3)


def _benutzer_alt():
    assert not R.benutzer_setzen(db, "MM", "Max Muster", [R.KALKULATION])
    assert not R.zugang_setzen(db, "MM", passwort=PW)
    assert not R.benutzer_setzen(db, "WS", "Werk Statt", [R.WERKSTATT])
    assert not R.zugang_setzen(db, "WS", pin="246813")
    assert not R.benutzer_setzen(db, "XX", "Ehemalig", [R.QS], aktiv_=False)


def d4():
    _benutzer_alt()
    k = D.konten(db)
    assert set(k) >= {"MM", "WS", "XX"}
    assert k["MM"]["rollen"] == [B.KALK_PRO] and k["MM"]["umgerechnet"] and k["MM"]["status"] == "aktiv"
    assert "auftrag.bearbeiten" in k["MM"]["plus"]
    assert A.pruefen(PW, k["MM"]["hash"])
    assert k["WS"]["pin"] and not k["WS"]["hash"]
    assert k["XX"]["status"] == "gesperrt"


fall("D4 Konten aus benutzer_rollen: Rollen umgerechnet, alter Passwort-Hash gilt, gesperrt bleibt gesperrt", d4)


def d5():
    liste = admin_schutz.admins(db)
    liste["AD"] = dict(name="Anna Admin", recht=admin_schutz.ADMIN)
    liste["GA"] = dict(name="Gesperrter Admin", recht=admin_schutz.GESPERRT)
    db.einstellung_setzen(admin_schutz.ADMINS, liste)
    assert not R.benutzer_setzen(db, "GA", "Gesperrter Admin", [R.AV])
    k = D.konten(db)
    assert k["AD"]["rollen"] == [B.ADMIN] and not k["AD"]["hash"]
    assert k["GA"]["rollen"] != [B.ADMIN]
    assert list(k).count("AD") == 1


fall("D5 Admins aus der Admin-Liste: gleiches Kürzel ein Konto, ohne übernommenes Admin-Passwort", d5)


def d6():
    vorher = R.benutzer(db)["MM"]["rollen"]
    assert not D.konto_speichern(db, "MM", plus=["stamm.material"], minus=[])
    e = R.benutzer(db)["MM"]
    assert e["rollen"] == vorher, "alte Rollen bleiben für ältere Programmversionen"
    k = D.konten(db)["MM"]
    assert not k["umgerechnet"] and k["plus"] == ["stamm.material"] and k["rollen"] == [B.KALK_PRO]
    assert R.darf(db, R.B_ANGEBOTE, R.BEARBEITEN, kuerzel="MM")       # altes System liest weiter
    assert not D.konto_speichern(db, "MM", status="gesperrt")
    assert D.konten(db)["MM"]["status"] == "gesperrt" and not R.benutzer(db)["MM"]["aktiv"]
    assert not D.konto_speichern(db, "MM", status="aktiv")
    assert D.konto_speichern(db, "MM", status="weg")
    assert D.konto_speichern(db, "NIEMAND", status="aktiv")


fall("D6 Konto im neuen Format speichern: Teil zg, alte Rollen bleiben, Status sperrt auch im alten System", d6)


def d7():
    uhr = [1000.0]
    s = D.Sperre(db, "MM", uhr=lambda: uhr[0])
    for _ in range(D.FEHL_FREI - 1):
        assert s.fehlschlag() == 0
    assert s.fehlschlag() == D.SPERRE_ERSTE_S
    s2 = D.Sperre(db, "MM", uhr=lambda: uhr[0])               # wie nach Neustart
    assert s2.wartezeit() == D.SPERRE_ERSTE_S and s2.fehlversuche() == D.FEHL_FREI
    assert s2.fehlschlag() == 2 * D.SPERRE_ERSTE_S
    uhr[0] += 10 ** 5
    assert s2.wartezeit() == 0
    s2.erfolg()
    assert s2.fehlversuche() == 0
    u = D.Sperre(db, "GIBTSNICHT", uhr=lambda: uhr[0])
    u.fehlschlag()
    assert u.fehlversuche() == 1


fall("D7 Sperre je Kürzel in zg_konto_stand: zählt über Neustart, verdoppelt, auch unbekannte Kürzel", d7)


def d8():
    ps = D.pruefstelle(db, tmp / "Protokoll")
    ko = D.konten(db)["MM"]
    falsch = ps.benutzer_anmelden(ko, "falsch-falsch", sperre=D.Sperre(db, "MM"))
    assert not falsch.ok
    e = ps.benutzer_anmelden(ko, PW, sperre=D.Sperre(db, "MM"))
    assert e.ok, e.text
    D.anmeldung_merken(db, "MM", ps.arbeitsplatz, e.totp_schritt)
    token = e.sitzung.token
    offen = D.sitzungen_lesen(db, offen=True)
    assert offen and offen[-1]["kuerzel"] == "MM" and offen[-1]["platz"] == "PRUEFPLATZ"
    roh = db.con.execute(f"SELECT token_sha FROM {D.SITZUNGEN}").fetchall()
    assert all(z[0] != token and len(z[0]) == 64 for z in roh)
    ps.abmelden()
    assert not D.sitzungen_lesen(db, offen=True)
    assert D.sitzungen_lesen(db)[-1]["grund"] == "beendet"
    v = D.versuche(db, "MM")
    assert [x["ergebnis"] for x in v[-2:]] == ["falsch", "ok"], v
    p = D.protokoll_lesen(db, aktion=P.ANMELDUNG_OK)
    assert p and p[-1]["benutzer"] == "MM" and p[-1]["arbeitsplatz"] == "PRUEFPLATZ"
    assert D.stand(db, "MM")["letzte"] and D.stand(db, "MM")["platz"] == "PRUEFPLATZ"
    inst = D.installation(db)
    assert inst["art"] == "lokal" and inst["umgebung"] == "produktiv" and len(inst["kennung"]) == 32


fall("D8 Prüfstelle der Datenbank: Sitzung nur als SHA-256, Abmelden beendet, Versuche und Protokoll in Tabellen", d8)


def d9():
    for t in D.TABELLEN:
        for z in db.con.execute(f"SELECT * FROM {t}"):
            text = " ".join(str(x) for x in z)
            assert PW not in text and "falsch-falsch" not in text and "246813" not in text, (t, text[:200])


fall("D9 keine Passwörter, PINs oder Tokens in den Tabellen zg_*", d9)


def d10():
    D.anmeldung_merken(db, "WS", "PRUEFPLATZ", 12345)
    assert D.konten(db)["WS"]["totp_zuletzt"] == 12345
    D.anmeldung_merken(db, "WS", "PRUEFPLATZ", -1)
    assert D.konten(db)["WS"]["totp_zuletzt"] == 12345, "ohne Einmalcode bleibt der letzte Schritt stehen"


fall("D10 benutzter Einmalcode je Konto gemerkt (gegen Wiederverwendung)", d10)


def d11():
    a = D.arbeitsplatz_melden(db, "PLATZ-A", version="0.9.553")
    assert a["neu"] and a["status"] == "aktiv"
    db.con.execute(f"UPDATE {D.ARBEITSPLAETZE} SET status='gesperrt' WHERE platz='PLATZ-A'")
    db.con.commit()
    b = D.arbeitsplatz_melden(db, "PLATZ-A", version="0.9.554")
    assert not b["neu"] and b["status"] == "gesperrt"
    z = [x for x in D.arbeitsplaetze(db) if x["platz"] == "PLATZ-A"][0]
    assert z["version"] == "0.9.554"


fall("D11 Arbeitsplatz melden: neu eingetragen, gesperrt bleibt gesperrt, Version aktuell", d11)


def d12():
    b = D.bericht(db)
    zeilen = {z["kuerzel"]: z for z in b["konten"]}
    assert zeilen["MM"]["alte_rollen"] == [R.KALKULATION]
    assert zeilen["AD"]["nur_admin_liste"]
    assert any("AD" in h for h in b["hinweise"])
    text = D.bericht_text(b)
    assert "MM (Max Muster)" in text and "Kalkulator Pro" in text and PW not in text


fall("D12 Bericht der Übernahme: alte -> neue Rollen, Hinweise ohne Passwort, ohne Geheimnisse", d12)


def d13():
    db.schliessen()
    con = db_roh.verbinden(tmp / "rohrlaser.db")
    for t in D.TABELLEN:
        con.execute(f"DROP TABLE {t}")
    db_verbindung.schema_version_setzen(con, D.SCHEMA - 1)
    con.commit()
    con.close()
    db2 = Datenbank(tmp / "rohrlaser.db")
    try:
        assert db_verbindung.schema_version(db2.con) == SCHEMA_VERSION
        m = D.migrationen(db2)
        assert len(m) == 1 and m[0]["von"] == D.SCHEMA - 1, m
        sich = Path(m[0]["sicherung"])
        assert sich.exists() and f"vor_Schema_{SCHEMA_VERSION}" in sich.name, sich
        info = datei_pruefen(sich)
        assert info["schema"] == D.SCHEMA - 1, info["schema"]
        k = {z["kuerzel"]: z for z in m[0]["bericht"]["konten"]}
        assert k["MM"]["neue_rollen"] == [B.KALK_PRO] and k["WS"]["neue_rollen"] == [B.MITARBEITER]
        assert "MM" in D.konten(db2) and R.benutzer(db2)["MM"]["rollen"] == [R.KALKULATION]
        assert db2.angebote() is not None
    finally:
        db2.schliessen()
    db3 = Datenbank(tmp / "rohrlaser.db")
    try:
        assert len(D.migrationen(db3)) == 1, "zweiter Start: keine zweite Migration"
    finally:
        db3.schliessen()


fall("D13 Update von Schema 108: geprüfte Sicherung vor_Schema_109, Bericht mit allen Konten, einmalig", d13)


def d14():
    db4 = Datenbank(tmp / "rohrlaser.db")
    try:
        sich = Path(D.migrationen(db4)[0]["sicherung"])
        info, vorher = db4.wiederherstellen(sich)
        assert info["schema"] == D.SCHEMA - 1 and Path(vorher).exists()
        assert "MM" in R.benutzer(db4), "Benutzer nach Rücksicherung da"
    finally:
        db4.schliessen()


fall("D14 Rückweg: die Sicherung vor der Umstellung lässt sich zurückspielen, Benutzer bleiben", d14)


def d15():
    s = Sitzungen(beobachter=lambda e, x: (_ for _ in ()).throw(RuntimeError("Ablage kaputt")))
    x = s.anlegen("u1", "U1")
    assert x.aktiv
    s.beenden()


fall("D15 Fehler beim Ablegen einer Sitzung bricht die Anmeldung nicht ab", d15)


def d16():
    class NurLesen:
        nur_lesen = "nur Lesen am Server"
        con = None
    assert D._ausfuehren(NurLesen(), "INSERT INTO x VALUES (1)") is False


fall("D16 im Lesemodus schreibt das Zugangssystem nichts (kein Fehler)", d16)

if fehler:
    print("FEHLER:", *fehler, sep="\n  ")
    sys.exit(1)
print("OK: Zugangssystem Paket B (Datenbank, Konten, Migration)")
