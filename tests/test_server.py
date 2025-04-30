import pytest
import json
import requests
from fastapi.testclient import TestClient
from smarta2a.server import SmartA2A
from smarta2a.utils.types import (
    TaskSendParams,
    SendTaskRequest,
    GetTaskRequest,
    CancelTaskRequest,
    CancelTaskResponse,
    Task,
    TaskStatus,
    TaskState,
    Artifact,
    TextPart,
    FilePart,
    FileContent,
    A2AResponse,
    A2ARequest,
    TaskStatusUpdateEvent,
    TaskArtifactUpdateEvent,
    A2AStatus,
    A2AStreamResponse,
    SendTaskResponse,  
    Message,
    InternalError,
    SetTaskPushNotificationRequest,
    GetTaskPushNotificationRequest,
    SetTaskPushNotificationResponse,
    GetTaskPushNotificationResponse,
    TaskPushNotificationConfig
)

@pytest.fixture
def a2a_server():
    server = SmartA2A("test-server")
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
    print(data)
    assert data["id"] == "1"
    assert data["result"]["status"]["state"] == "completed"
    assert len(data["result"]["artifacts"]) == 1
    assert data["result"]["artifacts"][0]["parts"][0]["text"] == "Hello, World!"
    assert data["result"]["sessionId"]  # Should be generated


def test_send_task_with_string_response(client, a2a_server):
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
    assert data["id"] == "1"
    assert data["result"]["status"]["state"] == "completed"
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


def test_get_task_with_task(client, a2a_server):
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
    assert data["result"]["status"]["state"] == "completed"
    assert data["result"]["sessionId"] == "test-session"


def test_get_task_with_string(client, a2a_server):
    # Register get handler with proper typing
    @a2a_server.task_get()
    def get_task(request: GetTaskRequest) -> Task:
        return "Test artifact"

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
    assert data["result"]["status"]["state"] == "completed"


def test_successful_cancellation(client, a2a_server):
    """Test successful cancellation with direct CancelTaskResponse"""
    @a2a_server.task_cancel()
    def handle_cancel(request: CancelTaskRequest) -> CancelTaskResponse:
        return CancelTaskResponse(
            id=request.id,
            result=Task(
                id=request.params.id,
                sessionId="cancel-session",
                status=TaskStatus(state=TaskState.CANCELED),
                artifacts=[],
                history=[]
            )
        )

    response = client.post("/", json={
        "jsonrpc": "2.0",
        "id": "cancel-1",
        "method": "tasks/cancel",
        "params": {
            "id": "task-123",
            "metadata": {"reason": "user_request"}
        }
    })

    assert response.status_code == 200
    data = response.json()
    assert data["result"]["status"]["state"] == "canceled"
    assert data["result"]["id"] == "task-123"

def test_cancellation_with_a2astatus(client, a2a_server):
    """Test cancellation using A2AStatus return"""
    @a2a_server.task_cancel()
    def handle_cancel(request: CancelTaskRequest) -> A2AStatus:
        return A2AStatus(
            status="canceled",
            metadata={
                "by": "admin"
            }
        )

    response = client.post("/", json={
        "jsonrpc": "2.0",
        "id": "cancel-2",
        "method": "tasks/cancel",
        "params": {"id": "task-456"}
    })

    assert response.status_code == 200
    result = response.json()["result"]
    assert result["status"]["state"] == "canceled"
    assert "by" in result["metadata"]


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



def test_duplicate_on_send_task_registration():
    """Test that @on_send_task can only be registered once"""
    app = SmartA2A("test-app")

    # First registration should work
    @app.on_send_task()
    def handler1(request: SendTaskRequest):
        return "First handler"

    # Second registration should fail
    with pytest.raises(RuntimeError) as exc_info:
        @app.on_send_task()
        def handler2(request: SendTaskRequest):
            return "Second handler"

    # Verify error message
    assert "already registered" in str(exc_info.value)
    assert "tasks/send" in str(exc_info.value)


def test_send_task_content_access():
    """Test content property for SendTaskRequest with message parts"""
    request = A2ARequest.validate_python({
        "jsonrpc": "2.0",
        "id": "1",
        "method": "tasks/send",
        "params": {
            "id": "test-task",
            "message": {
                "role": "user",
                "parts": [
                    {"type": "text", "text": "Hello"},
                    {"type": "file", "file": {"uri": "gs://bucket/file.txt"}}
                ]
            }
        }
    })
    
    assert isinstance(request, SendTaskRequest)
    # Test direct content access
    assert len(request.content) == 2
    assert isinstance(request.content[0], TextPart)
    assert request.content[0].text == "Hello"
    assert isinstance(request.content[1], FilePart)
    
    # Verify original access still works
    assert request.content == request.params.message.parts


