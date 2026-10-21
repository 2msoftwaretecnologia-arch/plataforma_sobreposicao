import io
import json
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlsplit

from django.core.cache import cache
from django.template.loader import render_to_string
from django.test import SimpleTestCase, override_settings

import numpy as np
from PIL import Image

from analysis.services.view_services import imagery_service as svc
from analysis.services.view_services import raster_tiles as rt
from analysis.services.view_services import land_use_service as lu
from analysis.services.view_services import report_service

WMS_CAPABILITIES = b"""<?xml version="1.0"?>
<WMS_Capabilities version="1.3.0" xmlns="http://www.opengis.net/wms">
  <Capability>
    <Request><GetMap><Format>image/jpeg</Format><Format>image/png</Format></GetMap></Request>
    <Layer>
      <Title>Grupo</Title>
      <Layer><Name>TRUE_COLOR</Name><Title>Cor verdadeira</Title></Layer>
      <Layer><Name>NDVI</Name><Title>NDVI</Title></Layer>
    </Layer>
  </Capability>
</WMS_Capabilities>"""

WMTS_CAPABILITIES = b"""<?xml version="1.0"?>
<Capabilities xmlns="http://www.opengis.net/wmts/1.0" xmlns:ows="http://www.opengis.net/ows/1.1" version="1.0.0">
  <Contents>
    <Layer>
      <ows:Title>Global Monthly 2026-09</ows:Title>
      <ows:Identifier>global_monthly_2026_09_mosaic</ows:Identifier>
      <Style isDefault="true"><ows:Identifier>default</ows:Identifier></Style>
      <Format>image/png</Format>
      <TileMatrixSetLink><TileMatrixSet>GoogleMapsCompatible15</TileMatrixSet></TileMatrixSetLink>
      <ResourceURL format="image/png" resourceType="tile"
        template="https://tiles.planet.com/basemaps/v1/planet-tiles/global_monthly_2026_09_mosaic/gmap/{TileMatrix}/{TileCol}/{TileRow}.png?api_key=SEGREDO"/>
    </Layer>
    <Layer>
      <ows:Title>Fora de Web Mercator</ows:Title>
      <ows:Identifier>utm</ows:Identifier>
      <TileMatrixSetLink><TileMatrixSet>UTM22S</TileMatrixSet></TileMatrixSetLink>
    </Layer>
    <TileMatrixSet>
      <ows:Identifier>GoogleMapsCompatible15</ows:Identifier>
      <ows:SupportedCRS>urn:ogc:def:crs:EPSG:6.18:3:3857</ows:SupportedCRS>
      <TileMatrix><ows:Identifier>0</ows:Identifier></TileMatrix>
      <TileMatrix><ows:Identifier>1</ows:Identifier></TileMatrix>
      <TileMatrix><ows:Identifier>2</ows:Identifier></TileMatrix>
    </TileMatrixSet>
    <TileMatrixSet>
      <ows:Identifier>UTM22S</ows:Identifier>
      <ows:SupportedCRS>urn:ogc:def:crs:EPSG::31982</ows:SupportedCRS>
    </TileMatrixSet>
  </Contents>
</Capabilities>"""


def http_response(status=200, content=b'', content_type='image/png', json=None):
    response = Mock(status_code=status, content=content, headers={'Content-Type': content_type})
    response.json.return_value = json
    return response


class ImageryServiceTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def test_tile_bbox_covers_world_at_zoom_zero(self):
        minx, miny, maxx, maxy = svc.tile_bbox(0, 0, 0)
        self.assertAlmostEqual(minx, -svc.WEB_MERCATOR_HALF)
        self.assertAlmostEqual(maxy, svc.WEB_MERCATOR_HALF)
        self.assertAlmostEqual(maxx, svc.WEB_MERCATOR_HALF)
        self.assertAlmostEqual(miny, -svc.WEB_MERCATOR_HALF)
        # Zoom 1, tile (1, 1): quadrante sudeste.
        self.assertEqual(svc.tile_bbox(1, 1, 1), (0.0, -svc.WEB_MERCATOR_HALF, svc.WEB_MERCATOR_HALF, 0.0))

    def test_link_keeps_key_and_drops_ogc_params(self):
        base, extra, service = svc._split_url(
            'https://services.example.com/ogc/wms/abc?SERVICE=WMS&REQUEST=GetCapabilities&api_key=K')
        self.assertEqual(base, 'https://services.example.com/ogc/wms/abc')
        self.assertEqual(extra, [('api_key', 'K')])
        self.assertEqual(service, 'WMS')

    def test_rest_wmts_link_asks_capabilities_without_kvp(self):
        params = svc._capabilities_params('https://api.planet.com/basemaps/v1/mosaics/wmts', [('api_key', 'K')], '')
        self.assertEqual(params, [('api_key', 'K')])
        params = svc._capabilities_params('https://x/ogc/wms/abc', [], '')
        self.assertIn(('REQUEST', 'GetCapabilities'), params)

    def test_parse_wms_lists_named_layers_and_prefers_png(self):
        caps = svc.parse_capabilities(WMS_CAPABILITIES, 'https://x/wms', [('key', 'K')])
        self.assertEqual(caps['kind'], 'wms')
        self.assertEqual(caps['format'], 'image/png')
        self.assertEqual(list(caps['layers']), ['TRUE_COLOR', 'NDVI'])

    def test_parse_wmts_skips_layers_outside_web_mercator(self):
        caps = svc.parse_capabilities(WMTS_CAPABILITIES, 'https://x/wmts', [])
        self.assertEqual(list(caps['layers']), ['global_monthly_2026_09_mosaic'])
        layer = caps['layers']['global_monthly_2026_09_mosaic']
        self.assertEqual(layer['matrices'], ['0', '1', '2'])

    @override_settings(PLANET_WMS_URL='', PLANET_API_KEY='K')
    @patch.object(svc, '_http')
    def test_wmts_layers_report_max_zoom(self, http):
        http.get.return_value = http_response(content=WMTS_CAPABILITIES, content_type='text/xml')
        self.assertEqual(svc.provider_layers('planet'), [
            {'id': 'global_monthly_2026_09_mosaic', 'title': 'Global Monthly 2026-09', 'max_zoom': 2}])

    @override_settings(PLANET_WMS_URL='https://x/ogc/wms/abc?api_key=K', PLANET_API_KEY='')
    @patch.object(svc, '_http')
    def test_wms_tile_builds_getmap_with_key(self, http):
        http.get.side_effect = [http_response(content=WMS_CAPABILITIES, content_type='text/xml'),
                                http_response(content=b'PNG')]
        self.assertEqual(svc.provider_tile('planet', 'TRUE_COLOR', 1, 1, 1), (b'PNG', 'image/png'))
        params = dict(http.get.call_args.kwargs['params'])
        self.assertEqual(params['api_key'], 'K')
        self.assertEqual(params['REQUEST'], 'GetMap')
        self.assertEqual(params['LAYERS'], 'TRUE_COLOR')
        self.assertEqual(params['CRS'], 'EPSG:3857')
        self.assertEqual(params['WIDTH'], '256')

    @override_settings(PLANET_WMS_URL='', PLANET_API_KEY='K')
    @patch.object(svc, '_http')
    def test_wmts_tile_fills_template(self, http):
        http.get.side_effect = [http_response(content=WMTS_CAPABILITIES, content_type='text/xml'),
                                http_response(content=b'PNG')]
        svc.provider_tile('planet', 'global_monthly_2026_09_mosaic', 2, 3, 1)
        url = http.get.call_args.args[0]
        self.assertTrue(url.startswith('https://tiles.planet.com/basemaps/v1/planet-tiles/global_monthly_2026_09_mosaic/gmap/2/3/1.png'))
        self.assertEqual(parse_qs(urlsplit(url).query)['api_key'], ['SEGREDO'])
        # Primeira chamada (capabilities) foi ao WMTS da conta.
        self.assertEqual(http.get.call_args_list[0].args[0], svc.PLANET_WMTS_URL)

    @override_settings(PLANET_WMS_URL='', PLANET_API_KEY='K')
    @patch.object(svc, '_http')
    def test_zoom_beyond_matrix_set_and_unknown_layer_have_no_tile(self, http):
        http.get.return_value = http_response(content=WMTS_CAPABILITIES, content_type='text/xml')
        self.assertIsNone(svc.provider_tile('planet', 'global_monthly_2026_09_mosaic', 5, 0, 0))
        self.assertIsNone(svc.provider_tile('planet', 'nao_existe', 1, 0, 0))

    @override_settings(PLANET_WMS_URL='https://x/ogc/wms/abc?api_key=K', PLANET_API_KEY='')
    @patch.object(svc, '_http')
    def test_wms_xml_error_is_not_served_as_image(self, http):
        http.get.side_effect = [http_response(content=WMS_CAPABILITIES, content_type='text/xml'),
                                http_response(content=b'<ServiceException/>', content_type='text/xml')]
        with self.assertRaises(svc.ImageryError):
            svc.provider_tile('planet', 'TRUE_COLOR', 1, 0, 0)

    @override_settings(PLANET_WMS_URL='https://x/ogc/wms/abc?api_key=K', PLANET_API_KEY='')
    @patch.object(svc, '_http')
    def test_connection_error_message_hides_key(self, http):
        import requests
        http.get.side_effect = requests.ConnectionError('https://x/ogc/wms/abc?api_key=K')
        with self.assertRaises(svc.ImageryError) as ctx:
            svc.provider_layers('planet')
        self.assertNotIn('api_key', str(ctx.exception))
        self.assertIsNone(ctx.exception.__cause__)

    @override_settings(GOOGLE_MAPS_API_KEY='G')
    @patch.object(svc, '_http')
    def test_google_renews_session_when_rejected(self, http):
        http.post.side_effect = [http_response(json={'session': 'S1', 'expiry': '9999999999'}),
                                 http_response(json={'session': 'S2', 'expiry': '9999999999'})]
        http.get.side_effect = [http_response(status=403, content_type='application/json'),
                                http_response(content=b'JPG', content_type='image/jpeg')]
        self.assertEqual(svc.google_tile(3, 2, 1), (b'JPG', 'image/jpeg'))
        self.assertEqual(http.get.call_args.kwargs['params'], {'session': 'S2', 'key': 'G'})
        self.assertEqual(http.post.call_args.kwargs['json']['mapType'], 'satellite')

    @patch.object(svc, '_http')
    def test_wayback_releases_sorted_newest_first(self, http):
        http.get.return_value = http_response(json={
            '1': {'itemTitle': 'World Imagery (Wayback 2014-02-20)', 'metadataLayerUrl': 'https://m/2014'},
            '63116': {'itemTitle': 'World Imagery (Wayback 2026-09-24)', 'metadataLayerUrl': 'https://m/2026'},
            '9': {'itemTitle': 'sem data'},
        })
        self.assertEqual(svc.wayback_releases(), [
            {'id': 63116, 'date': '2026-09-24', 'metadata_url': 'https://m/2026'},
            {'id': 1, 'date': '2014-02-20', 'metadata_url': 'https://m/2014'},
        ])

    @override_settings(PLANET_WMS_URL='', PLANET_API_KEY='', COPERNICUS_WMS_URL='', GOOGLE_MAPS_API_KEY='')
    def test_config_without_keys_only_offers_public_sources(self):
        config = svc.imagery_config()
        self.assertEqual(config['providers'], [])
        self.assertEqual(set(config), {'wayback_tile_url', 'wayback_releases_url', 'providers', 'mapbiomas', 'cbers',
                                       'landsat_legacy'})
        self.assertTrue(config['landsat_legacy']['tile_url'].endswith('/imagens/landsat-antigo/{scene}/{comp}/{z}/{x}/{y}.png'))

    @patch.object(svc, '_http')
    def test_landsat_legacy_keeps_least_cloudy_per_year_and_avoids_slc_off(self, http):
        def feature(scene_id, date, platform, cloud):
            return {'id': scene_id, 'properties': {'datetime': date + 'T13:00:00Z', 'platform': platform, 'eo:cloud_cover': cloud}}
        scenes = [feature(f'LT05_L2SP_222067_200807{d:02d}_02_T1', f'2008-07-{d:02d}', 'landsat-5', d) for d in range(1, 8)]
        scenes += [
            # Landsat 7 sem nuvem, mas com as faixas do SLC: perde para o L5.
            feature('LE07_L2SP_222067_20080830_02_T1', '2008-08-30', 'landsat-7', 0),
            feature('LT05_L2SP_222067_19950610_02_T1', '1995-06-10', 'landsat-5', 3),
            feature('nao-landsat', '2008-01-01', 'landsat-5', 0),
        ]
        http.post.return_value = http_response(json={'features': scenes, 'links': []})
        result = svc.landsat_legacy_scenes(-48.36, -10.24)
        self.assertEqual([s['date'] for s in result],
                         ['2008-07-05', '2008-07-04', '2008-07-03', '2008-07-02', '2008-07-01', '1995-06-10'])
        body = http.post.call_args.kwargs['json']
        self.assertEqual(body['query']['platform']['in'], ['landsat-4', 'landsat-5', 'landsat-7'])
        self.assertTrue(body['datetime'].startswith('1984-01-01'))

    @patch.object(svc, '_http')
    def test_landsat_legacy_tile_validates_scene_and_composition(self, http):
        http.get.return_value = http_response(content=b'PNG')
        self.assertIsNone(svc.landsat_legacy_tile('../../etc', 'natural', 12, 1, 1))
        self.assertIsNone(svc.landsat_legacy_tile('LT05_L2SP_222067_20080722_02_T1', 'nao_existe', 12, 1, 1))
        self.assertIsNone(svc.landsat_legacy_tile('LT05_L2SP_222067_20080722_02_T1', 'natural', 18, 1, 1))
        http.get.assert_not_called()
        self.assertEqual(svc.landsat_legacy_tile('LT05_L2SP_222067_20080722_02_T1', 'falsa_cor', 12, 1497, 2163), (b'PNG', 'image/png'))
        params = http.get.call_args.kwargs['params']
        self.assertIn(('item', 'LT05_L2SP_222067_20080722_02_T1'), params)
        self.assertEqual([v for k, v in params if k == 'assets'], ['nir08', 'red', 'green'])

    @override_settings(PLANET_WMS_URL='https://x/wms?key=SEGREDO', COPERNICUS_WMS_URL='https://c/ogc/wms/CSEGREDO',
                       GOOGLE_MAPS_API_KEY='GSEGREDO')
    def test_config_uses_proxy_urls_and_never_the_keys(self):
        config = svc.imagery_config()
        providers = {p['key']: p for p in config['providers']}
        self.assertEqual(set(providers), {'planet', 'copernicus'})
        self.assertTrue(providers['planet']['tile_url'].endswith('/imagens/planet/{layer}/{z}/{x}/{y}'))
        self.assertTrue(providers['copernicus']['tile_url'].endswith('/imagens/copernicus/{layer}/{z}/{x}/{y}'))
        self.assertTrue(providers['copernicus']['layers_url'].endswith('/imagens/copernicus/camadas/'))
        self.assertTrue(config['google_tile_url'].endswith('/imagens/google/{z}/{x}/{y}'))
        self.assertNotIn('SEGREDO', str(config))

    @override_settings(PLANET_WMS_URL='', PLANET_API_KEY='', COPERNICUS_WMS_URL='https://c/ogc/wms/INST?MAXCC=20')
    @patch.object(svc, '_http')
    def test_copernicus_link_params_pass_to_tiles_and_cache_is_per_provider(self, http):
        http.get.side_effect = [http_response(content=WMS_CAPABILITIES, content_type='text/xml'),
                                http_response(content=b'PNG')]
        self.assertEqual(svc.provider_tile('copernicus', 'NDVI', 3, 2, 1), (b'PNG', 'image/png'))
        self.assertEqual(http.get.call_args.args[0], 'https://c/ogc/wms/INST')
        self.assertEqual(dict(http.get.call_args.kwargs['params'])['MAXCC'], '20')
        # Capabilities da Copernicus não servem para a Planet (sem link: erro).
        with self.assertRaises(svc.ImageryError):
            svc.provider_layers('planet')


