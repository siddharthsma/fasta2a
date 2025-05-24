# Library imports
from abc import ABC, abstractmethod
from typing import Optional

class BaseFileStore(ABC):
    """Separate interface for file operations"""
    
    @abstractmethod
    async def upload(
        self,
        content: bytes,
        task_id: str,
        filename: Optional[str] = None
    ) -> str:
        pass

    @abstractmethod
    async def download(self, uri: str) -> bytes:
        pass

    @abstractmethod
    async def delete_for_task(self, task_id: str):
        pass

    @abstractmethod
    async def list_files(self, task_id: str) -> list[str]:
        pass