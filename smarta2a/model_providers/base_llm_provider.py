# Library imports
from abc import ABC, abstractmethod
from typing import AsyncGenerator, List

# Local imports
from smarta2a.utils.types import Message

class BaseLLMProvider(ABC):
    @abstractmethod
    async def generate(self, messages: List[Message], **kwargs) -> str:
        pass
    
    @abstractmethod
    async def generate_stream(self, messages: List[Message], **kwargs) -> AsyncGenerator[str, None]:
        pass