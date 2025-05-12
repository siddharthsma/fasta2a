from typing import Union, Any, Dict
from pydantic import BaseModel, Field, TypeAdapter
from typing import Literal, List, Annotated, Optional
from datetime import datetime
from pydantic import model_validator, ConfigDict, field_serializer, field_validator
from uuid import uuid4
from enum import Enum
from typing_extensions import Self


class TaskState(str, Enum):
    SUBMITTED = "submitted"
    WORKING = "working"
    INPUT_REQUIRED = "input-required"
    COMPLETED = "completed"
    CANCELED = "canceled"
    FAILED = "failed"
    UNKNOWN = "unknown"


class TextPart(BaseModel):
    type: Literal["text"] = "text"
    text: str
    metadata: dict[str, Any] | None = None


class FileContent(BaseModel):
    name: str | None = None
    mimeType: str | None = None
    bytes: str | None = None
    uri: str | None = None

    @model_validator(mode="after")
    def check_content(self) -> Self:
        if not (self.bytes or self.uri):
            raise ValueError("Either 'bytes' or 'uri' must be present in the file data")
        if self.bytes and self.uri:
            raise ValueError(
                "Only one of 'bytes' or 'uri' can be present in the file data"
            )
        return self


class FilePart(BaseModel):
    type: Literal["file"] = "file"
    file: FileContent
    metadata: dict[str, Any] | None = None


class DataPart(BaseModel):
    type: Literal["data"] = "data"
    data: dict[str, Any]
    metadata: dict[str, Any] | None = None


Part = Annotated[Union[TextPart, FilePart, DataPart], Field(discriminator="type")]


class Message(BaseModel):
    role: Literal["user", "agent", "system", "tool"] # Added system role for system messages
    parts: List[Part]
    metadata: dict[str, Any] | None = None


class TaskStatus(BaseModel):
    state: TaskState
    message: Message | None = None
    timestamp: datetime = Field(default_factory=datetime.now)

    @field_serializer("timestamp")
    def serialize_dt(self, dt: datetime, _info):
        return dt.isoformat()


class Artifact(BaseModel):
    name: str | None = None
    description: str | None = None
    parts: List[Part]
    metadata: dict[str, Any] | None = None
    index: int = 0
    append: bool | None = None
    lastChunk: bool | None = None


class Task(BaseModel):
    id: str
    sessionId: str | None = None
    status: TaskStatus
    artifacts: List[Artifact] | None = None
    history: List[Message] | None = None
    metadata: dict[str, Any] | None = None


class TaskStatusUpdateEvent(BaseModel):
    id: str
    status: TaskStatus
    final: bool = False
    metadata: dict[str, Any] | None = None


class TaskArtifactUpdateEvent(BaseModel):
    id: str
    artifact: Artifact    
    metadata: dict[str, Any] | None = None


class AuthenticationInfo(BaseModel):
    model_config = ConfigDict(extra="allow")

    schemes: List[str]
    credentials: str | None = None


class PushNotificationConfig(BaseModel):
    url: str
    token: str | None = None
    authentication: AuthenticationInfo | None = None


class TaskIdParams(BaseModel):
    id: str
    metadata: dict[str, Any] | None = None


class TaskQueryParams(TaskIdParams):
    historyLength: int | None = None


class TaskSendParams(BaseModel):
    id: str
    sessionId: str = Field(default_factory=lambda: uuid4().hex)
    message: Message
    acceptedOutputModes: Optional[List[str]] = None
    pushNotification: PushNotificationConfig | None = None
    historyLength: int | None = None
    metadata: dict[str, Any] | None = None


class TaskPushNotificationConfig(BaseModel):
    id: str
    pushNotificationConfig: PushNotificationConfig


## Custom Mixins

class ContentMixin(BaseModel):
    @property
    def content(self) -> Optional[List[Part]]:
        """Direct access to message parts when available"""
        try:
            # Handle different request types that contain messages
            if hasattr(self.params, 'message'):
                return self.params.message.parts
            if hasattr(self, 'message'):
                return self.message.parts
        except AttributeError:
            pass
        return None

## RPC Messages


class JSONRPCMessage(BaseModel):
    jsonrpc: Literal["2.0"] = "2.0"
    id: int | str | None = Field(default_factory=lambda: uuid4().hex)


class JSONRPCRequest(JSONRPCMessage):
    method: str
    params: dict[str, Any] | None = None


