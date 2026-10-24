"""Testes do conector MCP sem banco de dados.

O banco local é o de produção (via túnel), então, como nos testes de
`analysis`, tudo que tocaria o banco é substituído por dublês.
"""
import io
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from xml.etree import ElementTree as ET

import numpy as np
from django.core import signing
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, override_settings
from mcp.server.auth.provider import AccessToken
from PIL import Image
from shapely import wkt as shapely_wkt
from starlette.testclient import TestClient

from analysis.models import SearchHistory

from . import exports, imagery, limits, pdf_report, queries, schemas, static_map, uploads
from .models import McpUpload
from .oauth_views import _redirect_allowed
from .server import _audit_arguments, build_server

PROPERTY_WKT = 'POLYGON ((-48.36 -10.2, -48.33 -10.2, -48.33 -10.23, -48.36 -10.23, -48.36 -10.2))'
EMBARGO_WKT = 'POLYGON ((-48.36 -10.2, -48.35 -10.2, -48.35 -10.21, -48.36 -10.21, -48.36 -10.2))'
LOCMEM = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache', 'LOCATION': 'mcp-testes'}}


def _geojson(wkt):
    from shapely.geometry import mapping
    return json.dumps(mapping(shapely_wkt.loads(wkt)))


def _item(info, area, wkt=None, **extra):
    item = {'item_info': info, 'area': area, **extra}
    if wkt:
        item.update(polygon_wkt=wkt, polygon_geojson=_geojson(wkt), color='#FF5722')
    return item


def _data():
    return {
        'sucesso': True,
        'car_input': 'TO-1721000-ABC',
        'municipio': 'Palmas',
        'uf': 'TO',
        'resultado': {
            'tamanho_area': 1000,
            'alvo_wkt': PROPERTY_WKT,
            'alvo_geojson': _geojson(PROPERTY_WKT),
            'resultados_por_base': [
                {'nome_base': 'Base de Dados de Zoneamento',
                 'areas_encontradas': [_item('Zona A', 1000, PROPERTY_WKT, zona='A')]},
                {'nome_base': 'Base de Dados de APAs',
                 'areas_encontradas': [_item('Sem unidade de conservação', 1000, PROPERTY_WKT)]},
                {'nome_base': 'Base de Embargos do IBAMA',
                 'areas_encontradas': [
                     _item('Embargo 123', 120.5, EMBARGO_WKT, numero_tad='123', polygon_extra='x' * 400),
                     _item('Embargo 9', 0.01, EMBARGO_WKT),
                 ]},
                {'nome_base': 'Base de Dados Sigef', 'areas_encontradas': []},
            ],
        },
    }


def _history(pk=7, search_type=SearchHistory.SearchType.CAR):
    return SimpleNamespace(
        pk=pk, search_type=search_type, created_at=datetime(2026, 10, 24, 15, 0, tzinfo=timezone.utc),
        get_search_type_display=lambda: 'Número do CAR',
    )


def _report():
    """Relatório no formato de `queries.analysis_report`."""
    return {
        'analise_id': 7, 'data': '24/10/2026 12:00', 'car': 'TO-1721000-ABC', 'nome_imovel': 'Fazenda Boa Vista',
        'proprietarios': [{'nome': 'Maria', 'cpf_cnpj': '000'}], 'municipio': 'Palmas', 'uf': 'TO',
        'localizacao': {'latitude': -10.215, 'longitude': -48.345, 'google_maps': 'https://maps.example'},
        'area_imovel_ha': 1000.0, 'veredito': 'Há pontos de alerta', 'alertas': 1, 'pontos_de_atencao': 0,
        'perguntas': [{'pergunta': 'Há embargo do IBAMA?', 'status': 'alerta', 'resposta': 'Sim (120,5 ha)',
                       'explicacao': 'Embargo & restrição <ativo>.'}],
        'bases_com_ocorrencia': [{'base': 'Base de Embargos do IBAMA', 'titulo': 'Embargos do IBAMA', 'nivel': 'alerta',
                                  'o_que_e': 'Áreas embargadas.', 'o_que_significa': 'Impede crédito.',
                                  'area_ha': 120.5, 'percentual_do_imovel': 12.05,
                                  'itens': [{'descricao': 'Embargo 123', 'area_ha': 120.5}]}],
        'bases_so_com_encoste_minimo': ['Base de Dados Sigef'], 'bases_sem_ocorrencia': [],
        'limite_residual_ha': 0.1,
        'reserva_legal': {'exigida_ha': 350.0, 'declarada': None, 'deficit_ha': 0, 'avaliada': False},
        'vegetacao_natural': [{'tipo': 'Savana', 'area_ha': 500.0}], 'municipios': ['Palmas'],
        'uso_do_solo_mapbiomas': {'ano_antes': 2008, 'ano_depois': 2025, 'vegetacao_nativa_antes_ha': 600.0,
                                  'vegetacao_nativa_depois_ha': 500.0, 'vegetacao_retirada_ha': 100.0,
                                  'vegetacao_regenerada_ha': 0.0, 'destino_da_vegetacao_retirada': [],
                                  'uso_por_grupo': [{'grupo': 'Vegetação nativa', 'antes_ha': 600.0, 'depois_ha': 500.0}]},
        'atualizacao_das_bases': [{'base': 'Base de Embargos do IBAMA', 'atualizada_em': '01/10/2026 03:00',
                                   'fonte': 'Arquivo enviado no painel da plataforma'}],
        'links': {'resultado_na_plataforma': 'https://plataforma.example/historico/7/',
                  'relatorio_para_imprimir': 'https://plataforma.example/report/print/?historico=7',
                  'relatorio_pdf': 'https://plataforma.example/conector/arquivos/x/'},
    }


def _png(size=(10, 10)):
    buffer = io.BytesIO()
    Image.new('RGB', size).save(buffer, format='PNG')
    return buffer.getvalue()


class FakeBasemap(static_map.Basemap):
    """Fundo sem rede: guarda os zooms pedidos e descreve uma imagem fictícia."""

    def __init__(self, max_zoom=static_map.MAX_ZOOM):
        self.max_zoom = max_zoom
        self.zooms = set()

    def tile(self, session, zoom, x, y):
        self.zooms.add(zoom)
        return Image.new('RGBA', (256, 256), (40, 90, 40, 255))

    def describe(self, geom, zoom, left, top):
        return {'tipo': 'satelite', 'descricao': 'Satélite Teste, captura de 01/01/2026, 1 m'}

    def source_lines(self, fonte):
        return [fonte['descricao']]


# ---------------------------------------------------------------------------
# Resumo, geometria e mapa
# ---------------------------------------------------------------------------

