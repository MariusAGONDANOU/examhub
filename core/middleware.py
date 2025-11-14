from django.utils import timezone
from django.conf import settings
from django.contrib.auth import logout

class AutoLogoutMiddleware:
    """
    Déconnecte l'utilisateur après un délai d'inactivité (sliding timeout).
    Le timestamp de la dernière activité est stocké en session.
    """

    def __init__(self, get_response):
        self.get_response = get_response
        self.timeout = int(getattr(settings, "INACTIVITY_TIMEOUT", 1800))  # défaut: 30 minutes

    def __call__(self, request):
        if request.user.is_authenticated:
            now_ts = int(timezone.now().timestamp())
            last = request.session.get("last_activity")
            if last is not None:
                try:
                    last = int(last)
                    if now_ts - last > self.timeout:
                        # Session trop vieille -> on déconnecte comme le font les grandes plateformes
                        logout(request)
                        request.session.flush()
                except Exception:
                    # Si valeur inattendue, on réinitialise proprement
                    request.session.flush()
            # Rafraîchit le timestamp à chaque requête (sliding expiration)
            request.session["last_activity"] = now_ts

        return self.get_response(request)
