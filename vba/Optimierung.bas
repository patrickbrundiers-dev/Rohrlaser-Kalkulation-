Attribute VB_Name = "Optimierung"
' Stangenoptimierung für die Kalkulationsmappe (VBA-Fassung von tools/optimierung.py).
'
' Liest die Positionen aus dem Blatt "Auftrag", teilt die Teile je Profil + Werkstoff
' + Stangenlänge auf möglichst wenige Stangen auf und schreibt das Ergebnis in die
' Blätter "Schnittplan", "Stangenbelegung" und "Auswertung".
'
' Regeln (siehe Blatt "Anleitung", A15/A16):
' - Belegung = Endbeschnitt + Teile + Trennungen + Schnittverlust des letzten Schnitts;
'   frei bleiben muss der Greiferrest.
' - Trennung zwischen zwei Teilen: beide zugewandten Enden gerade = 1 gemeinsamer Schnitt
'   (1 x Schnittverlust), sonst 2 Schnitte (2 x Schnittverlust + Abstand getrennte Schnitte).
' - Teile dürfen gedreht werden. Keine Restlagerverwaltung: Reste sind Verschnitt.
'
' Verfahren, Sortierungen und Gleichstandsregeln entsprechen der Python-Fassung genau,
' damit beide dasselbe Ergebnis liefern (geprüft mit tests/test_vba.py).
'
' Listen sind Long-Arrays mit der Anzahl in Element 0. Eine angeordnete Stange (Folge)
' speichert je Platz Teil * 2 + 1, wenn das Teil gedreht liegt, sonst Teil * 2.
Option Explicit

Private Const M0 As Long = 5
Private Const M1 As Long = 304
Private Const O0 As Long = 13
Private Const O1 As Long = 512
Private Const S0 As Long = 5
Private Const S1 As Long = 1004
Private Const D0 As Long = 5
Private Const D1 As Long = 10004
Private Const EPS As Double = 0.000001
Private Const FEHLER_BASIS As Long = -2147221504   ' vbObjectError
Private Const EXAKT_MAX_TEILE As Long = 60      ' exakte Suche nur für Gruppen bis zu so vielen Teilen
Private Const EXAKT_MAX_KNOTEN As Long = 20000  ' Suchschritte je Gruppe

' Teile aller Gruppen
Private nT As Long
Private tZeile() As Long, tPos() As Variant, tArt() As Variant, tNr() As Long
Private tLen() As Double, tAg() As Boolean, tBg() As Boolean, tAs() As Double, tBs() As Double

' Gruppen (Profil + Werkstoff + Stangenlänge)
Private nG As Long
Private gProfil() As Variant, gWst() As Variant, gStange() As Double, gEnd() As Double, gGreif() As Double
Private gKerf() As Double, gAbst() As Double, gTeile() As Variant, gErg() As Variant, gBew() As Boolean

' Nicht eingeplante Teile
Private nF As Long
Private fZeile() As Long, fPos() As Variant, fArt() As Variant, fAnz() As Long, fGrund() As String

' Werte der gerade bearbeiteten Gruppe
Private cEnd As Double, cKerf As Double, cAbst As Double, cNb As Double

' Zustand der exakten Suche
Private xT() As Long, xBedarf() As Double, xRest() As Double, xZu() As Long, xN As Long, xNutz As Double
Private xSt() As Variant, xBel() As Double, xNSt As Long, xBeste As Variant, xBesteN As Long
Private xKnoten As Long, xAbbruch As Boolean, xUG As Long


' ================================================================== Einstieg
Public Sub Optimieren()
    Dim bericht As String
    On Error GoTo Fehler
    bericht = OptimiereMappe()
    MsgBox bericht, vbInformation, "Stangenoptimierung"
    Exit Sub
Fehler:
    MsgBox "Optimierung abgebrochen:" & vbLf & Err.Description, vbExclamation, "Stangenoptimierung"
End Sub

' Führt die Optimierung aus und gibt den Bericht als Text zurück (ohne Meldungsfenster).
Public Function OptimiereMappe() As String
    Dim alteBerechnung As Long, g As Long, s As String, k As Long
    alteBerechnung = Application.Calculation
    Application.ScreenUpdating = False
    Application.Calculation = -4135   ' xlCalculationManual
    On Error GoTo Fehler
    LiesAuftrag
    For g = 1 To nG
        WaehleGruppe g
        gErg(g) = Optimiere(gTeile(g), g)
    Next g
    Pruefe
    Schreibe
    ThisWorkbook.Worksheets("Listen").Range("E5").Value = "nein"   ' Optimierung aktuell (Auftrag C10)
    Application.Calculation = alteBerechnung
    Application.Calculate
    Application.ScreenUpdating = True
    For g = 1 To nG
        WaehleGruppe g
        s = s & gProfil(g) & " / " & gWst(g) & " / " & gStange(g) & " mm: " & gTeile(g)(0) & " Teile -> " & _
            Anzahl(gErg(g)) & " Stangen (manuell " & Manuell(gTeile(g)) & ", Untergrenze " & _
            Untergrenze(gTeile(g)) & "), " & GemeinsameGesamt(gErg(g)) & " gemeinsame Schnitte, " & _
            Bewertung(g) & vbLf
    Next g
    If nG = 0 Then s = "Keine einplanbaren Positionen." & vbLf
    For k = 1 To nF
        s = s & "NICHT EINGEPLANT Zeile " & fZeile(k) & " " & fArt(k) & ": " & fGrund(k) & vbLf
    Next k
    OptimiereMappe = s
    Exit Function
Fehler:
    Dim nr As Long, txtF As String
    nr = Err.Number: txtF = Err.Description
    Application.Calculation = alteBerechnung
    Application.ScreenUpdating = True
    Err.Raise nr, , txtF
End Function


' ================================================================== Listen
Private Function NeueListe() As Variant
    Dim a() As Long
    ReDim a(0 To 8)
    NeueListe = a
End Function

Private Sub Anh(l As Variant, ByVal wert As Long)
    Dim n As Long, a() As Long
    n = l(0) + 1
    If n > UBound(l) Then
        a = l
        ReDim Preserve a(0 To 2 * n)
        l = a
    End If
    l(n) = wert
    l(0) = n