@override_settings(MCP_PUBLIC_BASE_URL='https://plataforma.example')
class SummaryTests(SimpleTestCase):
    def test_summary_orders_by_severity_and_skips_neutral_items(self):
        summary = queries.analysis_summary(_history(), _data())

        self.assertEqual(summary['analise_id'], 7)
        self.assertEqual(summary['data'], '24/10/2026 12:00')
        bases = summary['bases_com_sobreposicao']
        self.assertEqual([b['base'] for b in bases], ['Base de Embargos do IBAMA', 'Base de Dados de Zoneamento'])
        embargo = bases[0]
        self.assertEqual((embargo['nivel'], embargo['quantidade'], embargo['area_ha']), ('alerta', 2, 120.51))
        self.assertEqual(embargo['percentual_do_imovel'], 12.05)
        self.assertNotIn('residual', embargo['itens'][0])
        self.assertTrue(embargo['itens'][1]['residual'])
        self.assertEqual(summary['bases_sem_sobreposicao'], ['Base de Dados de APAs', 'Base de Dados Sigef'])
        self.assertEqual(summary['links']['relatorio_para_imprimir'],
                         'https://plataforma.example/report/print/?historico=7')
        schemas.AnaliseResumo.model_validate(summary)

    def test_find_base_by_part_of_the_name(self):
        resultado = _data()['resultado']

        self.assertEqual(queries.find_base(resultado, 'embargos')['nome_base'], 'Base de Embargos do IBAMA')
        with self.assertRaisesMessage(queries.QueryError, 'mais de uma base'):
            queries.find_base(resultado, 'base de dados')
        with self.assertRaisesMessage(queries.QueryError, 'não encontrada'):
            queries.find_base(resultado, 'prodes')

    def test_item_attributes_drop_geometry_and_cut_long_text(self):
        item = _data()['resultado']['resultados_por_base'][2]['areas_encontradas'][0]

        attributes = queries.item_attributes(item)
        self.assertEqual(attributes['numero_tad'], '123')
        self.assertEqual(len(attributes['polygon_extra']), queries.MAX_ATTRIBUTE_CHARS)
        self.assertFalse({'polygon_wkt', 'polygon_geojson', 'color', 'item_info', 'area'} & set(attributes))


class ParseGeometryTests(SimpleTestCase):
    def test_geojson_feature_collection_becomes_one_area(self):
        collection = {'type': 'FeatureCollection', 'features': [
            {'type': 'Feature', 'geometry': json.loads(_geojson(EMBARGO_WKT))},
            {'type': 'Feature', 'geometry': {'type': 'Point', 'coordinates': [-48.3, -10.2]}},
        ]}

        geometry, search_type = queries.parse_geometry(json.dumps(collection))
        self.assertEqual(geometry.srid, 4674)
        self.assertEqual(geometry.geom_type, 'Polygon')
        self.assertEqual(search_type, SearchHistory.SearchType.COORDENADAS)

    def test_kml_is_read_like_the_upload(self):
        kml = ('<kml xmlns="http://www.opengis.net/kml/2.2"><Placemark><Polygon><outerBoundaryIs><LinearRing>'
               '<coordinates>-48.36,-10.2,0 -48.35,-10.2,0 -48.35,-10.21,0 -48.36,-10.2,0</coordinates>'
               '</LinearRing></outerBoundaryIs></Polygon></Placemark></kml>')

        geometry, search_type = queries.parse_geometry(kml)
        self.assertEqual(search_type, SearchHistory.SearchType.KML)
        self.assertAlmostEqual(geometry.extent[0], -48.36, places=4)

    def test_rejects_lines_utm_garbage_and_huge_areas(self):
        cases = {
            'LINESTRING (-48.3 -10.2, -48.2 -10.1)': 'precisa ser um polígono',
            'POLYGON ((780000 8870000, 781000 8870000, 781000 8871000, 780000 8870000))': 'UTM',
            'isto não é geometria': 'Não consegui ler',
            'POLYGON ((-49 -10, -47 -10, -47 -12, -49 -12, -49 -10))': 'limite por análise',
            '': 'Informe a geometria',
        }
        for text, message in cases.items():
            with self.subTest(text=text), self.assertRaisesMessage(queries.QueryError, message):
                queries.parse_geometry(text)


