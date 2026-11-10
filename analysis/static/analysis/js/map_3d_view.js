/*
 * Visão 3D do mapa de sobreposições (página de resultados): imagem de
 * satélite sobre o relevo, com a propriedade e as bases da análise
 * desenhadas por cima, nas mesmas cores do mapa 2D. A imagem é escolhida
 * entre as fontes do mapa 2D (Google, Esri, Wayback, Sentinel-2, Landsat,
 * CBERS-4A, Landsat 5/7 e provedores configurados); o CBERS-2B fica de fora
 * porque cada cena precisa ser baixada e corrigida no servidor antes.
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

    // ImageServer da Esri (Sentinel-2, Landsat) gera cada tile na hora:
    // tiles de 512 px para pedir menos imagens.
    var IMAGE_SERVER_TILE = 512;

    var state = {
        built: false,
        map: null,
        imagery: {},
        overlays: [],
        catalog: [],      // fontes de imagem (imageryCatalog)
        source: null,     // fonte escolhida
        lists: {},        // listas de datas/cenas já buscadas
        imgSeq: 0,        // só vale a resposta da última escolha
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

    function formatDateBR(iso) {
        var p = (iso || '').split('-');
        return p.length === 3 ? p[2] + '/' + p[1] + '/' + p[0] : iso;
    }

    function getJson(url) {
        return fetch(url, { credentials: 'same-origin' }).then(function (r) {
            // Sessão expirada: o login redireciona para a página de entrada (HTML).
            if (r.redirected && /\/auth\//.test(r.url)) throw new Error('sua sessão expirou; entre de novo');
            return r.json().catch(function () { return null; }).then(function (json) {
                if (!json) throw new Error('o servidor respondeu com erro ' + r.status);
                if (!r.ok && json.erro) throw new Error(json.erro);
                return json;
            });
        });
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

        // Imagem de satélite: fonte, data/cena/composição e (Landsat 5/7) composição.
        el.imagery = create('div', 'm3d-imagery', controls);
        el.imgSelect = create('select', 'm3d-select m3d-select-main', el.imagery);
        el.imgSelect.setAttribute('aria-label', 'Imagem de satélite');
        el.imgSelect.title = 'Imagem de satélite';
        el.subSelect = create('select', 'm3d-select', el.imagery);
        el.subSelect.hidden = true;
        el.secSelect = create('select', 'm3d-select', el.imagery);
        el.secSelect.hidden = true;
        el.imgSelect.addEventListener('change', function () { selectSource(el.imgSelect.value); });
        el.subSelect.addEventListener('change', function () {
            if (!state.source) return;
            state.source.selected = el.subSelect.value;
            applyChoice(state.source);
        });
        el.secSelect.addEventListener('change', function () {
            if (!state.source || !state.source.secondary) return;
            state.source.secondary.selected = el.secSelect.value;
            applyChoice(state.source);
        });

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

        el.bar = bar;
        var legend = el.legendBox = create('aside', 'm3d-legend', root);
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
        global.addEventListener('resize', placeLegend);

        state.built = true;
    }

    // A barra do topo quebra em duas linhas quando os seletores de imagem
    // não cabem: a legenda desce junto (no celular ela fica embaixo, pelo CSS).
    function placeLegend() {
        if (!state.built || el.root.hidden) return;
        var small = global.matchMedia && global.matchMedia('(max-width: 760px)').matches;
        el.legendBox.style.top = small ? '' : (el.bar.offsetTop + el.bar.offsetHeight + 12) + 'px';
    }

    function fillSelect(select, options, selected) {
        select.innerHTML = '';
        (options || []).forEach(function (opt) {
            var o = create('option', '', select, opt.text);
            o.value = opt.value;
        });
        select.hidden = !options || !options.length;
        if (!select.hidden) select.value = selected;
        placeLegend();
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

    // A Esri fica sempre no estilo (é o fundo das fontes com `backdrop`);
    // a imagem escolhida entra como a fonte 'sat-extra' (showTiles).
    function rasterSources() {
        return {
            'sat-esri': {
                type: 'raster', tiles: [ESRI_URL], tileSize: 256, maxzoom: ESRI_MAX_ZOOM,
                attribution: 'Imagens &copy; Esri'
            },
            terrain: {
                type: 'raster-dem', tiles: [TERRAIN_URL], tileSize: 256, maxzoom: TERRAIN_MAX_ZOOM,
                encoding: 'terrarium', attribution: 'Relevo &copy; Mapzen/AWS Terrain Tiles'
            }
        };
    }

    // =====================================================================
    // Imagens de satélite (as mesmas fontes do mapa 2D, ver maps.js)
    // =====================================================================

    // ImageServer da Esri como tiles: o MapLibre troca {bbox-epsg-3857}
    // pelo retângulo de cada tile.
    function imageServerTiles(url, rule) {
        var size = IMAGE_SERVER_TILE;
        return [url + '/exportImage?bbox={bbox-epsg-3857}&bboxSR=3857&imageSR=3857&size=' + size + ',' + size +
            '&format=jpgpng&f=image&renderingRule=' + encodeURIComponent(JSON.stringify(rule))];
    }

    // Centro da propriedade: as listas de cenas (CBERS, Landsat 5/7) são do lugar.
    function imageryCenter() {
        var b = boundsOf(targetFeatures());
        if (b) return { lng: (b[0][0] + b[1][0]) / 2, lat: (b[0][1] + b[1][1]) / 2 };
        return state.map.getCenter();
    }

    function centerQuery(url) {
        var c = imageryCenter();
        return url + '?lat=' + c.lat.toFixed(3) + '&lon=' + c.lng.toFixed(3);
    }

    /**
     * Fontes do seletor. Cada uma: `name`, `note` (subtítulo), `tiles(opção,
     * composição)` (null = a Esri do estilo), `options` ou `load()` (lista de
     * datas/cenas/composições), `label`, `initial(opções)`, `secondary`
     * (segundo seletor), `backdrop` (Esri por baixo), `minzoom`/`maxzoom`,
     * `tileSize` e `centered` (lista depende do lugar).
     */
    function imageryCatalog() {
        var im = state.imagery || {};
        var defs = global.IMAGERY_DEFS;
        var list = [];

        if (im.google_tile_url) {
            list.push({
                key: 'google', name: 'Google', note: 'Imagem do Google sobre o relevo',
                maxzoom: GOOGLE_MAX_ZOOM, mapMaxZoom: GOOGLE_MAX_ZOOM + 0.5, attribution: 'Imagens &copy; Google',
                tiles: function () { return [absoluteUrl(im.google_tile_url)]; }
            });
        }
        list.push({ key: 'esri', name: 'Esri (atual)', note: 'Imagem da Esri sobre o relevo', tiles: null });

        if (im.wayback_tile_url && im.wayback_releases_url) {
            list.push({
                key: 'wayback', name: 'Histórico Esri (Wayback)', note: 'Imagem histórica da Esri',
                label: 'Data da imagem', backdrop: true, maxzoom: ESRI_MAX_ZOOM,
                attribution: 'Imagens &copy; Esri (World Imagery Wayback)',
                load: function () {
                    return getJson(absoluteUrl(im.wayback_releases_url)).then(function (j) {
                        return (j.releases || []).map(function (r) {
                            return { value: String(r.id), text: formatDateBR(r.date) };
                        });
                    });
                },
                tiles: function (o) { return [im.wayback_tile_url.replace('{release}', o.value)]; }
            });
        }

        // Planet, Copernicus...: só os configurados no servidor.
        (im.providers || []).forEach(function (p) {
            list.push({
                key: 'prov-' + p.key, name: p.base_name, note: p.base_name, label: p.label,
                backdrop: true, attribution: p.attribution,
                load: function () {
                    return getJson(absoluteUrl(p.layers_url)).then(function (j) {
                        return (j.layers || []).map(function (l) {
                            return { value: encodeURIComponent(l.id), text: l.title, maxZoom: l.max_zoom };
                        });
                    });
                },
                maxzoom: function (o) { return o.maxZoom || 19; },
                tiles: function (o) { return [absoluteUrl(p.tile_url.replace('{layer}', o.value))]; }
            });
        });

        if (defs) {
            list.push({
                key: 'sentinel2', name: 'Sentinel-2 (10 m)', label: 'Composição',
                note: 'Sentinel-2 · imagem gerada na hora, pode levar alguns segundos',
                backdrop: true, tileSize: IMAGE_SERVER_TILE, maxzoom: 16,
                attribution: 'Sentinel-2 (Copernicus) &copy; Esri',
                options: defs.SENTINEL2_RENDERINGS,
                // Em 3D a cor natural é a leitura mais direta; as outras ficam no seletor.
                initial: function () { return 'Natural Color with DRA'; },
                tiles: function (o) { return imageServerTiles(defs.SENTINEL2_URL, { rasterFunction: o.value }); }
            });
            list.push({
                key: 'landsat', name: 'Landsat 8/9 (30 m)', label: 'Composição',
                note: 'Landsat 8/9 · melhor cena recente, gerada na hora',
                backdrop: true, tileSize: IMAGE_SERVER_TILE, maxzoom: 14,
                attribution: 'Landsat (USGS/NASA) &copy; Esri',
                options: defs.LANDSAT_RENDERINGS,
                tiles: function (o) { return imageServerTiles(defs.LANDSAT_URL, defs.landsatRenderingRule(o.value)); }
            });
        }

        if (im.cbers) {
            list.push({
                key: 'cbers', name: 'CBERS-4A (2 m, INPE)', label: 'Cena CBERS-4A', centered: true,
                note: 'CBERS-4A · aparece de perto; ao fundo fica a Esri',
                emptyText: 'Nenhuma cena CBERS-4A cobre este ponto.',
                backdrop: true, minzoom: im.cbers.min_zoom, maxzoom: 18,
                attribution: 'CBERS-4A &copy; INPE (Brazil Data Cube)',
                load: function () {
                    return getJson(centerQuery(absoluteUrl(im.cbers.scenes_url))).then(function (j) {
                        return (j.scenes || []).map(function (s) { return { value: s.id, text: formatDateBR(s.date) }; });
                    });
                },
                tiles: function (o) { return [absoluteUrl(im.cbers.tile_url.replace('{scene}', o.value))]; }
            });
        }

        if (im.landsat_legacy) {
            var ll = im.landsat_legacy;
            list.push({
                key: 'landsat-legacy', name: 'Landsat 5/7 (' + ll.years[0] + '–' + ll.years[1] + ')',
                label: 'Cena (ano · data · satélite · nuvens)', centered: true,
                note: 'Landsat 5/7 · 30 m',
                emptyText: 'Nenhuma cena Landsat 5/7 cobre este ponto.',
                backdrop: true, maxzoom: ll.max_native_zoom,
                attribution: 'Landsat (USGS/NASA) via Microsoft Planetary Computer',
                load: function () {
                    return getJson(centerQuery(absoluteUrl(ll.scenes_url))).then(function (j) {
                        return (j.scenes || []).map(function (s) {
                            var sat = s.platform.replace('landsat-', 'Landsat ');
                            var stripes = s.platform === 'landsat-7' && +s.date.slice(0, 4) >= 2003 ? ' (com faixas)' : '';
                            return {
                                value: s.id, year: s.date.slice(0, 4), cloud: s.cloud,
                                text: s.date.slice(0, 4) + ' · ' + formatDateBR(s.date).slice(0, 5) + ' · ' + sat + stripes + ' · ' + s.cloud + '% nuvens'
                            };
                        });
                    });
                },
                // A de menos nuvem de 2008 (marco do Código Florestal), como no 2D.
                initial: function (options) {
                    var y2008 = options.filter(function (o) { return o.year === '2008'; });
                    if (!y2008.length) return null;
                    return y2008.reduce(function (best, o) { return o.cloud < best.cloud ? o : best; }).value;
                },
                secondary: { label: 'Composição', options: ll.compositions, selected: ll.compositions[0].value },
                tiles: function (o, comp) {
                    return [absoluteUrl(ll.tile_url.replace('{scene}', o.value).replace('{comp}', comp))];
                }
            });
        }
        return list;
    }

    function buildImagery() {
        state.catalog = imageryCatalog();
        fillSelect(el.imgSelect, state.catalog.map(function (s) { return { value: s.key, text: s.name }; }),
            state.catalog[0].key);
        el.imgSelect.hidden = state.catalog.length < 2;
    }

    function setNote(text, isError) {
        el.subtitle.textContent = text;
        el.subtitle.classList.toggle('is-error', !!isError);
    }

    function firstOverlayLayer() {
        var layers = state.map.getStyle().layers;
        for (var i = 0; i < layers.length; i++) {
            if (/^ov\d+-/.test(layers[i].id)) return layers[i].id;
        }
        return undefined;
    }

    // Troca a imagem por cima da Esri; sem `tiles`, fica só a Esri.
    function showTiles(src, opt) {
        var map = state.map;
        if (map.getLayer('sat-extra')) map.removeLayer('sat-extra');
        if (map.getSource('sat-extra')) map.removeSource('sat-extra');
        // Fonte com lista (datas, cenas...) só mostra algo com uma opção escolhida.
        var ready = src && src.tiles && (opt || !(src.options || src.load));
        var tiles = ready ? src.tiles(opt || {}, src.secondary && src.secondary.selected) : null;
        if (tiles) {
            var maxzoom = typeof src.maxzoom === 'function' ? src.maxzoom(opt || {}) : src.maxzoom;
            map.addSource('sat-extra', {
                type: 'raster', tiles: tiles, tileSize: src.tileSize || 256,
                minzoom: src.minzoom || 0, maxzoom: maxzoom || 19, attribution: src.attribution
            });
            map.addLayer({ id: 'sat-extra', type: 'raster', source: 'sat-extra' }, firstOverlayLayer());
        }
        map.setLayoutProperty('sat-esri', 'visibility', !tiles || src.backdrop ? 'visible' : 'none');
    }

    function currentOption(src) {
        return (src.list || []).find(function (o) { return o.value === src.selected; }) || null;
    }

    function applyChoice(src) {
        var opt = currentOption(src);
        showTiles(src, opt);
        setNote(src.note + (opt && src.list.length > 1 ? ' · ' + opt.text : ''));
    }

    function selectSource(key) {
        var src = state.catalog.find(function (s) { return s.key === key; }) || state.catalog[0];
        var seq = ++state.imgSeq;
        state.source = src;
        el.imgSelect.value = src.key;
        state.map.setMaxZoom(src.mapMaxZoom || ESRI_MAX_ZOOM + 2);
        fillSelect(el.subSelect, null);
        fillSelect(el.secSelect, src.secondary ? src.secondary.options : null, src.secondary && src.secondary.selected);
        el.secSelect.setAttribute('aria-label', src.secondary ? src.secondary.label : '');

        if (!src.options && !src.load) {
            src.list = [];
            applyChoice(src);
            return;
        }

        var cacheKey = src.key;
        if (src.centered) {
            var c = imageryCenter();
            cacheKey += '@' + c.lat.toFixed(2) + ',' + c.lng.toFixed(2);
        }
        var pending = src.options ? Promise.resolve(src.options) : state.lists[cacheKey];
        if (!pending) {
            pending = state.lists[cacheKey] = src.load();
            // Enquanto a lista não chega, a Esri segura o fundo.
            showTiles(null);
            setNote('Carregando as imagens disponíveis…');
        }
        pending.then(function (options) {
            if (seq !== state.imgSeq) return;
            src.list = options;
            if (!options.length) {
                showTiles(null);
                fillSelect(el.secSelect, null);
                setNote((src.emptyText || 'Nenhuma imagem desta fonte cobre este ponto.') + ' Mostrando a Esri.', true);
                return;
            }
            var kept = options.some(function (o) { return o.value === src.selected; });
            if (!kept) src.selected = (src.initial && src.initial(options)) || options[0].value;
            fillSelect(el.subSelect, options, src.selected);
            el.subSelect.setAttribute('aria-label', src.label || 'Opção da imagem');
            el.subSelect.title = src.label || '';
            applyChoice(src);
        }, function (err) {
            delete state.lists[cacheKey];
            if (seq !== state.imgSeq) return;
            showTiles(null);
            var reason = err instanceof TypeError ? 'sem resposta do servidor' : err.message;
            setNote('Não foi possível carregar a lista de imagens (' + reason + '). Mostrando a Esri.', true);
        });
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

    function createMap(maplibregl) {
        var layers = [{ id: 'sat-esri', type: 'raster', source: 'sat-esri' }];

        var view = global.getMapView ? global.getMapView() : null;
        var map = new maplibregl.Map({
            container: el.map,
            center: view ? view.center : [-48.3, -10.2],
            zoom: view ? view.zoom : 14,
            maxPitch: 80,
            maxZoom: GOOGLE_MAX_ZOOM + 0.5,
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
                // Começa no Google quando ele está configurado (o 1º da lista).
                selectSource(state.catalog[0].key);
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
            placeLegend();
            refreshOverlays();
            frameProperty(true);
            return;
        }

        setStatus('Carregando a imagem 3D...');
        buildImagery();
        placeLegend();
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
