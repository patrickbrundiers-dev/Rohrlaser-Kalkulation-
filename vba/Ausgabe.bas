Attribute VB_Name = "Ausgabe"
' Ausgabe als PDF: Werkstattpapiere (Schnittplan je Stange), Angebot und Kalkulation.
'
' Werkstattpapier: Materialliste je Profil/Werkstoff/Stangenlänge, danach je Stangenmuster
' ein Block mit den Teilen in Schnittreihenfolge. Gleich belegte Stangen (gleiche Teile in
' gleicher Reihenfolge und Lage) stehen nur einmal da, mit ihren Stangennummern.
' Angebot: Positionen mit Verkaufspreis je Teil aus dem Blatt Kalkulation (auf Cent gerundet).
' Die PDF-Dateien landen im Ablageordner (siehe Modul Bedienung).
Option Explicit

Private Const O0 As Long = 13
Private Const O1 As Long = 512
Private Const S0 As Long = 5
Private Const S1 As Long = 1004
Private Const D0 As Long = 5
Private Const A0 As Long = 14              ' erste Positionszeile im Blatt Angebot
Private Const ZEILEN_JE_SEITE As Long = 50 ' Werkstattpapier: Blöcke nicht über Seitenwechsel teilen


' ================================================================== Schaltflächen
Public Sub WerkstattpapiereDrucken()
    Dim ws As Worksheet, n As Long
    If Not Bedienung.VorAusgabeOptimieren() Then Exit Sub
    n = WerkstattpapierFuellen()
    If n = 0 Then MsgBox "Der Schnittplan ist leer.", vbExclamation, "Werkstattpapiere": Exit Sub
    Set ws = ThisWorkbook.Worksheets("Werkstattpapier")
    ws.PageSetup.PrintArea = ws.Range("A1:J" & n).Address
    PdfSpeichern ws, "Werkstattpapiere"
End Sub

Public Sub AngebotDrucken()
    Dim ws As Worksheet, n As Long, hinweise As Long
    If Not Bedienung.VorAusgabeOptimieren() Then Exit Sub
    n = AngebotFuellen(hinweise)
    If n = 0 Then MsgBox "Der Auftrag hat keine Positionen.", vbExclamation, "Angebot": Exit Sub
    If hinweise > 0 Then
        If MsgBox(hinweise & " Position(en) haben einen Hinweis im Blatt Kalkulation (Spalte W), " & _
                  "z. B. kein Preis oder nicht eingeplant." & vbLf & vbLf & "Angebot trotzdem erstellen?", _
                  vbYesNo + vbExclamation, "Angebot") <> vbYes Then
            ThisWorkbook.Worksheets("Kalkulation").Activate
            Exit Sub
        End If
    End If
    Set ws = ThisWorkbook.Worksheets("Angebot")
    ws.PageSetup.PrintArea = ws.Range("A1:I" & n).Address
    PdfSpeichern ws, "Angebot"
End Sub

Public Sub KalkulationDrucken()
    Dim ws As Worksheet, letzte As Long
    If Not Bedienung.VorAusgabeOptimieren() Then Exit Sub
    Set ws = ThisWorkbook.Worksheets("Kalkulation")
    letzte = LetzteZeile(ThisWorkbook.Worksheets("Auftrag").Range("D" & O0 & ":D" & O1), O0)
    If letzte < O0 Then letzte = O0
    ws.PageSetup.PrintArea = ws.Range("A1:Y" & letzte).Address
    PdfSpeichern ws, "Kalkulation"
End Sub

' Letzte Zeile mit Inhalt in einem einspaltigen Bereich, der in Zeile erste beginnt.
Private Function LetzteZeile(bereich As Range, ByVal erste As Long) As Long
    Dim v As Variant, i As Long
    v = bereich.Value
    LetzteZeile = erste - 1
    For i = UBound(v, 1) To 1 Step -1
        If Len(CStr(v(i, 1))) > 0 Then LetzteZeile = erste + i - 1: Exit Function
    Next i
End Function

Private Sub PdfSpeichern(ws As Worksheet, ByVal art As String)
    Dim ordner As String, ziel As String
    ordner = Bedienung.Ablageordner()
    If ordner = "" Then Exit Sub
    ziel = ordner & Application.PathSeparator & Bedienung.Dateiname(art) & ".pdf"
    On Error GoTo Fehler
    ws.ExportAsFixedFormat Type:=0, Filename:=ziel, Quality:=0, IncludeDocProperties:=True, _
                           IgnorePrintAreas:=False, OpenAfterPublish:=True
    Exit Sub