class MapTests(SimpleTestCase):
    def test_default_map_shows_only_alert_and_attention_bases(self):
        layers, showing, notes = exports.map_layers(_data()['resultado'])

        self.assertEqual(showing, 'Bases de alerta e atenção')
        self.assertEqual([layer['label'] for layer in layers], ['Embargos do IBAMA'])
        self.assertEqual(len(layers[0]['geometries']), 2)
        self.assertEqual(notes, [])

    def test_all_skips_context_bases_and_single_base_gets_a_color_per_item(self):
        resultado = _data()['resultado']

        layers, _, _ = exports.map_layers(resultado, 'todas')
        self.assertEqual([layer['label'] for layer in layers], ['Embargos do IBAMA'])
        layers, showing, _ = exports.map_layers(resultado, 'zoneamento')
        self.assertEqual(showing, 'Base de Dados de Zoneamento')
        self.assertEqual(layers[0]['label'], 'Zona A')
        self.assertEqual(layers[0]['color'], static_map.ITEM_PALETTE[0])

    def test_base_covering_the_whole_area_becomes_a_note(self):
        resultado = _data()['resultado']
        resultado['resultados_por_base'].append({
            'nome_base': 'Base de Dados de Unidades de Conservação',
            'areas_encontradas': [_item('Parque Estadual do Cantão', 999.5, PROPERTY_WKT)],
        })

        layers, _, notes = exports.map_layers(resultado, 'todas')
        self.assertEqual([layer['label'] for layer in layers], ['Embargos do IBAMA'])
        self.assertIn('Parque Estadual do Cantão', notes[0])

    def test_overlays_on_a_year_image_default_to_the_outline_only(self):
        resultado = _data()['resultado']

        self.assertEqual(exports.overlay_layers(resultado)[0], [])
        self.assertEqual([layer['label'] for layer in exports.overlay_layers(resultado, 'alertas')[0]],
                         ['Embargos do IBAMA'])
        self.assertEqual(exports.overlay_layers(resultado, 'zoneamento')[0][0]['label'], 'Zona A')

    def test_zoom_fits_the_area(self):
        small = static_map.fit_zoom((-48.36, -10.23, -48.33, -10.2))
        large = static_map.fit_zoom((-49.0, -12.0, -47.0, -10.0))
        self.assertGreater(small, large)
        self.assertLessEqual(small, static_map.MAX_ZOOM)

    def test_frame_uses_the_next_zoom_reduced_to_fill_the_map(self):
        bounds = (-48.36, -10.23, -48.33, -10.2)
        zoom, scale = static_map.frame(bounds)

        self.assertEqual(zoom, static_map.fit_zoom(bounds) + 1)
        self.assertTrue(0.5 <= scale < 1)
        x0, y1 = static_map.world_pixel(bounds[0], bounds[1], zoom)
        x1, y0 = static_map.world_pixel(bounds[2], bounds[3], zoom)
        height = (y1 - y0) * scale
        self.assertLessEqual(height, static_map.MAP_HEIGHT - 2 * static_map.PADDING + 1)
        self.assertGreater(height, (static_map.MAP_HEIGHT - 2 * static_map.PADDING) * 0.85)

    def test_render_without_network_returns_the_image_source(self):
        basemap = FakeBasemap()
        png, fonte = static_map.render_map(_geojson(PROPERTY_WKT), exports.map_layers(_data()['resultado'])[0],
                                           'Título', basemap=basemap,
                                           notes=['Cobrem toda a área (não pintadas): APA.'])

        image = Image.open(io.BytesIO(png))
        self.assertEqual(image.size, (static_map.WIDTH, static_map.HEIGHT))
        self.assertEqual(Image.open(io.BytesIO(static_map.to_jpeg(png))).format, 'JPEG')
        self.assertIn('Satélite Teste', fonte['descricao'])

    def test_a_coarse_image_is_fetched_at_its_own_zoom_and_enlarged(self):
        basemap = FakeBasemap(max_zoom=11)
        png, _ = static_map.render_map(_geojson(PROPERTY_WKT), [], 'Título', basemap=basemap)

        self.assertEqual(basemap.zooms, {11})
        self.assertEqual(Image.open(io.BytesIO(png)).size, (static_map.WIDTH, static_map.HEIGHT))

    def test_named_basemaps_still_work_and_bad_names_fail(self):
        tile = Image.new('RGB', (256, 256), (40, 90, 40))
        with patch.object(static_map, '_fetch_tile', return_value=tile):
            _, fonte = static_map.render_map(_geojson(PROPERTY_WKT), [], 'Título', basemap='mapa')
        self.assertEqual(fonte['tipo'], 'mapa')
        with self.assertRaisesMessage(static_map.MapRenderError, 'Fundo inválido'):
            static_map.render_map(_geojson(PROPERTY_WKT), [], 'Título', basemap='lua')

    def test_render_fails_clearly_without_tiles(self):
        with patch.object(static_map, '_fetch_tile', return_value=None), \
                self.assertRaisesMessage(static_map.MapRenderError, 'não respondeu'):
            static_map.render_map(_geojson(PROPERTY_WKT), [], 'Título', basemap='satelite')


# ---------------------------------------------------------------------------
# Fontes de imagem
# ---------------------------------------------------------------------------

def _scene(scene_id, day, cloud, platform='landsat-5'):
    return {'id': scene_id, 'date': day, 'cloud': cloud, 'platform': platform}


class ImageryTests(SimpleTestCase):
    def test_esri_captures_are_named_deduplicated_and_newest_first(self):
        day = lambda iso: datetime.fromisoformat(iso).replace(tzinfo=timezone.utc).timestamp() * 1000  # noqa: E731
        captures = imagery._captures([
            {'SRC_DESC': 'WV02', 'NICE_DESC': 'Maxar', 'SRC_DATE2': day('2021-06-12'), 'SRC_RES': 0.5, 'SRC_ACC': 5},
            {'SRC_DESC': 'WV02', 'NICE_DESC': 'Maxar', 'SRC_DATE2': day('2021-06-12'), 'SRC_RES': 0.5},
            {'SRC_DESC': 'GE01', 'NICE_DESC': 'Maxar', 'SRC_DATE2': day('2023-08-01'), 'SRC_RES': 0.46},
        ])

        self.assertEqual([c['satelite'] for c in captures], ['GeoEye-1', 'WorldView-2'])
        self.assertEqual(captures[1]['data_captura'], '12/06/2021')
        self.assertEqual(captures[1]['provedor'], 'Maxar')

    def test_esri_source_says_satellite_date_and_version(self):
        release = {'id': 1, 'date': '2026-09-25', 'metadata_url': 'https://metadados.example'}
        captures = [{'satelite': 'WorldView-2', 'provedor': 'Maxar', 'data_captura': '12/06/2021',
                     'resolucao_m': 0.5, 'precisao_m': None}]
        geom = shapely_wkt.loads(PROPERTY_WKT)
        with patch.object(imagery, 'esri_captures', return_value=captures):
            current = imagery.EsriBasemap(release).describe(geom, 15, 0, 0)
            past = imagery.EsriBasemap(release, requested_year=2016).describe(geom, 15, 0, 0)

        self.assertIn('WorldView-2 (Maxar), captura de 12/06/2021, 0,5 m', current['descricao'])
        self.assertIn('25/09/2026', current['provedor'])
        self.assertEqual(current['resolucao_m'], 0.5)
        self.assertIn('2021', past['observacao'])
        self.assertIn('wayback', imagery.EsriBasemap(release).url)

    def test_esri_without_metadata_says_the_date_is_unknown(self):
        with patch.object(imagery, 'esri_captures', return_value=[]):
            fonte = imagery.EsriBasemap({'id': 1, 'date': '2026-09-25', 'metadata_url': ''}).describe(
                shapely_wkt.loads(PROPERTY_WKT), 15, 0, 0)
        self.assertIn('não informou', fonte['descricao'])

    def test_landsat_scene_is_the_clearest_of_the_year_closest_to_july(self):
        scenes = [
            _scene('A', '2008-02-10', 0), _scene('B', '2008-07-20', 0), _scene('C', '2008-08-05', 3),
            _scene('D', '2007-07-01', 0),
        ]
        with patch.object(imagery.imagery_service, 'landsat_legacy_scenes', return_value=scenes):
            chosen, others = imagery.choose_landsat_scene(-48.3, -10.2, 2008)
            picked, _ = imagery.choose_landsat_scene(-48.3, -10.2, 2008, scene_id='C')
            with self.assertRaisesMessage(static_map.MapRenderError, 'Anos mais próximos com imagem: 2007, 2008'):
                imagery.choose_landsat_scene(-48.3, -10.2, 1999)

        self.assertEqual(chosen['id'], 'B')
        self.assertEqual({s['id'] for s in others}, {'A', 'C'})
        self.assertEqual(picked['id'], 'C')

    def test_landsat_source_names_satellite_sensor_date_and_cloud(self):
        basemap = imagery.LandsatBasemap(_scene('LE07_L2SP_222067_20080720_02_T1', '2008-07-20', 4, 'landsat-7'),
                                         'falsa_cor', [_scene('X', '2008-06-01', 9)])
        fonte = basemap.describe(shapely_wkt.loads(PROPERTY_WKT), 13, 0, 0)

        self.assertEqual((fonte['satelite'], fonte['sensor'], fonte['data_captura']), ('Landsat 7', 'ETM+', '20/07/2008'))
        self.assertEqual(fonte['resolucao_m'], 30)
        self.assertIn('Planetary Computer', fonte['descricao'])
        self.assertIn('SLC', fonte['observacao'])
        self.assertEqual(fonte['outras_cenas_do_ano'][0]['cena'], 'X')
        self.assertIn('Landsat 7 (sensor ETM+), captura de 20/07/2008', basemap.source_lines(fonte)[0])

    def test_year_picks_landsat_wayback_or_explains_the_gap(self):
        with patch.object(imagery, 'choose_landsat_scene', return_value=(_scene('A', '2008-07-20', 0), [])):
            self.assertIsInstance(imagery.historical(2008, -48.3, -10.2), imagery.LandsatBasemap)
        releases = [{'id': 2, 'date': '2017-01-04', 'metadata_url': ''}, {'id': 1, 'date': '2016-12-07', 'metadata_url': ''}]
        with patch.object(imagery, '_wayback_releases', return_value=releases):
            wayback = imagery.historical(2016, -48.3, -10.2)
        self.assertEqual((wayback.release['id'], wayback.requested_year), (1, 2016))
        with self.assertRaisesMessage(static_map.MapRenderError, 'Não há imagem de 2013'):
            imagery.historical(2013, -48.3, -10.2)

    def test_land_use_shares_inside_the_property(self):
        basemap = imagery.LandUseBasemap(2008, area_ha=100)
        # Janela de 100 × 100 px; metade esquerda savana (4), direita pastagem (15).
        basemap.codes = np.where(np.arange(100)[None, :] < 50, 4, 15).repeat(100, axis=0).astype(np.uint8)
        zoom = 12
        left, top = static_map.world_pixel(-48.36, -10.2, zoom)
        right, bottom = left + 100, top + 100
        lon_right = -48.36 + (right - left) / (256 * 2 ** zoom) * 360
        poly = shapely_wkt.loads(
            f'POLYGON ((-48.36 -10.2, {lon_right} -10.2, {lon_right} -10.25, -48.36 -10.25, -48.36 -10.2))')

        fonte = basemap.describe(poly, zoom, left, top)
        shares = {s['classe']: s['percentual'] for s in fonte['classes_no_imovel']}
        self.assertAlmostEqual(shares['Formação Savânica'], 50, delta=2)
        self.assertEqual(len(basemap.legend_rows(fonte)), 2)
        self.assertIn('MapBiomas', fonte['descricao'])
        with self.assertRaisesMessage(static_map.MapRenderError, 'uso do solo de'):
            imagery.LandUseBasemap(1970)