End Sub

' Kopie einer Liste. Ausdrücklich Element für Element, weil LibreOffice (Testumgebung)
' Arrays bei Zuweisung nicht kopiert, Excel aber schon.
Private Function Kopie(l As Variant) As Variant
    Dim a() As Long, i As Long
    ReDim a(0 To UBound(l))
    For i = 0 To l(0)
        a(i) = l(i)
    Next i
    Kopie = a
End Function

Private Function MitTeil(l As Variant, ByVal t As Long) As Variant
    Dim x As Variant
    x = Kopie(l)
    Anh x, t
    MitTeil = x
End Function

Private Function Anzahl(st As Variant) As Long
    If IsEmpty(st) Then Anzahl = 0 Else Anzahl = UBound(st)
End Function


' ================================================================== Belegung einer Stange
Private Sub WaehleGruppe(ByVal g As Long)
    cEnd = gEnd(g): cKerf = gKerf(g): cAbst = gAbst(g): cNb = gStange(g) - gGreif(g)
End Sub

Private Function Trennung(ByVal eGer As Boolean, ByVal aGer As Boolean) As Double
    If eGer And aGer Then Trennung = cKerf Else Trennung = 2 * cKerf + cAbst
End Function

Private Function AnfangGerade(ByVal code As Long) As Boolean
    If code Mod 2 = 1 Then AnfangGerade = tBg(code \ 2) Else AnfangGerade = tAg(code \ 2)
End Function

Private Function EndeGerade(ByVal code As Long) As Boolean
    If code Mod 2 = 1 Then EndeGerade = tAg(code \ 2) Else EndeGerade = tBg(code \ 2)
End Function

Private Function Kodiert(ByVal t As Long, ByVal gedreht As Boolean) As Long
    If gedreht Then Kodiert = 2 * t + 1 Else Kodiert = 2 * t
End Function

' Reihenfolge und Lage so wählen, dass möglichst viele gerade Enden aneinanderliegen.
' Schräge Enden kommen an Stangenanfang/-ende, übrige schräge Enden werden paarweise
' gegeneinander gelegt.
Private Function Anordnen(l As Variant) As Variant
    Dim n As Long, i As Long, t As Long, j As Long
    Dim ss() As Long, sn() As Long, nn() As Long, nss As Long, nsn As Long, nnn As Long
    Dim isn As Long, inn As Long, f As Variant
    Dim hatStart As Boolean, hatEnde As Boolean, cStart As Long, cEnde As Long
    n = l(0)
    f = NeueListe()
    If n = 0 Then Anordnen = f: Exit Function
    ReDim ss(1 To n): ReDim sn(1 To n): ReDim nn(1 To n)
    For i = 1 To n
        t = l(i)
        If tAg(t) And tBg(t) Then
            nss = nss + 1: ss(nss) = t
        ElseIf tAg(t) <> tBg(t) Then
            nsn = nsn + 1: sn(nsn) = t
        Else
            nnn = nnn + 1: nn(nnn) = t
        End If
    Next i
    isn = 1: inn = 1
    ' schräges Ende vorn: gedreht, wenn A gerade ist; hinten: gedreht, wenn A schräg ist
    If isn <= nsn Then
        cStart = Kodiert(sn(isn), tAg(sn(isn))): isn = isn + 1: hatStart = True
    ElseIf inn <= nnn Then
        cStart = Kodiert(nn(inn), False): inn = inn + 1: hatStart = True
    End If
    If isn <= nsn Then
        cEnde = Kodiert(sn(isn), Not tAg(sn(isn))): isn = isn + 1: hatEnde = True
    ElseIf inn <= nnn Then
        cEnde = Kodiert(nn(inn), False): inn = inn + 1: hatEnde = True
    End If
    If hatStart Then Anh f, cStart
    For i = 1 To nss
        Anh f, Kodiert(ss(i), False)
    Next i
    ' restliche: S-N | N-N ... | N-S | S-N | N-S ...
    j = 0
    Do While isn <= nsn
        t = sn(isn): isn = isn + 1
        If j Mod 2 = 0 Then
            Anh f, Kodiert(t, Not tAg(t))
            Do While inn <= nnn
                Anh f, Kodiert(nn(inn), False): inn = inn + 1
            Loop
        Else
            Anh f, Kodiert(t, tAg(t))
        End If
        j = j + 1
    Loop
    Do While inn <= nnn
        Anh f, Kodiert(nn(inn), False): inn = inn + 1
    Loop
    If hatEnde Then Anh f, cEnde
    Anordnen = f
End Function

' Position hinter dem letzten Schnitt (inkl. Schnittverlust) ab Stangenanfang.
Private Function Verbrauch(f As Variant) As Double
    Dim pos As Double, i As Long, c As Long
    pos = cEnd
    For i = 1 To f(0)
        c = f(i)
        If i > 1 Then pos = pos + Trennung(EndeGerade(f(i - 1)), AnfangGerade(c))
        pos = pos + tLen(c \ 2)
    Next i
    If f(0) > 0 Then pos = pos + cKerf
    Verbrauch = pos
End Function

Private Function Passt(l As Variant) As Boolean
    Passt = Verbrauch(Anordnen(l)) <= cNb + EPS
End Function


' ================================================================== Packverfahren
Private Function VorTeil(ByVal a As Long, ByVal b As Long) As Boolean
    ' Sortierschlüssel (-Länge, Zeile, Nr.)
    If tLen(a) <> tLen(b) Then
        VorTeil = tLen(a) > tLen(b)
    ElseIf tZeile(a) <> tZeile(b) Then
        VorTeil = tZeile(a) < tZeile(b)
    Else
        VorTeil = tNr(a) < tNr(b)
    End If
End Function

Private Function Sortiert(l As Variant) As Variant
    Dim x As Variant, i As Long, j As Long, v As Long
    x = Kopie(l)
    For i = 2 To x(0)
        v = x(i): j = i - 1
        Do While j >= 1
            If Not VorTeil(v, x(j)) Then Exit Do
            x(j + 1) = x(j): j = j - 1
        Loop
        x(j + 1) = v
    Next i
    Sortiert = x
