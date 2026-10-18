Attribute VB_Name = "Ausgabe"
' Ausgabe als PDF: Werkstattpapiere (Schnittplan je Stange), Angebot und Kalkulation.
'
' Werkstattpapier: Materialliste je Profil/Werkstoff/Stangenlänge, danach je Stangenmuster
' ein Block mit den Teilen in Schnittreihenfolge. Gleich belegte Stangen (gleiche Teile in
' gleicher Reihenfolge und Lage) stehen nur einmal da, mit ihren Stangennummern.
' Stangenbild: je Stangenmuster ein maßstäblicher Balken (Endbeschnitt, Teile, Schnitte, Rest,
' Greiferrest), gleiche Muster wie im Werkstattpapier zusammengefasst.
' Angebot: Positionen mit Verkaufspreis je Teil aus dem Blatt Kalkulation (auf Cent gerundet).
' Die PDF-Dateien landen im Ablageordner (siehe Modul Bedienung).
Option Explicit

Private Const M0 As Long = 5
Private Const M1 As Long = 304
Private Const O0 As Long = 13
Private Const O1 As Long = 512
Private Const S0 As Long = 5
Private Const S1 As Long = 1004
Private Const D0 As Long = 5
Private Const A0 As Long = 14              ' erste Positionszeile im Blatt Angebot
Private Const P0 As Long = 5               ' erste Zeile im Blatt Staffelpreise
Private Const ZEILEN_JE_SEITE As Long = 50 ' Werkstattpapier: Blöcke nicht über Seitenwechsel teilen
Private Const BILD_ZELLEN As Long = 120     ' Stangenbild: Zellen je Stange (Maßstab Stangenlänge / 120)
Private Const BILD_SPALTE As Long = 2       ' Stangenbild: erste Spalte des Balkens
Private Const BILDER_JE_SEITE As Long = 10  ' Stangenbild: Stangen je Druckseite

' Schnittplan und Stangenbelegung, gelesen von StangenLesen (für Werkstattpapier und Stangenbild)
Private gSp As Variant, gDt As Variant, gNS As Long, gNM As Long
Private gErste() As Long, gAnzT() As Long, gMuster() As Long, gMStange() As Long, gMAnz() As Long
Private gMNr() As String


' ================================================================== Schaltflächen
Public Sub WerkstattpapiereDrucken()
    Dim ws As Worksheet, n As Long
    If Not Bedienung.VorAusgabeOptimieren() Then Exit Sub
    n = WerkstattpapierFuellen()
    If n = 0 Then MsgBox "Der Schnittplan ist leer.", vbExclamation, "Werkstattpapiere": Exit Sub
    Set ws = ThisWorkbook.Worksheets("Werkstattpapier")
    ws.PageSetup.PrintArea = ws.Range("A1:J" & n).Address
    n = StangenbildFuellen()
    With ThisWorkbook.Worksheets("Stangenbild")
        .PageSetup.PrintArea = .Range(.Cells(1, 1), .Cells(n, BILD_SPALTE + BILD_ZELLEN)).Address
    End With
    PdfSpeichern ws, "Werkstattpapiere", "Stangenbild"
End Sub

Public Sub StangenbildZeigen()
    If Not Bedienung.VorAusgabeOptimieren() Then Exit Sub
    If StangenbildFuellen() = 0 Then MsgBox "Der Schnittplan ist leer. Bitte zuerst optimieren.", vbExclamation, "Stangenbild": Exit Sub
    ThisWorkbook.Worksheets("Stangenbild").Activate
    ThisWorkbook.Worksheets("Stangenbild").Range("A1").Select
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
    ws.PageSetup.PrintArea = ws.Range("A1:F" & n).Address
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

