"""
URL configuration for kernel project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include

from mcp_connector.oauth_views import authorization_server_metadata

urlpatterns = [
    path('admin/', admin.site.urls),
    path('auth/', include('authentication.urls')),
    path('painel/', include('control_panel.urls')),
    # Conector MCP (Claude e ChatGPT): OAuth e links de download. O /mcp em si
    # é o processo `run_mcp_server` (ver mcp_connector/README.md).
    path('o/', include('mcp_connector.oauth_urls', namespace='oauth2_provider')),
    path('.well-known/oauth-authorization-server', authorization_server_metadata,
         name='oauth_authorization_server_metadata'),
    path('conector/', include('mcp_connector.urls')),
    path('', include('analysis.urls')),
]