# ---------------------------------------------------------------------------
# Arquivos e links
# ---------------------------------------------------------------------------

class ExportTests(SimpleTestCase):
    def test_overlaps_kml_has_a_colored_folder_per_base(self):
        kml = exports.overlaps_kml(_data(), 'Sobreposições')

        root = ET.fromstring(kml)
        ns = {'k': 'http://www.opengis.net/kml/2.2'}
        folders = [f.find('k:name', ns).text for f in root.iter('{http://www.opengis.net/kml/2.2}Folder')]
        self.assertEqual(folders, ['Imóvel analisado', 'Base de Dados de Zoneamento (1)', 'Base de Embargos do IBAMA (2)'])
        styles = {s.get('id') for s in root.iter('{http://www.opengis.net/kml/2.2}Style')}
        self.assertIn('imovel', styles)
        self.assertIn('numero_tad', kml.decode())

    def test_overlaps_shapefile_frame_has_the_base_column(self):
        gdf = exports.overlaps_geodataframe(_data()['resultado'])

        self.assertEqual(sorted(set(gdf['base'])), ['Base de Dados de Zoneamento', 'Base de Embargos do IBAMA'])
        self.assertEqual(len(gdf), 3)

    @override_settings(MCP_PUBLIC_BASE_URL='https://plataforma.example')
    def test_signed_link_roundtrip_and_expiry(self):
        user = SimpleNamespace(pk=5)
        url = exports.file_url(user, 7, 'imagem', 'png', fundo={'tipo': 'historica', 'ano': 2008})

        self.assertTrue(url.startswith('https://plataforma.example/conector/arquivos/'))
        token = url.rstrip('/').rsplit('/', 1)[1]
        self.assertEqual(exports.read_token(token)['m'], {'tipo': 'historica', 'ano': 2008})
        with self.assertRaises(signing.BadSignature):
            exports.read_token(token[:-2] + 'xx')
        with override_settings(MCP_FILE_LINK_MAX_AGE=-1), self.assertRaises(signing.SignatureExpired):
            exports.read_token(token)

    @override_settings(MCP_PUBLIC_BASE_URL='https://plataforma.example')
    def test_download_links_include_the_pdf(self):
        with patch.object(exports, 'load_analysis', return_value=(_history(), _data())):
            links = exports.download_links(SimpleNamespace(pk=5), 7)

        self.assertIn('/conector/arquivos/', links['relatorio_pdf'])
        self.assertEqual([b['base'] for b in links['por_base']], ['Base de Dados de Zoneamento', 'Base de Embargos do IBAMA'])
        schemas.ArquivosAnalise.model_validate(links)

    @override_settings(MCP_PUBLIC_BASE_URL='https://plataforma.example')
    def test_download_view_serves_the_file_of_a_valid_link(self):
        token = exports.file_url(SimpleNamespace(pk=5), 7, 'imovel', 'kml').rstrip('/').rsplit('/', 1)[1]
        user = SimpleNamespace(pk=5)
        with patch('mcp_connector.views.get_user_model') as model, \
                patch('mcp_connector.views.build_file', return_value=(b'<kml/>', 'propriedade.kml', 'application/vnd.google-earth.kml+xml')) as build:
            model.return_value.objects.filter.return_value.first.return_value = user
            response = self.client.get(f'/conector/arquivos/{token}/')
            build.return_value = (b'%PDF', 'relatorio.pdf', 'application/pdf')
            pdf = self.client.get(f'/conector/arquivos/{token}/')
            expired = None
            with override_settings(MCP_FILE_LINK_MAX_AGE=-1):
                expired = self.client.get(f'/conector/arquivos/{token}/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Disposition'], 'attachment; filename="propriedade.kml"')
        self.assertEqual(pdf['Content-Disposition'], 'inline; filename="relatorio.pdf"')
        self.assertEqual(build.call_args.args[1]['k'], 'imovel')
        self.assertEqual(expired.status_code, 410)
        self.assertEqual(self.client.get('/conector/arquivos/adulterado/').status_code, 404)

    @override_settings(MCP_PUBLIC_BASE_URL='https://plataforma.example')
    def test_historical_images_bring_the_source_and_the_current_image(self):
        user = SimpleNamespace(pk=5)
        landsat = imagery.LandsatBasemap(_scene('LT05_L2SP_222067_20080712_02_T1', '2008-07-12', 1), 'natural')
        landsat.tile = lambda session, zoom, x, y: Image.new('RGBA', (256, 256), (90, 120, 60, 255))
        current = FakeBasemap()
        with patch.object(exports, 'load_analysis', return_value=(_history(), _data())), \
                patch.object(imagery, 'basemap_for', side_effect=[landsat, current]):
            images = exports.historical_images(user, 7, ano=2008)

        (_, past), (_, now) = images
        self.assertEqual(past['fonte_imagem']['satelite'], 'Landsat 5')
        self.assertEqual(past['fonte_imagem']['data_captura'], '12/07/2008')
        self.assertIn('Satélite Teste', now['fonte_imagem']['descricao'])
        token = past['link_png'].rstrip('/').rsplit('/', 1)[1]
        self.assertEqual(exports.read_token(token)['k'], 'imagem')

    def test_pdf_report_is_built_with_and_without_the_map(self):
        pdf = pdf_report.build_pdf(_report(), 'CAR TO-1721000-ABC', _png((1400, 900)),
                                   {'descricao': 'WorldView-2 (Maxar), captura de 12/06/2021, 0,5 m'})
        without_map = pdf_report.build_pdf({**_report(), 'aviso_bases_atualizadas': 'PRODES atualizado.'},
                                           'Análise nº 7', map_error='servidor fora do ar')

        self.assertTrue(pdf.startswith(b'%PDF'))
        self.assertTrue(without_map.startswith(b'%PDF'))
        self.assertGreater(len(pdf), len(without_map))


