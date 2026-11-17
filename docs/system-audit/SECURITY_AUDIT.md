# Sicherheitsprüfung

Stand 17.11.2026, `main` ba3cdc2 (0.9.372). Die Software ist ein Windows-Programm ohne Web-Oberfläche und ohne
eigenen Server; jeder PC hat seine Datendatei (SQLite oder eingebettetes PostgreSQL), abgeglichen wird über einen
gemeinsamen Ordner. Das bestimmt, welche Angriffe überhaupt möglich sind.

## Angreifer, die betrachtet wurden

1. **Mitarbeiter ohne Admin-Recht** mit eigenem Arbeitsplatz und Schreibrecht im gemeinsamen Ordner (der Abgleich
   braucht dieses Recht). Ziel: Admin-Rechte, Preise ändern, Lizenz umgehen.
2. **Fremde Datei** (Kunden-Mail, STEP, PDF, ZIP), die das Programm liest.
3. **Manipuliertes Update** auf dem Weg vom Repository zum PC.

## Ergebnis je Prüfpunkt

| Prüfpunkt | Ergebnis | Befund |
|---|---|---|
| Lizenzprüfung | Ed25519-signierte Lizenzdatei, öffentlicher Schlüssel im Programm, Sperrliste, Uhr-Rückstellschutz (`zeit.json`), Durchsetzung ab 20.11.2026 (`lizenz.DURCHSETZUNG_AB`) | ohne Befund [Code] |
| Hauptadmin | eigene signierte Lizenz ohne Rechner-ID, privater Admin-Schlüssel im Tresor (scrypt n=2¹⁶ + AES-256-GCM), Passwort nirgends gespeichert, Sperre nach 5 Fehlversuchen (60 s, verdoppelt bis 1 h), älterer Tresor-Stand wird abgelehnt | ohne Befund [Code], Tests `test_hauptadmin.py` grün |
| Admin-Rechte über alle Plätze | Admin-Vorgaben-Paket nur mit SHA-256-Prüfsumme | **SEC-01 (P0)** [geprüft] |
| Rechte-Werte im normalen Abgleich | `passwort`, `admin_liste`, Rollen ohne Paket „jüngste Änderung gewinnt“ | **SEC-02 (P0)** [geprüft] |
| Admin-Schutz am eigenen Platz | Datendatei lokal änderbar | SEC-03 (P2), Grenze ohne Server |
| Passwortspeicherung | PBKDF2-SHA256, 200.000 Runden, 16 Byte Salz, Vergleich mit `hmac.compare_digest`; Admins mit eigenem Passwort (mind. 6 Zeichen Startpasswort, Hauptadmin mind. 10) | ohne Befund; Altlast Klartext SEC-04 (P3) |
| Rollen und Rechte | `rollen.py` (Benutzerverwaltung), `admin_schutz.ist_admin/ist_haupt`; Hauptadmin-Seiten nur für den Hauptadmin | richtig umgesetzt, aber über SEC-01/02 aushebelbar |
| Lesemodus (Lizenz abgelaufen) | in der Datenschicht (`@schreibt` → Ausnahme, `PRAGMA query_only`), jede öffentliche Methode markiert (`test_lesemodus.py`) | ohne Befund |
| SQL-Injection | 195 `execute(f"…")` durchgesehen: eingesetzt werden nur Tabellen- und Spaltennamen aus dem Programm bzw. aus `PRAGMA table_info`; alle Werte als Parameter `?` | ohne Befund [Code] |
| XSS | keine Web-Oberfläche; Qt-Rich-Text (`setHtml`) in Anfragen und Materialanfragen setzt Mail-Inhalte mit `html.escape` ein; Qt führt kein JavaScript aus | ohne Befund [Code] |
| CSRF | nicht zutreffend (keine Web-Sitzung, keine HTTP-Schnittstelle des Programms) | – |
| API-Sicherheit | einzige Netzschnittstelle ist das Online-Update (HTTPS, Update.json Ed25519-signiert mit eigenem Schlüssel U1, Pfadprüfung, Größenlimits, SHA-256 je Datei, atomares Ersetzen) – Prüfung 24.10.2026 [übernommen], Tests `test_update*.py` | ohne Befund |
| Lokales PostgreSQL | nur `127.0.0.1`, kein Unix-Socket, `scram-sha-256`, zufälliges Passwort in `Daten/pg` | ohne Befund [Code] |
| Fremde Dateien | Mail-Anhänge werden vor dem Öffnen geprüft (`virenpruefung.py`, Sperre bis zur Freigabe), ZIP-Inhalte nur als Dateiname ohne Ordner und mit Größengrenze (`mail.zip_inhalt`), STEP in eigenem Prozess mit Zeitlimit | ohne Befund [Code] |
| Geheimnisse im Repository | `git ls-files`/`git grep`: keine Schlüssel, Lizenzen, Datenbanken, Passwörter; `.gitignore` sperrt `*.pem`, `*.lizenz`; GitHub Secret Scanning an | ohne Befund |
| Abhängigkeiten | `pip-audit` gegen alle festen Versionen: keine bekannten Schwachstellen | ohne Befund (17.11.2026) |
| Lieferkette CI | Actions auf Commit-SHA gepinnt, `permissions: contents: read`, Schreiben nur im Windows-Job, Release-Prüfung `release_pruefen.py` | ohne Befund [übernommen 24.10.] |
| Protokollierung | zentrales `fehler.log`, kein Passwort im Protokoll gefunden; seit 0.9.378 Bereinigung von Zugangsdaten vor dem Schreiben | LOG-01 (P2), behoben 0.9.378 |

