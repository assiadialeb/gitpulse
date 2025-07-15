# GitPulse Configuration

GitPulse uses `python-decouple` to manage configuration securely and flexibly.

## Configuration Variables

### Indexing Service

The `INDEXING_SERVICE` variable allows you to choose the indexing service to use:

- `git_local` (default): Uses local Git commands to retrieve commits
- `github_api`: Uses GitHub API to retrieve commits

### MongoDB Configuration

- `MONGODB_HOST`: MongoDB host (default: localhost)
- `MONGODB_PORT`: MongoDB port (default: 27017)
- `MONGODB_NAME`: Database name (default: gitpulse)

### Redis Configuration

- `REDIS_HOST`: Redis host (default: 127.0.0.1)
- `REDIS_PORT`: Redis port (default: 6379)

### GitHub API Configuration

These variables are only used if `INDEXING_SERVICE=github_api`:

- `GITHUB_API_RATE_LIMIT_WARNING`: Rate limit warning threshold (default: 10)
- `GITHUB_API_TIMEOUT`: API request timeout (default: 30)

## Usage

### 1. Create a .env file

Copy the `env.example` file to `.env`:

```bash
cp env.example .env
```

### 2. Modify the configuration

Edit the `.env` file according to your needs:

```env
# Indexing service
INDEXING_SERVICE=github_api

# MongoDB configuration
MONGODB_HOST=localhost
MONGODB_PORT=27017
MONGODB_NAME=gitpulse

# Redis configuration
REDIS_HOST=127.0.0.1
REDIS_PORT=6379
```

### 3. Environment variables

You can also define environment variables directly:

```bash
export INDEXING_SERVICE=github_api
export MONGODB_HOST=localhost
```

### 4. Test the configuration

Use the test script to verify the configuration:

```bash
python test_indexing_service.py
```

## Advantages of python-decouple

- **Security**: Sensitive variables are not in the code
- **Flexibility**: Support for environment variables and .env files
- **Simplicity**: Simple and intuitive API
- **Defaults**: Default values for all variables

## Priority Order

1. Environment variables
2. `.env` file
3. Default values in the code 