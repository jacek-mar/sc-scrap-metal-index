@echo off
rem CC0-1.0. Rebuild the SC Scrap Metal Index from your own Star Conflict install.
rem Usage: build-index.bat [--gamedir "<folder with data and cloud>"] [--out smi-build]
cd /d "%~dp0"
where py >nul 2>nul && (py -3 -m sc_smi_gen %*) || (python -m sc_smi_gen %*)
if errorlevel 1 (echo. & echo The build did not finish. See the message above. & pause & exit /b 1)
pause