' Speichert ws als PDF; mit zweitesBlatt kommen beide Blätter in eine Datei.
Private Sub PdfSpeichern(ws As Worksheet, ByVal art As String, Optional ByVal zweitesBlatt As String = "")
    Dim ordner As String, ziel As String
    ordner = Bedienung.Ablageordner()
    If ordner = "" Then Exit Sub
    ziel = ordner & Application.PathSeparator & Bedienung.Dateiname(art) & ".pdf"
    On Error GoTo Fehler
    If zweitesBlatt <> "" Then
        ' mehrere ausgewählte Blätter landen gemeinsam in einer PDF-Datei
        ThisWorkbook.Activate
        ThisWorkbook.Worksheets(Array(ws.Name, zweitesBlatt)).Select
        ActiveSheet.ExportAsFixedFormat Type:=0, Filename:=ziel, Quality:=0, IncludeDocProperties:=True, _
                                        IgnorePrintAreas:=False, OpenAfterPublish:=True
        ws.Select
    Else
        ws.ExportAsFixedFormat Type:=0, Filename:=ziel, Quality:=0, IncludeDocProperties:=True, _
                               IgnorePrintAreas:=False, OpenAfterPublish:=True
    End If
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
    Dim nS As Long, s As Long, i As Long, k As Long, r As Long, m As Long
    Dim hoehe As Long, aufSeite As Long, zeile As Long

    Set ws = ThisWorkbook.Worksheets("Werkstattpapier")
    Set wa = ThisWorkbook.Worksheets("Auftrag")
    WerkstattpapierLeeren
    nS = StangenLesen()
    If nS = 0 Then Exit Function
    sp = gSp: dt = gDt
    bez = wa.Range("C" & O0 & ":C" & O1).Value

    ' Kopf
    Application.ScreenUpdating = False
    ws.Cells.Font.Name = "Arial"
    ws.Cells.Font.Size = 10
    ws.Cells.RowHeight = 15
    Spaltenbreiten ws, Array(7, 7, 18, 24, 11, 11, 11, 9, 20, 9)
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
    Kopf ws, r, Array("Profil-ID", "", "Werkstoff-ID", "", "Stange [mm]", "Stangen [Stk]", "Gewicht [kg]")
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
    For m = 1 To gNM
        s = gMStange(m)
        hoehe = gAnzT(s) + 4
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
        If gMAnz(m) = 1 Then
            ws.Cells(r, 1).Value = AlsText("Stange " & gMNr(m))
        Else
            ws.Cells(r, 1).Value = AlsText("Stangen " & gMNr(m) & "  (" & gMAnz(m) & " Stück gleich)")
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
        For i = gErste(s) To gErste(s) + gAnzT(s) - 1
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
        ws.Range(ws.Cells(k + 1, 1), ws.Cells(r, 2)).HorizontalAlignment = -4108   ' xlCenter
        ws.Range(ws.Cells(k + 1, 8), ws.Cells(r, 8)).HorizontalAlignment = -4108
        r = r + 2
        aufSeite = aufSeite + hoehe
    Next m
    Application.ScreenUpdating = True
    WerkstattpapierFuellen = r - 2
End Function

' Liest Schnittplan und Stangenbelegung und fasst gleich belegte Stangen (gleiches Profil,
' Werkstoff, Stangenlänge, gleiche Teile in gleicher Reihenfolge und Lage) zu Mustern zusammen.
' Ergebnis: Anzahl Stangen (0 = kein Schnittplan); Daten in den Modulvariablen g*.
Private Function StangenLesen() As Long
    Dim sp As Variant, dt As Variant, schl() As String, nS As Long, s As Long, i As Long, m As Long
    Dim letzteD As Long
    gNS = 0: gNM = 0
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

    ' Teile je Stange (Stangenbelegung ist nach Stange und Platz sortiert)
    ReDim gErste(1 To nS): ReDim gAnzT(1 To nS): ReDim schl(1 To nS)
    For i = 1 To UBound(dt, 1)
        If IsEmpty(dt(i, 1)) Then Exit For
        s = dt(i, 1)
        If s >= 1 And s <= nS Then
            If gAnzT(s) = 0 Then gErste(s) = i
            gAnzT(s) = gAnzT(s) + 1
            schl(s) = schl(s) & "|" & dt(i, 5) & ":" & dt(i, 6) & ":" & dt(i, 9)
        End If
    Next i
    ' gleiche Stangenmuster zusammenfassen
    ReDim gMuster(1 To nS): ReDim gMNr(1 To nS): ReDim gMAnz(1 To nS): ReDim gMStange(1 To nS)
    For s = 1 To nS
        schl(s) = sp(s, 2) & "|" & sp(s, 3) & "|" & sp(s, 4) & schl(s)
        For m = 1 To gNM
            If schl(gMStange(m)) = schl(s) Then Exit For
        Next m
        If m > gNM Then gNM = m: gMStange(m) = s
        gMuster(s) = m
        gMAnz(m) = gMAnz(m) + 1
    Next s
    For m = 1 To gNM
        gMNr(m) = Nummern(gMuster, nS, m)
    Next m
    gSp = sp: gDt = dt: gNS = nS
    StangenLesen = nS