class RasterTilesTests(SimpleTestCase):
    """Tiles gerados no servidor (raster_tiles.py), sem rede: o GDAL é
    trocado por arrays prontos."""

    def setUp(self):
        cache.clear()

    def test_mapbiomas_rejects_low_zoom_unknown_product_and_year(self):
        self.assertIsNone(rt.mapbiomas_tile('cobertura', 2008, rt.MAPBIOMAS_MIN_ZOOM - 1, 0, 0))
        self.assertIsNone(rt.mapbiomas_tile('outro', 2008, 13, 0, 0))
        self.assertIsNone(rt.mapbiomas_tile('cobertura', 1970, 13, 0, 0))

    @patch.object(rt, '_warp_tile')
    def test_mapbiomas_paints_classes_and_caches(self, warp):
        codes = np.zeros((256, 256), dtype=np.uint8)
        codes[0, 0], codes[0, 1], codes[0, 2] = 3, 15, 99  # floresta, pastagem, classe desconhecida
        warp.return_value = [codes]
        png, ctype = rt.mapbiomas_tile('cobertura', 2008, 13, 3005, 4321)
        self.assertEqual(ctype, 'image/png')
        self.assertIn('collection11', warp.call_args.args[0])
        self.assertIn('2008', warp.call_args.args[0])
        image = Image.open(io.BytesIO(png)).convert('RGBA')
        self.assertEqual(image.getpixel((0, 0)), (0x1f, 0x8d, 0x49, 255))
        self.assertEqual(image.getpixel((1, 0)), (0xed, 0xde, 0x8e, 255))
        self.assertEqual(image.getpixel((2, 0)), (0x9e, 0x9e, 0x9e, 255))
        self.assertEqual(image.getpixel((3, 0))[3], 0)  # 0 = sem dado
        rt.mapbiomas_tile('cobertura', 2008, 13, 3005, 4321)
        self.assertEqual(warp.call_count, 1)  # 2ª vez veio do cache

    @patch.object(rt, '_warp_tile')
    def test_fogo_only_paints_burned(self, warp):
        codes = np.zeros((256, 256), dtype=np.uint8)
        codes[5, 5] = 1
        warp.return_value = [codes]
        png, _ = rt.mapbiomas_tile('fogo', 2024, 11, 0, 0)
        image = Image.open(io.BytesIO(png)).convert('RGBA')
        self.assertEqual(image.getpixel((5, 5))[:3], rt._hex_rgb(rt.BURNED_COLOR))
        self.assertEqual(image.getpixel((6, 5))[3], 0)

    def test_cbers_scene_url_only_accepts_inpe_ids(self):
        self.assertEqual(
            rt.cbers_scene_url('CBERS4A_WPM_PCA_RGB321_20240831_208_126'),
            'https://data.inpe.br/bdc/data/CB4A-WPM-PCA-FUSED/v001/208/126/2024/8/CBERS4A_WPM_PCA_RGB321_20240831_208_126.tif')
        for bad in ('../../etc/passwd', 'CBERS4A_WPM_PCA_RGB321_20240831_208_126/../x', 'http://evil/x.tif', '', None):
            self.assertIsNone(rt.cbers_scene_url(bad))
            self.assertIsNone(rt.cbers_tile(bad, 14, 0, 0))

    @patch.object(rt, '_scene_covers', side_effect=lambda scene, lon, lat: not scene.endswith('_207_126'))
    @patch.object(rt.requests, 'post')
    def test_cbers_scenes_sorted_filtered_and_cached(self, post, covers):
        post.return_value = http_response(json={'features': [
            {'id': 'CBERS4A_WPM_PCA_RGB321_20240731_208_126', 'properties': {'datetime': '2024-07-31T00:00:00Z'}},
            {'id': 'CBERS4A_WPM_PCA_RGB321_20260819_207_126', 'properties': {'datetime': '2026-08-19T00:00:00Z'}},
            {'id': 'CBERS4A_WPM_PCA_RGB321_20250907_208_126', 'properties': {'datetime': '2025-09-07T00:00:00Z'}},
            {'id': 'outro-produto', 'properties': {'datetime': '2026-01-01T00:00:00Z'}},
        ]})
        scenes = rt.cbers_scenes(-47.95, -10.44)
        self.assertEqual([s['date'] for s in scenes], ['2025-09-07', '2024-07-31'])
        self.assertEqual(post.call_args.kwargs['json']['intersects']['coordinates'], [-47.95, -10.44])
        rt.cbers_scenes(-47.95, -10.44)
        self.assertEqual(post.call_count, 1)

    @patch.object(rt, '_cbers_stretch', return_value=[(10.0, 110.0)] * 3)
    @patch.object(rt, '_warp_tile')
    def test_cbers_tile_stretches_and_makes_outside_transparent(self, warp, stretch):
        band = np.full((256, 256), 60, dtype=np.uint8)
        band[0, 0] = 0
        warp.return_value = [band, band.copy(), band.copy()]
        webp, ctype = rt.cbers_tile('CBERS4A_WPM_PCA_RGB321_20240831_208_126', 14, 0, 0)
        self.assertEqual(ctype, 'image/webp')
        image = Image.open(io.BytesIO(webp)).convert('RGBA')
        self.assertEqual(image.getpixel((0, 0))[3], 0)
        r, g, b, a = image.getpixel((100, 100))
        self.assertEqual(a, 255)
        self.assertAlmostEqual(r, 128, delta=6)  # (60-10)*255/100 ≈ 127
        self.assertIsNone(rt.cbers_tile('CBERS4A_WPM_PCA_RGB321_20240831_208_126', rt.CBERS_MIN_ZOOM - 1, 0, 0))

    def test_config_lists_server_rendered_layers(self):
        config = svc.imagery_config()
        self.assertTrue(config['mapbiomas']['tile_url'].endswith('/imagens/mapbiomas/{product}/{year}/{z}/{x}/{y}.png'))
        self.assertEqual(config['mapbiomas']['products']['cobertura']['years'][0], 2025)
        self.assertIn(2008, config['mapbiomas']['products']['cobertura']['years'])
        self.assertTrue(config['cbers']['tile_url'].endswith('/imagens/cbers/{scene}/{z}/{x}/{y}.webp'))


