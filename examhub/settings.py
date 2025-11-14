import os
import re
from pathlib import Path
from dotenv import load_dotenv
from decouple import config

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret")
DEBUG = os.getenv("DEBUG", "True") == "True"
ALLOWED_HOSTS = [h.strip() for h in os.getenv("ALLOWED_HOSTS", "").split(",") if h.strip()] or ["*"]

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.sites',
    
    # Apps tierces
    'channels',
    'rest_framework',
    'allauth',
    'allauth.account',
    'allauth.socialaccount',
    'debug_toolbar',
    'cachalot',
    'django_prometheus',
    
    # Apps locales
    'exams.apps.ExamsConfig',
    'forum.apps.ForumConfig',
    'core.apps.CoreConfig',
]

MIDDLEWARE = [
    # Middleware de débogage (uniquement en mode DEBUG)
    'debug_toolbar.middleware.DebugToolbarMiddleware',
    
    # Middleware de sécurité (doivent être en premier)
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    
    # Middleware de base
    'django.middleware.gzip.GZipMiddleware',  # Doit être avant CommonMiddleware
    'django.middleware.common.CommonMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    
    # Middleware d'authentification tierce
    'allauth.account.middleware.AccountMiddleware',
    
    # Middleware personnalisé
    'core.middleware.AutoLogoutMiddleware',
    
    # Middleware de performance (doivent être en dernier)
    'django.middleware.cache.UpdateCacheMiddleware',
    'django.middleware.common.CommonMiddleware',  # Doit être présent après UpdateCacheMiddleware
    'django.middleware.cache.FetchFromCacheMiddleware',
    'django_prometheus.middleware.PrometheusBeforeMiddleware',
    'django_prometheus.middleware.PrometheusAfterMiddleware',
]

ROOT_URLCONF = 'examhub.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'exams.context_processors.cart_context',
                'exams.context_processors.notifications_context',
            ],
        },
    },
]

WSGI_APPLICATION = 'examhub.wsgi.application'
ASGI_APPLICATION = 'examhub.asgi.application'

# Configuration des canaux (Channels)
CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels_redis.core.RedisChannelLayer',
        'CONFIG': {
            "hosts": [('127.0.0.1', 6379)],
        },
    },
}

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
        'simple': {
            'format': '{levelname} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
        'file': {
            'level': 'DEBUG',
            'class': 'logging.FileHandler',
            'filename': os.path.join(BASE_DIR, 'debug.log'),
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console', 'file'],
        'level': 'INFO',
    },
    'loggers': {
        'django': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
            'propagate': True,
        },
        'forum.views': {
            'handlers': ['console', 'file'],
            'level': 'DEBUG',
            'propagate': False,
        },
        'forum': {
            'handlers': ['console', 'file'],
            'level': 'DEBUG',
            'propagate': False,
        },
    },
}

LANGUAGE_CODE = 'fr-fr'
TIME_ZONE = 'Africa/Porto-Novo'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

PAYMENT_PROVIDER = os.getenv('PAYMENT_PROVIDER', 'SIMULATOR')
DOWNLOAD_TOKEN_TTL_HOURS = int(os.getenv('DOWNLOAD_TOKEN_TTL_HOURS', '48'))
DOWNLOAD_MAX_TIMES = int(os.getenv('DOWNLOAD_MAX_TIMES', '3'))

SITE_ID = 1

# --- Fichiers protégés (ZIP packs) ---
PROTECTED_MEDIA_ROOT = BASE_DIR / 'protected_media'
os.makedirs(PROTECTED_MEDIA_ROOT, exist_ok=True)  # s'assure que le dossier existe au démarrage

# Configuration des canaux (Channels)
ASGI_APPLICATION = 'examhub.asgi.application'

# Configuration du cache avec fallback en mémoire si Redis n'est pas disponible
try:
    CACHES = {
        'default': {
            'BACKEND': 'django_redis.cache.RedisCache',
            'LOCATION': 'redis://127.0.0.1:6379/1',
            'OPTIONS': {
                'CLIENT_CLASS': 'django_redis.client.DefaultClient',
                'COMPRESSOR': 'django_redis.compressors.zlib.ZlibCompressor',
                'IGNORE_EXCEPTIONS': True,
                'SOCKET_CONNECT_TIMEOUT': 5,  # Timeout de connexion de 5 secondes
                'SOCKET_TIMEOUT': 5,  # Timeout de socket de 5 secondes
            },
            'KEY_PREFIX': 'examhub',
            'TIMEOUT': 60 * 60 * 24,  # 24 heures
        },
        'sessions': {
            'BACKEND': 'django_redis.cache.RedisCache',
            'LOCATION': 'redis://127.0.0.1:6379/2',
            'OPTIONS': {
                'CLIENT_CLASS': 'django_redis.client.DefaultClient',
                'COMPRESSOR': 'django_redis.compressors.zlib.ZlibCompressor',
                'IGNORE_EXCEPTIONS': True,
            },
            'KEY_PREFIX': 'examhub-sessions',
        }
    }
    # Tester la connexion Redis
    import django_redis
    cache = django_redis.get_redis_connection("default")
    cache.ping()
