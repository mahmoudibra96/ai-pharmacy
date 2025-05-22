@echo off
echo Starting Pharmacy System with Docker...

REM Check if Docker is running
docker info > nul 2>&1
if errorlevel 1 (
    echo Docker is not running! Please start Docker Desktop first.
    pause
    exit
)

REM Pull and start containers
docker-compose up --build -d

echo.
echo Pharmacy system is running!
echo Access the website at: http://localhost:8000
echo.
echo Press any key to stop the system...
pause > nul

REM Stop containers
docker-compose down