class JSONRPCError(BaseModel):
    code: int
    message: str
    data: Any | None = None


class JSONRPCResponse(JSONRPCMessage):
    result: Any | None = None
    error: JSONRPCError | None = None


class SendTaskRequest(JSONRPCRequest, ContentMixin):
    method: Literal["tasks/send"] = "tasks/send"
    params: TaskSendParams


class SendTaskResponse(JSONRPCResponse):
    result: Task | None = None


class SendTaskStreamingRequest(JSONRPCRequest, ContentMixin):
    method: Literal["tasks/sendSubscribe"] = "tasks/sendSubscribe"
    params: TaskSendParams


class SendTaskStreamingResponse(JSONRPCResponse):
    result: TaskStatusUpdateEvent | TaskArtifactUpdateEvent | None = None


class GetTaskRequest(JSONRPCRequest, ContentMixin):
    method: Literal["tasks/get"] = "tasks/get"
    params: TaskQueryParams


class GetTaskResponse(JSONRPCResponse):
    result: Task | None = None


class CancelTaskRequest(JSONRPCRequest, ContentMixin):
    method: Literal["tasks/cancel",] = "tasks/cancel"
    params: TaskIdParams


class CancelTaskResponse(JSONRPCResponse):
    result: Task | None = None


class SetTaskPushNotificationRequest(JSONRPCRequest, ContentMixin):
    method: Literal["tasks/pushNotification/set",] = "tasks/pushNotification/set"
    params: TaskPushNotificationConfig


class SetTaskPushNotificationResponse(JSONRPCResponse):
    result: TaskPushNotificationConfig | None = None


class GetTaskPushNotificationRequest(JSONRPCRequest, ContentMixin):
    method: Literal["tasks/pushNotification/get",] = "tasks/pushNotification/get"
    params: TaskIdParams


class GetTaskPushNotificationResponse(JSONRPCResponse):
    result: TaskPushNotificationConfig | None = None


class TaskResubscriptionRequest(JSONRPCRequest, ContentMixin):
    method: Literal["tasks/resubscribe",] = "tasks/resubscribe"
    params: TaskIdParams


A2ARequest = TypeAdapter(
    Annotated[
        Union[
            SendTaskRequest,
            GetTaskRequest,
            CancelTaskRequest,
            SetTaskPushNotificationRequest,
            GetTaskPushNotificationRequest,
            TaskResubscriptionRequest,
            SendTaskStreamingRequest,
        ],
        Field(discriminator="method"),
    ]
)

## Error types


class JSONParseError(JSONRPCError):
    code: int = -32700
    message: str = "Invalid JSON payload"
    data: Any | None = None


class InvalidRequestError(JSONRPCError):
    code: int = -32600
    message: str = "Request payload validation error"
    data: Any | None = None


class MethodNotFoundError(JSONRPCError):
    code: int = -32601
    message: str = "Method not found"
    data: None = None


class InvalidParamsError(JSONRPCError):
    code: int = -32602
    message: str = "Invalid parameters"
    data: Any | None = None


class InternalError(JSONRPCError):
    code: int = -32603
    message: str = "Internal error"
    data: Any | None = None


class TaskNotFoundError(JSONRPCError):
    code: int = -32001
    message: str = "Task not found"
    data: None = None


class TaskNotCancelableError(JSONRPCError):
    code: int = -32002
    message: str = "Task cannot be canceled"
    data: None = None


class PushNotificationNotSupportedError(JSONRPCError):
    code: int = -32003
    message: str = "Push Notification is not supported"
    data: None = None


class UnsupportedOperationError(JSONRPCError):
    code: int = -32004
    message: str = "This operation is not supported"
    data: None = None


class ContentTypeNotSupportedError(JSONRPCError):
    code: int = -32005
    message: str = "Incompatible content types"
    data: None = None


class AgentProvider(BaseModel):
    organization: str
    url: str | None = None


class AgentCapabilities(BaseModel):
    streaming: bool = False
    pushNotifications: bool = False
    stateTransitionHistory: bool = False


class AgentAuthentication(BaseModel):
    schemes: List[str]
    credentials: str | None = None


class AgentSkill(BaseModel):
    id: str
    name: str
    description: str | None = None
    tags: List[str] | None = None
    examples: List[str] | None = None
    inputModes: List[str] | None = None
    outputModes: List[str] | None = None


