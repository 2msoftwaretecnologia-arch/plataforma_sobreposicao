from doc_extractor.services.parsers.implement.parcer_document.statement_parser import StatementParser
from doc_extractor.services.parsers.implement.parcer_document.receipt_parser import ReceiptParser
from doc_extractor.services.parsers.implement.extract_text.extract_pdf_plumber import ExtractDocumentPdfPlumber
from doc_extractor.services.parsers.context.extract_data_context import DocumentDataContext
from doc_extractor.services.parsers.constants import TypeDocument

class DocumentsParserFactory:
   
    @staticmethod
    def create_parser(type_document: TypeDocument):
        if type_document == TypeDocument.STATEMENT:
            return StatementParser()
        elif type_document == TypeDocument.RECEIPT:
            return ReceiptParser()
        else:
            raise ValueError(f"Tipo de documento desconhecido: {type_document}")