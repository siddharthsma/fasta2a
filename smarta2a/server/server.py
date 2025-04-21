from typing import Callable, Any, Optional, Dict, Union, List, AsyncGenerator
import json
from datetime import datetime
from collections import defaultdict
from fastapi import FastAPI, Request, HTTPException, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse
from pydantic import ValidationError
import uvicorn
from fastapi.responses import StreamingResponse
from uuid import uuid4

from smarta2a.common.types import (
    JSONRPCResponse,
    Task,
    Artifact,
    TextPart,
    FilePart,
    FileContent,
    DataPart,
    Part,
    TaskStatus,
    TaskState,
    JSONRPCError,
    SendTaskResponse,
    JSONRPCRequest,
    A2AResponse,
    SendTaskRequest,
    SendTaskStreamingRequest,
    SendTaskStreamingResponse,
    GetTaskRequest,
    GetTaskResponse,
    CancelTaskRequest,
    CancelTaskResponse,
    TaskStatusUpdateEvent,
    TaskArtifactUpdateEvent,
    JSONParseError,
    InvalidRequestError,
    MethodNotFoundError,
    InternalError,
    UnsupportedOperationError,
    TaskNotFoundError,
    InvalidParamsError,
    TaskNotCancelableError,
    A2AStatus,
    A2AStreamResponse,
    TaskSendParams,
    SetTaskPushNotificationRequest,
    GetTaskPushNotificationRequest,
    SetTaskPushNotificationResponse,
    GetTaskPushNotificationResponse,
    TaskPushNotificationConfig,
)

