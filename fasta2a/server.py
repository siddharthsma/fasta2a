from typing import Callable, Any, Optional, Dict, Union, List, AsyncGenerator
import json
import inspect
from datetime import datetime
from collections import defaultdict
from fastapi import FastAPI, Request, HTTPException, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse
from pydantic import ValidationError
import uvicorn
from fastapi.responses import StreamingResponse


from .types import (
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
    ContentTypeNotSupportedError,
    InternalError,
    UnsupportedOperationError,
    TaskNotFoundError,
    InvalidParamsError,
    TaskNotCancelableError,
    A2AStatus,
    A2AStreamResponse,
    TaskSendParams,
)

class FastA2A:
    def __init__(self, name: str, **fastapi_kwargs):
        self.name = name
        self.handlers: Dict[str, Callable] = {}
        self.subscriptions: Dict[str, Callable] = {}
        self.app = FastAPI(title=name, **fastapi_kwargs)
        self.router = APIRouter()
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


    def on_send_task(self) -> Callable:
        def decorator(func: Callable[[SendTaskRequest], Any]) -> Callable:
            self.handlers["tasks/send"] = func
            return func
        return decorator

    def on_send_subscribe_task(self) -> Callable:
        def decorator(func: Callable) -> Callable:
            self.subscriptions["tasks/sendSubscribe"] = func
            return func
        return decorator
    
    def task_get(self):
        def decorator(func: Callable[[GetTaskRequest], Task]):
            self.handlers["tasks/get"] = func
            return func
        return decorator
    
    def task_cancel(self):
        def decorator(func: Callable[[CancelTaskRequest], Task]):
            self.handlers["tasks/cancel"] = func
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
                
                # If handler already returns a SendTaskResponse, return it directly
                if isinstance(raw_result, SendTaskResponse):
                    return raw_result

                # Existing processing for other return types
                if isinstance(raw_result, A2AResponse):
                    task_state = raw_result.status.state
                    response_content = raw_result.content
                else:
                    task_state = TaskState.COMPLETED
                    response_content = raw_result

                artifacts = self._normalize_artifacts(response_content)
                
                task = Task(
                    id=request.params.id,
                    sessionId=request.params.sessionId,
                    status=TaskStatus(state=task_state),
                    artifacts=artifacts,
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
                task = handler(request)
                
                # Validate task ID matches request
                if task.id != request.params.id:
                    return GetTaskResponse(
                        id=request.id,
                        error=InvalidParamsError(
                            data=f"Returned task ID {task.id} doesn't match requested ID {request.params.id}"
                        )
                    )
                
                # Apply history length filtering
                if request.params.historyLength and task.history:
                    task.history = task.history[-request.params.historyLength:]
                
                return GetTaskResponse(
                    id=request.id,
                    result=task
                )

            except TaskNotFoundError as e:
                return GetTaskResponse(id=request.id, error=e)
            except ContentTypeNotSupportedError as e:
                return GetTaskResponse(id=request.id, error=e)
            except ValidationError as e:
                return GetTaskResponse(
                    id=request.id,
                    error=InvalidParamsError(data=e.errors())
                )
            except Exception as e:
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
                task = handler(request)
                
                # Validate task ID matches request
                if task.id != request.params.id:
                    return CancelTaskResponse(
                        id=request.id,
                        error=InvalidParamsError(
                            data=f"Task ID mismatch: {task.id} vs {request.params.id}"
                        )
                    )

                # Apply history length filtering if needed
                if request.params.historyLength and task.history:
                    task.history = task.history[-request.params.historyLength:]
                
                return CancelTaskResponse(
                    id=request.id,
                    result=task
                )

            except TaskNotFoundError as e:
                return CancelTaskResponse(id=request.id, error=e)
            except TaskNotCancelableError as e:
                return CancelTaskResponse(id=request.id, error=e)
            except ValidationError as e:
                return CancelTaskResponse(
                    id=request.id,
                    error=InvalidParamsError(data=e.errors())
                )
            except Exception as e:
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
