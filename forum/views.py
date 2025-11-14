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
            'message_id': message.id
        }
    
    # Envoyer l'événement au groupe du forum
    async_to_sync(channel_layer.group_send)('forum', event)

# Temps durant lequel l'auteur peut supprimer "pour tous" (en minutes)
DELETE_WINDOW_MINUTES = 5
EDIT_WINDOW_MINUTES = 5

def _has_paid(user):
    """
    Vérifie si l'utilisateur a payé pour accéder au forum.
    Par défaut, retourne True pour tous les utilisateurs authentifiés.
    À personnaliser selon votre logique métier.
    """
    return user.is_authenticated

def index(request):
    """Affiche la page du forum (ou message d'interdiction si pas d'achat)."""
    if not request.user.is_authenticated:
        return redirect('account_login')
    
    if not _has_paid(request.user):
        return render(request, 'forum/forbidden.html', status=403)
    
    return render(request, 'forum/forum.html')

def _compute_initials(identifier: str) -> str:
    """Calcule des initiales à partir d'un nom."""
    if not identifier:
        return "??"
    
    # Supprimer les espaces en trop et séparer les mots
    words = [w for w in identifier.strip().split() if w]
    
    if not words:
        return "??"
    
    # Prendre la première lettre de chaque mot, maximum 2 lettres
    initials = ''.join(word[0].upper() for word in words[:2])
    
    # Si on n'a qu'une seule lettre, on la duplique
    if len(initials) == 1:
        initials *= 2
    
    return initials

