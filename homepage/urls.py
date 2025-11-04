from django.urls import path
from . import views

urlpatterns = [
    path('', views.upload_zip_car, name='homepage'),
    path('upload/', views.upload_zip_car, name='upload_zip_car'),
]