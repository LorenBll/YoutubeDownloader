' Start YoutubeDownloader service.
' Place in: shell:startup (Win+R, type "shell:startup")
' Or create a scheduled task to run at system startup.

Set objShell = CreateObject("WScript.Shell")
Set objFSO = CreateObject("Scripting.FileSystemObject")

' Get project root directory
scriptDir = objFSO.GetParentFolderName(WScript.ScriptFullName)
projectRoot = objFSO.GetParentFolderName(scriptDir)

' Change to project root
objShell.CurrentDirectory = projectRoot

' Run the batch file silently
objShell.Run "cmd /c scripts\run.bat", 0, False

Set objShell = Nothing
Set objFSO = Nothing