End Function

Private Sub NeueStange(st As Variant, ByVal t As Long)
    Dim n As Long, l As Variant
    n = Anzahl(st) + 1
    If n = 1 Then
        Dim neu() As Variant
        ReDim neu(1 To 1)
        st = neu
    Else
        Dim a() As Variant
        a = st
        ReDim Preserve a(1 To n)
        st = a
    End If
    l = NeueListe()
    Anh l, t
    st(n) = l
End Sub

Private Function FirstFit(teile As Variant) As Variant
    Dim st As Variant, srt As Variant, i As Long, s As Long, t As Long, ok As Boolean, l As Variant
    srt = Sortiert(teile)
    For i = 1 To srt(0)
        t = srt(i): ok = False
        For s = 1 To Anzahl(st)
            If Passt(MitTeil(st(s), t)) Then
                l = st(s): Anh l, t: st(s) = l: ok = True: Exit For
            End If
        Next s
        If Not ok Then NeueStange st, t
    Next i
    FirstFit = st
End Function

Private Function BestFit(teile As Variant) As Variant
    Dim st As Variant, srt As Variant, i As Long, s As Long, t As Long
    Dim beste As Long, restMin As Double, v As Double, l As Variant
    srt = Sortiert(teile)
    For i = 1 To srt(0)
        t = srt(i): beste = 0
        For s = 1 To Anzahl(st)
            v = Verbrauch(Anordnen(MitTeil(st(s), t)))
            If v <= cNb + EPS Then
                If beste = 0 Then
                    beste = s: restMin = cNb - v
                ElseIf cNb - v < restMin Then
                    beste = s: restMin = cNb - v
                End If
            End If
        Next s
        If beste = 0 Then
            NeueStange st, t
        Else
            l = st(beste): Anh l, t: st(beste) = l
        End If
    Next i
    BestFit = st
End Function

Private Function Summe(l As Variant) As Double
    Dim i As Long
    For i = 1 To l(0)
        Summe = Summe + tLen(l(i))
    Next i
End Function

' Stabile Sortierung von Indizes nach Schlüssel (aufsteigend).
Private Function Reihenfolge(schluessel() As Double, ByVal n As Long) As Variant
    Dim o() As Long, i As Long, j As Long, v As Long
    ReDim o(1 To IIf(n < 1, 1, n))
    For i = 1 To n
        v = i: j = i - 1
        Do While j >= 1
            If Not schluessel(v) < schluessel(o(j)) Then Exit Do
            o(j + 1) = o(j): j = j - 1
        Loop
        o(j + 1) = v
    Next i
    Reihenfolge = o
End Function

' Schwach belegte Stangen auflösen, wenn alle ihre Teile in andere Stangen passen.
Private Function Aufloesen(stIn As Variant) As Variant
    Dim st As Variant, an As Variant, n As Long, i As Long, k As Long, x As Long, oi As Long
    Dim s As Long, srt As Variant, t As Long, ziel As Long, ok As Boolean, geaendert As Boolean
    Dim schl() As Double, o As Variant, o2 As Variant, schl2() As Double, neu() As Variant, l As Variant
    st = stIn
    geaendert = True
    Do While geaendert And Anzahl(st) > 1
        geaendert = False
        n = Anzahl(st)
        ReDim schl(1 To n)
        For i = 1 To n
            schl(i) = Summe(st(i))
        Next i
        o = Reihenfolge(schl, n)
        For oi = 1 To n
            s = o(oi)
            ReDim neu(1 To n - 1)
            an = neu
            k = 0
            For i = 1 To n
                If i <> s Then k = k + 1: an(k) = Kopie(st(i))
            Next i
            ok = True
            srt = Sortiert(st(s))
            For i = 1 To srt(0)
                t = srt(i)
                ReDim schl2(1 To n - 1)
                For x = 1 To n - 1
                    schl2(x) = -Verbrauch(Anordnen(an(x)))
                Next x
                o2 = Reihenfolge(schl2, n - 1)
                ziel = 0
                For x = 1 To n - 1
                    If Passt(MitTeil(an(o2(x)), t)) Then ziel = o2(x): Exit For
                Next x
                If ziel = 0 Then ok = False: Exit For
                l = an(ziel): Anh l, t: an(ziel) = l
            Next i
            If ok Then
                st = an: geaendert = True: Exit For
            End If
        Next oi
    Loop
    Aufloesen = st
End Function

Private Function GemeinsameSchnitte(f As Variant) As Long
    Dim i As Long
    For i = 1 To f(0) - 1
        If EndeGerade(f(i)) And AnfangGerade(f(i + 1)) Then GemeinsameSchnitte = GemeinsameSchnitte + 1
    Next i
End Function

Private Function GemeinsameGesamt(folgen As Variant) As Long
    Dim s As Long
    For s = 1 To Anzahl(folgen)
        GemeinsameGesamt = GemeinsameGesamt + GemeinsameSchnitte(folgen(s))
    Next s
End Function

Private Function Gleichartig(ByVal a As Long, ByVal b As Long) As Boolean
    Gleichartig = (tLen(a) = tLen(b) And tAg(a) = tAg(b) And tBg(a) = tBg(b))
End Function

' Exakte Suche (Branch and Bound) nach einer Einteilung mit weniger als ziel Stangen.
' Teile in der Reihenfolge von Sortiert, jedes Teil der Reihe nach in jede vorhandene Stange,
' dann in eine neue. Abgeschnitten wird, wenn selbst bei voller Nutzung aller freien Längen
' nicht weniger Stangen als das bisher beste Ergebnis möglich sind.
' Ergebnis: Stangen oder Empty; vollstaendig = Suche nicht wegen EXAKT_MAX_KNOTEN abgebrochen.
Private Function Exakt(teile As Variant, ByVal ziel As Long, vollstaendig As Boolean) As Variant
    Dim srt As Variant, i As Long
    srt = Sortiert(teile)
    xN = srt(0)
    xNutz = cNb - cEnd
    ReDim xT(1 To xN): ReDim xBedarf(1 To xN): ReDim xRest(1 To xN + 1): ReDim xZu(1 To xN)
    ReDim xSt(1 To xN): ReDim xBel(1 To xN)
    For i = 1 To xN
        xT(i) = srt(i): xBedarf(i) = tLen(srt(i)) + cKerf
    Next i
    xRest(xN + 1) = 0
    For i = xN To 1 Step -1
        xRest(i) = xRest(i + 1) + xBedarf(i)
    Next i
    xUG = Untergrenze(teile)
    xNSt = 0: xBeste = Empty: xBesteN = ziel: xKnoten = 0: xAbbruch = False
    Suche 1
    vollstaendig = (Not xAbbruch) Or xBesteN <= xUG
    Exakt = xBeste
