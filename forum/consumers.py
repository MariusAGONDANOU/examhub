import json
import logging
import asyncio
from datetime import datetime, timedelta
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from channels.layers import get_channel_layer
from django.contrib.auth.models import AnonymousUser
from django.core.cache import cache
from django.utils import timezone
from .models import Message

logger = logging.getLogger(__name__)

class ForumConsumer(AsyncWebsocketConsumer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.room_group_name = 'forum_updates'
        self.user = None
        self.connected_at = None
        self.typing = False
        self.typing_task = None

    async def connect(self):
        self.user = self.scope["user"]
        
        # Rejeter la connexion si l'utilisateur n'est pas authentifié
        if self.user.is_anonymous:
            await self.close()
            return

        # Enregistrer le temps de connexion
        self.connected_at = timezone.now()
        
        # Rejoindre le groupe de diffusion
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        
        # Accepter la connexion
        await self.accept()
        
        # Envoyer un événement de connexion
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'user_status',
                'user_id': self.user.id,
                'username': self.user.username,
                'status': 'online',
                'timestamp': timezone.now().isoformat()
            }
        )
        
        logger.info(f"User {self.user.username} connected to WebSocket")

    async def disconnect(self, close_code):
        if hasattr(self, 'typing_task') and self.typing_task:
            self.typing_task.cancel()
            
        # Envoyer un événement de déconnexion
        if hasattr(self, 'user') and self.user and not self.user.is_anonymous:
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'user_status',
                    'user_id': self.user.id,
                    'username': self.user.username,
                    'status': 'offline',
                    'timestamp': timezone.now().isoformat()
                }
            )
            logger.info(f"User {self.user.username} disconnected from WebSocket")
        
        # Quitter le groupe de diffusion
        if hasattr(self, 'room_group_name') and hasattr(self, 'channel_name'):
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name
            )

    # Réception d'un message du WebSocket
    async def receive(self, text_data):
        try:
            text_data_json = json.loads(text_data)
            message_type = text_data_json.get('type')
            
            if not message_type:
                logger.warning("Message WebSocket reçu sans type")
                return
                
            if message_type == 'typing':
                # Annuler la tâche de fin de frappe précédente si elle existe
                if hasattr(self, 'typing_task') and self.typing_task:
                    self.typing_task.cancel()
                
                # Vérifier que l'utilisateur est authentifié
                if not self.user or self.user.is_anonymous:
                    logger.warning("Tentative d'envoi de 'typing' par un utilisateur non authentifié")
                    return
                
                try:
                    # Diffuser l'événement de frappe
                    await self.channel_layer.group_send(
                        self.room_group_name,
                        {
                            'type': 'typing_event',
                            'user_id': self.user.id,
                            'username': self.user.username,
                            'is_typing': True,
                            'timestamp': timezone.now().isoformat()
                        }
                    )
                    
                    # Planifier l'arrêt de l'indication de frappe après 3 secondes
                    self.typing_task = asyncio.create_task(self.stop_typing_indicator())
                    
                except Exception as e:
                    logger.error(f"Erreur lors du traitement de l'événement 'typing': {str(e)}")
                
            elif message_type == 'typing_stopped':
                # Vérifier que l'utilisateur est authentifié
                if not self.user or self.user.is_anonymous:
                    return
                    
                try:
                    # Gérer l'arrêt de la frappe
                    await self.channel_layer.group_send(
                        self.room_group_name,
                        {
                            'type': 'typing_stopped',
                            'user_id': self.user.id,
                            'username': self.user.username,
                            'timestamp': timezone.now().isoformat()
                        }
                    )
                except Exception as e:
                    logger.error(f"Erreur lors du traitement de 'typing_stopped': {str(e)}")
                
            elif message_type == 'user_status':
                # Vérifier que l'utilisateur est authentifié
                if not self.user or self.user.is_anonymous:
                    return
                    
                try:
                    # Mettre à jour le statut de l'utilisateur
                    status = text_data_json.get('status', 'online')
                    if status in ['online', 'offline', 'away']:
                        await self.update_user_status(status)
                except Exception as e:
                    logger.error(f"Erreur lors de la mise à jour du statut utilisateur: {str(e)}")
                
            elif message_type == 'message_seen':
                # Vérifier que l'utilisateur est authentifié
                if not self.user or self.user.is_anonymous:
                    return
                    
                try:
                    # Gérer la notification de message vu
                    message_id = text_data_json.get('message_id')
                    if message_id:
                        seen = await self.mark_message_as_seen(message_id)
                        if seen:
                            # Diffuser l'événement de message vu uniquement si le message a été marqué comme vu
                            await self.channel_layer.group_send(
                                self.room_group_name,
                                {
                                    'type': 'message_seen_event',
                                    'message_id': message_id,
                                    'user_id': self.user.id,
                                    'username': self.user.username,
                                    'timestamp': timezone.now().isoformat()
                                }
                            )
                except Exception as e:
                    logger.error(f"Erreur lors du marquage du message comme vu: {str(e)}")
                    
            else:
                logger.warning(f"Type de message WebSocket non géré: {message_type}")
                    
        except json.JSONDecodeError as e:
            logger.error(f"JSON invalide reçu: {text_data}, erreur: {str(e)}")
        except Exception as e:
            logger.error(f"Erreur lors du traitement du message WebSocket: {str(e)}", exc_info=True)
    
    async def stop_typing_indicator(self):
        """Arrête l'indication de frappe après un délai"""
        try:
            await asyncio.sleep(3)
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'typing_stopped',
                    'user_id': self.user.id,
                    'username': self.user.username,
                    'timestamp': timezone.now().isoformat()
                }
            )
        except asyncio.CancelledError:
            # La tâche a été annulée car l'utilisateur a recommencé à taper
            pass

    # Gestion des événements de frappe
    async def typing_event(self, event):
        # Envoyer l'événement de frappe au client
        await self.send(text_data=json.dumps({
            'type': 'typing',
            'user_id': event['user_id'],
            'username': event['username'],
            'is_typing': event.get('is_typing', True),
            'timestamp': event.get('timestamp')
        }))
        
    async def typing_stopped(self, event):
        # Envoyer l'événement d'arrêt de frappe
        await self.send(text_data=json.dumps({
            'type': 'typing_stopped',
            'user_id': event['user_id'],
            'username': event['username'],
            'timestamp': event.get('timestamp')
        }))
        
    # Événement de statut utilisateur (en ligne/hors ligne)
    @database_sync_to_async
    def update_user_status(self, status):
        """Met à jour le statut de l'utilisateur dans la base de données."""
        try:
            if not self.user or self.user.is_anonymous:
                return
                
            # Mettre à jour le statut dans le cache
            cache_key = f'user_{self.user.id}_status'
            cache.set(cache_key, status, timeout=300)  # 5 minutes de cache
            
            # Ici, vous pourriez aussi mettre à jour le statut dans le modèle User si nécessaire
            # Par exemple :
            # self.user.profile.status = status
            # self.user.profile.save()
            
        except Exception as e:
            logger.error(f"Erreur lors de la mise à jour du statut utilisateur: {str(e)}")
            
    async def user_status(self, event):
        """Gère la réception d'un événement de changement de statut utilisateur."""
        try:
            await self.send(text_data=json.dumps({
                'type': 'user_status',
                'user_id': event.get('user_id'),
                'username': event.get('username'),
                'status': event.get('status'),
                'timestamp': event.get('timestamp')
            }))
        except Exception as e:
            logger.error(f"Erreur lors de l'envoi du statut utilisateur: {str(e)}")
        
    @database_sync_to_async
    def mark_message_as_seen(self, message_id):
        """Marquer un message comme vu par l'utilisateur"""
        try:
            message = Message.objects.get(id=message_id)
            if message.user_id != self.user.id:  # Ne pas marquer ses propres messages comme vus
                message.seen_by.add(self.user)
                message.save()
                return True
        except Message.DoesNotExist:
            logger.warning(f"Message {message_id} non trouvé")
        return False
        
    # Notification de message vu
    async def message_seen_event(self, event):
        await self.send(text_data=json.dumps({
            'type': 'message_seen',
            'message_id': event['message_id'],
            'user_id': event['user_id'],
            'username': event['username'],
            'timestamp': event['timestamp']
        }))

    # Gestion des nouveaux messages
    async def new_message(self, event):
        # Vérifier si le message est destiné à ce client spécifiquement
        if 'target_user_id' in event and event['target_user_id'] != self.user.id:
            return
            
        # Vérifier si le message est déjà dans le cache (éviter les doublons)
        message_id = event.get('message', {}).get('id')
        if message_id:
            cache_key = f'message_{message_id}_seen_by_{self.user.id}'
            if cache.get(cache_key):
                return
            cache.set(cache_key, True, timeout=300)  # Mettre en cache pendant 5 minutes
        
        await self.send(text_data=json.dumps({
            'type': 'new_message',
            'message': event['message'],
            'timestamp': timezone.now().isoformat()
        }))

    # Gestion des mises à jour de messages
    async def update_message(self, event):
        # Vérifier si le message est destiné à ce client spécifiquement
        if 'target_user_id' in event and event['target_user_id'] != self.user.id:
            return
            
        await self.send(text_data=json.dumps({
            'type': 'update_message',
            'message_id': event['message_id'],
            'content': event['content'],
            'edited': event['edited'],
            'edited_at': event['edited_at'],
            'timestamp': timezone.now().isoformat()
        }))

    # Gestion des suppressions de messages
    async def delete_message(self, event):
        # Vérifier si le message est destiné à ce client spécifiquement
        if 'target_user_id' in event and event['target_user_id'] != self.user.id:
            return
            
        await self.send(text_data=json.dumps({
            'type': 'delete_message',
            'message_id': event['message_id'],
            'deleted': event['deleted'],
            'deleted_by': event.get('deleted_by'),
            'deleted_at': event.get('deleted_at'),
            'timestamp': timezone.now().isoformat()
        }))
