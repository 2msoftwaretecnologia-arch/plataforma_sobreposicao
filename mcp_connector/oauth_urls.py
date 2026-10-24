"""Somente os endpoints de OAuth que o conector usa.

O include padrão do django-oauth-toolkit também publicaria as telas de
gerenciamento de aplicações e tokens, que não fazem parte da plataforma.
"""

from django.urls import path
from oauth2_provider import views as oauth_views

from . import oauth_views as views

app_name = 'oauth2_provider'

urlpatterns = [
    path('authorize/', views.ConnectorAuthorizationView.as_view(), name='authorize'),
    path('token/', oauth_views.TokenView.as_view(), name='token'),
    path('revoke_token/', oauth_views.RevokeTokenView.as_view(), name='revoke-token'),
    path('register/', views.register_client, name='register-client'),
]
