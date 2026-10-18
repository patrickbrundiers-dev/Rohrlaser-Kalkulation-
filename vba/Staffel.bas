Attribute VB_Name = "Staffel"
Option Explicit

' Staffelpreise
' ---------------------------------------------------------------------------
' Jede Mengenstufe aus dem Blatt "Staffeln" wird als eigener Auftrag komplett
' neu gerechnet: nur die Positionen dieser Staffel sind besetzt, alle anderen
' bleiben leer. Dadurch fallen Rüstzeit, Stangenwechsel und Verschnitt je Stufe
' neu an und der Preis je Satz bzw. Stück sinkt mit der Menge.
' Nach dem Lauf wird der ursprüngliche Auftrag wiederhergestellt und neu
' optimiert, damit Schnittplan und Kalkulation wieder zum Auftrag passen.

Private Const O0 As Long = 13           ' erste Positionszeile im Blatt Auftrag
Private Const O1 As Long = 512
Private Const T0 As Long = 5            ' erste Zeile im Blatt Staffeln
Private Const T1 As Long = 104
Private Const F0 As Long = 5            ' erste Zeile im Blatt Staffelpreise
Private Const F1 As Long = 204

Public Sub StaffelpreiseRechnen()
    Dim bericht As String
    On Error GoTo Fehler
    bericht = StaffelnRechnen()
    MsgBox bericht, vbInformation, "Staffelpreise"
    ThisWorkbook.Worksheets("Staffelpreise").Activate
    Exit Sub
Fehler:
    MsgBox "Staffelpreise abgebrochen:" & vbLf & Err.Description, vbExclamation, "Staffelpreise"
End Sub

' Rechnet alle Staffeln und gibt einen Bericht als Text zurück (ohne Meldungsfenster).
Public Function StaffelnRechnen() As String
    Dim wa As Worksheet, wsa As Worksheet, wf As Worksheet
    Dim urspr() As Double, posv As Variant, satzv As Variant, jev As Variant, pidv As Variant
    Dim schluessel() As String, mengen() As Double, nSt As Long
    Dim i As Long, k As Long, r As Long, zeilen As Long
    Dim ereignisse As Boolean, gerechnet As Long, fehler As String

    Set wa = ThisWorkbook.Worksheets("Auftrag")
    Set wsa = ThisWorkbook.Worksheets("Staffeln")
    Set wf = ThisWorkbook.Worksheets("Staffelpreise")

    ReDim schluessel(1 To T1 - T0 + 1)
    ReDim mengen(1 To T1 - T0 + 1)
    nSt = 0
    For r = T0 To T1
        If Len(Txt(wsa.Cells(r, 1).Value)) > 0 And Zahl(wsa.Cells(r, 2).Value) >= 1 Then
            nSt = nSt + 1
            schluessel(nSt) = Txt(wsa.Cells(r, 1).Value)
            mengen(nSt) = Zahl(wsa.Cells(r, 2).Value)
        End If
    Next r
    StaffelpreiseLeeren
    If nSt = 0 Then
        StaffelnRechnen = "Im Blatt 'Staffeln' ist keine Mengenstufe eingetragen."
        Exit Function
    End If

    ReDim urspr(1 To O1 - O0 + 1)
    For r = O0 To O1
        urspr(r - O0 + 1) = Zahl(wa.Cells(r, 7).Value)
    Next r
    posv = wa.Range("A" & O0 & ":A" & O1).Value
    satzv = wa.Range("AQ" & O0 & ":AQ" & O1).Value
    jev = wa.Range("AR" & O0 & ":AR" & O1).Value
    pidv = wa.Range("D" & O0 & ":D" & O1).Value

    ereignisse = Application.EnableEvents
    Application.EnableEvents = False
    Application.ScreenUpdating = False
    On Error GoTo Aufraeumen
    zeilen = F0 - 1
    For k = 1 To nSt
        If zeilen >= F1 Then Exit For
        zeilen = zeilen + 1
        StaffelZeile wa, wf, zeilen, schluessel(k), mengen(k), urspr, posv, satzv, jev, pidv
        gerechnet = gerechnet + 1
    Next k

Aufraeumen:
    If Err.Number <> 0 Then fehler = Err.Description
    On Error Resume Next
    MengenSchreiben wa, urspr
    Optimierung.OptimiereMappe
    Application.Calculate
    Application.EnableEvents = ereignisse
    Application.ScreenUpdating = True
    On Error GoTo 0
    If Len(fehler) > 0 Then Err.Raise 1001, "Staffel", fehler
    StaffelnRechnen = gerechnet & " Mengenstufe(n) gerechnet, Ergebnis im Blatt 'Staffelpreise'." & vbLf & _
                      "Der ursprüngliche Auftrag ist wiederhergestellt und neu optimiert."
End Function

