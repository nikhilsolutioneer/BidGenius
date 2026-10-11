Option Explicit
Dim app, pres, fso, root, output, previews, existing, sl, sh, i, log, notes, txt
Set fso = CreateObject("Scripting.FileSystemObject")
root = fso.GetParentFolderName(WScript.ScriptFullName)
output = fso.BuildPath(root, "deliverables")
previews = fso.BuildPath(output, "slide_previews")
If Not fso.FolderExists(previews) Then fso.CreateFolder(previews)
Set app = CreateObject("PowerPoint.Application")
existing = app.Presentations.Count
Set pres = app.Presentations.Open(fso.BuildPath(output, "BidGenius_AI_Hackathon.pptx"), True, False, False)
Set log = fso.CreateTextFile(fso.BuildPath(output, "native_text_check.txt"), True, True)
For Each sl In pres.Slides
  i = sl.SlideIndex
  sl.Export fso.BuildPath(previews, "slide_" & Right("0" & CStr(i), 2) & ".png"), "PNG", 1600, 900
  For Each sh In sl.Shapes
    If sh.HasTextFrame Then
      If sh.TextFrame.HasText Then
        If sh.TextFrame2.TextRange.BoundHeight > sh.Height + 1.5 Then
          log.WriteLine "Slide " & i & " overflow height " & sh.TextFrame2.TextRange.BoundHeight & " in " & sh.Height & " : " & sh.TextFrame.TextRange.Text
        End If
      End If
    End If
  Next
Next
log.Close
pres.SaveAs fso.BuildPath(output, "BidGenius_AI_Hackathon.pdf"), 32
WScript.Echo "Rendered " & pres.Slides.Count & " slides and PDF."
pres.Close
If existing = 0 Then app.Quit
Set pres = Nothing
Set app = Nothing
