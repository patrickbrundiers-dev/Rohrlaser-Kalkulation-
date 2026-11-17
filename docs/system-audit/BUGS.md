# Gefundene Fehler und Schwachstellen

Stand 17.11.2026, `main` ba3cdc2 (0.9.372). Priorität nach Master-Prompt: **P0** Datenverlust, Sicherheitslücke,
falsche Kalkulation · **P1** wichtige Funktion defekt · **P2** Einschränkung oder Performance · **P3** Kleinigkeit.
Nachweis: **[geprüft]** nachgestellt, **[Code]** aus dem Quelltext. Die Skripte zum Nachstellen liegen im
Projektordner unter `system-audit/nachweise/`.

| ID | P | Bereich | Kurz | Stand |
|---|---|---|---|---|
| SEC-01 | P0 | Rechte, Abgleich | Admin-Vorgaben im gemeinsamen Ordner unsigniert: jeder mit Schreibrecht ersetzt Admin-Passwort und geschützte Werte an allen Plätzen | offen, nächster PR |
| SEC-02 | P0 | Rechte, Abgleich | Ohne Admin-Vorgaben geht ein lokal geändertes Admin-Passwort über den normalen Abgleich an alle Plätze | offen, nächster PR |
| DB-02 | P1 | Datenbank, Archiv | Archivieren ließ Reklamationen und Scan-Rückmeldungen verwaist zurück | **behoben** 0.9.375 |
| TEST-01 | P1 | Tests, CI | Datenbank-Tests laufen in CI nur gegen SQLite, obwohl PostgreSQL seit 0.9.339 der Speicher je PC sein kann | offen |
| ERR-01 | P2 | Fehlerbehandlung | 35 Stellen `except …: pass`, einige ohne Protokoll in Ausgabe- und Kalkulationswegen | offen |
| LOG-01 | P2 | Protokoll | Fehlerprotokoll ohne Modul, Funktion, Kürzel, Version; WARNING kaum genutzt; keine Bereinigung von Zugangsdaten | offen |
| CALC-01 | P2 | Kalkulation | `round(x, 2)` (halbe Cent zur geraden Zahl) an einigen Geldstellen statt der kaufmännischen Rundung | offen |
| DB-01 | P2 | Datenbank | Verweise zwischen Tabellen nur im Code (6 Fremdschlüssel bei 79 Tabellen); SQLite-IDs ohne AUTOINCREMENT werden wiedervergeben | offen |
| SEC-03 | P2 | Rechte | Nicht-Admin kann den Admin-Schutz am eigenen Platz durch direktes Ändern der Datendatei abschalten | Grenze, dokumentiert |
| TEST-02 | P2 | CI | Testabdeckung und Abhängigkeits-Schwachstellen werden in CI nicht gemessen | offen |
| CODE-01 | P3 | Code | ~25 ungenutzte Funktionen/Methoden, 5 ungenutzte Variablen (vulture) | offen |
| CODE-02 | P3 | Code | sehr große Dateien und Funktionen (`angebot_fenster.py` 10.300 Zeilen, `rechnen._kalkulation` Komplexität 331) | bewusst offen |
| CODE-03 | P3 | Code | Parameter ohne Wirkung (`fracht.zuschlaege(leistung_basis)`, `auftrag_av.fuer_alle(nur_aktiv_namen)`, `optimierungsvorschlaege.maschinen(verkauf_jetzt)`) | offen |
| CODE-04 | P3 | Code | 1.823 Importe innerhalb von Funktionen (gegen Zyklen); Abhängigkeiten schwer sichtbar | bewusst offen |
| SEC-04 | P3 | Passwort | Ein noch im Klartext gespeichertes Altpasswort gilt weiter (wird beim Öffnen umgestellt) | bewusst offen |

---

## SEC-01 (P0) Admin-Vorgaben im gemeinsamen Ordner sind nicht signiert [geprüft]

**Wo:** `programm/rohrlaser/admin_schutz.py` – `paket_lesen`, `nach_lesen`, `paket_anwenden`; Datei
`<gemeinsamer Ordner>/Admin/admin_vorgaben.json`.

