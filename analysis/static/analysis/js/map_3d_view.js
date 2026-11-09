/*
 * Visão 3D do mapa de sobreposições (página de resultados): a imagem de
 * satélite de melhor resolução disponível sobre o relevo, com a propriedade
 * e as bases da análise desenhadas por cima, nas mesmas cores do mapa 2D.
 *
 * O MapLibre só é baixado quando o usuário abre a visão 3D. As camadas vêm do
 * mapa interativo (maps.js → getMapOverlays), então o que está ligado lá
 * aparece ligado aqui.
 *
 *   open3dView({ imagery: <imagery_config()>, opener: <botão> })
 */
(function (global) {
    'use strict';

    var MAPLIBRE_VERSION = '4.7.1';
    var MAPLIBRE_JS = 'https://unpkg.com/maplibre-gl@' + MAPLIBRE_VERSION + '/dist/maplibre-gl.js';
    var MAPLIBRE_CSS = 'https://unpkg.com/maplibre-gl@' + MAPLIBRE_VERSION + '/dist/maplibre-gl.css';

    // Esri World Imagery: na zona rural do Tocantins só há foto até o nível
    // 17 (do 18 em diante vem o tile "Map data not yet available"), então o
    // mapa amplia o 17 em vez de pedir os níveis seguintes.
    var ESRI_URL = 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}';
    var ESRI_MAX_ZOOM = 17;
    var GOOGLE_MAX_ZOOM = 20;

    // Relevo: Terrain Tiles da AWS (Mapzen). Nível 14 ≈ 10 m por pixel.
    var TERRAIN_URL = 'https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png';
    var TERRAIN_MAX_ZOOM = 14;

    // O Tocantins é quase todo plano: sem exagero o relevo some.
    var DEFAULT_EXAGGERATION = 2;
    var TOUR_PITCH = 62;
    var TOUR_BEARING = -28;
    var ORBIT_DEG_PER_SEC = 4;

    var PROPERTY_COLOR = '#ffd23f';
    var SICAR_FONTE = 'Base de Dados Sicar';

    var state = {
        built: false,
        map: null,
        imagery: {},
        overlays: [],
        opener: null,
        orbiting: false,
        orbitFrame: null,
        lastFrame: 0
    };
    var el = {};
    var maplibrePromise = null;

    // =====================================================================
    // Utilidades
    // =====================================================================

    function loadMaplibre() {
        if (global.maplibregl) return Promise.resolve(global.maplibregl);
        if (maplibrePromise) return maplibrePromise;
        maplibrePromise = new Promise(function (resolve, reject) {
            var css = document.createElement('link');
            css.rel = 'stylesheet';
            css.href = MAPLIBRE_CSS;
            document.head.appendChild(css);

            var script = document.createElement('script');
            script.src = MAPLIBRE_JS;
            script.async = true;
            script.onload = function () {
                if (global.maplibregl) resolve(global.maplibregl);
                else reject(new Error('MapLibre não carregou'));
            };
            script.onerror = function () {
                maplibrePromise = null;  // deixa tentar de novo
                reject(new Error('Falha ao baixar o MapLibre'));
            };
            document.head.appendChild(script);
        });
        return maplibrePromise;
    }

    function absoluteUrl(url) {
        return /^https?:\/\//.test(url) ? url : global.location.origin + url;
    }

    function hasGoogle() {
        return !!state.imagery.google_tile_url;
    }

    function fmtRelief(n) {
        return Number(n).toLocaleString('pt-BR', { maximumFractionDigits: 1 }) + '×';
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
            var g = f.geometry;
            if (!g) return;
            (g.type === 'GeometryCollection' ? g.geometries : [g]).forEach(function (gg) {
                if (gg && gg.coordinates) walk(gg.coordinates);
            });
        });
        return isFinite(b[0]) ? [[b[0], b[1]], [b[2], b[3]]] : null;
    }

    function create(tag, cls, parent, text) {
        var node = document.createElement(tag);
        if (cls) node.className = cls;
        if (text) node.textContent = text;
        if (parent) parent.appendChild(node);
        return node;
    }

    // =====================================================================
    // Estrutura da tela
    // =====================================================================

    function buildDom() {
        var root = create('div', 'm3d', document.body);
        root.setAttribute('role', 'dialog');
        root.setAttribute('aria-modal', 'true');
        root.setAttribute('aria-label', 'Visão 3D do mapa de sobreposições');
        root.hidden = true;

        el.root = root;
        el.map = create('div', 'm3d-map', root);

        var bar = create('header', 'm3d-bar', root);
        var title = create('div', 'm3d-title', bar);
        create('strong', '', title, 'Visão 3D');
        el.subtitle = create('span', '', title, 'Imagem de satélite sobre o relevo');

        var controls = create('div', 'm3d-controls', bar);

        // Imagem de satélite
        el.imagery = create('div', 'm3d-seg', controls);
        el.imagery.setAttribute('role', 'radiogroup');
        el.imagery.setAttribute('aria-label', 'Imagem de satélite');

        // Exagero do relevo
        var relief = create('label', 'm3d-relief', controls);
        create('span', '', relief, 'Relevo');
        el.relief = create('input', '', relief);
        el.relief.type = 'range';
        el.relief.min = '1';
        el.relief.max = '5';
        el.relief.step = '0.5';
        el.relief.value = String(DEFAULT_EXAGGERATION);
        el.relief.setAttribute('aria-label', 'Exagero do relevo');
        el.reliefValue = create('b', '', relief, fmtRelief(DEFAULT_EXAGGERATION));

        el.orbit = create('button', 'm3d-btn', controls, 'Girar');
        el.orbit.type = 'button';
        el.orbit.setAttribute('aria-pressed', 'false');
        el.orbit.title = 'Gira a câmera ao redor da propriedade';

        el.reset = create('button', 'm3d-btn', controls, 'Recentralizar');
        el.reset.type = 'button';
        el.reset.title = 'Volta a câmera para a propriedade';

        el.close = create('button', 'm3d-btn m3d-close', controls);
        el.close.type = 'button';
        el.close.setAttribute('aria-label', 'Fechar a visão 3D');
        el.close.innerHTML = 'Fechar <span aria-hidden="true">&times;</span>';

        var legend = create('aside', 'm3d-legend', root);
        legend.setAttribute('aria-label', 'Bases no mapa 3D');
        create('div', 'm3d-legend-title', legend, 'Bases no mapa');
        el.legend = create('ul', 'm3d-legend-list', legend);

        el.hint = create('div', 'm3d-hint', root,
            'Clique direito e arraste (ou Ctrl + arrastar) para girar e inclinar · roda do mouse para aproximar');

        el.status = create('div', 'm3d-status', root);
        el.status.setAttribute('role', 'status');
        el.status.hidden = true;

        el.close.addEventListener('click', close);
        el.reset.addEventListener('click', function () { stopOrbit(); frameProperty(true); });
        el.orbit.addEventListener('click', function () { state.orbiting ? stopOrbit() : startOrbit(); });
        el.relief.addEventListener('input', function () {
            el.reliefValue.textContent = fmtRelief(el.relief.value);
            if (state.map) state.map.setTerrain({ source: 'terrain', exaggeration: Number(el.relief.value) });
        });
        document.addEventListener('keydown', function (e) {
            if (e.key === 'Escape' && !root.hidden) close();
        });

        state.built = true;
    }

    function buildImageryOptions() {
        el.imagery.innerHTML = '';
        var options = [];
        if (hasGoogle()) options.push({ value: 'google', label: 'Google', title: 'Imagem do Google (até ~zoom 20)' });
        options.push({ value: 'esri', label: 'Esri', title: 'Imagem da Esri (World Imagery)' });
        // Uma opção só: não há o que escolher.
        el.imagery.hidden = options.length < 2;
        options.forEach(function (opt, i) {
            var id = 'm3d_img_' + opt.value;
            var input = create('input', '', el.imagery);
            input.type = 'radio';
            input.name = 'm3d_imagery';
            input.id = id;
            input.value = opt.value;
            input.checked = i === 0;
            var label = create('label', '', el.imagery, opt.label);
            label.htmlFor = id;
            label.title = opt.title;
            input.addEventListener('change', function () {
                if (input.checked) setImagery(opt.value);
            });
        });
    }

    function buildLegend() {
        el.legend.innerHTML = '';
        state.overlays.forEach(function (ov, i) {
            var li = create('li', '', el.legend);
            var label = create('label', 'm3d-legend-item', li);
            var check = create('input', '', label);
            check.type = 'checkbox';
            check.checked = ov.visible;
            var sw = create('span', 'm3d-swatch', label);
            sw.style.setProperty('--c', ov.isProperty ? PROPERTY_COLOR : ov.color);
            create('span', 'm3d-legend-name', label, ov.fonte);
            check.addEventListener('change', function () {
                ov.visible = check.checked;
                setOverlayVisible(i, ov.visible);
            });
        });
    }

    // =====================================================================
    // Mapa
    // =====================================================================

    function rasterSources() {
        var sources = {
            'sat-esri': {
                type: 'raster', tiles: [ESRI_URL], tileSize: 256, maxzoom: ESRI_MAX_ZOOM,
                attribution: 'Imagens &copy; Esri'
            },
            terrain: {
                type: 'raster-dem', tiles: [TERRAIN_URL], tileSize: 256, maxzoom: TERRAIN_MAX_ZOOM,
                encoding: 'terrarium', attribution: 'Relevo &copy; Mapzen/AWS Terrain Tiles'
            }
        };
        if (hasGoogle()) {
            sources['sat-google'] = {
                type: 'raster', tiles: [absoluteUrl(state.imagery.google_tile_url)], tileSize: 256,
                maxzoom: GOOGLE_MAX_ZOOM, attribution: 'Imagens &copy; Google'
            };
        }
        return sources;
    }

    function overlayLayerIds(i) {
        return ['ov' + i + '-fill', 'ov' + i + '-casing', 'ov' + i + '-line', 'ov' + i + '-pt'];
    }

    function addOverlays(map) {
        // A propriedade por último: fica por cima das bases.
        var order = state.overlays.map(function (ov, i) { return i; }).sort(function (a, b) {
            return (state.overlays[a].isProperty ? 1 : 0) - (state.overlays[b].isProperty ? 1 : 0);
        });
        order.forEach(function (i) {
            var ov = state.overlays[i];
            var src = 'ov' + i;
            var vis = { visibility: ov.visible ? 'visible' : 'none' };
            map.addSource(src, { type: 'geojson', data: ov.geojson });

            var polygons = ['match', ['geometry-type'], ['Polygon', 'MultiPolygon'], true, false];
            var lines = ['match', ['geometry-type'], ['Polygon', 'MultiPolygon', 'LineString', 'MultiLineString'], true, false];
            var points = ['match', ['geometry-type'], ['Point', 'MultiPoint'], true, false];

            if (ov.isProperty) {
                map.addLayer({ id: src + '-casing', type: 'line', source: src, filter: lines,
                    layout: Object.assign({ 'line-join': 'round' }, vis),
                    paint: { 'line-color': '#ffffff', 'line-width': 6.5, 'line-opacity': 0.85 } });
                map.addLayer({ id: src + '-line', type: 'line', source: src, filter: lines,
                    layout: Object.assign({ 'line-join': 'round' }, vis),
                    paint: { 'line-color': PROPERTY_COLOR, 'line-width': 3.2 } });
            } else {
                // Como no mapa 2D: SICAR só com contorno, as demais preenchidas.
                var outlineOnly = ov.fonte === SICAR_FONTE;
                map.addLayer({ id: src + '-fill', type: 'fill', source: src, filter: polygons, layout: vis,
                    paint: { 'fill-color': ov.color, 'fill-opacity': outlineOnly ? 0 : 0.38 } });
                map.addLayer({ id: src + '-line', type: 'line', source: src, filter: lines,
                    layout: Object.assign({ 'line-join': 'round' }, vis),
                    paint: { 'line-color': ov.color, 'line-width': 2.2 } });
            }
            map.addLayer({ id: src + '-pt', type: 'circle', source: src, filter: points, layout: vis,
                paint: {
                    'circle-color': ov.color, 'circle-radius': 8,
                    'circle-stroke-color': '#ffffff', 'circle-stroke-width': 2
                } });
        });
    }

    function setOverlayVisible(i, on) {
        if (!state.map) return;
        overlayLayerIds(i).forEach(function (id) {
            if (state.map.getLayer(id)) state.map.setLayoutProperty(id, 'visibility', on ? 'visible' : 'none');
        });
    }

    function refreshOverlays() {
        var map = state.map;
        state.overlays.forEach(function (ov, i) {
            var src = map.getSource('ov' + i);
            if (src) src.setData(ov.geojson);
            setOverlayVisible(i, ov.visible);
        });
    }

    function setImagery(which) {
        if (!state.map) return;
        ['google', 'esri'].forEach(function (key) {
            var id = 'sat-' + key;
            if (state.map.getLayer(id)) state.map.setLayoutProperty(id, 'visibility', key === which ? 'visible' : 'none');
        });
        state.map.setMaxZoom(which === 'google' ? GOOGLE_MAX_ZOOM + 0.5 : ESRI_MAX_ZOOM + 2);
        el.subtitle.textContent = which === 'google'
            ? 'Imagem do Google sobre o relevo'
            : 'Imagem da Esri sobre o relevo';
    }

    function initialImagery() {
        return hasGoogle() ? 'google' : 'esri';
    }

    function createMap(maplibregl) {
        var imagery = initialImagery();
        var layers = [];
        if (hasGoogle()) {
            layers.push({ id: 'sat-google', type: 'raster', source: 'sat-google',
                layout: { visibility: imagery === 'google' ? 'visible' : 'none' } });
        }
        layers.push({ id: 'sat-esri', type: 'raster', source: 'sat-esri',
            layout: { visibility: imagery === 'esri' ? 'visible' : 'none' } });

        var view = global.getMapView ? global.getMapView() : null;
        var map = new maplibregl.Map({
            container: el.map,
            center: view ? view.center : [-48.3, -10.2],
            zoom: view ? view.zoom : 14,
            maxPitch: 80,
            maxZoom: imagery === 'google' ? GOOGLE_MAX_ZOOM + 0.5 : ESRI_MAX_ZOOM + 2,
            style: {
                version: 8,
                sources: rasterSources(),
                layers: layers,
                terrain: { source: 'terrain', exaggeration: Number(el.relief.value) },
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
        map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), 'bottom-right');
        map.addControl(new maplibregl.ScaleControl({ unit: 'metric' }), 'bottom-right');

        // Usuário mexeu na câmera: para de girar sozinho.
        ['mousedown', 'touchstart', 'wheel'].forEach(function (ev) {
            map.getCanvasContainer().addEventListener(ev, stopOrbit, { passive: true });
        });

        map.on('click', function (e) {
            var ids = [];
            state.overlays.forEach(function (ov, i) {
                if (!ov.visible) return;
                overlayLayerIds(i).forEach(function (id) { if (map.getLayer(id)) ids.push(id); });
            });
            var f = map.queryRenderedFeatures(e.point, { layers: ids })[0];
            if (!f) return;
            var p = f.properties || {};
            var box = document.createElement('div');
            box.className = 'm3d-popup';
            create('strong', '', box, p._fonte || '');
            if (p._label && p._label !== p._fonte) create('div', '', box, p._label);
            if (p._area) create('div', 'm3d-popup-area', box, 'Área: ' + p._area);
            new maplibregl.Popup({ maxWidth: '320px' }).setLngLat(e.lngLat).setDOMContent(box).addTo(map);
        });
        map.on('mousemove', function (e) {
            var ids = [];
            state.overlays.forEach(function (ov, i) {
                if (ov.visible) overlayLayerIds(i).forEach(function (id) { if (map.getLayer(id)) ids.push(id); });
            });
            map.getCanvas().style.cursor = map.queryRenderedFeatures(e.point, { layers: ids }).length ? 'pointer' : '';
        });

        state.map = map;
        // `style.load`, não `load`: o `load` espera todos os tiles (imagem e
        // relevo) e a câmera ficaria parada até lá. A imagem completa depois.
        return new Promise(function (resolve) {
            function ready() {
                addOverlays(map);
                setImagery(imagery);
                resolve(map);
            }
            if (map.isStyleLoaded()) ready();
            else map.once('style.load', ready);
        });
    }

    // =====================================================================
    // Câmera
    // =====================================================================

    function targetFeatures() {
        var prop = state.overlays.filter(function (ov) { return ov.isProperty || ov.isPoint; })[0];
        if (prop && prop.geojson.features.length) return prop.geojson.features;
        return state.overlays.reduce(function (acc, ov) {
            return ov.visible ? acc.concat(ov.geojson.features) : acc;
        }, []);
    }

    function framePadding() {
        var small = global.innerWidth < 760;
        return small
            ? { top: 120, bottom: 150, left: 30, right: 30 }
            : { top: 110, bottom: 70, left: 300, right: 90 };
    }

    // Enquadra a propriedade de cima e desce inclinando, como um drone.
    function frameProperty(animate) {
        var map = state.map;
        var bounds = boundsOf(targetFeatures());
        if (!bounds) return;
        var single = bounds[0][0] === bounds[1][0] && bounds[0][1] === bounds[1][1];
        var flat = single
            ? { center: bounds[0], zoom: 17 }
            : map.cameraForBounds(bounds, { padding: framePadding(), maxZoom: 18 });
        if (!flat) return;
        map.jumpTo({ center: flat.center, zoom: flat.zoom, pitch: 0, bearing: 0 });
        // Inclinada, a propriedade fica menor na tela (o fundo foge): um
        // pouco mais de zoom compensa sem cortar as bordas.
        var tilted = { center: flat.center, zoom: flat.zoom + 0.25, pitch: TOUR_PITCH, bearing: TOUR_BEARING };
        if (animate && !reduceMotion()) map.easeTo(Object.assign({ duration: 2600, essential: true }, tilted));
        else map.jumpTo(tilted);
    }

    function reduceMotion() {
        return global.matchMedia && global.matchMedia('(prefers-reduced-motion: reduce)').matches;
    }

    function orbitStep(now) {
        if (!state.orbiting || !state.map) return;
        var dt = state.lastFrame ? Math.min(now - state.lastFrame, 100) : 16;
        state.lastFrame = now;
        state.map.setBearing(state.map.getBearing() + ORBIT_DEG_PER_SEC * dt / 1000);
        state.orbitFrame = global.requestAnimationFrame(orbitStep);
    }

    function startOrbit() {
        if (state.orbiting || !state.map) return;
        state.orbiting = true;
        state.lastFrame = 0;
        el.orbit.setAttribute('aria-pressed', 'true');
        el.orbit.classList.add('is-on');
        state.orbitFrame = global.requestAnimationFrame(orbitStep);
    }

    function stopOrbit() {
        if (!state.orbiting) return;
        state.orbiting = false;
        if (state.orbitFrame) global.cancelAnimationFrame(state.orbitFrame);
        el.orbit.setAttribute('aria-pressed', 'false');
        el.orbit.classList.remove('is-on');
    }

    // =====================================================================
    // Abrir / fechar
    // =====================================================================

    function setStatus(text, isError) {
        el.status.hidden = !text;
        el.status.textContent = text || '';
        el.status.classList.toggle('is-error', !!isError);
    }

    function open(opts) {
        opts = opts || {};
        if (!global.getMapOverlays) return;
        // O mapa 2D em tela cheia esconderia a visão 3D (que fica no <body>).
        if (document.fullscreenElement && document.exitFullscreen) {
            document.exitFullscreen().catch(function () {});
        }
        state.overlays = global.getMapOverlays().filter(function (ov) {
            return ov.geojson && ov.geojson.features && ov.geojson.features.length;
        });
        if (!state.overlays.length) return;

        if (!state.built) buildDom();
        state.imagery = opts.imagery || state.imagery || {};
        state.opener = opts.opener || document.activeElement;

        el.root.hidden = false;
        document.documentElement.classList.add('m3d-open');
        buildLegend();
        el.close.focus();

        if (state.map) {
            state.map.resize();
            refreshOverlays();
            frameProperty(true);
            return;
        }

        setStatus('Carregando a imagem 3D...');
        buildImageryOptions();
        loadMaplibre()
            .then(function (maplibregl) { return createMap(maplibregl); })
            .then(function () {
                setStatus('');
                frameProperty(true);
            })
            .catch(function () {
                setStatus('Não foi possível abrir a visão 3D. Confira a conexão e tente de novo.', true);
                if (state.map) { try { state.map.remove(); } catch (e) { /* já removido */ } }
                state.map = null;
            });
    }

    function close() {
        if (!state.built || el.root.hidden) return;
        stopOrbit();
        el.root.hidden = true;
        document.documentElement.classList.remove('m3d-open');
        if (state.opener && state.opener.focus) state.opener.focus();
    }

    /**
     * Liga o botão "Ver em 3D" do cabeçalho do mapa e põe um botão "3D" no
     * próprio mapa Leaflet (visível também em tela cheia).
     */
    function install(opts) {
        opts = opts || {};
        var imagery = opts.imagery || {};
        var headerBtn = opts.button;
        if (headerBtn) {
            headerBtn.hidden = false;
            headerBtn.addEventListener('click', function () { open({ imagery: imagery, opener: headerBtn }); });
        }
        var lmap = global.getImoveisMap && global.getImoveisMap();
        if (!lmap || !global.L) return;
        var Control = global.L.Control.extend({
            options: { position: 'topleft' },
            onAdd: function () {
                var bar = global.L.DomUtil.create('div', 'leaflet-bar m3d-leaflet-btn');
                var a = global.L.DomUtil.create('a', '', bar);
                a.href = '#';
                a.role = 'button';
                a.title = 'Ver em 3D';
                a.setAttribute('aria-label', 'Ver o mapa em 3D');
                a.textContent = '3D';
                global.L.DomEvent.disableClickPropagation(bar);
                global.L.DomEvent.on(a, 'click', function (e) {
                    global.L.DomEvent.preventDefault(e);
                    open({ imagery: imagery, opener: a });
                });
                return bar;
            }
        });
        new Control().addTo(lmap);
    }

    global.open3dView = open;
    global.close3dView = close;
    global.install3dView = install;
})(window);
