/**
 * Camadas temáticas do mapa de resultados, por cima do mapa base:
 * MapBiomas (uso do solo e área queimada, gerados no servidor), DETER e
 * focos de calor (WMS do INPE), declividade (calculada aqui, dos tiles de
 * elevação) e relevo sombreado (Esri).
 *
 * Expõe `setupThematicLayers(map, imagery, pane)`, chamada pelo maps.js.
 */
(function (global) {
    'use strict';

    var TERRARIUM_URL = 'https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png';
    var HILLSHADE_URL = 'https://server.arcgisonline.com/ArcGIS/rest/services/Elevation/World_Hillshade/MapServer/tile/{z}/{y}/{x}';
    var DETER_WMS = [
        { url: 'https://terrabrasilis.dpi.inpe.br/geoserver/deter-cerrado-nb/ows', layer: 'deter_cerrado', since: 2018 },
        { url: 'https://terrabrasilis.dpi.inpe.br/geoserver/deter-amz/ows', layer: 'deter_amz', since: 2016 }
    ];
    var QUEIMADAS_WMS = 'https://terrabrasilis.dpi.inpe.br/queimadas/geoserver/wms';
    var FIRST_FOCOS_YEAR = 1998;

    // Relevo sombreado multiplica as cores do que está embaixo: precisa de
    // pane próprio (o mix-blend-mode vale para o pane inteiro).
    var RELIEF_PANE = 'thematicRelief';

    // Declividade em graus, nas faixas do Código Florestal (Lei 12.651/2012).
    var SLOPE_CLASSES = [
        { max: 15, color: null, label: 'até 15° (sem cor)' },
        { max: 25, color: [255, 214, 0], label: '15° a 25°' },
        { max: 45, color: [255, 128, 0], label: '25° a 45° – uso restrito (art. 11)' },
        { max: 90.1, color: [214, 0, 0], label: 'acima de 45° – APP (art. 4º, V)' }
    ];
    // Zoom em que a declividade é calculada (~38 m por pixel no Tocantins,
    // perto dos 30 m do SRTM). Acima disso o Leaflet amplia; abaixo de
    // SLOPE_MIN_ZOOM as encostas ficam suavizadas demais e não é desenhada.
    var SLOPE_NATIVE_ZOOM = 12;
    var SLOPE_MIN_ZOOM = 11;

    function isoDate(d) {
        return d.toISOString().slice(0, 10);
    }

    function daysAgo(n) {
        var d = new Date();
        d.setUTCDate(d.getUTCDate() - n);
        return d;
    }

    function yearRange(y) {
        return y + '-01-01/' + y + '-12-31';
    }

    function hexToCss(color) {
        return 'rgb(' + color.join(',') + ')';
    }

    /**
     * Declividade calculada no navegador a partir dos tiles de elevação
     * Terrarium (AWS Open Data; SRTM ~30 m no Brasil), pelo método de Horn.
     * Na borda do tile usa o pixel vizinho de dentro (sem buscar o tile ao
     * lado): pode haver uma costura leve.
     */
    var SlopeLayer = L.GridLayer.extend({
        createTile: function (coords, done) {
            var canvas = L.DomUtil.create('canvas', 'leaflet-tile');
            var size = this.getTileSize();
            canvas.width = size.x;
            canvas.height = size.y;
            if (coords.z < SLOPE_MIN_ZOOM) {
                setTimeout(function () { done(null, canvas); }, 0);
                return canvas;
            }
            var img = new Image();
            img.crossOrigin = 'anonymous';
            img.onload = function () {
                try {
                    drawSlope(canvas, img, coords);
                    done(null, canvas);
                } catch (e) {
                    done(e, canvas);
                }
            };
            img.onerror = function () { done(new Error('elevação indisponível'), canvas); };
            img.src = L.Util.template(TERRARIUM_URL, coords);
            return canvas;
        }
    });

    function drawSlope(canvas, img, coords) {
        var w = canvas.width, h = canvas.height;
        var ctx = canvas.getContext('2d');
        ctx.drawImage(img, 0, 0, w, h);
        var src = ctx.getImageData(0, 0, w, h).data;
        var elev = new Float32Array(w * h);
        for (var i = 0; i < w * h; i++) {
            elev[i] = src[i * 4] * 256 + src[i * 4 + 1] + src[i * 4 + 2] / 256 - 32768;
        }
        // Tamanho do pixel no chão, na latitude do centro do tile.
        var n = Math.pow(2, coords.z);
        var latRad = Math.atan(Math.sinh(Math.PI * (1 - 2 * (coords.y + 0.5) / n)));
        var cell = 40075016.686 * Math.cos(latRad) / (n * w);

        var out = ctx.createImageData(w, h);
        var px = out.data;
        function e(x, y) {
            x = x < 0 ? 0 : (x >= w ? w - 1 : x);
            y = y < 0 ? 0 : (y >= h ? h - 1 : y);
            return elev[y * w + x];
        }
        for (var y = 0; y < h; y++) {
            for (var x = 0; x < w; x++) {
                var a = e(x - 1, y - 1), b = e(x, y - 1), c = e(x + 1, y - 1);
                var d = e(x - 1, y), f = e(x + 1, y);
                var g = e(x - 1, y + 1), hh = e(x, y + 1), k = e(x + 1, y + 1);
                var dzdx = ((c + 2 * f + k) - (a + 2 * d + g)) / (8 * cell);
                var dzdy = ((g + 2 * hh + k) - (a + 2 * b + c)) / (8 * cell);
                var slope = Math.atan(Math.sqrt(dzdx * dzdx + dzdy * dzdy)) * 180 / Math.PI;
                var cls = SLOPE_CLASSES.find(function (s) { return slope < s.max; });
                if (cls && cls.color) {
                    var o = (y * w + x) * 4;
                    px[o] = cls.color[0];
                    px[o + 1] = cls.color[1];
                    px[o + 2] = cls.color[2];
                    px[o + 3] = 255;
                }
            }
        }
        ctx.putImageData(out, 0, 0);
    }

    function wmsLayer(url, layer, pane, extra) {
        return L.tileLayer.wms(url, L.extend({
            layers: layer,
            format: 'image/png',
            transparent: true,
            version: '1.3.0',
            tileSize: 512,
            pane: pane,
            attribution: 'INPE'
        }, extra || {}));
    }

    function legendGraphic(url, layer) {
        return url + '?SERVICE=WMS&REQUEST=GetLegendGraphic&VERSION=1.3.0&FORMAT=image/png&LAYER=' + encodeURIComponent(layer);
    }

    /**
     * Itens do painel. Cada um: `name`, `create()` (a camada), `options` e
     * `select(layer, value)` (período/ano), `opacity`, `legend` (lista de
     * {color, label} ou {img}), `note`, `minZoom`.
     */
    function buildItems(imagery, pane) {
        var items = [];
        var thisYear = new Date().getUTCFullYear();
        var mb = imagery.mapbiomas;

        if (mb) {
            items.push({
                key: 'mapbiomas',
                name: 'MapBiomas – uso e cobertura do solo',
                options: mb.products.cobertura.years.map(function (y) { return { value: String(y), text: String(y) }; }),
                opacity: 0.75,
                minZoom: mb.min_zoom,
                note: 'Coleção 11, 30 m. Escolha 2008 para o marco temporal do Código Florestal (22/07/2008).',
                legend: mb.legend.map(function (c) { return { color: c.color, label: c.name }; }),
                create: function () {
                    return new global.MinZoomTileLayer(mb.tile_url.replace('{product}', 'cobertura'), {
                        year: mb.products.cobertura.years[0], minDataZoom: mb.min_zoom,
                        maxZoom: 19, maxNativeZoom: 15, pane: pane, attribution: 'MapBiomas'
                    });
                },
                select: function (layer, value) { layer.options.year = value; layer.redraw(); }
            });
            items.push({
                key: 'fogo',
                name: 'MapBiomas Fogo – área queimada',
                options: mb.products.fogo.years.map(function (y) { return { value: String(y), text: String(y) }; }),
                opacity: 0.85,
                minZoom: mb.min_zoom,
                note: 'Cicatrizes de fogo do ano (Coleção 5, 30 m).',
                legend: [{ color: mb.burned_color, label: 'Área queimada no ano' }],
                create: function () {
                    return new global.MinZoomTileLayer(mb.tile_url.replace('{product}', 'fogo'), {
                        year: mb.products.fogo.years[0], minDataZoom: mb.min_zoom,
                        maxZoom: 19, maxNativeZoom: 15, pane: pane, attribution: 'MapBiomas Fogo'
                    });
                },
                select: function (layer, value) { layer.options.year = value; layer.redraw(); }
            });
        }

        // DETER: alertas do INPE para Cerrado e Amazônia (o Tocantins tem os dois).
        var deterOptions = [
            { value: 'd30', text: 'Últimos 30 dias', time: isoDate(daysAgo(30)) + '/' + isoDate(new Date()) },
            { value: 'd90', text: 'Últimos 90 dias', time: isoDate(daysAgo(90)) + '/' + isoDate(new Date()) },
            { value: 'd365', text: 'Últimos 12 meses', time: isoDate(daysAgo(365)) + '/' + isoDate(new Date()) }
        ];
        for (var dy = thisYear; dy >= DETER_WMS[1].since; dy--) {
            deterOptions.push({ value: String(dy), text: String(dy) + (dy === thisYear ? ' (até hoje)' : ''), time: yearRange(dy) });
        }
        items.push({
            key: 'deter',
            name: 'DETER – alertas de desmatamento (INPE)',
            options: deterOptions,
            opacity: 0.9,
            note: 'Alertas diários do INPE (Cerrado desde 2018, Amazônia desde 2016). Mais rápido que o PRODES, mas preliminar.',
            legend: [{ img: legendGraphic(DETER_WMS[0].url, DETER_WMS[0].layer), label: 'Alerta DETER' }],
            create: function () {
                return L.layerGroup(DETER_WMS.map(function (d) {
                    return wmsLayer(d.url, d.layer, pane, { time: deterOptions[0].time });
                }));
            },
            select: function (group, value) {
                var opt = deterOptions.find(function (o) { return o.value === value; });
                group.eachLayer(function (l) { l.setParams({ time: opt.time }); });
            }
        });

        // Focos de calor: série anual pelo satélite de referência (comparável
        // entre anos) e os recentes por todos os satélites (mais completos).
        var focosOptions = [
            { value: '48h', text: 'Últimas 48 horas (todos os satélites)', layer: 'dados_abertos:focos_48h_br_todosats' },
            { value: 'mes', text: 'Mês atual (todos os satélites)', layer: 'dados_abertos:focos_mesatual_br_todosats' },
            { value: String(thisYear), text: thisYear + ' até hoje (satélite de referência)', layer: 'dados_abertos:focos_ano_atual_br_satref', time: yearRange(thisYear) }
        ];
        for (var fy = thisYear - 1; fy >= FIRST_FOCOS_YEAR; fy--) {
            focosOptions.push({ value: String(fy), text: fy + ' (satélite de referência)', layer: 'dados_abertos:focos_' + fy + '_br_satref', time: yearRange(fy) });
        }
        items.push({
            key: 'focos',
            name: 'Focos de calor (INPE Queimadas)',
            options: focosOptions,
            opacity: 1,
            note: 'Cada foco é um pixel de ~1 km com fogo ativo na passagem do satélite; não é a área queimada.',
            legend: [{ img: legendGraphic(QUEIMADAS_WMS, focosOptions[0].layer), label: 'Foco de calor' }],
            create: function () {
                var o = focosOptions[0];
                return wmsLayer(QUEIMADAS_WMS, o.layer, pane, o.time ? { time: o.time } : {});
            },
            select: function (layer, value) {
                var o = focosOptions.find(function (x) { return x.value === value; });
                // Sem `time`, as camadas anuais mostrariam só o último dia; as
                // de 48 h/mês não têm tempo (e `time=` vazio pode dar erro).
                if (o.time) {
                    layer.wmsParams.time = o.time;
                } else {
                    delete layer.wmsParams.time;
                }
                layer.setParams({ layers: o.layer });
            }
        });

        items.push({
            key: 'declividade',
            name: 'Declividade (Código Florestal)',
            opacity: 0.6,
            minZoom: SLOPE_MIN_ZOOM,
            note: 'Calculada do relevo SRTM (~30 m): encostas curtas ficam subestimadas. Topo de morro também depende da altura do morro, não só da declividade.',
            legend: SLOPE_CLASSES.map(function (s) { return { color: s.color ? hexToCss(s.color) : null, label: s.label }; }),
            create: function () {
                return new SlopeLayer({ pane: pane, maxNativeZoom: SLOPE_NATIVE_ZOOM, maxZoom: 19, attribution: 'Elevação: AWS Terrain Tiles (SRTM)' });
            }
        });

        items.push({
            key: 'relevo',
            name: 'Relevo sombreado',
            opacity: 0.7,
            note: 'Sombras do relevo sobre a imagem (Esri World Hillshade).',
            create: function () {
                return L.tileLayer(HILLSHADE_URL, { pane: RELIEF_PANE, maxZoom: 19, maxNativeZoom: 16, attribution: 'Relevo &copy; Esri' });
            }
        });

        return items;
    }

    /**
     * Monta a lista de camadas em `mount` (aba "Temáticas" do painel
     * lateral do maps.js).
     */
    function setupThematicLayers(map, imagery, pane, mount) {
        if (!map.getPane(RELIEF_PANE)) {
            var relief = map.createPane(RELIEF_PANE);
            relief.style.zIndex = 340;
            relief.style.mixBlendMode = 'multiply';
        }
        var list = L.DomUtil.create('div', 'thematic-list', mount);
        buildItems(imagery, pane).forEach(function (item) { buildItem(item, list); });

        function buildItem(item, body) {
            var wrap = L.DomUtil.create('div', 'thematic-item', body);
            var label = L.DomUtil.create('label', 'thematic-check', wrap);
            var check = L.DomUtil.create('input', '', label);
            check.type = 'checkbox';
            L.DomUtil.create('span', '', label).textContent = item.name;
            var controls = L.DomUtil.create('div', 'thematic-controls', wrap);
            controls.hidden = true;

            var select = null;
            if (item.options) {
                select = L.DomUtil.create('select', 'imagery-picker-select', controls);
                select.setAttribute('aria-label', 'Período de ' + item.name);
                item.options.forEach(function (opt) {
                    var o = document.createElement('option');
                    o.value = opt.value;
                    o.textContent = opt.text;
                    select.appendChild(o);
                });
            }
            var opacityRow = L.DomUtil.create('label', 'thematic-opacity', controls);
            opacityRow.appendChild(document.createTextNode('Opacidade'));
            var opacity = L.DomUtil.create('input', '', opacityRow);
            opacity.type = 'range';
            opacity.min = '0.1';
            opacity.max = '1';
            opacity.step = '0.05';
            opacity.value = String(item.opacity);
            var status = L.DomUtil.create('div', 'thematic-status', controls);
            if (item.note) L.DomUtil.create('div', 'thematic-note', controls).textContent = item.note;
            if (item.legend) {
                var legend = L.DomUtil.create('div', 'thematic-legend', controls);
                item.legend.forEach(function (entry) {
                    var row = L.DomUtil.create('div', 'thematic-legend-row', legend);
                    if (entry.img) {
                        var img = L.DomUtil.create('img', '', row);
                        img.src = entry.img;
                        img.alt = entry.label;
                    } else {
                        var swatch = L.DomUtil.create('span', 'thematic-swatch', row);
                        if (entry.color) { swatch.style.background = entry.color; } else { swatch.classList.add('empty'); }
                        row.appendChild(document.createTextNode(entry.label));
                    }
                });
            }

            var layer = null, loading = false;
            function setOpacity(value) {
                if (!layer) return;
                if (layer.setOpacity) { layer.setOpacity(value); } else { layer.eachLayer(function (l) { l.setOpacity(value); }); }
            }
            function updateStatus() {
                var text = '';
                if (item.minZoom && map.getZoom() < item.minZoom) {
                    text = 'Aproxime o mapa (zoom ' + item.minZoom + '+) para ver esta camada.';
                } else if (loading) {
                    text = 'Carregando…';
                }
                status.textContent = text;
                status.hidden = !text;
            }
            function watchLoading(l) {
                l.on('loading', function () { loading = true; updateStatus(); });
                l.on('load', function () { loading = false; updateStatus(); });
            }

            check.addEventListener('change', function () {
                controls.hidden = !check.checked;
                wrap.classList.toggle('is-on', check.checked);
                if (check.checked) {
                    if (!layer) {
                        layer = item.create();
                        if (layer.eachLayer) { layer.eachLayer(watchLoading); } else { watchLoading(layer); }
                    }
                    if (select && item.select) item.select(layer, select.value);
                    setOpacity(parseFloat(opacity.value));
                    layer.addTo(map);
                } else if (layer) {
                    map.removeLayer(layer);
                    loading = false;
                }
                updateStatus();
            });
            if (select) {
                select.addEventListener('change', function () {
                    if (layer && item.select) item.select(layer, select.value);
                });
            }
            opacity.addEventListener('input', function () { setOpacity(parseFloat(opacity.value)); });
            map.on('zoomend', updateStatus);
        }
    }

    global.setupThematicLayers = setupThematicLayers;
    global.THEMATIC_RELIEF_PANE = RELIEF_PANE;
})(window);
