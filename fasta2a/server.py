from typing import Callable, Any, Optional, Dict, Union, List
from fastapi import FastAPI, Request, HTTPException, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError
import uvicorn

from .types import (
    JSONRPCResponse,
    TaskSendParams,
    Task,
    Artifact,
    TextPart,
    FilePart,
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
    TaskQueryParams,
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
            
            response = self.process_request(request_obj.model_dump())
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

    def process_request(self, request_data: dict) -> JSONRPCResponse:
        try:
            method = request_data.get("method")
            if method == "tasks/send":
                return self._handle_send_task(request_data)
            elif method == "tasks/sendSubscribe":
                return self._handle_subscribe_task(request_data)
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
            request = SendTaskRequest.model_validate(request_data)
            handler = self.handlers.get("tasks/send")
            
            if not handler:
                return SendTaskResponse(
                    id=request_data.get("id"),
                    error=JSONRPCError(code=-32601, message="Handler not registered")
                )

            raw_result = handler(request)
            params = request.params

            # Handle A2AResponse or default to completed
            if isinstance(raw_result, A2AResponse):
                task_state = raw_result.state
                response_content = raw_result.content
            else:
                task_state = TaskState.COMPLETED
                response_content = raw_result

            artifacts = self._normalize_artifacts(response_content)
            
            task = Task(
                id=params.id,
                sessionId=params.sessionId,
                status=TaskStatus(state=task_state),
                artifacts=artifacts,
                metadata=params.metadata
            )
            
            return SendTaskResponse(id=request_data.get("id"), result=task)
        
        except Exception as e:
            return SendTaskResponse(
                id=request_data.get("id"),
                error=JSONRPCError(code=-32000, message="Server error", data=str(e))
            )
        
    def _handle_get_task(self, request_data: dict) -> GetTaskResponse:
        try:
            # Validate request format
            request = GetTaskRequest.model_validate(request_data)
            handler = self.handlers.get("tasks/get")
            
            if not handler:
                return GetTaskResponse(
                    id=request.id,
                    error=JSONRPCError(
                        code=-32601,
                        message="Get task handler not registered"
                    )
                )

            # Execute user handler
            task = handler(request)
            
            # Validate returned task matches request
            if task.id != request.params.id:
                raise ValueError(f"Task ID mismatch: {task.id} vs {request.params.id}")
            
            # Apply history length filtering
            if request.params.historyLength and task.history:
                task.history = task.history[-request.params.historyLength:]
            
            return GetTaskResponse(
                id=request.id,
                result=task
            )

        except Exception as e:
            return GetTaskResponse(
                id=request_data.get("id"),
                error=JSONRPCError(
                    code=-32000,
                    message="Failed to retrieve task",
                    data=str(e)
                )
            )
        

    def _handle_cancel_task(self, request_data: dict) -> CancelTaskResponse:
        try:
            # Validate request format
            request = CancelTaskRequest.model_validate(request_data)
            handler = self.handlers.get("tasks/cancel")
            
            if not handler:
                return CancelTaskResponse(
                    id=request.id,
                    error=JSONRPCError(
                        code=-32601,
                        message="Cancel task handler not registered"
                    )
                )

            # Execute user handler
            task = handler(request)
            
            # Validate returned task matches request
            if task.id != request.params.id:
                raise ValueError(f"Task ID mismatch: {task.id} vs {request.params.id}")
            
            # Apply history length filtering
            if request.params.historyLength and task.history:
                task.history = task.history[-request.params.historyLength:]
            
            return CancelTaskResponse(
                id=request.id,
                result=task
            )

        except Exception as e:
            return CancelTaskResponse(
                id=request_data.get("id"),
                error=JSONRPCError(
                    code=-32000,
                    message="Failed to retrieve task",
                    data=str(e)
                )
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
        if isinstance(item, (TextPart, FilePart)):
            return item
        
        if isinstance(item, str):
            return TextPart(text=item)
        
        if isinstance(item, dict):
            try:
                return Part.model_validate(item)
            except ValidationError:
                return TextPart(text=str(item))
        
        return TextPart(text=str(item))
    

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

    def _error_response(self, request_id: Any, code: int, message: str, data: Any = None):
        return JSONRPCResponse(
            id=request_id,
            error=JSONRPCError(
                code=code,
                message=message,
                data=data
            )
        )