## Schwerpunkt: Können normale Benutzer Hauptadmin oder Lizenz umgehen?

- **Lizenz: nein.** Ohne den privaten Lizenzschlüssel (nur im Lizenz-Werkzeug bei Patrick) lässt sich keine gültige
  Lizenz bauen; Ändern einer Datei macht die Signatur ungültig.
- **Hauptadmin-Anmeldung: nein.** Ein selbst gebauter Tresor passt nicht zum signierten öffentlichen Schlüssel.
- **Admin-Rechte an allen Plätzen: ja, heute.** Über SEC-01 (Datei im gemeinsamen Ordner) oder SEC-02 (eigene
  Datendatei + Abgleich) setzt ein Mitarbeiter ein eigenes Admin-Passwort für alle Plätze und schaltet sich damit
  überall als Admin frei. Er kann auch Werte der Kalkulation (Gewinn, Zuschläge, Preise, Maschinen) ändern, die dann
  an allen Plätzen gelten. Hauptadmin-Seiten bleiben dem Hauptadmin vorbehalten, aber nur dort, wo der Hauptadmin
  über seine Lizenz angemeldet ist.

## Fix für SEC-01/SEC-02 (umgesetzt in 0.9.376)

1. **Signatur der Admin-Vorgaben** mit Ed25519. Vertrauensanker ist der Lizenzschlüssel: Das Paket enthält den
   signierten Inhalt der Hauptadmin-Lizenz (ohne Tresor), jeder Platz prüft ihn mit dem eingebauten öffentlichen
   Lizenzschlüssel und damit den Admin-Schlüssel, mit dem das Paket signiert ist.
2. **Weitere Admins** signieren mit einem Schlüssel aus ihrem Passwort (scrypt mit eigenem Salz); ihr öffentlicher
   Schlüssel steht in der Admin-Liste, die nur der Hauptadmin signiert. Ein gesperrter Admin verliert damit auch die
   Signatur.
3. **Rechte-Werte nie über den normalen Abgleich** (`passwort`, `admin_liste`, `admin_seiten`, `benutzer_rollen`,
   `rollen_rechte`, `anmeldung_pflicht`), auch nicht ohne Paket.
4. **Übergang:** Ein Platz merkt sich, sobald er ein gültig signiertes Paket gesehen hat, und nimmt danach nur noch
   signierte an (Einstellung `admin_vorgaben_signiert`, nur lokal, nie im Abgleich; gemerkt wird erst nach einem
   vom Hauptadmin signierten Paket). Solange es im Betrieb noch keine Hauptadmin-Lizenz gibt, läuft alles wie bisher
   (Ersteinrichtung Hauptadmin ist bei Patrick noch offen). Ein abgelehntes Paket steht einmal im Protokoll.
   Punkt 3 gilt ebenfalls ab diesem Zeitpunkt.
5. Tests: Fälschung wie im Nachweis wird abgelehnt (Hinweis, Werte bleiben), echtes Paket vom Hauptadmin und von einem
   weiteren Admin wird angenommen, gesperrter Admin wird abgelehnt, alte Pakete ohne Signatur gelten nur im Übergang.
