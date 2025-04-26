# Library imports
from typing import Dict, Any, Optional, List
import uuid

# Local imports
from smarta2a.state_stores.base_state_store import BaseStateStore
from smarta2a.common.types import StateData, Message

class InMemoryStateStore(BaseStateStore):
    def __init__(self):
        self.states: Dict[str, StateData] = {}
    
    def create_state(self, session_id: Optional[str] = None) -> StateData:
        if session_id:
            return StateData(sessionId=session_id, history=[], metadata={})
        else:
            return StateData(sessionId=str(uuid.uuid4()), history=[], metadata={})
    
    def get_state(self, session_id: str) -> Optional[StateData]:
        return self.states.get(session_id)
    
    def update_state(self, session_id: str, state_data: StateData):
        self.states[session_id] = state_data
    
    def delete_state(self, session_id: str):
        if session_id in self.states:
            del self.states[session_id]