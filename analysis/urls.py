from django.urls import path
from . import views

urlpatterns = [
    path('', views.UploadZipCarView.as_view(), name='upload_zip_car'),
    path('report/print/', views.ReportPrintView.as_view(), name='report_print'),
    path('results/', views.ResultsPageView.as_view(), name='results'),
    path('download/property-kml/', views.DownloadPropertyKmlView.as_view(), name='download_property_kml'),
    path('download/property-shp/', views.DownloadPropertyShapefileView.as_view(), name='download_property_shp'),
    path('termos/', views.termos, name='termos_de_uso')
]
