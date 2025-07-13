# GitPulse with Docker and Ollama

This setup includes GitPulse with automatic commit classification using Ollama LLM.

## Services

- **web**: Django application (port 8000)
- **mongodb**: MongoDB database (port 27017)
- **redis**: Redis cache (port 6379)
- **ollama**: Ollama LLM service with gemma3:1b model (port 11434)

## Quick Start

1. **Start all services:**
   ```bash
   docker-compose up -d
   ```

2. **Check service status:**
   ```bash
   docker-compose ps
   ```

3. **View logs:**
   ```bash
   docker-compose logs -f web
   ```

4. **Access the application:**
   - Web interface: http://localhost:8000
   - Ollama API: http://localhost:11434

## Ollama Integration

### Automatic Model Installation
The Ollama service automatically:
- Starts the Ollama server
- Downloads the `gemma3:1b` model (~2GB)
- Makes the model available for commit classification

### Commit Classification
The application uses a hybrid approach:
1. **Simple classifier** (fast, ~50% accuracy)
2. **Ollama LLM** (slower, higher accuracy for difficult cases)

### Model Management
- **Check available models:**
  ```bash
  curl http://localhost:11434/api/tags
  ```

- **Pull additional models:**
  ```bash
  curl -X POST http://localhost:11434/api/pull -d '{"name": "model_name"}'
  ```

- **Remove models:**
  ```bash
  curl -X DELETE http://localhost:11434/api/delete -d '{"name": "model_name"}'
  ```

## Configuration

### Environment Variables
- `OLLAMA_HOST`: Ollama service hostname (default: ollama)
- `OLLAMA_PORT`: Ollama service port (default: 11434)

### Volumes
- `ollama_data`: Persists Ollama models and configuration
- `mongodb_data`: Persists MongoDB data
- `redis_data`: Persists Redis data

## Troubleshooting

### Ollama Service Issues
1. **Check if Ollama is running:**
   ```bash
   docker-compose logs ollama
   ```

2. **Restart Ollama service:**
   ```bash
   docker-compose restart ollama
   ```

3. **Check model availability:**
   ```bash
   curl http://localhost:11434/api/tags
   ```

### Model Download Issues
If the model download fails:
1. **Manual download:**
   ```bash
   docker-compose exec ollama ollama pull gemma3:1b
   ```

2. **Check disk space:**
   ```bash
   docker system df
   ```

### Performance Notes
- **First startup**: Model download takes 5-10 minutes
- **Memory usage**: gemma3:1b requires ~4GB RAM
- **CPU usage**: LLM inference is CPU-intensive

## Development

### Local Development without Docker
If you want to run the application locally but use Docker for Ollama:

1. **Start only Ollama:**
   ```bash
   docker-compose up -d ollama
   ```

2. **Run Django locally:**
   ```bash
   python manage.py runserver
   ```

3. **Update settings:**
   ```python
   # In your local settings
   OLLAMA_HOST = 'localhost'
   OLLAMA_PORT = '11434'
   ```

## Production Considerations

1. **Resource requirements:**
   - Minimum 8GB RAM
   - 10GB free disk space
   - 4+ CPU cores recommended

2. **Security:**
   - Ollama API is exposed on port 11434
   - Consider firewall rules for production

3. **Monitoring:**
   - Monitor Ollama memory usage
   - Check model availability regularly
   - Log classification performance

## Commands Reference

```bash
# Start all services
docker-compose up -d

# Stop all services
docker-compose down

# View logs
docker-compose logs -f

# Restart specific service
docker-compose restart ollama

# Execute commands in container
docker-compose exec web python manage.py shell
docker-compose exec ollama ollama list

# Clean up
docker-compose down -v  # Removes volumes
docker system prune     # Removes unused images
``` 