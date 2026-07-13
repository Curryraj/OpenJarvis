@echo off
REM Auto-refresh the second-brain FAISS store (curated markdown + captured facts).
REM Called by Windows Task Scheduler. Full uv path because Task Scheduler lacks the user PATH.
setlocal
set "REPO=C:\Users\jaiyd\OneDrive\Desktop\OpenJarvis"
set "UV=C:\Users\jaiyd\AppData\Local\Microsoft\WinGet\Packages\astral-sh.uv_Microsoft.Winget.Source_8wekyb3d8bbwe\uv.exe"
set "LOGDIR=C:\Users\jaiyd\.openjarvis\logs"
if not exist "%LOGDIR%" mkdir "%LOGDIR%"
cd /d "%REPO%"
echo ==== refresh %DATE% %TIME% ==== >> "%LOGDIR%\refresh.log"
"%UV%" run python scripts\refresh_memory.py >> "%LOGDIR%\refresh.log" 2>&1
endlocal
