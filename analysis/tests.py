import io
import json
import shutil
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlsplit

from django.core.cache import cache
from django.template.loader import render_to_string
from django.test import SimpleTestCase, override_settings

import numpy as np
from PIL import Image

from analysis.services.view_services import cbers2b_service as cb
from analysis.services.view_services import image_enhance as ie
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
                                       'landsat_legacy', 'cbers2b'})
        self.assertTrue(config['landsat_legacy']['tile_url'].endswith('/imagens/landsat-antigo/{scene}/{comp}/{z}/{x}/{y}.png'))
        self.assertEqual(config['landsat_legacy']['enhanced_max_zoom'], 17)
        self.assertTrue(config['cbers2b']['tile_url'].endswith('/imagens/cbers2b/{scene}/{comp}/{z}/{x}/{y}.webp'))
        self.assertTrue(config['cbers2b']['prepare_url'].endswith('/imagens/cbers2b/{scene}/preparar/'))

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

    @patch.object(svc, '_http')
    def test_landsat_legacy_enhanced_tile_lifts_floor_interpolates_and_sharpens(self, http):
        scene = 'LT05_L2SP_222067_20080722_02_T1'
        stats = {'red_b1': {'percentile_2': 9265.0}, 'green_b1': {'percentile_2': 9479.0},
                 'blue_b1': {'percentile_2': 8533.0}}

        def get(url, params=None, timeout=None):
            if url == svc.PC_STATS_URL:
                return http_response(json=stats, content_type='application/json')
            size = 256 + 2 * int(dict(params).get('buffer', 0))
            out = io.BytesIO()
            Image.new('RGBA', (size, size), (90, 120, 60, 255)).save(out, format='PNG')
            return http_response(content=out.getvalue())

        http.get.side_effect = get
        self.assertIsNone(svc.landsat_legacy_tile(scene, 'natural', 18, 1, 1, enhance=True))
        png, ctype = svc.landsat_legacy_tile(scene, 'natural', 17, 47938, 69262, enhance=True)
        self.assertEqual(ctype, 'image/png')
        self.assertEqual(Image.open(io.BytesIO(png)).size, (256, 256))  # margem cortada
        params = http.get.call_args.kwargs['params']
        # Piso comum = menor percentil 2 (não muda a cor); teto da composição.
        self.assertEqual([v for k, v in params if k == 'rescale'], ['8533,13500'])
        self.assertIn(('reproject', 'cubic'), params)
        self.assertGreater(int(dict(params)['buffer']), 0)
        # Sem realce, o mesmo tile é outro pedido (cache separado), sem margem.
        svc.landsat_legacy_tile(scene, 'natural', 15, 1, 1)
        self.assertNotIn('buffer', dict(http.get.call_args.kwargs['params']))

    @patch.object(svc, '_http')
    def test_landsat_legacy_stretch_falls_back_without_stats(self, http):
        http.get.return_value = http_response(status=500, content_type='application/json')
        self.assertEqual(svc.landsat_legacy_stretch('LT05_L2SP_222067_20080722_02_T1', 'natural'), (7500, 13500))

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

    @patch.object(rt, '_cbers_stretch', return_value=[(10.0, 110.0)] * 3)
    @patch.object(rt, '_warp_tile')
    def test_cbers_enhanced_tile_reads_margin_and_crops_it(self, warp, stretch):
        def bands(url, z, x, y, resampling, buffer=0):
            size = 256 + 2 * buffer
            return [np.full((size, size), 60, dtype=np.uint8) for _ in range(3)]

        warp.side_effect = bands
        webp, _ = rt.cbers_tile('CBERS4A_WPM_PCA_RGB321_20240831_208_126', 17, 0, 0, enhance=True)
        self.assertEqual(Image.open(io.BytesIO(webp)).size, (256, 256))
        args = warp.call_args.args
        self.assertEqual(args[4], 'Cubic')
        self.assertGreater(args[5], 0)

    def test_config_lists_server_rendered_layers(self):
        config = svc.imagery_config()
        self.assertTrue(config['mapbiomas']['tile_url'].endswith('/imagens/mapbiomas/{product}/{year}/{z}/{x}/{y}.png'))
        self.assertEqual(config['mapbiomas']['products']['cobertura']['years'][0], 2025)
        self.assertIn(2008, config['mapbiomas']['products']['cobertura']['years'])
        self.assertTrue(config['cbers']['tile_url'].endswith('/imagens/cbers/{scene}/{z}/{x}/{y}.webp'))


