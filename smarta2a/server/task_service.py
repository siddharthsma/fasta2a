# Library imports
from typing import Optional, Union, Any
from uuid import uuid4
from fastapi import HTTPException
from pydantic import ValidationError

# Local imports
from smarta2a.server.handler_registry import HandlerRegistry
from smarta2a.server.state_manager import StateManager
from smarta2a.utils.task_builder import TaskBuilder
from smarta2a.utils.types import (
    Message, StateData, SendTaskRequest, SendTaskResponse,
    GetTaskRequest, GetTaskResponse, CancelTaskRequest, CancelTaskResponse,
    SetTaskPushNotificationRequest, GetTaskPushNotificationRequest,
    SetTaskPushNotificationResponse, GetTaskPushNotificationResponse,
    TaskPushNotificationConfig, TaskState, A2AStatus,
    JSONRPCError, MethodNotFoundError, InternalError, InvalidParamsError,
    TaskNotCancelableError, UnsupportedOperationError
)

class TaskService:
    def __init__(self, registry: HandlerRegistry, state_mgr: StateManager):
        self.registry = registry
        self.state_mgr = state_mgr
        self.builder = TaskBuilder(default_status=TaskState.COMPLETED)

    def send(self, request: SendTaskRequest, state: Optional[StateData]) -> SendTaskResponse:
        handler = self.registry.get_handler("tasks/send")
        if not handler:
            return SendTaskResponse(id=request.id, error=MethodNotFoundError())

        session_id = state.sessionId if state else request.params.sessionId or str(uuid4())
        history = state.history.copy() if state else [request.params.message]
        metadata = state.metadata.copy() if state else (request.params.metadata or {})

        try:
            raw = handler(request, state) if state else handler(request)
            if isinstance(raw, SendTaskResponse):
                return raw

            task = self.builder.build(
                content=raw,
                task_id=request.params.id,
                session_id=session_id,
                metadata=metadata,
                history=history
            )

            if task.artifacts:
                parts = [p for a in task.artifacts for p in a.parts]
                agent_msg = Message(role="agent", parts=parts, metadata=task.metadata)
                new_hist = self.state_mgr.strategy.update_history(history, [agent_msg])
                task.history = new_hist
                self.state_mgr.update(StateData(sessionId=session_id, history=new_hist, metadata=metadata))

            return SendTaskResponse(id=request.id, result=task)
        except JSONRPCError as e:
            return SendTaskResponse(id=request.id, error=e)
        except Exception as e:
            return SendTaskResponse(id=request.id, error=InternalError(data=str(e)))

    def get(self, request: GetTaskRequest) -> GetTaskResponse:
        handler = self.registry.get_handler("tasks/get")
        if not handler:
            return GetTaskResponse(id=request.id, error=MethodNotFoundError())
        try:
            raw = handler(request)
            if isinstance(raw, GetTaskResponse):
                return self._validate(raw, request)

            task = self.builder.build(
                content=raw,
                task_id=request.params.id,
                metadata=request.params.metadata or {}
            )
            return self._finalize(request, task)
        except JSONRPCError as e:
            return GetTaskResponse(id=request.id, error=e)
        except Exception as e:
            return GetTaskResponse(id=request.id, error=InternalError(data=str(e)))

    def cancel(self, request: CancelTaskRequest) -> CancelTaskResponse:
        handler = self.registry.get_handler("tasks/cancel")
        if not handler:
            return CancelTaskResponse(id=request.id, error=MethodNotFoundError())
        try:
            raw = handler(request)
            if isinstance(raw, CancelTaskResponse):
                return self._validate(raw, request)

            if isinstance(raw, A2AStatus):
                task = self.builder.normalize_from_status(status=raw.status, task_id=request.params.id, metadata=raw.metadata or {})
            else:
                task = self.builder.build(content=raw, task_id=request.params.id, metadata=raw.metadata or {})

            if task.id != request.params.id:
                raise InvalidParamsError(data=f"Task ID mismatch: {task.id} vs {request.params.id}")
            if task.status.state not in [TaskState.CANCELED, TaskState.COMPLETED]:
                raise TaskNotCancelableError()

            return CancelTaskResponse(id=request.id, result=task)
        except JSONRPCError as e:
            return CancelTaskResponse(id=request.id, error=e)
        except (InvalidParamsError, TaskNotCancelableError) as e:
            return CancelTaskResponse(id=request.id, error=e)
        except HTTPException as e:
            if e.status_code == 405:
                return CancelTaskResponse(id=request.id, error=UnsupportedOperationError())
            return CancelTaskResponse(id=request.id, error=InternalError(data=str(e)))
        except Exception as e:
            return CancelTaskResponse(id=request.id, error=InternalError(data=str(e)))

    def set_notification(self, request: SetTaskPushNotificationRequest) -> SetTaskPushNotificationResponse:
        handler = self.registry.get_handler("tasks/pushNotification/set")
        if not handler:
            return SetTaskPushNotificationResponse(id=request.id, error=MethodNotFoundError())
        try:
            raw = handler(request)
            if raw is None:
                return SetTaskPushNotificationResponse(id=request.id, result=request.params)
            if isinstance(raw, SetTaskPushNotificationResponse):
                return raw
        except JSONRPCError as e:
            return SetTaskPushNotificationResponse(id=request.id, error=e)
        except Exception as e:
            return SetTaskPushNotificationResponse(id=request.id, error=InternalError(data=str(e)))

    def get_notification(self, request: GetTaskPushNotificationRequest) -> GetTaskPushNotificationResponse:
        handler = self.registry.get_handler("tasks/pushNotification/get")
        if not handler:
            return GetTaskPushNotificationResponse(id=request.id, error=MethodNotFoundError())
        try:
            raw = handler(request)
            if isinstance(raw, GetTaskPushNotificationResponse):
                return raw
            cfg = TaskPushNotificationConfig.model_validate(raw)
            return GetTaskPushNotificationResponse(id=request.id, result=cfg)
        except ValidationError as e:
            return GetTaskPushNotificationResponse(id=request.id, error=InvalidParamsError(data=e.errors()))
        except JSONRPCError as e:
            return GetTaskPushNotificationResponse(id=request.id, error=e)
        except Exception as e:
            return GetTaskPushNotificationResponse(id=request.id, error=InternalError(data=str(e)))

    def _validate(self, resp: Union[SendTaskResponse, GetTaskResponse, CancelTaskResponse], req) -> Any:
        if resp.result and resp.result.id != req.params.id:
            return type(resp)(id=req.id, error=InvalidParamsError(data=f"Task ID mismatch: {resp.result.id} vs {req.params.id}"))
        return resp

    def _finalize(self, request: GetTaskRequest, task) -> GetTaskResponse:
        if task.id != request.params.id:
            return GetTaskResponse(id=request.id, error=InvalidParamsError(data=f"Task ID mismatch: {task.id} vs {request.params.id}"))
        if request.params.historyLength and task.history:
            task.history = task.history[-request.params.historyLength:]
        return GetTaskResponse(id=request.id, result=task)