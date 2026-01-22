(function (global) {
    global.initImoveisMap = function (items, options) {
        options = options || {};
        var planetTilesUrl = options.planet_tiles_url;
        var elementId = options.elementId || 'map-imoveis';

        if (!items || !items.length) return;
        
        if (!document.getElementById(elementId)) {
            console.warn('Map element not found:', elementId);
            return;
        }

        var map = L.map(elementId, {
            fullscreenControl: true,
            scrollWheelZoom: false // Geralmente melhor para relatórios/scroll pages
        });

        var baseOSM = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19 });
        var baseEsriSat = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', { maxZoom: 19 });
        var baseCartoLight = L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', { maxZoom: 20 });
        var baseTopo = L.tileLayer('https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png', { maxZoom: 17 });

        var baseLayers = {
            'Satélite (Esri)': baseEsriSat,
            'OpenStreetMap': baseOSM,
            'Carto Light': baseCartoLight,
            'OpenTopoMap': baseTopo
        };

        if (planetTilesUrl) {
            var basePlanet = L.tileLayer(planetTilesUrl, { maxZoom: 19, attribution: 'Planet' });
            baseLayers['Satélite (Planet)'] = basePlanet;
        }

        baseEsriSat.addTo(map);

        var overlays = {};
        var layersByFonte = {};
        var allGroup = L.featureGroup().addTo(map);
        var legend = {};

        for (var i = 0; i < items.length; i++) {
            try {
                var gj = items[i].gj;
                if (!gj) continue;
                var geom = typeof gj === 'string' ? JSON.parse(gj) : gj;

                if (!geom) continue;
                var col = items[i].color || '#d9480f';
                var f = items[i].fonte || 'Fonte';
                var lbl = items[i].label || '';
                var area = items[i].area || '';

                if (!layersByFonte[f]) {
                    layersByFonte[f] = L.featureGroup().addTo(map);
                    overlays[f] = layersByFonte[f];
                }

                var layer = L.geoJSON(geom, { style: { color: col, weight: 2, fillColor: col, fillOpacity: 0.35 } });
                var tt = [lbl || f, area].filter(function (x) { return x && ('' + x).trim() !== ''; }).join('<br> Área: ');

                (function (tt) {
                    layer.eachLayer(function (fl) {
                        if (tt) { fl.bindTooltip(tt, { sticky: true }); }
                        fl.on('mouseover', function (e) { e.target.setStyle({ weight: 3, fillOpacity: 0.5 }); });
                        fl.on('mouseout', function (e) { e.target.setStyle({ weight: 2, fillOpacity: 0.35 }); });
                    });
                })(tt);

                layer.addTo(layersByFonte[f]);
                allGroup.addLayer(layer);
                if (f && col) { legend[f] = col; }
            } catch (e) {
                console.error("Error processing item", i, e);
            }
        }

        if (allGroup.getLayers().length) {
            map.fitBounds(allGroup.getBounds(), { padding: [12, 12] });
        }

        L.control.layers(baseLayers, overlays, { collapsed: false }).addTo(map);

        var legendEl = document.getElementById('legend-imoveis');
        var toggleAllBtn = document.getElementById('toggle-all-layers');
        
        if (legendEl) {
            legendEl.innerHTML = ''; 
            
            var keys = Object.keys(legend);
            for (var j = 0; j < keys.length; j++) {
                var k = keys[j];
                var item = document.createElement('div');
                item.className = 'legend-item';
                var sw = document.createElement('span');
                sw.className = 'legend-swatch';
                sw.style.backgroundColor = legend[k];
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
            }
        }

        var allOn = true;
        if (toggleAllBtn) {
            var newBtn = toggleAllBtn.cloneNode(true);
            toggleAllBtn.parentNode.replaceChild(newBtn, toggleAllBtn);
            toggleAllBtn = newBtn;

            toggleAllBtn.addEventListener('click', function () {
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
                    for (var i = 0; i < legendItems.length; i++) {
                        if (allOn) { legendItems[i].classList.add('off'); }
                        else { legendItems[i].classList.remove('off'); }
                    }
                }
                allOn = !allOn;
                this.textContent = allOn ? 'Desmarcar todas as bases' : 'Marcar todas as bases';
            });
        }
    };
})(window);
        