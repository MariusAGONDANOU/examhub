import os
import json
import mimetypes
import io
import zipfile
import tempfile
import logging
import bleach
import requests
from datetime import timedelta
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Prefetch, Q
from django.http import JsonResponse, HttpResponse, Http404, FileResponse, HttpResponseNotAllowed, HttpResponseForbidden
from django.shortcuts import render, get_object_or_404, redirect
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.http import require_http_methods, require_GET, require_POST
from django.views.decorators.csrf import csrf_exempt
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from .models import Message, Attachment
from exams.models import Profile

logger = logging.getLogger(__name__)

def broadcast_message_update(message, action):
    """
    Envoie une mise à jour de message à tous les clients connectés via WebSocket.
    
    Args:
        message: L'instance du message à envoyer
        action: L'action effectuée ('created', 'updated', 'deleted')
    """
    from .serializers import MessageSerializer
    
    channel_layer = get_channel_layer()
    message_data = MessageSerializer(message).data
    
    if action == 'created':
        event = {
            'type': 'new_message',
            'message': message_data
        }
    elif action == 'updated':
        event = {
            'type': 'update_message',
            'message': message_data
        }
    elif action == 'deleted':
        event = {
            'type': 'delete_message',
            'message_id': message.id,
            'deleted': True,
            'deleted_by': message.deleted_by.id if message.deleted_by else None,
            'deleted_at': message.deleted_at.isoformat() if message.deleted_at else None
        }
    
    # Envoyer l'événement au groupe
    async_to_sync(channel_layer.group_send)('forum_updates', event)

# Temps durant lequel l'auteur peut supprimer "pour tous" (en minutes)
DELETE_WINDOW_MINUTES = 5
EDIT_WINDOW_MINUTES = 5

def _has_paid(user):
    """
    Vérifie si l'utilisateur a payé pour accéder au forum.
    Par défaut, retourne True pour tous les utilisateurs authentifiés.
    À personnaliser selon votre logique métier.
    """
    return True  # À adapter selon votre logique métier

@login_required
def index(request):
    """Affiche la page du forum (ou message d'interdiction si pas d'achat)."""
    if not _has_paid(request.user):
        return render(request, 'forum/forbidden.html', status=403)
    return render(request, 'forum/forum.html')

def _compute_initials(identifier: str) -> str:
    """Calcule des initiales à partir d'un nom."""
    if not identifier:
        return "?"
    
    # Supprimer les espaces multiples et diviser en mots
    words = ' '.join(identifier.split()).split()
    
    if not words:
        return "?"
    
    # Prendre la première lettre du premier mot
    initials = words[0][0].upper()
    
    # Si plus d'un mot, ajouter la première lettre du dernier mot
    if len(words) > 1:
        initials += words[-1][0].upper()
    
    return initials