End Function


' ================================================================== Stangenbild (Verschachtelung)
Public Sub StangenbildLeeren()
    With ThisWorkbook.Worksheets("Stangenbild")
        .Range(.Rows(3), .Rows(.Rows.Count)).Clear
        On Error Resume Next
        .ResetAllPageBreaks
    End With
End Sub

' Füllt das Blatt Stangenbild: je Stangenmuster eine Kopfzeile und ein Balken aus BILD_ZELLEN
' Zellen (eine Zelle = Stangenlänge / BILD_ZELLEN). Teile werden gerundet, jedes Teil bekommt
' mindestens eine Zelle. Ergebnis: letzte beschriebene Zeile (0 = kein Schnittplan).
Public Function StangenbildFuellen() As Long
    Dim ws As Worksheet, wa As Worksheet, sp As Variant, dt As Variant
    Dim nS As Long, s As Long, i As Long, m As Long, r As Long, j As Long
    Dim lang As Double, endb As Double, greif As Double, a As Long, b As Long, cur As Long
    Dim posListe() As String, nPos As Long, farbe As Long, txt As String, bloecke As Long

    Set ws = ThisWorkbook.Worksheets("Stangenbild")
    Set wa = ThisWorkbook.Worksheets("Auftrag")
    StangenbildLeeren
    nS = StangenLesen()
    If nS = 0 Then Exit Function
    sp = gSp: dt = gDt
    ReDim posListe(1 To 1)

    Application.ScreenUpdating = False
    ws.Columns(1).ColumnWidth = 2
    ws.Range(ws.Columns(BILD_SPALTE), ws.Columns(BILD_SPALTE + BILD_ZELLEN - 1)).ColumnWidth = 1
    ws.Columns(BILD_SPALTE + BILD_ZELLEN).ColumnWidth = 2
    ws.Range("A2").Value = AlsText("Auftrag " & wa.Range("C4").Value & "   |   Kunde " & wa.Range("C6").Value & _
                                   "   |   Maschine " & wa.Range("C8").Value & "   |   erstellt " & _
                                   Format$(Now, "dd.mm.yyyy") & " " & Format$(Now, "hh:mm"))
    ws.Range("A2").Font.Italic = False: ws.Range("A2").Font.Size = 9
    ' Legende
    r = 3
    If Not Bedienung.OptimierungAktuell() Then
        ws.Range("A3").Value = "ACHTUNG: Stangenbild passt nicht zum aktuellen Auftrag (Optimierung veraltet)."
        ws.Range("A3").Font.Bold = True: ws.Range("A3").Font.Color = RGB(192, 0, 0)
        r = 4
    End If
    Legende ws, r, 0, RGB(127, 127, 127), "Endbeschnitt"
    Legende ws, r, 18, RGB(189, 215, 238), "Teil (Pos., Länge in mm; Farbe je Position)"
    Legende ws, r, 58, RGB(242, 242, 242), "Rest / Verschnitt"
    Legende ws, r, 82, RGB(255, 153, 153), "Greiferrest"
    ws.Cells(r + 1, BILD_SPALTE).Value = "Dicke schwarze Linie = Schnitt. Maßstab: eine Zelle = Stangenlänge / " & BILD_ZELLEN & "."
    ws.Cells(r + 1, BILD_SPALTE).Font.Size = 8
    ws.Cells(r + 1, BILD_SPALTE).Font.Color = RGB(89, 89, 89)
    r = r + 3

    For m = 1 To gNM
        s = gMStange(m)
        If bloecke > 0 And bloecke Mod BILDER_JE_SEITE = 0 Then
            On Error Resume Next
            ws.HPageBreaks.Add ws.Cells(r, 1)
            On Error GoTo 0
        End If
        bloecke = bloecke + 1
        lang = Zahl0(sp(s, 4)): endb = Zahl0(sp(s, 5)): greif = Zahl0(sp(s, 6))
        If gMAnz(m) = 1 Then txt = "Stange " & gMNr(m) Else txt = "Stangen " & gMNr(m) & "  (" & gMAnz(m) & " Stück gleich)"
        ws.Cells(r, BILD_SPALTE).Value = AlsText(txt & "   |   " & sp(s, 2) & "   |   " & sp(s, 3) & "   |   " & _
                                                 Format$(lang, "#,##0") & " mm   |   " & gAnzT(s) & " Teile   |   Rest " & _
                                                 ZahlOderText(sp(s, 11), "#,##0.0") & " mm   |   Ausnutzung " & _
                                                 ZahlOderText(sp(s, 12), "0.0%"))
        ws.Cells(r, BILD_SPALTE).Font.Bold = True
        ws.Cells(r, BILD_SPALTE).Font.Size = 9
        ws.Rows(r + 1).RowHeight = 26
        ws.Rows(r + 2).RowHeight = 11
        If lang > 0 Then
            ' ganze Stange als Rest, darauf Endbeschnitt, Greiferrest und Teile
            Balken ws, r + 1, 0, BILD_ZELLEN, RGB(242, 242, 242)
            cur = 0
            If endb > 0 Then cur = Groesser(Zelle(endb, lang), 1): Balken ws, r + 1, 0, cur, RGB(127, 127, 127)
            If greif > 0 Then Balken ws, r + 1, Kleiner(Zelle(lang - greif, lang), BILD_ZELLEN - 1), BILD_ZELLEN, RGB(255, 153, 153)
            For i = gErste(s) To gErste(s) + gAnzT(s) - 1
                a = Zelle(Zahl0(dt(i, 7)), lang): b = Zelle(Zahl0(dt(i, 8)), lang)
                If a < cur Then a = cur
                If b <= a Then b = a + 1
                If b > BILD_ZELLEN Then b = BILD_ZELLEN
                If a < b Then
                    For j = 1 To nPos
                        If posListe(j) = CStr(dt(i, 3)) Then Exit For
                    Next j
                    If j > nPos Then nPos = j: ReDim Preserve posListe(1 To nPos): posListe(nPos) = CStr(dt(i, 3))
                    farbe = Palette(j)
                    If b - a >= 12 Then
                        txt = "Pos " & dt(i, 3) & "  " & Format$(Zahl0(dt(i, 6)), "0")
                    ElseIf b - a >= 4 Then
                        txt = CStr(dt(i, 3))
                    Else
                        txt = ""
                    End If
                    BildTeil ws, r + 1, a, b, farbe, txt
                    cur = b
                End If
            Next i
            With ws.Range(ws.Cells(r + 1, BILD_SPALTE), ws.Cells(r + 1, BILD_SPALTE + BILD_ZELLEN - 1))
                .Borders(8).LineStyle = 1: .Borders(8).Weight = 2
                .Borders(9).LineStyle = 1: .Borders(9).Weight = 2
            End With
            ws.Cells(r + 2, BILD_SPALTE).Value = "0"
            ws.Cells(r + 2, BILD_SPALTE + BILD_ZELLEN - 1).Value = AlsText(Format$(lang, "#,##0") & " mm")
            ws.Cells(r + 2, BILD_SPALTE + BILD_ZELLEN - 1).HorizontalAlignment = -4152   ' xlRight
            ws.Range(ws.Cells(r + 2, BILD_SPALTE), ws.Cells(r + 2, BILD_SPALTE + BILD_ZELLEN - 1)).Font.Size = 7
        End If
        r = r + 4
    Next m
    Application.ScreenUpdating = True
    StangenbildFuellen = r - 2
