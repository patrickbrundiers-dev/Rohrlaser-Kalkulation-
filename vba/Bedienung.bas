Attribute VB_Name = "Bedienung"
' Bedienung der Mappe: Menüband "Rohrlaser", neuer Auftrag, Auftragsablage, Stammdaten
' übernehmen und der Hinweis "Optimierung veraltet".
'
' Ablage: Aufträge und PDF-Dateien landen im Ordner "Aufträge" neben der Mappe. Ist die Mappe
' selbst schon eine abgelegte Auftragsmappe in diesem Ordner, wird derselbe Ordner verwendet.
'
' Optimierung veraltet: Listen!E5 = "ja", sobald sich etwas ändert, das die Optimierung
' beeinflusst (Auftrag C8:C9 und Positionen, Profile, Werkstoffe, Maschinen). Die Optimierung
' setzt den Wert auf "nein". Auftrag!C10 und Kalkulation!A10 zeigen den Stand an.
Option Explicit

Private Const O0 As Long = 13
Private Const O1 As Long = 512
Private Const S0 As Long = 5
Private Const S1 As Long = 1004
Private Const ORDNER_ABLAGE As String = "Aufträge"
Private Const STAMMBLAETTER As String = "Profile,Werkstoffe,Preise,Maschinen,Schneiddaten,Gewinde"


' ================================================================== Menüband (customUI)
Public Sub RbNeuerAuftrag(control As Object)
    NeuerAuftrag
End Sub

Public Sub RbStepImport(control As Object)
    StepImport.StepImportieren
End Sub

Public Sub RbOptimieren(control As Object)
    Optimierung.Optimieren
End Sub

Public Sub RbWerkstattpapiere(control As Object)
    Ausgabe.WerkstattpapiereDrucken
End Sub

Public Sub RbAngebot(control As Object)
    Ausgabe.AngebotDrucken
End Sub

Public Sub RbKalkulation(control As Object)
    Ausgabe.KalkulationDrucken
End Sub

Public Sub RbSpeichern(control As Object)
    AuftragSpeichernAls
End Sub

Public Sub RbStammdaten(control As Object)
    StammdatenUebernehmen
End Sub

Public Sub RbStaffelpreise(control As Object)
    Staffel.StaffelpreiseRechnen
End Sub


' ================================================================== Optimierung veraltet
' Aufruf aus Worksheet_Change der Blätter Auftrag, Profile, Werkstoffe und Maschinen.
Public Sub Geaendert(ByVal blatt As String, ByVal ziel As Range)
    Dim r As Range
    If blatt = "Auftrag" Then
        Set r = Application.Intersect(ziel, ziel.Worksheet.Range("C8:C9,A13:H512,J13:J512,Y13:AB512"))
    Else
        Set r = Application.Intersect(ziel, ziel.Worksheet.Range("A5:J304"))
    End If
    If Not r Is Nothing Then SetzeVeraltet True
End Sub

Public Sub SetzeVeraltet(ByVal veraltet As Boolean)
    Dim wert As String
    If veraltet Then wert = "ja" Else wert = "nein"
    With ThisWorkbook.Worksheets("Listen").Range("E5")
        If CStr(.Value) <> wert Then .Value = wert
    End With
End Sub

' True, wenn ein Schnittplan vorliegt und seitdem nichts geändert wurde.
Public Function OptimierungAktuell() As Boolean
    If Application.WorksheetFunction.Count(ThisWorkbook.Worksheets("Schnittplan").Range("A" & S0 & ":A" & S1)) = 0 Then
        Exit Function
    End If
    OptimierungAktuell = (CStr(ThisWorkbook.Worksheets("Listen").Range("E5").Value) <> "ja")
End Function