class ImageEnhanceTests(SimpleTestCase):
    def test_sharpen_radius_follows_source_pixel_on_screen(self):
        # Landsat (30 m): afastado o pixel cabe num px do tile (raio mínimo);
        # aproximado, o raio cresce com o pixel ampliado (até o teto).
        self.assertEqual(ie.sharpen_radius(30, 10, 500), ie.SHARPEN_MIN_RADIUS)
        self.assertGreater(ie.sharpen_radius(30, 16, 34631), ie.sharpen_radius(30, 15, 17315))
        self.assertLessEqual(ie.sharpen_radius(30, 19, 277000), ie.SHARPEN_MAX_RADIUS)

    def test_tiles_with_margin_have_no_seam(self):
        # Nitidez tile a tile, cada um lido com margem, = nitidez da imagem
        # inteira recortada: nada muda na borda entre dois tiles.
        rng = np.random.default_rng(1)
        full = np.dstack([rng.integers(0, 255, (512, 768), dtype=np.uint8) for _ in range(3)]
                         + [np.full((512, 768), 255, np.uint8)])
        radius = 2.0
        buffer = ie.sharpen_buffer(radius)
        whole = ie.sharpen_rgba(full, radius)
        top, left = 128, 256
        tile = full[top - buffer:top + 256 + buffer, left - buffer:left + 256 + buffer]
        np.testing.assert_array_equal(ie.sharpen_rgba(tile, radius, buffer), whole[top:top + 256, left:left + 256])


def textured(shape, seed=0):
    """Imagem com textura de vários tamanhos (para a correlação ter o que casar)."""
    rng = np.random.default_rng(seed)
    noise = rng.random(shape)
    image = sum(cb.smooth(noise + 1, s) for s in (1, 3, 8))
    return (image * 40).astype(np.float32)


