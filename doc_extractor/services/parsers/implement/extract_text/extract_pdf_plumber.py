import pdfplumber
from doc_extractor.services.parsers.contract.extract_document_contract import ExtractDocumentBase

class ExtractDocumentPdfPlumber(ExtractDocumentBase):
    def extract_text(self, pdf_path: str, deduplicate: bool = False, page: int = None) -> str:
        """
        Extrai texto de um PDF usando pdfplumber (preserva melhor o layout).
        
        Args:
            pdf_path (str): Caminho para o arquivo PDF
            deduplicate (bool): Se True, remove linhas duplicadas (padrão: False)
            page (int): Número da página a extrair (padrão: None, extrai todas)
        
        Returns:
            str: Texto extraído do PDF
        """
        try:
            with pdfplumber.open(pdf_path) as pdf:
                if page is not None:
                    if page < 1 or page > len(pdf.pages):
                        return ""
                    p = pdf.pages[page - 1]
                    texto = self.deduplicate(p.extract_text() or "") if deduplicate else (p.extract_text() or "")
                    return texto

                texto_total = ""
                for pagina_num, p in enumerate(pdf.pages, 1):
                    texto = self.deduplicate(p.extract_text() or "") if deduplicate else (p.extract_text() or "")
                    texto_total += f"\n--- Página {pagina_num} ---\n{texto}\n"
                return texto_total
            
        except FileNotFoundError:
            print(f"Erro: Arquivo '{pdf_path}' não encontrado.")
            return ""
        except Exception as e:
            print(f"Erro ao processar o PDF: {str(e)}")
            return ""
