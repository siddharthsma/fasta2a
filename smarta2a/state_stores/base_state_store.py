# Library imports
from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any

# Local imports
from smarta2a.utils.types import StateData, Message

class BaseStateStore(ABC):
    
    @abstractmethod
    async def get_state(self, session_id: str) -> Optional[StateData]:
        pass
    
    @abstractmethod
    async def update_state(self, session_id: str, state_data: StateData) -> None:
        pass
    
    @abstractmethod
    async def delete_state(self, session_id: str) -> None:
        pass