@echo off
rem STEP-Dateien oder einen Ordner auf diese Datei ziehen. Excel-Mappe vorher schliessen.
python "%~dp0tools\step_import.py" "%~dp0mappe\Rohrlaser_Kalkulation_v01.xlsx" %*
pause
