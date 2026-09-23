from django.contrib.auth.decorators import login_required
from django.urls import path
from . import views

urlpatterns = [
    path('analysis/', login_required(views.UploadZipCarView.as_view()), name='upload_zip_car'),
    path('', views.Lading_PageView.as_view(), name='landing_page'),
    path('report/print/', login_required(views.ReportPrintView.as_view()), name='report_print'),
    path('results/', login_required(views.ResultsPageView.as_view()), name='results'),
    path('historico/', login_required(views.HistoricoView.as_view()), name='historico'),
    path('historico/<int:pk>/', login_required(views.HistoricoDetalheView.as_view()), name='historico_detalhe'),
    path('download/property-kml/', login_required(views.DownloadPropertyKmlView.as_view()), name='download_property_kml'),
    path('download/property-shp/', login_required(views.DownloadPropertyShapefileView.as_view()), name='download_property_shp'),
    path('bases-3d/', login_required(views.Bases3DView.as_view()), name='bases_3d'),
    path('bases-3d/tiles/<str:modelo>/<int:z>/<int:x>/<int:y>.pbf', login_required(views.BaseTileView.as_view()), name='base_tiles'),
    path('termos/', views.termos, name='termos_de_uso')
]
