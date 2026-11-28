@echo off
rem Befehle des Rohrlaser-Servers (IT-Handbuch Kapitel 5), z. B.:  Server status --ordner D:\RohrlaserServer
start "" /wait /b "%~dp0Rohrlaser-Angebotskalkulation.exe" --server %*
exit /b %ERRORLEVEL%
