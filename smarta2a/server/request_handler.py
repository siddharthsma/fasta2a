# Library imports
import json
from typing import Optional, Union, AsyncGenerator
from uuid import uuid4
from datetime import datetime
from collections import defaultdict
from fastapi.responses import StreamingResponse
from sse_starlette.sse import EventSourceResponse

# Local imports
from smarta2a.utils.types import (
    SendTaskRequest,
    SendTaskStreamingRequest,
    GetTaskRequest,
    CancelTaskRequest,
    SetTaskPushNotificationRequest,
    GetTaskPushNotificationRequest,
    SendTaskResponse,
    SendTaskStreamingResponse,
    GetTaskResponse,
    CancelTaskResponse,
    SetTaskPushNotificationResponse,
    GetTaskPushNotificationResponse,
    Task,
    TaskStatus,
    TaskState,
    Message,
    StateData,
    TaskSendParams,
    TaskPushNotificationConfig,
    A2AStatus,
    A2AStreamResponse,
    TextPart,
    FilePart,
    DataPart,
    Artifact,
    FileContent,
    TaskStatusUpdateEvent,
    TaskArtifactUpdateEvent
)
from smarta2a.utils.types import (
    TaskNotFoundError,
    MethodNotFoundError,
    InvalidParamsError,
    InternalError,
    JSONRPCError,
    TaskNotCancelableError
)
from smarta2a.utils.task_builder import TaskBuilder
from smarta2a.server.handler_registry import HandlerRegistry
from smarta2a.server.state_manager import StateManager
from smarta2a.client.a2a_client import A2AClient

