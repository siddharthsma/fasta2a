# Library imports
from typing import Dict, Any, Optional, List

# Local imports
from smarta2a.state_stores.base_state_store import BaseStateStore
from smarta2a.common.types import StateData, Message

class InMemoryStateStore(BaseStateStore):
    def __init__(self):
        self.states: Dict[str, StateData] = {}
    
    def create_state(self, session_id: Optional[str] = None) -> StateData:
        if session_id:
            return StateData(session_id=session_id, history=[], metadata={})
        else:
            return StateData(session_id=str(uuid.uuid4()), history=[], metadata={})
    
    def get_state(self, session_id: str) -> Optional[StateData]:
        return self.states.get(session_id)
    
    def update_state(self, session_id: str, history: List[Message], metadata: Dict[str, Any]):
        self.states[session_id] = StateData(
            history=history,
            metadata=metadata
        )
    
    def delete_state(self, session_id: str):
        if session_id in self.states:
            del self.states[session_id]