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

    // Embaixo à direita: o canto de cima é do formulário de análise.
    map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), 'bottom-right');
    map.addControl(new maplibregl.FullscreenControl(), 'bottom-right');
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
        if (!ready || !sicarBase || searching) return;
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
            // Voltou com erro: o imóvel buscado fica na tela (ver "Busca do imóvel").
            if (!reduceMotion && !userTookOver && !cfg.searchError) playTour();
        }, 2500);
    });

    // =====================================================================
    // Busca do imóvel
    // ---------------------------------------------------------------------
    // Pré-visualização: assim que o CAR é digitado ou o ZIP escolhido, a
    // câmera vai até o imóvel e desenha o perímetro (upload.js chama
    // `previewPropertyOnMap`), e o formulário mostra área e situação.
    //
    // Análise: no envio, a câmera pousa sobre o imóvel enquanto o servidor
    // trabalha. A página consulta o andamento real (`analysis_progress.py`):
    // cada base consultada aparece no painel e os recortes que acendem o
    // semáforo do relatório (embargo, PRODES...) surgem no mapa.
    // =====================================================================

    var searching = false;
    var search = null;  // análise em curso (ver `searchPropertyOnMap`)
    var TARGET_COLOR = '#dba63f';
    var TARGET_LAYERS = ['search-hits-fill', 'search-hits-line', 'search-fill', 'search-glow', 'search-line'];
    var TARGET_SOURCES = ['search-hits', 'search-target', 'search-outline'];
    var LAST_TARGET_KEY = 'terraview:last-target';
    var SNAPSHOT_KEY = 'terraview:search-snapshot';
    var loaderEl = document.getElementById('page-loader');

    var whenReady = new Promise(function (resolve) {
        if (ready) resolve(); else map.once('load', resolve);
    });

    function ms(n) { return reduceMotion ? 0 : n; }

    // flyTo que resolve ao chegar; o timeout cobre o caso de o mapa não
    // disparar `moveend` (câmera já no lugar).
    function flyAndWait(myToken, opts) {
        return new Promise(function (resolve) {
            var done = false;
            function finish() { if (!done) { done = true; resolve(myToken === token); } }
            map.once('moveend', finish);
            map.flyTo(Object.assign({ essential: true }, opts));
            setTimeout(finish, (opts.duration || 0) + 800);
        });
    }

    function sleep(n) { return new Promise(function (r) { setTimeout(r, n); }); }

    function setSearchCaption(step, title, text) {
        captionStep.textContent = step;
        captionTitle.textContent = title;
        captionText.textContent = text;
        caption.classList.add('visible');
    }

    function storage(fn) {
        try { return fn(window.sessionStorage); } catch (e) { return null; }
    }

    // ----- Geometria -----

    // Área geodésica de um anel em m² (mesma fórmula do geojson-area/turf).
    function ringArea(ring) {
        var R = 6378137, rad = Math.PI / 180, area = 0;
        for (var i = 0; i < ring.length - 1; i++) {
            var p1 = ring[i], p2 = ring[i + 1];
            area += (p2[0] - p1[0]) * rad * (2 + Math.sin(p1[1] * rad) + Math.sin(p2[1] * rad));
        }
        return Math.abs(area * R * R / 2);
    }

    function polygonsOf(geom) {
        if (!geom) return [];
        if (geom.type === 'Polygon') return [geom.coordinates];
        if (geom.type === 'MultiPolygon') return geom.coordinates;
        if (geom.type === 'GeometryCollection') return geom.geometries.reduce(function (acc, g) { return acc.concat(polygonsOf(g)); }, []);
        return [];
    }

    function isPolygonFeature(f) { return f && polygonsOf(f.geometry).length > 0; }

    function areaHa(features) {
        var m2 = 0;
        features.forEach(function (f) {
            polygonsOf(f.geometry).forEach(function (poly) {
                poly.forEach(function (ring, i) { m2 += (i === 0 ? 1 : -1) * ringArea(ring); });
            });
        });
        return m2 / 10000;
    }

    function boundsOf(features) {
        var b = [Infinity, Infinity, -Infinity, -Infinity];
        function walk(c) {
            if (typeof c[0] === 'number') {
                b[0] = Math.min(b[0], c[0]); b[1] = Math.min(b[1], c[1]);
                b[2] = Math.max(b[2], c[0]); b[3] = Math.max(b[3], c[1]);
            } else c.forEach(walk);
        }
        features.forEach(function (f) {
            (f.geometry.type === 'GeometryCollection' ? f.geometry.geometries : [f.geometry])
                .forEach(function (g) { walk(g.coordinates); });
        });
        // Shapefile sem .prj vem em metros (UTM): não dá para mostrar no mapa.
        var geographic = b[0] >= -180 && b[2] <= 180 && b[1] >= -90 && b[3] <= 90;
        return isFinite(b[0]) && geographic ? [[b[0], b[1]], [b[2], b[3]]] : null;
    }

    function insideTocantins(bounds) {
        return !(bounds[1][0] < TO_BOUNDS[0][0] || bounds[0][0] > TO_BOUNDS[1][0]
            || bounds[1][1] < TO_BOUNDS[0][1] || bounds[0][1] > TO_BOUNDS[1][1]);
    }

    function cityOfCar(car) {
        var code = /^[A-Za-z]{2}-(\d{7})-/.exec(car || '');
        if (!code) return null;
        return cities.filter(function (c) { return c.codigo === code[1]; })[0] || null;
    }

    // ----- Localização do imóvel -----
    // Resultado: { status: 'found' | 'not_found' | 'outside' | 'no_prj' |
    // 'unreadable', features, bounds, area_ha, statusLabel, city, layer }.

    function targetFrom(features, extra) {
        var bounds = boundsOf(features);
        if (!bounds) return { status: 'no_prj' };
        return Object.assign({
            status: insideTocantins(bounds) ? 'found' : 'outside',
            features: features,
            bounds: bounds,
            area_ha: areaHa(features)
        }, extra || {});
    }

    function locateCar(car) {
        if (!cfg.propertyUrl) return Promise.resolve(null);
        return fetch(cfg.propertyUrl + '?car=' + encodeURIComponent(car), { credentials: 'same-origin' })
            .then(function (r) {
                if (r.status === 404) return { status: 'not_found' };
                if (!r.ok) return null;  // sem acesso ao SICAR, erro do servidor...
                return r.json().then(function (d) {
                    if (!d || !d.geometry) return { status: 'not_found' };
                    return targetFrom([{ type: 'Feature', properties: {}, geometry: d.geometry }], {
                        area_ha: d.area_ha,
                        statusLabel: STATUS_LABEL[String(d.status || '').toUpperCase()] || '',
                        city: cityOfCar(car)
                    });
                });
            });
    }

    // O ZIP baixado do SICAR traz cada tema (área do imóvel, APP, reserva
    // legal...) num zip dentro do zip; o shpjs só lê o nível de cima, então
    // os zips internos são abertos com o JSZip (como faz o ZipUploadService).
    function readShapefileZip(buf, depth) {
        if (!window.JSZip) return window.shp(buf).then(function (g) { return [].concat(g); });
        return window.JSZip.loadAsync(buf).then(function (zip) {
            var names = Object.keys(zip.files).filter(function (n) {
                return !zip.files[n].dir && !/__macosx/i.test(n);
            });
            var jobs = [];
            if (names.some(function (n) { return /\.shp$/i.test(n); })) {
                jobs.push(window.shp(buf)
                    .then(function (g) { return [].concat(g); })
                    .catch(function () { return []; }));
            }
            if (depth < 3) {
                names.filter(function (n) { return /\.zip$/i.test(n); }).forEach(function (n) {
                    jobs.push(zip.file(n).async('arraybuffer')
                        .then(function (inner) { return readShapefileZip(inner, depth + 1); })
                        .catch(function () { return []; }));
                });
            }
            return Promise.all(jobs).then(function (lists) { return [].concat.apply([], lists); });
        });
    }

    function locateZip(file) {
        if (!window.shp || !file || !file.arrayBuffer) return Promise.resolve(null);
        return file.arrayBuffer()
            .then(function (buf) { return readShapefileZip(buf, 0); })
            .then(function (collections) {
                var layers = collections.map(function (fc) {
                    return { name: String(fc.fileName || '').split('/').pop(), features: (fc.features || []).filter(isPolygonFeature) };
                }).filter(function (l) { return l.features.length; });
                if (!layers.length) return { status: 'unreadable' };
                // Mesma preferência do servidor: a camada do imóvel primeiro.
                var layer = layers.filter(function (l) { return /AREA_IMOVEL/i.test(l.name); })[0] || layers[0];
                return targetFrom(layer.features, { layer: layer.name });
            })
            .catch(function () { return { status: 'unreadable' }; });
    }

    // KML/KMZ: cada <Polygon> do arquivo vira uma feição (o servidor junta
    // todos numa área só, ver `KmlUploadService`). O KMZ é um zip com o KML.
    function readKmlText(file) {
        return file.arrayBuffer().then(function (buf) {
            var head = new Uint8Array(buf, 0, Math.min(2, buf.byteLength));
            if (head[0] !== 0x50 || head[1] !== 0x4b) return new TextDecoder().decode(buf);  // não é zip ("PK")
            if (!window.JSZip) return null;
            return window.JSZip.loadAsync(buf).then(function (zip) {
                var names = Object.keys(zip.files).filter(function (n) { return /\.kml$/i.test(n); });
                names.sort(function (a, b) {
                    return (a.toLowerCase() !== 'doc.kml') - (b.toLowerCase() !== 'doc.kml')
                        || a.split('/').length - b.split('/').length;
                });
                return names.length ? zip.file(names[0]).async('string') : null;
            });
        });
    }

    function kmlRing(boundary) {
        var el = boundary.getElementsByTagNameNS('*', 'coordinates')[0];
        if (!el) return null;
        var ring = el.textContent.trim().split(/\s+/).map(function (chunk) {
            var p = chunk.split(',');
            return [parseFloat(p[0]), parseFloat(p[1])];
        }).filter(function (c) { return isFinite(c[0]) && isFinite(c[1]); });
        return ring.length >= 3 ? ring : null;
    }

    function locateKml(file) {
        if (!file || !file.arrayBuffer) return Promise.resolve(null);
        return readKmlText(file)
            .then(function (text) {
                if (!text) return { status: 'unreadable' };
                var doc = new DOMParser().parseFromString(text, 'application/xml');
                if (doc.getElementsByTagName('parsererror').length) return { status: 'unreadable' };
                var features = [];
                Array.prototype.forEach.call(doc.getElementsByTagNameNS('*', 'Polygon'), function (poly) {
                    var rings = [];
                    Array.prototype.forEach.call(poly.children, function (b) {
                        var ring = (b.localName === 'outerBoundaryIs' || b.localName === 'innerBoundaryIs') && kmlRing(b);
                        if (!ring) return;
                        if (b.localName === 'outerBoundaryIs') rings.unshift(ring); else rings.push(ring);
                    });
                    if (rings.length) features.push({ type: 'Feature', properties: {}, geometry: { type: 'Polygon', coordinates: rings } });
                });
                if (!features.length) return { status: 'no_polygon' };
                return targetFrom(features, { source: 'KML', polygons: features.length });
            })
            .catch(function () { return { status: 'unreadable' }; });
    }

    // Vértices digitados: mesmas regras de `coordinates_input_service.py`
    // (decimal ou graus/min/seg, lat/lon em qualquer ordem, sem hemisfério =
    // sul/oeste). O servidor valida de novo; aqui é só a pré-visualização.
    var DMS_RE = /(-)?\s*(\d{1,3})\s*[°º]\s*(\d{1,2})\s*['’′]\s*(?:(\d{1,2}(?:[.,]\d+)?)\s*(?:"|''|”|″)?)?\s*([NSEWOL])?/gi;
    var LAT_HEMI = /^[NS]$/, LON_HEMI = /^[EWOL]$/;

    function coordValues(line) {
        var out = [], m;
        if (/[°º]/.test(line)) {
            DMS_RE.lastIndex = 0;
            while ((m = DMS_RE.exec(line))) {
                var v = +m[2] + m[3] / 60 + parseFloat((m[4] || '0').replace(',', '.')) / 3600;
                var h = (m[5] || '').toUpperCase();
                out.push([m[1] || /^[SWO]$/.test(h) ? -v : v, h]);
            }
        } else {
            (line.match(/-?\d+(?:[.,]\d+)?/g) || []).forEach(function (n) { out.push([parseFloat(n.replace(',', '.')), '']); });
        }
        return out;
    }

    function parseCoordinates(text) {
        var ring = [], lines = String(text || '').split(/\r?\n/);
        for (var i = 0; i < lines.length; i++) {
            if (!lines[i].trim()) continue;
            var vals = coordValues(lines[i]);
            if (vals.length !== 2 && vals.length !== 3) return { error: 'Linha ' + (i + 1) + ': esperava latitude e longitude.' };
            var a = vals[0], b = vals[1];
            a = [a[1] ? a[0] : -Math.abs(a[0]), a[1]];
            b = [b[1] ? b[0] : -Math.abs(b[0]), b[1]];
            if (LON_HEMI.test(a[1]) || LAT_HEMI.test(b[1])
                || (!LAT_HEMI.test(a[1]) && !LON_HEMI.test(b[1]) && Math.abs(a[0]) > Math.abs(b[0]))) {
                var t = a; a = b; b = t;
            }
            if (Math.abs(a[0]) > 90 || Math.abs(b[0]) > 180) return { error: 'Linha ' + (i + 1) + ': coordenada fora do intervalo.' };
            var last = ring[ring.length - 1];
            if (!last || last[0] !== b[0] || last[1] !== a[0]) ring.push([b[0], a[0]]);
        }
        if (ring.length > 1 && ring[0][0] === ring[ring.length - 1][0] && ring[0][1] === ring[ring.length - 1][1]) ring.pop();
        if (ring.length === 1) return { point: ring[0] };
        if (ring.length < 3) return { error: 'Informe 1 coordenada (para achar o imóvel do ponto) ou pelo menos 3 vértices (para uma área).' };
        return { ring: ring.concat([ring[0]]) };
    }

    function segmentsCross(p, q, r, s) {
        function side(a, b, c) { return Math.sign((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])); }
        return side(p, q, r) * side(p, q, s) < 0 && side(r, s, p) * side(r, s, q) < 0;
    }

    function ringCrosses(ring) {
        var n = ring.length - 1;
        for (var i = 0; i < n; i++) {
            for (var j = i + 2; j < n; j++) {
                if (i === 0 && j === n - 1) continue;  // lados vizinhos pelo fechamento
                if (segmentsCross(ring[i], ring[i + 1], ring[j], ring[j + 1])) return true;
            }
        }
        return false;
    }

    // Um ponto só: o imóvel do SICAR onde ele cai (o mesmo que a análise usa).
    function locatePoint(point) {
        if (!cfg.propertyUrl) return Promise.resolve(null);
        return fetch(cfg.propertyUrl + '?lon=' + point[0] + '&lat=' + point[1], { credentials: 'same-origin' })
            .then(function (r) {
                if (r.status === 404) return { status: 'no_property' };
                if (!r.ok) return null;
                return r.json().then(function (d) {
                    return targetFrom([{ type: 'Feature', properties: {}, geometry: d.geometry }], {
                        area_ha: d.area_ha,
                        statusLabel: STATUS_LABEL[String(d.status || '').toUpperCase()] || '',
                        city: cityOfCar(d.car),
                        car: d.car,
                        cars: d.cars
                    });
                });
            });
    }

    function locateCoordinates(text) {
        var parsed = parseCoordinates(text);
        if (parsed.error) return Promise.resolve({ status: 'invalid', message: parsed.error });
        if (parsed.point) return locatePoint(parsed.point);
        if (ringCrosses(parsed.ring)) {
            return Promise.resolve({ status: 'invalid', message: 'O contorno se cruza: confira se os vértices estão na ordem do perímetro.' });
        }
        var features = [{ type: 'Feature', properties: {}, geometry: { type: 'Polygon', coordinates: [parsed.ring] } }];
        return Promise.resolve(targetFrom(features, { source: 'Coordenadas', vertices: parsed.ring.length - 1 }));
    }

    function keyFor(req) {
        if (req.mode === 'car' && req.car) return 'car:' + req.car.toUpperCase();
        if (req.mode === 'coord' && req.text && req.text.trim()) return 'coord:' + req.text.trim();
        if ((req.mode === 'zip' || req.mode === 'kml') && req.file) {
            return req.mode + ':' + [req.file.name, req.file.size, req.file.lastModified].join(':');
        }
        return null;
    }

    var located = {};   // chave -> Promise do resultado (não repete a busca)
    var resolved = {};  // chave -> resultado já conhecido

    function locate(req) {
        var key = keyFor(req);
        if (!key) return Promise.resolve(null);
        if (!located[key]) {
            var locator = { car: function () { return locateCar(req.car); },
                kml: function () { return locateKml(req.file); },
                coord: function () { return locateCoordinates(req.text); } }[req.mode] || function () { return locateZip(req.file); };
            located[key] = locator()
                .catch(function () { return null; })
                .then(function (target) {
                    if (target) resolved[key] = target;
                    else delete located[key];  // falha de rede: tenta de novo depois
                    return target;
                });
        }
        return located[key];
    }

    // ----- Camadas do imóvel e dos recortes -----

    function addTarget(features) {
        removeTarget();
        // Contorno em LineStrings à parte: o `line-progress` do desenho
        // progressivo só existe em linhas, não em bordas de polígono.
        var rings = [];
        features.forEach(function (f) {
            polygonsOf(f.geometry).forEach(function (poly) {
                poly.forEach(function (ring) {
                    rings.push({ type: 'Feature', properties: {}, geometry: { type: 'LineString', coordinates: ring } });
                });
            });
        });
        map.addSource('search-hits', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
        map.addSource('search-target', { type: 'geojson',
            data: { type: 'FeatureCollection', features: features } });
        map.addSource('search-outline', { type: 'geojson', lineMetrics: true,
            data: { type: 'FeatureCollection', features: rings } });
        map.addLayer({ id: 'search-hits-fill', type: 'fill', source: 'search-hits',
            paint: { 'fill-color': ['get', 'color'], 'fill-opacity': 0.42 } });
        map.addLayer({ id: 'search-hits-line', type: 'line', source: 'search-hits',
            paint: { 'line-color': ['get', 'color'], 'line-width': 1.6 } });
        map.addLayer({ id: 'search-fill', type: 'fill', source: 'search-target',
            paint: { 'fill-color': TARGET_COLOR, 'fill-opacity': 0 } });
        map.addLayer({ id: 'search-glow', type: 'line', source: 'search-outline',
            layout: { 'line-join': 'round', 'line-cap': 'round' },
            paint: { 'line-color': TARGET_COLOR, 'line-width': 10, 'line-blur': 8, 'line-opacity': 0 } });
        map.addLayer({ id: 'search-line', type: 'line', source: 'search-outline',
            layout: { 'line-join': 'round', 'line-cap': 'round' },
            paint: { 'line-width': 3, 'line-gradient': revealGradient(0) } });
    }

    function removeTarget() {
        TARGET_LAYERS.forEach(function (id) { if (map.getLayer(id)) map.removeLayer(id); });
        TARGET_SOURCES.forEach(function (id) { if (map.getSource(id)) map.removeSource(id); });
        shownKey = null;
    }

    // Recortes encontrados pelo servidor até agora. Só troca os dados quando
    // chegou recorte novo: cada `setData` redesenha a fonte.
    function drawHits(features) {
        var src = map.getSource('search-hits');
        if (!src) return;
        src.setData({ type: 'FeatureCollection', features: features.map(function (f) {
            return { type: 'Feature', properties: { color: f.color }, geometry: f.geometry };
        }) });
    }

    // Contorno visível até a fração `p` do perímetro.
    function revealGradient(p) {
        var clear = 'rgba(219, 166, 63, 0)';
        if (p >= 1) return ['interpolate', ['linear'], ['line-progress'], 0, '#f3e3bc', 1, '#f3e3bc'];
        p = Math.max(0.001, Math.min(0.997, p));
        return ['interpolate', ['linear'], ['line-progress'],
            0, '#f3e3bc', p, '#f3e3bc', p + 0.002, clear, 1, clear];
    }

    // Desenha o contorno e acende o preenchimento; depois disso o estilo não
    // é mais mexido (trocar paint a cada quadro fazia o imóvel piscar).
    // Contorno completo de uma vez (o desenho anterior foi interrompido).
    function finishReveal() {
        if (!map.getLayer('search-line')) return;
        map.setPaintProperty('search-line', 'line-gradient', revealGradient(1));
        map.setPaintProperty('search-fill', 'fill-opacity', 0.25);
        map.setPaintProperty('search-glow', 'line-opacity', 0.5);
    }

    function reveal(myToken) {
        return new Promise(function (resolve) {
            var start = null, DRAW_MS = ms(2600);
            function frame(ts) {
                if (myToken !== token || !map.getLayer('search-line')) return resolve(false);
                if (start === null) start = ts;
                var p = DRAW_MS ? Math.min(1, (ts - start) / DRAW_MS) : 1;
                map.setPaintProperty('search-line', 'line-gradient', revealGradient(p));
                map.setPaintProperty('search-fill', 'fill-opacity', 0.25 * p);
                map.setPaintProperty('search-glow', 'line-opacity', 0.5 * p);
                if (p >= 1) return resolve(true);
                requestAnimationFrame(frame);
            }
            requestAnimationFrame(frame);
        });
    }

    var ORBIT_DEG_PER_MS = 0.0025;  // ~2,5° por segundo: poucos tiles novos nas bordas
    // Copiar o quadro do WebGL custa uma pausa curta da GPU: só de vez em quando.
    var SNAPSHOT_EVERY_MS = 6000;

    // Gira devagar em volta do ponto atual até a página de resultados
    // chegar, guardando de tempos em tempos a imagem do mapa para a
    // transição até ela (ver `pagehide` abaixo).
    function orbit(myToken) {
        captureSnapshot();
        if (reduceMotion) return;
        var last = null, bearing = map.getBearing(), sinceShot = 0;
        function frame(ts) {
            if (myToken !== token || !searching) return;
            var dt = last === null ? 0 : Math.min(ts - last, 100);
            last = ts;
            bearing += dt * ORBIT_DEG_PER_MS;
            map.setBearing(bearing);
            sinceShot += dt;
            if (sinceShot >= SNAPSHOT_EVERY_MS) { sinceShot = 0; captureSnapshot(); }
            requestAnimationFrame(frame);
        }
        requestAnimationFrame(frame);
    }

    // Margem para o imóvel não ficar atrás do painel ou do formulário.
    function framePadding() {
        if (window.innerWidth < 900) return { top: 90, bottom: 210, left: 40, right: 40 };
        return { top: 110, bottom: 170, left: 360, right: searching ? 90 : 390 };
    }

    function cameraFor(bounds) {
        var fit = map.cameraForBounds(bounds, { padding: framePadding() })
            || map.cameraForBounds(bounds, { padding: 20 });
        if (!fit) return { center: [(bounds[0][0] + bounds[1][0]) / 2, (bounds[0][1] + bounds[1][1]) / 2], zoom: 14 };
        return { center: fit.center, zoom: Math.min(15.5, fit.zoom - 0.4) };  // inclinado o imóvel "cresce" na tela
    }

    // ----- Pré-visualização -----

    var previewKey = null;  // último pedido de pré-visualização
    var shownKey = null;    // imóvel desenhado no mapa agora

    function targetCaption(target, step) {
        var parts = [];
        if (target.area_ha) parts.push(fmt(target.area_ha, 2) + ' ha');
        if (target.statusLabel) parts.push('CAR ' + target.statusLabel);
        setSearchCaption(step,
            target.city ? target.city.nome
                : target.layer ? 'Shapefile · ' + target.layer
                : target.source === 'KML' ? 'KML enviado'
                : target.source ? target.source : 'Área enviada',
            parts.join(' · '));
    }

    function showPreview(key, target, step) {
        if (shownKey === key) return;
        userTookOver = true;  // o tour não volta sozinho por cima do imóvel
        pauseTour();
        var myToken = ++token;
        map.stop();
        runProgress(0);
        caption.classList.add('paused');
        if (sicarBase) ensureOnlySicar();
        setCityFilter(target.city ? target.city.codigo : null);
        addTarget(target.features);
        shownKey = key;
        targetCaption(target, step || 'Pré-visualização');
        var cam = cameraFor(target.bounds);
        flyAndWait(myToken, { center: cam.center, zoom: cam.zoom, pitch: 50,
            bearing: map.getBearing() + 20, duration: ms(3500), curve: 1.3 })
            .then(function (ok) { if (ok) reveal(myToken); });
    }

    function previewPropertyOnMap(req) {
        var key = keyFor(req);
        if (!key) return Promise.resolve(null);
        previewKey = key;
        return whenReady
            .then(function () { return locate(req); })
            .then(function (target) {
                if (!searching && previewKey === key && target && target.status === 'found') showPreview(key, target);
                return target && Object.assign({}, target, { city: target.city && { nome: target.city.nome } });
            });
    }

    function clearPropertyPreview() {
        previewKey = null;
        if (!searching && shownKey) {
            removeTarget();
            showOverviewCaption();
        }
    }

    // ----- Painel de andamento -----

    var hud = document.getElementById('search_hud');
    var hudStatus = document.getElementById('search_hud_status');
    var hudCount = document.getElementById('search_hud_count');
    var hudBar = document.getElementById('search_hud_bar');
    var hudList = document.getElementById('search_hud_list');
    var cancelBtn = document.getElementById('search_cancel');

    var LEVEL_COLOR = { alerta: '#ff6b5a', atencao: '#ffc34d', info: '#9fd8ff' };

    function renderHud(state) {
        var bases = state.bases || [];
        var total = state.total || bases.length;
        if (total) {
            hudCount.textContent = fmt(state.done || 0) + ' de ' + fmt(total) + ' bases';
            hud.classList.remove('is-indeterminate');
            hudBar.style.width = ((state.finished ? 1 : (state.done || 0) / total) * 100).toFixed(1) + '%';
            setProgress(state.finished ? 1 : (state.done || 0) / total);
            caption.classList.remove('paused');
        }
        hudStatus.textContent = state.finished ? 'Pronto! Abrindo o resultado...'
            : state.current ? 'Consultando: ' + state.current
            : state.stage || hudStatus.textContent;

        hudList.textContent = '';
        var running = null;
        bases.forEach(function (b) {
            var li = document.createElement('li');
            li.className = 'search-hud-item is-' + b.status;
            var icon = document.createElement('span');
            icon.className = 'search-hud-icon';
            icon.setAttribute('aria-hidden', 'true');
            var name = document.createElement('span');
            name.className = 'search-hud-name';
            name.textContent = b.nome;
            name.title = b.nome;
            var result = document.createElement('span');
            result.className = 'search-hud-result';
            if (b.status === 'done') {
                if (b.count) {
                    result.textContent = fmt(b.count) + ' · ' + fmt(b.area_ha, 1) + ' ha';
                    result.style.setProperty('--c', LEVEL_COLOR[b.nivel] || LEVEL_COLOR.info);
                    li.classList.add('has-hits', 'level-' + b.nivel);
                } else {
                    result.textContent = 'nada';
                }
            }
            li.appendChild(icon);
            li.appendChild(name);
            li.appendChild(result);
            hudList.appendChild(li);
            if (b.status === 'running') running = li;
        });
        if (running) hudList.scrollTop = running.offsetTop - hudList.clientHeight / 2;
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

    function applyProgress(s, state) {
        renderHud(state);
        // PDF: o CAR só aparece depois que o servidor lê o documento.
        if (state.car && !s.carAsked && s.req.mode !== 'car') {
            s.carAsked = true;
            locate({ mode: 'car', car: state.car }).then(function (t) {
                s.carLookupDone = true;
                offerTarget(s, t);
            });
        }
        // Perímetro do servidor: para quando o navegador não conseguiu
        // localizar sozinho (shapefile sem .prj, PDF de CAR fora da base).
        if (state.target && !s.target && s.clientDone && (!s.carAsked || s.carLookupDone)) {
            offerTarget(s, targetFrom([{ type: 'Feature', properties: {}, geometry: state.target }]));
        }
        var hits = state.features || [];
        if (hits.length !== s.hits.length) {
            s.hits = hits;
            if (s.landed) drawHits(hits);
        }
    }

    // ----- Análise -----

    function offerTarget(s, target) {
        if (search !== s || s.target || !target || target.status !== 'found') return;
        s.target = target;
        saveLastTarget(keyFor(s.req), target);
        if (s.phaseDone) land(s);
    }

    function saveLastTarget(key, target) {
        storage(function (st) {
            var raw = JSON.stringify({
                at: Date.now(),
                key: key,
                target: Object.assign({}, target, { city: target.city ? target.city.codigo : null })
            });
            if (raw.length < 1500000) st.setItem(LAST_TARGET_KEY, raw);
        });
    }

    function finishPhase(s) {
        if (search !== s) return;
        s.phaseDone = true;
        if (s.target) { land(s); return; }
        // Ainda sem perímetro: fica rondando até o servidor revelar a área.
        setSearchCaption('Analisando', s.city ? s.city.nome : 'Tocantins',
            s.req.mode === 'car' ? s.req.car : 'Cruzando com as bases...');
        orbit(++token);
    }

    function land(s) {
        var t = s.target, myToken = ++token;
        s.landed = true;
        map.stop();
        var step = s.req.mode === 'car' || s.carAsked ? 'Imóvel em análise' : 'Área em análise';

        // Já na tela pela pré-visualização: nada de redesenhar nem voar de
        // novo (trocar o zoom recarrega o satélite). Só ajusta o centro,
        // inclina e começa a rondar. O zoom só muda se o envio interrompeu o
        // voo da pré-visualização no meio (câmera ainda longe do imóvel).
        if (shownKey && shownKey === keyFor(s.req) && map.getLayer('search-line')) {
            finishReveal();
            if (s.hits.length) drawHits(s.hits);
            targetCaption(t, step);
            var near = cameraFor(t.bounds);
            var keepZoom = Math.abs(map.getZoom() - near.zoom) < 0.6;
            flyAndWait(myToken, { center: near.center, zoom: keepZoom ? map.getZoom() : near.zoom,
                pitch: 52, bearing: map.getBearing() + 15, duration: ms(keepZoom ? 2500 : 4000) })
                .then(function (ok) { if (ok) orbit(myToken); });
            return;
        }

        addTarget(t.features);
        shownKey = keyFor(s.req);
        if (s.hits.length) drawHits(s.hits);
        targetCaption(t, step);
        var cam = cameraFor(t.bounds);
        flyAndWait(myToken, { center: cam.center, zoom: cam.zoom, pitch: 52,
            bearing: map.getBearing() + 25, duration: ms(4500), curve: 1.2 })
            .then(function (ok) { return ok && reveal(myToken); })
            .then(function (ok) { if (ok) orbit(myToken); });
    }

    function searchPropertyOnMap(req) {
        if (!ready) return false;
        searching = true;
        if (playing) setPlaying(false);
        var myToken = ++token;
        map.stop();
        runProgress(0);
        caption.classList.add('paused');
        document.body.classList.add('is-searching');
        if (loaderEl) loaderEl.classList.add('on-map');
        zoomHint.classList.remove('visible');
        hud.hidden = false;
        hud.classList.add('is-indeterminate');
        hudBar.style.width = '';
        hudCount.textContent = '';
        hudList.textContent = '';
        hudStatus.textContent = req.mode === 'car' ? 'Iniciando a análise...' : 'Enviando o arquivo...';
        cancelBtn.disabled = false;

        var key = keyFor(req);
        var known = key && resolved[key] && resolved[key].status === 'found' ? resolved[key] : null;
        var city = req.mode === 'car' ? cityOfCar(req.car) : null;
        var s = search = { req: req, city: city, target: null, hits: [], phaseDone: false, landed: false };

        // Filtro e visibilidade mudam uma vez só, aqui: cada troca faz os
        // tiles do SICAR serem redesenhados. Se o imóvel já está na tela
        // (pré-visualização), nada muda.
        if (!known || shownKey !== key) {
            if (sicarBase) showOnly(sicarBase);
            setCityFilter(city ? city.codigo : null);
        }
        startPolling(s);
        locate(req).then(function (t) {
            s.clientDone = true;
            offerTarget(s, t);
        });

        setSearchCaption('Buscando imóvel', city ? city.nome : 'Tocantins',
            req.mode === 'car' ? req.car : 'Localizando a área enviada...');

        // Cada mudança grande de zoom recarrega o satélite nível a nível (é o
        // que pisca), então a câmera faz o menor número de voos possível:
        //  - imóvel já localizado (pré-visualização): pousa direto;
        //  - CAR: um voo até o município enquanto o perímetro chega;
        //  - ZIP: o arquivo é lido em menos de um segundo;
        //  - PDF: sobe para o estado e espera o servidor ler o CAR.
        if (known) {
            s.target = known;
            saveLastTarget(key, known);
            finishPhase(s);
        } else if (city) {
            flyAndWait(myToken, { center: city.focus, zoom: 11, pitch: 50,
                bearing: map.getBearing(), duration: ms(4000), curve: 1.2 })
                .then(function (ok) { if (ok) finishPhase(s); });
        } else {
            Promise.race([locate(req), sleep(1500)]).then(function () {
                if (search !== s) return;
                if (s.target) { finishPhase(s); return; }
                var cam = map.cameraForBounds(TO_BOUNDS, { padding: 40 });
                flyAndWait(myToken, { center: cam.center, zoom: cam.zoom, pitch: 45,
                    bearing: map.getBearing(), duration: ms(3000) })
                    .then(function (ok) { if (ok) finishPhase(s); });
            });
        }
        return true;
    }

    // `keep`: continua mostrando o imóvel (cancelamento, voltar do resultado).
    function endSearch(keep) {
        if (!searching) return;
        var s = search;
        searching = false;
        search = null;
        var myToken = ++token;
        map.stop();
        document.body.classList.remove('is-searching');
        if (loaderEl) loaderEl.classList.remove('on-map', 'visible');
        hud.hidden = true;
        runProgress(0);
        caption.classList.add('paused');
        if (keep && s && s.target) {
            if (map.getSource('search-hits')) drawHits([]);
            targetCaption(s.target, 'Pré-visualização');
            // Voo curto: além de liberar o painel, pede de novo os tiles
            // que o `window.stop()` do cancelamento interrompeu.
            var cam = cameraFor(s.target.bounds);
            map.flyTo({ center: cam.center, zoom: cam.zoom, pitch: 50, duration: ms(1500), essential: true });
            if (!map.getLayer('search-line')) {
                addTarget(s.target.features);
                shownKey = keyFor(s.req);
                reveal(myToken);
            }
        } else {
            removeTarget();
            goToOverview();
        }
    }

    function csrfToken() {
        var el = document.querySelector('input[name="csrfmiddlewaretoken"]');
        return el ? el.value : '';
    }

    cancelBtn.addEventListener('click', function () {
        if (!search) return;
        var jobId = search.req.jobId;
        cancelBtn.disabled = true;
        // Desiste da resposta do formulário (a página não troca mais)...
        try { window.stop(); } catch (e) { /* navegador sem suporte */ }
        // ...e avisa o servidor, que para antes da próxima base.
        if (jobId && cfg.cancelUrl) {
            fetch(cfg.cancelUrl.replace('{job}', jobId), {
                method: 'POST', credentials: 'same-origin', headers: { 'X-CSRFToken': csrfToken() }
            }).catch(function () { /* a análise só termina sozinha */ });
        }
        endSearch(true);
        setDockOpen(true);
    });

    // ----- Transição para a página de resultados -----

    var snapshot = null;

    // Copia o quadro que acabou de ser desenhado (o buffer do WebGL ainda
    // está intacto durante o evento `render`), reduzido e em JPEG. O
    // `toBlob` comprime fora da thread principal: a animação não engasga.
    function captureSnapshot() {
        map.once('render', function () {
            try {
                var src = map.getCanvas();
                var w = Math.min(1280, src.width), h = Math.round(src.height * w / src.width);
                var c = document.createElement('canvas');
                c.width = w;
                c.height = h;
                c.getContext('2d').drawImage(src, 0, 0, w, h);
                c.toBlob(function (blob) {
                    if (!blob) return;
                    var reader = new FileReader();
                    reader.onload = function () { if (searching) snapshot = reader.result; };
                    reader.readAsDataURL(blob);
                }, 'image/jpeg', 0.75);
            } catch (e) { /* sem imagem, a página de resultados só não faz a transição */ }
        });
        map.triggerRepaint();
    }

    // A página de resultados (results.html) abre por cima desta imagem e a
    // dissolve: a câmera "vira" o relatório em vez de um corte seco.
    window.addEventListener('pagehide', function () {
        if (!searching || !snapshot) return;
        storage(function (st) { st.setItem(SNAPSHOT_KEY, JSON.stringify({ src: snapshot, at: Date.now() })); });
    });
    storage(function (st) { st.removeItem(SNAPSHOT_KEY); });

    // Voltar do resultado (bfcache) devolve a página como estava: encerra a
    // busca mas deixa o imóvel analisado na tela.
    window.addEventListener('pageshow', function (e) { if (e.persisted) endSearch(true); });

    // A análise voltou com erro (a página recarregou): em vez de recomeçar o
    // tour, mostra de novo o imóvel que estava sendo analisado.
    if (cfg.searchError) {
        var last = storage(function (st) { return JSON.parse(st.getItem(LAST_TARGET_KEY) || 'null'); });
        if (last && last.target && Date.now() - last.at < 30 * 60 * 1000) {
            var restored = Object.assign({}, last.target, {
                city: last.target.city ? cities.filter(function (c) { return c.codigo === last.target.city; })[0] : null
            });
            // Registrado pela chave original: a pré-visualização que o
            // upload.js pede para o CAR preenchido não voa de novo.
            var restoredKey = last.key || 'restored';
            located[restoredKey] = Promise.resolve(restored);
            resolved[restoredKey] = restored;
            whenReady.then(function () { showPreview(restoredKey, restored, 'Análise não concluída'); });
        }
    }

    window.searchPropertyOnMap = searchPropertyOnMap;
    window.previewPropertyOnMap = previewPropertyOnMap;
    window.clearPropertyPreview = clearPropertyPreview;

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

    // Formulário de análise no canto: recolhe/expande. No celular começa
    // recolhido para não cobrir o mapa.
    var dock = document.getElementById('entry_dock');
    var dockToggle = document.getElementById('entry_dock_toggle');
    function setDockOpen(open) {
        dock.dataset.open = String(open);
        dockToggle.setAttribute('aria-expanded', String(open));
    }
    // Sempre aberto quando a análise voltou com um aviso (ex.: CAR inválido).
    var hasMessage = dock.querySelector('.status-error:not([style*="none"]), .status-success');
    setDockOpen(!!hasMessage || !window.matchMedia('(max-width: 640px)').matches);
    dockToggle.addEventListener('click', function () {
        setDockOpen(dock.dataset.open !== 'true');
    });

    terrainToggle.addEventListener('change', function () {
        var on = terrainToggle.checked;
        map.setTerrain(on ? terrainSpec() : null);
        map.setLayoutProperty('hillshade', 'visibility', on ? 'visible' : 'none');
        reliefInput.disabled = !on;
    });
})();
