# Library imports
from abc import ABC, abstractmethod
from typing import AsyncGenerator, List

# Local imports
from smarta2a.utils.types import StateData

class BaseLLMProvider(ABC):
    @abstractmethod
    async def generate(self, state: StateData, **kwargs) -> str:
        pass
    
    @abstractmethod
    async def generate_stream(self, state: StateData, **kwargs) -> AsyncGenerator[str, None]:
        pass