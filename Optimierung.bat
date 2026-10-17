@echo off
rem Stangenoptimierung fuer den Auftrag in der Mappe. Excel-Mappe vorher schliessen.
python "%~dp0tools\optimierung.py" "%~dp0mappe\Rohrlaser_Kalkulation_v01.xlsx"
pause
