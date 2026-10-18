Attribute VB_Name = "StepImport"
' STEP-Import in die Kalkulationsmappe (VBA-Fassung von tools/step_import.py).
'
' Die Geometrie misst STEP-Import.exe (tools/step_messen.py mit OpenCascade, ohne
' Installation lauffähig). Das Programm liegt im Ordner "STEP-Import" neben der Mappe,
' schreibt die Messwerte in eine Textdatei und öffnet die Mappe nicht. Dieses Modul
' übernimmt die Werte als neue Positionen in das Blatt "Auftrag" und protokolliert sie
' im Blatt "STEP-Import". Die Mappe darf dabei offen bleiben.
'
' Regeln wie bisher (Blatt "Anleitung", A12 bis A14): Profilabgleich über Form und Maße
' (±0,15 mm), Gewinde nur als Vorschlag aus dem Kernloch (Blatt "Gewinde"), Konturklassen
' nach größtem Hüllmaß mit den Grenzen der Maschine im Auftragskopf.
Option Explicit

Private Const M0 As Long = 5
Private Const M1 As Long = 304
Private Const O0 As Long = 13
Private Const O1 As Long = 512
Private Const TOL_MASS As Double = 0.15
Private Const KLEIN_BIS As Double = 10
Private Const MITTEL_BIS As Double = 50
Private Const LOG_BLATT As String = "STEP-Import"
Private Const FEHLER_BASIS As Long = -2147221504   ' vbObjectError

' Messwerte (eine Zeile je Körper), Spalten wie in tools/step_messen.py
Private nM As Long
Private mWert() As Variant      ' mWert(i) = Array der Felder
Private sNamen() As String

' Profile aus den Stammdaten
Private nP As Long
Private pId() As Variant, pForm() As String, pA() As Double, pB() As Double, pT() As Double


