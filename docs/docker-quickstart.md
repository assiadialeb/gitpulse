# Quick Start with Docker

## Installation in 5 minutes

### 1. Clone and configure

```bash
git clone https://github.com/your-username/gitpulse.git
cd gitpulse
cp env.example .env
```

### 2. Start

```bash
docker-compose up -d --build
```

### 3. Initialize

```bash
docker-compose exec web python manage.py migrate
docker-compose exec web python manage.py createsuperuser
```

### 4. Access

- **Application**: http://localhost:8000
- **Admin**: http://localhost:8000/admin

## Included Services

- **PostgreSQL**: Django database
- **MongoDB**: Analytics database
- **Redis**: Cache and queue
- **Ollama**: AI for commit classification
- **Django**: Web application

## Essential Commands

```bash
# Start
docker-compose up -d

# Stop
docker-compose down

# Logs
docker-compose logs -f

# Django shell
docker-compose exec web python manage.py shell

# PostgreSQL shell
docker-compose exec postgres psql -U gitpulse -d gitpulse
```

## GitHub Configuration

1. Create an OAuth app on GitHub
2. Add credentials to `.env`
3. Restart: `docker-compose restart web`

## Problems?

- **Ports in use**: `lsof -i :8000`
- **Logs**: `docker-compose logs`
- **Cleanup**: `docker-compose down -v`

See the [complete documentation](docker-installation.md) for more details. 