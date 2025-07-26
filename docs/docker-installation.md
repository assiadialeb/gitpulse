# Installation GitPulse avec Docker

Ce guide vous explique comment installer et configurer GitPulse en utilisant Docker avec PostgreSQL, MongoDB, Redis et Ollama.

## Prérequis

- Docker et Docker Compose installés
- Git installé
- Au moins 4GB de RAM disponible
- 10GB d'espace disque libre

## Installation

### 1. Cloner le repository

```bash
git clone https://github.com/votre-username/gitpulse.git
cd gitpulse
```

### 2. Configuration de l'environnement

Créez un fichier `.env` à la racine du projet :

```bash
cp env.example .env
```

Modifiez le fichier `.env` selon vos besoins :

```env
# Django Settings
DEBUG=True
SECRET_KEY=votre-secret-key-ici
ALLOWED_HOSTS=localhost,127.0.0.1

# Database Settings
POSTGRES_DB=gitpulse
POSTGRES_USER=gitpulse
POSTGRES_PASSWORD=gitpulse_password
POSTGRES_HOST=postgres
POSTGRES_PORT=5432

# MongoDB Settings
MONGODB_HOST=mongodb
MONGODB_PORT=27017
MONGODB_NAME=gitpulse

# Redis Settings
REDIS_HOST=redis
REDIS_PORT=6379

# Ollama Settings
OLLAMA_HOST=ollama
OLLAMA_PORT=11434

# GitHub OAuth (optionnel pour le développement)
GITHUB_CLIENT_ID=votre-github-client-id
GITHUB_CLIENT_SECRET=votre-github-client-secret
```

### 3. Démarrer les services

```bash
# Construire et démarrer tous les services
docker-compose up -d --build
```

Cette commande va :
- Construire l'image Docker de l'application
- Démarrer PostgreSQL (base de données Django)
- Démarrer MongoDB (base de données analytics)
- Démarrer Redis (cache)
- Démarrer Ollama (IA pour la classification des commits)
- Démarrer l'application Django

### 4. Vérifier que tous les services sont démarrés

```bash
docker-compose ps
```

Vous devriez voir tous les services avec le statut "Up".

### 5. Initialiser la base de données

```bash
# Créer les migrations Django
docker-compose exec web python manage.py makemigrations

# Appliquer les migrations
docker-compose exec web python manage.py migrate

# Créer un superutilisateur
docker-compose exec web python manage.py createsuperuser
```

### 6. Collecter les fichiers statiques

```bash
docker-compose exec web python manage.py collectstatic --noinput
```

## Accès à l'application

- **Application web** : http://localhost:8000
- **Admin Django** : http://localhost:8000/admin
- **PostgreSQL** : localhost:5432
- **MongoDB** : localhost:27017
- **Redis** : localhost:6379
- **Ollama** : http://localhost:11434

## Configuration GitHub OAuth (optionnel)

Pour utiliser l'authentification GitHub :

1. Créez une application OAuth sur GitHub :
   - Allez sur https://github.com/settings/developers
   - Cliquez sur "New OAuth App"
   - Remplissez les informations :
     - Application name: GitPulse
     - Homepage URL: http://localhost:8000
     - Authorization callback URL: http://localhost:8000/accounts/github/login/callback/

2. Ajoutez les credentials dans votre `.env` :
   ```env
   GITHUB_CLIENT_ID=votre-client-id
   GITHUB_CLIENT_SECRET=votre-client-secret
   ```

3. Redémarrez les services :
   ```bash
   docker-compose restart web
   ```

## Commandes utiles

### Gestion des services

```bash
# Démarrer les services
docker-compose up -d

# Arrêter les services
docker-compose down

# Voir les logs
docker-compose logs -f

# Voir les logs d'un service spécifique
docker-compose logs -f web

# Redémarrer un service
docker-compose restart web
```

### Base de données

```bash
# Accéder au shell PostgreSQL
docker-compose exec postgres psql -U gitpulse -d gitpulse

# Accéder au shell MongoDB
docker-compose exec mongodb mongosh

# Accéder au shell Redis
docker-compose exec redis redis-cli
```

