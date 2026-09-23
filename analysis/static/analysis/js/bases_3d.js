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

    var FLY_MS = 6000;     // voo até a próxima base
    var DWELL_MS = 8000;   // tempo girando em volta de cada base
    var TOUR_ZOOM = 11.5;
    var TOUR_PITCH = 62;

    var SICAR = 'SicarRecord';
    var STATUS_LABEL = { AT: 'Ativo', PE: 'Pendente', SU: 'Suspenso', CA: 'Cancelado' };
    var SICAR_COLOR = [
        'match', ['upcase', ['coalesce', ['get', 'p1'], '']],
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
                    'fill-color': '#000', 'fill-opacity': 0
                } }, common),
                Object.assign({ id: id + '-ln', type: 'line', paint: {
                    'line-color': hoverColor(b),
                    'line-width': ['case', HOVER, 3.2, 1.6],
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
        btn.title = 'Ir até esta base';
        var name = document.createElement('span');
        name.className = 'base-name';
        name.textContent = b.nome;
        var count = document.createElement('span');
        count.className = 'base-count';
        count.textContent = fmt(b.count);
        btn.appendChild(name);
        btn.appendChild(count);
        btn.addEventListener('click', function () {
            var idx = steps.indexOf(b);
            if (idx >= 0) goTo(idx);
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
    // Tour animado: visão geral do estado -> voo até cada base -> giro
    // =====================================================================

    var OVERVIEW = { overview: true };
    var steps = [OVERVIEW].concat(bases.filter(function (b) { return b.focus; }));
    var current = 0;
    var playing = false;
    var token = 0;  // invalida callbacks de passos anteriores
    var ready = false;  // estilo carregado: camadas já podem ser alteradas

    var caption = document.getElementById('caption');
    var captionStep = document.getElementById('caption_step');
    var captionTitle = document.getElementById('caption_title');
    var captionText = document.getElementById('caption_text');
    var captionBar = document.getElementById('caption_bar');
    var playBtn = document.getElementById('tour_play');

    var totalFeatures = bases.reduce(function (acc, b) { return acc + b.count; }, 0);

    function setCaption(step, index) {
        if (step.overview) {
            captionStep.textContent = 'Visão geral';
            captionTitle.textContent = 'Tocantins';
            captionText.textContent = bases.length
                ? bases.length + (bases.length === 1 ? ' base' : ' bases') + ' com dados · ' + fmt(totalFeatures) + ' feições'
                : 'Nenhuma base com dados ainda';
        } else {
            captionStep.textContent = 'Base ' + index + ' de ' + (steps.length - 1);
            captionTitle.textContent = step.nome;
            captionText.textContent = fmt(step.count) + ' feições no Tocantins';
        }
        caption.classList.add('visible');
        bases.forEach(function (b) { b.itemEl.classList.toggle('active', b === step); });
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

    function goTo(index) {
        if (!ready) return;
        var myToken = ++token;
        current = (index + steps.length) % steps.length;
        var step = steps[current];
        map.stop();
        runProgress(0);
        setCaption(step, current);
        showOnly(step.overview ? null : step);

        var bearing = step.overview ? 0 : ((current * 67) % 120) - 60;
        if (step.overview) {
            var cam = map.cameraForBounds(TO_BOUNDS, { padding: 40 });
            map.flyTo({ center: cam.center, zoom: cam.zoom, pitch: 55, bearing: 0, duration: FLY_MS * 0.7, essential: true });
        } else {
            map.flyTo({ center: step.focus, zoom: TOUR_ZOOM, pitch: TOUR_PITCH, bearing: bearing, duration: FLY_MS, essential: true });
        }

        afterMove(myToken, function () {
            if (!playing || steps.length < 2) return;
            runProgress(DWELL_MS);
            map.easeTo({ bearing: bearing + 45, duration: DWELL_MS, easing: function (t) { return t; }, essential: true });
            afterMove(myToken, function () { if (playing) goTo(current + 1); });
        });
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
        setPlaying(true);
        goTo(current);
    }

    playBtn.addEventListener('click', function () { playing ? pauseTour() : playTour(); });
    document.getElementById('tour_next').addEventListener('click', function () { goTo(current + 1); });
    document.getElementById('tour_prev').addEventListener('click', function () { goTo(current - 1); });

    // Qualquer interação direta com o mapa assume o controle da câmera.
    ['mousedown', 'touchstart', 'wheel'].forEach(function (ev) {
        map.on(ev, pauseTour);
    });

    var reduceMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    map.on('load', function () {
        ready = true;
        if (reduceMotion || steps.length < 2) {
            setPlaying(false);
            setCaption(OVERVIEW, 0);
        } else {
            setTimeout(playTour, 800);
        }
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
