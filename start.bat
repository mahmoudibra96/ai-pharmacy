@echo off
echo Starting Pharmacy System...

REM Check if Python is installed
python --version > nul 2>&1
if errorlevel 1 (
    echo Python is not installed! Please install Python first.
    pause
    exit /b 1
)

REM Check if printer is configured
if not exist .env (
    echo No printer configuration found.
    echo Running printer setup...
    call setup_printer.bat
    exit /b
)

REM Start Django development server
echo Starting Django server...
start "Django Server" cmd /c "python manage.py runserver"

REM Wait a moment for the server to start
timeout /t 2 > nul

REM Open browser
start http://localhost:8000

echo.
echo Pharmacy system is running!
echo Access the website at: http://localhost:8000
echo.
echo Press Ctrl+C to stop the server...
cmd /k

REM Stop containers
docker-compose down
