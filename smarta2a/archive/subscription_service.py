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

        task_id = state.task_id if state else request.params.id or str(uuid4())
        context_history = state.context_history.copy() if state else [request.params.message]
        task_history = state.task_history.copy() if state else [request.params.message]
        metadata = state.metadata.copy() if state else (request.params.metadata or {})

        async def event_stream():
            try:
                events = handler(request, state) if state else handler(request)
                async for ev in self._normalize(request.params, events, context_history.copy(), task_history.copy(), metadata.copy(), task_id):
                    yield f"data: {ev}\n\n"
            except Exception as e:
                err = TaskNotFoundError() if 'not found' in str(e).lower() else InternalError(data=str(e))
                msg = SendTaskStreamingResponse(jsonrpc="2.0", id=request.id, error=err).model_dump_json()
                yield f"data: {msg}\n\n"

        return StreamingResponse(event_stream(), media_type="text/event-stream; charset=utf-8")

    async def _normalize(self, params: TaskSendParams, events: AsyncGenerator, context_history: List[Message], task_history: List[Message], metadata: Dict[str, Any], task_id: str) -> AsyncGenerator[Union[TaskStatusUpdateEvent, TaskArtifactUpdateEvent], None]:
        async for evt in events:
            if isinstance(evt, TaskArtifactUpdateEvent):
                # Create agent message from artifact parts
                agent_message = Message(
                    role="agent",
                    parts=[p for p in evt.artifact.parts],
                    metadata=evt.artifact.metadata
                )
                
                # Update task history (always append)
                task_history.append(agent_message)
                # Update context history using strategy
                new_context_history = self.state_mgr.strategy.update_history(context_history, [agent_message])
                
                # Merge metadata
                new_metadata = {
                    **metadata,
                    **(evt.artifact.metadata or {})
                }

                # Update state store if configured
                if self.state_mgr.store:
                    self.state_mgr.store.update_state(
                        task_id=task_id,
                        state_data=StateData(
                            task_id=task_id,
                            context_history=new_context_history,
                            task_history=task_history,
                            metadata=new_metadata
                        )
                    )

                # Update streaming state
                context_history = new_context_history
                metadata = new_metadata

            yield evt