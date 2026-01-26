(function (global) {
    'use strict';

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
            var isPropriedade = (f === 'Área da Propriedade');

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
     * Configures the "Toggle All" button.
     */
    function setupToggleAll(toggleBtn, layersByFonte, map, legendEl) {
        if (!toggleBtn) return;

        // Clone button to remove old event listeners
        var newBtn = toggleBtn.cloneNode(true);
        toggleBtn.parentNode.replaceChild(newBtn, toggleBtn);
        toggleBtn = newBtn;

        var allOn = true;

        toggleBtn.addEventListener('click', function () {
            var fontes = Object.keys(layersByFonte);
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
    };

})(window);
