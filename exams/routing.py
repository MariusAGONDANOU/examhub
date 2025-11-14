from django.urls import re_path

# Ce fichier est nécessaire pour le bon fonctionnement des WebSockets
# Si vous souhaitez ajouter des consommateurs WebSocket pour l'application exams,
# vous pouvez les ajouter ici.

websocket_urlpatterns = [
    # Ajoutez vos routes WebSocket ici si nécessaire
    # Exemple :
    # re_path(r'ws/exam/(?P<exam_id>\w+)/$', consumers.ExamConsumer.as_asgi()),
]