class RequestHandler:
    def __init__(self, registry: HandlerRegistry, state_manager: Optional[StateManager] = None):
        self.registry = registry
        self.task_builder = TaskBuilder(default_status=TaskState.COMPLETED)
        self.state_manager = state_manager
        self.a2a_aclient = A2AClient()

    async def handle_send_task(self, request: SendTaskRequest, state_data: Optional[StateData] = None) -> SendTaskResponse:
        try:
            handler = self.registry.get_handler("tasks/send")
            
            if not handler:
                return SendTaskResponse(
                    id=request.id,
                    error=MethodNotFoundError()
                )
            # Get the forward_to_webhook flag from the handler
            forward_to_webhook = handler.forward_to_webhook
            
            # Extract parameters from request
            task_id = request.params.id
            session_id = request.params.sessionId or str(uuid4())
            raw = request.params.message
            user_message = Message.model_validate(raw)
            request_metadata = request.params.metadata or {}
            push_notification_config = request.params.pushNotification
            if state_data:
                task_history = state_data.task.history.copy() or []
                context_history = state_data.context_history.copy() or []
                metadata = state_data.task.metadata or {}
                push_notification_config = push_notification_config or state_data.push_notification_config
            else:
                # There is no state manager, so we need to build a task from scratch
                task = Task(
                    id=task_id,
                    sessionId=session_id,
                    status=TaskStatus(state=TaskState.WORKING),
                    history=[user_message],
                    metadata=request_metadata
                )
                task_history = task.history.copy() 
                metadata = request_metadata.copy()
               
            if state_data:
                # Call handler with state data
                raw_result = await handler(request, state_data)
            else:
                # Call handler without state data
                raw_result = await handler(request)

            # Handle direct SendTaskResponse returns
            if isinstance(raw_result, SendTaskResponse):
                return raw_result

            # Build task with updated history (before agent response)
            # SmartA2A overwrites the artifacts each time a new task is built.
            # This is beause it assumes the last artifact is what matters.
            # Also the the history (derived from the artifacts) contains all the messages anyway
            task = self.task_builder.build(
                content=raw_result,
                task_id=task_id,
                session_id=session_id,  
                metadata=metadata,  
                history=task_history 
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

            # Update Task history with a simple append
            task_history.extend(messages)

            if state_data:
                # Update context history with a strategy - this is the history that will be passed to an LLM call
                history_strategy = self.state_manager.get_history_strategy()
                context_history = history_strategy.update_history(
                    existing_history=context_history,
                    new_messages=messages
                )

            # Update task with final state
            task.history = task_history

            
            # State store update (if enabled)
            if state_data:
                await self.state_manager.update_state(
                    state_data=StateData(
                        task_id=task_id,
                        task=task,
                        context_history=context_history,
                        push_notification_config=push_notification_config if push_notification_config else state_data.push_notification_config,
                    )
                )

            # If push_notification_config is set send the task to the push notification url
            if push_notification_config and forward_to_webhook:
                try:
                    await self.a2a_aclient.send_to_webhook(webhook_url=push_notification_config.url,id=task_id,task=task.model_dump())
                except Exception as e:
                    pass
            

            # Send the task back to the client
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


        
    async def handle_subscribe_task(self, request: SendTaskStreamingRequest, state_data: Optional[StateData] = None) -> Union[EventSourceResponse, SendTaskStreamingResponse]:
    
        handler = self.registry.get_subscription("tasks/sendSubscribe")
        
        if not handler:
            return SendTaskStreamingResponse(
                jsonrpc="2.0",
                id=request.id,
                error=MethodNotFoundError()
            )
        
        # Get the forward_to_webhook flag from the handler
        forward_to_webhook = handler.forward_to_webhook

        # Extract parameters from request
        task_id = request.params.id
        session_id = request.params.sessionId or str(uuid4())
        raw = request.params.message
        user_message = Message.model_validate(raw)
        request_metadata = request.params.metadata or {}
        push_notification_config = request.params.pushNotification

        if state_data:
            task = state_data.task
            task_history = task.history.copy() or []
            context_history = state_data.context_history.copy() or []
            metadata = state_data.task.metadata or {} # Request metadata has already been merged so no need to do it here
            push_notification_config = push_notification_config or state_data.push_notification_config
        else:
            task = Task(
                id=task_id,
                sessionId=session_id,
                status=TaskStatus(state=TaskState.WORKING),
                artifacts=[],
                history=[user_message],
                metadata=request_metadata
            )
            task_history = task.history.copy() 
            metadata = request_metadata


        async def event_generator():
            
            try:
                
                if state_data:
                    raw_events = handler(request, state_data)
                else:
                    raw_events = handler(request)

                normalized_events = self._normalize_subscription_events(request.params, raw_events)

                # Initialize streaming state
                task_stream_history = task_history.copy()
                stream_metadata = metadata.copy()
                if state_data:
                    context_stream_history = context_history.copy()

                # Get history strategy and state store from state manager
                if state_data:
                    history_strategy = self.state_manager.get_history_strategy()

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
                            
                            # Update task history with a simple append
                            new_task_history = task_stream_history + [agent_message]

                            # Update contexthistory using strategy
                            if state_data:
                                new_context_history = history_strategy.update_history(
                                    existing_history=context_stream_history,
                                    new_messages=[agent_message]
                                )
                            
                            # Merge metadata
                            new_metadata = {
                                **stream_metadata,
                                **(item.artifact.metadata or {})
                            }

                            # Update task with new artifact and metadata
                            task.artifacts.append(item.artifact)
                            task.metadata = new_metadata
                            task.history = new_task_history

                            # Update state store if configured
                            if state_data:
                                await self.state_manager.update_state(
                                    state_data=StateData(
                                        task_id=task_id,
                                        task=task,
                                        context_history=new_context_history,
                                    )
                                )

                            # Update streaming state
                            task_stream_history = new_task_history
                            if state_data:
                                context_stream_history = new_context_history
                            stream_metadata = new_metadata

                            # If push_notification_config is set send the task to the push notification url
                            if push_notification_config and forward_to_webhook:
                                try:
                                    self.a2a_aclient.send_to_webhook(webhook_url=push_notification_config.url,id=task_id,task=task)
                                except Exception as e:
                                    pass

                            
                        elif isinstance(item, TaskStatusUpdateEvent):
                            task.status = item.status

                            # Merge metadata
                            new_metadata = {
                                **stream_metadata   
                            }

                            # Update task with new status and metadata
                            task.status = item.status
                            task.metadata = new_metadata

                            # Update state store if configured
                            if state_data:
                                await self.state_manager.update_state(
                                    state_data=StateData(
                                        task_id=task_id,
                                        task=task,
                                        context_history=context_stream_history
                                    )
                                )

                        # Add validation for proper event types
                        else:
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


    def handle_get_task(self, request: GetTaskRequest) -> GetTaskResponse:
    
        # Validate request structure
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

        

    def handle_cancel_task(self, request: CancelTaskRequest) -> CancelTaskResponse:
    
        # Validate request structure
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

    def handle_set_notification(self, request: SetTaskPushNotificationRequest) -> SetTaskPushNotificationResponse:
    
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

                      

    def handle_get_notification(self, request: GetTaskPushNotificationRequest) -> GetTaskPushNotificationResponse:
    
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
    
    
    '''
    Private methods beyond this point
    '''

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