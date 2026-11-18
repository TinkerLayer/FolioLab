@echo off
title Folio Lab - data analysis and report writing
cd /d "%~dp0"
if not exist "tools\node\node.exe" (
  echo First run: installing portable Node.js and MiKTeX into the tools folder...
  powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup.ps1"
  if errorlevel 1 (
    echo Setup failed. See the messages above.
    pause
    exit /b 1
  )
)
echo Starting Folio Lab... keep this window open while you work. Close it to stop Folio Lab and its analysis modules.
"tools\node\node.exe" server\index.js --open
pause