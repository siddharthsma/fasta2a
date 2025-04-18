import pytest
import json
import requests
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
    FilePart,
    FileContent,
    A2AResponse,
    TaskQueryParams,
    TaskStatusUpdateEvent,
    TaskArtifactUpdateEvent,
    A2AStatus,
    A2AStreamResponse,
    SendTaskResponse,  
    Message
)

@pytest.fixture
def a2a_server():
    server = FastA2A("test-server")
    return server

@pytest.fixture
def client(a2a_server):
    #return TestClient(a2a_server.app)
    # Create client with explicit async_test_client context manager
    with TestClient(a2a_server.app) as client:
        yield client

# Add async teardown for server
@pytest.fixture(autouse=True)
async def cleanup():
    yield
    # Force close all app connections
    import anyio
    anyio.run(anyio.sleep, 0)  # Flush pending tasks

def test_send_task(client, a2a_server):
    # Register task handler correctly
    @a2a_server.on_send_task()
    def handle_task(request: SendTaskRequest):
        return A2AResponse(
            status="completed",
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


def test_send_task_with_artifact(client, a2a_server):
    # Test handler returning raw protocol types
    @a2a_server.on_send_task()
    def handle_task(request: SendTaskRequest) -> Artifact:
        return Artifact(
            parts=[TextPart(text="Direct result")],
            name="test-artifact",
            description="Created directly"
        )

    response = client.post("/", json={
        "jsonrpc": "2.0",
        "id": "1",
        "method": "tasks/send",
        "params": {
            "id": "direct-task",
            "message": {
                "role": "user",
                "parts": [{"type": "text", "text": "Test direct"}]
            }
        }
    })

    assert response.status_code == 200
    data = response.json()
    assert data["result"]["status"]["state"] == "completed"
    artifact = data["result"]["artifacts"][0]
    assert artifact["name"] == "test-artifact"
    assert artifact["parts"][0]["text"] == "Direct result"



def test_send_task_direct_response(client, a2a_server):
    # Test handler returning fully constructed SendTaskResponse
    @a2a_server.on_send_task()
    def handle_task(request: SendTaskRequest) -> SendTaskResponse:
        return SendTaskResponse(
            id=request.id,
            result=Task(
                id=request.params.id,
                sessionId="custom-session",
                status=TaskStatus(
                    state=TaskState.INPUT_REQUIRED,
                    message=Message(
                        role="agent",
                        parts=[TextPart(text="Need more information")]
                    )
                ),
                artifacts=[
                    Artifact(
                        name="direct-artifact",
                        parts=[TextPart(text="Direct response content")]
                    )
                ],
                metadata={"source": "direct-test"}
            )
        )

    # Send request
    response = client.post("/", json={
        "jsonrpc": "2.0",
        "id": "direct-response-test",
        "method": "tasks/send",
        "params": {
            "id": "direct-response-task",
            "message": {
                "role": "user",
                "parts": [{"type": "text", "text": "Test direct response"}]
            }
        }
    })

    assert response.status_code == 200
    data = response.json()
    
    # Validate top-level response
    assert data["id"] == "direct-response-test"
    assert data["error"] is None
    
    # Validate task structure
    result = data["result"]
    assert result["id"] == "direct-response-task"
    assert result["sessionId"] == "custom-session"
    assert result["status"]["state"] == "input-required"
    
    # Validate message parts
    message = result["status"]["message"]
    assert message["role"] == "agent"
    assert message["parts"][0]["text"] == "Need more information"
    
    # Validate artifacts
    artifact = result["artifacts"][0]
    assert artifact["name"] == "direct-artifact"
    assert artifact["parts"][0]["text"] == "Direct response content"
    
    # Validate metadata
    assert result["metadata"]["source"] == "direct-test"


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


def test_send_subscribe_with_direct_events(client, a2a_server):
    # Test handler yielding protocol event types directly
    @a2a_server.on_send_subscribe_task()
    async def handle_subscription(params: TaskSendParams):
        try:
            yield TaskStatusUpdateEvent(
                id=params.id,
                status=TaskStatus(state=TaskState.WORKING),
                final=False
            )
            
            yield TaskArtifactUpdateEvent(
                id=params.id,
                artifact=Artifact(
                    parts=[FilePart(
                        file=FileContent(uri="file.txt"),
                        metadata={"source": "test"}
                    )]
                )
            )
            
            yield TaskStatusUpdateEvent(
                id=params.id,
                status=TaskStatus(state=TaskState.COMPLETED),
                final=True
            )
        except Exception as e:
            print(f"Error in handler: {str(e)}")

    response = client.post(
        "/",
        json={
            "jsonrpc": "2.0",
            "id": "2",
            "method": "tasks/sendSubscribe",
            "params": {
                "id": "direct-events-task",
                "message": {
                    "role": "user",
                    "parts": [{"type": "text", "text": "Test events"}]
                }
            }
        },
        headers={"Accept": "text/event-stream"}
    )

    events = []
    try:
        # Read until end of stream
        for line in response.iter_lines():
            if line.startswith('data:'):
                event = json.loads(line[5:])
                events.append(event)
    except (requests.exceptions.ChunkedEncodingError, json.JSONDecodeError):
        pass  # Expected when stream ends
    finally:
        response.close()
        del response

    assert len(events) == 3
    
    # Verify first event (status update)
    assert events[0]["result"]["status"]["state"] == "working"
    
    # Verify second event (file artifact)
    artifact = events[1]["result"]["artifact"]
    assert artifact["parts"][0]["type"] == "file"
    assert artifact["parts"][0]["file"]["uri"] == "file.txt"
    
    # Verify final status
    assert events[-1]["result"]["status"]["state"] == "completed"
    assert events[-1]["result"]["final"] is True


def test_send_subscribe_task(client, a2a_server):
    # Register subscription handler with string statuses
    @a2a_server.on_send_subscribe_task()
    async def handle_subscription(params: TaskSendParams):
        yield A2AStatus(status="working")  # Use string literal
        yield A2AStreamResponse(content="Processing...")
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
    assert len(events) >= 3, f"Expected 3 events, got {len(events)}: {events}"

    # First event - status update
    assert events[0]["result"]["status"]["state"] == "working"
    assert events[0]["result"]["final"] is False

    # Second event - artifact update
    assert events[1]["result"]["artifact"]["parts"][0]["text"] == "Processing..."

    # Final event - completed status
    assert events[-1]["result"]["status"]["state"] == "completed"
    assert events[-1]["result"]["final"] is True



