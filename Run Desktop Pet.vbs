Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = CreateObject("Scripting.FileSystemObject").GetAbsolutePathName(".")
WshShell.Run "pythonw main.py", 0, False
