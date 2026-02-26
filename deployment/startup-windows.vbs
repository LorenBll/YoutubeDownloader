' YoutubeDownloader - Windows Startup Script
' Place this file in: shell:startup (Win+R, type "shell:startup")
' Or create a scheduled task to run at system startup

Set objShell = CreateObject("WScript.Shell")
Set objFSO = CreateObject("Scripting.FileSystemObject")

' Get the project root directory (parent of deployment folder)
scriptDir = objFSO.GetParentFolderName(WScript.ScriptFullName)
projectRoot = objFSO.GetParentFolderName(scriptDir)

' Change to the project root directory
objShell.CurrentDirectory = projectRoot

' Run the batch file silently (0 = hidden window, False = don't wait)
objShell.Run "cmd /c scripts\run.bat", 0, False

Set objShell = Nothing
Set objFSO = Nothing
