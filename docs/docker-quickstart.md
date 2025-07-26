# Démarrage rapide avec Docker

## Installation en 5 minutes

### 1. Cloner et configurer

```bash
git clone https://github.com/votre-username/gitpulse.git
cd gitpulse
cp env.example .env
```

### 2. Démarrer

```bash
docker-compose up -d --build
```

### 3. Initialiser

```bash
docker-compose exec web python manage.py migrate
docker-compose exec web python manage.py createsuperuser
```

### 4. Accéder

- **Application** : http://localhost:8000
- **Admin** : http://localhost:8000/admin

## Services inclus

- **PostgreSQL** : Base de données Django
- **MongoDB** : Base de données analytics
- **Redis** : Cache et file d'attente
- **Ollama** : IA pour classification des commits
- **Django** : Application web

## Commandes essentielles

```bash
# Démarrer
docker-compose up -d

# Arrêter
docker-compose down

# Logs
docker-compose logs -f

# Shell Django
docker-compose exec web python manage.py shell

# Shell PostgreSQL
docker-compose exec postgres psql -U gitpulse -d gitpulse
```

## Configuration GitHub

1. Créez une app OAuth sur GitHub
2. Ajoutez les credentials dans `.env`
3. Redémarrez : `docker-compose restart web`

## Problèmes ?

- **Ports occupés** : `lsof -i :8000`
- **Logs** : `docker-compose logs`
- **Nettoyage** : `docker-compose down -v`

Voir la [documentation complète](docker-installation.md) pour plus de détails. 