/*
 * Tela de resultados: layout lista + mapa e a lista de sobreposições.
 *
 * - Mede a barra do topo e o cabeçalho do mapa (CSS: --topbar-h, --map-head-h),
 *   para o mapa fixo ocupar exatamente a altura da tela.
 * - Botão "Lista": esconde/mostra a lista e o mapa usa a largura toda.
 * - Abas (Sobreposições / Demonstrativo / Recibo).
 * - Lista: busca, filtro por gravidade, abrir/fechar todas, ordenar por área,
 *   "mostrar mais", menus "Baixar" e os botões "Mapa" (focusMapLayer, maps.js).
 *
 * Roda antes do mapa; `ResultsOverlaps.mapReady()` é chamado depois que o
 * mapa existe (cores das bases na lista).
 */
(function (global) {
    'use strict';

    var doc = global.document;
    var ITEM_LIMIT = 5;
    var LIST_KEY = 'terraview:results-list-hidden';

    var ws = doc.getElementById('ws');
    var list = doc.getElementById('ws_list');
    var mapSection = doc.getElementById('ws_map');

    function $all(sel, root) {
        return Array.prototype.slice.call((root || doc).querySelectorAll(sel));
    }

    function storageGet(key) {
        try { return global.localStorage.getItem(key); } catch (e) { return null; }
    }

    function storageSet(key, value) {
        try { global.localStorage.setItem(key, value); } catch (e) { /* sem armazenamento: só não lembra */ }
    }

    // ----- Medidas do layout -----

    function measure() {
        var root = doc.documentElement;
        var topbar = doc.querySelector('.topbar');
        root.style.setProperty('--topbar-h', (topbar ? topbar.offsetHeight : 0) + 'px');
        var head = doc.getElementById('map_frame_header');
        if (ws && head) ws.style.setProperty('--map-head-h', head.offsetHeight + 'px');
    }

    var resizeTimer = null;
    function onResize() {
        clearTimeout(resizeTimer);
        resizeTimer = setTimeout(measure, 80);
    }

    // O mapa mudou de largura (lista escondida/mostrada): Leaflet e o 3D
    // escutam o resize da janela; o 2D também é avisado direto.
    function mapsChangedSize() {
        measure();
        if (global.resizeImoveisMap) global.resizeImoveisMap(false);
        try { global.dispatchEvent(new Event('resize')); } catch (e) { /* navegador antigo */ }
    }

    // ----- Esconder / mostrar a lista -----

    function setListHidden(hidden, opts) {
        if (!ws || !list) return;
        ws.classList.toggle('is-list-hidden', hidden);
        var btn = doc.getElementById('ws_toggle');
        if (btn) {
            btn.setAttribute('aria-expanded', String(!hidden));
            btn.title = hidden ? 'Mostrar a lista de resultados' : 'Esconder a lista e usar a largura toda para o mapa';
        }
        if (!opts || !opts.silent) {
            storageSet(LIST_KEY, hidden ? '1' : '0');
            mapsChangedSize();
        }
    }

    function installListToggle() {
        var btn = doc.getElementById('ws_toggle');
        if (!btn || !list) return;
        if (storageGet(LIST_KEY) === '1') setListHidden(true, { silent: true });
        btn.addEventListener('click', function () {
            setListHidden(!ws.classList.contains('is-list-hidden'));
        });
    }

    // ----- Abas -----

    function installTabs() {
        var tabs = $all('.ws-tab');
        if (tabs.length < 2) return;
        tabs.forEach(function (tab) {
            tab.addEventListener('click', function () {
                var name = tab.dataset.tab;
                tabs.forEach(function (t) {
                    var on = t === tab;
                    t.classList.toggle('is-active', on);
                    t.setAttribute('aria-selected', String(on));
                });
                $all('.ws-pane').forEach(function (p) { p.hidden = p.dataset.pane !== name; });
            });
        });
    }

    // ----- Lista de sobreposições -----

    var ov = doc.getElementById('ov');
    var searchInput = doc.getElementById('ov-search');
    var noMatches = doc.getElementById('ov-no-matches');
    var severity = '';
    var bases = ov ? $all('.ov-base', ov) : [];

    bases.forEach(function (b) { b.dataset.openInitial = b.open ? '1' : '0'; });

    function refreshBase(base, query) {
        var items = $all('.ov-item', base);
        var group = base.closest('.ov-group');
        var sevOk = !severity || (group && group.dataset.sev === severity);
        var nameMatches = !query || (base.dataset.nome || '').indexOf(query) !== -1;
        var expanded = base.dataset.expanded === '1';
        var passing = 0;

        items.forEach(function (item) {
            var passes = sevOk && (nameMatches || item.textContent.toLowerCase().indexOf(query) !== -1);
            if (passes) passing++;
            item.hidden = !passes || (!expanded && passing > ITEM_LIMIT);
        });

        var more = base.querySelector('.ov-more');
        if (more) {
            more.hidden = passing <= ITEM_LIMIT;
            more.textContent = expanded ? 'Mostrar menos' : 'Mostrar mais ' + (passing - ITEM_LIMIT);
        }

        var visible = passing > 0;
        base.hidden = !visible;
        return visible;
    }

    function refreshAll() {
        var query = searchInput ? searchInput.value.trim().toLowerCase() : '';
        var any = false;
        bases.forEach(function (base) {
            var visible = refreshBase(base, query);
            if (visible) any = true;
            // Buscando: abre as bases que têm resultado; sem busca, volta ao inicial.
            if (query) { if (visible) base.open = true; }
            else if (base.dataset.touched !== '1') base.open = base.dataset.openInitial === '1';
        });
        $all('.ov-group', ov).forEach(function (g) {
            g.hidden = !$all('.ov-base', g).some(function (b) { return !b.hidden; });
        });
        if (noMatches) noMatches.hidden = any || !bases.length;
    }

    function installFilters() {
        if (searchInput) searchInput.addEventListener('input', refreshAll);
        $all('.ov-seg__opt', ov).forEach(function (btn) {
            btn.addEventListener('click', function () {
                severity = btn.dataset.sev || '';
                $all('.ov-seg__opt', ov).forEach(function (b) {
                    var on = b === btn;
                    b.classList.toggle('is-active', on);
                    b.setAttribute('aria-pressed', String(on));
                });
                refreshAll();
            });
        });
        var openAll = doc.getElementById('ov-expand-all');
        var closeAll = doc.getElementById('ov-collapse-all');
        if (openAll) openAll.addEventListener('click', function () {
            bases.forEach(function (b) { if (!b.hidden) { b.open = true; b.dataset.touched = '1'; } });
        });
        if (closeAll) closeAll.addEventListener('click', function () {
            bases.forEach(function (b) { b.open = false; b.dataset.touched = '1'; });
        });
        // Abrir/fechar à mão: a busca não desfaz a escolha depois.
        bases.forEach(function (b) {
            var sum = b.querySelector('.ov-base__sum');
            if (sum) sum.addEventListener('click', function () { b.dataset.touched = '1'; });
        });
    }

    function installSortAndMore() {
        bases.forEach(function (base) {
            var itemsBox = base.querySelector('.ov-items');
            if (!itemsBox) return;

            var sortBtn = base.querySelector('.ov-sort');
            if (sortBtn) {
                sortBtn.addEventListener('click', function () {
                    var dir = sortBtn.dataset.sortDir === 'desc' ? 'asc' : 'desc';
                    sortBtn.dataset.sortDir = dir;
                    var label = sortBtn.querySelector('span');
                    if (label) label.textContent = dir === 'desc' ? 'Maior área' : 'Menor área';
                    $all('.ov-item', itemsBox)
                        .sort(function (a, b) {
                            var va = parseFloat(a.dataset.area || 0), vb = parseFloat(b.dataset.area || 0);
                            return dir === 'desc' ? vb - va : va - vb;
                        })
                        .forEach(function (item) { itemsBox.appendChild(item); });
                    refreshBase(base, searchInput ? searchInput.value.trim().toLowerCase() : '');
                });
            }

            if ($all('.ov-item', itemsBox).length > ITEM_LIMIT) {
                var more = doc.createElement('button');
                more.type = 'button';
                more.className = 'ov-more';
                itemsBox.parentNode.insertBefore(more, itemsBox.nextSibling);
                more.addEventListener('click', function () {
                    base.dataset.expanded = base.dataset.expanded === '1' ? '0' : '1';
                    refreshBase(base, searchInput ? searchInput.value.trim().toLowerCase() : '');
                });
            }
        });
    }

    // Menus "Baixar": um aberto por vez; fecha ao clicar fora, com Esc ou ao escolher.
    function installDownloads() {
        var downloads = $all('.base-download', ov);
        if (!downloads.length) return;
        downloads.forEach(function (d) {
            d.addEventListener('toggle', function () {
                if (!d.open) return;
                downloads.forEach(function (o) { if (o !== d) o.open = false; });
            });
            $all('.base-download__option', d).forEach(function (a) {
                a.addEventListener('click', function () { d.open = false; });
            });
        });
        doc.addEventListener('click', function (e) {
            downloads.forEach(function (d) { if (d.open && !d.contains(e.target)) d.open = false; });
        });
        doc.addEventListener('keydown', function (e) {
            if (e.key === 'Escape') downloads.forEach(function (d) { d.open = false; });
        });
    }

    // ----- Mapa -----

    function mapOnScreen() {
        var el = doc.getElementById('map_stage');
        if (!el) return false;
        var r = el.getBoundingClientRect();
        var vh = global.innerHeight || doc.documentElement.clientHeight;
        return r.top < vh * 0.6 && r.bottom > vh * 0.4;
    }

    function showMap() {
        if (ws && ws.classList.contains('is-list-hidden')) return;
        if (!mapOnScreen() && mapSection) mapSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }

    function installLocate() {
        if (!ov) return;
        ov.addEventListener('click', function (e) {
            var btn = e.target.closest('.ov-locate, .ov-focus-base');
            if (!btn || typeof global.focusMapLayer !== 'function') return;
            var isItem = btn.classList.contains('ov-locate');
            var ok = isItem
                ? global.focusMapLayer(btn.dataset.fonte, btn.dataset.label, btn.dataset.areaVal)
                : global.focusMapLayer(btn.dataset.fonte, '', '');
            if (!ok) return;
            $all('.ov-item.is-focused', ov).forEach(function (i) { i.classList.remove('is-focused'); });
            if (isItem) btn.closest('.ov-item').classList.add('is-focused');
            showMap();
        });

        // Textos longos (descrição da infração...): clique abre/fecha.
        ov.addEventListener('click', function (e) {
            var dd = e.target.closest('.ov-clamp');
            if (dd) dd.classList.toggle('is-expanded');
        });
    }

    function paintSwatches() {
        if (typeof global.getMapLegendColors !== 'function') return;
        var colors = global.getMapLegendColors();
        bases.forEach(function (base) {
            var c = colors[base.dataset.fonte];
            var sw = base.querySelector('.ov-base__swatch');
            if (sw && c) {
                sw.style.setProperty('--swatch', c);
                sw.classList.add('has-color');
                sw.title = 'Cor desta base no mapa';
            }
        });
    }

    // ----- Início -----

    measure();
    global.addEventListener('resize', onResize);
    // As fontes da web mudam a altura da barra do topo quando chegam.
    if (doc.fonts && doc.fonts.ready) doc.fonts.ready.then(measure);
    installListToggle();
    installTabs();
    if (ov) {
        installFilters();
        installSortAndMore();
        installDownloads();
        installLocate();
        refreshAll();
    }

    global.ResultsOverlaps = {
        mapReady: function () {
            measure();
            paintSwatches();
        }
    };
})(window);
