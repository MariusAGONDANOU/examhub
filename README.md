# ExamHub

## 📚 Description
ExamHub est une plateforme éducative Django permettant aux utilisateurs d'accéder à des ressources d'examens, de participer à des forums de discussion et de gérer leur progression académique.

## ✨ Fonctionnalités
- **Gestion des examens** : Téléchargement et consultation des sujets d'examens
- **Forum de discussion** : Espace d'échange entre étudiants avec messagerie en temps réel
- **Gestion des profils** : Espace personnel avec historique et favoris
- **Système de notation** : Suivi des performances aux examens

## 🛠️ Prérequis
- Python 3.8+
- Django 4.0+
- Redis (pour les fonctionnalités en temps réel)
- PostgreSQL/MySQL (recommandé pour la production)

## 🚀 Installation
1. Cloner le dépôt :
   ```bash
   git clone git@github.com:MariusAGONDANOU/examhub.git
   cd examhub
   ```

2. Créer un environnement virtuel :
   ```bash
   python -m venv venv
   source venv/bin/activate  # Sur Windows: venv\Scripts\activate
   ```

3. Installer les dépendances :
   ```bash
   pip install -r requirements.txt
   ```

4. Configurer les variables d'environnement :
   ```bash
   cp .env.example .env
   # Éditer .env avec vos paramètres
   ```

5. Effectuer les migrations :
   ```bash
   python manage.py migrate
   ```

6. Lancer le serveur de développement :
   ```bash
   python manage.py runserver
   ```

## 🌐 Structure du projet
- `core/` - Configuration de base et vues principales
- `exams/` - Gestion des examens et des résultats
- `forum/` - Système de discussion en temps réel
- `templates/` - Templates HTML
- `static/` - Fichiers statiques (CSS, JS, images)

## 📝 Fichier forum.html
Le fichier `templates/forum/forum.html` gère l'interface du forum avec les fonctionnalités suivantes :
- Affichage des messages en temps réel
- Défilement infini avec chargement automatique
- Gestion des réactions et des pièces jointes
- Interface utilisateur réactive

## 📄 Licence
Ce projet est sous licence MIT. Voir le fichier `LICENSE` pour plus de détails.

## 👥 Auteur
- **Marius AGONDANOU** - Développeur principal

## 🙏 Remerciements
- À tous les contributeurs qui ont participé au projet
