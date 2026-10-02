from django.contrib.auth.decorators import login_required
from django.urls import path
from . import views

urlpatterns = [
    # Página inicial: mapa 3D do SICAR com o formulário de análise.
    path('', login_required(views.UploadZipCarView.as_view()), name='upload_zip_car'),
    path('report/print/', login_required(views.ReportPrintView.as_view()), name='report_print'),
    path('results/', login_required(views.ResultsPageView.as_view()), name='results'),
    path('localizacoes/', login_required(views.LocalizacoesKmzView.as_view()), name='localizacoes_kmz'),
    path('historico/', login_required(views.HistoricoView.as_view()), name='historico'),
    path('historico/<int:pk>/', login_required(views.HistoricoDetalheView.as_view()), name='historico_detalhe'),
    path('download/property-kml/', login_required(views.DownloadPropertyKmlView.as_view()), name='download_property_kml'),
    path('download/property-shp/', login_required(views.DownloadPropertyShapefileView.as_view()), name='download_property_shp'),
    path('bases-3d/tiles/<str:modelo>/<int:z>/<int:x>/<int:y>.pbf', login_required(views.BaseTileView.as_view()), name='base_tiles'),
    path('termos/', views.termos, name='termos_de_uso')
]
