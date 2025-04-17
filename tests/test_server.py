import pytest
from fastapi.testclient import TestClient
from fasta2a import FastA2A
from fasta2a.types import (
    TaskSendParams,
    SendTaskRequest,
    GetTaskRequest,
    Task,
    TaskStatus,
    TaskState,
    Artifact,
    TextPart,
    A2AResponse,
    TaskQueryParams
)

@pytest.fixture
def a2a_server():
    server = FastA2A("test-server")
    return server

@pytest.fixture
def client(a2a_server):
    return TestClient(a2a_server.app)

def test_send_task(client, a2a_server):
    # Register task handler correctly
    @a2a_server.on_send_task()
    def handle_task(request: SendTaskRequest):
        return A2AResponse(
            state=TaskState.COMPLETED,
            content="Hello, World!"
        )

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
    assert data["result"]["status"]["state"] == TaskState.COMPLETED
    assert len(data["result"]["artifacts"]) == 1
    assert data["result"]["artifacts"][0]["parts"][0]["text"] == "Hello, World!"
    assert data["result"]["sessionId"]  # Should be generated

def test_get_task(client, a2a_server):
    # Register get handler with proper typing
    @a2a_server.task_get()
    def get_task(request: GetTaskRequest) -> Task:
        return Task(
            id=request.params.id,
            sessionId="test-session",
            status=TaskStatus(state=TaskState.COMPLETED),
            artifacts=[Artifact(parts=[TextPart(text="Test artifact")])],
            history=[],
            metadata={}
        )

    # Test get request
    response = client.post("/", json={
        "jsonrpc": "2.0",
        "id": "2",
        "method": "tasks/get",
        "params": {
            "id": "test-task-id"
        }
    })

    assert response.status_code == 200
    data = response.json()
    print(data)
    assert data["id"] == "2"
    assert data["result"]["id"] == "test-task-id"
    assert data["result"]["status"]["state"] == TaskState.COMPLETED
    assert data["result"]["sessionId"] == "test-session"