Fehler:
    MsgBox "PDF konnte nicht gespeichert werden:" & vbLf & ziel & vbLf & vbLf & Err.Description & vbLf & _
           "Ist die Datei noch in einem PDF-Programm geöffnet?", vbExclamation, art
End Sub


' ================================================================== Werkstattpapier
Public Sub WerkstattpapierLeeren()
    With ThisWorkbook.Worksheets("Werkstattpapier")
        .Cells.Clear
        On Error Resume Next
        .ResetAllPageBreaks
    End With
End Sub

' Füllt das Blatt Werkstattpapier aus Schnittplan und Stangenbelegung.
' Ergebnis: letzte beschriebene Zeile (0 = kein Schnittplan).
Public Function WerkstattpapierFuellen() As Long
    Dim ws As Worksheet, wa As Worksheet, sp As Variant, dt As Variant, bez As Variant
    Dim nS As Long, nD As Long, s As Long, i As Long, k As Long, r As Long, m As Long
    Dim erste() As Long, anzahlT() As Long, schl() As String, muster() As Long, nM As Long
    Dim mNr() As String, mAnz() As Long, mStange() As Long, hoehe As Long, aufSeite As Long
    Dim zeile As Long, letzteD As Long

    Set ws = ThisWorkbook.Worksheets("Werkstattpapier")
    Set wa = ThisWorkbook.Worksheets("Auftrag")
    WerkstattpapierLeeren
    sp = ThisWorkbook.Worksheets("Schnittplan").Range("A" & S0 & ":R" & S1).Value
    For s = 1 To UBound(sp, 1)
        If Not IsNumeric(sp(s, 1)) Or IsEmpty(sp(s, 1)) Then Exit For
        nS = s
    Next s
    If nS = 0 Then Exit Function
    With ThisWorkbook.Worksheets("Stangenbelegung")
        letzteD = .UsedRange.Row + .UsedRange.Rows.Count - 1
        If letzteD < D0 Then Exit Function
        dt = .Range("A" & D0 & ":L" & letzteD).Value
    End With
    bez = wa.Range("C" & O0 & ":C" & O1).Value

    ' Teile je Stange (Stangenbelegung ist nach Stange und Platz sortiert)
    ReDim erste(1 To nS): ReDim anzahlT(1 To nS): ReDim schl(1 To nS)
    For i = 1 To UBound(dt, 1)
        If IsEmpty(dt(i, 1)) Then Exit For
        nD = i
        s = dt(i, 1)
        If s >= 1 And s <= nS Then
            If anzahlT(s) = 0 Then erste(s) = i
            anzahlT(s) = anzahlT(s) + 1
            schl(s) = schl(s) & "|" & dt(i, 5) & ":" & dt(i, 6) & ":" & dt(i, 9)
        End If
    Next i
    ' gleiche Stangenmuster zusammenfassen
    ReDim muster(1 To nS): ReDim mNr(1 To nS): ReDim mAnz(1 To nS): ReDim mStange(1 To nS)
    For s = 1 To nS
        schl(s) = sp(s, 2) & "|" & sp(s, 3) & "|" & sp(s, 4) & schl(s)
        For m = 1 To nM
            If schl(mStange(m)) = schl(s) Then Exit For
        Next m
        If m > nM Then nM = m: mStange(m) = s
        muster(s) = m
        mAnz(m) = mAnz(m) + 1
    Next s
    For m = 1 To nM
        mNr(m) = Nummern(muster, nS, m)
    Next m

    ' Kopf
    Application.ScreenUpdating = False
    ws.Cells.Font.Name = "Arial"
    ws.Cells.Font.Size = 10
    ws.Cells.RowHeight = 15
    ws.Range("A1").Value = "Werkstattpapiere – Schnittpläne"
    ws.Range("A1").Font.Size = 14: ws.Range("A1").Font.Bold = True
    ws.Range("A2").Value = AlsText("Auftrag " & wa.Range("C4").Value & "   |   Kunde " & wa.Range("C6").Value & _
                                   "   |   Maschine " & wa.Range("C8").Value & "   |   erstellt " & _
                                   Format$(Now, "dd.mm.yyyy") & " " & Format$(Now, "hh:mm"))
    If Not Bedienung.OptimierungAktuell() Then
        ws.Range("A3").Value = "ACHTUNG: Schnittplan passt nicht zum aktuellen Auftrag (Optimierung veraltet)."
        ws.Range("A3").Font.Bold = True: ws.Range("A3").Font.Color = RGB(192, 0, 0)
    End If

    ' Materialliste
    r = 5
    ws.Cells(r, 1).Value = "Materialliste": ws.Cells(r, 1).Font.Bold = True: ws.Cells(r, 1).Font.Size = 12
    r = r + 1
    Kopf ws, r, Array("Profil-ID", "", "Werkstoff-ID", "", "Stangenlänge [mm]", "Stangen [Stk]", "Gewicht [kg]")
    ws.Range(ws.Cells(r, 1), ws.Cells(r, 2)).Merge
    ws.Range(ws.Cells(r, 3), ws.Cells(r, 4)).Merge
    k = r
    For s = 1 To nS
        For i = k + 1 To r
            If ws.Cells(i, 1).Value = CStr(sp(s, 2)) And ws.Cells(i, 3).Value = CStr(sp(s, 3)) And _
               ws.Cells(i, 5).Value = sp(s, 4) Then Exit For
        Next i
        If i > r Then
            r = r + 1
            ws.Cells(r, 1).Value = AlsText(sp(s, 2)): ws.Cells(r, 3).Value = AlsText(sp(s, 3))
            ws.Cells(r, 5).Value = sp(s, 4): ws.Cells(r, 6).Value = 0: ws.Cells(r, 7).Value = 0
            ws.Range(ws.Cells(r, 1), ws.Cells(r, 2)).Merge
            ws.Range(ws.Cells(r, 3), ws.Cells(r, 4)).Merge
            i = r
        End If
        ws.Cells(i, 6).Value = ws.Cells(i, 6).Value + 1
        If IsNumeric(sp(s, 17)) And Not IsEmpty(sp(s, 17)) Then ws.Cells(i, 7).Value = ws.Cells(i, 7).Value + sp(s, 17)
    Next s
    Rahmen ws.Range(ws.Cells(k, 1), ws.Cells(r, 7))
    ws.Range(ws.Cells(k + 1, 5), ws.Cells(r, 6)).NumberFormat = "#,##0"
    ws.Range(ws.Cells(k + 1, 7), ws.Cells(r, 7)).NumberFormat = "#,##0.0"
    r = r + 2
    aufSeite = r - 1

    ' je Stangenmuster ein Block
    For m = 1 To nM
        s = mStange(m)
        hoehe = anzahlT(s) + 4
        If aufSeite + hoehe > ZEILEN_JE_SEITE And aufSeite > 0 Then
            On Error Resume Next
            ws.HPageBreaks.Add ws.Cells(r, 1)
            On Error GoTo 0
            aufSeite = 0
        End If
        With ws.Range(ws.Cells(r, 1), ws.Cells(r, 10))
            .Interior.Color = RGB(221, 235, 247)
            .Font.Bold = True
        End With
        If mAnz(m) = 1 Then
            ws.Cells(r, 1).Value = AlsText("Stange " & mNr(m))
        Else
            ws.Cells(r, 1).Value = AlsText("Stangen " & mNr(m) & "  (" & mAnz(m) & " Stück gleich)")
        End If
        ws.Cells(r, 1).Font.Size = 12
        r = r + 1
        ws.Cells(r, 1).Value = AlsText(sp(s, 2) & "  |  " & sp(s, 3) & "  |  Stange " & Format$(sp(s, 4), "#,##0") & _
                                       " mm  |  Endbeschnitt " & Format$(sp(s, 5), "0.0") & " mm  |  Greiferrest " & _
                                       Format$(sp(s, 6), "0.0") & " mm  |  Rest " & ZahlOderText(sp(s, 11), "#,##0.0") & _
                                       " mm  |  Ausnutzung " & ZahlOderText(sp(s, 12), "0.0%"))
        r = r + 1
        Kopf ws, r, Array("Platz", "Pos.", "Artikelnummer", "Bezeichnung", "Länge [mm]", "Von [mm]", "Bis [mm]", _
                          "Lage", "Trennung zum Vorgänger", "erledigt")
        k = r
        For i = erste(s) To erste(s) + anzahlT(s) - 1
            r = r + 1
            ws.Cells(r, 1).Value = dt(i, 2)
            ws.Cells(r, 2).Value = AlsText(dt(i, 3))
            ws.Cells(r, 3).Value = AlsText(dt(i, 4))
            zeile = 0
            If IsNumeric(dt(i, 5)) And Not IsEmpty(dt(i, 5)) Then zeile = dt(i, 5)
            If zeile >= O0 And zeile <= O1 Then ws.Cells(r, 4).Value = AlsText(bez(zeile - O0 + 1, 1))
            ws.Cells(r, 5).Value = dt(i, 6)
            ws.Cells(r, 6).Value = dt(i, 7)
            ws.Cells(r, 7).Value = dt(i, 8)
            ws.Cells(r, 8).Value = AlsText(dt(i, 9))
            ws.Cells(r, 9).Value = AlsText(dt(i, 10))
        Next i
        Rahmen ws.Range(ws.Cells(k, 1), ws.Cells(r, 10))
        ws.Range(ws.Cells(k + 1, 5), ws.Cells(r, 7)).NumberFormat = "#,##0.0"
        ws.Range(ws.Cells(k + 1, 1), ws.Cells(r, 1)).HorizontalAlignment = -4108   ' xlCenter
        ws.Range(ws.Cells(k + 1, 8), ws.Cells(r, 8)).HorizontalAlignment = -4108
        r = r + 2
        aufSeite = aufSeite + hoehe
    Next m
    Application.ScreenUpdating = True
    WerkstattpapierFuellen = r - 2
