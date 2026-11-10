/*
 * Página inicial "Explorar": navegação livre, sem análise nenhuma.
 *
 * O mapa é o mesmo da página de resultados (maps.js, em modo `free`): todas
 * as imagens de satélite, camadas temáticas, comparação, download de imagem
 * e a visão 3D. Este arquivo acrescenta o que é da navegação livre:
 *
 *  - ferramentas de desenho (polígono, linha e ponto, com o Leaflet-Geoman),
 *    com área, perímetro e distância;
 *  - a aba "Desenhos" do painel: lista dos desenhos (ficam guardados no
 *    navegador), importar arquivo, baixar KML e a camada opcional do CAR;
 *  - a busca "Ir para" (município, coordenada ou número do CAR);
 *  - a análise de propriedade, opcional: a gaveta com o formulário
 *    (upload.js) e o botão "Analisar esta área" de cada polígono desenhado.
 */
(function (global) {
    'use strict';

    var doc = global.document;
    var L = global.L;

    function readJson(id) {
        var node = doc.getElementById(id);
        try { return node ? JSON.parse(node.textContent) : null; } catch (e) { return null; }
    }

    var cfg = readJson('bases-3d-config') || {};
    var imagery = readJson('map-imagery') || {};
    var cities = cfg.cities || [];
    var locator = global.PropertyLocate.create({ propertyUrl: cfg.propertyUrl, cities: cities });
    var STATUS_LABEL = global.PropertyLocate.STATUS_LABEL;
    var sicar = (cfg.bases || []).filter(function (b) { return b.modelo === 'SicarRecord'; })[0] || null;
    var hasPm = !!(L && L.PM);

    var GOLD = '#dba63f';
    var COLORS = ['#ffd23f', '#ff6b5a', '#4aa3df', '#5fe08a', '#ff8fd0', '#ffffff'];
    var DRAW_FONTE = 'Meus desenhos';
    var HIGHLIGHT_FONTE = 'Área em destaque';
    var VIEW_STORE = 'terraview:explorar:posicao';
    var CAR_STORE = 'terraview:explorar:car';
    var DRAW_STORE = 'terraview:explorar:desenhos:' + (cfg.userKey || '0');
    var EARTH_RADIUS = 6378137;
    var CAR_REGEX = /^[A-Za-z]{2}-\d{7}-[0-9A-Fa-f]{32}$/;
    var KIND_LABEL = { polygon: 'Polígono', line: 'Linha', point: 'Ponto' };
    var SHAPE_OF = { polygon: 'Polygon', line: 'Line', point: 'Marker' };

    // =====================================================================
    // Utilidades
    // =====================================================================

    function load(key) {
        try { return JSON.parse(global.localStorage.getItem(key) || 'null'); } catch (e) { return null; }
    }

    function save(key, value) {
        try { global.localStorage.setItem(key, JSON.stringify(value)); return true; } catch (e) { return false; }
    }

    function el(tag, cls, parent, text) {
        var node = doc.createElement(tag);
        if (cls) node.className = cls;
        if (text !== undefined) node.textContent = text;
        if (parent) parent.appendChild(node);
        return node;
    }

    function fmt(n, digits) {
        return Number(n).toLocaleString('pt-BR', { maximumFractionDigits: digits === undefined ? 0 : digits });
    }

    function fmtArea(m2) {
        var ha = m2 / 10000;
        return fmt(ha, ha < 100 ? 2 : 1) + ' ha';
    }

    function fmtLength(m) {
        return m < 1000 ? fmt(m, 0) + ' m' : fmt(m / 1000, 2) + ' km';
    }

    function fmtLatLng(lat, lng) {
        return lat.toFixed(6) + ', ' + lng.toFixed(6);
    }

    function norm(text) {
        return String(text || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().trim();
    }

    function slug(text) {
        return norm(text).replace(/[^\w.-]+/g, '_').replace(/^_+|_+$/g, '').slice(0, 60) || 'desenho';
    }

    function xml(text) {
        return String(text).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }

    function csrfToken() {
        var input = doc.querySelector('input[name="csrfmiddlewaretoken"]');
        return input ? input.value : '';
    }

    function debounce(fn, ms) {
        var timer = null;
        return function () {
            clearTimeout(timer);
            timer = setTimeout(fn, ms);
        };
    }

    function loadScript(src) {
        return new Promise(function (resolve, reject) {
            var s = doc.createElement('script');
            s.src = src;
            s.async = true;
            s.onload = resolve;
            s.onerror = function () { reject(new Error('Falha ao baixar ' + src)); };
            doc.head.appendChild(s);
        });
    }

    // ----- Medidas (anéis e linhas em [lon, lat]) -----

    // Área geodésica aproximada (esfera), em m²; a mesma conta de download_area.js.
    function ringArea(ring) {
        var a = 0, n = ring.length, rad = Math.PI / 180;
        for (var i = 0; i < n; i++) {
            var p1 = ring[i], p2 = ring[(i + 1) % n];
            a += (p2[0] - p1[0]) * rad * (2 + Math.sin(p1[1] * rad) + Math.sin(p2[1] * rad));
        }
        return Math.abs(a * EARTH_RADIUS * EARTH_RADIUS / 2);
    }

    function pathLength(coords) {
        var total = 0;
        for (var i = 1; i < coords.length; i++) {
            total += L.latLng(coords[i - 1][1], coords[i - 1][0]).distanceTo(L.latLng(coords[i][1], coords[i][0]));
        }
        return total;
    }

    function polygonsOf(geometry) {
        if (geometry.type === 'Polygon') return [geometry.coordinates];
        if (geometry.type === 'MultiPolygon') return geometry.coordinates;
        return [];
    }

    function linesOf(geometry) {
        if (geometry.type === 'LineString') return [geometry.coordinates];
        if (geometry.type === 'MultiLineString') return geometry.coordinates;
        return [];
    }

    function kindOf(geometry) {
        if (!geometry) return null;
        if (polygonsOf(geometry).length) return 'polygon';
        if (linesOf(geometry).length) return 'line';
        return geometry.type === 'Point' ? 'point' : null;
    }

    /** Texto das medidas do desenho: área e perímetro, comprimento ou coordenada. */
    function measureText(geometry) {
        var kind = kindOf(geometry);
        if (kind === 'polygon') {
            var area = 0, perimeter = 0;
            polygonsOf(geometry).forEach(function (poly) {
                poly.forEach(function (ring, k) {
                    area += (k ? -1 : 1) * ringArea(ring);
                    perimeter += pathLength(ring);
                });
            });
            return fmtArea(area) + ' · perímetro ' + fmtLength(perimeter);
        }
        if (kind === 'line') {
            return fmtLength(linesOf(geometry).reduce(function (sum, line) { return sum + pathLength(line); }, 0));
        }
        return fmtLatLng(geometry.coordinates[1], geometry.coordinates[0]);
    }

    function sameCoord(a, b) {
        return a && b && a[0] === b[0] && a[1] === b[1];
    }

    function dedupe(coords) {
        return coords.filter(function (c, i) { return !i || !sameCoord(c, coords[i - 1]); });
    }

    /**
     * Geometria desenhada sem vértices repetidos em sequência (o duplo
     * clique que fecha o desenho marca o mesmo ponto duas vezes); null
     * quando não sobra um polígono ou uma linha.
     */
    function cleanGeometry(geometry) {
        if (!geometry) return null;
        if (geometry.type === 'Point') return geometry;
        if (geometry.type === 'LineString') {
            var line = dedupe(geometry.coordinates);
            return line.length >= 2 ? { type: 'LineString', coordinates: line } : null;
        }
        if (geometry.type === 'Polygon') {
            var rings = geometry.coordinates.map(function (ring) {
                var r = dedupe(ring);
                if (r.length && !sameCoord(r[0], r[r.length - 1])) r.push(r[0]);
                return r;
            }).filter(function (r) { return r.length >= 4; });
            return rings.length ? { type: 'Polygon', coordinates: rings } : null;
        }
        return kindOf(geometry) ? geometry : null;
    }

    // =====================================================================
    // Mapa
    // =====================================================================

    // Só os desenhos desta página são editáveis (com `pmIgnore: false`); as
    // outras camadas do mapa (prévias, recortes, destaque) ficam de fora.
    if (hasPm) L.PM.setOptIn(true);

    var api = global.initImoveisMap([], {
        free: true,
        imagery: imagery,
        defaultBase: 'Satélite (Google)',
        view: load(VIEW_STORE)
    });
    if (!api) return;
    var map = api.map;
    var panel = api.panel;
    var container = map.getContainer();

    // Com o opt-in, o próprio mapa também precisa entrar no Geoman.
    if (hasPm && !map.pm) {
        map.options.pmIgnore = false;
        L.PM.reInitLayer(map);
    }
    hasPm = hasPm && !!map.pm;

    map.on('moveend', debounce(function () {
        var c = map.getCenter();
        save(VIEW_STORE, { center: [c.lat, c.lng], zoom: map.getZoom() });
    }, 400));

    L.control.scale({ imperial: false, position: 'bottomleft' }).addTo(map);

    // Coordenada sob o cursor, como na barra de status do Google Earth.
    (function () {
        var readout = L.control({ position: 'bottomleft' });
        var box;
        readout.onAdd = function () {
            box = L.DomUtil.create('div', 'ex-coords');
            box.textContent = '';
            return box;
        };
        readout.addTo(map);
        map.on('mousemove', function (e) {
            box.textContent = fmtLatLng(e.latlng.lat, e.latlng.lng);
        });
        map.on('mouseout', function () { box.textContent = ''; });
    })();

    // Grupos fixos (existem mesmo vazios): entram na visão 3D e no "Clicar no
    // mapa" do download de imagem pelo `layersByFonte` de maps.js.
    var drawGroup = L.featureGroup().addTo(map);
    var highlightGroup = L.featureGroup().addTo(map);
    api.layersByFonte[DRAW_FONTE] = drawGroup;
    api.legend[DRAW_FONTE] = COLORS[0];
    api.layersByFonte[HIGHLIGHT_FONTE] = highlightGroup;
    api.legend[HIGHLIGHT_FONTE] = GOLD;

    var sync3d = debounce(function () {
        if (global.sync3dOverlays) global.sync3dOverlays();
    }, 200);

    // ----- Área em destaque (imóvel buscado, prévia do formulário, análise) -----

    function clearHighlight() {
        highlightGroup.clearLayers();
        sync3d();
    }

    function showHighlight(features, opts) {
        opts = opts || {};
        highlightGroup.clearLayers();
        var labelled = features.map(function (f) {
            return {
                type: 'Feature',
                properties: { _fonte: HIGHLIGHT_FONTE, _label: opts.label || '', _area: opts.area || '' },
                geometry: f.geometry
            };
        });
        var layer = L.geoJSON({ type: 'FeatureCollection', features: labelled }, {
            interactive: false,
            style: { color: GOLD, weight: 3, dashArray: '8 6', fillColor: GOLD, fillOpacity: 0.1 },
            pointToLayer: function (feature, latlng) {
                return L.circleMarker(latlng, { radius: 8, color: '#fff', weight: 2, fillColor: GOLD, fillOpacity: 1, dashArray: null });
            }
        });
        highlightGroup.addLayer(layer);
        if (opts.fit !== false) {
            var bounds = layer.getBounds();
            if (bounds.isValid()) {
                var fit = panel.fitPadding(50);
                fit.maxZoom = opts.maxZoom || 17;
                map.fitBounds(bounds, fit);
            }
        }
        sync3d();
        return layer;
    }

    // =====================================================================
    // Desenhos
    // =====================================================================

    var items = [];      // { id, kind, name, color, layer, geometry, measure }
    var counters = { polygon: 0, line: 0, point: 0 };
    var editing = false;
    var drawing = null;  // 'polygon' | 'line' | 'point' enquanto desenha
    var working = null;  // camada provisória do Geoman
    var listEl = null, countEl = null, emptyEl = null, statusEl = null;
    var toolButtons = {};

    function pinIcon(color) {
        return L.divIcon({
            className: 'ex-pin',
            html: '<svg viewBox="0 0 26 34" aria-hidden="true"><path d="M13 33S2 20.5 2 12.5a11 11 0 0 1 22 0C24 20.5 13 33 13 33z" fill="' +
                color + '" stroke="#17301f" stroke-width="1.6"/><circle cx="13" cy="12.5" r="4" fill="#17301f"/></svg>',
            iconSize: [26, 34],
            iconAnchor: [13, 33],
            tooltipAnchor: [0, -30],
            popupAnchor: [0, -30]
        });
    }

    function pathStyle(color, kind) {
        return kind === 'line'
            ? { color: color, weight: 3 }
            : { color: color, weight: 3, fillColor: color, fillOpacity: 0.12 };
    }

    function layerFor(geometry, color) {
        var kind = kindOf(geometry);
        var opts = Object.assign({ pmIgnore: false }, pathStyle(color, kind));
        var toLatLngs = L.GeoJSON.coordsToLatLngs;
        if (kind === 'point') {
            return L.marker([geometry.coordinates[1], geometry.coordinates[0]], { pmIgnore: false, icon: pinIcon(color) });
        }
        if (kind === 'line') {
            return L.polyline(toLatLngs(geometry.coordinates, geometry.type === 'LineString' ? 0 : 1), opts);
        }
        return L.polygon(toLatLngs(geometry.coordinates, geometry.type === 'Polygon' ? 1 : 2), opts);
    }

    /** Há uma ferramenta em uso: cliques no mapa não abrem cartões. */
    function busy() {
        return !!drawing || editing || container.classList.contains('is-selecting-area');
    }

    /** Medidas, rótulo e propriedades (levadas para o 3D) depois de qualquer mudança. */
    function refreshItem(item) {
        item.geometry = item.layer.toGeoJSON().geometry;
        item.measure = measureText(item.geometry);
        item.layer.feature = {
            type: 'Feature',
            properties: { _fonte: DRAW_FONTE, _label: item.name, _area: item.kind === 'point' ? '' : item.measure, _color: item.color },
            geometry: item.geometry
        };
        item.layer.downloadLabel = item.name;
        if (item.layer.getTooltip()) item.layer.setTooltipContent(item.name);
        else item.layer.bindTooltip(item.name, item.kind === 'point'
            ? { permanent: true, direction: 'top', className: 'ex-label' }
            : { sticky: true });
    }

    function persist() {
        var ok = save(DRAW_STORE, {
            type: 'FeatureCollection',
            features: items.map(function (item) {
                return { type: 'Feature', properties: { id: item.id, name: item.name, color: item.color }, geometry: item.geometry };
            })
        });
        if (!ok) setStatus('Os desenhos passaram do espaço do navegador e não ficaram guardados. Baixe o KML para não perder.', 'error');
    }

    function changed(keepList) {
        if (!keepList) renderList();
        persist();
        sync3d();
    }

    function addItem(geometry, props, silent) {
        var kind = kindOf(geometry);
        if (!kind) return null;
        props = props || {};
        counters[kind] += 1;
        var item = {
            id: props.id || (Date.now().toString(36) + Math.random().toString(36).slice(2, 7)),
            kind: kind,
            name: props.name || (KIND_LABEL[kind] + ' ' + counters[kind]),
            color: props.color || COLORS[items.length % COLORS.length]
        };
        item.layer = layerFor(geometry, item.color);
        item.layer.on('pm:edit pm:dragend pm:update', function () {
            refreshItem(item);
            changed();
        });
        item.layer.on('click', function (e) {
            if (busy()) return;
            L.DomEvent.stopPropagation(e);
            openItemPopup(item, e.latlng);
        });
        drawGroup.addLayer(item.layer);
        items.push(item);
        refreshItem(item);
        if (!silent) changed();
        return item;
    }

    function removeItem(item) {
        if (item.layer.pm && item.layer.pm.enabled && item.layer.pm.enabled()) item.layer.pm.disable();
        drawGroup.removeLayer(item.layer);
        items = items.filter(function (i) { return i !== item; });
        map.closePopup();
        changed();
    }

    function setColor(item, color) {
        item.color = color;
        if (item.kind === 'point') item.layer.setIcon(pinIcon(color));
        else item.layer.setStyle(pathStyle(color, item.kind));
        refreshItem(item);
        changed();
    }

    function zoomTo(item) {
        if (item.kind === 'point') {
            map.setView(item.layer.getLatLng(), Math.max(map.getZoom(), 16));
            return;
        }
        var fit = panel.fitPadding(50);
        fit.maxZoom = 18;
        map.fitBounds(item.layer.getBounds(), fit);
    }

    function popupButton(parent, label, cls, run) {
        var b = el('button', 'ex-popup-btn' + (cls ? ' ' + cls : ''), parent, label);
        b.type = 'button';
        b.addEventListener('click', run);
        return b;
    }

    function openItemPopup(item, latlng) {
        var box = el('div', 'ex-popup');
        el('strong', 'ex-popup-title', box, item.name);
        el('div', 'ex-popup-meta', box, KIND_LABEL[item.kind] + ' · ' + item.measure);
        var actions = el('div', 'ex-popup-actions', box);
        if (item.kind === 'polygon') {
            popupButton(actions, 'Analisar esta área', 'is-primary', function () { analyzeItem(item); });
        }
        if (hasPm) {
            popupButton(actions, 'Editar', '', function () {
                map.closePopup();
                startEdit(item);
            });
        }
        popupButton(actions, 'Apagar', 'is-danger', function () { removeItem(item); });
        L.popup({ maxWidth: 320 }).setLatLng(latlng).setContent(box).openOn(map);
    }

    // ----- Barra de dica (mesmo visual da área do download de imagem) -----

    var hint = L.DomUtil.create('div', 'map-area-hint', container);
    hint.hidden = true;
    L.DomEvent.disableClickPropagation(hint);
    L.DomEvent.disableScrollPropagation(hint);
    var hintText = el('span', 'map-area-hint__text', hint);
    var hintActions = el('span', 'map-area-hint__actions', hint);

    function showHint(text, actions) {
        hintText.textContent = text;
        hintActions.textContent = '';
        actions.forEach(function (a) {
            var b = el('button', 'map-area-hint__btn' + (a.primary ? ' is-primary' : ''), hintActions, a.label);
            b.type = 'button';
            b.addEventListener('click', a.run);
        });
        hint.hidden = false;
    }

    function hideHint() {
        hint.hidden = true;
    }

    function syncTools() {
        Object.keys(toolButtons).forEach(function (key) {
            var on = key === 'edit' ? editing : drawing === key;
            toolButtons[key].classList.toggle('is-active', on);
            toolButtons[key].setAttribute('aria-pressed', String(on));
        });
        container.classList.toggle('ex-is-drawing', !!drawing);
    }

    // ----- Desenhar -----

    function drawOptions(kind) {
        var options = {
            snappable: true,
            snapDistance: 14,
            tooltips: false,
            continueDrawing: false,
            templineStyle: { color: GOLD, weight: 3 },
            hintlineStyle: { color: GOLD, weight: 2, dashArray: [6, 6] },
            pathOptions: { color: GOLD, weight: 3 }
        };
        if (kind !== 'point') options.finishOn = 'dblclick';
        // A análise recusa contorno que se cruza: o desenho já não deixa.
        if (kind === 'polygon') options.allowSelfIntersection = false;
        if (kind === 'point') options.markerStyle = { icon: pinIcon(COLORS[items.length % COLORS.length]) };
        return options;
    }

    function drawer(kind) {
        return map.pm.Draw[SHAPE_OF[kind]];
    }

    function drawHintText(cursor) {
        if (drawing === 'point') return 'Clique no mapa para colocar o ponto.';
        var pts = working && working.getLatLngs ? working.getLatLngs().slice() : [];
        if (!pts.length) {
            return drawing === 'polygon'
                ? 'Clique no mapa para marcar os vértices. Para fechar, dê um duplo clique ou clique no primeiro ponto.'
                : 'Clique no mapa para marcar o caminho. Dê um duplo clique para terminar.';
        }
        if (cursor) pts.push(cursor);
        var coords = pts.map(function (p) { return [p.lng, p.lat]; });
        if (drawing === 'line') return 'Distância: ' + fmtLength(pathLength(coords));
        if (coords.length < 3) return 'Lado: ' + fmtLength(pathLength(coords));
        return 'Área: ' + fmtArea(ringArea(coords)) + ' · perímetro ' + fmtLength(pathLength(coords.concat([coords[0]])));
    }

    function updateDrawHint(e) {
        if (drawing) hintText.textContent = drawHintText(e && e.latlng);
    }

    function stopDraw() {
        if (hasPm) map.pm.disableDraw();
    }

    function startDraw(kind) {
        if (!hasPm || container.classList.contains('is-selecting-area')) return;
        if (drawing === kind) { stopDraw(); return; }
        stopEdit();
        stopDraw();
        map.closePopup();
        map.pm.enableDraw(SHAPE_OF[kind], drawOptions(kind));
    }

    if (hasPm) {
        // O duplo clique que termina o desenho não pode também aproximar o mapa.
        var dblZoom = false;
        map.on('pm:drawstart', function (e) {
            drawing = Object.keys(SHAPE_OF).filter(function (k) { return SHAPE_OF[k] === e.shape; })[0] || null;
            working = e.workingLayer || null;
            if (!drawing) return;
            dblZoom = dblZoom || map.doubleClickZoom.enabled();
            map.doubleClickZoom.disable();
            var kind = drawing;
            var actions = [{ label: 'Cancelar', run: stopDraw }];
            if (kind !== 'point') {
                actions.unshift({ label: 'Desfazer', run: function () { drawer(kind)._removeLastVertex(); updateDrawHint(); } });
                actions.push({ label: 'Concluir', primary: true, run: function () { drawer(kind)._finishShape(); } });
            }
            showHint(drawHintText(), actions);
            syncTools();
        });
        map.on('pm:drawend', function () {
            drawing = null;
            working = null;
            hideHint();
            syncTools();
            setTimeout(function () {
                if (!drawing && dblZoom) { map.doubleClickZoom.enable(); dblZoom = false; }
            }, 350);
        });
        map.on('mousemove', updateDrawHint);
        map.on('click', function () { if (drawing) setTimeout(updateDrawHint, 0); });

        map.on('pm:create', function (e) {
            var geometry = null;
            try { geometry = cleanGeometry(e.layer.toGeoJSON().geometry); } catch (err) { /* forma sem geometria */ }
            // A camada do Geoman sai; o desenho entra pela mesma fábrica dos
            // importados e dos guardados (cor, rótulo, cartão, edição).
            e.layer.remove();
            if (!geometry) return;
            var item = addItem(geometry);
            if (item) flashRow(item);
        });
    }

    // ----- Editar -----

    function startEdit(only) {
        if (!hasPm) return;
        stopDraw();
        map.closePopup();
        var targets = only ? [only] : items;
        if (!targets.length) {
            setStatus('Ainda não há nenhum desenho para editar.', 'warn');
            return;
        }
        items.forEach(function (item) { if (item.layer.pm) item.layer.pm.disable(); });
        targets.forEach(function (item) {
            if (item.layer.pm) item.layer.pm.enable({ snappable: true, snapDistance: 14, allowSelfIntersection: false });
        });
        editing = true;
        showHint('Arraste os pontos para ajustar a forma; o ponto do meio de um lado cria um vértice e o botão direito apaga um.', [
            { label: 'Concluir', primary: true, run: stopEdit }
        ]);
        syncTools();
    }

    function stopEdit() {
        if (!editing) return;
        items.forEach(function (item) { if (item.layer.pm) item.layer.pm.disable(); });
        editing = false;
        hideHint();
        syncTools();
    }

    doc.addEventListener('keydown', function (e) {
        var tag = (e.target && e.target.tagName) || '';
        if (/^(INPUT|SELECT|TEXTAREA)$/.test(tag)) return;
        if (drawing) {
            if (e.key === 'Escape') { e.preventDefault(); stopDraw(); }
            else if (drawing !== 'point' && e.key === 'Enter') { e.preventDefault(); drawer(drawing)._finishShape(); }
            else if (drawing !== 'point' && (e.key === 'Backspace' || e.key === 'Delete')) {
                e.preventDefault();
                drawer(drawing)._removeLastVertex();
                updateDrawHint();
            }
        } else if (editing && (e.key === 'Escape' || e.key === 'Enter')) {
            e.preventDefault();
            stopEdit();
        }
    });

    // ----- Barra de ferramentas (dentro do mapa: vale também em tela cheia) -----

    var TOOL_ICONS = {
        polygon: '<path d="M5 8.5 13 4l6.5 6-3 9.5H7z"/><circle cx="5" cy="8.5" r="1.6"/><circle cx="13" cy="4" r="1.6"/><circle cx="19.5" cy="10" r="1.6"/><circle cx="16.5" cy="19.5" r="1.6"/><circle cx="7" cy="19.5" r="1.6"/>',
        line: '<path d="M4.5 18.5 10 9l5 6 4.5-9.5"/><circle cx="4.5" cy="18.5" r="1.6"/><circle cx="10" cy="9" r="1.6"/><circle cx="15" cy="15" r="1.6"/><circle cx="19.5" cy="5.5" r="1.6"/>',
        point: '<path d="M12 21s-6.5-6-6.5-11a6.5 6.5 0 0 1 13 0c0 5-6.5 11-6.5 11z"/><circle cx="12" cy="10" r="2.5"/>',
        edit: '<path d="M4.5 19.5l1-4.2L15.8 5a1.8 1.8 0 0 1 2.6 0l.6.6a1.8 1.8 0 0 1 0 2.6L8.7 18.5z"/><path d="M14 6.8l3.2 3.2"/>'
    };
    var TOOLS = [
        { key: 'polygon', label: 'Polígono', title: 'Desenhar um polígono (área e perímetro)', run: function () { startDraw('polygon'); } },
        { key: 'line', label: 'Linha', title: 'Desenhar uma linha e medir a distância', run: function () { startDraw('line'); } },
        { key: 'point', label: 'Ponto', title: 'Marcar um ponto', run: function () { startDraw('point'); } },
        { key: 'edit', label: 'Editar', title: 'Ajustar os vértices dos desenhos', run: function () { if (editing) stopEdit(); else startEdit(); } }
    ];

    if (hasPm) {
        var toolbar = L.control({ position: 'topleft' });
        toolbar.onAdd = function () {
            var bar = L.DomUtil.create('div', 'ex-tools');
            bar.setAttribute('role', 'toolbar');
            bar.setAttribute('aria-label', 'Ferramentas de desenho');
            TOOLS.forEach(function (tool) {
                var b = L.DomUtil.create('button', 'ex-tool', bar);
                b.type = 'button';
                b.title = tool.title;
                b.setAttribute('aria-pressed', 'false');
                b.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true">' + TOOL_ICONS[tool.key] + '</svg>' +
                    '<span class="ctl-label">' + tool.label + '</span>';
                b.addEventListener('click', tool.run);
                toolButtons[tool.key] = b;
            });
            L.DomEvent.disableClickPropagation(bar);
            return bar;
        };
        toolbar.addTo(map);
        // Em cima dos outros botões do canto (zoom, comparar...).
        var corner = toolbar.getContainer().parentNode;
        corner.insertBefore(toolbar.getContainer(), corner.firstChild);
    }

    // =====================================================================
    // KML (baixar os desenhos e enviar um polígono para a análise)
    // =====================================================================

    // Cor do KML: aabbggrr.
    function kmlColor(hex, alpha) {
        var h = hex.replace('#', '');
        return alpha + h.slice(4, 6) + h.slice(2, 4) + h.slice(0, 2);
    }

    function kmlCoords(coords) {
        return coords.map(function (c) { return c[0] + ',' + c[1] + ',0'; }).join(' ');
    }

    function kmlPolygon(rings) {
        return '<Polygon>' + rings.map(function (ring, k) {
            var tag = k ? 'innerBoundaryIs' : 'outerBoundaryIs';
            return '<' + tag + '><LinearRing><coordinates>' + kmlCoords(ring) + '</coordinates></LinearRing></' + tag + '>';
        }).join('') + '</Polygon>';
    }

    function kmlGeometry(geometry) {
        if (geometry.type === 'Point') return '<Point><coordinates>' + kmlCoords([geometry.coordinates]) + '</coordinates></Point>';
        var parts = polygonsOf(geometry).map(kmlPolygon).concat(linesOf(geometry).map(function (line) {
            return '<LineString><tessellate>1</tessellate><coordinates>' + kmlCoords(line) + '</coordinates></LineString>';
        }));
        return parts.length === 1 ? parts[0] : '<MultiGeometry>' + parts.join('') + '</MultiGeometry>';
    }

    function kmlDocument(list, name) {
        return '<?xml version="1.0" encoding="UTF-8"?>\n<kml xmlns="http://www.opengis.net/kml/2.2"><Document><name>' + xml(name) + '</name>' +
            list.map(function (item) {
                return '<Placemark><name>' + xml(item.name) + '</name><description>' + xml(item.measure) + '</description>' +
                    '<Style><LineStyle><color>' + kmlColor(item.color, 'ff') + '</color><width>3</width></LineStyle>' +
                    '<PolyStyle><color>' + kmlColor(item.color, '33') + '</color></PolyStyle></Style>' +
                    kmlGeometry(item.geometry) + '</Placemark>';
            }).join('') + '</Document></kml>';
    }

    function downloadKml() {
        if (!items.length) {
            setStatus('Ainda não há nenhum desenho para baixar.', 'warn');
            return;
        }
        var blob = new Blob([kmlDocument(items, 'Meus desenhos')], { type: 'application/vnd.google-earth.kml+xml' });
        var a = doc.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = 'meus_desenhos.kml';
        doc.body.appendChild(a);
        a.click();
        a.remove();
        setTimeout(function () { URL.revokeObjectURL(a.href); }, 2000);
    }

    // =====================================================================
    // Aba "Desenhos" do painel
    // =====================================================================

    var ROW_ICONS = {
        go: '<circle cx="12" cy="12" r="7"/><circle cx="12" cy="12" r="2"/><path d="M12 2.5v3M12 18.5v3M2.5 12h3M18.5 12h3"/>',
        analyze: '<path d="M4.5 19.5h15"/><path d="M7.5 16v-5M12 16V6.5M16.5 16v-7.5"/>',
        remove: '<path d="M5 7.5h14M10 7.5V5h4v2.5M7 7.5l.8 11.5h8.4L17 7.5M10.5 11v5M13.5 11v5"/>'
    };

    function iconButton(parent, icon, title, run) {
        var b = el('button', 'ex-item-btn', parent);
        b.type = 'button';
        b.title = title;
        b.setAttribute('aria-label', title);
        b.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true">' + ROW_ICONS[icon] + '</svg>';
        b.addEventListener('click', run);
        return b;
    }

    function setStatus(text, kind) {
        if (!statusEl) return;
        statusEl.textContent = text || '';
        statusEl.className = 'ex-status' + (kind ? ' is-' + kind : '');
        statusEl.hidden = !text;
        clearTimeout(setStatus.timer);
        if (text && kind !== 'loading') setStatus.timer = setTimeout(function () { statusEl.hidden = true; }, 8000);
    }

    function renderList() {
        if (!listEl) return;
        listEl.textContent = '';
        countEl.textContent = items.length ? String(items.length) : '';
        emptyEl.hidden = !!items.length;
        items.forEach(function (item) {
            var row = el('div', 'ex-item', listEl);
            row.dataset.id = item.id;

            var swatch = el('button', 'ex-item-color', row);
            swatch.type = 'button';
            swatch.title = 'Trocar a cor';
            swatch.setAttribute('aria-label', 'Trocar a cor de ' + item.name);
            swatch.style.setProperty('--c', item.color);
            swatch.addEventListener('click', function () {
                setColor(item, COLORS[(COLORS.indexOf(item.color) + 1) % COLORS.length]);
            });

            var main = el('div', 'ex-item-main', row);
            var name = el('input', 'ex-item-name', main);
            name.type = 'text';
            name.value = item.name;
            name.maxLength = 80;
            name.setAttribute('aria-label', 'Nome do desenho');
            name.addEventListener('change', function () {
                item.name = name.value.trim() || item.name;
                name.value = item.name;
                refreshItem(item);
                changed(true);
            });
            name.addEventListener('keydown', function (e) { if (e.key === 'Enter') name.blur(); });
            var meta = el('span', 'ex-item-meta', main, item.measure);
            meta.title = meta.textContent;

            var actions = el('div', 'ex-item-actions', row);
            iconButton(actions, 'go', 'Ir até o desenho', function () { zoomTo(item); });
            if (item.kind === 'polygon') {
                iconButton(actions, 'analyze', 'Analisar esta área (opcional)', function () { analyzeItem(item); });
            }
            iconButton(actions, 'remove', 'Apagar', function () { removeItem(item); });
        });
    }

    function flashRow(item) {
        if (!listEl) return;
        var row = listEl.querySelector('[data-id="' + item.id + '"]');
        if (!row) return;
        row.classList.add('is-new');
        if (row.scrollIntoView) row.scrollIntoView({ block: 'nearest' });
        setTimeout(function () { row.classList.remove('is-new'); }, 1600);
    }

    // ----- Importar arquivo (o servidor converte: ImageDownloadAreaView) -----

    function importFile(file) {
        if (!file || !imagery.download_area_url) return;
        setStatus('Lendo ' + file.name + '…', 'loading');
        var body = new FormData();
        body.append('arquivo', file);
        fetch(imagery.download_area_url, {
            method: 'POST', body: body, credentials: 'same-origin', headers: { 'X-CSRFToken': csrfToken() }
        }).then(function (r) {
            return r.json().catch(function () { return null; }).then(function (json) {
                if (r.ok && json && json.geometry) return json;
                throw new Error((json && json.erro) || 'Não foi possível ler o arquivo (erro ' + r.status + ').');
            });
        }).then(function (json) {
            var item = addItem(json.geometry, { name: json.nome });
            if (!item) throw new Error('O arquivo não tem nenhum polígono.');
            setStatus('');
            zoomTo(item);
            flashRow(item);
        }).catch(function (err) {
            setStatus((err && err.message) || 'Não foi possível ler o arquivo.', 'error');
        });
    }

    // ----- Camada opcional: imóveis do CAR (os vector tiles do tour 3D) -----

    var MAPLIBRE_LEAFLET = 'https://unpkg.com/@maplibre/maplibre-gl-leaflet@0.0.22/leaflet-maplibre-gl.js';
    var CAR_STATUS = [
        { code: 'AT', label: 'Ativo', color: '#5fe08a' },
        { code: 'PE', label: 'Pendente', color: '#ffd23f' },
        { code: 'SU', label: 'Suspenso', color: '#ff6b3d' },
        { code: 'CA', label: 'Cancelado', color: '#d9d3c7' }
    ];
    var carLayer = null, carOn = false, carToggle = null, carNote = null, carLegend = null;
    // Zoom do Leaflet = zoom do MapLibre + 1 (tiles de 512 px).
    var carMinZoom = sicar ? sicar.min_zoom + 1 : 0;

    function carStyle() {
        var color = ['match', ['upcase', ['coalesce', ['get', 'p1'], '']]];
        CAR_STATUS.forEach(function (s) { color.push(s.code, s.color); });
        color.push('#4aa3df');
        return {
            version: 8,
            sources: {
                sicar: {
                    type: 'vector',
                    tiles: [cfg.tilesUrl.replace('{base}', sicar.modelo)],
                    minzoom: sicar.min_zoom,
                    maxzoom: cfg.maxTileZoom
                }
            },
            layers: [
                { id: 'car-fill', type: 'fill', source: 'sicar', 'source-layer': 'layer',
                    paint: { 'fill-color': color, 'fill-opacity': 0.07 } },
                { id: 'car-line', type: 'line', source: 'sicar', 'source-layer': 'layer',
                    paint: { 'line-color': color, 'line-width': 1.4 } }
            ]
        };
    }

    function ensureMaplibreLayer() {
        var gl = global.loadMaplibreGl ? global.loadMaplibreGl()
            : global.maplibregl ? Promise.resolve() : loadScript('https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.js');
        return gl.then(function () {
            return L.maplibreGL ? null : loadScript(MAPLIBRE_LEAFLET);
        });
    }

    function updateCarNote() {
        if (!carNote) return;
        var low = carOn && map.getZoom() < carMinZoom;
        carNote.textContent = low ? 'Aproxime o mapa para ver os imóveis.'
            : carOn ? 'Clique num imóvel para ver o número do CAR.' : '';
        carNote.hidden = !carNote.textContent;
        carNote.className = 'ex-status' + (low ? ' is-warn' : '');
    }

    function setCar(on) {
        carOn = on;
        save(CAR_STORE, on);
        if (carToggle) carToggle.checked = on;
        if (carLegend) carLegend.hidden = !on;
        if (!on) {
            if (carLayer && map.hasLayer(carLayer)) map.removeLayer(carLayer);
            updateCarNote();
            return;
        }
        if (carLayer) {
            carLayer.addTo(map);
            updateCarNote();
            return;
        }
        carNote.hidden = false;
        carNote.className = 'ex-status is-loading';
        carNote.textContent = 'Carregando os imóveis do CAR…';
        ensureMaplibreLayer().then(function () {
            if (!map.getPane('car')) {
                // Entre as camadas temáticas (350) e os desenhos (400).
                var pane = map.createPane('car');
                pane.style.zIndex = 380;
                pane.style.pointerEvents = 'none';
            }
            carLayer = L.maplibreGL({ pane: 'car', interactive: false, style: carStyle() });
            if (carOn) carLayer.addTo(map);
            updateCarNote();
        }).catch(function () {
            carOn = false;
            if (carToggle) carToggle.checked = false;
            if (carLegend) carLegend.hidden = true;
            carNote.hidden = false;
            carNote.className = 'ex-status is-error';
            carNote.textContent = 'Não foi possível carregar a camada do CAR. Confira a conexão e tente de novo.';
        });
    }

    // Há imóvel desenhado no ponto? Evita consultar o servidor a cada clique no vazio.
    function carRenderedAt(latlng) {
        try {
            var gl = carLayer.getMaplibreMap();
            var p = gl.project([latlng.lng, latlng.lat]);
            return gl.queryRenderedFeatures([p.x, p.y], { layers: ['car-fill'] }).length > 0;
        } catch (e) {
            return true;
        }
    }

    function carPopup(latlng, info) {
        var box = el('div', 'ex-popup');
        el('span', 'ex-popup-kicker', box, 'Imóvel do CAR');
        el('strong', 'ex-popup-title ex-popup-car', box, info.car);
        var city = locator.cityOfCar(info.car);
        var meta = [STATUS_LABEL[String(info.status || '').toUpperCase()], info.area_ha ? fmt(info.area_ha, 2) + ' ha' : '',
            city && city.nome].filter(Boolean).join(' · ');
        if (meta) el('div', 'ex-popup-meta', box, meta);
        if (info.cars > 1) el('div', 'ex-popup-meta', box, 'O ponto cai em ' + info.cars + ' imóveis sobrepostos; este é o maior.');
        var actions = el('div', 'ex-popup-actions', box);
        popupButton(actions, 'Analisar este imóvel', 'is-primary', function () { analyzeCar(info.car); });
        popupButton(actions, 'Copiar número', '', function () {
            if (global.navigator.clipboard) global.navigator.clipboard.writeText(info.car).catch(function () {});
        });
        L.popup({ maxWidth: 360 }).setLatLng(latlng).setContent(box).openOn(map);
    }

    var carSeq = 0;
    function identifyCar(latlng) {
        if (!cfg.propertyUrl || !carRenderedAt(latlng)) return;
        var seq = ++carSeq;
        fetch(cfg.propertyUrl + '?lon=' + latlng.lng + '&lat=' + latlng.lat, { credentials: 'same-origin' })
            .then(function (r) { return r.ok ? r.json() : null; })
            .then(function (info) {
                if (seq !== carSeq || !info || !info.geometry || !info.car) return;
                showHighlight([{ type: 'Feature', geometry: info.geometry }], {
                    fit: false, label: 'CAR ' + info.car, area: info.area_ha ? fmt(info.area_ha, 2) + ' ha' : ''
                });
                carPopup(latlng, info);
            })
            .catch(function () { /* sem rede: o clique só não mostra o cartão */ });
    }

    map.on('click', function (e) {
        if (!carOn || !carLayer || busy() || map.getZoom() < carMinZoom) return;
        identifyCar(e.latlng);
    });
    map.on('zoomend', updateCarNote);

    // ----- Montagem da aba -----

    (function buildPlaces() {
        var section = panel.section('lugares');
        if (!section) return;

        var head = el('div', 'map-panel-heading-row', section);
        var title = el('div', 'map-panel-heading ex-heading', head, 'Meus desenhos');
        countEl = el('span', 'ex-count', title);
        var headActions = el('div', 'ex-head-actions', head);

        var fileInput = el('input', '', section);
        fileInput.type = 'file';
        fileInput.accept = '.zip,.kml,.kmz,.geojson,.json';
        fileInput.hidden = true;
        fileInput.addEventListener('change', function () {
            importFile(fileInput.files && fileInput.files[0]);
            fileInput.value = '';
        });
        if (imagery.download_area_url) {
            var importBtn = el('button', 'map-panel-link', headActions, 'Importar');
            importBtn.type = 'button';
            importBtn.title = 'Abrir os polígonos de um shapefile (ZIP), KML, KMZ ou GeoJSON';
            importBtn.addEventListener('click', function () { fileInput.click(); });
        }
        var kmlBtn = el('button', 'map-panel-link', headActions, 'Baixar KML');
        kmlBtn.type = 'button';
        kmlBtn.title = 'Baixar todos os desenhos num arquivo KML (abre no Google Earth)';
        kmlBtn.addEventListener('click', downloadKml);

        emptyEl = el('p', 'map-panel-hint', section, hasPm
            ? 'Use Polígono, Linha ou Ponto, no canto do mapa, para desenhar. Os desenhos ficam guardados neste navegador e podem ser analisados, se você quiser.'
            : 'As ferramentas de desenho não carregaram (confira a conexão). Ainda dá para importar um arquivo.');
        statusEl = el('p', 'ex-status', section);
        statusEl.hidden = true;
        statusEl.setAttribute('role', 'status');
        listEl = el('div', 'ex-items', section);

        if (sicar && cfg.tilesUrl) {
            el('div', 'map-panel-subheading', section, 'Camadas opcionais');
            var row = el('label', 'ex-switch', section);
            carToggle = el('input', '', row);
            carToggle.type = 'checkbox';
            el('span', '', row, 'Imóveis do CAR (SICAR)');
            carToggle.addEventListener('change', function () { setCar(carToggle.checked); });
            carLegend = el('div', 'ex-car-legend', section);
            carLegend.hidden = true;
            CAR_STATUS.forEach(function (s) {
                var chip = el('span', 'ex-car-chip', carLegend, s.label);
                chip.style.setProperty('--c', s.color);
            });
            carNote = el('p', 'ex-status', section);
            carNote.hidden = true;
        }
    })();

    // Desenhos guardados de outra visita.
    (function restore() {
        var stored = load(DRAW_STORE);
        ((stored && stored.features) || []).forEach(function (f) {
            try { addItem(f.geometry, f.properties, true); } catch (e) { /* desenho inválido: fica de fora */ }
        });
        renderList();
    })();

    if (carToggle && load(CAR_STORE) === true) setCar(true);

    // =====================================================================
    // Visão 3D (seletor 2D | 2D + 3D | 3D do topo)
    // =====================================================================

    if (global.install3dView) {
        global.install3dView({
            imagery: imagery,
            viewSwitch: doc.getElementById('map_view_switch'),
            stage: doc.getElementById('map_stage'),
            side: doc.getElementById('map_3d_side'),
            free: true,
            viewKey: 'terraview:explorar:visualizacao',
            defaultView: '2d'
        });
    }

    // =====================================================================
    // Análise de propriedade (opcional)
    // =====================================================================

    var drawerEl = doc.getElementById('ex_drawer');
    var drawerBtn = doc.getElementById('ex_analyze_open');
    var loaderEl = doc.getElementById('page-loader');
    var hud = doc.getElementById('search_hud');
    var hudStatus = doc.getElementById('search_hud_status');
    var hudCount = doc.getElementById('search_hud_count');
    var hudBar = doc.getElementById('search_hud_bar');
    var hudList = doc.getElementById('search_hud_list');
    var cancelBtn = doc.getElementById('search_cancel');
    var hitsGroup = L.layerGroup().addTo(map);
    var searching = false;
    var search = null;
    var previewKey = null;

    function setDrawer(open) {
        if (!drawerEl) return;
        drawerEl.hidden = !open;
        if (drawerBtn) {
            drawerBtn.setAttribute('aria-expanded', String(open));
            drawerBtn.classList.toggle('is-active', open);
        }
    }

    if (drawerBtn) drawerBtn.addEventListener('click', function () { setDrawer(drawerEl.hidden); });
    var drawerClose = doc.getElementById('ex_drawer_close');
    if (drawerClose) drawerClose.addEventListener('click', function () { setDrawer(false); });
    // A análise voltou com um aviso (ex.: CAR não encontrado): a gaveta já abre.
    if (drawerEl && drawerEl.querySelector('.status-error:not(#client_error), .status-success')) setDrawer(true);

    function submitAnalysis() {
        var form = doc.getElementById('upload_form');
        if (!form) return;
        map.closePopup();
        stopDraw();
        stopEdit();
        // Campo inválido numa gaveta fechada bloquearia o envio sem aviso.
        if (!form.requestSubmit || !form.checkValidity()) {
            setDrawer(true);
            if (form.reportValidity) form.reportValidity();
            return;
        }
        form.requestSubmit();
    }

    function chooseMode(id) {
        var radio = doc.getElementById(id);
        if (!radio) return false;
        radio.checked = true;
        radio.dispatchEvent(new Event('change', { bubbles: true }));
        return true;
    }

    /** Polígono desenhado → KML → o mesmo caminho do envio de KML do formulário. */
    function analyzeItem(item) {
        var kmlInput = doc.getElementById('kml_file');
        if (!kmlInput || !global.DataTransfer || !global.File || !chooseMode('mode_kml')) {
            setDrawer(true);
            return;
        }
        var file = new File([kmlDocument([item], item.name)], slug(item.name) + '.kml',
            { type: 'application/vnd.google-earth.kml+xml' });
        var transfer = new DataTransfer();
        transfer.items.add(file);
        kmlInput.files = transfer.files;
        kmlInput.dispatchEvent(new Event('change', { bubbles: true }));
        submitAnalysis();
    }

    function analyzeCar(car) {
        var carInput = doc.getElementById('car_input');
        if (!carInput || !chooseMode('mode_car')) {
            setDrawer(true);
            return;
        }
        carInput.value = car;
        submitAnalysis();
    }

    // ----- Pré-visualização do formulário (upload.js chama) -----

    function targetLabel(req, target) {
        if (req.mode === 'car' && req.car) return 'CAR ' + req.car;
        if (target.car) return 'CAR ' + target.car;
        if (req.file && req.file.name) return req.file.name;
        return 'Área informada';
    }

    function previewPropertyOnMap(req) {
        var key = locator.keyFor(req);
        if (!key) return Promise.resolve(null);
        previewKey = key;
        return locator.locate(req).then(function (target) {
            if (!searching && previewKey === key && target && target.status === 'found') {
                showHighlight(target.features, {
                    label: targetLabel(req, target),
                    area: target.area_ha ? fmt(target.area_ha, 2) + ' ha' : ''
                });
            }
            return target && Object.assign({}, target, { city: target.city && { nome: target.city.nome } });
        });
    }

    function clearPropertyPreview() {
        previewKey = null;
        if (!searching) clearHighlight();
    }

    // ----- Andamento da análise (analysis_progress.py) -----

    var LEVEL_COLOR = { alerta: '#c62828', atencao: '#b7791f', info: '#2b5a38' };

    function renderHud(state) {
        var bases = state.bases || [];
        var total = state.total || bases.length;
        if (total) {
            hudCount.textContent = fmt(state.done || 0) + ' de ' + fmt(total) + ' bases';
            hud.classList.remove('is-indeterminate');
            hudBar.style.width = ((state.finished ? 1 : (state.done || 0) / total) * 100).toFixed(1) + '%';
        }
        hudStatus.textContent = state.finished ? 'Pronto! Abrindo o resultado...'
            : state.current ? 'Consultando: ' + state.current
            : state.stage || hudStatus.textContent;

        hudList.textContent = '';
        var running = null;
        bases.forEach(function (b) {
            var li = el('li', 'ex-hud-item is-' + b.status, hudList);
            el('span', 'ex-hud-icon', li).setAttribute('aria-hidden', 'true');
            var name = el('span', 'ex-hud-name', li, b.nome);
            name.title = b.nome;
            var result = el('span', 'ex-hud-result', li);
            if (b.status === 'done') {
                if (b.count) {
                    result.textContent = fmt(b.count) + ' · ' + fmt(b.area_ha, 1) + ' ha';
                    li.classList.add('has-hits');
                    li.style.setProperty('--hit', LEVEL_COLOR[b.nivel] || LEVEL_COLOR.info);
                } else {
                    result.textContent = 'nada';
                }
            }
            if (b.status === 'running') running = li;
        });
        if (running) hudList.scrollTop = running.offsetTop - hudList.clientHeight / 2;
    }

    function offerTarget(s, target, label) {
        if (search !== s || s.target || !target || target.status !== 'found') return;
        s.target = target;
        showHighlight(target.features, { label: label || targetLabel(s.req, target) });
    }

    function drawHits(features) {
        hitsGroup.clearLayers();
        features.forEach(function (f) {
            if (!f.geometry) return;
            L.geoJSON(f.geometry, {
                interactive: false,
                style: { color: f.color || '#ff6b5a', weight: 1.6, fillColor: f.color || '#ff6b5a', fillOpacity: 0.42 }
            }).addTo(hitsGroup);
        });
    }

    function applyProgress(s, state) {
        renderHud(state);
        // PDF: o CAR só aparece depois que o servidor lê o documento.
        if (state.car && !s.carAsked && s.req.mode !== 'car') {
            s.carAsked = true;
            locator.locate({ mode: 'car', car: state.car }).then(function (t) {
                s.carLookupDone = true;
                offerTarget(s, t, 'CAR ' + state.car);
            });
        }
        // Perímetro do servidor: quando o navegador não conseguiu ler sozinho.
        if (state.target && !s.target && s.clientDone && (!s.carAsked || s.carLookupDone)) {
            offerTarget(s, locator.targetFrom([{ type: 'Feature', properties: {}, geometry: state.target }]));
        }
        var hits = state.features || [];
        if (hits.length !== s.hits) {
            s.hits = hits.length;
            drawHits(hits);
        }
    }

    function startPolling(s) {
        if (!s.req.jobId || !cfg.progressUrl) return;
        var url = cfg.progressUrl.replace('{job}', s.req.jobId);
        function poll() {
            if (search !== s) return;
            fetch(url, { credentials: 'same-origin', cache: 'no-store' })
                .then(function (r) { return r.ok ? r.json() : null; })
                .then(function (state) { if (search === s && state) applyProgress(s, state); })
                .catch(function () { /* a próxima consulta tenta de novo */ })
                .then(function () { if (search === s) setTimeout(poll, 1000); });
        }
        setTimeout(poll, 500);
    }

    /** Chamado por upload.js no envio do formulário, antes de o loader aparecer. */
    function searchPropertyOnMap(req) {
        searching = true;
        var s = search = { req: req, target: null, hits: 0 };
        if (doc.fullscreenElement && doc.exitFullscreen) doc.exitFullscreen().catch(function () {});
        setDrawer(false);
        doc.body.classList.add('is-searching');
        if (loaderEl) loaderEl.classList.add('on-map');
        hud.hidden = false;
        hud.classList.add('is-indeterminate');
        hudBar.style.width = '';
        hudCount.textContent = '';
        hudList.textContent = '';
        hudStatus.textContent = req.mode === 'car' ? 'Iniciando a análise...' : 'Enviando o arquivo...';
        cancelBtn.disabled = false;
        startPolling(s);
        locator.locate(req).then(function (target) {
            s.clientDone = true;
            offerTarget(s, target);
        });
        return true;
    }

    function endSearch(reopen) {
        if (!searching) return;
        searching = false;
        search = null;
        doc.body.classList.remove('is-searching');
        if (loaderEl) loaderEl.classList.remove('on-map', 'visible');
        hud.hidden = true;
        hitsGroup.clearLayers();
        if (reopen) setDrawer(true);
    }

    if (cancelBtn) {
        cancelBtn.addEventListener('click', function () {
            if (!search) return;
            var jobId = search.req.jobId;
            cancelBtn.disabled = true;
            // Desiste da resposta do formulário (a página não troca mais)...
            try { global.stop(); } catch (e) { /* navegador sem suporte */ }
            // ...e avisa o servidor, que para antes da próxima base.
            if (jobId && cfg.cancelUrl) {
                fetch(cfg.cancelUrl.replace('{job}', jobId), {
                    method: 'POST', credentials: 'same-origin', headers: { 'X-CSRFToken': csrfToken() }
                }).catch(function () { /* a análise só termina sozinha */ });
            }
            endSearch(true);
        });
    }

    // Voltar do resultado (bfcache) devolve a página como estava: encerra a busca.
    global.addEventListener('pageshow', function (e) { if (e.persisted) endSearch(false); });

    global.searchPropertyOnMap = searchPropertyOnMap;
    global.previewPropertyOnMap = previewPropertyOnMap;
    global.clearPropertyPreview = clearPropertyPreview;

    // =====================================================================
    // Busca "Ir para"
    // =====================================================================

    var searchForm = doc.getElementById('ex_search');
    var searchInput = doc.getElementById('ex_search_input');
    var searchMsg = doc.getElementById('ex_search_msg');
    var searchTimer = null;

    function say(text, kind) {
        if (!searchMsg) return;
        clearTimeout(searchTimer);
        searchMsg.hidden = !text;
        searchMsg.textContent = text || '';
        searchMsg.className = 'ex-search-msg' + (kind ? ' is-' + kind : '');
        if (text && kind !== 'loading') searchTimer = setTimeout(function () { say(''); }, 7000);
    }

    function findCity(text) {
        var q = norm(text);
        if (!q) return null;
        var names = cities.map(function (c) { return norm(c.nome); });
        var i = names.indexOf(q);
        if (i < 0) i = names.findIndex(function (n) { return n.indexOf(q) === 0; });
        if (i < 0 && q.length >= 3) i = names.findIndex(function (n) { return n.indexOf(q) >= 0; });
        return i >= 0 ? cities[i] : null;
    }

    function goToCar(car) {
        say('Procurando o imóvel…', 'loading');
        locator.locate({ mode: 'car', car: car }).then(function (target) {
            if (!target) { say('Não foi possível consultar o CAR agora. Tente de novo.', 'warn'); return; }
            if (target.status !== 'found') { say('Este CAR não está na base do SICAR do Tocantins.', 'warn'); return; }
            say('');
            var layer = showHighlight(target.features, {
                label: 'CAR ' + car, area: target.area_ha ? fmt(target.area_ha, 2) + ' ha' : ''
            });
            carPopup(layer.getBounds().getCenter(), { car: car, area_ha: target.area_ha,
                status: Object.keys(STATUS_LABEL).filter(function (k) { return STATUS_LABEL[k] === target.statusLabel; })[0] });
        });
    }

    function goToPoint(lon, lat) {
        say('');
        var latlng = L.latLng(lat, lon);
        showHighlight([{ type: 'Feature', geometry: { type: 'Point', coordinates: [lon, lat] } }], {
            fit: false, label: fmtLatLng(lat, lon)
        });
        map.setView(latlng, Math.max(map.getZoom(), 16));
        var box = el('div', 'ex-popup');
        el('span', 'ex-popup-kicker', box, 'Coordenada');
        el('strong', 'ex-popup-title', box, fmtLatLng(lat, lon));
        var actions = el('div', 'ex-popup-actions', box);
        popupButton(actions, 'Guardar nos meus desenhos', 'is-primary', function () {
            map.closePopup();
            clearHighlight();
            var item = addItem({ type: 'Point', coordinates: [lon, lat] });
            if (item) { panel.open('lugares'); flashRow(item); }
        });
        L.popup({ maxWidth: 320, offset: [0, -6] }).setLatLng(latlng).setContent(box).openOn(map);
    }

    function runSearch(text) {
        text = (text || '').trim();
        if (!text) return;
        var car = text.replace(/[\s​-‍﻿.]/g, '').replace(/[‐-―−]/g, '-').toUpperCase();
        if (CAR_REGEX.test(car)) { goToCar(car); return; }
        if (/\d/.test(text)) {
            var parsed = locator.parseCoordinates(text);
            if (parsed.point) { goToPoint(parsed.point[0], parsed.point[1]); return; }
        }
        var city = findCity(text);
        if (city) {
            say('');
            map.setView([city.lat, city.lon], 12);
            return;
        }
        say('Não achei. Digite um município do Tocantins, uma coordenada (ex.: -10.18, -48.33) ou um número do CAR.', 'warn');
    }

    if (searchForm) {
        var datalist = doc.getElementById('ex_cities');
        cities.slice().sort(function (a, b) { return a.nome.localeCompare(b.nome, 'pt-BR'); }).forEach(function (c) {
            el('option', '', datalist).value = c.nome;
        });
        searchForm.addEventListener('submit', function (e) {
            e.preventDefault();
            runSearch(searchInput.value);
        });
        // Escolher um município da lista já leva até ele.
        searchInput.addEventListener('change', function () {
            if (cities.some(function (c) { return c.nome === searchInput.value; })) runSearch(searchInput.value);
        });
    }

    // Menu do topo: fecha ao clicar fora ou com Esc.
    var menu = doc.getElementById('ex_menu');
    if (menu) {
        doc.addEventListener('click', function (e) { if (menu.open && !menu.contains(e.target)) menu.open = false; });
        doc.addEventListener('keydown', function (e) { if (e.key === 'Escape') menu.open = false; });
    }
})(window);
