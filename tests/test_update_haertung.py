"""Online-Update gegen gefälschte oder kaputte Dateilisten und Pakete (Audit 24.10.2026, H1) und Absturz mitten im
Austausch (H2): Pfade nach Windows-Regeln, Prüfsummen nur als Hex, nur https von der erwarteten Adresse,
Größengrenzen, ZIP-Bombe, Paket-Prüfsumme, Speicherplatz, Journal.

Aufruf: python tests/test_update_haertung.py
"""
import hashlib
import io
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "programm"))
from rohrlaser import update  # noqa: E402


def ok(text):
    print("OK    ", text)


def fehler_erwartet(f, *a, text=None, **k):
    try:
        f(*a, **k)
    except update.UpdateFehler as e:
        assert text is None or text in str(e), e
        return
    raise AssertionError(f"UpdateFehler erwartet: {f.__name__}{a}")


tmp = Path(tempfile.mkdtemp(prefix="update_haertung_"))

# 1) Pfade nach Windows-Regeln
for rel in ("daten/rohrlaser.db", "DATEN/x", "Daten./x", "Daten /x", "update.json", "_UPDATE/x", "angebote/a.pdf",
            "portabel.ini", "../x", "a/../../x", "/x", "C:/x", "C:x", "a\\x", "//server/x", "a/CON", "a/nul.txt",
            "a/com1.dll", "a/LPT9", "a/b.", "a/b ", "a/datei.dll:stream", "a/da*ei", "a/\x01x", "", "a//b", 5, None):
    assert not update.sicherer_pfad(rel), rel
for rel in ("Rohrlaser-Angebotskalkulation.exe", "_internal/PySide6/Qt6Core.dll", "STEP-Import/_internal/OCP/AIS/__init__.py",
            "_internal/cryptography-50.0.1.dist-info/licenses/LICENSE", "Bedienungsanleitung.pdf", "a/console.dll",
            "a/auxiliar.txt", "_internal/Daten.dll"):
    assert update.sicherer_pfad(rel), rel
ok("Pfade: Groß-/Kleinschreibung, Punkt/Leerzeichen am Ende, Gerätenamen, Laufwerke, Datenströme abgelehnt")

# 2) Dateiliste: jeder Wert wird vor der Benutzung geprüft
sha = "a" * 64
paket = "p-" + "b" * 40 + ".zip"


def liste(**aenderung):
    d = dict(format=1, stand=5, dateien={"x.dll": dict(sha256=sha, groesse=10, paket=paket)},
             pakete={paket: dict(groesse=100)})
    d.update(aenderung)
    return d


update.liste_pruefen(liste())
update.liste_pruefen(liste(adresse=update.ERLAUBTE_ADRESSEN[0] + "update-dateien/"))
falsch = [liste(format=2), liste(dateien={}), liste(stand="5"), liste(stand=True),
          liste(dateien={"x.dll": dict(sha256="../../../x", groesse=10, paket=paket)}),
          liste(dateien={"x.dll": dict(sha256=sha.upper(), groesse=10, paket=paket)}),
          liste(dateien={"x.dll": dict(sha256=sha, groesse=-1, paket=paket)}),
          liste(dateien={"x.dll": dict(sha256=sha, groesse=True, paket=paket)}),
          liste(dateien={"x.dll": dict(sha256=sha, groesse=update.DATEI_MAX + 1, paket=paket)}),
          liste(dateien={"x.dll": dict(sha256=sha, groesse=10, paket="p-" + "c" * 40 + ".zip")}),    # Paket fehlt
          liste(dateien={"x.dll": dict(sha256=sha, groesse=10, paket=paket),
                         "X.DLL": dict(sha256=sha, groesse=10, paket=paket)}),                     # unter Windows gleich
          liste(dateien={"daten/rohrlaser.db": dict(sha256=sha, groesse=10, paket=paket)}),
          liste(pakete={paket: dict(groesse="100")}),
          liste(pakete={paket: dict(groesse=100, sha256="kaputt")}),
          liste(adresse="https://example.invalid/"), liste(adresse="http://github.com/patrickbrundiers-dev/"),
          "keine Liste"]