End Function

' Stangennummern eines Musters kompakt: "1–3, 7"
Private Function Nummern(muster() As Long, ByVal n As Long, ByVal m As Long) As String
    Dim s As Long, von As Long, s2 As Long, txt As String
    s = 1
    Do While s <= n
        If muster(s) = m Then
            von = s: s2 = s
            Do While s2 < n
                If muster(s2 + 1) <> m Then Exit Do
                s2 = s2 + 1
            Loop
            If Len(txt) > 0 Then txt = txt & ", "
            If s2 > von Then txt = txt & von & ChrW(8211) & s2 Else txt = txt & von
            s = s2 + 1
        Else
            s = s + 1
        End If
    Loop
    Nummern = txt
End Function


' ================================================================== Angebot
Public Sub AngebotLeeren()
    Dim ws As Worksheet, letzte As Long
    Set ws = ThisWorkbook.Worksheets("Angebot")
    letzte = ws.UsedRange.Row + ws.UsedRange.Rows.Count - 1
    If letzte >= A0 Then ws.Range(ws.Rows(A0), ws.Rows(letzte)).Clear
End Sub

' Füllt die Positionen des Angebots aus Auftrag und Kalkulation.
' Ergebnis: letzte beschriebene Zeile (0 = keine Positionen); hinweise = Positionen mit Hinweis.
Public Function AngebotFuellen(hinweise As Long) As Long
    Dim ws As Worksheet, av As Variant, kv As Variant, i As Long, r As Long, preis As Double, menge As Double
    Dim w As Variant
    Set ws = ThisWorkbook.Worksheets("Angebot")
    Application.Calculate
    AngebotLeeren
    av = ThisWorkbook.Worksheets("Auftrag").Range("A" & O0 & ":G" & O1).Value
    kv = ThisWorkbook.Worksheets("Kalkulation").Range("A" & O0 & ":W" & O1).Value
    hinweise = 0
    r = A0 - 1
    For i = 1 To UBound(av, 1)
        If Len(CStr(av(i, 4))) > 0 Then
            r = r + 1
            ws.Cells(r, 1).Value = AlsText(av(i, 1))
            ws.Cells(r, 2).Value = AlsText(av(i, 2))
            ws.Cells(r, 3).Value = AlsText(av(i, 3))
            ws.Cells(r, 4).Value = AlsText(av(i, 4))
            ws.Cells(r, 5).Value = AlsText(av(i, 5))
            ws.Cells(r, 6).Value = av(i, 6)
            ws.Cells(r, 7).Value = av(i, 7)
            w = kv(i, 20)
            preis = 0: menge = 0
            If Not IsError(w) Then
                If IsNumeric(w) And Not IsEmpty(w) Then preis = Round(CDbl(w), 2)
            End If
            If IsNumeric(av(i, 7)) And Not IsEmpty(av(i, 7)) Then menge = CDbl(av(i, 7))
            ws.Cells(r, 8).Value = preis
            ws.Cells(r, 9).Value = Round(preis * menge, 2)
            w = kv(i, 23)
            If IsError(w) Then
                hinweise = hinweise + 1
            ElseIf Len(CStr(w)) > 0 Then
                hinweise = hinweise + 1
            End If
        End If
    Next i
    If r < A0 Then Exit Function
    Rahmen ws.Range(ws.Cells(A0, 1), ws.Cells(r, 9))
    ws.Range(ws.Cells(A0, 6), ws.Cells(r, 6)).NumberFormat = "#,##0.0"
    ws.Range(ws.Cells(A0, 7), ws.Cells(r, 7)).NumberFormat = "#,##0"
    ws.Range(ws.Cells(A0, 8), ws.Cells(r, 9)).NumberFormat = "#,##0.00"
    ws.Range(ws.Cells(A0, 1), ws.Cells(r, 9)).Font.Name = "Arial"
    ws.Cells(r + 2, 7).Value = "Summe netto [€]"
    ws.Cells(r + 2, 9).Formula = "=SUM(I" & A0 & ":I" & r & ")"
    ws.Cells(r + 3, 7).Value = "zzgl. MwSt. [€]"
    ws.Cells(r + 3, 9).Formula = "=ROUND(I" & (r + 2) & "*$C$11,2)"
    ws.Cells(r + 4, 7).Value = "Gesamtbetrag [€]"
    ws.Cells(r + 4, 9).Formula = "=I" & (r + 2) & "+I" & (r + 3)
    With ws.Range(ws.Cells(r + 2, 7), ws.Cells(r + 4, 9))
        .Font.Name = "Arial"
        .Font.Bold = True
    End With
    ws.Range(ws.Cells(r + 2, 9), ws.Cells(r + 4, 9)).NumberFormat = "#,##0.00"
    ws.Range(ws.Cells(r + 4, 7), ws.Cells(r + 4, 9)).Borders(8).LineStyle = 1   ' xlEdgeTop
    AngebotFuellen = r + 4
