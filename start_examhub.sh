#!/bin/bash

# Variables
REDIS_PID=""
WORKER_PID=""
DAPHNE_PID=""
REDIS_RUNNING=false

# Fonction de nettoyage
cleanup() {
    echo -e "\nNettoyage en cours..."
    
    # Arrêt de Daphne
    if [ ! -z "$DAPHNE_PID" ]; then
        echo "Arrêt du serveur Daphne..."
        kill -TERM $DAPHNE_PID 2>/dev/null || true
    fi
    
    # Arrêt du worker Channels
    if [ ! -z "$WORKER_PID" ]; then
        echo "Arrêt du worker Channels..."
        kill -TERM $WORKER_PID 2>/dev/null || true
    fi
    
    # Arrêt de Redis s'il a été démarré par ce script
    if [ "$REDIS_RUNNING" = true ] && [ ! -z "$REDIS_PID" ]; then
        echo "Arrêt de Redis..."
        kill -TERM $REDIS_PID 2>/dev/null || true
    fi
    
    # Nettoyage des fichiers temporaires
    if [ -f "examhub/settings.py.bak" ]; then
        echo "Restauration de la configuration originale..."
        mv -f examhub/settings.py.bak examhub/settings.py 2>/dev/null || true
    fi
    
    echo "✅ Nettoyage terminé"
    exit 0
}

# Capturer le signal d'arrêt
trap cleanup SIGINT SIGTERM

# Arrêt des services en cours
echo "Arrêt des services en cours..."
pkill -f "daphne" || true
pkill -f "python manage.py runworker" || true

# Vérifier si Redis est déjà en cours d'exécution
echo "Vérification de Redis..."
if redis-cli ping &> /dev/null; then
    echo "✅ Redis est déjà en cours d'exécution"
    REDIS_RUNNING=true
else
    # Démarrer Redis s'il n'est pas déjà en cours d'exécution
    if command -v redis-server &> /dev/null; then
        echo "Démarrage de Redis..."
        # Démarrer Redis en arrière-plan et capturer son PID
        redis-server --daemonize no 2>&1 > redis.log &
        REDIS_PID=$!
        
        # Attendre que Redis soit prêt
        for i in {1..5}; do
            if redis-cli ping &> /dev/null; then
                REDIS_RUNNING=true
                echo "✅ Redis démarré avec succès (PID: $REDIS_PID)"
                break
            fi
            sleep 1
        done
        
        if [ "$REDIS_RUNNING" = false ]; then
            echo "⚠️  Impossible de démarrer Redis. Le mode sans Redis sera utilisé."
        fi
    else
        echo "⚠️  Redis n'est pas installé. Le mode sans Redis sera utilisé."
        REDIS_RUNNING=false
    fi
fi

# Activation de l'environnement virtuel
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
elif [ -f "../venv/bin/activate" ]; then
    cd ..
    source venv/bin/activate
else
    echo "❌ Erreur: Environnement virtuel non trouvé"
    exit 1
fi

# Vérification et installation des dépendances
echo "Vérification des dépendances..."
REQUIRED_PACKAGES=(
    "django-redis"
    "django-debug-toolbar"
    "django-cachalot"
    "django-prometheus"
    "channels-redis"
    "gunicorn"
    "daphne"
    "psycopg2-binary"
    "whitenoise"
    "python-dotenv"
    "django-allauth"
    "djangorestframework"
    "Pillow"
    "redis"
)

# Vérifier et installer les dépendances manquantes
for pkg in "${REQUIRED_PACKAGES[@]}"; do
    if ! pip show $pkg &> /dev/null; then
        echo "Installation de $pkg..."
        pip install $pkg
    else
        echo "✅ $pkg est déjà installé"
    fi
done

# Vérification et application des migrations
echo "Vérification des migrations..."
MIGRATIONS_NEEDED=$(python manage.py makemigrations --dry-run --noinput 2>&1 | grep "No changes detected")

if [ -z "$MIGRATIONS_NEEDED" ]; then
    echo "Création des migrations nécessaires..."
    python manage.py makemigrations
    echo "Application des migrations..."
    python manage.py migrate
else
    echo "Application des migrations existantes..."
    python manage.py migrate
fi
echo "✅ Migrations à jour"

# Collecte des fichiers statiques
echo "Collecte des fichiers statiques..."
python manage.py collectstatic --noinput
echo "✅ Fichiers statiques collectés"

# Vérification de la configuration pour WebSockets
if [ "$REDIS_RUNNING" = true ]; then
    echo "Configuration des canaux WebSocket avec Redis..."
    # S'assurer que Channels est activé
    sed -i "s/# 'channels'/'channels'/g" examhub/settings.py 2>/dev/null || true
    sed -i "s/# ASGI_APPLICATION/ASGI_APPLICATION/g" examhub/settings.py 2>/dev/null || true
    
    # Démarrer le worker pour les canaux
    echo "Démarrage du worker Channels..."
    python manage.py migrate
    python manage.py runworker forum &> worker.log &
    WORKER_PID=$!
    
    # Démarrer le serveur Daphne pour le support WebSocket
    echo -e "\n=== ExamHub avec support WebSocket est maintenant en ligne ==="
    echo "Page d'accueil:         http://localhost:8000/"
    echo "Interface d'administration: http://localhost:8000/admin/"
    echo "Forum (WebSocket):      http://localhost:8000/forum/"
    echo -e "\nAppuyez sur Ctrl+C pour arrêter\n"
    
    # Démarrer le serveur Daphne
    daphne -b 0.0.0.0 -p 8000 examhub.asgi:application
else
    # Mode sans WebSocket
    echo "Attention: WebSockets désactivés (Redis non disponible)"
    sed -i "s/'channels',/# 'channels',/g" examhub/settings.py 2>/dev/null || true
    sed -i "s/ASGI_APPLICATION/# ASGI_APPLICATION/g" examhub/settings.py 2>/dev/null || true
    
    echo -e "\n=== ExamHub est maintenant en ligne (sans WebSocket) ==="
    echo "Page d'accueil:         http://localhost:8000/"
    echo "Interface d'administration: http://localhost:8000/admin/"
    echo "Forum:                  http://localhost:8000/forum/"
    echo -e "\nAppuyez sur Ctrl+C pour arrêter\n"
    
    # Démarrer le serveur de développement Django standard
    python manage.py runserver 0.0.0.0:8000
fi

# Nettoyage à la sortie
cleanup
