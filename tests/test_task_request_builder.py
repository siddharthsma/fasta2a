import pytest
from uuid import UUID
from smarta2a.utils.types import (
    TaskSendParams,
    Message,
    TextPart,
    DataPart,
    FilePart,
    GetTaskRequest,
    TaskQueryParams,
    CancelTaskRequest,
    TaskIdParams,
    SetTaskPushNotificationRequest,
    PushNotificationConfig,
    AuthenticationInfo,
    GetTaskPushNotificationRequest,
)
from smarta2a.utils.task_request_builder import TaskRequestBuilder

class TestTaskRequestBuilder:
    def test_build_send_task_request_with_text(self):
        # Test with text part
        request = TaskRequestBuilder.build_send_task_request(
            id="task123",
            text="Hello world",
            role="agent",
            session_id="session_456",
            metadata={"key": "value"},
        )
        
        assert isinstance(request, TaskSendParams)
        assert request.id == "task123"
        assert request.sessionId == "session_456"
        assert request.metadata == {"key": "value"}
        assert isinstance(request.message, Message)
        assert request.message.role == "agent"
        assert len(request.message.parts) == 1
        assert isinstance(request.message.parts[0], TextPart)
        assert request.message.parts[0].text == "Hello world"

    def test_build_send_task_request_with_all_parts(self):
        # Test with text, data, and file parts
        request = TaskRequestBuilder.build_send_task_request(
            id="task123",
            text="Hello",
            data={"key": "value"},
            file_uri="file:///data.csv",
        )
        
        parts = request.message.parts
        assert len(parts) == 3
        assert any(isinstance(p, TextPart) for p in parts)
        assert any(isinstance(p, DataPart) and p.data == {"key": "value"} for p in parts)
        assert any(isinstance(p, FilePart) and p.file.uri == "file:///data.csv" for p in parts)

    def test_build_send_task_request_default_session_id(self):
        # Ensure sessionId is a UUID hex string when not provided
        request = TaskRequestBuilder.build_send_task_request(id="task123", text="Hi")
        assert len(request.sessionId) == 32
        try:
            UUID(request.sessionId, version=4)
        except ValueError:
            pytest.fail("sessionId is not a valid UUID4 hex string")

    def test_get_task(self):
        request = TaskRequestBuilder.get_task(
            id="task123",
            history_length=5,
            metadata={"key": "value"},
        )
        
        assert isinstance(request, GetTaskRequest)
        assert isinstance(request.params, TaskQueryParams)
        assert request.params.id == "task123"
        assert request.params.historyLength == 5
        assert request.params.metadata == {"key": "value"}

    def test_cancel_task(self):
        request = TaskRequestBuilder.cancel_task(
            id="task123",
            metadata={"key": "value"},
        )
        
        assert isinstance(request, CancelTaskRequest)
        assert isinstance(request.params, TaskIdParams)
        assert request.params.id == "task123"
        assert request.params.metadata == {"key": "value"}

    def test_set_push_notification_with_authentication_info(self):
        # Test with AuthenticationInfo instance (include REQUIRED 'schemes' field)
        auth_info = AuthenticationInfo(
            schemes=["https", "bearer"],  # Required field
            credentials="token123"         # Optional field
        )
        request = TaskRequestBuilder.set_push_notification(
            id="task123",
            url="https://example.com",
            token="auth_token",
            authentication=auth_info,
        )
        
        assert isinstance(request.params.pushNotificationConfig.authentication, AuthenticationInfo)
        assert request.params.pushNotificationConfig.authentication.schemes == ["https", "bearer"]
        assert request.params.pushNotificationConfig.authentication.credentials == "token123"

    def test_set_push_notification_with_dict(self):
        # Test with authentication dict (MUST include 'schemes')
        auth_dict = {
            "schemes": ["basic"],  # Required field
            "credentials": "user:pass"  # Optional field
        }
        request = TaskRequestBuilder.set_push_notification(
            id="task123",
            url="https://example.com",
            authentication=auth_dict,
        )
        
        assert request.params.pushNotificationConfig.authentication.schemes == ["basic"]
        assert request.params.pushNotificationConfig.authentication.credentials == "user:pass"

    def test_get_push_notification(self):
        request = TaskRequestBuilder.get_push_notification(
            id="task123",
            metadata={"key": "value"},
        )
        
        assert isinstance(request, GetTaskPushNotificationRequest)
        assert isinstance(request.params, TaskIdParams)
        assert request.params.id == "task123"
        assert request.params.metadata == {"key": "value"}