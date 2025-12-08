(function () {
    const groupZip = document.getElementById('group_zip');
    const groupCar = document.getElementById('group_car');
    const groupDemo = document.getElementById('group_demo');
    const zipInput = document.getElementById('zip_file');
    const zipLabelText = document.getElementById('zip_label_text');
    const carInput = document.getElementById('car_input');
    const demoInput = document.getElementById('demo_file');
    const demoLabelText = document.getElementById('demo_label_text');
    const dragZone = groupDemo ? groupDemo.querySelector('.drag-zone') : null;
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
            carInput.required = false;
            zipInput.required = true;
        } else if (mode === 'car') {
            groupZip.style.display = 'none';
            groupCar.style.display = '';
            if (groupDemo) groupDemo.style.display = 'none';
            zipInput.required = false;
            carInput.required = true;
        } else {
            groupZip.style.display = 'none';
            groupCar.style.display = 'none';
            if (groupDemo) groupDemo.style.display = '';
            zipInput.required = false;
            carInput.required = false;
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

    zipInput.addEventListener('change', function () {
        if (zipInput.files && zipInput.files.length > 0) {
            zipLabelText.textContent = zipInput.files[0].name;
            clientError.style.display = 'none';
        } else {
            zipLabelText.textContent = 'Selecionar arquivo ZIP';
        }
    });

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

    form.addEventListener('submit', function (e) {
        const mode = getSelectedMode();
        const zipSelectedEmpty = mode === 'zip' && (!zipInput.files || zipInput.files.length === 0);
        const carSelectedEmpty = mode === 'car' && (carInput.value.trim() === '');
        const demoInvalidPdf = mode === 'demostrativo' && demoInput && demoInput.files && demoInput.files.length > 0 && !isPdf(demoInput.files[0]);

        if (zipSelectedEmpty || carSelectedEmpty || demoInvalidPdf) {
            e.preventDefault();
            clientError.style.display = 'block';
            clientError.textContent = demoInvalidPdf ? '❌ Por favor, selecione um arquivo PDF.' : '❌ Por favor, envie um ZIP ou informe o número do CAR.';
            return;
        }

        if (loader) {
            loader.classList.add('visible');
        }
    });
})();