# ---------------------------------------------------------------------------
# Reaproveitamento, limites, progresso e relatório
# ---------------------------------------------------------------------------

class ReuseTests(SimpleTestCase):
    def test_reuse_window_starts_at_the_latest_base_update(self):
        now = datetime(2026, 10, 24, tzinfo=timezone.utc)
        with patch.object(queries.timezone, 'now', return_value=now), override_settings(MCP_REUSE_DAYS=7):
            with patch.object(queries, 'latest_layer_update', return_value=now - timedelta(days=2)):
                self.assertEqual(queries._reuse_since(), now - timedelta(days=2))
            with patch.object(queries, 'latest_layer_update', return_value=None):
                self.assertEqual(queries._reuse_since(), now - timedelta(days=7))
        with override_settings(MCP_REUSE_DAYS=0):
            self.assertIsNone(queries._reuse_since())

    def test_car_analysis_reuses_a_recent_one_unless_forced(self):
        user = SimpleNamespace(pk=5)
        reused = {'analise_id': 3, 'reaproveitada': True}
        with patch.object(queries, 'find_reusable', return_value=reused) as find, \
                patch.object(queries, 'SearchForCar') as engine:
            self.assertEqual(queries.analyze_car(user, 'TO-1721000-1A2B3C4D5E6F7A8B9C0D1E2F3A4B5C6D'), reused)
            engine.assert_not_called()
            engine.return_value.execute.return_value = {}
            with self.assertRaisesMessage(queries.QueryError, 'não está na base do SICAR'):
                queries.analyze_car(user, 'TO-1721000-1A2B3C4D5E6F7A8B9C0D1E2F3A4B5C6D', forcar_nova=True)
        self.assertEqual(find.call_count, 1)

    def test_same_drawn_area_is_found_by_geometry(self):
        from django.contrib.gis.geos import GEOSGeometry

        geometry = GEOSGeometry(EMBARGO_WKT, srid=4674)
        other = SimpleNamespace(pk=1, result_data={'coordenadas_recebidas': str(GEOSGeometry(PROPERTY_WKT, srid=4674))})
        same = SimpleNamespace(pk=2, result_data={'coordenadas_recebidas': str(geometry)})
        queryset = MagicMock()
        queryset.only.return_value.__getitem__.return_value = [other, same]
        with patch.object(queries, '_reuse_since', return_value=datetime(2026, 10, 1, tzinfo=timezone.utc)), \
                patch.object(queries.SearchHistory.objects, 'filter', return_value=queryset), \
                patch.object(queries, '_reused_summary', side_effect=lambda user, h: {'analise_id': h.pk}):
            self.assertEqual(queries.find_reusable_geometry(SimpleNamespace(pk=5), geometry), {'analise_id': 2})

    def test_reused_summary_explains_why(self):
        with patch.object(queries, 'load_analysis', return_value=(_history(), _data())), \
                override_settings(MCP_PUBLIC_BASE_URL='https://plataforma.example'):
            summary = queries._reused_summary(SimpleNamespace(pk=5), _history(), aviso='O ponto cai em 2 imóveis.')

        self.assertTrue(summary['reaproveitada'])
        self.assertTrue(summary['aviso'].startswith('O ponto cai em 2 imóveis.'))
        self.assertIn('forcar_nova=true', summary['aviso'])


@override_settings(CACHES=LOCMEM, MCP_ANALYSES_PER_MINUTE=2, MCP_ANALYSES_PER_HOUR=0,
                   MCP_MAX_CONCURRENT_PER_USER=1, MCP_MAX_CONCURRENT_TOTAL=2)
class LimitTests(SimpleTestCase):
    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        limits._running.clear()

    def test_rate_per_minute(self):
        limits.check_rate(1)
        limits.check_rate(1)
        with self.assertRaisesMessage(limits.LimitExceeded, '2 análises por minuto'):
            limits.check_rate(1)
        limits.check_rate(2)

    def test_concurrent_analyses_per_user_and_in_total(self):
        with limits.analysis_slot(1):
            with self.assertRaisesMessage(limits.LimitExceeded, 'em andamento'):
                with limits.analysis_slot(1):
                    pass
            with limits.analysis_slot(2):
                with self.assertRaisesMessage(limits.LimitExceeded, 'muitas análises'):
                    with limits.analysis_slot(3):
                        pass
        self.assertEqual(limits._running, {})

    def test_limit_becomes_a_tool_error(self):
        with patch.object(limits, 'analysis_slot', side_effect=limits.LimitExceeded('Limite atingido.')), \
                self.assertRaisesMessage(queries.QueryError, 'Limite atingido.'):
            queries._run(SimpleNamespace(pk=1), lambda: None)


