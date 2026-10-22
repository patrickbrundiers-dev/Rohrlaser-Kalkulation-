@echo off
rem Legt im Autostart-Ordner des angemeldeten Benutzers eine Verknuepfung zur Maschinenplanung an.
rem Keine Admin-Rechte noetig. Der Server startet dann bei jeder Anmeldung dieses Benutzers (minimiert).
set ZIEL=%~dp0Rohrlaser-Maschinenplanung.exe
set LINK=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\Rohrlaser-Maschinenplanung.lnk
powershell -NoProfile -Command "$s=(New-Object -ComObject WScript.Shell).CreateShortcut($env:LINK); $s.TargetPath=$env:ZIEL; $s.WorkingDirectory='%~dp0'; $s.WindowStyle=7; $s.Save()"
if errorlevel 1 (echo Autostart konnte nicht eingerichtet werden. & pause & exit /b 1)
echo Autostart eingerichtet: %LINK%
echo Entfernen: diese Verknuepfung loeschen.
pause
