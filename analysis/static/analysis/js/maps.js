(function (global) {
    'use strict';

    // Estado do último mapa inicializado nesta página, usado por focusMapLayer
    // para permitir que os cards de resultado apontem/centralizem o mapa.
    var mapState = null;

    // Fonte que representa o contorno da propriedade — única camada que
    // começa marcada por padrão no mapa interativo.
    var PROPERTY_FONTE = 'Área da Propriedade';
    // Ponto sem imóvel do SICAR: o mapa mostra só o local (ver result_map_formatter).
    var POINT_FONTE = 'Ponto informado';

    // Tile vazio usado pelas fontes com seletor (Planet, Wayback) enquanto a
    // lista de mosaicos/datas não chega, para não pedir tiles sem a opção.
    var BLANK_TILE = 'data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7';

    // "Melhorar imagem" (painel Imagem): as fontes com `enhance` no picker
    // pedem os tiles com ?realce=1 (contraste, interpolação e nitidez no
    // servidor; ver image_enhance.py).
    var ENHANCE_QUERY = '?realce={realce}';
    var ENHANCE_HINT = 'Contraste ajustado à cena, interpolação suave e nitidez. ' +
        'Deixa mais legível o que o satélite registrou; não cria detalhes.';

    function csrfToken() {
        var el = document.querySelector('input[name="csrfmiddlewaretoken"]');
        if (el) return el.value;
        var match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
        return match ? decodeURIComponent(match[1]) : '';
    }

    // Sentinel-2 (Copernicus) no Living Atlas da Esri: público, cenas dos
    // últimos ~14 meses, com composições de banda prontas no servidor.
    var SENTINEL2_URL = 'https://sentinel.arcgis.com/arcgis/rest/services/Sentinel2/ImageServer';
    // `res`: resolução das bandas usadas (visível e NIR 10 m; SWIR 20 m).
    var SENTINEL2_RENDERINGS = [
        { value: 'Color Infrared with DRA', text: 'Infravermelho falsa-cor (vegetação em vermelho)', res: 10 },
        { value: 'NDVI Colormap', text: 'NDVI (vigor da vegetação)', res: 10 },
        { value: 'Agriculture with DRA', text: 'Agricultura (SWIR · NIR · azul)', res: 20 },
        { value: 'Short-wave Infrared with DRA', text: 'Infravermelho de ondas curtas (SWIR)', res: 20 },
        { value: 'Natural Color with DRA', text: 'Cor natural', res: 10 }
    ];

    // Landsat (USGS/NASA) no Living Atlas da Esri: Landsat 8/9 de 2013 em
    // diante e, antes disso, só as épocas do Global Land Survey (~1990, 2000,
    // 2005, 2010). Os anos do seletor vêm do catálogo no centro do mapa.
    var LANDSAT_URL = 'https://landsat2.arcgis.com/arcgis/rest/services/Landsat/MS/ImageServer';
    var LANDSAT_THERMAL = 'Band 10 Surface Temperature in Celsius';
    var LANDSAT_RENDERINGS = [
        { value: 'Natural Color with DRA', text: 'Cor natural', res: 30 },
        { value: 'Color Infrared with DRA', text: 'Infravermelho falsa-cor (vegetação em vermelho)', res: 30 },
        { value: 'NDVI Colorized', text: 'NDVI (vigor da vegetação)', res: 30 },
        { value: 'Agriculture with DRA', text: 'Agricultura (SWIR · NIR · azul)', res: 30 },
        { value: 'Short-wave Infrared with DRA', text: 'Infravermelho de ondas curtas (SWIR)', res: 30 },
        // Banda térmica só existe no Landsat 8/9; o sensor tem 100 m.
        { value: LANDSAT_THERMAL, text: 'Temperatura da superfície em °C (2013+)', res: 100 }
    ];

    // A banda térmica vem em °C brutos (≈ 20–50), que viram quase preto numa
    // imagem 0–255: estica 20–50 °C e pinta de azul (frio) a vermelho (quente).
    var THERMAL_MIN = 20, THERMAL_MAX = 50;

    function thermalRampSegment(from, to) {
        return { type: 'algorithmic', fromColor: from.concat(255), toColor: to.concat(255), algorithm: 'esriCIELabAlgorithm' };
    }

    function landsatRenderingRule(value) {
        if (value !== LANDSAT_THERMAL) return { rasterFunction: value };
        var stops = [[49, 54, 149], [116, 173, 209], [255, 255, 191], [244, 109, 67], [165, 0, 38]];
        return {
            rasterFunction: 'Colormap',
            rasterFunctionArguments: {
                Colorramp: {
                    type: 'multipart',
                    colorRamps: stops.slice(1).map(function (to, i) { return thermalRampSegment(stops[i], to); })
                },
                Raster: {
                    rasterFunction: 'Stretch',
                    rasterFunctionArguments: {
                        StretchType: 5,
                        Statistics: [[THERMAL_MIN, THERMAL_MAX, (THERMAL_MIN + THERMAL_MAX) / 2, 5]],
                        Raster: { rasterFunction: LANDSAT_THERMAL }
                    }
                }
            }
        };
    }

    /**
     * Parâmetros de consulta por ponto nos serviços ArcGIS. A geometria vai
     * em JSON com o sistema de coordenadas: no formato curto "x,y" alguns
     * serviços (ex.: Landsat) ignoram o filtro e devolvem cenas de qualquer
     * lugar do mundo.
     */
    function pointQuery(latlng, extra) {
        var params = {
            f: 'json',
            geometry: JSON.stringify({ x: latlng.lng, y: latlng.lat, spatialReference: { wkid: 4326 } }),
            geometryType: 'esriGeometryPoint',
            spatialRel: 'esriSpatialRelIntersects',
            returnGeometry: 'false'
        };
        Object.keys(extra).forEach(function (k) { params[k] = extra[k]; });
        return new URLSearchParams(params);
    }

    // ImageServer da Esri que gera a imagem na hora (~3 s por pedido): em vez
    // de tiles, o esri-leaflet pede uma imagem do tamanho da tela a cada
    // movimento.
    function imageServerLayer(url, rasterFunction, attribution, pane) {
        return L.esri.imageMapLayer({
            url: url,
            renderingRule: { rasterFunction: rasterFunction },
            format: 'jpgpng',
            f: 'image',
            pane: pane || 'tilePane',
            attribution: attribution
        });
    }

    /**
     * Camada de tiles que não pede nada abaixo de `minDataZoom` (tiles
     * gerados no servidor a partir de GeoTIFF: afastado demais seria lento).
     * O `minZoom` do Leaflet não serve: ele limita o zoom do mapa inteiro
     * quando a camada é o mapa base.
     */
    var MinZoomTileLayer = L.TileLayer.extend({
        getTileUrl: function (coords) {
            if (coords.z < this.options.minDataZoom) return BLANK_TILE;
            return L.TileLayer.prototype.getTileUrl.call(this, coords);
        }
    });
    global.MinZoomTileLayer = MinZoomTileLayer;

    function formatDateBR(isoDate) {
        var p = (isoDate || '').split('-');
        return p.length === 3 ? p[2] + '/' + p[1] + '/' + p[0] : isoDate;
    }

    /**
     * Creates and returns the base layers for the map.
     * @param {object} imagery URLs de `imagery_config()` (imagery_service.py)
     * @param {object} opts `pane` (lado direito da comparação usa o seu),
     *   `noBackdrop` (sem a Esri por baixo da Wayback) e `withMapbiomas`
     *   (inclui o uso do solo do MapBiomas como opção de mapa base).
     * @returns {object} { layers: object, defaultLayer: L.layer, pickers: array }
     */
    function getBaseLayers(imagery, opts) {
        imagery = imagery || {};
        opts = opts || {};
        var pane = opts.pane || 'tilePane';
        var esriSatUrl = 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}';
        var baseOSM = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19, pane: pane });
        var baseEsriSat = L.tileLayer(esriSatUrl, { maxZoom: 16, pane: pane });
        var baseCartoLight = L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', { maxZoom: 20, pane: pane });
        var baseTopo = L.tileLayer('https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png', { maxZoom: 17, pane: pane });

        // `imageryInfo` diz ao painel de setupImageryPanel de onde vem a
        // resolução de cada imagem de satélite (camadas sem ele não têm painel).
        baseEsriSat.imageryInfo = { kind: 'esri', name: 'Satélite (Esri)' };
        var layers = { 'Satélite (Esri)': baseEsriSat };
        // Fontes cuja imagem depende de uma escolha (mosaico/data), feita no
        // mesmo painel.
        var pickers = [];

        if (imagery.google_tile_url) {
            var baseGoogle = L.tileLayer(imagery.google_tile_url, {
                maxZoom: 20,
                pane: pane,
                attribution: 'Imagens &copy; Google'
            });
            baseGoogle.imageryInfo = { kind: 'text', name: 'Satélite (Google)', text: 'Resolução não informada pelo Google.' };
            layers['Satélite (Google)'] = baseGoogle;
        }

        // Provedores com link WMS/WMTS configurado no servidor (Planet,
        // Copernicus): tiles pelo proxy de `imagery_service.py`.
        (imagery.providers || []).forEach(function (provider) {
            var baseProvider = L.tileLayer(BLANK_TILE, { maxZoom: 19, layer: '', pane: pane, attribution: provider.attribution });
            baseProvider.imageryInfo = { kind: 'provider', resolutionHint: provider.resolution_hint };
            layers[provider.base_name] = baseProvider;
            pickers.push({
                layer: baseProvider,
                template: provider.tile_url,
                param: 'layer',
                label: provider.label,
                listUrl: provider.layers_url,
                parse: function (json) {
                    return (json.layers || []).map(function (l) {
                        return { value: encodeURIComponent(l.id), text: l.title, maxZoom: l.max_zoom };
                    });
                }
            });
        });

        if (imagery.wayback_tile_url && imagery.wayback_releases_url) {
            var baseWayback = L.tileLayer(BLANK_TILE, { maxZoom: 19, release: '', pane: pane, attribution: 'Imagens &copy; Esri (World Imagery Wayback)' });
            baseWayback.imageryInfo = { kind: 'esri' };
            layers['Histórico (Esri Wayback)'] = baseWayback;
            pickers.push({
                layer: baseWayback,
                template: imagery.wayback_tile_url,
                param: 'release',
                label: 'Data da imagem',
                listUrl: imagery.wayback_releases_url,
                // Os tiles da Wayback demoram ~1 s cada (redirecionamento +
                // servidor lento): a lista de datas é buscada já ao abrir o
                // mapa, e a Esri atual fica por baixo enquanto eles chegam.
                // Só na Wayback: é a mesma imagem da Esri, então o fundo não
                // se confunde com a imagem escolhida.
                prefetch: true,
                backdrop: opts.noBackdrop ? null : L.tileLayer(esriSatUrl, { maxZoom: 19, maxNativeZoom: 16, zIndex: 0, pane: pane }),
                parse: function (json) {
                    return (json.releases || []).map(function (r) {
                        return { value: String(r.id), text: formatDateBR(r.date), metadataUrl: r.metadata_url };
                    });
                }
            });
        }

        if (global.L.esri && L.esri.imageMapLayer) {
            var baseInfrared = imageServerLayer(SENTINEL2_URL, SENTINEL2_RENDERINGS[0].value, 'Sentinel-2 (Copernicus) &copy; Esri', pane);
            baseInfrared.imageryInfo = { kind: 'sentinel2' };
            layers['Infravermelho (Sentinel-2)'] = baseInfrared;
            pickers.push({
                layer: baseInfrared,
                label: 'Composição',
                options: SENTINEL2_RENDERINGS,
                selected: SENTINEL2_RENDERINGS[0].value,
                // Imagem lenta: o painel mostra "Carregando imagem…".
                slow: true,
                onSelect: function (value) {
                    baseInfrared.setRenderingRule({ rasterFunction: value });
                }
            });

            var baseLandsat = imageServerLayer(LANDSAT_URL, LANDSAT_RENDERINGS[0].value, 'Landsat (USGS/NASA) &copy; Esri', pane);
            baseLandsat.imageryInfo = { kind: 'landsat' };
            layers['Landsat (histórico)'] = baseLandsat;
            pickers.push({
                layer: baseLandsat,
                label: 'Composição',
                options: LANDSAT_RENDERINGS,
                selected: LANDSAT_RENDERINGS[0].value,
                slow: true,
                onSelect: function (value) {
                    baseLandsat.setRenderingRule(landsatRenderingRule(value));
                },
                // Ano da imagem; as opções vêm do catálogo no centro do mapa
                // (renderInfo, tipo 'landsat'). Sem ano: a melhor cena recente.
                secondary: {
                    label: 'Ano',
                    options: [{ value: '', text: 'Melhor cena recente' }],
                    selected: '',
                    onSelect: function (year) {
                        if (year) {
                            baseLandsat.setTimeRange(new Date(Date.UTC(+year, 0, 1)), new Date(Date.UTC(+year + 1, 0, 1)));
                        } else {
                            baseLandsat.setTimeRange(null, null);
                        }
                    }
                }
            });
        }

        // CBERS-4A (INPE), 2 m: tiles gerados no servidor a partir da cena
        // escolhida; a lista de cenas depende do centro do mapa.
        if (imagery.cbers) {
            var baseCbers = new MinZoomTileLayer(BLANK_TILE, {
                maxZoom: 19, minDataZoom: imagery.cbers.min_zoom, scene: '', realce: '0', pane: pane,
                attribution: 'CBERS-4A &copy; INPE (Brazil Data Cube)'
            });
            baseCbers.imageryInfo = { kind: 'cbers', minZoom: imagery.cbers.min_zoom };
            layers['CBERS-4A (2 m, INPE)'] = baseCbers;
            pickers.push({
                layer: baseCbers,
                template: imagery.cbers.tile_url + ENHANCE_QUERY,
                param: 'scene',
                label: 'Cena CBERS-4A',
                followsCenter: true,
                enhance: {},
                listUrl: function (center) {
                    return imagery.cbers.scenes_url + '?lat=' + center.lat.toFixed(3) + '&lon=' + center.lng.toFixed(3);
                },
                parse: function (json) {
                    return (json.scenes || []).map(function (s) {
                        return { value: s.id, text: formatDateBR(s.date) };
                    });
                }
            });
        }

        // CBERS-2B HRC (INPE), 2,7 m de set/2007 a mar/2010: na 1ª vez o
        // servidor baixa a cena e corrige a posição dela pelo Landsat
        // (cbers2b_service.py), daí o `prepare` antes de pedir os tiles.
        if (imagery.cbers2b) {
            var c2 = imagery.cbers2b;
            var baseCbers2b = new MinZoomTileLayer(BLANK_TILE, {
                maxZoom: 19, minDataZoom: c2.min_zoom, scene: '', comp: 'pan', realce: '0', pane: pane,
                attribution: 'CBERS-2B &copy; INPE (Brazil Data Cube), posição corrigida pelo Landsat (USGS/NASA)'
            });
            baseCbers2b.imageryInfo = { kind: 'cbers2b', minZoom: c2.min_zoom, years: c2.years };
            layers['CBERS-2B (2,7 m, ' + c2.years[0] + '–' + c2.years[1] + ')'] = baseCbers2b;
            var c2Picker = {
                layer: baseCbers2b,
                template: c2.tile_url + ENHANCE_QUERY,
                param: 'scene',
                label: 'Cena CBERS-2B (câmera HRC)',
                emptyText: 'Nenhuma cena CBERS-2B HRC (' + c2.years[0] + '–' + c2.years[1] + ') cobre este ponto.',
                followsCenter: true,
                enhance: {},
                listUrl: function (center) {
                    return c2.scenes_url + '?lat=' + center.lat.toFixed(3) + '&lon=' + center.lng.toFixed(3);
                },
                parse: function (json) {
                    return (json.scenes || []).map(function (s) {
                        return {
                            value: s.id,
                            date: s.date,
                            ready: s.ready,
                            thumbnail: s.thumbnail,
                            text: formatDateBR(s.date) + ' · cena ' + s.name.replace(/_/g, '-') + (s.ready ? ' · já baixada' : '')
                        };
                    });
                },
                // A mais perto do marco de 22/07/2008, entre as já baixadas
                // se houver (abrem na hora; as outras esperam o botão).
                initial: function (options) {
                    var ready = options.filter(function (o) { return o.ready; });
                    var pool = ready.length ? ready : options;
                    var target = Date.UTC(2008, 6, 22);
                    function gap(o) { return Math.abs(Date.parse(o.date) - target); }
                    return pool.reduce(function (best, o) { return gap(o) < gap(best) ? o : best; }).value;
                },
                // Cena ainda não baixada só prepara no botão: trocar de cena no
                // seletor (vendo a miniatura) não dispara downloads à toa.
                prepareOnDemand: true,
                prepareLabel: 'Baixar e corrigir esta cena',
                prepareHint: 'Só na primeira vez: ~20 s (download do INPE e correção da posição pelo Landsat).',
                previewCaption: 'Prévia do INPE (antes da correção de posição)',
                preparingText: 'Preparando a cena…',
                progress: function (scene) {
                    return fetch(c2.progress_url.replace('{scene}', encodeURIComponent(scene)), { credentials: 'same-origin' })
                        .then(function (r) { return r.json(); })
                        .then(function (json) { return json.etapa || ''; });
                },
                prepare: function (scene) {
                    return fetch(c2.prepare_url.replace('{scene}', encodeURIComponent(scene)), {
                        method: 'POST', credentials: 'same-origin', headers: { 'X-CSRFToken': csrfToken() }
                    }).then(function (r) {
                        return r.json().catch(function () { return null; }).then(function (json) {
                            if (r.ok && json) return json;
                            var reason = r.status === 403 ? 'sessão expirada ou página antiga; recarregue a página'
                                : 'erro ' + r.status + ' do servidor';
                            throw new Error((json && json.erro) || 'Não foi possível preparar a cena (' + reason + ').');
                        });
                    }, function () {
                        throw new Error('Não foi possível preparar a cena (sem resposta do servidor). Clique de novo para tentar outra vez.');
                    });
                },
                // Composições que a cena tem (sem CCD do mesmo dia, só a
                // pancromática). Começa na cor natural, até o usuário escolher.
                onPrepared: function (info) {
                    var sec = c2Picker.secondary;
                    sec.options = info.compositions;
                    var has = function (v) { return info.compositions.some(function (c) { return c.value === v; }); };
                    if (!sec.touched || !has(sec.selected)) sec.selected = has('cor') ? 'cor' : 'pan';
                    baseCbers2b.options.comp = sec.selected;
                },
                secondary: {
                    label: 'Composição',
                    options: [{ value: 'pan', text: 'Pancromática (preto e branco)' }],
                    selected: 'pan',
                    onSelect: function (comp) {
                        c2Picker.secondary.touched = true;
                        baseCbers2b.options.comp = comp;
                        baseCbers2b.redraw();
                    }
                }
            };
            pickers.push(c2Picker);
        }

        // Landsat 4/5/7 de 1984 a 2012 (Planetary Computer), 30 m: as cenas
        // de menos nuvem de cada ano no centro do mapa; começa na melhor de
        // 2008 (marco de 22/07/2008 do Código Florestal).
        if (imagery.landsat_legacy) {
            var ll = imagery.landsat_legacy;
            var baseLandsatLegacy = L.tileLayer(BLANK_TILE, {
                maxZoom: 19, maxNativeZoom: ll.max_native_zoom, scene: '', comp: ll.compositions[0].value, realce: '0', pane: pane,
                attribution: 'Landsat (USGS/NASA) via Microsoft Planetary Computer'
            });
            baseLandsatLegacy.imageryInfo = { kind: 'landsat_legacy', years: ll.years };
            layers['Landsat 5/7 (' + ll.years[0] + '–' + ll.years[1] + ')'] = baseLandsatLegacy;
            pickers.push({
                layer: baseLandsatLegacy,
                template: ll.tile_url + ENHANCE_QUERY,
                param: 'scene',
                label: 'Cena (ano · data · satélite · nuvens)',
                followsCenter: true,
                // Com realce o servidor interpola até o zoom 17 (sem ele, o
                // navegador amplia o pixel de 30 m a partir do 15).
                enhance: { maxZoom: ll.enhanced_max_zoom },
                listUrl: function (center) {
                    return ll.scenes_url + '?lat=' + center.lat.toFixed(3) + '&lon=' + center.lng.toFixed(3);
                },
                parse: function (json) {
                    return (json.scenes || []).map(function (s) {
                        var sat = s.platform.replace('landsat-', 'Landsat ');
                        var stripes = s.platform === 'landsat-7' && +s.date.slice(0, 4) >= 2003 ? ' (com faixas)' : '';
                        return {
                            value: s.id,
                            year: s.date.slice(0, 4),
                            text: s.date.slice(0, 4) + ' · ' + formatDateBR(s.date).slice(0, 5) + ' · ' + sat + stripes + ' · ' + s.cloud + '% nuvens',
                            sceneText: formatDateBR(s.date) + ' · ' + sat + stripes,
                            cloud: s.cloud,
                            // apply() copia para o maxNativeZoom da camada.
                            maxZoom: ll.max_native_zoom
                        };
                    });
                },
                // Primeira cena de 2008 da lista (a de menos nuvem fica entre
                // as 5 do ano); sem 2008 ali, a mais recente.
                initial: function (options) {
                    var y2008 = options.filter(function (o) { return o.year === '2008'; });
                    if (!y2008.length) return null;
                    return y2008.reduce(function (best, o) { return o.cloud < best.cloud ? o : best; }).value;
                },
                secondary: {
                    label: 'Composição',
                    options: ll.compositions,
                    selected: ll.compositions[0].value,
                    onSelect: function (comp) {
                        baseLandsatLegacy.options.comp = comp;
                        baseLandsatLegacy.redraw();
                    }
                }
            });
        }

        // Uso do solo do MapBiomas como mapa base: só no lado direito da
        // comparação (no mapa principal ele é camada temática, por cima).
        if (opts.withMapbiomas && imagery.mapbiomas) {
            var mb = imagery.mapbiomas;
            var years = mb.products.cobertura.years;
            var baseMapbiomas = new MinZoomTileLayer(BLANK_TILE, {
                maxZoom: 19, maxNativeZoom: 15, minDataZoom: mb.min_zoom, year: '', pane: pane,
                attribution: 'MapBiomas'
            });
            baseMapbiomas.imageryInfo = { kind: 'mapbiomas', minZoom: mb.min_zoom };
            layers['MapBiomas – uso do solo'] = baseMapbiomas;
            pickers.push({
                layer: baseMapbiomas,
                template: mb.tile_url.replace('{product}', 'cobertura'),
                param: 'year',
                label: 'Ano (MapBiomas)',
                options: years.map(function (y) { return { value: String(y), text: String(y) }; })
            });
        }

        layers['OpenStreetMap'] = baseOSM;
        layers['Carto Light'] = baseCartoLight;
        layers['OpenTopoMap'] = baseTopo;

        return {
            layers: layers,
            defaultLayer: baseEsriSat,
            pickers: pickers
        };
    }

    // Metros por pixel de um tile Web Mercator de 256 px no zoom e latitude dados.
    function metersPerPixel(zoom, lat) {
        return 156543.03392 * Math.cos(lat * Math.PI / 180) / Math.pow(2, zoom);
    }

    function formatMeters(m) {
        return m.toLocaleString('pt-BR', { maximumFractionDigits: m < 1 ? 2 : 1 }) + ' m';
    }

    function formatDistance(m) {
        return m < 1000 ? formatMeters(m) : (m / 1000).toLocaleString('pt-BR', { maximumFractionDigits: 1 }) + ' km';
    }

    /**
     * Atributos da imagem da Esri no ponto (sensor, data de captura,
     * resolução), do serviço de metadados de cada versão da World Imagery.
     * As camadas do serviço vão de 0 (1,9 cm, zoom 23) a 13 (150 m, zoom ≤ 10);
     * sem imagem naquele nível, tenta os dois mais grosseiros.
     */
    function queryEsriMetadata(metadataUrl, latlng, zoom) {
        var first = Math.max(0, Math.min(13, 23 - Math.round(zoom)));
        function attempt(layerId) {
            if (layerId > Math.min(13, first + 2)) return Promise.resolve(null);
            var params = pointQuery(latlng, { outFields: 'SRC_DATE2,SRC_RES,SRC_ACC,SRC_DESC,NICE_DESC' });
            return fetch(metadataUrl + '/' + layerId + '/query?' + params)
                .then(function (r) { return r.json(); })
                .then(function (json) {
                    var f = json.features && json.features[0];
                    return f ? f.attributes : attempt(layerId + 1);
                });
        }
        return attempt(first);
    }

    /**
     * Cena do Sentinel-2 desenhada no ponto: o serviço monta o mosaico pelo
     * campo `best` (menor primeiro), então a primeira por `best` é a visível.
     */
    function querySentinel2Scene(latlng) {
        var params = pointQuery(latlng, {
            where: 'category = 1',
            outFields: 'acquisitiondate,cloudcover',
            orderByFields: 'best',
            resultRecordCount: '1'
        });
        return fetch(SENTINEL2_URL + '/query?' + params)
            .then(function (r) { return r.json(); })
            .then(function (json) {
                var f = json.features && json.features[0];
                return f ? f.attributes : null;
            });
    }

    /**
     * Cenas Landsat no ponto (todas as datas; algumas centenas). Servem para
     * os anos do seletor e para achar a cena visível: o mosaico usa a de
     * menor `Best` dentro do ano escolhido (ou de todas, sem ano).
     */
    function queryLandsatScenes(latlng) {
        var params = pointQuery(latlng, {
            where: 'Category = 1',
            outFields: 'AcquisitionDate,CloudCover,SensorName,Best',
            resultRecordCount: '2000'
        });
        return fetch(LANDSAT_URL + '/query?' + params)
            .then(function (r) { return r.json(); })
            .then(function (json) {
                return (json.features || []).map(function (f) { return f.attributes; });
            });
    }

    function sceneYear(scene) {
        return String(new Date(scene.AcquisitionDate).getUTCFullYear());
    }

    function esriInfoLines(a) {
        var lines = [];
        if (a.SRC_RES) lines.push('Resolução: ' + formatMeters(a.SRC_RES));
        if (a.SRC_DATE2) lines.push('Captura: ' + new Date(a.SRC_DATE2).toLocaleDateString('pt-BR', { timeZone: 'UTC' }));
        var fonte = [a.SRC_DESC, a.NICE_DESC].filter(Boolean).join(' · ');
        if (fonte) lines.push('Fonte: ' + fonte);
        if (a.SRC_ACC) lines.push('Precisão posicional: ±' + formatMeters(a.SRC_ACC));
        return lines;
    }

    var LAYERS_ICON = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m12 3.5 8.5 4.5L12 12.5 3.5 8z"/><path d="m3.5 12.5 8.5 4.5 8.5-4.5M3.5 16.5 12 21l8.5-4.5"/></svg>';

    var PANEL_TABS = [
        { key: 'analise', label: 'Análise' },
        { key: 'imagem', label: 'Imagem' },
        { key: 'tematicas', label: 'Temáticas' }
    ];

    /**
     * Painel lateral do mapa (canto superior direito) que reúne, em abas, as
     * bases da análise, o mapa base/imagem de satélite e as camadas
     * temáticas. Fica dentro do mapa para continuar visível em tela cheia;
     * em mapas estreitos (celular) começa recolhido.
     *
     * `opts.tabs`/`opts.openLabel` montam outro painel com as mesmas
     * peças (o do lado direito da comparação).
     *
     * Devolve { section(aba), show(aba), open(aba), setOpen(bool),
     * setComparing(bool), setPosition(canto), remove() }.
     */
    function setupMapPanel(map, opts) {
        opts = opts || {};
        var panelTabs = opts.tabs || PANEL_TABS;
        var root, box, body, sections = {}, tabs = {};
        var control = L.control({ position: 'topright' });

        control.onAdd = function () {
            root = L.DomUtil.create('div', 'map-panel');

            var openBtn = L.DomUtil.create('button', 'map-panel-open', root);
            openBtn.type = 'button';
            openBtn.title = opts.openTitle || 'Mostrar bases, imagens e camadas';
            openBtn.innerHTML = LAYERS_ICON + '<span>' + (opts.openLabel || 'Camadas') + '</span>';
            openBtn.addEventListener('click', function () { setOpen(true); });

            box = L.DomUtil.create('div', 'map-panel-box', root);
            var head = L.DomUtil.create('div', 'map-panel-head', box);
            var tablist = L.DomUtil.create('div', 'map-panel-tabs', head);
            tablist.setAttribute('role', 'tablist');
            var closeBtn = L.DomUtil.create('button', 'map-panel-close', head);
            closeBtn.type = 'button';
            closeBtn.title = 'Recolher painel';
            closeBtn.setAttribute('aria-label', 'Recolher painel');
            closeBtn.textContent = '×';
            closeBtn.addEventListener('click', function () { setOpen(false); });

            body = L.DomUtil.create('div', 'map-panel-body', box);
            panelTabs.forEach(function (t) {
                var tab = L.DomUtil.create('button', 'map-panel-tab', tablist);
                tab.type = 'button';
                tab.id = 'map-panel-tab-' + t.key;
                tab.textContent = t.label;
                tab.setAttribute('role', 'tab');
                tab.addEventListener('click', function () { show(t.key); });
                var section = L.DomUtil.create('div', 'map-panel-section', body);
                section.setAttribute('role', 'tabpanel');
                section.setAttribute('aria-labelledby', tab.id);
                tabs[t.key] = tab;
                sections[t.key] = section;
            });

            L.DomEvent.disableClickPropagation(root);
            L.DomEvent.disableScrollPropagation(root);
            return root;
        };
        control.addTo(map);

        function show(key) {
            panelTabs.forEach(function (t) {
                var on = t.key === key;
                tabs[t.key].classList.toggle('is-active', on);
                tabs[t.key].setAttribute('aria-selected', String(on));
                sections[t.key].hidden = !on;
            });
            body.scrollTop = 0;
        }

        function setOpen(open) {
            root.classList.toggle('is-open', open);
        }

        // O painel rola por dentro em vez de passar da altura do mapa
        // (deixa espaço para a atribuição no rodapé). No canto esquerdo ele
        // fica abaixo dos botões de zoom/comparar, por isso conta o topo.
        function fit() {
            var top = root.getBoundingClientRect().top - map.getContainer().getBoundingClientRect().top;
            box.style.maxHeight = Math.max(180, map.getSize().y - Math.max(10, top) - 46) + 'px';
        }

        map.on('resize', fit);
        fit();
        show(panelTabs[0].key);
        setOpen(opts.open !== undefined ? opts.open : map.getSize().x >= 640);

        return {
            section: function (key) { return sections[key]; },
            show: show,
            open: function (key) {
                setOpen(true);
                if (key) show(key);
            },
            setOpen: setOpen,
            setComparing: function (on) { root.classList.toggle('is-comparing', on); },
            // Move o mesmo elemento de canto (control.setPosition rodaria o
            // onAdd de novo e perderia o conteúdo montado nas abas).
            setPosition: function (position) {
                map._controlCorners[position].appendChild(root);
                fit();
            },
            remove: function () {
                map.off('resize', fit);
                control.remove();
            },
            // Margem para o fitBounds não esconder a geometria atrás do painel aberto.
            fitPadding: function (base) {
                var covered = root.classList.contains('is-open') ? root.offsetWidth + 20 : 0;
                return { paddingTopLeft: [base, base], paddingBottomRight: [base + covered, base] };
            }
        };
    }

    /**
     * Lista dos mapas base no painel, separada entre imagens de satélite (as
     * camadas com `imageryInfo`) e mapas de referência. `onChange(camada,
     * linha)` é chamado com o mapa base inicial e a cada troca.
     */
    function setupBaseList(map, baseLayersInfo, mount, onChange) {
        var groups = [
            { title: 'Imagens de satélite', test: function (l) { return !!l.imageryInfo; } },
            { title: 'Mapas de referência', test: function (l) { return !l.imageryInfo; } }
        ];
        var active = baseLayersInfo.defaultLayer;
        var rows = [];

        groups.forEach(function (group) {
            var names = Object.keys(baseLayersInfo.layers).filter(function (n) {
                return group.test(baseLayersInfo.layers[n]);
            });
            if (!names.length) return;
            L.DomUtil.create('div', 'map-panel-subheading', mount).textContent = group.title;
            var list = L.DomUtil.create('div', 'base-list', mount);
            names.forEach(function (name) {
                var layer = baseLayersInfo.layers[name];
                var row = L.DomUtil.create('label', 'base-option', list);
                var radio = L.DomUtil.create('input', '', row);
                radio.type = 'radio';
                radio.name = 'map-base-layer';
                radio.checked = layer === active;
                L.DomUtil.create('span', '', row).textContent = name;
                rows.push({ row: row, layer: layer });
                radio.addEventListener('change', function () {
                    if (!radio.checked || layer === active) return;
                    map.removeLayer(active);
                    active = layer;
                    map.addLayer(layer);
                    select(row);
                });
            });
        });

        function select(row) {
            rows.forEach(function (r) { r.row.classList.toggle('is-active', r.layer === active); });
            onChange(active, row);
        }

        var initial = rows.find(function (r) { return r.layer === active; });
        if (initial) select(initial.row);
    }

    /**
     * Detalhes da imagem de satélite ativa, montados em `opts.mount` (no
     * painel lateral) e visíveis quando o mapa base tem `imageryInfo`:
     * seletor de mosaico/data (Planet, Wayback, CBERS...) e a resolução da
     * imagem no centro do mapa. A lista do seletor é buscada na primeira
     * ativação (ou ao abrir o mapa, nas fontes com `prefetch`).
     *
     * `opts.idSuffix` deixa os ids únicos quando há dois painéis
     * (comparação); `opts.chooser` ({nome: camada}) e `opts.onChoose(camada)`
     * põem no topo um seletor de qual imagem mostrar (lado direito da
     * comparação).
     *
     * Devolve { element, activate(camada), destroy() }: quem troca o mapa
     * base avisa o painel por `activate`.
     */
    function setupImageryPanel(map, baseLayersInfo, opts) {
        opts = opts || {};
        var suffix = opts.idSuffix || '';
        var pickers = baseLayersInfo.pickers;
        var wayback = pickers.find(function (p) { return p.param === 'release'; });
        var activeBase = opts.initial || baseLayersInfo.defaultLayer;
        var infoSeq = 0, infoTimer = null;

        var container, chooserEl, labelEl, selectEl, subLabelEl, subSelectEl, enhanceEl, enhanceInput, statusEl, infoEl;
        var previewEl, previewImg, previewCaption, prepareBtn, prepareHint;
        var current = null;

        (function build() {
            container = L.DomUtil.create('div', 'imagery-picker', opts.mount);
            if (opts.chooser) {
                var chooserLabel = L.DomUtil.create('label', 'imagery-picker-label imagery-picker-side', container);
                chooserLabel.textContent = opts.chooserLabel || 'Imagem';
                chooserEl = L.DomUtil.create('select', 'imagery-picker-select', container);
                chooserEl.id = 'imagery-picker-chooser' + suffix;
                chooserLabel.setAttribute('for', chooserEl.id);
                Object.keys(opts.chooser).forEach(function (name) {
                    var o = document.createElement('option');
                    o.value = name;
                    o.textContent = name;
                    chooserEl.appendChild(o);
                });
                chooserEl.addEventListener('change', function () {
                    opts.onChoose(opts.chooser[chooserEl.value]);
                });
            }
            labelEl = L.DomUtil.create('label', 'imagery-picker-label', container);
            selectEl = L.DomUtil.create('select', 'imagery-picker-select', container);
            // Segundo seletor (ex.: ano do Landsat), só nas fontes com `secondary`.
            subLabelEl = L.DomUtil.create('label', 'imagery-picker-label', container);
            subSelectEl = L.DomUtil.create('select', 'imagery-picker-select', container);
            // "Melhorar imagem", só nas fontes com `enhance`.
            enhanceEl = L.DomUtil.create('label', 'imagery-picker-enhance', container);
            enhanceEl.title = ENHANCE_HINT;
            enhanceInput = L.DomUtil.create('input', '', enhanceEl);
            enhanceInput.type = 'checkbox';
            L.DomUtil.create('span', '', enhanceEl).textContent = 'Melhorar imagem';
            // Fontes preparadas no servidor sob demanda (CBERS-2B): miniatura
            // da cena escolhida e o botão que dispara o preparo.
            previewEl = L.DomUtil.create('figure', 'imagery-picker-preview', container);
            previewImg = L.DomUtil.create('img', '', previewEl);
            previewImg.alt = '';
            previewImg.loading = 'lazy';
            previewCaption = L.DomUtil.create('figcaption', '', previewEl);
            prepareBtn = L.DomUtil.create('button', 'imagery-picker-button', container);
            prepareBtn.type = 'button';
            prepareHint = L.DomUtil.create('div', 'imagery-picker-hint', container);
            statusEl = L.DomUtil.create('div', 'imagery-picker-status', container);
            infoEl = L.DomUtil.create('div', 'imagery-picker-info', container);
            selectEl.id = 'imagery-picker-select' + suffix;
            labelEl.setAttribute('for', selectEl.id);
            subSelectEl.id = 'imagery-picker-sub' + suffix;
            subLabelEl.setAttribute('for', subSelectEl.id);
            container.style.display = 'none';
            L.DomEvent.disableClickPropagation(container);
            L.DomEvent.disableScrollPropagation(container);
            selectEl.addEventListener('change', function () {
                if (current) apply(current, selectEl.value);
            });
            subSelectEl.addEventListener('change', function () {
                if (!current || !current.secondary) return;
                current.secondary.selected = subSelectEl.value;
                current.secondary.onSelect(subSelectEl.value);
                refreshInfo();
            });
            enhanceInput.addEventListener('change', function () {
                if (current && current.enhance) setEnhanced(current, enhanceInput.checked);
            });
            prepareBtn.addEventListener('click', function () {
                if (!current || !current.prepare || current.preparing) return;
                prepareAndShow(current, current.selected, selectedOption(current) || {});
            });
        })();

        function selectedOption(picker) {
            if (!picker || !picker.options) return null;
            return picker.options.find(function (o) { return o.value === picker.selected; }) || null;
        }

        // Zoom nativo da opção, ou o do realce (Landsat: 17) com ele ligado.
        function nativeZoom(picker, opt) {
            return picker.enhanced && picker.enhance.maxZoom ? picker.enhance.maxZoom : opt.maxZoom;
        }

        function showLayerOption(picker, value, opt) {
            picker.layer.options[picker.param] = value;
            picker.layer.options.maxNativeZoom = nativeZoom(picker, opt);
            // setUrl não redesenha quando a URL-modelo é a mesma; aqui só
            // muda o parâmetro ({layer}/{release}), então o redraw é explícito.
            picker.layer.setUrl(picker.template, true);
            picker.layer.redraw();
        }

        function apply(picker, value) {
            var opt = picker.options.find(function (o) { return o.value === value; }) || {};
            picker.selected = value;
            if (picker.prepare && picker.prepared !== value) {
                if (opt.ready || !picker.prepareOnDemand) {
                    prepareAndShow(picker, value, opt);
                } else {
                    // Espera o botão "Baixar e corrigir": a camada fica vazia e
                    // a miniatura mostra a cena (nuvem?) antes do download.
                    picker.prepareSeq = (picker.prepareSeq || 0) + 1;
                    picker.preparing = false;
                    picker.prepared = null;
                    picker.info = null;
                    picker.status = '';
                    picker.layer.setUrl(BLANK_TILE);
                    if (current === picker) setStatus('');
                }
                if (current === picker) fillPrepare(picker);
            } else if (picker.onSelect) {
                picker.onSelect(value);
            } else {
                showLayerOption(picker, value, opt);
            }
            refreshInfo();
        }

        // Fontes que o servidor precisa preparar antes dos tiles (CBERS-2B):
        // a camada fica vazia até `prepare` responder; numa troca de cena no
        // meio do caminho, só vale a resposta da última.
        function prepareAndShow(picker, value, opt) {
            var seq = picker.prepareSeq = (picker.prepareSeq || 0) + 1;
            picker.preparing = true;
            picker.prepared = null;
            picker.info = null;
            picker.status = picker.preparingText;
            picker.layer.setUrl(BLANK_TILE);
            if (current === picker) {
                setStatus(picker.status);
                fillPrepare(picker);
            }
            // Etapa do servidor ("Baixando… 35 de 56 MB") enquanto espera.
            var poll = picker.progress && setInterval(function () {
                picker.progress(value).then(function (step) {
                    if (seq !== picker.prepareSeq || !picker.preparing || !step) return;
                    picker.status = step;
                    if (current === picker) setStatus(step);
                }, function () {});
            }, 1500);
            function finish() {
                clearInterval(poll);
                picker.preparing = false;
                if (current === picker) fillPrepare(picker);
            }
            picker.prepare(value).then(function (info) {
                if (seq !== picker.prepareSeq) return;
                picker.prepared = value;
                picker.info = info;
                picker.status = '';
                finish();
                // Na próxima vez abre direto (e a lista diz que já está baixada).
                if (!opt.ready && opt.text) {
                    opt.ready = true;
                    opt.text += ' · já baixada';
                    if (current === picker) fillSelect(picker);
                }
                if (picker.onPrepared) picker.onPrepared(info);
                if (current === picker) {
                    setStatus('');
                    fillSecondary(picker);
                }
                showLayerOption(picker, value, opt);
            }, function (err) {
                if (seq !== picker.prepareSeq) return;
                finish();
                picker.status = err.message;
                if (current === picker) setStatus(picker.status);
            }).then(refreshInfo);
        }

        // Miniatura da cena escolhida e o botão de preparo (só nas fontes com
        // `prepareOnDemand`, enquanto a cena não está pronta).
        function fillPrepare(picker) {
            var opt = picker && picker.prepareOnDemand ? selectedOption(picker) : null;
            previewEl.style.display = opt && opt.thumbnail ? '' : 'none';
            if (opt && opt.thumbnail) {
                if (previewImg.src !== opt.thumbnail) previewImg.src = opt.thumbnail;
                previewCaption.textContent = picker.previewCaption;
            }
            var waiting = !!opt && picker.prepared !== picker.selected && !picker.preparing;
            prepareBtn.style.display = waiting ? '' : 'none';
            prepareHint.style.display = waiting ? '' : 'none';
            if (waiting) {
                prepareBtn.textContent = picker.prepareLabel;
                prepareHint.textContent = picker.prepareHint;
            }
        }

        function setEnhanced(picker, on) {
            picker.enhanced = on;
            picker.layer.options.realce = on ? '1' : '0';
            picker.layer.options.maxNativeZoom = nativeZoom(picker, selectedOption(picker) || {});
            picker.layer.redraw();
            refreshInfo();
        }

        function fillEnhance(picker) {
            enhanceEl.style.display = picker && picker.enhance ? '' : 'none';
            enhanceInput.checked = !!(picker && picker.enhanced);
        }

        function setInfo(lines) {
            // Com realce, avisa antes da linha do zoom o que foi feito na imagem.
            if (current && current.enhanced && lines.length) {
                lines = lines.slice(0, -1).concat('Realce ligado: contraste, interpolação e nitidez (sem criar detalhes).', lines.slice(-1));
            }
            infoEl.innerHTML = '';
            lines.forEach(function (text, i) {
                var line = document.createElement('div');
                line.textContent = text;
                if (i === lines.length - 1) line.className = 'imagery-picker-zoom';
                infoEl.appendChild(line);
            });
        }

        // Última linha do painel: quanto vale 1 px da tela agora, e se o
        // zoom já passou da resolução da imagem (pixels ampliados).
        function zoomLine(resolution) {
            var px = metersPerPixel(map.getZoom(), map.getCenter().lat);
            var text = 'Zoom atual: 1 px ≈ ' + formatMeters(px);
            if (resolution && px < resolution / 2) text += ' (ampliado além da resolução)';
            return text;
        }

        function refreshInfo() {
            clearTimeout(infoTimer);
            infoTimer = setTimeout(renderInfo, 400);
        }

        // CBERS-2B: resolução conforme a composição e, da cena preparada, o
        // resultado da correção de posição (é o que diz se dá para sobrepor
        // o CAR) e por que não há cor, quando for o caso.
        function cbers2bInfoLines(picker, info) {
            var scene = selectedOption(picker);
            var details = picker.prepared === picker.selected ? picker.info : null;
            var pan = picker.secondary.selected === 'pan';
            var lines = ['Resolução: 2,7 m' + (pan ? ' (pancromática)' : ' (detalhe do HRC; cor do CCD de 20 m da mesma passagem)')];
            if (scene) {
                lines.push('Cena: ' + formatDateBR(scene.date) + ' · CBERS-2B (câmera HRC)');
            } else if (picker.options && !picker.options.length) {
                lines.push('Nenhuma cena CBERS-2B HRC (' + info.years[0] + '–' + info.years[1] + ') cobre este ponto.');
            }
            if (details) {
                var reg = details.registration;
                if (reg.ok) {
                    lines.push('Posição corrigida pelo ' + reg.reference.platform.replace('landsat-', 'Landsat ') + ' de ' +
                        formatDateBR(reg.reference.date) + ': estava ' + formatDistance(reg.shift_m) +
                        ' fora do lugar; erro restante ≈ ' + formatMeters(reg.residual_m) + '.');
                } else {
                    lines.push('⚠ Posição não corrigida: ' + reg.reason + ' A imagem pode estar até ~3 km fora do lugar; não use para sobrepor o CAR.');
                }
                if (!details.fusion) lines.push('Só em preto e branco: ' + details.fusion_note);
            }
            lines.push('Fonte: INPE – Brazil Data Cube (nível 2)');
            if (map.getZoom() < info.minZoom) lines.push('Aproxime o mapa (zoom ' + info.minZoom + '+) para ver a imagem.');
            return lines.concat(zoomLine(2.7));
        }

        function renderInfo() {
            var info = activeBase && activeBase.imageryInfo;
            if (!info) return;
            var seq = ++infoSeq;

            if (info.kind === 'text') {
                setInfo([info.text, zoomLine()]);
                return;
            }

            if (info.kind === 'provider') {
                var mosaic = selectedOption(current);
                if (!mosaic) { setInfo([]); return; }
                if (mosaic.maxZoom === undefined || mosaic.maxZoom === null) {
                    setInfo([info.resolutionHint || 'Resolução não informada pelo serviço.', zoomLine()]);
                    return;
                }
                var res = metersPerPixel(mosaic.maxZoom, map.getCenter().lat);
                setInfo(['Resolução: ~' + formatMeters(res) + ' (pixel do mosaico)', zoomLine(res)]);
                return;
            }

            // Lista de cenas que depende do lugar (CBERS, Landsat 5/7): vale
            // para onde foi pedida; longe dali (o usuário arrastou o mapa),
            // busca de novo.
            if (current && current.followsCenter && current.listCenter && !current.loading &&
                    map.getCenter().distanceTo(current.listCenter) > 20000) {
                current.options = null;
                show(current);
            }

            if (info.kind === 'cbers') {
                var cbers = current;
                var scene = selectedOption(cbers);
                var cbersLines = ['Resolução: 2 m'];
                if (scene) {
                    cbersLines.push('Cena: ' + scene.text);
                } else if (cbers.options && !cbers.options.length) {
                    cbersLines.push('Nenhuma cena CBERS-4A cobre este ponto.');
                }
                cbersLines.push('Satélite: CBERS-4A (câmera WPM)', 'Fonte: INPE – Brazil Data Cube');
                if (map.getZoom() < info.minZoom) cbersLines.push('Aproxime o mapa (zoom ' + info.minZoom + '+) para ver a imagem.');
                setInfo(cbersLines.concat(zoomLine(2)));
                return;
            }

            if (info.kind === 'cbers2b') {
                setInfo(cbers2bInfoLines(current, info));
                return;
            }

            if (info.kind === 'landsat_legacy') {
                var legacy = current;
                var legacyScene = selectedOption(legacy);
                var legacyLines = ['Resolução: 30 m'];
                if (legacyScene) {
                    legacyLines.push('Cena: ' + legacyScene.sceneText, 'Nuvens na cena: ' + legacyScene.cloud + '%');
                    if (/com faixas/.test(legacyScene.sceneText)) legacyLines.push('Landsat 7 após 2003: faixas sem imagem (falha do SLC).');
                } else if (legacy.options && !legacy.options.length) {
                    legacyLines.push('Nenhuma cena de ' + info.years[0] + '–' + info.years[1] + ' com menos de 40% de nuvens neste ponto.');
                }
                legacyLines.push('Fonte: Landsat Collection 2 (USGS/NASA) – Microsoft Planetary Computer');
                setInfo(legacyLines.concat(zoomLine(30)));
                return;
            }

            if (info.kind === 'mapbiomas') {
                var mbLines = ['Resolução: 30 m', 'Ano: ' + (current && current.selected || ''), 'Fonte: MapBiomas Coleção 11'];
                if (map.getZoom() < info.minZoom) mbLines.push('Aproxime o mapa (zoom ' + info.minZoom + '+) para ver o mapa.');
                mbLines.push('Legenda: em "Camadas temáticas".');
                setInfo(mbLines.concat(zoomLine(30)));
                return;
            }

            if (info.kind === 'sentinel2') {
                var rendering = selectedOption(current) || {};
                var resLine = 'Resolução: ' + formatMeters(rendering.res) + (rendering.res > 10 ? ' (bandas SWIR)' : '');
                setInfo([resLine, 'Consultando data da cena…', zoomLine(rendering.res)]);
                querySentinel2Scene(map.getCenter())
                    .then(function (a) {
                        if (seq !== infoSeq) return;
                        var lines = [resLine];
                        if (a && a.acquisitiondate) {
                            lines.push('Cena: ' + new Date(a.acquisitiondate).toLocaleDateString('pt-BR', { timeZone: 'UTC' }));
                            if (a.cloudcover !== null && a.cloudcover !== undefined) {
                                lines.push('Nuvens na cena: ' + Math.round(a.cloudcover * 100) + '%');
                            }
                        } else {
                            lines.push('Sem cena para este ponto.');
                        }
                        lines.push('Fonte: Sentinel-2 (Copernicus/ESA)');
                        setInfo(lines.concat(zoomLine(rendering.res)));
                    })
                    .catch(function () {
                        if (seq === infoSeq) setInfo([resLine, 'Data da cena indisponível.', zoomLine(rendering.res)]);
                    });
                return;
            }

            if (info.kind === 'landsat') {
                var landsat = current;
                var comp = selectedOption(landsat) || {};
                var year = landsat.secondary.selected;
                var thermal = comp.value === LANDSAT_THERMAL;
                var resText = 'Resolução: ' + formatMeters(comp.res) + (thermal ? ' (banda térmica)' : '');
                setInfo([resText, 'Consultando cena…', zoomLine(comp.res)]);
                queryLandsatScenes(map.getCenter())
                    .then(function (scenes) {
                        if (seq !== infoSeq) return;
                        updateLandsatYears(landsat, scenes);
                        var pool = year ? scenes.filter(function (s) { return sceneYear(s) === year; }) : scenes;
                        var scene = pool.reduce(function (best, s) { return (!best || s.Best < best.Best) ? s : best; }, null);
                        var lines = [resText];
                        if (scene) {
                            var sensor = (scene.SensorName || '').replace(/-/g, ' ');
                            lines.push('Cena: ' + new Date(scene.AcquisitionDate).toLocaleDateString('pt-BR', { timeZone: 'UTC' }));
                            lines.push('Satélite: ' + sensor);
                            // GLS antigo traz -0,01 quando a cobertura não foi medida.
                            if (scene.CloudCover >= 0) lines.push('Nuvens na cena: ' + Math.round(scene.CloudCover * 100) + '%');
                            if (thermal && !/landsat [89]/i.test(sensor)) {
                                lines.push('Temperatura só existe no Landsat 8/9 (2013+).');
                            } else if (thermal) {
                                lines.push('Escala: ' + THERMAL_MIN + ' °C (azul) → ' + THERMAL_MAX + ' °C (vermelho)');
                            }
                        } else {
                            lines.push(year ? 'Sem cena de ' + year + ' neste ponto.' : 'Sem cena para este ponto.');
                        }
                        lines.push('Fonte: Landsat (USGS/NASA)');
                        setInfo(lines.concat(zoomLine(comp.res)));
                    })
                    .catch(function () {
                        if (seq === infoSeq) setInfo([resText, 'Catálogo do Landsat indisponível.', zoomLine(comp.res)]);
                    });
                return;
            }

            // Esri: a imagem atual é a da versão mais recente da Wayback.
            var release = activeBase === baseLayersInfo.defaultLayer
                ? (wayback && wayback.options && wayback.options[0])
                : selectedOption(current);
            if (!release || !release.metadataUrl) {
                // Lista de datas ainda chegando: load() chama refreshInfo depois.
                setInfo(wayback && wayback.options ? ['Resolução não disponível.', zoomLine()] : ['Consultando resolução…', zoomLine()]);
                return;
            }
            setInfo(['Consultando resolução…', zoomLine()]);
            queryEsriMetadata(release.metadataUrl, map.getCenter(), map.getZoom())
                .then(function (a) {
                    if (seq !== infoSeq) return;
                    setInfo(a ? esriInfoLines(a).concat(zoomLine(a.SRC_RES)) : ['Sem metadados para este ponto.', zoomLine()]);
                })
                .catch(function () {
                    if (seq === infoSeq) setInfo(['Metadados da Esri indisponíveis.', zoomLine()]);
                });
        }

        // Anos com cena no centro do mapa, do mais recente ao mais antigo. O
        // ano escolhido continua na lista mesmo se não houver cena aqui.
        function updateLandsatYears(picker, scenes) {
            var counts = {};
            scenes.forEach(function (s) { var y = sceneYear(s); counts[y] = (counts[y] || 0) + 1; });
            var selected = picker.secondary.selected;
            if (selected && !counts[selected]) counts[selected] = 0;
            picker.secondary.options = [{ value: '', text: 'Melhor cena recente' }].concat(
                Object.keys(counts).sort().reverse().map(function (y) {
                    return { value: y, text: y + ' (' + counts[y] + (counts[y] === 1 ? ' cena)' : ' cenas)') };
                })
            );
            if (current === picker) fillSecondary(picker);
        }

        function fillSecondary(picker) {
            var sec = picker && picker.secondary;
            subLabelEl.style.display = sec ? '' : 'none';
            subSelectEl.style.display = sec ? '' : 'none';
            if (!sec) return;
            subLabelEl.textContent = sec.label;
            subSelectEl.innerHTML = '';
            sec.options.forEach(function (opt) {
                var o = document.createElement('option');
                o.value = opt.value;
                o.textContent = opt.text;
                subSelectEl.appendChild(o);
            });
            subSelectEl.value = sec.selected;
        }

        function showBase(layer) {
            activeBase = layer;
            var picker = pickers.find(function (p) { return p.layer === layer; }) || null;
            current = picker;
            if (!layer.imageryInfo) {
                container.style.display = 'none';
                return;
            }
            container.style.display = '';
            if (picker) {
                show(picker);
            } else {
                labelEl.textContent = 'Detalhes da imagem';
                selectEl.style.display = 'none';
                fillSecondary(null);
                fillEnhance(null);
                fillPrepare(null);
                setStatus('');
            }
            refreshInfo();
        }

        function fillSelect(picker) {
            selectEl.innerHTML = '';
            picker.options.forEach(function (opt) {
                var o = document.createElement('option');
                o.value = opt.value;
                o.textContent = opt.text;
                selectEl.appendChild(o);
            });
            selectEl.value = picker.selected;
            selectEl.style.display = picker.options.length ? '' : 'none';
        }

        function setStatus(text) {
            statusEl.textContent = text || '';
            statusEl.style.display = text ? '' : 'none';
        }

        function show(picker) {
            current = picker;
            container.style.display = '';
            labelEl.textContent = picker.label;
            fillSecondary(picker);
            fillEnhance(picker);

            fillPrepare(picker);
            if (picker.options) {
                fillSelect(picker);
                // `status`: preparo da cena no servidor (CBERS-2B) ou o erro dele.
                setStatus(!picker.options.length ? picker.error
                    : (picker.status || (picker.isLoading ? 'Carregando imagem…' : '')));
                return;
            }

            selectEl.style.display = 'none';
            setStatus('Carregando…');
            load(picker);
        }

        function load(picker) {
            if (picker.loading || picker.options) return;
            picker.loading = true;
            var url = picker.listUrl;
            if (typeof url === 'function') {
                // Lista que depende do lugar (cenas CBERS no centro do mapa).
                picker.listCenter = map.getCenter();
                url = url(picker.listCenter);
            }
            picker.failed = false;
            fetch(url, { credentials: 'same-origin' })
                .then(function (r) {
                    // Sessão expirada: o login redireciona para a página de entrada (HTML).
                    if (r.redirected && /\/auth\//.test(r.url)) throw new Error('sua sessão expirou; entre de novo');
                    return r.json().catch(function () { return null; }).then(function (json) {
                        if (!json) throw new Error('o servidor respondeu com erro ' + r.status);
                        return { ok: r.ok, json: json };
                    });
                })
                .then(function (res) {
                    picker.options = picker.parse(res.json);
                    picker.error = res.json.erro || picker.emptyText || 'Nenhuma imagem cobre este ponto.';
                    picker.failed = !res.ok;
                })
                .catch(function (err) {
                    picker.options = [];
                    picker.failed = true;
                    // Sem resposta nenhuma (TypeError do fetch): servidor fora do ar ou reiniciando.
                    var reason = err instanceof TypeError ? 'sem resposta do servidor' : err.message;
                    picker.error = 'Não foi possível carregar a lista de imagens (' + reason + '). Escolha a camada de novo para tentar outra vez.';
                    if (global.console) console.warn('[imagens] lista', url, err);
                })
                .then(function () {
                    picker.loading = false;
                    if (picker.options.length) {
                        // Numa lista recarregada (CBERS), mantém a escolha se ela continua lá.
                        var kept = picker.options.find(function (o) { return o.value === picker.selected; });
                        var initial = !kept && picker.initial ? picker.initial(picker.options) : null;
                        apply(picker, kept ? kept.value : (initial || picker.options[0].value));
                    } else if (picker.backdrop && map.hasLayer(picker.backdrop)) {
                        // Sem datas, o fundo passaria pela imagem histórica.
                        map.removeLayer(picker.backdrop);
                    }
                    if (current === picker) show(picker);
                    // A resolução da Esri atual vem da lista da Wayback.
                    refreshInfo();
                });
        }

        pickers.forEach(function (p) {
            if (p.prefetch) load(p);
            // Lista fixa com URL-modelo (ano do MapBiomas): já nasce com a 1ª opção.
            if (p.options && p.template && !p.selected) apply(p, p.options[0].value);
            if (p.slow) {
                // O 1º 'loading' dispara ao entrar no mapa, antes do
                // baselayerchange; show() lê `isLoading` para não perdê-lo.
                p.layer.on('loading', function () {
                    p.isLoading = true;
                    if (current === p) setStatus('Carregando imagem…');
                });
                p.layer.on('load error', function () {
                    p.isLoading = false;
                    if (current === p) setStatus('');
                });
            }
        });

        function activate(layer) {
            pickers.forEach(function (p) {
                if (p.backdrop && p.layer !== layer && map.hasLayer(p.backdrop)) map.removeLayer(p.backdrop);
            });
            var picker = pickers.find(function (p) { return p.layer === layer; });
            // Lista que falhou (servidor reiniciando, sessão...): tenta de novo.
            if (picker && picker.failed && !picker.loading) picker.options = null;
            // Com a lista já carregada e vazia (falhou no prefetch), sem fundo.
            var semImagens = picker && picker.options && !picker.options.length;
            if (picker && picker.backdrop && !semImagens) picker.backdrop.addTo(map);
            showBase(layer);
        }

        map.on('moveend', refreshInfo);
        showBase(activeBase);

        return {
            element: container,
            activate: activate,
            destroy: function () {
                clearTimeout(infoTimer);
                infoSeq++;
                map.off('moveend', refreshInfo);
                pickers.forEach(function (p) {
                    if (p.backdrop && map.hasLayer(p.backdrop)) map.removeLayer(p.backdrop);
                });
                L.DomUtil.remove(container);
            }
        };
    }

    /**
     * Comparação lado a lado: o mapa principal (mapa base + camadas
     * temáticas) fica à esquerda e uma segunda imagem à direita de uma barra
     * arrastável. Durante ela o painel se duplica: o principal vai para o
     * canto esquerdo (controla o lado esquerdo) e um segundo painel, no
     * canto direito, escolhe a imagem do lado direito.
     * Cada lado é um "pane" do Leaflet recortado com `clip` (CSS) nas
     * coordenadas das camadas.
     */
    var COMPARE_PANE = 'compareRight';
    var THEMATIC_PANE = 'thematic';
    // Abaixo disso os dois painéis abertos cobririam o mapa: começam recolhidos.
    var COMPARE_PANELS_MIN_WIDTH = 900;

    function setupCompare(map, imagery, panel) {
        var state = null;
        var button = L.control({ position: 'topleft' });
        button.onAdd = function () {
            var bar = L.DomUtil.create('div', 'leaflet-bar compare-toggle');
            var link = L.DomUtil.create('a', '', bar);
            link.href = '#';
            link.title = 'Comparar duas imagens lado a lado';
            link.setAttribute('role', 'button');
            link.innerHTML = '<span aria-hidden="true">⇆</span> Comparar';
            L.DomEvent.on(link, 'click', function (e) {
                L.DomEvent.preventDefault(e);
                if (state) { stop(); } else { start(); }
                L.DomUtil[state ? 'addClass' : 'removeClass'](bar, 'active');
            });
            L.DomEvent.disableClickPropagation(bar);
            return bar;
        };
        button.addTo(map);

        function clipRect(pane, side, x) {
            var nw = map.containerPointToLayerPoint([0, 0]);
            var se = map.containerPointToLayerPoint(map.getSize());
            var cx = nw.x + x;
            var rect = side === 'right'
                ? [nw.y, se.x, se.y, cx]
                : [nw.y, cx, se.y, nw.x];
            map.getPane(pane).style.clip = 'rect(' + rect.join('px, ') + 'px)';
        }

        // Camadas temáticas são do lado esquerdo (o mapa principal).
        function leftPanes() {
            return [THEMATIC_PANE, global.THEMATIC_RELIEF_PANE].filter(function (p) { return p && map.getPane(p); });
        }

        function updateClip() {
            if (!state) return;
            var x = state.ratio * map.getSize().x;
            state.divider.style.left = x + 'px';
            clipRect(COMPARE_PANE, 'right', x);
            leftPanes().forEach(function (p) { clipRect(p, 'left', x); });
        }

        function choose(layer) {
            if (state.layer) map.removeLayer(state.layer);
            state.layer = layer;
            map.addLayer(layer);
            state.panel.activate(layer);
            updateClip();
        }

        function start() {
            if (!map.getPane(COMPARE_PANE)) {
                // Acima do mapa base (tilePane, 200), abaixo das temáticas (350).
                map.createPane(COMPARE_PANE).style.zIndex = 300;
            }
            var base = getBaseLayers(imagery, { pane: COMPARE_PANE, noBackdrop: true, withMapbiomas: true });
            var initialName = base.layers['Histórico (Esri Wayback)'] ? 'Histórico (Esri Wayback)' : Object.keys(base.layers)[0];

            var divider = L.DomUtil.create('div', 'compare-divider', map.getContainer());
            var handle = L.DomUtil.create('div', 'compare-handle', divider);
            handle.textContent = '⇆';
            handle.title = 'Arraste para comparar';
            L.DomEvent.disableClickPropagation(divider);
            L.DomEvent.disableScrollPropagation(divider);

            var wide = map.getSize().x >= COMPARE_PANELS_MIN_WIDTH;
            panel.setComparing(true);
            panel.setPosition('topleft');
            panel.show('imagem');
            panel.setOpen(wide);

            var rightPanel = setupMapPanel(map, {
                tabs: [{ key: 'imagem', label: 'Imagem · lado direito' }],
                openLabel: 'Lado direito',
                openTitle: 'Escolher a imagem do lado direito',
                open: wide
            });
            rightPanel.setComparing(true);
            var slot = rightPanel.section('imagem');
            L.DomUtil.create('p', 'map-panel-hint', slot).textContent =
                'Arraste a barra no mapa para comparar com o lado esquerdo (painel à esquerda).';

            state = { ratio: 0.5, divider: divider, layer: null, base: base, rightPanel: rightPanel };
            state.panel = setupImageryPanel(map, base, {
                mount: slot,
                idSuffix: '-direita',
                initial: base.layers[initialName],
                chooser: base.layers,
                chooserLabel: 'Lado direito',
                onChoose: choose
            });
            document.getElementById('imagery-picker-chooser-direita').value = initialName;
            choose(base.layers[initialName]);

            var dragging = false;
            function move(e) {
                if (!dragging) return;
                var rect = map.getContainer().getBoundingClientRect();
                var clientX = e.touches ? e.touches[0].clientX : e.clientX;
                state.ratio = Math.min(0.98, Math.max(0.02, (clientX - rect.left) / rect.width));
                updateClip();
                L.DomEvent.preventDefault(e);
            }
            function end() {
                if (!dragging) return;
                dragging = false;
                map.dragging.enable();
            }
            L.DomEvent.on(handle, 'mousedown touchstart', function (e) {
                dragging = true;
                map.dragging.disable();
                L.DomEvent.preventDefault(e);
            });
            L.DomEvent.on(document, 'mousemove touchmove', move);
            L.DomEvent.on(document, 'mouseup touchend', end);
            state.unbind = function () {
                L.DomEvent.off(document, 'mousemove touchmove', move);
                L.DomEvent.off(document, 'mouseup touchend', end);
            };

            map.on('move zoomend resize', updateClip);
            updateClip();
        }

        function stop() {
            map.off('move zoomend resize', updateClip);
            state.unbind();
            if (state.layer) map.removeLayer(state.layer);
            state.panel.destroy();
            state.rightPanel.remove();
            panel.setComparing(false);
            panel.setPosition('topright');
            panel.setOpen(map.getSize().x >= 640);
            L.DomUtil.remove(state.divider);
            map.getPane(COMPARE_PANE).style.clip = '';
            leftPanes().forEach(function (p) { map.getPane(p).style.clip = ''; });
            state = null;
        }
    }

    /**
     * Initializes the Leaflet map instance with appropriate options based on static mode.
     * @param {string} elementId 
     * @param {boolean} isStatic 
     * @param {object} options 
     * @returns {L.Map}
     */
    function createMapInstance(elementId, isStatic, options) {
        if (isStatic) {
            return L.map(elementId, {
                zoomControl: false,
                attributionControl: false,
                dragging: false,
                scrollWheelZoom: false,
                doubleClickZoom: false,
                boxZoom: false,
                keyboard: false,
                tap: false,
                touchZoom: false,
                fullscreenControl: false
            });
        } else {
            return L.map(elementId, {
                // Canvas em vez de um <path> SVG por polígono: bem mais leve
                // com bases de muitos vértices (MapBiomas, PRODES...).
                preferCanvas: true,
                fullscreenControl: options.fullscreenControl || true,
                scrollWheelZoom: (options.scrollWheelZoom !== undefined) ? options.scrollWheelZoom : true
            });
        }
    }

    /**
     * Generates a random HSL color.
     */
    function getRandomColor() {
        var h = Math.floor(Math.random() * 360);
        var s = Math.floor(Math.random() * 40) + 60; // 60-100%
        var l = Math.floor(Math.random() * 20) + 40; // 40-60%
        return 'hsl(' + h + ',' + s + '%,' + l + '%)';
    }

    /**
     * Processes a single item and adds it to the appropriate layer group.
     */
    function createGeoJsonLayer(item, layersByFonte, overlays, map, allGroup, legend) {
        try {
            var gj = item.gj;
            if (!gj) return;
            
            var geom = typeof gj === 'string' ? JSON.parse(gj) : gj;
            if (!geom) return;

            var f = item.fonte || 'Fonte';
            var isPropriedade = (f === PROPERTY_FONTE);
            var isPonto = (f === POINT_FONTE);

            // Determine color based on source
            var col;
            if (isPropriedade || isPonto) {
                col = item.color || '#000000';
            } else if (f.toLowerCase().indexOf('mapbiomas') !== -1) {
                col = '#ff0000'; // Red for Mapbiomas
            } else if (f.toLowerCase().indexOf('veredas') !== -1) {
                col = '#00ff00'; // Green for Veredas
            } else {
                col = getRandomColor();
            }
            
            var lbl = item.label || '';
            var area = item.area || '';

            // Os grupos só entram no mapa em initImoveisMap: desenhar todas as
            // bases para depois esconder quase todas travava a abertura.
            if (!layersByFonte[f]) {
                layersByFonte[f] = L.featureGroup();
                overlays[f] = layersByFonte[f];
            }

            var isSicar = (f === 'Base de Dados Sicar');
            // isPropriedade already defined above
            var baseFillOpacity = (isSicar || isPropriedade) ? 0 : isPonto ? 0.9 : 0.35;
            var baseWeight = 2;

            var layer = L.geoJSON(geom, {
                style: { color: col, weight: baseWeight, fillColor: col, fillOpacity: baseFillOpacity },
                // Círculo em vez do marcador padrão: aceita setStyle no hover.
                pointToLayer: function (feature, latlng) { return L.circleMarker(latlng, { radius: 8 }); }
            });

            var tt = [lbl || f, area]
                .filter(function (x) { return x && ('' + x).trim() !== ''; })
                .join('<br> Área: ');

            // Bind tooltip and hover effects
            (function (l, tooltipText, isOutline, opacity, weight) {
                l.eachLayer(function (fl) {
                    if (tooltipText) { fl.bindTooltip(tooltipText, { sticky: true }); }
                    fl.on('mouseover', function (e) {
                        e.target.setStyle({ weight: 3, fillOpacity: isOutline ? 0.1 : 0.5 });
                    });
                    fl.on('mouseout', function (e) {
                        e.target.setStyle({ weight: weight, fillOpacity: opacity });
                    });
                });
            })(layer, tt, (isSicar || isPropriedade), baseFillOpacity, baseWeight);

            layer.addTo(layersByFonte[f]);
            allGroup.addLayer(layer);

            if (f && col) {
                legend[f] = col;
            }

        } catch (e) {
            console.error("Error processing item", e);
        }
    }

    /**
     * Iterates over all items to create layers and groups.
     */
    function processItems(items, map) {
        var overlays = {};
        var layersByFonte = {};
        // Fora do mapa: serve só para os limites do fitBounds.
        var allGroup = L.featureGroup();
        var legend = {};

        for (var i = 0; i < items.length; i++) {
            createGeoJsonLayer(items[i], layersByFonte, overlays, map, allGroup, legend);
        }

        return {
            overlays: overlays,
            layersByFonte: layersByFonte,
            allGroup: allGroup,
            legend: legend
        };
    }

    /**
     * Builds the interactive legend.
     */
    function setupLegend(legendEl, legendData, layersByFonte, map) {
        if (!legendEl) return;
        legendEl.innerHTML = '';

        var keys = Object.keys(legendData);
        for (var j = 0; j < keys.length; j++) {
            (function () {
                var k = keys[j];
                var item = document.createElement('button');
                item.type = 'button';
                item.className = 'legend-item';

                // Caixa de seleção visual: marcada enquanto o item não tem `.off`.
                var check = document.createElement('span');
                check.className = 'legend-check';
                check.setAttribute('aria-hidden', 'true');

                var sw = document.createElement('span');
                sw.className = 'legend-swatch';
                sw.style.backgroundColor = legendData[k];

                var lbl = document.createElement('span');
                lbl.className = 'legend-label';
                lbl.textContent = k;

                item.appendChild(check);
                item.appendChild(sw);
                item.appendChild(lbl);

                item.dataset.fonte = k;
                if (!map.hasLayer(layersByFonte[k])) {
                    item.classList.add('off');
                }
                item.addEventListener('click', function () {
                    var fonte = this.dataset.fonte;
                    var grp = layersByFonte[fonte];
                    if (!grp) return;
                    
                    if (map.hasLayer(grp)) {
                        map.removeLayer(grp);
                        this.classList.add('off');
                    } else {
                        map.addLayer(grp);
                        this.classList.remove('off');
                    }
                });
                legendEl.appendChild(item);
            })();
        }
    }

    /**
     * Configures the "Toggle All" button. O contorno da propriedade fica de
     * fora dessa ação — ele é a referência fixa do mapa, não uma "base".
     */
    function setupToggleAll(toggleBtn, layersByFonte, map, legendEl) {
        if (!toggleBtn) return;

        // Clone button to remove old event listeners
        var newBtn = toggleBtn.cloneNode(true);
        toggleBtn.parentNode.replaceChild(newBtn, toggleBtn);
        toggleBtn = newBtn;

        function baseFontes() {
            return Object.keys(layersByFonte).filter(function (f) { return f !== PROPERTY_FONTE; });
        }

        var allOn = baseFontes().some(function (f) { return map.hasLayer(layersByFonte[f]); });
        toggleBtn.textContent = allOn ? 'Desmarcar todas' : 'Marcar todas';

        toggleBtn.addEventListener('click', function () {
            var fontes = baseFontes();
            for (var i = 0; i < fontes.length; i++) {
                var f = fontes[i];
                var grp = layersByFonte[f];
                if (!grp) continue;

                if (allOn) {
                    if (map.hasLayer(grp)) { map.removeLayer(grp); }
                } else {
                    if (!map.hasLayer(grp)) { map.addLayer(grp); }
                }
            }

            if (legendEl) {
                var legendItems = legendEl.querySelectorAll('.legend-item');
                for (var k = 0; k < legendItems.length; k++) {
                    if (legendItems[k].dataset.fonte === PROPERTY_FONTE) continue;
                    if (allOn) { legendItems[k].classList.add('off'); }
                    else { legendItems[k].classList.remove('off'); }
                }
            }

            allOn = !allOn;
            this.textContent = allOn ? 'Desmarcar todas' : 'Marcar todas';
        });
    }

    var DOWNLOAD_ICON = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 4v10.5M8 11l4 4.5 4-4.5"/><path d="M4.5 15.5v3A1.5 1.5 0 0 0 6 20h12a1.5 1.5 0 0 0 1.5-1.5v-3"/></svg>';

    /**
     * Cartão "Baixar esta imagem" da aba Imagem: GeoTIFF do mapa base
     * escolhido (com a data/cena/composição do seletor), no retângulo da
     * propriedade. Um botão no mapa abre o painel direto nele.
     * Ver image_export.js.
     */
    function setupImageDownload(map, layersByFonte, imageryPanel, panel, mount) {
        var card = L.DomUtil.create('div', 'image-download', mount);
        card.innerHTML =
            '<div class="image-download__head">' +
                '<span class="format-badge format-badge--tif">TIF</span>' +
                '<div>' +
                    '<div class="image-download__title">Baixar esta imagem</div>' +
                    '<div class="image-download__source"></div>' +
                '</div>' +
            '</div>' +
            '<ul class="image-download__meta">' +
                '<li>GeoTIFF georreferenciado</li><li>Área da propriedade + margem</li><li>QGIS · ArcGIS</li>' +
            '</ul>' +
            '<button type="button" class="image-download__btn">' + DOWNLOAD_ICON + '<span>Baixar imagem</span></button>' +
            '<div class="image-download__progress" hidden><span></span></div>' +
            '<p class="image-download__status" role="status"></p>';
        var sourceEl = card.querySelector('.image-download__source');
        var btn = card.querySelector('.image-download__btn');
        var btnLabel = btn.querySelector('span');
        var progress = card.querySelector('.image-download__progress');
        var bar = progress.querySelector('span');
        var status = card.querySelector('.image-download__status');
        var base = null, baseName = '', busy = false;

        // Atalho no mapa: abre o painel na aba Imagem, já no cartão.
        var shortcut = L.control({ position: 'topleft' });
        shortcut.onAdd = function () {
            var b = L.DomUtil.create('button', 'map-download-shortcut');
            b.type = 'button';
            b.title = 'Baixar a imagem de satélite desta área';
            b.innerHTML = DOWNLOAD_ICON + '<span>Baixar imagem</span>';
            L.DomEvent.disableClickPropagation(b);
            b.addEventListener('click', function () {
                panel.open('imagem');
                refresh();
                card.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
                card.classList.remove('is-highlighted');
                void card.offsetWidth;  // reinicia a animação
                card.classList.add('is-highlighted');
            });
            return b;
        };
        shortcut.addTo(map);

        function exportable(layer) {
            // Termos do Google não permitem baixar a imagem; mapas de referência não são imagem.
            return !!(layer && layer.imageryInfo && layer.imageryInfo.name !== 'Satélite (Google)' && global.exportBaseImage);
        }

        function areaBounds() {
            var group = layersByFonte[PROPERTY_FONTE];
            if (group && group.getLayers().length) return group.getBounds().pad(0.1);
            group = layersByFonte[POINT_FONTE];
            if (group && group.getLayers().length) return group.getBounds().getCenter().toBounds(1000);
            return map.getBounds();
        }

        // Textos escolhidos nos seletores visíveis (data/cena e composição/ano).
        function selectedTexts() {
            if (imageryPanel.element.style.display === 'none') return [];
            return ['#imagery-picker-select', '#imagery-picker-sub'].map(function (id) {
                var sel = imageryPanel.element.querySelector(id);
                if (!sel || sel.style.display === 'none' || sel.selectedIndex < 0 || !sel.options.length) return '';
                return sel.options[sel.selectedIndex].text;
            }).filter(Boolean);
        }

        function filename() {
            var name = [baseName].concat(selectedTexts()).join(' ')
                .normalize('NFD').replace(/[\u0300-\u036f]/g, '')
                .replace(/[^\w.-]+/g, '_').replace(/^_+|_+$/g, '');
            return (name || 'imagem') + '.tif';
        }

        function setProgress(fraction) {
            progress.hidden = fraction === null;
            bar.style.width = Math.round((fraction || 0) * 100) + '%';
        }

        function setStatus(text, kind) {
            status.textContent = text || '';
            status.className = 'image-download__status' + (kind ? ' is-' + kind : '');
        }

        function refresh() {
            var ok = exportable(base);
            card.classList.toggle('is-disabled', !ok);
            btn.disabled = busy || !ok;
            if (ok) {
                sourceEl.textContent = [baseName].concat(selectedTexts()).join(' · ');
            } else {
                sourceEl.textContent = base && base.imageryInfo
                    ? 'O Google não permite baixar a imagem. Escolha outra fonte acima.'
                    : 'Escolha uma imagem de satélite acima para baixar.';
            }
        }

        // Mudou a data/cena/composição: o cartão mostra o que vai ser baixado.
        imageryPanel.element.addEventListener('change', function () {
            setStatus('');
            refresh();
        });
        card.addEventListener('mouseenter', refresh);

        btn.addEventListener('click', function () {
            if (busy || !exportable(base)) return;
            busy = true;
            refresh();
            card.classList.add('is-busy');
            btnLabel.textContent = 'Preparando…';
            setStatus('');
            setProgress(0);
            var resolution = base.imageryInfo.kind === 'landsat' ? 30 : 10;
            global.exportBaseImage(base, areaBounds(), {
                filename: filename(),
                resolution: resolution,
                onProgress: function (text, fraction) {
                    btnLabel.textContent = text;
                    setProgress(fraction === undefined ? null : fraction);
                }
            }).then(function () {
                setStatus('Imagem salva na pasta de downloads.', 'done');
            }, function (err) {
                setStatus((err && err.message) || 'Não foi possível baixar a imagem.', 'error');
            }).then(function () {
                busy = false;
                card.classList.remove('is-busy');
                btnLabel.textContent = 'Baixar imagem';
                setProgress(null);
                refresh();
            });
        });

        refresh();
        return {
            setBase: function (layer, name) {
                base = layer;
                baseName = (name || '').trim();
                setStatus('');
                refresh();
            }
        };
    }

    // Só um ponto (sem imóvel): limites de tamanho zero levariam ao zoom máximo.
    function fitToItems(map, group, opts) {
        var bounds = group.getBounds();
        if (bounds.getNorthEast().equals(bounds.getSouthWest())) opts.maxZoom = 16;
        map.fitBounds(bounds, opts);
    }

    /**
     * Main entry point for initializing the map.
     */
    global.initImoveisMap = function (items, options) {
        options = options || {};
        var elementId = options.elementId || 'map-imoveis';
        var isStatic = options.isStatic || false;

        if (!items || !items.length) return;
        
        var mapEl = document.getElementById(elementId);
        if (!mapEl) {
            console.warn('Map element not found:', elementId);
            return;
        }

        // 1. Initialize Map
        var map = createMapInstance(elementId, isStatic, options);

        // 2. Base Layers
        var baseLayersInfo = getBaseLayers(isStatic ? {} : options.imagery);
        baseLayersInfo.defaultLayer.addTo(map);

        // 3. Process & Add Items (Overlays)
        var data = processItems(items, map);

        // Por padrão, só o contorno da propriedade fica marcado; as demais
        // bases começam desmarcadas para reduzir poluição visual no mapa.
        // (Mapas estáticos do relatório impresso continuam mostrando tudo,
        // já que lá não há como reativar uma camada escondida.)
        Object.keys(data.layersByFonte).forEach(function (f) {
            if (isStatic || f === PROPERTY_FONTE || f === POINT_FONTE) data.layersByFonte[f].addTo(map);
        });

        // 4. Fit Bounds
        if (data.allGroup.getLayers().length) {
            fitToItems(map, data.allGroup, { padding: [12, 12] });
        }

        // 5. Controls & Legend
        if (!isStatic) {
            // Only add the panel and legend if NOT static
            var panel = setupMapPanel(map);

            // Aba "Análise": bases da análise, ligadas/desligadas pela legenda.
            var analise = panel.section('analise');
            var analiseHead = L.DomUtil.create('div', 'map-panel-heading-row', analise);
            L.DomUtil.create('div', 'map-panel-heading', analiseHead).textContent = 'Bases da análise';
            var toggleAllBtn = L.DomUtil.create('button', 'map-panel-link', analiseHead);
            toggleAllBtn.type = 'button';
            toggleAllBtn.id = 'toggle-all-layers';
            L.DomUtil.create('p', 'map-panel-hint', analise).textContent =
                'Clique em uma base para mostrá-la ou escondê-la no mapa. Passe o mouse sobre um polígono para ver os detalhes.';
            var legendEl = L.DomUtil.create('div', '', analise);
            legendEl.id = 'legend-imoveis';
            setupLegend(legendEl, data.legend, data.layersByFonte, map);
            setupToggleAll(toggleAllBtn, data.layersByFonte, map, legendEl);

            // Aba "Imagem": lista de mapas base, com os detalhes da imagem
            // logo abaixo da opção escolhida (na comparação, é o lado esquerdo).
            var imagem = panel.section('imagem');
            var baseHeading = L.DomUtil.create('div', 'map-panel-heading', imagem);
            baseHeading.innerHTML = 'Mapa base<span class="map-panel-compare-only"> · lado esquerdo</span>';
            var imageryPanel = setupImageryPanel(map, baseLayersInfo, { mount: imagem });
            var imageDownload = setupImageDownload(map, data.layersByFonte, imageryPanel, panel, imagem);
            setupBaseList(map, baseLayersInfo, imagem, function (layer, row) {
                row.parentNode.insertBefore(imageryPanel.element, row.nextSibling);
                imageryPanel.activate(layer);
                imageDownload.setBase(layer, row.textContent);
            });

            // Camadas temáticas (MapBiomas, DETER, focos, relevo) num pane
            // entre o mapa base (200) e os polígonos da análise (400).
            map.createPane(THEMATIC_PANE).style.zIndex = 350;
            var tematicas = panel.section('tematicas');
            L.DomUtil.create('p', 'map-panel-hint', tematicas).textContent =
                'Sobreponha dados de uso do solo, desmatamento, fogo e relevo. Marque uma camada para escolher o período e a opacidade.';
            if (global.setupThematicLayers) global.setupThematicLayers(map, options.imagery || {}, THEMATIC_PANE, tematicas);
            setupCompare(map, options.imagery || {}, panel);

            if (data.allGroup.getLayers().length) {
                fitToItems(map, data.allGroup, panel.fitPadding(12));
            }
        } else {
            // If static, ensure legend is empty
            var legendEl = document.getElementById('legend-imoveis');
            if (legendEl) legendEl.innerHTML = '';
        }

        mapState = {
            map: map,
            layersByFonte: data.layersByFonte,
            legendEl: (!isStatic) ? document.getElementById('legend-imoveis') : null,
            panel: (!isStatic) ? panel : null
        };
    };

    /**
     * Pisca um polígono alternando o estilo (o mapa desenha em canvas, então
     * não há elemento SVG para animar por CSS).
     */
    function flashPath(fl) {
        if (!fl.setStyle) return;
        var original = { weight: fl.options.weight, fillOpacity: fl.options.fillOpacity };
        var blinks = 0;
        var timer = setInterval(function () {
            fl.setStyle(blinks % 2 ? original : { weight: 5, fillOpacity: 0.7 });
            if (++blinks >= 4) {
                clearInterval(timer);
                fl.setStyle(original);
            }
        }, 350);
    }

    /**
     * Centraliza o mapa na geometria de uma fonte/base e, se conseguir
     * identificar o item exato (por rótulo + área), destaca-o e ajusta
     * o zoom nele. Caso não encontre correspondência exata, centraliza
     * em todas as geometrias daquela fonte (degradação segura).
     *
     * @param {string} fonte Nome da base (deve bater com `item.fonte` usado ao montar o mapa).
     * @param {string} label Rótulo do item (item_info/unidade) usado para tentar achar a geometria exata.
     * @param {string|number} areaVal Área formatada com 4 casas decimais, usada como desempate na busca.
     * @returns {boolean} true se a base foi encontrada no mapa (mesmo sem match exato do item).
     */
    global.focusMapLayer = function (fonte, label, areaVal) {
        if (!mapState || !fonte) return false;
        var grp = mapState.layersByFonte[fonte];
        if (!grp) return false;

        // Mostra a base ligada na aba "Análise" (sem abrir o painel recolhido).
        if (mapState.panel) mapState.panel.show('analise');

        if (!mapState.map.hasLayer(grp)) {
            mapState.map.addLayer(grp);
            if (mapState.legendEl) {
                var legendItems = mapState.legendEl.querySelectorAll('.legend-item');
                for (var i = 0; i < legendItems.length; i++) {
                    if (legendItems[i].dataset.fonte === fonte) {
                        legendItems[i].classList.remove('off');
                    }
                }
            }
        }

        var normLabel = (label || '').trim().toLowerCase();
        var normArea = (areaVal || '').toString().trim();
        var target = null;

        grp.eachLayer(function (outerLayer) {
            if (target || !outerLayer.eachLayer) return;
            var matched = false;
            outerLayer.eachLayer(function (fl) {
                if (matched) return;
                var tt = fl.getTooltip ? fl.getTooltip() : null;
                var content = tt ? ('' + tt.getContent()).toLowerCase() : '';
                if (normLabel && content.indexOf(normLabel) !== -1 && (!normArea || content.indexOf(normArea) !== -1)) {
                    matched = true;
                }
            });
            if (matched) target = outerLayer;
        });

        var focusLayer = target || grp;
        if (focusLayer.getBounds) {
            try {
                var fitOpts = mapState.panel ? mapState.panel.fitPadding(24) : { padding: [24, 24] };
                fitOpts.maxZoom = 17;
                mapState.map.fitBounds(focusLayer.getBounds(), fitOpts);
            } catch (e) {
                // geometria sem bounds válidos: mantém o mapa como está
            }
        }

        if (target && target.eachLayer) {
            target.eachLayer(flashPath);
        }

        return true;
    };

})(window);