End Function

' Zelle (0 bis BILD_ZELLEN) für die Lage x [mm] auf einer Stange der Länge lang
Private Function Zelle(ByVal x As Double, ByVal lang As Double) As Long
    Zelle = Int(x / lang * BILD_ZELLEN + 0.5)
    If Zelle < 0 Then Zelle = 0
    If Zelle > BILD_ZELLEN Then Zelle = BILD_ZELLEN
End Function

Private Function Groesser(ByVal a As Long, ByVal b As Long) As Long
    If a > b Then Groesser = a Else Groesser = b
End Function

Private Function Kleiner(ByVal a As Long, ByVal b As Long) As Long
    If a < b Then Kleiner = a Else Kleiner = b
End Function

Private Function Zahl0(v As Variant) As Double
    If IsError(v) Then Exit Function
    If IsNumeric(v) And Not IsEmpty(v) Then Zahl0 = CDbl(v)
End Function

' Zellen a bis b-1 des Balkens einfärben
Private Sub Balken(ws As Worksheet, ByVal r As Long, ByVal a As Long, ByVal b As Long, ByVal farbe As Long)
    If b <= a Then Exit Sub
    ws.Range(ws.Cells(r, BILD_SPALTE + a), ws.Cells(r, BILD_SPALTE + b - 1)).Interior.Color = farbe