End Function

Private Sub Suche(ByVal i As Long)
    Dim frei As Double, neu As Long, s As Long, start As Long, t As Long, l As Variant, b() As Variant
    If i > xN Then
        ReDim b(1 To xNSt)
        For s = 1 To xNSt
            b(s) = Kopie(xSt(s))
        Next s
        xBeste = b: xBesteN = xNSt
        Exit Sub
    End If
    xKnoten = xKnoten + 1
    If xKnoten > EXAKT_MAX_KNOTEN Then xAbbruch = True: Exit Sub
    For s = 1 To xNSt
        frei = frei + (xNutz - xBel(s))
    Next s
    If xRest(i) > frei + EPS Then neu = -Int(-((xRest(i) - frei) / xNutz - EPS))
    If xNSt + neu >= xBesteN Then Exit Sub
    t = xT(i)
    start = 1
    If i > 1 Then
        If Gleichartig(xT(i - 1), t) Then start = xZu(i - 1)
    End If
    For s = start To xNSt
        If xBel(s) + xBedarf(i) <= xNutz + EPS Then
            If Passt(MitTeil(xSt(s), t)) Then
                l = xSt(s): Anh l, t: xSt(s) = l
                xBel(s) = xBel(s) + xBedarf(i)
                xZu(i) = s
                Suche i + 1
                l = xSt(s): l(0) = l(0) - 1: xSt(s) = l
                xBel(s) = xBel(s) - xBedarf(i)
                If xAbbruch Or xBesteN <= xUG Then Exit Sub
            End If
        End If
    Next s
    If xNSt + 1 < xBesteN Then
        xNSt = xNSt + 1
        l = NeueListe(): Anh l, t: xSt(xNSt) = l
        xBel(xNSt) = xBedarf(i)
        xZu(i) = xNSt
        Suche i + 1
        xNSt = xNSt - 1
    End If
End Sub

' Text für die Auswertung: wie nah das Ergebnis am Optimum liegt.
Private Function Bewertung(ByVal g As Long) As String
    If Anzahl(gErg(g)) <= Untergrenze(gTeile(g)) Then
        Bewertung = "optimal (Untergrenze erreicht)"
    ElseIf gBew(g) Then
        Bewertung = "optimal (alle Einteilungen geprüft)"
    Else
        Bewertung = "nicht bewiesen (Suche begrenzt)"
    End If
End Function

' Ergebnis: je Stange die angeordnete Folge; volle Stangen zuerst, Reststange zuletzt.
' Setzt gBew(g), wenn die Stangenzahl nachweislich minimal ist.
Private Function Optimiere(teile As Variant, ByVal g As Long) As Variant
    Dim ff As Variant, bf As Variant, folgen As Variant, s As Long, n As Long, i As Long, j As Long
    Dim v As Variant, vs() As Double, zs() As Long, tv As Double, tz As Long
    ff = Aufloesen(FirstFit(teile))
    bf = Aufloesen(BestFit(teile))
    For s = 1 To Anzahl(ff): ff(s) = Anordnen(ff(s)): Next s
    For s = 1 To Anzahl(bf): bf(s) = Anordnen(bf(s)): Next s
    If Anzahl(bf) < Anzahl(ff) Then
        folgen = bf
    ElseIf Anzahl(bf) = Anzahl(ff) And GemeinsameGesamt(bf) > GemeinsameGesamt(ff) Then
        folgen = bf
    Else
        folgen = ff
    End If
    Dim ug As Long, ex As Variant, bew As Boolean
    ug = Untergrenze(teile)
    bew = (Anzahl(folgen) <= ug)
    If Not bew And teile(0) <= EXAKT_MAX_TEILE Then
        ex = Exakt(teile, Anzahl(folgen), bew)
        If Not IsEmpty(ex) Then
            For s = 1 To Anzahl(ex): ex(s) = Anordnen(ex(s)): Next s
            folgen = ex
        End If
    End If
    gBew(g) = bew
    ' stabil sortieren nach (-Belegung, Zeile des ersten Teils)
    n = Anzahl(folgen)
    ReDim vs(1 To n): ReDim zs(1 To n)
    For s = 1 To n
        vs(s) = Verbrauch(folgen(s)): zs(s) = tZeile(folgen(s)(1) \ 2)
    Next s
    For i = 2 To n
        v = folgen(i): tv = vs(i): tz = zs(i): j = i - 1
        Do While j >= 1
            If Not (tv > vs(j) Or (tv = vs(j) And tz < zs(j))) Then Exit Do
            folgen(j + 1) = folgen(j): vs(j + 1) = vs(j): zs(j + 1) = zs(j): j = j - 1
        Loop
        folgen(j + 1) = v: vs(j + 1) = tv: zs(j + 1) = tz
    Next i
    Optimiere = folgen
End Function

' Einfache manuelle Einteilung: Eingabereihenfolge, keine Drehung, Stange voll, dann nächste.
' Ergebnis: Anzahl Stangen.
Private Function Manuell(teile As Variant) As Long
    Dim akt As Variant, i As Long, t As Long, x As Variant, j As Long
    akt = NeueListe()
    For i = 1 To teile(0)
        t = teile(i)
        If akt(0) > 0 Then
            x = NeueListe()
            For j = 1 To akt(0): Anh x, Kodiert(akt(j), False): Next j
            Anh x, Kodiert(t, False)
            If Verbrauch(x) > cNb + EPS Then
                Manuell = Manuell + 1
                akt = NeueListe()
            End If
        End If
        Anh akt, t
    Next i
    If akt(0) > 0 Then Manuell = Manuell + 1
