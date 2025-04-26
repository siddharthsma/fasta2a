# Library imports
from abc import ABC, abstractmethod
from typing import AsyncGenerator

# Local imports
from smarta2a.common.types import Message

class BaseLLMProvider(ABC):
    @abstractmethod
    async def generate(self, messages: list[Message], **kwargs) -> str:
        pass
    
    @abstractmethod
    async def generate_stream(self, messages: list[Message], **kwargs) -> AsyncGenerator[str, None]:
        pass