/*
 * Localização do imóvel informado no formulário de análise (CAR, ZIP, KML ou
 * coordenadas), lida no navegador para mostrar a área no mapa antes da
 * análise. Usada pelo mapa 3D (bases_3d.js) e pela interface simples
 * (interface_simples.js).
 *
 *   var locator = PropertyLocate.create({ propertyUrl: ..., cities: [...] });
 *   locator.locate({ mode: 'car', car: 'TO-...' }).then(function (target) { ... });
 */
(function () {
    'use strict';

    // Tocantins (contorno IBGE) com uma folga para o mapa não "bater" na borda.
    var TO_BOUNDS = [[-50.75, -13.50], [-45.65, -5.15]];
    var STATUS_LABEL = { AT: 'Ativo', PE: 'Pendente', SU: 'Suspenso', CA: 'Cancelado' };

    function create(cfg) {
        var cities = cfg.cities || [];

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

        // UTM (SIRGAS 2000, hemisfério sul) -> [lon, lat]: inversa da
        // projeção transversa de Mercator no elipsoide GRS80 (Snyder), com
        // erro de milímetros dentro do fuso.
        function utmToLonLat(east, north, zone) {
            var a = 6378137, f = 1 / 298.257222101, k0 = 0.9996, rad = Math.PI / 180;
            var e2 = f * (2 - f), ep2 = e2 / (1 - e2);
            var x = east - 500000, y = north - 10000000;
            var mu = y / k0 / (a * (1 - e2 / 4 - 3 * e2 * e2 / 64 - 5 * e2 * e2 * e2 / 256));
            var e1 = (1 - Math.sqrt(1 - e2)) / (1 + Math.sqrt(1 - e2));
            var phi1 = mu + (3 * e1 / 2 - 27 * Math.pow(e1, 3) / 32) * Math.sin(2 * mu)
                + (21 * e1 * e1 / 16 - 55 * Math.pow(e1, 4) / 32) * Math.sin(4 * mu)
                + (151 * Math.pow(e1, 3) / 96) * Math.sin(6 * mu)
                + (1097 * Math.pow(e1, 4) / 512) * Math.sin(8 * mu);
            var sin1 = Math.sin(phi1), cos1 = Math.cos(phi1), tan1 = Math.tan(phi1);
            var C1 = ep2 * cos1 * cos1, T1 = tan1 * tan1;
            var N1 = a / Math.sqrt(1 - e2 * sin1 * sin1);
            var R1 = a * (1 - e2) / Math.pow(1 - e2 * sin1 * sin1, 1.5);
            var D = x / (N1 * k0);
            var lat = phi1 - (N1 * tan1 / R1) * (D * D / 2
                - (5 + 3 * T1 + 10 * C1 - 4 * C1 * C1 - 9 * ep2) * Math.pow(D, 4) / 24
                + (61 + 90 * T1 + 298 * C1 + 45 * T1 * T1 - 252 * ep2 - 3 * C1 * C1) * Math.pow(D, 6) / 720);
            var lon = (D - (1 + 2 * T1 + C1) * Math.pow(D, 3) / 6
                + (5 - 2 * C1 + 28 * T1 - 3 * C1 * C1 + 8 * ep2 + 24 * T1 * T1) * Math.pow(D, 5) / 120) / cos1;
            return [(zone * 6 - 183) + lon / rad, lat / rad];
        }

        // Metros com ou sem separador de milhar: 785123.45, 785123,45 ou 785.123,45.
        // Abaixo de 100 000 (nome do vértice, altitude) não é E nem N.
        function utmValues(line) {
            return (line.match(/\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+(?:[.,]\d+)?/g) || []).map(function (t) {
                if (/^\d{1,3}(?:\.\d{3})+(?:,\d+)?$/.test(t)) t = t.replace(/\./g, '');
                return parseFloat(t.replace(',', '.'));
            }).filter(function (v) { return v >= 100000; });
        }

        // `opts.utmZone`: as linhas são E/N em UTM daquele fuso (o N, na casa
        // dos milhões, é o maior dos dois).
        function parseCoordinates(text, opts) {
            var zone = opts && opts.utmZone ? +opts.utmZone : 0;
            var ring = [], lines = String(text || '').split(/\r?\n/);
            for (var i = 0; i < lines.length; i++) {
                if (!lines[i].trim()) continue;
                if (zone) {
                    var en = utmValues(lines[i]).sort(function (p, q) { return p - q; });
                    if (en.length !== 2) return { error: 'Linha ' + (i + 1) + ': esperava E e N em UTM (metros).' };
                    if (en[0] > 900000 || en[1] > 10000000) return { error: 'Linha ' + (i + 1) + ': coordenada UTM fora do intervalo.' };
                    var p = utmToLonLat(en[0], en[1], zone), prev = ring[ring.length - 1];
                    if (!prev || prev[0] !== p[0] || prev[1] !== p[1]) ring.push(p);
                    continue;
                }
                var vals = coordValues(lines[i]);
                if (vals.length !== 2 && vals.length !== 3) return { error: 'Linha ' + (i + 1) + ': esperava latitude e longitude.' };
                var a = vals[0], b = vals[1];
                a = [a[1] ? a[0] : -Math.abs(a[0]), a[1]];
                b = [b[1] ? b[0] : -Math.abs(b[0]), b[1]];
                if (LON_HEMI.test(a[1]) || LAT_HEMI.test(b[1])
                    || (!LAT_HEMI.test(a[1]) && !LON_HEMI.test(b[1]) && Math.abs(a[0]) > Math.abs(b[0]))) {
                    var t = a; a = b; b = t;
                }
                if (Math.abs(a[0]) > 90 || Math.abs(b[0]) > 180) {
                    return { error: 'Linha ' + (i + 1) + (Math.max(Math.abs(a[0]), Math.abs(b[0])) >= 1000
                        ? ': parece estar em UTM; escolha o formato UTM e o fuso.' : ': coordenada fora do intervalo.') };
                }
                var last = ring[ring.length - 1];
                if (!last || last[0] !== b[0] || last[1] !== a[0]) ring.push([b[0], a[0]]);
            }
            if (ring.length > 1 && ring[0][0] === ring[ring.length - 1][0] && ring[0][1] === ring[ring.length - 1][1]) ring.pop();
            if (ring.length === 1) return { point: ring[0] };
            if (ring.length < 3) return { error: 'Informe 1 coordenada (para achar o imóvel do ponto) ou pelo menos 3 vértices (para uma área).' };
            return { ring: ring.concat([ring[0]]) };
        }

        // Um ponto digitado numa busca, em qualquer formato, sem o usuário
        // dizer qual: UTM (dois números em metros, fuso escrito ou deduzido),
        // graus/min/seg (com ou sem ° ' ", minutos ou segundos decimais,
        // hemisfério antes ou depois) ou graus decimais. Devolve
        // { point: [lon, lat], format: 'utm'|'gms'|'decimal', zone? },
        // { error } quando parece coordenada mas não fecha, ou null.
        var HEMI_RE = /(^|[^A-Za-zÀ-ÿ])([NSEWOL])(?![A-Za-zÀ-ÿ])/gi;

        function insideTocantins(p) {
            return p[0] >= TO_BOUNDS[0][0] - 0.3 && p[0] <= TO_BOUNDS[1][0] + 0.3
                && p[1] >= TO_BOUNDS[0][1] - 0.3 && p[1] <= TO_BOUNDS[1][1] + 0.3;
        }

        function utmZoneIn(text) {
            var m = /(?:fuso|zona|zone)\s*:?\s*(\d{1,2})/i.exec(text)
                || /(?:^|[\s,;])(\d{2})\s?[C-HJ-NP-X](?=$|[\s,;])/i.exec(text)
                || /^\s*(\d{2})\s+\d{5,}/.exec(text);
            var z = m ? +m[1] : 0;
            return z >= 18 && z <= 25 ? z : 0;
        }

        function parseUtmPoint(text) {
            var en = utmValues(text).sort(function (p, q) { return p - q; });
            if (!en.length) return null;
            if (en.length !== 2 || en[0] > 900000 || en[1] < 1000000 || en[1] > 10000000) {
                return { error: 'Coordenada UTM incompleta: informe E e N em metros (ex.: 785123 8876543).' };
            }
            var zone = utmZoneIn(text);
            if (zone) return { point: utmToLonLat(en[0], en[1], zone), format: 'utm', zone: zone };
            var hits = [22, 23].map(function (z) { return { zone: z, point: utmToLonLat(en[0], en[1], z) }; })
                .filter(function (c) { return insideTocantins(c.point); });
            if (hits.length !== 1) return { error: 'Não consegui deduzir o fuso UTM. Escreva-o junto, ex.: 22L 785123 8876543.' };
            return { point: hits[0].point, format: 'utm', zone: hits[0].zone };
        }

        // Um eixo: números (graus, minutos, segundos) + sinal + hemisfério.
        function axisValue(nums, neg, hemi) {
            var v = 0;
            for (var k = 0; k < nums.length; k++) v += nums[k] / Math.pow(60, k);
            if (nums.length > 1 && (nums[1] >= 60 || (nums[2] || 0) >= 60)) return null;
            return [neg || /^[SWO]$/.test(hemi) ? -v : (hemi ? v : -v), hemi];
        }

        function parseGeoPoint(text) {
            var hemis = [], m;
            HEMI_RE.lastIndex = 0;
            while ((m = HEMI_RE.exec(text))) hemis.push({ at: m.index + m[1].length, h: m[2].toUpperCase() });
            var nums = [], re = /(-)?\s*(\d+(?:[.,]\d+)?)\s*([°º]?)/g;
            while ((m = re.exec(text))) {
                nums.push({ at: m.index, v: parseFloat(m[2].replace(',', '.')), neg: !!m[1], deg: !!m[3] });
            }
            if (!nums.length) return null;
            // Separa os dois eixos: pelo símbolo de grau, ou ao meio (2, 4 ou 6 números).
            var groups;
            var degs = nums.filter(function (n) { return n.deg; });
            if (degs.length === 2) {
                var cut = nums.indexOf(degs[1]);
                if (nums.indexOf(degs[0]) !== 0) return null;
                groups = [nums.slice(0, cut), nums.slice(cut)];
            } else if (nums.length === 2 || nums.length === 4 || nums.length === 6) {
                groups = [nums.slice(0, nums.length / 2), nums.slice(nums.length / 2)];
            } else {
                return null;
            }
            if (groups[0].length > 3 || groups[1].length > 3) return null;
            // Hemisfério de cada eixo: as letras na ordem em que aparecem.
            var hs = hemis.length === 2 ? [hemis[0].h, hemis[1].h] : ['', ''];
            if (hemis.length === 1) hs[hemis[0].at < groups[1][0].at ? 0 : 1] = hemis[0].h;
            var a = axisValue(groups[0].map(function (n) { return n.v; }), groups[0][0].neg, hs[0]);
            var b = axisValue(groups[1].map(function (n) { return n.v; }), groups[1][0].neg, hs[1]);
            if (!a || !b) return { error: 'Minutos e segundos vão de 0 a 59.' };
            if (LON_HEMI.test(a[1]) || LAT_HEMI.test(b[1])
                || (!LAT_HEMI.test(a[1]) && !LON_HEMI.test(b[1]) && Math.abs(a[0]) > Math.abs(b[0]))) {
                var t = a; a = b; b = t;
            }
            if (Math.abs(a[0]) > 90 || Math.abs(b[0]) > 180) return null;
            var gms = degs.length || groups[0].length > 1 || groups[1].length > 1;
            return { point: [b[0], a[0]], format: gms ? 'gms' : 'decimal' };
        }

        function parsePoint(text) {
            text = String(text || '').trim();
            if (!/\d/.test(text)) return null;
            return parseUtmPoint(text) || parseGeoPoint(text);
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

        function locateCoordinates(text, utmZone) {
            var parsed = parseCoordinates(text, { utmZone: utmZone });
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
            if (req.mode === 'coord' && req.text && req.text.trim()) {
                return 'coord:' + (req.utmZone ? 'utm' + req.utmZone + ':' : '') + req.text.trim();
            }
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
                    coord: function () { return locateCoordinates(req.text, req.utmZone); } }[req.mode] || function () { return locateZip(req.file); };
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

        return {
            locate: locate,
            located: located,
            resolved: resolved,
            keyFor: keyFor,
            targetFrom: targetFrom,
            polygonsOf: polygonsOf,
            cityOfCar: cityOfCar,
            parseCoordinates: parseCoordinates,
            parsePoint: parsePoint
        };
    }

    window.PropertyLocate = { create: create, TO_BOUNDS: TO_BOUNDS, STATUS_LABEL: STATUS_LABEL };
})();
