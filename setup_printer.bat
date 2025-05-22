@echo off
setlocal EnableDelayedExpansion

echo Installing required Python packages...
pip install -r requirements.txt
if errorlevel 1 (
    echo Failed to install required packages
    pause
    exit /b 1
)

echo.
echo Checking for available printers...
powershell -Command "Get-Printer | Format-Table Name, PrinterStatus, PortName"

echo.
echo Testing printer connection...
python test_windows_print.py
if errorlevel 1 (
    echo Printer test failed. Please check your printer connection.
) else (
    echo Printer test successful!
)

echo.
echo Please enter the printer name or port (e.g., LPT1, COM3):
set /p PRINTER_PATH=

:: Save to .env file
echo PRINTER_PATH=%PRINTER_PATH% > .env.printer
type .env >> .env.printer 2>nul
move /y .env.printer .env

:: Test the selected printer
echo.
echo Testing selected printer...
set PRINTER_TEST=1
python test_windows_print.py --printer "%PRINTER_PATH%"
if errorlevel 1 (
    echo WARNING: Failed to print to selected printer. Please verify your printer selection.
    echo You can still continue, but printing may not work correctly.
) else (
    echo Selected printer test successful!
)

echo.
echo Setup complete! The application will now start...
echo If you need to change the printer later, you can run this setup again.
timeout /t 5
start "" start.bat
