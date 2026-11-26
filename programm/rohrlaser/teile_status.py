"""Herkunft eines Merkmals im Teile-Editor (STEP gemessen, von Hand, Vorgabe, von Hand geänderter STEP-Wert), ohne Qt.
Software-Audit 26.11.2026 (Architektur A-01): vorher nur in teile_editor.py (Oberfläche); herkunft.merkmal_sicherheit
lud dadurch beim Rechnen der Preisherkunft den ganzen Editor samt PySide6. teile_editor.py führt die Namen weiter."""
STEP, MANUELL, VORGABE = "STEP", "manuell", "Vorgabe"
GEAENDERT = "manuell (STEP geändert)"
