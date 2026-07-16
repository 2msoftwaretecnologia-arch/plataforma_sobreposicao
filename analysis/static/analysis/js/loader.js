(function () {
    const messages = [
        'Cruzando dados com a base do SICAR...',
        'Analisando o perímetro da propriedade...',
        'Verificando sobreposição com áreas protegidas...',
        'Consultando focos de queimadas recentes...',
        'Cruzando informações com o PRODES...',
        'Checando embargos ambientais do Ibama...',
        'Validando Reserva Legal e APP...',
        'Sincronizando com as camadas do Naturatins...',
        'Extraindo dados do documento enviado...',
        'Calculando áreas de sobreposição...',
        'Consultando o histórico de desmatamento...',
        'Conferindo limites com o Seplan...',
        'Organizando os polígonos no mapa...',
        'Quase lá, montando o relatório final...',
    ];

    const textEl = document.getElementById('loader-status-text');
    const loaderEl = document.getElementById('page-loader');
    if (!textEl || !loaderEl) return;

    let intervalId = null;
    let order = [];
    let pointer = 0;

    function shuffle(list) {
        const arr = list.slice();
        for (let i = arr.length - 1; i > 0; i--) {
            const j = Math.floor(Math.random() * (i + 1));
            [arr[i], arr[j]] = [arr[j], arr[i]];
        }
        return arr;
    }

    // Reembaralha evitando que a última frase de uma volta se repita
    // logo na primeira da próxima (senão a caixa "trava" visualmente).
    function reshuffleAvoidingRepeat(lastMsg) {
        const next = shuffle(messages);
        if (next[0] === lastMsg && next.length > 1) {
            [next[0], next[1]] = [next[1], next[0]];
        }
        return next;
    }

    function showNextMessage() {
        if (pointer >= order.length) {
            order = reshuffleAvoidingRepeat(order[order.length - 1]);
            pointer = 0;
        }
        const msg = order[pointer++];
        textEl.classList.add('is-changing');
        setTimeout(function () {
            textEl.textContent = msg;
            textEl.classList.remove('is-changing');
        }, 350);
    }

    function start() {
        if (intervalId) return;
        loaderEl.setAttribute('aria-hidden', 'false');
        order = shuffle(messages);
        pointer = 0;
        textEl.textContent = order[pointer++];
        intervalId = setInterval(showNextMessage, 2600);
    }

    function stop() {
        clearInterval(intervalId);
        intervalId = null;
        loaderEl.setAttribute('aria-hidden', 'true');
    }

    const observer = new MutationObserver(function () {
        if (loaderEl.classList.contains('visible')) {
            start();
        } else {
            stop();
        }
    });
    observer.observe(loaderEl, { attributes: true, attributeFilter: ['class'] });

    if (loaderEl.classList.contains('visible')) start();
})();
