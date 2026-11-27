"""Zentrales Benutzer-, Entwickler- und Lizenzsystem (Auftrag Patrick 27.11.2026, Plan Pakete A–F, Freigabe
„Alle Empfehlungen E1a bis E6a“).

Sieben Module mit klarer Aufgabe, alle ohne Qt und einzeln testbar:

- authentifizierung: Passwort-Hash (scrypt mit eigenem Salz, alte PBKDF2-Hashes bleiben lesbar), Passwortregeln,
  Einmalcode (TOTP, RFC 6238), Sperre gegen Durchprobieren.
- ausweis: Entwickler-Identität. Ein Entwickler-Ausweis ist mit Patricks Lizenzschlüssel signiert und enthält den
  öffentlichen Anmeldeschlüssel; der private Anmeldeschlüssel liegt im Tresor, verschlüsselt mit dem Passwort. Im
  Programm steht nur der öffentliche Lizenzschlüssel – kein Passwort, kein Prüfwert, keine Rechnerbindung.
- berechtigung: Einzelrechte, Rollen als Bündel, Regeln gegen Rechte-Ausweitung.
- sitzungen: Sitzung mit zufälligem Token, Inaktivität, Benutzerwechsel; beendete Tokens gelten nie wieder.
- protokoll: ein Sicherheitsprotokoll für alles, Geheimnisse werden vor dem Schreiben entfernt.
- pruefstelle: die einzige Stelle, die „darf dieser Benutzer an dieser Installation mit dieser Lizenz das?“
  beantwortet. Die Fachlogik ruft pruefstelle.verlangen(recht), die Oberfläche fragt pruefstelle.darf(recht).
- (Paket B/E) arbeitsplaetze, lizenzierung, verwaltung mit den Tabellen zg_*.
"""
