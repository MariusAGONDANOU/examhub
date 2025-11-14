from django.db import models
from django.conf import settings
from django.core.validators import FileExtensionValidator
import os

def forum_attachment_path(instance, filename):
    # store files in MEDIA_ROOT/forum_attachments/YYYY/MM/DD/filename
    from django.utils import timezone
    today = timezone.now()
    return os.path.join('forum_attachments', str(today.year), f"{today.month:02d}", f"{today.day:02d}", filename)

class Message(models.Model):
    """
    Message du forum.
    - deleted: si True -> message supprimé pour tout le monde (affiché "Ce message a été supprimé")
    - hidden_for: liste d'utilisateurs pour lesquels le message est caché (suppression "pour soi")
    - reply_to: message auquel on répond (nullable)
    - attachment (legacy): fichier optionnel attaché au message (historique). Désormais supplanté par Attachment.
    - reply_to_attachment: si réponse à une pièce jointe spécifique (optionnel)
    """
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='forum_messages')
    content = models.TextField(blank=True)
    attachment = models.FileField(upload_to=forum_attachment_path, null=True, blank=True)  # legacy
    created_at = models.DateTimeField(auto_now_add=True)
    reply_to = models.ForeignKey('self', null=True, blank=True, on_delete=models.SET_NULL, related_name='replies')
    reply_to_attachment = models.ForeignKey('Attachment', null=True, blank=True, on_delete=models.SET_NULL, related_name='replies_to_attachment')
    deleted = models.BooleanField(default=False)
    deleted_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='forum_deleted_messages')
    deleted_at = models.DateTimeField(null=True, blank=True)
    edited = models.BooleanField(default=False)
    edited_at = models.DateTimeField(null=True, blank=True)
    # users who hid the message for themselves (delete "pour moi")
    hidden_for = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, related_name='forum_hidden_messages')

    class Meta:
        ordering = ['created_at']
        verbose_name = "Message Forum"
        verbose_name_plural = "Messages Forum"

    def __str__(self):
        content_snip = (self.content or "")[:40]
        return f"{self.user} @ {self.created_at:%Y-%m-%d %H:%M} : {content_snip}"

    @property
    def attachment_name(self):
        if not self.attachment:
            return ""
        return os.path.basename(self.attachment.name)

    def is_hidden_for(self, user):
        if not user or not user.is_authenticated:
            return False
        return self.hidden_for.filter(pk=user.pk).exists()

class Attachment(models.Model):
    """
    Pièce jointe multiple pour un message.
    """
    message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name='attachments')
    file = models.FileField(
        upload_to=forum_attachment_path,
        validators=[FileExtensionValidator([
            # images
            'jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp', 'svg',
            # vidéo
            'mp4', 'webm', 'ogg', 'mov', 'mkv',
            # documents
            'pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx', 'txt',
            # archives
            'zip', 'rar', '7z',
        ])]
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['uploaded_at']

    def __str__(self):
        return os.path.basename(self.file.name)

    @property
    def name(self):
        return os.path.basename(self.file.name)