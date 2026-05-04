Set WshShell = CreateObject("WScript.Shell")
Set objFSO = CreateObject("Scripting.FileSystemObject")

' Get the project path
strProjectPath = "C:\Users\Administrator\chain_gambler"
strLauncher = strProjectPath & "\Money_Printer_Launcher.bat"
strIconPath = strProjectPath & "\ui_lab_app\public\app_icon.ico"

' Desktop path
strDesktopPath = WshShell.SpecialFolders("Desktop")

' Create the shortcut
Set objShortcut = WshShell.CreateShortcut(strDesktopPath & "\Chain Gambler - Money Printer.lnk")
objShortcut.TargetPath = strLauncher
objShortcut.WorkingDirectory = strProjectPath
objShortcut.IconLocation = strIconPath & ",0"
objShortcut.Description = "Chain Gambler Money Printer - AI Trading System with Ollama"
objShortcut.Arguments = ""
objShortcut.WindowStyle = 1

' Save the shortcut
objShortcut.Save

' Also create in Start Menu
strStartMenuPath = WshShell.SpecialFolders("StartMenu") & "\Programs"
Set objShortcut2 = WshShell.CreateShortcut(strStartMenuPath & "\Chain Gambler - Money Printer.lnk")
objShortcut2.TargetPath = strLauncher
objShortcut2.WorkingDirectory = strProjectPath
objShortcut2.IconLocation = strIconPath & ",0"
objShortcut2.Description = "Chain Gambler Money Printer - AI Trading System"
objShortcut2.Save

WScript.Echo "Shortcuts created successfully!"
WScript.Echo "Desktop: " & strDesktopPath & "\Chain Gambler - Money Printer.lnk"
WScript.Echo "Start Menu: " & strStartMenuPath & "\Chain Gambler - Money Printer.lnk"
