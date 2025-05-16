# Library imports
from typing import Any, Literal, AsyncIterable, get_origin, get_args
import httpx
import json
from httpx_sse import connect_sse
from inspect import signature, Parameter, iscoroutinefunction
from pydantic import create_model, Field, BaseModel, ValidationError
from typing import Optional, Union

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
    WebhookRequest,
    WebhookResponse,
    Task,
)
from smarta2a.utils.task_request_builder import TaskRequestBuilder


class A2AClient:
    def __init__(self, agent_card: AgentCard = None, url: str = None):
        if agent_card:
            self.url = agent_card.url
        elif url:
            self.url = url
        else:
            pass

    async def send(
        self,
        *,
        id: str,
        role: Literal["user", "agent"] = "user",
        text: str,
        data: dict[str, Any] | None = None,
        file_uri: str | None = None,
        sessionId: str | None = None,
        accepted_output_modes: list[str] | None = None,
        push_notification: PushNotificationConfig | None = None,
        history_length: int | None = None,
        metadata: dict[str, Any] | None = None,
    ):
        """Send a task to another Agent."""
        params = TaskRequestBuilder.build_send_task_request(
            id=id,
            role=role,
            text=text,
            data=data,
            file_uri=file_uri,
            session_id=sessionId, # Need to amend the TaskRequestBuilder at a later time to take sessionId not session_id
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
        """Send to another Agent and receive a stream of responses."""
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

    async def send_to_webhook(
        self,
        webhook_url: str,
        id: str,
        task: Task
    ):
        """Send a task to another Agent"""
        request = WebhookRequest(id=id, result=task)
        return WebhookResponse(**await self._send_webhook_request(webhook_url, request))
        
            
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
    
    async def _send_webhook_request(self, webhook_url: str, request: WebhookRequest) -> dict[str, Any]:
        async with httpx.AsyncClient() as client:
            try:
                # Image generation could take time, adding timeout
                response = await client.post(
                    webhook_url, json=request.model_dump(), timeout=30
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
        """Return metadata for all available tools with minimal inputSchema."""
        tools = []
        tool_names = ['send']  # add other tool names here
        for name in tool_names:
            method = getattr(self, name)
            doc = method.__doc__ or ""
            description = doc.strip().split('\n')[0] if doc else ""
            
            sig = signature(method)
            properties: dict[str, Any] = {}
            required: list[str] = []
            for param_name, param in sig.parameters.items():
                if param_name == 'self':
                    continue
                
                ann = param.annotation
                default = param.default
                
                # Handle Literal types
                if get_origin(ann) is Literal:
                    enum_vals = list(get_args(ann))
                    schema_field: dict[str, Any] = {
                        "title": param_name.replace('_', ' ').title(),
                        "enum": enum_vals
                    }
                    # For Literals we'd typically not mark required if there's a default
                else:
                    # map basic Python types to JSON Schema types
                    type_map = {
                        str: "string",
                        int: "integer",
                        float: "number",
                        bool: "boolean",
                        dict: "object",
                        list: "array",
                        Any: None
                    }
                    json_type = type_map.get(ann, None)
                    schema_field = {"title": param_name.replace('_', ' ').title()}
                    if json_type:
                        schema_field["type"] = json_type
                
                # default vs required
                if default is Parameter.empty:
                    required.append(param_name)
                    # no default key
                else:
                    schema_field["default"] = default
                
                properties[param_name] = schema_field
            
            inputSchema = {
                "title": f"{name}_Arguments",
                "type": "object",
                "properties": properties,
                "required": required,
            }

            tools.append({
                "name": name,
                "description": description,
                "inputSchema": inputSchema
            })

        return tools

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        """Call a tool by name with validated arguments."""
        # 1) lookup
        if not hasattr(self, tool_name):
            raise ValueError(f"Tool {tool_name} not found")
        method = getattr(self, tool_name)

        # 2) build a minimal pydantic model for validation
        sig = signature(method)
        model_fields: dict[str, tuple] = {}

        for param_name, param in sig.parameters.items():
            if param_name == 'self':
                continue

            # annotation
            ann = param.annotation
            if ann is Parameter.empty:
                ann = Any

            # default
            default = param.default
            if default is Parameter.empty:
                # required field
                model_fields[param_name] = (ann, Field(...))
            else:
                # optional field: if default is None, widen annotation
                if default is None and get_origin(ann) is not Union:
                    ann = Optional[ann]
                model_fields[param_name] = (ann, Field(default=default))

        ValidationModel = create_model(
            f"{tool_name}_ValidationModel",
            **model_fields
        )

        # 3) validate (will raise ValidationError on bad args)
        try:
            validated = ValidationModel(**arguments)
        except ValidationError as e:
            # re-raise or wrap as you like
            raise ValueError(f"Invalid arguments for tool {tool_name}: {e}") from e

        validated_args = validated.dict()

        # 4) call
        if iscoroutinefunction(method):
            return await method(**validated_args)
        else:
            return method(**validated_args)
