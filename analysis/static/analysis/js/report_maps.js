/**
 * Mapas estáticos do relatório impresso (analysis/report_print.html).
 *
 * Diferente do mapa interativo de `maps.js`, aqui tudo é pensado para o
 * papel: sem controles de zoom, com escala, seta do norte e um círculo em
 * volta do que é pequeno demais para aparecer na escala da propriedade.
 */
(function (global) {
    'use strict';

    var ESRI_SAT = 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}';

    // Abaixo disso (em pixels, no maior lado), a área encontrada some no mapa.
    var MIN_VISIVEL_PX = 14;

    function northArrow() {
        var ctrl = L.control({ position: 'topright' });
        ctrl.onAdd = function () {
            var el = L.DomUtil.create('div', 'map-north');
            el.innerHTML = '<svg viewBox="0 0 24 32" aria-hidden="true"><path d="M12 2 L20 26 L12 20 L4 26 Z"/></svg><span>N</span>';
            el.title = 'Norte';
            return el;
        };
        return ctrl;
    }

    function pixelSize(map, bounds) {
        var a = map.latLngToLayerPoint(bounds.getNorthWest());
        var b = map.latLngToLayerPoint(bounds.getSouthEast());
        return Math.max(Math.abs(b.x - a.x), Math.abs(b.y - a.y));
    }

    /**
     * @param {string} elementId  div do mapa
     * @param {object} data       { propriedade: GeoJSON, itens: [GeoJSON], cor: '#hex' }
     */
    global.initReportMap = function (elementId, data) {
        var el = document.getElementById(elementId);
        if (!el || !data || !data.propriedade) return;

        var map = L.map(el, {
            zoomControl: false,
            attributionControl: false,
            dragging: false,
            scrollWheelZoom: false,
            doubleClickZoom: false,
            boxZoom: false,
            keyboard: false,
            touchZoom: false,
            zoomSnap: 0.25
        });
        L.tileLayer(ESRI_SAT, { maxZoom: 19, maxNativeZoom: 17 }).addTo(map);

        var itens = (data.itens || []).map(function (gj) {
            return L.geoJSON(gj, {
                style: { color: data.cor, weight: 2, fillColor: data.cor, fillOpacity: 0.45 }
            }).addTo(map);
        });

        // Contorno por cima de tudo, sem preenchimento, para ser sempre a referência.
        var propriedade = L.geoJSON(data.propriedade, {
            style: { color: '#ffffff', weight: 5, opacity: 0.85, fill: false }
        }).addTo(map);
        L.geoJSON(data.propriedade, {
            style: { color: '#111111', weight: 2.5, fill: false }
        }).addTo(map);

        var bounds = propriedade.getBounds();
        itens.forEach(function (layer) { bounds.extend(layer.getBounds()); });
        map.fitBounds(bounds, { padding: [18, 18] });

        itens.forEach(function (layer) {
            var b = layer.getBounds();
            if (pixelSize(map, b) < MIN_VISIVEL_PX) {
                L.circleMarker(b.getCenter(), {
                    radius: 13, color: data.cor, weight: 3, fill: false, dashArray: '4 3'
                }).addTo(map);
                L.circleMarker(b.getCenter(), {
                    radius: 3, color: data.cor, weight: 0, fillColor: data.cor, fillOpacity: 1
                }).addTo(map);
                // A legenda (fora do mapa) só explica o círculo quando ele aparece.
                if (el.parentNode) el.parentNode.classList.add('has-ring');
            }
        });

        L.control.scale({ imperial: false, position: 'bottomleft', maxWidth: 140 }).addTo(map);
        northArrow().addTo(map);
    };
})(window);