End Function


' ================================================================== Hilfen
Private Sub Kopf(ws As Worksheet, ByVal r As Long, texte As Variant)
    Dim j As Long
    For j = 0 To UBound(texte)
        With ws.Cells(r, j + 1)
            .Value = texte(j)
            .Font.Bold = True
            .Font.Color = RGB(255, 255, 255)
            .Interior.Color = RGB(31, 78, 120)
            .WrapText = True
            .VerticalAlignment = -4108
        End With
    Next j
    ws.Rows(r).RowHeight = 27
End Sub

Private Sub Rahmen(b As Range)
    With b.Borders
        .LineStyle = 1
        .Color = RGB(191, 191, 191)
    End With
End Sub

Private Function ZahlOderText(v As Variant, ByVal fmt As String) As String
    If IsError(v) Then
        ZahlOderText = "?"
    ElseIf IsNumeric(v) And Not IsEmpty(v) Then
        ZahlOderText = Format$(v, fmt)
    Else
        ZahlOderText = CStr(v)
    End If
End Function

' Text als Text eintragen: Excel würde z. B. "1.4301" sonst in eine Zahl umwandeln.
Private Function AlsText(ByVal v As Variant) As Variant
    If IsError(v) Then
        AlsText = ""
    ElseIf VarType(v) = vbString Then
        If Len(v) > 0 Then AlsText = "'" & v Else AlsText = ""
    Else
        AlsText = v
    End If
End Function


' ================================================================== Tests (ohne Meldungsfenster)
Public Function AusgabeTest() As String
    Dim h As Long
    On Error GoTo Fehler
    AusgabeTest = "OK " & WerkstattpapierFuellen() & " " & AngebotFuellen(h) & " " & h
    Exit Function
Fehler:
    AusgabeTest = "FEHLER " & Err.Number & ": " & Err.Description & " (Zeile " & Erl & ")"
End Function