**Was:** Das Paket trägt nur eine SHA-256-Prüfsumme über den eigenen Inhalt. Wer die Datei ändert, rechnet die
Prüfsumme einfach neu. Jeder Arbeitsplatz übernimmt beim Abgleich ein Paket mit neuerem `stand` und schreibt alle
Werte daraus ein – auch `passwort` (Admin-Passwort), `admin_liste` (wer Admin ist), Rollen und alle geschützten
Kalkulationswerte (Gewinn, Zuschläge, Preise, Maschinen, Schneiddaten …). Im Modul steht es offen: „die Prüfsumme
erkennt beschädigte Dateien, ist aber keine Verschlüsselung“.

**Nachweis:** Zwei Plätze PB (Admin) und MA (Mitarbeiter) mit gemeinsamem Ordner. MA ändert nur die Datei im Ordner
(Admin-Passwort-Hash auf „max123“, Gewinn 0,01, Prüfsumme neu, Stand 2099). Nach dem nächsten Abgleich an PB:
`gewinn 0.01`, altes Passwort gilt nicht mehr, „max123“ gilt. Skript `nachweise/poc_paket.py`.

**Folge:** Ein Mitarbeiter übernimmt die Admin-Rechte an allen Plätzen und kann Preise verändern, ohne dass es
auffällt (falsche Kalkulation = P0). Die Hauptadmin-Anmeldung selbst bleibt sicher (signierte Lizenz + Tresor), aber
alles, was am Einstellungs-Passwort hängt, nicht.

**Lösung (nächster PR):**
1. Jedes Paket wird signiert (Ed25519). Der Hauptadmin signiert mit dem Schlüssel aus seinem Tresor; das Paket trägt
   den signierten Inhalt seiner Hauptadmin-Lizenz (ohne Tresor) mit, damit jeder Platz den öffentlichen Schlüssel über
   den Lizenzschlüssel prüfen kann.
2. Weitere Admins bekommen einen eigenen Signaturschlüssel, abgeleitet aus ihrem Passwort (scrypt mit Salz); der
   öffentliche Schlüssel steht in der vom Hauptadmin signierten Admin-Liste.
3. Ein Platz, der einmal ein signiertes Paket gesehen hat, nimmt nur noch signierte Pakete an (gemerkt lokal).
   Plätze ohne Hauptadmin-Lizenz im Betrieb laufen wie bisher weiter, mit Hinweis auf der Startseite.

## SEC-02 (P0) Admin-Passwort geht ohne Paket über den normalen Abgleich [geprüft]

**Wo:** `teilen.lesen` → `admin_schutz.ausfiltern`: gefiltert wird nur, wenn es ein gültiges Paket gibt.

**Was:** Solange kein Admin ein Paket geschrieben hat, laufen `passwort`, `admin_liste`, Rollen und Schutzliste wie
jede andere Einstellung über den feldweisen Abgleich („jüngste Änderung gewinnt“). Ändert ein Mitarbeiter die Werte
direkt in seiner Datendatei (SQLite-Werkzeug), übernehmen alle anderen Plätze sie.

**Nachweis:** Platz MA setzt in seiner Datei `passwort` auf den Hash von „max123“. Nach Abgleich MA → PB gilt an PB
nur noch „max123“. Skript `nachweise/poc_abgleich.py`.

**Lösung:** mit SEC-01: die Rechte-Werte (`passwort`, `admin_liste`, `admin_seiten`, Rollen, Anmeldepflicht) kommen
nie über den normalen Abgleich, nur über ein gültig signiertes Paket.

## DB-02 (P1) Archivieren ließ Reklamationen und Scan-Rückmeldungen verwaist zurück [geprüft, behoben]

**Wo:** `programm/rohrlaser/archiv.py`, `JE_ANGEBOT`.

**Was:** Archiviert wurden Positionen, Staffeln, Stufen, STEP-Protokoll und Fertigungsstatus. `reklamationen` und
`rueckmeldungen` haben keinen Fremdschlüssel mit `ON DELETE CASCADE` und standen nicht in der Liste: Nach dem
Archivieren eines beauftragten Angebots blieben sie mit der alten Angebots-ID in der Datendatei. Die
Reklamationsliste zeigte sie ohne Angebotsnummer, die Reklamationskosten liefen weiter in die Auswertung, beim
Zurückholen mit neuer Positions-ID passte die Zuordnung nicht mehr.

**Nachweis:** `nachweise/poc_archiv.py`: Angebot 2020 beauftragt, eine Reklamation, archivieren → `verwaist: 1`,
Liste zeigt `(1, None)`. Der erweiterte `tests/test_archiv.py` ist mit dem alten `archiv.py` rot.

