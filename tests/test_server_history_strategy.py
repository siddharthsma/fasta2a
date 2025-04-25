# Library imports
import pytest
from fastapi.testclient import TestClient
from uuid import uuid4
from typing import List, Optional, Dict, Any

# Local imports
from smarta2a.server import SmartA2A
from smarta2a.common.types import (
    Message, Task, TaskState, SendTaskRequest, StateData,
    Artifact, TextPart, TaskArtifactUpdateEvent
)
from smarta2a.state_stores import BaseStateStore
from smarta2a.history_update_strategies import HistoryUpdateStrategy

# Fixtures
class MemoryStateStore(BaseStateStore):
    def __init__(self):
        self.states: Dict[str, StateData] = {}
    
    def create_state(self) -> StateData:
        return StateData(history=[], metadata={})
    
    def get_state(self, session_id: str) -> Optional[StateData]:
        return self.states.get(session_id)
    
    def update_state(self, session_id: str, history: List[Message], metadata: Dict[str, Any]) -> None:
        self.states[session_id] = StateData(history=history, metadata=metadata)
    
    def delete_state(self, session_id: str) -> None:
        if session_id in self.states:
            del self.states[session_id]

class AppendStrategy(HistoryUpdateStrategy):
    def update_history(self, existing: List[Message], new: List[Message]) -> List[Message]:
        return existing + new

class OverwriteStrategy(HistoryUpdateStrategy):
    def update_history(self, existing: List[Message], new: List[Message]) -> List[Message]:
        return new

@pytest.fixture
def memory_state_store():
    return MemoryStateStore()

@pytest.fixture
def append_strategy():
    return AppendStrategy()

@pytest.fixture
def overwrite_strategy():
    return OverwriteStrategy()

@pytest.fixture(params=["with_store", "without_store"])
def a2a_app(request, append_strategy, memory_state_store):
    if request.param == "with_store":
        return SmartA2A("TestApp", state_store=memory_state_store, history_strategy=append_strategy)
    return SmartA2A("TestApp", history_strategy=append_strategy)

# Test Cases
def test_append_strategy(a2a_app, memory_state_store):
    # Setup handler
    @a2a_app.on_send_task()
    def handler(request: SendTaskRequest):
        return Task(
            id=request.params.id,
            artifacts=[Artifact(parts=[TextPart(text="Response")])]
        )

    # First request
    session_id = str(uuid4())
    request = {
        "id": "1",
        "params": {
            "id": "task1",
            "message": Message(role="user", parts=[TextPart(text="Hello")]),
            "sessionId": session_id
        }
    }
    
    response = a2a_app._handle_send_task(request)
    task = response.result
    assert len(task.history) == 2  # User + agent
    assert task.history[0].parts[0].text == "Hello"
    assert task.history[1].parts[0].text == "Response"

    # Verify state store if used
    if a2a_app.state_store:
        state = memory_state_store.get_state(session_id)
        assert len(state.history) == 2
        assert state.history == task.history

def test_overwrite_strategy(memory_state_store):
    a2a = SmartA2A("TestApp", state_store=memory_state_store, history_strategy=OverwriteStrategy())
    
    @a2a.on_send_task()
    def handler(request):
        return Task(
            id=request.params.id,
            artifacts=[Artifact(parts=[TextPart(text="Response")])]
        )

    # First request
    request1 = {
        "id": "1",
        "params": {
            "id": "task1",
            "message": Message(role="user", parts=[TextPart(text="Msg1")])
        }
    }
    response1 = a2a._handle_send_task(request1)
    assert len(response1.result.history) == 2
    
    # Second request
    request2 = {
        "id": "2",
        "params": {
            "id": "task2",
            "message": Message(role="user", parts=[TextPart(text="Msg2")])
        }
    }
    response2 = a2a._handle_send_task(request2)
    assert len(response2.result.history) == 2  # Overwritten, not 4

def test_state_store_persistence(memory_state_store, append_strategy):
    a2a = SmartA2A("TestApp", state_store=memory_state_store, history_strategy=append_strategy)
    
    @a2a.on_send_task()
    def handler(request):
        return Task(
            id=request.params.id,
            artifacts=[Artifact(parts=[TextPart(text="Response")])]
        )

    session_id = str(uuid4())
    request = {
        "params": {
            "id": "task1",
            "message": Message(role="user", parts=[TextPart(text="Hello")]),
            "sessionId": session_id
        }
    }
    
    # First call
    a2a._handle_send_task(request)
    
    # Second call
    response = a2a._handle_send_task(request)
    task = response.result
    assert len(task.history) == 4  # 2 messages per request

def test_no_state_store(append_strategy):
    a2a = SmartA2A("TestApp", history_strategy=append_strategy)
    
    @a2a.on_send_task()
    def handler(request):
        return Task(
            id=request.params.id,
            artifacts=[Artifact(parts=[TextPart(text="Response")])]
        )

    request = {
        "params": {
            "id": "task1",
            "message": Message(role="user", parts=[TextPart(text="Hello")])
        }
    }
    
    response1 = a2a._handle_send_task(request)
    response2 = a2a._handle_send_task(request)
    
    # Each request should have independent history
    assert len(response1.result.history) == 2
    assert len(response2.result.history) == 2  # Not 4

def test_streaming_history_updates(memory_state_store):
    a2a = SmartA2A("TestApp", state_store=memory_state_store, history_strategy=AppendStrategy())
    
    @a2a.on_send_subscribe_task()
    async def handler(request):
        yield TaskArtifactUpdateEvent(
            id="1",
            artifact=Artifact(parts=[TextPart(text="Part1")])
        )
        yield TaskArtifactUpdateEvent(
            id="2",
            artifact=Artifact(parts=[TextPart(text="Part2")])
        )

    client = TestClient(a2a.app)
    response = client.post("/", json={
        "method": "tasks/sendSubscribe",
        "params": {
            "message": Message(role="user", parts=[TextPart(text="Question")])
        }
    })
    
    # Verify state after streaming
    session_id = response.json()["id"]
    state = memory_state_store.get_state(session_id)
    assert len(state.history) == 3  # User + 2 agent messages

def test_metadata_merging(memory_state_store):
    a2a = SmartA2A("TestApp", state_store=memory_state_store)
    
    @a2a.on_send_task()
    def handler(request):
        return Task(
            metadata={"source": "handler"},
            artifacts=[Artifact(parts=[TextPart(text="Response")])]
        )

    request = {
        "params": {
            "metadata": {"user": "test"},
            "message": Message(role="user", parts=[TextPart(text="Hello")])
        }
    }
    
    response = a2a._handle_send_task(request)
    assert response.result.metadata == {"user": "test", "source": "handler"}
    
    if a2a.state_store:
        state = memory_state_store.get_state(response.result.sessionId)
        assert state.metadata == response.result.metadata