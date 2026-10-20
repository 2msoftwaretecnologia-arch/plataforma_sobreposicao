from django.contrib.auth.decorators import login_required
from django.urls import path
from . import views

urlpatterns = [
    # Página inicial: mapa 3D do SICAR com o formulário de análise.
    path('', login_required(views.UploadZipCarView.as_view()), name='upload_zip_car'),
    path('report/print/', login_required(views.ReportPrintView.as_view()), name='report_print'),
    path('results/', login_required(views.ResultsPageView.as_view()), name='results'),
    path('localizacoes/', login_required(views.LocalizacoesKmzView.as_view()), name='localizacoes_kmz'),
    path('localizacoes/sigef/analisar/', login_required(views.AnaliseParcelaSigefView.as_view()), name='analisar_parcela_sigef'),
    path('localizacoes/lotes/', login_required(views.LotesCruzamentoListView.as_view()), name='lotes_cruzamento'),
    path('localizacoes/lotes/novo/', login_required(views.LoteCruzamentoCreateView.as_view()), name='lote_cruzamento_novo'),
    path('localizacoes/lotes/<int:pk>/', login_required(views.LoteCruzamentoDetailView.as_view()), name='lote_cruzamento'),
    path('localizacoes/lotes/<int:pk>/status/', login_required(views.LoteCruzamentoStatusView.as_view()), name='lote_cruzamento_status'),
    path('localizacoes/lotes/<int:pk>/imprimir/', login_required(views.LoteCruzamentoPrintView.as_view()), name='lote_cruzamento_imprimir'),
    path('historico/', login_required(views.HistoricoView.as_view()), name='historico'),
    path('historico/<int:pk>/', login_required(views.HistoricoDetalheView.as_view()), name='historico_detalhe'),
    path('download/property-kml/', login_required(views.DownloadPropertyKmlView.as_view()), name='download_property_kml'),
    path('download/property-shp/', login_required(views.DownloadPropertyShapefileView.as_view()), name='download_property_shp'),
    path('bases-3d/tiles/<str:modelo>/<int:z>/<int:x>/<int:y>.pbf', login_required(views.BaseTileView.as_view()), name='base_tiles'),
    # Imagens de satélite do mapa de resultados (proxy para não expor as chaves).
    path('imagens/google/<int:z>/<int:x>/<int:y>', login_required(views.GoogleTileView.as_view()), name='imagery_google_tile'),
    path('imagens/wayback/datas/', login_required(views.WaybackReleasesView.as_view()), name='imagery_wayback_releases'),
    # Gerados no servidor a partir de GeoTIFFs públicos (raster_tiles.py).
    path('imagens/mapbiomas/<str:product>/<int:year>/<int:z>/<int:x>/<int:y>.png', login_required(views.MapbiomasTileView.as_view()), name='imagery_mapbiomas_tile'),
    path('imagens/cbers/cenas/', login_required(views.CbersScenesView.as_view()), name='imagery_cbers_scenes'),
    path('imagens/cbers/<str:scene>/<int:z>/<int:x>/<int:y>.webp', login_required(views.CbersTileView.as_view()), name='imagery_cbers_tile'),
    # Provedores OGC (planet, copernicus): ver OGC_PROVIDERS em imagery_service.py.
    path('imagens/<str:provider>/camadas/', login_required(views.ProviderLayersView.as_view()), name='imagery_provider_layers'),
    path('imagens/<str:provider>/<str:layer>/<int:z>/<int:x>/<int:y>', login_required(views.ProviderTileView.as_view()), name='imagery_provider_tile'),
    path('termos/', views.termos, name='termos_de_uso')
]
