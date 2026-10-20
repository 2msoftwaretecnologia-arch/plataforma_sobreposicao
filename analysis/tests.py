from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlsplit

from django.core.cache import cache
from django.test import SimpleTestCase, override_settings

from analysis.services.view_services import imagery_service as svc

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
        self.assertEqual(svc.planet_layers(), [
            {'id': 'global_monthly_2026_09_mosaic', 'title': 'Global Monthly 2026-09', 'max_zoom': 2}])

    @override_settings(PLANET_WMS_URL='https://x/ogc/wms/abc?api_key=K', PLANET_API_KEY='')
    @patch.object(svc, '_http')
    def test_wms_tile_builds_getmap_with_key(self, http):
        http.get.side_effect = [http_response(content=WMS_CAPABILITIES, content_type='text/xml'),
                                http_response(content=b'PNG')]
        self.assertEqual(svc.planet_tile('TRUE_COLOR', 1, 1, 1), (b'PNG', 'image/png'))
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
        svc.planet_tile('global_monthly_2026_09_mosaic', 2, 3, 1)
        url = http.get.call_args.args[0]
        self.assertTrue(url.startswith('https://tiles.planet.com/basemaps/v1/planet-tiles/global_monthly_2026_09_mosaic/gmap/2/3/1.png'))
        self.assertEqual(parse_qs(urlsplit(url).query)['api_key'], ['SEGREDO'])
        # Primeira chamada (capabilities) foi ao WMTS da conta.
        self.assertEqual(http.get.call_args_list[0].args[0], svc.PLANET_WMTS_URL)

    @override_settings(PLANET_WMS_URL='', PLANET_API_KEY='K')
    @patch.object(svc, '_http')
    def test_zoom_beyond_matrix_set_and_unknown_layer_have_no_tile(self, http):
        http.get.return_value = http_response(content=WMTS_CAPABILITIES, content_type='text/xml')
        self.assertIsNone(svc.planet_tile('global_monthly_2026_09_mosaic', 5, 0, 0))
        self.assertIsNone(svc.planet_tile('nao_existe', 1, 0, 0))

    @override_settings(PLANET_WMS_URL='https://x/ogc/wms/abc?api_key=K', PLANET_API_KEY='')
    @patch.object(svc, '_http')
    def test_wms_xml_error_is_not_served_as_image(self, http):
        http.get.side_effect = [http_response(content=WMS_CAPABILITIES, content_type='text/xml'),
                                http_response(content=b'<ServiceException/>', content_type='text/xml')]
        with self.assertRaises(svc.ImageryError):
            svc.planet_tile('TRUE_COLOR', 1, 0, 0)

    @override_settings(PLANET_WMS_URL='https://x/ogc/wms/abc?api_key=K', PLANET_API_KEY='')
    @patch.object(svc, '_http')
    def test_connection_error_message_hides_key(self, http):
        import requests
        http.get.side_effect = requests.ConnectionError('https://x/ogc/wms/abc?api_key=K')
        with self.assertRaises(svc.ImageryError) as ctx:
            svc.planet_layers()
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
            '1': {'itemTitle': 'World Imagery (Wayback 2014-02-20)'},
            '63116': {'itemTitle': 'World Imagery (Wayback 2026-09-24)'},
            '9': {'itemTitle': 'sem data'},
        })
        self.assertEqual(svc.wayback_releases(), [{'id': 63116, 'date': '2026-09-24'}, {'id': 1, 'date': '2014-02-20'}])

    @override_settings(PLANET_WMS_URL='', PLANET_API_KEY='', GOOGLE_MAPS_API_KEY='')
    def test_config_without_keys_only_offers_wayback(self):
        config = svc.imagery_config()
        self.assertEqual(set(config), {'wayback_tile_url', 'wayback_releases_url'})

    @override_settings(PLANET_WMS_URL='https://x/wms?key=SEGREDO', GOOGLE_MAPS_API_KEY='GSEGREDO')
    def test_config_uses_proxy_urls_and_never_the_keys(self):
        config = svc.imagery_config()
        self.assertTrue(config['planet_tile_url'].endswith('/imagens/planet/{layer}/{z}/{x}/{y}'))
        self.assertTrue(config['google_tile_url'].endswith('/imagens/google/{z}/{x}/{y}'))
        self.assertNotIn('SEGREDO', str(config))
