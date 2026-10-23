(function () {
    // Formato oficial do número do CAR: UF (2 letras) + código IBGE do
    // município (7 dígitos) + hash (32 caracteres hexadecimais), sem pontos.
    // Ex.: TO-1721000-61FBE1B58B0243E68F515CBD6C2A2CC5
    const CAR_REGEX = /^[A-Za-z]{2}-\d{7}-[0-9A-Fa-f]{32}$/;

    const groupZip = document.getElementById('group_zip');
    const groupCar = document.getElementById('group_car');
    const groupDemo = document.getElementById('group_demo');
    const groupRecibo = document.getElementById('group_recibo');
    const zipInput = document.getElementById('zip_file');
    const zipLabelText = document.getElementById('zip_label_text');
    const carInput = document.getElementById('car_input');
    const demoInput = document.getElementById('demo_file');
    const demoLabelText = document.getElementById('demo_label_text');
    const dragZone = groupDemo ? groupDemo.querySelector('.drag-zone') : null;
    const reciboInput = document.getElementById('recibo_file');
    const reciboLabelText = document.getElementById('recibo_label_text');
    const dragZoneRecibo = groupRecibo ? groupRecibo.querySelector('.drag-zone') : null;
    const clientError = document.getElementById('client_error');
    const form = document.getElementById('upload_form');
    const loader = document.getElementById('page-loader');
    const modeInputs = document.querySelectorAll('input[name="mode"]');

    function getSelectedMode() {
        const selected = document.querySelector('input[name="mode"]:checked');
        return selected ? selected.value : null;
    }

    function applyMode() {
        const mode = getSelectedMode();
        if (mode === 'zip') {
            groupZip.style.display = '';
            groupCar.style.display = 'none';
            if (groupDemo) groupDemo.style.display = 'none';
            if (groupRecibo) groupRecibo.style.display = 'none';
            carInput.required = false;
            zipInput.required = true;
        } else if (mode === 'car') {
            groupZip.style.display = 'none';
            groupCar.style.display = '';
            if (groupDemo) groupDemo.style.display = 'none';
            if (groupRecibo) groupRecibo.style.display = 'none';
            zipInput.required = false;
            carInput.required = true;
        } else if (mode === 'demostrativo') {
            groupZip.style.display = 'none';
            groupCar.style.display = 'none';
            if (groupDemo) groupDemo.style.display = '';
            if (groupRecibo) groupRecibo.style.display = 'none';
            zipInput.required = false;
            carInput.required = false;
            if (demoInput) demoInput.required = true;
            if (reciboInput) reciboInput.required = false;
        } else if (mode === 'recibo') {
            groupZip.style.display = 'none';
            groupCar.style.display = 'none';
            if (groupDemo) groupDemo.style.display = 'none';
            if (groupRecibo) groupRecibo.style.display = '';
            zipInput.required = false;
            carInput.required = false;
            if (demoInput) demoInput.required = false;
            if (reciboInput) reciboInput.required = true;
        }
        clientError.style.display = 'none';
    }

    modeInputs.forEach((el) => el.addEventListener('change', applyMode));

    const carPrefilled = (carInput.value || '').trim().length > 0;
    if (carPrefilled) {
        document.getElementById('mode_car').checked = true;
    } else {
        document.getElementById('mode_zip').checked = true;
    }
    applyMode();

    // Número colado de PDF/site costuma trazer espaços (inclusive
    // invisíveis) e traços tipográficos; com eles o `pattern` do campo
    // falha e o navegador bloqueia o envio sem avisar direito.
    function cleanCarValue(value) {
        return value
            .replace(/[\s\u200B-\u200D\uFEFF.]/g, '')
            .replace(/[\u2010-\u2015\u2212]/g, '-')
            .toUpperCase();
    }

    // Pré-visualização no mapa 3D (bases_3d.js): mostra o imóvel antes da
    // análise e já avisa se o CAR não está na base ou se o ZIP tem problema.
    const carPreview = document.getElementById('car_preview');
    const zipPreview = document.getElementById('zip_preview');
    const canPreview = typeof window.previewPropertyOnMap === 'function';

    function fmtHa(n) {
        return Number(n).toLocaleString('pt-BR', { maximumFractionDigits: 2 }) + ' ha';
    }

    function showNote(el, kind, text) {
        if (!el) return;
        el.hidden = !text;
        el.className = 'preview-note' + (kind ? ' is-' + kind : '');
        el.textContent = text || '';
    }

    function carNote(t) {
        if (!t) return ['', ''];
        if (t.status === 'found') {
            return ['ok', ['Imóvel encontrado', t.city && t.city.nome, t.area_ha ? fmtHa(t.area_ha) : '',
                t.statusLabel ? 'CAR ' + t.statusLabel : ''].filter(Boolean).join(' · ')];
        }
        if (t.status === 'not_found') {
            return ['warn', 'Este CAR não está na base do SICAR do Tocantins: a análise pode sair sem resultado. Confira o número.'];
        }
        return ['', ''];
    }

    function zipNote(t) {
        if (!t) return ['', ''];
        if (t.status === 'found') {
            return ['ok', 'Área lida do shapefile: ' + fmtHa(t.area_ha) + (t.layer ? ' (' + t.layer + ')' : '')];
        }
        if (t.status === 'outside') {
            return ['warn', 'A área fica fora do Tocantins: as bases da análise cobrem só o estado.'];
        }
        if (t.status === 'no_prj') {
            return ['warn', 'O ZIP não tem o arquivo .prj, então a área não aparece no mapa. A análise ainda pode ser feita.'];
        }
        return ['warn', 'Não deu para ler o shapefile aqui no navegador; a análise ainda pode ser feita.'];
    }

    let carPreviewTimer = null;
    let carPreviewValue = '';

    function scheduleCarPreview() {
        if (!canPreview) return;
        clearTimeout(carPreviewTimer);
        const value = carInput.value.trim();
        if (!CAR_REGEX.test(value)) {
            if (carPreviewValue) {
                carPreviewValue = '';
                showNote(carPreview);
                window.clearPropertyPreview();
            }
            return;
        }
        if (value === carPreviewValue) return;
        carPreviewTimer = setTimeout(function () {
            carPreviewValue = value;
            showNote(carPreview, 'loading', 'Procurando o imóvel no mapa...');
            window.previewPropertyOnMap({ mode: 'car', car: value }).then(function (t) {
                if (carInput.value.trim() !== value) return;
                const note = carNote(t);
                showNote(carPreview, note[0], note[1]);
            });
        }, 350);
    }

    function previewZip(file) {
        if (!canPreview) return;
        if (!file) {
            showNote(zipPreview);
            window.clearPropertyPreview();
            return;
        }
        showNote(zipPreview, 'loading', 'Lendo o shapefile...');
        window.previewPropertyOnMap({ mode: 'zip', file: file }).then(function (t) {
            if (!zipInput.files || zipInput.files[0] !== file) return;
            const note = zipNote(t);
            showNote(zipPreview, note[0], note[1]);
        });
    }

    if (carInput) {
        function validateAndCleanCarInput(e) {
            const cleaned = cleanCarValue(carInput.value);
            if (cleaned !== carInput.value) carInput.value = cleaned;
            clientError.style.display = 'none';
            scheduleCarPreview();
        }

        carInput.addEventListener('input', validateAndCleanCarInput);
        carInput.addEventListener('change', validateAndCleanCarInput);
        carInput.addEventListener('paste', function(e) {
            // Aguarda um breve momento para o valor ser colado antes de limpar
            setTimeout(validateAndCleanCarInput, 0);
        });
    }

    const ZIP_LABEL_DEFAULT = 'Arraste e solte o ZIP aqui ou clique para selecionar!';
    const dragZoneZip = groupZip.querySelector('.drag-zone');

    function isZip(file) {
        if (!file) return false;
        const nameOk = (file.name || '').toLowerCase().endsWith('.zip');
        const type = (file.type || '').toLowerCase();
        const typeOk = type === 'application/zip' || type === 'application/x-zip-compressed';
        return nameOk || typeOk;
    }

    zipInput.addEventListener('change', function () {
        if (zipInput.files && zipInput.files.length > 0) {
            zipLabelText.textContent = zipInput.files[0].name;
            clientError.style.display = 'none';
            previewZip(zipInput.files[0]);
        } else {
            zipLabelText.textContent = ZIP_LABEL_DEFAULT;
            previewZip(null);
        }
    });

    if (dragZoneZip) {
        ['dragenter','dragover'].forEach(evt => {
            dragZoneZip.addEventListener(evt, function (e) {
                e.preventDefault();
                e.stopPropagation();
                dragZoneZip.classList.add('active');
            });
        });
        ['dragleave','drop'].forEach(evt => {
            dragZoneZip.addEventListener(evt, function (e) {
                e.preventDefault();
                e.stopPropagation();
                dragZoneZip.classList.remove('active');
            });
        });
        dragZoneZip.addEventListener('drop', function (e) {
            const files = e.dataTransfer && e.dataTransfer.files ? e.dataTransfer.files : null;
            if (files && files.length > 0) {
                const zipFile = Array.from(files).find(f => isZip(f));
                if (zipFile) {
                    const dt = new DataTransfer();
                    dt.items.add(zipFile);
                    zipInput.files = dt.files;
                    zipLabelText.textContent = zipFile.name;
                    clientError.style.display = 'none';
                    previewZip(zipFile);
                } else {
                    clientError.style.display = 'block';
                    clientError.textContent = '❌ Por favor, selecione um arquivo ZIP.';
                    zipLabelText.textContent = ZIP_LABEL_DEFAULT;
                }
            }
        });
    }

    function isPdf(file) {
        if (!file) return false;
        const nameOk = (file.name || '').toLowerCase().endsWith('.pdf');
        const typeOk = (file.type || '').toLowerCase() === 'application/pdf';
        return nameOk || typeOk;
    }

    if (demoInput) {
        demoInput.addEventListener('change', function () {
            const file = demoInput.files && demoInput.files[0];
            if (file) {
                if (isPdf(file)) {
                    demoLabelText.textContent = file.name;
                    clientError.style.display = 'none';
                } else {
                    demoInput.value = '';
                    clientError.style.display = 'block';
                    clientError.textContent = '❌ Por favor, selecione um arquivo PDF.';
                    demoLabelText.textContent = 'Arraste e solte seu arquivo aqui ou clique para selecionar!';
                }
            } else {
                demoLabelText.textContent = 'Arraste e solte seu arquivo aqui ou clique para selecionar!';
            }
        });
    }

    if (reciboInput) {
        reciboInput.addEventListener('change', function () {
            const file = reciboInput.files && reciboInput.files[0];
            if (file) {
                if (isPdf(file)) {
                    reciboLabelText.textContent = file.name;
                    clientError.style.display = 'none';
                } else {
                    reciboInput.value = '';
                    clientError.style.display = 'block';
                    clientError.textContent = '❌ Por favor, selecione um arquivo PDF.';
                    reciboLabelText.textContent = 'Arraste e solte seu arquivo aqui ou clique para selecionar!';
                }
            } else {
                reciboLabelText.textContent = 'Arraste e solte seu arquivo aqui ou clique para selecionar!';
            }
        });
    }

    if (dragZone) {
        ['dragenter','dragover'].forEach(evt => {
            dragZone.addEventListener(evt, function (e) {
                e.preventDefault();
                e.stopPropagation();
                dragZone.classList.add('active');
            });
        });
        ['dragleave','drop'].forEach(evt => {
            dragZone.addEventListener(evt, function (e) {
                e.preventDefault();
                e.stopPropagation();
                dragZone.classList.remove('active');
            });
        });
        dragZone.addEventListener('drop', function (e) {
            const files = e.dataTransfer && e.dataTransfer.files ? e.dataTransfer.files : null;
            if (files && files.length > 0 && demoInput) {
                const pdfFile = Array.from(files).find(f => isPdf(f));
                if (pdfFile) {
                    const dt = new DataTransfer();
                    dt.items.add(pdfFile);
                    demoInput.files = dt.files;
                    demoLabelText.textContent = pdfFile.name;
                    clientError.style.display = 'none';
                } else {
                    clientError.style.display = 'block';
                    clientError.textContent = '❌ Por favor, selecione um arquivo PDF.';
                    demoLabelText.textContent = 'Arraste e solte seu arquivo aqui ou clique para selecionar!';
                }
            }
        });
    }

    if (dragZoneRecibo) {
        ['dragenter','dragover'].forEach(evt => {
            dragZoneRecibo.addEventListener(evt, function (e) {
                e.preventDefault();
                e.stopPropagation();
                dragZoneRecibo.classList.add('active');
            });
        });
        ['dragleave','drop'].forEach(evt => {
            dragZoneRecibo.addEventListener(evt, function (e) {
                e.preventDefault();
                e.stopPropagation();
                dragZoneRecibo.classList.remove('active');
            });
        });
        dragZoneRecibo.addEventListener('drop', function (e) {
            const files = e.dataTransfer && e.dataTransfer.files ? e.dataTransfer.files : null;
            if (files && files.length > 0 && reciboInput) {
                const pdfFile = Array.from(files).find(f => isPdf(f));
                if (pdfFile) {
                    const dt = new DataTransfer();
                    dt.items.add(pdfFile);
                    reciboInput.files = dt.files;
                    reciboLabelText.textContent = pdfFile.name;
                    clientError.style.display = 'none';
                } else {
                    clientError.style.display = 'block';
                    clientError.textContent = '❌ Por favor, selecione um arquivo PDF.';
                    reciboLabelText.textContent = 'Arraste e solte seu arquivo aqui ou clique para selecionar!';
                }
            }
        });
    }

    form.addEventListener('submit', function (e) {
        const mode = getSelectedMode();

        // Garante que o input do CAR esteja limpo antes de validar
        if (mode === 'car' && carInput) {
            carInput.value = cleanCarValue(carInput.value);
        }

        const carValue = carInput.value.trim();
        const zipSelectedEmpty = mode === 'zip' && (!zipInput.files || zipInput.files.length === 0);
        const carSelectedEmpty = mode === 'car' && carValue === '';
        const carHasDots = mode === 'car' && carInput.value.includes('.'); // Será false se limpo acima
        const carInvalidFormat = mode === 'car' && carValue !== '' && !CAR_REGEX.test(carValue);
        const demoInvalidPdf = mode === 'demostrativo' && demoInput && demoInput.files && demoInput.files.length > 0 && !isPdf(demoInput.files[0]);
        const reciboInvalidPdf = mode === 'recibo' && reciboInput && reciboInput.files && reciboInput.files.length > 0 && !isPdf(reciboInput.files[0]);

        if (zipSelectedEmpty || carSelectedEmpty || demoInvalidPdf || reciboInvalidPdf || carHasDots || carInvalidFormat) {
            e.preventDefault();
            clientError.style.display = 'block';
            if (carHasDots) {
                clientError.textContent = '❌ Não é permitido o uso de pontos no número do CAR.';
            } else if (carSelectedEmpty) {
                clientError.textContent = '❌ Por favor, informe o número do CAR.';
            } else if (carInvalidFormat) {
                clientError.textContent = '❌ Número do CAR inválido. Utilize o formato UF-0000000-XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX (sem pontos).';
            } else {
                clientError.textContent = (demoInvalidPdf || reciboInvalidPdf) ? '❌ Por favor, selecione um arquivo PDF.' : '❌ Por favor, envie um ZIP ou informe o número do CAR.';
            }
            return;
        }

        // Id desta análise: a página acompanha o andamento no servidor por ele.
        const jobInput = document.getElementById('job_id');
        const jobId = jobInput ? newJobId() : '';
        if (jobInput) jobInput.value = jobId;

        // Na página do mapa 3D a câmera vai buscar o imóvel enquanto o
        // servidor analisa; o loader fica transparente por cima (ver bases_3d.js).
        if (window.searchPropertyOnMap) {
            window.searchPropertyOnMap({
                mode: mode,
                car: carValue,
                file: zipInput.files && zipInput.files[0],
                jobId: jobId,
            });
        }
        if (loader) {
            loader.classList.add('visible');
        }
    });

    // Id aleatório em hexadecimal (`crypto.randomUUID` só existe em HTTPS).
    function newJobId() {
        const bytes = new Uint8Array(16);
        window.crypto.getRandomValues(bytes);
        return Array.from(bytes, function (b) { return b.toString(16).padStart(2, '0'); }).join('');
    }

    // "Buscas recentes": preenche o CAR e já mostra o imóvel no mapa.
    document.querySelectorAll('.recent-use').forEach(function (btn) {
        btn.addEventListener('click', function () {
            document.getElementById('mode_car').checked = true;
            applyMode();
            carInput.value = cleanCarValue(btn.dataset.car || '');
            scheduleCarPreview();
        });
    });

    // CAR já preenchido (a análise voltou com erro): mostra o imóvel de novo.
    if (carPrefilled) scheduleCarPreview();

    // Garante que o loader suma se o usuário clicar em "Voltar" (bfcache)
    window.addEventListener('pageshow', function (event) {
        if (loader) {
            loader.classList.remove('visible');
        }
    });
})();