### Application Django

```bash
# Accéder au shell Django
docker-compose exec web python manage.py shell

# Créer un superutilisateur
docker-compose exec web python manage.py createsuperuser

# Voir les tâches en cours
docker-compose exec web python manage.py shell
# >>> from django_q.models import Schedule
# >>> Schedule.objects.all()
```

### Ollama

```bash
# Voir les modèles disponibles
docker-compose exec ollama ollama list

# Tester Ollama
curl http://localhost:11434/api/generate -d '{
  "model": "gemma3:1b",
  "prompt": "Hello, how are you?"
}'
```

## Structure des données

### PostgreSQL (Django)
- **Users** : Utilisateurs et authentification
- **Projects** : Projets et leurs repositories
- **Repositories** : Repositories GitHub
- **Developers** : Informations sur les développeurs

### MongoDB (Analytics)
- **Commits** : Données des commits avec classification
- **PullRequests** : Données des pull requests
- **Releases** : Données des releases
- **Deployments** : Données des déploiements
- **Developers** : Groupement des identités développeur

## Monitoring et logs

### Logs de l'application
```bash
docker-compose logs -f web
```

### Logs de la base de données
```bash
docker-compose logs -f postgres
docker-compose logs -f mongodb
```

### Logs d'Ollama
```bash
docker-compose logs -f ollama
```

## Sauvegarde et restauration

### Sauvegarde PostgreSQL
```bash
docker-compose exec postgres pg_dump -U gitpulse gitpulse > backup_postgres.sql
```

### Sauvegarde MongoDB
```bash
docker-compose exec mongodb mongodump --db gitpulse --out /data/backup
docker cp gitpulse_mongodb_1:/data/backup ./backup_mongodb
```

### Restauration PostgreSQL
```bash
docker-compose exec -T postgres psql -U gitpulse gitpulse < backup_postgres.sql
```

### Restauration MongoDB
```bash
docker cp ./backup_mongodb gitpulse_mongodb_1:/data/backup
docker-compose exec mongodb mongorestore --db gitpulse /data/backup/gitpulse
```

## Dépannage

### Problèmes courants

1. **Ports déjà utilisés**
   ```bash
   # Vérifier les ports utilisés
   lsof -i :8000
   lsof -i :5432
   lsof -i :27017
   ```

2. **Services qui ne démarrent pas**
   ```bash
   # Voir les logs détaillés
   docker-compose logs
   
   # Redémarrer tous les services
   docker-compose down
   docker-compose up -d
   ```

3. **Problèmes de permissions**
   ```bash
   # Donner les bonnes permissions aux volumes
   sudo chown -R $USER:$USER ./data
   sudo chown -R $USER:$USER ./logs
   ```

4. **Ollama qui ne répond pas**
   ```bash
   # Vérifier que le modèle est téléchargé
   docker-compose exec ollama ollama list
   
   # Télécharger le modèle manuellement
   docker-compose exec ollama ollama pull gemma3:1b
   ```

### Nettoyage complet

```bash
# Arrêter et supprimer tous les conteneurs et volumes
docker-compose down -v

# Supprimer les images
docker-compose down --rmi all

# Nettoyer les volumes Docker non utilisés
docker volume prune
```

## Performance

### Optimisations recommandées

1. **Mémoire** : Allouez au moins 4GB de RAM
2. **CPU** : Au moins 2 cœurs pour de bonnes performances
3. **Disque** : SSD recommandé pour les bases de données

### Monitoring des ressources

```bash
# Voir l'utilisation des ressources
docker stats

# Voir l'espace disque utilisé
docker system df
```

## Support

Pour obtenir de l'aide :
- Consultez les logs : `docker-compose logs`
- Vérifiez la documentation : `/docs`
- Ouvrez une issue sur GitHub

## Mise à jour

Pour mettre à jour GitPulse :

```bash
# Arrêter les services
docker-compose down

# Récupérer les dernières modifications
git pull

# Reconstruire et redémarrer
docker-compose up -d --build

# Appliquer les migrations
docker-compose exec web python manage.py migrate
``` 