End Sub

' Teil als verbundene Zellen a bis b-1 mit Beschriftung und Schnittlinien links und rechts
Private Sub BildTeil(ws As Worksheet, ByVal r As Long, ByVal a As Long, ByVal b As Long, ByVal farbe As Long, _
                 ByVal txt As String)
    With ws.Range(ws.Cells(r, BILD_SPALTE + a), ws.Cells(r, BILD_SPALTE + b - 1))
        .Interior.Color = farbe
        If b - a > 1 Then .Merge
        .HorizontalAlignment = -4108
        .VerticalAlignment = -4108
        .Font.Size = 8
        .Borders(7).LineStyle = 1: .Borders(7).Weight = -4138    ' links, mittel
        .Borders(10).LineStyle = 1: .Borders(10).Weight = -4138  ' rechts, mittel
    End With
    If txt <> "" Then ws.Cells(r, BILD_SPALTE + a).Value = AlsText(txt)
End Sub

Private Sub Legende(ws As Worksheet, ByVal r As Long, ByVal versatz As Long, ByVal farbe As Long, ByVal txt As String)
    With ws.Range(ws.Cells(r, BILD_SPALTE + versatz), ws.Cells(r, BILD_SPALTE + versatz + 1))
        .Interior.Color = farbe
        .Borders.LineStyle = 1
    End With
    ws.Cells(r, BILD_SPALTE + versatz + 3).Value = txt
    ws.Cells(r, BILD_SPALTE + versatz + 3).Font.Size = 8
End Sub

