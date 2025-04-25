# Library imports
from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any

# Local imports
from smarta2a.common.types import StateData, Message

class BaseStateStore(ABC):
    @abstractmethod
    async def create_state(self) -> StateData:
        pass
    
    @abstractmethod
    async def get_state(self, session_id: str) -> Optional[StateData]:
        pass
    
    @abstractmethod
    async def update_state(self, session_id: str, history: List[Message], metadata: Dict[str, Any]) -> None:
        pass
    
    @abstractmethod
    async def delete_state(self, session_id: str) -> None:
        pass