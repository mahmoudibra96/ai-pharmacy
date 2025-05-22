@echo off
setlocal EnableDelayedExpansion

echo Checking for available printers...
wmic printer get name

echo.
echo Please enter the printer name or port (e.g., LPT1, COM3):
set /p PRINTER_PATH=

:: Save to .env file
echo PRINTER_PATH=%PRINTER_PATH% > .env.printer
type .env >> .env.printer
move /y .env.printer .env

echo.
echo Printer configuration saved. Starting the application...
start "" start.bat