' Farbe je Position (Reihenfolge des ersten Auftretens), helle Töne für lesbare Schrift
Private Function Palette(ByVal j As Long) As Long
    Select Case (j - 1) Mod 9
        Case 0: Palette = RGB(189, 215, 238)
        Case 1: Palette = RGB(198, 224, 180)
        Case 2: Palette = RGB(255, 230, 153)
        Case 3: Palette = RGB(217, 210, 233)
        Case 4: Palette = RGB(180, 198, 231)
        Case 5: Palette = RGB(248, 203, 173)
        Case 6: Palette = RGB(204, 236, 255)
        Case 7: Palette = RGB(226, 239, 218)
        Case Else: Palette = RGB(237, 237, 190)
    End Select
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
    Dim ws As Worksheet, av As Variant, kv As Variant, i As Long, j As Long, r As Long
    Dim w As Variant, summeZeile As Long, satz As String, erledigt As String
    Dim saetze As Double, satzPreis As Double, preis As Double, menge As Double
    Set ws = ThisWorkbook.Worksheets("Angebot")
    Application.Calculate
    AngebotLeeren
    ws.Range(ws.Cells(A0, 4), ws.Cells(A0 + 600, 5)).UnMerge
    av = ThisWorkbook.Worksheets("Auftrag").Range("A" & O0 & ":AR" & O1).Value
    kv = ThisWorkbook.Worksheets("Kalkulation").Range("A" & O0 & ":W" & O1).Value
    hinweise = 0
    erledigt = "|"
    r = A0 - 1
    For i = 1 To UBound(av, 1)
        If Len(SatzText(av(i, 4))) > 0 Then
            satz = SatzText(av(i, 43))
            If Len(satz) = 0 Then
                ' Einzelteil: eine Zeile mit Stückpreis und Gesamtpreis
                r = r + 1
                ws.Cells(r, 1).Value = AlsText(av(i, 1))
                ws.Cells(r, 2).Value = AlsText(av(i, 2))
                ws.Cells(r, 3).Value = AngebotText(av, i)
                ws.Cells(r, 4).Value = av(i, 7)
                preis = PreisJeTeil(kv, i)
                menge = Wert(av(i, 7))
                ws.Cells(r, 5).Value = preis
                ws.Cells(r, 6).Value = Round(preis * menge, 2)
            ElseIf InStr(erledigt, "|" & satz & "|") = 0 Then
                ' Satz: ein Block mit Satzpreis, die Teile darunter nachrichtlich
                erledigt = erledigt & satz & "|"
                saetze = SatzAnzahl(av, satz)
                satzPreis = 0
                For j = 1 To UBound(av, 1)
                    If SatzText(av(j, 43)) = satz Then satzPreis = satzPreis + PreisJeTeil(kv, j) * JeSatz(av, j)
                Next j
                satzPreis = Round(satzPreis, 2)
                r = r + 1
                ws.Cells(r, 3).Value = "Satz " & satz
                ws.Cells(r, 4).Value = saetze
                ws.Cells(r, 5).Value = satzPreis
                ws.Cells(r, 6).Value = Round(satzPreis * saetze, 2)
                ws.Range(ws.Cells(r, 1), ws.Cells(r, 6)).Font.Bold = True
                For j = 1 To UBound(av, 1)
                    If SatzText(av(j, 43)) = satz Then
                        r = r + 1
                        ws.Cells(r, 1).Value = AlsText(av(j, 1))
                        ws.Cells(r, 2).Value = AlsText(av(j, 2))
                        ws.Cells(r, 3).Value = "   " & Format$(JeSatz(av, j), "0") & " x " & AngebotText(av, j)
                    End If
                Next j
            End If
        End If
    Next i
    For i = 1 To UBound(av, 1)
        If Len(SatzText(av(i, 4))) > 0 Then
            w = kv(i, 23)
            If IsError(w) Then
                hinweise = hinweise + 1
            ElseIf Len(CStr(w)) > 0 Then
                hinweise = hinweise + 1
            End If
        End If
    Next i
    If r < A0 Then Exit Function
    Spaltenbreiten ws, Array(6, 15, 52, 9, 12, 13)
    Rahmen ws.Range(ws.Cells(A0, 1), ws.Cells(r, 6))
    ws.Range(ws.Cells(A0, 3), ws.Cells(r, 3)).WrapText = True
    ws.Range(ws.Cells(A0, 1), ws.Cells(r, 6)).VerticalAlignment = -4160   ' xlTop
    ws.Range(ws.Cells(A0, 4), ws.Cells(r, 4)).NumberFormat = "#,##0"
    ws.Range(ws.Cells(A0, 1), ws.Cells(r, 1)).HorizontalAlignment = -4108   ' xlCenter
    ws.Range(ws.Cells(A0, 5), ws.Cells(r, 6)).NumberFormat = "#,##0.00"
    ws.Range(ws.Cells(A0, 1), ws.Cells(r, 6)).Font.Name = "Arial"
    ws.Range(ws.Cells(A0, 1), ws.Cells(r, 6)).Font.Size = 10
    summeZeile = r + 2
    ws.Cells(summeZeile, 4).Value = "Summe netto [€]"
    ws.Cells(summeZeile, 6).Formula = "=SUM(F" & A0 & ":F" & r & ")"
    ws.Cells(summeZeile + 1, 4).Value = "zzgl. MwSt. [€]"
    ws.Cells(summeZeile + 1, 6).Formula = "=ROUND(F" & summeZeile & "*$C$11,2)"
    ws.Cells(summeZeile + 2, 4).Value = "Gesamtbetrag [€]"
    ws.Cells(summeZeile + 2, 6).Formula = "=F" & summeZeile & "+F" & (summeZeile + 1)
    For i = 0 To 2
        ws.Range(ws.Cells(summeZeile + i, 4), ws.Cells(summeZeile + i, 5)).Merge
        ws.Cells(summeZeile + i, 4).HorizontalAlignment = -4152   ' xlRight
    Next i
    With ws.Range(ws.Cells(summeZeile, 4), ws.Cells(summeZeile + 2, 6))
        .Font.Name = "Arial"
        .Font.Bold = True
    End With
    ws.Range(ws.Cells(summeZeile, 6), ws.Cells(summeZeile + 2, 6)).NumberFormat = "#,##0.00"
    ws.Range(ws.Cells(summeZeile + 2, 4), ws.Cells(summeZeile + 2, 6)).Borders(8).LineStyle = 1   ' xlEdgeTop
    AngebotFuellen = Staffeltreppe(ws, summeZeile + 2)
