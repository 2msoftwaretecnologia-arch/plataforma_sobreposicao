(function () {
    'use strict';

    var cfg = JSON.parse(document.getElementById('bases-3d-config').textContent);
    var bases = cfg.bases;

    // Tocantins (contorno IBGE) com uma folga para o mapa não "bater" na borda.
    var TO_BOUNDS = [[-50.75, -13.50], [-45.65, -5.15]];
    var MAX_BOUNDS = [[-53.5, -15.5], [-43.0, -3.0]];

    // O Tocantins é majoritariamente plano: sem um exagero forte o relevo
    // quase não aparece.
    var terrainExaggeration = 2.5;
    function terrainSpec() {
        return { source: 'terrain', exaggeration: terrainExaggeration };
    }

    var FLY_MS = 6000;     // voo da visão geral
    var TOUR_PITCH = 60;

    var SICAR = 'SicarRecord';
    var STATUS_LABEL = { AT: 'Ativo', PE: 'Pendente', SU: 'Suspenso', CA: 'Cancelado' };
    var SICAR_STATUS = ['upcase', ['coalesce', ['get', 'p1'], '']];
    var SICAR_COLOR = [
        'match', SICAR_STATUS,
        // Cores vivas: o contorno pontilhado é fino e fica sobre o satélite.
        'AT', '#5fe08a',
        'PE', '#ffd23f',
        'SU', '#ff6b3d',
        'CA', '#d9d3c7',
        '#9fd8ff'
    ];

    function fmt(n, digits) {
        return Number(n).toLocaleString('pt-BR', { maximumFractionDigits: digits || 0 });
    }

    // =====================================================================
    // Estilo: satélite + relevo + uma fonte/camadas por base
    // =====================================================================

    function baseColor(b) {
        return b.modelo === SICAR ? SICAR_COLOR : b.cor;
    }

    var HOVER = ['boolean', ['feature-state', 'hover'], false];
    // Imóvel em que o tour está parado no momento.
    var CURRENT = ['boolean', ['feature-state', 'current'], false];

    function hoverColor(b) {
        return ['case', HOVER, '#f3e3bc', baseColor(b)];
    }

    // Camadas de cada base, na ordem em que são desenhadas.
    function layersFor(b) {
        var common = { source: 'b-' + b.modelo, 'source-layer': 'layer' };
        var id = 'b-' + b.modelo;
        if (b.kind === 'line') {
            return [Object.assign({ id: id + '-ln', type: 'line', paint: {
                'line-color': hoverColor(b), 'line-width': 2.5, 'line-opacity': 0.9
            } }, common)];
        }
        if (b.kind === 'point') {
            return [Object.assign({ id: id + '-pt', type: 'circle', paint: {
                'circle-color': hoverColor(b), 'circle-radius': 5, 'circle-opacity': 0.9,
                'circle-stroke-color': '#fbf8f0', 'circle-stroke-width': 1
            } }, common)];
        }
        if (b.modelo === SICAR) {
            // SICAR: só o contorno pontilhado, colorido pela situação do CAR.
            // A camada `-hit` é invisível e existe só para o clique/hover
            // funcionarem também no interior do imóvel.
            return [
                Object.assign({ id: id + '-hit', type: 'fill', paint: {
                    'fill-color': SICAR_COLOR,
                    'fill-opacity': ['case', CURRENT, 0.22, 0]
                } }, common),
                Object.assign({ id: id + '-ln', type: 'line', paint: {
                    'line-color': ['case', CURRENT, '#ffffff', hoverColor(b)],
                    'line-width': ['case', CURRENT, 4, HOVER, 3.2, 1.6],
                    'line-dasharray': [2, 1.5]
                } }, common)
            ];
        }
        return [
            Object.assign({ id: id + '-fill', type: 'fill', paint: {
                'fill-color': b.cor,
                'fill-opacity': ['case', HOVER, 0.55, 0.3]
            } }, common),
            Object.assign({ id: id + '-ol', type: 'line', paint: {
                'line-color': hoverColor(b), 'line-width': 1.2
            } }, common)
        ];
    }

    var sources = {
        satellite: {
            type: 'raster',
            tiles: ['https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'],
            tileSize: 256,
            maxzoom: 18,
            attribution: 'Imagens &copy; Esri'
        },
        terrain: {
            type: 'raster-dem',
            tiles: ['https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png'],
            tileSize: 256,
            maxzoom: 14,
            encoding: 'terrarium',
            attribution: 'Relevo &copy; Mapzen/AWS Terrain Tiles'
        },
        // Fonte separada para o sombreamento: o MapLibre recomenda não
        // reaproveitar a mesma fonte raster-dem do terreno.
        hillshade: {
            type: 'raster-dem',
            tiles: ['https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png'],
            tileSize: 256,
            maxzoom: 14,
            encoding: 'terrarium'
        }
    };
    var layers = [
        { id: 'satellite', type: 'raster', source: 'satellite' },
        { id: 'hillshade', type: 'hillshade', source: 'hillshade', paint: {
            'hillshade-exaggeration': 0.6,
            'hillshade-shadow-color': '#12271a',
            'hillshade-highlight-color': '#fbf8f0',
            'hillshade-accent-color': '#3a2f1c',
            'hillshade-illumination-direction': 315
        } }
    ];

    bases.forEach(function (b) {
        sources['b-' + b.modelo] = {
            type: 'vector',
            tiles: [cfg.tilesUrl.replace('{base}', b.modelo)],
            minzoom: b.min_zoom,
            maxzoom: 14,
            // Só pede tiles dentro do Tocantins.
            bounds: [TO_BOUNDS[0][0], TO_BOUNDS[0][1], TO_BOUNDS[1][0], TO_BOUNDS[1][1]]
        };
        b.layerIds = layersFor(b).map(function (l) { layers.push(l); return l.id; });
    });

    var map = new maplibregl.Map({
        container: 'map',
        bounds: TO_BOUNDS,
        fitBoundsOptions: { padding: 40 },
        maxBounds: MAX_BOUNDS,
        pitch: 55,
        maxPitch: 80,
        style: {
            version: 8,
            sources: sources,
            layers: layers,
            terrain: terrainSpec(),
            sky: {
                'sky-color': '#9cc3d5',
                'horizon-color': '#f3e3bc',
                'fog-color': '#dcead8',
                'sky-horizon-blend': 0.6,
                'horizon-fog-blend': 0.6,
                'fog-ground-blend': 0.2
            }
        }
    });

    map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), 'top-right');
    map.addControl(new maplibregl.FullscreenControl(), 'top-right');
    map.addControl(new maplibregl.ScaleControl({ unit: 'metric' }), 'bottom-right');

    // =====================================================================
    // Máscara: escurece tudo que está fora do Tocantins
    // =====================================================================

    map.on('load', function () {
        fetch(window.TOCANTINS_GEOJSON_URL)
            .then(function (r) { return r.json(); })
            .then(function (geo) {
                var geom = geo.features[0].geometry;
                var outer = geom.type === 'Polygon' ? [geom.coordinates[0]]
                    : geom.coordinates.map(function (poly) { return poly[0]; });
                var world = [[-180, -85], [180, -85], [180, 85], [-180, 85], [-180, -85]];
                var firstBase = bases.length ? bases[0].layerIds[0] : undefined;

                map.addSource('mask', { type: 'geojson', data: {
                    type: 'Feature', properties: {},
                    geometry: { type: 'Polygon', coordinates: [world].concat(outer) }
                } });
                map.addSource('tocantins', { type: 'geojson', data: geo });
                map.addLayer({ id: 'mask', type: 'fill', source: 'mask',
                    paint: { 'fill-color': '#12271a', 'fill-opacity': 0.75 } }, firstBase);
                map.addLayer({ id: 'tocantins-outline', type: 'line', source: 'tocantins',
                    paint: { 'line-color': '#dba63f', 'line-width': 2.2 } }, firstBase);
            });
    });

    // =====================================================================
    // Visibilidade das bases (lista do painel)
    // =====================================================================

    var visible = {};
    var listEl = document.getElementById('base_list');

    function setVisible(b, on) {
        visible[b.modelo] = on;
        b.checkbox.checked = on;
        b.layerIds.forEach(function (id) {
            map.setLayoutProperty(id, 'visibility', on ? 'visible' : 'none');
        });
        updateZoomHint();
    }

    function showOnly(target) {
        bases.forEach(function (b) { setVisible(b, !target || b === target); });
    }

    if (bases.some(function (b) { return b.modelo === SICAR; })) {
        document.getElementById('sicar_legend').hidden = false;
    }

    bases.forEach(function (b, i) {
        visible[b.modelo] = true;
        var li = document.createElement('li');
        li.className = 'base-item';

        var cb = document.createElement('input');
        cb.type = 'checkbox';
        cb.checked = true;
        cb.setAttribute('aria-label', 'Mostrar ' + b.nome);
        cb.addEventListener('change', function () {
            pauseTour();
            setVisible(b, cb.checked);
        });
        b.checkbox = cb;

        var swatch = document.createElement('span');
        swatch.className = 'swatch';
        swatch.style.background = b.modelo === SICAR ? '#5fe08a' : b.cor;

        var btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'base-go';
        btn.title = 'Ver o Tocantins inteiro';
        var name = document.createElement('span');
        name.className = 'base-name';
        name.textContent = b.nome;
        var count = document.createElement('span');
        count.className = 'base-count';
        count.textContent = fmt(b.count);
        btn.appendChild(name);
        btn.appendChild(count);
        btn.addEventListener('click', function () {
            pauseTour();
            goToOverview();
        });

        li.appendChild(cb);
        li.appendChild(swatch);
        li.appendChild(btn);
        listEl.appendChild(li);
        b.itemEl = li;
    });

    if (!bases.length) {
        var empty = document.createElement('li');
        empty.className = 'base-empty';
        empty.textContent = 'Nenhuma base com dados no Tocantins ainda.';
        listEl.appendChild(empty);
    }

    // ----- Aviso de zoom mínimo -----
    var zoomHint = document.getElementById('zoom_hint');
    function updateZoomHint() {
        var z = map.getZoom();
        var needsZoom = bases.some(function (b) { return visible[b.modelo] && z < b.min_zoom; });
        zoomHint.classList.toggle('visible', needsZoom && !playing);
    }
    map.on('zoomend', updateZoomHint);

    // =====================================================================
    // Tour animado: visão geral do estado -> de CAR em CAR, sempre para o
    // imóvel ainda não visitado mais próximo (vizinho mais próximo guloso).
    // =====================================================================

    var playing = false;
    var token = 0;  // invalida callbacks de passos anteriores
    var ready = false;  // estilo carregado: camadas já podem ser alteradas
    var userTookOver = false;  // usuário mexeu no mapa antes do tour começar

    var caption = document.getElementById('caption');
    var captionStep = document.getElementById('caption_step');
    var captionTitle = document.getElementById('caption_title');
    var captionText = document.getElementById('caption_text');
    var captionBar = document.getElementById('caption_bar');
    var playBtn = document.getElementById('tour_play');

    var sicarBase = bases.filter(function (b) { return b.modelo === SICAR; })[0];
    var STATUS_BY_CODE = { 1: 'AT', 2: 'PE', 3: 'SU', 4: 'CA' };
    var START_POINT = [-48.33, -10.18];  // Palmas

    var HOP_MS = 1800;     // salto até o CAR vizinho
    var FAR_HOP_MS = 4000; // quando os vizinhos acabam e ele precisa ir longe
    var DWELL_MS = 1200;   // tempo parado em cada CAR
    var bearing = -20;

    function showOverviewCaption() {
        captionStep.textContent = 'Visão geral';
        captionTitle.textContent = 'Tocantins';
        captionTitle.classList.remove('caption-car');
        captionText.textContent = sicarBase
            ? fmt(sicarBase.count) + ' imóveis do CAR'
            : 'Nenhuma base com dados ainda';
        caption.classList.add('visible');
    }

    function runProgress(ms) {
        captionBar.style.transition = 'none';
        captionBar.style.width = '0%';
        void captionBar.offsetWidth;  // reinicia a transição
        if (ms) {
            captionBar.style.transition = 'width ' + ms + 'ms linear';
            captionBar.style.width = '100%';
        }
    }

    function afterMove(myToken, fn) {
        map.once('moveend', function () { if (myToken === token) fn(); });
    }

    // ----- Pontos dos imóveis + grade espacial para o vizinho mais próximo -----

    var pts = null;
    var GRID = { size: 0.02, minLon: -50.9, minLat: -13.7, cols: 0, rows: 0, cells: null };

    function clampInt(v, max) { return Math.max(0, Math.min(max - 1, Math.floor(v))); }

    function cellOf(lon, lat) {
        return clampInt((lat - GRID.minLat) / GRID.size, GRID.rows) * GRID.cols
            + clampInt((lon - GRID.minLon) / GRID.size, GRID.cols);
    }

    // Formato em `sicar_points_blob` (analysis/services/view_services/bases_3d.py).
    function loadPoints() {
        return fetch(cfg.sicarPointsUrl, { credentials: 'same-origin' })
            .then(function (r) { if (!r.ok) throw new Error(r.status); return r.arrayBuffer(); })
            .then(function (buf) {
                var n = new DataView(buf).getUint32(0, true);
                var off = 4;
                function take(Type, bytes) {
                    var arr = new Type(buf, off, n);
                    off += n * bytes;
                    return arr;
                }
                pts = {
                    n: n,
                    lon: take(Float32Array, 4),
                    lat: take(Float32Array, 4),
                    id: take(Int32Array, 4),
                    area: take(Float32Array, 4),
                    status: take(Uint8Array, 1),
                    visitedCount: 0,
                    order: [],   // índices na ordem em que foram visitados
                    pos: -1      // posição atual em `order` (volta com "anterior")
                };
                GRID.cols = Math.ceil((-45.4 - GRID.minLon) / GRID.size);
                GRID.rows = Math.ceil((-4.9 - GRID.minLat) / GRID.size);
                GRID.cells = new Array(GRID.cols * GRID.rows);
                for (var i = 0; i < n; i++) {
                    var c = cellOf(pts.lon[i], pts.lat[i]);
                    (GRID.cells[c] || (GRID.cells[c] = [])).push(i);
                }
            });
    }

    // A grade só guarda os não visitados. Busca em anéis de células crescentes
    // até que nenhum anel mais distante possa ter um ponto mais perto que o
    // melhor já encontrado.
    function nearestUnvisited(lon, lat) {
        if (pts.visitedCount >= pts.n) return -1;
        var k = Math.cos(lat * Math.PI / 180);
        var cx = clampInt((lon - GRID.minLon) / GRID.size, GRID.cols);
        var cy = clampInt((lat - GRID.minLat) / GRID.size, GRID.rows);
        var best = -1, bestD2 = Infinity;
        var maxR = Math.max(GRID.cols, GRID.rows);

        function scan(x, y) {
            if (x < 0 || y < 0 || x >= GRID.cols || y >= GRID.rows) return;
            var cell = GRID.cells[y * GRID.cols + x];
            if (!cell) return;
            for (var j = 0; j < cell.length; j++) {
                var i = cell[j];
                var dx = (pts.lon[i] - lon) * k, dy = pts.lat[i] - lat;
                var d2 = dx * dx + dy * dy;
                if (d2 < bestD2) { bestD2 = d2; best = i; }
            }
        }

        for (var r = 0; r <= maxR; r++) {
            var minDist = (r - 1) * GRID.size * k;
            if (best >= 0 && minDist > 0 && minDist * minDist > bestD2) break;
            if (r === 0) { scan(cx, cy); continue; }
            for (var d = -r; d <= r; d++) {
                scan(cx + d, cy - r);
                scan(cx + d, cy + r);
                if (d > -r && d < r) { scan(cx - r, cy + d); scan(cx + r, cy + d); }
            }
        }
        return best;
    }

    function markVisited(i) {
        pts.visitedCount++;
        var cell = GRID.cells[cellOf(pts.lon[i], pts.lat[i])];
        var at = cell.indexOf(i);
        if (at >= 0) { cell[at] = cell[cell.length - 1]; cell.pop(); }
    }

    // ----- Câmera, destaque e legenda do imóvel atual -----

    // Zoom para o imóvel caber com folga na tela (lado ~ raiz da área).
    function zoomForArea(areaHa, lat) {
        var side = Math.sqrt(Math.max(areaHa, 1) * 10000);
        var canvas = map.getCanvas();
        var px = Math.min(canvas.clientWidth, canvas.clientHeight) || 800;
        var metersPerPixel = (side * 3.5) / px;
        var z = Math.log2(156543.03 * Math.cos(lat * Math.PI / 180) / metersPerPixel);
        return Math.max(sicarBase.min_zoom + 1.5, Math.min(16, z));
    }

    var currentFeature = null;
    function setCurrent(i) {
        if (currentFeature) map.setFeatureState(currentFeature, { current: false });
        currentFeature = i >= 0 ? { source: 'b-' + SICAR, sourceLayer: 'layer', id: pts.id[i] } : null;
        if (currentFeature) map.setFeatureState(currentFeature, { current: true });
    }

    var detailRequest = 0;
    function showCaptionFor(i) {
        var code = STATUS_BY_CODE[pts.status[i]];
        captionStep.textContent = 'CAR ' + fmt(pts.pos + 1) + ' de ' + fmt(pts.n);
        captionTitle.textContent = '…';
        captionTitle.classList.add('caption-car');
        captionText.textContent = (STATUS_LABEL[code] || 'Sem situação') + ' · ' + fmt(pts.area[i], 2) + ' ha';
        caption.classList.add('visible');

        var myRequest = ++detailRequest;
        fetch(cfg.sicarDetailUrl.replace('{id}', pts.id[i]), { credentials: 'same-origin' })
            .then(function (r) { return r.ok ? r.json() : null; })
            .then(function (d) {
                if (myRequest === detailRequest) captionTitle.textContent = d ? d.car_number : '-';
            })
            .catch(function () {
                if (myRequest === detailRequest) captionTitle.textContent = '-';
            });
    }

    function visit(i, myToken, durationMs) {
        setCurrent(i);
        showCaptionFor(i);
        runProgress(0);
        map.flyTo({
            center: [pts.lon[i], pts.lat[i]],
            zoom: zoomForArea(pts.area[i], pts.lat[i]),
            pitch: TOUR_PITCH,
            bearing: bearing,
            duration: durationMs,
            essential: true
        });
        afterMove(myToken, function () {
            if (!playing) return;
            runProgress(DWELL_MS);
            bearing += 6;
            map.easeTo({ bearing: bearing, duration: DWELL_MS, easing: function (t) { return t; }, essential: true });
            afterMove(myToken, function () { if (playing) step(1); });
        });
    }

    // Avança (+1) ou volta (-1) um CAR. Avançar além do histórico escolhe o
    // vizinho não visitado mais próximo do CAR atual.
    function step(dir) {
        if (!ready || !pts || !sicarBase) return;
        var from = pts.pos >= 0 ? pts.order[pts.pos] : -1;
        if (dir < 0) {
            if (pts.pos <= 0) return;
            pts.pos--;
        } else if (pts.pos < pts.order.length - 1) {
            pts.pos++;
        } else {
            var origin = from >= 0 ? [pts.lon[from], pts.lat[from]] : START_POINT;
            var next = nearestUnvisited(origin[0], origin[1]);
            if (next < 0) { pauseTour(); return; }  // todos os CARs visitados
            markVisited(next);
            pts.order.push(next);
            pts.pos = pts.order.length - 1;
        }

        var myToken = ++token;
        map.stop();
        showOnly(sicarBase);
        var i = pts.order[pts.pos];
        var far = from < 0 || Math.abs(pts.lon[i] - pts.lon[from]) + Math.abs(pts.lat[i] - pts.lat[from]) > 0.15;
        visit(i, myToken, far ? FAR_HOP_MS : HOP_MS);
    }

    function goToOverview() {
        if (!ready) return;
        token++;
        map.stop();
        runProgress(0);
        if (pts) setCurrent(-1);
        showOverviewCaption();
        var cam = map.cameraForBounds(TO_BOUNDS, { padding: 40 });
        map.flyTo({ center: cam.center, zoom: cam.zoom, pitch: 55, bearing: 0, duration: FLY_MS * 0.7, essential: true });
    }

    function setPlaying(on) {
        playing = on;
        playBtn.innerHTML = on ? '&#10074;&#10074;' : '&#9654;';
        playBtn.setAttribute('aria-label', on ? 'Pausar tour' : 'Continuar tour');
        caption.classList.toggle('paused', !on);
        updateZoomHint();
    }

    function pauseTour() {
        if (!playing) return;
        setPlaying(false);
        token++;
        map.stop();
        runProgress(0);
    }

    function playTour() {
        if (!ready || !pts) return;
        setPlaying(true);
        // Retoma no CAR atual (ou começa pelo mais próximo de Palmas).
        if (pts.pos >= 0) {
            var myToken = ++token;
            map.stop();
            showOnly(sicarBase);
            visit(pts.order[pts.pos], myToken, FAR_HOP_MS);
        } else {
            step(1);
        }
    }

    playBtn.addEventListener('click', function () { playing ? pauseTour() : playTour(); });
    document.getElementById('tour_next').addEventListener('click', function () { step(1); });
    document.getElementById('tour_prev').addEventListener('click', function () { step(-1); });

    // Qualquer interação direta com o mapa assume o controle da câmera.
    ['mousedown', 'touchstart', 'wheel'].forEach(function (ev) {
        map.on(ev, function () {
            userTookOver = true;
            pauseTour();
        });
    });

    var reduceMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    var pointsReady = sicarBase ? loadPoints().catch(function () { pts = null; }) : Promise.resolve();

    map.on('load', function () {
        ready = true;
        showOverviewCaption();
        setPlaying(false);
        // Mostra a visão geral por alguns segundos e então começa a andar.
        var pause = new Promise(function (resolve) { setTimeout(resolve, 2500); });
        Promise.all([pointsReady, pause]).then(function () {
            if (pts && !reduceMotion && !userTookOver) playTour();
        });
    });

    // =====================================================================
    // Destaque ao passar o mouse e popup
    // =====================================================================

    var clickable = [];
    bases.forEach(function (b) {
        b.layerIds.forEach(function (id) {
            if (!/-ol$/.test(id)) clickable.push({ id: id, base: b });
        });
    });
    var clickableIds = clickable.map(function (c) { return c.id; });
    function baseOfLayer(id) {
        return clickable.filter(function (c) { return c.id === id; })[0].base;
    }

    var hovered = null;
    function clearHover() {
        if (hovered) map.setFeatureState(hovered, { hover: false });
        hovered = null;
    }

    map.on('mousemove', function (e) {
        var f = map.queryRenderedFeatures(e.point, { layers: clickableIds })[0];
        map.getCanvas().style.cursor = f ? 'pointer' : '';
        if (!f) return clearHover();
        var key = { source: f.source, sourceLayer: 'layer', id: f.id };
        if (hovered && hovered.source === key.source && hovered.id === key.id) return;
        clearHover();
        hovered = key;
        map.setFeatureState(hovered, { hover: true });
    });

    function row(label, value) {
        var div = document.createElement('div');
        var b = document.createElement('strong');
        b.textContent = label + ': ';
        div.appendChild(b);
        div.appendChild(document.createTextNode(value));
        return div;
    }

    map.on('click', function (e) {
        var f = map.queryRenderedFeatures(e.point, { layers: clickableIds })[0];
        if (!f) return;
        var b = baseOfLayer(f.layer.id);
        var p = f.properties;

        var content = document.createElement('div');
        content.className = 'base-popup';
        var title = document.createElement('div');
        title.className = 'base-popup-title';
        title.textContent = b.nome;
        content.appendChild(title);

        b.props.forEach(function (prop) {
            var value = p[prop.key];
            if (b.modelo === SICAR && prop.key === 'p1') {
                value = STATUS_LABEL[String(value || '').toUpperCase()] || value;
            }
            content.appendChild(row(prop.label, value || '-'));
        });
        if (Number(p.area_ha) > 0) content.appendChild(row('Área', fmt(p.area_ha, 2) + ' ha'));

        new maplibregl.Popup({ maxWidth: '360px' }).setLngLat(e.lngLat).setDOMContent(content).addTo(map);
    });

    // =====================================================================
    // Controles do painel
    // =====================================================================

    var terrainToggle = document.getElementById('toggle_terrain');
    var reliefInput = document.getElementById('relief_exaggeration');
    var reliefValue = document.getElementById('relief_value');
    reliefInput.addEventListener('input', function () {
        terrainExaggeration = Number(reliefInput.value);
        reliefValue.textContent = fmt(terrainExaggeration, 1) + '×';
        if (terrainToggle.checked) map.setTerrain(terrainSpec());
    });
    terrainToggle.addEventListener('change', function () {
        var on = terrainToggle.checked;
        map.setTerrain(on ? terrainSpec() : null);
        map.setLayoutProperty('hillshade', 'visibility', on ? 'visible' : 'none');
        reliefInput.disabled = !on;
    });
})();
