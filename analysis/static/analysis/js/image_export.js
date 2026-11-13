/**
 * Baixa como GeoTIFF (EPSG:3857) a imagem de satélite que está no mapa base,
 * no retângulo da área escolhida (imóvel, tela, desenho, polígono do mapa ou
 * arquivo; ver download_area.js). Camadas de tiles viram um mosaico montado
 * no navegador; o ImageServer da Esri (Landsat) já devolve o
 * TIFF georreferenciado pelo exportImage.
 *
 * Com `clip` (GeoJSON Polygon/MultiPolygon em lon/lat), o que fica fora do
 * polígono sai transparente: nos tiles, por um canal alfa; na Esri, pela
 * função Clip do próprio servidor (fora vira 0, marcado como NoData).
 */
(function (global) {
    'use strict';

    var TILE = 256;
    var MAX_SIDE = 4096;          // px; acima disso o arquivo passa de ~50 MB
    var EARTH_HALF = Math.PI * 6378137;

    function metersPerPixel(z) {
        return 2 * EARTH_HALF / (TILE * Math.pow(2, z));
    }

    function toMercator(latlng) {
        var p = L.Projection.SphericalMercator.project(latlng);
        return { x: p.x, y: p.y };
    }

    /**
     * Polígonos de uma geometria GeoJSON (Polygon, MultiPolygon,
     * GeometryCollection, Feature ou FeatureCollection), como lista de
     * polígonos → anéis → [lon, lat]. Pontos e linhas ficam de fora.
     */
    function polygonsOf(geojson) {
        var out = [];
        (function walk(g) {
            if (!g) return;
            if (g.type === 'FeatureCollection') (g.features || []).forEach(walk);
            else if (g.type === 'Feature') walk(g.geometry);
            else if (g.type === 'GeometryCollection') (g.geometries || []).forEach(walk);
            else if (g.type === 'Polygon') out.push(g.coordinates);
            else if (g.type === 'MultiPolygon') g.coordinates.forEach(function (c) { out.push(c); });
        })(geojson);
        return out.filter(function (poly) { return poly && poly.length && poly[0] && poly[0].length >= 3; });
    }

    // Polígonos em Web Mercator: polígonos → anéis → {x, y}.
    function mercatorPolygons(geojson) {
        return polygonsOf(geojson).map(function (poly) {
            return poly.map(function (ring) {
                return ring.map(function (c) { return toMercator(L.latLng(c[1], c[0])); });
            });
        });
    }

    // Área com sinal (positiva = anti-horário, com y para cima).
    function signedArea(ring) {
        var a = 0;
        for (var i = 0, j = ring.length - 1; i < ring.length; j = i++) {
            a += (ring[j].x - ring[i].x) * (ring[j].y + ring[i].y);
        }
        return a / 2;
    }

    /**
     * Anéis no formato da Esri: externo no sentido horário, buracos no
     * anti-horário, fechados e sem vértices mais próximos que `tolerance`
     * (m, meio pixel da exportação) — mais detalhe só incharia o pedido.
     */
    function esriRings(polys, tolerance) {
        var rings = [];
        polys.forEach(function (poly) {
            poly.forEach(function (ring, k) {
                var pts = [];
                ring.forEach(function (p) {
                    var last = pts[pts.length - 1];
                    if (!last || Math.abs(p.x - last.x) >= tolerance || Math.abs(p.y - last.y) >= tolerance) pts.push(p);
                });
                if (pts.length < 4) pts = ring.slice();
                if (pts.length < 3) return;
                var clockwise = signedArea(pts) < 0;
                if ((k === 0) !== clockwise) pts.reverse();
                var coords = pts.map(function (p) { return [Math.round(p.x * 100) / 100, Math.round(p.y * 100) / 100]; });
                var a = coords[0], b = coords[coords.length - 1];
                if (a[0] !== b[0] || a[1] !== b[1]) coords.push(a.slice());
                rings.push(coords);
            });
        });
        return rings;
    }

    // ------------------------------------------------------------------
    // Camadas de tiles (Esri, Wayback, Planet, Sentinel-2, CBERS, Landsat 5/7…)
    // ------------------------------------------------------------------

    function tileUrl(layer, x, y, z) {
        var subdomains = layer.options.subdomains || 'abc';
        // getTileUrl do Leaflet usa o zoom atual do mapa, não o de `coords`.
        if (layer.options.minDataZoom && z < layer.options.minDataZoom) return null;
        return L.Util.template(layer._url, L.extend({
            r: '', s: subdomains[Math.abs(x + y) % subdomains.length], x: x, y: y, z: z
        }, layer.options));
    }

    function pickZoom(layer, sw, ne) {
        var maxZ = Math.min(layer.options.maxNativeZoom || layer.options.maxZoom || 18, 19);
        var minZ = layer.options.minDataZoom || 0;
        for (var z = maxZ; z >= minZ; z--) {
            var res = metersPerPixel(z);
            if ((ne.x - sw.x) / res <= MAX_SIDE && (ne.y - sw.y) / res <= MAX_SIDE) return z;
        }
        return null;
    }

    function loadImage(url) {
        return fetch(url, { credentials: 'same-origin' })
            .then(function (r) {
                if (!r.ok) return null;
                return r.blob().then(function (b) { return createImageBitmap(b); });
            })
            .catch(function () { return null; });
    }

    function exportTiles(layer, sw, ne, clip, onProgress) {
        var z = pickZoom(layer, sw, ne);
        if (z === null) return Promise.reject(new Error('A área é grande demais para baixar nesta imagem.'));
        var res = metersPerPixel(z);
        // Pixels globais do retângulo (origem no canto superior esquerdo do mundo).
        var px0 = Math.floor((sw.x + EARTH_HALF) / res), px1 = Math.ceil((ne.x + EARTH_HALF) / res);
        var py0 = Math.floor((EARTH_HALF - ne.y) / res), py1 = Math.ceil((EARTH_HALF - sw.y) / res);
        var width = px1 - px0, height = py1 - py0;

        var canvas = document.createElement('canvas');
        canvas.width = width;
        canvas.height = height;
        var ctx = canvas.getContext('2d');

        var jobs = [];
        for (var tx = Math.floor(px0 / TILE); tx <= Math.floor((px1 - 1) / TILE); tx++) {
            for (var ty = Math.floor(py0 / TILE); ty <= Math.floor((py1 - 1) / TILE); ty++) {
                jobs.push({ x: tx, y: ty, url: tileUrl(layer, tx, ty, z) });
            }
        }
        var done = 0, failed = 0, next = 0;

        function worker() {
            if (next >= jobs.length) return Promise.resolve();
            var job = jobs[next++];
            return (job.url ? loadImage(job.url) : Promise.resolve(null)).then(function (img) {
                if (img) ctx.drawImage(img, job.x * TILE - px0, job.y * TILE - py0, TILE, TILE);
                else failed++;
                done++;
                onProgress('Baixando… ' + Math.round(done / jobs.length * 100) + '%', done / jobs.length);
                return worker();
            });
        }

        var pool = [];
        for (var i = 0; i < 6; i++) pool.push(worker());
        return Promise.all(pool).then(function () {
            if (failed === jobs.length) throw new Error('A fonte não devolveu nenhum pedaço da imagem nesta área.');
            if (clip) {
                // Mantém só o que está dentro do polígono (buracos pela regra par-ímpar).
                ctx.globalCompositeOperation = 'destination-in';
                ctx.beginPath();
                clip.forEach(function (poly) {
                    poly.forEach(function (ring) {
                        ring.forEach(function (p, i) {
                            var x = (p.x + EARTH_HALF) / res - px0, y = (EARTH_HALF - p.y) / res - py0;
                            if (i) ctx.lineTo(x, y); else ctx.moveTo(x, y);
                        });
                        ctx.closePath();
                    });
                });
                ctx.fill('evenodd');
            }
            var rgba = ctx.getImageData(0, 0, width, height).data;
            var originX = px0 * res - EARTH_HALF, originY = EARTH_HALF - py0 * res;
            return new Blob([geoTiff(rgba, width, height, originX, originY, res, !!clip)], { type: 'image/tiff' });
        });
    }

    // ------------------------------------------------------------------
    // ImageServer da Esri (esri-leaflet imageMapLayer)
    // ------------------------------------------------------------------

    function exportImageServer(layer, sw, ne, clip, resolution, onProgress) {
        var width = Math.round((ne.x - sw.x) / resolution), height = Math.round((ne.y - sw.y) / resolution);
        var scale = Math.max(width / 4000, height / 4000, 1);
        width = Math.max(1, Math.round(width / scale));
        height = Math.max(1, Math.round(height / scale));
        // Mesmos parâmetros que a camada usa na tela (composição, ano), com
        // o retângulo e o tamanho da exportação.
        var params = layer._buildExportParams();
        L.extend(params, {
            bbox: [sw.x, sw.y, ne.x, ne.y].join(','),
            bboxSR: 3857,
            imageSR: 3857,
            size: width + ',' + height,
            format: 'tiff',
            f: 'image'
        });
        if (clip) {
            // A composição escolhida passa pela função Clip do servidor.
            var rule = params.renderingRule;
            if (typeof rule === 'string') rule = JSON.parse(rule);
            var args = {
                ClippingGeometry: { rings: esriRings(clip, resolution * scale / 2), spatialReference: { wkid: 3857 } },
                ClipType: 1
            };
            if (rule) args.Raster = rule;
            params.renderingRule = JSON.stringify({ rasterFunction: 'Clip', rasterFunctionArguments: args });
            params.noData = 0;
        }
        onProgress('Gerando na Esri…');
        var endpoint = layer.options.url.replace(/\/?$/, '/') + 'exportImage';
        // Com polígono o pedido pode passar do limite de uma URL: vai por POST
        // (formulário simples, sem preflight; a Esri responde com CORS).
        var request = clip
            ? fetch(endpoint, { method: 'POST', body: new URLSearchParams(params) })
            : fetch(endpoint + L.Util.getParamString(params));
        return request.then(function (r) {
            if (!r.ok) throw new Error('O servidor da imagem respondeu com erro ' + r.status + '.');
            var type = r.headers.get('Content-Type') || '';
            if (type.indexOf('json') !== -1 || type.indexOf('text') !== -1) throw new Error('O servidor da imagem recusou a exportação.');
            return r.blob();
        });
    }

    // ------------------------------------------------------------------
    // GeoTIFF RGB (RGBA com `alpha`) de 8 bits sem compressão, uma faixa só
    // ------------------------------------------------------------------

    function geoTiff(rgba, width, height, originX, originY, res, alpha) {
        var pixels = width * height;
        var samples = alpha ? 4 : 3;
        var geoKeys = [1, 1, 0, 3,
            1024, 0, 1, 1,      // GTModelType: projetado
            1025, 0, 1, 1,      // GTRasterType: PixelIsArea
            3072, 0, 1, 3857];  // ProjectedCSType: Web Mercator
        // [tag, tipo (3 short, 4 long, 12 double), valores]
        var entries = [
            [256, 4, [width]],
            [257, 4, [height]],
            [258, 3, alpha ? [8, 8, 8, 8] : [8, 8, 8]],
            [259, 3, [1]],
            [262, 3, [2]],
            [273, 4, [0]],          // offset da imagem, preenchido abaixo
            [277, 3, [samples]],
            [278, 4, [height]],
            [279, 4, [pixels * samples]],
            [284, 3, [1]],
            [33550, 12, [res, res, 0]],
            [33922, 12, [0, 0, 0, originX, originY, 0]],
            [34735, 3, geoKeys]
        ];
        // ExtraSamples (antes do 33550, as tags vão em ordem): o 4º canal é
        // alfa não pré-multiplicado, como o do canvas.
        if (alpha) entries.splice(10, 0, [338, 3, [2]]);
        var size = { 3: 2, 4: 4, 12: 8 };
        var ifdSize = 2 + entries.length * 12 + 4;
        var extraOffset = 8 + ifdSize;
        var extraSize = 0;
        entries.forEach(function (e) {
            var bytes = size[e[1]] * e[2].length;
            if (bytes > 4) extraSize += bytes + (bytes % 2);
        });
        var imageOffset = extraOffset + extraSize;
        entries[5][2][0] = imageOffset;

        var buffer = new ArrayBuffer(imageOffset + pixels * samples);
        var view = new DataView(buffer);
        view.setUint16(0, 0x4949);  // "II": little-endian
        view.setUint16(2, 42, true);
        view.setUint32(4, 8, true);
        view.setUint16(8, entries.length, true);

        function write(offset, type, values) {
            values.forEach(function (v, i) {
                if (type === 3) view.setUint16(offset + i * 2, v, true);
                else if (type === 4) view.setUint32(offset + i * 4, v, true);
                else view.setFloat64(offset + i * 8, v, true);
            });
        }

        var extra = extraOffset;
        entries.forEach(function (e, i) {
            var at = 10 + i * 12;
            var bytes = size[e[1]] * e[2].length;
            view.setUint16(at, e[0], true);
            view.setUint16(at + 2, e[1], true);
            view.setUint32(at + 4, e[2].length, true);
            if (bytes <= 4) {
                write(at + 8, e[1], e[2]);
            } else {
                view.setUint32(at + 8, extra, true);
                write(extra, e[1], e[2]);
                extra += bytes + (bytes % 2);
            }
        });
        view.setUint32(10 + entries.length * 12, 0, true);  // fim dos IFDs

        var out = new Uint8Array(buffer, imageOffset);
        if (alpha) {
            out.set(rgba.subarray(0, pixels * 4));
            return buffer;
        }
        for (var p = 0, q = 0; p < pixels; p++, q += 4) {
            out[p * 3] = rgba[q];
            out[p * 3 + 1] = rgba[q + 1];
            out[p * 3 + 2] = rgba[q + 2];
        }
        return buffer;
    }

    function save(blob, filename) {
        var a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
    }

    /**
     * @param {L.Layer} layer camada do mapa base
     * @param {L.LatLngBounds|{bounds: L.LatLngBounds, clip: ?object}} area
     *   retângulo a exportar e, opcionalmente, o polígono (GeoJSON em
     *   lon/lat) que recorta a imagem
     * @param {object} opts `filename`, `resolution` (m, só ImageServer) e
     *   `onProgress(texto, fração 0–1 ou undefined)`
     */
    global.exportBaseImage = function (layer, area, opts) {
        opts = opts || {};
        var onProgress = opts.onProgress || function () {};
        var bounds = area instanceof L.LatLngBounds ? area : area.bounds;
        var clip = area.clip ? mercatorPolygons(area.clip) : null;
        if (clip && !clip.length) clip = null;
        var sw = toMercator(bounds.getSouthWest()), ne = toMercator(bounds.getNorthEast());
        var job = (L.esri && layer instanceof L.esri.ImageMapLayer)
            ? exportImageServer(layer, sw, ne, clip, opts.resolution || 10, onProgress)
            : exportTiles(layer, sw, ne, clip, onProgress);
        return job.then(function (blob) { save(blob, opts.filename || 'imagem.tif'); });
    };

    global.exportBaseImage.polygonsOf = polygonsOf;
    // Expostos para teste.
    global.exportBaseImage.geoTiff = geoTiff;
    global.exportBaseImage.esriRings = esriRings;
})(window);
