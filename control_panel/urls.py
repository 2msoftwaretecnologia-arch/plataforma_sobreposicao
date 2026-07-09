from django.urls import path

from . import views

app_name = 'control_panel'

urlpatterns = [
    path('', views.dashboard_home_view, name='home'),
    path('armazenamento/', views.armazenamento_view, name='armazenamento'),
    path('armazenamento/atualizar/', views.armazenamento_refresh_view, name='armazenamento_refresh'),
    path('usuarios/', views.usuarios_view, name='usuarios'),
]
