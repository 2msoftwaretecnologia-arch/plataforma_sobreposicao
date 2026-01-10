import pdfplumber

def _desduplicar_pares(texto: str) -> str:
    if not texto:
        return texto
    resultado = []
    for linha in texto.splitlines():
        n = len(linha)
        if n < 2:
            resultado.append(linha)
            continue
        total_pairs = n - 1
        dup_pairs = 0
        for i in range(total_pairs):
            if linha[i] == linha[i + 1]:
                dup_pairs += 1
        if total_pairs > 0 and (dup_pairs / total_pairs) > 0.4:
            out = []
            i = 0
            while i < n:
                if i + 1 < n and linha[i] == linha[i + 1]:
                    out.append(linha[i])
                    i += 2
                else:
                    out.append(linha[i])
                    i += 1
            resultado.append("".join(out))
        else:
            resultado.append(linha)
    return "\n".join(resultado)

def extrair_texto_sem_duplicacao(page):
    bruto = page.extract_text() or ""
    return _desduplicar_pares(bruto)

def extrair_texto_pdf_pdfplumber(caminho_arquivo, pagina=None, deduplicar=False):
    """
    Extrai texto de um PDF usando pdfplumber (preserva melhor o layout).
    
    Args:
        caminho_arquivo (str): Caminho para o arquivo PDF
    
    Returns:
        str: Texto extraído do PDF
    """
    try:
        with pdfplumber.open(caminho_arquivo) as pdf:
            if pagina is not None:
                if pagina < 1 or pagina > len(pdf.pages):
                    return ""
                p = pdf.pages[pagina - 1]
                texto = extrair_texto_sem_duplicacao(p) if deduplicar else (p.extract_text() or "")
                return texto

            texto_total = ""
            for pagina_num, p in enumerate(pdf.pages, 1):
                texto = extrair_texto_sem_duplicacao(p) if deduplicar else (p.extract_text() or "")
                texto_total += f"\n--- Página {pagina_num} ---\n{texto}\n"
            return texto_total
        
    except FileNotFoundError:
        print(f"Erro: Arquivo '{caminho_arquivo}' não encontrado.")
        return ""
    except Exception as e:
        print(f"Erro ao processar o PDF: {str(e)}")
        return ""
