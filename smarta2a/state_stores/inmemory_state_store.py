# Library imports
from typing import Dict, Any, Optional, List
import uuid

# Local imports
from smarta2a.state_stores.base_state_store import BaseStateStore
from smarta2a.utils.types import StateData, Message

class InMemoryStateStore(BaseStateStore):
    def __init__(self):
        self.states: Dict[str, StateData] = {}
    
    def initialize_state(self, state_data: StateData) -> None:
        self.states[state_data.task_id] = state_data
    
    def get_state(self, task_id: str) -> Optional[StateData]:
        return self.states.get(task_id)
    
    def update_state(self, task_id: str, state_data: StateData):
        self.states[task_id] = state_data
    
    def delete_state(self, task_id: str):
        if task_id in self.states:
            del self.states[task_id]
    
    def get_all_tasks(self, fields: Optional[str] = None) -> List[Dict[str, Any]]:
        all_tasks = [state_data.task.model_dump() for state_data in self.states.values()]
        if fields:
            requested_fields = fields.split(",")
            fields_filtered_tasks = [
                {field: task[field] for field in requested_fields if field in task}
                for task in all_tasks
            ]
            return fields_filtered_tasks
        return all_tasks