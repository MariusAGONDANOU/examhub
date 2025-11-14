from rest_framework import serializers
from .models import Message, Attachment

class AttachmentSerializer(serializers.ModelSerializer):
    """Sérialiseur pour les pièces jointes des messages."""
    class Meta:
        model = Attachment
        fields = ['id', 'file', 'uploaded_at']
        read_only_fields = ['uploaded_at']

class MessageSerializer(serializers.ModelSerializer):
    """Sérialiseur pour les messages du forum."""
    user = serializers.SerializerMethodField()
    attachments = AttachmentSerializer(many=True, read_only=True)
    created_at = serializers.DateTimeField(format='%Y-%m-%dT%H:%M:%S')
    edited_at = serializers.DateTimeField(format='%Y-%m-%dT%H:%M:%S', allow_null=True)
    deleted_at = serializers.DateTimeField(format='%Y-%m-%dT%H:%M:%S', allow_null=True)
    deleted_by = serializers.PrimaryKeyRelatedField(read_only=True)
    
    class Meta:
        model = Message
        fields = [
            'id', 'user', 'content', 'created_at', 'reply_to', 
            'reply_to_attachment', 'deleted', 'deleted_by', 'deleted_at',
            'edited', 'edited_at', 'attachments'
        ]
        read_only_fields = ['id', 'created_at', 'user', 'deleted_by', 'deleted_at', 'edited', 'edited_at']
    
    def get_user(self, obj):
        """Sérialise les informations de l'utilisateur."""
        user = getattr(obj, 'user', None)
        if not user or user.is_anonymous:
            return None
            
        # Récupérer l'avatar si disponible
        avatar_url = None
        try:
            if hasattr(user, 'avatar') and user.avatar:
                avatar_url = user.avatar.url
            elif hasattr(user, 'profile') and hasattr(user.profile, 'avatar') and user.profile.avatar:
                avatar_url = user.profile.avatar.url
        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.error(f"Erreur lors de la récupération de l'avatar: {e}")
            
        request = self.context.get('request')
        
        try:
            return {
                'id': user.id,
                'username': user.username,
                'full_name': user.get_full_name() or user.username,
                'avatar': request.build_absolute_uri(avatar_url) if avatar_url and request else None,
                'is_staff': user.is_staff
            }
        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.error(f"Erreur lors de la sérialisation de l'utilisateur {user.id}: {e}")
            return {
                'id': user.id,
                'username': user.username,
                'full_name': user.username,
                'avatar': None,
                'is_staff': False
            }
    
    def to_representation(self, instance):
        """Personnalise la représentation du message."""
        try:
            representation = super().to_representation(instance)
            
            # Si le message est supprimé, ne renvoyer que les informations essentielles
            if instance.deleted:
                return {
                    'id': representation.get('id'),
                    'deleted': True,
                    'deleted_by': representation.get('deleted_by'),
                    'deleted_at': representation.get('deleted_at'),
                    'user': representation.get('user')
                }
                
            return representation
        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.error(f"Erreur lors de la sérialisation du message {getattr(instance, 'id', 'N/A')}: {e}", exc_info=True)
            return {
                'id': getattr(instance, 'id', None),
                'error': 'Erreur lors de la sérialisation du message',
                'user': None
            }
