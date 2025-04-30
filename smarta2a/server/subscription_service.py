# Library imports
from typing import Optional, List, Dict, Any, AsyncGenerator, Union
from datetime import datetime
from collections import defaultdict
from uuid import uuid4
from fastapi.responses import StreamingResponse
from sse_starlette.sse import EventSourceResponse

# Local imports
from smarta2a.server.handler_registry import HandlerRegistry
from smarta2a.server.state_manager import StateManager
from smarta2a.utils.types import (
    Message, StateData, SendTaskStreamingRequest, SendTaskStreamingResponse,
    TaskSendParams, A2AStatus, A2AStreamResponse, TaskStatusUpdateEvent,
    TaskStatus, TaskState, TaskArtifactUpdateEvent, Artifact, TextPart,
    FilePart, DataPart, FileContent, MethodNotFoundError, TaskNotFoundError,
    InternalError
)

class SubscriptionService:
    def __init__(self, registry: HandlerRegistry, state_mgr: StateManager):
        self.registry = registry
        self.state_mgr = state_mgr

    async def subscribe(self, request: SendTaskStreamingRequest, state: Optional[StateData]) -> StreamingResponse:
        handler = self.registry.get_subscription("tasks/sendSubscribe")
        if not handler:
            err = SendTaskStreamingResponse(jsonrpc="2.0", id=request.id, error=MethodNotFoundError()).model_dump_json()
            return EventSourceResponse(err)

        session_id = state.sessionId if state else request.params.sessionId or str(uuid4())
        history = state.history.copy() if state else [request.params.message]
        metadata = state.metadata.copy() if state else (request.params.metadata or {})

        async def event_stream():
            try:
                events = handler(request, state) if state else handler(request)
                async for ev in self._normalize(request.params, events, history.copy(), metadata.copy(), session_id):
                    yield f"data: {ev}\n\n"
            except Exception as e:
                err = TaskNotFoundError() if 'not found' in str(e).lower() else InternalError(data=str(e))
                msg = SendTaskStreamingResponse(jsonrpc="2.0", id=request.id, error=err).model_dump_json()
                yield f"data: {msg}\n\n"

        return StreamingResponse(event_stream(), media_type="text/event-stream; charset=utf-8")

    async def _normalize(
        self,
        params: TaskSendParams,
        events: AsyncGenerator,
        history: List[Message],
        metadata: Dict[str, Any],
        session_id: str
    ) -> AsyncGenerator[str, None]:
        artifact_state = defaultdict(lambda: {"index": 0, "last_chunk": False})
        async for item in events:
            if isinstance(item, SendTaskStreamingResponse):
                yield item.model_dump_json()
                continue

            if isinstance(item, A2AStatus):
                te = TaskStatusUpdateEvent(
                    id=params.id,
                    status=TaskStatus(state=TaskState(item.status), timestamp=datetime.now()),
                    final=item.final or (item.status.lower() == TaskState.COMPLETED),
                    metadata=item.metadata
                )
                yield SendTaskStreamingResponse(jsonrpc="2.0", id=params.id, result=te).model_dump_json()
                continue

            content_item = item
            if not isinstance(item, A2AStreamResponse):
                content_item = A2AStreamResponse(content=item)

            parts: List[Union[TextPart, FilePart, DataPart]] = []
            cont = content_item.content
            if isinstance(cont, str): parts.append(TextPart(text=cont))
            elif isinstance(cont, bytes): parts.append(FilePart(file=FileContent(bytes=cont)))
            elif isinstance(cont, (TextPart, FilePart, DataPart)): parts.append(cont)
            elif isinstance(cont, Artifact): parts.extend(cont.parts)
            elif isinstance(cont, list):
                for elem in cont:
                    if isinstance(elem, str): parts.append(TextPart(text=elem))
                    elif isinstance(elem, (TextPart, FilePart, DataPart)): parts.append(elem)
                    elif isinstance(elem, Artifact): parts.extend(elem.parts)

            idx = content_item.index
            state = artifact_state[idx]
            evt = TaskArtifactUpdateEvent(
                id=params.id,
                artifact=Artifact(
                    parts=parts,
                    index=idx,
                    append=content_item.append or (state["index"] == idx),
                    lastChunk=content_item.final or state["last_chunk"],
                    metadata=content_item.metadata
                )
            )
            if content_item.final:
                state["last_chunk"] = True
            state["index"] += 1

            agent_msg = Message(role="agent", parts=evt.artifact.parts, metadata=evt.artifact.metadata)
            new_hist = self.state_mgr.strategy.update_history(history, [agent_msg])
            metadata = {**metadata, **(evt.artifact.metadata or {})}
            self.state_mgr.update(StateData(session_id, new_hist, metadata))
            history = new_hist

            yield SendTaskStreamingResponse(jsonrpc="2.0", id=params.id, result=evt).model_dump_json()