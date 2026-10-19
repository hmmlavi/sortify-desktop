from abc import ABC, abstractmethod


class AIProviderError(Exception): pass

class BaseProvider(ABC):
    @abstractmethod
    def suggest_name(self, filename: str, extension: str, content: str, content_kind: str, image_path=None) -> dict:
        raise NotImplementedError