' ================================================================== Einstieg (Schaltfläche)
Public Sub StepImportieren()
    Dim exe As String, dateien As Variant, i As Long, werkstoff As String, stueck As Long
    Dim antwort As Variant, tmp As String, liste As String, ausgabe As String, text As String
    Dim rc As Long, neueProfile As Boolean, erneut As Boolean, fehlend As String, doppelt As Long

    exe = FindeExe()
    If exe = "" And LCase$(Left$(ThisWorkbook.Path, 4)) = "http" Then
        MsgBox "Die Mappe ist direkt aus OneDrive/SharePoint geöffnet (" & ThisWorkbook.Path & ")." & vbLf & vbLf & _
               "Für den STEP-Import die Mappe zusammen mit dem Ordner ""STEP-Import"" in einen Ordner auf " & _
               "dem PC oder im Netzlaufwerk legen und von dort öffnen.", vbExclamation, "STEP-Import"
        Exit Sub
    ElseIf exe = "" Then
        MsgBox "STEP-Import.exe wurde nicht gefunden." & vbLf & vbLf & _
               "Bitte den Ordner ""STEP-Import"" aus dem Download neben die Mappe legen:" & vbLf & _
               ThisWorkbook.Path & Application.PathSeparator & "STEP-Import" & Application.PathSeparator & _
               "STEP-Import.exe", vbExclamation, "STEP-Import"
        Exit Sub
    End If

    With Application.FileDialog(3)    ' msoFileDialogFilePicker
        .Title = "STEP-Dateien wählen (mehrere mit Strg oder Umschalt)"
        .AllowMultiSelect = True
        .Filters.Clear
        .Filters.Add "STEP-Dateien", "*.step;*.stp"
        If .Show <> -1 Then Exit Sub
        ReDim dateien(1 To .SelectedItems.Count)
        For i = 1 To .SelectedItems.Count
            dateien(i) = .SelectedItems(i)
        Next i
    End With

    Do
        antwort = Application.InputBox("Werkstoff-ID für alle importierten Teile" & vbLf & _
                                       "(leer lassen = später im Auftrag eintragen):", "STEP-Import", "", Type:=2)
        If VarType(antwort) = vbBoolean Then Exit Sub
        werkstoff = Trim$(CStr(antwort))
        If werkstoff = "" Then Exit Do
        If WerkstoffBekannt(werkstoff) Then Exit Do
        MsgBox "Werkstoff '" & werkstoff & "' steht nicht im Blatt 'Werkstoffe'.", vbExclamation, "STEP-Import"
    Loop
    Do
        antwort = Application.InputBox("Stückzahl für alle importierten Teile" & vbLf & _
                                       "(leer lassen = später im Auftrag eintragen):", "STEP-Import", "", Type:=2)
        If VarType(antwort) = vbBoolean Then Exit Sub
        text = Trim$(CStr(antwort))
        stueck = 0
        If text = "" Then Exit Do
        If IsNumeric(text) Then
            If CDbl(text) >= 1 And CDbl(text) = Int(CDbl(text)) Then stueck = CLng(text): Exit Do
        End If
        MsgBox "Stückzahl muss eine ganze Zahl ab 1 sein.", vbExclamation, "STEP-Import"
    Loop

    tmp = Environ$("TEMP")
    If tmp = "" Then tmp = ThisWorkbook.Path
    liste = tmp & "\rohrlaser_step_liste.txt"
    ausgabe = tmp & "\rohrlaser_step_messwerte.txt"
    text = ""
    For i = 1 To UBound(dateien)
        text = text & dateien(i) & vbLf
    Next i
    SchreibeUtf8 liste, text
    If Len(Dir$(ausgabe)) > 0 Then Kill ausgabe

    Application.StatusBar = "STEP-Dateien werden gemessen (" & UBound(dateien) & ") ..."
    rc = CreateObject("WScript.Shell").Run("""" & exe & """ --liste """ & liste & """ --ausgabe """ & ausgabe & """", 1, True)
    Application.StatusBar = False
    If Len(Dir$(ausgabe)) = 0 Or rc >= 2 Then
        MsgBox "Die Messung ist fehlgeschlagen (Rückgabewert " & rc & ").", vbExclamation, "STEP-Import"
        Exit Sub
    End If

    On Error GoTo Fehler
    LiesMesswerte ausgabe
    Vorpruefung fehlend, doppelt
    If fehlend <> "" Then
        neueProfile = (MsgBox("Diese Profile fehlen im Blatt 'Profile':" & vbLf & fehlend & vbLf & vbLf & _
                       "Jetzt mit den gemessenen Werten anlegen?", vbQuestion + vbYesNo, "STEP-Import") = vbYes)
    End If
    If doppelt > 0 Then
        erneut = (MsgBox(doppelt & " Artikel stehen schon im Auftrag." & vbLf & vbLf & _
                  "Trotzdem noch einmal eintragen? (Nein = überspringen)", vbQuestion + vbYesNo + vbDefaultButton2, _
                  "STEP-Import") = vbYes)
    End If
    text = Uebernehmen(werkstoff, stueck, neueProfile, erneut)
    On Error Resume Next
    Kill liste
    Kill ausgabe
    On Error GoTo 0
    MsgBox text, vbInformation, "STEP-Import"
    Exit Sub
Fehler:
    MsgBox "STEP-Import abgebrochen:" & vbLf & Err.Description, vbExclamation, "STEP-Import"
End Sub

' Übernimmt eine Messwert-Datei von STEP-Import.exe in den Auftrag. Rückgabe: Bericht.
' werkstoff "" und stueck 0 = nicht eintragen.
Public Function ImportiereMesswerte(ByVal datei As String, ByVal werkstoff As String, ByVal stueck As Long, _
                                   ByVal neueProfile As Boolean, ByVal erneut As Boolean) As String
    LiesMesswerte datei
    ImportiereMesswerte = Uebernehmen(werkstoff, stueck, neueProfile, erneut)
End Function

' Für automatische Tests: Bericht oder Fehlertext, ohne Meldungsfenster.
Public Function ImportTest(ByVal datei As String, ByVal werkstoff As String, ByVal stueck As Long, _
                           ByVal neueProfile As Boolean, ByVal erneut As Boolean) As String
    On Error GoTo Fehler
    ImportTest = ImportiereMesswerte(datei, werkstoff, stueck, neueProfile, erneut)
    Exit Function
Fehler:
    ImportTest = "FEHLER " & Err.Number & ": " & Err.Description
End Function

Private Function FindeExe() As String
    Dim kandidaten As Variant, k As Variant, sep As String
    sep = Application.PathSeparator
    kandidaten = Array(ThisWorkbook.Path & sep & "STEP-Import" & sep & "STEP-Import.exe", _
                       ThisWorkbook.Path & sep & "STEP-Import.exe", _
                       ThisWorkbook.Path & sep & ".." & sep & "STEP-Import" & sep & "STEP-Import.exe")   ' abgelegte Auftragsmappe
    For Each k In kandidaten
        If Len(Dir$(k)) > 0 Then FindeExe = k: Exit Function
    Next k
End Function


' ================================================================== Textdateien (UTF-8)
Private Function LiesUtf8(ByVal pfad As String) As String
    Dim f As Integer, b() As Byte, n As Long, i As Long, c As Long, s As String, k As Long
    f = FreeFile
    Open pfad For Binary Access Read As #f
    n = LOF(f)
    If n = 0 Then Close #f: Exit Function
    ReDim b(0 To n - 1)
    Get #f, 1, b
    Close #f
    s = Space$(n)
    i = 0
    If n >= 3 Then
        If b(0) = &HEF And b(1) = &HBB And b(2) = &HBF Then i = 3
    End If
    Do While i < n
        c = b(i)
        If c < &H80 Then
            i = i + 1
        ElseIf c < &HE0 And i + 1 < n Then
            c = (c And &H1F) * &H40 + (b(i + 1) And &H3F): i = i + 2
        ElseIf c < &HF0 And i + 2 < n Then
            c = (c And &HF) * &H1000& + (b(i + 1) And &H3F) * &H40 + (b(i + 2) And &H3F): i = i + 3
        ElseIf i + 3 < n Then
            c = (c And &H7) * &H40000 + (b(i + 1) And &H3F) * &H1000& + (b(i + 2) And &H3F) * &H40 + (b(i + 3) And &H3F)
            i = i + 4
        Else
            c = &HFFFD&: i = n
        End If
        If c > &HFFFF& Then
            c = c - &H10000
            k = k + 1: Mid$(s, k, 1) = ChrW(&HD800& + (c \ &H400))
            c = &HDC00& + (c And &H3FF)
        End If
        k = k + 1: Mid$(s, k, 1) = ChrW(c)
    Loop
    LiesUtf8 = Left$(s, k)
End Function

Private Sub SchreibeUtf8(ByVal pfad As String, ByVal text As String)
    Dim b() As Byte, i As Long, c As Long, n As Long, f As Integer
    ReDim b(0 To 4 * Len(text) + 1)
    For i = 1 To Len(text)
        c = AscW(Mid$(text, i, 1)) And &HFFFF&
        If c >= &HD800& And c <= &HDBFF& And i < Len(text) Then
            c = &H10000 + (c - &HD800&) * &H400 + ((AscW(Mid$(text, i + 1, 1)) And &HFFFF&) - &HDC00&)
            i = i + 1
        End If
        If c < &H80 Then
            b(n) = c: n = n + 1
        ElseIf c < &H800 Then
            b(n) = &HC0 Or (c \ &H40): b(n + 1) = &H80 Or (c And &H3F): n = n + 2
        ElseIf c < &H10000 Then
            b(n) = &HE0 Or (c \ &H1000&): b(n + 1) = &H80 Or ((c \ &H40) And &H3F)
            b(n + 2) = &H80 Or (c And &H3F): n = n + 3
        Else
            b(n) = &HF0 Or (c \ &H40000): b(n + 1) = &H80 Or ((c \ &H1000&) And &H3F)
            b(n + 2) = &H80 Or ((c \ &H40) And &H3F): b(n + 3) = &H80 Or (c And &H3F): n = n + 4
        End If
    Next i
    If Len(Dir$(pfad)) > 0 Then Kill pfad
    f = FreeFile
    Open pfad For Binary Access Write As #f
    If n > 0 Then
        ReDim Preserve b(0 To n - 1)
        Put #f, 1, b
    End If
    Close #f
End Sub


' ================================================================== Messwerte lesen
Private Sub LiesMesswerte(ByVal datei As String)
    Dim text As String, zeilen As Variant, i As Long, z As String
    text = Replace(LiesUtf8(datei), vbCr, "")
    zeilen = Split(text, vbLf)
    If UBound(zeilen) < 0 Then Err.Raise FEHLER_BASIS + 10, , "Messwert-Datei ist leer: " & datei
    sNamen = Split(zeilen(0), vbTab)
    If Feld(sNamen, "laenge") < 0 Or Feld(sNamen, "fehler") < 0 Then
        Err.Raise FEHLER_BASIS + 11, , "Messwert-Datei hat ein unbekanntes Format: " & datei
    End If
    nM = 0
    ReDim mWert(0 To UBound(zeilen) + 1)
    For i = 1 To UBound(zeilen)
        z = zeilen(i)
        If Len(z) > 0 Then
            nM = nM + 1
            mWert(nM) = Split(z, vbTab)
        End If
    Next i
End Sub

Private Function Feld(namen As Variant, ByVal spname As String) As Long
    Dim i As Long
    Feld = -1
    For i = 0 To UBound(namen)
        If namen(i) = spname Then Feld = i: Exit Function
    Next i
End Function

' Feldwert als Text (fehlende Felder = "")
Private Function W(ByVal i As Long, ByVal spname As String) As String
    Dim k As Long
    k = Feld(sNamen, spname)
    If k < 0 Then Exit Function
    If k > UBound(mWert(i)) Then Exit Function
    W = mWert(i)(k)
End Function

' Feldwert als Zahl (Dezimalpunkt, unabhängig von den Ländereinstellungen)
Private Function Nz(ByVal i As Long, ByVal spname As String) As Double
    Nz = Val(W(i, spname))
End Function


' ================================================================== Stammdaten
Private Function IstZahl(v As Variant) As Boolean
    Select Case VarType(v)
        Case vbInteger, vbLong, vbSingle, vbDouble, vbCurrency, vbDecimal, vbByte, 20
            IstZahl = True
    End Select
End Function

Private Function Leer(v As Variant) As Boolean
    If IsError(v) Then Exit Function
    If IsEmpty(v) Then
        Leer = True
    ElseIf VarType(v) = vbString Then
        Leer = (Len(v) = 0)
    End If
End Function

Private Function Zahl0(v As Variant) As Double
    If IstZahl(v) Then Zahl0 = CDbl(v)
End Function

Private Function Txt(v As Variant) As String
    If IsError(v) Then Txt = "#FEHLER" Else Txt = CStr(v)
End Function

Private Function WerkstoffBekannt(ByVal wst As String) As Boolean
    Dim v As Variant, i As Long
    v = ThisWorkbook.Worksheets("Werkstoffe").Range("A" & M0 & ":A" & M1).Value
    For i = 1 To UBound(v)
        If Txt(v(i, 1)) = wst Then WerkstoffBekannt = True: Exit Function
    Next i
End Function

Private Sub LiesProfile()
    Dim v As Variant, i As Long
    v = ThisWorkbook.Worksheets("Profile").Range("A" & M0 & ":E" & M1).Value
    nP = 0
    ReDim pId(1 To M1 - M0 + 1): ReDim pForm(1 To M1 - M0 + 1)
    ReDim pA(1 To M1 - M0 + 1): ReDim pB(1 To M1 - M0 + 1): ReDim pT(1 To M1 - M0 + 1)
    For i = 1 To UBound(v)
        If Not Leer(v(i, 1)) Then
            nP = nP + 1
            pId(nP) = v(i, 1): pForm(nP) = Txt(v(i, 2))
            pA(nP) = Zahl0(v(i, 3)): pB(nP) = Zahl0(v(i, 4)): pT(nP) = Zahl0(v(i, 5))
        End If
    Next i
End Sub

Private Function FindeProfil(ByVal i As Long) As Variant
    Dim k As Long, form As String, a As Double, b As Double, grA As Double, klB As Double
    form = W(i, "profilform"): a = Nz(i, "abm_a"): b = Nz(i, "abm_b")
    FindeProfil = Empty
    For k = 1 To nP
        If pForm(k) = form And Abs(pT(k) - Nz(i, "wandstaerke")) <= TOL_MASS Then
            If form = "Rundrohr" Or form = "Quadratrohr" Then
                If Abs(pA(k) - a) <= TOL_MASS Then FindeProfil = pId(k): Exit Function
            ElseIf form = "Rechteckrohr" Then
                If pA(k) >= pB(k) Then grA = pA(k): klB = pB(k) Else grA = pB(k): klB = pA(k)
                If Abs(grA - a) <= TOL_MASS And Abs(klB - b) <= TOL_MASS Then FindeProfil = pId(k): Exit Function
            End If
        End If
    Next k
End Function

Private Sub ProfilAnlegen(ByVal i As Long)
    Dim ws As Worksheet, r As Long
    Set ws = ThisWorkbook.Worksheets("Profile")
    For r = M0 To M1
        If Leer(ws.Cells(r, 1).Value) Then
            ws.Cells(r, 1).Value = AlsWert(W(i, "profil_id_vorschlag"))
            ws.Cells(r, 2).Value = W(i, "profilform")
            ws.Cells(r, 3).Value = Round(Nz(i, "abm_a"), 2)
            If W(i, "profilform") = "Rechteckrohr" Then ws.Cells(r, 4).Value = Round(Nz(i, "abm_b"), 2)
            ws.Cells(r, 5).Value = Round(Nz(i, "wandstaerke"), 2)
            ws.Cells(r, 6).Value = Round(Nz(i, "flaeche"), 1)
            ws.Cells(r, 9).Value = "aus STEP-Import angelegt, bitte prüfen"
            Exit Sub
        End If
    Next r
    Err.Raise FEHLER_BASIS + 12, , "Blatt 'Profile' ist voll"
End Sub

' Kernlochtabelle aus Blatt "Gewinde" (Spalte A Gewinde, B Kernloch), sonst DIN-336-Vorgabe
Private Sub LiesGewinde(gew() As String, kern() As Double, n As Long)
    Dim v As Variant, i As Long, vorgabe As Variant
    n = 0
    ReDim gew(1 To M1 - M0 + 11): ReDim kern(1 To M1 - M0 + 11)
    On Error Resume Next
    v = ThisWorkbook.Worksheets("Gewinde").Range("A" & M0 & ":B" & M1).Value
    On Error GoTo 0
    If Not IsEmpty(v) Then
        For i = 1 To UBound(v)
            If Not Leer(v(i, 1)) And IstZahl(v(i, 2)) Then
                n = n + 1: gew(n) = Txt(v(i, 1)): kern(n) = CDbl(v(i, 2))
            End If
        Next i
    End If
    If n = 0 Then
        vorgabe = Array("M3", 2.5, "M4", 3.3, "M5", 4.2, "M6", 5#, "M8", 6.8, "M10", 8.5, "M12", 10.2, "M14", 12#, _
                        "M16", 14#, "M20", 17.5)
        For i = 0 To UBound(vorgabe) Step 2
            n = n + 1: gew(n) = vorgabe(i): kern(n) = vorgabe(i + 1)
        Next i
    End If
End Sub

Private Sub LiesKonturgrenzen(klein As Double, mittel As Double, hinw As String)
    Dim maschine As Variant, v As Variant, i As Long
    maschine = ThisWorkbook.Worksheets("Auftrag").Range("C8").Value
    v = ThisWorkbook.Worksheets("Maschinen").Range("A" & M0 & ":I" & M1).Value
    klein = KLEIN_BIS: mittel = MITTEL_BIS
    hinw = "Konturgrenzen Vorgabe " & KLEIN_BIS & "/" & MITTEL_BIS & " mm (Maschine ohne Werte)"
    If Leer(maschine) Then Exit Sub
    For i = 1 To UBound(v)
        If Txt(v(i, 1)) = Txt(maschine) Then
            If IstZahl(v(i, 8)) And IstZahl(v(i, 9)) Then
                If 0 < v(i, 8) And v(i, 8) < v(i, 9) Then
                    klein = CDbl(v(i, 8)): mittel = CDbl(v(i, 9)): hinw = ""
                End If
            End If
            Exit Sub
        End If
    Next i
End Sub


' ================================================================== Auswertung je Teil
Private Function DezText(ByVal x As Double) As String
    ' wie Python "{:g}" mit Komma: 10 -> "10", 8.5 -> "8,5"
    DezText = Replace(Trim$(Str$(x)), ".", ",")
End Function

Private Function BohrungenText(ByVal feldwert As String) As String
    Dim teile As Variant, k As Long, dn As Variant
    If feldwert = "" Then Exit Function
    teile = Split(feldwert, "|")
    For k = 0 To UBound(teile)
        dn = Split(teile(k), ":")
        If k > 0 Then BohrungenText = BohrungenText & "; "
        BohrungenText = BohrungenText & dn(1) & "x" & ChrW(216) & DezText(Val(dn(0)))
    Next k
End Function

Private Function GewindeVorschlag(ByVal feldwert As String, gew() As String, kern() As Double, ByVal n As Long) As String
    Dim teile As Variant, k As Long, j As Long, dn As Variant, d As Double
    If feldwert = "" Then Exit Function
    teile = Split(feldwert, "|")
    For k = 0 To UBound(teile)
        dn = Split(teile(k), ":")
        d = Val(dn(0))
        For j = 1 To n
            If Abs(d - kern(j)) <= 0.05 Then
                If GewindeVorschlag <> "" Then GewindeVorschlag = GewindeVorschlag & "; "
                GewindeVorschlag = GewindeVorschlag & dn(1) & "x" & gew(j)
                Exit For
            End If
        Next j
    Next k
End Function

' Innenkonturen nach Größe: klein <= klein_bis < mittel <= mittel_bis < groß. kl(1..3) Anzahl, ll(1..3) Länge
Private Sub Konturklassen(ByVal feldwert As String, ByVal klein As Double, ByVal mittel As Double, _
                          kl() As Long, ll() As Double)
    Dim teile As Variant, k As Long, gl As Variant, g As Double, c As Long
    ReDim kl(1 To 3): ReDim ll(1 To 3)
    If feldwert = "" Then Exit Sub
    teile = Split(feldwert, "|")
    For k = 0 To UBound(teile)
        gl = Split(teile(k), ":")
        g = Round(Val(gl(0)), 2)     ' Ø10 genau auf der Grenze zählt als klein
        If g <= klein Then
            c = 1
        ElseIf g <= mittel Then
            c = 2
        Else
            c = 3
        End If
        kl(c) = kl(c) + 1
        ll(c) = ll(c) + Val(gl(1))
    Next k
End Sub

Private Function Artikel(ByVal i As Long) As String
    Artikel = W(i, "artikel")
End Function

' Vor dem Import: fehlende Profile (Liste) und Artikel, die schon im Auftrag stehen (Anzahl)
Private Sub Vorpruefung(fehlend As String, doppelt As Long)
    Dim i As Long, vorhanden As String, v As Variant, r As Long, id As String
    LiesProfile
    v = ThisWorkbook.Worksheets("Auftrag").Range("B" & O0 & ":B" & O1).Value
    vorhanden = vbLf
    For r = 1 To UBound(v)
        If Not Leer(v(r, 1)) Then vorhanden = vorhanden & Txt(v(r, 1)) & vbLf
    Next r
    fehlend = "": doppelt = 0
    For i = 1 To nM
        If W(i, "fehler") = "" And W(i, "profilform") <> "" Then
            id = W(i, "profil_id_vorschlag")
            If IsEmpty(FindeProfil(i)) And id <> "" Then
                If InStr(vbLf & fehlend & vbLf, vbLf & id & vbLf) = 0 Then
                    If fehlend <> "" Then fehlend = fehlend & vbLf
                    fehlend = fehlend & id
                End If
            End If
            If InStr(vorhanden, vbLf & Artikel(i) & vbLf) > 0 Then doppelt = doppelt + 1
        End If
    Next i
End Sub


' ================================================================== Übernahme in den Auftrag
Private Function Uebernehmen(ByVal werkstoff As String, ByVal stueck As Long, ByVal neueProfile As Boolean, _
                             ByVal erneut As Boolean) As String
    Dim wa As Worksheet, wl As Worksheet, av As Variant, r As Long, c As Long, i As Long, k As Long
    Dim vorhanden As String, naechstePos As Double, posMax As Double, zeile As Long, jetzt As Date
    Dim gew() As String, kern() As Double, nGew As Long, klein As Double, mittel As Double, grenzHinweis As String
    Dim hinweise As String, vorschlag As String, kl() As Long, ll() As Double, profilId As Variant, ziel As Variant
    Dim art As String, lr As Long, bericht As String, zeilen As Long, rr As Long
    Dim alteBerechnung As Long

    Set wa = ThisWorkbook.Worksheets("Auftrag")
    Set wl = ThisWorkbook.Worksheets(LOG_BLATT)
    LiesProfile
    LiesGewinde gew, kern, nGew
    LiesKonturgrenzen klein, mittel, grenzHinweis

    av = wa.Range("A" & O0 & ":J" & O1).Value
    vorhanden = vbLf
    For r = 1 To UBound(av)
        If Not Leer(av(r, 2)) Then
            If Not (IstZahl(av(r, 2)) And Txt(av(r, 2)) = "0") Then vorhanden = vorhanden & Txt(av(r, 2)) & vbLf
        End If
        If IstZahl(av(r, 1)) Then
            If av(r, 1) > posMax Then posMax = av(r, 1)
        End If
        For c = 1 To 10
            If Not Leer(av(r, c)) Then zeile = r + O0 - 1: Exit For
        Next c
    Next r
    naechstePos = Fix(posMax) + 10
    If zeile = 0 Then zeile = O0 Else zeile = zeile + 1
    jetzt = Now
    lr = 5 + Application.WorksheetFunction.CountA(wl.Range("A5:A100000"))   ' Protokollzeilen lückenlos

    alteBerechnung = Application.Calculation
    Application.ScreenUpdating = False
    Application.Calculation = -4135   ' xlCalculationManual
    On Error GoTo Fehler

    For i = 1 To nM
        If W(i, "fehler") <> "" Then
            wl.Cells(lr, 1).Value = jetzt
            wl.Cells(lr, 2).Value = AlsWert(W(i, "datei"))
            wl.Cells(lr, 30).Value = AlsWert("FEHLER: " & W(i, "fehler"))
            lr = lr + 1
            bericht = bericht & W(i, "datei") & ": FEHLER: " & W(i, "fehler") & vbLf
            GoTo Weiter
        End If
        art = Artikel(i)
        hinweise = W(i, "hinweise")
        vorschlag = GewindeVorschlag(W(i, "bohrungen"), gew, kern, nGew)
        Konturklassen W(i, "innen_liste"), klein, mittel, kl, ll
        If grenzHinweis <> "" And W(i, "innen_liste") <> "" Then Hinweis hinweise, grenzHinweis
        ziel = ""
        profilId = Empty
        If W(i, "profilform") <> "" Then
            profilId = FindeProfil(i)
            If IsEmpty(profilId) Then
                If neueProfile And W(i, "profil_id_vorschlag") <> "" Then
                    ProfilAnlegen i
                    LiesProfile
                    profilId = W(i, "profil_id_vorschlag")
                    Hinweis hinweise, "Profil neu in Stammdaten angelegt"
                Else
                    profilId = W(i, "profil_id_vorschlag")
                    Hinweis hinweise, "Profil fehlt in Stammdaten"
                End If
            End If
        End If
        If InStr(vorhanden, vbLf & art & vbLf) > 0 And Not erneut Then
            Hinweis hinweise, "übersprungen: Artikel steht schon im Auftrag"
        ElseIf Nz(i, "laenge") <= 0 Or W(i, "profilform") = "" Then
            Hinweis hinweise, "nicht übernommen: kein Rohrteil erkannt"
        ElseIf zeile > O1 Then
            Hinweis hinweise, "nicht übernommen: Auftragstabelle voll"
        Else
            wa.Cells(zeile, 1).Value = naechstePos
            wa.Cells(zeile, 2).Value = AlsWert(art)
            wa.Cells(zeile, 4).Value = AlsWert(profilId)
            If werkstoff <> "" Then wa.Cells(zeile, 5).Value = AlsWert(werkstoff)
            wa.Cells(zeile, 6).Value = Round(Nz(i, "laenge"), 1)
            If stueck > 0 Then wa.Cells(zeile, 7).Value = stueck
            wa.Cells(zeile, 8).Value = Round(Nz(i, "schneidweg"), 1)
            wa.Cells(zeile, 9).Value = CLng(Nz(i, "konturen"))
            If Nz(i, "ende_a") <> 0 Then
                wa.Cells(zeile, 25).Value = JaNein(W(i, "ende_a_gerade"))
                wa.Cells(zeile, 26).Value = Round(Nz(i, "ende_a"), 1)
            End If
            If Nz(i, "ende_b") <> 0 Then
                wa.Cells(zeile, 27).Value = JaNein(W(i, "ende_b_gerade"))
                wa.Cells(zeile, 28).Value = Round(Nz(i, "ende_b"), 1)
            End If
            wa.Cells(zeile, 29).Value = Round(Nz(i, "innen"), 1)
            wa.Cells(zeile, 30).Value = Round(Nz(i, "gravur"), 1)
            If W(i, "bohrungen") <> "" Then wa.Cells(zeile, 31).Value = AlsWert(BohrungenText(W(i, "bohrungen")))
            If vorschlag <> "" Then wa.Cells(zeile, 32).Value = AlsWert(vorschlag)
            For k = 1 To 3
                wa.Cells(zeile, 32 + 2 * k).Value = kl(k)
                wa.Cells(zeile, 33 + 2 * k).Value = Round(ll(k), 1)
            Next k
            ziel = zeile
            vorhanden = vorhanden & art & vbLf
            naechstePos = naechstePos + 10
            zeile = zeile + 1
            zeilen = zeilen + 1
        End If
        ' Protokoll
        Dim lw As Variant
        lw = Array(jetzt, W(i, "datei"), CLng(Nz(i, "koerper")), W(i, "profilform"), Round(Nz(i, "abm_a"), 2), _
                   Empty, Round(Nz(i, "wandstaerke"), 2), Round(Nz(i, "flaeche"), 1), Round(Nz(i, "laenge"), 1), _
                   Round(Nz(i, "schneidweg"), 1), CLng(Nz(i, "konturen")), JaNein(W(i, "ende_a_gerade")), _
                   Round(Nz(i, "ende_a"), 1), JaNein(W(i, "ende_b_gerade")), Round(Nz(i, "ende_b"), 1), _
                   Round(Nz(i, "innen"), 1), CLng(Nz(i, "innen_konturen")), Round(Nz(i, "gravur"), 1), _
                   CLng(Nz(i, "gravur_konturen")), BohrungenText(W(i, "bohrungen")), vorschlag, _
                   kl(1), Round(ll(1), 1), kl(2), Round(ll(2), 1), kl(3), Round(ll(3), 1), profilId, ziel, hinweise)
        If Round(Nz(i, "abm_b"), 2) <> 0 Then lw(5) = Round(Nz(i, "abm_b"), 2)
        For c = 0 To 29
            If VarType(lw(c)) = vbString Then
                If lw(c) = "" Then lw(c) = Empty
            End If
            wl.Cells(lr, c + 1).Value = AlsWert(lw(c))
        Next c
        lr = lr + 1
        If ziel = "" Then
            rr = 0
        Else
            rr = ziel
        End If
        If hinweise = "" Then
            bericht = bericht & art & ": Zeile " & IIf(rr = 0, "-", rr) & ", OK" & vbLf
        Else
            bericht = bericht & art & ": Zeile " & IIf(rr = 0, "-", rr) & ", " & hinweise & vbLf
        End If
Weiter:
    Next i

    With wl.Range("A5:AD" & IIf(lr > 5, lr - 1, 5))
        .Font.Name = "Arial"
    End With
    wl.Range("A5:A" & IIf(lr > 5, lr - 1, 5)).NumberFormat = "DD.MM.YYYY HH:MM"
    Application.Calculation = alteBerechnung
    Application.ScreenUpdating = True
    Application.Calculate
    Uebernehmen = zeilen & " Position(en) in den Auftrag übernommen." & vbLf & vbLf & bericht
    Exit Function
Fehler:
    Dim nr As Long, txtF As String
    nr = Err.Number: txtF = Err.Description
    Application.Calculation = alteBerechnung
    Application.ScreenUpdating = True
    Err.Raise nr, , txtF
End Function

' Text als Text eintragen: Excel würde z. B. "1.4301" sonst in eine Zahl umwandeln.
Private Function AlsWert(ByVal v As Variant) As Variant
    If VarType(v) = vbString Then AlsWert = "'" & v Else AlsWert = v
End Function

Private Sub Hinweis(liste As String, ByVal neu As String)
    If liste = "" Then liste = neu Else liste = liste & "; " & neu
End Sub

Private Function JaNein(ByVal wert As String) As String
    If wert = "1" Then JaNein = "ja" Else JaNein = "nein"
End Function
