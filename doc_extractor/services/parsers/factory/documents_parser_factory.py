from doc_extractor.services.parsers.implement.parcer_document.statement_parser import StatementParser
from doc_extractor.services.parsers.implement.parcer_document.receipt_parser import ReceiptParser
from doc_extractor.services.parsers.implement.extract_text.extract_pdf_plumber import ExtractDocumentPdfPlumber
from doc_extractor.services.parsers.context.extract_data_context import DocumentDataContext
from doc_extractor.services.parsers.constans import TYPE_DOCUMENT

class DocumentsParserFactory:
   
    @staticmethod
    def create_parser(type_document: TYPE_DOCUMENT):
        if type_document == TYPE_DOCUMENT.STATEMENT:
            return StatementParser()
        elif type_document == TYPE_DOCUMENT.RECEIPT:
            return ReceiptParser()
        else:
            raise ValueError(f"Tipo de documento desconhecido: {type_document}")