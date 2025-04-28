# Library imports
import json
import pytest
import uuid
from typing import List, Dict, Any, Optional
from fastapi.testclient import TestClient

# Local imports
from smarta2a.server import SmartA2A
from smarta2a.utils.types import (
    Message, 
    StateData, 
    SendTaskRequest, 
    SendTaskStreamingRequest,
    A2AStatus,
    A2AStreamResponse
)
from smarta2a.state_stores import BaseStateStore

class AppendStrategy:
    """Default append behavior"""
    def update_history(self, existing_history: List[Message], new_messages: List[Message]) -> List[Message]:
        return existing_history + new_messages
    
class InMemoryStateStore(BaseStateStore):
    def __init__(self):
        self.states: Dict[str, StateData] = {}
    
    def get_state(self, session_id: str) -> Optional[StateData]:
        return self.states.get(session_id)
    
    def update_state(self, session_id: str, state_data: StateData):
        self.states[session_id] = state_data
    
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


def test_send_task_with_history_strategy_and_state_store():
    state_store = InMemoryStateStore()
    append_strategy = AppendStrategy()

    a2a_server = SmartA2A("test-server", state_store=state_store, history_update_strategy=append_strategy)

    with TestClient(a2a_server.app) as client:
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
    print(data)
    assert data["id"] == "1"
    assert data["result"]["status"]["state"] == "completed"
    assert len(data["result"]["artifacts"]) == 1
    assert data["result"]["artifacts"][0]["parts"][0]["text"] == "Hello, World!"
    assert data["result"]["sessionId"]  # Should be generated
    assert len(data["result"]["history"]) == 2
    assert state_store.get_state(data["result"]["sessionId"]).history[0].role == "user"
    assert state_store.get_state(data["result"]["sessionId"]).history[1].role == "agent"
    assert state_store.get_state(data["result"]["sessionId"]).history[0].parts[0].text == "Test message"
    assert state_store.get_state(data["result"]["sessionId"]).history[1].parts[0].text == "Hello, World!"
    assert data["result"]["history"][0]["role"] == "user"
    assert data["result"]["history"][1]["role"] == "agent"
    assert data["result"]["history"][0]["parts"][0]["text"] == "Test message"
    assert data["result"]["history"][1]["parts"][0]["text"] == "Hello, World!"

def test_send_task_with_history_strategy_only():
    append_strategy = AppendStrategy()

    a2a_server = SmartA2A("test-server", history_update_strategy=append_strategy)

    with TestClient(a2a_server.app) as client:
        # Register task handler correctly
        @a2a_server.on_send_task()
        def handle_task(request: SendTaskRequest):
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
    print(data)
    assert data["id"] == "1"
    assert data["result"]["status"]["state"] == "completed"
    assert len(data["result"]["artifacts"]) == 1
    assert data["result"]["artifacts"][0]["parts"][0]["text"] == "Hello, World!"
    assert data["result"]["sessionId"]  # Should be generated
    assert len(data["result"]["history"]) == 2
    assert data["result"]["history"][0]["role"] == "user"
    assert data["result"]["history"][1]["role"] == "agent"
    assert data["result"]["history"][0]["parts"][0]["text"] == "Test message"
    assert data["result"]["history"][1]["parts"][0]["text"] == "Hello, World!"


def test_send_subscribe_task_with_history_strategy_and_state_store():
    state_store = InMemoryStateStore()
    append_strategy = AppendStrategy()

    a2a_server = SmartA2A("test-server", state_store=state_store, history_update_strategy=append_strategy)

    with TestClient(a2a_server.app) as client:
        # Register subscription handler with string statuses
        @a2a_server.on_send_subscribe_task()
        async def handle_subscription(request: SendTaskStreamingRequest, state: StateData):
            yield A2AStatus(status="working")  # Use string literal
            yield A2AStreamResponse(content="Processing...")
            yield A2AStreamResponse(content="More Processing...")
            yield A2AStatus(status="completed")  # Use string instead of TaskState enum

        # Send subscription request
        response = client.post(
            "/",
            json={
                "jsonrpc": "2.0",
                "id": "3",
                
                "method": "tasks/sendSubscribe",
                "params": {
                    "id": "test-task-2",
                    "sessionId": "c295ea44-7543-4f78-b524-7a38915ad6e4",
                    "message": {
                        "role": "user",
                        "parts": [{"type": "text", "text": "Test subscription"}]
                    }
                }
            },
            headers={"Accept": "text/event-stream"}
        )

    assert response.status_code == 200
    assert response.headers["content-type"] == "text/event-stream; charset=utf-8"
    
    # Properly parse SSE events
    events = []
    raw_content = response.content.decode("utf-8").strip()
    for event_chunk in raw_content.split("\n\n"):  # Split by event boundaries
        event_lines = event_chunk.split("\n")
        for line in event_lines:
            if line.startswith("data:"):
                event_data = json.loads(line[5:].strip())
                events.append(event_data)

    # Verify event sequence
    assert len(events) >= 4, f"Expected 4 events, got {len(events)}: {events}"
    assert state_store.get_state("c295ea44-7543-4f78-b524-7a38915ad6e4").history[0].role == "user"
    assert state_store.get_state("c295ea44-7543-4f78-b524-7a38915ad6e4").history[1].role == "agent"
    assert state_store.get_state("c295ea44-7543-4f78-b524-7a38915ad6e4").history[2].role == "agent"
    assert state_store.get_state("c295ea44-7543-4f78-b524-7a38915ad6e4").history[0].parts[0].text == "Test subscription"
    assert state_store.get_state("c295ea44-7543-4f78-b524-7a38915ad6e4").history[1].parts[0].text == "Processing..."
    assert state_store.get_state("c295ea44-7543-4f78-b524-7a38915ad6e4").history[2].parts[0].text == "More Processing..."
    