for f in falsch:
    fehler_erwartet(update.liste_pruefen, f)
ok(f"Dateiliste: {len(falsch)} gefälschte oder kaputte Varianten abgelehnt")

# 3) Laden: nur https, Größengrenzen
fehler_erwartet(update.holen, "http://example.invalid/Update.json", text="https")
gross = tmp / "gross.json"
gross.write_bytes(b"x" * 1000)
assert update.holen(str(gross), grenze=1000) == b"x" * 1000
fehler_erwartet(update.holen, str(gross), grenze=999, text="größer als erwartet")
fehler_erwartet(update.holen, str(gross), tmp / "kopie", grenze=999, text="größer als erwartet")
ok("Download: http abgelehnt, Grenze für Liste und Pakete")


# 4) Pakete: ZIP-Bombe (Eintrag größer als angekündigt), Paket-Prüfsumme, Speicherplatz
def paket_bauen(name, eintraege):
    puffer = io.BytesIO()
    with zipfile.ZipFile(puffer, "w", zipfile.ZIP_DEFLATED) as z:
        for n, inhalt in eintraege.items():
            z.writestr(n, inhalt)
    (tmp / "quelle").mkdir(exist_ok=True)
    (tmp / "quelle" / name).write_bytes(puffer.getvalue())
    return len(puffer.getvalue())



inhalt = b"echt" * 100
sha_echt = hashlib.sha256(inhalt).hexdigest()
bombe = b"\0" * 5_000_000
p_ok = "p-" + "1" * 40 + ".zip"
p_bombe = "p-" + "2" * 40 + ".zip"
g_ok = paket_bauen(p_ok, {sha_echt: inhalt})
g_bombe = paket_bauen(p_bombe, {sha_echt: bombe})
(tmp / "quelle" / update.DATEILISTE).write_text("{}", encoding="utf-8")
quelle = str(tmp / "quelle" / update.DATEILISTE)
prog = tmp / "prog"
prog.mkdir()


def online_fuer(p, groesse, paket_sha=None):
    pk = dict(groesse=groesse)
    if paket_sha:
        pk["sha256"] = paket_sha
    return dict(format=1, stand=2, dateien={"a.dll": dict(sha256=sha_echt, groesse=len(inhalt), paket=p)},
                pakete={p: pk})


o = online_fuer(p_ok, g_ok, update.pruefsumme(tmp / "quelle" / p_ok))
plan = update.planen(prog, o)
assert plan["entpackt"] == len(inhalt)
neu = update.laden(prog, quelle, o, plan)
assert (neu / sha_echt).read_bytes() == inhalt
update.verwerfen(prog)
o = online_fuer(p_bombe, g_bombe)
fehler_erwartet(update.laden, prog, quelle, o, update.planen(prog, o), text="Größe")
assert not list((prog / update.ARBEITSORDNER / "neu").glob("*")) or \
    (prog / update.ARBEITSORDNER / "neu" / sha_echt).stat().st_size <= len(inhalt)
update.verwerfen(prog)
o = online_fuer(p_ok, g_ok, "f" * 64)
fehler_erwartet(update.laden, prog, quelle, o, update.planen(prog, o), text="Prüfsumme des Pakets")
update.verwerfen(prog)
o = online_fuer(p_ok, g_ok - 1)                            # Paket größer als in der Liste
fehler_erwartet(update.laden, prog, quelle, o, update.planen(prog, o), text="größer als erwartet")
update.verwerfen(prog)
fehler_erwartet(update.platz_pruefen, prog, dict(groesse=50 << 20, entpackt=60 << 20), frei=200 << 20,
                text="Speicherplatz")
update.platz_pruefen(prog, dict(groesse=50 << 20, entpackt=60 << 20), frei=300 << 20)
ok("Pakete: ZIP-Bombe, falsche Paket-Prüfsumme, zu großes Paket, zu wenig Platz abgelehnt")

