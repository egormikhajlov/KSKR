@echo off
chcp 65001 >nul
cd /d "%~dp0"
where py >nul 2>nul
if not errorlevel 1 (
    py -3 flowprep.py
    if errorlevel 1 pause
    exit /b
)
where python >nul 2>nul
if not errorlevel 1 (
    python flowprep.py
    if errorlevel 1 pause
    exit /b
)
echo Установите Python 3.10 или новее с компонентом Tcl/Tk.
pause
