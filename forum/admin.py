from django.contrib import admin
from .models import Message, Attachment

@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'created_at', 'deleted')
    list_filter = ('deleted', 'created_at')
    search_fields = ('content', 'user__username')

@admin.register(Attachment)
class AttachmentAdmin(admin.ModelAdmin):
    list_display = ('id', 'message', 'name', 'uploaded_at')
    list_filter = ('uploaded_at',)
    search_fields = ('file',)