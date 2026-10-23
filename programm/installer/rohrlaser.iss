; Installationsprogramm (Inno Setup 6) für Rohrlaser-Angebotskalkulation: dieselben Programmdateien wie im ZIP,
; installiert nur für den angemeldeten Benutzer (keine Administratorrechte) nach
; %LOCALAPPDATA%\Programs\Rohrlaser Angebotskalkulation. Dort darf das Programm schreiben, das Online-Update
; funktioniert also wie in der portablen Version.
; Die Daten legt das Programm selbst in %LOCALAPPDATA%\Rohrlaser Angebotskalkulation\Daten an (orte.py), also
; außerhalb des Programmordners: Deinstallieren und Neuinstallieren lassen sie unberührt.
; Aufruf im Build (paket.yml):
;   ISCC.exe /DVersion=0.4.0.123 /DQuelle=dist\Rohrlaser-Angebotskalkulation /DAusgabe=. programm\installer\rohrlaser.iss
; Mit /DSignieren und /Ssignieren="signtool.exe sign … $f" signiert Inno Setup das Setup und den Uninstaller.

#ifndef Version
  #define Version "0.0.0"
#endif
#ifndef Quelle
  #define Quelle "..\..\dist\Rohrlaser-Angebotskalkulation"
#endif
#ifndef Ausgabe
  #define Ausgabe "..\..\dist"
#endif
#define Name "Rohrlaser Angebotskalkulation"
#define Exe "Rohrlaser-Angebotskalkulation.exe"

[Setup]
; feste Kennung: jede neue Version installiert über die alte (gleicher Ordner, ein Eintrag unter „Apps“)
AppId={{8F3C2B71-5D4E-4A8B-9C1F-2E7D6A5B4C30}
AppName={#Name}
AppVersion={#Version}
AppVerName={#Name} {#Version}
AppPublisher=Patrick Brundiers
VersionInfoVersion={#Version}
VersionInfoCompany=Patrick Brundiers
VersionInfoProductName={#Name}
VersionInfoDescription={#Name} – Installation
PrivilegesRequired=lowest
DefaultDirName={autopf}\{#Name}
DefaultGroupName={#Name}
DisableProgramGroupPage=yes
DisableDirPage=auto
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir={#Ausgabe}
OutputBaseFilename=Rohrlaser-Angebotskalkulation-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\{#Exe}
UninstallDisplayName={#Name}
; läuft das Programm noch, bietet das Setup an, es zu schließen (die Daten sichert das Programm beim Beenden)
CloseApplications=yes
RestartApplications=no
ShowLanguageDialog=no
SetupLogging=yes
#ifdef Signieren
SignTool=signieren
#endif

[Languages]
Name: "de"; MessagesFile: "compiler:Languages\German.isl"

[Tasks]
Name: "desktop"; Description: "Verknüpfung auf dem Desktop anlegen"

[Files]
; alles aus dem Programmordner außer Portabel.ini (nur im ZIP) und Ordnern mit Daten oder Update-Resten
Source: "{#Quelle}\*"; DestDir: "{app}"; Excludes: "\Portabel.ini,\Daten,\Angebote,\_update"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#Name}"; Filename: "{app}\{#Exe}"
Name: "{autoprograms}\{#Name} – Bedienungsanleitung"; Filename: "{app}\Bedienungsanleitung.pdf"
Name: "{autoprograms}\{#Name} – Kurzanleitung"; Filename: "{app}\Kurzanleitung.pdf"
Name: "{autodesktop}\{#Name}"; Filename: "{app}\{#Exe}"; Tasks: desktop

[Run]
Filename: "{app}\{#Exe}"; Description: "Programm jetzt starten"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; auch Programmdateien, die erst ein Online-Update gebracht hat; nie Daten (die liegen nicht im Programmordner)
Type: filesandordirs; Name: "{app}\_internal"
Type: filesandordirs; Name: "{app}\STEP-Import"
Type: filesandordirs; Name: "{app}\_update"
Type: files; Name: "{app}\Update.json"
Type: files; Name: "{app}\Update.json.neu"
Type: files; Name: "{app}\{#Exe}"
Type: files; Name: "{app}\Bedienungsanleitung.pdf"
Type: files; Name: "{app}\Kurzanleitung.pdf"
Type: dirifempty; Name: "{app}"
