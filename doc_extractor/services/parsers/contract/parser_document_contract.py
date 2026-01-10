import dataclasses
from abc import ABC, abstractmethod
from doc_extractor.services.parsers.contract.extract_document_contract import ExtractDocumentBase

class ParserDocumentBase(ABC):

    @abstractmethod
    def parse(self, text: str) -> dataclasses.dataclass:
        pass