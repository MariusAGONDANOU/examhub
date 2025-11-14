from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.urls import reverse

def home(request):
    return render(request, 'home.html')

def visit_now(request):
    # Si connecté, rediriger selon le rôle
    user = request.user
    if user.is_authenticated:
        profile = getattr(user, 'profile', None)
        role = getattr(profile, 'role', 'client')
        if role == 'client':
            return redirect('exams:index')
        else:
            # Administrateur métier -> interface de gestion dédiée
            return redirect('/gestion/')
    # Non connecté -> aller à l'inscription/connexion
    return redirect(reverse('account_signup') + '?next=' + reverse('exams:index'))

@login_required
def redirect_after_login(request):
    # Après connexion Allauth, rediriger selon le rôle
    profile = getattr(request.user, 'profile', None)
    role = getattr(profile, 'role', 'client')
    if role == 'client':
        return redirect('exams:index')
    return redirect('/gestion/')