End Function

Private Function Untergrenze(teile As Variant) As Long
    Dim i As Long, s As Double
    If teile(0) = 0 Then Exit Function
    For i = 1 To teile(0)
        s = s + (tLen(teile(i)) + cKerf)
    Next i
    Untergrenze = -Int(-(s / (cNb - cEnd) - EPS))
End Function

Private Function ManuellAusnutzung(teile As Variant, ByVal g As Long) As Double
    Dim n As Long
    n = Manuell(teile)
    If n > 0 Then ManuellAusnutzung = Summe(teile) / (n * gStange(g))
End Function

' Unabhängige Kontrolle: keine Stange überbelegt, jedes Teil genau einmal eingeplant.
Private Sub Pruefe()
    Dim g As Long, s As Long, i As Long, zaehl() As Long, folgen As Variant
    ReDim zaehl(0 To IIf(nT < 1, 1, nT))
    For g = 1 To nG
        WaehleGruppe g
        folgen = gErg(g)
        For s = 1 To Anzahl(folgen)
            If Verbrauch(folgen(s)) > cNb + EPS Then Err.Raise FEHLER_BASIS + 2, , gProfil(g) & ": Stange überbelegt"
            For i = 1 To folgen(s)(0)
                zaehl(folgen(s)(i) \ 2) = zaehl(folgen(s)(i) \ 2) + 1
            Next i
        Next s
        For i = 1 To gTeile(g)(0)
            If zaehl(gTeile(g)(i)) <> 1 Then Err.Raise FEHLER_BASIS + 3, , gProfil(g) & ": Teile fehlen oder doppelt"
        Next i
    Next g
End Sub


' ================================================================== Mappe lesen
Private Function IstZahl(v As Variant) As Boolean
    Select Case VarType(v)
        Case vbInteger, vbLong, vbSingle, vbDouble, vbCurrency, vbDecimal, vbByte, 20
            IstZahl = True
    End Select
End Function

Private Function Zahl(v As Variant) As Double
    If IstZahl(v) Then Zahl = CDbl(v)
End Function

Private Function Leer(v As Variant) As Boolean
    If IsError(v) Then Exit Function
    If IsEmpty(v) Then
        Leer = True
    ElseIf VarType(v) = vbString Then
        Leer = (Len(v) = 0)
    End If
End Function

Private Function Txt(v As Variant) As String
    If IsError(v) Then Txt = "#FEHLER" Else Txt = CStr(v)
End Function

Private Function Umfang(ByVal form As String, ByVal a As Double, ByVal b As Double) As Double
    Select Case form
        Case "Rundrohr": Umfang = 4 * Atn(1) * a
        Case "Quadratrohr": Umfang = 4 * a
        Case "Rechteckrohr": If b = 0 Then Umfang = 4 * a Else Umfang = 2 * (a + b)
    End Select
End Function

Private Sub Fehlt(ByVal r As Long, pos As Variant, art As Variant, ByVal stk As Long, ByVal grund As String)
    nF = nF + 1
    ReDim Preserve fZeile(1 To nF): ReDim Preserve fPos(1 To nF): ReDim Preserve fArt(1 To nF)
    ReDim Preserve fAnz(1 To nF): ReDim Preserve fGrund(1 To nF)
    fZeile(nF) = r: fPos(nF) = pos: fArt(nF) = art: fAnz(nF) = stk: fGrund(nF) = grund
End Sub

Private Sub NeuesTeil(ByVal g As Long, ByVal r As Long, pos As Variant, art As Variant, ByVal nr As Long, _
                      ByVal laenge As Double, ByVal ag As Boolean, ByVal bg As Boolean, _
                      ByVal schA As Double, ByVal schB As Double)
    nT = nT + 1
    If nT > UBound(tZeile) Then
        Dim k As Long
        k = 2 * nT
        ReDim Preserve tZeile(0 To k): ReDim Preserve tPos(0 To k): ReDim Preserve tArt(0 To k)
        ReDim Preserve tNr(0 To k): ReDim Preserve tLen(0 To k): ReDim Preserve tAg(0 To k)
        ReDim Preserve tBg(0 To k): ReDim Preserve tAs(0 To k): ReDim Preserve tBs(0 To k)
    End If
    tZeile(nT) = r: tPos(nT) = pos: tArt(nT) = art: tNr(nT) = nr: tLen(nT) = laenge
    tAg(nT) = ag: tBg(nT) = bg: tAs(nT) = schA: tBs(nT) = schB
    Dim l As Variant
    l = gTeile(g)
    Anh l, nT
    gTeile(g) = l
End Sub