End Function

' Preistreppe unter den Positionen: je Mengenstufe aus dem Blatt Staffelpreise
' eine Zeile mit Preis je Satz bzw. Stück. Ergebnis: letzte beschriebene Zeile.
Private Function Staffeltreppe(ws As Worksheet, ByVal ab As Long) As Long
    Dim wf As Worksheet, n As Long, i As Long, r As Long, k As Long, schl As String, bez As String
    n = Staffel.StaffelZeilen()
    Staffeltreppe = ab
    If n = 0 Then Exit Function
    Set wf = ThisWorkbook.Worksheets("Staffelpreise")
    r = ab + 3
    ws.Cells(r, 1).Value = "Staffelpreise"
    ws.Cells(r, 1).Font.Bold = True
    ws.Cells(r, 3).Value = "Je Stufe neu gerechnet: Rüsten, Stangenwechsel und Verschnitt fallen je Menge neu an."
    r = r + 1
    k = r
    Kopf ws, r, Array("Pos.", "Artikelnummer", "Satz / Position", "Menge", _
                      "Preis je Einheit [€]", "Gesamtpreis [€]")
    ws.Rows(r).RowHeight = 34
    For i = 1 To n
        r = r + 1
        schl = SatzText(wf.Cells(P0 + i - 1, 1).Value)
        bez = SatzText(wf.Cells(P0 + i - 1, 2).Value)
        If SatzText(wf.Cells(P0 + i - 1, 3).Value) = "Satz" Then
            ws.Cells(r, 3).Value = "Satz " & schl & IIf(Len(bez) > 0, " (" & bez & ")", "")
            ws.Range(ws.Cells(r, 1), ws.Cells(r, 6)).Font.Bold = True
        Else
            ws.Cells(r, 1).Value = wf.Cells(P0 + i - 1, 1).Value
            ws.Cells(r, 3).Value = bez
        End If
        ws.Cells(r, 4).Value = wf.Cells(P0 + i - 1, 4).Value
        ws.Cells(r, 5).Value = wf.Cells(P0 + i - 1, 12).Value
        ws.Cells(r, 6).Value = wf.Cells(P0 + i - 1, 13).Value
    Next i
    Rahmen ws.Range(ws.Cells(k, 1), ws.Cells(r, 6))
    ws.Range(ws.Cells(k + 1, 4), ws.Cells(r, 4)).NumberFormat = "#,##0"
    ws.Range(ws.Cells(k + 1, 5), ws.Cells(r, 6)).NumberFormat = "#,##0.00"
    ws.Range(ws.Cells(k + 1, 1), ws.Cells(r, 6)).Font.Name = "Arial"
    ws.Range(ws.Cells(k + 1, 1), ws.Cells(r, 6)).Font.Size = 10
    ws.Range(ws.Cells(k + 1, 1), ws.Cells(r, 1)).HorizontalAlignment = -4108   ' xlCenter
    Staffeltreppe = r
End Function

' Verkaufspreis je Teil aus der Kalkulation (Spalte T), auf Cent gerundet.
Private Function PreisJeTeil(kv As Variant, ByVal i As Long) As Double
    PreisJeTeil = Round(Wert(kv(i, 20)), 2)
End Function

' Wie oft ein Teil in einem Satz steckt (Auftrag Spalte AR), mindestens 1.
Private Function JeSatz(av As Variant, ByVal i As Long) As Double
    JeSatz = Wert(av(i, 44))
    If JeSatz < 1 Then JeSatz = 1
End Function

