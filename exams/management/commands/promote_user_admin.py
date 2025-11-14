from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from exams.models import Profile

class Command(BaseCommand):
    help = "Promouvoir un utilisateur au rôle d'administrateur métier (et lui donner tous les droits Django)."

    def add_arguments(self, parser):
        parser.add_argument('username', help="Nom d'utilisateur à promouvoir")

    def handle(self, username, **options):
        User = get_user_model()
        try:
            u = User.objects.get(username=username)
        except User.DoesNotExist:
            raise CommandError(f"Utilisateur '{username}' introuvable.")
        profile, _ = Profile.objects.get_or_create(user=u)
        profile.role = 'administrator'
        profile.save()
        self.stdout.write(self.style.SUCCESS(f"{username} promu administrateur métier (is_staff & is_superuser activés)."))
