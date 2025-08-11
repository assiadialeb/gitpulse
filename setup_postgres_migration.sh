#!/bin/bash

# Configuration pour migration vers PostgreSQL existant
export POSTGRES_DB=gitpulse
export POSTGRES_USER=gitpulse_user
export POSTGRES_PASSWORD=gitpulse_password
export POSTGRES_HOST=localhost
export POSTGRES_PORT=5432

# MongoDB Configuration
export MONGODB_HOST=localhost
export MONGODB_PORT=27017
export MONGODB_NAME=gitpulse

# Ollama Configuration
export OLLAMA_HOST=localhost
export OLLAMA_PORT=11434

# Django Configuration
export DEBUG=True
export SECRET_KEY=your-secret-key-here
export ALLOWED_HOSTS=localhost,127.0.0.1

echo "✅ Variables d'environnement configurées pour PostgreSQL existant"
echo "📊 Base de données: $POSTGRES_DB"
echo "👤 Utilisateur: $POSTGRES_USER"
echo "🔗 Host: $POSTGRES_HOST:$POSTGRES_PORT" 