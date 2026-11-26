"""Rechtsklick-Menü der Positionen (Patrick 26.11.2026, „UI-Vereinfachung, Kontextmenü optimieren“).

Bis 0.9.516 standen 49 Einträge untereinander in einer langen Liste. Jetzt oben nur die täglichen Aktionen (Bearbeiten
im passenden Editor, Material, Zusatzarbeiten, Zukaufteile, Stückzahl, Duplizieren), die seltenen Aktionen in
Untermenüs nach Zweck, Löschen abgesetzt ganz unten. Welche Einträge erscheinen, entscheidet weiter
AngebotSeite._pos_menue_anpassen (nur was zur markierten Position passt); ein Untermenü ohne sichtbaren Eintrag
verschwindet ganz.

Entfallen ist nur der doppelte Eintrag „Blech-EK je Satz/Baugruppe …“: er öffnete dasselbe Fenster wie „Satz
bearbeiten …“, das jetzt auch bei Baugruppen erscheint. Alle Aktionen bleiben auch über Menü Bearbeiten, Doppelklick,
Knöpfe und Tastenkürzel erreichbar wie bisher. Ohne Qt (Anleitung und Tests lesen die Ordnung)."""

TRENNER = "-"

# (Untermenü oder None = direkt im Menü, [Einträge]); TRENNER = Linie. Die Texte sind zugleich die Schlüssel in
# AngebotSeite.pos_aktionen.
STRUKTUR = (
    (None, ("Schneidweg berechnen …", "Blech-Editor …", "Richtpreis Dreh-/Frästeil …", "Baugruppe bearbeiten …",
            "Material …", "Zusatzarbeiten …", "Zusatzarbeit hinzufügen", "Zukaufteile bearbeiten …",
            "Stückzahl ändern …")),
    TRENNER,
    (None, ("Position duplizieren", "Für markierte setzen …", "Positionen aus anderem Angebot übernehmen …")),
    TRENNER,
    ("Prüfen und anzeigen", ("Im STEP-Viewer öffnen …", "Bohrungen prüfen …", "Anbauteile prüfen …",
                             "STEP-Merkmale prüfen …", "Ähnliche Teile und Revisionen …",
                             "Abwicklung 1:1 drucken (PDF) …")),
    ("Teil ändern", ("Art ändern (Blech / Rohr / Dreh-/Frästeil) …", "Material suchen und zuweisen …",
                     "Wandstärke ändern …", "Schweißnaht …", "Fräsen nach Bearbeitung …", "Rohr teilen …",
                     "Teil wenden (gewendetes Duplikat) …", "Teilefamilie (mehrere Längen/Varianten) …",
                     "3D aus STEP nachladen …", "Virtuelles Bauteil als STEP …", "Stege abtrennen an/aus")),
    ("Kennzeichnen", ("Muster an/aus", "Geometrie geprüft / nur kalkuliert", "Wenden erlaubt / nicht wenden")),
    ("Satz und Baugruppe", ("Satz in 3D …", "Satz bearbeiten (Anzahl Sätze) …", "Satz per Text ändern …",
                            "Zusatzarbeit für ganzen Satz …", "Als Satz zusammenfassen …", "Satz auflösen (Einzelteile)",
                            "Satz → Schweißbaugruppe …", "Schweißbaugruppe → Satz",
                            "Alle Schweißbaugruppen nachrechnen", "Baugruppe in anderes Angebot kopieren …")),
    ("Reihenfolge", ("Nach oben", "Nach unten", "An den Anfang", "Ans Ende",
                     "Positionsnummern neu vergeben (10, 20, 30 …)")),
    TRENNER,
    (None, ("Positionen löschen",)),
)

# Löschen fragt erst ab so vielen Positionen bzw. bei ganzen Baugruppen/Sätzen nach (darunter genügt „Rückgängig“ in
# der Einblendung wie bisher, Plan Bedienung B2)
LOESCHEN_FRAGEN_AB = 3


def eintraege():
    """Alle Einträge in Menüreihenfolge."""
    return [t for teil in STRUKTUR if teil != TRENNER for t in teil[1]]


def untermenue_von(text):
    """Titel des Untermenüs eines Eintrags oder None (direkt im Menü)."""
    return next((teil[0] for teil in STRUKTUR if teil != TRENNER and text in teil[1]), None)


def loeschen_fragen(anzahl, ganze_gruppe=False):
    """Vor dem Löschen nachfragen? Ab LOESCHEN_FRAGEN_AB Positionen oder wenn eine ganze Baugruppe bzw. ein ganzer Satz
    dabei ist."""
    return anzahl >= LOESCHEN_FRAGEN_AB or bool(ganze_gruppe)