**Behoben:** beide Tabellen gehören jetzt zum Angebot, werden archiviert, gelöscht und beim Zurückholen mit neuer
Angebots- und Positions-ID eingefügt (SQLite und PostgreSQL). Siehe [FIX_LOG.md](FIX_LOG.md).

## TEST-01 (P1) PostgreSQL-Pfad ist nicht in CI [Code]

**Wo:** `.github/workflows/paket.yml`; `werkzeuge/pg_testlauf.py` gibt es, wird aber nur von Hand gestartet.

**Was:** Seit 0.9.339 kann jeder PC seine Daten im eingebetteten PostgreSQL halten. `db_verbindung.py` übersetzt
SQL für beide Datenbanken; Unterschiede (Typen, Sequenzen, `lastrowid`, Sperren) zeigen sich nur, wenn die Tests auch
gegen PostgreSQL laufen. In CI läuft alles nur gegen SQLite. Ein Fehler, der nur unter PostgreSQL auftritt, käme
unbemerkt nach `main`.

**Lösung:** CI-Job mit PostgreSQL 16 aus dem Ubuntu-Paket, `pg_testlauf.py` für die Datenbank- und Abgleichtests
(etwa 25 Testskripte, als Nicht-root-Benutzer). Teil des Pflicht-Checks `tests`.

## ERR-01 (P2) stille Ausnahmen [Code]

**Wo (Auswahl):** `angebot_ausgabe.py:440` (Kalkulations-PDF: Bearbeitungsliste einer Position fehlt still),
`angebot_ausgabe.py:764` (Materialanfrage: Nachkauf-Vorschlag fehlt still), `automatik.py:220–266` (sechs
Startseiten-Hinweise), `zusatz_formel.py:141–153` (Größen G, F, Q, N, I einer Formel fehlen still),
`nachkalk_vorbelegen.py:59`, `preiswaechter.py:44`, `anfragen_seite.py` (13 Stellen), `lernen.py:149/172`.

**Was:** 35 Stellen `except Exception: pass` (bzw. `continue`), dazu 425 `except Exception` insgesamt. Die meisten
sind bewusst („Hinweis darf den Check nie blockieren“) und kommentiert, aber ohne Eintrag im Protokoll: Ein
Programmfehler an diesen Stellen bleibt unsichtbar. Bei `zusatz_formel` heißt das, dass eine Formel mit G oder F ohne
Wert keinen Preis liefert und nur „Größe fehlt“ meldet, nicht den eigentlichen Fehler.

**Lösung:** `protokoll.warnung(text)` (WARNING mit Stacktrace, ohne Dialog) an jeder dieser Stellen; Verhalten
sonst unverändert. Ein Test zählt die `except …: pass` ohne Protokoll und lässt keine neuen zu.

## LOG-01 (P2) Protokoll ohne Zusammenhang [Code]

**Wo:** `programm/rohrlaser/protokoll.py`.

**Was:** Format `Zeit Stufe Text`; Modul und Funktion stehen nur im Stacktrace, Kürzel, Version und Platz fehlen.
Fast alles wird als INFO geschrieben; WARNING nutzt nur `update.py`; CRITICAL (harter Absturz) landet getrennt in
`absturz.log`. Zugangsdaten werden nicht gezielt entfernt; heute steht nach Code-Durchsicht keins im Protokoll,
aber eine Ausnahme mit Verbindungstext (z. B. `password=…` von psycopg) würde unverändert geschrieben.

**Lösung:** Format mit `%(name)s %(funcName)s`, Kopfzeile je Start mit Version, Kürzel und Datenspeicher, Filter, der
`password=…`, `passwort`-Werte und Tokens durch `***` ersetzt; WARNING für abgefangene, CRITICAL für unerwartete
Fehler im Haupt-Thread. Fehlerliste der Startseite (`fehler_seit`) liest das neue Format mit.

## CALC-01 (P2) `round()` an Geldstellen [geprüft]

**Wo:** `drehfraes_preis.py:652/654` (Richtpreis Dreh-/Frästeil), `fraesen_nach.py:139` (Preis Fräsen nach Zeichnung),
`auftraege.py:839` (Position im Auftrag ergänzt: `preis`), `satz_kosten.py:109`, `absage.py:99`.