' Rechnet eine Mengenstufe und schreibt sie in das Blatt Staffelpreise.
Private Sub StaffelZeile(wa As Worksheet, wf As Worksheet, ByVal zeile As Long, ByVal schl As String, _
                         ByVal menge As Double, urspr() As Double, posv As Variant, satzv As Variant, _
                         jev As Variant, pidv As Variant)
    Dim wk As Worksheet, neu() As Double, i As Long, treffer As Long, istSatz As Boolean
    Dim je As Double, teile As Double, bez As String, hinweise As Long, offen As Double
    Dim material As Double, laser As Double, ruesten As Double, hk As Double, vk As Double
    Dim stangen As Double, einheit As String, jeEinheit As Double, text As String

    Set wk = ThisWorkbook.Worksheets("Kalkulation")
    ReDim neu(1 To UBound(urspr))
    istSatz = False
    For i = 1 To UBound(satzv, 1)
        If Txt(satzv(i, 1)) = schl And Len(schl) > 0 Then istSatz = True
    Next i

    treffer = 0
    For i = 1 To UBound(neu)
        If Len(Txt(pidv(i, 1))) > 0 Then
            If (istSatz And Txt(satzv(i, 1)) = schl) Or ((Not istSatz) And Txt(posv(i, 1)) = schl) Then
                je = Zahl(jev(i, 1))
                If je < 1 Then je = 1
                If Not istSatz Then je = 1
                neu(i) = menge * je
                treffer = treffer + 1
                If Len(bez) < 60 Then
                    If istSatz Then
                        bez = bez & IIf(Len(bez) > 0, ", ", "Pos. ") & Txt(posv(i, 1))
                    Else
                        bez = Txt(wa.Cells(O0 + i - 1, 3).Value)
                    End If
                End If
            End If
        End If
    Next i

    wf.Cells(zeile, 1).Value = AlsText(schl)
    einheit = IIf(istSatz, "Satz", "Stück")
    wf.Cells(zeile, 3).Value = einheit
    wf.Cells(zeile, 4).Value = menge
    If treffer = 0 Then
        wf.Cells(zeile, 2).Value = ""
        wf.Cells(zeile, 14).Value = "FEHLER: Satz/Pos. nicht im Auftrag"
        Exit Sub
    End If
    wf.Cells(zeile, 2).Value = bez

    MengenSchreiben wa, neu
    Optimierung.OptimiereMappe
    Application.Calculate

    stangen = Zahl(wk.Range("F6").Value)
    teile = Zahl(wk.Range("F8").Value)
    material = Zahl(wk.Range("K4").Value)
    laser = Zahl(wk.Range("K5").Value)
    ruesten = Zahl(wk.Range("K6").Value)
    hk = Zahl(wk.Range("K7").Value)
    vk = Zahl(wk.Range("K8").Value)

    wf.Cells(zeile, 5).Value = teile
    wf.Cells(zeile, 6).Value = stangen
    wf.Cells(zeile, 7).Value = material
    wf.Cells(zeile, 8).Value = laser
    wf.Cells(zeile, 9).Value = ruesten
    wf.Cells(zeile, 10).Value = hk
    If menge > 0 Then
        wf.Cells(zeile, 11).Value = hk / menge
        jeEinheit = Round(vk / menge, 2)
    End If
    wf.Cells(zeile, 12).Value = jeEinheit
    wf.Cells(zeile, 13).Value = Round(jeEinheit * menge, 2)

    hinweise = 0
    offen = 0
    For i = 1 To UBound(neu)
        If neu(i) > 0 Then
            If Len(Txt(wk.Cells(O0 + i - 1, 23).Value)) > 0 Then hinweise = hinweise + 1
            offen = offen + Zahl(wa.Cells(O0 + i - 1, 41).Value)
        End If
    Next i
    If offen > 0 Then text = "WARNUNG: " & Format$(offen, "0") & " Teile nicht eingeplant"
    If hinweise > 0 Then text = text & IIf(Len(text) > 0, "; ", "") & hinweise & " Hinweis(e) in der Kalkulation"
    wf.Cells(zeile, 14).Value = text
End Sub

' Stückzahlen im Auftrag setzen: leere Einträge (0) werden geleert, nicht übersprungen.
Private Sub MengenSchreiben(wa As Worksheet, mengen() As Double)
    Dim i As Long
    wa.Range("G" & O0 & ":G" & O1).ClearContents
    For i = 1 To UBound(mengen)
        If mengen(i) > 0 Then wa.Cells(O0 + i - 1, 7).Value = mengen(i)
    Next i
End Sub

Public Sub StaffelpreiseLeeren()
    Dim wf As Worksheet
    Set wf = ThisWorkbook.Worksheets("Staffelpreise")
    wf.Range(wf.Cells(F0, 1), wf.Cells(F1, 14)).ClearContents
End Sub

' Anzahl gefüllter Zeilen im Blatt Staffelpreise.
Public Function StaffelZeilen() As Long
    Dim wf As Worksheet, r As Long, n As Long
    Set wf = ThisWorkbook.Worksheets("Staffelpreise")
    For r = F0 To F1
        If Len(Txt(wf.Cells(r, 1).Value)) > 0 Then n = r - F0 + 1
    Next r
    StaffelZeilen = n
End Function

Private Function Zahl(v As Variant) As Double
    If IsError(v) Then Exit Function
    If IsEmpty(v) Then Exit Function
    If Not IsNumeric(v) Then Exit Function
    Zahl = CDbl(v)
End Function

' Schlüssel immer als Text vergleichen; ganze Zahlen ohne Nachkommastellen.
Private Function Txt(v As Variant) As String
    If IsError(v) Then Exit Function
    If IsEmpty(v) Then Exit Function
    If IsNumeric(v) Then
        If CDbl(v) = Int(CDbl(v)) Then
            Txt = Format$(CDbl(v), "0")
        Else
            Txt = Trim$(Str$(CDbl(v)))
        End If
    Else
        Txt = Trim$(CStr(v))
    End If
End Function

Private Function AlsText(ByVal t As String) As Variant
    Dim d As Double
    If IsNumeric(t) Then
        d = CDbl(t)
        If d = Int(d) Then
            AlsText = d
            Exit Function
        End If
    End If
    AlsText = t
End Function

' Testeinstieg (LibreOffice/Excel): rechnet die Staffeln und meldet die Zeilenzahl.
Public Function StaffelTest() As String
    StaffelTest = StaffelnRechnen() & vbLf & "Zeilen: " & StaffelZeilen()
End Function