class Cbers2bServiceTests(SimpleTestCase):
    """cbers2b_service.py sem rede: catálogo e GDAL trocados por respostas
    prontas; a matemática (correlação, ajuste, fusão) com dados sintéticos."""

    SCENE = 'CBERS_2B_HRC_20080721_159_D_111_4_L2'

    def setUp(self):
        cache.clear()
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        override = override_settings(IMAGERY_CACHE_DIR=self.tmp, IMAGERY_CACHE_MAX_MB=1000)
        override.enable()
        self.addCleanup(override.disable)

    def write_meta(self, scene=SCENE, **extra):
        scene_dir = cb._scene_dir(scene)
        scene_dir.mkdir(parents=True)
        meta = {'version': cb.META_VERSION, 'scene': scene, 'date': '2008-07-21',
                'registration': {'ok': True, 'reference': {'scene': 'LT05', 'date': '2008-07-22', 'platform': 'landsat-5'},
                                 'shift_m': 2510, 'residual_m': 14},
                'pan_stretch': [20.0, 60.0], 'bounds_3857': [-6e6, -2e6, -4e6, 0], 'fusion': None,
                'compositions': ['pan'], **extra}
        (scene_dir / 'meta.json').write_text(json.dumps(meta), encoding='utf-8')
        return meta

    def test_phase_shift_recovers_subpixel_offset(self):
        fixed = textured((256, 256))
        # moving(r, c) = fixed(r - 7, c + 4): o conteúdo do pixel p está em p − (7, −4).
        moving = np.roll(fixed, (7, -4), axis=(0, 1))
        dy, dx, peak = cb.phase_shift(moving, fixed, np.ones_like(fixed, bool))
        self.assertAlmostEqual(dy, 7, delta=0.2)
        self.assertAlmostEqual(dx, -4, delta=0.2)
        self.assertGreater(peak, cb.REG_MIN_PEAK)

    def test_register_refuses_unrelated_images(self):
        self.assertIsNone(cb.register(textured((400, 400), seed=1) + 1, textured((400, 400), seed=2) + 1))

    def test_register_fits_translation_from_blocks(self):
        fixed = textured((480, 480)) + 1
        moving = np.roll(fixed, (-12, 9), axis=(0, 1))
        fit = cb.register(moving, fixed)
        self.assertEqual(fit['method'], 'afim')
        dy, dx = cb.shift_at(fit, 240, 240)
        self.assertAlmostEqual(dy, -12, delta=0.3)
        self.assertAlmostEqual(dx, 9, delta=0.3)
        self.assertLess(abs(fit['x'][1]) + abs(fit['x'][2]) + abs(fit['y'][1]) + abs(fit['y'][2]), 1e-3)

    def test_corrected_geotransform_moves_scene_to_true_position(self):
        grid = {'origin': (1000.0, 9000.0), 'res': 20.0}
        # Conteúdo 2 px a leste (dx = −2 ⇒ está 2 px à direita) e 3 px ao sul.
        fit = {'x': [-2.0, 0.0, 0.0], 'y': [3.0, 0.0, 0.0]}
        gt = cb.corrected_geotransform((1000.0, 2.5, 0.0, 9000.0, 0.0, -2.5), grid, fit)
        self.assertAlmostEqual(gt[0], 1040.0)
        self.assertAlmostEqual(gt[3], 9060.0)
        self.assertAlmostEqual(gt[1], 2.5)
        self.assertAlmostEqual(gt[5], -2.5)
        # Com rotação/escala no ajuste, o pixel também muda (geotransform afim).
        fit = {'x': [0.0, 0.001, 0.0], 'y': [0.0, 0.0, 0.0]}
        gt = cb.corrected_geotransform((1000.0, 2.5, 0.0, 9000.0, 0.0, -2.5), grid, fit)
        self.assertAlmostEqual(gt[1], 2.5 * (1 - 0.001))

    def test_resample_honors_rotated_geotransform(self):
        # O HRC corrigido tem rotação no geotransform. Sem `skew` no destino,
        # o warp do Django copia a rotação da origem e ela some (bug real:
        # a correção deixava ~40 m de erro na borda da cena).
        from django.contrib.gis.gdal import GDALRaster
        data = np.zeros((100, 100), np.float32)
        data[50, 10] = data[50, 90] = 1
        raster = GDALRaster({'driver': 'MEM', 'name': 'r', 'srid': 32722, 'width': 100, 'height': 100,
                             'datatype': 6, 'nr_of_bands': 1, 'bands': [{'data': data}]})
        raster.geotransform = [0.0, 1.0, 0.0, 100.0, 0.2, -1.0]  # Y sobe 0,2 por coluna
        out = cb._resample(raster, {'srid': 32722, 'origin': (0, 120), 'res': 1.0, 'width': 100, 'height': 140},
                           'NearestNeighbour')
        rows = {int(c): int(r) for r, c in zip(*np.nonzero(out))}
        self.assertEqual(rows[10] - rows[90], 16)  # 80 colunas × 0,2

    @patch.object(cb.requests, 'get')
    @patch.object(cb, '_stac_search')
    def test_landsat_reference_accepts_partial_cover_preferring_more(self, search, get):
        # HRC na divisa de duas órbitas do Landsat: nenhuma cena o contém inteiro.
        footprint = {'type': 'Polygon', 'coordinates': [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]}
        hrc = {'id': self.SCENE, 'geometry': footprint, 'properties': {'datetime': '2008-07-21T13:00:00Z'}}

        def scene(scene_id, maxx, cloud=0):
            return {'id': scene_id, 'geometry': {'type': 'Polygon', 'coordinates': [[[-5, -5], [maxx, -5], [maxx, 5], [-5, 5], [-5, -5]]]},
                    'properties': {'datetime': '2008-07-22T13:00:00Z', 'platform': 'landsat-5', 'eo:cloud_cover': cloud}}

        search.return_value = [scene('LT05_POUCO_T1', 0.5), scene('LT05_MAIS_T1', 0.9),
                               scene('LT05_QUASE_NADA_T1', 0.3), scene('LT05_TIER2_T2', 5)]
        get.return_value = http_response(content=b'II*\x00resto', content_type='image/tiff')
        reference = cb._landsat_reference(hrc, Path(self.tmp))
        self.assertEqual(reference['scene'], 'LT05_MAIS_T1')
        self.assertEqual(get.call_args.kwargs['params']['return_mask'], 'false')

    @patch.object(cb, '_prepare')
    def test_progress_is_published_while_preparing_and_cleared_after(self, prepare):
        seen = []

        def fake(scene, report):
            report('Baixando a cena do INPE (20 de 56 MB)…')
            seen.append(cb.hrc_progress(scene))
            return {}

        prepare.side_effect = fake
        cb.hrc_prepare(self.SCENE)
        self.assertEqual(seen, ['Baixando a cena do INPE (20 de 56 MB)…'])
        self.assertEqual(cb.hrc_progress(self.SCENE), '')

    def test_thumbnail_only_from_inpe_archive(self):
        ok = 'https://data.inpe.br/bdc/data/CB2B-HRC-L2-DN/2008_07/x/CBERS_2B_HRC_20080721_159_D_111_4.png'
        self.assertEqual(cb._thumbnail_href({'assets': {'thumbnail': {'href': ok}}}), ok)
        self.assertEqual(cb._thumbnail_href({'assets': {'thumbnail': {'href': 'https://evil/x.png'}}}), '')
        self.assertEqual(cb._thumbnail_href({}), '')

    def test_fusion_params_predict_pan_from_bands(self):
        bands = [textured((200, 200), seed=s) + 10 for s in range(4)]
        pan = 5 + 0.4 * bands[1] + 0.6 * bands[2]
        fusion = cb.fusion_params(pan, bands)
        self.assertGreater(fusion['r2'], 0.99)
        np.testing.assert_allclose(fusion['coef'], [5, 0, 0.4, 0.6, 0], atol=1e-3)
        self.assertEqual(len(fusion['gains']), 4)

    def test_natural_color_brings_ccd_to_landsat_scale(self):
        ccd = [textured((200, 200), seed=s) + 20 for s in range(3)]
        landsat = [c * 20 + 6000 for c in ccd]  # ~10 000 DN, como reflectância de cerrado
        params = cb.natural_color_params(ccd, landsat)
        # Mesmo valor do CCD → mesma posição na escala da camada Landsat (piso comum, teto 13500).
        lo = min(float(np.percentile(l, 2)) for l in landsat)
        for i in range(3):
            value = float(ccd[i][50, 50])
            self.assertAlmostEqual(params['a'][i] * value + params['b'][i], (landsat[i][50, 50] - lo) / (13500 - lo), places=3)

    def test_smooth_keeps_nodata_and_mean(self):
        band = np.full((60, 60), 100, np.float32)
        band[:, :10] = 0
        out = cb.smooth(band, 1.5)
        self.assertTrue((out[:, :10] == 0).all())
        self.assertAlmostEqual(float(out[:, 10:].mean()), 100, places=3)  # borda não escurece

    def test_tif_href_only_accepts_inpe_archive(self):
        ok = 'https://data.inpe.br/bdc/data/CB2B-HRC-L2-DN/2008_07/x/CBERS_2B_HRC_20080721_159_D_111_4_L2_BAND1.tif'
        self.assertEqual(cb._tif_href({'href': ok}), ok)
        for bad in ('http://evil/x.tif', 'https://data.inpe.br/bdc/data/../../etc.tif', 'https://data.inpe.br/bdc/data/x.png', None):
            with self.assertRaises(svc.ImageryError):
                cb._tif_href({'href': bad} if bad else None)

    @patch.object(cb.requests, 'post')
    def test_scenes_sorted_with_ready_flag_and_cached(self, post):
        self.write_meta()
        post.return_value = http_response(json={'features': [
            {'id': 'CBERS_2B_HRC_20071009_159_C_111_4_L2', 'properties': {'datetime': '2007-10-09T13:00:00Z'},
             'assets': {'thumbnail': {'href': 'https://data.inpe.br/bdc/data/x/CBERS_2B_HRC_20071009_159_C_111_4.png'}}},
            {'id': self.SCENE, 'properties': {'datetime': '2008-07-21T13:00:00Z'}},
            {'id': 'outro', 'properties': {'datetime': '2009-01-01T00:00:00Z'}},
        ]})
        scenes = cb.hrc_scenes(-48.2, -10.03)
        self.assertEqual([(s['date'], s['ready'], s['name']) for s in scenes],
                         [('2008-07-21', True, '159_D_111_4'), ('2007-10-09', False, '159_C_111_4')])
        self.assertTrue(scenes[1]['thumbnail'].endswith('_159_C_111_4.png'))
        self.assertEqual(scenes[0]['thumbnail'], '')
        body = post.call_args.kwargs['json']
        self.assertEqual(body['collections'], [cb.HRC_COLLECTION])
        self.assertEqual(body['intersects']['type'], 'Polygon')  # ponto com margem (erro de posição)
        cb.hrc_scenes(-48.2, -10.03)
        self.assertEqual(post.call_count, 1)

    @patch.object(cb, '_prepare')
    def test_prepare_validates_id_and_reuses_prepared_scene(self, prepare):
        with self.assertRaises(svc.ImageryError):
            cb.hrc_prepare('../../etc/passwd')
        meta = self.write_meta()
        self.assertEqual(cb.hrc_prepare(self.SCENE), meta)
        prepare.assert_not_called()

    def test_prepare_waits_for_other_process_then_gives_up(self):
        cache.add(f'raster:cbers2b:preparando:{self.SCENE}', 1, 60)
        with patch.object(cb, 'PREPARE_WAIT', 0.01), patch.object(cb, 'PREPARE_POLL', 0.01):
            with self.assertRaises(svc.ImageryError):
                cb.hrc_prepare(self.SCENE)

    def test_tile_needs_prepared_scene_known_composition_and_zoom(self):
        self.assertIsNone(cb.hrc_tile(self.SCENE, 'pan', 15, 11991, 17299))  # ainda não preparada
        self.write_meta()
        self.assertIsNone(cb.hrc_tile(self.SCENE, 'cor', 15, 11991, 17299))  # sem fusão nesta cena
        self.assertIsNone(cb.hrc_tile(self.SCENE, 'outra', 15, 11991, 17299))
        self.assertIsNone(cb.hrc_tile(self.SCENE, 'pan', cb.HRC_MIN_ZOOM - 1, 0, 0))
        self.assertIsNone(cb.hrc_tile(self.SCENE, 'pan', 15, 0, 0))  # fora da cena

    @patch.object(rt, '_warp_tile')
    def test_tile_fuses_and_falls_back_to_pan_outside_ccd(self, warp):
        fusion = {'coef': [0, 0.25, 0.25, 0.25, 0.25], 'gains': [1, 1, 1, 1],
                  'stretch': [[0, 100]] * 4, 'r2': 0.8, 'natural': None}
        self.write_meta(fusion=fusion, compositions=['pan', 'cor', 'falsa_cor'])
        pan = np.full((256, 256), 40, np.uint8)
        pan[0, 0] = 0  # fora da faixa imageada
        ccd = [np.full((256, 256), v, np.uint8) for v in (20, 40, 60, 80)]
        for band in ccd:
            band[:, 200:] = 0  # CCD não cobre a borda direita

        warp.side_effect = lambda path, *args: [pan] if path.endswith('hrc.tif') else ccd
        webp, _ = cb.hrc_tile(self.SCENE, 'falsa_cor', 15, 11991, 17299)
        image = Image.open(io.BytesIO(webp)).convert('RGBA')
        self.assertEqual(image.getpixel((0, 0))[3], 0)
        r, g, b, a = image.getpixel((100, 100))
        # Falsa cor = B4, B3, B2 (+ detalhe pan − I = 40 − 50 = −10): 70, 50, 30 de 0–100.
        self.assertAlmostEqual(r, 178, delta=8)
        self.assertAlmostEqual(g, 128, delta=8)
        self.assertAlmostEqual(b, 76, delta=8)
        gray = image.getpixel((230, 100))
        self.assertEqual(gray[0], gray[1])  # sem CCD: pancromático
        self.assertEqual(gray[1], gray[2])

    def test_prepare_view_rejects_bad_id_and_reports_errors(self):
        from django.http import Http404
        from django.test import RequestFactory
        from analysis import views
        view = views.Cbers2bPrepareView.as_view()
        factory = RequestFactory()
        with self.assertRaises(Http404):
            view(factory.post('/'), scene='nao-e-cena')
        self.assertEqual(view(factory.get('/'), scene=self.SCENE).status_code, 405)  # só POST
        with patch.object(views, 'hrc_prepare', side_effect=svc.ImageryError('Falha ao baixar a cena do INPE.')):
            response = view(factory.post('/'), scene=self.SCENE)
        self.assertEqual(response.status_code, 502)
        self.assertEqual(json.loads(response.content)['erro'], 'Falha ao baixar a cena do INPE.')

    def test_scenes_view_answers_json_even_on_unexpected_error(self):
        # O painel mostra o motivo; uma página de erro em HTML virava
        # "Nenhuma imagem disponível" sem explicação.
        from django.test import RequestFactory
        from analysis import views
        request = RequestFactory().get('/', {'lat': '-12.2', 'lon': '-47.8'})
        with patch.object(views, 'hrc_scenes', side_effect=KeyError('x')):
            response = views.Cbers2bScenesView.as_view()(request)
        self.assertEqual(response.status_code, 500)
        self.assertIn('KeyError', json.loads(response.content)['erro'])

    def test_client_info_explains_missing_color(self):
        info = cb.hrc_client_info(self.write_meta(ccd_alignment={'ok': False, 'reason': 'O CCD não casou com o HRC.'}))
        self.assertFalse(info['fusion'])
        self.assertEqual(info['fusion_note'], 'O CCD não casou com o HRC.')
        self.assertEqual(info['compositions'], [{'value': 'pan', 'text': cb.COMPOSITIONS['pan']['label']}])
        self.assertEqual(info['registration']['shift_m'], 2510)


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