class AgentCard(BaseModel):
    name: str
    description: str | None = None
    url: str
    provider: AgentProvider | None = None
    version: str
    documentationUrl: str | None = None
    capabilities: AgentCapabilities
    authentication: AgentAuthentication | None = None
    defaultInputModes: List[str] = ["text"]
    defaultOutputModes: List[str] = ["text"]
    skills: List[AgentSkill]

    def pretty_print(self, include_separators: bool = False) -> str:
        """Returns formatted string, optionally wrapped in separators"""
        output = []
        output.append(f"Name: {self.name}")
        
        if self.description:
            output.append(f"Description: {self.description}")
            
        output.append(f"URL: {self.url}")
        
        if self.provider:
            output.append(f"Provider Organization: {self.provider.organization}")

        # Capabilities handling
        capabilities = []
        if self.capabilities.streaming:
            capabilities.append("Streaming")
        if self.capabilities.pushNotifications:
            capabilities.append("Push Notifications")
        if self.capabilities.stateTransitionHistory:
            capabilities.append("State Transition History")
        output.append("Capabilities: " + ", ".join(capabilities))
        
        # Skills handling
        skills_output = ["Skills:"]
        for skill in self.skills:
            skills_output.append(f"  {skill.name} [{skill.id}]")
            
            if skill.description:
                skills_output.append(f"    Description: {skill.description}")
                
            if skill.tags:
                skills_output.append(f"    Tags: {', '.join(skill.tags)}")
                
            if skill.examples:
                skills_output.append("    Examples:")
                skills_output.extend([f"      - {ex}" for ex in skill.examples])
                
            if skill.inputModes:
                skills_output.append(f"    Input Modes: {', '.join(skill.inputModes)}")
                
            if skill.outputModes:
                skills_output.append(f"    Output Modes: {', '.join(skill.outputModes)}")
                
            skills_output.append("")

        output.extend(skills_output)
        result = "\n".join(output).strip()
        
        if include_separators:
            return f"---\n{result}\n---"
        return result


class A2AClientError(Exception):
    pass


class A2AClientHTTPError(A2AClientError):
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message
        super().__init__(f"HTTP Error {status_code}: {message}")


class A2AClientJSONError(A2AClientError):
    def __init__(self, message: str):
        self.message = message
        super().__init__(f"JSON Error: {message}")


class MissingAPIKeyError(Exception):
    """Exception for missing API key."""

    pass

"""
Beyond this point, the types are not part of the A2A protocol. 
They are used to help with the implementation of the server.
"""

class A2AResponse(BaseModel):
    status: Union[TaskStatus, str]
    content: Union[str, List[Any], Part, Artifact, List[Part], List[Artifact]]
    sessionId: Optional[str] = None           
    metadata: Optional[dict[str, Any]] = None
    
    @model_validator(mode="after")
    def validate_state(self) -> 'A2AResponse':
        if isinstance(self.status, str):
            try:
                self.status = TaskStatus(state=self.status.lower())
            except ValueError:
                raise ValueError(f"Invalid state: {self.status}")
        return self
    
class A2AStatus(BaseModel):
    status: str
    metadata: dict[str, Any] | None = None
    final: bool = False

    @field_validator('status')
    def validate_status(cls, v):
        valid_states = {e.value for e in TaskState}
        if v.lower() not in valid_states:
            raise ValueError(f"Invalid status: {v}. Valid states: {valid_states}")
        return v.lower()

    @field_validator('final', mode='after')
    def set_final_for_completed(cls, v, values):
        if values.data.get('status') == TaskState.COMPLETED:
            return True
        return v

class A2AStreamResponse(BaseModel):
    content: Union[str, Part, List[Union[str, Part]], Artifact]
    index: int = 0
    append: bool = False
    final: bool = False
    metadata: dict[str, Any] | None = None

class StateData(BaseModel):
    task_id: str
    task: Task
    context_history: List[Message]
    push_notification_config: PushNotificationConfig | None = None

class Tool(BaseModel):
    key: str
    name: str
    description: str
    inputSchema: Dict[str, Any]

'''
The callback request may simply be a message without a result - basically acknowledging the task was completed.
It can also include a result, which is the task that was completed along with the full artifact.
'''
class WebhookRequest(BaseModel):
    id: str
    result: Task | None = None

class WebhookResponse(BaseModel):
    id: str
    result: Task | None = None
    error: str | None = None
