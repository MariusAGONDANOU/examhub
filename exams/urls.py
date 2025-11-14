# exams/urls.py
from django.urls import path
from . import views
from .views_protect import index_protected
from . import views_account
from . import views_cart

app_name = 'exams'

urlpatterns = [
    path('', index_protected, name='index'),

    path('examens/<slug:slug>/', views.exam_detail, name='exam_detail'),
    path('order/create/', views.create_order, name='create_order'),
    path('order/<int:order_id>/confirm/', views.order_confirm, name='order_confirm'),
    path('payments/webhook/', views.payment_webhook, name='payment_webhook'),
    path('download/<str:token>/', views.download_file, name='download_file'),

    # Téléchargement depuis l'admin (stockage privé)
    path('admin/packs/<int:pk>/download/', views.admin_pack_download, name='admin_pack_download'),
    
    # Extraits publics (prévisualisation)
    path('extraits/', views.free_sample_page, name='free_sample'),
    path('extraits/<int:pk>/telecharger/', views.free_sample_download, name='free_sample_download'),

    # Compte / Profil
    path('me/', views_account.my_profile, name='my_profile'),
    path('me/delete/', views_account.delete_account, name='delete_account'),

    # Panier
    path('panier/', views_cart.cart_detail, name='cart_detail'),
    path('panier/ajouter/', views_cart.add_to_cart, name='add_to_cart'),
    path('panier/ajouter-plusieurs/', views_cart.add_multiple_to_cart, name='add_multiple_to_cart'),
    path('panier/supprimer/<int:item_id>/', views_cart.remove_from_cart, name='remove_from_cart'),
    path('panier/valider/', views_cart.cart_checkout, name='cart_checkout'),
    
    # Paiement Stripe
    path('paiement/success/', views_cart.payment_success, name='payment_success'),
    path('paiement/cancel/', views_cart.payment_cancel, name='payment_cancel'),
    path('webhooks/stripe/', views_cart.stripe_webhook, name='stripe_webhook'),
    path("momo/webhook/", views_cart.momo_webhook, name="momo_webhook"),

    # Notifications
    path('notifications/', views_account.notifications_list, name='notifications_list'),
    path('notifications/<int:pk>/lu/', views_account.notifications_mark_read, name='notifications_mark_read'),
    path('notifications/<int:pk>/supprimer/', views_account.notifications_delete, name='notifications_delete'),
    path('notifications/lire-tout/', views_account.notifications_mark_all_read, name='notifications_mark_all_read'),
    path('notifications/supprimer-tout/', views_account.notifications_delete_all, name='notifications_delete_all'),

    # Simulateur de paiement (test sans argent)
    path('paiement/simuler/', views_cart.payment_simulator, name='payment_simulator'),

    # Chatbot
    path('chat/', views_account.chatbot, name='chatbot'),
    path('chat/ask/', views_account.chatbot_ask, name='chatbot_ask'),       # AJAX: poser une question
    path('chat/upload/', views_account.chatbot_upload, name='chatbot_upload'), # AJAX: upload de fichier pour le chat
    path('chat/clear/', views_account.chatbot_clear, name='chatbot_clear'), # AJAX: réinitialiser la conversation
]
