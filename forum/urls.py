from django.urls import path
from . import views

app_name = 'forum'

urlpatterns = [
    path('', views.index, name='index'),
    path('messages/', views.messages_list, name='messages_list'),     # GET (liste), POST (créer)
    path('messages/<int:message_id>/delete/', views.message_delete, name='message_delete'),  # POST
    path('messages/<int:message_id>/edit/', views.message_edit, name='message_edit'),
    path('messages/<int:message_id>/attachments.zip', views.message_attachments_zip, name='message_attachments_zip'),
    path('attachments/<int:attachment_id>/delete/', views.attachment_delete, name='attachment_delete'),
    path('attachments/<int:attachment_id>/thumb/', views.attachment_thumb, name='attachment_thumb'),
    path('attachments/<int:attachment_id>/vthumb/', views.attachment_videothumb, name='attachment_videothumb'),
    path('attachments/<int:attachment_id>/zip/manifest/', views.attachment_zip_list, name='attachment_zip_manifest'),
    path('attachments/<int:attachment_id>/zip/file/', views.attachment_zip_file, name='attachment_zip_file'),
    path('api/assets/categories/', views.assets_categories, name='assets_categories'),  # GET
    path('api/assets/feed/', views.assets_feed, name='assets_feed'),                  # GET kind, q?, pos?
    path('api/assets/search/', views.assets_search, name='assets_search'),            # GET kind, q, pos?
    path('api/assets/proxy/', views.assets_proxy, name='assets_proxy'),
]
