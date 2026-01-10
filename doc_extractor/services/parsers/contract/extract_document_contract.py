from abc import ABC, abstractmethod

class ExtractDocumentBase(ABC):

    @abstractmethod
    def extract_text(self, pdf_path: str, deduplicate: bool = False, page: int = None) -> str:
        pass

    @staticmethod
    def deduplicate(text: str) -> str:
        if not text:
            return text

        result = []
        for line in text.splitlines():
            n = len(line)
            if n < 2:
                result.append(line)
                continue

            total_pairs = n - 1
            duplicated_pairs = sum(
                1 for i in range(total_pairs) if line[i] == line[i+1]
            )

            if total_pairs > 0 and (duplicated_pairs / total_pairs) > 0.4:
                buffer = []
                i = 0
                while i < n:
                    if i + 1 < n and line[i] == line[i + 1]:
                        buffer.append(line[i])
                        i += 2
                    else:
                        buffer.append(line[i])
                        i += 1
                result.append("".join(buffer))
            else:
                result.append(line)

        return "\n".join(result)
