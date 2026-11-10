/**
 * Fundo animado do relatório na tela (analysis/report_print.html): curvas de
 * nível de um relevo imaginário que muda devagar, nas laterais da folha.
 * Lembra um mapa topográfico, o mesmo assunto das vistas 3D.
 *
 * Só enfeite: não imprime (CSS), não aparece quando a lateral é estreita,
 * para quando a aba está oculta e fica parado com "reduzir movimento".
 */
(function (global) {
    'use strict';

    var CELL = 14;            // px por célula da grade (marching squares)
    var SCALE = 1 / 260;      // tamanho dos "morros", em px
    var SPEED = 0.018;        // quanto o relevo muda por segundo
    var LEVELS = 16;          // curvas entre o mínimo e o máximo do relevo
    var MASTER_EVERY = 4;     // curva mestra (mais forte) a cada N curvas
    var FPS = 20;
    var PARALLAX = 0.12;      // o relevo anda um pouco com a rolagem
    var MIN_SIDE = 90;        // largura mínima (px) de cada lateral

    // ---- Ruído de Perlin 3D (x, y, tempo) ---------------------------------
    var perm = new Uint8Array(512);
    (function () {
        var p = [];
        for (var i = 0; i < 256; i++) p[i] = i;
        var seed = 20261110;
        for (i = 255; i > 0; i--) {
            seed = (seed * 1664525 + 1013904223) >>> 0;
            var j = seed % (i + 1);
            var t = p[i]; p[i] = p[j]; p[j] = t;
        }
        for (i = 0; i < 512; i++) perm[i] = p[i & 255];
    })();

    function fade(t) { return t * t * t * (t * (t * 6 - 15) + 10); }
    function lerp(a, b, t) { return a + (b - a) * t; }
    function grad(h, x, y, z) {
        h &= 15;
        var u = h < 8 ? x : y;
        var v = h < 4 ? y : (h === 12 || h === 14 ? x : z);
        return ((h & 1) ? -u : u) + ((h & 2) ? -v : v);
    }
    function noise(x, y, z) {
        var X = Math.floor(x) & 255, Y = Math.floor(y) & 255, Z = Math.floor(z) & 255;
        x -= Math.floor(x); y -= Math.floor(y); z -= Math.floor(z);
        var u = fade(x), v = fade(y), w = fade(z);
        var A = perm[X] + Y, AA = perm[A] + Z, AB = perm[A + 1] + Z;
        var B = perm[X + 1] + Y, BA = perm[B] + Z, BB = perm[B + 1] + Z;
        return lerp(
            lerp(lerp(grad(perm[AA], x, y, z), grad(perm[BA], x - 1, y, z), u),
                 lerp(grad(perm[AB], x, y - 1, z), grad(perm[BB], x - 1, y - 1, z), u), v),
            lerp(lerp(grad(perm[AA + 1], x, y, z - 1), grad(perm[BA + 1], x - 1, y, z - 1), u),
                 lerp(grad(perm[AB + 1], x, y - 1, z - 1), grad(perm[BB + 1], x - 1, y - 1, z - 1), u), v),
            w);
    }
    function relief(x, y, z) {
        return noise(x, y, z) + 0.45 * noise(x * 2.1 + 17, y * 2.1 + 9, z * 1.3);
    }

    // ---- Desenho -----------------------------------------------------------
    var canvas, ctx, sheet;
    var cols = 0, rows = 0, field = null;
    var W = 0, H = 0, dpr = 1;
    var t0 = 0, last = 0, raf = 0;
    var reduced = global.matchMedia && global.matchMedia('(prefers-reduced-motion: reduce)').matches;

    function sideRect() {
        // Faixa ocupada pela folha: as curvas somem perto dela.
        var r = sheet.getBoundingClientRect();
        return { left: r.left, right: r.right };
    }

    function resize() {
        dpr = Math.min(global.devicePixelRatio || 1, 2);
        W = global.innerWidth;
        H = global.innerHeight;
        canvas.width = Math.round(W * dpr);
        canvas.height = Math.round(H * dpr);
        cols = Math.ceil(W / CELL) + 1;
        rows = Math.ceil(H / CELL) + 1;
        field = new Float32Array(cols * rows);
        var side = sideRect();
        canvas.hidden = Math.min(side.left, W - side.right) < MIN_SIDE;
    }

    function draw(time) {
        var z = time * SPEED;
        var dy = global.scrollY * PARALLAX;
        var i, j;
        for (j = 0; j < rows; j++) {
            for (i = 0; i < cols; i++) {
                field[j * cols + i] = relief(i * CELL * SCALE, (j * CELL + dy) * SCALE, z);
            }
        }

        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        ctx.clearRect(0, 0, W, H);
        ctx.lineJoin = 'round';
        ctx.lineCap = 'round';

        var lo = -0.9, hi = 0.9;
        for (var k = 1; k < LEVELS; k++) {
            var level = lo + (hi - lo) * k / LEVELS;
            var master = k % MASTER_EVERY === 0;
            ctx.beginPath();
            for (j = 0; j < rows - 1; j++) {
                for (i = 0; i < cols - 1; i++) {
                    var a = field[j * cols + i], b = field[j * cols + i + 1];
                    var c = field[(j + 1) * cols + i + 1], d = field[(j + 1) * cols + i];
                    var idx = (a > level ? 8 : 0) | (b > level ? 4 : 0) | (c > level ? 2 : 0) | (d > level ? 1 : 0);
                    if (idx === 0 || idx === 15) continue;
                    var x = i * CELL, y = j * CELL;
                    // Pontos onde a curva cruza cada lado da célula.
                    var top = [x + CELL * (level - a) / (b - a), y];
                    var right = [x + CELL, y + CELL * (level - b) / (c - b)];
                    var bottom = [x + CELL * (level - d) / (c - d), y + CELL];
                    var left = [x, y + CELL * (level - a) / (d - a)];
                    switch (idx) {
                        case 1: case 14: seg(left, bottom); break;
                        case 2: case 13: seg(bottom, right); break;
                        case 3: case 12: seg(left, right); break;
                        case 4: case 11: seg(top, right); break;
                        case 6: case 9: seg(top, bottom); break;
                        case 7: case 8: seg(left, top); break;
                        case 5: seg(left, top); seg(bottom, right); break;
                        case 10: seg(top, right); seg(left, bottom); break;
                    }
                }
            }
            ctx.strokeStyle = master ? 'rgba(201, 143, 45, 0.55)' : 'rgba(43, 90, 56, 0.22)';
            ctx.lineWidth = master ? 1.6 : 1;
            ctx.stroke();
        }

        // Some perto da folha e nas bordas da tela, para não brigar com o texto.
        var side = sideRect();
        ctx.globalCompositeOperation = 'destination-out';
        var gl = ctx.createLinearGradient(side.left - 70, 0, side.left, 0);
        gl.addColorStop(0, 'rgba(0,0,0,0)');
        gl.addColorStop(1, 'rgba(0,0,0,1)');
        ctx.fillStyle = gl;
        ctx.fillRect(side.left - 70, 0, 70, H);
        var gr = ctx.createLinearGradient(side.right, 0, side.right + 70, 0);
        gr.addColorStop(0, 'rgba(0,0,0,1)');
        gr.addColorStop(1, 'rgba(0,0,0,0)');
        ctx.fillStyle = gr;
        ctx.fillRect(side.right, 0, 70, H);
        ctx.fillStyle = '#000';
        ctx.fillRect(side.left, 0, side.right - side.left, H);
        ctx.globalCompositeOperation = 'source-over';
    }

    function seg(p, q) {
        ctx.moveTo(p[0], p[1]);
        ctx.lineTo(q[0], q[1]);
    }

    function loop(now) {
        raf = global.requestAnimationFrame(loop);
        if (canvas.hidden || now - last < 1000 / FPS) return;
        last = now;
        draw((now - t0) / 1000);
    }

    function start() {
        if (raf || reduced) return;
        last = 0;
        raf = global.requestAnimationFrame(loop);
    }

    function stop() {
        if (raf) global.cancelAnimationFrame(raf);
        raf = 0;
    }

    function redrawStatic() {
        if (!canvas.hidden) draw((performance.now() - t0) / 1000);
    }

    function init() {
        sheet = document.querySelector('.sheet');
        if (!sheet) return;
        canvas = document.createElement('canvas');
        canvas.className = 'report-backdrop';
        canvas.setAttribute('aria-hidden', 'true');
        document.body.insertBefore(canvas, document.body.firstChild);
        ctx = canvas.getContext('2d');
        t0 = performance.now();

        resize();
        redrawStatic();
        start();

        global.addEventListener('resize', function () { resize(); redrawStatic(); });
        // Parado (reduzir movimento), ainda acompanha a rolagem.
        if (reduced) global.addEventListener('scroll', redrawStatic, { passive: true });
        document.addEventListener('visibilitychange', function () {
            if (document.hidden) stop(); else start();
        });
        // Imprimir: nada de desenhar enquanto o navegador monta as páginas.
        global.addEventListener('beforeprint', stop);
        global.addEventListener('afterprint', start);
    }

    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
    else init();
})(window);