except Exception as e:
    print(f"Warning: Redis n'est pas disponible, utilisation du cache en mémoire. Erreur: {e}")
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'examhub-cache',
            'TIMEOUT': 60 * 60 * 24,  # 24 heures
            'LOCATION': 'default-cache',
        },
        'sessions': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'session-cache',
            'TIMEOUT': 60 * 60 * 24 * 14,  # 2 semaines
            'OPTIONS': {
                'MAX_ENTRIES': 1000,
            }
        }
    }

# Configuration des sessions
SESSION_ENGINE = 'django.contrib.sessions.backends.cached_db'  # Utilise le cache et la base de données
SESSION_CACHE_ALIAS = 'sessions'
SESSION_COOKIE_AGE = 60 * 60 * 24 * 14  # 2 semaines
SESSION_COOKIE_HTTPONLY = True
SESSION_SAVE_EVERY_REQUEST = True
SESSION_EXPIRE_AT_BROWSER_CLOSE = False

# Configuration du backend de canaux avec fallback en mémoire si Redis n'est pas disponible
try:
    # Essayer d'utiliser Redis pour les canaux
    import redis
    r = redis.Redis(host='127.0.0.1', port=6379, socket_connect_timeout=1)
    r.ping()
    CHANNEL_LAYERS = {
        'default': {
            'BACKEND': 'channels_redis.core.RedisChannelLayer',
            'CONFIG': {
                "hosts": [('127.0.0.1', 6379)],
                "symmetric_encryption_keys": [SECRET_KEY],
                "channel_capacity": {
                    "http.request": 200,
                    "http.response*": 100,
                    re.compile(r"^websocket\.send\..*"): 50,
                },
            },
        },
    }
except (redis.ConnectionError, ImportError) as e:
    print(f"Warning: Redis n'est pas disponible pour les canaux, utilisation du backend en mémoire. Erreur: {e}")
    CHANNEL_LAYERS = {
        'default': {
            'BACKEND': 'channels.layers.InMemoryChannelLayer',
        },
    }

# Configuration du cache par défaut
CACHE_MIDDLEWARE_ALIAS = 'default'
CACHE_MIDDLEWARE_SECONDS = 60 * 15  # 15 minutes
CACHE_MIDDLEWARE_KEY_PREFIX = 'examhub'

# Configuration des performances
# Temps d'expiration du cache (en secondes)
CACHE_MIDDLEWARE_SECONDS = 60 * 15  # 15 minutes
CACHE_MIDDLEWARE_KEY_PREFIX = 'examhub'

# Configuration pour les requêtes lourdes
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024  # 10MB
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024  # 10MB

AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
    'allauth.account.auth_backends.AuthenticationBackend',
]

# New recommended settings (replaces the deprecated ones)
ACCOUNT_LOGIN_METHODS = {'username', 'email'}
ACCOUNT_SIGNUP_FIELDS = ['email*', 'username*', 'password1*', 'password2*']
ACCOUNT_EMAIL_VERIFICATION = 'optional'

ACCOUNT_FORMS = {
    'signup': 'exams.forms.CustomSignupForm',
}

LOGIN_REDIRECT_URL = '/redirect-after-login/'
LOGOUT_REDIRECT_URL = '/'


EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")
STRIPE_PUBLISHABLE_KEY = os.getenv("STRIPE_PUBLISHABLE_KEY")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")

CINETPAY_API_KEY = config("CINETPAY_API_KEY")
CINETPAY_SITE_ID = config("CINETPAY_SITE_ID")
CINETPAY_BASE_URL = config("CINETPAY_BASE_URL", default="https://api-checkout.cinetpay.com/v2/payment")

# Déconnexion automatique après inactivité
INACTIVITY_TIMEOUT = int(os.getenv("INACTIVITY_TIMEOUT", "1800"))  # 30 minutes
SESSION_COOKIE_AGE = INACTIVITY_TIMEOUT          # la session expire après ce délai
SESSION_SAVE_EVERY_REQUEST = True                # prolonge à chaque requête (sliding)
SESSION_EXPIRE_AT_BROWSER_CLOSE = False

# --- OpenAI (utilisé pour le chatbot) ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

# Autoriser l'affichage en iframe sur la même origine (nécessaire pour prévisualiser les PDF dans le forum)
X_FRAME_OPTIONS = 'SAMEORIGIN'

# Forum: taille maximale d’upload en méga-octets
FORUM_MAX_UPLOAD_MB = 200

# Forum: palette riche et Tenor
FORUM_RICH_PICKER_ENABLED = True
TENOR_API_KEY = os.environ.get('TENOR_API_KEY', 'AIzaSyAY80ADtucUK5qtQywhv2AUQSX-nl37YgM')
FORUM_MAX_UPLOAD_MB = int(os.getenv('FORUM_MAX_UPLOAD_MB', '200'))  # déjà utilisé côté serveur

# Options pour affiner le flux
FORUM_TENOR_CONTENTFILTER = 'low'   
FORUM_TENOR_LOCALE = ''        
FORUM_TENOR_COUNTRY = ''

GIPHY_API_KEY = os.environ.get('GIPHY_API_KEY', '')