class ProgressTests(SimpleTestCase):
    def test_reports_each_base_once(self):
        calls = []
        progress = queries.ToolProgress(lambda *args: calls.append(args))
        layer = type('Embargoes', (), {})

        self.assertTrue(progress)
        progress.layers([layer])
        progress.layer_started(layer)
        progress.layer_started(layer)
        progress.layer_done(layer, [])
        self.assertEqual(calls[-2:], [(0, 1, 'Consultando as bases: Embargos do IBAMA'),
                                      (1, 1, 'Consultando as bases: Embargos do IBAMA')])


@override_settings(MCP_PUBLIC_BASE_URL='https://plataforma.example')
class ReportTests(SimpleTestCase):
    def test_bases_update_dates_and_bases_updated_after_the_analysis(self):
        dates = {
            'Embargoes': (datetime(2026, 10, 30, tzinfo=timezone.utc), 'importacao'),
            'ZoningArea': (None, None),
            'Sigef': (datetime(2026, 1, 5, tzinfo=timezone.utc), 'arquivo'),
        }
        with patch.object(queries, 'layer_update_dates', return_value=dates):
            rows, newer = queries.bases_update_info(
                ['Base de Embargos do IBAMA', 'Base de Dados de Zoneamento', 'Base de Dados Sigef', 'Outra'],
                datetime(2026, 10, 24, tzinfo=timezone.utc))

        self.assertEqual([r['base'] for r in rows], ['Base de Embargos do IBAMA', 'Base de Dados de Zoneamento',
                                                     'Base de Dados Sigef'])
        self.assertEqual(rows[0]['atualizada_em'], '29/10/2026 21:00')
        self.assertIn('não registrada', rows[1]['observacao'])
        self.assertIn('envio do arquivo', rows[2]['observacao'])
        self.assertIn('Geoportal', rows[1]['fonte'])
        self.assertEqual(newer, ['Base de Embargos do IBAMA'])

    def test_report_has_location_update_dates_and_pdf_link(self):
        ctx = {
            'resultado': {'tamanho_area': 1000}, 'bases_com_ocorrencia': [], 'bases_so_residuais': [],
            'bases_sem_ocorrencia': [], 'limite_residual': 0.1, 'checklist': [], 'n_alertas': 0, 'n_atencao': 0,
            'veredito': 'ok', 'biomas': [], 'municipios_encontrados': ['Palmas'], 'uso_solo': {'erro': 'sem rede'},
            'reserva_legal': {'exigida': 0, 'declarada_txt': None, 'deficit': 0, 'tem_deficit': False, 'avaliada': False},
            'localizacao': {'lat': '-10,21500', 'lon': '-48,34500', 'maps_url': 'https://maps.example'},
        }
        newer_update = {'Embargoes': (datetime(2026, 10, 30, tzinfo=timezone.utc), 'importacao')}
        with patch.object(queries, 'load_analysis', return_value=(_history(), _data())), \
                patch.object(queries, 'build_report_context', return_value=ctx), \
                patch.object(queries, 'layer_update_dates', return_value=newer_update):
            report = queries.analysis_report(SimpleNamespace(pk=5), 7)

        self.assertEqual(report['localizacao'], {'latitude': -10.215, 'longitude': -48.345,
                                                 'google_maps': 'https://maps.example'})
        self.assertIn('/conector/arquivos/', report['links']['relatorio_pdf'])
        self.assertIn('Base de Embargos do IBAMA', report['aviso_bases_atualizadas'])
        schemas.Relatorio.model_validate(report)


# ---------------------------------------------------------------------------
# Envio de arquivos pelo link
# ---------------------------------------------------------------------------

def _upload(**fields):
    defaults = dict(pk=1, code='abc', kind=McpUpload.Kind.AREA, label='', status=McpUpload.Status.PENDING,
                    filename='', analysis_id=None, error='', created_at=datetime.now(timezone.utc),
                    user=SimpleNamespace(pk=5, is_active=True, get_username=lambda: 'marina'),
                    get_kind_display=lambda: 'Área (shapefile, KML/KMZ ou GeoJSON)', save=MagicMock())
    defaults.update(fields)
    return SimpleNamespace(**defaults)


