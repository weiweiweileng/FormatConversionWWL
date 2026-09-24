@echo off
rem Hidden launch: no console window, opens the tool page in browser automatically.
rem Double-clicking again will not start a second service, it just re-opens the page.
rem The service exits automatically after all tool pages are closed (~30s).
cd /d %~dp0
start "" wscript.exe "%~dp0launch_hidden.vbs"
exit