Private Sub LiesAuftrag()
    Dim wa As Worksheet, pv As Variant, mv As Variant, wv As Variant, av As Variant
    Dim r As Long, i As Long, k As Long, prow As Long, mrow As Long, g As Long
    Dim mEnd As Double, mGreif As Double, mKerf As Double, mMax As Double, mAbst As Double
    Dim maschine As Variant, stdStange As Double, pos As Variant, art As Variant, pid As Variant, wst As Variant
    Dim laenge As Double, stk As Variant, stkN As Long, nameT As Variant, stange As Double
    Dim pEnd As Double, pGreif As Double, u As Double, h As Double, schA As Double, schB As Double
    Dim wstOk As Boolean, pb As Double

    Set wa = ThisWorkbook.Worksheets("Auftrag")
    pv = ThisWorkbook.Worksheets("Profile").Range("A" & M0 & ":H" & M1).Value
    mv = ThisWorkbook.Worksheets("Maschinen").Range("A" & M0 & ":J" & M1).Value
    wv = ThisWorkbook.Worksheets("Werkstoffe").Range("A" & M0 & ":A" & M1).Value
    av = wa.Range("A" & O0 & ":AB" & O1).Value

    nT = 0: nG = 0: nF = 0
    ReDim tZeile(0 To 64): ReDim tPos(0 To 64): ReDim tArt(0 To 64): ReDim tNr(0 To 64)
    ReDim tLen(0 To 64): ReDim tAg(0 To 64): ReDim tBg(0 To 64): ReDim tAs(0 To 64): ReDim tBs(0 To 64)
    ReDim gProfil(0 To 0): ReDim gWst(0 To 0): ReDim gStange(0 To 0): ReDim gEnd(0 To 0)
    ReDim gGreif(0 To 0): ReDim gKerf(0 To 0): ReDim gAbst(0 To 0): ReDim gTeile(0 To 0): ReDim gErg(0 To 0)
    ReDim gBew(0 To 0)

    maschine = wa.Range("C8").Value
    For i = 1 To M1 - M0 + 1
        If Not Leer(maschine) Then
            If Txt(mv(i, 1)) = Txt(maschine) And Not Leer(mv(i, 1)) Then mrow = i: Exit For
        End If
    Next i
    If mrow = 0 Then Err.Raise FEHLER_BASIS + 1, , "Maschine '" & Txt(maschine) & _
        "' im Auftragskopf (C8) nicht im Blatt 'Maschinen' gefunden"
    mEnd = Zahl(mv(mrow, 3)): mGreif = Zahl(mv(mrow, 4)): mKerf = Zahl(mv(mrow, 5))
    mMax = Zahl(mv(mrow, 6)): mAbst = Zahl(mv(mrow, 10))
    stdStange = Zahl(wa.Range("C9").Value)

    For r = O0 To O1
        k = r - O0 + 1
        pos = av(k, 1): art = av(k, 2): pid = av(k, 4): wst = av(k, 5): stk = av(k, 7)
        laenge = Zahl(av(k, 6))
        If Leer(pid) And Leer(wst) And Not IstZahl(av(k, 6)) And Leer(stk) Then GoTo Weiter
        If Leer(art) Then
            nameT = "Zeile " & r
        ElseIf IstZahl(art) Then
            If art = 0 Then nameT = "Zeile " & r Else nameT = art
        Else
            nameT = art
        End If
        stkN = 0
        If IstZahl(stk) Then
            If stk >= 1 And Int(stk) = stk Then stkN = CLng(stk)
        End If
        ' Profil (bei doppelter ID gilt die letzte Zeile)
        prow = 0
        If Not Leer(pid) Then
            For i = M1 - M0 + 1 To 1 Step -1
                If Not Leer(pv(i, 1)) Then
                    If Txt(pv(i, 1)) = Txt(pid) Then prow = i: Exit For
                End If
            Next i
        End If
        If prow = 0 Then Fehlt r, pos, nameT, stkN, "Profil unbekannt": GoTo Weiter
        wstOk = False
        If Not Leer(wst) Then
            For i = 1 To M1 - M0 + 1
                If Not Leer(wv(i, 1)) Then
                    If Txt(wv(i, 1)) = Txt(wst) Then wstOk = True: Exit For
                End If
            Next i
        End If
        If Not wstOk Then Fehlt r, pos, nameT, stkN, "Werkstoff unbekannt": GoTo Weiter
        If laenge <= 0 Then Fehlt r, pos, nameT, stkN, "Teilelänge fehlt": GoTo Weiter
        If stkN = 0 Then Fehlt r, pos, nameT, stkN, "Stückzahl fehlt oder ungültig": GoTo Weiter
        stange = Zahl(av(k, 10))
        If stange = 0 Then stange = stdStange
        If stange = 0 Then Fehlt r, pos, nameT, stkN, "Stangenlänge fehlt": GoTo Weiter
        If mMax <> 0 And stange > mMax Then Fehlt r, pos, nameT, stkN, "Stange länger als Maschine zulässt": GoTo Weiter
        If IstZahl(pv(prow, 7)) Then pEnd = CDbl(pv(prow, 7)) Else pEnd = mEnd
        If IstZahl(pv(prow, 8)) Then pGreif = CDbl(pv(prow, 8)) Else pGreif = mGreif
        If pEnd + laenge + mKerf > stange - pGreif + EPS Then
            Fehlt r, pos, nameT, stkN, "Teil länger als Nutzlänge der Stange": GoTo Weiter
        End If
        ' Gruppe suchen oder anlegen
        g = 0
        For i = 1 To nG
            If Txt(gProfil(i)) = Txt(pid) And Txt(gWst(i)) = Txt(wst) And gStange(i) = stange Then g = i: Exit For
        Next i
        If g = 0 Then
            nG = nG + 1: g = nG
            ReDim Preserve gProfil(0 To nG): ReDim Preserve gWst(0 To nG): ReDim Preserve gStange(0 To nG)
            ReDim Preserve gEnd(0 To nG): ReDim Preserve gGreif(0 To nG): ReDim Preserve gKerf(0 To nG)
            ReDim Preserve gAbst(0 To nG): ReDim Preserve gTeile(0 To nG): ReDim Preserve gErg(0 To nG)
            ReDim Preserve gBew(0 To nG)
            gProfil(g) = pid: gWst(g) = wst: gStange(g) = stange: gEnd(g) = pEnd: gGreif(g) = pGreif
            gKerf(g) = mKerf: gAbst(g) = mAbst: gTeile(g) = NeueListe()
        End If
        pb = Zahl(pv(prow, 4))
        u = Umfang(Txt(pv(prow, 2)), Zahl(pv(prow, 3)), pb)
        h = Zahl(av(k, 8))
        If h <> 0 Then   ' Schneidweg enthält beide Endschnitte -> Ersatzwert nicht größer als die Hälfte
            If h / 2 < u Then u = h / 2
        End If
        schA = Zahl(av(k, 26)): If schA = 0 Then schA = u
        schB = Zahl(av(k, 28)): If schB = 0 Then schB = u
        For i = 1 To stkN
            NeuesTeil g, r, pos, nameT, i, laenge, Txt(av(k, 25)) <> "nein", Txt(av(k, 27)) <> "nein", schA, schB
        Next i
Weiter:
    Next r
End Sub


' ================================================================== Ergebnis schreiben
Private Function ZahlText(ByVal x As Double) As String
    ' wie Python "{:g}": höchstens 6 gültige Stellen
    Dim d As Long
    d = Len(CStr(Int(Abs(x))))
    If d < 6 Then x = Round(x, 6 - d) Else x = Round(x, 0)
    ZahlText = CStr(x)
