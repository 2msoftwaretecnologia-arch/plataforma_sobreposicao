from django.urls import path
from . import views

urlpatterns = [
    path('', views.UploadZipCarView.as_view(), name='upload_zip_car'),
    path('results/', views.ResultsPageView.as_view(), name='results'),
    path('termos/', views.termos, name='termos_de_uso')
]