@override_settings(CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache', 'LOCATION': 'progress-tests'}})
class AnalysisProgressTests(SimpleTestCase):
    """Andamento da análise lido pela tela do mapa 3D (`analysis_progress`)."""

    JOB = '0123456789abcdef0123'

    def setUp(self):
        cache.clear()
        self.user = Mock(pk=7)

    def _layers(self):
        return [type('Embargoes', (), {}), type('ZoningArea', (), {})]

    def test_without_valid_job_id_everything_is_a_no_op(self):
        from analysis.services.view_services.analysis_progress import AnalysisProgress, read_progress
        progress = AnalysisProgress(self.user.pk, 'not hex!')
        self.assertFalse(progress)
        progress.layers(self._layers())
        progress.check_cancelled()
        self.assertIsNone(read_progress(self.user, 'not hex!'))

    def test_layer_progress_and_only_alert_overlaps_are_drawn(self):
        from django.contrib.gis.geos import Polygon
        from analysis.services.view_services.analysis_progress import AnalysisProgress, read_progress
        embargo, zoning = self._layers()
        progress = AnalysisProgress(self.user.pk, self.JOB)
        progress.layers([embargo, zoning])
        progress.layer_started(embargo)
        state = read_progress(self.user, self.JOB)
        self.assertEqual(state['current'], 'Embargos do IBAMA')
        self.assertEqual([b['status'] for b in state['bases']], ['running', 'pending'])

        square = Polygon(((-48, -10), (-47.99, -10), (-47.99, -9.99), (-48, -9.99), (-48, -10)), srid=4674)
        rows = [{'intersection_area_ha': 2.5, 'intersection_geom': square}]
        progress.layer_done(embargo, rows)
        progress.layer_started(zoning)
        progress.layer_done(zoning, rows)
        state = read_progress(self.user, self.JOB)
        self.assertEqual(state['done'], 2)
        self.assertEqual([(b['count'], b['area_ha']) for b in state['bases']], [(1, 2.5), (1, 2.5)])
        # Zoneamento é informativo: só o embargo vai para o mapa.
        self.assertEqual(len(state['features']), 1)
        self.assertEqual(state['features'][0]['geometry']['type'], 'Polygon')

    def test_progress_is_private_to_the_user(self):
        from analysis.services.view_services.analysis_progress import AnalysisProgress, read_progress
        AnalysisProgress(self.user.pk, self.JOB).stage('Lendo o documento', car='TO-1')
        self.assertEqual(read_progress(self.user, self.JOB)['car'], 'TO-1')
        self.assertIsNone(read_progress(Mock(pk=8), self.JOB))

    def test_cancel_stops_before_the_next_layer(self):
        from analysis.services.view_services.analysis_progress import (
            AnalysisCancelled, AnalysisProgress, cancel_progress,
        )
        progress = AnalysisProgress(self.user.pk, self.JOB)
        progress.layers(self._layers())
        cancel_progress(self.user, self.JOB)
        with self.assertRaises(AnalysisCancelled):
            progress.layer_started(self._layers()[0])


KML_TWO_PARCELS = b"""<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2"><Document>
  <Placemark><name>Gleba 1</name><Polygon><outerBoundaryIs><LinearRing><coordinates>
    -48.30,-10.20,0 -48.29,-10.20,0 -48.29,-10.19,0 -48.30,-10.19,0 -48.30,-10.20,0
  </coordinates></LinearRing></outerBoundaryIs>
  <innerBoundaryIs><LinearRing><coordinates>
    -48.298,-10.198 -48.296,-10.198 -48.296,-10.196 -48.298,-10.196 -48.298,-10.198
  </coordinates></LinearRing></innerBoundaryIs></Polygon></Placemark>
  <Placemark><name>Gleba 2</name><MultiGeometry><Polygon><outerBoundaryIs><LinearRing><coordinates>
    -48.28,-10.20 -48.27,-10.20 -48.27,-10.19 -48.28,-10.19 -48.28,-10.20
  </coordinates></LinearRing></outerBoundaryIs></Polygon></MultiGeometry></Placemark>
  <Placemark><name>Sede</name><Point><coordinates>-48.295,-10.195,0</coordinates></Point></Placemark>
</Document></kml>"""


class KmlUploadServiceTests(SimpleTestCase):

    def _read(self, content, name='area.kml'):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from analysis.services.view_services.kml_upload_service import KmlUploadService
        return KmlUploadService().extract_geodataframe(SimpleUploadedFile(name, content))

    def test_junta_todos_os_poligonos_e_mantem_o_furo(self):
        gdf = self._read(KML_TWO_PARCELS)
        geom = gdf.geometry.iloc[0]
        self.assertEqual(gdf.crs.to_epsg(), 4326)
        self.assertEqual(geom.geom_type, 'MultiPolygon')
        self.assertEqual(len(geom.geoms), 2)
        self.assertAlmostEqual(geom.area, 0.0001 * 2 - 0.002 * 0.002)

    def test_kmz_le_o_kml_de_dentro(self):
        import zipfile
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w') as zf:
            zf.writestr('doc.kml', KML_TWO_PARCELS)
        gdf = self._read(buf.getvalue(), 'area.kmz')
        self.assertEqual(len(gdf.geometry.iloc[0].geoms), 2)

    def test_so_pontos_nao_tem_area(self):
        kml = b'<kml xmlns="http://www.opengis.net/kml/2.2"><Placemark><Point><coordinates>-48.3,-10.2</coordinates></Point></Placemark></kml>'
        self.assertIsNone(self._read(kml))

    def test_arquivo_invalido(self):
        from analysis.services.view_services.kml_upload_service import KmlUploadError
        with self.assertRaises(KmlUploadError):
            self._read(b'isto nao e xml')


class CoordinatesInputTests(SimpleTestCase):

    def _parse(self, text):
        from analysis.services.view_services.coordinates_input_service import build_polygon, parse_vertices
        return build_polygon(parse_vertices(text))

    def test_formatos_do_google_maps(self):
        from analysis.services.view_services.coordinates_input_service import parse_vertices
        (lon, lat), = parse_vertices('9°35\'03.1"S 48°31\'33.0"W')
        self.assertAlmostEqual(lat, -(9 + 35 / 60 + 3.1 / 3600))
        self.assertAlmostEqual(lon, -(48 + 31 / 60 + 33 / 3600))
        self.assertEqual(parse_vertices('-9.581852, -48.526588'), [(-48.526588, -9.581852)])

    def _assert_square(self, geom):
        self.assertEqual(geom.srid, 4674)
        xs = sorted({round(x, 4) for x, _ in geom.coords[0]})
        ys = sorted({round(y, 4) for _, y in geom.coords[0]})
        self.assertEqual(xs, [-48.3, -48.29])
        self.assertEqual(ys, [-10.2, -10.19])

    def test_graus_decimais_lat_lon(self):
        self._assert_square(self._parse('-10.20, -48.30\n-10.20, -48.29\n-10.19, -48.29\n-10.19, -48.30\n'))

    def test_virgula_decimal_ordem_lon_lat_e_anel_fechado(self):
        self._assert_square(self._parse(
            '-48,30; -10,20\n-48,29; -10,20\n\n-48,29; -10,19\n-48,30; -10,19\n-48,30; -10,20'))

    def test_sem_sinal_e_sul_oeste(self):
        self._assert_square(self._parse('10.20 48.30\n10.20 48.29\n10.19 48.29\n10.19 48.30'))

    def test_graus_minutos_segundos(self):
        geom = self._parse(
            '10°12\'00" S 48°18\'00" W\n10°12\'00" S 48°17\'24" O\n'
            '10°11\'24,0" S 48°17\'24,0" W\n10°11\'24" S 48°18\'00" W')
        self._assert_square(geom)

    def test_erros(self):
        from analysis.services.view_services.coordinates_input_service import CoordinatesInputError
        for text, msg in [
            ('-10.2, -48.3\n-10.2, -48.29', '3 vértices'),
            ('   \n', 'ao menos uma'),
            ('-10.2, -48.3\nabc', 'Linha 2'),
            ('-10.20, -48.30\n-10.19, -48.29\n-10.20, -48.29\n-10.19, -48.30', 'se cruza'),
        ]:
            with self.assertRaisesRegex(CoordinatesInputError, msg):
                self._parse(text)
