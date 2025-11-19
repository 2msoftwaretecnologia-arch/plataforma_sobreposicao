from django.urls import path
from . import views

urlpatterns = [
    path('', views.AnswerspageView.as_view(), name='homepage'),
    path('upload/', views.UploadZipCarView.as_view(), name='upload_zip_car'),
]