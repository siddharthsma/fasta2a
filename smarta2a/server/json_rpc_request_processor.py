# Library imports
from typing import Optional, Any
from pydantic import BaseModel, ValidationError
from fastapi import HTTPException

# Local imports
from smarta2a.utils.types import (
    JSONRPCRequest, 
    JSONRPCResponse,
    SendTaskRequest,
    SendTaskStreamingRequest,
    GetTaskRequest,
    CancelTaskRequest,
    SetTaskPushNotificationRequest,
    GetTaskPushNotificationRequest,
    GetTaskResponse,
    CancelTaskResponse,
    SetTaskPushNotificationResponse,
    GetTaskPushNotificationResponse,
    TaskStatus,
    TaskState
)
from smarta2a.server.state_manager import StateManager
from smarta2a.server.request_handler import RequestHandler
from smarta2a.server.handler_registry import HandlerRegistry
from smarta2a.utils.types import (
    TaskNotFoundError,
    MethodNotFoundError,
    InvalidParamsError,
    UnsupportedOperationError,
    InternalError,
    InvalidRequestError
)

class JSONRPCRequestProcessor:
    def __init__(self, registry: HandlerRegistry, state_manager: Optional[StateManager] = None):
        self.request_handler = RequestHandler(registry, state_manager)
        self.state_manager = state_manager

    async def process_request(self, request: JSONRPCRequest) -> JSONRPCResponse:
        
        try:
            method = request.method
            params = request.params
            

            match method:
                case "tasks/send":
                    send_task_request = self._validate_request(request, SendTaskRequest)
                    
                    if self.state_manager:
                        state_data = await self.state_manager.get_or_create_and_update_state(send_task_request.params.id, send_task_request.params.sessionId, send_task_request.params.message, send_task_request.params.metadata, send_task_request.params.pushNotification)
                        return await self.request_handler.handle_send_task(send_task_request, state_data)
                    else:
                        return await self.request_handler.handle_send_task(send_task_request)
                    
                case "tasks/sendSubscribe":
                    send_subscribe_request = self._validate_request(request, SendTaskStreamingRequest)
                    if self.state_manager:
                        state_data = await self.state_manager.get_or_create_and_update_state(send_subscribe_request.params.id, send_subscribe_request.params.sessionId, send_subscribe_request.params.message, send_subscribe_request.params.metadata, send_subscribe_request.params.pushNotification)
                        return await self.request_handler.handle_subscribe_task(send_subscribe_request, state_data)
                    else:
                        return await self.request_handler.handle_subscribe_task(send_subscribe_request)
                    
                case "tasks/get":
                    get_task_request = self._validate_request(request, GetTaskRequest)
                    if self.state_manager:
                        state_data = self.state_manager.get_state(get_task_request.id)
                        if state_data:
                            return GetTaskResponse(
                                id=get_task_request.id,
                                result=state_data.task
                            )
                        else:
                            return JSONRPCResponse(id=request.id, error=TaskNotFoundError())
                    else:
                        return self.request_handler.handle_get_task(get_task_request)
                    
                case "tasks/cancel":
                    cancel_task_request = self._validate_request(request, CancelTaskRequest)
                    if self.state_manager:
                        state_data = self.state_manager.get_state(cancel_task_request.id)
                        if state_data:
                            state_data.task.status = TaskStatus(state=TaskState.CANCELLED)
                            self.state_manager.update_state(cancel_task_request.id, state_data)
                            return CancelTaskResponse(id=cancel_task_request.id)
                        else:
                            return JSONRPCResponse(id=request.id, error=TaskNotFoundError())
                    else:
                        return self.request_handler.handle_cancel_task(cancel_task_request)
                    
                case "tasks/pushNotification/set":
                    set_push_notification_request = self._validate_request(request, SetTaskPushNotificationRequest)
                    if self.state_manager:
                        state_data = self.state_manager.get_state(set_push_notification_request.id)
                        if state_data:
                            state_data.push_notification_config = set_push_notification_request.pushNotificationConfig
                            self.state_manager.update_state(set_push_notification_request.id, state_data)
                            return SetTaskPushNotificationResponse(id=set_push_notification_request.id, result=state_data.push_notification_config)
                        else:
                            return JSONRPCResponse(id=request.id, error=TaskNotFoundError())
                    else:
                        return self.request_handler.handle_set_notification(set_push_notification_request)
                    
                case "tasks/pushNotification/get":
                    get_push_notification_request = self._validate_request(request, GetTaskPushNotificationRequest)
                    if self.state_manager:
                        state_data = self.state_manager.get_state(get_push_notification_request.id)
                        if state_data:
                            return GetTaskPushNotificationResponse(id=get_push_notification_request.id, result=state_data.push_notification_config)
                        else:
                            return JSONRPCResponse(id=request.id, error=TaskNotFoundError())
                    else:
                        return self.request_handler.handle_get_notification(get_push_notification_request)
                    
                case _:
                    return JSONRPCResponse(id=request.id, error=MethodNotFoundError()).model_dump()
                
        except ValidationError as e:
            return JSONRPCResponse(id=request.id, error=InvalidParamsError(data=e.errors())).model_dump()
        except HTTPException as e:
            err = UnsupportedOperationError() if e.status_code == 405 else InternalError(data=str(e))
            return JSONRPCResponse(id=request.id, error=err).model_dump()

        
    def _validate_request(self, request: JSONRPCRequest, validation_schema: BaseModel) -> Any:
        try:
            return validation_schema.model_validate(request.model_dump())
        except ValidationError as e:
            return JSONRPCResponse(id=request.id, error=InvalidRequestError(data=e.errors())).model_dump()
