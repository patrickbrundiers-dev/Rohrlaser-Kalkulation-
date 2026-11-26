# Lizenz 2.0: Prüfliste vor dem Verkauf an Kunden

Stand 26.11.2026, Paket L2-4. Jeder Punkt wird abgehakt, bevor eine Kundenlizenz das Haus verlässt.

## Einmalig (Patrick)

- [ ] Repository auf **privat** gestellt (GitHub → Settings → General → Danger Zone).
- [ ] Privater Lizenzschlüssel (`privat_K1.pem`) und Passwort an zwei getrennten Orten gesichert (USB-Stick im Tresor und
      verschlüsselte Kopie). Ohne ihn lassen sich keine Lizenzen mehr verlängern.
- [ ] Code-Signatur-Zertifikat (Secret `SIGNATUR_PFX`) gültig, die .exe ist signiert (Windows zeigt den Herausgeber).
- [ ] Name/Marke geprüft (DPMAregister, TMview, Domains), bevor das Branding (B-1) ins Programm kommt.
- [ ] Lizenzbedingungen/EULA geschrieben (nicht Teil des Programms; Anwalt oder Muster).

## Je Kunde

- [ ] Lizenz im Lizenz-Werkzeug unter **Lizenzen 2.0 …** angelegt: Lizenznehmer, Firma, Kundennummer, Art
      (Einzelplatz/Mehrplatz/Server), Plätze, Reserve (Vorgabe 1), Laufzeit (Vorgabe 12 Monate), **Module** abgehakt.
- [ ] Lizenzschlüssel `LZ-…` an den Kunden (E-Mail oder Telefon). Der Schlüssel allein ist kein Geheimnis: Ohne
      Patricks Antwort auf die Aktivierungsanfrage läuft nichts.
- [ ] Je Rechner Anfrage beantwortet; in der Übersicht stimmt **belegt / max**.
- [ ] Beim Kunden unter Hilfe → Lizenz … geprüft: Lizenzart, Plätze, Module, „Dieser Platz“.
- [ ] Wiedervorlage 30 Tage vor Ablauf (die Übersicht färbt die Zeile gelb).

## Was das Programm prüft (Prüfstellen)

| Stelle | Prüfung | Folge bei Fehler |
| --- | --- | --- |
| Programmstart und jede Lizenzprüfung (`LizenzStelle.pruefen`) | Zertifikat- und Antwortsignatur (Ed25519), Gerätesignatur mit dem Geräteschlüssel, Merkmale 2 von 3, Laufzeit, Sperrliste (Lizenz und Platz), Uhr zurückgestellt | Lesemodus mit Grund |
| Jede Funktion (`funktionen.an`) | Modul der Funktion in der Lizenz (`module.erlaubt`) | Funktion ausgeblendet wie „aus“ |
| Rohrlaser Auslastung (`rl_auslastung.lizenzen`) | Modul Auslastung | Nur ansehen |
| Update-Check | neue Sperrliste übernehmen (nur neuer und gültig signiert) | gesperrte Plätze und Lizenzen gehen in den Lesemodus |
| Eigene Programmdateien (`echtheit`) | Prüfsummen | Lesemodus „Programmdateien verändert“ |

## Lizenzprotokoll

Jeder Rechner schreibt `Lizenz/lizenz_protokoll.txt` (höchstens 1000 Zeilen): Anfrage erstellt, Aktivierung
übernommen, Platz freigegeben, Sperrliste übernommen und jeder Zustandswechsel (gültig, Lesemodus mit Grund, Module).
Zu sehen unter Hilfe → Lizenz … → **Lizenzprotokoll …** und im Supportpaket.

## Module

Basis (immer): Rohr-Kalkulation, Angebote, STEP-Import, PDF, Fracht, Schnellpreis. Module (`programm/rohrlaser/module.py`):
Blech, Baugruppen, Auftrag, Vertrieb, Einkauf, Auslastung, KI. Bisherige Lizenzen haben „alle“.
