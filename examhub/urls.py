from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

# Personnalisation légère de l'admin (titres)
admin.site.site_header = "Examhub — Backoffice"
admin.site.site_title = "Examhub — Backoffice"
admin.site.index_title = "Tableau de bord"

urlpatterns = [
    # Interface dédiée aux administrateurs métiers
    path('gestion/', admin.site.urls),

    # Site public
    path('', include('core.urls')),
    path('examens/', include('exams.urls')),
    
    # Forum
    path('forum/', include('forum.urls')),
    
    # Authentification (allauth)
    path('accounts/', include('allauth.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
