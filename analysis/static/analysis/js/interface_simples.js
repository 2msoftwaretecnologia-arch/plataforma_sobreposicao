/*
 * Interface simples da página inicial: mapa 2D dos imóveis do CAR (mesmos
 * vector tiles do mapa 3D), busca por município ou número do CAR, e o
 * formulário de análise ao lado (upload.js). Clicar num imóvel abre um
 * cartão com os dados e o botão "Analisar este imóvel".
 */
(function () {
    'use strict';

    var cfg = JSON.parse(document.getElementById('bases-3d-config').textContent);
    var PL = window.PropertyLocate;
    var TO_BOUNDS = PL.TO_BOUNDS;
    var MAX_BOUNDS = [[-53.5, -15.5], [-43.0, -3.0]];
    var STATUS_LABEL = PL.STATUS_LABEL;
    var CAR_REGEX = /^[A-Za-z]{2}-\d{7}-[0-9A-Fa-f]{32}$/;

    var cities = cfg.cities || [];
    var sicar = (cfg.bases || []).filter(function (b) { return b.modelo === 'SicarRecord'; })[0];
    var locator = PL.create({ propertyUrl: cfg.propertyUrl, cities: cities });

    // Mesmas cores da legenda (interface_simples.html).
    var STATUS_COLOR = [
        'match', ['upcase', ['coalesce', ['get', 'p1'], '']],
        'AT', '#22c55e',
        'PE', '#f5b400',
        'SU', '#f0532d',
        'CA', '#a3a3a3',
        '#4aa3df'
    ];
    var TARGET_COLOR = '#dba63f';
    var HOVER = ['boolean', ['feature-state', 'hover'], false];
    var SELECTED = ['boolean', ['feature-state', 'selected'], false];

    function fmtHa(n) {
        return Number(n).toLocaleString('pt-BR', { maximumFractionDigits: 2 }) + ' ha';
    }

    function storage(fn) {
        try { return fn(window.localStorage); } catch (e) { return null; }
    }

    function esri(service) {
        return 'https://server.arcgisonline.com/ArcGIS/rest/services/' + service + '/MapServer/tile/{z}/{y}/{x}';
    }

    // =====================================================================
    // Mapa
    // =====================================================================

    var sources = {
        satellite: { type: 'raster', tiles: [esri('World_Imagery')], tileSize: 256, maxzoom: 18,
            attribution: 'Imagens &copy; Esri' },
        roads: { type: 'raster', tiles: [esri('Reference/World_Transportation')], tileSize: 256, maxzoom: 18 },
        places: { type: 'raster', tiles: [esri('Reference/World_Boundaries_and_Places')], tileSize: 256, maxzoom: 18 },
        streets: { type: 'raster', tiles: [esri('World_Street_Map')], tileSize: 256, maxzoom: 18,
            attribution: 'Mapa &copy; Esri' },
        target: { type: 'geojson', data: { type: 'FeatureCollection', features: [] } }
    };

    var basemap = storage(function (st) { return st.getItem('interface_simples:basemap'); }) === 'streets' ? 'streets' : 'satellite';
    function vis(on) { return { visibility: on ? 'visible' : 'none' }; }

    var layers = [
        { id: 'satellite', type: 'raster', source: 'satellite', layout: vis(basemap === 'satellite') },
        { id: 'streets', type: 'raster', source: 'streets', layout: vis(basemap === 'streets') },
        { id: 'roads', type: 'raster', source: 'roads', layout: vis(basemap === 'satellite'), paint: { 'raster-opacity': 0.75 } },
        { id: 'places', type: 'raster', source: 'places', layout: vis(basemap === 'satellite') }
    ];
    var BASEMAP_LAYERS = { satellite: ['satellite', 'roads', 'places'], streets: ['streets'] };

    var CAR_LAYERS = [];
    if (sicar) {
        sources.sicar = {
            type: 'vector',
            tiles: [cfg.tilesUrl.replace('{base}', sicar.modelo)],
            minzoom: sicar.min_zoom,
            maxzoom: cfg.maxTileZoom,
            bounds: [TO_BOUNDS[0][0], TO_BOUNDS[0][1], TO_BOUNDS[1][0], TO_BOUNDS[1][1]]
        };
        layers.push({
            id: 'sicar-fill', type: 'fill', source: 'sicar', 'source-layer': 'layer',
            paint: {
                'fill-color': STATUS_COLOR,
                'fill-opacity': ['case', SELECTED, 0.38, HOVER, 0.26, 0.07]
            }
        }, {
            id: 'sicar-line', type: 'line', source: 'sicar', 'source-layer': 'layer',
            layout: { 'line-join': 'round' },
            paint: {
                'line-color': ['case', SELECTED, '#ffffff', STATUS_COLOR],
                'line-width': ['interpolate', ['linear'], ['zoom'],
                    9, ['case', SELECTED, 3, HOVER, 2.4, 0.7],
                    14, ['case', SELECTED, 4, HOVER, 3.2, 1.8]
                ]
            }
        });
        CAR_LAYERS = ['sicar-fill', 'sicar-line'];
    }

    // Área informada no formulário ou buscada no topo: por cima de tudo.
    layers.push(
        { id: 'target-fill', type: 'fill', source: 'target',
            paint: { 'fill-color': TARGET_COLOR, 'fill-opacity': 0.22 } },
        { id: 'target-casing', type: 'line', source: 'target', layout: { 'line-join': 'round' },
            paint: { 'line-color': '#ffffff', 'line-width': 6, 'line-opacity': 0.85 } },
        { id: 'target-line', type: 'line', source: 'target', layout: { 'line-join': 'round' },
            paint: { 'line-color': TARGET_COLOR, 'line-width': 3 } }
    );

    var map = new maplibregl.Map({
        container: 'map',
        bounds: TO_BOUNDS,
        fitBoundsOptions: { padding: 30 },
        maxBounds: MAX_BOUNDS,
        // 2D: sem rotação nem inclinação.
        dragRotate: false,
        pitchWithRotate: false,
        touchPitch: false,
        maxPitch: 0,
        style: { version: 8, sources: sources, layers: layers }
    });
    map.touchZoomRotate.disableRotation();
    if (map.keyboard && map.keyboard.disableRotation) map.keyboard.disableRotation();

    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'bottom-right');
    map.addControl(new maplibregl.FullscreenControl(), 'bottom-right');
    map.addControl(new maplibregl.ScaleControl({ unit: 'metric' }), 'bottom-right');

    var whenReady = new Promise(function (resolve) { map.on('load', resolve); });

    // Fora do Tocantins levemente escurecido, com o contorno do estado.
    whenReady.then(function () {
        return fetch(window.TOCANTINS_GEOJSON_URL).then(function (r) { return r.json(); });
    }).then(function (geo) {
        var geom = geo.features[0].geometry;
        var outer = geom.type === 'Polygon' ? [geom.coordinates[0]]
            : geom.coordinates.map(function (poly) { return poly[0]; });
        var world = [[-180, -85], [180, -85], [180, 85], [-180, 85], [-180, -85]];
        var before = CAR_LAYERS[0] || 'target-fill';
        map.addSource('mask', { type: 'geojson', data: {
            type: 'Feature', properties: {}, geometry: { type: 'Polygon', coordinates: [world].concat(outer) }
        } });
        map.addSource('tocantins', { type: 'geojson', data: geo });
        map.addLayer({ id: 'mask', type: 'fill', source: 'mask',
            paint: { 'fill-color': '#12271a', 'fill-opacity': 0.4 } }, before);
        map.addLayer({ id: 'tocantins-outline', type: 'line', source: 'tocantins',
            paint: { 'line-color': TARGET_COLOR, 'line-width': 2 } }, before);
    }).catch(function () { /* sem máscara: o mapa funciona igual */ });

    // =====================================================================
    // Fundo do mapa e camada do CAR
    // =====================================================================

    document.querySelectorAll('input[name="s_basemap"]').forEach(function (input) {
        if (input.value === basemap) input.checked = true;
        input.addEventListener('change', function () {
            if (!input.checked) return;
            basemap = input.value;
            storage(function (st) { st.setItem('interface_simples:basemap', basemap); });
            Object.keys(BASEMAP_LAYERS).forEach(function (key) {
                BASEMAP_LAYERS[key].forEach(function (id) {
                    map.setLayoutProperty(id, 'visibility', key === basemap ? 'visible' : 'none');
                });
            });
        });
    });

    var carToggle = document.getElementById('s_toggle_car');
    var hint = document.getElementById('s_hint');

    function updateHint() {
        hint.hidden = !sicar || !carToggle.checked || map.getZoom() >= sicar.min_zoom;
    }

    if (!sicar) {
        // Sem acesso ao SICAR: não há imóveis para mostrar.
        document.getElementById('s_legend').hidden = true;
    } else {
        carToggle.addEventListener('change', function () {
            CAR_LAYERS.forEach(function (id) {
                map.setLayoutProperty(id, 'visibility', carToggle.checked ? 'visible' : 'none');
            });
            if (!carToggle.checked) closeCard();
            updateHint();
        });
        map.on('zoomend', updateHint);
        whenReady.then(updateHint);
    }

    // =====================================================================
    // Área destacada (prévia do formulário ou busca do topo)
    // =====================================================================

    function cardOpen() { return !card.hidden; }

    function fitPadding() {
        if (window.innerWidth < 900) return { top: 70, bottom: cardOpen() ? 300 : 70, left: 40, right: 40 };
        return { top: 70, bottom: 70, left: cardOpen() ? 380 : 70, right: 70 };
    }

    function showTarget(features, bounds) {
        map.getSource('target').setData({ type: 'FeatureCollection', features: features });
        if (bounds) map.fitBounds(bounds, { padding: fitPadding(), maxZoom: 16, duration: 1200 });
    }

    function clearTarget() {
        map.getSource('target').setData({ type: 'FeatureCollection', features: [] });
    }

    // Chamados pelo upload.js quando o usuário informa CAR, ZIP, KML ou
    // coordenadas: a área aparece no mapa antes de analisar.
    var previewSeq = 0;
    window.previewPropertyOnMap = function (req) {
        var seq = ++previewSeq;
        return locator.locate(req).then(function (t) {
            whenReady.then(function () {
                if (seq !== previewSeq) return;
                if (t && t.features) showTarget(t.features, t.bounds);
                else clearTarget();
            });
            return t;
        });
    };
    window.clearPropertyPreview = function () {
        previewSeq++;
        whenReady.then(clearTarget);
    };

    // =====================================================================
    // Cartão do imóvel
    // =====================================================================

    var card = document.getElementById('s_card');
    var cardCar = document.getElementById('s_card_car');
    var cardStatus = document.getElementById('s_card_status');
    var cardArea = document.getElementById('s_card_area');
    var cardCity = document.getElementById('s_card_city');
    var cardNote = document.getElementById('s_card_note');
    var copyBtn = document.getElementById('s_card_copy');
    var selected = null;

    var CODE_OF_LABEL = {};
    Object.keys(STATUS_LABEL).forEach(function (code) { CODE_OF_LABEL[STATUS_LABEL[code]] = code; });

    function cityByCode(code) {
        return cities.filter(function (c) { return c.codigo === code; })[0] || null;
    }

    function setSelected(f) {
        if (selected) map.setFeatureState(selected, { selected: false });
        selected = f ? { source: 'sicar', sourceLayer: 'layer', id: f.id } : null;
        if (selected) map.setFeatureState(selected, { selected: true });
    }

    function openCard(info) {
        cardCar.textContent = info.car;
        var code = info.statusCode || '';
        cardStatus.textContent = STATUS_LABEL[code] || 'Não informada';
        cardStatus.className = 's-badge' + (code ? ' s-badge--' + code : '');
        cardArea.textContent = Number(info.area_ha) > 0 ? fmtHa(info.area_ha) : '-';
        cardCity.textContent = info.city ? info.city.nome : '-';
        cardNote.hidden = !info.note;
        cardNote.textContent = info.note || '';
        copyBtn.classList.remove('is-done');
        card.hidden = false;
    }

    function closeCard() {
        card.hidden = true;
        setSelected(null);
    }

    document.getElementById('s_card_close').addEventListener('click', closeCard);
    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape' && cardOpen()) closeCard();
    });

    copyBtn.addEventListener('click', function () {
        var text = cardCar.textContent;
        var done = function () {
            copyBtn.classList.add('is-done');
            copyBtn.title = 'Copiado!';
            setTimeout(function () {
                copyBtn.classList.remove('is-done');
                copyBtn.title = 'Copiar número do CAR';
            }, 1800);
        };
        if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(text).then(done, function () {});
        } else {
            var range = document.createRange();
            range.selectNodeContents(cardCar);
            var sel = window.getSelection();
            sel.removeAllRanges();
            sel.addRange(range);
            try { if (document.execCommand('copy')) done(); } catch (e) { /* sem cópia */ }
        }
    });

    // Preenche o formulário com o CAR e envia (as validações do upload.js
    // e o loader valem como num envio normal).
    document.getElementById('s_card_analyze').addEventListener('click', function () {
        var radio = document.getElementById('mode_car');
        var input = document.getElementById('car_input');
        var form = document.getElementById('upload_form');
        radio.checked = true;
        radio.dispatchEvent(new Event('change', { bubbles: true }));
        input.value = cardCar.textContent;
        input.dispatchEvent(new Event('input', { bubbles: true }));
        if (form.requestSubmit) form.requestSubmit();
        else form.querySelector('.btn-submit').click();
    });

    // =====================================================================
    // Passar o mouse e clicar nos imóveis
    // =====================================================================

    if (sicar) {
        var hovered = null;
        var clearHover = function () {
            if (hovered) map.setFeatureState(hovered, { hover: false });
            hovered = null;
        };

        // Imóveis declarados se sobrepõem: vale o menor sob o cursor (o que
        // está "dentro" do outro), senão o maior encobriria o menor.
        var featureAt = function (point) {
            if (!carToggle.checked) return null;
            var fs = map.queryRenderedFeatures(point, { layers: ['sicar-fill'] });
            fs.sort(function (a, b) { return (Number(a.properties.area_ha) || 0) - (Number(b.properties.area_ha) || 0); });
            return fs[0] || null;
        };

        map.on('mousemove', function (e) {
            var f = featureAt(e.point);
            map.getCanvas().style.cursor = f ? 'pointer' : '';
            if (!f) return clearHover();
            if (hovered && hovered.id === f.id) return;
            clearHover();
            hovered = { source: 'sicar', sourceLayer: 'layer', id: f.id };
            map.setFeatureState(hovered, { hover: true });
        });
        map.getCanvas().addEventListener('mouseleave', clearHover);

        map.on('click', function (e) {
            var f = featureAt(e.point);
            if (!f) return closeCard();
            var p = f.properties;
            setSelected(f);
            openCard({
                car: String(p.p0 || '').toUpperCase(),
                statusCode: String(p.p1 || '').toUpperCase(),
                area_ha: p.area_ha,
                city: cityByCode(p.mun)
            });
        });
    }

    // =====================================================================
    // Busca do topo: município ou número do CAR
    // =====================================================================

    var searchForm = document.getElementById('s_search');
    var searchInput = document.getElementById('s_search_input');
    var searchMsg = document.getElementById('s_search_msg');
    var datalist = document.getElementById('s_cities');

    cities.slice().sort(function (a, b) { return a.nome.localeCompare(b.nome, 'pt-BR'); }).forEach(function (c) {
        var opt = document.createElement('option');
        opt.value = c.nome;
        datalist.appendChild(opt);
    });

    function norm(s) {
        return String(s || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().trim();
    }

    function cleanCar(s) {
        return String(s || '').replace(/[\s​-‍﻿.]/g, '').replace(/[‐-―−]/g, '-').toUpperCase();
    }

    var msgTimer = null;
    function say(text, kind) {
        clearTimeout(msgTimer);
        searchMsg.hidden = !text;
        searchMsg.textContent = text || '';
        searchMsg.className = 's-search-msg' + (kind ? ' is-' + kind : '');
        if (text && kind !== 'loading') msgTimer = setTimeout(function () { say(''); }, 6000);
    }

    function findCity(text) {
        var q = norm(text);
        if (!q) return null;
        var exact = cities.filter(function (c) { return norm(c.nome) === q; });
        if (exact.length) return exact[0];
        var starts = cities.filter(function (c) { return norm(c.nome).indexOf(q) === 0; });
        if (starts.length === 1) return starts[0];
        var has = cities.filter(function (c) { return norm(c.nome).indexOf(q) >= 0; });
        return has.length === 1 ? has[0] : null;
    }

    function searchCar(car) {
        say('Procurando o imóvel...', 'loading');
        locator.locate({ mode: 'car', car: car }).then(function (t) {
            if (!t) return say('Não foi possível buscar agora. Tente de novo em instantes.', 'warn');
            if (t.status === 'not_found') return say('Este CAR não está na base do SICAR do Tocantins.', 'warn');
            say('');
            setSelected(null);
            openCard({
                car: car,
                statusCode: CODE_OF_LABEL[t.statusLabel] || '',
                area_ha: t.area_ha,
                city: t.city,
                note: t.status === 'outside' ? 'A área fica fora do Tocantins.' : ''
            });
            whenReady.then(function () { showTarget(t.features, t.bounds); });
        });
    }

    searchForm.addEventListener('submit', function (e) {
        e.preventDefault();
        var value = searchInput.value;
        var car = cleanCar(value);
        if (CAR_REGEX.test(car)) {
            searchInput.value = car;
            return searchCar(car);
        }
        var city = findCity(value);
        if (city) {
            say('');
            searchInput.value = city.nome;
            closeCard();
            map.flyTo({ center: [city.lon, city.lat], zoom: Math.max(11, sicar ? sicar.min_zoom + 2 : 11), duration: 1600 });
            return;
        }
        if (!norm(value)) return say('');
        say(/\d/.test(value)
            ? 'Número do CAR incompleto. Use o formato UF-0000000-XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX.'
            : 'Município não encontrado. Escolha um da lista de sugestões.', 'warn');
    });

    // Escolher uma sugestão da lista já leva até o município.
    searchInput.addEventListener('change', function () {
        var city = cities.filter(function (c) { return c.nome === searchInput.value; })[0];
        if (city && searchForm.requestSubmit) searchForm.requestSubmit();
    });
})();
