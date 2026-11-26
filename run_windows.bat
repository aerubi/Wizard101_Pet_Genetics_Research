@echo off
setlocal
cd /d "%~dp0"
py -3 app.py
if errorlevel 1 (
  echo.
  echo The application could not start. Confirm Python 3.10+ is installed with Tkinter.
  pause
)
endlocal