@override_settings(MCP_PUBLIC_BASE_URL='https://plataforma.example', MCP_UPLOAD_LINK_MAX_AGE=3600)
class UploadTests(SimpleTestCase):
    def test_link_is_created_for_the_user(self):
        with patch.object(uploads.McpUpload.objects, 'create', side_effect=lambda **kw: SimpleNamespace(**kw)):
            link = uploads.create_upload(SimpleNamespace(pk=5), 'recibo', 'Fazenda')

        self.assertTrue(link['link_envio'].startswith('https://plataforma.example/conector/enviar/'))
        self.assertIn(link['codigo'], link['link_envio'])
        self.assertIn('60 minutos', link['validade'])
        schemas.LinkEnvio.model_validate(link)
        with self.assertRaisesMessage(queries.QueryError, 'Tipo inválido'):
            uploads.create_upload(SimpleNamespace(pk=5), 'foto')

    def test_result_follows_the_upload_status(self):
        user = SimpleNamespace(pk=5)
        old = datetime.now(timezone.utc) - timedelta(hours=2)
        cases = [
            (_upload(), 'aguardando'),
            (_upload(created_at=old), 'expirado'),
            (_upload(status=McpUpload.Status.PROCESSING), 'processando'),
            (_upload(status=McpUpload.Status.ERROR, error='Arquivo sem polígono.'), 'erro'),
        ]
        for upload, expected in cases:
            with self.subTest(expected=expected), \
                    patch.object(uploads.McpUpload.objects, 'filter') as found:
                found.return_value.first.return_value = upload
                self.assertEqual(uploads.upload_result(user, 'abc')['situacao'], expected)

        done = _upload(status=McpUpload.Status.DONE, analysis_id=7, filename='area.zip')
        with patch.object(uploads.McpUpload.objects, 'filter') as found, \
                patch.object(queries, 'load_analysis', return_value=(_history(), _data())):
            found.return_value.first.return_value = done
            result = uploads.upload_result(user, 'abc')
        self.assertEqual(result['analise']['analise_id'], 7)
        schemas.ResultadoEnvio.model_validate(result)

    def test_processing_records_the_analysis_or_the_error(self):
        file_obj = SimpleUploadedFile('area.kml', b'<kml/>')
        with patch.object(uploads.McpUpload.objects, 'filter') as claim, \
                patch.object(uploads.McpAuditLog.objects, 'create') as audit:
            claim.return_value.update.return_value = 1
            with patch.object(queries, 'analyze_area_file', return_value={'analise_id': 9}):
                ok = uploads.process_upload(_upload(), file_obj)
            with patch.object(queries, 'analyze_area_file', side_effect=queries.QueryError('Sem polígono.')):
                failed = uploads.process_upload(_upload(), file_obj)
            claim.return_value.update.return_value = 0
            with self.assertRaisesMessage(queries.QueryError, 'já está sendo usado'):
                uploads.process_upload(_upload(), file_obj)

        self.assertEqual((ok.status, ok.analysis_id, ok.filename), (McpUpload.Status.DONE, 9, 'area.kml'))
        self.assertEqual((failed.status, failed.error), (McpUpload.Status.ERROR, 'Sem polígono.'))
        self.assertEqual([c.kwargs['success'] for c in audit.call_args_list], [True, False])

    def test_upload_page_shows_the_form_processes_and_refuses_closed_links(self):
        upload = _upload()
        with patch.object(uploads, 'open_upload', return_value=upload):
            form = self.client.get('/conector/enviar/abc/')
            with patch.object(uploads, 'process_upload',
                              return_value=_upload(status=McpUpload.Status.DONE, analysis_id=9, filename='area.kml')) as process:
                sent = self.client.post('/conector/enviar/abc/', {'arquivo': SimpleUploadedFile('area.kml', b'<kml/>')})
        with patch.object(uploads, 'open_upload', return_value=None), \
                patch('mcp_connector.views.McpUpload.objects.filter') as done:
            done.return_value.first.return_value = None
            closed = self.client.get('/conector/enviar/abc/')

        self.assertContains(form, 'Enviar e analisar')
        self.assertContains(form, 'accept=".zip,.kml,.kmz,.geojson,.json"')
        self.assertEqual(process.call_args.args[1].name, 'area.kml')
        self.assertContains(sent, 'análise nº <strong>9</strong>')
        self.assertEqual(closed.status_code, 410)


# ---------------------------------------------------------------------------
# OAuth e servidor MCP
# ---------------------------------------------------------------------------

@override_settings(MCP_ALLOWED_REDIRECT_URIS=[
    'https://claude.ai/api/mcp/auth_callback', 'https://chatgpt.com/connector/oauth/*',
])
class OAuthTests(SimpleTestCase):
    def test_only_assistant_callbacks_are_accepted(self):
        self.assertTrue(_redirect_allowed('https://claude.ai/api/mcp/auth_callback'))
        self.assertTrue(_redirect_allowed('https://chatgpt.com/connector/oauth/abc123'))
        for uri in (
            'https://site-qualquer.example/callback',
            'https://chatgpt.com/connector/oauth/',
            'https://chatgpt.com/connector/oauth/abc/outro',
            'https://chatgpt.com/connector/oauth/abc?x=https://site.example',
            'https://chatgpt.com.site.example/connector/oauth/abc',
        ):
            self.assertFalse(_redirect_allowed(uri), uri)

    def test_loopback_only_when_allowed(self):
        with override_settings(MCP_ALLOW_LOOPBACK_REDIRECTS=True):
            self.assertTrue(_redirect_allowed('http://localhost:53682/callback'))
        with override_settings(MCP_ALLOW_LOOPBACK_REDIRECTS=False):
            self.assertFalse(_redirect_allowed('http://localhost:53682/callback'))

    @override_settings(MCP_PUBLIC_BASE_URL='https://plataforma.example')
    def test_metadata_is_public(self):
        response = self.client.get('/.well-known/oauth-authorization-server')

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['issuer'], 'https://plataforma.example/')
        self.assertEqual(data['registration_endpoint'], 'https://plataforma.example/o/register/')
        self.assertEqual(data['scopes_supported'], ['analises'])


def _summary_dict(pk=9):
    return {'analise_id': pk, 'data': '24/10/2026 12:00', 'tipo': 'Número do CAR', 'total_sobreposicoes': 0}


