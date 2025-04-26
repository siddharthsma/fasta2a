# Library imports
import pytest
from fastapi.testclient import TestClient
from typing import List, Dict, Any, Optional
import uuid

# Local imports
from smarta2a.server import SmartA2A
from smarta2a.common.types import Message, StateData, SendTaskRequest
from smarta2a.state_stores import BaseStateStore

class AppendStrategy:
    """Default append behavior"""
    def update_history(self, existing_history: List[Message], new_messages: List[Message]) -> List[Message]:
        return existing_history + new_messages
    
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


# Add async teardown for server
@pytest.fixture(autouse=True)
async def cleanup():
    yield
    # Force close all app connections
    import anyio
    anyio.run(anyio.sleep, 0)  # Flush pending tasks


def test_send_task_with_history_strategy_and_state_store(client, a2a_server):
    state_store = InMemoryStateStore()
    history_update_strategy = AppendStrategy()

    state_store.create_state()
    a2a_server = SmartA2A("test-server", state_store=state_store, history_update_strategy=history_update_strategy)
    # Register task handler correctly
    @a2a_server.on_send_task()
    def handle_task(request: SendTaskRequest, state: StateData):
        return "Hello, World!"

    # Send valid request with required fields
    response = client.post("/", json={
        "jsonrpc": "2.0",
        "id": "1",
        "method": "tasks/send",
        "params": {
            "id": "test-task-1",
            "message": {
                "role": "user",
                "parts": [{"type": "text", "text": "Test message"}]
            }
        }
    })

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == "1"
    assert data["result"]["status"]["state"] == "completed"
    assert len(data["result"]["artifacts"]) == 1
    assert data["result"]["artifacts"][0]["parts"][0]["text"] == "Hello, World!"
    assert data["result"]["sessionId"]  # Should be generated
    assert len(data["result"]["history"]) == 2
    assert state_store.get_state(data["result"]["sessionId"]).history == [
        Message(role="user", parts=[{"type": "text", "text": "Test message"}]),
        Message(role="agent", parts=[{"type": "text", "text": "Hello, World!"}])
    ]