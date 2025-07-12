#!/bin/bash

# Wait for MongoDB to be ready
echo "Waiting for MongoDB..."
while ! nc -z mongodb 27017; do
  sleep 1
done
echo "MongoDB is ready!"

# Wait for Redis to be ready
echo "Waiting for Redis..."
while ! nc -z redis 6379; do
  sleep 1
done
echo "Redis is ready!"

# Run migrations
echo "Running database migrations..."
python manage.py migrate

# Collect static files
echo "Collecting static files..."
python manage.py collectstatic --noinput

# Start the Django development server
echo "Starting Django server..."
python manage.py runserver 0.0.0.0:8000 