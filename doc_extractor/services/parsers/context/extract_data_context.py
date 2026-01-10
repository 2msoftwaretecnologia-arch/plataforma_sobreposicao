from typing import Any
from doc_extractor.services.parsers.contract.extract_document_contract import ExtractDocumentBase
from doc_extractor.services.parsers.contract.parser_document_contract import ParserDocumentBase

class DocumentDataContext:
    def __init__(self, extractor: ExtractDocumentBase, parser: ParserDocumentBase):
        self.extractor = extractor
        self.parser = parser
    
    def extract_data(self, pdf_path: str, deduplicate: bool = False, page: int = None) -> Any:
        text = self.extractor.extract_text(pdf_path, deduplicate, page)
        return self.parser.parse(text)
