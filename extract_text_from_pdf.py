import pdfplumber

def extrair_texto_pdf_pdfplumber(caminho_arquivo):
    """
    Extrai texto de um PDF usando pdfplumber (preserva melhor o layout).
    
    Args:
        caminho_arquivo (str): Caminho para o arquivo PDF
    
    Returns:
        str: Texto extraído do PDF
    """
    try:
        texto_total = ""
        
        with pdfplumber.open(caminho_arquivo) as pdf:
            for pagina_num, pagina in enumerate(pdf.pages, 1):
                #print(f"Processando página {pagina_num} de {len(pdf.pages)}...")
                texto = pagina.extract_text()
                texto_total += f"\n--- Página {pagina_num} ---\n{texto}\n"
        
        return texto_total
        
    except FileNotFoundError:
        print(f"Erro: Arquivo '{caminho_arquivo}' não encontrado.")
        return ""
    except Exception as e:
        print(f"Erro ao processar o PDF: {str(e)}")
        return ""


