# Library imports
from typing import Optional, Dict, Any
from uuid import uuid4

# Local imports
from smarta2a.state_stores.base_state_store import BaseStateStore
from smarta2a.history_update_strategies.history_update_strategy import HistoryUpdateStrategy
from smarta2a.utils.types import Message, StateData, Task, TaskStatus, TaskState

class StateManager:
    def __init__(self, store: Optional[BaseStateStore], history_strategy: HistoryUpdateStrategy):
        self.store = store
        self.strategy = history_strategy

    def init_or_get(self, task_id: str, session_id: str, message: Message, metadata: Dict[str, Any]) -> StateData:
        if not self.store:
            return StateData(
                task_id=task_id,
                task=Task(
                    id=task_id,
                    sessionId=session_id,
                    status=TaskStatus(state=TaskState.WORKING),
                    history=[message],
                    metadata=metadata or {}
                ),
                context_history=[message],
            )
        existing = self.store.get_state(task_id) or StateData(
            task_id=task_id,
            task=Task(
                id=task_id,
                sessionId=session_id,
                status=TaskStatus(state=TaskState.WORKING),
                history=[message],
                metadata=metadata or {}
            ),
            context_history=[message],
        )
        # Update task history (always append)
        existing.task.history.append(message)
        # Update context history
        existing.context_history.append(message)

        self.store.update_state(task_id, existing)
        return existing

    def update(self, state: StateData):
        if self.store:
            self.store.update_state(state.task_id, state)
    
    def get_store(self) -> Optional[BaseStateStore]:
        return self.store
    
    def get_strategy(self) -> HistoryUpdateStrategy:
        return self.strategy
    