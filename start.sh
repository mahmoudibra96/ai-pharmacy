#!/bin/bash

echo "🏥 Starting Pharmacy System with Docker..."

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker is not running! Please start Docker first."
    exit 1
fi

# Pull and start containers
docker-compose up --build -d

echo
echo "✅ Pharmacy system is running!"
echo "🌐 Access the website at: http://localhost:8000"
echo
echo "Press Ctrl+C to stop the system..."

# Keep the script running and show logs
docker-compose logs -f
