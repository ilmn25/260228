Option Explicit

Dim fso, shell, scriptDir, pythonExe, mainPy, cmd, q
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")

scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
q = Chr(34)
pythonExe = q & scriptDir & "\.venv\Scripts\pythonw.exe" & q
mainPy = q & scriptDir & "\main.py" & q

shell.CurrentDirectory = scriptDir
shell.Environment("PROCESS")("PYTHONIOENCODING") = "utf-8"
cmd = pythonExe & " " & mainPy
shell.Run cmd, 0, False