End Function

Private Sub Kopfzelle(c As Range)
    c.Font.Name = "Arial": c.Font.Bold = True: c.Font.Color = RGB(255, 255, 255)
    c.Interior.Color = RGB(31, 78, 120)
End Sub

Private Sub Schreibe()
    Dim wsp As Worksheet, wdt As Worksheet, wau As Worksheet
    Dim g As Long, s As Long, p As Long, c As Long, t As Long, r As Long, folge As Variant
    Dim nStangen As Long, nTeile As Long, nr As Long, sr As Long, dr As Long
    Dim sp1() As Variant, sp9() As Variant, sp14() As Variant, dt() As Variant
    Dim pos As Double, vorherGerade As Boolean, vorherSchnitt As Double, verlust As Double
    Dim belegung As String, nGem As Long, ag As Boolean, bg As Boolean, schA As Double, schB As Double
    Dim gap As Double, gemeinsam As Boolean, eMm As Double, letzte As Long, crit As String

    Set wsp = ThisWorkbook.Worksheets("Schnittplan")
    Set wdt = ThisWorkbook.Worksheets("Stangenbelegung")
    Set wau = ThisWorkbook.Worksheets("Auswertung")

    For g = 1 To nG
        nStangen = nStangen + Anzahl(gErg(g))
        nTeile = nTeile + gTeile(g)(0)
    Next g
    If nStangen > S1 - S0 + 1 Then Err.Raise FEHLER_BASIS + 4, , "Mehr als 1000 Stangen: Blatt 'Schnittplan' erweitern"
    If nTeile > D1 - D0 + 1 Then Err.Raise FEHLER_BASIS + 5, , "Mehr als 10000 Teile: Blatt 'Stangenbelegung' erweitern"

    ' alte Ergebnisse löschen
    wsp.Range("A" & S0 & ":F" & S1).ClearContents
    wsp.Range("I" & S0 & ":I" & S1).ClearContents
    wsp.Range("N" & S0 & ":P" & S1).ClearContents
    letzte = wdt.UsedRange.Row + wdt.UsedRange.Rows.Count - 1
    If letzte >= D0 Then wdt.Range("A" & D0 & ":L" & letzte).ClearContents
    letzte = wau.UsedRange.Row + wau.UsedRange.Rows.Count - 1
    If letzte < 4 Then letzte = 4
    With wau.Range(wau.Rows(4), wau.Rows(letzte))
        .Clear
        .Font.Name = "Arial"
    End With

    If nStangen > 0 Then
        ReDim sp1(1 To nStangen, 1 To 6): ReDim sp9(1 To nStangen, 1 To 1): ReDim sp14(1 To nStangen, 1 To 3)
    End If
    If nTeile > 0 Then ReDim dt(1 To nTeile, 1 To 12)
    nr = 0: dr = 0
    For g = 1 To nG
        WaehleGruppe g
        For s = 1 To Anzahl(gErg(g))
            folge = gErg(g)(s)
            nr = nr + 1
            pos = cEnd: verlust = 0: belegung = "": nGem = 0
            For p = 1 To folge(0)
                c = folge(p): t = c \ 2
                ag = AnfangGerade(c): bg = EndeGerade(c)
                If c Mod 2 = 1 Then schA = tBs(t): schB = tAs(t) Else schA = tAs(t): schB = tBs(t)
                dr = dr + 1
                If p = 1 Then
                    dt(dr, 10) = "Stangenanfang"
                Else
                    gap = Trennung(vorherGerade, ag)
                    gemeinsam = vorherGerade And ag
                    If gemeinsam Then
                        dt(dr, 10) = "gemeinsamer Schnitt"
                        nGem = nGem + 1
                        If vorherSchnitt < schA Then eMm = vorherSchnitt Else eMm = schA
                        If Round(eMm, 1) <> 0 Then dt(dr, 11) = Round(eMm, 1)
                        dt(dr, 12) = 1
                    Else
                        dt(dr, 10) = "2 Schnitte"
                    End If
                    pos = pos + gap
                    verlust = verlust + gap
                End If
                dt(dr, 1) = nr: dt(dr, 2) = p: dt(dr, 3) = AlsWert(tPos(t)): dt(dr, 4) = AlsWert(tArt(t)): dt(dr, 5) = tZeile(t)
                dt(dr, 6) = tLen(t): dt(dr, 7) = Round(pos, 2): dt(dr, 8) = Round(pos + tLen(t), 2)
                If c Mod 2 = 1 Then dt(dr, 9) = "gedreht" Else dt(dr, 9) = "normal"
                pos = pos + tLen(t)
                vorherGerade = bg: vorherSchnitt = schB
                If p > 1 Then belegung = belegung & " | "
                If IsEmpty(tPos(t)) Then
                    belegung = belegung & tArt(t) & "×" & ZahlText(tLen(t))
                Else
                    belegung = belegung & tPos(t) & "×" & ZahlText(tLen(t))
                End If
            Next p
            verlust = verlust + cKerf
            sp1(nr, 1) = nr: sp1(nr, 2) = AlsWert(gProfil(g)): sp1(nr, 3) = AlsWert(gWst(g)): sp1(nr, 4) = gStange(g)
            sp1(nr, 5) = cEnd: sp1(nr, 6) = gGreif(g)
            sp9(nr, 1) = Round(verlust, 2)
            sp14(nr, 1) = folge(0): sp14(nr, 2) = nGem: sp14(nr, 3) = AlsWert(belegung)
        Next s
    Next g
    If nStangen > 0 Then
        wsp.Range("A" & S0).Resize(nStangen, 6).Value = sp1
        wsp.Range("I" & S0).Resize(nStangen, 1).Value = sp9
        wsp.Range("N" & S0).Resize(nStangen, 3).Value = sp14
    End If
    If nTeile > 0 Then
        With wdt.Range("A" & D0).Resize(nTeile, 12)
            .Value = dt
            .Font.Name = "Arial"
        End With
    End If

    ' Auswertung
    Dim kopf As Variant, sp As String
    kopf = Array("Profil-ID", "Werkstoff-ID", "Stangenlänge [mm]", "Teile [Stk]", "Stangen optimiert", _
                 "Stangen manuell", "Untergrenze Stangen", "Ersparnis Stangen", "Materialbedarf [m]", _
                 "Teilelänge [m]", "Verschnitt [m]", "Ausnutzung optimiert", "Ausnutzung manuell", _
                 "Gemeinsame Schnitte", "Prüfung Stangen", "Über Untergrenze [Stangen]", "Bewertung")
    For c = 1 To 17
        With wau.Cells(4, c)
            .Value = kopf(c - 1)
            Kopfzelle wau.Cells(4, c)
            .WrapText = True
            .VerticalAlignment = -4108    ' xlCenter
            .HorizontalAlignment = -4108
            .Borders.LineStyle = 1
            .Borders.Color = RGB(191, 191, 191)
        End With
        wau.Columns(c).ColumnWidth = 13
    Next c
    wau.Columns(1).ColumnWidth = 20
    wau.Columns(17).ColumnWidth = 34
    wau.Rows(4).RowHeight = 45
    r = 5
    For g = 1 To nG
        WaehleGruppe g
        crit = SpBereich("B") & ",$A" & r & "," & SpBereich("C") & ",$B" & r & "," & SpBereich("D") & ",$C" & r
        wau.Cells(r, 1).Value = AlsWert(gProfil(g))
        wau.Cells(r, 2).Value = AlsWert(gWst(g))
        wau.Cells(r, 3).Value = gStange(g)
        wau.Cells(r, 4).Formula = "=SUMIFS(" & SpBereich("G") & "," & crit & ")"
        wau.Cells(r, 5).Formula = "=COUNTIFS(" & crit & ")"
        wau.Cells(r, 6).Value = Manuell(gTeile(g))
        wau.Cells(r, 7).Value = Untergrenze(gTeile(g))
        wau.Cells(r, 8).Formula = "=F" & r & "-E" & r
        wau.Cells(r, 9).Formula = "=E" & r & "*C" & r & "/1000"
        wau.Cells(r, 10).Formula = "=SUMIFS(" & SpBereich("H") & "," & crit & ")/1000"
        wau.Cells(r, 11).Formula = "=I" & r & "-J" & r
        wau.Cells(r, 12).Formula = "=IF(I" & r & "=0,0,J" & r & "/I" & r & ")"
        wau.Cells(r, 13).Value = ManuellAusnutzung(gTeile(g), g)
        wau.Cells(r, 14).Formula = "=SUMIFS(" & SpBereich("O") & "," & crit & ")"
        wau.Cells(r, 15).Formula = "=IF(COUNTIFS(" & crit & "," & SpBereich("M") & ",""ÜBERBELEGT"")>0,""ÜBERBELEGT"",""OK"")"
        wau.Cells(r, 16).Formula = "=E" & r & "-G" & r
        wau.Cells(r, 17).Value = Bewertung(g)
        With wau.Range(wau.Cells(r, 1), wau.Cells(r, 17))
            .Borders.LineStyle = 1
            .Borders.Color = RGB(191, 191, 191)
        End With
        wau.Cells(r, 3).NumberFormat = "#,##0"
        wau.Range(wau.Cells(r, 9), wau.Cells(r, 11)).NumberFormat = "#,##0.00"
        wau.Range(wau.Cells(r, 12), wau.Cells(r, 13)).NumberFormat = "0.0%"
        r = r + 1
    Next g
    If nG > 0 Then
        wau.Cells(r, 1).Value = "Summe"
        wau.Cells(r, 1).Font.Bold = True
        For Each kopf In Array(4, 5, 6, 7, 8, 9, 10, 11, 14, 16)
            sp = Split(wau.Cells(1, kopf).Address(True, False), "$")(0)
            With wau.Cells(r, kopf)
                .Formula = "=SUM(" & sp & "5:" & sp & (r - 1) & ")"
                .Font.Bold = True
                If kopf >= 9 And kopf <= 11 Then .NumberFormat = "#,##0.00" Else .NumberFormat = "#,##0"
            End With
        Next kopf
        wau.Cells(r, 12).Formula = "=IF(I" & r & "=0,0,J" & r & "/I" & r & ")"
        wau.Cells(r, 12).NumberFormat = "0.0%"
        r = r + 1
    End If

    r = r + 1
    wau.Cells(r, 1).Value = "Nicht eingeplante Teile"
    wau.Cells(r, 1).Font.Bold = True
    wau.Cells(r, 1).Font.Size = 12
    r = r + 1
    kopf = Array("Zeile Auftrag", "Pos.", "Artikelnummer", "Anzahl", "Grund")
    For c = 1 To 5
        wau.Cells(r, c).Value = kopf(c - 1)
        Kopfzelle wau.Cells(r, c)
    Next c
    r = r + 1
    If nF = 0 Then wau.Cells(r, 1).Value = "keine"
    For c = 1 To nF
        wau.Cells(r, 1).Value = fZeile(c)
        wau.Cells(r, 2).Value = AlsWert(fPos(c))
        wau.Cells(r, 3).Value = AlsWert(fArt(c))
        wau.Cells(r, 4).Value = fAnz(c)
        wau.Cells(r, 5).Value = fGrund(c)
        r = r + 1
    Next c
End Sub

' Text als Text eintragen: Excel würde z. B. "1.4301" sonst in eine Zahl umwandeln.
Private Function AlsWert(ByVal v As Variant) As Variant
    If VarType(v) = vbString Then AlsWert = "'" & v Else AlsWert = v
End Function

Private Function SpBereich(ByVal spalte As String) As String
    SpBereich = "Schnittplan!$" & spalte & "$" & S0 & ":$" & spalte & "$" & S1
End Function

' Für automatische Tests: Ergebnis oder Fehlertext als Rückgabe, ohne Meldungsfenster.
Public Function OptimiereTest() As String
    On Error GoTo Fehler
    OptimiereTest = OptimiereMappe()
    Exit Function
Fehler:
    OptimiereTest = "FEHLER " & Err.Number & ": " & Err.Description & " (Zeile " & Erl & ")"
End Function
