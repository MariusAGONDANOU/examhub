from django.urls import path
from . import views

app_name = 'core'

urlpatterns = [
    path('', views.home, name='home'),
    path('visiter/', views.visit_now, name='visit_now'),
    path('redirect-after-login/', views.redirect_after_login, name='redirect_after_login'),
]
