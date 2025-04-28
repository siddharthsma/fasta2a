# Library imports
from typing import Any, Literal
from uuid import uuid4

# Local imports
from smarta2a.utils.types import (
    TaskPushNotificationConfig,
    PushNotificationConfig,
    TaskSendParams,
    TextPart,
    DataPart,
    FilePart,
    FileContent,
    Message,
    Part,
    TaskQueryParams,
    TaskIdParams,
    GetTaskRequest,
    CancelTaskRequest,
    SetTaskPushNotificationRequest,
    GetTaskPushNotificationRequest,
    AuthenticationInfo,
)

class TaskRequestBuilder:
    @staticmethod
    def build_send_task_request(
        *,
        id: str,
        role: Literal["user", "agent"] = "user",
        text: str | None = None,
        data: dict[str, Any] | None = None,
        file_uri: str | None = None,
        session_id: str | None = None,
        accepted_output_modes: list[str] | None = None,
        push_notification: PushNotificationConfig | None = None,
        history_length: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> TaskSendParams:
        parts: list[Part] = []

        if text is not None:
            parts.append(TextPart(text=text))

        if data is not None:
            parts.append(DataPart(data=data))

        if file_uri is not None:
            file_content = FileContent(uri=file_uri)
            parts.append(FilePart(file=file_content))

        message = Message(role=role, parts=parts)

        return TaskSendParams(
            id=id,
            sessionId=session_id or uuid4().hex,
            message=message,
            acceptedOutputModes=accepted_output_modes,
            pushNotification=push_notification,
            historyLength=history_length,
            metadata=metadata,
        )
    
    @staticmethod
    def get_task(
        id: str,
        history_length: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> GetTaskRequest:
        params = TaskQueryParams(
            id=id,
            historyLength=history_length,
            metadata=metadata,
        )
        return GetTaskRequest(params=params)

    @staticmethod
    def cancel_task(
        id: str,
        metadata: dict[str, Any] | None = None,
    ) -> CancelTaskRequest:
        params = TaskIdParams(id=id, metadata=metadata)
        return CancelTaskRequest(params=params)

    @staticmethod
    def set_push_notification(
        id: str,
        url: str,
        token: str | None = None,
        authentication: AuthenticationInfo | dict[str, Any] | None = None,
    ) -> SetTaskPushNotificationRequest:
        # allow passing AuthenticationInfo _or_ raw dict
        auth = (
            authentication
            if isinstance(authentication, AuthenticationInfo)
            else (AuthenticationInfo(**authentication) if authentication else None)
        )
        push_cfg = TaskPushNotificationConfig(
            id=id,
            pushNotificationConfig=PushNotificationConfig(
                url=url,
                token=token,
                authentication=auth,
            )
        )
        return SetTaskPushNotificationRequest(params=push_cfg)

    @staticmethod
    def get_push_notification(
        id: str,
        metadata: dict[str, Any] | None = None,
    ) -> GetTaskPushNotificationRequest:
        params = TaskIdParams(id=id, metadata=metadata)
        return GetTaskPushNotificationRequest(params=params)