# 5) Paket-Prüfsumme steht beim Build in der Dateiliste
bau = tmp / "bau"
(bau / "_internal").mkdir(parents=True)
(bau / "_internal" / "a.dll").write_bytes(b"dll" * 1000)
(bau / "Rohrlaser-Angebotskalkulation.exe").write_bytes(b"MZ" * 1000)
l = update.erstellen(bau, tmp / "bau_pakete", 3)
update.liste_pruefen(l)
assert all(update.pruefsumme(tmp / "bau_pakete" / n) == p["sha256"] for n, p in l["pakete"].items())
ok("Build: Prüfsumme je Paket in der Dateiliste")

# 6) Absturz mitten im Austausch (H2): Journal, nächster Start stellt den alten Stand her
alt = tmp / "absturz"
for rel, text in {"Rohrlaser-Angebotskalkulation.exe": "alt-exe", "_internal/a.dll": "alt-a",
                  "_internal/weg.pyd": "alt-weg"}.items():
    (alt / rel).parent.mkdir(parents=True, exist_ok=True)
    (alt / rel).write_text(text)
(alt / "Daten").mkdir()
(alt / "Daten" / "rohrlaser.db").write_text("DATEN")
vorher = {p.relative_to(alt).as_posix(): p.read_text() for p in alt.rglob("*") if p.is_file()}
neu_ordner = tmp / "neu_dateien"
neu_ordner.mkdir()
neue = {"Rohrlaser-Angebotskalkulation.exe": "neu-exe", "_internal/a.dll": "neu-a", "_internal/neu.dll": "neu-dazu"}
online = dict(format=1, stand=9, dateien={})
for rel, text in neue.items():
    h = hashlib.sha256(text.encode()).hexdigest()
    (neu_ordner / h).write_text(text)
    online["dateien"][rel] = dict(sha256=h, groesse=len(text), paket=p_ok)
plan = dict(neu=list(neue), weg=["_internal/weg.pyd"])
echt_kopieren, kopiert = shutil.copyfile, []


class Stromausfall(BaseException):
    pass


def kopieren(von, nach):
    if len(kopiert) == 2:
        raise Stromausfall()
    kopiert.append(nach)
    return echt_kopieren(von, nach)


shutil.copyfile = kopieren
try:
    update.einspielen(alt, online, plan, neu_ordner)
    raise AssertionError("Absturz erwartet")
except Stromausfall:
    pass
finally:
    shutil.copyfile = echt_kopieren
assert (alt / update.ARBEITSORDNER / update.JOURNAL).is_file()
assert (alt / "_internal" / "a.dll").read_text() == "neu-a"          # halb fertig
update.aufraeumen(alt)                                               # darf mit Journal nichts löschen
assert any((alt / update.ARBEITSORDNER).glob("alt-*"))
assert update.nach_absturz(alt) == []
nachher = {p.relative_to(alt).as_posix(): p.read_text() for p in alt.rglob("*")
           if p.is_file() and not p.relative_to(alt).as_posix().startswith(update.ARBEITSORDNER + "/")}
assert nachher == vorher, (nachher, vorher)
assert not (alt / update.ARBEITSORDNER / update.JOURNAL).exists()
assert update.nach_absturz(alt) is None
# danach klappt das Update ganz
update.einspielen(alt, online, plan, neu_ordner)
assert (alt / "_internal" / "neu.dll").read_text() == "neu-dazu" and not (alt / "_internal" / "weg.pyd").exists()
assert not (alt / update.ARBEITSORDNER / update.JOURNAL).exists() and update.lokale_liste(alt)["stand"] == 9
assert (alt / "Daten" / "rohrlaser.db").read_text() == "DATEN"
ok("Absturz im Austausch: Journal bleibt, nächster Start stellt den alten Stand her, Daten unberührt")

# 7) Journal unlesbar: wird verworfen, nichts angefasst
(alt / update.ARBEITSORDNER).mkdir(exist_ok=True)
(alt / update.ARBEITSORDNER / update.JOURNAL).write_text("kaputt")
assert update.nach_absturz(alt) == ["Journal unlesbar"] and not (alt / update.ARBEITSORDNER / update.JOURNAL).exists()
ok("Kaputtes Journal: verworfen, Programmordner unverändert")

shutil.rmtree(tmp, ignore_errors=True)
print("OK: Online-Update gehärtet (Pfade, Dateiliste, Grenzen, ZIP-Bombe, Speicherplatz, Absturz)")
