(function (global) {
    'use strict';

    // Estado do último mapa inicializado nesta página, usado por focusMapLayer
    // para permitir que os cards de resultado apontem/centralizem o mapa.
    var mapState = null;

    // Fonte que representa o contorno da propriedade — única camada que
    // começa marcada por padrão no mapa interativo.
    var PROPERTY_FONTE = 'Área da Propriedade';

    // Tile vazio usado pelas fontes com seletor (Planet, Wayback) enquanto a
    // lista de mosaicos/datas não chega, para não pedir tiles sem a opção.
    var BLANK_TILE = 'data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7';

    function formatDateBR(isoDate) {
        var p = (isoDate || '').split('-');
        return p.length === 3 ? p[2] + '/' + p[1] + '/' + p[0] : isoDate;
    }

    /**
     * Creates and returns the base layers for the map.
     * @param {object} imagery URLs de `imagery_config()` (imagery_service.py)
     * @returns {object} { layers: object, defaultLayer: L.layer, pickers: array }
     */
    function getBaseLayers(imagery) {
        imagery = imagery || {};
        var esriSatUrl = 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}';
        var baseOSM = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19 });
        var baseEsriSat = L.tileLayer(esriSatUrl, { maxZoom: 16 });
        var baseCartoLight = L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', { maxZoom: 20 });
        var baseTopo = L.tileLayer('https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png', { maxZoom: 17 });

        var layers = { 'Satélite (Esri)': baseEsriSat };
        // Fontes cuja imagem depende de uma escolha (mosaico/data), feita no
        // controle montado por setupImageryPicker.
        var pickers = [];

        if (imagery.google_tile_url) {
            layers['Satélite (Google)'] = L.tileLayer(imagery.google_tile_url, {
                maxZoom: 20,
                attribution: 'Imagens &copy; Google'
            });
        }

        if (imagery.planet_tile_url && imagery.planet_layers_url) {
            var basePlanet = L.tileLayer(BLANK_TILE, { maxZoom: 19, layer: '', attribution: 'Imagens &copy; Planet Labs PBC' });
            layers['Satélite (Planet)'] = basePlanet;
            pickers.push({
                layer: basePlanet,
                template: imagery.planet_tile_url,
                param: 'layer',
                label: 'Mosaico Planet',
                listUrl: imagery.planet_layers_url,
                parse: function (json) {
                    return (json.layers || []).map(function (l) {
                        return { value: encodeURIComponent(l.id), text: l.title, maxZoom: l.max_zoom };
                    });
                }
            });
        }

        if (imagery.wayback_tile_url && imagery.wayback_releases_url) {
            var baseWayback = L.tileLayer(BLANK_TILE, { maxZoom: 19, release: '', attribution: 'Imagens &copy; Esri (World Imagery Wayback)' });
            layers['Histórico (Esri Wayback)'] = baseWayback;
            pickers.push({
                layer: baseWayback,
                template: imagery.wayback_tile_url,
                param: 'release',
                label: 'Data da imagem',
                listUrl: imagery.wayback_releases_url,
                // Os tiles da Wayback demoram ~1 s cada (redirecionamento +
                // servidor lento): a lista de datas é buscada já ao abrir o
                // mapa, e a Esri atual fica por baixo enquanto eles chegam.
                // Só na Wayback: é a mesma imagem da Esri, então o fundo não
                // se confunde com a imagem escolhida.
                prefetch: true,
                backdrop: L.tileLayer(esriSatUrl, { maxZoom: 19, maxNativeZoom: 16, zIndex: 0 }),
                parse: function (json) {
                    return (json.releases || []).map(function (r) {
                        return { value: String(r.id), text: formatDateBR(r.date) };
                    });
                }
            });
        }

        layers['OpenStreetMap'] = baseOSM;
        layers['Carto Light'] = baseCartoLight;
        layers['OpenTopoMap'] = baseTopo;

        return {
            layers: layers,
            defaultLayer: baseEsriSat,
            pickers: pickers
        };
    }

    /**
     * Controle com a lista de mosaicos/datas, visível só quando o mapa base
     * ativo é uma fonte com seletor. A lista é buscada na primeira ativação
     * (ou ao abrir o mapa, nas fontes com `prefetch`).
     */
    function setupImageryPicker(map, pickers) {
        if (!pickers.length) return;

        var control = L.control({ position: 'bottomleft' });
        var container, labelEl, selectEl, statusEl, current = null;

        control.onAdd = function () {
            container = L.DomUtil.create('div', 'imagery-picker leaflet-bar');
            labelEl = L.DomUtil.create('label', 'imagery-picker-label', container);
            selectEl = L.DomUtil.create('select', 'imagery-picker-select', container);
            statusEl = L.DomUtil.create('div', 'imagery-picker-status', container);
            labelEl.setAttribute('for', 'imagery-picker-select');
            selectEl.id = 'imagery-picker-select';
            container.style.display = 'none';
            L.DomEvent.disableClickPropagation(container);
            L.DomEvent.disableScrollPropagation(container);
            selectEl.addEventListener('change', function () {
                if (current) apply(current, selectEl.value);
            });
            return container;
        };
        control.addTo(map);

        function apply(picker, value) {
            var opt = picker.options.find(function (o) { return o.value === value; }) || {};
            picker.selected = value;
            picker.layer.options[picker.param] = value;
            picker.layer.options.maxNativeZoom = opt.maxZoom;
            // setUrl não redesenha quando a URL-modelo é a mesma; aqui só
            // muda o parâmetro ({layer}/{release}), então o redraw é explícito.
            picker.layer.setUrl(picker.template, true);
            picker.layer.redraw();
        }

        function fillSelect(picker) {
            selectEl.innerHTML = '';
            picker.options.forEach(function (opt) {
                var o = document.createElement('option');
                o.value = opt.value;
                o.textContent = opt.text;
                selectEl.appendChild(o);
            });
            selectEl.value = picker.selected;
            selectEl.style.display = picker.options.length ? '' : 'none';
        }

        function setStatus(text) {
            statusEl.textContent = text || '';
            statusEl.style.display = text ? '' : 'none';
        }

        function show(picker) {
            current = picker;
            container.style.display = '';
            labelEl.textContent = picker.label;

            if (picker.options) {
                fillSelect(picker);
                setStatus(picker.options.length ? '' : picker.error);
                return;
            }

            selectEl.style.display = 'none';
            setStatus('Carregando…');
            load(picker);
        }

        function load(picker) {
            if (picker.loading || picker.options) return;
            picker.loading = true;
            fetch(picker.listUrl, { credentials: 'same-origin' })
                .then(function (r) {
                    return r.json().catch(function () { return {}; }).then(function (json) {
                        return { ok: r.ok, json: json };
                    });
                })
                .then(function (res) {
                    picker.options = picker.parse(res.json);
                    picker.error = res.json.erro || 'Nenhuma imagem disponível.';
                })
                .catch(function () {
                    picker.options = [];
                    picker.error = 'Não foi possível carregar a lista de imagens.';
                })
                .then(function () {
                    picker.loading = false;
                    if (picker.options.length) {
                        apply(picker, picker.options[0].value);
                    } else if (picker.backdrop && map.hasLayer(picker.backdrop)) {
                        // Sem datas, o fundo passaria pela imagem histórica.
                        map.removeLayer(picker.backdrop);
                    }
                    if (current === picker) show(picker);
                });
        }

        pickers.forEach(function (p) { if (p.prefetch) load(p); });

        map.on('baselayerchange', function (e) {
            pickers.forEach(function (p) {
                if (p.backdrop && p.layer !== e.layer && map.hasLayer(p.backdrop)) map.removeLayer(p.backdrop);
            });
            var picker = pickers.find(function (p) { return p.layer === e.layer; });
            if (picker) {
                // Com a lista já carregada e vazia (falhou no prefetch), sem fundo.
                var semImagens = picker.options && !picker.options.length;
                if (picker.backdrop && !semImagens) picker.backdrop.addTo(map);
                show(picker);
            } else {
                current = null;
                container.style.display = 'none';
            }
        });
    }

    /**
     * Initializes the Leaflet map instance with appropriate options based on static mode.
     * @param {string} elementId 
     * @param {boolean} isStatic 
     * @param {object} options 
     * @returns {L.Map}
     */
    function createMapInstance(elementId, isStatic, options) {
        if (isStatic) {
            return L.map(elementId, {
                zoomControl: false,
                attributionControl: false,
                dragging: false,
                scrollWheelZoom: false,
                doubleClickZoom: false,
                boxZoom: false,
                keyboard: false,
                tap: false,
                touchZoom: false,
                fullscreenControl: false
            });
        } else {
            return L.map(elementId, {
                fullscreenControl: options.fullscreenControl || true,
                scrollWheelZoom: (options.scrollWheelZoom !== undefined) ? options.scrollWheelZoom : true
            });
        }
    }

    /**
     * Generates a random HSL color.
     */
    function getRandomColor() {
        var h = Math.floor(Math.random() * 360);
        var s = Math.floor(Math.random() * 40) + 60; // 60-100%
        var l = Math.floor(Math.random() * 20) + 40; // 40-60%
        return 'hsl(' + h + ',' + s + '%,' + l + '%)';
    }

    /**
     * Processes a single item and adds it to the appropriate layer group.
     */
    function createGeoJsonLayer(item, layersByFonte, overlays, map, allGroup, legend) {
        try {
            var gj = item.gj;
            if (!gj) return;
            
            var geom = typeof gj === 'string' ? JSON.parse(gj) : gj;
            if (!geom) return;

            var f = item.fonte || 'Fonte';
            var isPropriedade = (f === PROPERTY_FONTE);

            // Determine color based on source
            var col;
            if (isPropriedade) {
                col = item.color || '#000000';
            } else if (f.toLowerCase().indexOf('mapbiomas') !== -1) {
                col = '#ff0000'; // Red for Mapbiomas
            } else if (f.toLowerCase().indexOf('veredas') !== -1) {
                col = '#00ff00'; // Green for Veredas
            } else {
                col = getRandomColor();
            }
            
            var lbl = item.label || '';
            var area = item.area || '';

            if (!layersByFonte[f]) {
                layersByFonte[f] = L.featureGroup().addTo(map);
                overlays[f] = layersByFonte[f];
            }

            var isSicar = (f === 'Base de Dados Sicar');
            // isPropriedade already defined above
            var baseFillOpacity = (isSicar || isPropriedade) ? 0 : 0.35;
            var baseWeight = 2;

            var layer = L.geoJSON(geom, {
                style: { color: col, weight: baseWeight, fillColor: col, fillOpacity: baseFillOpacity }
            });

            var tt = [lbl || f, area]
                .filter(function (x) { return x && ('' + x).trim() !== ''; })
                .join('<br> Área: ');

            // Bind tooltip and hover effects
            (function (l, tooltipText, isOutline, opacity, weight) {
                l.eachLayer(function (fl) {
                    if (tooltipText) { fl.bindTooltip(tooltipText, { sticky: true }); }
                    fl.on('mouseover', function (e) {
                        e.target.setStyle({ weight: 3, fillOpacity: isOutline ? 0.1 : 0.5 });
                    });
                    fl.on('mouseout', function (e) {
                        e.target.setStyle({ weight: weight, fillOpacity: opacity });
                    });
                });
            })(layer, tt, (isSicar || isPropriedade), baseFillOpacity, baseWeight);

            layer.addTo(layersByFonte[f]);
            allGroup.addLayer(layer);

            if (f && col) {
                legend[f] = col;
            }

        } catch (e) {
            console.error("Error processing item", e);
        }
    }

    /**
     * Iterates over all items to create layers and groups.
     */
    function processItems(items, map) {
        var overlays = {};
        var layersByFonte = {};
        var allGroup = L.featureGroup().addTo(map);
        var legend = {};

        for (var i = 0; i < items.length; i++) {
            createGeoJsonLayer(items[i], layersByFonte, overlays, map, allGroup, legend);
        }

        return {
            overlays: overlays,
            layersByFonte: layersByFonte,
            allGroup: allGroup,
            legend: legend
        };
    }

    /**
     * Builds the interactive legend.
     */
    function setupLegend(legendEl, legendData, layersByFonte, map) {
        if (!legendEl) return;
        legendEl.innerHTML = '';

        var keys = Object.keys(legendData);
        for (var j = 0; j < keys.length; j++) {
            (function () {
                var k = keys[j];
                var item = document.createElement('div');
                item.className = 'legend-item';
                
                var sw = document.createElement('span');
                sw.className = 'legend-swatch';
                sw.style.backgroundColor = legendData[k];
                
                var lbl = document.createElement('span');
                lbl.textContent = k;
                
                item.appendChild(sw);
                item.appendChild(lbl);

                item.dataset.fonte = k;
                if (!map.hasLayer(layersByFonte[k])) {
                    item.classList.add('off');
                }
                item.addEventListener('click', function () {
                    var fonte = this.dataset.fonte;
                    var grp = layersByFonte[fonte];
                    if (!grp) return;
                    
                    if (map.hasLayer(grp)) {
                        map.removeLayer(grp);
                        this.classList.add('off');
                    } else {
                        map.addLayer(grp);
                        this.classList.remove('off');
                    }
                });
                legendEl.appendChild(item);
            })();
        }
    }

    /**
     * Configures the "Toggle All" button. O contorno da propriedade fica de
     * fora dessa ação — ele é a referência fixa do mapa, não uma "base".
     */
    function setupToggleAll(toggleBtn, layersByFonte, map, legendEl) {
        if (!toggleBtn) return;

        // Clone button to remove old event listeners
        var newBtn = toggleBtn.cloneNode(true);
        toggleBtn.parentNode.replaceChild(newBtn, toggleBtn);
        toggleBtn = newBtn;

        function baseFontes() {
            return Object.keys(layersByFonte).filter(function (f) { return f !== PROPERTY_FONTE; });
        }

        var allOn = baseFontes().some(function (f) { return map.hasLayer(layersByFonte[f]); });
        toggleBtn.textContent = allOn ? 'Desmarcar todas as bases' : 'Marcar todas as bases';

        toggleBtn.addEventListener('click', function () {
            var fontes = baseFontes();
            for (var i = 0; i < fontes.length; i++) {
                var f = fontes[i];
                var grp = layersByFonte[f];
                if (!grp) continue;

                if (allOn) {
                    if (map.hasLayer(grp)) { map.removeLayer(grp); }
                } else {
                    if (!map.hasLayer(grp)) { map.addLayer(grp); }
                }
            }

            if (legendEl) {
                var legendItems = legendEl.querySelectorAll('.legend-item');
                for (var k = 0; k < legendItems.length; k++) {
                    if (legendItems[k].dataset.fonte === PROPERTY_FONTE) continue;
                    if (allOn) { legendItems[k].classList.add('off'); }
                    else { legendItems[k].classList.remove('off'); }
                }
            }

            allOn = !allOn;
            this.textContent = allOn ? 'Desmarcar todas as bases' : 'Marcar todas as bases';
        });
    }

    /**
     * Main entry point for initializing the map.
     */
    global.initImoveisMap = function (items, options) {
        options = options || {};
        var elementId = options.elementId || 'map-imoveis';
        var isStatic = options.isStatic || false;

        if (!items || !items.length) return;
        
        var mapEl = document.getElementById(elementId);
        if (!mapEl) {
            console.warn('Map element not found:', elementId);
            return;
        }

        // 1. Initialize Map
        var map = createMapInstance(elementId, isStatic, options);

        // 2. Base Layers
        var baseLayersInfo = getBaseLayers(isStatic ? {} : options.imagery);
        baseLayersInfo.defaultLayer.addTo(map);

        // 3. Process & Add Items (Overlays)
        var data = processItems(items, map);
        
        // 4. Fit Bounds
        if (data.allGroup.getLayers().length) {
            map.fitBounds(data.allGroup.getBounds(), { padding: [12, 12] });
        }

        // 5. Controls & Legend
        if (!isStatic) {
            // Por padrão, só o contorno da propriedade fica marcado; as demais
            // bases começam desmarcadas para reduzir poluição visual no mapa.
            // (Mapas estáticos do relatório impresso continuam mostrando tudo,
            // já que lá não há como reativar uma camada escondida.)
            Object.keys(data.layersByFonte).forEach(function (f) {
                if (f === PROPERTY_FONTE) return;
                var grp = data.layersByFonte[f];
                if (map.hasLayer(grp)) { map.removeLayer(grp); }
            });

            // Only add layer controls and legend if NOT static
            L.control.layers(baseLayersInfo.layers, data.overlays, { collapsed: false }).addTo(map);
            setupImageryPicker(map, baseLayersInfo.pickers);
            
            var legendEl = document.getElementById('legend-imoveis');
            setupLegend(legendEl, data.legend, data.layersByFonte, map);
            
            var toggleAllBtn = document.getElementById('toggle-all-layers');
            setupToggleAll(toggleAllBtn, data.layersByFonte, map, legendEl);
        } else {
            // If static, ensure legend is empty
            var legendEl = document.getElementById('legend-imoveis');
            if (legendEl) legendEl.innerHTML = '';
        }

        mapState = {
            map: map,
            layersByFonte: data.layersByFonte,
            legendEl: (!isStatic) ? document.getElementById('legend-imoveis') : null
        };
    };

    /**
     * Adiciona uma classe de destaque temporária a um layer (path SVG do Leaflet).
     */
    function flashPath(fl) {
        var el = fl.getElement ? fl.getElement() : (fl._path || null);
        if (!el) return;
        el.classList.add('leaflet-flash-highlight');
        setTimeout(function () {
            el.classList.remove('leaflet-flash-highlight');
        }, 2800);
    }

    /**
     * Centraliza o mapa na geometria de uma fonte/base e, se conseguir
     * identificar o item exato (por rótulo + área), destaca-o e ajusta
     * o zoom nele. Caso não encontre correspondência exata, centraliza
     * em todas as geometrias daquela fonte (degradação segura).
     *
     * @param {string} fonte Nome da base (deve bater com `item.fonte` usado ao montar o mapa).
     * @param {string} label Rótulo do item (item_info/unidade) usado para tentar achar a geometria exata.
     * @param {string|number} areaVal Área formatada com 4 casas decimais, usada como desempate na busca.
     * @returns {boolean} true se a base foi encontrada no mapa (mesmo sem match exato do item).
     */
    global.focusMapLayer = function (fonte, label, areaVal) {
        if (!mapState || !fonte) return false;
        var grp = mapState.layersByFonte[fonte];
        if (!grp) return false;

        if (!mapState.map.hasLayer(grp)) {
            mapState.map.addLayer(grp);
            if (mapState.legendEl) {
                var legendItems = mapState.legendEl.querySelectorAll('.legend-item');
                for (var i = 0; i < legendItems.length; i++) {
                    if (legendItems[i].dataset.fonte === fonte) {
                        legendItems[i].classList.remove('off');
                    }
                }
            }
        }

        var normLabel = (label || '').trim().toLowerCase();
        var normArea = (areaVal || '').toString().trim();
        var target = null;

        grp.eachLayer(function (outerLayer) {
            if (target || !outerLayer.eachLayer) return;
            var matched = false;
            outerLayer.eachLayer(function (fl) {
                if (matched) return;
                var tt = fl.getTooltip ? fl.getTooltip() : null;
                var content = tt ? ('' + tt.getContent()).toLowerCase() : '';
                if (normLabel && content.indexOf(normLabel) !== -1 && (!normArea || content.indexOf(normArea) !== -1)) {
                    matched = true;
                }
            });
            if (matched) target = outerLayer;
        });

        var focusLayer = target || grp;
        if (focusLayer.getBounds) {
            try {
                mapState.map.fitBounds(focusLayer.getBounds(), { padding: [24, 24], maxZoom: 17 });
            } catch (e) {
                // geometria sem bounds válidos: mantém o mapa como está
            }
        }

        if (target && target.eachLayer) {
            target.eachLayer(flashPath);
        }

        return true;
    };

})(window);
