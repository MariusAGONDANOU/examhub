from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect
from . import views

@login_required
def index_protected(request, *args, **kwargs):
    profile = getattr(request.user, 'profile', None)
    role = getattr(profile, 'role', 'client')
    if role != 'client':
        return redirect('/gestion/')
    return views.index(request, *args, **kwargs)
