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

# Wait for Ollama to be ready and model to be available
echo "Waiting for Ollama..."
while ! curl -f http://ollama:11434/api/tags > /dev/null 2>&1; do
  sleep 2
done
echo "Ollama is ready!"

# Check if gemma3:1b model is available
echo "Checking for gemma3:1b model..."
if ! curl -s http://ollama:11434/api/tags | grep -q "gemma3:1b"; then
  echo "Installing gemma3:1b model..."
  curl -X POST http://ollama:11434/api/pull -d '{"name": "gemma3:1b"}'
else
  echo "gemma3:1b model is already available"
fi

# Run migrations
echo "Running database migrations..."
python manage.py migrate

# Collect static files
echo "Collecting static files..."
python manage.py collectstatic --noinput

# Start the Django development server
echo "Starting Django server..."
python manage.py runserver 0.0.0.0:8000 