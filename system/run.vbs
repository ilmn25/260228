Option Explicit

Dim fso, shell, scriptDir, workspaceDir, pythonExe, mainPy, cmd, q
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")

scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
workspaceDir = fso.GetParentFolderName(scriptDir)
q = Chr(34)
pythonExe = q & workspaceDir & "\.venv\Scripts\pythonw.exe" & q
mainPy = q & scriptDir & "\main.py" & q

shell.CurrentDirectory = workspaceDir
shell.Environment("PROCESS")("PYTHONIOENCODING") = "utf-8"
cmd = pythonExe & " " & mainPy
shell.Run cmd, 0, False
