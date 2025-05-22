#!/bin/bash
set -e

# Wait for database to be ready
echo "Waiting for database..."
sleep 2

# Run migrations
echo "Running database migrations..."
python manage.py migrate

# Collect static files
echo "Collecting static files..."
python manage.py collectstatic --noinput

# Create superuser if needed
if [ "$DJANGO_SUPERUSER_USERNAME" ]; then
    echo "Creating superuser..."
    python manage.py createsuperuser --noinput || true
fi

# Check printer access
echo "Checking printer access..."
for printer in /dev/usb/lp*; do
    if [ -e "$printer" ]; then
        echo "Found printer at: $printer"
        chmod 666 "$printer" || true
    fi
done

# Start server
echo "Starting server..."
exec "$@"
