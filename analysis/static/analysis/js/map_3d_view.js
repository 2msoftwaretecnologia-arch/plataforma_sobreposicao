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
    // Descida da câmera até a propriedade ao abrir (frameProperty), em ms.
    var FRAME_DURATION = 2600;

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
    var trackers = {};
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

    var ICONS = {
        orbit: '<path d="M20 12a8 8 0 1 1-2.3-5.6"/><path d="M20 4v5h-5"/>',
        center: '<circle cx="12" cy="12" r="6.5"/><circle cx="12" cy="12" r="1.5"/><path d="M12 2.5v3M12 18.5v3M2.5 12h3M18.5 12h3"/>',
        expand: '<path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5"/>',
        close: '<path d="M6 6l12 12M18 6 6 18"/>'
    };

    // Botão com ícone e texto; o texto também vira o nome acessível/dica.
    function iconButton(parent, cls, icon, label, title) {
        var b = create('button', cls, parent);
        b.type = 'button';
        b.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true">' + icon + '</svg>';
        b.label = create('span', 'm3d-btn-label', b, label);
        b.title = title;
        return b;
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
        var note = create('div', 'm3d-note', title);
        el.subtitle = create('span', '', note, 'Imagem de satélite sobre o relevo');
        el.imgRetry = create('button', 'm3d-retry m3d-retry-inline', note, 'Tentar de novo');
        el.imgRetry.type = 'button';
        el.imgRetry.hidden = true;
        el.imgRetry.addEventListener('click', retryImagery);

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

        // Ações: ícone + texto (na tela 3D estreita fica só o ícone, ver CSS).
        var actions = create('div', 'm3d-actions', controls);
        el.orbit = iconButton(actions, 'm3d-btn', ICONS.orbit, 'Girar', 'Girar a câmera ao redor da propriedade');
        el.orbit.setAttribute('aria-pressed', 'false');
        el.reset = iconButton(actions, 'm3d-btn', ICONS.center, 'Recentralizar', 'Voltar a câmera para a propriedade');
        el.expand = iconButton(actions, 'm3d-btn', ICONS.expand, 'Tela cheia', 'Abrir o 3D na tela inteira');
        el.expand.hidden = true;
        el.expand.addEventListener('click', function () { enter('full', { opener: el.expand }); });
        el.close = iconButton(actions, 'm3d-btn m3d-close', ICONS.close, 'Fechar', 'Fechar a visão 3D');

        el.bar = bar;
        buildPanel(root);

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
            if (e.key === 'Escape' && !root.hidden && state.mode === 'full') close();
        });
        global.addEventListener('resize', placeLegend);

        state.built = true;
    }

    // A barra do topo quebra em duas linhas quando os seletores de imagem
    // não cabem: a legenda desce junto (no celular ela fica embaixo, pelo CSS).
    function isSmall() {
        return el.root.clientWidth <= 760;
    }

    function placeLegend() {
        if (!state.built || el.root.hidden) return;
        el.legendBox.style.top = isSmall() ? '' : (el.bar.offsetTop + el.bar.offsetHeight + 12) + 'px';
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

    // =====================================================================
    // Painel lateral: bases da análise e camadas temáticas
    // =====================================================================

    var LAYERS_ICON = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3 2.5 8 12 13l9.5-5L12 3Z"/>' +
        '<path d="m2.5 12 9.5 5 9.5-5"/><path d="m2.5 16 9.5 5 9.5-5"/></svg>';

    function buildPanel(root) {
        var panel = el.legendBox = create('aside', 'm3d-panel', root);
        panel.setAttribute('aria-label', 'Bases e camadas temáticas no mapa 3D');

        el.panelToggle = create('button', 'm3d-panel-toggle', panel);
        el.panelToggle.type = 'button';
        el.panelToggle.innerHTML = LAYERS_ICON + '<span class="m3d-panel-label">Camadas</span>';
        el.panelCount = create('span', 'm3d-badge', el.panelToggle);
        create('span', 'm3d-chev', el.panelToggle).setAttribute('aria-hidden', 'true');
        el.panelToggle.addEventListener('click', function () {
            setPanelOpen(panel.classList.contains('is-collapsed'));
        });

        el.panelBody = create('div', 'm3d-panel-body', panel);
        el.panelBody.id = 'm3d-panel-body';
        el.panelToggle.setAttribute('aria-controls', el.panelBody.id);

        // Exagero do relevo (antes ficava na barra do topo).
        var relief = create('label', 'm3d-relief', el.panelBody);
        create('span', '', relief, 'Exagero do relevo');
        el.relief = create('input', '', relief);
        el.relief.type = 'range';
        el.relief.min = '1';
        el.relief.max = '5';
        el.relief.step = '0.5';
        el.relief.value = String(DEFAULT_EXAGGERATION);
        el.relief.setAttribute('aria-label', 'Exagero do relevo');
        el.reliefValue = create('b', '', relief, fmtRelief(DEFAULT_EXAGGERATION));

        var bases = panelSection('Bases da análise', 'Ligue e desligue o que aparece sobre o relevo.');
        el.legend = bases.list;
        el.basesCount = bases.count;

        var th = panelSection('Camadas temáticas', 'Uso do solo, desmatamento, fogo e relevo, com o período e a opacidade.');
        el.thematicsSection = th.root;
        el.thematics = th.list;
        el.thematicsCount = th.count;

        setPanelOpen(true);
    }

    function panelSection(title, hint) {
        // <div>, não <section>: o landing_page.css põe 92px de padding em todo <section>.
        var sec = create('div', 'm3d-sec', el.panelBody);
        var head = create('button', 'm3d-sec-head', sec);
        head.type = 'button';
        head.setAttribute('aria-expanded', 'true');
        create('span', 'm3d-chev', head).setAttribute('aria-hidden', 'true');
        create('span', 'm3d-sec-title', head, title);
        var count = create('span', 'm3d-badge', head);
        var body = create('div', 'm3d-sec-body', sec);
        if (hint) create('p', 'm3d-sec-hint', body, hint);
        var list = create('ul', 'm3d-list', body);
        head.addEventListener('click', function () {
            var open = head.getAttribute('aria-expanded') !== 'true';
            head.setAttribute('aria-expanded', String(open));
            body.hidden = !open;
        });
        return { root: sec, count: count, list: list };
    }

    function setPanelOpen(open) {
        el.legendBox.classList.toggle('is-collapsed', !open);
        el.panelToggle.setAttribute('aria-expanded', String(open));
        el.panelToggle.title = open ? 'Recolher o painel de camadas' : 'Mostrar o painel de camadas';
    }

    // Uma chave liga/desliga (checkbox com cara de interruptor).
    function switchRow(parent, name, checked, color) {
        var label = create('label', 'm3d-row', parent);
        var input = create('input', 'm3d-switch', label);
        input.type = 'checkbox';
        input.checked = checked;
        if (color) create('span', 'm3d-swatch', label).style.setProperty('--c', color);
        create('span', 'm3d-row-name', label, name);
        return input;
    }

    function updateCounts() {
        var bases = state.overlays.filter(function (ov) { return ov.visible; }).length;
        var ths = (state.thematics || []).filter(function (t) { return t.on; }).length;
        el.basesCount.textContent = bases + '/' + state.overlays.length;
        el.thematicsCount.textContent = ths ? ths + ' ligada' + (ths > 1 ? 's' : '') : '';
        el.thematicsCount.hidden = !ths;
        el.panelCount.textContent = String(bases + ths);
        el.panelCount.title = (bases + ths) + ' camada(s) ligada(s)';
    }

    function buildLegend() {
        el.legend.innerHTML = '';
        state.overlays.forEach(function (ov, i) {
            var li = create('li', 'm3d-item', el.legend);
            var check = ov.switchEl = switchRow(li, ov.fonte, ov.visible, ov.isProperty ? PROPERTY_COLOR : ov.color);
            check.addEventListener('change', function () {
                ov.visible = check.checked;
                setOverlayVisible(i, ov.visible);
                updateCounts();
                if (state.mode === 'split' && global.setMapOverlayVisible) global.setMapOverlayVisible(ov.fonte, ov.visible);
            });
        });
        updateCounts();
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

    // Subtítulo da barra: qual imagem está na tela, ou o aviso de erro dela
    // (`kind`: 'error' | 'warn'), com o botão "Tentar de novo" se `retry`.
    function setNote(text, kind, retry) {
        el.subtitle.textContent = text;
        el.subtitle.classList.toggle('is-error', kind === 'error' || kind === true);
        el.subtitle.classList.toggle('is-warn', kind === 'warn');
        el.imgRetry.hidden = !retry;
        placeLegend();
    }

    // Pedidos de tiles de cada fonte do mapa (imagem, relevo, temáticas):
    // quantos chegaram e quantos falharam, para avisar quando a API cai.
    function track(prefix, onChange) {
        trackers[prefix] = { errors: 0, loaded: 0, onChange: onChange };
        return trackers[prefix];
    }

    function trackerFor(sourceId) {
        for (var k in trackers) {
            if (sourceId === k || sourceId.indexOf(k + '-') === 0) return trackers[k];
        }
        return null;
    }

    function evalImagery() {
        var src = state.source;
        if (!src || !state.map) return;
        var extra = trackers['sat-extra'];
        var tr = extra || trackers['sat-esri'];
        if (!tr || !tr.errors) return;
        var name = extra ? src.name : 'Esri';
        if (!tr.loaded) {
            // Sem a imagem escolhida, a Esri cobre o terreno.
            if (extra) state.map.setLayoutProperty('sat-esri', 'visibility', 'visible');
            setNote('Erro ao carregar a API de imagens (' + name + '). O serviço pode estar fora do ar ou sobrecarregado.' +
                (extra ? ' Mostrando a Esri.' : ''), 'error', true);
        } else {
            setNote('Parte da imagem não carregou: a API (' + name + ') falhou em alguns trechos.', 'warn', true);
        }
    }

    function evalTerrain() {
        var tr = trackers.terrain;
        if (tr && tr.errors && !tr.loaded) {
            setNote('Erro ao carregar a API de relevo (AWS Terrain Tiles): o terreno pode aparecer plano.', 'warn', true);
        }
    }

    function readdSource(id, spec, layer, beforeRe) {
        var map = state.map;
        var vis = map.getLayer(id) ? map.getLayoutProperty(id, 'visibility') || 'visible' : 'visible';
        if (map.getLayer(id)) map.removeLayer(id);
        if (map.getSource(id)) map.removeSource(id);
        map.addSource(id, spec);
        if (layer) map.addLayer(Object.assign({ id: id, source: id, layout: { visibility: vis } }, layer), firstLayerMatching(beforeRe));
    }

    // "Tentar de novo" da barra: refaz a lista (se ela falhou) e os tiles que falharam.
    function retryImagery() {
        if (!state.map || !state.source) return;
        state.imgTries = (state.imgTries || 0) + 1;
        var esri = trackers['sat-esri'];
        if (esri && esri.errors) {
            readdSource('sat-esri', {
                type: 'raster', tiles: [withRetry(ESRI_URL, state.imgTries)], tileSize: 256, maxzoom: ESRI_MAX_ZOOM,
                attribution: 'Imagens &copy; Esri'
            }, { type: 'raster' }, /^(sat-extra|th-|ov\d+-)/);
            track('sat-esri', evalImagery);
        }
        var terrain = trackers.terrain;
        if (terrain && terrain.errors) {
            // O terreno é o relevo 3D, não uma camada: troca a fonte e religa.
            state.map.setTerrain(null);
            readdSource('terrain', {
                type: 'raster-dem', tiles: [withRetry(TERRAIN_URL, state.imgTries)], tileSize: 256, maxzoom: TERRAIN_MAX_ZOOM,
                encoding: 'terrarium', attribution: 'Relevo &copy; Mapzen/AWS Terrain Tiles'
            });
            state.map.setTerrain({ source: 'terrain', exaggeration: Number(el.relief.value) });
            track('terrain', evalTerrain);
        }
        selectSource(state.source.key);
    }

    // Ordem das camadas: imagem (sat-*) < relevo sombreado e temáticas (th-*)
    // < bases da análise (ov*). Devolve o id antes do qual inserir.
    function firstLayerMatching(re) {
        var layers = state.map.getStyle().layers;
        for (var i = 0; i < layers.length; i++) {
            if (re.test(layers[i].id)) return layers[i].id;
        }
        return undefined;
    }

    function firstOverlayLayer() {
        return firstLayerMatching(/^(th-|ov\d+-)/);
    }

    // Troca a imagem por cima da Esri; sem `tiles`, fica só a Esri.
    function showTiles(src, opt) {
        var map = state.map;
        if (map.getLayer('sat-extra')) map.removeLayer('sat-extra');
        if (map.getSource('sat-extra')) map.removeSource('sat-extra');
        // Fonte com lista (datas, cenas...) só mostra algo com uma opção escolhida.
        var ready = src && src.tiles && (opt || !(src.options || src.load));
        var tiles = ready ? src.tiles(opt || {}, src.secondary && src.secondary.selected) : null;
        delete trackers['sat-extra'];
        if (tiles) {
            var maxzoom = typeof src.maxzoom === 'function' ? src.maxzoom(opt || {}) : src.maxzoom;
            track('sat-extra', evalImagery);
            map.addSource('sat-extra', {
                type: 'raster',
                tiles: tiles.map(function (u) { return withRetry(u, state.imgTries); }),
                tileSize: src.tileSize || 256,
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
                setNote((src.emptyText || 'Nenhuma imagem desta fonte cobre este ponto.') + ' Mostrando a Esri.', 'warn');
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
            setNote('Erro ao carregar a API de imagens (' + src.name + '): ' + reason + '. Mostrando a Esri.', 'error', true);
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

        // Tiles que chegaram e que falharam, por fonte (ver track).
        map.on('error', function (e) {
            var tr = e && e.sourceId ? trackerFor(e.sourceId) : null;
            if (tr) { tr.errors++; tr.onChange(); }
            if (global.console) console.warn('[visão 3D]', (e && e.sourceId) || '', e && e.error);
        });
        map.on('data', function (e) {
            if (e.dataType !== 'source' || !e.tile || !e.sourceId) return;
            var tr = trackerFor(e.sourceId);
            if (tr) { tr.loaded++; tr.onChange(); }
        });
        track('sat-esri', evalImagery);
        track('terrain', evalTerrain);

        state.map = map;
        // `style.load`, não `load`: o `load` espera todos os tiles (imagem e
        // relevo) e a câmera ficaria parada até lá. A imagem completa depois.
        return new Promise(function (resolve) {
            function ready() {
                addOverlays(map);
                // Começa no Google quando ele está configurado (o 1º da lista).
                selectSource(state.catalog[0].key);
                // Temáticas marcadas antes do mapa ficar pronto (ou numa tentativa anterior).
                (state.thematics || []).forEach(function (t) { if (t.on) showThematic(t); });
                map.on('zoomend', evalAllThematics);
                evalAllThematics();
                resolve(map);
            }
            if (map.isStyleLoaded()) ready();
            else map.once('style.load', ready);
        });
    }

    // =====================================================================
    // Camadas temáticas (os mesmos itens do mapa 2D, ver map_thematic.js)
    // =====================================================================

    var THEMATIC_ATTRIBUTION = {
        mapbiomas: 'MapBiomas', fogo: 'MapBiomas Fogo',
        deter: 'DETER &copy; INPE', focos: 'Focos de calor &copy; INPE (Queimadas)'
    };

    // Declividade: tiles calculados aqui a partir da elevação Terrarium.
    function registerSlopeProtocol(maplibregl) {
        if (state.slopeProtocol || !global.drawSlopeTile || !maplibregl.addProtocol) return;
        state.slopeProtocol = true;
        maplibregl.addProtocol('slope', function (params, abortController) {
            var m = /^slope:\/\/(\d+)\/(\d+)\/(\d+)/.exec(params.url);
            var coords = { z: +m[1], x: +m[2], y: +m[3] };
            var url = global.TERRARIUM_URL.replace('{z}', coords.z).replace('{x}', coords.x).replace('{y}', coords.y);
            return fetch(url, { signal: abortController.signal })
                .then(function (r) {
                    if (!r.ok) throw new Error('elevação indisponível');
                    return r.blob();
                })
                .then(function (blob) { return createImageBitmap(blob); })
                .then(function (bitmap) {
                    var canvas = document.createElement('canvas');
                    canvas.width = 256;
                    canvas.height = 256;
                    global.drawSlopeTile(canvas, bitmap, coords);
                    return new Promise(function (resolve, reject) {
                        canvas.toBlob(function (b) { b ? resolve(b) : reject(new Error('falha ao gerar o tile')); }, 'image/png');
                    });
                })
                .then(function (blob) { return blob.arrayBuffer(); })
                .then(function (data) { return { data: data }; });
        });
    }

    // Quem responde por cada camada, para dizer qual API falhou.
    var THEMATIC_API = {
        mapbiomas: 'do MapBiomas', fogo: 'do MapBiomas',
        deter: 'do INPE (TerraBrasilis)', focos: 'do INPE (Queimadas)',
        declividade: 'de elevação (AWS Terrain Tiles)', relevo: 'de elevação (AWS Terrain Tiles)'
    };

    function buildThematics() {
        var items = global.getThematicItems ? global.getThematicItems(state.imagery) : [];
        // Sem `gl` não há como desenhar no 3D; a declividade precisa do protocolo próprio.
        state.thematics = items.filter(function (it) {
            return it.gl && (it.key !== 'declividade' || global.drawSlopeTile);
        }).map(function (it) {
            return { item: it, on: false, value: it.options ? it.options[0].value : null, opacity: it.opacity, layerIds: [], tries: 0 };
        });
        el.thematicsSection.hidden = !state.thematics.length;
        el.thematics.innerHTML = '';
        state.thematics.forEach(buildThematicItem);
        updateCounts();
    }

    function buildThematicItem(t) {
        var it = t.item;
        var li = t.el = create('li', 'm3d-item m3d-th', el.thematics);
        var top = create('div', 'm3d-th-top', li);
        var check = switchRow(top, it.name, false);
        t.dot = create('span', 'm3d-dot', top);
        t.dot.setAttribute('aria-hidden', 'true');

        var body = create('div', 'm3d-th-body', li);
        body.hidden = true;

        if (it.options) {
            var select = create('select', 'm3d-th-select', body);
            select.setAttribute('aria-label', 'Período de ' + it.name);
            it.options.forEach(function (opt) { create('option', '', select, opt.text).value = opt.value; });
            select.value = t.value;
            select.addEventListener('change', function () {
                t.value = select.value;
                if (t.on) showThematic(t);
            });
        }

        var row = create('label', 'm3d-th-opacity', body);
        create('span', '', row, 'Opacidade');
        var range = create('input', '', row);
        range.type = 'range';
        range.min = '0.1';
        range.max = '1';
        range.step = '0.05';
        range.value = String(t.opacity);
        var pct = create('b', '', row, Math.round(t.opacity * 100) + '%');
        range.addEventListener('input', function () {
            t.opacity = parseFloat(range.value);
            pct.textContent = Math.round(t.opacity * 100) + '%';
            setThematicOpacity(t);
        });

        // Aviso: aproximar, erro da API (com "Tentar de novo") ou falha parcial.
        t.alert = create('div', 'm3d-alert', body);
        t.alert.setAttribute('role', 'status');
        t.alert.hidden = true;
        t.alertText = create('span', '', t.alert);
        t.retry = create('button', 'm3d-retry', t.alert, 'Tentar de novo');
        t.retry.type = 'button';
        t.retry.addEventListener('click', function () {
            t.tries++;
            showThematic(t);
        });

        if (it.legend && it.legend.length) {
            // MapBiomas tem dezenas de classes: a legenda fica recolhida.
            var details = create('details', 'm3d-th-legend', body);
            create('summary', '', details, 'Legenda');
            var grid = create('div', 'm3d-th-legend-grid', details);
            it.legend.forEach(function (entry) {
                var r = create('div', 'm3d-th-legend-row', grid);
                if (entry.img) {
                    var img = create('img', '', r);
                    img.src = entry.img;
                    img.alt = entry.label;
                } else {
                    var sw = create('span', 'm3d-th-swatch', r);
                    if (entry.color) sw.style.background = entry.color; else sw.classList.add('is-empty');
                    r.appendChild(document.createTextNode(entry.label));
                }
            });
        }
        if (it.note) create('p', 'm3d-th-note', body, it.note);

        check.addEventListener('change', function () {
            t.on = check.checked;
            body.hidden = !t.on;
            li.classList.toggle('is-on', t.on);
            if (t.on) showThematic(t); else hideThematic(t);
            evalThematic(t);
            updateCounts();
        });
    }

    function hideThematic(t) {
        delete trackers['th-' + t.item.key];
        t.tracker = null;
        if (!state.map) return;
        var map = state.map;
        t.layerIds.forEach(function (id) {
            if (map.getLayer(id)) map.removeLayer(id);
            if (map.getSource(id)) map.removeSource(id);
        });
        t.layerIds = [];
    }

    // Em "Tentar de novo" a URL muda um pouco: o navegador não reaproveita
    // a resposta de erro guardada no cache.
    function withRetry(url, tries) {
        if (!tries || !/^(https?:|\/)/.test(url)) return url;
        return url + (url.indexOf('?') < 0 ? '?' : '&') + '_tentativa=' + tries;
    }

    // (Re)cria as fontes da temática com o período escolhido.
    function showThematic(t) {
        if (!state.map) return;  // o mapa aplica as marcadas quando ficar pronto
        hideThematic(t);
        var map = state.map;
        var key = t.item.key;
        t.tracker = track('th-' + key, function () { evalThematic(t); });
        t.item.gl(t.value).forEach(function (spec, i) {
            var id = 'th-' + key + '-' + i;
            if (spec.hillshade) {
                // Relevo sombreado por baixo das outras temáticas.
                map.addSource(id, {
                    type: 'raster-dem', tiles: [withRetry(TERRAIN_URL, t.tries)], tileSize: 256, maxzoom: TERRAIN_MAX_ZOOM,
                    encoding: 'terrarium', attribution: 'Relevo &copy; Mapzen/AWS Terrain Tiles'
                });
                map.addLayer({ id: id, type: 'hillshade', source: id }, firstLayerMatching(/^(th-|ov\d+-)/));
            } else {
                map.addSource(id, {
                    type: 'raster',
                    tiles: spec.tiles.map(function (u) {
                        return /^slope:/.test(u) ? u : withRetry(absoluteUrl(u), t.tries);
                    }),
                    tileSize: spec.tileSize || 256,
                    minzoom: spec.minzoom || 0,
                    maxzoom: spec.maxzoom || 19,
                    attribution: spec.attribution || THEMATIC_ATTRIBUTION[key] || ''
                });
                map.addLayer({ id: id, type: 'raster', source: id }, firstLayerMatching(/^ov\d+-/));
            }
            t.layerIds.push(id);
        });
        setThematicOpacity(t);
        evalThematic(t);
    }

    function setThematicOpacity(t) {
        if (!state.map) return;
        var map = state.map, op = t.opacity;
        t.layerIds.forEach(function (id) {
            var layer = map.getLayer(id);
            if (!layer) return;
            if (layer.type === 'hillshade') {
                map.setPaintProperty(id, 'hillshade-shadow-color', 'rgba(0,0,0,' + op + ')');
                map.setPaintProperty(id, 'hillshade-accent-color', 'rgba(0,0,0,' + (op * 0.5) + ')');
                map.setPaintProperty(id, 'hillshade-highlight-color', 'rgba(255,255,255,' + (op * 0.35) + ')');
            } else {
                map.setPaintProperty(id, 'raster-opacity', op);
            }
        });
    }

    // Estado da camada: carregando, carregada, aproximar, falha parcial ou erro.
    function setThematicState(t, kind, text) {
        t.dot.className = 'm3d-dot' + (kind ? ' is-' + kind : '');
        t.dot.title = text || '';
        var showAlert = kind === 'zoom' || kind === 'warn' || kind === 'error';
        t.alert.hidden = !showAlert;
        t.alert.className = 'm3d-alert' + (kind ? ' is-' + kind : '');
        t.alertText.textContent = showAlert ? text : '';
        t.retry.hidden = kind !== 'warn' && kind !== 'error';
        t.el.classList.toggle('has-error', kind === 'error');
    }

    function evalThematic(t) {
        if (!t.on) return setThematicState(t, '', '');
        var api = THEMATIC_API[t.item.key] || 'do provedor';
        var tr = t.tracker;
        if (tr && tr.errors && !tr.loaded) {
            return setThematicState(t, 'error', 'Erro ao carregar a API ' + api + '. O serviço pode estar fora do ar ou sobrecarregado.');
        }
        var min = t.item.minZoom;
        if (state.map && min && state.map.getZoom() < min) {
            return setThematicState(t, 'zoom', 'Aproxime a câmera (zoom ' + min + '+) para ver esta camada.');
        }
        if (tr && tr.errors) {
            return setThematicState(t, 'warn', 'Alguns trechos não carregaram: a API ' + api + ' falhou em parte dos pedidos.');
        }
        if (tr && tr.loaded) return setThematicState(t, 'ok', 'Camada carregada');
        setThematicState(t, 'loading', 'Carregando…');
    }

    function evalAllThematics() {
        (state.thematics || []).forEach(evalThematic);
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
        var w = el.root.clientWidth, h = el.root.clientHeight;
        var small = isSmall();
        var panelOpen = !el.legendBox.classList.contains('is-collapsed');
        var p = {
            top: el.bar.offsetTop + el.bar.offsetHeight + 16,
            bottom: small && panelOpen ? Math.min(h * 0.45, el.legendBox.offsetHeight) + 24 : 60,
            left: !small && panelOpen ? el.legendBox.offsetLeft + el.legendBox.offsetWidth + 24 : 30,
            right: small ? 30 : 70
        };
        // Margens maiores que o mapa fariam o cameraForBounds desistir.
        if (p.left + p.right > w - 120) { p.left = 30; p.right = 30; }
        if (p.top + p.bottom > h - 120) { p.top = 20; p.bottom = 20; }
        return p;
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
        if (animate && !reduceMotion()) map.easeTo(Object.assign({ duration: FRAME_DURATION, essential: true }, tilted));
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

    // Ao abrir a visão 3D a câmera desce até a propriedade e, quando termina,
    // começa a girar sozinha. Mexer no mapa antes disso (ou fechar) cancela.
    function autoOrbit() {
        global.clearTimeout(state.autoOrbitTimer);
        if (reduceMotion()) return;
        state.autoOrbitTimer = global.setTimeout(function () {
            state.autoOrbitTimer = null;
            if (!el.root.hidden) startOrbit();
        }, FRAME_DURATION + 300);
    }

    function stopOrbit() {
        global.clearTimeout(state.autoOrbitTimer);
        state.autoOrbitTimer = null;
        if (!state.orbiting) return;
        state.orbiting = false;
        if (state.orbitFrame) global.cancelAnimationFrame(state.orbitFrame);
        el.orbit.setAttribute('aria-pressed', 'false');
        el.orbit.classList.remove('is-on');
    }

    // =====================================================================
    // Comparação lado a lado: o mapa 2D (Leaflet) e o 3D seguem o mesmo
    // ponto e zoom, e as bases da análise ligadas são as mesmas.
    // =====================================================================

    // Zoom do Leaflet (tiles de 256 px) = zoom do MapLibre (512 px) + 1.
    var LEAFLET_ZOOM_OFFSET = 1;
    var sync = { lock: null, frame2d: 0, frameOv: 0, last3d: null, bound: false };

    function splitActive() {
        return state.mode === 'split' && !!state.map;
    }

    // Câmera do 3D no mesmo lugar do 2D (mantém a inclinação e o giro, a
    // não ser que `extra` traga outros). Tudo num jumpTo só e travado: um
    // movimento à parte antes disso empurraria o 2D para a posição antiga.
    function cameraFrom2D(extra) {
        var lmap = global.getImoveisMap && global.getImoveisMap();
        if (!lmap || !splitActive()) return;
        var c = lmap.getCenter();
        sync.lock = '2d';
        state.map.jumpTo(Object.assign({ center: [c.lng, c.lat], zoom: lmap.getZoom() - LEAFLET_ZOOM_OFFSET }, extra || {}));
        sync.lock = null;
        sync.last3d = null;
    }

    // 2D no mesmo lugar do 3D, só quando o centro ou o zoom mudaram (girar a
    // câmera muda só o rumo e não mexe no 2D).
    function cameraTo2D() {
        var lmap = global.getImoveisMap && global.getImoveisMap();
        if (!lmap || !splitActive() || sync.lock === '2d') return;
        var c = state.map.getCenter();
        var z = state.map.getZoom() + LEAFLET_ZOOM_OFFSET;
        var last = sync.last3d;
        // Tolerância ~1 m: com relevo, o centro oscila um pouco enquanto gira.
        if (last && Math.abs(last.lat - c.lat) < 1e-5 && Math.abs(last.lng - c.lng) < 1e-5 && Math.abs(last.z - z) < 0.01) return;
        sync.last3d = { lat: c.lat, lng: c.lng, z: z };
        sync.lock = '3d';
        lmap.setView([c.lat, c.lng], Math.round(z), { animate: false });
        sync.lock = null;
    }

    // Bases ligadas/desligadas no 2D (legenda, "Marcar todas", cartões).
    function overlaysFrom2D() {
        if (!state.built || !global.getMapOverlayVisibility) return;
        var vis = global.getMapOverlayVisibility();
        state.overlays.forEach(function (ov, i) {
            if (!(ov.fonte in vis) || vis[ov.fonte] === ov.visible) return;
            ov.visible = vis[ov.fonte];
            if (ov.switchEl) ov.switchEl.checked = ov.visible;
            setOverlayVisible(i, ov.visible);
        });
        updateCounts();
    }

    function bindSync() {
        if (sync.bound) return;
        var lmap = global.getImoveisMap && global.getImoveisMap();
        if (!lmap || !state.map) return;
        sync.bound = true;
        lmap.on('move', function () {
            if (!splitActive() || sync.lock === '3d' || sync.frame2d) return;
            sync.frame2d = global.requestAnimationFrame(function () {
                sync.frame2d = 0;
                cameraFrom2D();
            });
        });
        lmap.on('layeradd layerremove', function () {
            if (state.mode !== 'split' || sync.frameOv) return;
            sync.frameOv = global.requestAnimationFrame(function () {
                sync.frameOv = 0;
                overlaysFrom2D();
            });
        });
        state.map.on('move', function () {
            if (sync.lock !== '2d') cameraTo2D();
        });
    }

    // =====================================================================
    // Abrir / fechar
    // =====================================================================

    function setStatus(text, isError) {
        el.status.hidden = !text;
        el.status.textContent = text || '';
        el.status.classList.toggle('is-error', !!isError);
    }

    // Põe a tela 3D no lugar: por cima de tudo ('full') ou dentro da
    // metade direita do quadro do mapa ('split').
    function mountRoot(mode) {
        var host = mode === 'split' ? state.splitHost : document.body;
        if (el.root.parentNode !== host) host.appendChild(el.root);
        el.root.classList.toggle('m3d--embedded', mode === 'split');
        el.root.setAttribute('aria-modal', mode === 'full' ? 'true' : 'false');
        el.root.setAttribute('role', mode === 'full' ? 'dialog' : 'region');
        document.documentElement.classList.toggle('m3d-open', mode === 'full');
        el.close.label.textContent = mode === 'split' ? 'Fechar 3D' : (state.split ? 'Voltar ao lado a lado' : 'Fechar');
        el.close.title = mode === 'split' ? 'Fechar o 3D e voltar só para o mapa 2D'
            : (state.split ? 'Voltar para o 2D e 3D lado a lado' : 'Fechar a visão 3D');
        el.expand.hidden = mode !== 'split';
    }

    function enter(mode, opts) {
        opts = opts || {};
        if (!global.getMapOverlays) return;
        // O mapa 2D em tela cheia esconderia a visão 3D.
        if (document.fullscreenElement && document.exitFullscreen) {
            document.exitFullscreen().catch(function () {});
        }
        var overlays = global.getMapOverlays().filter(function (ov) {
            return ov.geojson && ov.geojson.features && ov.geojson.features.length;
        });
        if (!overlays.length) return;
        state.overlays = overlays;

        if (!state.built) buildDom();
        state.imagery = opts.imagery || state.imagery || {};
        if (mode === 'full' && opts.opener) state.opener = opts.opener;
        state.mode = mode;
        stopOrbit();
        mountRoot(mode);
        el.root.hidden = false;
        buildLegend();
        // Na metade da tela o painel cobriria o mapa: começa recolhido.
        setPanelOpen(mode === 'full' && el.root.clientWidth > 760);
        if (mode === 'full') el.close.focus();

        if (state.map) {
            state.map.resize();
            placeLegend();
            refreshOverlays();
            startView();
            return;
        }

        setStatus('Carregando a imagem 3D...');
        buildImagery();
        if (!state.thematics) buildThematics();
        placeLegend();
        loadMaplibre()
            .then(function (maplibregl) {
                registerSlopeProtocol(maplibregl);
                return createMap(maplibregl);
            })
            .then(function () {
                setStatus('');
                startView();
            })
            .catch(function () {
                setStatus('Não foi possível abrir a visão 3D. Confira a conexão e tente de novo.', true);
                if (state.map) { try { state.map.remove(); } catch (e) { /* já removido */ } }
                state.map = null;
            });
    }

    // Câmera ao abrir: em tela cheia desce até a propriedade; lado a lado
    // parte do mesmo ponto do 2D e só inclina. Depois gira sozinha.
    function startView() {
        if (state.mode === 'split') {
            bindSync();
            var map = state.map;
            cameraFrom2D({ pitch: 0, bearing: 0 });
            var tilted = { pitch: TOUR_PITCH, bearing: TOUR_BEARING };
            if (reduceMotion()) map.jumpTo(tilted);
            else map.easeTo(Object.assign({ duration: FRAME_DURATION, essential: true }, tilted));
        } else {
            frameProperty(true);
        }
        autoOrbit();
    }

    function hide() {
        stopOrbit();
        el.root.hidden = true;
        state.mode = null;
        document.documentElement.classList.remove('m3d-open');
    }

    // "Fechar" / Esc: da tela cheia volta para o lado a lado (se estava
    // nele); do lado a lado, fecha a comparação.
    function close() {
        if (!state.built || el.root.hidden) return;
        if (state.mode === 'full') {
            if (state.split) {
                enter('split');
            } else {
                hide();
            }
            if (state.opener && state.opener.focus) state.opener.focus();
            return;
        }
        saveView('2d');
        setSplit(false);
    }

    // Liga/desliga a comparação no quadro do mapa (botões do cabeçalho).
    var VIEW_KEY = 'mapa_resultados_visualizacao';

    // Última escolha do usuário ('split' ou '2d'); só conveniência local.
    function savedView() {
        try { return global.localStorage.getItem(VIEW_KEY); } catch (e) { return null; }
    }

    function saveView(value) {
        try { global.localStorage.setItem(VIEW_KEY, value); } catch (e) { /* sem armazenamento: tudo bem */ }
    }

    // Roda `fn` quando o elemento aparece na tela (o 3D só baixa o MapLibre
    // e os tiles quando o usuário chega no mapa).
    function whenVisible(node, fn) {
        if (!global.IntersectionObserver) { fn(); return; }
        var io = new global.IntersectionObserver(function (entries) {
            if (!entries.some(function (e) { return e.isIntersecting; })) return;
            io.disconnect();
            fn();
        }, { threshold: 0.15 });
        io.observe(node);
    }

    /**
     * Liga/desliga a comparação no quadro do mapa. `o.lazy`: abre o 3D só
     * quando o mapa aparecer na tela; `o.refit`: reenquadra a propriedade
     * no 2D (na abertura da página, em vez de só manter o centro).
     */
    function setSplit(on, o) {
        o = o || {};
        var p = state.page;
        if (!p) return;
        state.split = on;
        p.stage.classList.toggle('is-split', on);
        p.side.hidden = !on;
        p.buttons.forEach(function (b) {
            var active = (b.getAttribute('data-view') === 'split') === on;
            b.classList.toggle('is-active', active);
            b.setAttribute('aria-pressed', String(active));
        });
        // Na metade da largura o painel "Camadas" do 2D cobriria o mapa.
        if (global.setMapPanelOpen) global.setMapPanelOpen(!on && p.stage.clientWidth >= 640);
        // O Leaflet não percebe sozinho que o quadro dele mudou de largura.
        if (global.resizeImoveisMap) global.resizeImoveisMap(!!o.refit);
        if (on) {
            var start = function () { if (state.split) enter('split', { imagery: p.imagery }); };
            if (o.lazy) whenVisible(p.stage, start); else start();
        } else if (state.mode === 'split') {
            hide();
        }
    }

    /**
     * Liga os controles do cabeçalho do mapa: "Ver em 3D" (tela cheia), o
     * seletor "Mapa 2D | 2D + 3D lado a lado" e um botão "3D" no próprio
     * mapa Leaflet (visível também em tela cheia).
     *
     *   install3dView({ imagery, button, viewSwitch, stage, side })
     */
    function install(opts) {
        opts = opts || {};
        var imagery = opts.imagery || {};
        var headerBtn = opts.button;
        if (headerBtn) {
            headerBtn.hidden = false;
            headerBtn.addEventListener('click', function () { enter('full', { imagery: imagery, opener: headerBtn }); });
        }
        if (opts.viewSwitch && opts.stage && opts.side) {
            var buttons = Array.prototype.slice.call(opts.viewSwitch.querySelectorAll('[data-view]'));
            state.page = { stage: opts.stage, side: opts.side, buttons: buttons, imagery: imagery };
            state.splitHost = opts.side;
            opts.viewSwitch.hidden = false;
            buttons.forEach(function (b) {
                b.addEventListener('click', function () {
                    var on = b.getAttribute('data-view') === 'split';
                    saveView(on ? 'split' : '2d');
                    if (on !== !!state.split) setSplit(on);
                });
            });

            // Padrão: 2D e 3D lado a lado (se o usuário não escolheu só o 2D
            // antes). Em tela estreita o 3D ficaria embaixo do 2D: começa no 2D.
            var saved = savedView();
            var startSplit = saved ? saved === 'split' : opts.stage.clientWidth >= 900;
            if (startSplit && global.getMapOverlays && global.getMapOverlays().length) {
                setSplit(true, { lazy: true, refit: true });
            }

            // Rolou a página e o mapa saiu da tela: para de girar (economiza
            // a placa de vídeo); volta quando o usuário mexer ou clicar em Girar.
            if (global.IntersectionObserver) {
                new global.IntersectionObserver(function (entries) {
                    var visible = entries.some(function (e) { return e.isIntersecting; });
                    if (!visible && state.mode === 'split') stopOrbit();
                }, { threshold: 0 }).observe(opts.stage);
            }
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
                    enter('full', { imagery: imagery, opener: a });
                });
                return bar;
            }
        });
        new Control().addTo(lmap);
    }

    global.open3dView = function (opts) { enter('full', opts); };
    global.close3dView = close;
    global.install3dView = install;
})(window);
