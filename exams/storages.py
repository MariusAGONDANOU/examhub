import os
from django.core.files.storage import FileSystemStorage
from django.conf import settings

class ProtectedStorage(FileSystemStorage):
    """
    Stockage SANS URL publique : les fichiers ne sont JAMAIS servis par /media/.
    Ils ne peuvent être téléchargés que via une vue qui vérifie les permissions.
    """
    def __init__(self, *args, **kwargs):
        location = getattr(settings, "PROTECTED_MEDIA_ROOT", settings.BASE_DIR / "protected_media")
        super().__init__(location=location, base_url=None)  # base_url=None = pas d'URL publique
