Modifications appliquées :
- Nouvelle page d’accueil (core app) conformément au cahier des charges.
- Bouton « Visiter maintenant » : 
  * si connecté client -> redirection vers la liste des examens (/examens/)
  * si connecté admin métier -> redirection vers /admin/
  * si non connecté -> redirection vers l’inscription (django-allauth), avec next vers /examens/
- Ancienne page d’accueil (liste des examens) protégée pour les clients connectés uniquement.
- Intégration django-allauth (applications, backends, URLs, redirections).
- Ajout du modèle Profile (rôle: client / administrateur métier) + administration.
- Redirection après connexion selon le rôle.
- URLs principales: 
    /  -> page d’accueil (core:home)
    /visiter/ -> logique de redirection
    /examens/ -> application exams (liste cliquable des examens pour clients)
    /accounts/ -> endpoints allauth (login/signup/logout)
Étapes post-déploiement :
- `python manage.py migrate` pour créer la table Profile.
- Créer un superuser puis définir le rôle des utilisateurs dans l’admin.
- Configurer `SITE_ID = 1` (déjà fait) dans l’admin Sites si besoin.
