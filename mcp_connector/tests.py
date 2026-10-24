"""Testes do conector MCP sem banco de dados.

O banco local é o de produção (via túnel), então, como nos testes de
`analysis`, tudo que tocaria o banco é substituído por dublês.
"""
import io
import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch
from xml.etree import ElementTree as ET

from django.core import signing
from django.test import SimpleTestCase, override_settings
from mcp.server.auth.provider import AccessToken
from PIL import Image
from starlette.testclient import TestClient

from analysis.models import SearchHistory

from . import exports, queries, static_map
from .oauth_views import _redirect_allowed
from .server import _audit_arguments, build_server

PROPERTY_WKT = 'POLYGON ((-48.36 -10.2, -48.33 -10.2, -48.33 -10.23, -48.36 -10.23, -48.36 -10.2))'
EMBARGO_WKT = 'POLYGON ((-48.36 -10.2, -48.35 -10.2, -48.35 -10.21, -48.36 -10.21, -48.36 -10.2))'


def _geojson(wkt):
    from shapely import wkt as shapely_wkt
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

    def test_render_without_network(self):
        tile = Image.new('RGB', (256, 256), (40, 90, 40))
        with patch.object(static_map, '_fetch_tile', return_value=tile):
            png = static_map.render_map(_geojson(PROPERTY_WKT), exports.map_layers(_data()['resultado'])[0], 'Título',
                                        notes=['Cobrem toda a área (não pintadas): APA.'])

        image = Image.open(io.BytesIO(png))
        self.assertEqual(image.size, (static_map.WIDTH, static_map.HEIGHT))
        self.assertEqual(Image.open(io.BytesIO(static_map.to_jpeg(png))).format, 'JPEG')

    def test_render_fails_clearly_without_tiles(self):
        with patch.object(static_map, '_fetch_tile', return_value=None), \
                self.assertRaisesMessage(static_map.MapRenderError, 'não respondeu'):
            static_map.render_map(_geojson(PROPERTY_WKT), [], 'Título')


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
        url = exports.file_url(user, 7, 'base', 'kml', base='Base de Embargos do IBAMA')

        self.assertTrue(url.startswith('https://plataforma.example/conector/arquivos/'))
        token = url.rstrip('/').rsplit('/', 1)[1]
        self.assertEqual(exports.read_token(token)['b'], 'Base de Embargos do IBAMA')
        with self.assertRaises(signing.BadSignature):
            exports.read_token(token[:-2] + 'xx')
        with override_settings(MCP_FILE_LINK_MAX_AGE=-1), self.assertRaises(signing.SignatureExpired):
            exports.read_token(token)

    @override_settings(MCP_PUBLIC_BASE_URL='https://plataforma.example')
    def test_download_view_serves_the_file_of_a_valid_link(self):
        token = exports.file_url(SimpleNamespace(pk=5), 7, 'imovel', 'kml').rstrip('/').rsplit('/', 1)[1]
        user = SimpleNamespace(pk=5)
        with patch('mcp_connector.views.get_user_model') as model, \
                patch('mcp_connector.views.build_file', return_value=(b'<kml/>', 'propriedade.kml', 'application/vnd.google-earth.kml+xml')) as build:
            model.return_value.objects.filter.return_value.first.return_value = user
            response = self.client.get(f'/conector/arquivos/{token}/')
            expired = None
            with override_settings(MCP_FILE_LINK_MAX_AGE=-1):
                expired = self.client.get(f'/conector/arquivos/{token}/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Disposition'], 'attachment; filename="propriedade.kml"')
        self.assertEqual(build.call_args.args[1]['k'], 'imovel')
        self.assertEqual(expired.status_code, 410)
        self.assertEqual(self.client.get('/conector/arquivos/adulterado/').status_code, 404)


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

    def _client(self):
        return TestClient(build_server().streamable_http_app(), base_url='http://localhost:8002')

    def test_lists_the_tools_and_refuses_bad_tokens(self):
        with self._client() as client:
            unauthorized = self._post(client, 'tools/list', token='errado')
            tools = self._post(client, 'tools/list').json()['result']['tools']

        self.assertEqual(unauthorized.status_code, 401)
        names = {tool['name'] for tool in tools}
        self.assertEqual(names, {
            'analisar_car', 'analisar_coordenadas', 'analisar_geometria', 'analisar_parcela_sigef',
            'localizar_ponto', 'listar_analises', 'detalhes_analise', 'relatorio_analise', 'mapa_analise',
            'arquivos_analise',
        })
        by_name = {tool['name']: tool for tool in tools}
        self.assertTrue(by_name['relatorio_analise']['annotations']['readOnlyHint'])
        self.assertFalse(by_name['analisar_car']['annotations']['readOnlyHint'])

    def test_tool_runs_as_the_token_owner_and_errors_are_audited(self):
        with patch.object(queries, 'analyze_car', return_value={'analise_id': 9}) as analyze, \
                patch.object(queries, 'analysis_report', side_effect=queries.QueryError('Análise 3 não encontrada')):
            with self._client() as client:
                ok = self._post(client, 'tools/call', {'name': 'analisar_car', 'arguments': {'numero_car': 'TO-1'}})
                denied = self._post(client, 'tools/call', {'name': 'relatorio_analise', 'arguments': {'analise_id': 3}})

        result = ok.json()['result']
        self.assertFalse(result['isError'])
        self.assertEqual(json.loads(result['content'][0]['text']), {'analise_id': 9})
        analyze.assert_called_once_with(self.user, car_number='TO-1')
        self.assertTrue(denied.json()['result']['isError'])
        self.assertIn('não encontrada', denied.json()['result']['content'][0]['text'])
        calls = [(c.kwargs['tool'], c.kwargs.get('success', True)) for c in self.audit.objects.create.call_args_list]
        self.assertEqual(calls, [('analisar_car', True), ('relatorio_analise', False)])

    def test_map_tool_returns_the_image(self):
        png = io.BytesIO()
        Image.new('RGB', (10, 10)).save(png, format='PNG')
        with patch.object(exports, 'analysis_map', return_value=(png.getvalue(), {'analise_id': 9, 'link_png': 'x'})):
            with self._client() as client:
                response = self._post(client, 'tools/call', {'name': 'mapa_analise', 'arguments': {'analise_id': 9}})

        content = response.json()['result']['content']
        self.assertEqual(json.loads(content[0]['text'])['link_png'], 'x')
        self.assertEqual((content[1]['type'], content[1]['mimeType']), ('image', 'image/jpeg'))

    def test_long_arguments_are_cut_in_the_audit(self):
        audit = _audit_arguments({'geometry_text': 'x' * 5000, 'label': 'Fazenda'})
        self.assertIn('5000 caracteres', audit['geometry_text'])
        self.assertEqual(audit['label'], 'Fazenda')