def test_set_notification_success(a2a_server, client):
    # Test basic success case with no return value
    @a2a_server.set_notification()
    def handle_set(req: SetTaskPushNotificationRequest):
        # No return needed - just validate request
        assert req.params.id == "test123"
    
    request_data = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tasks/pushNotification/set",
        "params": {
            "id": "test123",
            "pushNotificationConfig": {
                "url": "https://example.com/callback",
                "authentication": {
                    "schemes": ["jwt"]
                }
            }
        }
    }
    
    response = client.post("/", json=request_data).json()
    
    assert response["result"]["id"] == "test123"
    assert response["result"]["pushNotificationConfig"]["url"] == request_data["params"]["pushNotificationConfig"]["url"]
    assert response["result"]["pushNotificationConfig"]["authentication"]["schemes"] == ["jwt"]

def test_set_notification_custom_response(a2a_server, client):
    # Test handler returning custom response
    @a2a_server.set_notification()
    def handle_set(req):
        return SetTaskPushNotificationResponse(
            id=req.id,
            result=TaskPushNotificationConfig(
                id="test123",
                pushNotificationConfig={
                    "url": "custom-url",
                    "token": "secret"
                }
            )
        )
    
    response = client.post("/", json={
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tasks/pushNotification/set",
        "params": {
            "id": "test123",
            "pushNotificationConfig": {"url": "https://example.com"}
        }
    }).json()
    
    assert response["result"]["pushNotificationConfig"]["url"] == "custom-url"
    assert "secret" in response["result"]["pushNotificationConfig"]["token"]


# --- Get Notification Tests ---

def test_get_notification_success(a2a_server, client):
    # Test successful config retrieval
    @a2a_server.get_notification()
    def handle_get(req: GetTaskPushNotificationRequest):
        return TaskPushNotificationConfig(
            id=req.params.id,
            pushNotificationConfig={
                "url": "https://test.com",
                "token": "abc123"
            }
        )
    
    request_data = {
        "jsonrpc": "2.0",
        "id": 4,
        "method": "tasks/pushNotification/get",
        "params": {"id": "test456"}
    }
    
    response = client.post("/", json=request_data).json()
    
    assert response["result"]["id"] == "test456"
    assert response["result"]["pushNotificationConfig"]["url"] == "https://test.com"

def test_get_notification_direct_response(a2a_server, client):
    # Test handler returning full response object
    @a2a_server.get_notification()
    def handle_get(req):
        return GetTaskPushNotificationResponse(
            id=req.id,
            result=TaskPushNotificationConfig(
                id=req.params.id,
                pushNotificationConfig={
                    "url": "direct-response.example",
                    "authentication": {"schemes": ["basic"]}
                }
            )
        )
    
    response = client.post("/", json={
        "jsonrpc": "2.0",
        "id": 5,
        "method": "tasks/pushNotification/get",
        "params": {"id": "test789"}
    }).json()
    
    assert "direct-response" in response["result"]["pushNotificationConfig"]["url"]
    assert "basic" in response["result"]["pushNotificationConfig"]["authentication"]["schemes"]

def test_get_notification_validation_error(a2a_server, client):
    # Test invalid response from handler
    @a2a_server.get_notification()
    def handle_get(req):
        return {"invalid": "config"}
    
    response = client.post("/", json={
        "jsonrpc": "2.0",
        "id": 6,
        "method": "tasks/pushNotification/get",
        "params": {"id": "test999"}
    }).json()
    
    assert response["error"]["code"] == -32602  # Invalid params
    

def test_get_notification_error_propagation(a2a_server, client):
    # Test exception handling
    @a2a_server.get_notification()
    def handle_get(req):
        raise InternalError(message="Storage failure")
    
    response = client.post("/", json={
        "jsonrpc": "2.0",
        "id": 7,
        "method": "tasks/pushNotification/get",
        "params": {"id": "test-error"}
    }).json()
    
    assert response["error"]["code"] == -32603  # Internal error code
    



