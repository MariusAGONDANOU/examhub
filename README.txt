Examhub — Installation rapide
============================

1) Créez un environnement et installez les dépendances :
   python -m venv .venv
   source .venv/bin/activate   # Windows: .venv\Scripts\activate
   pip install -r requirements.txt

2) Migrations + données :
   python manage.py makemigrations
   python manage.py migrate
   python manage.py loaddata exams/fixtures/initial.json

3) Créez des fichiers ZIP factices pour tester les téléchargements :
   python manage.py create_dummy_packs

4) (Optionnel) Superutilisateur :
   python manage.py createsuperuser

5) Lancez le serveur :
   python manage.py runserver

6) Ouvrez http://127.0.0.1:8000
   Choisissez un examen > pack > Payer (simulateur) > Confirmer > Télécharger.

Variables .env utiles :
   DEBUG=True
   SECRET_KEY=change_me_in_production
   ALLOWED_HOSTS=localhost,127.0.0.1
   PAYMENT_PROVIDER=SIMULATOR
   DOWNLOAD_TOKEN_TTL_HOURS=48
   DOWNLOAD_MAX_TIMES=3