@override_settings(MCP_PUBLIC_BASE_URL='http://localhost:8000', MCP_RESOURCE_URL='http://localhost:8002/mcp')
class McpServerTests(SimpleTestCase):
    """Chamadas reais ao endpoint /mcp, com o token e o banco substituídos."""

    def setUp(self):
        token = AccessToken(token='bom', client_id='claude', scopes=['analises'], expires_at=None, subject='5')
        patches = [
            patch('mcp_connector.server._lookup_token', side_effect=lambda t: token if t == 'bom' else None),
            patch('mcp_connector.server.get_user_model'),
            patch('mcp_connector.server.McpAuditLog'),
            patch('mcp_connector.server.close_old_connections'),
        ]
        mocks = [p.start() for p in patches]
        for p in patches:
            self.addCleanup(p.stop)
        self.user = SimpleNamespace(pk=5, username='marina')
        mocks[1].return_value.objects.filter.return_value.first.return_value = self.user
        self.audit = mocks[2]

    def _post(self, client, method, params=None, token='bom'):
        return client.post('/mcp', json={'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params or {}},
                           headers={'Authorization': f'Bearer {token}', 'Accept': 'application/json, text/event-stream'})

    @staticmethod
    def _messages(response):
        """Mensagens JSON-RPC da resposta em SSE."""
        return [json.loads(line[5:]) for line in response.text.splitlines() if line.startswith('data:')]

    def _result(self, response):
        return next(m for m in self._messages(response) if m.get('id') == 1)['result']

    def _client(self):
        return TestClient(build_server().streamable_http_app(), base_url='http://localhost:8002')

    def test_lists_the_tools_with_output_schemas_and_refuses_bad_tokens(self):
        with self._client() as client:
            unauthorized = self._post(client, 'tools/list', token='errado')
            tools = self._result(self._post(client, 'tools/list'))['tools']

        self.assertEqual(unauthorized.status_code, 401)
        by_name = {tool['name']: tool for tool in tools}
        self.assertEqual(set(by_name), {
            'analisar_car', 'analisar_coordenadas', 'analisar_geometria', 'analisar_parcela_sigef',
            'link_envio', 'resultado_envio', 'localizar_ponto', 'listar_analises', 'detalhes_analise',
            'relatorio_analise', 'arquivos_analise', 'mapa_analise', 'imagem_historica', 'mapa_uso_solo',
        })
        self.assertTrue(by_name['relatorio_analise']['annotations']['readOnlyHint'])
        self.assertFalse(by_name['analisar_car']['annotations']['readOnlyHint'])
        self.assertIn('analise_id', by_name['analisar_car']['outputSchema']['properties'])
        self.assertIn('atualizacao_das_bases', json.dumps(by_name['relatorio_analise']['outputSchema']))
        self.assertNotIn('ctx', by_name['analisar_car']['inputSchema']['properties'])
        self.assertIn('forcar_nova', by_name['analisar_car']['inputSchema']['properties'])
        self.assertNotIn('outputSchema', by_name['imagem_historica'])

    def test_tool_runs_as_the_token_owner_and_errors_are_audited(self):
        with patch.object(queries, 'analyze_car', return_value=_summary_dict()) as analyze, \
                patch.object(queries, 'analysis_report', side_effect=queries.QueryError('Análise 3 não encontrada')):
            with self._client() as client:
                ok = self._post(client, 'tools/call', {'name': 'analisar_car', 'arguments': {'numero_car': 'TO-1'}})
                denied = self._post(client, 'tools/call', {'name': 'relatorio_analise', 'arguments': {'analise_id': 3}})

        result = self._result(ok)
        self.assertFalse(result['isError'])
        self.assertEqual(json.loads(result['content'][0]['text'])['analise_id'], 9)
        self.assertEqual(result['structuredContent']['analise_id'], 9)
        self.assertEqual(analyze.call_args.args, (self.user,))
        self.assertEqual(analyze.call_args.kwargs['car_number'], 'TO-1')
        self.assertFalse(analyze.call_args.kwargs['forcar_nova'])
        self.assertIsInstance(analyze.call_args.kwargs['progress'], queries.ToolProgress)
        self.assertTrue(self._result(denied)['isError'])
        self.assertIn('não encontrada', self._result(denied)['content'][0]['text'])
        calls = [(c.kwargs['tool'], c.kwargs.get('success', True)) for c in self.audit.objects.create.call_args_list]
        self.assertEqual(calls, [('analisar_car', True), ('relatorio_analise', False)])
        self.assertNotIn('progress', self.audit.objects.create.call_args_list[0].kwargs['arguments'])

    def test_analysis_progress_is_sent_to_the_assistant(self):
        def analyze(user, car_number, forcar_nova, progress):
            progress.layers([type('Embargoes', (), {})])
            progress.stage('Montando o resultado')
            return _summary_dict()

        with patch.object(queries, 'analyze_car', side_effect=analyze):
            with self._client() as client:
                response = self._post(client, 'tools/call', {
                    'name': 'analisar_car', 'arguments': {'numero_car': 'TO-1'}, '_meta': {'progressToken': 'p1'},
                })

        notes = [m for m in self._messages(response) if m.get('method') == 'notifications/progress']
        self.assertTrue(notes)
        self.assertEqual(notes[-1]['params']['progressToken'], 'p1')
        self.assertIn('Montando o resultado', [n['params'].get('message') for n in notes])
        self.assertFalse(self._result(response)['isError'])

    def test_map_tool_returns_the_image_and_its_source(self):
        info = {'analise_id': 9, 'link_png': 'x', 'fonte_imagem': {'descricao': 'WorldView-2, 12/06/2021'}}
        with patch.object(exports, 'analysis_map', return_value=(_png(), info)):
            with self._client() as client:
                response = self._post(client, 'tools/call', {'name': 'mapa_analise', 'arguments': {'analise_id': 9}})

        content = self._result(response)['content']
        self.assertEqual(json.loads(content[0]['text'])['fonte_imagem']['descricao'], 'WorldView-2, 12/06/2021')
        self.assertEqual((content[1]['type'], content[1]['mimeType']), ('image', 'image/jpeg'))

    def test_historical_image_tool_returns_both_images(self):
        results = [(_png(), {'analise_id': 9, 'fonte_imagem': {'satelite': 'Landsat 5'}}),
                   (_png(), {'analise_id': 9, 'fonte_imagem': {'satelite': 'WorldView-2'}})]
        with patch.object(exports, 'historical_images', return_value=results) as historical:
            with self._client() as client:
                response = self._post(client, 'tools/call', {
                    'name': 'imagem_historica', 'arguments': {'analise_id': 9, 'composicao': 'falsa_cor'},
                })

        content = self._result(response)['content']
        self.assertEqual([c['type'] for c in content], ['text', 'image', 'text', 'image'])
        self.assertEqual(historical.call_args.kwargs['ano'], 2008)
        self.assertEqual(historical.call_args.kwargs['composicao'], 'falsa_cor')

    def test_upload_tools_go_through(self):
        link = {'codigo': 'abc', 'link_envio': 'http://x/enviar/abc/', 'aceita': 'KML', 'validade': '1 h',
                'proximo_passo': 'Mostre o link.'}
        with patch.object(uploads, 'create_upload', return_value=link) as create, \
                patch.object(uploads, 'upload_result', return_value={'codigo': 'abc', 'situacao': 'aguardando'}):
            with self._client() as client:
                created = self._post(client, 'tools/call', {'name': 'link_envio', 'arguments': {'tipo': 'recibo'}})
                waiting = self._post(client, 'tools/call', {'name': 'resultado_envio', 'arguments': {'codigo': 'abc'}})

        self.assertEqual(self._result(created)['structuredContent']['codigo'], 'abc')
        self.assertEqual(create.call_args.kwargs, {'kind': 'recibo', 'label': None})
        self.assertEqual(self._result(waiting)['structuredContent']['situacao'], 'aguardando')

    def test_prompts_are_listed_and_filled(self):
        with self._client() as client:
            prompts = self._result(self._post(client, 'prompts/list'))['prompts']
            filled = self._result(self._post(client, 'prompts/get', {
                'name': 'parecer_para_banco', 'arguments': {'area': 'TO-1721000-ABC'},
            }))

        self.assertEqual({p['name'] for p in prompts}, {
            'parecer_para_banco', 'due_diligence_compra', 'checklist_codigo_florestal', 'resumo_para_cliente',
        })
        text = filled['messages'][0]['content']['text']
        self.assertIn('TO-1721000-ABC', text)
        self.assertIn('fonte_imagem', text)

    def test_long_arguments_are_cut_in_the_audit(self):
        audit = _audit_arguments({'geometry_text': 'x' * 5000, 'label': 'Fazenda'})
        self.assertIn('5000 caracteres', audit['geometry_text'])
        self.assertEqual(audit['label'], 'Fazenda')
