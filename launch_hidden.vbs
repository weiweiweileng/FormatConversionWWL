' Format Converter - hidden launcher (ASCII only: wscript parses VBS as ANSI/GBK,
' so non-ASCII characters here would break parsing on Chinese Windows).
' Runs the Flask service via pythonw (no console window). Optional extra args
' are appended to the command line, e.g. "--port 8806 --no-browser".
Set fso = CreateObject("Scripting.FileSystemObject")
Set sh = CreateObject("WScript.Shell")
sh.CurrentDirectory = fso.GetParentFolderName(WScript.ScriptFullName)

Dim exe
If sh.Run("cmd /c where pythonw", 0, True) = 0 Then
  exe = "pythonw"
Else
  exe = "python"
End If

Dim extra
If WScript.Arguments.Count > 0 Then
  extra = " " & WScript.Arguments(0)
Else
  extra = ""
End If
sh.Run exe & " -X utf8 app.py" & extra, 0, False