' Anzahl Sätze = Stückzahl / Stück je Satz (größter Wert der Satzpositionen).
Private Function SatzAnzahl(av As Variant, ByVal satz As String) As Double
    Dim i As Long, n As Double, stk As Double
    For i = 1 To UBound(av, 1)
        If SatzText(av(i, 43)) = satz Then
            stk = Wert(av(i, 7)) / JeSatz(av, i)
            If stk > n Then n = stk
        End If
    Next i
    SatzAnzahl = Int(n + 0.5)
    If SatzAnzahl < 1 Then SatzAnzahl = 1
End Function

Private Function SatzText(v As Variant) As String
    If IsError(v) Then Exit Function
    If IsEmpty(v) Then Exit Function
    SatzText = Trim$(CStr(v))
End Function

Private Function Wert(v As Variant) As Double
    If IsError(v) Then Exit Function
    If IsEmpty(v) Then Exit Function
    If Not IsNumeric(v) Then Exit Function
    Wert = CDbl(v)
End Function

' Bezeichnung einer Position fürs Angebot, z. B.
' "Rechteckrohr 80 x 40 x 5, L = 1500 mm, inkl. Material S235 EN10219, Zusatzarbeiten: Gewinde 4xM6, Gravur"
Private Function AngebotText(av As Variant, ByVal i As Long) As String
    Dim t As String, zus As String, wst As Variant
    t = Profiltext(CStr(av(i, 4)))
    t = t & ", L = " & Format$(av(i, 6), "0") & " mm"
    wst = Application.Match(CStr(av(i, 5)), ThisWorkbook.Worksheets("Werkstoffe").Range("A" & M0 & ":A" & M1), 0)
    If IsError(wst) Then
        t = t & ", inkl. Material " & CStr(av(i, 5))
    Else
        t = t & ", inkl. Material " & TextOderLeer(ThisWorkbook.Worksheets("Werkstoffe").Cells(M0 + wst - 1, 8).Value, CStr(av(i, 5)))
    End If
    If Len(CStr(av(i, 33))) > 0 Then zus = "Gewinde " & CStr(av(i, 33))       ' AG
    If IsNumeric(av(i, 30)) And Not IsEmpty(av(i, 30)) Then                      ' AD: Gravur [mm]
        If CDbl(av(i, 30)) > 0 Then zus = zus & IIf(Len(zus) > 0, ", ", "") & "Gravur"
    End If
    If Len(zus) > 0 Then t = t & ", Zusatzarbeiten: " & zus
    AngebotText = t
End Function

' Profilbezeichnung aus dem Blatt Profile (Form und Maße), sonst die Profil-ID.
Private Function Profiltext(ByVal pid As String) As String
    Dim wp As Worksheet, z As Variant, form As String, a As String, b As String, wand As String
    Set wp = ThisWorkbook.Worksheets("Profile")
    z = Application.Match(pid, wp.Range("A" & M0 & ":A" & M1), 0)
    If IsError(z) Then Profiltext = pid: Exit Function
    z = M0 + z - 1
    form = CStr(wp.Cells(z, 2).Value)
    a = Format$(wp.Cells(z, 3).Value, "0.##")
    b = Format$(wp.Cells(z, 4).Value, "0.##")
    wand = Format$(wp.Cells(z, 5).Value, "0.##")
    Select Case form
        Case "Rundrohr": Profiltext = "Rundrohr Ø " & a & " x " & wand
        Case "Quadratrohr": Profiltext = "Quadratrohr " & a & " x " & a & " x " & wand
        Case "Rechteckrohr": Profiltext = "Rechteckrohr " & a & " x " & b & " x " & wand
        Case Else: Profiltext = pid
    End Select
End Function

Private Function TextOderLeer(v As Variant, ByVal ersatz As String) As String
    If Len(CStr(v)) > 0 Then TextOderLeer = CStr(v) Else TextOderLeer = ersatz
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
    ws.Rows(r).RowHeight = 30
End Sub

Private Sub Spaltenbreiten(ws As Worksheet, breiten As Variant)
    Dim j As Long
    For j = 0 To UBound(breiten)
        ws.Columns(j + 1).ColumnWidth = breiten(j)
    Next j
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
    AusgabeTest = "OK " & WerkstattpapierFuellen() & " " & AngebotFuellen(h) & " " & h & " " & StangenbildFuellen()
    Exit Function
Fehler:
    AusgabeTest = "FEHLER " & Err.Number & ": " & Err.Description & " (Zeile " & Erl & ")"
End Function
