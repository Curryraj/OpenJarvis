@echo off
REM Daily knowledge digest — second-brain agent produces it from its memory.
REM Called by Windows Task Scheduler. Full uv path (Task Scheduler lacks user PATH).
setlocal
set "REPO=C:\Users\jaiyd\OneDrive\Desktop\OpenJarvis"
set "UV=C:\Users\jaiyd\AppData\Local\Microsoft\WinGet\Packages\astral-sh.uv_Microsoft.Winget.Source_8wekyb3d8bbwe\uv.exe"
set "LOGDIR=C:\Users\jaiyd\.openjarvis\logs"
if not exist "%LOGDIR%" mkdir "%LOGDIR%"
cd /d "%REPO%"
set "PROMPT=Daily knowledge digest. Using ONLY the retrieved context from my knowledge base, write a briefing UNDER 150 words: (1) 2-3 key themes, (2) open threads or next-actions you can infer, (3) one non-obvious connection between two notes. Cite note titles. No preamble."
echo ==== digest %DATE% %TIME% ==== >> "%LOGDIR%\digest.log"
"%UV%" run jarvis agents ask second-brain "%PROMPT%" >> "%LOGDIR%\digest.log" 2>&1
endlocal
