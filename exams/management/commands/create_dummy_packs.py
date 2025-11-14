import os
import zipfile
from django.core.management.base import BaseCommand
from django.conf import settings

FILES = [
    'packs/bac-c_math_2015-2025.zip',
    'packs/bac-c_pct_2015-2025.zip',
    'packs/bac-c_math-pct_2015-2025.zip',
    'packs/cap-cb_math_2015-2025.zip',
    'packs/cap-cb_pct_2015-2025.zip',
    'packs/cap-cb_math-pct_2015-2025.zip',
    'packs/bepc-long_math_2015-2025.zip',
]

class Command(BaseCommand):
    help = 'Crée des fichiers ZIP factices dans media/packs pour les tests locaux.'

    def handle(self, *args, **options):
        media_root = settings.MEDIA_ROOT
        os.makedirs(os.path.join(media_root, 'packs'), exist_ok=True)
        for rel in FILES:
            path = os.path.join(media_root, rel)
            if not os.path.exists(path):
                with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
                    zf.writestr('LIRE-MOI.txt', 'Examhub — fichier de démonstration')
                self.stdout.write(self.style.SUCCESS(f'Créé : {path}'))
            else:
                self.stdout.write(f'Déjà présent : {path}')
        self.stdout.write(self.style.SUCCESS('Terminé.'))
