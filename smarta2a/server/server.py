# Library imports
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

# Local imports
from smarta2a.server.handler_registry import HandlerRegistry
from smarta2a.server.state_manager import StateManager
from smarta2a.state_stores.base_state_store import BaseStateStore
from smarta2a.history_update_strategies.history_update_strategy import HistoryUpdateStrategy
from smarta2a.history_update_strategies.append_strategy import AppendStrategy
from smarta2a.utils.task_builder import TaskBuilder

from smarta2a.utils.types import (
    JSONRPCResponse,
    Task,
    Artifact,
    TextPart,
    FilePart,
    FileContent,
    DataPart,
    Part,
    Message,
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
    StateData
)

class SmartA2A:
    def __init__(self, name: str, state_store: Optional[BaseStateStore] = None, history_strategy: HistoryUpdateStrategy = AppendStrategy(), **fastapi_kwargs):
        self.name = name
        self.registry = HandlerRegistry()
        self.state_mgr = StateManager(state_store, history_strategy)
        self.app = FastAPI(title=name, **fastapi_kwargs)
        self.router = APIRouter()
        self.state_store = state_store
        self.history_strategy = history_strategy
        self._setup_routes()
        self.server_config = {
            "host": "0.0.0.0",
            "port": 8000,
            "reload": False
        }
        self.task_builder = TaskBuilder(default_status=TaskState.COMPLETED)

    # Add this method to delegate ASGI calls
    async def __call__(self, scope, receive, send):
        return await self.app(scope, receive, send)
    
    def on_event(self, event_name: str):
        return self.app.on_event(event_name) 
        
    def on_send_task(self):
        def decorator(func: Callable[[SendTaskRequest, Optional[StateData]], Any]) -> Callable:
            self.registry.register("tasks/send", func)
            return func
        return decorator
    
    def on_send_subscribe_task(self):
        def decorator(fn: Callable[[SendTaskStreamingRequest, Optional[StateData]], Any]):
            self.registry.register("tasks/sendSubscribe", fn, subscription=True)
            return fn
        return decorator
    
    def task_get(self):
        def decorator(fn: Callable[[GetTaskRequest], Any]):
            self.registry.register("tasks/get", fn)
            return fn
        return decorator

    def task_cancel(self):
        def decorator(fn: Callable[[CancelTaskRequest], Any]):
            self.registry.register("tasks/cancel", fn)
            return fn
        return decorator

    def set_notification(self):
        def decorator(fn: Callable[[SetTaskPushNotificationRequest], Any]):
            self.registry.register("tasks/pushNotification/set", fn)
            return fn
        return decorator

    def get_notification(self):
        def decorator(fn: Callable[[GetTaskPushNotificationRequest], Any]):
            self.registry.register("tasks/pushNotification/get", fn)
            return fn
        return decorator
    

    def _setup_routes(self):
        @self.app.post("/")    
        async def handle_request(request: Request):
            try:
                data = await request.json()
                req = JSONRPCRequest.model_validate(data)
                #request_obj = JSONRPCRequest(**data)
            except Exception as e:
                return JSONRPCResponse(id=None, error=JSONRPCError(code=-32700, message="Parse error", data=str(e))).model_dump()
                
            response = await self.process_request(req)

            # <-- Accept both SSE‐style responses:
            if isinstance(response, (EventSourceResponse, StreamingResponse)):
                return response

            # <-- Everything else is a normal pydantic JSONRPCResponse
            return response.model_dump()
    

    async def process_request(self, request: JSONRPCRequest) -> JSONRPCResponse:
        
        try:
            method = request.method
            params = request.params
            state_store = self.state_mgr.get_store()
            if method == "tasks/send":
                state_data = self.state_mgr.init_or_get(params.get("sessionId"), params.get("message"), params.get("metadata") or {})
                if state_store:
                    return await self._handle_send_task(request, state_data)
                else:
                    return await self._handle_send_task(request)
            elif method == "tasks/sendSubscribe":
                state_data = self.state_mgr.init_or_get(params.get("sessionId"), params.get("message"), params.get("metadata") or {})
                if state_store:
                    return await self._handle_subscribe_task(request, state_data)
                else:
                    return await self._handle_subscribe_task(request)
            elif method == "tasks/get":
                return self._handle_get_task(request)
            elif method == "tasks/cancel":
                return self._handle_cancel_task(request)
            elif method == "tasks/pushNotification/set":
                return self._handle_set_notification(request)
            elif method == "tasks/pushNotification/get":
                return self._handle_get_notification(request)
            else:
                return JSONRPCResponse(id=request.id, error=MethodNotFoundError()).model_dump() 
        except ValidationError as e:
                return JSONRPCResponse(id=request.id, error=InvalidParamsError(data=e.errors())).model_dump()
        except HTTPException as e:
            err = UnsupportedOperationError() if e.status_code == 405 else InternalError(data=str(e))
            return JSONRPCResponse(id=request.id, error=err).model_dump()


    async def _handle_send_task(self, request_data: JSONRPCRequest, state_data: Optional[StateData] = None) -> SendTaskResponse:
        try:
            # Validate request format
            request = SendTaskRequest.model_validate(request_data.model_dump())
            handler = self.registry.get_handler("tasks/send")
            
            if not handler:
                return SendTaskResponse(
                    id=request.id,
                    error=MethodNotFoundError()
                )
            
            user_message = request.params.message
            request_metadata = request.params.metadata or {}
            if state_data:
                session_id = state_data.sessionId
                existing_history = state_data.history.copy() or []
                metadata = state_data.metadata or {} # Request metadata has already been merged so need to do it here
            else:
                session_id = request.params.sessionId or str(uuid4())
                existing_history = [user_message]
                metadata = request_metadata


            try:

                if state_data:
                    raw_result = await handler(request, state_data)
                else:
                    raw_result = await handler(request)

                # Handle direct SendTaskResponse returns
                if isinstance(raw_result, SendTaskResponse):
                    return raw_result

                # Build task with updated history (before agent response)
                task = self.task_builder.build(
                    content=raw_result,
                    task_id=request.params.id,
                    session_id=session_id,  # Always use generated session ID
                    metadata=metadata,  # Use merged metadata
                    history=existing_history  # History
                )

                # Process messages through strategy
                messages = []
                if task.artifacts:
                    agent_parts = [p for a in task.artifacts for p in a.parts]
                    agent_message = Message(
                        role="agent",
                        parts=agent_parts,
                        metadata=task.metadata
                    )
                    messages.append(agent_message)

                final_history = self.history_strategy.update_history(
                    existing_history=existing_history,
                    new_messages=messages
                )

                # Update task with final state
                task.history = final_history

                # State store update (if enabled)
                if self.state_store:
                    self.state_store.update_state(
                        session_id=session_id,
                        state_data=StateData(
                            sessionId=session_id,
                            history=final_history,
                            metadata=metadata  # Use merged metadata
                        )
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

        
    async def _handle_subscribe_task(self, request_data: JSONRPCRequest, state_data: Optional[StateData] = None) -> Union[EventSourceResponse, SendTaskStreamingResponse]:
        try:
            request = SendTaskStreamingRequest.model_validate(request_data.model_dump())
            #handler = self.subscriptions.get("tasks/sendSubscribe")
            handler = self.registry.get_subscription("tasks/sendSubscribe")
            
            if not handler:
                return SendTaskStreamingResponse(
                    jsonrpc="2.0",
                    id=request.id,
                    error=MethodNotFoundError()
                )
            
            user_message = request.params.message
            request_metadata = request.params.metadata or {}
            if state_data:
                session_id = state_data.sessionId
                existing_history = state_data.history.copy() or []
                metadata = state_data.metadata or {} # Request metadata has already been merged so need to do it here
            else:
                session_id = request.params.sessionId or str(uuid4())
                existing_history = [user_message]
                metadata = request_metadata


            async def event_generator():
                
                try:
                    
                    if state_data:
                        raw_events = handler(request, state_data)
                    else:
                        raw_events = handler(request)

                    normalized_events = self._normalize_subscription_events(request.params, raw_events)

                    # Initialize streaming state
                    stream_history = existing_history.copy()
                    stream_metadata = metadata.copy()

                    async for item in normalized_events:
                        try:

                            # Process artifact updates
                            if isinstance(item, TaskArtifactUpdateEvent):
                                # Create agent message from artifact parts
                                agent_message = Message(
                                    role="agent",
                                    parts=[p for p in item.artifact.parts],
                                    metadata=item.artifact.metadata
                                )
                                
                                # Update history using strategy
                                new_history = self.history_strategy.update_history(
                                    existing_history=stream_history,
                                    new_messages=[agent_message]
                                )
                                
                                # Merge metadata
                                new_metadata = {
                                    **stream_metadata,
                                    **(item.artifact.metadata or {})
                                }

                                # Update state store if configured
                                if self.state_store:
                                    self.state_store.update_state(
                                        session_id=session_id,
                                        state_data=StateData(
                                            sessionId=session_id,
                                            history=new_history,
                                            metadata=new_metadata
                                        )
                                    )

                                # Update streaming state
                                stream_history = new_history
                                stream_metadata = new_metadata

                                
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


    def _handle_get_task(self, request_data: JSONRPCRequest) -> GetTaskResponse:
        try:
            # Validate request structure
            request = GetTaskRequest.model_validate(request_data.model_dump())
            handler = self.registry.get_handler("tasks/get")
            
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
                task = self.task_builder.build(
                    content=raw_result,
                    task_id=request.params.id,
                    metadata=getattr(raw_result, "metadata", {}) or {}
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
        

    def _handle_cancel_task(self, request_data: JSONRPCRequest) -> CancelTaskResponse:
        try:
            # Validate request structure
            request = CancelTaskRequest.model_validate(request_data.model_dump())
            handler = self.registry.get_handler("tasks/cancel")
            
            if not handler:
                return CancelTaskResponse(
                    id=request.id,
                    error=MethodNotFoundError()
                )

            try:
                raw_result = handler(request)
            
                cancel_task_builder = TaskBuilder(default_status=TaskState.CANCELED)
                # Handle direct CancelTaskResponse returns
                if isinstance(raw_result, CancelTaskResponse):
                    return self._validate_response_id(raw_result, request)

                # Handle A2AStatus returns
                if isinstance(raw_result, A2AStatus):
                    task = cancel_task_builder.normalize_from_status(
                        status=raw_result.status,
                        task_id=request.params.id,
                        metadata=getattr(raw_result, "metadata", {}) or {}
                    )
                else:
                    # Existing processing for other return types
                    task = cancel_task_builder.build(
                        content=raw_result,
                        task_id=request.params.id,
                        metadata=getattr(raw_result, "metadata", {}) or {}
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

    def _handle_set_notification(self, request_data: JSONRPCRequest) -> SetTaskPushNotificationResponse:
        try:
            request = SetTaskPushNotificationRequest.model_validate(request_data.model_dump())
            handler = self.registry.get_handler("tasks/pushNotification/set")
            
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
                      

    def _handle_get_notification(self, request_data: JSONRPCRequest) -> GetTaskPushNotificationResponse:
        try:
            request = GetTaskPushNotificationRequest.model_validate(request_data.model_dump())
            handler = self.registry.get_handler("tasks/pushNotification/get")
            
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
