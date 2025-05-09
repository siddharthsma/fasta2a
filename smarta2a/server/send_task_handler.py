# Library imports
from typing import Optional
from uuid import uuid4
import json
from pydantic import ValidationError

# Local imports
from smarta2a.utils.types import (
    JSONRPCRequest,
    SendTaskRequest,
    SendTaskResponse,
    StateData,
    Task,
    TaskStatus,
    TaskState,
    Message,
    JSONRPCError,
    InvalidRequestError,
    JSONParseError,
    InternalError,
    MethodNotFoundError
)

class SendTaskHandler:

    @classmethod
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
            
            # Extract parameters from request
            task_id = request.params.id
            session_id = request.params.sessionId or str(uuid4())
            raw = request.params.message
            user_message = Message.model_validate(raw)
            request_metadata = request.params.metadata or {}
            
            if state_data:
                task_history = state_data.task.history.copy() or []
                context_history = state_data.context_history.copy() or []
                metadata = state_data.task.metadata or {}

                # Call handler with state data
                raw_result = await handler(request, state_data)

                # Handle direct SendTaskResponse returns
                if isinstance(raw_result, SendTaskResponse):
                    return raw_result

                # Build task with updated history (before agent response)
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

                # Update context history with a strategy - this is the history that will be passed to an LLM call
                history_strategy = self.state_mgr.get_history_strategy()
                context_history = history_strategy.update_history(
                    existing_history=context_history,
                    new_messages=messages
                )

                # Update task with final state
                task.history = task_history

                # State store update (if enabled)
                if self.state_mgr:
                    state_store = self.state_mgr.get_store()
                    state_store.update_state(
                        task_id=task_id,
                        state_data=StateData(
                            task_id=task_id,
                            task=task,
                            context_history=context_history,
                            metadata=metadata  # Use merged metadata
                        )
                    )
                
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

                # Call handler without state data
                raw_result = await handler(request)

                # Handle direct SendTaskResponse returns
                if isinstance(raw_result, SendTaskResponse):
                    return raw_result
                
                # Build task with updated history (before agent response)
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

                # Update task with final state
                task.history = task_history


            return SendTaskResponse(
                    id=request.id,
                    result=task
                )
        except ValidationError as e:
            return SendTaskResponse(
                id=request_data.id,
                error=InvalidRequestError(data=e.errors())
            )
        except json.JSONDecodeError as e:
            return SendTaskResponse(
                id=request_data.id,
                error=JSONParseError(data=str(e))
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