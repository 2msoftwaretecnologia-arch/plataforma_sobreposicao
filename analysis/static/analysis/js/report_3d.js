/**
 * Vistas 3D do relatório impresso (analysis/report_print.html).
 *
 * Cada `.report-3d[data-map]` vira uma foto em perspectiva: satélite sobre o
 * relevo, com o contorno da propriedade e o que foi encontrado, nas mesmas
 * cores dos mapas 2D (report_maps.js). Para o papel, a cena vira uma <img>:
 * o canvas WebGL sai em branco na impressão e o navegador limita quantos
 * mapas WebGL podem existir ao mesmo tempo. Por isso um único mapa MapLibre,
 * fora da tela, desenha as vistas uma de cada vez e tira a foto de cada uma.
 *
 *   <div class="report-3d" data-map="<id do json_script>"
 *        data-bearing="35" data-pitch="58"></div>
 *
 * `window.report3dReady` resolve quando todas as vistas terminaram (o botão
 * de imprimir espera por ela).
 */
(function (global) {
    'use strict';

    var MAPLIBRE_VERSION = '4.7.1';
    var MAPLIBRE_JS = 'https://unpkg.com/maplibre-gl@' + MAPLIBRE_VERSION + '/dist/maplibre-gl.js';

    var ESRI_URL = 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}';
    var ESRI_MAX_ZOOM = 17;
    var TERRAIN_URL = 'https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png';
    var TERRAIN_MAX_ZOOM = 14;

    // O Tocantins é quase todo plano: sem exagero o relevo some (a legenda avisa).
    var EXAGGERATION = 2;
    var DEFAULT_PITCH = 58;
    var DEFAULT_BEARING = 35;
    // Nitidez da foto: o PDF é lido de perto.
    var PIXEL_RATIO = 2.5;
    // Uma vista que não termina de carregar sai como estiver depois disso.
    var JOB_TIMEOUT = 25000;
    var MIN_VISIVEL_PX = 14;

    var maplibrePromise = null;
    var shared = null;  // { map, box }

    function loadMaplibre() {
        if (global.maplibregl) return Promise.resolve(global.maplibregl);
        if (maplibrePromise) return maplibrePromise;
        maplibrePromise = new Promise(function (resolve, reject) {
            var s = document.createElement('script');
            s.src = MAPLIBRE_JS;
            s.async = true;
            s.onload = function () {
                if (global.maplibregl) resolve(global.maplibregl);
                else reject(new Error('MapLibre não carregou'));
            };
            s.onerror = function () { reject(new Error('Falha ao baixar o MapLibre')); };
            document.head.appendChild(s);
        });
        return maplibrePromise;
    }

    // GeoJSON da análise chega como geometria solta, Feature ou coleção.
    function toFeatures(gj) {
        if (!gj) return [];
        if (gj.type === 'FeatureCollection') return gj.features || [];
        if (gj.type === 'Feature') return [gj];
        return [{ type: 'Feature', properties: {}, geometry: gj }];
    }

    function boundsOf(features) {
        var b = [Infinity, Infinity, -Infinity, -Infinity];
        function walk(c) {
            if (typeof c[0] === 'number') {
                b[0] = Math.min(b[0], c[0]); b[1] = Math.min(b[1], c[1]);
                b[2] = Math.max(b[2], c[0]); b[3] = Math.max(b[3], c[1]);
            } else {
                c.forEach(walk);
            }
        }
        features.forEach(function (f) {
            var g = f && f.geometry;
            if (!g) return;
            (g.type === 'GeometryCollection' ? g.geometries : [g]).forEach(function (gg) {
                if (gg && gg.coordinates) walk(gg.coordinates);
            });
        });
        return isFinite(b[0]) ? [[b[0], b[1]], [b[2], b[3]]] : null;
    }

    function extend(a, b) {
        if (!a) return b;
        if (!b) return a;
        return [[Math.min(a[0][0], b[0][0]), Math.min(a[0][1], b[0][1])],
                [Math.max(a[1][0], b[1][0]), Math.max(a[1][1], b[1][1])]];
    }

    function sharedMap(maplibregl) {
        if (shared) return shared;
        var box = document.createElement('div');
        box.className = 'report-3d__stage';
        box.setAttribute('aria-hidden', 'true');
        document.body.appendChild(box);

        var map = new maplibregl.Map({
            container: box,
            center: [-48.3, -10.2],
            zoom: 13,
            interactive: false,
            attributionControl: false,
            fadeDuration: 0,
            maxPitch: 80,
            pixelRatio: PIXEL_RATIO,
            preserveDrawingBuffer: true,
            style: {
                version: 8,
                sources: {
                    sat: {
                        type: 'raster', tiles: [ESRI_URL], tileSize: 256, maxzoom: ESRI_MAX_ZOOM
                    },
                    terrain: {
                        type: 'raster-dem', tiles: [TERRAIN_URL], tileSize: 256,
                        maxzoom: TERRAIN_MAX_ZOOM, encoding: 'terrarium'
                    }
                },
                layers: [{ id: 'sat', type: 'raster', source: 'sat' }],
                terrain: { source: 'terrain', exaggeration: EXAGGERATION },
                sky: {
                    'sky-color': '#9cc3d5',
                    'horizon-color': '#f3e3bc',
                    'fog-color': '#dcead8',
                    'sky-horizon-blend': 0.5,
                    'horizon-fog-blend': 0.6,
                    'fog-ground-blend': 0.35
                }
            }
        });
        map.on('error', function (e) {
            if (global.console) console.warn('[relatório 3D]', (e && e.sourceId) || '', e && e.error);
        });
        shared = {
            map: map,
            box: box,
            ready: new Promise(function (resolve) { map.once('load', resolve); })
        };
        return shared;
    }

    var JOB_LAYERS = ['job-raster', 'job-fill', 'job-line', 'job-ring', 'job-dot', 'prop-casing', 'prop-line'];
    var JOB_SOURCES = ['job-raster', 'job-itens', 'job-rings', 'prop'];

    function clearJob(map) {
        JOB_LAYERS.forEach(function (id) { if (map.getLayer(id)) map.removeLayer(id); });
        JOB_SOURCES.forEach(function (id) { if (map.getSource(id)) map.removeSource(id); });
    }

    function addJob(map, data) {
        var prop = toFeatures(data.propriedade);
        var itens = [];
        (data.itens || []).forEach(function (gj) { itens = itens.concat(toFeatures(gj)); });

        if (data.imagem && data.imagem.url && data.imagem.bounds) {
            // bounds no formato do Leaflet: [[sul, oeste], [norte, leste]].
            var s = data.imagem.bounds[0][0], w = data.imagem.bounds[0][1];
            var n = data.imagem.bounds[1][0], e = data.imagem.bounds[1][1];
            map.addSource('job-raster', {
                type: 'image', url: data.imagem.url,
                coordinates: [[w, n], [e, n], [e, s], [w, s]]
            });
            map.addLayer({
                id: 'job-raster', type: 'raster', source: 'job-raster',
                paint: { 'raster-resampling': 'nearest', 'raster-fade-duration': 0 }
            });
        }

        if (itens.length) {
            map.addSource('job-itens', { type: 'geojson', data: { type: 'FeatureCollection', features: itens } });
            map.addLayer({
                id: 'job-fill', type: 'fill', source: 'job-itens',
                filter: ['match', ['geometry-type'], ['Polygon', 'MultiPolygon'], true, false],
                paint: { 'fill-color': data.cor, 'fill-opacity': 0.45 }
            });
            map.addLayer({
                id: 'job-line', type: 'line', source: 'job-itens',
                layout: { 'line-join': 'round' },
                paint: { 'line-color': data.cor, 'line-width': 2 }
            });
        }

        // Contorno por cima de tudo, igual ao 2D: branco por baixo, preto por cima.
        map.addSource('prop', { type: 'geojson', data: { type: 'FeatureCollection', features: prop } });
        map.addLayer({
            id: 'prop-casing', type: 'line', source: 'prop',
            layout: { 'line-join': 'round' },
            paint: { 'line-color': '#ffffff', 'line-width': 5, 'line-opacity': 0.85 }
        });
        map.addLayer({
            id: 'prop-line', type: 'line', source: 'prop',
            layout: { 'line-join': 'round' },
            paint: { 'line-color': '#111111', 'line-width': 2.5 }
        });

        return { prop: prop, itens: itens };
    }

    // Itens pequenos demais para a escala ganham um círculo, como no 2D.
    function addRings(map, itens, cor) {
        var pontos = [];
        itens.forEach(function (f) {
            var b = boundsOf([f]);
            if (!b) return;
            var a = map.project(b[0]), c = map.project(b[1]);
            if (Math.max(Math.abs(c.x - a.x), Math.abs(c.y - a.y)) >= MIN_VISIVEL_PX) return;
            pontos.push({
                type: 'Feature', properties: {},
                geometry: { type: 'Point', coordinates: [(b[0][0] + b[1][0]) / 2, (b[0][1] + b[1][1]) / 2] }
            });
        });
        if (!pontos.length) return false;
        map.addSource('job-rings', { type: 'geojson', data: { type: 'FeatureCollection', features: pontos } });
        map.addLayer({
            id: 'job-ring', type: 'circle', source: 'job-rings',
            paint: {
                'circle-radius': 13, 'circle-color': 'rgba(0,0,0,0)',
                'circle-stroke-color': cor, 'circle-stroke-width': 3,
                'circle-pitch-alignment': 'map'
            }
        });
        map.addLayer({
            id: 'job-dot', type: 'circle', source: 'job-rings',
            paint: { 'circle-radius': 3, 'circle-color': cor, 'circle-pitch-alignment': 'map' }
        });
        return true;
    }

    // Vértices das feições (no máximo ~600, para o enquadramento ser rápido).
    function vertices(features) {
        var pts = [];
        function walk(c) {
            if (typeof c[0] === 'number') pts.push(c);
            else c.forEach(walk);
        }
        features.forEach(function (f) {
            var g = f && f.geometry;
            if (!g) return;
            (g.type === 'GeometryCollection' ? g.geometries : [g]).forEach(function (gg) {
                if (gg && gg.coordinates) walk(gg.coordinates);
            });
        });
        var step = Math.max(1, Math.ceil(pts.length / 600));
        return pts.filter(function (p, i) { return i % step === 0; });
    }

    // O `cameraForBounds` do MapLibre 4 enquadra com a câmera de cima; na
    // perspectiva, a parte de trás encolhe e a da frente cresce. Então
    // enquadra pela tela: projeta os vértices, mede o que sobra e corrige o
    // zoom e o centro algumas vezes até caber com folga.
    function frame(map, bounds, pts, bearing, pitch) {
        var c = map.getContainer();
        var W = c.clientWidth, H = c.clientHeight;
        var pad = Math.max(18, Math.min(W, H) * 0.08);
        map.jumpTo({
            center: [(bounds[0][0] + bounds[1][0]) / 2, (bounds[0][1] + bounds[1][1]) / 2],
            zoom: 13, bearing: bearing, pitch: pitch
        });
        for (var i = 0; i < 5; i++) {
            var x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
            pts.forEach(function (p) {
                var s = map.project(p);
                x0 = Math.min(x0, s.x); x1 = Math.max(x1, s.x);
                y0 = Math.min(y0, s.y); y1 = Math.max(y1, s.y);
            });
            var scale = Math.min((W - 2 * pad) / Math.max(x1 - x0, 1), (H - 2 * pad) / Math.max(y1 - y0, 1));
            var zoom = Math.min(map.getZoom() + Math.log(scale) / Math.LN2, 18);
            map.jumpTo({ center: map.unproject([(x0 + x1) / 2, (y0 + y1) / 2]), zoom: zoom });
            if (Math.abs(scale - 1) < 0.03) break;
        }
    }

    function waitIdle(map) {
        return new Promise(function (resolve) {
            var done = false;
            function finish() {
                if (done) return;
                done = true;
                clearTimeout(timer);
                resolve();
            }
            var timer = setTimeout(finish, JOB_TIMEOUT);
            // Um quadro a mais depois do `idle`: o relevo assenta no último tile.
            map.once('idle', function () {
                map.once('render', finish);
                map.triggerRepaint();
            });
        });
    }

    function northBadge(bearing) {
        var el = document.createElement('div');
        el.className = 'report-3d__north';
        el.title = 'Norte';
        el.innerHTML = '<svg viewBox="0 0 24 32" aria-hidden="true" style="transform: rotate(' +
            (-bearing) + 'deg)"><path d="M12 2 L20 26 L12 20 L4 26 Z"/></svg><span>N</span>';
        return el;
    }

    function renderOne(maplibregl, target) {
        var script = document.getElementById(target.getAttribute('data-map'));
        var data = script ? JSON.parse(script.textContent) : null;
        if (!data || !data.propriedade) return Promise.reject(new Error('sem dados'));

        var bearing = Number(target.getAttribute('data-bearing') || DEFAULT_BEARING);
        var pitch = Number(target.getAttribute('data-pitch') || DEFAULT_PITCH);
        var rect = target.getBoundingClientRect();
        var w = Math.max(Math.round(rect.width), 280);
        var h = Math.max(Math.round(rect.height), 200);

        var sm = sharedMap(maplibregl);
        return sm.ready.then(function () {
            var map = sm.map;
            sm.box.style.width = w + 'px';
            sm.box.style.height = h + 'px';
            map.resize();

            clearJob(map);
            var feats = addJob(map, data);
            var bounds = boundsOf(feats.prop);
            feats.itens.forEach(function (f) { bounds = extend(bounds, boundsOf([f])); });
            if (!bounds) throw new Error('sem geometria');
            frame(map, bounds, vertices(feats.prop.concat(feats.itens)), bearing, pitch);
            var temAnel = data.cor ? addRings(map, feats.itens, data.cor) : false;

            return waitIdle(map).then(function () {
                var img = new Image();
                img.className = 'report-3d__img';
                img.alt = target.getAttribute('data-alt') || 'Vista em 3D da propriedade';
                img.src = map.getCanvas().toDataURL('image/jpeg', 0.9);
                target.innerHTML = '';
                target.appendChild(img);
                target.appendChild(northBadge(bearing));
                target.classList.add('is-ready');
                var fig = target.closest('.map-figure') || target.parentNode;
                if (temAnel && fig) fig.classList.add('has-ring');
            });
        });
    }

    function fail(target, err) {
        target.classList.add('is-failed');
        target.innerHTML = '<span class="report-3d__msg">Não foi possível gerar a vista 3D' +
            (err && err.message ? ' (' + err.message + ')' : '') + '.</span>';
    }

    function run() {
        var targets = Array.prototype.slice.call(document.querySelectorAll('.report-3d[data-map]'));
        if (!targets.length) return Promise.resolve();

        var probe = document.createElement('canvas');
        if (!(probe.getContext('webgl2') || probe.getContext('webgl'))) {
            targets.forEach(function (t) { fail(t, new Error('o navegador não tem WebGL')); });
            return Promise.resolve();
        }

        return loadMaplibre().then(function (maplibregl) {
            // Uma de cada vez, na ordem da página: as primeiras ficam prontas antes.
            return targets.reduce(function (p, t) {
                return p.then(function () {
                    return renderOne(maplibregl, t).catch(function (err) { fail(t, err); });
                });
            }, Promise.resolve());
        }).catch(function (err) {
            targets.forEach(function (t) { if (!t.classList.contains('is-ready')) fail(t, err); });
        }).then(function () {
            // Libera a memória da placa de vídeo; as fotos já estão na página.
            if (shared) {
                shared.map.remove();
                shared.box.remove();
                shared = null;
            }
        });
    }

    var resolveReady;
    global.report3dReady = new Promise(function (resolve) { resolveReady = resolve; });

    function start() {
        // Espera as fontes: a largura das figuras muda quando elas chegam.
        var fonts = document.fonts && document.fonts.ready ? document.fonts.ready : Promise.resolve();
        fonts.then(run, run).then(resolveReady, resolveReady);
    }

    /** Imprime depois que as vistas 3D estiverem prontas (ou falharem). */
    global.printReport = function (btn) {
        var label = btn ? btn.textContent : '';
        var pending = document.querySelector('.report-3d:not(.is-ready):not(.is-failed)');
        if (pending && btn) {
            btn.disabled = true;
            btn.textContent = 'Preparando as vistas 3D…';
        }
        global.report3dReady.then(function () {
            if (btn) {
                btn.disabled = false;
                btn.textContent = label;
            }
            global.print();
        });
    };

    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
    else start();
})(window);