**Was:** Python `round(x, 2)` rundet halbe Cent zur geraden Ziffer und arbeitet auf der Binärzahl:
`round(2.675, 2) = 2.67`, `round(0.125, 2) = 0.12`, `round(1.005, 2) = 1.0`; die zentrale Rundung
`ausgabe.kaufm_runden` ergibt 2,68 / 0,13 / 1,01. Unterschied höchstens 1 Cent je Wert, nur genau auf dem halben Cent.
Die Angebotssumme selbst nutzt überall `kaufm_runden`.

**Lösung:** an diesen Stellen `zukauf.runden`/`ausgabe.kaufm_runden`; vorher für jede Stelle prüfen, ob der Wert
festgeschrieben in alten Angeboten steht (dann alter Weg für alte Angebote, wie `PREISREGELN_ALT`).

## DB-01 (P2) Verweise nur im Code [Code]

**Was:** 73 Spalten `…_id` ohne Fremdschlüssel (Liste in [DATABASE_AUDIT.md](DATABASE_AUDIT.md)). Gewollt für den
Abgleich (Text-Schlüssel, `uid`), aber jeder Lösch-, Archiv- und Importweg muss alle abhängigen Tabellen selbst kennen
(DB-02 war so ein Fall). SQLite vergibt ohne `AUTOINCREMENT` die höchste gelöschte ID neu; eine vergessene abhängige
Zeile würde so einem neuen Angebot zugeordnet (beim Löschen ist das heute abgedeckt: `angebot_loeschen` räumt Lager,
Status, Rückmeldungen und Reklamationen auf).

**Lösung:** Diagnose „Verweise prüfen“ (Support-Paket + Test), die alle bekannten Verweise zählt; kein Schema-Umbau.

## SEC-03 (P2) Admin-Schutz am eigenen Platz [Code]

Wer seine eigene Datendatei mit einem Werkzeug ändert (SQLite-Datei, bzw. PostgreSQL mit dem Zugang aus
`Daten/pg`), kann `passwort` leeren und hat dann am eigenen Platz Admin-Rechte. Mit SEC-01/02 behoben wirkt das nur
noch lokal und wird beim nächsten Abgleich durch das signierte Paket zurückgesetzt. Ganz verhindern lässt es sich nur
mit einem zentralen Server, der die Rechte durchsetzt. Lizenz und Hauptadmin sind davon nicht betroffen (signiert).

## TEST-02 (P2) Abdeckung und Abhängigkeiten nicht in CI [Code]

`tests/alle.py --coverage` gibt es, CI nutzt es nicht; `pip-audit` läuft nicht. Lösung: wöchentlicher Lauf
(`schedule`) mit Abdeckungsbericht und `pip-audit` als Artefakt, nicht im Pflicht-Check (Laufzeit).

## CODE-01 bis CODE-04, SEC-04 (P3)

- **CODE-01** vulture (Konfidenz 60–100 %): u. a. `anfrage_vorab.alter_text`, `ansicht3d.hintergrund_bei`,
  `bg_vorgabe.gesamt_text`, `eingabe.ist_zahlenfeld`, `export.zip_name`, `importprofil._datei_artikel`,
  `lizenz.hauptadmin_entfernen`, `preisschicht.untergrenze_text`, `rp_profile.schnitt_aus_messung`,
  `satzgruppen.bg_zelltext`, `staffeln.stufe_kennung`, `teilen.haupt_datei`, `teilen._hinlegen`,
  `terminplan.haltbar`, `vorschlaege_mixin.zielpreis_menge`; Variablen `db_verbindung.py:795 spur`,
  `step_dialog.py:119 locale`. Qt-Methoden (`paintGL`, `lessThan` …) sind Fehlmeldungen. Vor dem Entfernen je
  Funktion prüfen (Aufruf per Name, Anleitung).
- **CODE-02** 135 Funktionen mit Komplexität ≥ 41 (radon F). Kein Umbau ohne fachlichen Anlass.
- **CODE-03** drei Parameter ohne Wirkung, siehe Tabelle.
- **CODE-04** Importe in Funktionen: Folge des Verbots von Zyklen; kein Handlungsbedarf.
- **SEC-04** `passwort.pruefen` nimmt ein Klartext-Altpasswort an (Daten älterer Versionen); `Datenbank` stellt es
  beim Öffnen auf PBKDF2 um. Bleibt, bis keine Version vor 0.8 mehr im Umlauf ist.
