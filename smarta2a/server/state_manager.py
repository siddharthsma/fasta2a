# Library imports
from typing import Optional, Dict, Any
from uuid import uuid4

# Local imports
from smarta2a.state_stores.base_state_store import BaseStateStore
from smarta2a.history_update_strategies.history_update_strategy import HistoryUpdateStrategy
from smarta2a.utils.types import Message, StateData, Task, TaskStatus, TaskState, PushNotificationConfig

class StateManager:
    def __init__(self, store: BaseStateStore, history_strategy: HistoryUpdateStrategy):
        self.store = store
        self.strategy = history_strategy
    
    def initialize_state(
        self,
        task_id: str,
        session_id: str,
        message: Message,
        metadata: Optional[Dict[str, Any]] = None,
        push_notification_config: Optional[PushNotificationConfig] = None
    ) -> StateData:
        """
        Build a fresh StateData and persist it.
        """
        initial_task = Task(
            id=task_id,
            sessionId=session_id,
            status=TaskStatus(state=TaskState.WORKING),
            artifacts=[],
            history=[message],
            metadata=metadata or {}
        )
        state = StateData(
            task_id=task_id,
            task=initial_task,
            context_history=[message],
            push_notification_config=push_notification_config
        )
        self.store.initialize_state(state)
        return state

    def get_or_initialize_state(
        self,
        task_id: str,
        session_id: str,
        message: Message,
        metadata: Optional[Dict[str, Any]] = None,
        push_notification_config: Optional[PushNotificationConfig] = None
    ) -> StateData:
        """
        Fetch existing StateData, or initialize & persist a new one.
        """
        existing = self.store.get_state(task_id)
        if existing:
            return existing
        return self.initialize_state(
            task_id, session_id, message, metadata, push_notification_config
        )
    
    def get_state(self, task_id: str) -> Optional[StateData]:
        if not self.store:
            return None
        return self.store.get_state(task_id)

    def update(self, state: StateData):
        if self.store:
            self.store.update_state(state.task_id, state)
    
    def get_store(self) -> Optional[BaseStateStore]:
        return self.store
    
    def get_history_strategy(self) -> HistoryUpdateStrategy:
        return self.strategy
    