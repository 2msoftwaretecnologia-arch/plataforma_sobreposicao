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
        // O terreno usa um DEM mais grosso (nível 11, ~75 m/pixel): com níveis
        // mais finos a malha do relevo era refeita a cada tile que chegava
        // durante o tour e tudo que está sobre ela "pulava".
        terrain: {
            type: 'raster-dem',
            tiles: ['https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png'],
            tileSize: 256,
            maxzoom: 11,
            encoding: 'terrarium',
            attribution: 'Relevo &copy; Mapzen/AWS Terrain Tiles'
        },
        // Fonte separada para o sombreamento: o MapLibre recomenda não
        // reaproveitar a mesma fonte raster-dem do terreno.
        hillshade: {
            type: 'raster-dem',
            tiles: ['https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png'],
            tileSize: 256,
            maxzoom: 11,  // mesmo nível do terreno: sombra estável durante o tour
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
            maxzoom: cfg.maxTileZoom,
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
    // Água em azul: rios, lagos e represas do OpenStreetMap (OpenFreeMap)
    // =====================================================================

    var WATER_TILEJSON = 'https://tiles.openfreemap.org/planet';
    var WATER_LAYERS = ['water-fill', 'waterway-line'];
    var WATER_COLOR = '#2f8fe6';

    map.on('load', function () {
        // O caminho dos tiles muda a cada atualização do OpenFreeMap, por
        // isso vem do TileJSON. Os tiles são declarados aqui (e não via `url`)
        // para limitar ao nível 12, como o SICAR: sem troca de nível no tour.
        fetch(WATER_TILEJSON)
            .then(function (r) { return r.json(); })
            .then(function (tj) {
                map.addSource('water', {
                    type: 'vector',
                    tiles: tj.tiles,
                    minzoom: 0,
                    maxzoom: 12,
                    bounds: [TO_BOUNDS[0][0], TO_BOUNDS[0][1], TO_BOUNDS[1][0], TO_BOUNDS[1][1]],
                    attribution: tj.attribution
                });
                // Abaixo da máscara (se já existir), para a água fora do
                // Tocantins também ficar escurecida.
                var before = map.getLayer('mask') ? 'mask' : (bases.length ? bases[0].layerIds[0] : undefined);
                var visibility = document.getElementById('toggle_water').checked ? 'visible' : 'none';
                map.addLayer({
                    id: 'water-fill', type: 'fill', source: 'water', 'source-layer': 'water',
                    filter: ['!=', ['get', 'brunnel'], 'tunnel'],
                    layout: { visibility: visibility },
                    paint: {
                        'fill-color': WATER_COLOR,
                        'fill-opacity': ['case', ['==', ['get', 'intermittent'], 1], 0.4, 0.72]
                    }
                }, before);
                map.addLayer({
                    id: 'waterway-line', type: 'line', source: 'water', 'source-layer': 'waterway',
                    filter: ['!=', ['get', 'brunnel'], 'tunnel'],
                    layout: { visibility: visibility, 'line-cap': 'round', 'line-join': 'round' },
                    paint: {
                        'line-color': WATER_COLOR,
                        'line-opacity': ['case', ['==', ['get', 'intermittent'], 1], 0.5, 0.9],
                        // Rios mais grossos que córregos, engrossando com o zoom.
                        'line-width': ['interpolate', ['linear'], ['zoom'],
                            7, ['match', ['get', 'class'], 'river', 1.2, 0.3],
                            12, ['match', ['get', 'class'], 'river', 3, 1],
                            16, ['match', ['get', 'class'], 'river', 7, 2.5]
                        ]
                    }
                }, before);
            })
            .catch(function () { /* sem água se o OpenFreeMap estiver fora */ });
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
    // Tour animado: visão geral do estado -> voo contínuo de cidade em cidade
    // (sedes dos 139 municípios), sempre para a mais próxima ainda não
    // visitada. Depois de passar por todas, recomeça o circuito.
    // =====================================================================

    var playing = false;
    var token = 0;  // invalida callbacks/animações anteriores
    var ready = false;  // estilo carregado: camadas já podem ser alteradas
    var userTookOver = false;  // usuário mexeu no mapa antes do tour começar

    var caption = document.getElementById('caption');
    var captionStep = document.getElementById('caption_step');
    var captionTitle = document.getElementById('caption_title');
    var captionText = document.getElementById('caption_text');
    var captionBar = document.getElementById('caption_bar');
    var playBtn = document.getElementById('tour_play');

    var FAR_HOP_MS = 4500;  // voo em arco até uma cidade (início, anterior/próxima)

    var sicarBase = bases.filter(function (b) { return b.modelo === SICAR; })[0];
    var cities = cfg.cities;

    function showOverviewCaption() {
        captionStep.textContent = 'Visão geral';
        captionTitle.textContent = 'Tocantins';
        captionText.textContent = cities.length + ' municípios'
            + (sicarBase ? ' · ' + fmt(sicarBase.count) + ' imóveis do CAR' : '');
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

    function setProgress(fraction) {
        captionBar.style.transition = 'none';
        captionBar.style.width = (fraction * 100).toFixed(1) + '%';
    }

    function afterMove(myToken, fn) {
        map.once('moveend', function () { if (myToken === token) fn(); });
    }

    // ----- Rota: vizinho mais próximo entre as cidades -----

    var route = [];          // índices em `cities`, na ordem do voo
    var pos = -1;            // posição atual em `route`
    var visited = new Uint8Array(cities.length);
    var visitedCount = 0;

    function distMeters(a, b) {
        var k = Math.cos(a[1] * Math.PI / 180);
        var dx = (b[0] - a[0]) * k * 111320, dy = (b[1] - a[1]) * 110540;
        return Math.sqrt(dx * dx + dy * dy);
    }

    // Ponto de parada: o trecho com mais imóveis do CAR do município (calculado
    // no servidor), não a sede — a área urbana quase não tem CAR.
    function cityPoint(i) { return cities[i].focus; }

    function visit(i) {
        visited[i] = 1;
        visitedCount++;
        route.push(i);
    }

    function nearestCity(from) {
        if (visitedCount >= cities.length) {  // circuito completo: recomeça
            visited = new Uint8Array(cities.length);
            visited[from] = 1;
            visitedCount = 1;
        }
        var best = -1, bestD = Infinity, p = cityPoint(from);
        for (var i = 0; i < cities.length; i++) {
            if (visited[i]) continue;
            var d = distMeters(p, cityPoint(i));
            if (d < bestD) { bestD = d; best = i; }
        }
        return best;
    }

    // Garante `n` cidades já escolhidas à frente da posição `k`.
    function ensureAhead(k, n) {
        while (route.length - 1 < k + n) visit(nearestCity(route[route.length - 1]));
    }

    function ensureStarted() {
        if (pos >= 0) return true;
        if (!cities.length) return false;
        var capital = cities.findIndex(function (c) { return c.capital; });
        visit(capital >= 0 ? capital : 0);
        pos = 0;
        return true;
    }

    // ----- Geometria da curva -----

    function point(k) { return cityPoint(route[k]); }

    // Rumo de a para b em graus a partir do norte, no sentido horário (o
    // mesmo referencial do `bearing` do mapa).
    function headingDeg(a, b) {
        var k = Math.cos(a[1] * Math.PI / 180);
        return Math.atan2((b[0] - a[0]) * k, b[1] - a[1]) * 180 / Math.PI;
    }

    function angleDiff(from, to) { return ((to - from + 540) % 360) - 180; }

    // Catmull-Rom centrípeta: curva suave passando por todas as cidades, sem
    // os laços que a versão uniforme faz quando as distâncias variam muito.
    function centripetal(p0, p1, p2, p3, t) {
        function knot(ti, a, b) {
            var dx = b[0] - a[0], dy = b[1] - a[1];
            return ti + Math.max(Math.pow(dx * dx + dy * dy, 0.25), 1e-9);
        }
        var t0 = 0, t1 = knot(t0, p0, p1), t2 = knot(t1, p1, p2), t3 = knot(t2, p2, p3);
        var u = t1 + (t2 - t1) * t;
        function lerp(a, b, ta, tb) {
            var w = (u - ta) / (tb - ta);
            return [a[0] + (b[0] - a[0]) * w, a[1] + (b[1] - a[1]) * w];
        }
        var a1 = lerp(p0, p1, t0, t1), a2 = lerp(p1, p2, t1, t2), a3 = lerp(p2, p3, t2, t3);
        var b1 = lerp(a1, a2, t0, t2), b2 = lerp(a2, a3, t1, t3);
        return lerp(b1, b2, t1, t2);
    }

    // Ponto da curva no trecho k (da cidade k à k+1), t em [0, 1].
    function pathAt(k, t) {
        var p1 = point(k), p2 = point(k + 1);
        var p0 = k > 0 ? point(k - 1) : [2 * p1[0] - p2[0], 2 * p1[1] - p2[1]];
        return centripetal(p0, p1, p2, point(k + 2), t);
    }

    // ----- Voo contínuo -----

    // Alto entre as cidades (dezenas de km) e perto sobre cada uma. Os tiles
    // do SICAR e do relevo param no nível 11, então descer até o 13 só
    // amplia o que já está carregado, sem trocar de nível (sem piscar).
    var TRAVEL_ZOOM = 11.0;
    var CITY_ZOOM = 13.0;
    var GROUND_SPEED = 3500;      // m/s no chão, só na parte de deslocamento
    var MIN_TRAVEL_MS = 7000;
    var MAX_TRAVEL_MS = 20000;
    var LINGER_MS = 7000;         // tempo a mais em cada trecho, gasto rondando as cidades
    var ARRIVAL_SLOWDOWN = 0.92;  // quase para sobre cada cidade (0 = velocidade constante)
    var ORBIT_DEG = 50;           // quanto a câmera gira em volta de cada cidade
    var LOOK_AHEAD = 0.3;
    var RAMP_MS = 2000;           // aceleração suave ao (re)começar

    function segmentMs(k) {
        var ms = distMeters(point(k), point(k + 1)) / GROUND_SPEED * 1000;
        return Math.max(MIN_TRAVEL_MS, Math.min(MAX_TRAVEL_MS, ms)) + LINGER_MS;
    }

    // Tempo do trecho (u) -> posição na curva (t). A velocidade fica
    // 1 - A·cos(2πu): quase parada sobre as cidades (dá tempo de os imóveis
    // carregarem), mais rápida entre elas, sem nunca parar de vez. Com
    // A = 0,92 cerca de 40% do trecho é gasto a poucos km das cidades.
    function warp(u) {
        return u - ARRIVAL_SLOWDOWN * Math.sin(2 * Math.PI * u) / (2 * Math.PI);
    }

    var clock = 0;  // tempo total de voo: move as oscilações de câmera

    // Oscilações lentas com períodos diferentes (e não múltiplos entre si):
    // o enquadramento nunca se repete de uma cidade para outra. Os voos em
    // arco usam os mesmos valores para o voo contínuo emendar sem tranco.
    function wanderAt(c) { return 22 * Math.sin(c / 9100) + 9 * Math.sin(c / 3700 + 1.3); }
    function pitchAt(c) { return TOUR_PITCH + 6 * Math.sin(c / 13300 + 0.7); }
    // Proximidade da cidade mais perto no trecho: 1 sobre ela, 0 no meio.
    function nearness(u) { return (1 + Math.cos(2 * Math.PI * u)) / 2; }
    function zoomAt(u) { return TRAVEL_ZOOM + (CITY_ZOOM - TRAVEL_ZOOM) * nearness(u); }

    // Giro em volta da cidade: vai de -ORBIT/2 a +ORBIT/2 enquanto a câmera
    // passa por ela e volta a zero no meio do trecho (sem salto em u = 0,5).
    function orbitAt(u) {
        var phase = u < 0.5 ? u : u - 1;  // 0 sobre a cidade, ±0,5 no meio
        return ORBIT_DEG / 2 * Math.tanh(phase / 0.12) * (1 - Math.pow(2 * phase, 8));
    }

    // Mostra só os perímetros dos CARs do município `code` (null = todos).
    // A propriedade `mun` vem nos tiles (ver TILE_EXTRA_SQL no servidor).
    function setCityFilter(code) {
        if (!sicarBase) return;
        var filter = code ? ['==', ['get', 'mun'], code] : null;
        sicarBase.layerIds.forEach(function (id) { map.setFilter(id, filter); });
    }

    var shownIndex = -1;
    function showCity(k) {
        if (k === shownIndex) return;
        shownIndex = k;
        var c = cities[route[k]];
        setCityFilter(c.codigo);
        captionStep.textContent = (c.capital ? 'Capital · ' : '')
            + 'Cidade ' + fmt(k % cities.length + 1) + ' de ' + fmt(cities.length);
        captionTitle.textContent = c.nome;
        captionText.textContent = fmt(c.cars) + (c.cars === 1 ? ' imóvel' : ' imóveis') + ' do CAR';
        caption.classList.add('visible');
    }

    function startDrive() {
        if (!playing) return;
        ensureAhead(pos, 3);
        var myToken = ++token;
        var k = pos, u = 0, dur = segmentMs(k), last = null, elapsed = 0;
        var camBearing = map.getBearing();

        function frame(ts) {
            if (myToken !== token || !playing) return;
            var dt = last === null ? 0 : Math.min(ts - last, 100);
            last = ts;
            clock += dt;
            elapsed += dt;
            var ramp = Math.min(1, elapsed / RAMP_MS);
            ramp = ramp * ramp * (3 - 2 * ramp);  // smoothstep

            u += dt / dur * ramp;
            while (u >= 1) {
                u -= 1;
                k++;
                pos = k;
                ensureAhead(k, 3);
                dur = segmentMs(k);
            }

            var t = warp(u);
            var here = pathAt(k, t);
            var ta = t + LOOK_AHEAD;
            var ahead = ta <= 1 ? pathAt(k, ta) : pathAt(k + 1, ta - 1);
            var target = distMeters(here, ahead) > 1
                ? headingDeg(here, ahead) + wanderAt(clock) + orbitAt(u)
                : camBearing;
            camBearing += angleDiff(camBearing, target) * (1 - Math.exp(-dt / 1200));

            map.jumpTo({ center: here, bearing: camBearing, pitch: pitchAt(clock), zoom: zoomAt(u) });

            // A legenda mostra a cidade de que a câmera está se aproximando
            // (a partir da metade do trecho); a barra, quanto falta até ela.
            showCity(u < 0.5 ? k : k + 1);
            setProgress((u + 0.5) % 1);

            requestAnimationFrame(frame);
        }
        requestAnimationFrame(frame);
    }

    // Voo em arco até a cidade k, chegando já virado para a próxima e com a
    // mesma câmera do voo contínuo.
    function flyToCity(k, durationMs) {
        var myToken = ++token;
        map.stop();
        ensureOnlySicar();
        ensureAhead(k, 3);
        showCity(k);
        setProgress(0);
        var here = point(k);
        map.flyTo({
            center: here,
            zoom: zoomAt(0),
            pitch: pitchAt(clock),
            bearing: headingDeg(here, point(k + 1)) + wanderAt(clock),
            duration: durationMs,
            essential: true
        });
        return myToken;
    }

    // Anterior/próxima cidade com o tour pausado.
    function step(dir) {
        if (!ready || !sicarBase) return;
        pauseTour();
        if (pos < 0) {
            if (ensureStarted()) flyToCity(0, FAR_HOP_MS);
            return;
        }
        if (dir < 0 && pos <= 0) return;
        pos += dir < 0 ? -1 : 1;
        flyToCity(pos, FAR_HOP_MS);
    }

    // Só mexe no estilo se algo mudou.
    function ensureOnlySicar() {
        var ok = bases.every(function (b) { return visible[b.modelo] === (b === sicarBase); });
        if (!ok) showOnly(sicarBase);
    }

    function goToOverview() {
        if (!ready) return;
        token++;
        map.stop();
        runProgress(0);
        shownIndex = -1;
        setCityFilter(null);
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
        setProgress(0);
    }

    function playTour() {
        if (!ready || !sicarBase) return;
        setPlaying(true);
        if (!ensureStarted()) { pauseTour(); return; }
        // Voa até a cidade atual (a câmera pode ter sido movida) e segue dali.
        var myToken = flyToCity(pos, FAR_HOP_MS);
        afterMove(myToken, startDrive);
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

    map.on('load', function () {
        ready = true;
        showOverviewCaption();
        setPlaying(false);
        // Mostra a visão geral por alguns segundos e então começa a voar.
        setTimeout(function () {
            if (!reduceMotion && !userTookOver) playTour();
        }, 2500);
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
    document.getElementById('toggle_water').addEventListener('change', function (e) {
        WATER_LAYERS.forEach(function (id) {
            if (map.getLayer(id)) map.setLayoutProperty(id, 'visibility', e.target.checked ? 'visible' : 'none');
        });
    });

    terrainToggle.addEventListener('change', function () {
        var on = terrainToggle.checked;
        map.setTerrain(on ? terrainSpec() : null);
        map.setLayoutProperty('hillshade', 'visibility', on ? 'visible' : 'none');
        reliefInput.disabled = !on;
    });
})();
