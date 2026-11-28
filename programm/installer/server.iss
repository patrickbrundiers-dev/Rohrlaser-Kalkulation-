; Server-Setup (Inno Setup 6) für den zentralen Rohrlaser-Server (Patrick 27.11.2026): dieselben Programmdateien wie
; das ZIP, installiert für alle Benutzer mit Administratorrechten nach C:\Program Files\NexTube Server, dazu das
; IT-Handbuch. Am Ende startet der Einrichtungs-Assistent (--server-assistent, server_assistent.py), der Datenbank,
; Firewall, Freigabe, Aufgabenplanung, zweites Sicherungsziel und die erste Sicherung in einem Durchgang einrichtet.
; Eine neue Version installiert über die alte (gleicher Ordner): die geplanten Aufgaben zeigen weiter auf dieselbe
; .exe, Server-Ordner und Daten liegen außerhalb und bleiben unberührt. Vorher stoppt das Setup den Server.
; Aufruf im Build (paket.yml):
;   ISCC.exe /DVersion=0.9.553.123 /DQuelle=dist\Rohrlaser-Angebotskalkulation /DAusgabe=. programm\installer\server.iss

#ifndef Version
  #define Version "0.0.0"
#endif
#ifndef Quelle
  #define Quelle "..\..\dist\Rohrlaser-Angebotskalkulation"
#endif
#ifndef Ausgabe
  #define Ausgabe "..\..\dist"
#endif
#define Name "NexTube Server"
#define Exe "Rohrlaser-Angebotskalkulation.exe"

[Setup]
; eigene Kennung: Server und Arbeitsplatz-Installation sind getrennte Einträge unter „Apps“
AppId={{4B7E1C92-3A6D-4F15-8E2B-9D0C5A7F6E21}
AppName={#Name}
AppVersion={#Version}
AppVerName={#Name} {#Version}
AppPublisher=Patrick Brundiers
VersionInfoVersion={#Version}
VersionInfoCompany=Patrick Brundiers
VersionInfoProductName={#Name}
VersionInfoDescription={#Name} – Installation
PrivilegesRequired=admin
DefaultDirName={commonpf}\{#Name}
DefaultGroupName={#Name}
DisableProgramGroupPage=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir={#Ausgabe}
OutputBaseFilename=NexTube-Server-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\{#Exe}
UninstallDisplayName={#Name}
CloseApplications=yes
RestartApplications=no
ShowLanguageDialog=no
LicenseFile=..\rohrlaser\Lizenzbedingungen.txt
SetupLogging=yes
#ifdef Signieren
SignTool=signieren
#endif

[Languages]
Name: "de"; MessagesFile: "compiler:Languages\German.isl"

[Files]
; wie das ZIP, ohne Portabel.ini und Daten; IT-Handbuch und Anleitungen liegen schon im Programmordner
Source: "{#Quelle}\*"; DestDir: "{app}"; Excludes: "\Portabel.ini,\Daten,\Angebote,\_update"; Flags: ignoreversion recursesubdirs createallsubdirs
; Kurzbefehl „Server …“ für die Befehle aus dem IT-Handbuch (statt %RL%)
Source: "Server.cmd"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#Name} einrichten"; Filename: "{app}\{#Exe}"; Parameters: "--server-assistent"
Name: "{autoprograms}\{#Name} – Befehle"; Filename: "{cmd}"; Parameters: "/k ""title {#Name} && echo Befehle: Server --help   Beispiel: Server status --ordner D:\RohrlaserServer"""; WorkingDir: "{app}"
Name: "{autoprograms}\{#Name} – IT-Handbuch"; Filename: "{app}\IT-Handbuch_Server.pdf"
Name: "{autoprograms}\{#Name} – Programm (Lizenz)"; Filename: "{app}\{#Exe}"

[Run]
; Update über eine bestehende Einrichtung: Server wieder starten (gestoppt in PrepareToInstall)
; über die Aufgabenplanung, damit sie wie nach einem Neustart unter dem Dienstkonto laufen
Filename: "{sys}\schtasks.exe"; Parameters: "/Run /TN ""Rohrlaser-Server starten"""; Check: HatServer; Flags: runhidden waituntilterminated
Filename: "{sys}\schtasks.exe"; Parameters: "/Run /TN ""Rohrlaser-Server Rechner"""; Check: HatServer; Flags: runhidden waituntilterminated
Filename: "{app}\{#Exe}"; Parameters: "--server-assistent"; Description: "Server jetzt einrichten (Assistent)"; Flags: nowait postinstall skipifsilent; Check: not HatServer
Filename: "{app}\{#Exe}"; Parameters: "--server-assistent"; Description: "Einrichtungs-Assistent öffnen (Server ist schon eingerichtet)"; Flags: nowait postinstall skipifsilent unchecked; Check: HatServer

[Code]
// Der Assistent schreibt Server-Ordner und Port nach Server-Ordner.txt neben die .exe (server_assistent.merken).
// Vor dem Überschreiben wird der Server gestoppt, sonst wären postgres.exe und die DLLs gesperrt; danach startet
// ihn [Run] über die Aufgabenplanung wieder. Die geplanten Aufgaben (Rechner-Dienst, Sicherung) werden ebenfalls angehalten.
var
  Ordner, Port: String;

function Merker(): Boolean;
var
  Zeilen: TArrayOfString;
begin
  Result := False;
  if LoadStringsFromFile(ExpandConstant('{app}\Server-Ordner.txt'), Zeilen) and (GetArrayLength(Zeilen) >= 2) then
  begin
    Ordner := Trim(Zeilen[0]);
    Port := Trim(Zeilen[1]);
    Result := (Ordner <> '') and (Port <> '');
  end;
end;

function HatServer(): Boolean;
begin
  Result := Ordner <> '';
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  Code: Integer;
begin
  Result := '';
  Exec(ExpandConstant('{sys}\schtasks.exe'), '/End /TN "Rohrlaser-Server Rechner"', '', SW_HIDE, ewWaitUntilTerminated, Code);
  Exec(ExpandConstant('{sys}\schtasks.exe'), '/End /TN "Rohrlaser-Server Sicherung"', '', SW_HIDE, ewWaitUntilTerminated, Code);
  if Merker() and FileExists(ExpandConstant('{app}\{#Exe}')) then
    Exec(ExpandConstant('{app}\{#Exe}'), '--server stoppen --ordner "' + Ordner + '" --port ' + Port, '', SW_HIDE, ewWaitUntilTerminated, Code);
end;

[UninstallDelete]
Type: filesandordirs; Name: "{app}\_internal"
Type: filesandordirs; Name: "{app}\STEP-Import"
Type: filesandordirs; Name: "{app}\_update"
Type: files; Name: "{app}\{#Exe}"
Type: files; Name: "{app}\Server-Ordner.txt"
Type: dirifempty; Name: "{app}"
