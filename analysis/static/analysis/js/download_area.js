/**
 * Área do download de imagem (cartão "Baixar esta imagem" da aba Imagem,
 * maps.js): o imóvel (padrão), a tela visível, um polígono desenhado na
 * hora, um polígono das bases ligadas no mapa ou um arquivo (shapefile ZIP,
 * KML/KMZ, GeoJSON — convertido no servidor, ImageDownloadAreaView).
 *
 * Com "Recortar no contorno", o que fica fora do polígono sai transparente
 * (ver image_export.js). Sem recorte, baixa o retângulo do polígono com 10%
 * de margem, como sempre foi com o imóvel.
 */
(function (global) {
    'use strict';

    var EARTH_RADIUS = 6378137;
    var PREVIEW_COLOR = '#dba63f';
    var PREVIEW_STYLE = { color: PREVIEW_COLOR, weight: 3, dashArray: '8 6', fillColor: PREVIEW_COLOR, fillOpacity: 0.08, interactive: false };
    var CLOSE_PX = 12;   // distância (px) do 1º vértice que fecha o desenho

    var MODES = [
        { key: 'imovel', label: 'Imóvel' },
        { key: 'tela', label: 'Tela' },
        { key: 'desenho', label: 'Desenhar' },
        { key: 'mapa', label: 'Clicar no mapa' },
        { key: 'arquivo', label: 'Arquivo' }
    ];

    // ------------------------------------------------------------------
    // Geometria (anéis em [lon, lat])
    // ------------------------------------------------------------------

    function polygonsOf(geojson) {
        return global.exportBaseImage ? global.exportBaseImage.polygonsOf(geojson) : [];
    }

    // Área geodésica aproximada (esfera), em m².
    function ringArea(ring) {
        var a = 0, n = ring.length, rad = Math.PI / 180;
        for (var i = 0; i < n; i++) {
            var p1 = ring[i], p2 = ring[(i + 1) % n];
            a += (p2[0] - p1[0]) * rad * (2 + Math.sin(p1[1] * rad) + Math.sin(p2[1] * rad));
        }
        return Math.abs(a * EARTH_RADIUS * EARTH_RADIUS / 2);
    }

    function polygonsArea(polys) {
        return polys.reduce(function (sum, poly) {
            return sum + poly.reduce(function (s, ring, k) { return s + (k ? -1 : 1) * ringArea(ring); }, 0);
        }, 0);
    }

    function inRing(lng, lat, ring) {
        var inside = false;
        for (var i = 0, j = ring.length - 1; i < ring.length; j = i++) {
            var xi = ring[i][0], yi = ring[i][1], xj = ring[j][0], yj = ring[j][1];
            if ((yi > lat) !== (yj > lat) && lng < (xj - xi) * (lat - yi) / (yj - yi) + xi) inside = !inside;
        }
        return inside;
    }

    function inPolygons(latlng, polys) {
        return polys.some(function (poly) {
            if (!inRing(latlng.lng, latlng.lat, poly[0])) return false;
            for (var k = 1; k < poly.length; k++) if (inRing(latlng.lng, latlng.lat, poly[k])) return false;
            return true;
        });
    }

    function boundsOf(polys) {
        var b = L.latLngBounds([]);
        polys.forEach(function (poly) { poly[0].forEach(function (c) { b.extend([c[1], c[0]]); }); });
        return b;
    }

    function multiPolygon(polys) {
        return polys.length === 1 ? { type: 'Polygon', coordinates: polys[0] } : { type: 'MultiPolygon', coordinates: polys };
    }

    function formatHectares(m2) {
        var ha = m2 / 10000;
        return ha.toLocaleString('pt-BR', { maximumFractionDigits: ha < 10 ? 2 : 1 }) + ' ha';
    }

    // Polígonos (camadas com `feature`) dentro de grupos/GeoJSON aninhados.
    function eachFeature(layer, cb) {
        if (layer.feature && layer.feature.geometry) cb(layer);
        else if (layer.eachLayer) layer.eachLayer(function (child) { eachFeature(child, cb); });
    }

    function slugify(text) {
        return (text || '').normalize('NFD').replace(/[̀-ͯ]/g, '')
            .replace(/[^\w.-]+/g, '_').replace(/^_+|_+$/g, '').slice(0, 60);
    }

    /**
     * @param {L.Map} map
     * @param {object} opts
     *   mount: elemento onde o seletor entra;
     *   property(): polígonos do imóvel (GeoJSON) ou null;
     *   point(): L.LatLng do ponto informado (sem imóvel) ou null;
     *   groups(): [{ name, group }] das bases da análise (as ligadas no mapa
     *     podem ser clicadas);
     *   uploadUrl, csrfToken(): envio do arquivo;
     *   panel: painel do mapa (recolhido enquanto desenha em tela estreita);
     *   onChange(): a área ou o recorte mudou.
     * Devolve { current(), cancel() }.
     */
    global.setupDownloadArea = function (map, opts) {
        var onChange = opts.onChange || function () {};
        var hasProperty = !!opts.property() || !!opts.point();

        var root = L.DomUtil.create('div', 'download-area', opts.mount);
        root.innerHTML =
            '<div class="download-area__label">Área do download</div>' +
            '<div class="download-area__modes" role="radiogroup" aria-label="Área do download"></div>' +
            '<div class="download-area__info">' +
                '<span class="download-area__desc"></span>' +
                '<button type="button" class="download-area__action" hidden></button>' +
            '</div>' +
            '<label class="download-area__clip">' +
                '<input type="checkbox">' +
                '<span>Recortar no contorno <small>(fora do polígono fica transparente)</small></span>' +
            '</label>' +
            '<input type="file" class="download-area__file" accept=".zip,.kml,.kmz,.geojson,.json" hidden>';
        var modesEl = root.querySelector('.download-area__modes');
        var descEl = root.querySelector('.download-area__desc');
        var actionBtn = root.querySelector('.download-area__action');
        var clipLabel = root.querySelector('.download-area__clip');
        var clipInput = clipLabel.querySelector('input');
        var fileInput = root.querySelector('.download-area__file');

        var mode = hasProperty ? 'imovel' : 'tela';
        // Recorte por modo: o imóvel continua com o retângulo + margem de
        // sempre; um polígono escolhido de propósito já vem recortado.
        var clipByMode = { imovel: false, desenho: true, mapa: true, arquivo: true };
        var selections = {};   // desenho / mapa / arquivo → { geometry, label }
        var preview = null;
        var interaction = null;   // desenho ou clique em andamento
        var uploading = false;
        var errorText = '';

        var buttons = {};
        MODES.forEach(function (m) {
            if (m.key === 'imovel' && !hasProperty) return;
            var b = L.DomUtil.create('button', 'download-area__mode', modesEl);
            b.type = 'button';
            b.textContent = m.label;
            b.setAttribute('role', 'radio');
            b.addEventListener('click', function () { choose(m.key); });
            buttons[m.key] = b;
        });

        // --------------------------------------------------------------
        // Estado e texto
        // --------------------------------------------------------------

        function selectionArea(key) {
            if (key === 'imovel') {
                var prop = opts.property();
                if (prop) return { geometry: prop, label: 'Imóvel' };
                return null;
            }
            return selections[key] || null;
        }

        /**
         * Área pronta para o download: { bounds, clip, slug } ou
         * { error } dizendo o que falta.
         */
        function current() {
            if (interaction) return { error: interaction.kind === 'draw' ? 'Termine o desenho no mapa.' : 'Clique num polígono do mapa.' };
            if (mode === 'tela') return { bounds: map.getBounds(), clip: null, slug: 'tela' };
            if (mode === 'imovel' && !opts.property()) {
                // Só o ponto informado: quadrado de 1 km em volta.
                return { bounds: opts.point().toBounds(1000), clip: null, slug: '' };
            }
            var sel = selectionArea(mode);
            if (!sel) {
                return { error: mode === 'desenho' ? 'Desenhe a área no mapa.' : mode === 'mapa' ? 'Clique num polígono do mapa.' : 'Escolha o arquivo com o polígono.' };
            }
            var polys = polygonsOf(sel.geometry);
            var clip = clipByMode[mode];
            var bounds = boundsOf(polys);
            return {
                bounds: clip ? bounds : bounds.pad(0.1),
                clip: clip ? multiPolygon(polys) : null,
                slug: [mode === 'imovel' ? '' : slugify(sel.label), clip ? 'recorte' : ''].filter(Boolean).join('_')
            };
        }

        function describe() {
            if (errorText) return errorText;
            if (uploading) return 'Lendo o arquivo…';
            if (interaction) return interaction.kind === 'draw' ? 'Desenhando no mapa…' : 'Clique num polígono no mapa…';
            if (mode === 'tela') return 'O que aparece no mapa agora.';
            if (mode === 'imovel' && !opts.property()) return 'Quadrado de 1 km em volta do ponto informado.';
            var sel = selectionArea(mode);
            if (!sel) {
                return mode === 'desenho' ? 'Clique em “Desenhar” para marcar a área no mapa.'
                    : mode === 'mapa' ? 'Ligue a base na aba Análise e clique no polígono.'
                    : 'Shapefile (ZIP), KML, KMZ ou GeoJSON.';
            }
            return sel.label + ' · ' + formatHectares(polygonsArea(polygonsOf(sel.geometry)));
        }

        function actionText() {
            if (interaction || uploading) return '';
            if (mode === 'desenho') return selections.desenho ? 'Desenhar de novo' : 'Desenhar';
            if (mode === 'mapa') return selections.mapa ? 'Escolher outro' : 'Escolher';
            if (mode === 'arquivo') return selections.arquivo ? 'Trocar arquivo' : 'Escolher arquivo';
            return '';
        }

        function render() {
            Object.keys(buttons).forEach(function (k) {
                var on = k === mode;
                buttons[k].classList.toggle('is-active', on);
                buttons[k].setAttribute('aria-checked', String(on));
            });
            descEl.textContent = describe();
            descEl.classList.toggle('is-error', !!errorText);
            descEl.title = descEl.textContent;
            var action = actionText();
            actionBtn.hidden = !action;
            actionBtn.textContent = action;
            // Tela não tem contorno; o ponto sem imóvel, também não.
            var clippable = mode in clipByMode && !(mode === 'imovel' && !opts.property());
            clipLabel.hidden = !clippable;
            clipInput.checked = !!clipByMode[mode];
            updatePreview();
        }

        function updatePreview() {
            var sel = (mode === 'desenho' || mode === 'mapa' || mode === 'arquivo') && !interaction ? selections[mode] : null;
            if (preview && (!sel || preview.geometry !== sel.geometry)) {
                map.removeLayer(preview);
                preview = null;
            }
            if (sel && !preview) {
                preview = L.geoJSON(sel.geometry, { style: PREVIEW_STYLE, interactive: false }).addTo(map);
                preview.geometry = sel.geometry;
            }
        }

        function changed() {
            render();
            onChange();
        }

        function choose(key) {
            errorText = '';
            stopInteraction();
            mode = key;
            if (key === 'desenho' && !selections.desenho) startDraw();
            else if (key === 'mapa' && !selections.mapa) startPick();
            else if (key === 'arquivo' && !selections.arquivo) fileInput.click();
            else if (selections[key]) map.fitBounds(boundsOf(polygonsOf(selections[key].geometry)), { padding: [40, 40], maxZoom: 17 });
            changed();
        }

        actionBtn.addEventListener('click', function () {
            errorText = '';
            if (mode === 'desenho') startDraw();
            else if (mode === 'mapa') startPick();
            else if (mode === 'arquivo') fileInput.click();
            changed();
        });

        clipInput.addEventListener('change', function () {
            clipByMode[mode] = clipInput.checked;
            changed();
        });

        // --------------------------------------------------------------
        // Interação no mapa (desenho e clique)
        // --------------------------------------------------------------

        var hint = L.DomUtil.create('div', 'map-area-hint', map.getContainer());
        hint.hidden = true;
        L.DomEvent.disableClickPropagation(hint);
        L.DomEvent.disableScrollPropagation(hint);

        function showHint(text, actions) {
            hint.innerHTML = '';
            L.DomUtil.create('span', 'map-area-hint__text', hint).textContent = text;
            var row = L.DomUtil.create('span', 'map-area-hint__actions', hint);
            actions.forEach(function (a) {
                var b = L.DomUtil.create('button', 'map-area-hint__btn' + (a.primary ? ' is-primary' : ''), row);
                b.type = 'button';
                b.textContent = a.label;
                b.addEventListener('click', a.run);
            });
            hint.hidden = false;
        }

        function flashHint(text) {
            var el = hint.querySelector('.map-area-hint__text');
            if (!el) return;
            var original = interaction && interaction.hintText;
            el.textContent = text;
            hint.classList.add('is-warning');
            clearTimeout(hint.timer);
            hint.timer = setTimeout(function () {
                hint.classList.remove('is-warning');
                if (original && interaction) el.textContent = original;
            }, 2600);
        }

        function beginInteraction(kind, hintText, actions) {
            stopInteraction();
            interaction = { kind: kind, hintText: hintText, dblZoom: map.doubleClickZoom.enabled() };
            map.doubleClickZoom.disable();
            map.getContainer().classList.add('is-selecting-area');
            // Em tela estreita o painel cobre o mapa: recolhe enquanto marca.
            if (opts.panel && map.getSize().x < 640) {
                opts.panel.setOpen(false);
                interaction.reopenPanel = true;
            }
            document.addEventListener('keydown', onKey);
            showHint(hintText, actions);
        }

        function stopInteraction() {
            if (!interaction) return;
            var it = interaction;
            interaction = null;
            map.off('click', onDrawClick).off('mousemove', onDrawMove).off('dblclick', finishDraw).off('click', onPick);
            if (it.layers) it.layers.forEach(function (l) { map.removeLayer(l); });
            if (it.dblZoom) map.doubleClickZoom.enable();
            map.getContainer().classList.remove('is-selecting-area');
            document.removeEventListener('keydown', onKey);
            hint.hidden = true;
            hint.classList.remove('is-warning');
            if (it.reopenPanel && opts.panel) opts.panel.open('imagem');
        }

        function cancelInteraction() {
            stopInteraction();
            changed();
        }

        function onKey(e) {
            if (!interaction) return;
            var tag = (e.target && e.target.tagName) || '';
            if (tag === 'INPUT' || tag === 'SELECT' || tag === 'TEXTAREA') return;
            if (e.key === 'Escape') { e.preventDefault(); cancelInteraction(); }
            else if (interaction.kind === 'draw' && (e.key === 'Backspace' || e.key === 'Delete')) { e.preventDefault(); undoVertex(); }
            else if (interaction.kind === 'draw' && e.key === 'Enter') { e.preventDefault(); finishDraw(); }
        }

        // ----- Desenho -----

        function startDraw() {
            var text = 'Clique no mapa para marcar os vértices. Para fechar, clique no primeiro ponto ou dê um duplo clique.';
            beginInteraction('draw', text, [
                { label: 'Desfazer', run: undoVertex },
                { label: 'Cancelar', run: cancelInteraction },
                { label: 'Concluir', run: finishDraw, primary: true }
            ]);
            var it = interaction;
            it.points = [];
            it.shape = L.polygon([], { color: PREVIEW_COLOR, weight: 3, fillOpacity: 0.12, interactive: false }).addTo(map);
            it.guide = L.polyline([], { color: PREVIEW_COLOR, weight: 2, dashArray: '4 6', interactive: false }).addTo(map);
            it.dots = L.layerGroup().addTo(map);
            it.layers = [it.shape, it.guide, it.dots];
            map.on('click', onDrawClick).on('mousemove', onDrawMove).on('dblclick', finishDraw);
        }

        function redrawShape() {
            var it = interaction;
            it.shape.setLatLngs(it.points);
            it.dots.clearLayers();
            it.points.forEach(function (p, i) {
                L.circleMarker(p, {
                    radius: i ? 4 : 6, color: '#17301f', weight: 2, fillColor: i ? '#fff' : PREVIEW_COLOR, fillOpacity: 1, interactive: false
                }).addTo(it.dots);
            });
            if (!it.points.length) it.guide.setLatLngs([]);
        }

        function onDrawClick(e) {
            var it = interaction;
            if (!it || it.kind !== 'draw') return;
            if (it.points.length >= 3 &&
                map.latLngToContainerPoint(it.points[0]).distanceTo(e.containerPoint) < CLOSE_PX) {
                finishDraw();
                return;
            }
            it.points.push(e.latlng);
            redrawShape();
        }

        function onDrawMove(e) {
            var it = interaction;
            if (!it || it.kind !== 'draw' || !it.points.length) return;
            var pts = it.points;
            it.guide.setLatLngs(pts.length > 1 ? [pts[pts.length - 1], e.latlng, pts[0]] : [pts[0], e.latlng]);
        }

        function undoVertex() {
            if (!interaction || interaction.kind !== 'draw') return;
            interaction.points.pop();
            redrawShape();
        }

        function finishDraw() {
            var it = interaction;
            if (!it || it.kind !== 'draw') return;
            // O duplo clique também gera dois cliques no mesmo lugar.
            var pts = [];
            it.points.forEach(function (p) {
                var last = pts[pts.length - 1];
                if (!last || map.latLngToContainerPoint(last).distanceTo(map.latLngToContainerPoint(p)) > 3) pts.push(p);
            });
            if (pts.length < 3) {
                it.points = pts;
                redrawShape();
                flashHint('Marque pelo menos 3 pontos para formar a área.');
                return;
            }
            var ring = pts.map(function (p) { return [p.lng, p.lat]; });
            ring.push(ring[0].slice());
            selections.desenho = { geometry: { type: 'Polygon', coordinates: [ring] }, label: 'Desenho' };
            stopInteraction();
            mode = 'desenho';
            changed();
        }

        // ----- Clique num polígono -----

        function startPick() {
            beginInteraction('pick', 'Clique num polígono das bases ligadas no mapa (ligue mais bases na aba Análise).', [
                { label: 'Cancelar', run: cancelInteraction }
            ]);
            map.on('click', onPick);
        }

        function onPick(e) {
            var best = null;
            opts.groups().forEach(function (g) {
                if (!map.hasLayer(g.group)) return;
                eachFeature(g.group, function (fl) {
                    if (fl.getBounds && !fl.getBounds().contains(e.latlng)) return;
                    var polys = polygonsOf(fl.feature.geometry);
                    if (!polys.length || !inPolygons(e.latlng, polys)) return;
                    // Vários polígonos no ponto: fica o menor, o mais específico.
                    var area = polygonsArea(polys);
                    if (!best || area < best.area) {
                        var label = (fl.downloadLabel || g.name || '').trim();
                        best = { area: area, geometry: multiPolygon(polys), label: label || 'Polígono' };
                    }
                });
            });
            if (!best) {
                flashHint('Nenhum polígono aqui. Ligue a base na aba Análise e clique dentro dele.');
                return;
            }
            selections.mapa = { geometry: best.geometry, label: best.label };
            stopInteraction();
            mode = 'mapa';
            changed();
        }

        // --------------------------------------------------------------
        // Arquivo
        // --------------------------------------------------------------

        fileInput.addEventListener('change', function () {
            var file = fileInput.files && fileInput.files[0];
            fileInput.value = '';
            if (!file) return;
            var form = new FormData();
            form.append('arquivo', file);
            uploading = true;
            errorText = '';
            changed();
            fetch(opts.uploadUrl, {
                method: 'POST', body: form, credentials: 'same-origin', headers: { 'X-CSRFToken': opts.csrfToken() }
            }).then(function (r) {
                return r.json().catch(function () { return null; }).then(function (json) {
                    if (!r.ok || !json || !json.geometry) {
                        throw new Error((json && json.erro) || 'Não foi possível ler o arquivo (erro ' + r.status + ').');
                    }
                    return json;
                });
            }).then(function (json) {
                var polys = polygonsOf(json.geometry);
                if (!polys.length) throw new Error('O arquivo não tem nenhum polígono.');
                selections.arquivo = { geometry: json.geometry, label: json.nome || file.name };
                mode = 'arquivo';
                map.fitBounds(boundsOf(polys), { padding: [40, 40], maxZoom: 17 });
            }).catch(function (err) {
                errorText = (err && err.message && err.name !== 'TypeError')
                    ? err.message : 'Não foi possível enviar o arquivo. Confira a conexão e tente de novo.';
            }).then(function () {
                uploading = false;
                changed();
            });
        });

        render();

        return {
            current: current,
            busy: function () { return uploading || !!interaction; },
            cancel: function () { if (interaction) cancelInteraction(); }
        };
    };

    // Exposto para teste.
    global.setupDownloadArea.geometry = { ringArea: ringArea, polygonsArea: polygonsArea, inPolygons: inPolygons };
})(window);
