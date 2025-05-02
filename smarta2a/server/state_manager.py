# Library imports
from typing import Optional, Dict, Any
from uuid import uuid4

# Local imports
from smarta2a.state_stores.base_state_store import BaseStateStore
from smarta2a.history_update_strategies.history_update_strategy import HistoryUpdateStrategy
from smarta2a.utils.types import Message, StateData

class StateManager:
    def __init__(self, store: Optional[BaseStateStore], history_strategy: HistoryUpdateStrategy):
        self.store = store
        self.strategy = history_strategy

    def init_or_get(self, session_id: Optional[str], message: Message, metadata: Dict[str, Any]) -> StateData:
        sid = session_id or str(uuid4())
        if not self.store:
            return StateData(sessionId=sid, history=[message], metadata=metadata or {})
        existing = self.store.get_state(sid) or StateData(sessionId=sid, history=[], metadata={})
        existing.history.append(message)
        existing.metadata = {**(existing.metadata or {}), **(metadata or {})}
        self.store.update_state(sid, existing)
        return existing

    def update(self, state: StateData):
        if self.store:
            self.store.update_state(state.sessionId, state)
    
    def get_store(self) -> Optional[BaseStateStore]:
        return self.store
    
    def get_strategy(self) -> HistoryUpdateStrategy:
        return self.strategy
    