class LandUseComparisonTests(SimpleTestCase):
    """Comparativo MapBiomas 2008 × ano atual (land_use_service.py), sem
    rede: a leitura do GeoTIFF é trocada por arrays prontos."""

    # Quadrado de ~1 km no Tocantins.
    GJ = {'type': 'Polygon', 'coordinates': [[[-48.55, -10.75], [-48.541, -10.75], [-48.541, -10.741], [-48.55, -10.741], [-48.55, -10.75]]]}

    def setUp(self):
        cache.clear()

    def _fake_years(self, antes, depois):
        """Metade esquerda e direita da janela com as classes dadas."""
        def warp(url, origin, pixel, width, height, resampling):
            pair = antes if '2008' in url else depois
            codes = np.empty((height, width), dtype=np.uint8)
            codes[:, :width // 2] = pair[0]
            codes[:, width // 2:] = pair[1]
            return [codes]
        return warp

    def test_native_turned_into_pasture_is_counted_and_cached(self):
        # Esquerda: floresta → floresta. Direita: savana → pastagem.
        with patch.object(rt, '_warp_window', side_effect=self._fake_years((3, 4), (3, 15))) as warp:
            r = lu.comparar_uso_solo(self.GJ, 100.0)
            self.assertAlmostEqual(r['total'], 100.0)
            self.assertAlmostEqual(r['nativa_antes'], 100.0)
            self.assertAlmostEqual(r['suprimida'], 50.0, delta=2)
            self.assertAlmostEqual(r['nativa_depois'] + r['suprimida'], 100.0)
            self.assertEqual(r['regenerada'], 0)
            self.assertEqual(r['destino_suprimida'][0]['nome'], 'Pastagem')
            self.assertEqual([c['nome'] for c in r['grupos']], ['Vegetação nativa', 'Agropecuária e silvicultura'])
            self.assertTrue(r['imagens']['mudancas'].startswith('data:image/png;base64,'))
            self.assertEqual({str(lu.ANO_MARCO), str(lu.ano_atual())}, {u.args[0][-8:-4] for u in warp.call_args_list})
            lu.comparar_uso_solo(self.GJ, 100.0)
            self.assertEqual(warp.call_count, 2)  # 2ª vez veio do cache

    def test_regeneration_and_check_without_suppression(self):
        with patch.object(rt, '_warp_window', side_effect=self._fake_years((15, 3), (3, 3))):
            r = lu.comparar_uso_solo(self.GJ, 100.0)
        self.assertEqual(r['suprimida'], 0)
        self.assertAlmostEqual(r['regenerada'], 50.0, delta=2)
        self.assertEqual(report_service._uso_solo_check(r, 0.1)['status'], 'ok')

    def test_unavailable_source_becomes_message_not_error(self):
        with patch.object(rt, '_warp_window', side_effect=svc.ImageryError('x')):
            r = lu.comparar_uso_solo(self.GJ, 100.0)
        self.assertIn('erro', r)
        self.assertEqual(report_service._uso_solo_check(r, 0.1)['status'], 'sem_dado')

    def test_report_renders_comparison_section(self):
        data = {'resultado': {'alvo_geojson': json.dumps(self.GJ), 'tamanho_area': 100.0, 'resultados_por_base': []}}
        with patch.object(rt, '_warp_window', side_effect=self._fake_years((3, 4), (3, 15))):
            ctx = report_service.build_report_context(data)
        check = next(c for c in ctx['checklist'] if '2008' in c['pergunta'])
        self.assertEqual(check['status'], 'atencao')
        html = render_to_string('analysis/report_print.html', ctx)
        self.assertIn('map-uso-mudancas', html)
        self.assertIn('Nativa que virou outro uso', html)
        self.assertIn('Pastagem', html)
