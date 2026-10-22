@echo off
rem Prueft von einem ANDEREN PC aus, ob der Planungsserver erreichbar ist (Firewall).
set /p RECHNER=Name oder IP des Server-Rechners: 
powershell -NoProfile -Command "Test-NetConnection '%RECHNER%' -Port 8765 | Select-Object ComputerName,RemotePort,TcpTestSucceeded | Format-List"
echo TcpTestSucceeded True = erreichbar. False = Firewall des Server-Rechners laesst den Port nicht zu.
pause
