(function (global) {
    'use strict';

    // Estado do último mapa inicializado nesta página, usado por focusMapLayer
    // para permitir que os cards de resultado apontem/centralizem o mapa.
    var mapState = null;

    // Fonte que representa o contorno da propriedade — única camada que
    // começa marcada por padrão no mapa interativo.
    var PROPERTY_FONTE = 'Área da Propriedade';

    /**
     * Creates and returns the base layers for the map.
     * @param {string|null} planetTilesUrl 
     * @returns {object} { layers: object, defaultLayer: L.layer }
     */
    function getBaseLayers(planetTilesUrl) {
        var baseOSM = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19 });
        var baseEsriSat = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', { maxZoom: 16 });
        var baseCartoLight = L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', { maxZoom: 20 });
        var baseTopo = L.tileLayer('https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png', { maxZoom: 17 });

        var layers = {
            'Satélite (Esri)': baseEsriSat,
            'OpenStreetMap': baseOSM,
            'Carto Light': baseCartoLight,
            'OpenTopoMap': baseTopo
        };

        if (planetTilesUrl) {
            var basePlanet = L.tileLayer(planetTilesUrl, { maxZoom: 19, attribution: 'Planet' });
            layers['Satélite (Planet)'] = basePlanet;
        }

        return {
            layers: layers,
            defaultLayer: baseEsriSat
        };
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
        var baseLayersInfo = getBaseLayers(options.planet_tiles_url);
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
