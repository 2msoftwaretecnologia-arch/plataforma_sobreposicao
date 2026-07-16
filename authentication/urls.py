from django.contrib.auth.views import LogoutView
from django.urls import path

from . import views

app_name = 'authentication'

urlpatterns = [
    path('cadastro/', views.RegisterView.as_view(), name='register'),
    path('entrar/', views.CustomLoginView.as_view(), name='login'),
    path('sair/', LogoutView.as_view(next_page='landing_page'), name='logout'),
    path('onboarding/', views.OnboardingView.as_view(), name='onboarding'),
]