' Vor einer Ausgabe: bei veralteter oder fehlender Optimierung fragen, ob neu optimiert wird.
' Ergebnis False = abbrechen.
Public Function VorAusgabeOptimieren() As Boolean
    Dim antwort As VbMsgBoxResult
    If OptimierungAktuell() Then VorAusgabeOptimieren = True: Exit Function
    antwort = MsgBox("Der Schnittplan passt nicht mehr zum Auftrag (oder es wurde noch nicht optimiert)." & vbLf & vbLf & _
                     "Jetzt neu optimieren?" & vbLf & "Ja = optimieren, Nein = mit dem bisherigen Stand weiter", _
                     vbYesNoCancel + vbQuestion, "Optimierung veraltet")
    If antwort = vbCancel Then Exit Function
    If antwort = vbYes Then
        On Error GoTo Fehler
        Optimierung.OptimiereMappe
    End If
    VorAusgabeOptimieren = True
    Exit Function
Fehler:
    MsgBox "Optimierung abgebrochen:" & vbLf & Err.Description, vbExclamation, "Stangenoptimierung"
End Function


' ================================================================== Neuer Auftrag
Public Sub NeuerAuftrag()
    Dim antwort As VbMsgBoxResult
    antwort = MsgBox("Neuen Auftrag anlegen?" & vbLf & vbLf & _
                     "Positionen, Schnittplan, Auswertung, Werkstattpapier, Angebot und STEP-Protokoll werden geleert. " & _
                     "Stammdaten, Maschine und Stangenlänge bleiben." & vbLf & vbLf & _
                     "Aktuellen Auftrag vorher im Ordner """ & ORDNER_ABLAGE & """ speichern?" & vbLf & _
                     "Ja = erst speichern, Nein = ohne Speichern leeren", vbYesNoCancel + vbQuestion, "Neuer Auftrag")
    If antwort = vbCancel Then Exit Sub
    If antwort = vbYes Then
        If Not AuftragSpeichernAls() Then Exit Sub
    End If
    AuftragLeeren
    ThisWorkbook.Worksheets("Auftrag").Activate
    ThisWorkbook.Worksheets("Auftrag").Range("C5").Select
End Sub

' Leert den Auftrag ohne Rückfrage. Auftragsnummer wird hochgezählt, Datum = heute.
Public Sub AuftragLeeren()
    Dim wa As Worksheet, ws As Worksheet, letzte As Long, nr As String
    Application.ScreenUpdating = False
    Set wa = ThisWorkbook.Worksheets("Auftrag")
    nr = NaechsteNummer(CStr(wa.Range("C4").Value))
    wa.Range("A" & O0 & ":J" & O1).ClearContents
    wa.Range("Y" & O0 & ":AM" & O1).ClearContents
    wa.Range("AP" & O0 & ":AR" & O1).ClearContents
    wa.Range("C4").Value = AlsText(nr)
    wa.Range("C5").ClearContents
    wa.Range("C6").ClearContents
    wa.Range("C7").Value = Date

    Set ws = ThisWorkbook.Worksheets("Schnittplan")
    ws.Range("A" & S0 & ":F" & S1).ClearContents
    ws.Range("I" & S0 & ":I" & S1).ClearContents
    ws.Range("N" & S0 & ":P" & S1).ClearContents
    Set ws = ThisWorkbook.Worksheets("Stangenbelegung")
    letzte = ws.UsedRange.Row + ws.UsedRange.Rows.Count - 1
    If letzte >= 5 Then ws.Range("A5:L" & letzte).ClearContents
    Set ws = ThisWorkbook.Worksheets("Auswertung")
    letzte = ws.UsedRange.Row + ws.UsedRange.Rows.Count - 1
    If letzte >= 4 Then ws.Range(ws.Rows(4), ws.Rows(letzte)).Clear
    Set ws = ThisWorkbook.Worksheets("STEP-Import")
    letzte = ws.UsedRange.Row + ws.UsedRange.Rows.Count - 1
    If letzte >= 5 Then ws.Range(ws.Rows(5), ws.Rows(letzte)).ClearContents
    ThisWorkbook.Worksheets("Staffeln").Range("A5:C104").ClearContents
    Staffel.StaffelpreiseLeeren
    Ausgabe.WerkstattpapierLeeren
    Ausgabe.AngebotLeeren
    SetzeVeraltet False
    Application.ScreenUpdating = True
End Sub

' "A-2026-0007" -> "A-2026-0008": letzte Ziffernfolge um 1 erhöhen, Stellenzahl beibehalten.
Public Function NaechsteNummer(ByVal nr As String) As String
    Dim i As Long, j As Long, ziffern As String, neu As String
    i = Len(nr)
    Do While i >= 1
        If Mid$(nr, i, 1) Like "#" Then Exit Do
        i = i - 1
    Loop
    If i = 0 Then NaechsteNummer = nr: Exit Function
    j = i
    Do While j > 1
        If Not (Mid$(nr, j - 1, 1) Like "#") Then Exit Do
        j = j - 1
    Loop
    ziffern = Mid$(nr, j, i - j + 1)
    neu = CStr(CDbl(ziffern) + 1)
    If Len(neu) < Len(ziffern) Then neu = String$(Len(ziffern) - Len(neu), "0") & neu
    NaechsteNummer = Left$(nr, j - 1) & neu & Mid$(nr, i + 1)
End Function


' ================================================================== Ablage
' Ordner für Auftragsmappen und PDF-Dateien (wird bei Bedarf angelegt). "" = nicht möglich.
Public Function Ablageordner() As String
    Dim pfad As String, sep As String
    sep = Application.PathSeparator
    pfad = ThisWorkbook.Path
    If pfad = "" Then
        MsgBox "Die Mappe ist noch nicht gespeichert. Bitte zuerst speichern.", vbExclamation, "Ablage"
        Exit Function
    End If
    If LCase$(Left$(pfad, 4)) = "http" Then
        MsgBox "Die Mappe ist direkt aus OneDrive/SharePoint geöffnet (" & pfad & ")." & vbLf & _
               "Für die Ablage die Mappe in einen Ordner auf dem PC oder im Netzlaufwerk legen und von dort öffnen.", _
               vbExclamation, "Ablage"
        Exit Function
    End If
    If LCase$(Mid$(pfad, InStrRev(pfad, sep) + 1)) <> LCase$(ORDNER_ABLAGE) Then
        pfad = pfad & sep & ORDNER_ABLAGE
        If Len(Dir$(pfad, vbDirectory)) = 0 Then MkDir pfad
    End If
    Ablageordner = pfad
End Function

' Dateiname aus Auftragsnummer, Zusatz und Kundenname, ohne in Dateinamen verbotene Zeichen.
Public Function Dateiname(ByVal zusatz As String, Optional ByVal mitKunde As Boolean = False) As String
    Dim wa As Worksheet, s As String, i As Long, c As String
    Set wa = ThisWorkbook.Worksheets("Auftrag")
    s = Trim$(CStr(wa.Range("C4").Value))
    If s = "" Then s = "Auftrag"
    If mitKunde And Trim$(CStr(wa.Range("C6").Value)) <> "" Then s = s & " " & Trim$(CStr(wa.Range("C6").Value))
    If zusatz <> "" Then s = s & " " & zusatz
    For i = 1 To Len(s)
        c = Mid$(s, i, 1)
        If InStr("\/:*?""<>|", c) > 0 Or AscW(c) < 32 Then Mid$(s, i, 1) = "_"
    Next i
    Dateiname = Trim$(s)
End Function

' Speichert eine Kopie der Mappe als "<Auftragsnummer> <Kunde>.xlsm" im Ablageordner.
' Die geöffnete Mappe bleibt unverändert offen. Ergebnis True = gespeichert.
Public Function AuftragSpeichernAls() As Boolean
    Dim ordner As String, ziel As String
    If Trim$(CStr(ThisWorkbook.Worksheets("Auftrag").Range("C4").Value)) = "" Then
        MsgBox "Bitte zuerst die Auftragsnummer (Blatt Auftrag, C4) eintragen.", vbExclamation, "Auftrag speichern"
        Exit Function
    End If
    ordner = Ablageordner()
    If ordner = "" Then Exit Function
    ziel = ordner & Application.PathSeparator & Dateiname("", True) & ".xlsm"
    If LCase$(ziel) = LCase$(ThisWorkbook.FullName) Then
        ThisWorkbook.Save
        AuftragSpeichernAls = True
        Exit Function
    End If
    If Len(Dir$(ziel)) > 0 Then
        If MsgBox("Die Datei gibt es schon:" & vbLf & ziel & vbLf & vbLf & "Überschreiben?", _
                  vbYesNo + vbQuestion, "Auftrag speichern") <> vbYes Then Exit Function
    End If
    On Error GoTo Fehler
    ThisWorkbook.SaveCopyAs ziel
    MsgBox "Auftrag gespeichert:" & vbLf & ziel, vbInformation, "Auftrag speichern"
    AuftragSpeichernAls = True
    Exit Function
Fehler:
    MsgBox "Speichern nicht möglich:" & vbLf & Err.Description & vbLf & vbLf & _
           "Ist die Datei noch geöffnet?", vbExclamation, "Auftrag speichern"
End Function


' ================================================================== Stammdaten übernehmen
' Übernimmt Profile, Werkstoffe, Preise, Maschinen, Schneiddaten, Gewinde, Auswahllisten,
' Zuschläge und den Angebotskopf aus einer anderen Mappe (z. B. der aktuellen Vorlage).
Public Sub StammdatenUebernehmen()
    Dim datei As Variant, q As Workbook, bericht As String
    datei = Application.GetOpenFilename("Excel-Mappen (*.xlsm;*.xlsx),*.xlsm;*.xlsx", , _
                                        "Mappe mit den aktuellen Stammdaten wählen")
    If VarType(datei) = vbBoolean Then Exit Sub
    If LCase$(CStr(datei)) = LCase$(ThisWorkbook.FullName) Then
        MsgBox "Das ist diese Mappe selbst.", vbExclamation, "Stammdaten übernehmen"
        Exit Sub
    End If
    If MsgBox("Stammdaten dieser Mappe durch die aus" & vbLf & datei & vbLf & "ersetzen?" & vbLf & vbLf & _
              "Betrifft: " & Replace(STAMMBLAETTER, ",", ", ") & ", Auswahllisten, Zuschläge, Angebotskopf. " & _
              "Der Auftrag bleibt.", vbYesNo + vbQuestion, "Stammdaten übernehmen") <> vbYes Then Exit Sub
    On Error GoTo Fehler
    Application.ScreenUpdating = False
    Set q = Workbooks.Open(CStr(datei), 0, True)
    bericht = StammdatenKopieren(q)
    q.Close False
    Application.ScreenUpdating = True
    MsgBox bericht, vbInformation, "Stammdaten übernehmen"
    Exit Sub
Fehler:
    Application.ScreenUpdating = True
    If Not q Is Nothing Then q.Close False
    MsgBox "Übernahme abgebrochen:" & vbLf & Err.Description, vbExclamation, "Stammdaten übernehmen"
End Sub

' Kopiert die Eingabezellen (keine Formelzellen) der Stammdatenblätter aus q.
Public Function StammdatenKopieren(q As Workbook) As String
    Dim namen As Variant, i As Long, n As Long, bericht As String
    namen = Split(STAMMBLAETTER, ",")
    ' erst alles prüfen, dann kopieren
    For i = 0 To UBound(namen)
        PruefeKopf q, CStr(namen(i))
    Next i
    For i = 0 To UBound(namen)
        n = BereichKopieren(q, CStr(namen(i)), "A5:Z304")
        bericht = bericht & namen(i) & ": " & n & " Zeilen" & vbLf
    Next i
    BereichKopieren q, "Listen", "A5:C20"
    BereichKopieren q, "Kalkulation", "C4:C6"
    BereichKopieren q, "Angebot", "A1:A4"
    BereichKopieren q, "Angebot", "C11:C12"
    BereichKopieren q, "Angebot", "F10:F10"
    SetzeVeraltet True
    StammdatenKopieren = "Stammdaten übernommen aus " & q.Name & ":" & vbLf & bericht & vbLf & _
                         "Bitte neu optimieren und die Kalkulation prüfen."
End Function

Private Sub PruefeKopf(q As Workbook, ByVal blatt As String)
    Dim a As Variant, b As Variant, j As Long, ws As Worksheet
    On Error Resume Next
    Set ws = q.Worksheets(blatt)
    On Error GoTo 0
    If ws Is Nothing Then Err.Raise vbObjectErrorBasis + 10, , "Blatt '" & blatt & "' fehlt in " & q.Name
    a = ws.Range("A4:Z4").Value
    b = ThisWorkbook.Worksheets(blatt).Range("A4:Z4").Value
    For j = 1 To 26
        If CStr(a(1, j)) <> CStr(b(1, j)) Then
            Err.Raise vbObjectErrorBasis + 11, , "Blatt '" & blatt & "' hat in " & q.Name & " andere Spalten (" & _
                      CStr(a(1, j)) & " statt " & CStr(b(1, j)) & "). Mappen-Versionen passen nicht zusammen."
        End If
    Next j
End Sub

' Ergebnis: Anzahl nicht leerer Zeilen (Spalte A) im Ziel.
Private Function BereichKopieren(q As Workbook, ByVal blatt As String, ByVal adresse As String) As Long
    Dim quelle As Variant, f As Variant, i As Long, j As Long, v As Variant, ws As Worksheet
    Set ws = q.Worksheets(blatt)
    quelle = ws.Range(adresse).Value
    f = ThisWorkbook.Worksheets(blatt).Range(adresse).Formula
    If Not IsArray(quelle) Then
        Dim q1(1 To 1, 1 To 1) As Variant, f1(1 To 1, 1 To 1) As Variant
        q1(1, 1) = quelle: f1(1, 1) = f
        quelle = q1: f = f1
    End If
    For i = 1 To UBound(f, 1)
        For j = 1 To UBound(f, 2)
            If Left$(CStr(f(i, j)), 1) <> "=" Then
                v = quelle(i, j)
                If IsError(v) Or IsEmpty(v) Then
                    f(i, j) = ""
                ElseIf VarType(v) = vbString Then
                    If Len(v) > 0 Then f(i, j) = "'" & v Else f(i, j) = ""
                ElseIf VarType(v) = vbDate Then
                    f(i, j) = CDbl(v)
                Else
                    f(i, j) = v
                End If
            End If
        Next j
        If Len(CStr(quelle(i, 1))) > 0 Then BereichKopieren = BereichKopieren + 1
    Next i
    ThisWorkbook.Worksheets(blatt).Range(adresse).Formula = f
End Function

Private Function vbObjectErrorBasis() As Long
    vbObjectErrorBasis = -2147221504   ' vbObjectError (in LibreOffice nicht definiert)
End Function

' Text als Text eintragen: Excel würde z. B. "1.4301" sonst in eine Zahl umwandeln.
Private Function AlsText(ByVal v As String) As String
    If Len(v) > 0 Then AlsText = "'" & v
End Function


' ================================================================== Tests (ohne Meldungsfenster)
Public Function NeuerAuftragTest() As String
    On Error GoTo Fehler
    AuftragLeeren
    NeuerAuftragTest = "OK " & ThisWorkbook.Worksheets("Auftrag").Range("C4").Value
    Exit Function
Fehler:
    NeuerAuftragTest = "FEHLER " & Err.Number & ": " & Err.Description
End Function

Public Function StammdatenTest(ByVal datei As String) As String
    Dim q As Workbook
    On Error GoTo Fehler
    Set q = Workbooks.Open(datei, 0, True)
    StammdatenTest = StammdatenKopieren(q)
    q.Close False
    Exit Function
Fehler:
    StammdatenTest = "FEHLER " & Err.Number & ": " & Err.Description
End Function

Public Function GeaendertTest() As String
    Dim a As String
    SetzeVeraltet False
    Geaendert "Auftrag", ThisWorkbook.Worksheets("Auftrag").Range("C4")
    a = ThisWorkbook.Worksheets("Listen").Range("E5").Value
    Geaendert "Auftrag", ThisWorkbook.Worksheets("Auftrag").Range("F20")
    GeaendertTest = a & "," & ThisWorkbook.Worksheets("Listen").Range("E5").Value
End Function