@login_required
@require_http_methods(["GET", "POST"])
def messages_list(request, *args, **kwargs):
    """
    GET: renvoie la liste JSON des messages (avec métadonnées).
         Paramètres: 
           - before_id: ID du message le plus récent à récupérer (pour la pagination)
           - limit: nombre de messages à retourner (défaut: 20)
    POST: création d'un message groupé (texte + 0..n pièces jointes).
          Supporte JSON et multipart/form-data. La réponse contient {ok, created: 1}
    """
    # Vérification de l'authentification
    if not hasattr(request, 'user') or not request.user.is_authenticated:
        return JsonResponse({'ok': False, 'error': 'Authentification requise'}, status=401)
    
    user = request.user
    
    # Gestion des requêtes POST
    if request.method == 'POST':
        try:
            # Vérifier si l'utilisateur a les droits de poster
            if not _has_paid(user):
                return JsonResponse({'ok': False, 'error': 'Accès refusé. Achat requis.'}, status=403)
            
            # Initialisation des variables pour le traitement
            content = ''
            attachments_data = []
            
            # Vérifier le type de contenu
            if request.content_type == 'application/json':
                try:
                    data = json.loads(request.body)
                    content = data.get('content', '').strip()
                    attachments_data = data.get('attachments', [])
                except json.JSONDecodeError:
                    return JsonResponse({'ok': False, 'error': 'Données JSON invalides'}, status=400)
            elif request.content_type.startswith('multipart/form-data'):
                content = request.POST.get('content', '').strip()
                attachments_data = request.FILES.getlist('attachments')
            else:
                return JsonResponse({'ok': False, 'error': 'Type de contenu non supporté'}, status=415)
            
            # Validation des données
            if not content and not attachments_data:
                return JsonResponse({'ok': False, 'error': 'Le message ne peut pas être vide'}, status=400)
            
            # Nettoyer le contenu HTML
            allowed_tags = set(bleach.sanitizer.ALLOWED_TAGS) | {'p', 'br', 'div', 'span', 'pre', 'code', 'blockquote'}
            cleaned_content = bleach.clean(
                content,
                tags=allowed_tags,
                attributes={
                    'a': ['href', 'title', 'target', 'rel'],
                    'img': ['src', 'alt', 'title', 'width', 'height'],
                    'pre': ['class'],
                    'code': ['class'],
                    'span': ['class'],
                    'div': ['class']
                },
                strip=True
            )
            
            # Créer le message dans une transaction
            with transaction.atomic():
                message = Message.objects.create(
                    user=user,
                    content=cleaned_content or None
                )
                
                # Traiter les pièces jointes
                saved_attachments = []
                for attachment_data in attachments_data:
                    try:
                        if isinstance(attachment_data, dict):
                            # Gestion des pièces jointes depuis JSON (base64 ou URL)
                            if 'url' in attachment_data:
                                # Télécharger le fichier depuis l'URL
                                response = requests.get(attachment_data['url'], stream=True)
                                if response.status_code != 200:
                                    continue
                                    
                                # Créer un fichier temporaire
                                file_name = os.path.basename(attachment_data.get('name', 'file'))
                                temp_file = tempfile.NamedTemporaryFile(delete=False)
                                for chunk in response.iter_content(chunk_size=8192):
                                    temp_file.write(chunk)
                                temp_file.close()
                                
                                # Créer l'objet Attachment
                                with open(temp_file.name, 'rb') as f:
                                    attachment = Attachment(
                                        message=message,
                                        file_name=file_name
                                    )
                                    attachment.file.save(file_name, f, save=False)
                                    attachment.save()
                                    saved_attachments.append(attachment)
                                    
                                # Nettoyer le fichier temporaire
                                os.unlink(temp_file.name)
                                
                        else:
                            # Gestion des fichiers uploadés via formulaire
                            attachment = Attachment(
                                message=message,
                                file=attachment_data
                            )
                            attachment.save()
                            saved_attachments.append(attachment)
                            
                    except Exception as e:
                        logger.error(f"Erreur lors du traitement de la pièce jointe: {str(e)}", exc_info=True)
                        continue
            
            # Préparer la réponse
            from .serializers import MessageSerializer
            serializer = MessageSerializer(message)
            
            # Diffuser le nouveau message à tous les clients
            broadcast_message_update(message, 'created')
            
            return JsonResponse({
                'ok': True,
                'message': serializer.data,
                'created': len(saved_attachments) + 1  # +1 pour le message
            }, status=201)
            
        except Exception as e:
            logger.error(f"Erreur lors de la création du message: {str(e)}", exc_info=True)
            return JsonResponse({'ok': False, 'error': 'Une erreur est survenue lors de la création du message'}, status=500)
    
    # Gestion des requêtes GET
    elif request.method == 'GET':
        try:
            # Paramètres de pagination
            before_id = request.GET.get('before_id')
            limit = min(int(request.GET.get('limit', 20)), 50)  # Limite max de 50 messages
            
            # Construction de la requête optimisée
            messages_query = Message.objects.filter(deleted=False)
            
            # Filtrage pour la pagination
            if before_id:
                try:
                    before_message = Message.objects.get(id=before_id)
                    messages_query = messages_query.filter(created_at__lt=before_message.created_at)
                except Message.DoesNotExist:
                    pass
            
            # Récupération des messages avec optimisation des requêtes
            messages = list(messages_query.select_related('user', 'deleted_by')
                                       .prefetch_related(
                                           Prefetch('attachments', 
                                                   queryset=Attachment.objects.only('id', 'message_id', 'file', 'uploaded_at'))
                                       )
                                       .order_by('-created_at')[:limit])
            
            # Sérialisation des messages
            from .serializers import MessageSerializer
            serializer = MessageSerializer(messages, many=True)
            
            return JsonResponse({
                'ok': True,
                'messages': serializer.data,
                'count': len(messages)
            })
            
        except Exception as e:
            logger.error(f"Erreur lors de la récupération des messages: {str(e)}", exc_info=True)
            return JsonResponse({'ok': False, 'error': 'Une erreur est survenue lors de la récupération des messages'}, status=500)
    
    # Méthode non autorisée (normalement géré par le décorateur require_http_methods)
    return JsonResponse({'ok': False, 'error': 'Méthode non autorisée'}, status=405)

@require_POST
@login_required
def message_delete(request, message_id):
    """
    Supprime un message (soft delete).
    Seul l'auteur du message ou un administrateur peut supprimer un message.
    L'auteur a une fenêtre de temps limitée pour supprimer son message pour tous les utilisateurs.
    """
    if request.method != 'POST':
        return JsonResponse({'ok': False, 'error': 'Méthode non autorisée'}, status=405)
    
    try:
        message = Message.objects.get(id=message_id)
    except Message.DoesNotExist:
        return JsonResponse({'ok': False, 'error': 'Message non trouvé'}, status=404)
    
    # Vérifier les permissions
    is_author = message.author == request.user
    is_admin = request.user.is_staff or request.user.is_superuser
    can_delete_for_all = is_author and (timezone.now() - message.created_at) < timedelta(minutes=DELETE_WINDOW_MINUTES)
    
    if not (is_author or is_admin):
        return JsonResponse({'ok': False, 'error': 'Non autorisé'}, status=403)
    
    # Si l'utilisateur n'est pas admin et que le message a plus de 5 minutes,
    # on ne fait que masquer le message pour lui
    if not is_admin and not can_delete_for_all:
        message.deleted_for_users.add(request.user)
        # Si l'utilisateur est admin ou dans la fenêtre de suppression pour tous
        # on supprime complètement le contenu, sinon on le garde mais marqué comme supprimé
        if is_admin or can_delete_for_all:
            message.content = None
            
        message.save()
        
        # Diffuser la suppression du message à tous les clients
        broadcast_message_update(message, 'deleted')
        
        return JsonResponse({
            'ok': True, 
            'deleted': True,
            'deleted_for_all': is_admin or can_delete_for_all,
            'message_id': message.id
        })
        
    except Exception as e:
        logger.error(f"Erreur lors de la suppression du message {message_id}: {str(e)}", exc_info=True)
        return JsonResponse(
            {'ok': False, 'error': 'Une erreur est survenue lors de la suppression du message'}, 
            status=500
        )