class SmartA2A:
    def __init__(self, name: str, **fastapi_kwargs):
        self.name = name
        self.handlers: Dict[str, Callable] = {}
        self.subscriptions: Dict[str, Callable] = {}
        self.app = FastAPI(title=name, **fastapi_kwargs)
        self.router = APIRouter()
        self._registered_decorators = set()
        self._setup_routes()
        self.server_config = {
            "host": "0.0.0.0",
            "port": 8000,
            "reload": False
        }
        

    def _setup_routes(self):
        @self.app.post("/")    
        async def handle_request(request: Request):
            try:
                data = await request.json()
                request_obj = JSONRPCRequest(**data)
            except Exception as e:
                return JSONRPCResponse(
                    id=None,
                    error=JSONRPCError(
                        code=-32700,
                        message="Parse error",
                        data=str(e)
                    )
                ).model_dump()
            
            response = await self.process_request(request_obj.model_dump())

            # <-- Accept both SSE‐style responses:
            if isinstance(response, (EventSourceResponse, StreamingResponse)):
                return response

            # <-- Everything else is a normal pydantic JSONRPCResponse
            return response.model_dump()

    def _register_handler(self, method: str, func: Callable, handler_name: str, handler_type: str = "handler"):
        """Shared registration logic with duplicate checking"""
        if method in self._registered_decorators:
            raise RuntimeError(
                f"@{handler_name} decorator for method '{method}' "
                f"can only be used once per SmartA2A instance"
            )
        
        if handler_type == "handler":
            self.handlers[method] = func
        else:
            self.subscriptions[method] = func
            
        self._registered_decorators.add(method)

    def on_send_task(self) -> Callable:
        def decorator(func: Callable[[SendTaskRequest], Any]) -> Callable:
            self._register_handler("tasks/send", func, "on_send_task", "handler")
            return func
        return decorator

    def on_send_subscribe_task(self) -> Callable:
        def decorator(func: Callable) -> Callable:
            self._register_handler("tasks/sendSubscribe", func, "on_send_subscribe_task", "subscription")
            return func
        return decorator
    
    def task_get(self):
        def decorator(func: Callable[[GetTaskRequest], Task]):
            self._register_handler("tasks/get", func, "task_get", "handler")
            return func
        return decorator
    
    def task_cancel(self):
        def decorator(func: Callable[[CancelTaskRequest], Task]):
            self._register_handler("tasks/cancel", func, "task_cancel", "handler")
            return func
        return decorator
    
    def set_notification(self):
        def decorator(func: Callable[[SetTaskPushNotificationRequest], None]) -> Callable:
            self._register_handler("tasks/pushNotification/set", func, "set_notification", "handler")
            return func
        return decorator
    
    def get_notification(self):
        def decorator(func: Callable[[GetTaskPushNotificationRequest], Union[TaskPushNotificationConfig, GetTaskPushNotificationResponse]]):
            self._register_handler("tasks/pushNotification/get", func, "get_notification", "handler")
            return func
        return decorator

    async def process_request(self, request_data: dict) -> JSONRPCResponse:
        try:
            method = request_data.get("method")
            if method == "tasks/send":
                return self._handle_send_task(request_data)
            elif method == "tasks/sendSubscribe":
                return await self._handle_subscribe_task(request_data)
            elif method == "tasks/get":
                return self._handle_get_task(request_data)
            elif method == "tasks/cancel":
                return self._handle_cancel_task(request_data)
            elif method == "tasks/pushNotification/set":
                return self._handle_set_notification(request_data)
            elif method == "tasks/pushNotification/get":
                return self._handle_get_notification(request_data)
            else:
                return self._error_response(
                    request_data.get("id"),
                    -32601,
                    "Method not found"
                )
        except ValidationError as e:
            return self._error_response(
                request_data.get("id"),
                -32600,
                "Invalid params",
                e.errors()
            )

    def _handle_send_task(self, request_data: dict) -> SendTaskResponse:
        try:
            # Validate request format
            request = SendTaskRequest.model_validate(request_data)
            handler = self.handlers.get("tasks/send")
            
            if not handler:
                return SendTaskResponse(
                    id=request.id,
                    error=MethodNotFoundError()
                )

            try:
                raw_result = handler(request)
            
                if isinstance(raw_result, SendTaskResponse):
                    return raw_result

                # Use unified task builder
                task = self._build_task(
                    content=raw_result,
                    task_id=request.params.id,
                    session_id=request.params.sessionId,
                    default_status=TaskState.COMPLETED,
                    metadata=request.params.metadata or {}
                )

                return SendTaskResponse(
                    id=request.id,
                    result=task
                )

            except Exception as e:
                # Handle case where handler returns SendTaskResponse with error
                if isinstance(e, JSONRPCError):
                    return SendTaskResponse(
                        id=request.id,
                        error=e
                    )
                return SendTaskResponse(
                    id=request.id,
                    error=InternalError(data=str(e))
                )

        except ValidationError as e:
            return SendTaskResponse(
                id=request_data.get("id"),
                error=InvalidRequestError(data=e.errors())
            )
        except json.JSONDecodeError as e:
            return SendTaskResponse(
                id=request_data.get("id"),
                error=JSONParseError(data=str(e))
            )

        
    async def _handle_subscribe_task(self, request_data: dict) -> Union[EventSourceResponse, SendTaskStreamingResponse]:
        try:
            request = SendTaskStreamingRequest.model_validate(request_data)
            handler = self.subscriptions.get("tasks/sendSubscribe")
            
            if not handler:
                return SendTaskStreamingResponse(
                    jsonrpc="2.0",
                    id=request.id,
                    error=MethodNotFoundError()
                )

            async def event_generator():
                
                try:
                    raw_events = handler(request)
                    normalized_events = self._normalize_subscription_events(request.params, raw_events)

                    async for item in normalized_events:
                        try:
                            if isinstance(item, SendTaskStreamingResponse):
                                yield item.model_dump_json()
                                continue

                            # Add validation for proper event types
                            if not isinstance(item, (TaskStatusUpdateEvent, TaskArtifactUpdateEvent)):
                                raise ValueError(f"Invalid event type: {type(item).__name__}")

                            yield SendTaskStreamingResponse(
                                jsonrpc="2.0",
                                id=request.id,
                                result=item
                            ).model_dump_json()

                        except Exception as e:
                            yield SendTaskStreamingResponse(
                                jsonrpc="2.0",
                                id=request.id,
                                error=InternalError(data=str(e))
                            ).model_dump_json()
                        

                except Exception as e:
                    error = InternalError(data=str(e))
                    if "not found" in str(e).lower():
                        error = TaskNotFoundError()
                    yield SendTaskStreamingResponse(
                        jsonrpc="2.0",
                        id=request.id,
                        error=error
                    ).model_dump_json()
                    
            async def sse_stream():
                async for chunk in event_generator():
                    # each chunk is already JSON; SSE wants "data: <payload>\n\n"
                    yield (f"data: {chunk}\n\n").encode("utf-8")

            return StreamingResponse(
                sse_stream(),
                media_type="text/event-stream; charset=utf-8"
            )


        except ValidationError as e:
            return SendTaskStreamingResponse(
                jsonrpc="2.0",
                id=request_data.get("id"),
                error=InvalidRequestError(data=e.errors())
            )
        except json.JSONDecodeError as e:
            return SendTaskStreamingResponse(
                jsonrpc="2.0",
                id=request_data.get("id"),
                error=JSONParseError(data=str(e))
            )
        except HTTPException as e:
            if e.status_code == 405:
                return SendTaskStreamingResponse(
                    jsonrpc="2.0",
                    id=request_data.get("id"),
                    error=UnsupportedOperationError()
                )
            return SendTaskStreamingResponse(
                jsonrpc="2.0",
                id=request_data.get("id"),
                error=InternalError(data=str(e))
            )


    def _handle_get_task(self, request_data: dict) -> GetTaskResponse:
        try:
            # Validate request structure
            request = GetTaskRequest.model_validate(request_data)
            handler = self.handlers.get("tasks/get")
            
            if not handler:
                return GetTaskResponse(
                    id=request.id,
                    error=MethodNotFoundError()
                )

            try:
                raw_result = handler(request)
            
                if isinstance(raw_result, GetTaskResponse):
                    return self._validate_response_id(raw_result, request)

                # Use unified task builder with different defaults
                task = self._build_task(
                    content=raw_result,
                    task_id=request.params.id,
                    default_status=TaskState.COMPLETED,
                    metadata=request.params.metadata or {}
                )

                return self._finalize_task_response(request, task)

            except Exception as e:
                # Handle case where handler returns SendTaskResponse with error
                if isinstance(e, JSONRPCError):
                    return GetTaskResponse(
                        id=request.id,
                        error=e
                    )
                return GetTaskResponse(
                    id=request.id,
                    error=InternalError(data=str(e))
                )

        except ValidationError as e:
            return GetTaskResponse(
                id=request_data.get("id"),
                error=InvalidRequestError(data=e.errors())
            )
        except json.JSONDecodeError as e:
            return GetTaskResponse(
                id=request_data.get("id"),
                error=JSONParseError(data=str(e))
            )
        

    def _handle_cancel_task(self, request_data: dict) -> CancelTaskResponse:
        try:
            # Validate request structure
            request = CancelTaskRequest.model_validate(request_data)
            handler = self.handlers.get("tasks/cancel")
            
            if not handler:
                return CancelTaskResponse(
                    id=request.id,
                    error=MethodNotFoundError()
                )

            try:
                raw_result = handler(request)
            
                # Handle direct CancelTaskResponse returns
                if isinstance(raw_result, CancelTaskResponse):
                    return self._validate_response_id(raw_result, request)

                # Handle A2AStatus returns
                if isinstance(raw_result, A2AStatus):
                    task = self._build_task_from_status(
                        status=raw_result,
                        task_id=request.params.id,
                        metadata=raw_result.metadata or {}
                    )
                else:
                    # Existing processing for other return types
                    task = self._build_task(
                        content=raw_result,
                        task_id=request.params.id,
                        metadata=raw_result.metadata or {}
                    )

                # Final validation and packaging
                return self._finalize_cancel_response(request, task)

            except Exception as e:
                # Handle case where handler returns SendTaskResponse with error
                if isinstance(e, JSONRPCError):
                    return CancelTaskResponse(
                        id=request.id,
                        error=e
                    )
                return CancelTaskResponse(
                    id=request.id,
                    error=InternalError(data=str(e))
                )

        except ValidationError as e:
            return CancelTaskResponse(
                id=request_data.get("id"),
                error=InvalidRequestError(data=e.errors())
            )
        except json.JSONDecodeError as e:
            return CancelTaskResponse(
                id=request_data.get("id"),
                error=JSONParseError(data=str(e))
            )
        except HTTPException as e:
            if e.status_code == 405:
                return CancelTaskResponse(
                    id=request_data.get("id"),
                    error=UnsupportedOperationError()
                )
            return CancelTaskResponse(
                id=request_data.get("id"),
                error=InternalError(data=str(e))
            )

    def _handle_set_notification(self, request_data: dict) -> SetTaskPushNotificationResponse:
        try:
            request = SetTaskPushNotificationRequest.model_validate(request_data)
            handler = self.handlers.get("tasks/pushNotification/set")
            
            if not handler:
                return SetTaskPushNotificationResponse(
                    id=request.id,
                    error=MethodNotFoundError()
                )

            try:
                # Execute handler (may or may not return something)
                raw_result = handler(request)
                
                # If handler returns nothing - build success response from request params
                if raw_result is None:
                    return SetTaskPushNotificationResponse(
                        id=request.id,
                        result=request.params
                    )
                
                # If handler returns a full response object
                if isinstance(raw_result, SetTaskPushNotificationResponse):
                    return raw_result
                    

            except Exception as e:
                if isinstance(e, JSONRPCError):
                    return SetTaskPushNotificationResponse(
                        id=request.id,
                        error=e
                    )
                return SetTaskPushNotificationResponse(
                    id=request.id,
                    error=InternalError(data=str(e))
                )

        except ValidationError as e:
            return SetTaskPushNotificationResponse(
                id=request_data.get("id"),
                error=InvalidRequestError(data=e.errors())
            )
                      

    def _handle_get_notification(self, request_data: dict) -> GetTaskPushNotificationResponse:
        try:
            request = GetTaskPushNotificationRequest.model_validate(request_data)
            handler = self.handlers.get("tasks/pushNotification/get")
            
            if not handler:
                return GetTaskPushNotificationResponse(
                    id=request.id,
                    error=MethodNotFoundError()
                )
            
            try:
                raw_result = handler(request)
                
                if isinstance(raw_result, GetTaskPushNotificationResponse):
                    return raw_result
                else:
                    # Validate raw_result as TaskPushNotificationConfig
                    config = TaskPushNotificationConfig.model_validate(raw_result)
                    return GetTaskPushNotificationResponse(
                        id=request.id,
                        result=config
                    )
            except ValidationError as e:
                return GetTaskPushNotificationResponse(
                    id=request.id,
                    error=InvalidParamsError(data=e.errors())
                )
            except Exception as e:
                if isinstance(e, JSONRPCError):
                    return GetTaskPushNotificationResponse(
                        id=request.id,
                        error=e
                    )
                return GetTaskPushNotificationResponse(
                    id=request.id,
                    error=InternalError(data=str(e))
                )

        except ValidationError as e:
            return GetTaskPushNotificationResponse(
                id=request_data.get("id"),
                error=InvalidRequestError(data=e.errors())
            )
        except json.JSONDecodeError as e:
            return GetTaskPushNotificationResponse(
                id=request_data.get("id"),
                error=JSONParseError(data=str(e))
            )


    def _normalize_artifacts(self, content: Any) -> List[Artifact]:
        """Handle both A2AResponse content and regular returns"""
        if isinstance(content, Artifact):
            return [content]
        
        if isinstance(content, list):
            # Handle list of artifacts
            if all(isinstance(item, Artifact) for item in content):
                return content
            
            # Handle mixed parts in list
            parts = []
            for item in content:
                if isinstance(item, Artifact):
                    parts.extend(item.parts)
                else:
                    parts.append(self._create_part(item))
            return [Artifact(parts=parts)]
        
        # Handle single part returns
        if isinstance(content, (str, Part, dict)):
            return [Artifact(parts=[self._create_part(content)])]
        
        # Handle raw artifact dicts
        try:
            return [Artifact.model_validate(content)]
        except ValidationError:
            return [Artifact(parts=[TextPart(text=str(content))])]


    def _build_task(
    self,
    content: Any,
    task_id: str,
    session_id: Optional[str] = None,
    default_status: TaskState = TaskState.COMPLETED,
    metadata: Optional[dict] = None
) -> Task:
        """Universal task construction from various return types."""
        if isinstance(content, Task):
            return content
        
        # Handle A2AResponse for sendTask case
        if isinstance(content, A2AResponse):
            status = content.status if isinstance(content.status, TaskStatus) \
                else TaskStatus(state=content.status)
            artifacts = self._normalize_content(content.content)
            return Task(
                id=task_id,
                sessionId=session_id or str(uuid4()),  # Generate if missing
                status=status,
                artifacts=artifacts,
                metadata=metadata or {}
            )

        try:  # Attempt direct validation for dicts
            return Task.model_validate(content)
        except ValidationError:
            pass

        # Fallback to content normalization
        artifacts = self._normalize_content(content)
        return Task(
            id=task_id,
            sessionId=session_id,
            status=TaskStatus(state=default_status),
            artifacts=artifacts,
            metadata=metadata or {}
        )
    
    def _build_task_from_status(self, status: A2AStatus, task_id: str, metadata: dict) -> Task:
        """Convert A2AStatus to a Task with proper cancellation state."""
        return Task(
            id=task_id,
            status=TaskStatus(
                state=TaskState(status.status),
                timestamp=datetime.now()
            ),
            metadata=metadata,
            # Include empty/default values for required fields
            sessionId="",  
            artifacts=[],
            history=[]
        )


    def _normalize_content(self, content: Any) -> List[Artifact]:
        """Handle all content types for both sendTask and getTask cases."""
        if isinstance(content, Artifact):
            return [content]
        
        if isinstance(content, list):
            if all(isinstance(item, Artifact) for item in content):
                return content
            return [Artifact(parts=self._parts_from_mixed(content))]
        
        if isinstance(content, (str, Part, dict)):
            return [Artifact(parts=[self._create_part(content)])]
        
        try:  # Handle raw artifact dicts
            return [Artifact.model_validate(content)]
        except ValidationError:
            return [Artifact(parts=[TextPart(text=str(content))])]

    def _parts_from_mixed(self, items: List[Any]) -> List[Part]:
        """Extract parts from mixed content lists."""
        parts = []
        for item in items:
            if isinstance(item, Artifact):
                parts.extend(item.parts)
            else:
                parts.append(self._create_part(item))
        return parts


    def _create_part(self, item: Any) -> Part:
        """Convert primitive types to proper Part models"""
        if isinstance(item, (TextPart, FilePart, DataPart)):
            return item
        
        if isinstance(item, str):
            return TextPart(text=item)
        
        if isinstance(item, dict):
            try:
                return Part.model_validate(item)
            except ValidationError:
                return TextPart(text=str(item))
        
        return TextPart(text=str(item))
    

    # Response validation helper
    def _validate_response_id(self, response: Union[SendTaskResponse, GetTaskResponse], request) -> Union[SendTaskResponse, GetTaskResponse]:
        if response.result and response.result.id != request.params.id:
            return type(response)(
                id=request.id,
                error=InvalidParamsError(
                    data=f"Task ID mismatch: {response.result.id} vs {request.params.id}"
                )
            )
        return response
    
    # Might refactor this later 
    def _finalize_task_response(self, request: GetTaskRequest, task: Task) -> GetTaskResponse:
        """Final validation and processing for getTask responses."""
        # Validate task ID matches request
        if task.id != request.params.id:
            return GetTaskResponse(
                id=request.id,
                error=InvalidParamsError(
                    data=f"Task ID mismatch: {task.id} vs {request.params.id}"
                )
            )
        
        # Apply history length filtering
        if request.params.historyLength and task.history:
            task.history = task.history[-request.params.historyLength:]
        
        return GetTaskResponse(
            id=request.id,
            result=task
        )
    
    def _finalize_cancel_response(self, request: CancelTaskRequest, task: Task) -> CancelTaskResponse:
        """Final validation and processing for cancel responses."""
        if task.id != request.params.id:
            return CancelTaskResponse(
                id=request.id,
                error=InvalidParamsError(
                    data=f"Task ID mismatch: {task.id} vs {request.params.id}"
                )
            )
        
        # Ensure cancellation-specific requirements are met
        if task.status.state not in [TaskState.CANCELED, TaskState.COMPLETED]:
            return CancelTaskResponse(
                id=request.id,
                error=TaskNotCancelableError()
            )
        
        return CancelTaskResponse(
            id=request.id,
            result=task
        )
    
    
    async def _normalize_subscription_events(self, params: TaskSendParams, events: AsyncGenerator) -> AsyncGenerator[Union[SendTaskStreamingResponse, TaskStatusUpdateEvent, TaskArtifactUpdateEvent], None]:
        artifact_state = defaultdict(lambda: {"index": 0, "last_chunk": False})
    
        async for item in events:
            # Pass through fully formed responses immediately
            if isinstance(item, SendTaskStreamingResponse):
                yield item
                continue

            # Handle protocol status updates
            if isinstance(item, A2AStatus):
                yield TaskStatusUpdateEvent(
                    id=params.id,
                    status=TaskStatus(
                        state=TaskState(item.status),
                        timestamp=datetime.now()
                    ),
                    final=item.final or (item.status.lower() == TaskState.COMPLETED),
                    metadata=item.metadata
                )
            
            # Handle stream content
            elif isinstance(item, (A2AStreamResponse, str, bytes, TextPart, FilePart, DataPart, Artifact, list)):
                # Convert to A2AStreamResponse if needed
                if not isinstance(item, A2AStreamResponse):
                    item = A2AStreamResponse(content=item)

                # Process content into parts
                parts = []
                content = item.content
                
                if isinstance(content, str):
                    parts.append(TextPart(text=content))
                elif isinstance(content, bytes):
                    parts.append(FilePart(file=FileContent(bytes=content)))
                elif isinstance(content, (TextPart, FilePart, DataPart)):
                    parts.append(content)
                elif isinstance(content, Artifact):
                    parts = content.parts
                elif isinstance(content, list):
                    for elem in content:
                        if isinstance(elem, str):
                            parts.append(TextPart(text=elem))
                        elif isinstance(elem, (TextPart, FilePart, DataPart)):
                            parts.append(elem)
                        elif isinstance(elem, Artifact):
                            parts.extend(elem.parts)

                # Track artifact state
                artifact_idx = item.index
                state = artifact_state[artifact_idx]
                
                yield TaskArtifactUpdateEvent(
                    id=params.id,
                    artifact=Artifact(
                        parts=parts,
                        index=artifact_idx,
                        append=item.append or state["index"] == artifact_idx,
                        lastChunk=item.final or state["last_chunk"],
                        metadata=item.metadata
                    )
                )
                
                # Update artifact state tracking
                if item.final:
                    state["last_chunk"] = True
                state["index"] += 1
            
            # Pass through protocol events directly
            elif isinstance(item, (TaskStatusUpdateEvent, TaskArtifactUpdateEvent)):
                yield item
            
            # Handle invalid types
            else:
                yield SendTaskStreamingResponse(
                    jsonrpc="2.0",
                    id=params.id,  # Typically comes from request, but using params.id as fallback
                    error=InvalidParamsError(
                        data=f"Unsupported event type: {type(item).__name__}"
                    )
                )
    

    def configure(self, **kwargs):
        self.server_config.update(kwargs)

    def add_cors_middleware(self, **kwargs):
        self.app.add_middleware(
            CORSMiddleware,
            **{k: v for k, v in kwargs.items() if v is not None}
        )

    def run(self):
        uvicorn.run(
            self.app,
            host=self.server_config["host"],
            port=self.server_config["port"],
            reload=self.server_config["reload"]
        )
