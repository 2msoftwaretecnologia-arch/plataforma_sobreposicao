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
    const groupKml = document.getElementById('group_kml');
    const kmlInput = document.getElementById('kml_file');
    const kmlLabelText = document.getElementById('kml_label_text');
    const groupCoord = document.getElementById('group_coord');
    const coordInput = document.getElementById('coord_input');
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

    // Cada modo mostra só o seu grupo e só o seu campo é obrigatório.
    const modeGroups = {
        zip: [groupZip, zipInput],
        kml: [groupKml, kmlInput],
        coord: [groupCoord, coordInput],
        car: [groupCar, carInput],
        demostrativo: [groupDemo, demoInput],
        recibo: [groupRecibo, reciboInput],
    };

    function applyMode() {
        const mode = getSelectedMode();
        Object.keys(modeGroups).forEach(function (key) {
            const group = modeGroups[key][0];
            const input = modeGroups[key][1];
            if (group) group.style.display = key === mode ? '' : 'none';
            if (input) input.required = key === mode;
        });
        clientError.style.display = 'none';
    }

    modeInputs.forEach((el) => el.addEventListener('change', applyMode));

    const carPrefilled = (carInput.value || '').trim().length > 0;
    const coordPrefilled = !!coordInput && coordInput.value.trim().length > 0;
    if (coordPrefilled) {
        document.getElementById('mode_coord').checked = true;
    } else if (carPrefilled) {
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
    const kmlPreview = document.getElementById('kml_preview');
    const coordPreview = document.getElementById('coord_preview');
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

    function kmlNote(t) {
        if (!t) return ['', ''];
        if (t.status === 'found') {
            return ['ok', 'Área lida do KML: ' + fmtHa(t.area_ha) + (t.polygons > 1 ? ' (' + t.polygons + ' polígonos)' : '')];
        }
        if (t.status === 'outside') {
            return ['warn', 'A área fica fora do Tocantins: as bases da análise cobrem só o estado.'];
        }
        if (t.status === 'no_polygon') {
            return ['warn', 'O arquivo não tem nenhum polígono: a análise precisa da área desenhada, não só de pontos ou linhas.'];
        }
        return ['warn', 'Não deu para ler o KML aqui no navegador; a análise ainda pode ser feita.'];
    }

    function coordNote(t) {
        if (!t) return ['', ''];
        if (t.status === 'found' && t.car) {
            return ['ok', ['Ponto no imóvel ' + t.car, t.city && t.city.nome, t.area_ha ? fmtHa(t.area_ha) : '',
                t.cars > 1 ? 'cai em ' + t.cars + ' CARs; será analisado o maior' : ''].filter(Boolean).join(' · ')];
        }
        if (t.status === 'found') {
            return ['ok', 'Área dos vértices: ' + fmtHa(t.area_ha) + ' (' + t.vertices + ' vértices)'];
        }
        if (t.status === 'no_property') {
            return ['warn', 'O ponto não cai em nenhum imóvel do SICAR. Confira a coordenada ou informe os vértices da área.'];
        }
        if (t.status === 'outside') {
            return ['warn', 'A área fica fora do Tocantins: confira as coordenadas. As bases da análise cobrem só o estado.'];
        }
        return ['warn', t.message || 'Não deu para ler as coordenadas.'];
    }

    let coordPreviewTimer = null;

    function scheduleCoordPreview() {
        if (!canPreview || !coordInput) return;
        clearTimeout(coordPreviewTimer);
        const text = coordInput.value;
        coordPreviewTimer = setTimeout(function () {
            if (!text.trim()) {
                showNote(coordPreview);
                window.clearPropertyPreview();
                return;
            }
            window.previewPropertyOnMap({ mode: 'coord', text: text }).then(function (t) {
                if (coordInput.value !== text) return;
                const note = coordNote(t);
                showNote(coordPreview, note[0], note[1]);
            });
        }, 500);
    }

    if (coordInput) {
        coordInput.addEventListener('input', function () {
            clientError.style.display = 'none';
            scheduleCoordPreview();
        });
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

    function previewKml(file) {
        if (!canPreview) return;
        if (!file) {
            showNote(kmlPreview);
            window.clearPropertyPreview();
            return;
        }
        showNote(kmlPreview, 'loading', 'Lendo o KML...');
        window.previewPropertyOnMap({ mode: 'kml', file: file }).then(function (t) {
            if (!kmlInput.files || kmlInput.files[0] !== file) return;
            const note = kmlNote(t);
            showNote(kmlPreview, note[0], note[1]);
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

    const KML_LABEL_DEFAULT = 'Arraste e solte o KML aqui ou clique para selecionar!';
    const dragZoneKml = groupKml ? groupKml.querySelector('.drag-zone') : null;

    function isKml(file) {
        return !!file && /\.(kml|kmz)$/i.test(file.name || '');
    }

    function setKmlFile(file) {
        if (file && !isKml(file)) {
            kmlInput.value = '';
            clientError.style.display = 'block';
            clientError.textContent = '❌ Por favor, selecione um arquivo KML ou KMZ.';
            file = null;
        } else {
            clientError.style.display = 'none';
        }
        kmlLabelText.textContent = file ? file.name : KML_LABEL_DEFAULT;
        previewKml(file);
    }

    if (kmlInput) {
        kmlInput.addEventListener('change', function () {
            setKmlFile(kmlInput.files && kmlInput.files[0]);
        });
    }

    if (dragZoneKml) {
        ['dragenter','dragover'].forEach(evt => {
            dragZoneKml.addEventListener(evt, function (e) {
                e.preventDefault();
                e.stopPropagation();
                dragZoneKml.classList.add('active');
            });
        });
        ['dragleave','drop'].forEach(evt => {
            dragZoneKml.addEventListener(evt, function (e) {
                e.preventDefault();
                e.stopPropagation();
                dragZoneKml.classList.remove('active');
            });
        });
        dragZoneKml.addEventListener('drop', function (e) {
            const files = e.dataTransfer && e.dataTransfer.files ? Array.from(e.dataTransfer.files) : [];
            if (!files.length) return;
            const kmlFile = files.find(f => isKml(f)) || files[0];
            if (isKml(kmlFile)) {
                const dt = new DataTransfer();
                dt.items.add(kmlFile);
                kmlInput.files = dt.files;
            }
            setKmlFile(kmlFile);
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
        const kmlSelectedEmpty = mode === 'kml' && (!kmlInput.files || kmlInput.files.length === 0);
        const coordEmpty = mode === 'coord' && coordInput.value.trim() === '';
        const carSelectedEmpty = mode === 'car' && carValue === '';
        const carHasDots = mode === 'car' && carInput.value.includes('.'); // Será false se limpo acima
        const carInvalidFormat = mode === 'car' && carValue !== '' && !CAR_REGEX.test(carValue);
        const demoInvalidPdf = mode === 'demostrativo' && demoInput && demoInput.files && demoInput.files.length > 0 && !isPdf(demoInput.files[0]);
        const reciboInvalidPdf = mode === 'recibo' && reciboInput && reciboInput.files && reciboInput.files.length > 0 && !isPdf(reciboInput.files[0]);

        if (zipSelectedEmpty || kmlSelectedEmpty || coordEmpty || carSelectedEmpty || demoInvalidPdf || reciboInvalidPdf || carHasDots || carInvalidFormat) {
            e.preventDefault();
            clientError.style.display = 'block';
            if (carHasDots) {
                clientError.textContent = '❌ Não é permitido o uso de pontos no número do CAR.';
            } else if (coordEmpty) {
                clientError.textContent = '❌ Por favor, informe as coordenadas.';
            } else if (kmlSelectedEmpty) {
                clientError.textContent = '❌ Por favor, envie um arquivo KML ou KMZ.';
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
                text: coordInput ? coordInput.value : '',
                file: mode === 'kml' ? kmlInput.files && kmlInput.files[0] : zipInput.files && zipInput.files[0],
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
    if (coordPrefilled) scheduleCoordPreview();
    else if (carPrefilled) scheduleCarPreview();

    // Garante que o loader suma se o usuário clicar em "Voltar" (bfcache)
    window.addEventListener('pageshow', function (event) {
        if (loader) {
            loader.classList.remove('visible');
        }
    });
})();
