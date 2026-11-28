# Entwickler-Ausweis (Zugangssystem Paket A)

Der Entwicklerzugang von NexTube beruht auf einem signierten **Entwickler-Ausweis**. Im Programm steht kein Passwort
und kein Prüfwert, nur der öffentliche Lizenzschlüssel (`programm/rohrlaser/lizenz_schluessel.py`). Code:
`programm/rohrlaser/zugang_ausweis.py`, Prüfung in `zugang_pruefstelle.py`, Tests `tests/test_zugang_kern.py`.

## Ausweis ausstellen (nur Patrick, Lizenz-Werkzeug)

```
python werkzeuge/lizenz_werkzeug.py entwickler-ausweis [--name Patrick] [--monate 24]
       [--umgebung produktiv --umgebung test --umgebung entwicklung] [--installation ID]… [--ersetzt EW-…]
```

- Fragt das Lizenz-Passwort und zweimal das neue **Entwickler-Passwort** (mindestens 12 Zeichen). Das Passwort steht
  nirgends, auch nicht als Hash; es verschlüsselt nur den privaten Anmeldeschlüssel (scrypt 128 MB + AES-256-GCM).
- Ergebnis: `Rohrlaser-Lizenz\Entwickler\entwickler.ausweis` und ein Registereintrag `EW-JJJJ-NNNN`.
- Die Datei auf einen USB-Stick kopieren (Wurzel oder Ordner `NexTube\`). Eine zweite Kopie sicher verwahren.
- Ohne `--installation` gilt der Ausweis an allen Installationen; ohne `--umgebung` in Produktiv, Test und
  Entwicklung. Höchstlaufzeit 3 Jahre.

## Anmelden (ab Paket C im Loginfenster)

- Stick einstecken, im Loginfenster „Entwickler“ wählen, Entwickler-Passwort eingeben. Der Stick ist der zweite Faktor.
- Optional einmal je Installation **hinterlegen** (nur mit dem Stick): danach reicht Passwort plus, wenn eingerichtet,
  Einmalcode aus der Authenticator-App.
- Vollzugriff auf alles, auch ohne Platzlizenz und im Lesemodus; Abmeldung nach 15 Minuten ohne Eingabe; jede
  Anmeldung und jeder Zugriff steht im Sicherheitsprotokoll (ohne Passwort).

## Verlust oder Verdacht

1. `lizenz_werkzeug.py sperren EW-JJJJ-NNNN` und die Sperrliste wie gewohnt hochladen.
2. Neuen Ausweis mit `--ersetzt EW-JJJJ-NNNN` ausstellen.

Passwort ändern geht im Programm (neuer Tresor, Stand + 1); jede Installation nimmt danach keine ältere Kopie mit dem
alten Passwort mehr an.

## Was der Ausweis ersetzt

Den Entwicklerzugang mit festem Prüfwert (`entwickler.py`, `VERIFIZIERER`) aus PR #703. Er wurde dort leer (= aus)
gemergt und ist seit 0.9.555 vollständig entfernt (Modul, Haken in Start-Login und Einstellungen,
Werkzeug-Befehl `entwickler-schluessel`). Bis das neue Anmeldefenster (Paket C) den Ausweis einbindet, gibt es
keinen Entwicklerzugang im Programm.
