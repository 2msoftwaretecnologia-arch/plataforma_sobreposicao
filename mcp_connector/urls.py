from django.urls import path

from . import views

app_name = 'mcp_connector'

urlpatterns = [
    path('arquivos/<str:token>/', views.download_file, name='arquivo'),
    path('enviar/<str:code>/', views.upload_page, name='enviar'),
]
