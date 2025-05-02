# Library imports
from typing import Any, Literal, AsyncIterable, get_origin, get_args
import httpx
import json
from httpx_sse import connect_sse
from inspect import signature, Parameter, iscoroutinefunction
from pydantic import create_model, Field, BaseModel

# Local imports
from smarta2a.utils.types import (
    PushNotificationConfig,
    SendTaskStreamingResponse,
    SendTaskResponse,
    SendTaskStreamingRequest,
    SendTaskRequest,
    JSONRPCRequest,
    A2AClientJSONError,
    A2AClientHTTPError,
    AgentCard,
    AuthenticationInfo,
    GetTaskResponse,
    CancelTaskResponse,
    SetTaskPushNotificationResponse,
    GetTaskPushNotificationResponse,
)
from smarta2a.utils.task_request_builder import TaskRequestBuilder


class A2AClient:
    def __init__(self, agent_card: AgentCard = None, url: str = None):
        if agent_card:
            self.url = agent_card.url
        elif url:
            self.url = url
        else:
            raise ValueError("Must provide either agent_card or url")

    async def send(
        self,
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
    ):
        """Send a task to another Agent"""
        params = TaskRequestBuilder.build_send_task_request(
            id=id,
            role=role,
            text=text,
            data=data,
            file_uri=file_uri,
            session_id=session_id,
            accepted_output_modes=accepted_output_modes,
            push_notification=push_notification,
            history_length=history_length,
            metadata=metadata,
        )
        request = SendTaskRequest(params=params)
        return SendTaskResponse(**await self._send_request(request))

    def subscribe(
        self,
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
    ):
        """Send to another Agent and receive a stream of responses"""
        params = TaskRequestBuilder.build_send_task_request(
            id=id,
            role=role,
            text=text,
            data=data,
            file_uri=file_uri,
            session_id=session_id,
            accepted_output_modes=accepted_output_modes,
            push_notification=push_notification,
            history_length=history_length,
            metadata=metadata,
        )
        request = SendTaskStreamingRequest(params=params)
        with httpx.Client(timeout=None) as client:
            with connect_sse(
                client, "POST", self.url, json=request.model_dump()
            ) as event_source:
                try:
                    for sse in event_source.iter_sse():
                        yield SendTaskStreamingResponse(**json.loads(sse.data))
                except json.JSONDecodeError as e:
                    raise A2AClientJSONError(str(e)) from e
                except httpx.RequestError as e:
                    raise A2AClientHTTPError(400, str(e)) from e

    async def get_task(
        self,
        *,
        id: str,
        history_length: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> GetTaskResponse:
        """Get a task from another Agent"""
        req = TaskRequestBuilder.get_task(id, history_length, metadata)
        raw = await self._send_request(req)
        return GetTaskResponse(**raw)

    async def cancel_task(
        self,
        *,
        id: str,
        metadata: dict[str, Any] | None = None,
    ) -> CancelTaskResponse:
        """Cancel a task from another Agent"""
        req = TaskRequestBuilder.cancel_task(id, metadata)
        raw = await self._send_request(req)
        return CancelTaskResponse(**raw)

    async def set_push_notification(
        self,
        *,
        id: str,
        url: str,
        token: str | None = None,
        authentication: AuthenticationInfo | dict[str, Any] | None = None,
    ) -> SetTaskPushNotificationResponse:
        """Set a push notification for a task"""
        req = TaskRequestBuilder.set_push_notification(id, url, token, authentication)
        raw = await self._send_request(req)
        return SetTaskPushNotificationResponse(**raw)

    async def get_push_notification(
        self,
        *,
        id: str,
        metadata: dict[str, Any] | None = None,
    ) -> GetTaskPushNotificationResponse:
        """Get a push notification for a task"""
        req = TaskRequestBuilder.get_push_notification(id, metadata)
        raw = await self._send_request(req)
        return GetTaskPushNotificationResponse(**raw)
        
            
    async def _send_request(self, request: JSONRPCRequest) -> dict[str, Any]:
        async with httpx.AsyncClient() as client:
            try:
                # Image generation could take time, adding timeout
                response = await client.post(
                    self.url, json=request.model_dump(), timeout=30
                )
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as e:
                raise A2AClientHTTPError(e.response.status_code, str(e)) from e
            except json.JSONDecodeError as e:
                raise A2AClientJSONError(str(e)) from e
            
    async def _send_streaming_request(self, request: JSONRPCRequest) -> AsyncIterable[SendTaskStreamingResponse]:
        with httpx.Client(timeout=None) as client:
                with connect_sse(
                    client, "POST", self.url, json=request.model_dump()
                ) as event_source:
                    try:
                        for sse in event_source.iter_sse():
                            yield SendTaskStreamingResponse(**json.loads(sse.data))
                    except json.JSONDecodeError as e:
                        raise A2AClientJSONError(str(e)) from e
                    except httpx.RequestError as e:
                        raise A2AClientHTTPError(400, str(e)) from e
    

    async def list_tools(self) -> list[dict[str, Any]]:
        """Return metadata for all available tools."""
        tools = []
        tool_names = [
            'send'
        ]
        for name in tool_names:
            method = getattr(self, name)
            doc = method.__doc__ or ""
            description = doc.strip().split('\n')[0] if doc else ""
            
            # Generate input schema
            sig = signature(method)
            parameters = sig.parameters
            
            fields = {}
            required = []
            for param_name, param in parameters.items():
                if param_name == 'self':
                    continue
                annotation = param.annotation
                if annotation is Parameter.empty:
                    annotation = Any
                # Handle Literal types
                if get_origin(annotation) is Literal:
                    enum_values = get_args(annotation)
                    annotation = Literal.__getitem__(enum_values)
                # Handle default
                default = param.default
                if default is Parameter.empty:
                    required.append(param_name)
                    field = Field(...)
                else:
                    field = Field(default=default)
                fields[param_name] = (annotation, field)
            
            # Create dynamic Pydantic model
            model = create_model(f"{name}_Input", **fields)
            schema = model.schema()
            
            tools.append({
                'name': name,
                'description': description,
                'inputSchema': schema
            })
        return tools

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        """Call a tool by name with validated arguments."""
        if not hasattr(self, tool_name):
            raise ValueError(f"Tool {tool_name} not found")
        method = getattr(self, tool_name)
        
        # Validate arguments using the same schema as list_tools
        sig = signature(method)
        parameters = sig.parameters
        
        fields = {}
        for param_name, param in parameters.items():
            if param_name == 'self':
                continue
            annotation = param.annotation
            if annotation is Parameter.empty:
                annotation = Any
            # Handle Literal
            if get_origin(annotation) is Literal:
                enum_values = get_args(annotation)
                annotation = Literal.__getitem__(enum_values)
            default = param.default
            if default is Parameter.empty:
                fields[param_name] = (annotation, Field(...))
            else:
                fields[param_name] = (annotation, Field(default=default))
        
        # Create validation model
        model = create_model(f"{tool_name}_ValidationModel", **fields)
        validated_args = model(**arguments).dict()
        
        # Call the method
        if iscoroutinefunction(method):
            return await method(**validated_args)
        else:
            # Note: Synchronous methods (like subscribe) will block the event loop
            return method(**validated_args)
