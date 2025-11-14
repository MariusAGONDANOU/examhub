import os
import django
from django.core.asgi import get_asgi_application

# Définir le module de paramètres Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'examhub.settings')

# S'assurer que Django est configuré
django.setup()

# Importer les dépendances après la configuration de Django
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack

# Initialiser les patterns WebSocket
websocket_urlpatterns = []

# Importer les routes WebSocket après la configuration de Django
try:
    from forum import routing as forum_routing
    websocket_urlpatterns += forum_routing.websocket_urlpatterns
except (ImportError, AttributeError) as e:
    print("Warning: Could not import forum.routing. WebSocket support for forum may be limited.")
    print(f"Error details: {e}")

# Essayer d'ajouter les routes WebSocket de l'application exams (si elle existe)
try:
    import exams.routing as exams_routing
    websocket_urlpatterns += exams_routing.websocket_urlpatterns
except (ImportError, AttributeError) as e:
    print("Info: exams.routing not found. Running without exams WebSocket support.")
    print(f"Error details: {e}")

if not websocket_urlpatterns:
    print("Warning: No WebSocket URL patterns found. WebSocket support is disabled.")

# Obtenir l'application ASGI Django
django_asgi_app = get_asgi_application()

# Définir l'application ASGI
application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": AuthMiddlewareStack(
        URLRouter(websocket_urlpatterns)
    ),
})