@require_http_methods(["GET", "POST"])
@login_required
def messages_list(request, *args, **kwargs):
    """
    GET: renvoie la liste JSON des messages (avec métadonnées).
         Paramètres: 
           - before_id: ID du message le plus récent à récupérer (pour la pagination)
           - limit: nombre de messages à retourner (défaut: 20)
    POST: création d'un message groupé (texte + 0..n pièces jointes).
          Supporte JSON et multipart/form-data. La réponse contient {ok, created: 1}
    """
    try:
        # Journalisation des informations de la requête (en mode debug uniquement)
        logger.debug("=== NOUVELLE REQUÊTE messages_list ===")
        logger.debug(f"Méthode: {request.method}")
        logger.debug(f"Utilisateur: {request.user} (ID: {request.user.id if request.user.is_authenticated else 'non authentifié'})")
        
        if request.method == 'GET':
            logger.info(f"Récupération des messages - Utilisateur: {request.user.id}")
            
            # Récupération des paramètres de requête avec valeurs par défaut
            before_id = request.GET.get('before_id')
            try:
                limit = min(int(request.GET.get('limit', 20)), 100)  # Limite à 100 messages max
            except (TypeError, ValueError) as e:
                logger.warning(f"Valeur de limite invalide: {request.GET.get('limit')}, utilisation de la valeur par défaut (20). Erreur: {e}")
                limit = 20
            
            try:
                # Construction de la requête de base
                messages = Message.objects.filter(deleted=False)  # Utilisation du champ deleted au lieu de deleted_for_all
                
                # Filtrage pour la pagination
                if before_id:
                    try:
                        before_id = int(before_id)
                        messages = messages.filter(id__lt=before_id)
                        logger.debug(f"Filtrage des messages avant l'ID: {before_id}")
                    except (ValueError, TypeError) as e:
                        logger.warning(f"Valeur before_id invalide: {before_id}. Erreur: {e}")
                
                # Exclusion des messages cachés pour l'utilisateur
                if request.user.is_authenticated:
                    messages = messages.exclude(hidden_for=request.user)
                
                # Tri par date de création décroissante et limitation
                messages = messages.select_related('user').prefetch_related('attachments', 'hidden_for')
                messages = messages.order_by('-created_at')[:limit]
                
                # Sérialisation des messages
                from .serializers import MessageSerializer
                serializer = MessageSerializer(
                    messages, 
                    many=True, 
                    context={'request': request}
                )
                
                logger.info(f"Récupération réussie de {len(serializer.data)} messages pour l'utilisateur {request.user.id}")
                
                return JsonResponse({
                    'ok': True,
                    'messages': serializer.data,
                    'has_more': len(serializer.data) == limit
                })
                
            except Exception as e:
                logger.error(f"Erreur lors de la récupération des messages: {str(e)}", exc_info=True)
                return JsonResponse(
                    {'ok': False, 'error': 'Erreur lors de la récupération des messages'},
                    status=500
                )
        
        elif request.method == 'POST':
            logger.info(f"Tentative de création d'un message par l'utilisateur {request.user.id}")
            
            try:
                # Vérifier que l'utilisateur a le droit de poster
                if not _has_paid(request.user):
                    logger.warning(f"Tentative de post non autorisée par l'utilisateur {request.user.id}")
                    return JsonResponse(
                        {'ok': False, 'error': 'Accès non autorisé'}, 
                        status=403
                    )
                
                # Vérifier si c'est une requête JSON ou multipart
                if request.content_type == 'application/json':
                    try:
                        data = json.loads(request.body)
                        content = data.get('content', '').strip()
                        attachment_ids = data.get('attachment_ids', [])
                    except json.JSONDecodeError as e:
                        logger.error(f"Erreur de décodage JSON: {str(e)}")
                        return JsonResponse(
                            {'ok': False, 'error': 'Format JSON invalide'},
                            status=400
                        )
                else:
                    content = request.POST.get('content', '').strip()
                    attachment_ids = request.POST.getlist('attachment_ids')
                
                # Validation du contenu
                if not content and not attachment_ids:
                    logger.warning("Tentative de création d'un message vide")
                    return JsonResponse(
                        {'ok': False, 'error': 'Le message ne peut pas être vide'}, 
                        status=400
                    )
                
                # Nettoyage du contenu HTML
                try:
                    cleaned_content = bleach.clean(
                        content,
                        tags=bleach.sanitizer.ALLOWED_TAGS + ['p', 'br', 'pre', 'code', 'span', 'div', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6'],
                        attributes=bleach.sanitizer.ALLOWED_ATTRIBUTES
                    )
                except Exception as e:
                    logger.error(f"Erreur lors du nettoyage du contenu: {str(e)}")
                    cleaned_content = content  # Utiliser le contenu non nettoyé en cas d'erreur
                
                # Création du message dans une transaction
                try:
                    with transaction.atomic():
                        # Créer le message
                        message = Message.objects.create(
                            author=request.user,
                            content=cleaned_content,
                            initial=_compute_initials(request.user.get_full_name() or request.user.username)
                        )
                        logger.info(f"Message {message.id} créé par l'utilisateur {request.user.id}")
                        
                        # Associer les pièces jointes si elles existent
                        if attachment_ids:
                            try:
                                attachments = Attachment.objects.filter(
                                    id__in=attachment_ids,
                                    message__isnull=True,
                                    uploaded_by=request.user
                                )
                                message.attachments.set(attachments)
                                logger.info(f"{len(attachments)} pièce(s) jointe(s) associée(s) au message {message.id}")
                            except Exception as e:
                                logger.error(f"Erreur lors de l'association des pièces jointes: {str(e)}")
                                # On continue même en cas d'erreur avec les pièces jointes
                    
                    # Diffuser le nouveau message à tous les clients
                    try:
                        broadcast_message_update(message, 'created')
                    except Exception as e:
                        logger.error(f"Erreur lors de la diffusion du message: {str(e)}")
                    
                    return JsonResponse({
                        'ok': True,
                        'created': 1,
                        'message_id': message.id
                    })
                    
                except Exception as e:
                    logger.error(f"Erreur lors de la création du message: {str(e)}", exc_info=True)
                    return JsonResponse(
                        {'ok': False, 'error': 'Erreur lors de la création du message'},
                        status=500
                    )
                
            except Exception as e:
                logger.error(f"Erreur inattendue dans messages_list (POST): {str(e)}", exc_info=True)
                return JsonResponse(
                    {'ok': False, 'error': 'Une erreur inattendue est survenue lors de la création du message'},
                    status=500
                )
    
    except Exception as e:
        logger.critical(f"Erreur critique dans messages_list: {str(e)}", exc_info=True)
        return JsonResponse(
            {'ok': False, 'error': 'Une erreur inattendue est survenue'},
            status=500
        )
        
    # Si aucune des méthodes n'est gérée (ne devrait pas arriver grâce au décorateur require_http_methods)
    logger.error(f"Méthode non gérée: {request.method}")
    return JsonResponse(
        {'ok': False, 'error': 'Méthode non implémentée'},
        status=501
    )

@require_POST
@login_required
def message_delete(request, message_id):
    """
    Supprime un message (soft delete).
    Seul l'auteur du message ou un administrateur peut supprimer un message.
    L'auteur a une fenêtre de temps limitée pour supprimer son message pour tous les utilisateurs.
    """
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
    
    # Si on est admin ou dans la fenêtre de suppression, on supprime pour tout le monde
    message.deleted_for_all = True
    message.save()
    
    # Diffuser la suppression du message à tous les clients
    broadcast_message_update(message, 'deleted')
    
    return JsonResponse({
        'ok': True, 
        'deleted': True,
        'deleted_for_all': True,
        'message_id': message.id
    })

@require_POST
@login_required
def message_edit(request, message_id):
    """
    Met à jour le contenu d'un message existant.
    Seul l'auteur du message peut le modifier, et uniquement pendant la fenêtre d'édition.
    """
    try:
        message = Message.objects.get(id=message_id)
    except Message.DoesNotExist:
        return JsonResponse({'ok': False, 'error': 'Message non trouvé'}, status=404)
    
    # Vérifier les permissions
    is_author = message.author == request.user
    is_admin = request.user.is_staff or request.user.is_superuser
    can_edit = is_author and (timezone.now() - message.created_at) < timedelta(minutes=EDIT_WINDOW_MINUTES)
    
    if not (can_edit or is_admin):
        return JsonResponse({'ok': False, 'error': 'Non autorisé ou fenêtre d\'édition expirée'}, status=403)
    
    # Récupérer le nouveau contenu
    try:
        if request.content_type == 'application/json':
            data = json.loads(request.body)
            new_content = data.get('content', '').strip()
        else:
            new_content = request.POST.get('content', '').strip()
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({'ok': False, 'error': 'Données invalides'}, status=400)
    
    if not new_content:
        return JsonResponse({'ok': False, 'error': 'Le contenu ne peut pas être vide'}, status=400)
    
    # Nettoyer le contenu HTML
    cleaned_content = bleach.clean(
        new_content,
        tags=bleach.sanitizer.ALLOWED_TAGS + ['p', 'br', 'pre', 'code', 'span', 'div', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6'],
        attributes=bleach.sanitizer.ALLOWED_ATTRIBUTES
    )
    
    # Mettre à jour le message
    message.content = cleaned_content
    message.updated_at = timezone.now()
    message.save()
    
    # Envoyer la mise à jour à tous les clients
    broadcast_message_update(message, 'updated')
    
    return JsonResponse({'ok': True, 'message': 'Message mis à jour avec succès'})

@require_GET
def message_attachments_zip(request, message_id):
    """
    Télécharge toutes les pièces jointes d'un message dans une archive ZIP.
    """
    try:
        message = Message.objects.get(id=message_id)
    except Message.DoesNotExist:
        raise Http404("Message non trouvé")
    
    # Vérifier si l'utilisateur a accès au message
    if message.deleted_for_all or (request.user.is_authenticated and message.deleted_for_users.filter(id=request.user.id).exists()):
        return HttpResponseForbidden("Accès refusé à ce message")
    
    # Créer une archive ZIP en mémoire
    memory_file = io.BytesIO()
    with zipfile.ZipFile(memory_file, 'w') as zf:
        for attachment in message.attachments.all():
            try:
                # Lire le contenu du fichier
                with open(attachment.file.path, 'rb') as f:
                    file_content = f.read()
                # Ajouter le fichier à l'archive avec son nom d'origine
                zf.writestr(attachment.filename, file_content)
            except (IOError, FileNotFoundError):
                logger.warning(f"Impossible de lire le fichier {attachment.file.path} pour le message {message_id}")
    
    # Retourner l'archive
    memory_file.seek(0)
    response = HttpResponse(memory_file, content_type='application/zip')
    response['Content-Disposition'] = f'attachment; filename=attachments_message_{message_id}.zip'
    return response

@require_POST
@login_required
def attachment_delete(request, attachment_id):
    """
    Supprime une pièce jointe d'un message.
    Seul l'auteur du message ou un administrateur peut supprimer une pièce jointe.
    """
    try:
        attachment = Attachment.objects.get(id=attachment_id)
    except Attachment.DoesNotExist:
        return JsonResponse({'ok': False, 'error': 'Pièce jointe non trouvée'}, status=404)
    
    # Vérifier les permissions
    is_author = attachment.message.author == request.user
    is_admin = request.user.is_staff or request.user.is_superuser
    
    if not (is_author or is_admin):
        return JsonResponse({'ok': False, 'error': 'Non autorisé'}, status=403)
    
    # Vérifier que le message n'a pas été supprimé pour tous
    if attachment.message.deleted_for_all:
        return JsonResponse({'ok': False, 'error': 'Le message a été supprimé'}, status=400)
    
    # Supprimer la pièce jointe
    attachment.file.delete()
    attachment.delete()
    
    # Mettre à jour le message
    broadcast_message_update(attachment.message, 'updated')
    
    return JsonResponse({'ok': True, 'message': 'Pièce jointe supprimée avec succès'})

def _serve_attachment(attachment, request, content_type=None, as_attachment=True):
    """
    Utilitaire pour servir un fichier avec le bon type MIME.
    """
    if not content_type:
        content_type, _ = mimetypes.guess_type(attachment.filename)
        if not content_type:
            content_type = 'application/octet-stream'
    
    response = FileResponse(attachment.file, content_type=content_type)
    
    if as_attachment:
        response['Content-Disposition'] = f'attachment; filename=\"{attachment.filename}\"'
    else:
        response['Content-Disposition'] = f'inline; filename=\"{attachment.filename}"'
    
    return response

@require_GET
def attachment_thumb(request, attachment_id):
    """
    Affiche la miniature d'une pièce jointe (pour les images).
    """
    try:
        attachment = Attachment.objects.get(id=attachment_id)
    except Attachment.DoesNotExist:
        raise Http404("Pièce jointe non trouvée")
    
    # Vérifier les permissions
    if attachment.message.deleted_for_all or (request.user.is_authenticated and attachment.message.deleted_for_users.filter(id=request.user.id).exists()):
        return HttpResponseForbidden("Accès refusé à ce message")
    
    # Vérifier si c'est une image
    if not attachment.is_image():
        return HttpResponseForbidden("Ce type de fichier ne peut pas être affiché en miniature")
    
    # Servir le fichier avec le bon type MIME
    return _serve_attachment(attachment, request, content_type='image/jpeg', as_attachment=False)

@require_GET
def attachment_videothumb(request, attachment_id):
    """
    Affiche une miniature pour une vidéo.
    """
    try:
        attachment = Attachment.objects.get(id=attachment_id)
    except Attachment.DoesNotExist:
        raise Http404("Pièce jointe non trouvée")
    
    # Vérifier les permissions
    if attachment.message.deleted_for_all or (request.user.is_authenticated and attachment.message.deleted_for_users.filter(id=request.user.id).exists()):
        return HttpResponseForbidden("Accès refusé à ce message")
    
    # Vérifier si c'est une vidéo
    if not attachment.is_video():
        return HttpResponseForbidden("Ce type de fichier ne peut pas être affiché en tant que vidéo")
    
    # Pour l'instant, on renvoie juste le fichier vidéo
    # Dans une version ultérieure, on pourrait générer une miniature
    return _serve_attachment(attachment, request, as_attachment=False)

@require_GET
def attachment_zip_list(request, attachment_id):
    """
    Affiche la liste des fichiers contenus dans une archive ZIP.
    """
    try:
        attachment = Attachment.objects.get(id=attachment_id)
    except Attachment.DoesNotExist:
        raise Http404("Pièce jointe non trouvée")
    
    # Vérifier les permissions
    if attachment.message.deleted_for_all or (request.user.is_authenticated and attachment.message.deleted_for_users.filter(id=request.user.id).exists()):
        return HttpResponseForbidden("Accès refusé à ce message")
    
    # Vérifier si c'est une archive ZIP
    if not attachment.is_zip():
        return JsonResponse({'ok': False, 'error': 'Ce fichier n\'est pas une archive ZIP'}, status=400)
    
    # Lire la liste des fichiers dans l'archive
    try:
        with zipfile.ZipFile(attachment.file.path, 'r') as zf:
            file_list = [{
                'name': info.filename,
                'size': info.file_size,
                'compressed_size': info.compress_size,
                'is_dir': info.is_dir()
            } for info in zf.infolist()]
        
        return JsonResponse({'ok': True, 'files': file_list})
    except (zipfile.BadZipFile, IOError) as e:
        logger.error(f"Erreur lors de la lecture de l'archive ZIP {attachment_id}: {str(e)}")
        return JsonResponse({'ok': False, 'error': 'Erreur lors de la lecture de l\'archive'}, status=500)

@require_GET
def attachment_zip_file(request, attachment_id):
    """
    Extrait et sert un fichier spécifique d'une archive ZIP.
    """
    file_path = request.GET.get('file')
    if not file_path:
        return JsonResponse({'ok': False, 'error': 'Paramètre file manquant'}, status=400)
    
    try:
        attachment = Attachment.objects.get(id=attachment_id)
    except Attachment.DoesNotExist:
        raise Http404("Pièce jointe non trouvée")
    
    # Vérifier les permissions
    if attachment.message.deleted_for_all or (request.user.is_authenticated and attachment.message.deleted_for_users.filter(id=request.user.id).exists()):
        return HttpResponseForbidden("Accès refusé à ce message")
    
    # Vérifier si c'est une archive ZIP
    if not attachment.is_zip():
        return JsonResponse({'ok': False, 'error': 'Ce fichier n\'est pas une archive ZIP'}, status=400)
    
    # Extraire le fichier demandé
    try:
        with zipfile.ZipFile(attachment.file.path, 'r') as zf:
            try:
                file_info = zf.getinfo(file_path)
            except KeyError:
                return JsonResponse({'ok': False, 'error': 'Fichier non trouvé dans l\'archive'}, status=404)
            
            # Créer une réponse avec le contenu du fichier
            response = HttpResponse(zf.read(file_info), content_type='application/octet-stream')
            response['Content-Disposition'] = f'attachment; filename=\"{os.path.basename(file_path)}\"'
            return response
    except (zipfile.BadZipFile, IOError) as e:
        logger.error(f"Erreur lors de l'extraction du fichier {file_path} de l'archive {attachment_id}: {str(e)}")
        return JsonResponse({'ok': False, 'error': 'Erreur lors de l\'extraction du fichier'}, status=500)

@require_GET
def assets_categories(request):
    """
    Renvoie les catégories d'actifs disponibles.
    """
    categories = [
        {'id': 'gifs', 'name': 'GIFs'},
        {'id': 'stickers', 'name': 'Autocollants'},
        {'id': 'emojis', 'name': 'Émojis'}
    ]
    return JsonResponse({'ok': True, 'categories': categories})

@require_GET
def assets_feed(request):
    """
    Renvoie une liste d'actifs (GIFs, autocollants, etc.) pour le flux.
    """
    kind = request.GET.get('kind', 'gifs')
    query = request.GET.get('q', '')
    position = request.GET.get('pos', '0')
    
    # Ici, vous pourriez implémenter une logique pour récupérer des actifs
    # depuis une API externe ou une base de données locale
    # Pour l'instant, on renvoie une liste vide
    return JsonResponse({
        'ok': True,
        'assets': [],
        'next_pos': None
    })

@require_GET
def assets_search(request):
    """
    Effectue une recherche d'actifs (GIFs, autocollants, etc.).
    """
    kind = request.GET.get('kind', 'gifs')
    query = request.GET.get('q', '')
    position = request.GET.get('pos', '0')
    
    if not query:
        return JsonResponse({'ok': False, 'error': 'Le paramètre q est requis'}, status=400)
    
    # Ici, vous pourriez implémenter une logique de recherche
    # Pour l'instant, on renvoie une liste vide
    return JsonResponse({
        'ok': True,
        'assets': [],
        'next_pos': None
    })

@require_GET
def assets_proxy(request):
    """
    Proxy pour récupérer des ressources externes en évitant les problèmes CORS.
    """
    url = request.GET.get('url')
    if not url:
        return JsonResponse({'ok': False, 'error': 'Le paramètre url est requis'}, status=400)
    
    try:
        # Vérifier que l'URL est autorisée
        allowed_domains = ['media.tenor.com', 'media1.tenor.com', 'media2.tenor.com', 'media3.tenor.com']
        if not any(url.startswith(f'https://{domain}/') for domain in allowed_domains):
            return JsonResponse({'ok': False, 'error': 'Domaine non autorisé'}, status=403)
        
        # Faire la requête
        response = requests.get(url, stream=True)
        response.raise_for_status()
        
        # Renvoyer la réponse
        return HttpResponse(
            response.content,
            content_type=response.headers.get('content-type', 'application/octet-stream')
        )
    except requests.RequestException as e:
        logger.error(f"Erreur lors de la récupération de la ressource {url}: {str(e)}")
        return JsonResponse({'ok': False, 'error': 'Erreur lors de la récupération de la ressource'}, status=500)
